"""Fail-closed static candidate checks; never a warehouse attestation or release approval."""
from datetime import datetime, timezone

from .common import digest, finding, report
from .manifest import audit_manifest
from .policy import Policy
from .sql_audit import audit_sql


def check_candidate(manifest, run_results, consumers, commit, policy=None, now=None):
    policy = policy or Policy()
    now = now or datetime.now(timezone.utc)
    findings = []
    import re
    if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", commit):
        raise ValueError("Expected candidate commit must be a full Git SHA")

    def block(rule, subject, message):
        findings.append(finding(rule, subject, message, "Rebuild/export candidate artifacts in the trusted CI job for this commit; resolve missing coverage."))

    def fresh(value, subject):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            age = (now - dt).total_seconds() / 3600
            if dt.tzinfo is None or not -5 / 60 <= age <= policy.max_evidence_age_hours:
                raise ValueError()
        except (AttributeError, TypeError, ValueError):
            block("ARTIFACT_FRESHNESS", subject, "Artifact timestamp is missing, stale or inconsistent.")

    for name, artifact in [("manifest", manifest), ("run_results", run_results)]:
        meta = artifact.get("metadata", {})
        if not isinstance(meta, dict):
            raise ValueError(f"{name}.metadata must be an object")
        env = meta.get("env", {})
        if not isinstance(env, dict) or env.get("GIT_SHA") != commit:
            block("CANDIDATE_BINDING", name, "Artifact does not identify the expected candidate commit.")
        fresh(meta.get("generated_at"), name)
    invocation = manifest.get("metadata", {}).get("invocation_id")
    if not invocation or invocation != run_results.get("metadata", {}).get("invocation_id"):
        block("CANDIDATE_BINDING", "dbt", "Manifest and run results do not share the same dbt invocation.")
    if not isinstance(run_results.get("args"), dict) or run_results["args"].get("which") != "build":
        block("DBT_EXECUTION", "run_results", "A dbt build result is required; compile/parse success is not execution evidence.")
    audit = audit_manifest(manifest, policy)
    if audit["status"] != "clear" or not audit["complete"]:
        block("CANDIDATE_MANIFEST", "manifest", "Manifest has findings or incomplete lineage/SQL coverage.")
    results = run_results.get("results", [])
    if not isinstance(results, list) or any(not isinstance(r, dict) for r in results):
        raise ValueError("run_results.results must be an array of objects")
    outcomes = {}
    unit_tests = manifest.get("unit_tests", {})
    if not isinstance(unit_tests, dict) or any(not isinstance(v, dict) for v in unit_tests.values()):
        raise ValueError("manifest.unit_tests must be an object of resources")
    executable = {**manifest.get("nodes", {}), **unit_tests}
    for row in results:
        uid = row.get("unique_id")
        if not isinstance(uid, str) or uid in outcomes:
            block("DBT_EXECUTION", "run_results", "Missing or duplicate result identity.")
            continue
        if uid not in executable or row.get("status") not in {"pass", "success"}:
            block("DBT_EXECUTION", uid, "Unexpected resource identity or unsuccessful execution result.")
        if row.get("failures") not in (None, 0):
            block("DBT_EXECUTION", uid, "The test reports failing rows despite its reported status.")
        outcomes[uid] = row.get("status")
    for uid, obj in executable.items():
        kind, cfg = obj.get("resource_type"), obj.get("config", {})
        if cfg.get("enabled") is False or cfg.get("materialized") == "ephemeral":
            continue
        if kind in {"model", "seed", "snapshot", "test", "unit_test"}:
            expected = "pass" if kind in {"test", "unit_test"} else "success"
            if outcomes.get(uid) != expected:
                block("DBT_EXECUTION", uid, f"Expected {expected}; received {outcomes.get(uid, 'missing')}.")
    if consumers.get("candidate_commit") != commit:
        block("CANDIDATE_BINDING", "consumers", "Consumer inventory is not bound to this candidate.")
    fresh(consumers.get("captured_at"), "consumers")
    queries = consumers.get("queries")
    if consumers.get("inventory_complete") is not True or not isinstance(queries, list) or not queries:
        block("CONSUMER_COVERAGE", "consumers", "A complete, nonempty consumer SQL inventory is required.")
        queries = []
    consumer_audits, ids = [], set()
    for query in queries:
        if not isinstance(query, dict) or not all(isinstance(query.get(k), str) and query[k].strip() for k in ("id", "owner", "sql")):
            block("CONSUMER_COVERAGE", "consumers", "Every query needs an identity, owner and compiled SQL.")
            continue
        if query["id"] in ids:
            block("CONSUMER_COVERAGE", query["id"], "Duplicate consumer identity.")
        ids.add(query["id"])
        result = audit_sql(query["sql"], "consumer", policy, query["id"])
        consumer_audits.append(result)
        if result["status"] != "clear" or not result["complete"]:
            block("CONSUMER_SQL", query["id"], "Consumer query has findings or incomplete coverage.")
    return report("candidate", findings, candidate_commit=commit, policy_hash=policy.hash,
                  artifact_hashes={"manifest": digest(manifest), "run_results": digest(run_results), "consumers": digest(consumers)},
                  manifest=audit, consumers=consumer_audits, complete=not findings,
                  warehouse_verified=False, release_approved=False,
                  scope="Candidate artifact checks only. Run in trusted CI with protected policy. Imported job artifacts and inventory declarations are not authenticated warehouse/business-owner approval.")
