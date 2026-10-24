"""Генерация синтетического датасета по складам и доставке.

Задержка не задаётся напрямую: она возникает из физики процесса.
Загрузка склада увеличивает очередь и время сборки, из-за чего заказ
не успевает на вечерний рейс и уезжает следующим утром. Дальше к сроку
добавляется вариативность транзита, зависящая от способа доставки и региона.
"""

import random
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20260101
ORDERS_TARGET = 14000
START_DATE = date(2025, 7, 1)
END_DATE = date(2025, 12, 31)

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

rng = np.random.default_rng(SEED)
random.seed(SEED)

REGIONS = [
    ("R-01", "Москва и Московская область", 1),
    ("R-02", "Санкт-Петербург и Ленинградская область", 1),
    ("R-03", "Центральный ФО", 2),
    ("R-04", "Северо-Западный ФО", 3),
    ("R-05", "Южный ФО", 2),
    ("R-06", "Приволжский ФО", 2),
    ("R-07", "Уральский ФО", 3),
    ("R-08", "Сибирский ФО", 4),
    ("R-09", "Дальневосточный ФО", 7),
    ("R-10", "Калининградская область", 5),
]

# warehouse_id, name, city, home_region, daily_capacity, base_picking_minutes
WAREHOUSES = [
    ("WH-01", "Склад Внуково", "Москва", "R-01", 34, 41.0),
    ("WH-02", "Склад Шушары", "Санкт-Петербург", "R-02", 21, 44.0),
    ("WH-03", "Склад Кольцово", "Екатеринбург", "R-07", 10, 47.0),
    ("WH-04", "Склад Толмачёво", "Новосибирск", "R-08", 17, 46.0),
    ("WH-05", "Склад Пашковский", "Краснодар", "R-05", 15, 43.0),
    ("WH-06", "Склад Свияжск", "Казань", "R-06", 15, 45.0),
]

WAREHOUSE_SHARES = {"WH-01": 0.34, "WH-02": 0.21, "WH-03": 0.12,
                    "WH-04": 0.10, "WH-05": 0.11, "WH-06": 0.12}

WAREHOUSE_REGIONS = {
    "WH-01": [("R-01", 0.55), ("R-03", 0.29), ("R-05", 0.06), ("R-06", 0.05), ("R-04", 0.05)],
    "WH-02": [("R-02", 0.55), ("R-04", 0.25), ("R-03", 0.08), ("R-10", 0.07), ("R-01", 0.05)],
    "WH-03": [("R-07", 0.60), ("R-06", 0.15), ("R-08", 0.14), ("R-01", 0.05), ("R-09", 0.06)],
    "WH-04": [("R-08", 0.65), ("R-09", 0.20), ("R-07", 0.10), ("R-06", 0.05)],
    "WH-05": [("R-05", 0.60), ("R-03", 0.15), ("R-06", 0.14), ("R-01", 0.11)],
    "WH-06": [("R-06", 0.60), ("R-07", 0.15), ("R-03", 0.15), ("R-05", 0.10)],
}

# method_id, name, delivery_fee
DELIVERY_METHODS = [
    ("DM-01", "Same-Day Courier", 690.0),
    ("DM-02", "Express", 390.0),
    ("DM-03", "Standard", 0.0),
    ("DM-04", "Pickup Point", 150.0),
    ("DM-05", "Economy", 0.0),
]

CARRIERS = {
    "DM-01": "CityExpress",
    "DM-02": "CityExpress",
    "DM-03": "RegionLogistics",
    "DM-04": "PickPointNet",
    "DM-05": "RegionLogistics",
}

# priority — множитель времени сборки, transit_risk — разброс транзита
METHOD_PROFILE = {
    "DM-01": (0.55, 1.15),
    "DM-02": (0.75, 1.40),
    "DM-03": (1.00, 0.60),
    "DM-04": (1.06, 0.55),
    "DM-05": (1.20, 1.80),
}

