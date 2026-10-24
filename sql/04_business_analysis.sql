-- ============================================================
-- 04. Анализ причин задержек и узких мест
-- ============================================================

-- 4.1 Сравнение перегруженных и недогруженных складов
WITH wh AS (
    SELECT
        warehouse_name,
        total_orders,
        avg_picking_minutes,
        avg_utilization,
        delay_rate
    FROM vw_warehouse_performance
)
SELECT
    CASE WHEN avg_utilization > 0.85 THEN 'высокая загрузка (>85%)'
         ELSE 'умеренная загрузка (<=85%)' END                     AS load_group,
    COUNT(*)                                                       AS warehouses,
    SUM(total_orders)                                              AS orders,
    ROUND(AVG(avg_picking_minutes), 1)                             AS avg_picking_minutes,
    ROUND(AVG(delay_rate), 2)                                      AS avg_delay_rate
FROM wh
GROUP BY load_group
ORDER BY load_group DESC;


-- 4.2 Узкое место внутри склада: этапы от заказа до отгрузки в часах
WITH stages AS (
    SELECT
        AVG(EXTRACT(EPOCH FROM (picking_started_at - order_created_at)) / 3600.0)
            AS queue_hours,
        AVG(EXTRACT(EPOCH FROM (picked_at - picking_started_at)) / 3600.0)
            AS picking_hours,
        AVG(EXTRACT(EPOCH FROM (packed_at - picked_at)) / 3600.0)
            AS packing_hours,
        AVG(EXTRACT(EPOCH FROM (shipped_at - packed_at)) / 3600.0)
            AS dispatch_wait_hours,
        AVG(EXTRACT(EPOCH FROM (delivered_at - shipped_at)) / 86400.0)
            AS transit_days
    FROM shipments s
    JOIN orders o ON o.order_id = s.order_id
    WHERE o.order_status = 'delivered'
),
totals AS (
    SELECT *, queue_hours + picking_hours + packing_hours + dispatch_wait_hours AS internal_hours
    FROM stages
)
SELECT 'Ожидание в очереди на сборку' AS stage, ROUND(queue_hours, 2) AS hours,
       ROUND(100.0 * queue_hours / internal_hours, 1) AS share_of_internal_pct FROM totals
UNION ALL
SELECT 'Сборка', ROUND(picking_hours, 2), ROUND(100.0 * picking_hours / internal_hours, 1) FROM totals
UNION ALL
SELECT 'Упаковка', ROUND(packing_hours, 2), ROUND(100.0 * packing_hours / internal_hours, 1) FROM totals
UNION ALL
SELECT 'Ожидание рейса', ROUND(dispatch_wait_hours, 2), ROUND(100.0 * dispatch_wait_hours / internal_hours, 1) FROM totals
ORDER BY hours DESC;


-- 4.2b Внутренний цикл склада против транзита
SELECT
    ROUND(AVG(EXTRACT(EPOCH FROM (shipped_at - order_created_at)) / 3600.0), 2)
                                                    AS avg_internal_hours,
    ROUND(AVG(EXTRACT(EPOCH FROM (delivered_at - shipped_at)) / 86400.0), 2)
                                                    AS avg_transit_days,
    ROUND(100.0 * AVG(EXTRACT(EPOCH FROM (shipped_at - order_created_at)) / 3600.0)
          / (AVG(EXTRACT(EPOCH FROM (shipped_at - order_created_at)) / 3600.0)
             + 24.0 * AVG(EXTRACT(EPOCH FROM (delivered_at - shipped_at)) / 86400.0)), 1)
                                                    AS internal_share_of_lead_time_pct
FROM shipments s
JOIN orders o ON o.order_id = s.order_id
WHERE o.order_status = 'delivered';


-- 4.3 Риск задержки в разрезе «склад + способ доставки»
SELECT
    warehouse_name,
    method_name,
    delivered_orders,
    avg_picking_minutes,
    avg_transit_days,
    delay_rate
