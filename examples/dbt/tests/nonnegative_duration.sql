SELECT event_id, duration_seconds
FROM {{ ref('fct_operation_event') }}
WHERE duration_seconds < 0 OR duration_seconds IS NULL
