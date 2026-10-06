# Evidence gates: cheapest disproof first

Run the gates in this order. A failed prerequisite means later inference is unsupported; it does not mean the business answer is zero. Record pass, fail, needs-evidence, not-run, or not-applicable. Never convert an unexecuted check into a pass.

| Gate | Action | Required evidence | Stop condition |
|---|---|---|---|
| 0 · Control query first | Run a known-positive control through the same connector, principal, project, relation scope and snapshot as the investigation. | Expected positive result, observed result, job/tool ID and context hash. | Error, permission issue, truncated response, unexpected empty result, different context. |
| 1 · Freshness before inference | Read both source watermark and observation timestamp. | UTC timestamps, ingestion SLA, event-time coverage, partition/window. | Stale, missing, future or inconsistent timestamps. |
| 2 · Ask the owner of the fact | Resolve the warehouse object, dbt artifact and BI/application dependency from their owning systems. | Fully qualified relation, principal, dev target, snapshot, generated-at time and source/version provenance. | Wrong environment, undocumented alias, inaccessible owning system or incomparable snapshots. |
| 3 · Diff records, not counts | Compare keyed records in both directions, values, missing fields, nulls and multiplicity. | Grain keys, full population/window, tolerances by measure, missing/new keys, changed columns, duplicates and representative witnesses. | Any unexplained difference, ambiguous grain or both sides empty. |
| 4 · Isolate, then bisect | Materialize relevant boundaries and follow a failing key. | Stage SQL, before/after key sets, multiplicities and first observed divergence. | A hypothesis without a reproducing join/filter/expression witness. |

The CLI `demo` runs controls and queries against a synthetic SQLite database. `evidence` validates supplied observations; it does not authenticate the warehouse job that allegedly produced them. Its hashes bind content, not truth. `diff` alone bypasses prerequisite gates and must never be presented as full evidence certification.

Imported controls, freshness and authority are labeled `unverified`, never pass. Supply each observation's population definition/ID, total result rows, extraction completeness and source-window completeness. Missing declarations, mismatched scopes or truncated extraction yield `incomplete`, even when supplied rows agree. Declarations are not attestation: imported bundles cannot become ready-for-review. Bind candidate_commit and manifest_hash for handoff; retrieve actual jobs through the approved warehouse identity before promoting any claim.

For live work, select a sentinel known to exist within the same source/time/RLS scope. `SELECT 1` tests SQL execution, not table access or population coverage. A table with legitimately zero rows needs independent authoritative population evidence; do not invent a positive sentinel. Record this as an investigation requiring review.

Compare old/new implementations at the same logical cutoff, timezone, source versions and access policy. If a migration crosses projects, create and review an explicit equivalence mapping; the supplied evaluator conservatively requires matching projects. A row limit or sample is useful for debugging but cannot establish full parity. Summaries must name the compared population, excluded fields, numeric tolerances, timezone, and residual uncertainty.

Use `python -m flightcheck.cli --policy config/policy.yml demo --case masked-loss`. Imported bundles follow `schemas/evidence.schema.json`. Refresh example timestamps by executing a new demo; never edit stale timestamps merely to make a gate pass.
