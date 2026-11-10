"""Загрузка готовой выгрузки Bank of England в PostgreSQL."""

import argparse
import hashlib
from pathlib import Path

from _boe_data import COLUMNS, csv_rows
from _boe_support import connect, read_snapshot, run

TABLE = "bank_of_england__raw"


def arguments():
    parser = argparse.ArgumentParser(
        description="Load saved BoE CSV files into PostgreSQL."
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        required=True,
        help="Folder with CSV files and manifest.json",
    )
    parser.add_argument(
        "--env-file", type=Path, help="Literal PG*=value connection settings"
    )
    return parser.parse_args()


def validate_snapshot(folder, manifest):
    if (
        manifest.get("source") != "bank-of-england"
        or manifest.get("format_version") != 2
        or manifest.get("status") != "complete"
    ):
        raise ValueError("A complete BoE v2 snapshot is required")
    rows, seen = 0, set()
    for part in manifest["parts"]:
        name = part["file"]
        if Path(name).name != name or name in seen or name not in manifest["files"]:
            raise ValueError("Invalid, repeated or untracked CSV part")
        seen.add(name)
        raw = (folder / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest["files"][name]["sha256"]:
            raise ValueError(f"Snapshot checksum mismatch: {name}")
        count = sum(1 for _ in csv_rows(raw))
        if count != part["rows"]:
            raise ValueError(f"CSV row count differs from manifest: {name}")
        rows += count
    if not rows or rows != manifest["total_rows"]:
        raise ValueError("Incorrect total row count")
    return rows


def replace_table(env_file, folder, manifest):
    from psycopg import sql

    expected = validate_snapshot(folder, manifest)
    with connect(env_file) as conn:
        conn.execute("SET LOCAL lock_timeout='10s'")
        conn.execute("SET LOCAL statement_timeout='120s'")
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (TABLE,))
        conn.execute(
            'CREATE TEMP TABLE boe_raw_stage ("DATE" text, "SERIES" text, "VALUE" text) ON COMMIT DROP'
        )
        with conn.cursor() as cursor:
            for part in manifest["parts"]:
                with cursor.copy(
                    'COPY boe_raw_stage ("DATE", "SERIES", "VALUE") FROM STDIN'
                ) as copy:
                    for row in csv_rows((folder / part["file"]).read_bytes()):
                        copy.write_row(row)
        actual = conn.execute("SELECT count(*) FROM boe_raw_stage").fetchone()[0]
        if actual != expected:
            raise ValueError("Incomplete staging COPY")
        conn.execute('CREATE SCHEMA IF NOT EXISTS "primary"')
        current = conn.execute(
            "SELECT column_name,data_type FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
            ("primary", TABLE),
        ).fetchall()
        target = sql.Identifier("primary", TABLE)
        if current and current != [(name, "text") for name in COLUMNS]:
            raise ValueError(
                "Existing BoE table has an unexpected schema; nothing was replaced"
            )
        conn.execute(
            sql.SQL(
                'CREATE TABLE IF NOT EXISTS {} ("DATE" text,"SERIES" text,"VALUE" text)'
            ).format(target)
        )
        conn.execute(sql.SQL("TRUNCATE TABLE {}").format(target))
        conn.execute(
            sql.SQL("INSERT INTO {} SELECT * FROM boe_raw_stage").format(target)
        )
    print(f'Loaded "primary".{TABLE}: {actual} rows, 3 original columns', flush=True)


def main():
    args = arguments()
    manifest = read_snapshot(args.snapshot, "bank-of-england")
    replace_table(args.env_file, args.snapshot, manifest)


if __name__ == "__main__":
    run(main)
