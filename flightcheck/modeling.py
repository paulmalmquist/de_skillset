from __future__ import annotations

from typing import Literal

import yaml
from pydantic import Field

from .common import StrictModel, finding, report, digest

Identifier = str


class Column(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    data_type: Literal["string", "int64", "float64", "numeric", "bignumeric", "bool", "date", "timestamp", "datetime"]
    description: str = Field(min_length=3)


class Measure(StrictModel):
    column: str
    aggregation: Literal["sum", "count", "min", "max", "ratio_of_sums", "last_value", "none"]
    additivity: Literal["additive", "semi_additive", "non_additive"]
    unit: str = Field(min_length=1)
    excluded_dimensions: list[str] = Field(default_factory=list)


class DimensionRef(StrictModel):
    column: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    model: str = Field(pattern=r"^dim_[a-z0-9_]+$")
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")


class ModelSpec(StrictModel):
    name: str = Field(pattern=r"^(fct|dim|bridge)_[a-z0-9_]+$")
    kind: Literal["fact", "dimension", "bridge"]
    business_process: str = Field(min_length=5)
    grain: str = Field(min_length=15)
    keys: list[str] = Field(min_length=1)
    owner: str = Field(min_length=3)
    source_model: str = Field(pattern=r"^(stg|int)_[a-z0-9_]+$")
    columns: list[Column] = Field(min_length=1)
    fact_type: Literal["transaction", "periodic_snapshot", "accumulating_snapshot"] | None = None
    measures: list[Measure] = Field(default_factory=list)
    dimensions: list[DimensionRef] = Field(default_factory=list)
    scd_type: Literal[1, 2] | None = None
    business_keys: list[str] = Field(default_factory=list)
    late_arrival_policy: str = Field(min_length=10)
    delete_policy: str = Field(min_length=10)
    allocation_policy: str | None = None


def validate_model(spec: ModelSpec):
    findings = []
    names = [c.name for c in spec.columns]
    expected_prefix = {"fact": "fct_", "dimension": "dim_", "bridge": "bridge_"}[spec.kind]
    if not spec.name.startswith(expected_prefix):
        findings.append(finding("MODEL_KIND", spec.name, "Model prefix and kind disagree.", "Use fct_, dim_, or bridge_ consistently."))
    if len(set(names)) != len(names) or len(set(spec.keys)) != len(spec.keys):
        findings.append(finding("MODEL_COLUMNS", spec.name, "Duplicate column or key declarations.", "Declare each identifier once."))
    for key in spec.keys + spec.business_keys:
        if key not in names:
            findings.append(finding("GRAIN_KEY", spec.name, f"Key {key} is absent from the column contract.", "Include the key with an explicit type."))
    if spec.kind == "fact" and not spec.fact_type:
        findings.append(finding("FACT_TYPE", spec.name, "Fact table type is missing.", "Declare transaction, periodic snapshot, or accumulating snapshot."))
    if spec.kind != "fact" and (spec.fact_type or spec.measures):
        findings.append(finding("MODEL_KIND", spec.name, "Fact-specific fields are declared on another model kind.", "Keep measures at a declared fact grain."))
    if spec.kind == "bridge" and (not spec.allocation_policy or len(spec.allocation_policy) < 15):
        findings.append(finding("BRIDGE_ALLOCATION", spec.name, "Bridge lacks an allocation/counting policy.", "Declare weighting, normalization and distinct-entity counting rules."))
    if spec.fact_type == "periodic_snapshot" and not any(c.data_type == "date" and c.name in spec.keys for c in spec.columns):
        findings.append(finding("SNAPSHOT_GRAIN", spec.name, "Periodic snapshot lacks a DATE key in its grain.", "Include the as-of date with the entity key."))
    if spec.fact_type == "accumulating_snapshot":
        findings.append(finding("ACCUMULATING_REOPEN", spec.name, "Reopened workflows need an explicit update/restatement rule.", "Document milestones, reopenings, and idempotent merge behavior.", severity="warn"))
    for measure in spec.measures:
        if measure.column not in names:
            findings.append(finding("MEASURE_COLUMN", spec.name, f"Measure {measure.column} is not in the output contract.", "Declare its type and source expression."))
        if measure.additivity != "additive" and measure.aggregation == "sum" and not measure.excluded_dimensions:
            findings.append(finding("MEASURE_ADDITIVITY", spec.name, f"{measure.column} cannot be summed across all dimensions.", "Declare excluded dimensions and the correct aggregate behavior."))
    for dim in spec.dimensions:
        if dim.column not in names:
            findings.append(finding("DIMENSION_KEY", spec.name, f"Foreign key {dim.column} is missing.", "Resolve the conformed surrogate key upstream, including unknown members."))
    if spec.kind == "dimension" and spec.scd_type is None:
        findings.append(finding("DIMENSION_HISTORY", spec.name, "No dimension history policy.", "Choose Type 1 or Type 2 deliberately."))
    if spec.scd_type == 2:
        required = {"valid_from", "valid_to", "is_current"}
        if not required.issubset(names) or not spec.business_keys:
            findings.append(finding("SCD2_FIELDS", spec.name, "Type 2 needs a natural key and validity columns.", "Declare business_keys, valid_from, valid_to, and is_current; use half-open intervals."))
        if set(spec.keys) == set(spec.business_keys):
            findings.append(finding("SCD2_KEY", spec.name, "Natural key alone cannot identify a Type 2 version.", "Use a version-specific surrogate key or natural key plus effective-from timestamp."))
        types = {c.name: c.data_type for c in spec.columns}
        if types.get("valid_from") not in {"timestamp", "datetime"} or types.get("valid_to") != types.get("valid_from") or types.get("is_current") != "bool":
            findings.append(finding("SCD2_TYPES", spec.name, "Validity columns have incompatible types.", "Use matching timestamp/datetime boundaries and a boolean is_current."))
    return report("model", findings, contract_hash=digest(spec.model_dump()), status_scope="Structural design review; uniqueness and business meaning require execution and owner review.")


def scaffold(spec: ModelSpec):
    assessment = validate_model(spec)
    if assessment["blocking"]:
        return {"assessment": assessment, "files": {}}
    model = {"name": spec.name, "description": f"{spec.business_process}. Grain: {spec.grain}", "access": "public",
             "config": {"materialized": "table", "contract": {"enforced": True}, "meta": {"flightcheck": {"layer": "mart", "owner": spec.owner, "grain": spec.grain, "keys": spec.keys}}},
             "columns": []}
    refs = {d.column: d for d in spec.dimensions}
    for column in spec.columns:
        obj = column.model_dump()
        tests = []
        if column.name in spec.keys or column.name in spec.business_keys:
            tests.append("not_null")
            if column.name in spec.keys and len(spec.keys) == 1:
                tests.append("unique")
        if column.name in refs:
            dim = refs[column.name]
            if "not_null" not in tests:
                tests.append("not_null")
            tests.append({"relationships": {"arguments": {"to": f"ref('{dim.model}')", "field": dim.key}}})
        if tests:
            obj["data_tests"] = tests
        model["columns"].append(obj)
    cols = ",\n    ".join(c.name for c in spec.columns)
    keys = ", ".join(spec.keys)
    nulls = " OR ".join(f"{k} IS NULL" for k in spec.keys)
    files = {
        f"models/marts/{spec.name}.sql": "-- Scaffold: source must already resolve keys, units and time semantics.\n-- Do not certify until dbt build and record reconciliation execute in dev.\nSELECT\n    " + cols + "\nFROM {{ ref('" + spec.source_model + "') }}\n",
        f"models/marts/{spec.name}.yml": yaml.safe_dump({"version": 2, "models": [model]}, sort_keys=False),
        f"tests/{spec.name}_grain.sql": f"SELECT {keys}, COUNT(*) AS row_count\nFROM {{{{ ref('{spec.name}') }}}}\nGROUP BY {keys}\nHAVING COUNT(*) > 1 OR {nulls}\n",
        f"contracts/{spec.name}.json": __import__("json").dumps(spec.model_dump(), indent=2) + "\n",
    }
    # dbt evaluates Jinja inside SQL comments; the declaration identifies the singular
    # test's intended coverage without requiring a third-party test package.
    grain_meta = {"flightcheck": {"test_kind": "grain", "keys": spec.keys}}
    files[f"tests/{spec.name}_grain.sql"] = "-- {{ config(meta=" + __import__("json").dumps(grain_meta) + ") }}\n" + files[f"tests/{spec.name}_grain.sql"]
    if spec.scd_type == 2:
        equality = " AND ".join(f"a.{k} = b.{k}" for k in spec.business_keys)
        different = " OR ".join(f"a.{k} != b.{k}" for k in spec.keys)
        timestamp_type = next(c.data_type for c in spec.columns if c.name == "valid_from").upper()
        files[f"tests/{spec.name}_overlap.sql"] = f"""SELECT a.{spec.keys[0]} AS version_a, b.{spec.keys[0]} AS version_b
FROM {{{{ ref('{spec.name}') }}}} a
JOIN {{{{ ref('{spec.name}') }}}} b ON {equality}
WHERE ({different})
  AND a.valid_from < COALESCE(b.valid_to, {timestamp_type}('9999-12-31 00:00:00'))
  AND b.valid_from < COALESCE(a.valid_to, {timestamp_type}('9999-12-31 00:00:00'))
"""
        bk = ", ".join(spec.business_keys)
        files[f"tests/{spec.name}_current.sql"] = f"SELECT {bk}\nFROM {{{{ ref('{spec.name}') }}}}\nGROUP BY {bk}\nHAVING COUNTIF(is_current) != 1\n"
        files[f"tests/{spec.name}_intervals.sql"] = f"SELECT {keys}\nFROM {{{{ ref('{spec.name}') }}}}\nWHERE valid_from IS NULL OR is_current IS NULL OR (valid_to IS NOT NULL AND valid_to <= valid_from) OR (is_current != (valid_to IS NULL))\n"
        business_nulls = " OR ".join(f"{key} IS NULL" for key in spec.business_keys)
        files[f"tests/{spec.name}_business_keys.sql"] = f"SELECT {keys}\nFROM {{{{ ref('{spec.name}') }}}}\nWHERE {business_nulls}\n"
    return {"assessment": assessment, "files": files}
