"""Download files and copy CSV/TSV fields to PostgreSQL without transforming them."""

import argparse
import csv
import gzip
import hashlib
import http.client
import io
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def arguments(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--from-year", type=int)
    parser.add_argument("--to-year", type=int)
    parser.add_argument(
        "--dataset",
        action="append",
        help="Download only this configured dataset ID; repeat to select several (default: all)",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Save and validate without connecting to PostgreSQL",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="Load a previously downloaded snapshot without network requests",
    )
    parser.add_argument(
        "--resume", type=Path, help="Continue a planned or interrupted full download"
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Save metadata and exact API row counts without downloading all pages or writing to DB",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        choices=range(1, 5),
        help="Concurrent API page requests (default: 2)",
    )
    parser.add_argument(
        "--db-workers",
        type=int,
        default=4,
        choices=range(1, 5),
        help="Checkpointed PostgreSQL upload connections (default: 4)",
    )
    parser.add_argument(
        "--allow-smaller-replacement",
        action="store_true",
        help="Explicitly allow replacing existing tables with fewer rows or dates",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Literal PG*=value file; overrides PG* environment variables",
    )
    args = parser.parse_args()
    if args.snapshot and (args.resume or args.plan):
        parser.error("--snapshot cannot be combined with --resume or --plan")
    if (args.snapshot or args.resume) and args.dataset:
        parser.error(
            "--snapshot/--resume already contains the selected datasets; do not combine with --dataset"
        )
    if (args.snapshot or args.resume) and (args.from_year or args.to_year):
        parser.error(
            "--snapshot/--resume already contains the selected periods; do not combine with year filters"
        )
    if args.from_year and args.to_year and args.from_year > args.to_year:
        parser.error("--from-year must not exceed --to-year")
    for year in (args.from_year, args.to_year):
        if year is not None and not 1 <= year <= datetime.now().year:
            parser.error("Years must be between 1 and the current year")
    return args


def new_snapshot(directory, source):
    timestamp = datetime.now(UTC)
    folder = (
        directory
        / "data"
        / (timestamp.strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8])
    )
    folder.mkdir(parents=True)
    return folder, {
        "source": source,
        "downloaded_at": timestamp.isoformat(),
        "files": {},
    }


