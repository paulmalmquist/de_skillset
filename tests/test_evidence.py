from datetime import datetime, timedelta, timezone
import pytest
from flightcheck.demo import demo_bundle
from flightcheck.evidence import evaluate
from flightcheck.reconcile import reconcile, trace_stages


@pytest.mark.parametrize("case,gate", [("control-failure",0),("stale",1),("wrong-environment",2)])
def test_stops_at_first_failed_prerequisite(case, gate):
    result=evaluate(demo_bundle(case))
    assert result["gates"][gate]["status"] == "fail"
    assert all(g["status"] == "not_run" for g in result["gates"][gate+1:])
    assert result["diff"] is None


def test_equal_counts_hide_three_failure_classes():
    result=evaluate(demo_bundle("masked-loss"));diff=result["diff"]
    assert diff["left_count"] == diff["right_count"] == 6
    assert diff["missing_keys"]["sample"] == [["OP-004"]]
    assert diff["duplicate_keys"]["right"]["sample"][0]["key"] == ["OP-003"]
    assert diff["changed_records"]["sample"][0]["key"] == ["OP-002"]
    assert result["trace"]["first_divergence"]["to"] == "02 · assignment join"


def test_clean_is_ready_for_review_never_certified():
    result=evaluate(demo_bundle("clean"))
    assert result["status"] == "ready_for_review"
    assert result["certified"] is False


def test_empty_is_inconclusive_even_with_good_control():
    result=evaluate(demo_bundle("empty"))
    assert result["gates"][0]["status"] == "pass"
    assert result["diff"]["status"] == "inconclusive"
    assert result["status"] == "blocked"


def test_missing_is_not_null_and_key_types_do_not_coerce():
    assert reconcile([{"id":1}], [{"id":1,"value":None}], ["id"])["changed_records"]["count"] == 1
    assert reconcile([{"id":1}], [{"id":"1"}], ["id"])["missing_keys"]["count"] == 1


def test_duplicates_are_ambiguous_even_if_identical():
    rows=[{"id":"a","value":1}]*2
    diff=reconcile(rows,rows,["id"])
    assert diff["status"] == "mismatch"
    assert diff["matched_unique_keys"] == 0


def test_null_keys_and_composite_keys():
    assert reconcile([{"a":1,"b":None}],[{"a":1,"b":None}],["a","b"])["invalid_keys"]["left"]["count"] == 1
    assert reconcile([{"a":1,"b":2}],[{"b":2,"a":1}],["a","b"])["status"] == "equal"


def test_explicit_tolerance_is_local_to_measure():
    a=[{"id":1,"value":1.00}];b=[{"id":1,"value":1.001}]
    assert reconcile(a,b,["id"],{"value":.01})["status"] == "equal"
    assert reconcile(a,b,["id"])["status"] == "mismatch"
    with pytest.raises(ValueError):reconcile(a,b,["id"],{"id":.1})
    with pytest.raises(ValueError):reconcile(a,b,["id"],{"value":float("nan")})


def test_nonfinite_and_invalid_rows_fail():
    with pytest.raises(ValueError):reconcile([{"id":1,"value":float("nan")}],[],["id"])
    with pytest.raises(ValueError):reconcile([],[],[])


@pytest.mark.parametrize("which",["future","naive","old-observation"])
def test_invalid_evidence_time(which):
    b=demo_bundle("clean")
    if which=="future":b.right.data_as_of=datetime.now(timezone.utc)+timedelta(days=1)
    elif which=="naive":b.right.observed_at=b.right.observed_at.replace(tzinfo=None)
    else:b.right.observed_at=datetime.now(timezone.utc)-timedelta(days=2)
    assert evaluate(b)["gates"][1]["status"] == "fail"


def test_control_context_mismatch():
    b=demo_bundle("clean");b.right.context.principal="different"
    assert evaluate(b)["gates"][0]["status"] == "fail"


def test_unrelated_trace_cannot_claim_isolation():
    b=demo_bundle("masked-loss");b.stages[0].rows=[{"event_id":"other"}]
    result=evaluate(b)
    assert result["gates"][4]["status"] == "needs_evidence"
    assert result["trace"] is None


def test_truncated_samples_do_not_truncate_counts():
    diff=reconcile([{"id":i} for i in range(40)],[],["id"],sample_limit=3)
    assert diff["missing_keys"]["count"] == 40
    assert len(diff["missing_keys"]["sample"]) == 3
