from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from .common import finding, report
from .policy import Policy, apply_exceptions


def parse_query(sql: str, dialect="bigquery"):
    if "{{" in sql or "{%" in sql or "{#" in sql:
        raise ValueError("Uncompiled Jinja: provide compiled SQL; macros are not guessed.")
    expressions = [node for node in sqlglot.parse(sql, read=dialect) if node is not None]
    if len(expressions) != 1 or not isinstance(expressions[0], exp.Query):
        raise ValueError("Exactly one read-only SELECT/UNION query is supported.")
    tree = expressions[0]
    # A query root alone is insufficient for dialects supporting data-changing CTEs.
    if any(isinstance(n, (exp.DDL, exp.DML, exp.Command, exp.Into)) for n in tree.walk()):
        raise ValueError("Data-changing SQL is not allowed, including within CTEs.")
    return tree


def physical_tables(tree):
    tables = {}
    for scope in traverse_scope(tree):
        for _, source in scope.sources.items():
            if isinstance(source, exp.Table):
                if not isinstance(source.this, exp.Identifier):
                    raise ValueError("Table-valued or external functions require manual lineage registration.")
                name = ".".join(p.name for p in source.parts)
                tables[name] = source
    return sorted(tables)


def audit_sql(sql: str, layer="consumer", policy: Policy | None = None, subject="query"):
    policy = policy or Policy()
    findings = []
    if layer not in policy.allowed_dependencies:
        raise ValueError("Unknown target layer")
    try:
        tree = parse_query(sql, policy.dialect)
        relations = physical_tables(tree)
    except Exception as exc:
        code = "SQL_UNCOMPILED" if "Uncompiled" in str(exc) else "SQL_READ_ONLY" if "read-only" in str(exc) or "Data-changing" in str(exc) else "SQL_PARSE"
        findings.append(finding(code, subject, str(exc), "Compile dbt SQL and submit one supported read-only query."))
        return report("sql", findings, relations=[], complete=False, policy_hash=policy.hash)
    for select in tree.find_all(exp.Select):
        for projection in select.expressions:
            target = projection.this if isinstance(projection, exp.Alias) else projection
            if isinstance(target, exp.Star) or isinstance(target, exp.Column) and target.is_star:
                findings.append(finding("SELECT_STAR", subject, "Wildcard projection makes the output contract unstable.", "Enumerate the required columns, including in CTEs.", projection=projection.sql(dialect=policy.dialect)))
        if select.args.get("distinct"):
            findings.append(finding("DISTINCT_MASKS_GRAIN", subject, "DISTINCT may hide fanout or an undeclared grain.", "Prove join cardinality and make deduplication deterministic.", severity="warn"))
    for join in tree.find_all(exp.Join):
        predicate = join.args.get("on")
        if (not predicate and not join.args.get("using")) or (predicate and not predicate.find(exp.Column)):
            findings.append(finding("JOIN_CARDINALITY", subject, "A join has no equality/range predicate.", "Declare intended cardinality and prove it; use a reviewed exception for intentional cross joins.", join=join.sql(dialect=policy.dialect)))
    for relation in relations:
        source_layer = policy.classify(relation)
        if source_layer == "unknown":
            findings.append(finding("UNCLASSIFIED_RELATION", subject, f"No unambiguous layer mapping for {relation}.", "Map the exact relation or dataset in config/policy.yml.", relation=relation))
        elif source_layer not in policy.allowed_dependencies[layer]:
            findings.append(finding("LAYER_BYPASS", subject, f"{layer} directly consumes {source_layer}: {relation}.", "Route the consumer through a contracted mart or serving model; track migration with an expiring exception.", relation=relation, from_layer=source_layer, to_layer=layer))
    findings = apply_exceptions(findings, policy)
    return report("sql", findings, relations=[{"name": r, "layer": policy.classify(r)} for r in relations], complete=True, policy_hash=policy.hash)
