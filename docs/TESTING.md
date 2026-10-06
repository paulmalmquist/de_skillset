# Verification

## Automated engine/API tests

```bash
python -m pip install -e '.[dev]'
python -m pytest
python -m flightcheck.cli eval
python scripts/check_catalog.py
node --check flightcheck/web/app.js
```

Tests exercise SQL CTE scope and read-only parsing, explicit columns, layer bypasses, exact exceptions/expiry, evidence short-circuiting, timestamps/context, duplicate/composite/NULL keys, missing-versus-NULL fields, numeric tolerances, trace binding, incomplete lineage/cycles, scaffold contracts and SCD2 tests, API authentication/origin checks, ZIP export, and ledger corruption detection.

The deterministic evaluation suite is not a Claude benchmark. `evals/agent-cases.json` supplies prompts and grading criteria for future model evaluations. Keep holdout examples separate from prompt authoring and record actual agent model/tool versions.

## Browser smoke test

Start the app on loopback. Verify desktop and mobile layouts and capture console errors before navigation.

1. Open Mission control; confirm the actual demo shows six baseline and six candidate rows, and two consumer bypass edges.
2. Select a graph node; confirm owner/grain/impact details update.
3. Run the masked-loss investigation; inspect missing, duplicate and changed-value witnesses.
4. Run control-failure, stale and wrong-environment scenarios; confirm later gates are not run. Run clean; confirm ready-for-review, not certified.
5. Audit the legacy query; then load and audit the published example. Without an exact registration it must block with PUBLISHED_CONTRACT. A constant query can exercise the static-clear path. Import a manifest and verify findings/lineage update.
6. Generate the Kimball model and download its ZIP; inspect the actual files. Break a grain key and confirm generation is blocked.
7. Search skills, open a skill/protocol, copy its invocation and navigate back using keyboard.
8. Run evaluations; verify results and actual run ledger entries. Refresh; confirm persistence. Export JSON and a Claude handoff.
9. Repeat navigation on a 390px viewport; no page-wide horizontal overflow should occur.
10. Import a current clean evidence bundle: control/freshness/authority must remain unverified, and the page must explain sample redaction. Truncate both sides without altering total_rows: matching subsets must show incomplete population coverage.

`scripts/browser_smoke.cjs` automates the principal paths with Playwright when installed. Set `FLIGHTCHECK_URL` to the local server. It writes screenshots and a JSON result to ignored `.flightcheck/browser/`.

```bash
npm ci
npx playwright install chromium
# In another terminal, start the app as above.
npm run test:browser
```

## Real environment verification still required

Execute dbt compile/build with your installed adapter and actual dev schemas, warehouse controls and freshness checks, full required record-parity windows, real consumer inventory, auth/SSO integration and review/cutover rehearsal. No live warehouse execution or production approval is claimed by the synthetic tests.