FROM vw_sla_analysis
ORDER BY delay_rate DESC
LIMIT 12;


-- 4.4 Заказы, оформленные после 16:00: успевают ли на вечерний рейс
SELECT
    CASE
        WHEN EXTRACT(HOUR FROM order_created_at) < 12 THEN 'до 12:00'
        WHEN EXTRACT(HOUR FROM order_created_at) < 16 THEN '12:00-16:00'
        WHEN EXTRACT(HOUR FROM order_created_at) < 20 THEN '16:00-20:00'
        ELSE 'после 20:00'
    END                                                            AS order_window,
    COUNT(*)                                                       AS orders,
    ROUND(AVG(EXTRACT(EPOCH FROM (shipped_at - order_created_at)) / 3600.0), 2)
                                                                   AS avg_hours_to_ship,
    ROUND(100.0 * AVG(CASE WHEN delivered_at::date > promised_date THEN 1 ELSE 0 END), 2)
                                                                   AS delay_rate
FROM orders o
JOIN shipments s ON s.order_id = o.order_id
WHERE o.order_status = 'delivered'
GROUP BY order_window
ORDER BY order_window;


-- 4.5 Товары и категории в задержанных заказах
SELECT
    c.category_name,
    COUNT(*)                                                       AS delivered_items,
    ROUND(100.0 * AVG(CASE WHEN f.is_delayed THEN 1 ELSE 0 END), 2) AS delay_rate
FROM vw_order_facts f
JOIN order_items i ON i.order_id = f.order_id
JOIN products p    ON p.product_id = i.product_id
JOIN categories c  ON c.category_id = p.category_id
GROUP BY c.category_name
ORDER BY delay_rate DESC;


-- 4.6 Вклад складов в общее число задержанных заказов
SELECT
    warehouse_name,
    COUNT(*) FILTER (WHERE is_delayed)                             AS delayed_orders,
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_delayed)
          / SUM(COUNT(*) FILTER (WHERE is_delayed)) OVER (), 2)    AS share_of_all_delays,
    ROUND(100.0 * AVG(CASE WHEN is_delayed THEN 1 ELSE 0 END), 2)  AS delay_rate
FROM vw_order_facts
GROUP BY warehouse_name
ORDER BY delayed_orders DESC;


-- 4.7 Пиковые периоды: объём и качество сервиса в пик против обычных дней
WITH peaks(peak_name, start_date, end_date) AS (
    VALUES
        ('Летняя распродажа', DATE '2025-07-10', DATE '2025-07-24'),
        ('Чёрная пятница',    DATE '2025-11-23', DATE '2025-12-01'),
        ('Декабрьский пик',   DATE '2025-12-10', DATE '2025-12-22')
)
SELECT
    COALESCE(p.peak_name, 'Обычные дни')                           AS period_type,
    COUNT(*)                                                       AS delivered_orders,
    ROUND(COUNT(*)::numeric / COUNT(DISTINCT f.order_date), 1)     AS orders_per_day,
    ROUND(AVG(f.picking_minutes), 1)                               AS avg_picking_minutes,
    ROUND(100.0 * AVG(CASE WHEN f.is_delayed THEN 1 ELSE 0 END), 2) AS delay_rate
FROM vw_order_facts f
LEFT JOIN peaks p ON f.order_date BETWEEN p.start_date AND p.end_date
GROUP BY p.peak_name
ORDER BY delivered_orders DESC;


-- 4.8 Задержка по длительности: сколько заказов опаздывают сильно
SELECT
    CASE
        WHEN delay_days <= 0 THEN '1. в срок'
        WHEN delay_days = 1  THEN '2. 1 день'
        WHEN delay_days = 2  THEN '3. 2 дня'
        ELSE '4. 3+ дня'
    END                                                            AS delay_bucket,
    COUNT(*)                                                       AS orders,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)             AS share_pct
