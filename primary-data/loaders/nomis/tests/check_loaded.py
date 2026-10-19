"""Read-only verification of the loaded Nomis snapshot and its full dimension coverage."""

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _nomis_download import BOROUGHS
from test_loader import _support, loader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Restrict verification to loopback PostgreSQL",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Save this verification separately from other database reports",
    )
    args = parser.parse_args()
    manifest = _support.read_snapshot(args.snapshot, "nomis")
    tables = loader.raw_tables(args.snapshot, manifest)
    report = {"checked_at_utc": datetime.now(UTC).isoformat(), "datasets": {}}
    settings = _support.connection_settings(args.env_file)
    if args.local_only:
        if settings["host"] not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("--local-only refuses a non-local PostgreSQL host")
        settings["hostaddr"] = "::1" if settings["host"] == "::1" else "127.0.0.1"
    report["local_only"] = args.local_only
    with psycopg.connect(
        **settings,
        connect_timeout=10,
        options="-c default_transaction_read_only=on -c statement_timeout=600000",
    ) as conn:
        for dataset, config in manifest["datasets"].items():
            table = loader.TABLE_NAMES[dataset]
            target = sql.Identifier("primary", table)
            columns, source_rows = tables[table]
            actual_columns = conn.execute(
                "SELECT column_name,data_type FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
                ("primary", table),
            ).fetchall()
            assert actual_columns == [(name, "text") for name in columns], (
                table,
                "column names or types differ",
            )
            dimensions = {"DATE": source_rows.dates, "GEOGRAPHY_CODE": BOROUGHS}
            dimensions.update(
                {
                    name.upper(): {str(value) for value in values}
                    for name, values in config.get(
                        "categories", config.get("filters", {})
                    ).items()
                }
            )
            fields = sql.SQL(", ").join(map(sql.Identifier, dimensions))
            groups = sql.SQL(", ").join(
                sql.SQL("({})").format(sql.Identifier(name)) for name in dimensions
            )
            # Hash the small category sets in one scan instead of sorting tens of
            # millions of repeated strings separately for every DISTINCT aggregate.
            query = sql.SQL(
                "SELECT GROUPING({}), {}, count(*), "
                "count(*) FILTER (WHERE \"OBS_VALUE\" <> '') FROM {} "
                "GROUP BY GROUPING SETS ((), {})"
            ).format(fields, fields, target, groups)
            full_mask = (1 << len(dimensions)) - 1
            masks = {
                full_mask ^ (1 << (len(dimensions) - index - 1)): (index, name)
                for index, name in enumerate(dimensions)
            }
            actual = {name: set() for name in dimensions}
            values = None
            for record in conn.execute(query):
                if record[0] == full_mask:
                    values = record[-2:]
                else:
                    index, name = masks[record[0]]
                    actual[name].add(record[index + 1])
            assert values is not None, (table, "missing total")
            assert values[0] == len(source_rows), (
                table,
                "row count",
                values[0],
                len(source_rows),
            )
            assert actual == dimensions, (
                table,
                "dimension coverage",
                actual,
                dimensions,
            )
            samples = {}
            # Nomis reuses some URNs across different APS variables. Page positions
            # identify the exact source record without assuming URN uniqueness.
            key_columns = [
                "DATE",
                "GEOGRAPHY_TYPECODE",
                "RECORD_COUNT",
                "RECORD_OFFSET",
            ]
            key_indices = [columns.index(name) for name in key_columns]
            for query in source_rows.queries:
                pages = query["pages"]
                for index in sorted({0, len(pages) // 2, len(pages) - 1}):
                    page = pages[index]
                    filename = page["filename"] if isinstance(page, dict) else page
                    page_columns, rows = _support.read_page(
                        args.snapshot / filename, loader.REQUIRED
                    )
                    assert page_columns == columns
                    value = columns.index("OBS_VALUE")
                    selected = [rows[0], rows[-1]]
                    for predicate in [
                        lambda r, i=value: r[i] != "",
                        lambda r, i=value: r[i] == "",
                        lambda r, i=value: r[i] == "0",
                    ]:
                        match = next((r for r in rows if predicate(r)), None)
                        if match is not None:
                            selected.append(match)
                    if "VARIABLE" in columns:
                        variable = columns.index("VARIABLE")
                        quoted = next((r for r in rows if r[variable] == "1500"), None)
                        if quoted is not None:
                            selected.append(quoted)
                    for row in selected:
                        samples[tuple(row[index] for index in key_indices)] = row
            keys = sql.SQL(", ").join(map(sql.Identifier, key_columns))
            placeholders = sql.SQL(", ").join(
                sql.SQL("({})").format(
                    sql.SQL(", ").join([sql.Placeholder()] * len(key_columns))
                )
                for _ in samples
            )
            cursor = conn.execute(
                sql.SQL("SELECT * FROM {} WHERE ({}) IN ({})").format(
                    target, keys, placeholders
                ),
                [value for key in samples for value in key],
            )
            assert [c.name for c in cursor.description] == columns
            assert Counter(cursor.fetchall()) == Counter(samples.values()), (
                table,
                "source fields differ",
            )
            report["datasets"][dataset] = {
                "table": table,
                "rows": values[0],
                "rows_with_observation_value": values[1],
                "rows_without_observation_value": values[0] - values[1],
                "dimension_cardinalities": {
                    name: len(items) for name, items in actual.items()
                },
                "exact_dimension_sets_verified": True,
                "exact_source_rows_checked": len(samples),
                "original_columns": len(columns),
            }
            print(
                f"PASS {table}: {values[0]:,} rows ({values[1]:,} with OBS_VALUE); all dates, boroughs and categories; {len(samples)} exact source records",
                flush=True,
            )
    report["total_rows"] = sum(d["rows"] for d in report["datasets"].values())
    destination = args.report or args.snapshot / "database-verification.json"
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"PASS total: {report['total_rows']:,} raw rows", flush=True)


if __name__ == "__main__":
    main()
