"""Конфигурация Superset для проекта Warehouse & Logistics Analytics.

Метаданные Superset хранятся в том же PostgreSQL, что и данные проекта,
но в отдельной базе: так не нужен второй сервер БД при ограниченной RAM.
"""

import os

SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "change_me_in_production")

SQLALCHEMY_DATABASE_URI = os.environ["SUPERSET_META_URI"]

# Кэш в памяти: Redis не поднимаем, на этом объёме RAM он лишний.
CACHE_CONFIG = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
}
DATA_CACHE_CONFIG = CACHE_CONFIG
FILTER_STATE_CACHE_CONFIG = CACHE_CONFIG
EXPLORE_FORM_DATA_CACHE_CONFIG = CACHE_CONFIG

# Русская локаль интерфейса и форматов
BABEL_DEFAULT_LOCALE = "ru"
LANGUAGES = {"ru": {"flag": "ru", "name": "Русский"}}

FEATURE_FLAGS = {
    "DASHBOARD_RBAC": False,
    "ENABLE_TEMPLATE_PROCESSING": True,
    "EMBEDDED_SUPERSET": False,
    "ALERT_REPORTS": False,
    "THUMBNAILS": False,
}

# Ограничения, чтобы контейнер не съел всю память машины
ROW_LIMIT = 10000
SUPERSET_WEBSERVER_TIMEOUT = 120
SQLLAB_TIMEOUT = 60
SQLLAB_ASYNC_TIME_LIMIT_SEC = 60

# Предупреждение о небезопасном ключе не нужно при локальном запуске
WTF_CSRF_ENABLED = True
TALISMAN_ENABLED = False

# Без этого Superset не принимает вход по HTTP без HTTPS
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_SAMESITE = "Lax"

# Загружаемые дашборды и чарты
SUPERSET_HOME = "/app/superset_home"

# Убираем лишние логи, чтобы не засорять диск
import logging

logging.getLogger("flask_appbuilder").setLevel(logging.WARNING)