TRANSIT_EXTRA = {"DM-01": 0, "DM-02": 0, "DM-03": 1, "DM-04": 1, "DM-05": 2}

REMOTE_REGIONS = {"R-09", "R-10"}

CATEGORIES = [
    ("C-01", "Электроника", (1800, 24000), ["Наушники", "Портативная колонка", "Фитнес-браслет", "Электронная книга", "Умная лампа"]),
    ("C-02", "Бытовая техника", (4500, 52000), ["Пылесос", "Кофемашина", "Мультиварка", "Утюг", "Фен"]),
    ("C-03", "Компьютеры", (12000, 95000), ["Ноутбук", "Монитор", "Клавиатура", "Мышь", "Веб-камера"]),
    ("C-04", "Смартфоны и аксессуары", (900, 68000), ["Смартфон", "Чехол", "Защитное стекло", "Зарядное устройство", "Power bank"]),
    ("C-05", "Товары для дома", (400, 8900), ["Набор полотенец", "Плед", "Органайзер", "Корзина для белья", "Коврик"]),
    ("C-06", "Кухня и столовая", (350, 12000), ["Набор посуды", "Сковорода", "Чайник", "Кружка", "Нож шеф-повара"]),
    ("C-07", "Одежда", (1200, 14500), ["Куртка", "Джинсы", "Футболка", "Свитер", "Платье"]),
    ("C-08", "Обувь", (1900, 18000), ["Кроссовки", "Ботинки", "Сандалии", "Лоферы", "Сапоги"]),
    ("C-09", "Красота и уход", (250, 7800), ["Крем для лица", "Шампунь", "Набор косметики", "Парфюм", "Маска для волос"]),
    ("C-10", "Здоровье", (300, 9500), ["Витамины", "Тонометр", "Массажёр", "Термометр", "Увлажнитель воздуха"]),
    ("C-11", "Спорт и отдых", (600, 21000), ["Гантели", "Коврик для йоги", "Велосипедный шлем", "Палатка", "Термос"]),
    ("C-12", "Детские товары", (400, 16000), ["Конструктор", "Коляска", "Детское автокресло", "Развивающий набор", "Рюкзак школьный"]),
    ("C-13", "Зоотовары", (200, 6200), ["Корм для кошек", "Лежанка", "Переноска", "Игрушка для собак", "Наполнитель"]),
    ("C-14", "Автотовары", (500, 18500), ["Автозарядное устройство", "Держатель телефона", "Компрессор", "Набор инструментов", "Коврики в салон"]),
]

BRANDS = ["Aurora", "Vega", "Nordline", "Kite", "Lumen", "Zeta", "Orbis", "Terra", "Fjord", "Krona"]

STAFF_PLAN = {"WH-01": 8, "WH-02": 5, "WH-03": 3, "WH-04": 4, "WH-05": 3, "WH-06": 3}
ROLE_WEIGHTS = [("Picker", 0.42), ("Packer", 0.26), ("Loader", 0.13),
                ("Warehouse Manager", 0.06), ("Dispatcher", 0.13)]

LAST_NAMES = ["Иванов", "Петров", "Смирнов", "Кузнецов", "Соколов", "Попов", "Лебедев", "Козлов",
              "Новиков", "Морозов", "Волков", "Зайцев", "Павлов", "Семёнов", "Голубев", "Виноградов",
              "Богданов", "Воробьёв", "Фёдоров", "Михайлов", "Беляев", "Тарасов", "Белов", "Комаров",
              "Орлов", "Киселёв", "Макаров", "Андреев", "Ковалёв", "Ильин"]
FIRST_NAMES = ["Алексей", "Мария", "Дмитрий", "Анна", "Сергей", "Ольга", "Иван", "Екатерина", "Павел",
               "Наталья", "Артём", "Юлия", "Михаил", "Светлана", "Роман", "Ирина", "Никита", "Татьяна",
               "Андрей", "Оксана", "Владимир", "Вера", "Максим", "Алина", "Егор", "Дарья", "Кирилл",
               "Полина", "Денис", "Марина"]

