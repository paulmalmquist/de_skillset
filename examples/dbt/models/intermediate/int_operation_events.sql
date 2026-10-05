SELECT
    event_id,
    TO_HEX(SHA256(work_order_id)) AS work_order_key,
    occurred_at,
    duration_seconds,
    cost_usd
FROM {{ ref('stg_operation_events') }}
