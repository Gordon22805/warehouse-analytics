"""Подключение Superset к аналитической базе проекта и регистрация датасетов.

Запуск: python superset/build_superset.py
Идемпотентен: повторный запуск обновляет существующие объекты.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from superset_api import Superset

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_NAME = "Warehouse Analytics"

# Датасеты: только views. Таблицы напрямую не подключаем, чтобы вся
# бизнес-логика оставалась в одном месте — в SQL.
DATASETS = [
    "vw_order_facts",
    "vw_warehouse_performance",
    "vw_delivery_performance",
    "vw_regional_performance",
    "vw_warehouse_daily_load",
    "vw_daily_orders",
    "vw_sla_analysis",
]


def find_database(ss):
    status, body = ss.get("/api/v1/database/?q=(page_size:100)")
    for item in body.get("result", []):
        if item["database_name"] == DB_NAME:
            return item["id"]
    return None


def ensure_database(ss) -> int:
    db_id = find_database(ss)
    payload = {
        "database_name": DB_NAME,
        "sqlalchemy_uri": os.environ["WAREHOUSE_URI"],
        "expose_in_sqllab": True,
        "allow_ctas": False,
        "allow_cvas": False,
        "allow_dml": False,
        "allow_run_async": False,
        "extra": json.dumps({
            "metadata_params": {},
            "engine_params": {"connect_args": {"connect_timeout": 15}},
            "metadata_cache_timeout": {},
            "schemas_allowed_for_file_upload": [],
        }),
    }
    if db_id:
        status, body = ss.put(f"/api/v1/database/{db_id}", payload)
        if status not in (200, 201):
            raise RuntimeError(f"update db failed: {status} {body}")
        print(f"  база обновлена (id={db_id})")
        return db_id

    status, body = ss.post("/api/v1/database/", payload)
    if status not in (200, 201):
        raise RuntimeError(f"create db failed: {status} {body}")
    db_id = body["id"]
    print(f"  база создана (id={db_id})")
    return db_id


def ensure_datasets(ss, db_id: int) -> dict[str, int]:
    status, body = ss.get(f"/api/v1/dataset/?q=(page_size:100)&filters=(database_id:{db_id})")
    existing = {d["table_name"]: d["id"] for d in body.get("result", [])}

    ids = {}
    for name in DATASETS:
        if name in existing:
            ids[name] = existing[name]
            print(f"  {name}: уже есть (id={existing[name]})")
            continue
        status, body = ss.post("/api/v1/dataset/", {
            "database": db_id,
            "schema": "public",
            "table_name": name,
        })
        if status not in (200, 201):
            raise RuntimeError(f"dataset {name} failed: {status} {body}")
        ids[name] = body["id"]
        print(f"  {name}: создан (id={body['id']})")
    return ids


def main() -> None:
    ss = Superset("admin", os.environ["SUPERSET_ADMIN_PASSWORD"])
    print("Подключение к базе:")
    db_id = ensure_database(ss)

    status, body = ss.get(f"/api/v1/database/{db_id}/connection")
    print(f"  проверка соединения: {body.get('message', status)}")

    print("Датасеты:")
    ids = ensure_datasets(ss, db_id)

    out = ROOT / "superset" / "assets" / "datasets.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"database_id": db_id, "datasets": ids},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nСохранено: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
