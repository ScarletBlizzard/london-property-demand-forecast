# Общий механизм переноса готовых таблиц между двумя PostgreSQL. Его вызывают отдельные
# transfer.py для BoE и Nomis; список нужных таблиц передаёт вызывающий загрузчик.
#
# Сначала проверяются локальные данные и сравниваются контрольные суммы всех полей.
# Совпадающие таблицы пропускаются, остальные копируются порциями и заменяются по одной
# транзакции на таблицу. Ошибка откатывает текущую таблицу; уже завершённые остаются.
# Запросов к API источников здесь нет.

import argparse
import ipaddress
import json
import socket
import time
from pathlib import Path

import psycopg
from psycopg import sql

SCHEMA = "primary"


# Читает параметры двух подключений, готовых выгрузок, режима сверки и файла отчёта.
def arguments(description, multiple_snapshots=False):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--source-env", type=Path, required=True, help="Local PostgreSQL PG*=value file"
    )
    parser.add_argument(
        "--target-env",
        type=Path,
        required=True,
        help="Destination PostgreSQL PG*=value file",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        required=True,
        action="append" if multiple_snapshots else "store",
        help="Complete saved snapshot used to validate local columns, counts and periods",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Compare both databases without writing",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25000,
        choices=range(1000, 100001),
        metavar="1000..100000",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Save counts, checksums and completion status as JSON",
    )
    return parser.parse_args()


# Фиксирует адрес подключения; источник должен быть локальным, без подмены из окружения.
def endpoint(settings, local=False):
    settings = dict(settings)
    host = settings["host"]
    if local and host not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("The source must be a local PostgreSQL server")
    if local:
        address = "::1" if host == "::1" else "127.0.0.1"
    else:
        try:
            address = str(ipaddress.ip_address(host))
        except ValueError:
            address = socket.getaddrinfo(
                host, settings.get("port", 5432), type=socket.SOCK_STREAM
            )[0][4][0]
    settings["hostaddr"] = address
    return settings


# Открывает соединение; при readonly читает данные из согласованного состояния без
# записи.
def connect(settings, readonly=False):
    conn = psycopg.connect(
        **settings,
        connect_timeout=15,
        application_name="raw-postgres-transfer",
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
        options="-c statement_timeout=1800000 -c lock_timeout=10000 -c client_encoding=UTF8",
    )
    conn.read_only = readonly
    if readonly:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
    return conn


# Читает имена и типы столбцов таблицы для сравнения структуры.
def columns(conn, table, schema=SCHEMA):
    return conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
        (schema, table),
    ).fetchall()


# Считает число строк и суммы SHA-256 по всем полям; порядок строк не важен, повторы
# учитываются.
def fingerprint(conn, relation, fields):
    sums = sql.SQL(", ").join(
        sql.SQL("coalesce(sum(('x' || substr(h, {}, 16))::bit(64)::bigint), 0)").format(
            sql.Literal(start)
        )
        for start in (1, 17, 33, 49)
    )
    query = sql.SQL(
        "SELECT count(*), {} FROM (SELECT encode(sha256(convert_to("
        "jsonb_build_array({})::text, 'UTF8')), 'hex') AS h FROM {} OFFSET 0) hashes"
    ).format(sums, sql.SQL(", ").join(map(sql.Identifier, fields)), relation)
    row = conn.execute(query).fetchone()
    return {"rows": row[0], "sha256_sums": [str(value) for value in row[1:]]}


# Возвращает все периоды таблицы, чтобы обнаружить потерю истории.
def dates(conn, relation):
    return {
        row[0]
        for row in conn.execute(
            sql.SQL('SELECT DISTINCT "DATE" FROM {}').format(relation)
        )
    }


# Составляет SQL-описание столбцов с исходными именами и типом text.
def definition(fields):
    return sql.SQL(", ").join(
        sql.SQL("{} text").format(sql.Identifier(field)) for field in fields
    )


# Передаёт строки обычным COPY, в том числе когда нужно сохранить SQL NULL.
def plain_copy(cur, stage, transport, fields, rows):
    with cur.copy(
        sql.SQL("COPY {} ({}) FROM STDIN").format(
            stage, sql.SQL(", ").join(map(sql.Identifier, fields))
        )
    ) as copy:
        for row in rows:
            copy.write_row(row)


# Обновляет JSON-отчёт через временный файл после очередного шага.
def save_report(path, report):
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(path)


