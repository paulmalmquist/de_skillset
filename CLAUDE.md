# Flightcheck — Relativity #DATA engineering harness

Read `AGENTS.md`, then `config/policy.yml`. Use the narrowest matching skill under `.claude/skills/`; load its referenced protocol only when needed. These files define a proposed engineering standard; verify actual organizational policy in the environment handoff.

## Task router

| Task / symptom | Start here | Follow with |
|---|---|---|
| Empty/zero/missing results | `/prove-control` | `/check-freshness`, `/resolve-authority` |
| Numbers disagree / parity | `/reconcile-records` | `/trace-record-loss`, `/prevent-join-fanout` |
| Reports query stg/int | `/audit-consumption` | `/inventory-legacy`, `/migrate-legacy-query` |
| New fact/dimension/mart | `/design-kimball` | `/design-conformed-dimensions`, `/handle-scd2` |
| Incremental or historical fix | `/validate-incremental` | `/plan-backfill` |
| Metric inconsistency | `/define-metric` | `/reconcile-records` |
| Completion/certification | `/review-data-change` | `/certify-data-product` |
| Repeated mistake or correction | `/capture-engineering-learning` | Held-out evaluation, independent review |
| Query cost or runtime claim | `/profile-bigquery` | Actual job evidence from approved tools |

## Working loop

Discover → prove controls/freshness/authority → declare grain → reproduce → implement in dev → reconcile → review → record the lesson.

Declare the task, context, evidence location and next action in `templates/task-packet.md`. Preserve continuity by writing facts and artifact paths, not an ever-growing narrative. `docs/ENVIRONMENT-HANDOFF.md` lists the inputs still needed for the real warehouse.

The app is a deterministic harness. It does not run Claude or provision warehouse access. Use the installed Claude Code session for reasoning and the CLI for repeatable checks. A reviewer role is provided in `.claude/agents/data-reviewer.md`; use it when an independent pass is appropriate, with raw artifacts instead of the implementer's intended answer.

## Useful commands

```bash
python -m flightcheck.cli --policy config/policy.yml audit-sql compiled.sql --layer consumer
python -m flightcheck.cli --policy config/policy.yml audit-manifest target/manifest.json
python -m flightcheck.cli diff left.json right.json --keys event_id
python -m flightcheck.cli trace stages.json --keys event_id
python -m flightcheck.cli scaffold contract.json --directory proposed-model
python -m pytest
python -m flightcheck.cli eval
```

Exit code 1 means blocked/mismatch/inconclusive/failed or incomplete coverage; 2 means invalid input or execution error. Static `review` means warnings or exceptions exist. These statuses are not production certification.
