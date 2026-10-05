# Prove incremental and historical correctness

Declare the mutable unit: append-only event, latest record, snapshot row, or historical version. Define the unique key, partition key, event time, update time, ingestion time, watermark and maximum expected lateness. Source hard deletes, soft deletes and correction events need explicit policies.

Required experiments in dev:
1. Full refresh of a bounded snapshot establishes a reference.
2. Incremental build over the same snapshot reconciles to the reference by records.
3. Replay the same batch twice; the second run produces no unintended changes.
4. Inject an older event with a recent ingestion timestamp; it must appear according to the lateness policy.
5. Inject a correction older than the lookback window; exercise a separate restatement path.
6. Inject duplicate source keys and equal timestamps; prove deterministic tie breaking before MERGE.
7. Exercise deletion, retraction and reopened workflow cases.
8. Re-run after a partial failure; record atomicity, checkpoints and the recovery action.

A fixed lookback is a cost/correctness tradeoff, not a proof that all late data is captured. Watermarks must not advance on partial failure. Use update/ingestion time when source semantics require it; preserve occurrence time for business reporting.

For backfills, estimate scanned/rewritten bytes, name exact partitions, set budgets, record source snapshot and plan resumable batches. Reconcile every partition plus cross-partition keys, conformed dimensions and aggregates. Test restoration to the prior version or compatibility interface. Keep production execution in the organization's deployment system; the app never performs warehouse DDL or writes.

Output: a replay matrix with observed results, idempotency evidence, late/delete policy, partition manifest, reconciliation results and rollback instructions. No destructive full-refresh recommendation without naming affected downstream consumers and recovery evidence.