# Сравнивает одну таблицу и при отличиях копирует, проверяет и заменяет её целиком.
def transfer_table(
    source, target, table, spec, source_check, *, check_only, batch_size, copy_batch
):
    fields = spec["columns"]
    relation = sql.Identifier(SCHEMA, table)
    expected_columns = [(field, "text") for field in fields]
    with target.transaction():
        if not check_only:
            target.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (table,))
        actual = columns(target, table)

        if actual and not check_only:
            target.execute(sql.SQL("LOCK TABLE {} IN SHARE MODE").format(relation))
            actual = columns(target, table)
        old_shape = bool(actual) and actual == [
            (field, "text") for field in spec.get("previous_columns", [])
        ]
        if actual and actual != expected_columns and not old_shape:
            raise ValueError(f"{table}: destination columns differ from the source")
        result = {"source": source_check, "columns": fields}
        print(f"{table}: comparing destination rows", flush=True)
        target_check = (
            fingerprint(target, relation, fields)
            if actual == expected_columns
            else None
        )
        result["target_before"] = target_check
        if target_check == source_check:
            result.update(status="identical", target_after=target_check)
            print(
                f"{table}: identical, skipping {source_check['rows']:,} rows",
                flush=True,
            )
            return result
        if actual:
            old_count = (
                target_check["rows"]
                if target_check
                else target.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(relation)
                ).fetchone()[0]
            )
            if old_count > source_check["rows"]:
                raise ValueError(
                    f"{table}: refusing to replace a larger destination table"
                )
            if not old_shape and not dates(target, relation) <= set(spec["dates"]):
                raise ValueError(f"{table}: replacement would remove existing periods")
        if check_only:
            result["status"] = "different" if actual else "missing"
            print(
                f"{table}: {result['status']}; local rows {source_check['rows']:,}",
                flush=True,
            )
            return result
        stage, transport = (
            sql.Identifier("raw_transfer_stage"),
            sql.Identifier("raw_transfer_payload"),
        )
        for temporary in (stage, transport):
            target.execute(
                sql.SQL("CREATE TEMP TABLE {} ({}) ON COMMIT DROP").format(
                    temporary, definition(fields)
                )
            )
        copied, last_update = 0, time.monotonic()
        print(
            f"{table}: copying {source_check['rows']:,} rows from local PostgreSQL",
            flush=True,
        )
        with (
            source.cursor(name="raw_transfer_read") as reader,
            target.cursor() as writer,
        ):
            reader.execute(
                sql.SQL("SELECT {} FROM {}").format(
                    sql.SQL(", ").join(map(sql.Identifier, fields)), relation
                )
            )
            while batch := reader.fetchmany(batch_size):
                sender = (
                    plain_copy
                    if any(value is None for row in batch for value in row)
                    else copy_batch
                )
                sender(writer, stage, transport, fields, batch)
                copied += len(batch)
                if time.monotonic() - last_update >= 10:
                    print(
                        f"{table}: staged {copied:,}/{source_check['rows']:,}",
                        flush=True,
                    )
                    last_update = time.monotonic()
        if (
            copied != source_check["rows"]
            or fingerprint(target, stage, fields) != source_check
        ):
            raise ValueError(f"{table}: staging checksum differs; rolling back")
        target.execute('CREATE SCHEMA IF NOT EXISTS "primary"')
        if old_shape:
            target.execute(sql.SQL("DROP TABLE {}").format(relation))
            actual = []
        if not actual:
            target.execute(
                sql.SQL("CREATE TABLE {} ({})").format(relation, definition(fields))
            )
        target.execute(sql.SQL("TRUNCATE TABLE {}").format(relation))
        target.execute(
            sql.SQL("INSERT INTO {} SELECT * FROM {}").format(relation, stage)
        )
        after = fingerprint(target, relation, fields)
        if after != source_check:
            raise ValueError(f"{table}: final checksum differs; rolling back")
        result.update(status="copied", target_after=after)
    print(f"{table}: committed and verified {source_check['rows']:,} rows", flush=True)
    return result


# Проверяет обе БД и все исходные таблицы, затем выполняет перенос и сохраняет его
# результат.
def transfer(
    source_settings,
    target_settings,
    tables,
    *,
    check_only=False,
    batch_size=25000,
    report_path=None,
    copy_batch=plain_copy,
):
    if not tables or any(spec["rows"] <= 0 for spec in tables.values()):
        raise ValueError("A nonempty complete source snapshot is required")
    source_settings = endpoint(source_settings, local=True)
    target_settings = endpoint(target_settings)
    if (
        source_settings["hostaddr"],
        str(source_settings.get("port", 5432)),
        source_settings["dbname"],
    ) == (
        target_settings["hostaddr"],
        str(target_settings.get("port", 5432)),
        target_settings["dbname"],
    ):
        raise ValueError("Source and destination must be different databases")
    report = {
        "format_version": 1,
        "status": "running",
        "check_only": check_only,
        "schema": SCHEMA,
        "checksum": "count and four exact sums of signed 64-bit SHA-256 parts over UTF-8 JSON arrays",
        "tables": {},
    }
    try:
        with connect(source_settings, readonly=True) as source:
            checks = {}

            for table, spec in tables.items():
                if columns(source, table) != [
                    (field, "text") for field in spec["columns"]
                ]:
                    raise ValueError(
                        f"{table}: local columns differ from the complete snapshot"
                    )
                relation = sql.Identifier(SCHEMA, table)
                print(f"{table}: checking all local rows", flush=True)
                checks[table] = fingerprint(source, relation, spec["columns"])
                if checks[table]["rows"] != spec["rows"] or dates(
                    source, relation
                ) != set(spec["dates"]):
                    raise ValueError(
                        f"{table}: local counts or periods differ from the complete snapshot"
                    )
                report["tables"][table] = {
                    "source": checks[table],
                    "status": "local_verified",
                }
                save_report(report_path, report)
            with connect(target_settings, readonly=check_only) as target:
                identity_sql = "SELECT current_database(), inet_server_addr()::text, inet_server_port()"
                if (
                    source.execute(identity_sql).fetchone()
                    == target.execute(identity_sql).fetchone()
                ):
                    raise ValueError("Source and destination are the same database")
                target.rollback()
                for table, spec in tables.items():
                    report["tables"][table] = transfer_table(
                        source,
                        target,
                        table,
                        spec,
                        checks[table],
                        check_only=check_only,
                        batch_size=batch_size,
                        copy_batch=copy_batch,
                    )
                    save_report(report_path, report)
        report["status"] = "checked" if check_only else "complete"
    except (Exception, KeyboardInterrupt) as exc:
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
        raise
    finally:
        save_report(report_path, report)
    return report
