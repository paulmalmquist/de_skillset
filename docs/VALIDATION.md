# Validation record · 2026-10-05

## Executed

- Editable installation of the package and development dependencies succeeded.
- **63 pytest tests passed** across the engine, API, hooks, schemas, CLI exit behavior, compiled-SQL fixture checks and catalog consistency.
- **13/13 deterministic regression scenarios passed**, executing synthetic SQLite controls and query results where applicable.
- **19 Claude skills and 9 protocols** passed frontmatter, reference and packaged-catalog consistency checks.
- Browser JavaScript passed `node --check`.
- A headless Chromium/Playwright pass completed **11 workflow checks**: desktop graph interaction; five investigation scenarios; blocked/clear SQL paths; model generation and a real ZIP download; skill search/modal; evaluations and run history; and 390px mobile layout. No page/console errors were observed. Results are in `browser-validation.json`; screenshots are in `screenshots/`.
- An independent agent followed the reconciliation and trace skills against raw fixture artifacts. It reproduced the missing key, duplicate grain and changed cost; checked the synthetic mechanism; and explicitly withheld claims about real warehouse correctness. This was one qualitative forward test, not a scored Claude benchmark.

The forward test exposed an ambiguous successful exit code from the trace command despite reported differences. The command now returns a nonzero result for mismatched/inconclusive stage populations and has a regression test. Browser testing exposed grid overflow on mobile; the graph now scrolls inside its panel.

One dependency emitted a Starlette/httpx test-client deprecation warning. Tests still passed. The harness does not suppress this warning.

## Not executed / not claimed

- No live BigQuery queries, dbt builds against BigQuery, production changes, warehouse credentials, or external metadata writes.
- No authenticated certification approval or enterprise SSO/RBAC integration.
- The worked dbt project's BigQuery SQL and configured layer paths were checked statically; its actual adapter compile/build remains an environment-specific dev task.
- Docker configuration is supplied but was not built in this environment.
- Agent evaluation prompts are supplied for future repeatable Claude/model benchmarking; no benchmark win rate is claimed.

Browser tooling in this environment required a locally provisioned Chromium executable because the standard browser download was unavailable. The committed browser script uses ordinary Playwright and optionally accepts `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`; the provisioned binary is not included in this repository.

Reproduce with the commands in `TESTING.md`. Bind future validation records to the actual commit, policy hash and source snapshot being reviewed.