WEEKDAY_FACTOR = {0: 1.16, 1: 1.06, 2: 1.00, 3: 1.02, 4: 1.09, 5: 0.90, 6: 0.84}

HOUR_WEIGHTS = np.array([
    0.9, 0.5, 0.3, 0.2, 0.2, 0.3, 0.7, 1.4, 2.4, 3.4, 4.1, 4.3,
    4.0, 3.7, 3.6, 3.8, 4.0, 4.2, 4.6, 5.2, 5.6, 5.1, 3.6, 1.9,
])
HOUR_WEIGHTS = HOUR_WEIGHTS / HOUR_WEIGHTS.sum()

PEAK_WINDOWS = [
    (date(2025, 7, 10), date(2025, 7, 24), 1.22),
    (date(2025, 11, 23), date(2025, 12, 1), 2.35),
    (date(2025, 12, 10), date(2025, 12, 22), 1.68),
]

MONTH_FACTOR = {7: 1.02, 8: 0.95, 9: 1.05, 10: 1.11, 11: 1.24, 12: 1.18}

DISPATCH_CUTOFF_HOUR = 20
DISPATCH_MORNING_HOUR = 8


def is_peak(d: date) -> bool:
    return any(start <= d <= end for start, end, _ in PEAK_WINDOWS)


def seasonal_factor(d: date) -> float:
    for start, end, factor in PEAK_WINDOWS:
        if start <= d <= end:
            return factor
    return MONTH_FACTOR[d.month]


def build_dimensions():
    regions = pd.DataFrame(REGIONS, columns=["region_id", "region_name", "base_transit_days"])

    warehouses = pd.DataFrame(
        [
            {
                "warehouse_id": wh_id,
                "warehouse_name": name,
                "city": city,
                "home_region_id": home_region,
                "daily_capacity": capacity,
                "base_picking_minutes": base_pick,
                "launched_at": date(2019, 1, 1) + timedelta(days=int(rng.integers(0, 1800))),
            }
            for wh_id, name, city, home_region, capacity, base_pick in WAREHOUSES
        ]
    )

    methods = pd.DataFrame(
        [(mid, name, fee) for mid, name, fee in DELIVERY_METHODS],
        columns=["method_id", "method_name", "delivery_fee"],
    )

    categories = pd.DataFrame([(cid, cname) for cid, cname, _, _ in CATEGORIES],
                              columns=["category_id", "category_name"])

    product_rows = []
    for cat_id, _, (low, high), nouns in CATEGORIES:
        for i in range(16):
            noun = nouns[i % len(nouns)]
            brand = BRANDS[int(rng.integers(0, len(BRANDS)))]
            price = float(np.clip(rng.lognormal(np.log((low + high) / 2), 0.45), low, high))
            product_rows.append(
                {
                    "product_name": f"{brand} {noun} {100 + i * 7}",
                    "category_id": cat_id,
                    "unit_price": round(price, 2),
                    "weight_kg": round(float(np.clip(rng.lognormal(0.2, 0.8), 0.05, 45)), 3),
                }
            )
    products = pd.DataFrame(product_rows).sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    products.insert(0, "product_id", [f"P-{i:04d}" for i in range(1, len(products) + 1)])

    roles = [r for r, _ in ROLE_WEIGHTS]
    role_p = [p for _, p in ROLE_WEIGHTS]
    emp_rows = []
    for wh_id, count in STAFF_PLAN.items():
        for _ in range(count):
            emp_rows.append(
                {
                    "warehouse_id": wh_id,
                    "full_name": f"{LAST_NAMES[int(rng.integers(0, len(LAST_NAMES)))]} "
                                 f"{FIRST_NAMES[int(rng.integers(0, len(FIRST_NAMES)))]}",
                    "role": roles[int(rng.choice(len(roles), p=role_p))],
                    "hired_at": date(2020, 1, 1) + timedelta(days=int(rng.integers(0, 1900))),
                    "is_active": bool(rng.random() > 0.08),
                }
            )
    employees = pd.DataFrame(emp_rows)
    employees.insert(0, "employee_id", [f"E-{i:03d}" for i in range(1, len(employees) + 1)])

    return regions, warehouses, methods, categories, products, employees


