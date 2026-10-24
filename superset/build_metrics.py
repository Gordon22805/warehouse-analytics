"""Метрики и вычисляемые колонки датасетов Superset.

В Superset 4.x метрики и колонки не создаются отдельными эндпоинтами:
они передаются целиком в PUT /api/v1/dataset/{id}. Поэтому сначала читаем
текущий набор, дополняем его и отправляем обратно.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from superset_api import Superset
from metrics import BY_DATASET

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def column_payload(col: dict) -> dict:
    # id обязателен: без него Superset считает колонку новой и падает
    # на проверке уникальности имён.
    payload = {
        "id": col["id"],
        "column_name": col["column_name"],
        "type": col.get("type"),
        "is_dttm": bool(col.get("is_dttm")),
        "filterable": bool(col.get("filterable", True)),
        "groupby": bool(col.get("groupby", True)),
        "expression": col.get("expression"),
        "description": col.get("description"),
        "verbose_name": col.get("verbose_name"),
        "python_date_format": col.get("python_date_format"),
    }
    return payload


def metric_payload(metric: dict) -> dict:
    return {
        "id": metric["id"],
        "metric_name": metric["metric_name"],
        "expression": metric["expression"],
        "description": metric.get("description"),
        "verbose_name": metric.get("verbose_name"),
        "d3format": metric.get("d3format"),
        "metric_type": metric.get("metric_type"),
        "warning_text": metric.get("warning_text"),
    }


def main() -> None:
    ss = Superset("admin", os.environ["SUPERSET_ADMIN_PASSWORD"])

    for ds_id, (metrics, columns) in BY_DATASET.items():
        status, body = ss.get(f"/api/v1/dataset/{ds_id}")
        result = body["result"]

        cols = {c["column_name"]: column_payload(c) for c in result["columns"]}
        mets = {m["metric_name"]: metric_payload(m) for m in result.get("metrics", [])}

        added_cols = added_mets = updated = 0
        for col_name, (expression, description) in columns.items():
            if col_name in cols:
                continue
            cols[col_name] = {
                "column_name": col_name,
                "type": "VARCHAR",
                "is_dttm": False,
                "filterable": True,
                "groupby": True,
                "expression": expression,
                "description": description,
                "verbose_name": col_name,
                "python_date_format": None,
            }
            added_cols += 1

        # Существующие метрики тоже обновляем: иначе правка выражения
        # в metrics.py не доедет до Superset.
        for metric_name, (expression, description, d3) in metrics.items():
            if metric_name in mets:
                current = mets[metric_name]
                if current["expression"] != expression or current.get("d3format") != d3:
                    current["expression"] = expression
                    current["description"] = description
                    current["d3format"] = d3
                    updated += 1
                continue
            mets[metric_name] = {
                "metric_name": metric_name,
                "expression": expression,
                "description": description,
                "verbose_name": metric_name,
                "d3format": d3,
                "metric_type": None,
                "warning_text": None,
            }
            added_mets += 1

        if not added_cols and not added_mets and not updated:
            print(f"  {result['table_name']}: без изменений")
            continue

        status, body = ss.put(f"/api/v1/dataset/{ds_id}", {
            "table_name": result["table_name"],
            "database_id": result["database"]["id"],
            "schema": result.get("schema"),
            "sql": result.get("sql"),
            "description": result.get("description"),
            "main_dttm_col": result.get("main_dttm_col"),
            "default_endpoint": result.get("default_endpoint"),
            "offset": result.get("offset", 0),
            "cache_timeout": result.get("cache_timeout"),
            "columns": list(cols.values()),
            "metrics": list(mets.values()),
        })
        if status not in (200, 201):
            raise RuntimeError(f"{result['table_name']}: {status} {body}")
        print(f"  {result['table_name']}: +{added_mets} метрик, +{added_cols} колонок,"
              f" ~{updated} обновлено")


if __name__ == "__main__":
    main()
