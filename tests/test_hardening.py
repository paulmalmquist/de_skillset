import copy
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
import yaml
from fastapi.testclient import TestClient

from flightcheck.candidate import check_candidate
from flightcheck.demo import demo_bundle
from flightcheck.evidence import evaluate
from flightcheck.manifest import audit_manifest, impact
from flightcheck.modeling import ModelSpec, scaffold
from flightcheck.policy import Policy, ExceptionRule
from flightcheck.server import create_app
from flightcheck.sql_audit import audit_sql
from flightcheck.store import RunStore
from flightcheck.cli import main


SHA = "a" * 40


def valid_manifest():
    m = {"metadata": {"dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json", "generated_at": datetime.now(timezone.utc).isoformat(), "invocation_id": "build-1", "env": {"GIT_SHA": SHA}}, "sources": {}, "nodes": {}}
    for name, sql, deps in [("a", "SELECT 1 AS id", []), ("b", "SELECT id FROM demo.mart.a", ["model.demo.a"])]:
        uid = f"model.demo.{name}"
        m["nodes"][uid] = {"resource_type": "model", "name": name, "relation_name": f"`demo.mart.{name}`", "access": "public", "columns": {"id": {"data_type": "int64"}}, "compiled_code": sql,
                           "config": {"materialized": "table", "contract": {"enforced": True}, "meta": {"flightcheck": {"layer": "mart", "owner": "fixture-owner", "grain": "one row per id", "keys": ["id"]}}}, "depends_on": {"nodes": deps}}
        for test in ["unique", "not_null"]:
            m["nodes"][f"test.demo.{name}_{test}"] = {"name": f"{name}_{test}", "resource_type": "test", "config": {"severity": "error"}, "test_metadata": {"name": test, "kwargs": {"column_name": "id"}}, "depends_on": {"nodes": [uid]}}
    return m


def registration():
    return Policy(published_contracts={"demo.mart.b": {"owner": "fixture-owner", "contract_id": "contract-v1", "lineage_reviewed": True, "expires_at": datetime.now(timezone.utc)+timedelta(days=1)}})


@pytest.mark.parametrize("predicate", ["a.id=a.id", "a.id=b.id OR TRUE", "b.id=b.id", "id=id", "a.id > 0"])
def test_join_requires_both_inputs_on_every_path(predicate):
    r = audit_sql(f"SELECT a.id FROM demo.raw.a a JOIN demo.raw.b b ON {predicate}", "staging")
    assert "JOIN_CARDINALITY" in {f["rule"] for f in r["findings"]}


def test_legitimate_join_predicate_and_nested_join_coverage():
    assert audit_sql("SELECT a.id FROM demo.raw.a a JOIN demo.raw.b b ON a.id=b.id AND b.id>0", "staging")["status"] == "clear"
    assert audit_sql("SELECT a.id FROM demo.raw.a a JOIN (demo.raw.b b CROSS JOIN demo.raw.c c) USING (id)", "staging")["status"] == "blocked"


def test_published_name_is_not_a_contract_and_expiry_matters():
    sql = "SELECT id FROM demo.mart.b"
    assert not audit_sql(sql)["complete"]
    p = registration()
    assert audit_sql(sql, policy=p)["status"] == "clear"
    p.published_contracts["demo.mart.b"].expires_at -= timedelta(days=2)
    assert audit_sql(sql, policy=p)["status"] == "blocked"


def test_routine_and_sql_changes_do_not_inherit_approval():
    assert not audit_sql("SELECT demo.fn(id) AS x FROM demo.raw.a", "staging")["complete"]
    sql = "SELECT id FROM demo.staging.a"
    f = audit_sql(sql)["findings"][0]
    e = ExceptionRule(fingerprint=f["fingerprint"], owner="owner", reviewer="reviewer", ticket="DE-001", reason="Temporary migration compatibility", expires_at=datetime.now(timezone.utc)+timedelta(days=1))
    assert audit_sql(sql, policy=Policy(exceptions=[e]))["blocking"] == 0
    assert audit_sql(sql+" WHERE id>0", policy=Policy(exceptions=[e]))["blocking"] == 1


def test_hardcoded_relation_is_in_impact_and_blocks_completeness():
    m = valid_manifest()
    assert audit_manifest(m)["status"] == "clear"
    m["nodes"]["model.demo.b"]["depends_on"]["nodes"] = []
    r = audit_manifest(m)
    assert r["status"] == "blocked" and not r["complete"]
    assert {n["id"] for n in impact(r, "model.demo.a")} == {"model.demo.b"}


