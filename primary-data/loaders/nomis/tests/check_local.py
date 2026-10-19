# Полная проверка чтения выгрузки Nomis и записи её полей в локальный PostgreSQL. Скрипт
# создаёт отдельную тестовую БД, загружает туда данные и сравнивает все строки с
# исходными, включая повторы.
#
# Дополнительно проверяются повторная загрузка, пропуски, сохранность посторонней
# таблицы и откат при ошибке COPY. Сравнение держит строки в памяти, поэтому этот
# вариант подходит для небольших тестовых выгрузок. Подключаться можно только локально;
# тестовая БД удаляется после проверки.

import argparse
import contextlib
import io
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_loader import SOURCE, _support, loader


# Создаёт тестовую БД, проверяет загрузку и откат ошибок, затем удаляет эту БД.
def main():
    parser = argparse.ArgumentParser(
        description="Compare every raw CSV field with PostgreSQL in a disposable LOCAL database."
    )
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    args = parser.parse_args()
    settings = _support.connection_settings(args.env_file)
    if settings["host"] not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Integration checks may only use localhost")
    tables = loader.raw_tables(
        args.snapshot, _support.read_snapshot(args.snapshot, SOURCE)
    )
    target = "loader_test_" + uuid4().hex[:12]
    with psycopg.connect(**dict(settings, dbname="postgres"), autocommit=True) as admin:
        admin.execute(
            psycopg.sql.SQL("CREATE DATABASE {}").format(psycopg.sql.Identifier(target))
        )
        try:
            # Подменяет подключение загрузчика, чтобы данные попадали только в тестовую
            # БД.
            def connect(_):
                return psycopg.connect(**dict(settings, dbname=target))

            # Сравнивает все исходные строки с записанными, сохраняя значимость
            # повторов.
            def check(tables):
                with connect(None) as conn:
                    for table, (columns, rows) in tables.items():
                        cursor = conn.execute(
                            psycopg.sql.SQL('SELECT * FROM "primary".{}').format(
                                psycopg.sql.Identifier(table)
                            )
                        )
                        assert [column.name for column in cursor.description] == columns
                        assert Counter(cursor.fetchall()) == Counter(rows), table

            with (
                patch.object(_support, "connect", connect),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                other_source = {"other_source_test": (["VALUE"], [("keep",)])}
                _support.replace_tables(None, other_source)
                _support.replace_tables(None, tables)
                check(tables)
                _support.replace_tables(None, tables)
                check(tables)
                check(other_source)

                edge_cases = {
                    "raw_test": (
                        ["TEXT", "VALUE"],
                        [
                            ("a", ""),
                            ("a", ""),
                            ("b", "001.2300"),
                            ("c", "0"),
                            ("d", ".."),
                        ],
                    )
                }
                _support.replace_tables(None, edge_cases)
                check(edge_cases)

                bad = {
                    table: (columns, list(rows))
                    for table, (columns, rows) in tables.items()
                }
                first = min(bad)
                bad[first][1].pop()
                last = max(bad)
                corrupt = list(bad[last][1][0])
                corrupt[0] = "\x00"
                bad[last][1][0] = tuple(corrupt)
                try:
                    _support.replace_tables(None, bad, allow_smaller=True)
                except psycopg.Error, ValueError:
                    pass
                else:
                    raise AssertionError("Expected a COPY failure")
                check(tables)
            print("PASS: every original column and CSV field matches PostgreSQL")
            print(
                "PASS: repeated loading preserves rows, empty strings, formatting and duplicate source records"
            )
            print("PASS: source isolation and rollback of source tables on failure")
        finally:
            admin.execute(
                psycopg.sql.SQL("DROP DATABASE {}").format(
                    psycopg.sql.Identifier(target)
                )
            )
            print("Removed disposable test database:", target)


if __name__ == "__main__":
    main()
