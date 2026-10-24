-- Warehouse & Logistics Analytics — схема БД
-- Порядок создания: справочники -> товары -> заказы -> доставка -> views

DROP VIEW IF EXISTS vw_sla_analysis CASCADE;
DROP VIEW IF EXISTS vw_regional_performance CASCADE;
DROP VIEW IF EXISTS vw_delivery_performance CASCADE;
DROP VIEW IF EXISTS vw_warehouse_performance CASCADE;
DROP VIEW IF EXISTS vw_daily_orders CASCADE;
DROP VIEW IF EXISTS vw_order_facts CASCADE;
DROP TABLE IF EXISTS shipments CASCADE;
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS employees CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS categories CASCADE;
DROP TABLE IF EXISTS delivery_methods CASCADE;
DROP TABLE IF EXISTS warehouses CASCADE;
DROP TABLE IF EXISTS regions CASCADE;

CREATE TABLE regions (
    region_id         VARCHAR(10) PRIMARY KEY,
    region_name       VARCHAR(120) NOT NULL UNIQUE,
    base_transit_days SMALLINT     NOT NULL CHECK (base_transit_days BETWEEN 0 AND 30)
);

CREATE TABLE warehouses (
    warehouse_id           VARCHAR(10) PRIMARY KEY,
    warehouse_name         VARCHAR(120) NOT NULL UNIQUE,
    city                   VARCHAR(80)  NOT NULL,
    home_region_id         VARCHAR(10)  NOT NULL REFERENCES regions (region_id),
    daily_capacity         SMALLINT     NOT NULL CHECK (daily_capacity > 0),
    base_picking_minutes   NUMERIC(6, 1) NOT NULL CHECK (base_picking_minutes > 0),
    launched_at            DATE         NOT NULL
);

CREATE TABLE delivery_methods (
    method_id    VARCHAR(10) PRIMARY KEY,
    method_name  VARCHAR(60) NOT NULL UNIQUE,
    delivery_fee NUMERIC(10, 2) NOT NULL CHECK (delivery_fee >= 0)
);

