# Worked Kimball example (synthetic; BigQuery dev only)

Two CSV seeds flow through explicit staging, an intermediate key projection, a Type 1 conformed work-order dimension, a transaction fact and a serving model. Every fact has one immutable event_id; costs are USD and durations are seconds. The unknown work order is __UNKNOWN__. Non-NULL orphan IDs fail relationship tests instead of silently disappearing. Source replay/incremental/SCD2 behavior is outside this small full-table example.

Install the dbt-bigquery adapter version approved by your organization, configure approved OAuth/ADC, and copy profiles.example.yml to an untracked profiles.yml in this directory. Set FLIGHTCHECK_DEV_PROJECT and FLIGHTCHECK_BQ_LOCATION to actual development values. Run dbt with --profiles-dir . from here:

```bash
dbt seed --target dev --profiles-dir .
dbt build --target dev --profiles-dir .
dbt compile --target dev --profiles-dir .
```

These commands CREATE/REPLACE dev datasets/models; they are not executed by the harness. The example profile does not specify production credentials. The default dbt schema macro produces datasets such as flightcheck_demo_staging and flightcheck_demo_mart. Audit the compiled manifest with config/example-dbt-policy.yml from the repository root.

The sample SQL and contracts are statically checked in the repository tests. No BigQuery/dbt execution is claimed until it runs in your approved dev environment. Part revision here is a Type 1 attribute; use a historical dimension when the reporting question requires as-of semantics.
