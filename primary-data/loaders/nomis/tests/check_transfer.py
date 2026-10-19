# Проверяет прямой перенос между PostgreSQL без API и больших исходных выгрузок. Для
# проверки создаются две отдельные локальные БД: одна играет роль источника, другая —
# назначения.
#
# На небольших таблицах проверяются точность полей, SQL NULL, повторы, пропуск
# совпадающих данных и защита от потери истории. Отдельные сценарии проверяют откат при
# ошибке и переход со старой структуры BoE. Нужны права на создание БД; обе тестовые
# базы удаляются после завершения.

import argparse
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _postgres_transfer as transport
from _nomis_support import connection_settings, copy_batch


# Создаёт две тестовые БД и прогоняет успешный перенос, повторный запуск и ошибки.
def main():
    parser = argparse.ArgumentParser(
        description="Exercise direct transfer against two disposable LOCAL PostgreSQL databases."
    )
    parser.add_argument("--env-file", required=True, type=Path)
    args = parser.parse_args()
    settings = transport.endpoint(connection_settings(args.env_file), local=True)
    names = ["transfer_test_" + uuid4().hex for _ in range(2)]
    src, dst = [dict(settings, dbname=name) for name in names]
    fields = ["DATE", "VALUE", "LABEL"]
    rows = [("2020", str(i), "same label") for i in range(2200)]
    rows[0:6] = [
        ("2020", "", "empty"),
        ("2020", None, "NULL"),
        ("2020", "001.2300", 'literal "\t\nКириллица  '),
        ("2021", " 0 ", "space"),
        ("2021", "duplicate", "same"),
        ("2021", "duplicate", "same"),
    ]
    spec = {"sample": {"columns": fields, "rows": len(rows), "dates": ["2020", "2021"]}}
    live = sql.Identifier("primary", "sample")

    # Читает целевую тестовую таблицу с учётом числа повторяющихся строк.
    def read():
        with psycopg.connect(**dst) as conn:
            return Counter(
                conn.execute(sql.SQL("SELECT * FROM {}").format(live)).fetchall()
            )

    # Вызывает общий перенос с подготовленными тестовыми подключениями и описанием
    # таблицы.
    def run(**kwargs):
        return transport.transfer(
            src, dst, spec, batch_size=1100, copy_batch=copy_batch, **kwargs
        )

    # Проверяет, что опасная операция завершается ожидаемой ошибкой.
    def fails(operation, message):
        try:
            operation()
        except (ValueError, RuntimeError) as exc:
            assert message in str(exc), str(exc)
        else:
            raise AssertionError("Expected failure: " + message)

    with psycopg.connect(**settings, autocommit=True) as admin:
        created = []
        try:
            for name in names:
                admin.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name))
                )
                created.append(name)
            for config in (src, dst):
                with psycopg.connect(**config) as conn:
                    conn.execute('CREATE SCHEMA "primary"')
                    conn.execute(
                        sql.SQL("CREATE TABLE {} ({})").format(
                            live, transport.definition(fields)
                        )
                    )
                    conn.execute('CREATE TABLE "primary".unrelated (value text)')
                    conn.execute("INSERT INTO \"primary\".unrelated VALUES ('keep')")
            with psycopg.connect(**src) as conn, conn.cursor() as cur:
                transport.plain_copy(cur, live, None, fields, rows)
            with psycopg.connect(**dst) as conn:
                conn.execute(
                    sql.SQL("INSERT INTO {} VALUES (%s,%s,%s)").format(live),
                    ("2020", "old", "keep until commit"),
                )
            original = read()
            assert run(check_only=True)["tables"]["sample"]["status"] == "different"
            assert read() == original
            print("PASS: check-only performs no writes", flush=True)

            original_sender = transport.plain_copy

            def failing_sender(*args):
                original_sender(*args)
                raise RuntimeError("injected copy failure")

            with patch.object(transport, "plain_copy", failing_sender):
                fails(run, "injected copy failure")
            assert read() == original
            print("PASS: interrupted transfer preserves the destination", flush=True)

            assert run()["tables"]["sample"]["status"] == "copied"
            assert read() == Counter(rows)
            assert run()["tables"]["sample"]["status"] == "identical"
            print(
                "PASS: all values, NULLs, blanks, duplicates, compressed pages and repeat skip",
                flush=True,
            )

            with psycopg.connect(**dst) as conn:
                conn.execute(
                    sql.SQL(
                        "UPDATE {} SET \"VALUE\"='changed' WHERE \"VALUE\"='2199'"
                    ).format(live)
                )
            assert run(check_only=True)["tables"]["sample"]["status"] == "different"
            assert run()["tables"]["sample"]["status"] == "copied"
            print("PASS: equal counts cannot hide changed values", flush=True)

            with psycopg.connect(**dst) as conn:
                conn.execute(
                    sql.SQL("INSERT INTO {} VALUES ('2020','extra','extra')").format(
                        live
                    )
                )
            fails(run, "larger destination")
            with psycopg.connect(**dst) as conn:
                conn.execute(
                    sql.SQL("DELETE FROM {} WHERE \"VALUE\"='extra'").format(live)
                )
            spec["sample"]["rows"] += 1
            fails(run, "local counts or periods")
            spec["sample"]["rows"] -= 1
            fails(lambda: transport.transfer(src, src, spec), "different databases")
            fails(
                lambda: transport.endpoint(dict(src, host="example.org"), local=True),
                "local PostgreSQL",
            )
            print(
                "PASS: incomplete source, smaller replacement, same DB and remote source refused",
                flush=True,
            )

            with psycopg.connect(**dst) as conn:
                conn.execute(
                    sql.SQL(
                        "UPDATE {} SET \"VALUE\"='before rollback' WHERE \"VALUE\"='2199'"
                    ).format(live)
                )
            before = read()
            original_fingerprint = transport.fingerprint
            calls = 0

            def failed_final(conn, relation, fields):
                nonlocal calls
                actual = original_fingerprint(conn, relation, fields)
                if conn.info.dbname == dst["dbname"] and relation == live:
                    calls += 1
                    if calls == 2:
                        raise RuntimeError("injected final failure")
                return actual

            with patch.object(transport, "fingerprint", failed_final):
                fails(run, "injected final failure")
            assert read() == before
            print("PASS: final validation failure rolls back publication", flush=True)

            previous = [
                "DATE",
                "IUMABEDR",
                "CFMBJ95",
                "IUMBV34",
                "LPMVTVU",
                "LPMVTVX",
                "LPMB3C2",
                "LPMB4B5",
            ]
            spec["sample"]["previous_columns"] = previous
            with psycopg.connect(**dst) as conn:
                conn.execute(sql.SQL("DROP TABLE {}").format(live))
                conn.execute(
                    sql.SQL("CREATE TABLE {} ({})").format(
                        live, transport.definition(previous)
                    )
                )
                conn.execute(
                    sql.SQL("INSERT INTO {} (\"DATE\") VALUES ('2000')").format(live)
                )

            def failed_migration(conn, relation, fields):
                if conn.info.dbname == dst["dbname"] and relation == live:
                    raise RuntimeError("injected migration failure")
                return original_fingerprint(conn, relation, fields)

            with patch.object(transport, "fingerprint", failed_migration):
                fails(run, "injected migration failure")
            with psycopg.connect(**dst) as conn:
                assert transport.columns(conn, "sample") == [
                    (field, "text") for field in previous
                ]
                assert conn.execute(
                    sql.SQL('SELECT "DATE" FROM {}').format(live)
                ).fetchall() == [("2000",)]
            print(
                "PASS: failed migration restores the old table structure and data",
                flush=True,
            )
            assert run()["tables"]["sample"]["status"] == "copied"
            assert read() == Counter(rows)
            with psycopg.connect(**dst) as conn:
                assert conn.execute('SELECT * FROM "primary".unrelated').fetchall() == [
                    ("keep",)
                ]
                assert conn.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname='primary' ORDER BY tablename"
                ).fetchall() == [("sample",), ("unrelated",)]
            print(
                "PASS: known old schema migrated; no backup tables; unrelated data preserved",
                flush=True,
            )
        finally:
            for name in reversed(created):
                admin.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                        sql.Identifier(name)
                    )
                )
    print("PASS: direct database transfer integration checks complete", flush=True)


if __name__ == "__main__":
    main()
