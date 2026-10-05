SELECT
    event_id,
    work_order_key,
    occurred_at,
    duration_seconds,
    cost_usd
FROM {{ ref('int_operation_events') }}
