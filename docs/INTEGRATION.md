# Integrate with an existing dbt repository

Install this package in the same environment as your warehouse tooling. Copy/merge the skills and protocols; preserve existing instruction files and hook settings. The bundled skills link to root-relative protocol paths, so keep the `.claude/skills` and `protocols` structure together.

Declare published model metadata, in addition to actual column contracts and tests:

```yaml
version: 2
models:
  - name: fct_operation_event
    access: public
    config:
      contract:
        enforced: true
      meta:
        flightcheck:
          layer: mart
          owner: YOUR_REAL_OWNER
          grain: One row per immutable operation completion event
          keys: [event_id]
```

This snippet is metadata only; the studio emits full columns/tests from a supplied spec. Use the declarations supported by your installed dbt version. The manifest reader merges top-level `meta` and `config.meta`.

In the real data repository, run a CI sequence equivalent to:

```bash
dbt deps
dbt compile --target dev
python -m flightcheck.cli --policy config/policy.yml --out .flightcheck/architecture.json audit-manifest target/manifest.json
dbt build --target dev --select YOUR_REVIEWED_SELECTION
```

Add runtime freshness, grain, relationship, incremental and record-parity checks appropriate to that change. Check actual sources and consumer SQL outside dbt exposures. Upload sanitized review artifacts to an internal destination, not a public workflow artifact containing warehouse rows.

## Optional tool hooks

`.claude/settings.json` enables PostToolUse lint feedback on local SQL edits. Uncompiled Jinja produces explicit incomplete feedback. `.claude/settings.pretool.example.json` illustrates a PreToolUse query adapter; merge it only after replacing the matcher with the real tool and verifying its input schema. The wrapper denies unrecognized or non-read-only SQL. It does not sandbox Bash, generic Python or other connectors.

## Exception review

Copy a finding's exact fingerprint into the policy's `exceptions` list with owner, different reviewer, ticket, reason and UTC expiry. The ticket/reviewer are declarations; authenticate approval through your existing PR process. Recheck expired exceptions in CI. Exemptions do not turn the result into `clear`.
