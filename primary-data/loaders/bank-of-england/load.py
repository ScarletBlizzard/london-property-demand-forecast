"""Download every public BoE catalogue series as original CSV and XML."""

import argparse
import hashlib
import sys
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(DIRECTORY))
import itertools

from _boe_catalog import CatalogueHTML, discover
from _boe_data import (
    COLUMNS,
    csv_rows,
    inspect_csv,
    metadata,
    observations,
    parse_metadata,
)
from _boe_support import SnapshotStore, connect, connection_settings, read_snapshot, run

TABLE = "bank_of_england__raw"
PREVIOUS_COLUMNS = [
    "DATE",
    "IUMABEDR",
    "CFMBJ95",
    "IUMBV34",
    "LPMVTVU",
    "LPMVTVX",
    "LPMB3C2",
    "LPMB4B5",
]


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--resume", type=Path, help="Continue an interrupted all-series download"
    )
    mode.add_argument(
        "--snapshot",
        type=Path,
        help="Load a completed all-series snapshot without network access",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Download and validate without PostgreSQL",
    )
    parser.add_argument(
        "--env-file", type=Path, help="Literal PG*=value connection settings"
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Refuse any PostgreSQL host except loopback",
    )
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=2)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=150,
        help="Technical request size, 1..300; every series is included",
    )
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 300:
        parser.error("--batch-size must be between 1 and 300")
    return args


def download(args):
    store = SnapshotStore(DIRECTORY, args.resume)
    print(f"Raw files: {store.folder.resolve()}", flush=True)
    try:
        return download_into(store, args)
    finally:
        store.checkpoint()


def download_into(store, args):
    if store.manifest.get("status") == "complete":
        validate_snapshot(store.folder, store.manifest)
        return store.folder, store.manifest
    if "catalogue" not in store.manifest:
        groups = discover(store, args.workers)
        store.checkpoint(catalogue=groups, status="catalogue_complete")
    codes = sorted(
        code
        for group in store.manifest["catalogue"].values()
        for code in group["codes"]
    )
    if "series" not in store.manifest:
        series, files = metadata(store, codes, args.batch_size, args.workers)
        store.checkpoint(
            series=series, metadata_files=files, status="metadata_complete"
        )
    parts, empty = observations(
        store, store.manifest["series"], args.batch_size, args.workers
    )
    store.checkpoint(parts=parts, no_observations=empty, status="validating")
    validate_snapshot(store.folder, store.manifest, require_complete=False)
    store.checkpoint(status="complete", total_rows=sum(part["rows"] for part in parts))
    return store.folder, store.manifest


