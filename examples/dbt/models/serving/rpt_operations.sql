-- One row per event. Type 1 work-order attributes are current attributes by design.
SELECT
    e.event_id,
    d.work_order_id,
    d.part_number,
    d.part_revision,
    e.occurred_at,
    e.duration_seconds,
    e.cost_usd
FROM {{ ref('fct_operation_event') }} e
LEFT JOIN {{ ref('dim_work_order') }} d
    ON e.work_order_key = d.work_order_key