@pytest.mark.parametrize("mutation", ["missing_key", "unrelated_test", "where", "error_if", "fail_calc", "limit", "disabled", "warn"])
def test_bad_grain_contract_cannot_pass(mutation):
    m = valid_manifest()
    if mutation == "missing_key":
        m["nodes"]["model.demo.b"]["config"]["meta"]["flightcheck"]["keys"] = ["nonexistent"]
    else:
        for test in ["unique", "not_null"]:
            t = m["nodes"][f"test.demo.b_{test}"]
            if mutation == "unrelated_test": t["test_metadata"]["kwargs"]["column_name"] = "unrelated"
            else: t["config"].update({"where": {"where": "FALSE"}, "error_if": {"error_if": ">1000"}, "fail_calc": {"fail_calc": "0"}, "limit": {"limit": 0}, "disabled": {"enabled": False}, "warn": {"severity": "warn"}}[mutation])
    assert "MODEL_TESTS" in {f["rule"] for f in audit_manifest(m)["findings"]}


def test_incremental_this_is_not_a_graph_cycle():
    m = valid_manifest()
    n = m["nodes"]["model.demo.a"]
    n["config"]["materialized"] = "incremental"
    n["compiled_code"] = "SELECT MAX(id)+1 AS id FROM demo.mart.a"
    assert audit_manifest(m)["status"] == "clear"


def test_staging_incremental_can_read_only_its_own_target():
    m = valid_manifest()
    m["nodes"] = {k: v for k,v in m["nodes"].items() if k == "model.demo.a" or k.startswith("test.demo.a_")}
    n = m["nodes"]["model.demo.a"]
    n["relation_name"] = "demo.staging.a"
    n["config"]["materialized"] = "incremental"
    n["config"]["meta"]["flightcheck"]["layer"] = "staging"
    n["compiled_code"] = "SELECT MAX(id)+1 AS id FROM demo.staging.a"
    assert audit_manifest(m)["status"] == "clear"
    n["compiled_code"] = "SELECT MAX(id)+1 AS id FROM demo.staging.other"
    assert "LAYER_BYPASS" in {f["rule"] for f in audit_manifest(m)["findings"]}


def test_only_ephemeral_paths_expand_declared_lineage():
    m = valid_manifest()
    n = copy.deepcopy(m["nodes"]["model.demo.b"])
    n.update(name="c", relation_name="demo.mart.c", depends_on={"nodes": ["model.demo.b"]})
    m["nodes"]["model.demo.c"] = n  # c declares b but directly reads a.
    r = audit_manifest(m)
    assert any(f["rule"] == "LINEAGE_INCOMPLETE" and f["subject"] == "model.demo.c" for f in r["findings"])


def test_singular_grain_metadata_accepts_null_test_metadata():
    m = valid_manifest()
    t = m["nodes"]["test.demo.a_unique"]
    t["test_metadata"] = None
    t["config"]["meta"] = {"flightcheck": {"test_kind": "grain", "keys": ["id"]}}
    assert audit_manifest(m)["status"] == "clear"


def test_scd2_rejects_null_business_key_and_overlapping_history():
    spec = ModelSpec(name="dim_part", kind="dimension", business_process="Part revision history", grain="One row per part version", keys=["part_sk"], owner="fixture-owner", source_model="int_part", scd_type=2, business_keys=["part_id"], late_arrival_policy="Replay affected history", delete_policy="Keep current tombstones", columns=[{"name": n, "data_type": t, "description": "Synthetic column"} for n,t in [("part_sk","int64"),("part_id","string"),("valid_from","timestamp"),("valid_to","timestamp"),("is_current","bool")]])
    files = scaffold(spec)["files"]
    columns = yaml.safe_load(files["models/marts/dim_part.yml"])["models"][0]["columns"]
    assert "not_null" in next(c for c in columns if c["name"] == "part_id")["data_tests"]
    conn = sqlite3.connect(":memory:")
    conn.create_function("TIMESTAMP", 1, lambda x: x)
    conn.executescript("CREATE TABLE dim_part(part_sk INTEGER,part_id TEXT,valid_from TEXT,valid_to TEXT,is_current INTEGER); INSERT INTO dim_part VALUES (1,NULL,'2025-01-01','2025-09-01',0),(2,NULL,'2025-03-01',NULL,1);")
    compile_sql = lambda s: s.replace("{{ ref('dim_part') }}", "dim_part")
    assert len(conn.execute(compile_sql(files["tests/dim_part_business_keys.sql"])).fetchall()) == 2
    conn.execute("UPDATE dim_part SET part_id='part-1'")
    assert conn.execute(compile_sql(files["tests/dim_part_overlap.sql"])).fetchall()
    conn.execute("UPDATE dim_part SET valid_to='2025-03-01' WHERE part_sk=1")
    assert not conn.execute(compile_sql(files["tests/dim_part_overlap.sql"])).fetchall()


