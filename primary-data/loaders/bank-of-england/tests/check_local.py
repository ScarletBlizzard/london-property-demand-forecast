# Проверки BoE с настоящим локальным PostgreSQL. По умолчанию скрипт создаёт отдельную
# тестовую БД и проверяет загрузку, повторный запуск, переход со старой структуры и
# откат при ошибке. После проверки тестовая БД удаляется.
#
# Есть и режим --verify-existing: он только читает выбранную локальную таблицу и сверяет
# её с сохранёнными CSV по числу строк и контрольным суммам. Скрипт не разрешает
# подключение к удалённому серверу.

import argparse
import hashlib
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_loader import loader, make_snapshot, support


# Считает число строк и сумму хешей отдельно для каждого ряда, учитывая повторы.
def fingerprint(rows):
    result = {}
    modulus = 1 << 256
    for row in rows:
        encoded = json.dumps(
            list(row), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        digest = int.from_bytes(hashlib.sha256(encoded).digest(), "big")
        count, total = result.get(row[1], (0, 0))
        result[row[1]] = (count + 1, (total + digest) % modulus)
    return result


# Сравнивает все CSV-строки с таблицей по контрольным суммам и проверяет её столбцы.
def verify(conn, folder, manifest):
    expected = fingerprint(
        row
        for part in manifest["parts"]
        for row in loader.csv_rows((folder / part["file"]).read_bytes())
    )
    with conn.cursor(name="verify_boe") as cur:
        cur.itersize = 10000
        cur.execute(
            'SELECT "DATE","SERIES","VALUE" FROM "primary".bank_of_england__raw'
        )
        actual = fingerprint(cur)
    if actual != expected:
        raise AssertionError("Source and database counts or multiset checksums differ")
    columns = conn.execute(
        "SELECT column_name,data_type FROM information_schema.columns "
        "WHERE table_schema='primary' AND table_name='bank_of_england__raw' "
        "ORDER BY ordinal_position"
    ).fetchall()
    assert columns == [(name, "text") for name in loader.COLUMNS]
    print(
        f"PASS: all {sum(value[0] for value in actual.values())} rows match source CSV by per-series count and SHA-256 multiset checksum",
        flush=True,
    )


# Выбирает сверку существующей таблицы или проверки с записью в отдельной тестовой БД.
def main():
    parser = argparse.ArgumentParser(
        description="Local PostgreSQL migration/rollback checks and complete source-to-table verification."
    )
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument(
        "--verify-existing",
        action="store_true",
        help="Read-only comparison with the selected LOCAL database",
    )
    args = parser.parse_args()
    settings = support.connection_settings(args.env_file)
    if settings["host"] not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Checks may only use localhost")
    settings["hostaddr"] = "::1" if settings["host"] == "::1" else "127.0.0.1"
    if args.verify_existing:
        if not args.snapshot:
            parser.error("--verify-existing requires --snapshot")
        manifest = support.read_snapshot(args.snapshot, "bank-of-england")
        loader.validate_snapshot(args.snapshot, manifest)
        with psycopg.connect(**settings) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            verify(conn, args.snapshot, manifest)
        return

    target = "loader_test_" + uuid4().hex[:12]
    with psycopg.connect(**dict(settings, dbname="postgres"), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
        try:
            # Подменяет подключение загрузчика, направляя запись только в созданную
            # тестовую БД.
            def connect(_, local_only=False):
                return psycopg.connect(**dict(settings, dbname=target))

            with tempfile.TemporaryDirectory(
                dir=loader.DIRECTORY / "data"
            ) as temporary:
                folder = Path(temporary)
                manifest = make_snapshot(folder)
                with connect(None) as conn:
                    conn.execute('CREATE SCHEMA "primary"')
                    fields = sql.SQL(",").join(
                        sql.SQL("{} text").format(sql.Identifier(c))
                        for c in loader.PREVIOUS_COLUMNS
                    )
                    conn.execute(
                        sql.SQL(
                            'CREATE TABLE "primary".bank_of_england__raw ({})'
                        ).format(fields)
                    )
                    conn.execute(
                        "INSERT INTO \"primary\".bank_of_england__raw VALUES ('old','1','2','3','4','5','6','7')"
                    )
                    conn.execute(
                        'CREATE TABLE "primary".other_source_test (value text)'
                    )
                    conn.execute(
                        "INSERT INTO \"primary\".other_source_test VALUES ('keep')"
                    )

                class FailInsertConnection(psycopg.Connection):
                    def execute(self, query, *params, **kwargs):
                        text = (
                            query.as_string(self)
                            if isinstance(query, sql.Composable)
                            else query
                        )
                        if text.startswith(
                            'INSERT INTO "primary"."bank_of_england__raw"'
                        ):
                            return super().execute("SELECT 1 / 0")
                        return super().execute(query, *params, **kwargs)

                def failing_connect(_, local_only=False):
                    return FailInsertConnection.connect(**dict(settings, dbname=target))

                with patch.object(loader, "connect", failing_connect):
                    try:
                        loader.replace_table(
                            args.env_file, folder, manifest, local_only=True
                        )
                    except psycopg.errors.DivisionByZero:
                        pass
                    else:
                        raise AssertionError("Expected failure after table replacement")
                with connect(None) as conn:
                    assert conn.execute(
                        'SELECT * FROM "primary".bank_of_england__raw'
                    ).fetchall() == [("old", "1", "2", "3", "4", "5", "6", "7")]

                with patch.object(loader, "connect", connect):
                    loader.replace_table(
                        args.env_file, folder, manifest, local_only=True
                    )
                    loader.replace_table(
                        args.env_file, folder, manifest, local_only=True
                    )
                    with connect(None) as conn:
                        verify(conn, folder, manifest)
                        expected_rows = list(
                            loader.csv_rows((folder / "observations.csv").read_bytes())
                        )
                        assert Counter(
                            conn.execute(
                                'SELECT * FROM "primary".bank_of_england__raw'
                            ).fetchall()
                        ) == Counter(expected_rows)
                        assert conn.execute(
                            "SELECT tablename FROM pg_tables WHERE schemaname='primary' AND tablename LIKE 'bank_of_england%' ORDER BY tablename"
                        ).fetchall() == [("bank_of_england__raw",)]
                        assert conn.execute(
                            'SELECT * FROM "primary".other_source_test'
                        ).fetchall() == [("keep",)]

                    def corrupt(_):
                        yield ("31 Jan 2023", "A", "\x00")

                    with patch.object(loader, "csv_rows", corrupt):
                        try:
                            loader.replace_table(
                                args.env_file, folder, manifest, local_only=True
                            )
                        except psycopg.Error, ValueError:
                            pass
                        else:
                            raise AssertionError("Expected COPY failure")
                    with connect(None) as conn:
                        verify(conn, folder, manifest)
                print(
                    "PASS: single BoE table, migration rollback, repeated load, exact text/duplicates, source isolation, rollback on COPY failure"
                )
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(target)))
            print("Removed disposable local database:", target)


if __name__ == "__main__":
    main()
