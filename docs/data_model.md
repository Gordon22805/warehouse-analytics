# Data Model

## ER-диаграмма

Схема соответствует `database/schema.sql`.

```mermaid
erDiagram
    regions ||--o{ warehouses : "домашний регион"
    regions ||--o{ orders : "регион доставки"
    warehouses ||--o{ orders : "обрабатывает"
    warehouses ||--o{ employees : "имеет"
    delivery_methods ||--o{ orders : "тариф"
    categories ||--o{ products : "содержит"
    orders ||--|{ order_items : "состоит из"
    products ||--o{ order_items : "входит в"
    orders ||--o| shipments : "доставляется"

    regions {
        varchar region_id PK
        varchar region_name UK
        smallint base_transit_days
    }
    warehouses {
        varchar warehouse_id PK
        varchar warehouse_name UK
        varchar city
        varchar home_region_id FK
        smallint daily_capacity
        numeric base_picking_minutes
        date launched_at
    }
    delivery_methods {
        varchar method_id PK
        varchar method_name UK
        numeric delivery_fee
    }
    categories {
        varchar category_id PK
        varchar category_name UK
    }
    products {
        varchar product_id PK
        varchar product_name
        varchar category_id FK
        numeric unit_price
        numeric weight_kg
    }
    employees {
        varchar employee_id PK
        varchar warehouse_id FK
        varchar full_name
        varchar role
        date hired_at
        boolean is_active
    }
    orders {
        varchar order_id PK
        timestamp order_created_at
        varchar warehouse_id FK
        varchar region_id FK
        varchar method_id FK
        varchar customer_id
        varchar order_status
        numeric goods_amount
        numeric delivery_fee
        numeric total_amount
        date promised_date
        smallint items_count
    }
    order_items {
        varchar order_item_id PK
        varchar order_id FK
        varchar product_id FK
        smallint quantity
        numeric unit_price
        numeric line_total
    }
    shipments {
        varchar shipment_id PK
        varchar order_id FK_UK
        varchar carrier
        timestamp assigned_at
        timestamp picking_started_at
        timestamp picked_at
        timestamp packed_at
        timestamp shipped_at
        timestamp delivered_at
    }
```

## Таблицы

| Таблица | Роль | Строк |
|---------|------|-------|
| `regions` | справочник регионов с плановым транзитом | 10 |
| `warehouses` | склады и их суточная мощность | 6 |
| `delivery_methods` | тарифы доставки и их стоимость | 5 |
| `categories` | категории товаров | 14 |
| `products` | товарный справочник | 224 |
| `employees` | сотрудники складов | 26 |
| `orders` | заголовок заказа | 13 805 |
| `order_items` | позиции заказа | 28 567 |
| `shipments` | этапы обработки и доставки | 13 331 |

## Ключевые решения

**`shipments` отделена от `orders`.** У заказа есть заголовок и есть исполнение.
Разделение позволяет хранить шесть временных отметок процесса и навесить `CHECK`,
который запрещает нарушение порядка этапов. Связь `1:1` через `UNIQUE(order_id)`:
один доставленный заказ — одна запись об исполнении.

**`promised_date` хранится в `orders`.** Обещанный срок фиксируется в момент оформления
и не пересчитывается задним числом, иначе анализ SLA потеряет смысл.

**`daily_capacity` хранится в `warehouses`.** Загрузка склада не является полем заказа —
она вычисляется как `COUNT(заказов за день) / daily_capacity` во view
`vw_warehouse_daily_load`. Это позволяет менять мощность без перезагрузки фактов.

**`CHECK` на временную цепочку.** `assigned_at <= picking_started_at <= picked_at <=
packed_at <= shipped_at <= delivered_at` защищает от логически невозможных данных
на уровне БД, а не только в Python.

**Денежные поля — `NUMERIC`, не `FLOAT`.** Суммы не должны терять точность при агрегации.

## Views для BI

| View | Назначение |
|------|-----------|
| `vw_order_facts` | одна строка на доставленный заказ со всеми метриками времени |
| `vw_warehouse_daily_load` | загрузка склада по дням относительно мощности |
| `vw_daily_orders` | дневная динамика заказов и выручки |
| `vw_warehouse_performance` | KPI по складам |
| `vw_delivery_performance` | KPI по способам доставки |
| `vw_regional_performance` | KPI по регионам |
| `vw_sla_analysis` | задержки в разрезе «склад × способ доставки» |

`vw_order_facts` — база для остальных view: метрики времени считаются один раз,
а не дублируются в каждом запросе. View фильтрует `order_status = 'delivered'`,
поэтому отменённые заказы не попадают в KPI доставки. Отмены учитываются отдельно
в `01_overview.sql` как `cancellation_rate`.