def validate_snapshot(folder, manifest, require_complete=True):
    if manifest.get("format_version") != 2 or (
        require_complete and manifest.get("status") != "complete"
    ):
        raise ValueError(
            "A completed all-series snapshot is required; use --resume for incomplete downloads"
        )
    for name, entry in manifest["files"].items():
        if (
            Path(name).name != name
            or hashlib.sha256((folder / name).read_bytes()).hexdigest()
            != entry["sha256"]
        ):
            raise ValueError(f"Snapshot checksum mismatch: {name}")
    groups = manifest["catalogue"]
    form = CatalogueHTML((folder / "catalog_form.html").read_bytes())
    if set(groups) != set(form.frequencies):
        raise ValueError("The catalogue does not cover every source frequency")
    for frequency, group in groups.items():
        source_codes = []
        for index, name in enumerate(group["files"], 1):
            page = CatalogueHTML((folder / name).read_bytes())
            number, first, last, total = page.page()
            page_codes = list(dict.fromkeys(page.codes))
            if (
                number != index
                or total != group["count"]
                or (total and first != len(source_codes) + 1)
                or len(page_codes) != (last - first + 1 if total else 0)
            ):
                raise ValueError(f"Incomplete saved catalogue pages: {frequency}")
            source_codes.extend(page_codes)
        if source_codes != group["codes"] or len(source_codes) != group["count"]:
            raise ValueError(f"Catalogue index differs from source pages: {frequency}")
    codes = [code for group in groups.values() for code in group["codes"]]
    if (
        not codes
        or len(codes) != len(set(codes))
        or any(g["count"] != len(g["codes"]) for g in groups.values())
    ):
        raise ValueError("Incomplete or repeated catalogue series")
    series = manifest["series"]
    if set(codes) != set(series):
        raise ValueError("Metadata does not cover the catalogue")
    found = {}
    for name in manifest["metadata_files"]:
        raw = (folder / name).read_bytes()
        expected = [
            el.attrib["SCODE"]
            for el in ET.fromstring(raw).iter()
            if "SCODE" in el.attrib
        ]
        if set(found).intersection(expected):
            raise ValueError("Repeated metadata series")
        found.update(parse_metadata(raw, expected))
    if found != series:
        raise ValueError("Metadata index differs from the original XML")
    empty = {code for code, item in series.items() if not item["FIRST_OBS"]}
    if set(manifest["no_observations"]) != empty:
        raise ValueError("Incorrect catalogue entries without observations")
    intervals, seen_files, rows, actual_bounds = {}, set(), 0, {}
    for part in manifest["parts"]:
        name = part["file"]
        if name in seen_files or name not in manifest["files"]:
            raise ValueError("Repeated or untracked CSV part")
        seen_files.add(name)
        start, end = date.fromisoformat(part["start"]), date.fromisoformat(part["end"])
        summary = inspect_csv((folder / name).read_bytes(), part["codes"], start, end)
        if any(summary[key] != part[key] for key in ("rows", "counts", "bounds")):
            raise ValueError(f"CSV coverage changed: {name}")
        for code in part["codes"]:
            intervals.setdefault(code, []).append((start, end))
        for code, bounds in summary["bounds"].items():
            previous = actual_bounds.get(code, bounds)
            actual_bounds[code] = [
                min(previous[0], bounds[0]),
                max(previous[1], bounds[1]),
            ]
        rows += summary["rows"]
    if set(intervals) != set(series) - empty:
        raise ValueError(
            "CSV requests do not cover every series with published history"
        )
    for code, ranges in intervals.items():
        ranges.sort()
        if any(
            left[1] + timedelta(days=1) != right[0]
            for left, right in itertools.pairwise(ranges)
        ):
            raise ValueError(f"Overlapping or incomplete download intervals: {code}")
        item = series[code]
        if actual_bounds.get(code) != [item["FIRST_OBS"], item["LAST_OBS"]]:
            raise ValueError(f"CSV observations do not cover published bounds: {code}")
        if ranges[0][0] > date.fromisoformat(item["FIRST_OBS"]) or ranges[-1][
            1
        ] < date.fromisoformat(item["LAST_OBS"]):
            raise ValueError(f"Truncated history: {code}")
    if not rows or ("total_rows" in manifest and manifest["total_rows"] != rows):
        raise ValueError("Incorrect total row count")
    return rows


def replace_table(env_file, folder, manifest, local_only=False):
    """Stage and atomically replace only this source's table, preserving raw text."""
    from psycopg import sql

    if local_only and connection_settings(env_file)["host"] not in (
        "localhost",
        "127.0.0.1",
        "::1",
    ):
        raise ValueError("--local-only refuses a non-local PostgreSQL host")
    expected = validate_snapshot(folder, manifest)
    with connect(env_file, local_only=local_only) as conn:
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
        if current == [(name, "text") for name in PREVIOUS_COLUMNS]:
            conn.execute(sql.SQL("DROP TABLE {}").format(target))
            current = []
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
    if args.snapshot:
        folder, manifest = (
            args.snapshot,
            read_snapshot(args.snapshot, "bank-of-england"),
        )
        validate_snapshot(folder, manifest)
    else:
        folder, manifest = download(args)
    print(
        f"Complete: {len(manifest['series'])} series, {manifest['total_rows']} CSV rows; "
        f"{len(manifest['no_observations'])} catalogue entries without observations",
        flush=True,
    )
    if not args.download_only:
        replace_table(args.env_file, folder, manifest, args.local_only)


if __name__ == "__main__":
    run(main)
