"""Загрузка processed CSV в PostgreSQL.

Скрипт идемпотентен: перед загрузкой таблицы очищаются в порядке,
обратном зависимостям внешних ключей.
"""

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
SCHEMA_PATH = PROJECT_ROOT / "database" / "schema.sql"

# Порядок важен: сначала справочники, затем факты
LOAD_ORDER = [
    "regions",
    "warehouses",
    "delivery_methods",
    "categories",
    "products",
    "employees",
    "orders",
    "order_items",
    "shipments",
]

TRUNCATE_ORDER = [
    "shipments",
    "order_items",
    "orders",
    "employees",
    "products",
    "categories",
    "delivery_methods",
    "warehouses",
    "regions",
]

DATE_COLUMNS = {
    "warehouses": ["launched_at"],
    "employees": ["hired_at"],
    "orders": ["order_created_at", "promised_date"],
    "shipments": ["assigned_at", "picking_started_at", "picked_at",
                  "packed_at", "shipped_at", "delivered_at"],
}


def get_engine():
    load_dotenv(PROJECT_ROOT / ".env")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5433")
    db = os.getenv("POSTGRES_DB", "warehouse_analytics")
    user = os.getenv("POSTGRES_USER", "warehouse_user")
    password = os.getenv("POSTGRES_PASSWORD", "warehouse_pass")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)


def read_processed(name: str) -> pd.DataFrame:
    path = PROCESSED_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Нет файла {path}. Сначала запусти analytics/data_quality.py")
    return pd.read_csv(path, parse_dates=DATE_COLUMNS.get(name, []) or None, encoding="utf-8")


def apply_schema(engine) -> None:
    ddl = SCHEMA_PATH.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(ddl)


def truncate_tables(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(
            f"TRUNCATE {', '.join(TRUNCATE_ORDER)} RESTART IDENTITY CASCADE"
        ))


def load_table(engine, name: str) -> int:
    df = read_processed(name)
    df.to_sql(name, engine, if_exists="append", index=False, method="multi", chunksize=1000)
    return len(df)


def main() -> None:
    engine = get_engine()

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    apply_schema(engine)
    truncate_tables(engine)

    print(f"{'Таблица':<18}{'Строк':>8}")
    print("-" * 26)
    total = 0
    for name in LOAD_ORDER:
        rows = load_table(engine, name)
        total += rows
        print(f"{name:<18}{rows:>8}")
    print("-" * 26)
    print(f"{'Итого':<18}{total:>8}")

    verify(engine)


def verify(engine) -> None:
    checks = {
        "orders без доставки (delivered)": """
            SELECT COUNT(*) FROM orders o
            WHERE o.order_status = 'delivered'
              AND NOT EXISTS (SELECT 1 FROM shipments s WHERE s.order_id = o.order_id)
        """,
        "shipments без заказа": """
            SELECT COUNT(*) FROM shipments s
            WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.order_id = s.order_id)
        """,
        "позиции без заказа": """
            SELECT COUNT(*) FROM order_items i
            WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.order_id = i.order_id)
        """,
        "нарушенная цепочка времени": """
            SELECT COUNT(*) FROM shipments
            WHERE NOT (assigned_at <= picking_started_at
                   AND picking_started_at <= picked_at
                   AND picked_at <= packed_at
                   AND packed_at <= shipped_at
                   AND shipped_at <= delivered_at)
        """,
    }
    print("\nПроверка целостности:")
    with engine.connect() as conn:
        for label, query in checks.items():
            count = conn.execute(text(query)).scalar()
            mark = "OK" if count == 0 else "FAIL"
            print(f"  [{mark}] {label}: {count}")


if __name__ == "__main__":
    main()
