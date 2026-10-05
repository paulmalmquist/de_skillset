SELECT
    CAST(event_id AS STRING) AS event_id,
    COALESCE(CAST(work_order_id AS STRING), '__UNKNOWN__') AS work_order_id,
    CAST(occurred_at AS TIMESTAMP) AS occurred_at,
    CAST(duration_seconds AS NUMERIC) AS duration_seconds,
    CAST(cost_usd AS NUMERIC) AS cost_usd
FROM {{ ref('raw_operation_events') }}
