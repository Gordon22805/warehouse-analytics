"""Запуск SQL-файлов из sql/ и вывод результатов.

Использование:
    python sql/run_queries.py            # все файлы
    python sql/run_queries.py 01         # только 01_overview.sql
"""

import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = Path(__file__).resolve().parent


def connect():
    load_dotenv(PROJECT_ROOT / ".env")
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5433"),
        dbname=os.getenv("POSTGRES_DB", "warehouse_analytics"),
        user=os.getenv("POSTGRES_USER", "warehouse_user"),
        password=os.getenv("POSTGRES_PASSWORD", "warehouse_pass"),
    )


def split_statements(sql_text: str) -> list[str]:
    statements, buffer = [], []
    for line in sql_text.splitlines():
        if line.strip().startswith("--"):
            continue
        buffer.append(line)
        if line.rstrip().endswith(";"):
            statement = "\n".join(buffer).strip().rstrip(";").strip()
            if statement:
                statements.append(statement)
            buffer = []
    return statements


def fetch(conn, statement: str) -> pd.DataFrame:
    # курсор без параметров, поэтому символ % в строковых литералах не интерпретируется
    with conn.cursor() as cur:
        cur.execute(statement)
        columns = [desc[0] for desc in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=columns)


def run_file(conn, path: Path) -> None:
    print(f"\n{'=' * 90}\n{path.name}\n{'=' * 90}")
    for idx, statement in enumerate(split_statements(path.read_text(encoding="utf-8")), start=1):
        try:
            df = fetch(conn, statement)
        except Exception as exc:
            conn.rollback()
            print(f"\n[{idx}] ОШИБКА: {exc}")
            continue
        print(f"\n--- запрос {idx} ---")
        print(df.to_string(index=False))


def main() -> None:
    pattern = sys.argv[1] if len(sys.argv) > 1 else ""
    conn = connect()
    try:
        for path in sorted(SQL_DIR.glob("*.sql")):
            if pattern in path.name:
                run_file(conn, path)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
