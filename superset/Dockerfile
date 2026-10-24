# Образ Superset с драйвером PostgreSQL.
# Базовый образ apache/superset не содержит psycopg2, поэтому метаданные
# и подключение к аналитической базе без него не работают.
FROM apache/superset:4.1.4

USER root

RUN pip install --no-cache-dir psycopg2-binary==2.9.10

USER superset
