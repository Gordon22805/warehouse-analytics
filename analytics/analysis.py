"""Аналитический слой: расчёт метрик, проверка гипотез о причинах задержек,
построение графиков и выгрузка витрин для Power BI.

Запуск: python analytics/analysis.py
"""

import os
from decimal import Decimal
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "reports"
FIG_DIR = REPORT_DIR / "figures"
POWERBI_DIR = PROJECT_ROOT / "data" / "powerbi"

PALETTE = ["#2E5EAA", "#E4572E", "#17A398", "#F4A259", "#6A4C93", "#8D99AE"]
GOOD, WARN, BAD = "#17A398", "#F4A259", "#C1352B"

plt.rcParams.update({
    "figure.dpi": 130,
    "savefig.dpi": 130,
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "--",
    "axes.titleweight": "bold",
})


def connect():
    load_dotenv(PROJECT_ROOT / ".env")
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5433"),
        dbname=os.getenv("POSTGRES_DB", "warehouse_analytics"),
        user=os.getenv("POSTGRES_USER", "warehouse_user"),
        password=os.getenv("POSTGRES_PASSWORD", "warehouse_pass"),
    )


def query(conn, sql: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    # psycopg2 отдаёт NUMERIC как Decimal, для расчётов нужен float
    for col in df.columns:
        if df[col].dtype == object:
            sample = df[col].dropna().head(20)
            if len(sample) and isinstance(sample.iloc[0], Decimal):
                df[col] = df[col].astype(float)
    return df


# ---------------------------------------------------------------- метрики

def load_metrics(conn) -> dict[str, pd.DataFrame]:
    return {
        "monthly": query(conn, """
            SELECT DATE_TRUNC('month', order_created_at)::date AS month,
                   COUNT(*) AS total_orders,
                   COUNT(*) FILTER (WHERE order_status = 'delivered') AS delivered_orders,
                   SUM(total_amount) FILTER (WHERE order_status = 'delivered') AS revenue,
                   AVG(total_amount) FILTER (WHERE order_status = 'delivered') AS aov
            FROM orders GROUP BY 1 ORDER BY 1
        """),
        "warehouses": query(conn, "SELECT * FROM vw_warehouse_performance ORDER BY total_orders DESC"),
        "methods": query(conn, "SELECT * FROM vw_delivery_performance ORDER BY delay_rate"),
        "regions": query(conn, "SELECT * FROM vw_regional_performance ORDER BY delay_rate DESC"),
        "facts": query(conn, "SELECT * FROM vw_order_facts"),
        "daily_load": query(conn, "SELECT * FROM vw_warehouse_daily_load"),
        "sla_grid": query(conn, "SELECT * FROM vw_sla_analysis ORDER BY delay_rate DESC"),
        "categories": query(conn, """
            SELECT c.category_name, SUM(i.line_total) AS revenue,
                   COUNT(DISTINCT o.order_id) AS orders
            FROM order_items i
            JOIN products p ON p.product_id = i.product_id
            JOIN categories c ON c.category_id = p.category_id
            JOIN orders o ON o.order_id = i.order_id AND o.order_status = 'delivered'
            GROUP BY 1 ORDER BY revenue DESC
        """),
        "planned_transit": query(conn, """
            SELECT region_id, method_id,
                   base_transit_days + CASE method_id
                       WHEN 'DM-01' THEN 0 WHEN 'DM-02' THEN 0
                       WHEN 'DM-03' THEN 1 WHEN 'DM-04' THEN 1 ELSE 2
                   END AS planned_transit
            FROM regions CROSS JOIN delivery_methods
        """),
    }


def test_hypotheses(m: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Проверка гипотез о причинах задержек статистическими тестами."""
    rows = []
    facts = m["facts"].copy()

    # Гипотеза 1: перегруженный склад задерживает чаще
    load = m["daily_load"][["warehouse_id", "load_date", "utilization"]]
    facts["order_date"] = pd.to_datetime(facts["order_date"]).dt.date
    facts = facts.merge(load, left_on=["warehouse_id", "order_date"],
                        right_on=["warehouse_id", "load_date"], how="left")
    overloaded = facts.loc[facts["utilization"] > 1.0, "is_delayed"]
    normal = facts.loc[facts["utilization"] <= 1.0, "is_delayed"]
    table = [[int(overloaded.sum()), int((~overloaded).sum())],
             [int(normal.sum()), int((~normal).sum())]]
    chi2, p, _, _ = stats.chi2_contingency(table)
    rows.append({
        "hypothesis": "H1: при загрузке склада >100% доля задержек выше",
        "group_a": f"перегрузка (n={len(overloaded)})",
        "metric_a": round(100 * overloaded.mean(), 2),
        "group_b": f"норма (n={len(normal)})",
        "metric_b": round(100 * normal.mean(), 2),
        "test": "chi2",
        "p_value": round(p, 6),
        "significant": "да" if p < 0.05 else "нет",
    })

    # Гипотеза 2: время сборки растёт с загрузкой (корреляция Спирмена)
    rho, p2 = stats.spearmanr(facts["utilization"].astype(float),
                              facts["picking_minutes"].astype(float),
                              nan_policy="omit")
    rows.append({
        "hypothesis": "H2: время сборки растёт с загрузкой склада",
        "group_a": "rho Спирмена",
        "metric_a": round(rho, 3),
        "group_b": "выборка",
        "metric_b": int(facts["picking_minutes"].notna().sum()),
        "test": "spearman",
        "p_value": round(p2, 10),
        "significant": "да" if p2 < 0.05 else "нет",
    })

    # Гипотеза 3: заказы после 20:00 опаздывают чаще
    facts["hour"] = pd.to_datetime(facts["order_created_at"]).dt.hour
    late_orders = facts.loc[facts["hour"] >= 20, "is_delayed"]
    early_orders = facts.loc[facts["hour"] < 20, "is_delayed"]
    table3 = [[int(late_orders.sum()), int((~late_orders).sum())],
              [int(early_orders.sum()), int((~early_orders).sum())]]
    chi3, p3, _, _ = stats.chi2_contingency(table3)
    rows.append({
        "hypothesis": "H3: заказы после 20:00 опаздывают чаще",
        "group_a": f"после 20:00 (n={len(late_orders)})",
        "metric_a": round(100 * late_orders.mean(), 2),
        "group_b": f"до 20:00 (n={len(early_orders)})",
        "metric_b": round(100 * early_orders.mean(), 2),
        "test": "chi2",
        "p_value": round(p3, 10),
        "significant": "да" if p3 < 0.05 else "нет",
    })

    # Гипотеза 4: Economy опаздывает чаще Standard
    eco = facts.loc[facts["method_id"] == "DM-05", "is_delayed"]
    std = facts.loc[facts["method_id"] == "DM-03", "is_delayed"]
    table4 = [[int(eco.sum()), int((~eco).sum())], [int(std.sum()), int((~std).sum())]]
    chi4, p4, _, _ = stats.chi2_contingency(table4)
    rows.append({
        "hypothesis": "H4: Economy опаздывает чаще Standard",
        "group_a": f"Economy (n={len(eco)})",
        "metric_a": round(100 * eco.mean(), 2),
        "group_b": f"Standard (n={len(std)})",
        "metric_b": round(100 * std.mean(), 2),
        "test": "chi2",
        "p_value": round(p4, 10),
        "significant": "да" if p4 < 0.05 else "нет",
    })

    # Гипотеза 5: удалённые регионы ждут дольше (Манн-Уитни)
    remote = {"R-09", "R-10"}
    rem = facts.loc[facts["region_id"].isin(remote), "lead_time_days"]
    core = facts.loc[~facts["region_id"].isin(remote), "lead_time_days"]
    u, p5 = stats.mannwhitneyu(rem, core, alternative="greater")
    rows.append({
        "hypothesis": "H5: удалённые регионы получают заказ дольше",
        "group_a": f"удалённые (n={len(rem)})",
        "metric_a": round(rem.mean(), 2),
        "group_b": f"остальные (n={len(core)})",
        "metric_b": round(core.mean(), 2),
        "test": "mann-whitney",
        "p_value": round(p5, 10),
        "significant": "да" if p5 < 0.05 else "нет",
    })

    # Гипотеза 6: в пиковые периоды SLA хуже (хи-квадрат)
    facts["order_date"] = pd.to_datetime(facts["order_date"])
    peak_mask = (
        facts["order_date"].between("2025-11-23", "2025-12-01")
        | facts["order_date"].between("2025-12-10", "2025-12-22")
        | facts["order_date"].between("2025-07-10", "2025-07-24")
    )
    peak = facts.loc[peak_mask, "is_delayed"]
    calm = facts.loc[~peak_mask, "is_delayed"]
    table6 = [[int(peak.sum()), int((~peak).sum())], [int(calm.sum()), int((~calm).sum())]]
    chi6, p6, _, _ = stats.chi2_contingency(table6)
    rows.append({
        "hypothesis": "H6: в пиковые периоды доля задержек выше",
        "group_a": f"пик (n={len(peak)})",
        "metric_a": round(100 * peak.mean(), 2),
        "group_b": f"обычные дни (n={len(calm)})",
        "metric_b": round(100 * calm.mean(), 2),
        "test": "chi2",
        "p_value": round(p6, 10),
        "significant": "да" if p6 < 0.05 else "нет",
    })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------- графики

def save(fig, name: str) -> None:
    fig.tight_layout()
    fig.savefig(FIG_DIR / name, bbox_inches="tight")
    plt.close(fig)


def plot_revenue_monthly(m) -> None:
    df = m["monthly"]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.bar(df["month"].astype(str).str[:7], df["revenue"] / 1e6, color=PALETTE[0], width=0.62)
    ax.set_title("Выручка по месяцам")
    ax.set_ylabel("млн руб.")
    for x, v in zip(range(len(df)), df["revenue"] / 1e6):
        ax.text(x, v + 1.5, f"{v:.0f}", ha="center", fontsize=9)
    ax.set_ylim(0, (df["revenue"] / 1e6).max() * 1.16)
    save(fig, "01_revenue_monthly.png")


def plot_orders_weekly(m) -> None:
    df = m["facts"].copy()
    df["order_date"] = pd.to_datetime(df["order_date"])
    weekly = df.set_index("order_date").resample("W")["order_id"].count()
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    ax.plot(weekly.index, weekly.values, color=PALETTE[0], linewidth=2)
    ax.fill_between(weekly.index, weekly.values, alpha=0.15, color=PALETTE[0])
    for start, end, label in [("2025-07-10", "2025-07-24", "Летняя распродажа"),
                              ("2025-11-23", "2025-12-01", "Чёрная пятница"),
                              ("2025-12-10", "2025-12-22", "Декабрьский пик")]:
        ax.axvspan(pd.Timestamp(start), pd.Timestamp(end), color=BAD, alpha=0.10)
        ax.text(pd.Timestamp(start), weekly.max() * 1.03, label, fontsize=8, color=BAD)
    ax.set_title("Доставленные заказы по неделям")
    ax.set_ylabel("заказов")
    ax.set_ylim(0, weekly.max() * 1.14)
    save(fig, "02_orders_weekly.png")


def plot_warehouse_perf(m) -> None:
    df = m["warehouses"].sort_values("avg_picking_minutes")
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.3))
    labels = df["warehouse_name"].str.replace("Склад ", "", regex=False)

    axes[0].barh(labels, df["avg_picking_minutes"], color=PALETTE[0])
    axes[0].set_title("Среднее время сборки, мин")
    axes[0].axvline(df["avg_picking_minutes"].mean(), color=BAD, linestyle="--", linewidth=1.4)
    axes[0].text(df["avg_picking_minutes"].mean(), -0.6, "среднее по сети",
                 color=BAD, fontsize=8, ha="center")

    axes[1].barh(labels, df["avg_utilization"] * 100, color=PALETTE[1])
    axes[1].axvline(100, color=BAD, linestyle="--", linewidth=1.4)
    axes[1].set_title("Средняя загрузка, % мощности")

    colors = [BAD if v > df["delay_rate"].mean() else GOOD for v in df["delay_rate"]]
    axes[2].barh(labels, df["delay_rate"], color=colors)
    axes[2].axvline(df["delay_rate"].mean(), color=BAD, linestyle="--", linewidth=1.4)
    axes[2].set_title("Доля задержек, %")

    fig.suptitle("Эффективность складов", fontweight="bold", y=1.02)
    save(fig, "03_warehouse_performance.png")


def plot_load_vs_delay(m) -> None:
    facts = m["facts"].copy()
    facts["order_date"] = pd.to_datetime(facts["order_date"]).dt.date
    load = m["daily_load"]
    facts = facts.merge(load[["warehouse_id", "load_date", "utilization"]],
                        left_on=["warehouse_id", "order_date"],
                        right_on=["warehouse_id", "load_date"], how="left")

    bands = pd.cut(facts["utilization"], [0, 0.6, 0.8, 0.95, 1.05, 3.0],
                   labels=["<60%", "60-80%", "80-95%", "95-105%", ">105%"])
    grp = facts.groupby(bands, observed=True).agg(
        picking=("picking_minutes", "mean"),
        delay=("is_delayed", "mean"),
        orders=("order_id", "count"),
    )

    fig, ax1 = plt.subplots(figsize=(9, 4.4))
    x = np.arange(len(grp))
    ax1.bar(x, grp["picking"], color=PALETTE[0], width=0.55, label="время сборки")
    ax1.set_ylabel("Время сборки, мин", color=PALETTE[0])
    ax1.set_xticks(x)
    ax1.set_xticklabels(grp.index, rotation=0)
    ax1.set_xlabel("Загрузка склада в день заказа")
    ax1.set_ylim(0, grp["picking"].max() * 1.35)

    ax2 = ax1.twinx()
    ax2.plot(x, grp["delay"] * 100, color=BAD, marker="o", linewidth=2.2, label="доля задержек")
    ax2.set_ylabel("Доля задержек, %", color=BAD)
    ax2.set_ylim(0, grp["delay"].max() * 130)
    ax2.grid(False)

    for xi, (p, d) in enumerate(zip(grp["picking"], grp["delay"] * 100)):
        ax1.text(xi, p + 0.8, f"{p:.0f}", ha="center", fontsize=9, color=PALETTE[0])
        ax2.text(xi, d + 0.5, f"{d:.1f}%", ha="center", fontsize=9, color=BAD)

    ax1.set_title("Загрузка склада: время сборки и доля задержек")
    save(fig, "04_load_vs_delay.png")


def plot_methods(m) -> None:
    df = m["methods"].sort_values("delay_rate")
    fig, ax = plt.subplots(figsize=(9, 4.0))
    colors = [BAD if v > 15 else WARN if v > 10 else GOOD for v in df["delay_rate"]]
    bars = ax.barh(df["method_name"], df["delay_rate"], color=colors)
    for bar, v, n in zip(bars, df["delay_rate"], df["delivered_orders"]):
        ax.text(v + 0.4, bar.get_y() + bar.get_height() / 2,
                f"{v:.1f}%  (n={n:,})".replace(",", " "), va="center", fontsize=9)
    ax.set_title("Доля задержек по способам доставки")
    ax.set_xlabel("% заказов с опозданием")
    ax.set_xlim(0, df["delay_rate"].max() * 1.35)
    save(fig, "05_methods_delay.png")


def plot_regions(m) -> None:
    df = m["regions"].copy()
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    sc = ax.scatter(df["avg_lead_time_days"], df["delay_rate"],
                    s=df["delivered_orders"] / 3, color=PALETTE[0],
                    alpha=0.65, edgecolor="white", linewidth=1.2)
    for _, r in df.iterrows():
        ax.annotate(r["region_name"].replace(" и Московская область", "")
                                .replace(" и Ленинградская область", ""),
                    (r["avg_lead_time_days"], r["delay_rate"]),
                    fontsize=8, xytext=(6, 4), textcoords="offset points")
    ax.axhline(df["delay_rate"].mean(), color=BAD, linestyle="--", linewidth=1.2)
    ax.set_xlabel("Средний срок доставки, дней")
    ax.set_ylabel("Доля задержек, %")
    ax.set_title("Регионы: срок доставки и доля задержек (размер = объём заказов)")
    save(fig, "06_regions.png")


def plot_sla_heatmap(m) -> None:
    df = m["sla_grid"]
    pivot = df.pivot_table(index="warehouse_name", columns="method_name",
                           values="delay_rate", aggfunc="mean")
    order_cols = ["Same-Day Courier", "Express", "Standard", "Pickup Point", "Economy"]
    pivot = pivot[[c for c in order_cols if c in pivot.columns]]
    pivot = pivot.sort_index()

    fig, ax = plt.subplots(figsize=(9, 4.2))
    im = ax.imshow(pivot.values, cmap="RdYlGn_r", aspect="auto", vmin=0, vmax=35)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=18, ha="right")
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index.str.replace("Склад ", "", regex=False))
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.0f}%", ha="center", va="center", fontsize=9,
                        color="white" if v > 24 else "black")
    ax.set_title("Доля задержек: склад × способ доставки")
    ax.grid(False)
    fig.colorbar(im, ax=ax, label="%", fraction=0.03)
    save(fig, "07_sla_heatmap.png")


def plot_stage_breakdown(m) -> None:
    facts = m["facts"].copy()
    facts["created"] = pd.to_datetime(facts["order_created_at"])
    stages = {
        "Ожидание в очереди": (pd.to_datetime(facts["picking_started_at"]) - facts["created"]).dt.total_seconds() / 3600,
        "Сборка": (pd.to_datetime(facts["picked_at"]) - pd.to_datetime(facts["picking_started_at"])).dt.total_seconds() / 3600,
        "Упаковка": (pd.to_datetime(facts["packed_at"]) - pd.to_datetime(facts["picked_at"])).dt.total_seconds() / 3600,
        "Ожидание рейса": (pd.to_datetime(facts["shipped_at"]) - pd.to_datetime(facts["packed_at"])).dt.total_seconds() / 3600,
    }
    means = {k: v.mean() for k, v in stages.items()}

    fig, ax = plt.subplots(figsize=(9, 4.0))
    bars = ax.bar(list(means.keys()), list(means.values()),
                  color=[PALETTE[0], PALETTE[2], PALETTE[3], PALETTE[1]], width=0.6)
    total = sum(means.values())
    for bar, (k, v) in zip(bars, means.items()):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.06,
                f"{v:.2f} ч\n{100 * v / total:.0f}%", ha="center", fontsize=9)
    ax.set_ylabel("часов на заказ")
    ax.set_title("Внутренний цикл склада: где теряется время (среднее по заказам)")
    ax.set_ylim(0, max(means.values()) * 1.3)
    save(fig, "08_stage_breakdown.png")


def plot_delay_distribution(m) -> None:
    df = m["facts"]["delay_days"].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(8.5, 4.0))
    colors = [GOOD if i <= 0 else WARN if i == 1 else BAD for i in df.index]
    ax.bar(df.index.astype(str), df.values, color=colors, width=0.62)
    ax.set_xlabel("Отклонение от обещанной даты, дней")
    ax.set_ylabel("заказов")
    ax.set_title("Распределение отклонений от обещанного срока")
    for x, v in enumerate(df.values):
        ax.text(x, v + 120, f"{v:,}".replace(",", " "), ha="center", fontsize=8)
    save(fig, "09_delay_distribution.png")


def plot_hour_effect(m) -> None:
    facts = m["facts"].copy()
    facts["hour"] = pd.to_datetime(facts["order_created_at"]).dt.hour
    grp = facts.groupby("hour").agg(delay=("is_delayed", "mean"), n=("order_id", "count"))
    grp = grp[grp["n"] >= 50]

    fig, ax = plt.subplots(figsize=(9, 4.0))
    colors = [BAD if h >= 20 else PALETTE[0] for h in grp.index]
    ax.bar(grp.index, grp["delay"] * 100, color=colors, width=0.72)
    ax.axvline(19.5, color=BAD, linestyle="--", linewidth=1.5)
    ax.text(19.7, grp["delay"].max() * 92, "вечерний рейс 20:00", color=BAD, fontsize=8)
    ax.set_xlabel("Час оформления заказа")
    ax.set_ylabel("Доля задержек, %")
    ax.set_title("Заказы, оформленные после 20:00, опаздывают в два раза чаще")
    ax.set_xticks(range(0, 24, 2))
    save(fig, "10_hour_effect.png")


def plot_delay_causes(m) -> None:
    """Показывает механизм задержки: пропуск вечернего рейса расходует весь буфер SLA."""
    facts = m["facts"].copy()
    facts["dispatch_lag"] = (pd.to_datetime(facts["shipped_at"]).dt.normalize()
                             - pd.to_datetime(facts["order_date"])).dt.days
    facts = facts.merge(m["planned_transit"], on=["region_id", "method_id"], how="left")
    # SLA = плановый транзит + один день на обработку заказа
    facts["sla_days"] = facts["planned_transit"] + 1
    facts["actual_transit"] = (pd.to_datetime(facts["delivered_at"]).dt.normalize()
                               - pd.to_datetime(facts["shipped_at"]).dt.normalize()).dt.days

    grp = (facts.groupby("dispatch_lag")
           .agg(orders=("order_id", "count"), delay=("is_delayed", "mean"))
           .reset_index())
    grp["label"] = grp["dispatch_lag"].map(
        {0: "Отгружен в день заказа\n(буфер SLA сохранён)",
         1: "Отгружен на следующий день\n(буфер SLA израсходован)"}
    )

    fig, ax = plt.subplots(figsize=(8.6, 4.2))
    colors = [GOOD, BAD]
    bars = ax.bar(grp["label"], grp["delay"] * 100, color=colors, width=0.5)
    for bar, (_, row) in zip(bars, grp.iterrows()):
        ax.text(bar.get_x() + bar.get_width() / 2, row["delay"] * 100 + 0.7,
                f"{row['delay'] * 100:.1f}%\n{int(row['orders']):,} заказов".replace(",", " "),
                ha="center", fontsize=10)
    ax.set_ylabel("Доля задержек, %")
    ax.set_ylim(0, grp["delay"].max() * 100 * 1.35)
    ax.set_title("Пропуск вечернего рейса увеличивает риск задержки в 4,9 раза")
    save(fig, "12_delay_causes.png")


def plot_categories(m) -> None:
    df = m["categories"].head(10)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.barh(df["category_name"][::-1], df["revenue"][::-1] / 1e6, color=PALETTE[0])
    ax.set_xlabel("млн руб.")
    ax.set_title("Топ-10 категорий по выручке")
    save(fig, "11_categories.png")


# ---------------------------------------------------------------- выгрузки

def export_powerbi(m: dict[str, pd.DataFrame], hypotheses: pd.DataFrame) -> None:
    """Выгружает витрины по схеме «звезда».

    Измерения (dim_*) содержат только атрибуты, факты (fact_*) — ключи и меры,
    агрегаты (agg_*) — готовые сводки для карточек. Смешивать нельзя: если
    положить суммы в измерение, при срезе по другому измерению они задублируются.
    """
    POWERBI_DIR.mkdir(parents=True, exist_ok=True)

    facts = m["facts"].copy()
    facts["order_date"] = pd.to_datetime(facts["order_date"])
    for col in ("order_created_at", "shipped_at", "delivered_at", "promised_date"):
        facts[col] = pd.to_datetime(facts[col])

    # Вычисляемые колонки: без них фильтры DAX по сравнению двух колонок
    # не работают (Power BI запрещает column-to-column в фильтре CALCULATE).
    facts["order_hour"] = facts["order_created_at"].dt.hour
    facts["dispatch_lag_days"] = (
        facts["shipped_at"].dt.normalize() - facts["order_date"]
    ).dt.days
    facts["is_next_day_ship"] = facts["dispatch_lag_days"] >= 1
    facts["is_evening_order"] = facts["order_hour"] >= 20
    facts["order_date"] = facts["order_date"].dt.strftime("%Y-%m-%d")

    facts.to_csv(POWERBI_DIR / "fact_orders.csv", index=False, encoding="utf-8-sig")
    m["daily_load"].to_csv(POWERBI_DIR / "fact_warehouse_load.csv",
                           index=False, encoding="utf-8-sig")

    # --- Измерения: только атрибуты ---
    dim_warehouse = (m["warehouses"][["warehouse_id", "warehouse_name", "city", "daily_capacity"]]
                     .sort_values("warehouse_id"))
    dim_warehouse.to_csv(POWERBI_DIR / "dim_warehouse.csv", index=False, encoding="utf-8-sig")

    (m["methods"][["method_id", "method_name"]].sort_values("method_id")
     .to_csv(POWERBI_DIR / "dim_delivery_method.csv", index=False, encoding="utf-8-sig"))

    (m["regions"][["region_id", "region_name"]].sort_values("region_id")
     .to_csv(POWERBI_DIR / "dim_region.csv", index=False, encoding="utf-8-sig"))

    dim_date = build_dim_date(facts["order_date"].min(), facts["order_date"].max())
    dim_date.to_csv(POWERBI_DIR / "dim_date.csv", index=False, encoding="utf-8-sig")

    # --- Агрегаты: готовые сводки для карточек, не для срезов по факту ---
    m["warehouses"].to_csv(POWERBI_DIR / "agg_warehouse_summary.csv",
                           index=False, encoding="utf-8-sig")
    m["methods"].to_csv(POWERBI_DIR / "agg_method_summary.csv",
                        index=False, encoding="utf-8-sig")
    m["regions"].to_csv(POWERBI_DIR / "agg_region_summary.csv",
                        index=False, encoding="utf-8-sig")

    daily = (
        facts.groupby("order_date")
        .agg(total_orders=("order_id", "count"),
             revenue=("total_amount", "sum"),
             delayed_orders=("is_delayed", "sum"),
             avg_lead_time_days=("lead_time_days", "mean"),
             avg_picking_minutes=("picking_minutes", "mean"))
        .reset_index()
    )
    daily["delay_rate"] = (100 * daily["delayed_orders"] / daily["total_orders"]).round(2)
    daily.to_csv(POWERBI_DIR / "agg_daily.csv", index=False, encoding="utf-8-sig")

    m["sla_grid"].to_csv(POWERBI_DIR / "agg_sla_grid.csv", index=False, encoding="utf-8-sig")
    hypotheses.to_csv(POWERBI_DIR / "hypothesis_tests.csv", index=False, encoding="utf-8-sig")


WEEKDAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг",
               "Пятница", "Суббота", "Воскресенье"]
MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
             "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


def build_dim_date(start: str, end: str) -> pd.DataFrame:
    """Календарь для срезов и time intelligence. Непрерывный, без пропусков."""
    dates = pd.date_range(start=start, end=end, freq="D")
    iso_weekday = dates.day_of_week + 1  # pandas: 0 = понедельник, ISO: 1 = понедельник
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "year": dates.year,
        "quarter": "Q" + dates.quarter.astype(str),
        "month_number": dates.month,
        "month_name": [MONTHS_RU[m - 1] for m in dates.month],
        "year_month": dates.strftime("%Y-%m"),
        "day_of_month": dates.day,
        "weekday_number": iso_weekday,
        "weekday_name": [WEEKDAYS_RU[d - 1] for d in iso_weekday],
        "is_weekend": iso_weekday >= 6,
    })


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        metrics = load_metrics(conn)
    finally:
        conn.close()

    hypotheses = test_hypotheses(metrics)

    plot_revenue_monthly(metrics)
    plot_orders_weekly(metrics)
    plot_warehouse_perf(metrics)
    plot_load_vs_delay(metrics)
    plot_methods(metrics)
    plot_regions(metrics)
    plot_sla_heatmap(metrics)
    plot_stage_breakdown(metrics)
    plot_delay_distribution(metrics)
    plot_hour_effect(metrics)
    plot_delay_causes(metrics)
    plot_categories(metrics)

    export_powerbi(metrics, hypotheses)

    hypotheses.to_csv(REPORT_DIR / "hypothesis_tests.csv", index=False, encoding="utf-8")

    print(f"Графиков сохранено:  {len(list(FIG_DIR.glob('*.png')))}")
    print(f"Витрины для Power BI: {POWERBI_DIR}")
    print("\nПроверка гипотез:")
    print(hypotheses[["hypothesis", "metric_a", "metric_b", "p_value", "significant"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
