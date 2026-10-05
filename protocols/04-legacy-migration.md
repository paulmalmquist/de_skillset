# Strangle a legacy query with evidence

1. Preserve the original SQL, report definitions, parameters, schedules, source watermarks and result contract. Identify the owner and consumers. Rank migrations by business impact, usage, bypass depth, grain ambiguity and change risk.
2. Establish gates 0–2. Freeze an agreed comparison population/snapshot and record the original code hash. Capture production behavior with authorized read-only tools; implement in dev.
3. Inventory hidden business rules: filters, join types, rounding, default values, current-only dimension joins, timezone boundaries, deduplication, currencies and security predicates.
4. Profile the apparent grain. Reproduce each suspected defect with a record witness. Separate intended legacy behavior from acknowledged legacy bugs. The old query is a baseline, not automatically the truth.
5. Design a target fact/dimension model. Write a source-to-target mapping and a decision record for each intentional semantic change. Preserve the legacy output using a compatibility view when useful.
6. Reconcile both directions by key and column over representative and full required windows: empty partitions, month ends, late events, deleted parents, duplicate inputs, rework, NULLs and backfills. Agree explicit tolerances and exclusions before running the comparison.
7. Measure query cost, latency and partition pruning in dev. Dry-run byte estimates do not prove runtime performance or correctness.
8. Shadow the consumer, obtain owner acceptance and switch one consumer at a time. Monitor usage and semantic drift. A switch is a separately reviewed deployment action.
9. Retire internal access only after observed usage has cleared for an agreed period, documentation points to the new interface, and rollback has been rehearsed.

Deliver a migration packet using `templates/migration-plan.md`: consumer inventory, old/new query hashes, declared grain, mapping, reconciliations, approved semantic deltas, performance evidence, owner review, cutover sequence, rollback target and deprecation deadline. Do not silently rewrite business semantics to force parity or preserve a known defect merely to keep totals unchanged.