def fetch(url, folder, name, manifest):
    """Save the exact response bytes and provenance before interpreting the response."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AI-year-project/1.0 (public statistical data research)"
        },
    )
    attempts = 5
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
                metadata = {
                    "url": url,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "content_type": response.headers.get("Content-Type"),
                    "last_modified": response.headers.get("Last-Modified"),
                }
            if not raw:
                raise ValueError(f"Empty response: {url}")
            # Decompression returns the original response bytes, without changing any CSV field.
            stored = (
                gzip.compress(raw, compresslevel=1, mtime=0)
                if name.endswith(".gz")
                else raw
            )
            metadata["sha256"] = hashlib.sha256(stored).hexdigest()
            metadata["response_sha256"] = hashlib.sha256(raw).hexdigest()
            temporary = folder / (name + ".part")
            temporary.write_bytes(stored)
            temporary.replace(folder / name)
            manifest["files"][name] = metadata
            return raw
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            http.client.IncompleteRead,
            ssl.SSLError,
        ):
            if attempt == attempts - 1:
                raise
        time.sleep(2**attempt)


def save_manifest(folder, manifest):
    temporary = folder / "manifest.json.part"
    temporary.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(folder / "manifest.json")


def read_snapshot(folder, source):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest["source"] != source:
        raise ValueError(f"Expected a {source} snapshot")
    for name, metadata in manifest["files"].items():
        if Path(name).name != name:
            raise ValueError("Invalid snapshot filename")
        with (folder / name).open("rb") as stream:
            checksum = file_hash(stream)
        if checksum != metadata["sha256"]:
            raise ValueError(f"Snapshot checksum mismatch: {name}")
    return manifest


def file_hash(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def csv_bytes(path):
    return (
        gzip.decompress(path.read_bytes())
        if path.name.endswith(".gz")
        else path.read_bytes()
    )


def read_csv(raw, required, allow_empty=False):
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    columns = next(reader, [])
    if not columns or not set(required).issubset(columns):
        raise ValueError(
            f"Unexpected CSV header; expected {sorted(required)}, received {columns}"
        )
    if len(columns) != len(set(columns)) or any(
        not c or len(c.encode("utf-8")) > 63 for c in columns
    ):
        raise ValueError(
            "CSV columns must be nonempty, unique and fit PostgreSQL identifiers"
        )
    # Empty physical lines are CSV separators, not records. Empty fields stay empty strings.
    rows = [tuple(row) for row in reader if row]
    if (not rows and not allow_empty) or any(len(row) != len(columns) for row in rows):
        raise ValueError("Empty or incomplete CSV")
    return columns, rows


def read_tsv(raw, required, allow_empty=False):
    """Decode Nomis TSV's literal text wrappers, including its unescaped interior quotes.

    Nomis emits tabs between fields and wraps text in one pair of quotes, but does
    not escape interior quotes (e.g. APS variable 1500). Do not repair the response
    or use a permissive CSV parser, which would drop a literal quote from its name.
    """

    def unwrap(value):
        return (
            value[1:-1]
            if len(value) >= 2 and value.startswith('"') and value.endswith('"')
            else value
        )

    lines = raw.decode("utf-8-sig").splitlines()
    records = [
        tuple(unwrap(value) for value in line.split("\t")) for line in lines if line
    ]
    columns = list(records[0]) if records else []
    rows = records[1:]
    if not columns or not required.issubset(columns):
        raise ValueError("Unexpected Nomis TSV header")
    if len(columns) != len(set(columns)) or any(
        not c or len(c.encode("utf-8")) > 63 for c in columns
    ):
        raise ValueError("Invalid Nomis TSV columns")
    if (not rows and not allow_empty) or any(len(row) != len(columns) for row in rows):
        raise ValueError("Empty or incomplete Nomis TSV")
    return columns, rows


def read_page(path, required):
    reader = read_tsv if path.name.endswith((".tsv", ".tsv.gz")) else read_csv
    return reader(csv_bytes(path), required)


def connection_settings(env_file):
    names = {
        "PGHOST": "host",
        "PGPORT": "port",
        "PGDATABASE": "dbname",
        "PGUSER": "user",
        "PGPASSWORD": "password",
        "PGSSLMODE": "sslmode",
        "PGPASSFILE": "passfile",
    }
    settings = {key: os.environ[key] for key in names if key in os.environ}
    if env_file:
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if not separator or key.strip() not in names:
                raise ValueError(
                    "Environment file must contain literal PG*=value lines, not shell commands"
                )
            settings[key.strip()] = value
    if any(not settings.get(key) for key in ("PGHOST", "PGDATABASE", "PGUSER")):
        raise ValueError(
            "Explicit PGHOST, PGDATABASE and PGUSER are required; use --env-file or environment variables"
        )
    return {names[key]: value for key, value in settings.items()}


def connect(env_file):
    import psycopg

    settings = connection_settings(env_file)
    print(
        f"Connecting to {settings['host']}:{settings.get('port', '5432')}/{settings['dbname']} as {settings['user']}",
        flush=True,
    )
    return psycopg.connect(
        **settings, connect_timeout=10, application_name="primary-data-loader"
    )


def copy_batch(cur, stage, transport, columns, rows):
    """Transfer repeated text once per page, then restore exact fields inside PostgreSQL.

    This only encodes the network payload. The source snapshot, staging table and
    final table all retain the original text, including blanks and duplicates.
    """
    from psycopg import sql

    fields = sql.SQL(", ").join(map(sql.Identifier, columns))
    if len(rows) < 1024:
        with cur.copy(sql.SQL("COPY {} ({}) FROM STDIN").format(stage, fields)) as copy:
            for row in rows:
                copy.write_row(row)
        return
    if any(len(row) != len(columns) for row in rows):
        raise ValueError("Incomplete raw row")
    payload_columns, payload_values, expressions, parameters = [], [], [], []
    for column, values in zip(columns, zip(*rows)):
        field = sql.Identifier(column)
        unique = list(dict.fromkeys(values))
        if len(unique) == 1:
            expressions.append(sql.SQL("%s::text"))
            parameters.append(unique[0])
            continue
        dictionary = json.dumps(unique, ensure_ascii=False, separators=(",", ":"))
        # Avoid dictionaries for unique identifiers, offsets and small values.
        encoded_size = len(dictionary) + len(rows) * (len(str(len(unique))) + 1)
        original_size = sum(len(value) + 1 for value in values)
        if encoded_size < original_size * 0.75:
            indices = {value: str(index) for index, value in enumerate(unique)}
            payload_values.append([indices[value] for value in values])
            expressions.append(sql.SQL("(%s::jsonb ->> {}::integer)").format(field))
            parameters.append(dictionary)
        else:
            payload_values.append(values)
            expressions.append(field)
        payload_columns.append(field)
    if not payload_columns:
        # A page of identical records must still retain every duplicate.
        cur.execute(
            sql.SQL("INSERT INTO {} ({}) SELECT {} FROM generate_series(1, %s)").format(
                stage, fields, sql.SQL(", ").join(expressions)
            ),
            parameters + [len(rows)],
        )
    else:
        cur.execute(sql.SQL("TRUNCATE TABLE {}").format(transport))
        with cur.copy(
            sql.SQL("COPY {} ({}) FROM STDIN").format(
                transport, sql.SQL(", ").join(payload_columns)
            )
        ) as copy:
            for row in zip(*payload_values):
                copy.write_row(row)
        cur.execute(
            sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(
                stage, fields, sql.SQL(", ").join(expressions), transport
            ),
            parameters,
        )
    if cur.rowcount != len(rows):
        raise ValueError("Incomplete transport decoding; rolling back all tables")


def replace_tables(env_file, tables, allow_smaller=False, schema="primary"):
    """Replace this source's tables with the exact CSV fields, all stored as TEXT."""
    from psycopg import sql

    if not tables or any(not rows for columns, rows in tables.values()):
        raise ValueError("Refusing to load empty CSV files")
    with connect(env_file) as conn, conn.cursor() as cur:
        cur.execute("SET LOCAL lock_timeout = '10s'")
        cur.execute("SET LOCAL statement_timeout = '120s'")
        cur.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema))
        )
        staged = []
        for index, table in enumerate(sorted(tables)):
            columns, rows = tables[table]
            lock_key = table if schema == "primary" else schema + "." + table
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (lock_key,))
            target = sql.Identifier(schema, table)
            definition = sql.SQL(", ").join(
                sql.SQL("{} text").format(sql.Identifier(c)) for c in columns
            )
            cur.execute(
                sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(target, definition)
            )
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
                (schema, table),
            )
            if cur.fetchall() != [(c, "text") for c in columns]:
                raise ValueError(
                    f"{table}: existing table does not match the raw CSV columns"
                )
            if not allow_smaller:
                cur.execute(sql.SQL("SELECT count(*) FROM {}").format(target))
                if cur.fetchone()[0] > len(rows):
                    raise ValueError(
                        f"{table}: refusing a smaller replacement; use --allow-smaller-replacement only intentionally"
                    )
                if "DATE" in columns:
                    dates = (
                        rows.dates
                        if hasattr(rows, "dates")
                        else {r[columns.index("DATE")] for r in rows}
                    )
                    cur.execute(
                        sql.SQL('SELECT DISTINCT "DATE" FROM {}').format(target)
                    )
                    if any(date not in dates for (date,) in cur.fetchall()):
                        raise ValueError(
                            f"{table}: replacement would remove existing periods; use --allow-smaller-replacement only intentionally"
                        )
            stage = sql.Identifier(f"nomis_stage_{index}")
            cur.execute(
                sql.SQL("CREATE TEMP TABLE {} ({}) ON COMMIT DROP").format(
                    stage, definition
                )
            )
            transport = sql.Identifier(f"nomis_transport_{index}")
            cur.execute(
                sql.SQL("CREATE TEMP TABLE {} ({}) ON COMMIT DROP").format(
                    transport, definition
                )
            )
            fields = sql.SQL(", ").join(map(sql.Identifier, columns))
            batches = rows.batches() if hasattr(rows, "batches") else [rows]
            copied = 0
            for batch in batches:
                copy_batch(cur, stage, transport, columns, batch)
                copied += len(batch)
                if hasattr(rows, "batches"):
                    print(f"Staged {table}: {copied:,}/{len(rows):,}", flush=True)
            cur.execute(sql.SQL("SELECT count(*) FROM {}").format(stage))
            if cur.fetchone()[0] != len(rows):
                raise ValueError(f"{table}: incomplete COPY")
            staged.append((target, stage, fields, len(rows)))
        # Live data stays readable while pages are copied and validated.
        cur.execute("SET LOCAL statement_timeout = '1800s'")
        for target, stage, fields, expected in staged:
            cur.execute(sql.SQL("TRUNCATE TABLE {}").format(target))
            cur.execute(
                sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(
                    target, fields, fields, stage
                )
            )
            if cur.rowcount != expected:
                raise ValueError(
                    "Incomplete insertion into a live Nomis table; rolling back all tables"
                )
    for table, (columns, rows) in tables.items():
        print(
            f"Loaded {table}: {len(rows)} rows, {len(columns)} original columns",
            flush=True,
        )


def run(main):
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:  # noqa: BLE001 - CLI boundary reports errors and exits.
        # Connection errors can include server/user names, but never print the config or DSN.
        import sys

        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
