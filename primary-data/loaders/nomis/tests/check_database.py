"""Exercise the loader in a newly created isolated schema; never write primary."""

import argparse
import contextlib
import io
import sys
from collections import Counter
from itertools import islice
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_loader import _support, loader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument(
        "--sample-rows",
        type=int,
        default=137,
        help="Rows per source, up to one 25,000-row page",
    )
    args = parser.parse_args()
    if not 1 <= args.sample_rows <= 25000:
        parser.error("--sample-rows must be between 1 and 25000")
    settings = _support.connection_settings(args.env_file)
    original = loader.raw_tables(
        args.snapshot, _support.read_snapshot(args.snapshot, "nomis")
    )
    tables = {
        name: (columns, list(islice(rows, args.sample_rows)))
        for name, (columns, rows) in original.items()
    }
    schema = "nomis_test_" + uuid4().hex

    def write(data, **options):
        with contextlib.redirect_stdout(io.StringIO()):
            _support.replace_tables(args.env_file, data, schema=schema, **options)

    def check(data):
        with psycopg.connect(**settings, connect_timeout=10) as conn:
            for name, (columns, rows) in data.items():
                cursor = conn.execute(
                    sql.SQL("SELECT * FROM {}").format(sql.Identifier(schema, name))
                )
                assert [column.name for column in cursor.description] == columns
                assert Counter(cursor.fetchall()) == Counter(rows), name

    with psycopg.connect(**settings, connect_timeout=10, autocommit=True) as admin:
        # CREATE without IF NOT EXISTS proves this exact schema belongs to this run.
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            other = {"unrelated": (["VALUE"], [("keep",)])}
            write(other)
            write(tables)
            check(tables)
            write(tables)
            check(tables)
            check(other)
            edges = {
                "edge_cases": (
                    ["TEXT", "VALUE"],
                    [
                        ("a", ""),
                        ("a", ""),
                        ("b", "001.2300"),
                        ("c", "0"),
                        ("d", ".."),
                        ('student" ', " 0 "),
                    ],
                )
            }
            write(edges)
            check(edges)
            # Exercise constant, dictionary and literal payloads together, plus an all-constant page.
            labels = [
                "",
                'literal " quote  ',
                "tab\tand\nnewline",
                "Кириллица и пробел  ",
            ]
            transport_cases = {
                "transport_cases": (
                    ["CONSTANT", "LABEL", "LITERAL"],
                    [
                        (" 001.2300 ", labels[i % len(labels)], f"unique-{i:08d}")
                        for i in range(2048)
                    ],
                ),
                "identical_rows": (["CONSTANT", "EMPTY"], [('student" ', "")] * 1024),
            }
            write(transport_cases)
            check(transport_cases)
            first = min(tables)
            smaller = {first: (tables[first][0], tables[first][1][:-1])}
            try:
                write(smaller)
            except ValueError as exc:
                assert "smaller replacement" in str(exc)
            else:
                raise AssertionError("Smaller replacement was not rejected")
            check(tables)
            columns, rows = tables[first]
            date_index = columns.index("DATE")
            shifted = []
            for row in rows + [rows[0]]:
                values = list(row)
                values[date_index] = "2099"
                shifted.append(tuple(values))
            try:
                write({first: (columns, shifted)})
            except ValueError as exc:
                assert "remove existing periods" in str(exc)
            else:
                raise AssertionError("Lost periods were not rejected")
            bad = {
                name: (cols, list(values)) for name, (cols, values) in tables.items()
            }
            last = max(bad)
            corrupt = list(bad[last][1][0])
            corrupt[0] = "\x00"
            bad[last][1][0] = tuple(corrupt)
            try:
                write(bad, allow_smaller=True)
            except psycopg.Error, ValueError:
                pass
            else:
                raise AssertionError("Expected COPY failure")
            check(tables)
            check(other)
            # Fail after some live test tables have already been replaced, not just during staging.
            function = sql.Identifier(schema, "skip_insert")
            admin.execute(
                sql.SQL(
                    "CREATE FUNCTION {}() RETURNS trigger LANGUAGE plpgsql AS "
                    "$$ BEGIN RETURN NULL; END $$"
                ).format(function)
            )
            admin.execute(
                sql.SQL(
                    "CREATE TRIGGER skip_insert BEFORE INSERT ON {} "
                    "FOR EACH ROW EXECUTE FUNCTION {}()"
                ).format(sql.Identifier(schema, last), function)
            )
            changed = {
                name: (cols, list(values)) for name, (cols, values) in tables.items()
            }
            values = list(changed[first][1][0])
            values[changed[first][0].index("OBS_VALUE")] = "rollback-test-value"
            changed[first][1][0] = tuple(values)
            try:
                write(changed)
            except ValueError as exc:
                assert "Incomplete insertion" in str(exc)
            else:
                raise AssertionError("Expected live-table row-count failure")
            check(tables)
            print(
                "PASS: exact original fields, repeated loads, empty strings, literal quotes and duplicate rows"
            )
            print(
                "PASS: compact network transfer restores constants, dictionaries, literal fields and identical rows exactly"
            )
            print(
                "PASS: fewer-row and lost-period guards; staging and final-replacement rollback; source isolation"
            )
        finally:
            assert (
                schema.startswith("nomis_test_")
                and len(schema) == len("nomis_test_") + 32
            )
            admin.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )
            print("Removed isolated test schema; primary was never modified")


if __name__ == "__main__":
    main()
