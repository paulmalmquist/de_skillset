# Model a business process at a declared grain

1. Name the business process and decisions the model must support. Ask the business owner to distinguish event, state and lifecycle questions.
2. Declare exactly what one row represents in business language. Then identify a deterministic key for that grain. Profile uniqueness and NULLs; a synthetic ID alone does not prove the business grain.
3. Select conformed dimensions, natural and surrogate keys, unknown/not-applicable members, history policy and role-playing dates.
4. Select facts at that grain. Specify unit, currency, sign convention, additive dimensions, zero/NULL semantics and calculation ownership. Derive ratios from their components, not averages of ratios.

Choose transaction facts for immutable events, periodic snapshots for entity state at a date, and accumulating snapshots for lifecycle milestones. Do not place work-order totals on operation-event rows without an allocation rule; do not sum inventory balances through time. Keep nonconforming grains in separate facts and drill across on shared dimensions. Bridges need an explicit allocation or distinct-entity counting rule.

Manufacturing design questions, not assertions about existing Relativity schemas:
- Is an operation uniquely identified within a work order, revision and attempt? Are rework and reversals new events?
- Is the part identified by part number plus revision and effectivity? Are lot and serial separate identities?
- Does a quality issue occur once per finding, affected unit, disposition, or inspection attempt?
- Are cost measures actual, standard, committed or forecast? Which currency and conversion date?
- Which timestamp means occurrence, source update, ingestion, and business reporting day?

Keep a bus matrix in `templates/bus-matrix.csv`. A reused column name is not a conformed dimension: its keys, attributes, meanings and change policy must agree.

For Type 2 history use half-open validity `[valid_from, valid_to)`. Prove no overlaps, exactly one current row under the adopted tombstone policy, and one matching version per event timestamp. Specify late dimension arrivals, correction of old intervals, replay behavior and unknown-member rekeying. Never join all fact history to the current dimension version by accident.

Output: a typed ModelSpec, source-to-target mapping, bus-matrix change, decision record, SQL, schema contract, key tests, relationship tests, interval tests where applicable, a parity scope and unresolved business decisions. The studio generates scaffolds from a specification; it does not discover source semantics or implement SCD merges for you. A dbt contract checks output shape/types; data tests and business approval remain necessary.
