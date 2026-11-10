"""Чтение готовых CSV/TSV и запись исходных полей в PostgreSQL."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path


def arguments(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--snapshot",
        type=Path,
        required=True,
        help="Folder with CSV/TSV pages and manifest.json",
    )
    parser.add_argument(
        "--db-workers",
        type=int,
        default=4,
        choices=range(1, 5),
        help="PostgreSQL upload connections (default: 4)",
    )
    parser.add_argument(
        "--allow-smaller-replacement",
        action="store_true",
        help="Allow replacing existing tables with fewer rows or dates",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Literal PG*=value file; overrides PG* environment variables",
    )
    return parser.parse_args()


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

    rows = [tuple(row) for row in reader if row]
    if (not rows and not allow_empty) or any(len(row) != len(columns) for row in rows):
        raise ValueError("Empty or incomplete CSV")
    return columns, rows


def read_tsv(raw, required, allow_empty=False):

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
    except (Exception, KeyboardInterrupt) as exc:
        import sys

        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