def build_daily_counts():
    days = pd.date_range(START_DATE, END_DATE, freq="D")
    weights = np.array([
        seasonal_factor(ts.date()) * WEEKDAY_FACTOR[ts.weekday()] * float(rng.lognormal(0, 0.11))
        for ts in days
    ])
    counts = rng.multinomial(ORDERS_TARGET, weights / weights.sum())
    return days, counts


def base_transit_days(region_id, method_id):
    region_days = next(r[2] for r in REGIONS if r[0] == region_id)
    return region_days + TRANSIT_EXTRA[method_id]


# Обещанный срок = плановый транзит + один день на обработку заказа.
# Один день на обработку означает отгрузку в день оформления: если склад
# не успел на вечерний рейс, буфер уже израсходован.
SLA_HANDLING_DAYS = 1


def promise_days(region_id, method_id):
    return max(1, base_transit_days(region_id, method_id) + SLA_HANDLING_DAYS)


def promised_date_for(order_dt, region_id, method_id):
    return order_dt.date() + timedelta(days=promise_days(region_id, method_id))


def method_weights(region_id, home_region_id):
    if region_id == home_region_id:
        return [0.10, 0.28, 0.32, 0.20, 0.10]
    if region_id in REMOTE_REGIONS:
        return [0.00, 0.18, 0.34, 0.20, 0.28]
    return [0.00, 0.22, 0.36, 0.24, 0.18]


def transit_shift(transit_risk, region_id, peak):
    """Отклонение фактического транзита от планового в днях.

    Отрицательное значение — курьер приехал раньше срока.
    """
    risk = transit_risk * (1.35 if region_id in REMOTE_REGIONS else 1.0) * (1.0 + 0.15 * peak)
    p_early = 0.18 / risk
    p_late1 = 0.20 * risk
    p_late2 = 0.05 * risk

    r = rng.random()
    if r < p_early:
        return -1
    if r < p_early + p_late1:
        return 1
    if r < p_early + p_late1 + p_late2:
        return 2
    return 0


