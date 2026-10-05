# Published interfaces and internal layers

Default dependency rules are project policy, not a claim that Kimball requires one universal staging architecture.

| Target | Allowed direct parents |
|---|---|
| staging | source |
| intermediate | staging, intermediate |
| mart | staging, intermediate, mart |
| serving | mart, serving |
| consumer | mart, serving |

Staging standardizes source names/types and records provenance. Intermediate models isolate transformations and joins. Marts express governed business grains and dimensions. Serving models shape published marts for a specific consumption pattern. A broad serving table is acceptable when its grain and metric semantics remain explicit.

Power BI, Grafana, Dreamcatcher and ad hoc published reports are consumers. Do not grant certification to a report that reads `stg_` or `int_` tables merely because its totals look right. Inventory query text, views, materialized views, scheduled queries, stored procedures and application code, including dependencies outside dbt exposures.

Use manifest `meta.flightcheck.layer` for models and explicit relation patterns for SQL. Ambiguous or missing mappings remain blocked. SQL is parsed with SQLGlot scope resolution so CTE aliases are not mistaken for physical tables. Uncompiled Jinja, dynamic SQL and unsupported table functions require compiled SQL or registered lineage; they are not silently approved.

Hardcoded SQL may bypass dbt `ref` lineage. Audit compiled SQL as well as the manifest graph. Artifact generation time is not a source watermark. Missing compiled SQL reduces coverage. External consumers and undocumented warehouse views make blast radius incomplete.

Migration exceptions match one finding fingerprint, name an owner and different reviewer, reference a ticket, explain the rationale and expire at a timezone-aware timestamp. The repository verifies the shape and expiry, not the identity of the approver. Review exceptions through protected code review. Never waive parse/read-only failures, unresolved dependencies or cycles to achieve a green check.

Example relation patterns in `config/policy.yml` are synthetic. Replace them with your actual projects/datasets before using audits as required checks. Enforcement of warehouse access belongs in IAM/authorized views and deployment controls; the scanner cannot stop an unconfigured external tool from querying a table.
