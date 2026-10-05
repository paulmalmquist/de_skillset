"""Synthetic manufacturing fixture. Every demo query/control actually executes in SQLite."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from .common import digest
from .evidence import Context, EvidenceBundle, Observation, Control

CASES = {
    "masked-loss": "Equal counts, dropped operation, duplicate join, changed cost",
    "clean": "Corrected model: all six records agree",
    "control-failure": "Broken control: empty results cannot be trusted",
    "stale": "Stale watermark: inference stops at gate 1",
    "wrong-environment": "Wrong project: authority check blocks comparison",
    "value-drift": "Same keys and counts, different cost",
    "empty": "Empty comparison: inconclusive",
}


def demo_bundle(case="masked-loss"):
    if case not in CASES:
        raise ValueError("Unknown demo scenario")
    now = datetime.now(timezone.utc)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE operation(event_id TEXT PRIMARY KEY, work_order_id TEXT, status TEXT, cost REAL);
        INSERT INTO operation VALUES
        ('OP-001','WO-101','complete',120.0),('OP-002','WO-101','complete',85.0),
        ('OP-003','WO-102','complete',240.0),('OP-004','WO-103','open',45.0),
        ('OP-005','WO-104','complete',170.0),('OP-006','WO-104','complete',95.0);
        CREATE TABLE assignments(event_id TEXT, assignee TEXT);
        INSERT INTO assignments VALUES ('OP-003','A'),('OP-003','B');
    """)
    base = "SELECT event_id, work_order_id, status, cost FROM operation"
    joined = "SELECT o.event_id, o.work_order_id, o.status, o.cost FROM operation o LEFT JOIN assignments a ON o.event_id = a.event_id"
    candidate = base
    if case == "masked-loss":
        candidate = "SELECT o.event_id, o.work_order_id, o.status, CASE WHEN o.event_id='OP-002' THEN o.cost + 10 ELSE o.cost END AS cost FROM operation o LEFT JOIN assignments a ON o.event_id=a.event_id WHERE o.status='complete'"
    elif case == "value-drift":
        candidate = "SELECT event_id, work_order_id, status, cost + CASE WHEN event_id='OP-002' THEN 10 ELSE 0 END AS cost FROM operation"
    elif case in {"empty", "control-failure"}:
        base += " WHERE 1=0"
        candidate = base
    def observe(sql, relation):
        context = Context(environment="dev", project="synthetic-manufacturing", relation=relation, principal="local-demo", snapshot_id="fixture-v1")
        control_result = conn.execute("SELECT COUNT(*) FROM operation WHERE event_id = 'OP-001'").fetchone()[0]
        return Observation(context=context, expected_context=context.model_copy(), sql_hash=digest(sql), query_id=f"sqlite-{digest(sql)[:12]}", tool="sqlite3",
                           observed_at=now, data_as_of=now - timedelta(minutes=20),
                           control=Control(query_id="sqlite-control-op001", context_hash=digest(context.model_dump()), succeeded=True, expected=1, actual=control_result),
                           rows=[dict(r) for r in conn.execute(sql).fetchall()])
    left, right = observe(base, "fixture.baseline"), observe(candidate, "fixture.candidate")
    if case == "control-failure":
        right.control.actual = conn.execute("SELECT COUNT(*) FROM operation WHERE event_id='NO-SUCH-KEY'").fetchone()[0]
    if case == "stale":
        right.data_as_of = now - timedelta(days=3)
    if case == "wrong-environment":
        right.context = right.context.model_copy(update={"project": "wrong-project"})
        right.control.context_hash = digest(right.context.model_dump())
    stages = [{"name": "01 · source operations", "rows": [dict(r) for r in conn.execute("SELECT event_id FROM operation")]},
              {"name": "02 · assignment join", "rows": [dict(r) for r in conn.execute(joined)]},
              {"name": "03 · status filter + cost", "rows": right.rows}] if case == "masked-loss" else []
    conn.close()
    return EvidenceBundle(title=CASES[case], provenance="synthetic-executed", left=left, right=right, keys=["event_id"], stages=stages)
