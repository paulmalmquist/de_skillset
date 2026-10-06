# Red-team fixes

The October 2026 sweep reproduced false passes despite the original 63 passing tests. The changes below add adversarial regression coverage without asserting that synthetic tests validate the company's warehouse.

| Finding | Implemented behavior |
|---|---|
| SQL dependency omitted from dbt graph | Resolve physical identities, retain inferred impact edges, block missing/ambiguous lineage. |
| Any test counted as sufficient | Check exact typed keys, null tests, uniqueness and conservative blocking test configurations. |
| One-sided/tautological join predicate | Require a cross-input comparison on each OR path; block unsupported nested groups. Actual cardinality still needs execution. |
| NULL SCD2 natural keys escaped overlap checks | Generate natural-key not-null tests and a singular missing-business-key test alongside interval/current/overlap checks. |
| Dataset name implied publication | Require exact, unexpired interface registration for standalone consumers. |
| Exception survived SQL changes | Bind SQL finding fingerprints to the complete query hash. |
| Imported evidence appeared ready | Mark control/freshness/authority as unverified; missing coverage as incomplete. Import never produces ready-for-review. |
| Harness CI confused with candidate verification | Add `check-candidate` for actual bound dbt/consumer artifacts; no release approval or attestation claim. |
| Local evidence exposed record witnesses | Redact imported samples before API storage/response/export; retain statistics. Seven-day default retention and owner-only database permissions. |
| App factory bypassed CLI host guard | Enforce allowed hosts and local clients without a token in the application middleware; require explicit Bearer authentication when configured. |

Independent review also covered nested join syntax, disabled/filtered tests, incremental `this` reads, ordinary versus ephemeral ancestors, and singular-test metadata. Follow-up review and verification results are recorded in VALIDATION.md.

## Integration work remains

No live BigQuery/job attestation adapter, enterprise SSO/RBAC, complete consumer discovery, scored Claude benchmark, or real business-owner certification has been fabricated. Configure these in the approved internal environment. The new candidate gate only checks consistency and completeness of artifacts supplied by a trusted runner. A malicious runner or editable approval policy remains outside that trust boundary.

First acceptance exercise: migrate one actual legacy query in dev, identify its true consumers and grain, capture controls/complete windows from authoritative jobs, execute tests, reconcile old/new semantics with approved deltas, and rehearse rollback. Pay particular attention to operation versus attempt, rework, revision effectivity, lot/serial identity and historical corrections.
