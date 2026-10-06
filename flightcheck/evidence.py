from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import Field

from .common import StrictModel, digest, now_iso
from .policy import Policy
from .reconcile import reconcile, trace_stages


class Context(StrictModel):
    environment: str = Field(min_length=1)
    project: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    principal: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)


class Control(StrictModel):
    query_id: str = Field(min_length=1)
    context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    succeeded: bool
    expected: int = Field(gt=0)
    actual: int = Field(ge=0)


class Population(StrictModel):
    definition: str = Field(min_length=10)
    population_id: str = Field(min_length=3)
    total_rows: int = Field(ge=0)
    extraction_complete: bool
    source_window_complete: bool


class Observation(StrictModel):
    context: Context
    expected_context: Context
    sql_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    query_id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    observed_at: datetime
    data_as_of: datetime
    control: Control
    rows: list[dict] = Field(max_length=50000)
    population: Population | None = None


class Stage(StrictModel):
    name: str = Field(min_length=1)
    rows: list[dict] = Field(max_length=50000)


class EvidenceBundle(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    provenance: Literal["synthetic-executed", "imported-unattested"] = "imported-unattested"
    left: Observation
    right: Observation
    keys: list[str] = Field(min_length=1)
    tolerances: dict[str, float] = Field(default_factory=dict)
    stages: list[Stage] = Field(default_factory=list, max_length=50)
    candidate_commit: str | None = Field(default=None, pattern=r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
    manifest_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


GATES = [
    ("control", "Control query first", "Prove that the connection can return a known result."),
    ("freshness", "Freshness before inference", "Verify source watermarks and evidence age."),
    ("authority", "Ask the owner of the fact", "Resolve relation, identity, environment, and snapshot."),
    ("records", "Diff records, not counts", "Compare keys, values, nulls, and multiplicity."),
    ("isolate", "Isolate, then bisect", "Locate the first observed join or filter divergence."),
]


def evaluate(bundle: EvidenceBundle, policy=None, now=None):
    policy = policy or Policy()
    now = now or datetime.now(timezone.utc)
    gates = [{"id": k, "index": i, "title": title, "description": detail, "status": "not_run", "detail": "Waiting for prerequisite gates."}
             for i, (k, title, detail) in enumerate(GATES)]
    result = {"title": bundle.title, "provenance": bundle.provenance, "created_at": now_iso(),
              "policy_hash": policy.hash, "input_hash": digest(bundle.model_dump(mode="json")),
              "gates": gates, "status": "blocked", "diff": None, "trace": None,
              "certified": False, "scope": "Evidence review only. Hashes identify inputs; they do not attest that imported observations are truthful."}
    sides = (("left", bundle.left), ("right", bundle.right))
    imported = bundle.provenance == "imported-unattested"
    coverage = []
    for label, obs in sides:
        p = obs.population
        if p is None or not p.extraction_complete or not p.source_window_complete or p.total_rows != len(obs.rows):
            coverage.append(f"{label}: full extraction and source-window completeness are not established")
    if bundle.left.population and bundle.right.population:
        if (bundle.left.population.population_id, bundle.left.population.definition) != (bundle.right.population.population_id, bundle.right.population.definition):
            coverage.append("Compared populations have different definitions/identifiers")
    result["coverage"] = {"complete": not coverage, "issues": coverage, "attested": False}
    result["candidate_commit"] = bundle.candidate_commit
    result["manifest_hash"] = bundle.manifest_hash
    def mark(index, status, detail):
        if imported and index <= 2 and status == "pass":
            status, detail = "unverified", "Reported only; warehouse execution is not authenticated. " + detail
        gates[index].update(status=status, detail=detail)
    for label, obs in sides:
        control = obs.control
        if not control.succeeded or control.actual != control.expected or control.context_hash != digest(obs.context.model_dump()):
            mark(0, "fail", f"{label}: known-result control failed or used a different query context. Absence is not evidence.")
            return result
    mark(0, "pass", "Both controls returned the expected positive result in their observation context.")
    for label, obs in sides:
        if obs.observed_at.tzinfo is None or obs.data_as_of.tzinfo is None:
            mark(1, "fail", f"{label}: timestamps must include timezone offsets.")
            return result
        evidence_age = (now - obs.observed_at).total_seconds() / 3600
        data_age = (now - obs.data_as_of).total_seconds() / 3600
        if evidence_age < -5 / 60 or data_age < -5 / 60 or obs.data_as_of > obs.observed_at or evidence_age > policy.max_evidence_age_hours or data_age > policy.max_freshness_hours:
            mark(1, "fail", f"{label}: stale or inconsistent timestamps. Evidence age {evidence_age:.2f}h; data age {data_age:.2f}h.")
            return result
    mark(1, "pass", "Both evidence timestamps and source watermarks are within the configured windows.")
    for label, obs in sides:
        if obs.context != obs.expected_context:
            mark(2, "fail", f"{label}: the resolved context differs from the declared context.")
            return result
    for field in ("environment", "project", "principal", "snapshot_id"):
        if getattr(bundle.left.context, field) != getattr(bundle.right.context, field):
            mark(2, "fail", f"Comparison contexts disagree on {field}. Define an equivalent snapshot before comparing.")
            return result
    mark(2, "pass", "Resolved contexts match declarations and share environment, project, principal, and snapshot.")
    diff = reconcile(bundle.left.rows, bundle.right.rows, bundle.keys, bundle.tolerances)
    result["diff"] = diff
    if diff["status"] == "equal":
        mark(3, "pass", f"{diff['matched_unique_keys']} unique records agree at the declared grain and tolerances.")
        mark(4, "not_applicable", "No record discrepancy was found in this comparison scope.")
        result["status"] = "incomplete" if coverage else "unverified" if imported else "ready_for_review"
        if coverage:
            mark(3, "needs_evidence", "Supplied rows agree, but population coverage is incomplete: " + "; ".join(coverage))
    elif diff["status"] == "inconclusive":
        mark(3, "fail", "Both result sets are empty; no positive business population was compared.")
    else:
        mark(3, "fail", "Record reconciliation found differences; equal row counts do not establish parity.")
        result["status"] = "mismatch"
        if len(bundle.stages) >= 2:
            project = lambda rows: [{k: row[k] for k in bundle.keys if k in row} for row in rows]
            # Trace boundaries must belong to this comparison; duplicate populations are compared as multisets.
            from collections import Counter
            from .reconcile import canonical
            same = lambda a, b: Counter(map(canonical, project(a))) == Counter(map(canonical, project(b)))
            if not same(bundle.stages[0].rows, bundle.left.rows) or not same(bundle.stages[-1].rows, bundle.right.rows):
                mark(4, "needs_evidence", "Trace endpoints do not match this comparison's key populations.")
                return result
            result["trace"] = trace_stages([s.model_dump() for s in bundle.stages], bundle.keys)
            mark(4, "pass" if result["trace"]["first_divergence"] else "needs_evidence",
                 "First observed key divergence located; investigate the mechanism." if result["trace"]["first_divergence"] else "Key sets are stable; bisect the changed value expression with a record witness.")
        else:
            mark(4, "needs_evidence", "Materialize CTE/join/filter stages and compare a failing key at each boundary.")
    return result