FROM vw_order_facts
GROUP BY delay_bucket
ORDER BY delay_bucket;


-- 4.9 Склад с худшим SLA в разрезе способа доставки
WITH ranked AS (
    SELECT
        warehouse_name,
        method_name,
        delivered_orders,
        delay_rate,
        RANK() OVER (PARTITION BY method_name ORDER BY delay_rate DESC) AS rnk
    FROM vw_sla_analysis
)
SELECT method_name, warehouse_name, delivered_orders, delay_rate
FROM ranked
WHERE rnk = 1
ORDER BY delay_rate DESC;


-- 4.10 Механизм задержки: пропуск вечернего рейса расходует весь буфер SLA
-- SLA = дата заказа + плановый транзит + 1 день на обработку.
-- Отгрузка в день заказа оставляет сутки запаса, отгрузка на следующий день
-- съедает буфер полностью, поэтому любая задержка в пути превращается в опоздание.
SELECT
    (f.shipped_at::date - f.order_date)                             AS dispatch_lag_days,
    COUNT(*)                                                        AS orders,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)              AS share_pct,
    ROUND(AVG(f.actual_transit_days), 2)                            AS avg_transit_days,
    ROUND(100.0 * AVG(CASE WHEN f.is_delayed THEN 1 ELSE 0 END), 2) AS delay_rate
FROM (
    SELECT f.*,
           (f.delivered_at::date - f.shipped_at::date)              AS actual_transit_days
    FROM vw_order_facts f
) f
GROUP BY dispatch_lag_days
ORDER BY dispatch_lag_days;


-- 4.11 Сколько задержек связано с пропуском вечернего рейса
WITH base AS (
    SELECT
        f.*,
        (f.shipped_at::date - f.order_date)                         AS dispatch_lag,
        (f.delivered_at::date - f.shipped_at::date)                 AS actual_transit,
        r.base_transit_days + CASE f.method_id
            WHEN 'DM-01' THEN 0 WHEN 'DM-02' THEN 0
            WHEN 'DM-03' THEN 1 WHEN 'DM-04' THEN 1 ELSE 2
        END                                                         AS planned_transit
    FROM vw_order_facts f
    JOIN regions r ON r.region_id = f.region_id
)
SELECT
    COUNT(*) FILTER (WHERE dispatch_lag = 1)                        AS shipped_next_day,
    COUNT(*)                                                        AS delivered_orders,
    ROUND(100.0 * COUNT(*) FILTER (WHERE dispatch_lag = 1) / COUNT(*), 1)
                                                                    AS next_day_ship_pct,
    COUNT(*) FILTER (WHERE dispatch_lag + actual_transit - planned_transit - 1 > 0)
                                                                    AS delayed_orders,
    ROUND(100.0 * COUNT(*) FILTER (WHERE dispatch_lag + actual_transit - planned_transit - 1 > 0
                                     AND dispatch_lag = 1)
          / NULLIF(COUNT(*) FILTER (WHERE dispatch_lag + actual_transit - planned_transit - 1 > 0), 0), 1)
                                                                    AS delayed_with_late_dispatch_pct
FROM base;


-- 4.12 Пропуск рейса по складам
WITH base AS (
    SELECT f.warehouse_name, (f.shipped_at::date - f.order_date) AS dispatch_lag,
           f.is_delayed
    FROM vw_order_facts f
)
SELECT
    warehouse_name,
    COUNT(*)                                                        AS delivered_orders,
    ROUND(AVG(dispatch_lag), 3)                                     AS avg_dispatch_lag,
    ROUND(100.0 * AVG(CASE WHEN dispatch_lag = 1 THEN 1 ELSE 0 END), 2)
                                                                    AS next_day_ship_pct,
    ROUND(100.0 * AVG(CASE WHEN is_delayed THEN 1 ELSE 0 END), 2)   AS delay_rate
FROM base
GROUP BY warehouse_name
ORDER BY delay_rate DESC;

