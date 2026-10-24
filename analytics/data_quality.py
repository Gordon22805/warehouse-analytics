"""Проверки качества данных и очистка raw-датасета.

Каждая проверка возвращает найденные проблемы и действие, которое было применено.
Результат сохраняется в data/processed/quality_report.csv.
"""

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

DATE_COLUMNS = {
    "orders": ["order_created_at", "promised_date"],
    "shipments": ["assigned_at", "picking_started_at", "picked_at",
                  "packed_at", "shipped_at", "delivered_at"],
    "warehouses": ["launched_at"],
    "employees": ["hired_at"],
}

ALLOWED_STATUSES = {"delivered", "cancelled"}
SHIPMENT_TIME_CHAIN = ["assigned_at", "picking_started_at", "picked_at",
                       "packed_at", "shipped_at", "delivered_at"]


def load_raw() -> dict[str, pd.DataFrame]:
    tables = {}
    for path in sorted(RAW_DIR.glob("*.csv")):
        name = path.stem
        parse = DATE_COLUMNS.get(name, [])
        tables[name] = pd.read_csv(path, parse_dates=parse if parse else None, encoding="utf-8")
    missing = {"orders", "order_items", "shipments", "products", "warehouses"} - tables.keys()
    if missing:
        raise FileNotFoundError(f"В data/raw не хватает файлов: {sorted(missing)}")
    return tables


def _issue(table: str, check: str, issues: int, severity: str, action: str) -> dict:
    return {
        "table": table,
        "check": check,
        "issues_found": int(issues),
        "severity": severity,
        "action": action,
    }


