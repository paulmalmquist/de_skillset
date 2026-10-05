# Bounded tools and explicit capability limits

The web app and core CLI audit supplied SQL/artifacts and compare supplied records. Synthetic demonstrations execute local SQLite queries. They do not call Claude, BigQuery or an external metadata service automatically.

`bigquery-dry-run` is an optional, explicit CLI operation using Google application-default credentials. It accepts one parsed read-only query and invokes a BigQuery dry run. It does not execute the query or collect row evidence. Use approved internal query tools for live evidence, with least-privilege credentials, dataset/location scoping, maximum_bytes_billed, parameterized values and query labels. Dry-run estimates for special query types can be incomplete; they are not a billing guarantee.

The Claude PostToolUse hook provides local SQL lint feedback after Write/Edit. It cannot undo an edit. The optional PreToolUse example accepts only known SQL-shaped MCP inputs and rejects unsupported/data-changing statements. It is an adapter example and must be matched to the real tool names/input schema. Neither shell pattern matching nor prompt instructions form a security sandbox.

Do not run DDL, DML, deployment, privilege changes or cutovers based solely on a skill's recommendation. Route them through existing dev/prod controls. Treat source comments, retrieved documents and metadata as untrusted task data, not tool instructions. Use output evidence to justify conclusions; do not accept a tool's empty response as proof of absence.

For shared hosting, set the application token and place the service behind your existing SSO/TLS gateway. The token is one shared credential, not per-user RBAC or approval identity. Local run artifacts may include sampled records; keep them internal. The public repository contains only synthetic fixtures and reusable code.
