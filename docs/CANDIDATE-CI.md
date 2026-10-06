# Check the actual candidate in warehouse CI

Install a reviewed, pinned Flightcheck version in the existing internal warehouse runner. Protect the checker, policy, exceptions, inventory exporter and workflow through normal code-owner review. These instructions do not configure branch protection or warehouse permissions automatically.

In the dev build job, set `DBT_ENV_CUSTOM_ENV_GIT_SHA` to the checked-out candidate SHA before running dbt. dbt writes the prefix-stripped value to artifact `metadata.env.GIT_SHA` ([official metadata documentation](https://docs.getdbt.com/reference/dbt-jinja-functions/env_var#custom-metadata)). Keep the manifest and run results from the **same build invocation**. Running `dbt compile` afterward changes the manifest invocation and invalidates the pair.

```bash
export DBT_ENV_CUSTOM_ENV_GIT_SHA="$(git rev-parse HEAD)"
dbt build --target dev
# Export current consumer SQL from its owning systems to private/consumers.json.
# Use your existing inventory exporter; do not mark an unfinished inventory complete.
python -m flightcheck.cli --policy private/policy.yml \
  --out private/candidate-check.json check-candidate target/manifest.json \
  --run-results target/run_results.json \
  --consumers private/consumers.json \
  --commit "$DBT_ENV_CUSTOM_ENV_GIT_SHA"
```

This initial implementation requires outcomes for every enabled materialized model, seed, snapshot and test in the manifest. A partial/selective build blocks on missing outcomes; do not reuse older test results to fill gaps. Incremental self-target reads are permitted; declaring a graph cycle is not. Missing hardcoded references appear as inferred impact edges and still block completion. Only ephemeral paths are expanded to their physical ancestors.

Consumer inventory format (replace all example values with fresh, observed values):

```json
{
  "candidate_commit": "FULL_CANDIDATE_SHA",
  "captured_at": "UTC_CAPTURE_TIMESTAMP",
  "inventory_complete": false,
  "queries": [
    {"id": "report-system/report-id", "owner": "confirmed-owner", "sql": "COMPILED_SQL_FROM_OWNING_SYSTEM"}
  ]
}
```

Include Power BI, Grafana, Dreamcatcher, scheduled queries, views and relevant notebook consumers in the scope agreed with the owner. Empty inventory, missing ownership, duplicates and incomplete exports block. The flag is a declaration checked for consistency, not a discovery mechanism.

Standalone consumer SQL requires exact reviewed publication registrations in policy:

```yaml
published_contracts:
  your_project.your_mart.your_model:
    owner: confirmed-owner
    contract_id: internal-contract-version-or-ticket
    lineage_reviewed: true
    expires_at: '2026-11-01T00:00:00Z'
```

Use actual approved values and an appropriate expiry. Dataset wildcards classify layers but cannot register publication. Review view/routine internals in their owning systems. The provided sample policy has no live registrations. Unknown routines and nested join groups remain unsupported rather than silently passing.

Published manifest models need typed declared grain columns, blocking `not_null` on every key, and exact-grain uniqueness. Supported coverage includes generic single-column `unique`, `unique_combination_of_columns`, or a reviewed singular grain test with `config.meta.flightcheck.test_kind: grain` and exact `keys`. Filtered/limited tests and altered failure-count thresholds do not establish grain coverage. Generated scaffolds carry the singular-test declaration. This verifies declared intent and build outcome; it cannot prove arbitrary custom test semantics.

An exit 0 means **static candidate artifact checks passed**. The result always includes `warehouse_verified: false` and `release_approved: false`. Build these artifacts inside the trusted job rather than accepting uploads as execution proof. Controls, authoritative job lookups, full population reconciliation, business invariants and authenticated owner approval remain separate required release evidence. Never use exit 0 alone as production certification.

Official artifact references: [manifest](https://docs.getdbt.com/reference/artifacts/manifest-json), [run results](https://docs.getdbt.com/reference/artifacts/run-results-json).
