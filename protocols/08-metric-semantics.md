# One metric, one explicit definition

Before implementing a metric, declare name, business question, owner, fact grain, population/filter, numerator, denominator, allowed dimensions, unit/currency, time basis, aggregation, NULL/zero handling, freshness and exclusions.

An aggregate such as total completed operations is a metric. A dimension such as facility is a slicing attribute. A row-level measure such as duration_seconds can feed several metrics. A chart is a presentation. A KPI adds a target/threshold and decision context. Do not register every display label as a separate authoritative metric.

Reuse the same semantic definition across Power BI, Grafana and Dreamcatcher. Record report-specific adaptations and identify which platform owns the executable definition. A matching number today does not establish matching semantics: test filters, security context, timezone boundaries, weighted averages, ratios, rework and excluded populations.

For metadata publication, map internal model/column IDs to OpenMetadata entity identifiers in the actual environment. Do not invent API versions, service names, certification tags or connector behavior. This repository provides a mapping template, not a connected metadata publisher.

Output: `templates/metric-contract.yml`, test cases for edge conditions, lineage to governed facts/dimensions, consumers and an owner-reviewed version. Keep any display-only calculation visibly separate from the governed definition.
