# Assemble an evidence-backed review packet

Treat certification as a state of a particular object version, policy version and evidence window. A changed query, schema, source, grain, access policy or material business rule invalidates the relevant checks.

| Claim | Minimum evidence |
|---|---|
| Structurally publishable | Owner, declared grain/keys, column types/descriptions, allowed dependencies, schema contract, semantic definitions. |
| Correct in scope | Controls, fresh/authoritative source context, executed data tests, record reconciliation, invariants and approved semantic deltas. |
| Operable | Scheduling/SLA, incremental replay, lineage, failure alerts, cost bounds, backfill and rollback. |
| Safe to migrate consumers | Complete consumer inventory, access review, owner acceptance, shadow results and cutover plan. |

Report statuses as proposed, blocked, ready-for-review, or approved through the organization's review system. The local app does not issue approval or production certification. Self-entered reviewer names and checksum matches are not authenticated sign-off.

Use `templates/review-packet.md`. Bind evidence to code commit, config hash, model/query hash, environment, source snapshot, query/job IDs, observed-at times and a reproducible command. Save records in the approved internal evidence store; sanitized samples may accompany a PR. The local ledger is a convenience store and must not be treated as immutable or access-controlled enterprise audit storage.

Make the required CI check run the scanner against the real candidate manifest and compiled SQL. The repository's own CI validates this harness and synthetic fixtures only. Protect changes to policy, exceptions, hooks, skills and eval expectations with independent review. CI cannot be made authoritative by a prompt; configure branch protection and warehouse access separately.
