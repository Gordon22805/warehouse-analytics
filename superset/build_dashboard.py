"""Чарты и дашборд Superset для проекта Warehouse & Logistics Analytics.

Все чарты строятся на views базы, поэтому числа совпадают с SQL-анализом
и с витринами Power BI. Дашборд экспортируется в superset/assets/.
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

FACT = 1
WH = 2
METHOD = 3
REGION = 4
LOAD = 5
DAILY = 6
SLA = 7

GOOD, WARN, BAD = "#17A398", "#F4A259", "#C1352B"
PALETTE = ["#2E5EAA", "#E4572E", "#17A398", "#F4A259", "#6A4C93", "#8D99AE"]


def base(viz_type, ds_id, ds_name, **extra):
    params = {
        "datasource": f"{ds_id}__table",
        "viz_type": viz_type,
        "adhoc_filters": [],
        "row_limit": 1000,
        "color_scheme": "supersetColors",
        # Данные обновляются скриптом, поэтому кэш только мешает:
        # чарт показывал бы цифры до последней загрузки.
        "cache_timeout": 0,
    }
    params.update(extra)
    return {
        "slice_name": extra.pop("_name", None) or viz_type,
        "viz_type": viz_type,
        "datasource_id": ds_id,
        "datasource_type": "table",
        "datasource_name": ds_name,
        "params": json.dumps(params, ensure_ascii=False),
    }


def big_number(name, ds_id, ds_name, metric, fmt=None, subheader=None):
    chart = base("big_number_total", ds_id, ds_name,
                 metric=metric,
                 y_axis_format=fmt or "SMART_NUMBER",
                 subheader=subheader or "",
                 header_font_size=0.3,
                 subtitle_font_size=0.12)
    chart["slice_name"] = name
    return chart


def echarts_bar(name, ds_id, ds_name, x, metrics, orientation="vertical",
                color=None, y_format=None, sort_desc=False):
    params = {
        "x_axis": x,
        "metrics": metrics,
        "groupby": [],
        "orientation": orientation,
        "show_legend": len(metrics) > 1,
        "show_value": True,
        "y_axis_format": y_format or "SMART_NUMBER",
        "x_axis_sort": x,
        "x_axis_sort_asc": not sort_desc,
        "rich_tooltip": True,
        "bar_stacked": False,
    }
    if color:
        params["color_scheme"] = "supersetColors"
        params["linear_color_scheme"] = color
    chart = base("echarts_timeseries_bar", ds_id, ds_name, **params)
    chart["slice_name"] = name
    return chart


def echarts_line(name, ds_id, ds_name, x, metrics, y_format=None):
    params = {
        "x_axis": x,
        "metrics": metrics,
        "groupby": [],
        "show_legend": len(metrics) > 1,
        "y_axis_format": y_format or "SMART_NUMBER",
        "rich_tooltip": True,
        "markerEnabled": True,
    }
    chart = base("echarts_timeseries_line", ds_id, ds_name, **params)
    chart["slice_name"] = name
    return chart


def pie(name, ds_id, ds_name, groupby, metric):
    params = {
        "groupby": [groupby],
        "metric": metric,
        "show_labels": True,
        "show_legend": True,
        "label_type": "key_percent",
        "donut": True,
        "innerRadius": 45,
    }
    chart = base("pie", ds_id, ds_name, **params)
    chart["slice_name"] = name
    return chart


def table(name, ds_id, ds_name, groupby, metrics):
    params = {
        "groupby": groupby,
        "metrics": metrics,
        "show_cell_bars": True,
        "include_search": False,
        "page_length": 20,
        "order_desc": True,
    }
    chart = base("table", ds_id, ds_name, **params)
    chart["slice_name"] = name
    return chart


CHARTS = [
    # --- Страница 1: обзор ---
    big_number("Заказы", FACT, "vw_order_facts", "Заказы", "SMART_NUMBER",
               "доставлено за период"),
    big_number("Выручка", FACT, "vw_order_facts", "Выручка", "$,.0f",
               "рублей, по доставленным заказам"),
    big_number("Средний чек", FACT, "vw_order_facts", "Средний чек", "$,.0f",
               "рублей за заказ"),
    big_number("Доля задержек", FACT, "vw_order_facts", "Доля задержек",
               ".1%", "от доставленных заказов"),
    big_number("Средний срок доставки", FACT, "vw_order_facts", "Ср. срок, дн",
               ".2f", "дней от заказа до доставки"),
    echarts_line("Выручка по месяцам", DAILY, "vw_daily_orders",
                 "order_date", ["Выручка"], "$,.0f"),
    echarts_bar("Задержки по складам", WH, "vw_warehouse_performance",
                "warehouse_name", ["Доля задержек"], "horizontal", None, ".1%",
                sort_desc=True),

    # --- Страница 2: причины задержек ---
    echarts_bar("Задержки: день заказа против следующего дня", FACT, "vw_order_facts",
                "Режим отгрузки", ["Доля задержек"], "vertical", None, ".1%"),
    big_number("Риск при пропуске рейса", FACT, "vw_order_facts",
               "Риск при пропуске рейса", ".2f", "во сколько раз выше риск"),
    echarts_bar("Задержки: вечерние и дневные заказы", FACT, "vw_order_facts",
                "Время заказа", ["Доля задержек"], "vertical", None, ".1%"),
    echarts_bar("Задержки по тарифам", METHOD, "vw_delivery_performance",
                "method_name", ["Доля задержек"], "horizontal", None, ".1%",
                sort_desc=True),
    table("Склад × тариф", SLA, "vw_sla_analysis",
          ["warehouse_name", "method_name"],
          ["Заказы", "Доля задержек", "Ср. сборка, мин", "Ср. транзит, дн"]),

    # --- Страница 3: склады ---
    echarts_bar("Время сборки по складам", WH, "vw_warehouse_performance",
                "warehouse_name", ["Ср. сборка, мин"], "horizontal", None, ".1f",
                sort_desc=True),
    echarts_bar("Загрузка складов", WH, "vw_warehouse_performance",
                "warehouse_name", ["Ср. загрузка", "Пиковая загрузка"],
                "horizontal", None, ".1%", sort_desc=True),
    echarts_line("Загрузка по дням: Кольцово", LOAD, "vw_warehouse_daily_load",
                 "load_date", ["Ср. загрузка"], ".1%"),
    table("Склады: сводка", WH, "vw_warehouse_performance",
          ["warehouse_name"],
          ["Заказы", "Выручка", "Доля задержек", "Ср. сборка, мин",
           "Ср. загрузка", "Доля дней с перегрузкой"]),

    # --- Страница 4: доставка и регионы ---
    echarts_bar("Срок доставки по тарифам", METHOD, "vw_delivery_performance",
                "method_name", ["Ср. срок, дн", "Ср. транзит, дн"],
                "horizontal", None, ".2f"),
    pie("Структура заказов по тарифам", METHOD, "vw_delivery_performance",
        "method_name", "Заказы"),
    echarts_bar("Задержки по регионам", REGION, "vw_regional_performance",
                "region_name", ["Доля задержек"], "horizontal", None, ".1%",
                sort_desc=True),
    table("Регионы: сводка", REGION, "vw_regional_performance",
          ["region_name"],
          ["Заказы", "Выручка", "Доля задержек", "Ср. срок, дн", "Ср. транзит, дн"]),
]


def ensure_charts(ss) -> dict[str, int]:
    """Создаёт чарты, а у существующих обновляет параметры.

    Просто пропускать существующие нельзя: после правки формата или
    метрики чарт остался бы со старыми настройками.
    """
    status, body = ss.get("/api/v1/chart/?q=(page_size:100)")
    existing = {c["slice_name"]: c["id"] for c in body.get("result", [])}

    ids = {}
    for chart in CHARTS:
        name = chart["slice_name"]
        payload = {k: v for k, v in chart.items() if k != "datasource_name"}
        if name in existing:
            chart_id = existing[name]
            status, body = ss.put(f"/api/v1/chart/{chart_id}", payload)
            if status not in (200, 201):
                raise RuntimeError(f"{name}: {status} {body}")
            ids[name] = chart_id
            print(f"  ~ {name}")
        else:
            status, body = ss.post("/api/v1/chart/", payload)
            if status not in (200, 201):
                raise RuntimeError(f"{name}: {status} {body}")
            ids[name] = body["id"]
            print(f"  + {name}")
    return ids


def layout(chart_ids: dict[str, int]) -> dict:
    """Раскладка дашборда.

    Сетка Superset: ширина — 12 колонок, высота — в единицах по 8 px
    (минимум 40 px). Идентификаторы строк обязаны быть уникальны в
    пределах всего дашборда, поэтому в них входит номер вкладки:
    ROW-<вкладка>-<строка>.
    """
    def box(chart_name, page, row, width, height_px):
        chart_id = chart_ids[chart_name]
        row_id = f"ROW-{page}-{row}"
        return {
            "type": "CHART",
            "id": f"CHART-{chart_id}",
            "meta": {"chartId": chart_id,
                     "sliceName": chart_name,
                     "width": width,
                     "height": height_px // 8},
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", "TABS_ID", f"TAB-{page}", row_id],
        }

    def row(page, row):
        return {
            "type": "ROW",
            "id": f"ROW-{page}-{row}",
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", "TABS_ID", f"TAB-{page}"],
        }

    # (название, строка, ширина в колонках, высота в px). Ширина по строке = 12.
    pages = {
        "1": [
            ("Заказы", 1, 3, 160), ("Выручка", 1, 3, 160),
            ("Средний чек", 1, 3, 160), ("Доля задержек", 1, 3, 160),
            ("Выручка по месяцам", 2, 8, 400), ("Средний срок доставки", 2, 4, 400),
            ("Задержки по складам", 3, 12, 400),
        ],
        "2": [
            ("Задержки: день заказа против следующего дня", 1, 6, 400),
            ("Риск при пропуске рейса", 1, 3, 200),
            ("Задержки: вечерние и дневные заказы", 1, 3, 400),
            ("Задержки по тарифам", 2, 6, 400),
            ("Склад × тариф", 3, 12, 500),
        ],
        "3": [
            ("Время сборки по складам", 1, 6, 400),
            ("Загрузка складов", 1, 6, 400),
            ("Загрузка по дням: Кольцово", 2, 12, 400),
            ("Склады: сводка", 3, 12, 400),
        ],
        "4": [
            ("Срок доставки по тарифам", 1, 7, 400),
            ("Структура заказов по тарифам", 1, 5, 400),
            ("Задержки по регионам", 2, 6, 400),
            ("Регионы: сводка", 2, 6, 400),
        ],
    }

    position = {
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"],
                    "parents": []},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": ["TABS_ID"],
                    "parents": ["ROOT_ID"]},
        "TABS_ID": {"type": "TABS", "id": "TABS_ID", "children": [],
                    "parents": ["ROOT_ID", "GRID_ID"]},
    }

    for page, items in pages.items():
        tab_id = f"TAB-{page}"
        position["TABS_ID"]["children"].append(tab_id)
        position[tab_id] = {"type": "TAB", "id": tab_id,
                            "meta": {"text": TABS[page]},
                            "children": [], "parents": ["ROOT_ID", "GRID_ID", "TABS_ID"]}

        rows = {}
        for name, r, w, h in items:
            if r not in rows:
                rows[r] = row(page, r)
                position[f"ROW-{page}-{r}"] = rows[r]
                position[tab_id]["children"].append(f"ROW-{page}-{r}")
            rows[r]["children"].append(f"CHART-{chart_ids[name]}")
            position[f"CHART-{chart_ids[name]}"] = box(name, page, r, w, h)

    return position


TABS = {
    "1": "Обзор",
    "2": "Причины задержек",
    "3": "Склады",
    "4": "Доставка и регионы",
}


def main() -> None:
    ss = Superset("admin", os.environ["SUPERSET_ADMIN_PASSWORD"])

    print("Чарты:")
    ids = ensure_charts(ss)
    print(f"  всего: {len(ids)}")

    meta = {"label_colors": {}, "shared_label_colors": {},
            "color_scheme_domain": [], "expanded_slices": {},
            "refresh_frequency": 0, "timed_refresh_immune_slices": [],
            "default_filters": "{}", "cross_filters_enabled": False,
            "filter_scopes": {}, "chart_configuration": {}}

    status, body = ss.get("/api/v1/dashboard/?q=(page_size:100)")
    existing = {d["dashboard_title"]: d["id"] for d in body.get("result", [])}

    payload = {
        "dashboard_title": "Логистика: заказы, склады, доставка",
        "slug": "logistics-overview",
        "published": True,
        "position_json": json.dumps(layout(ids), ensure_ascii=False),
        "json_metadata": json.dumps(meta, ensure_ascii=False),
    }

    title = payload["dashboard_title"]
    if title in existing:
        dash_id = existing[title]
        status, body = ss.put(f"/api/v1/dashboard/{dash_id}", payload)
        action = "обновлён"
    else:
        status, body = ss.post("/api/v1/dashboard/", payload)
        dash_id = body.get("id")
        action = "создан"
    if status not in (200, 201):
        raise RuntimeError(f"dashboard: {status} {body}")
    print(f"\nДашборд {action}: id={dash_id}")

    # Связь «чарт — дашборд» хранится отдельно от position_json:
    # без неё дашборд показывает «с этим компонентом не связана ни одна диаграмма».
    # datasource_id в ответе API отсутствует, поэтому берём его из params.
    print("Привязка чартов к дашборду:")
    linked = 0
    for name, chart_id in ids.items():
        status, body = ss.get(f"/api/v1/chart/{chart_id}")
        chart = body["result"]
        if any(d["id"] == dash_id for d in chart.get("dashboards", [])):
            continue
        ds_id = int(json.loads(chart["params"])["datasource"].split("__")[0])
        status, body = ss.put(f"/api/v1/chart/{chart_id}", {
            "slice_name": chart["slice_name"],
            "viz_type": chart["viz_type"],
            "datasource_id": ds_id,
            "datasource_type": "table",
            "params": chart["params"],
            "dashboards": [dash_id],
        })
        if status not in (200, 201):
            raise RuntimeError(f"link {name}: {status} {body}")
        linked += 1
    print(f"  привязано: {linked} из {len(ids)}")

    # Экспорт через API: в assets попадает настоящий дашборд, который можно
    # импортировать в другую инсталляцию Superset, а не список id.
    out = ROOT / "superset" / "assets" / "dashboard_export.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    status, data = ss.get_raw(f"/api/v1/dashboard/export/?q=!({dash_id})")
    if status == 200 and data:
        out.write_bytes(data)
        print(f"Экспорт: {out.relative_to(ROOT)} ({len(data) // 1024} КБ)")
    else:
        print(f"Экспорт не удался: {status}, {len(data)} байт")


if __name__ == "__main__":
    main()