def generate():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    regions, warehouses, methods, categories, products, employees = build_dimensions()

    days, counts = build_daily_counts()
    wh_ids = [w[0] for w in WAREHOUSES]
    wh_home_region = {w[0]: w[3] for w in WAREHOUSES}
    wh_capacity = {w[0]: w[4] for w in WAREHOUSES}
    wh_base_pick = {w[0]: w[5] for w in WAREHOUSES}
    wh_share = np.array([WAREHOUSE_SHARES[w] for w in wh_ids])

    method_ids = [m[0] for m in DELIVERY_METHODS]
    method_fee = {m[0]: m[2] for m in DELIVERY_METHODS}

    prod_ids = products["product_id"].tolist()
    prod_price = dict(zip(products["product_id"], products["unit_price"]))

    orders_rows, items_rows, shipments_rows = [], [], []
    order_seq = item_seq = ship_seq = 0

    for ts, n_orders in zip(days, counts):
        day = ts.date()
        day_share = wh_share * rng.lognormal(0, 0.10, size=len(wh_ids))
        per_wh = rng.multinomial(int(n_orders), day_share / day_share.sum())
        peak = is_peak(day)

        for wh_id, k in zip(wh_ids, per_wh):
            if k == 0:
                continue
            load = k / wh_capacity[wh_id]
            region_pairs = WAREHOUSE_REGIONS[wh_id]
            region_ids = [r for r, _ in region_pairs]
            region_weights = np.array([w for _, w in region_pairs])

            for _ in range(int(k)):
                order_seq += 1
                order_id = f"O-{order_seq:06d}"

                order_dt = datetime(day.year, day.month, day.day,
                                    int(rng.choice(24, p=HOUR_WEIGHTS)),
                                    int(rng.integers(0, 60)))

                region_id = region_ids[int(rng.choice(len(region_ids), p=region_weights))]
                method_id = method_ids[int(rng.choice(len(method_ids),
                                                      p=method_weights(region_id, wh_home_region[wh_id])))]

                n_items = int(rng.choice([1, 2, 3, 4, 5], p=[0.42, 0.28, 0.16, 0.09, 0.05]))
                goods_amount = 0.0
                for idx in rng.choice(len(prod_ids), size=n_items, replace=False):
                    item_seq += 1
                    pid = prod_ids[int(idx)]
                    qty = int(rng.choice([1, 2, 3], p=[0.76, 0.18, 0.06]))
                    price = float(prod_price[pid])
                    goods_amount += qty * price
                    items_rows.append(
                        {
                            "order_item_id": f"OI-{item_seq:07d}",
                            "order_id": order_id,
                            "product_id": pid,
                            "quantity": qty,
                            "unit_price": round(price, 2),
                            "line_total": round(qty * price, 2),
                        }
                    )

                fee = float(method_fee[method_id])
                status = "cancelled" if rng.random() < 0.035 else "delivered"
                promised = promised_date_for(order_dt, region_id, method_id)

                orders_rows.append(
                    {
                        "order_id": order_id,
                        "order_created_at": order_dt,
                        "warehouse_id": wh_id,
                        "region_id": region_id,
                        "method_id": method_id,
                        "customer_id": f"C-{int(rng.integers(1, 5200)):05d}",
                        "order_status": status,
                        "goods_amount": round(goods_amount, 2),
                        "delivery_fee": fee,
                        "total_amount": round(goods_amount + fee, 2),
                        "promised_date": promised,
                        "items_count": n_items,
                    }
                )

                if status == "cancelled":
                    continue

                ship_seq += 1
                shipments_rows.append(
                    _build_shipment(order_id, ship_seq, order_dt, load, wh_base_pick[wh_id],
                                    n_items, method_id, region_id, peak)
                )

    orders = pd.DataFrame(orders_rows)
    items = pd.DataFrame(items_rows)
    shipments = pd.DataFrame(shipments_rows)

    orders = _inject_order_issues(orders)
    items = _inject_item_issues(items)

    regions.to_csv(RAW_DIR / "regions.csv", index=False, encoding="utf-8")
    warehouses.to_csv(RAW_DIR / "warehouses.csv", index=False, encoding="utf-8")
    methods.to_csv(RAW_DIR / "delivery_methods.csv", index=False, encoding="utf-8")
    categories.to_csv(RAW_DIR / "categories.csv", index=False, encoding="utf-8")
    products.to_csv(RAW_DIR / "products.csv", index=False, encoding="utf-8")
    employees.to_csv(RAW_DIR / "employees.csv", index=False, encoding="utf-8")
    orders.to_csv(RAW_DIR / "orders.csv", index=False, encoding="utf-8")
    items.to_csv(RAW_DIR / "order_items.csv", index=False, encoding="utf-8")
    shipments.to_csv(RAW_DIR / "shipments.csv", index=False, encoding="utf-8")

    print(f"Заказов:            {len(orders)}")
    print(f"Позиций заказа:     {len(items)}")
    print(f"Отправлений:        {len(shipments)}")
    print(f"Товаров:            {len(products)}")
    print(f"Сотрудников:        {len(employees)}")
    print(f"Период:             {orders['order_created_at'].min()} — {orders['order_created_at'].max()}")
    print(f"Файлы записаны в:   {RAW_DIR}")


def queue_minutes(load, priority, peak):
    """Очередь на сборку растёт нелинейно: при загрузке около 100% склад захлёбывается.

    Модель простая: время ожидания пропорционально rho / (1 - rho),
    где rho — загрузка склада относительно суточной мощности.
    """
    rho = min(load, 0.965)
    wait = 11.0 * (rho / (1.0 - rho))
    return (wait + 12.0) * priority + 10.0 * peak


