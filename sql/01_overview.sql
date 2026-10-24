-- ============================================================
-- 01. Обзорные показатели бизнеса
-- ============================================================

-- 1.1 Ключевые KPI за весь период
SELECT
    COUNT(*)                                                        AS total_orders,
    COUNT(*) FILTER (WHERE order_status = 'delivered')              AS delivered_orders,
    COUNT(*) FILTER (WHERE order_status = 'cancelled')              AS cancelled_orders,
    ROUND(SUM(total_amount) FILTER (WHERE order_status = 'delivered'), 2)
                                                                    AS revenue,
    ROUND(AVG(total_amount) FILTER (WHERE order_status = 'delivered'), 2)
                                                                    AS avg_order_value,
    ROUND(SUM(delivery_fee) FILTER (WHERE order_status = 'delivered'), 2)
                                                                    AS delivery_revenue,
    ROUND(100.0 * COUNT(*) FILTER (WHERE order_status = 'cancelled') / COUNT(*), 2)
                                                                    AS cancellation_rate
FROM orders;


-- 1.2 Динамика по месяцам
SELECT
    DATE_TRUNC('month', order_created_at)::date                     AS month,
    COUNT(*)                                                        AS total_orders,
    COUNT(*) FILTER (WHERE order_status = 'delivered')              AS delivered_orders,
    ROUND(SUM(total_amount) FILTER (WHERE order_status = 'delivered'), 2)
                                                                    AS revenue,
    ROUND(AVG(total_amount) FILTER (WHERE order_status = 'delivered'), 2)
                                                                    AS avg_order_value
FROM orders
GROUP BY DATE_TRUNC('month', order_created_at)
ORDER BY month;


-- 1.3 Недельная динамика объёма и выручки
SELECT
    DATE_TRUNC('week', order_created_at)::date                      AS week_start,
    COUNT(*)                                                        AS total_orders,
    ROUND(SUM(total_amount) FILTER (WHERE order_status = 'delivered'), 2)
                                                                    AS revenue,
    ROUND(100.0 * AVG(CASE WHEN order_status = 'cancelled' THEN 1 ELSE 0 END), 2)
                                                                    AS cancellation_rate
FROM orders
GROUP BY DATE_TRUNC('week', order_created_at)
ORDER BY week_start;


-- 1.4 Профиль спроса по дням недели
SELECT
    TO_CHAR(order_created_at, 'ID')                                 AS iso_weekday,
    TO_CHAR(order_created_at, 'Day')                                AS weekday_name,
    COUNT(*)                                                        AS total_orders,
    ROUND(AVG(total_amount), 2)                                     AS avg_order_value
FROM orders
GROUP BY TO_CHAR(order_created_at, 'ID'), TO_CHAR(order_created_at, 'Day')
ORDER BY iso_weekday;


-- 1.5 Пять самых результативных дней по выручке
SELECT
    order_created_at::date                                          AS order_date,
    COUNT(*)                                                        AS total_orders,
    ROUND(SUM(total_amount) FILTER (WHERE order_status = 'delivered'), 2)
                                                                    AS revenue
FROM orders
GROUP BY order_created_at::date
ORDER BY revenue DESC
LIMIT 5;


-- 1.6 Топ категорий по выручке
SELECT
    c.category_name,
    COUNT(DISTINCT o.order_id)                                      AS orders_with_category,
    SUM(i.quantity)                                                 AS units_sold,
    ROUND(SUM(i.line_total), 2)                                     AS revenue,
    ROUND(100.0 * SUM(i.line_total)
          / SUM(SUM(i.line_total)) OVER (), 2)                       AS revenue_share
FROM order_items i
JOIN products p   ON p.product_id = i.product_id
JOIN categories c ON c.category_id = p.category_id
JOIN orders o     ON o.order_id = i.order_id AND o.order_status = 'delivered'
GROUP BY c.category_name
ORDER BY revenue DESC;
