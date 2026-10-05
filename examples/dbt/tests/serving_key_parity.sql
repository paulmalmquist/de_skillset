SELECT COALESCE(f.event_id, r.event_id) AS event_id
FROM {{ ref('fct_operation_event') }} f
FULL OUTER JOIN {{ ref('rpt_operations') }} r ON f.event_id = r.event_id
WHERE f.event_id IS NULL OR r.event_id IS NULL
