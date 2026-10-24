-- ============================================================
-- 02. Эффективность складов
-- ============================================================

-- 2.1 Сводка по складам: объём, скорость сборки, загрузка, задержки
SELECT
    warehouse_name,
    total_orders,
    orders_share,
    revenue,
    avg_picking_minutes,
    avg_fulfillment_hours,
    avg_utilization,
    peak_utilization,
    overloaded_days_share,
    delay_rate,
    on_time_rate
FROM vw_warehouse_performance
ORDER BY total_orders DESC;


-- 2.2 Сравнение склада со средним по сети
WITH network AS (
    SELECT
        ROUND(AVG(avg_picking_minutes), 1) AS net_picking,
        ROUND(AVG(delay_rate), 2)          AS net_delay,
        ROUND(AVG(avg_utilization), 3)     AS net_utilization
    FROM vw_warehouse_performance
)
SELECT
    w.warehouse_name,
    w.avg_picking_minutes,
    ROUND(100.0 * (w.avg_picking_minutes - n.net_picking) / n.net_picking, 1)
                                            AS picking_vs_network_pct,
    w.avg_utilization,
    ROUND(100.0 * (w.avg_utilization - n.net_utilization) / n.net_utilization, 1)
                                            AS utilization_vs_network_pct,
    w.delay_rate,
    ROUND(w.delay_rate - n.net_delay, 2)    AS delay_vs_network_pp
FROM vw_warehouse_performance w
CROSS JOIN network n
ORDER BY w.avg_picking_minutes DESC;


-- 2.3 Загрузка складов по дням: долгие дни и перегрузка
SELECT
    w.warehouse_name,
    COUNT(*)                                                       AS days_in_period,
    ROUND(AVG(l.utilization), 3)                                   AS avg_utilization,
    ROUND(MAX(l.utilization), 3)                                   AS max_utilization,
    COUNT(*) FILTER (WHERE l.utilization > 1.0)                    AS days_over_capacity,
    ROUND(100.0 * COUNT(*) FILTER (WHERE l.utilization > 1.0) / COUNT(*), 2)
                                                                   AS overload_share
FROM vw_warehouse_daily_load l
JOIN warehouses w ON w.warehouse_id = l.warehouse_id
GROUP BY w.warehouse_name
ORDER BY avg_utilization DESC;


-- 2.4 Время сборки и задержки по уровню загрузки склада
SELECT
    CASE
        WHEN f.utilization IS NULL              THEN 'нет данных'
        WHEN f.utilization < 0.60               THEN '1. низкая (<60%)'
        WHEN f.utilization < 0.80               THEN '2. средняя (60-80%)'
        WHEN f.utilization < 0.95               THEN '3. высокая (80-95%)'
        WHEN f.utilization <= 1.05              THEN '4. на пределе (95-105%)'
        ELSE                                         '5. перегрузка (>105%)'
    END                                                            AS load_band,
    COUNT(*)                                                       AS orders,
    ROUND(AVG(f.picking_minutes), 1)                               AS avg_picking_minutes,
    ROUND(AVG(f.fulfillment_hours), 2)                             AS avg_fulfillment_hours,
    ROUND(100.0 * AVG(CASE WHEN f.is_delayed THEN 1 ELSE 0 END), 2)
                                                                   AS delay_rate
FROM (
    SELECT
        o.*,
        l.utilization,
        s.picked_at,
        s.picking_started_at,
        s.shipped_at,
        s.delivered_at,
        o.promised_date,
        (s.delivered_at::date > o.promised_date) AS is_delayed,
        EXTRACT(EPOCH FROM (s.picked_at - s.picking_started_at)) / 60.0
                                                  AS picking_minutes,
        EXTRACT(EPOCH FROM (s.shipped_at - o.order_created_at)) / 3600.0
                                                  AS fulfillment_hours
    FROM orders o
    JOIN shipments s ON s.order_id = o.order_id
    LEFT JOIN vw_warehouse_daily_load l
           ON l.warehouse_id = o.warehouse_id
          AND l.load_date = o.order_created_at::date
    WHERE o.order_status = 'delivered'
) f
GROUP BY load_band
ORDER BY load_band;


-- 2.5 Корреляция «загрузка склада — время сборки — задержка» по дням
WITH daily AS (
    SELECT
        l.warehouse_id,
        l.load_date,
        l.utilization,
        ROUND(AVG(EXTRACT(EPOCH FROM (s.picked_at - s.picking_started_at)) / 60.0), 1)
                                                    AS avg_picking_minutes,
        ROUND(100.0 * AVG(CASE WHEN s.delivered_at::date > o.promised_date THEN 1 ELSE 0 END), 2)
                                                    AS delay_rate,
        COUNT(*)                                    AS orders
    FROM vw_warehouse_daily_load l
    JOIN orders o    ON o.warehouse_id = l.warehouse_id
                    AND o.order_created_at::date = l.load_date
                    AND o.order_status = 'delivered'
    JOIN shipments s ON s.order_id = o.order_id
    GROUP BY l.warehouse_id, l.load_date, l.utilization
)
SELECT
    ROUND(CORR(utilization, avg_picking_minutes)::numeric, 3) AS corr_utilization_picking,
    ROUND(CORR(utilization, delay_rate)::numeric, 3)          AS corr_utilization_delay,
    ROUND(CORR(avg_picking_minutes, delay_rate)::numeric, 3)  AS corr_picking_delay,
    COUNT(*)                                                  AS warehouse_days
FROM daily;


-- 2.6 Сотрудники по складам и ролям
SELECT
    w.warehouse_name,
    COUNT(e.employee_id)                                            AS total_employees,
    COUNT(e.employee_id) FILTER (WHERE e.is_active)                 AS active_employees,
    COUNT(e.employee_id) FILTER (WHERE e.role IN ('Picker', 'Packer')) AS picking_staff
FROM warehouses w
LEFT JOIN employees e ON e.warehouse_id = w.warehouse_id
GROUP BY w.warehouse_name
ORDER BY total_employees DESC;
