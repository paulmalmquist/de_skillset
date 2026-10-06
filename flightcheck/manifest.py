from __future__ import annotations

from collections import deque

from .common import Finding, finding, report, digest
from .policy import Policy, apply_exceptions
from .sql_audit import audit_sql, parse_query, physical_tables


def relation_name(obj):
    name = obj.get("relation_name")
    if not name and obj.get("database") and obj.get("schema"):
        name = ".".join([obj["database"], obj["schema"], obj.get("alias") or obj.get("identifier") or obj.get("name", "")])
    if not name:
        return None
    try:
        names = physical_tables(parse_query(f"SELECT 1 FROM {name}"))
        return names[0].lower() if len(names) == 1 else None
    except Exception:
        return None


def contract_tests(obj, attached):
    """Validate test coverage by exact grain columns, not by number of tests."""
    metadata = {**obj.get("meta", {}), **obj.get("config", {}).get("meta", {})}.get("flightcheck", {})
    keys = metadata.get("keys")
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and k for k in keys) or len(set(keys)) != len(keys):
        return ["keys must be a nonempty, distinct list of column names"]
    columns = obj.get("columns", {})
    if not isinstance(columns, dict):
        return ["columns must be an object"]
    missing = [f"grain column {key} is absent or untyped" for key in keys
               if not isinstance(columns.get(key), dict) or not columns[key].get("data_type")]
    nulls, unique = set(), False
    for test in attached:
        cfg = test.get("config", {})
        if (cfg.get("where") or cfg.get("limit") is not None
                or str(cfg.get("error_if", ">0")).replace(" ", "") != ">0"
                or str(cfg.get("fail_calc", "count(*)")).replace(" ", "").lower() != "count(*)"):
            continue
        tm = test.get("test_metadata") or {}
        args = tm.get("kwargs", {})
        if not isinstance(args, dict):
            continue
        column = args.get("column_name") or test.get("column_name")
        if isinstance(column, str):
            column = column.strip('`"')
        if tm.get("name") == "not_null" and isinstance(column, str):
            nulls.add(column)
        if tm.get("name") == "unique" and keys == [column]:
            unique = True
        combination = args.get("combination_of_columns")
        if tm.get("name") == "unique_combination_of_columns" and isinstance(combination, list) and all(isinstance(k, str) for k in combination) and set(combination) == set(keys):
            unique = True
        coverage = {**test.get("meta", {}), **test.get("config", {}).get("meta", {})}.get("flightcheck", {})
        if coverage.get("test_kind") == "grain" and coverage.get("keys") == keys:
            unique = True  # Explicit singular-test declaration, still requires dbt execution.
    missing += [f"missing blocking not_null test for {key}" for key in keys if key not in nulls]
    if not unique:
        missing.append("missing blocking uniqueness test for the exact declared grain")
    return missing