def _build_shipment(order_id, ship_seq, order_dt, load, base_pick, n_items, method_id,
                    region_id, peak):
    priority, transit_risk = METHOD_PROFILE[method_id]

    picking_minutes = (
        base_pick
        * (0.80 + 0.35 * load)
        * (0.90 + 0.08 * n_items)
        * priority
        * float(rng.lognormal(0, 0.12))
    )
    packing_minutes = (5.0 + 2.2 * n_items) * float(rng.lognormal(0, 0.18))

    assigned_at = order_dt + timedelta(minutes=float(rng.uniform(1, 6)))
    picking_started_at = assigned_at + timedelta(minutes=queue_minutes(load, priority, peak))
    picked_at = picking_started_at + timedelta(minutes=picking_minutes)
    packed_at = picked_at + timedelta(minutes=packing_minutes)

    # отгрузка привязана к рейсу: последний выезд в 20:00, иначе заказ уходит утром
    cutoff = packed_at.replace(hour=DISPATCH_CUTOFF_HOUR, minute=0, second=0, microsecond=0)
    if packed_at <= cutoff:
        shipped_at = packed_at + timedelta(minutes=float(rng.uniform(10, 90)))
    else:
        morning = (packed_at + timedelta(days=1)).replace(
            hour=DISPATCH_MORNING_HOUR, minute=0, second=0, microsecond=0
        )
        shipped_at = morning + timedelta(minutes=float(rng.uniform(0, 150)))

    planned_transit = base_transit_days(region_id, method_id)
    transit_days = max(1, planned_transit + transit_shift(transit_risk, region_id, peak))
    delivered_date = shipped_at.date() + timedelta(days=transit_days)
    delivered_at = datetime(delivered_date.year, delivered_date.month, delivered_date.day,
                            int(rng.integers(9, 21)), int(rng.integers(0, 60)))

    return {
        "shipment_id": f"SH-{ship_seq:06d}",
        "order_id": order_id,
        "carrier": CARRIERS[method_id],
        "assigned_at": assigned_at,
        "picking_started_at": picking_started_at,
        "picked_at": picked_at,
        "packed_at": packed_at,
        "shipped_at": shipped_at,
        "delivered_at": delivered_at,
    }


def _inject_order_issues(orders):
    df = orders.copy()

    dup_idx = rng.choice(len(df), size=int(len(df) * 0.008), replace=False)
    df = pd.concat([df, df.iloc[dup_idx]], ignore_index=True)

    df["customer_id"] = df["customer_id"].astype(object)
    df.loc[rng.choice(len(df), size=int(len(df) * 0.02), replace=False), "customer_id"] = None

    df["region_id"] = df["region_id"].astype(object)
    df.loc[rng.choice(len(df), size=int(len(df) * 0.008), replace=False), "region_id"] = None

    neg = rng.choice(len(df), size=int(len(df) * 0.003), replace=False)
    df.loc[neg, "goods_amount"] = -df.loc[neg, "goods_amount"].abs()
    df.loc[neg, "total_amount"] = df.loc[neg, "goods_amount"] + df.loc[neg, "delivery_fee"]

    df.loc[rng.choice(len(df), size=int(len(df) * 0.012), replace=False), "delivery_fee"] = np.nan
    df.loc[rng.choice(len(df), size=int(len(df) * 0.002), replace=False), "order_created_at"] = pd.NaT
    df.loc[rng.choice(len(df), size=int(len(df) * 0.002), replace=False), "items_count"] = 0

    return df.sample(frac=1.0, random_state=SEED).reset_index(drop=True)


def _inject_item_issues(items):
    df = items.copy()
    df["product_id"] = df["product_id"].astype(object)

    orphan = rng.choice(len(df), size=max(1, int(len(df) * 0.002)), replace=False)
    df.loc[orphan, "product_id"] = "P-9999"

    zero_price = rng.choice(len(df), size=max(1, int(len(df) * 0.0015)), replace=False)
    df.loc[zero_price, "unit_price"] = 0.0

    return df


if __name__ == "__main__":
    generate()