CREATE TABLE categories (
    category_id   VARCHAR(10) PRIMARY KEY,
    category_name VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE products (
    product_id   VARCHAR(10) PRIMARY KEY,
    product_name VARCHAR(160)   NOT NULL,
    category_id  VARCHAR(10)   NOT NULL REFERENCES categories (category_id),
    unit_price   NUMERIC(10, 2) NOT NULL CHECK (unit_price > 0),
    weight_kg    NUMERIC(8, 3)  NOT NULL CHECK (weight_kg > 0)
);

CREATE TABLE employees (
    employee_id  VARCHAR(10) PRIMARY KEY,
    warehouse_id VARCHAR(10) NOT NULL REFERENCES warehouses (warehouse_id),
    full_name    VARCHAR(120) NOT NULL,
    role         VARCHAR(40)  NOT NULL,
    hired_at     DATE         NOT NULL,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE TABLE orders (
    order_id         VARCHAR(12) PRIMARY KEY,
    order_created_at TIMESTAMP   NOT NULL,
    warehouse_id     VARCHAR(10) NOT NULL REFERENCES warehouses (warehouse_id),
    region_id        VARCHAR(10) NOT NULL REFERENCES regions (region_id),
    method_id        VARCHAR(10) NOT NULL REFERENCES delivery_methods (method_id),
    customer_id      VARCHAR(20) NOT NULL,
    order_status     VARCHAR(20) NOT NULL CHECK (order_status IN ('delivered', 'cancelled')),
    goods_amount     NUMERIC(12, 2) NOT NULL CHECK (goods_amount >= 0),
    delivery_fee     NUMERIC(10, 2) NOT NULL CHECK (delivery_fee >= 0),
    total_amount     NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    promised_date    DATE          NOT NULL,
    items_count      SMALLINT      NOT NULL CHECK (items_count > 0)
);

CREATE TABLE order_items (
    order_item_id VARCHAR(14) PRIMARY KEY,
    order_id      VARCHAR(12) NOT NULL REFERENCES orders (order_id) ON DELETE CASCADE,
    product_id    VARCHAR(10) NOT NULL REFERENCES products (product_id),
    quantity      SMALLINT     NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(10, 2) NOT NULL CHECK (unit_price > 0),
    line_total    NUMERIC(12, 2) NOT NULL CHECK (line_total > 0)
);

CREATE TABLE shipments (
    shipment_id         VARCHAR(12) PRIMARY KEY,
    order_id            VARCHAR(12) NOT NULL UNIQUE REFERENCES orders (order_id) ON DELETE CASCADE,
    carrier             VARCHAR(60) NOT NULL,
    assigned_at         TIMESTAMP   NOT NULL,
    picking_started_at  TIMESTAMP   NOT NULL,
    picked_at           TIMESTAMP   NOT NULL,
    packed_at           TIMESTAMP   NOT NULL,
    shipped_at          TIMESTAMP   NOT NULL,
    delivered_at        TIMESTAMP   NOT NULL,
    CHECK (assigned_at <= picking_started_at),
    CHECK (picking_started_at <= picked_at),
    CHECK (picked_at <= packed_at),
    CHECK (packed_at <= shipped_at),
    CHECK (shipped_at <= delivered_at)
);

CREATE INDEX idx_orders_created_at ON orders (order_created_at);
CREATE INDEX idx_orders_warehouse ON orders (warehouse_id);
CREATE INDEX idx_orders_region ON orders (region_id);
CREATE INDEX idx_orders_method ON orders (method_id);
CREATE INDEX idx_order_items_order ON order_items (order_id);
CREATE INDEX idx_order_items_product ON order_items (product_id);
CREATE INDEX idx_shipments_delivered ON shipments (delivered_at);


-- Базовый view: одна строка на доставленный заказ со всеми производными метриками.
CREATE VIEW vw_order_facts AS
SELECT
    o.order_id,
    o.order_created_at,
    o.order_created_at::date                        AS order_date,
    o.warehouse_id,
    w.warehouse_name,
    w.daily_capacity,
    o.region_id,
    r.region_name,
    o.method_id,
    m.method_name,
    o.customer_id,
    o.goods_amount,
    o.delivery_fee,
    o.total_amount,
    o.items_count,
    o.promised_date,
    s.shipment_id,
    s.carrier,
    s.assigned_at,
    s.picking_started_at,
    s.picked_at,
    s.packed_at,
    s.shipped_at,
    s.delivered_at,
    ROUND(EXTRACT(EPOCH FROM (s.picked_at - s.picking_started_at)) / 60.0, 1)
                                                    AS picking_minutes,
    ROUND(EXTRACT(EPOCH FROM (s.packed_at - s.picked_at)) / 60.0, 1)
                                                    AS packing_minutes,
    ROUND(EXTRACT(EPOCH FROM (s.shipped_at - o.order_created_at)) / 3600.0, 2)
                                                    AS fulfillment_hours,
    ROUND(EXTRACT(EPOCH FROM (s.delivered_at - s.shipped_at)) / 86400.0, 2)
                                                    AS transit_days,
    ROUND(EXTRACT(EPOCH FROM (s.delivered_at - o.order_created_at)) / 86400.0, 2)
                                                    AS lead_time_days,
    (s.delivered_at::date - o.promised_date)        AS delay_days,
    (s.delivered_at::date > o.promised_date)        AS is_delayed,
    -- Признаки механизма задержки: пропуск вечернего рейса.
    -- Нужны как отдельные колонки, потому что BI-инструменты не умеют
    -- сравнивать две колонки внутри фильтра меры.
    EXTRACT(HOUR FROM o.order_created_at)::int      AS order_hour,
    (s.shipped_at::date - o.order_created_at::date) AS dispatch_lag_days,
    (s.shipped_at::date > o.order_created_at::date) AS is_next_day_ship,
    (EXTRACT(HOUR FROM o.order_created_at) >= 20)   AS is_evening_order
FROM orders o
JOIN shipments s         ON s.order_id = o.order_id
JOIN warehouses w        ON w.warehouse_id = o.warehouse_id
JOIN regions r           ON r.region_id = o.region_id
JOIN delivery_methods m  ON m.method_id = o.method_id
WHERE o.order_status = 'delivered';


-- Суточная загрузка склада: сколько заказов пришло на склад за день относительно мощности.
CREATE VIEW vw_warehouse_daily_load AS
SELECT
    o.warehouse_id,
    o.order_created_at::date                        AS load_date,
    COUNT(*)                                        AS orders_count,
    w.daily_capacity,
    ROUND(COUNT(*)::numeric / w.daily_capacity, 3)  AS utilization
FROM orders o
JOIN warehouses w ON w.warehouse_id = o.warehouse_id
GROUP BY o.warehouse_id, o.order_created_at::date, w.daily_capacity;


CREATE VIEW vw_daily_orders AS
SELECT
    o.order_created_at::date                          AS order_date,
    COUNT(*)                                          AS total_orders,
    COUNT(*) FILTER (WHERE o.order_status = 'delivered') AS delivered_orders,
    COUNT(*) FILTER (WHERE o.order_status = 'cancelled') AS cancelled_orders,
    ROUND(SUM(o.total_amount) FILTER (WHERE o.order_status = 'delivered'), 2)
                                                      AS revenue,
    ROUND(AVG(o.total_amount) FILTER (WHERE o.order_status = 'delivered'), 2)
                                                      AS avg_order_value
FROM orders o
GROUP BY o.order_created_at::date;


CREATE VIEW vw_warehouse_performance AS
WITH order_stats AS (
    SELECT
        warehouse_id,
        COUNT(*)                                             AS total_orders,
        COUNT(*) FILTER (WHERE order_status = 'delivered')    AS delivered_orders,
        SUM(total_amount) FILTER (WHERE order_status = 'delivered') AS revenue
    FROM orders
    GROUP BY warehouse_id
),
ship_stats AS (
    SELECT
        warehouse_id,
        ROUND(AVG(picking_minutes), 1)   AS avg_picking_minutes,
        ROUND(AVG(packing_minutes), 1)   AS avg_packing_minutes,
        ROUND(AVG(fulfillment_hours), 2) AS avg_fulfillment_hours,
        ROUND(AVG(transit_days), 2)      AS avg_transit_days,
        ROUND(100.0 * AVG(CASE WHEN is_delayed THEN 1 ELSE 0 END), 2) AS delay_rate,
        ROUND(100.0 * AVG(CASE WHEN NOT is_delayed THEN 1 ELSE 0 END), 2) AS on_time_rate
    FROM vw_order_facts
    GROUP BY warehouse_id
),
load_stats AS (
    SELECT
        warehouse_id,
        ROUND(AVG(utilization), 3) AS avg_utilization,
        ROUND(MAX(utilization), 3) AS peak_utilization,
        ROUND(100.0 * AVG(CASE WHEN utilization > 1 THEN 1 ELSE 0 END), 2) AS overloaded_days_share
    FROM vw_warehouse_daily_load
    GROUP BY warehouse_id
)
SELECT
    w.warehouse_id,
    w.warehouse_name,
    w.city,
    w.daily_capacity,
    o.total_orders,
    o.delivered_orders,
    ROUND(o.revenue, 2)                     AS revenue,
    ROUND(100.0 * o.total_orders
          / SUM(o.total_orders) OVER (), 2) AS orders_share,
    s.avg_picking_minutes,
    s.avg_packing_minutes,
    s.avg_fulfillment_hours,
    s.avg_transit_days,
    s.delay_rate,
    s.on_time_rate,
    l.avg_utilization,
    l.peak_utilization,
    l.overloaded_days_share
FROM warehouses w
JOIN order_stats o ON o.warehouse_id = w.warehouse_id
JOIN ship_stats s  ON s.warehouse_id = w.warehouse_id
JOIN load_stats l  ON l.warehouse_id = w.warehouse_id;


CREATE VIEW vw_delivery_performance AS
SELECT
    f.method_id,
    f.method_name,
    COUNT(*)                                                          AS delivered_orders,
    ROUND(AVG(f.transit_days), 2)                                     AS avg_transit_days,
    ROUND(AVG(f.lead_time_days), 2)                                   AS avg_lead_time_days,
    ROUND(100.0 * AVG(CASE WHEN NOT f.is_delayed THEN 1 ELSE 0 END), 2) AS on_time_rate,
    ROUND(100.0 * AVG(CASE WHEN f.is_delayed THEN 1 ELSE 0 END), 2)   AS delay_rate,
    ROUND(AVG(f.delay_days) FILTER (WHERE f.is_delayed), 2)           AS avg_delay_days_when_late,
    ROUND(SUM(f.total_amount), 2)                                     AS revenue,
    ROUND(SUM(f.delivery_fee), 2)                                     AS delivery_revenue
FROM vw_order_facts f
GROUP BY f.method_id, f.method_name;


CREATE VIEW vw_regional_performance AS
SELECT
    f.region_id,
    f.region_name,
    COUNT(*)                                                          AS delivered_orders,
    ROUND(SUM(f.total_amount), 2)                                     AS revenue,
    ROUND(AVG(f.lead_time_days), 2)                                   AS avg_lead_time_days,
    ROUND(AVG(f.transit_days), 2)                                     AS avg_transit_days,
    ROUND(100.0 * AVG(CASE WHEN NOT f.is_delayed THEN 1 ELSE 0 END), 2) AS on_time_rate,
    ROUND(100.0 * AVG(CASE WHEN f.is_delayed THEN 1 ELSE 0 END), 2)   AS delay_rate,
    ROUND(AVG(f.delay_days) FILTER (WHERE f.is_delayed), 2)           AS avg_delay_days_when_late
FROM vw_order_facts f
GROUP BY f.region_id, f.region_name;


-- Разрез SLA по паре «склад + способ доставки»: где именно теряется срок.
CREATE VIEW vw_sla_analysis AS
SELECT
    f.warehouse_id,
    f.warehouse_name,
    f.method_id,
    f.method_name,
    COUNT(*)                                                          AS delivered_orders,
    ROUND(AVG(f.picking_minutes), 1)                                  AS avg_picking_minutes,
    ROUND(AVG(f.fulfillment_hours), 2)                                AS avg_fulfillment_hours,
    ROUND(AVG(f.transit_days), 2)                                     AS avg_transit_days,
    ROUND(100.0 * AVG(CASE WHEN f.is_delayed THEN 1 ELSE 0 END), 2)   AS delay_rate
FROM vw_order_facts f
GROUP BY f.warehouse_id, f.warehouse_name, f.method_id, f.method_name
HAVING COUNT(*) >= 30;