def audit_manifest(manifest: dict, policy: Policy | None = None):
    policy = policy or Policy()
    findings, nodes, edges = [], {}, []
    if not isinstance(manifest.get("nodes"), dict) or not isinstance(manifest.get("sources", {}), dict):
        return report("manifest", [finding("MANIFEST_FORMAT", "manifest", "Missing nodes/sources dictionaries.", "Export a dbt manifest.json.")], nodes=[], edges=[], complete=False)
    for section in ("metadata", "exposures"):
        if not isinstance(manifest.get(section, {}), dict):
            raise ValueError(f"manifest.{section} must be an object")
    for section in ("nodes", "sources", "exposures"):
        for uid, obj in manifest.get(section, {}).items():
            if not isinstance(obj, dict):
                raise ValueError(f"{uid} must be a resource object")
            for key in ("config", "meta", "depends_on", "owner", "test_metadata"):
                if key == "test_metadata" and obj.get(key) is None:
                    continue  # dbt singular tests use null test_metadata.
                if key in obj and not isinstance(obj[key], dict):
                    raise ValueError(f"{uid}.{key} must be an object")
            deps = obj.get("depends_on", {}).get("nodes", [])
            if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
                raise ValueError(f"{uid} dependencies must be an array of identifiers")
            for meta in [obj.get("meta", {}), obj.get("config", {}).get("meta", {})]:
                if not isinstance(meta, dict) or not isinstance(meta.get("flightcheck", {}), dict):
                    raise ValueError(f"{uid} flightcheck metadata must be an object")
    meta = manifest.get("metadata", {})
    schema = meta.get("dbt_schema_version", "")
    if not schema.endswith(("/v12.json", "/v11.json", "/v10.json", "/v9.json")):
        findings.append(finding("MANIFEST_FORMAT", "manifest", "Missing or unsupported manifest schema version.", "Use a supported dbt manifest v9–v12; add a fixture before enabling other versions."))
    resources = {**manifest.get("sources", {}), **manifest["nodes"], **manifest.get("exposures", {})}
    identities = {}
    for uid, obj in resources.items():
        if obj.get("resource_type") in {"model", "source", "seed", "snapshot"} and obj.get("config", {}).get("enabled") is not False:
            identity = relation_name(obj)
            if identity:
                identities.setdefault(identity, []).append(uid)
    registered = set(identities)
    sql_relations = {}
    tests = {}
    for uid, obj in resources.items():
        if obj.get("resource_type") == "test" and obj.get("config", {}).get("enabled") is not False and obj.get("config", {}).get("severity", "error").lower() == "error":
            for dep in obj.get("depends_on", {}).get("nodes", []):
                tests.setdefault(dep, []).append(obj)
    for uid, obj in resources.items():
        kind = obj.get("resource_type")
        if kind not in {"model", "source", "seed", "snapshot", "exposure"} or obj.get("config", {}).get("enabled") is False:
            continue
        cfg = obj.get("config", {})
        metadata = {**obj.get("meta", {}), **cfg.get("meta", {})}.get("flightcheck", {})
        layer = "source" if kind in {"source", "seed", "snapshot"} else "consumer" if kind == "exposure" else metadata.get("layer", "unknown")
        node = {"id": uid, "name": obj.get("name", uid), "layer": layer,
                "resource_type": kind, "owner": metadata.get("owner") or obj.get("owner", {}).get("name"),
                "grain": metadata.get("grain"), "keys": metadata.get("keys", []),
                "tests": [t.get("name", "custom") for t in tests.get(uid, [])], "path": obj.get("original_file_path", "")}
        nodes[uid] = node
        if layer not in policy.allowed_dependencies:
            findings.append(finding("MODEL_LAYER", uid, "Model layer is undeclared.", "Set config.meta.flightcheck.layer; names alone do not establish a contract."))
        if kind == "model" and layer in {"mart", "serving"}:
            for field in ("owner", "grain", "keys"):
                if not node[field] or (field in {"owner", "grain"} and not isinstance(node[field], str)):
                    findings.append(finding("MODEL_CONTRACT", uid, f"Published model lacks {field}.", "Declare owner, one-row grain, and a key list in meta.flightcheck.", missing=field))
            if cfg.get("contract", {}).get("enforced") is not True:
                findings.append(finding("DBT_CONTRACT", uid, "Published schema contract is not enforced.", "Enable the dbt contract and declare column types; retain data tests separately."))
            if obj.get("access", cfg.get("access")) != "public":
                findings.append(finding("MODEL_ACCESS", uid, "Published model is not marked public in dbt.", "Review and set public access for the published interface.", severity="warn"))
            for problem in contract_tests(obj, tests.get(uid, [])):
                findings.append(finding("MODEL_TESTS", uid, problem, "Declare typed grain columns and blocking tests for each key and exact grain; execute them in dbt."))
        if kind == "model":
            identity = relation_name(obj)
            if cfg.get("materialized") != "ephemeral" and (not identity or len(identities.get(identity, [])) != 1):
                findings.append(finding("RELATION_IDENTITY", uid, "Missing or ambiguous physical relation identity.", "Export database/schema/alias or relation_name from the compiled manifest."))
            if identity and policy.classify(identity) != layer:
                findings.append(finding("RELATION_IDENTITY", uid, "Declared layer disagrees with the physical relation policy.", "Resolve the exact dataset mapping and metadata before publication."))
            sql = obj.get("compiled_code") or obj.get("compiled_sql")
            if sql and layer in policy.allowed_dependencies:
                # AST checks also catch hardcoded tables omitted from dbt ref lineage.
                sql_audit = audit_sql(sql, layer, policy, uid, registered_relations=registered,
                                      incremental_target=identity if cfg.get("materialized") == "incremental" else None)
                sql_relations[uid] = [r["name"].lower() for r in sql_audit["relations"]]
                findings.extend(Finding.model_validate(f)
                                for f in sql_audit["findings"])
            else:
                findings.append(finding("SQL_COVERAGE", uid, "Compiled SQL is absent; graph checks cannot see hardcoded dependencies.", "Run dbt compile in dev and export the resulting manifest.", severity="warn"))
    for uid, node in nodes.items():
        for dep in resources[uid].get("depends_on", {}).get("nodes", []):
            if dep not in nodes:
                findings.append(finding("LINEAGE_INCOMPLETE", uid, f"Dependency {dep} is unresolved.", "Include upstream packages/resources and external dependency mappings.", dependency=dep))
                continue
            source_layer = nodes[dep]["layer"]
            allowed = source_layer in policy.allowed_dependencies.get(node["layer"], [])
            edges.append({"source": dep, "target": uid, "allowed": allowed})
            if not allowed:
                findings.append(finding("LAYER_BYPASS", uid, f"{node['name']} consumes {nodes[dep]['name']} ({source_layer}).", "Migrate this dependency to the published layer.", dependency=dep, from_layer=source_layer, to_layer=node["layer"]))
    for uid, relations in sql_relations.items():
        declared = set(resources[uid].get("depends_on", {}).get("nodes", []))
        # Only ephemeral dependencies inline their physical inputs. Ordinary grandparents
        # do not excuse an undeclared direct table reference.
        pending, ancestors = list(declared), set()
        while pending:
            dep = pending.pop()
            if dep not in ancestors and dep in resources:
                ancestors.add(dep)
                if resources[dep].get("config", {}).get("materialized") == "ephemeral":
                    pending.extend(resources[dep].get("depends_on", {}).get("nodes", []))
        for relation in relations:
            matches = identities.get(relation, [])
            if len(matches) != 1:
                findings.append(finding("LINEAGE_INCOMPLETE", uid, f"SQL relation {relation} is absent or ambiguous in the manifest.", "Register its source/model identity and include upstream definitions.", relation=relation))
                continue
            dep = matches[0]
            if dep == uid and resources[uid].get("config", {}).get("materialized") == "incremental":
                continue  # {{ this }} reads existing target state, not a DAG self-dependency.
            if dep not in ancestors:
                findings.append(finding("LINEAGE_INCOMPLETE", uid, f"SQL dependency {relation} is missing from declared lineage.", "Replace hardcoded references with ref/source; inferred edge is retained for impact analysis.", relation=relation))
            if dep in nodes and not any(e["source"] == dep and e["target"] == uid for e in edges):
                allowed = nodes[dep]["layer"] in policy.allowed_dependencies.get(nodes[uid]["layer"], [])
                edges.append({"source": dep, "target": uid, "allowed": allowed, "inferred": True})
                if not allowed:
                    findings.append(finding("LAYER_BYPASS", uid, "Inferred SQL edge violates the declared layer boundary.", "Route the dependency through its published interface.", dependency=dep))
    # Kahn's algorithm catches cycles without recursion depth failures on large DAGs.
    indegree = {n: 0 for n in nodes}
    children = {n: [] for n in nodes}
    for edge in edges:
        indegree[edge["target"]] += 1
        children[edge["source"]].append(edge["target"])
    pending = deque(n for n in nodes if indegree[n] == 0)
    visited = 0
    while pending:
        n = pending.popleft()
        visited += 1
        for child in children[n]:
            indegree[child] -= 1
            if indegree[child] == 0:
                pending.append(child)
    if visited != len(nodes):
        findings.append(finding("LINEAGE_CYCLE", "manifest", "Dependency graph contains a cycle.", "Remove the cycle before calculating migration order."))
    if not nodes:
        findings.append(finding("MANIFEST_FORMAT", "manifest", "No inspectable assets were found.", "Supply an enabled dbt project manifest."))
    findings = sorted(apply_exceptions(findings, policy), key=lambda f: f.severity != "block")
    return report("manifest", findings, nodes=list(nodes.values()), edges=edges,
                  complete=not any(f.rule in {"MANIFEST_FORMAT", "LINEAGE_INCOMPLETE", "LINEAGE_CYCLE", "MODEL_LAYER", "SQL_COVERAGE", "SQL_PARSE", "SQL_UNCOMPILED", "SQL_READ_ONLY", "RELATION_IDENTITY", "ROUTINE_COVERAGE"} for f in findings),
                  generated_at=meta.get("generated_at"), policy_hash=policy.hash, manifest_hash=digest(manifest),
                  scope="Static artifact audit; live warehouse state and out-of-manifest consumers are unverified.")


def impact(audit: dict, node_id: str):
    known = {n["id"] for n in audit["nodes"]}
    if node_id not in known:
        raise ValueError("Unknown node")
    seen, queue = {node_id}, deque([(node_id, 0)])
    results = []
    children = {}
    for edge in audit["edges"]:
        children.setdefault(edge["source"], []).append(edge["target"])
    while queue:
        current, depth = queue.popleft()
        for child in children.get(current, []):
            if child not in seen:
                seen.add(child)
                results.append({"id": child, "distance": depth + 1})
                queue.append((child, depth + 1))
    return results
