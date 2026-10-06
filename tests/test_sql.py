import pytest
from flightcheck.sql_audit import audit_sql, parse_query
from flightcheck.policy import Policy, ExceptionRule
from datetime import datetime, timedelta, timezone


def registered_policy():
    return Policy(published_contracts={name: {"owner": "fixture-owner", "contract_id": "fixture-only", "lineage_reviewed": True, "expires_at": datetime.now(timezone.utc)+timedelta(days=1)}
                                      for name in ["demo.mart.events", "demo.mart.a", "demo.serving.b"]})


def rules(sql, layer="consumer", policy=None):
    return {f["rule"] for f in audit_sql(sql, layer, policy)["findings"]}


@pytest.mark.parametrize("sql,rule", [
    ("SELECT * FROM demo.mart.events", "SELECT_STAR"),
    ("SELECT e.* FROM demo.mart.events e", "SELECT_STAR"),
    ("SELECT * EXCEPT(hidden) FROM demo.mart.events", "SELECT_STAR"),
    ("WITH a AS (SELECT * FROM demo.mart.events) SELECT event_id FROM a", "SELECT_STAR"),
    ("SELECT id FROM demo.staging.events", "LAYER_BYPASS"),
    ("SELECT id FROM demo.intermediate.events", "LAYER_BYPASS"),
    ("SELECT id FROM demo.unknown.events", "UNCLASSIFIED_RELATION"),
    ("SELECT id FROM {{ ref('events') }}", "SQL_UNCOMPILED"),
    ("DELETE FROM demo.mart.events WHERE TRUE", "SQL_READ_ONLY"),
    ("SELECT 1; DROP TABLE events", "SQL_READ_ONLY"),
    ("SELECT a.id FROM demo.mart.a a CROSS JOIN demo.mart.b b", "JOIN_CARDINALITY"),
    ("SELECT DISTINCT id FROM demo.mart.a", "DISTINCT_MASKS_GRAIN"),
])
def test_detects(sql, rule):
    assert rule in rules(sql)


def test_count_star_and_literals_are_not_projection_wildcards():
    assert not rules("SELECT COUNT(*) AS records, 'SELECT * FROM staging.bad' AS note FROM demo.mart.events", policy=registered_policy())


def test_cte_alias_shadowing_does_not_hide_qualified_relation():
    result = audit_sql("WITH events AS (SELECT id FROM demo.mart.events) SELECT e.id FROM events e JOIN demo.staging.events s ON e.id=s.id", policy=registered_policy())
    assert {r["name"] for r in result["relations"]} == {"demo.mart.events", "demo.staging.events"}
    assert result["blocking"] == 1


def test_nested_cte_scope_and_union():
    result = audit_sql("WITH x AS (SELECT id FROM demo.mart.a) SELECT id FROM x UNION ALL SELECT id FROM demo.serving.b", policy=registered_policy())
    assert result["status"] == "clear"
    assert len(result["relations"]) == 2


def test_ambiguous_mapping_fails_closed():
    policy = Policy(relation_layers={"*.mart.*": "mart", "demo.*.*": "intermediate"})
    assert "UNCLASSIFIED_RELATION" in rules("SELECT id FROM demo.mart.a", policy=policy)


def test_staging_to_source_is_allowed():
    assert audit_sql("SELECT id FROM demo.raw.a", "staging")["status"] == "clear"


def test_exact_reviewed_exception_and_expiration():
    sql = "SELECT id FROM demo.staging.a"
    f = audit_sql(sql)["findings"][0]
    ex = ExceptionRule(fingerprint=f["fingerprint"], owner="owner", reviewer="reviewer", ticket="DE-123", reason="Temporary migration compatibility.", expires_at=datetime.now(timezone.utc)+timedelta(days=2))
    policy = Policy(exceptions=[ex])
    assert audit_sql(sql, policy=policy)["blocking"] == 0
    assert audit_sql("SELECT id FROM demo.staging.b", policy=policy)["blocking"] == 1
    ex.expires_at = datetime.now(timezone.utc)-timedelta(days=1)
    assert "EXCEPTION_INVALID" in rules(sql, policy=Policy(exceptions=[ex]))


def test_self_review_does_not_waive():
    sql="SELECT id FROM demo.staging.a"
    f=audit_sql(sql)["findings"][0]
    ex=ExceptionRule(fingerprint=f["fingerprint"],owner="same",reviewer="same",ticket="DE-123",reason="Temporary migration compatibility.",expires_at=datetime.now(timezone.utc)+timedelta(days=1))
    assert audit_sql(sql,policy=Policy(exceptions=[ex]))["blocking"] >= 1


@pytest.mark.parametrize("sql", ["SELECT FROM", "", "WITH x AS (DELETE FROM t RETURNING id) SELECT id FROM x"])
def test_invalid_or_mutating_queries_are_not_clear(sql):
    assert audit_sql(sql)["status"] == "blocked"
