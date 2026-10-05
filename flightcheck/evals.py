from .demo import CASES, demo_bundle
from .evidence import evaluate
from .sql_audit import audit_sql


def run_evaluations():
    checks = []
    expectations = {"masked-loss": ("mismatch", 3), "clean": ("ready_for_review", None),
                    "control-failure": ("blocked", 0), "stale": ("blocked", 1),
                    "wrong-environment": ("blocked", 2), "value-drift": ("mismatch", 3), "empty": ("blocked", 3)}
    for case, (status, failure) in expectations.items():
        actual = evaluate(demo_bundle(case))
        first = next((g["index"] for g in actual["gates"] if g["status"] == "fail"), None)
        checks.append({"name": CASES[case], "expected": f"{status}; first failed gate={failure}",
                       "actual": f"{actual['status']}; first failed gate={first}", "passed": (actual["status"], first) == (status, failure)})
    for title, sql, expected in [
        ("Consumer cannot read staging", "SELECT event_id FROM demo.staging.operations", "LAYER_BYPASS"),
        ("Consumer cannot read intermediate", "SELECT event_id FROM demo.intermediate.operations", "LAYER_BYPASS"),
        ("Unknown dataset is not silently trusted", "SELECT event_id FROM demo.mystery.operations", "UNCLASSIFIED_RELATION"),
        ("Uncompiled macros remain unverified", "SELECT event_id FROM {{ ref('fct_events') }}", "SQL_UNCOMPILED"),
        ("CTE wildcard is caught", "WITH a AS (SELECT * FROM demo.mart.operations) SELECT event_id FROM a", "SELECT_STAR"),
        ("Read-only boundary", "DELETE FROM demo.mart.operations WHERE TRUE", "SQL_READ_ONLY"),
    ]:
        result = audit_sql(sql)
        codes = [f["rule"] for f in result["findings"]]
        checks.append({"name": title, "expected": expected, "actual": ", ".join(codes), "passed": expected in codes})
    return {"kind": "evaluations", "status": "passed" if all(c["passed"] for c in checks) else "failed",
            "passed": sum(c["passed"] for c in checks), "total": len(checks), "checks": checks,
            "scope": "Deterministic regression fixtures, not a measured Claude performance benchmark."}
