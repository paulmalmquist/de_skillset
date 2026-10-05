SELECT
    CAST(work_order_id AS STRING) AS work_order_id,
    CAST(part_number AS STRING) AS part_number,
    CAST(part_revision AS STRING) AS part_revision
FROM {{ ref('raw_work_orders') }}
