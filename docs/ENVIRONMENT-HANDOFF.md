# Connect the harness to the real #DATA environment

The repository works immediately on synthetic fixtures. Complete this mapping before treating it as an organizational check.

| Input | Current implementation | What to confirm |
|---|---|---|
| Warehouse | BigQuery SQL dialect; optional dry-run CLI | Dev project, location, approved ADC/tool identity, exact datasets. |
| Layer policy | `config/policy.yml` synthetic relation patterns; no live publication registrations | Actual layer mappings plus exact reviewed publication contracts and expiries. |
| dbt | Manifest v9–v12 reader; compiled SQL inspection | Core/adapter versions, project path, dev target, compile commands, model metadata placement. |
| Consumers | dbt exposures + pasted/uploaded SQL | Power BI, Grafana, Dreamcatcher, scheduled queries, views and direct notebook users. |
| Freshness | 24h source / 4h evidence default proposals | Object-specific SLA and complete population/window definition. CLI can use a different policy per domain. |
| Keys and dimensions | Typed model contracts; examples only | Work-order/operation/attempt grain, part revision, lot/serial, machine, site and calendar authority. |
| History | SCD2 interval tests and design protocol | Current-member/tombstone rule, effectivity, late corrections and unknown members. |
| Metrics | Contract template | Authoritative definitions, unit/currency policy and semantic layer ownership. |
| Metadata | No live publisher | OpenMetadata services, entity IDs, API version, test/certification mapping and permissions. |
| Review | Packet templates and local review states | Code owners, authenticated approval system, certification lifecycle and deployment controls. |
| Evidence | Local SQLite; imported samples redacted; 7-day retention; imports remain unverified | Authoritative job verification, full-window coverage, internal evidence destination, access and retention rules. |
| Tool harness | Local CLI + optional query hook example | Real Claude MCP tool names/schemas and allowlisted capabilities. |

## First useful integration pass

1. Select one real problem report and its current SQL; identify the report owner and business question.
2. Export the dev dbt manifest after compile, plus current report/application dependencies from their owning systems.
3. Add exact dataset mappings and `meta.flightcheck` declarations. Audit and identify incomplete coverage explicitly.
4. Establish controls, watermarks and a common snapshot; create a bounded, permitted evidence bundle without copying internal records into this public repository.
5. Use the legacy-migration skill to design the target grain and published interface. Generate a scaffold, implement dev mappings and run dbt tests.
6. Reconcile records, resolve intentional semantic deltas with the owner and assemble the review packet.
7. Integrate the CLI in the actual warehouse CI; make that check required only after measuring false positives and testing exception review.

Use `docs/CANDIDATE-CI.md` for the executable candidate artifact gate. It requires a full same-invocation dbt build and current consumer inventory; compile-only, stale, mismatched, missing or failed outcomes block. Passing this static gate is not warehouse attestation or production approval.

Store environment overrides and private evidence in the internal warehouse repository or ignored `private/` directory. Do not commit credentials. Existing dev/prod authority remains authoritative; these proposed protocols do not grant additional permissions.
