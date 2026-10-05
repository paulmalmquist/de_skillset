from __future__ import annotations

from collections import deque

from .common import Finding, finding, report
from .policy import Policy, apply_exceptions
from .sql_audit import audit_sql


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
    tests = {}
    for uid, obj in resources.items():
        if obj.get("resource_type") == "test":
            for dep in obj.get("depends_on", {}).get("nodes", []):
                tests.setdefault(dep, []).append(obj.get("test_metadata", {}).get("name", obj.get("name", "custom")))
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
                "tests": tests.get(uid, []), "path": obj.get("original_file_path", "")}
        nodes[uid] = node
        if layer not in policy.allowed_dependencies:
            findings.append(finding("MODEL_LAYER", uid, "Model layer is undeclared.", "Set config.meta.flightcheck.layer; names alone do not establish a contract."))
        if kind == "model" and layer in {"mart", "serving"}:
            for field in ("owner", "grain", "keys"):
                if not node[field]:
                    findings.append(finding("MODEL_CONTRACT", uid, f"Published model lacks {field}.", "Declare owner, one-row grain, and a key list in meta.flightcheck.", missing=field))
            if cfg.get("contract", {}).get("enforced") is not True:
                findings.append(finding("DBT_CONTRACT", uid, "Published schema contract is not enforced.", "Enable the dbt contract and declare column types; retain data tests separately."))
            if obj.get("access", cfg.get("access")) != "public":
                findings.append(finding("MODEL_ACCESS", uid, "Published model is not marked public in dbt.", "Review and set public access for the published interface.", severity="warn"))
            if not tests.get(uid):
                findings.append(finding("MODEL_TESTS", uid, "No attached dbt tests found.", "Add grain, null-key, relationship, and business-invariant tests."))
        if kind == "model":
            sql = obj.get("compiled_code") or obj.get("compiled_sql")
            if sql and layer in policy.allowed_dependencies:
                # AST checks also catch hardcoded tables omitted from dbt ref lineage.
                findings.extend(Finding.model_validate(f)
                                for f in audit_sql(sql, layer, policy, uid)["findings"])
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
                  complete=not any(f.rule in {"MANIFEST_FORMAT", "LINEAGE_INCOMPLETE", "LINEAGE_CYCLE", "MODEL_LAYER", "SQL_COVERAGE", "SQL_PARSE", "SQL_UNCOMPILED"} for f in findings),
                  generated_at=meta.get("generated_at"), policy_hash=policy.hash,
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