def clean_orders(orders: pd.DataFrame, methods: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    df = orders.copy()
    issues = []

    dup_mask = df.duplicated(subset=["order_id"], keep="first")
    issues.append(_issue("orders", "duplicate order_id", dup_mask.sum(), "high", "удалены дубликаты"))
    df = df.loc[~dup_mask].copy()

    bad_status = ~df["order_status"].isin(ALLOWED_STATUSES)
    issues.append(_issue("orders", "unknown order_status", bad_status.sum(), "high", "строки удалены"))
    df = df.loc[~bad_status].copy()

    no_date = df["order_created_at"].isna()
    issues.append(_issue("orders", "missing order_created_at", no_date.sum(), "high", "строки удалены"))
    df = df.loc[~no_date].copy()

    no_region = df["region_id"].isna()
    issues.append(_issue("orders", "missing region_id", no_region.sum(), "medium",
                         "строки удалены — регион нельзя восстановить"))
    df = df.loc[~no_region].copy()

    no_customer = df["customer_id"].isna()
    issues.append(_issue("orders", "missing customer_id", no_customer.sum(), "low",
                         "заполнено значением UNKNOWN"))
    df["customer_id"] = df["customer_id"].fillna("UNKNOWN")

    negative = df["goods_amount"] < 0
    issues.append(_issue("orders", "negative goods_amount", negative.sum(), "high", "строки удалены"))
    df = df.loc[~negative].copy()

    # Тариф доставки фиксирован справочником, поэтому пропуск восстанавливается по способу доставки
    fee_map = dict(zip(methods["method_id"], methods["delivery_fee"]))
    no_fee = df["delivery_fee"].isna()
    issues.append(_issue("orders", "missing delivery_fee", no_fee.sum(), "medium",
                         "восстановлено по справочнику delivery_methods"))
    df["delivery_fee"] = df["delivery_fee"].fillna(df["method_id"].map(fee_map))

    impossible_promise = df["promised_date"] < df["order_created_at"].dt.normalize()
    issues.append(_issue("orders", "promised_date earlier than order date", impossible_promise.sum(),
                         "medium", "срок пересчитан как order date + 1 день"))
    df.loc[impossible_promise, "promised_date"] = (
        df.loc[impossible_promise, "order_created_at"].dt.normalize() + pd.Timedelta(days=1)
    )

    return df.reset_index(drop=True), issues


def clean_items(items: pd.DataFrame, valid_orders: set[str],
                valid_products: set[str]) -> tuple[pd.DataFrame, list[dict]]:
    df = items.copy()
    issues = []

    orphan_product = ~df["product_id"].isin(valid_products)
    issues.append(_issue("order_items", "product_id отсутствует в products", orphan_product.sum(),
                         "high", "строки удалены"))
    df = df.loc[~orphan_product].copy()

    orphan_order = ~df["order_id"].isin(valid_orders)
    issues.append(_issue("order_items", "order_id отсутствует в orders", orphan_order.sum(),
                         "high", "строки удалены"))
    df = df.loc[~orphan_order].copy()

    bad_qty = df["quantity"] <= 0
    issues.append(_issue("order_items", "quantity <= 0", bad_qty.sum(), "high", "строки удалены"))
    df = df.loc[~bad_qty].copy()

    bad_price = df["unit_price"] <= 0
    issues.append(_issue("order_items", "unit_price <= 0", bad_price.sum(), "high", "строки удалены"))
    df = df.loc[~bad_price].copy()

    expected_total = (df["quantity"] * df["unit_price"]).round(2)
    mismatched = (expected_total - df["line_total"]).abs() > 0.01
    issues.append(_issue("order_items", "line_total не равен quantity * unit_price",
                         mismatched.sum(), "medium", "line_total пересчитан"))
    df["line_total"] = expected_total

    return df.reset_index(drop=True), issues


def clean_shipments(shipments: pd.DataFrame,
                    valid_orders: set[str]) -> tuple[pd.DataFrame, list[dict]]:
    df = shipments.copy()
    issues = []

    orphan = ~df["order_id"].isin(valid_orders)
    issues.append(_issue("shipments", "order_id отсутствует в orders", orphan.sum(), "high",
                         "строки удалены"))
    df = df.loc[~orphan].copy()

    duplicate = df.duplicated(subset=["order_id"], keep="first")
    issues.append(_issue("shipments", "более одной доставки на заказ", duplicate.sum(), "high",
                         "оставлена первая запись"))
    df = df.loc[~duplicate].copy()

    broken_chain = pd.Series(False, index=df.index)
    for prev_col, next_col in zip(SHIPMENT_TIME_CHAIN, SHIPMENT_TIME_CHAIN[1:]):
        broken_chain |= df[next_col] < df[prev_col]
    issues.append(_issue("shipments", "нарушен порядок этапов заказа", broken_chain.sum(), "high",
                         "строки удалены"))
    df = df.loc[~broken_chain].copy()

    return df.reset_index(drop=True), issues


def validate(tables: dict[str, pd.DataFrame]) -> list[dict]:
    orders = tables["orders"]
    items = tables["order_items"]
    shipments = tables["shipments"]
    issues = []

    no_items = ~orders["order_id"].isin(set(items["order_id"]))
    issues.append(_issue("orders", "заказ без позиций", no_items.sum(), "high",
                         "заказы удалены" if no_items.any() else "нет проблем"))

    delivered_without_shipment = orders.loc[
        orders["order_status"] == "delivered", "order_id"
    ].pipe(lambda s: ~s.isin(set(shipments["order_id"])))
    issues.append(_issue("orders", "доставленный заказ без записи в shipments",
                         delivered_without_shipment.sum(), "high",
                         "заказы переведены в cancelled" if delivered_without_shipment.any()
                         else "нет проблем"))

    return issues


def clean_all(raw: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    issues: list[dict] = []

    orders, order_issues = clean_orders(raw["orders"], raw["delivery_methods"])
    issues += order_issues

    items, item_issues = clean_items(
        raw["order_items"], set(orders["order_id"]), set(raw["products"]["product_id"])
    )
    issues += item_issues

    # Сумма заказа приводится к сумме позиций, иначе выручка в отчётах расходится с детализацией
    line_stats = (
        items.groupby("order_id")
        .agg(goods_amount=("line_total", "sum"), items_count=("order_item_id", "count"))
        .reset_index()
    )
    orders = orders.drop(columns=["goods_amount", "items_count"]).merge(
        line_stats, on="order_id", how="inner"
    )
    issues.append(_issue("orders", "goods_amount / items_count не совпадают с позициями",
                         len(raw["orders"]) - len(orders), "medium",
                         "пересчитано из order_items, заказы без позиций удалены"))

    orders["goods_amount"] = orders["goods_amount"].round(2)
    orders["items_count"] = orders["items_count"].astype(int)
    orders["total_amount"] = (orders["goods_amount"] + orders["delivery_fee"]).round(2)

    shipments, shipment_issues = clean_shipments(raw["shipments"], set(orders["order_id"]))
    issues += shipment_issues

    tables = {
        "regions": raw["regions"],
        "warehouses": raw["warehouses"],
        "delivery_methods": raw["delivery_methods"],
        "categories": raw["categories"],
        "products": raw["products"],
        "employees": raw["employees"],
        "orders": orders,
        "order_items": items,
        "shipments": shipments,
    }

    issues += validate(tables)

    no_shipment = (tables["orders"]["order_status"] == "delivered") & (
        ~tables["orders"]["order_id"].isin(set(tables["shipments"]["order_id"]))
    )
    tables["orders"].loc[no_shipment, "order_status"] = "cancelled"

    return tables, pd.DataFrame(issues)


def save_processed(tables: dict[str, pd.DataFrame], report: pd.DataFrame) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(PROCESSED_DIR / f"{name}.csv", index=False, encoding="utf-8")
    report.to_csv(PROCESSED_DIR / "quality_report.csv", index=False, encoding="utf-8")


def run() -> pd.DataFrame:
    raw = load_raw()
    tables, report = clean_all(raw)
    save_processed(tables, report)

    print(f"{'Таблица':<18}{'Проверка':<52}{'Найдено':>9}")
    print("-" * 81)
    for row in report.itertuples():
        print(f"{row.table:<18}{row.check:<52}{row.issues_found:>9}")
    print("-" * 81)
    print(f"Заказов до очистки:      {len(raw['orders'])}")
    print(f"Заказов после очистки:   {len(tables['orders'])}")
    print(f"Отчёт записан в:         {PROCESSED_DIR / 'quality_report.csv'}")
    return report


if __name__ == "__main__":
    run()
