from __future__ import annotations

import hmac
import io
import json
import os
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import Field

from .common import StrictModel
from .demo import CASES, demo_bundle
from .evidence import EvidenceBundle, evaluate, GATES
from .evals import run_evaluations
from .handoff import handoff
from .manifest import audit_manifest, impact
from .modeling import ModelSpec, scaffold
from .policy import load_policy
from .reconcile import reconcile, trace_stages
from .sql_audit import audit_sql
from .store import RunStore

PACKAGE = Path(__file__).parent


class SQLRequest(StrictModel):
    sql: str = Field(min_length=1, max_length=200000)
    layer: str = "consumer"
    title: str = Field(default="SQL review", max_length=200)


class DiffRequest(StrictModel):
    left: list[dict] = Field(max_length=50000)
    right: list[dict] = Field(max_length=50000)
    keys: list[str] = Field(min_length=1)
    tolerances: dict[str, float] = Field(default_factory=dict)


def create_app(db_path=None, policy_path=None):
    app = FastAPI(title="Flightcheck · #DATA", version="0.1.0")
    store = RunStore(db_path)
    policy = load_policy(policy_path or os.getenv("FLIGHTCHECK_POLICY"))
    token = os.getenv("FLIGHTCHECK_TOKEN", "")
    allowed_hosts = os.getenv("FLIGHTCHECK_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
    if not token and any(h.strip() not in {"localhost", "127.0.0.1", "[::1]"} for h in allowed_hosts):
        raise ValueError("A token is required for non-loopback allowed hosts")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[h.strip() for h in allowed_hosts])

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if not token and request.client and request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse({"detail": "A token is required for remote clients."}, status_code=403)
        if request.url.path.startswith("/api/") and token:
            header = request.headers.get("Authorization", "")
            supplied = header[7:] if header.startswith("Bearer ") else ""
            if not hmac.compare_digest(supplied.encode(), token.encode()):
                return JSONResponse({"detail": "A valid access token is required."}, status_code=401)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Cross-origin writes are disabled."}, status_code=403)
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 10 * 1024 * 1024:
                    return JSONResponse({"detail": "Request exceeds the 10 MiB limit."}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def invalid(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/bootstrap")
    def bootstrap():
        return {"cases": CASES, "gates": GATES, "policy": policy.model_dump(mode="json"), "policy_hash": policy.hash,
                "catalog": json.loads((PACKAGE / "data/catalog.json").read_text()),
                "model_example": json.loads((PACKAGE / "data/model-example.json").read_text()),
                "manifest_example": json.loads((PACKAGE / "data/manifest-example.json").read_text())}

    @app.post("/api/demo/{case}")
    def demo(case: str):
        bundle = demo_bundle(case)
        return store.save("investigation", bundle.title, evaluate(bundle, policy))

    @app.post("/api/evidence")
    def evidence(bundle: EvidenceBundle):
        bundle.provenance = "imported-unattested"
        return store.save("investigation", bundle.title, evaluate(bundle, policy))

    @app.post("/api/audit/sql")
    def sql_audit(body: SQLRequest):
        return store.save("sql", body.title, audit_sql(body.sql, body.layer, policy, body.title))

    @app.post("/api/audit/manifest")
    def manifest_audit(body: dict):
        return store.save("manifest", "dbt lineage audit", audit_manifest(body, policy))

    @app.get("/api/runs/{run_id}/impact/{node_id:path}")
    def downstream(run_id: str, node_id: str):
        run = get_run(run_id)
        if run.get("kind") != "manifest":
            raise HTTPException(422, "Select a manifest audit")
        return {"descendants": impact(run, node_id)}

    @app.post("/api/reconcile")
    def diff(body: DiffRequest):
        return store.save("reconcile", "Record comparison", reconcile(**body.model_dump()))

    @app.post("/api/models")
    def models(spec: ModelSpec):
        result = scaffold(spec)
        return store.save("model", spec.name, {**result, "status": result["assessment"]["status"]})

    @app.post("/api/evaluations")
    def evaluations():
        return store.save("evaluations", "Synthetic regression suite", run_evaluations())

    @app.get("/api/runs")
    def runs():
        return store.list()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        result = store.get(run_id)
        if result is None:
            raise HTTPException(404, "Run not found")
        return result

    @app.get("/api/runs/{run_id}/handoff", response_class=PlainTextResponse)
    def export_handoff(run_id: str):
        return handoff(get_run(run_id))

    @app.get("/api/runs/{run_id}/scaffold.zip")
    def download_scaffold(run_id: str):
        run = get_run(run_id)
        if not run.get("files"):
            raise HTTPException(422, "This run has no generated model files")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in run["files"].items():
                archive.writestr(name, content)
        return Response(buffer.getvalue(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="dbt-model-scaffold.zip"'})

    @app.get("/")
    def index():
        return FileResponse(PACKAGE / "web/index.html")

    app.mount("/static", StaticFiles(directory=PACKAGE / "web"), name="static")
    return app
