-- ============================================================
-- 03. Доставка: сроки, SLA, регионы, способы доставки
-- ============================================================

-- 3.1 KPI доставки по сети
SELECT
    COUNT(*)                                                       AS delivered_orders,
    ROUND(AVG(transit_days), 2)                                    AS avg_transit_days,
    ROUND(AVG(lead_time_days), 2)                                  AS avg_lead_time_days,
    ROUND(AVG(fulfillment_hours), 2)                               AS avg_fulfillment_hours,
    ROUND(100.0 * AVG(CASE WHEN is_delayed THEN 1 ELSE 0 END), 2)  AS delay_rate,
    ROUND(100.0 * AVG(CASE WHEN NOT is_delayed THEN 1 ELSE 0 END), 2)
                                                                   AS on_time_delivery_rate,
    ROUND(AVG(delay_days) FILTER (WHERE is_delayed), 2)            AS avg_delay_days_when_late,
    COUNT(*) FILTER (WHERE delay_days >= 2)                        AS orders_late_2plus_days
FROM vw_order_facts;


-- 3.2 Показатели по способам доставки
SELECT
    method_name,
    delivered_orders,
    avg_transit_days,
    avg_lead_time_days,
    on_time_rate,
    delay_rate,
    avg_delay_days_when_late,
    revenue,
    delivery_revenue,
    ROUND(revenue / delivered_orders, 2)                           AS avg_order_value
FROM vw_delivery_performance
ORDER BY delay_rate;


-- 3.3 Показатели по регионам
SELECT
    region_name,
    delivered_orders,
    revenue,
    avg_lead_time_days,
    avg_transit_days,
    on_time_rate,
    delay_rate,
    avg_delay_days_when_late
FROM vw_regional_performance
ORDER BY delay_rate DESC;


-- 3.4 Время этапов заказа: где теряется время
SELECT
    ROUND(AVG(EXTRACT(EPOCH FROM (picking_started_at - order_created_at)) / 60.0), 1)
                                                    AS avg_wait_to_picking_start_min,
    ROUND(AVG(EXTRACT(EPOCH FROM (picked_at - picking_started_at)) / 60.0), 1)
                                                    AS avg_picking_min,
    ROUND(AVG(EXTRACT(EPOCH FROM (packed_at - picked_at)) / 60.0), 1)
                                                    AS avg_packing_min,
    ROUND(AVG(EXTRACT(EPOCH FROM (shipped_at - packed_at)) / 3600.0), 2)
                                                    AS avg_pack_to_ship_hours,
    ROUND(AVG(EXTRACT(EPOCH FROM (delivered_at - shipped_at)) / 86400.0), 2)
                                                    AS avg_transit_days,
    ROUND(AVG(EXTRACT(EPOCH FROM (delivered_at - order_created_at)) / 86400.0), 2)
                                                    AS avg_lead_time_days
FROM shipments s
JOIN orders o ON o.order_id = s.order_id
WHERE o.order_status = 'delivered';


-- 3.5 Регионы, где доставка систематически хуже среднего
WITH region_stats AS (
    SELECT
        region_name,
        delivered_orders,
        avg_lead_time_days,
        delay_rate,
        ROUND(AVG(avg_lead_time_days) OVER (), 2)  AS network_lead_time,
        ROUND(AVG(delay_rate) OVER (), 2)          AS network_delay_rate
    FROM vw_regional_performance
)
SELECT
    region_name,
    delivered_orders,
    avg_lead_time_days,
    network_lead_time,
    ROUND(avg_lead_time_days - network_lead_time, 2)  AS lead_time_gap_days,
    delay_rate,
    network_delay_rate,
    ROUND(delay_rate - network_delay_rate, 2)         AS delay_gap_pp
FROM region_stats
ORDER BY delay_gap_pp DESC;


-- 3.6 Динамика SLA по месяцам
SELECT
    DATE_TRUNC('month', order_date)::date                          AS month,
    COUNT(*)                                                       AS delivered_orders,
    ROUND(AVG(lead_time_days), 2)                                  AS avg_lead_time_days,
    ROUND(AVG(picking_minutes), 1)                                 AS avg_picking_minutes,
    ROUND(100.0 * AVG(CASE WHEN is_delayed THEN 1 ELSE 0 END), 2)  AS delay_rate
FROM vw_order_facts
GROUP BY DATE_TRUNC('month', order_date)
ORDER BY month;


-- 3.7 Влияние сезона и дня недели на SLA
SELECT
    TO_CHAR(order_date, 'Day')                                     AS weekday_name,
    COUNT(*)                                                       AS delivered_orders,
    ROUND(AVG(picking_minutes), 1)                                 AS avg_picking_minutes,
    ROUND(100.0 * AVG(CASE WHEN is_delayed THEN 1 ELSE 0 END), 2)  AS delay_rate
FROM vw_order_facts
GROUP BY TO_CHAR(order_date, 'Day'), TO_CHAR(order_date, 'ID')
ORDER BY TO_CHAR(order_date, 'ID');


-- 3.8 Регионы и способы доставки с наихудшим SLA (минимум 50 заказов)
SELECT
    f.region_name,
    f.method_name,
    COUNT(*)                                                       AS delivered_orders,
    ROUND(AVG(f.lead_time_days), 2)                                AS avg_lead_time_days,
    ROUND(100.0 * AVG(CASE WHEN f.is_delayed THEN 1 ELSE 0 END), 2) AS delay_rate
FROM vw_order_facts f
GROUP BY f.region_name, f.method_name
HAVING COUNT(*) >= 50
ORDER BY delay_rate DESC, delivered_orders DESC
LIMIT 10;
