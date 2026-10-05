WITH operations AS (
    SELECT * FROM `synthetic.intermediate.operation_events`
)
SELECT DISTINCT event_id, work_order_id, cost_usd FROM operations
