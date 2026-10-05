import copy,json
from pathlib import Path
import pytest,yaml,sqlglot
from flightcheck.manifest import audit_manifest,impact
from flightcheck.modeling import ModelSpec,validate_model,scaffold

DATA=Path(__file__).parents[1]/"flightcheck/data"


def manifest():return json.loads((DATA/"manifest-example.json").read_text())
def spec():return ModelSpec.model_validate_json((DATA/"model-example.json").read_text())


def test_exposures_and_transitive_impact():
    a=audit_manifest(manifest())
    assert sum(f["rule"]=="LAYER_BYPASS" for f in a["findings"])==2
    descendants={d["id"] for d in impact(a,"model.demo.stg_operation_events")}
    assert "exposure.demo.dreamcatcher_builds" in descendants
    assert "exposure.demo.power_bi_operations" in descendants


def test_unresolved_and_cycles_fail_closed():
    m=manifest();m["nodes"]["model.demo.stg_operation_events"]["depends_on"]["nodes"]=["missing"]
    a=audit_manifest(m)
    assert a["complete"] is False
    assert "LINEAGE_INCOMPLETE" in {f["rule"] for f in a["findings"]}
    m=manifest();m["nodes"]["model.demo.stg_operation_events"]["depends_on"]["nodes"]=["model.demo.int_operation_events"]
    assert "LINEAGE_CYCLE" in {f["rule"] for f in audit_manifest(m)["findings"]}


def test_hardcoded_bypass_not_in_ref_graph():
    m=manifest();n=m["nodes"]["model.demo.rpt_operations"]
    n["compiled_code"]="SELECT id FROM synthetic.staging.hidden_table"
    assert any(f["rule"]=="LAYER_BYPASS" and f["evidence"].get("relation")=="synthetic.staging.hidden_table" for f in audit_manifest(m)["findings"])


def test_missing_compiled_sql_means_incomplete_coverage():
    a=audit_manifest(manifest())
    assert not a["complete"]
    assert "SQL_COVERAGE" in {f["rule"] for f in a["findings"]}


@pytest.mark.parametrize("bad", [{}, {"nodes":[],"sources":{}}, {"nodes":{},"sources":{}}])
def test_bad_or_empty_manifest_is_blocked(bad):
    assert audit_manifest(bad)["status"]=="blocked"


def test_malformed_resource_has_clear_error():
    with pytest.raises(ValueError):audit_manifest({"nodes":{"x":1}})


def test_model_scaffold_contract_and_sql():
    s=spec();out=scaffold(s)
    assert out["assessment"]["blocking"]==0
    assert len(out["files"])==4
    yml=yaml.safe_load(out["files"][f"models/marts/{s.name}.yml"])
    assert yml["models"][0]["config"]["contract"]["enforced"] is True
    for path,content in out["files"].items():
        if path.endswith('.sql'):
            import re
            compiled=re.sub(r"\{\{ ref\('([^']+)'\) \}\}",r"demo.mart.\1",content)
            sqlglot.parse_one(compiled,read="bigquery")


def test_invalid_grain_prevents_files():
    s=spec();s.keys=["absent"]
    assert not scaffold(s)["files"]


def test_nonadditive_measure_cannot_sum_all_dimensions():
    s=spec();s.measures[0].additivity="semi_additive"
    assert "MEASURE_ADDITIVITY" in {f["rule"] for f in validate_model(s)["findings"]}


def test_scd2_requires_version_grain_and_intervals():
    d={"name":"dim_part","kind":"dimension","business_process":"Part revision history","grain":"One row per part dimension version","keys":["part_key"],"owner":"data-owner","source_model":"int_parts","scd_type":2,"business_keys":["part_id"],"columns":[{"name":n,"data_type":t,"description":"Versioned attribute"} for n,t in [("part_key","string"),("part_id","string"),("valid_from","timestamp"),("valid_to","timestamp"),("is_current","bool")]],"late_arrival_policy":"Restate affected intervals with replay.","delete_policy":"Maintain a tombstone current version."}
    out=scaffold(ModelSpec.model_validate(d))
    assert "tests/dim_part_overlap.sql" in out["files"]
    assert "tests/dim_part_current.sql" in out["files"]
    assert "tests/dim_part_intervals.sql" in out["files"]
    d["keys"]=["part_id"]
    assert "SCD2_KEY" in {f["rule"] for f in validate_model(ModelSpec.model_validate(d))["findings"]}
