# Legacy migration plan

## Scope and semantics
Consumer, owner, usage evidence, current dependencies, baseline SQL hash, candidate SQL hash,
declared grain, population/window, preserved behaviors and separately approved bug fixes.

## Implementation
Source-to-target mapping, conformed dimensions, compatibility interface, tests,
incremental/deletion policy, access controls and downstream blast radius (including unknown coverage).

## Verification
Controls, source watermarks, authoritative contexts, record differences, tolerances,
late/NULL/duplicate/rework cases, full required window, query jobs, cost/latency and artifacts.

## Cutover and recovery
Shadow period, owner acceptance, each consumer's switch, observability thresholds,
rollback target/command, recovery rehearsal, retirement usage window and exception expiry.
