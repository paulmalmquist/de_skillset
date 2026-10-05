from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .demo import demo_bundle, CASES
from .evidence import EvidenceBundle, evaluate
from .evals import run_evaluations
from .manifest import audit_manifest
from .modeling import ModelSpec, scaffold
from .policy import load_policy
from .reconcile import reconcile, trace_stages
from .sql_audit import audit_sql, parse_query


def read_json(path):
    return json.loads(Path(path).read_text())


def main(argv=None):
    parser = argparse.ArgumentParser(description="Flightcheck: evidence-first data engineering")
    parser.add_argument("--policy", help="Versioned policy YAML (uses example defaults when omitted)")
    parser.add_argument("--out", help="Write JSON result to this file")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    sql = sub.add_parser("audit-sql")
    sql.add_argument("path")
    sql.add_argument("--layer", default="consumer", choices=["source", "staging", "intermediate", "mart", "serving", "consumer"])
    manifest = sub.add_parser("audit-manifest")
    manifest.add_argument("path")
    demo = sub.add_parser("demo")
    demo.add_argument("--case", choices=list(CASES), default="masked-loss")
    evidence = sub.add_parser("evidence")
    evidence.add_argument("path")
    diff = sub.add_parser("diff")
    diff.add_argument("left")
    diff.add_argument("right")
    diff.add_argument("--keys", required=True, help="Comma-separated grain columns")
    trace = sub.add_parser("trace")
    trace.add_argument("path")
    trace.add_argument("--keys", required=True)
    model = sub.add_parser("scaffold")
    model.add_argument("path")
    model.add_argument("--directory", required=True, help="New output directory; existing files are never overwritten")
    sub.add_parser("eval")
    bq = sub.add_parser("bigquery-dry-run")
    bq.add_argument("path")
    bq.add_argument("--project", required=True)
    bq.add_argument("--location", required=True)
    args = parser.parse_args(argv)
    policy = load_policy(args.policy)
    if args.command == "serve":
        if args.host not in {"127.0.0.1", "localhost", "::1"} and not os.getenv("FLIGHTCHECK_TOKEN"):
            parser.error("Set FLIGHTCHECK_TOKEN before binding a non-loopback interface.")
        import uvicorn
        from .server import create_app
        uvicorn.run(create_app(policy_path=args.policy), host=args.host, port=args.port)
        return 0
    try:
        if args.command == "audit-sql":
            result = audit_sql(Path(args.path).read_text(), args.layer, policy, args.path)
        elif args.command == "audit-manifest":
            result = audit_manifest(read_json(args.path), policy)
        elif args.command == "demo":
            result = evaluate(demo_bundle(args.case), policy)
        elif args.command == "evidence":
            bundle = EvidenceBundle.model_validate(read_json(args.path))
            bundle.provenance = "imported-unattested"
            result = evaluate(bundle, policy)
        elif args.command == "diff":
            result = reconcile(read_json(args.left), read_json(args.right), args.keys.split(","))
        elif args.command == "trace":
            result = trace_stages(read_json(args.path), args.keys.split(","))
        elif args.command == "scaffold":
            result = scaffold(ModelSpec.model_validate(read_json(args.path)))
            if result["files"]:
                output = Path(args.directory)
                if output.exists():
                    raise ValueError("Output directory already exists; use a new directory.")
                for name, content in result["files"].items():
                    path = output / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content)
            result["status"] = result["assessment"]["status"]
        elif args.command == "eval":
            result = run_evaluations()
        else:
            sql = Path(args.path).read_text()
            parse_query(sql, "bigquery")
            from google.cloud import bigquery
            client = bigquery.Client(project=args.project, location=args.location)
            job = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
            result = {"status": "dry_run_only", "project": args.project, "location": args.location,
                      "estimated_bytes": job.total_bytes_processed, "statement_type": job.statement_type,
                      "scope": "A dry run estimates/validates SQL. It does not prove row-level correctness or source freshness."}
        encoded = json.dumps(result, indent=2, allow_nan=False)
        if args.out:
            path = Path(args.out)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(encoded + "\n")
        print(encoded)
        return 1 if result.get("status") in {"blocked", "mismatch", "inconclusive", "failed"} or result.get("complete") is False else 0
    except (ValueError, OSError, ImportError, KeyError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
