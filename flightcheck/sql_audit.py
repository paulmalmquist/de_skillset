from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from .common import finding, report, digest
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


def _connects(predicate, right, left):
    """Require a cross-input comparison on every OR path; this is not a cardinality proof."""
    if isinstance(predicate, exp.Paren):
        return _connects(predicate.this, right, left)
    if isinstance(predicate, exp.And):
        return _connects(predicate.this, right, left) or _connects(predicate.expression, right, left)
    if isinstance(predicate, exp.Or):
        return _connects(predicate.this, right, left) and _connects(predicate.expression, right, left)
    if not isinstance(predicate, (exp.EQ, exp.NullSafeEQ, exp.LT, exp.LTE, exp.GT, exp.GTE)):
        return False
    def qualifiers(expr):
        if expr.find(exp.Query):
            return set()
        return {c.table.lower() for c in expr.find_all(exp.Column) if c.table}
    a, b = qualifiers(predicate.this), qualifiers(predicate.expression)
    return bool(a and b and ((a <= {right} and b <= left) or (b <= {right} and a <= left)))


def audit_sql(sql: str, layer="consumer", policy: Policy | None = None, subject="query", *, registered_relations=(), incremental_target=None):
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
        return report("sql", findings, relations=[], complete=False, policy_hash=policy.hash, sql_hash=digest(sql))
    checked_joins = set()
    for select in tree.find_all(exp.Select):
        for projection in select.expressions:
            target = projection.this if isinstance(projection, exp.Alias) else projection
            if isinstance(target, exp.Star) or isinstance(target, exp.Column) and target.is_star:
                findings.append(finding("SELECT_STAR", subject, "Wildcard projection makes the output contract unstable.", "Enumerate the required columns, including in CTEs.", projection=projection.sql(dialect=policy.dialect)))
        if select.args.get("distinct"):
            findings.append(finding("DISTINCT_MASKS_GRAIN", subject, "DISTINCT may hide fanout or an undeclared grain.", "Prove join cardinality and make deduplication deterministic.", severity="warn"))
        source = select.args.get("from_")
        left = {source.this.alias_or_name.lower()} if source else set()
        for join in select.args.get("joins", []):
            checked_joins.add(id(join))
            right = join.this.alias_or_name.lower()
            if not join.args.get("using") and not _connects(join.args.get("on"), right, left):
                findings.append(finding("JOIN_CARDINALITY", subject, "Join predicate does not establish a connection between both inputs on every OR path.", "Qualify columns on both inputs and execute grain/fanout tests; explicitly review intentional cross joins.", join=join.sql(dialect=policy.dialect)))
            left.add(right)
    for join in tree.find_all(exp.Join):
        if id(join) not in checked_joins:
            findings.append(finding("JOIN_CARDINALITY", subject, "Nested join group cannot be fully resolved by this checker.", "Express nested join groups as explicit CTEs and verify their grain separately.", join=join.sql(dialect=policy.dialect)))
    for routine in tree.find_all(exp.Anonymous):
        findings.append(finding("ROUTINE_COVERAGE", subject, "Routine dependencies and effects are not resolved.", "Inspect the routine in its owning system before accepting this query.", routine=routine.sql(dialect=policy.dialect)))
    for relation in relations:
        source_layer = policy.classify(relation)
        if source_layer == "unknown":
            findings.append(finding("UNCLASSIFIED_RELATION", subject, f"No unambiguous layer mapping for {relation}.", "Map the exact relation or dataset in config/policy.yml.", relation=relation))
        elif source_layer not in policy.allowed_dependencies[layer] and relation.lower() != incremental_target:
            findings.append(finding("LAYER_BYPASS", subject, f"{layer} directly consumes {source_layer}: {relation}.", "Route the consumer through a contracted mart or serving model; track migration with an expiring exception.", relation=relation, from_layer=source_layer, to_layer=layer))
        elif source_layer in {"mart", "serving"} and relation.lower() not in registered_relations and not policy.publication_registered(relation):
            findings.append(finding("PUBLISHED_CONTRACT", subject, f"Published interface {relation} has no current reviewed registration.", "Register this exact relation, owner, contract, expiry and reviewed upstream lineage; dataset names alone are insufficient.", relation=relation))
    # Waivers expire when the actual SQL changes, even at the same path/relation.
    for f in findings:
        f.evidence["sql_hash"] = digest(sql)
        f.fingerprint = digest({"rule": f.rule, "subject": f.subject, "evidence": f.evidence})
    findings = apply_exceptions(findings, policy)
    return report("sql", findings, relations=[{"name": r, "layer": policy.classify(r)} for r in relations],
                  complete=not any(f.rule in {"ROUTINE_COVERAGE", "PUBLISHED_CONTRACT", "UNCLASSIFIED_RELATION"} for f in findings),
                  policy_hash=policy.hash, sql_hash=digest(sql),
                  scope="Static query checks and declared interface registrations; join cardinality and live view lineage require execution/owner review.")
