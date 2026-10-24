"""Метрики и вычисляемые колонки датасетов Superset.

Метрики — это агрегаты, которые Superset считает сам. Логика совпадает
с SQL-запросами из sql/ и мерами Power BI из powerbi/dax_measures.dax.

Формат d3 задаётся здесь, а не в каждом чарте: иначе одна и та же метрика
в карточке и в таблице выглядела бы по-разному.
"""

DELAYED = "CASE WHEN is_delayed THEN 1 ELSE 0 END"
PCT = ".1%"
MONEY = "$,.0f"
COUNT = ",d"
MINUTES = ",.1f"
DAYS = ",.2f"

FACT_METRICS = {
    "Заказы": ("COUNT(*)", "Количество доставленных заказов", COUNT),
    "Выручка": ("SUM(total_amount)", "Сумма выручки по доставленным заказам", MONEY),
    "Средний чек": ("AVG(total_amount)", "Выручка на один заказ", MONEY),
    "Задержки": (f"SUM({DELAYED})", "Заказы, доставленные позже обещанной даты", COUNT),
    "Доля задержек": (f"AVG({DELAYED})", "Доля задержек в общем числе доставленных", PCT),
    "Ср. сборка, мин": ("AVG(picking_minutes)", "Среднее время сборки", MINUTES),
    "Ср. упаковка, мин": ("AVG(packing_minutes)", "Среднее время упаковки", MINUTES),
    "Ср. цикл, ч": ("AVG(fulfillment_hours)", "От создания заказа до отгрузки", DAYS),
    "Ср. транзит, дн": ("AVG(transit_days)", "От отгрузки до доставки", DAYS),
    "Ср. срок, дн": ("AVG(lead_time_days)", "От заказа до доставки", DAYS),
    "Позиций на заказ": ("AVG(items_count)", "Среднее число позиций", DAYS),
    "Доля отгрузки на след. день": (
        "AVG(CASE WHEN is_next_day_ship THEN 1 ELSE 0 END)",
        "Доля заказов, отгруженных позже дня оформления", PCT),
    "Задержки при отгрузке в день заказа": (
        "SUM(CASE WHEN NOT is_next_day_ship AND is_delayed THEN 1 ELSE 0 END)::numeric"
        " / NULLIF(SUM(CASE WHEN NOT is_next_day_ship THEN 1 ELSE 0 END), 0)",
        "Доля задержек среди заказов, отгруженных в день оформления", PCT),
    "Задержки при отгрузке на след. день": (
        "SUM(CASE WHEN is_next_day_ship AND is_delayed THEN 1 ELSE 0 END)::numeric"
        " / NULLIF(SUM(CASE WHEN is_next_day_ship THEN 1 ELSE 0 END), 0)",
        "Доля задержек среди заказов, отгруженных на следующий день", PCT),
    "Риск при пропуске рейса": (
        "(SUM(CASE WHEN is_next_day_ship AND is_delayed THEN 1 ELSE 0 END)::numeric"
        " / NULLIF(SUM(CASE WHEN is_next_day_ship THEN 1 ELSE 0 END), 0))"
        " / NULLIF(SUM(CASE WHEN NOT is_next_day_ship AND is_delayed THEN 1 ELSE 0 END)::numeric"
        " / NULLIF(SUM(CASE WHEN NOT is_next_day_ship THEN 1 ELSE 0 END), 0), 0)",
        "Во сколько раз пропуск вечернего рейса повышает риск задержки", ",.2f"),
    "Задержки при вечернем заказе": (
        "SUM(CASE WHEN is_evening_order AND is_delayed THEN 1 ELSE 0 END)::numeric"
        " / NULLIF(SUM(CASE WHEN is_evening_order THEN 1 ELSE 0 END), 0)",
        "Доля задержек среди заказов после 20:00", PCT),
    "Задержки при дневном заказе": (
        "SUM(CASE WHEN NOT is_evening_order AND is_delayed THEN 1 ELSE 0 END)::numeric"
        " / NULLIF(SUM(CASE WHEN NOT is_evening_order THEN 1 ELSE 0 END), 0)",
        "Доля задержек среди заказов до 20:00", PCT),
}

FACT_COLUMNS = {
    "Режим отгрузки": (
        "CASE WHEN is_next_day_ship THEN 'На следующий день' ELSE 'В день заказа' END",
        "Подпись для среза вместо true/false"),
    "Время заказа": (
        "CASE WHEN is_evening_order THEN 'После 20:00' ELSE 'До 20:00' END",
        "Подпись для среза вместо true/false"),
}

