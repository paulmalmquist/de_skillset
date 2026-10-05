-- Type 1 example. It intentionally does not represent historical work-order attributes.
SELECT
    TO_HEX(SHA256(work_order_id)) AS work_order_key,
    work_order_id,
    part_number,
    part_revision
FROM {{ ref('stg_work_orders') }}