def test_unattested_or_truncated_evidence_never_ready():
    b = demo_bundle("clean")
    b.provenance = "imported-unattested"
    b.left.query_id = "invented"
    r = evaluate(b)
    assert r["status"] == "unverified"
    assert all(g["status"] == "unverified" for g in r["gates"][:3])
    b.left.rows = b.left.rows[:1]; b.right.rows = b.right.rows[:1]
    assert evaluate(b)["status"] == "incomplete"
    b.left.population = None
    assert not evaluate(b)["coverage"]["complete"]


def candidate_args():
    m = valid_manifest()
    results = {"args": {"which": "build"}, "metadata": copy.deepcopy(m["metadata"]), "results": [{"unique_id": uid, "status": "pass" if n["resource_type"] == "test" else "success"} for uid,n in m["nodes"].items()]}
    consumers = {"candidate_commit": SHA, "captured_at": m["metadata"]["generated_at"], "inventory_complete": True, "queries": [{"id": "report-1", "owner": "fixture-owner", "sql": "SELECT id FROM demo.mart.b"}]}
    return m, results, consumers


def test_candidate_checks_valid_bound_artifacts_without_approving_release():
    r = check_candidate(*candidate_args(), SHA, registration())
    assert r["status"] == "clear"
    assert not r["release_approved"] and not r["warehouse_verified"]


def test_candidate_cli_and_imported_evidence_exit_codes(tmp_path, capsys):
    m, runs, consumers = candidate_args()
    for name, value in [("manifest", m), ("runs", runs), ("consumers", consumers)]:
        (tmp_path/f"{name}.json").write_text(json.dumps(value))
    policy_path = tmp_path/"policy.yml"
    policy_path.write_text(yaml.safe_dump(registration().model_dump(mode="json")))
    args = ["--policy", str(policy_path), "check-candidate", str(tmp_path/"manifest.json"), "--run-results", str(tmp_path/"runs.json"), "--consumers", str(tmp_path/"consumers.json"), "--commit", SHA]
    assert main(args) == 0
    runs["args"]["which"] = "compile"
    (tmp_path/"runs.json").write_text(json.dumps(runs))
    assert main(args) == 1
    bundle_path = tmp_path/"evidence.json"
    bundle_path.write_text(demo_bundle("clean").model_dump_json())
    assert main(["evidence", str(bundle_path)]) == 1


@pytest.mark.parametrize("mutation", ["stale", "commit", "invocation", "missing_test", "failed_test", "consumer_bypass", "inventory", "unregistered", "compile", "unknown_result", "hidden_failures"])
def test_candidate_fails_closed(mutation):
    m, runs, consumers = candidate_args()
    p = registration()
    if mutation == "stale": m["metadata"]["generated_at"] = "2000-01-01T00:00:00Z"
    elif mutation == "commit": runs["metadata"]["env"]["GIT_SHA"] = "b"*40
    elif mutation == "invocation": runs["metadata"]["invocation_id"] = "other"
    elif mutation == "missing_test": runs["results"].pop()
    elif mutation == "failed_test": runs["results"][-1]["status"] = "fail"
    elif mutation == "consumer_bypass": consumers["queries"][0]["sql"] = "SELECT id FROM demo.staging.a"
    elif mutation == "inventory": consumers["inventory_complete"] = False
    elif mutation == "compile": runs["args"]["which"] = "compile"
    elif mutation == "unknown_result": runs["results"].append({"unique_id": "test.unknown", "status": "error"})
    elif mutation == "hidden_failures": runs["results"][-1]["failures"] = 2
    else: p = Policy()
    assert check_candidate(m, runs, consumers, SHA, p)["status"] == "blocked"


def test_host_rebinding_and_remote_factory_access_are_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("FLIGHTCHECK_TOKEN", raising=False)
    monkeypatch.delenv("FLIGHTCHECK_ALLOWED_HOSTS", raising=False)
    app = create_app(tmp_path/"runs.db")
    with TestClient(app, base_url="http://evil.example") as c:
        assert c.get("/api/runs").status_code == 400
    with TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.1", 123)) as c:
        assert c.get("/api/runs").status_code == 403


def test_evidence_samples_are_redacted_and_old_runs_expire(tmp_path):
    s = RunStore(tmp_path/"runs.db", retention_days=1)
    b = demo_bundle("masked-loss"); b.provenance = "imported-unattested"
    r = s.save("investigation", "test", evaluate(b))
    assert r["samples_redacted"]
    assert r["diff"]["changed_records"]["sample"] == []
    assert r["diff"]["changed_records"]["count"] == 1
    with sqlite3.connect(s.path) as conn:
        conn.execute("UPDATE runs SET created_at='2000-01-01T00:00:00+00:00'")
    assert s.get(r["id"]) is None and s.list() == []
