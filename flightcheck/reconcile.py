from __future__ import annotations

import json
import math
from collections import defaultdict
from decimal import Decimal

from .common import digest


def canonical(value):
    # Preserve types and NULL versus missing. Never silently stringify numeric identifiers.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def equivalent(a, b, tolerance=None):
    if tolerance is not None and isinstance(a, (int, float)) and not isinstance(a, bool) and isinstance(b, (int, float)) and not isinstance(b, bool):
        return abs(Decimal(str(a)) - Decimal(str(b))) <= Decimal(str(tolerance))
    return canonical(a) == canonical(b)


def reconcile(left: list[dict], right: list[dict], keys: list[str], tolerances=None, sample_limit=20):
    if not keys or len(set(keys)) != len(keys):
        raise ValueError("Declare a nonempty, unique list of grain columns.")
    if len(left) + len(right) > 100_000:
        raise ValueError("Local comparison limit is 100,000 rows; use warehouse partitioned reconciliation for larger data.")
    tolerances = tolerances or {}
    if any(k in keys for k in tolerances):
        raise ValueError("Tolerance cannot be applied to grain keys.")
    if any(not isinstance(v, (float, int)) or isinstance(v, bool) or not math.isfinite(v) or v < 0 for v in tolerances.values()):
        raise ValueError("Tolerances must be finite, nonnegative numbers.")
    groups, invalid, columns = [], {}, []
    for label, rows in (("left", left), ("right", right)):
        group = defaultdict(list)
        bad = []
        colset = set()
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError("Each row must be an object.")
            canonical(row)  # Reject NaN, Infinity and non-JSON inputs before comparisons.
            colset.update(row)
            if any(k not in row or row[k] is None or isinstance(row[k], (dict, list)) for k in keys):
                bad.append(index)
                continue
            group[canonical([row[k] for k in keys])].append(row)
        groups.append(group)
        invalid[label] = {"count": len(bad), "sample_row_indexes": bad[:sample_limit]}
        columns.append(colset)
    lg, rg = groups
    missing = sorted(set(lg) - set(rg))
    added = sorted(set(rg) - set(lg))
    duplicates = {label: {"count": sum(len(rows) > 1 for rows in group.values()),
                           "sample": [{"key": json.loads(k), "multiplicity": len(v)} for k, v in group.items() if len(v) > 1][:sample_limit]}
                  for label, group in (("left", lg), ("right", rg))}
    changed, multiplicity = [], []
    compared = 0
    for key in sorted(set(lg) & set(rg)):
        if len(lg[key]) != len(rg[key]):
            multiplicity.append({"key": json.loads(key), "left": len(lg[key]), "right": len(rg[key])})
        if len(lg[key]) != 1 or len(rg[key]) != 1:
            continue  # Ambiguous grain: do not invent row pairing.
        compared += 1
        a, b = lg[key][0], rg[key][0]
        changes = []
        for column in sorted(set(a) | set(b)):
            if column not in a or column not in b or not equivalent(a.get(column), b.get(column), tolerances.get(column)):
                changes.append({"column": column, "left": a.get(column), "right": b.get(column), "left_present": column in a, "right_present": column in b})
        if changes:
            changed.append({"key": json.loads(key), "changes": changes})
    issues = len(missing) + len(added) + len(changed) + sum(v["count"] for v in duplicates.values()) + sum(v["count"] for v in invalid.values())
    status = "inconclusive" if not left and not right else "mismatch" if issues else "equal"
    return {"status": status, "keys": keys, "left_count": len(left), "right_count": len(right),
            "matched_unique_keys": compared, "missing_keys": {"count": len(missing), "sample": [json.loads(k) for k in missing[:sample_limit]]},
            "added_keys": {"count": len(added), "sample": [json.loads(k) for k in added[:sample_limit]]},
            "changed_records": {"count": len(changed), "sample": changed[:sample_limit]},
            "multiplicity_changes": {"count": len(multiplicity), "sample": multiplicity[:sample_limit]},
            "duplicate_keys": duplicates, "invalid_keys": invalid,
            "schema_difference": {"left_only": sorted(columns[0] - columns[1]), "right_only": sorted(columns[1] - columns[0])},
            "tolerances": tolerances, "sample_limit": sample_limit,
            "input_hash": digest({"left": left, "right": right, "keys": keys, "tolerances": tolerances})}


def trace_stages(stages: list[dict], keys: list[str]):
    """Profile each materialized stage; duplicates and NULLs remain visible."""
    if len(stages) < 2:
        raise ValueError("At least two materialized stages are required.")
    transitions = []
    first = None
    for previous, current in zip(stages, stages[1:]):
        # Trace key retention only; projection/value changes can be intentional across stages.
        before = [{k: r[k] for k in keys if k in r} for r in previous["rows"]]
        after = [{k: r[k] for k in keys if k in r} for r in current["rows"]]
        diff = reconcile(before, after, keys)
        entry = {"from": previous["name"], "to": current["name"], "before": len(before), "after": len(after),
                 "missing": diff["missing_keys"]["count"], "added": diff["added_keys"]["count"],
                 "duplicate_keys": diff["duplicate_keys"]["right"]["count"], "invalid_keys": diff["invalid_keys"]["right"]["count"],
                 "status": diff["status"]}
        transitions.append(entry)
        if first is None and diff["status"] != "equal":
            first = entry
    return {"status": "mismatch" if any(t["status"] == "mismatch" for t in transitions) else "inconclusive" if first else "equal",
            "first_divergence": first, "transitions": transitions,
            "scope": "First observed key divergence, not proof of root cause. Inspect the named join/filter and business rule."}