LOAD_METRICS = {
    "Ср. загрузка": ("AVG(utilization)", "Средняя загрузка склада относительно мощности", PCT),
    "Пиковая загрузка": ("MAX(utilization)", "Максимальная загрузка за период", PCT),
    "Дней с перегрузкой": (
        "SUM(CASE WHEN utilization > 1 THEN 1 ELSE 0 END)",
        "Дни, когда заказов было больше суточной мощности", COUNT),
    "Дней в периоде": ("COUNT(*)", "Число дней с заказами", COUNT),
    "Заказов в день": ("AVG(orders_count)", "Среднее число заказов на склад в день", ",.0f"),
}

WH_METRICS = {
    "Заказы": ("SUM(delivered_orders)", "Доставленные заказы склада", COUNT),
    "Выручка": ("SUM(revenue)", "Выручка склада", MONEY),
    # Во views доли хранятся в процентах (0–100), а формат .1% ждёт долю
    # от единицы, поэтому делим на 100.
    "Доля задержек": ("AVG(delay_rate) / 100.0", "Доля задержек склада", PCT),
    "Ср. сборка, мин": ("AVG(avg_picking_minutes)", "Среднее время сборки", MINUTES),
    "Ср. загрузка": ("AVG(avg_utilization)", "Средняя загрузка", PCT),
    "Пиковая загрузка": ("MAX(peak_utilization)", "Максимальная загрузка", PCT),
    "Доля дней с перегрузкой": (
        "AVG(overloaded_days_share) / 100.0", "Доля дней перегрузки", PCT),
    "Доля заказов сети": ("SUM(orders_share) / 100.0", "Доля склада в заказах сети", PCT),
}

METHOD_METRICS = {
    "Заказы": ("SUM(delivered_orders)", "Доставленные заказы", COUNT),
    "Выручка": ("SUM(revenue)", "Выручка тарифа", MONEY),
    "Доля задержек": ("AVG(delay_rate) / 100.0", "Доля задержек тарифа", PCT),
    "Ср. транзит, дн": ("AVG(avg_transit_days)", "Средний транзит", DAYS),
    "Ср. срок, дн": ("AVG(avg_lead_time_days)", "Средний срок доставки", DAYS),
    "Ср. опоздание, дн": (
        "AVG(avg_delay_days_when_late)", "Среднее опоздание при задержке", DAYS),
}

REGION_METRICS = {
    "Заказы": ("SUM(delivered_orders)", "Доставленные заказы", COUNT),
    "Выручка": ("SUM(revenue)", "Выручка региона", MONEY),
    "Доля задержек": ("AVG(delay_rate) / 100.0", "Доля задержек региона", PCT),
    "Ср. транзит, дн": ("AVG(avg_transit_days)", "Средний транзит", DAYS),
    "Ср. срок, дн": ("AVG(avg_lead_time_days)", "Средний срок доставки", DAYS),
}

DAILY_METRICS = {
    "Заказы": ("SUM(delivered_orders)", "Доставленные заказы за день", COUNT),
    "Выручка": ("SUM(revenue)", "Выручка за день", MONEY),
    "Отмены": ("SUM(cancelled_orders)", "Отменённые заказы за день", COUNT),
    "Средний чек": ("AVG(avg_order_value)", "Средний чек за день", MONEY),
}

SLA_METRICS = {
    "Заказы": ("SUM(delivered_orders)", "Доставленные заказы", COUNT),
    "Доля задержек": ("AVG(delay_rate) / 100.0", "Доля задержек", PCT),
    "Ср. сборка, мин": ("AVG(avg_picking_minutes)", "Среднее время сборки", MINUTES),
    "Ср. цикл, ч": ("AVG(avg_fulfillment_hours)", "Средний внутренний цикл", DAYS),
    "Ср. транзит, дн": ("AVG(avg_transit_days)", "Средний транзит", DAYS),
}

BY_DATASET = {
    1: (FACT_METRICS, FACT_COLUMNS),      # vw_order_facts
    2: (WH_METRICS, {}),                  # vw_warehouse_performance
    3: (METHOD_METRICS, {}),              # vw_delivery_performance
    4: (REGION_METRICS, {}),              # vw_regional_performance
    5: (LOAD_METRICS, {}),                # vw_warehouse_daily_load
    6: (DAILY_METRICS, {}),               # vw_daily_orders
    7: (SLA_METRICS, {}),                 # vw_sla_analysis
}
