# Полная выгрузка Nomis большая, и передача в БД может оборваться. Этот модуль сохраняет
# каждую принятую страницу вместе с отметкой о завершении. Для этого в PostgreSQL
# создаётся отдельная служебная схема.
#
# При повторном запуске подтверждённые страницы пропускаются. Когда все данные на месте,
# выбранные таблицы в primary заменяются одной транзакцией. При ошибке прежние таблицы
# остаются, а сохранённые страницы можно использовать для следующей попытки. После
# успеха служебная схема удаляется.

import gzip
import hashlib
import json
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path

import psycopg
from _nomis_data import REQUIRED, TABLE_NAMES, check_page
from _nomis_support import connection_settings, copy_batch, read_csv, read_tsv
from psycopg import sql

NETWORK_ERRORS = (psycopg.OperationalError, psycopg.InterfaceError)


# Отличает сбой соединения, который можно повторить, от ошибки самого SQL или данных.
def _network_error(exc):
    if isinstance(exc, psycopg.InterfaceError):
        return True
    return isinstance(exc, psycopg.OperationalError) and (
        exc.sqlstate is None
        or exc.sqlstate.startswith("08")
        or exc.sqlstate in {"57P01", "57P02", "57P03"}
    )


# Описывает один файл страницы: набор, запрос, позицию, число строк и контрольную сумму.
@dataclass(frozen=True)
class Page:
    dataset: str
    query: str
    offset: int
    rows: int
    total: int
    filename: str
    checksum: str

    # Возвращает ключ страницы, по которому проверяется, была ли она уже записана.
    @property
    def key(self):
        return self.dataset, self.query, self.offset


# Получает имя служебной схемы и метку её принадлежности конкретной выгрузке.
def checkpoint_identity(manifest, target_schema):
    raw = json.dumps(
        [target_schema, manifest],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    digest = hashlib.sha256(raw).hexdigest()
    return "nomis_stage_" + digest[:24], "nomis raw checkpoint v1 " + digest


# Открывает соединение для передачи страниц с ограничениями времени ожидания.
def _connect(settings):
    return psycopg.connect(
        **settings,
        autocommit=True,
        connect_timeout=10,
        application_name="nomis-checkpoint-loader",
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
        options="-c statement_timeout=180000 -c lock_timeout=30000",
    )


# Составляет SQL-описание исходных столбцов, сохраняя для каждого тип text.
def _definition(columns):
    return sql.SQL(", ").join(
        sql.SQL("{} text").format(sql.Identifier(c)) for c in columns
    )


# Читает имена и типы столбцов существующей таблицы в исходном порядке.
def _columns(cur, schema, table):
    cur.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
        (schema, table),
    )
    return cur.fetchall()


# Проверяет структуру таблиц и, если не разрешено обратное, запрещает потерю строк и
# периодов.
def _validate_targets(cur, tables, schema, allow_smaller):
    for table, (columns, rows) in tables.items():
        actual = _columns(cur, schema, table)
        if not actual:
            continue
        if actual != [(c, "text") for c in columns]:
            raise ValueError(f"{schema}.{table}: columns differ from the raw source")
        if not allow_smaller:
            target = sql.Identifier(schema, table)
            cur.execute(sql.SQL("SELECT count(*) FROM {}").format(target))
            if cur.fetchone()[0] > len(rows):
                raise ValueError(f"{table}: refusing a smaller replacement")
            cur.execute(sql.SQL('SELECT DISTINCT "DATE" FROM {}').format(target))
            if any(date not in rows.dates for (date,) in cur.fetchall()):
                raise ValueError(f"{table}: replacement would remove existing periods")


# Собирает список страниц полной выгрузки и проверяет, что между ними нет пропусков.
def _pages(manifest):
    if manifest.get("version") != 2 or manifest.get("status") != "complete":
        raise ValueError("Checkpointed loading requires a complete v2 snapshot")
    if not manifest["datasets"] or not set(manifest["datasets"]) <= TABLE_NAMES.keys():
        raise ValueError(
            "The snapshot must contain one or more configured Nomis datasets"
        )
    pages = []
    for dataset, config in manifest["datasets"].items():
        TABLE_NAMES[dataset]
        for query in config["queries"]:
            offset = 0
            for page in query["pages"]:
                if (
                    page["offset"] != offset
                    or page["rows"] <= 0
                    or Path(page["filename"]).name != page["filename"]
                ):
                    raise ValueError("Incomplete source page sequence")
                pages.append(
                    Page(
                        dataset,
                        query["id"],
                        offset,
                        page["rows"],
                        query["record_count"],
                        page["filename"],
                        manifest["files"][page["filename"]]["sha256"],
                    )
                )
                offset += page["rows"]
            if offset != query["record_count"]:
                raise ValueError("Incomplete source query")
    return pages


# Проверяет метку схемы, прежде чем использовать или удалять её как свою.
def _assert_owned(cur, stage, marker):
    cur.execute(
        "SELECT obj_description(oid, 'pg_namespace') FROM pg_namespace WHERE nspname=%s",
        (stage,),
    )
    if cur.fetchone() != (marker,):
        raise ValueError(
            "Checkpoint schema is not owned by this snapshot; refusing to modify it"
        )


# Создаёт или открывает служебные таблицы для строк, принятых страниц и состояния
# загрузки.
def _setup(conn, stage, marker, tables):
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("SELECT to_regnamespace(%s)", (stage,))
        if cur.fetchone()[0] is None:
            cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(stage)))
            cur.execute(
                sql.SQL("COMMENT ON SCHEMA {} IS {}").format(
                    sql.Identifier(stage), sql.Literal(marker)
                )
            )
        _assert_owned(cur, stage, marker)
        cur.execute(
            sql.SQL(
                "CREATE TABLE IF NOT EXISTS {} "
                "(dataset text, query_id text, record_offset bigint, row_count integer, checksum text, "
                "PRIMARY KEY (dataset, query_id, record_offset))"
            ).format(sql.Identifier(stage, "_pages"))
        )
        cur.execute(
            sql.SQL(
                "CREATE TABLE IF NOT EXISTS {} (id integer PRIMARY KEY CHECK (id=1), loaded boolean NOT NULL)"
            ).format(sql.Identifier(stage, "_state"))
        )
        cur.execute(
            sql.SQL("INSERT INTO {} VALUES (1, false) ON CONFLICT DO NOTHING").format(
                sql.Identifier(stage, "_state")
            )
        )
        for table, (columns, _) in tables.items():
            cur.execute(
                sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
                    sql.Identifier(stage, table), _definition(columns)
                )
            )
            if _columns(cur, stage, table) != [(c, "text") for c in columns]:
                raise ValueError("Checkpoint columns differ from the source")


# Записывает страницу и отметку о ней одной транзакцией; повтор после обрыва не
# добавляет дубли.
def _upload_page(page, context):
    if context["stop"].is_set():
        raise RuntimeError("Upload cancelled; committed checkpoints remain available")
    stored = (context["folder"] / page.filename).read_bytes()
    if hashlib.sha256(stored).hexdigest() != page.checksum:
        raise ValueError(f"Changed source file: {page.filename}")
    raw = gzip.decompress(stored) if page.filename.endswith(".gz") else stored
    reader = read_tsv if page.filename.endswith((".tsv", ".tsv.gz")) else read_csv
    columns, rows = reader(raw, REQUIRED | {"GEOGRAPHY_CODE"})
    table = TABLE_NAMES[page.dataset]
    if columns != context["tables"][table][0] or len(rows) != page.rows:
        raise ValueError("Source page columns or row count changed")
    check_page(columns, rows, page.offset, page.total)
    local = context["local"]
    for attempt in range(5):
        if context["stop"].is_set():
            raise RuntimeError(
                "Upload cancelled; committed checkpoints remain available"
            )
        try:
            if getattr(local, "conn", None) is None or local.conn.closed:
                local.conn = _connect(context["settings"])
                local.transports = set()
                with context["connections_lock"]:
                    context["connections"].append(local.conn)
            conn = local.conn
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "INSERT INTO {} VALUES (%s,%s,%s,%s,%s) "
                        "ON CONFLICT DO NOTHING RETURNING row_count"
                    ).format(sql.Identifier(context["stage"], "_pages")),
                    (*page.key, page.rows, page.checksum),
                )
                if cur.fetchone() is None:
                    cur.execute(
                        sql.SQL(
                            "SELECT row_count, checksum FROM {} WHERE dataset=%s AND query_id=%s AND record_offset=%s"
                        ).format(sql.Identifier(context["stage"], "_pages")),
                        page.key,
                    )
                    if cur.fetchone() != (page.rows, page.checksum):
                        raise ValueError("Checkpoint does not match the source page")
                    return page.rows
                transport = sql.Identifier("nomis_transfer_" + page.dataset.lower())
                if table not in local.transports:
                    cur.execute(
                        sql.SQL(
                            "CREATE TEMP TABLE {} ({}) ON COMMIT PRESERVE ROWS"
                        ).format(transport, _definition(columns))
                    )
                    local.transports.add(table)
                copy_batch(
                    cur,
                    sql.Identifier(context["stage"], table),
                    transport,
                    columns,
                    rows,
                )
            return page.rows
        except NETWORK_ERRORS as exc:
            if not _network_error(exc):
                raise
            if getattr(local, "conn", None) is not None:
                local.conn.close()
            if attempt == 4:
                raise
            print(
                f"Retrying page {page.dataset}/{page.query}/{page.offset}; committed data is preserved "
                f"({type(exc).__name__}: {(str(exc).splitlines() or [''])[0]})",
                flush=True,
            )
            time.sleep(2**attempt)


# Находит незаписанные страницы и распределяет их между подключениями к БД.
def _transfer(conn, pages, context, workers):
    stage = context["stage"]
    records = conn.execute(
        sql.SQL(
            "SELECT dataset, query_id, record_offset, row_count, checksum FROM {}"
        ).format(sql.Identifier(stage, "_pages"))
    ).fetchall()
    expected = {page.key: page for page in pages}
    done = set()
    count = 0
    for dataset, query, offset, rows, checksum in records:
        key = dataset, query, offset
        page = expected.get(key)
        if page is None or (rows, checksum) != (page.rows, page.checksum):
            raise ValueError("Checkpoint contains an unexpected page")
        done.add(key)
        count += rows
    total = sum(page.rows for page in pages)
    print(
        f"Checkpoint: {count:,}/{total:,} rows already committed; {workers} upload connections",
        flush=True,
    )
    remaining = iter(page for page in pages if page.key not in done)
    heartbeat = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = set()
        try:
            while True:
                while len(pending) < workers:
                    page = next(remaining, None)
                    if page is None:
                        break
                    pending.add(pool.submit(_upload_page, page, context))
                if not pending:
                    break
                finished, pending = wait(
                    pending, timeout=20, return_when=FIRST_COMPLETED
                )
                for future in finished:
                    count += future.result()
                    print(f"Checkpointed raw rows: {count:,}/{total:,}", flush=True)
                if time.monotonic() - heartbeat >= 20:
                    conn.execute("SELECT 1")
                    heartbeat = time.monotonic()
        except BaseException:
            context["stop"].set()
            for future in pending:
                future.cancel()
            raise


# Проверяет число подготовленных строк и заменяет все выбранные таблицы одной
# транзакцией.
def _finish(conn, stage, tables, target_schema, allow_smaller):
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout='1800s'")
        cur.execute("SET LOCAL lock_timeout='10s'")
        for table in sorted(tables):
            key = table if target_schema == "primary" else target_schema + "." + table
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (key,))
        _validate_targets(cur, tables, target_schema, allow_smaller)
        cur.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                sql.Identifier(target_schema)
            )
        )
        for table, (columns, rows) in tables.items():
            cur.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(stage, table))
            )
            if cur.fetchone()[0] != len(rows):
                raise ValueError(
                    f"{table}: incomplete checkpoint data; live tables were not replaced"
                )
            cur.execute(
                sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
                    sql.Identifier(target_schema, table), _definition(columns)
                )
            )
        print(
            f"All checkpoint counts verified; replacing {len(tables)} selected live table(s) atomically",
            flush=True,
        )
        targets = [sql.Identifier(target_schema, table) for table in sorted(tables)]
        cur.execute(sql.SQL("TRUNCATE TABLE {}").format(sql.SQL(", ").join(targets)))
        for table in sorted(tables):
            columns, rows = tables[table]
            fields = sql.SQL(", ").join(map(sql.Identifier, columns))
            cur.execute(
                sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(
                    sql.Identifier(target_schema, table),
                    fields,
                    fields,
                    sql.Identifier(stage, table),
                )
            )
            if cur.rowcount != len(rows):
                raise ValueError(
                    "Incomplete insertion into a live Nomis table; rolling back all tables"
                )
        cur.execute(
            sql.SQL("UPDATE {} SET loaded=true WHERE id=1").format(
                sql.Identifier(stage, "_state")
            )
        )


# Управляет загрузкой, продолжением после обрывов и удалением своей служебной схемы
# после успеха.
def load_snapshot(
    env_file,
    folder,
    manifest,
    tables,
    allow_smaller=False,
    workers=4,
    target_schema="primary",
):
    if not 1 <= workers <= 4:
        raise ValueError("Use between one and four database upload connections")
    pages = _pages(manifest)
    if set(tables) != {TABLE_NAMES[page.dataset] for page in pages}:
        raise ValueError("Snapshot and target tables differ")
    settings = connection_settings(env_file)
    stage, marker = checkpoint_identity(manifest, target_schema)
    completed = False
    for attempt in range(5):
        context = {
            "settings": settings,
            "folder": folder,
            "tables": tables,
            "stage": stage,
            "local": threading.local(),
            "stop": threading.Event(),
            "connections": [],
            "connections_lock": threading.Lock(),
        }
        try:
            with _connect(settings) as conn:
                if not conn.execute(
                    "SELECT pg_try_advisory_lock(hashtext(%s))", (stage,)
                ).fetchone()[0]:
                    raise ValueError(
                        "This snapshot is already being uploaded by another process"
                    )
                if not completed:
                    with conn.cursor() as cur:
                        _validate_targets(cur, tables, target_schema, allow_smaller)
                    _setup(conn, stage, marker, tables)
                    loaded = conn.execute(
                        sql.SQL("SELECT loaded FROM {} WHERE id=1").format(
                            sql.Identifier(stage, "_state")
                        )
                    ).fetchone()[0]
                    if not loaded:
                        _transfer(conn, pages, context, workers)
                        _finish(conn, stage, tables, target_schema, allow_smaller)
                    completed = True

                with conn.cursor() as cur:
                    cur.execute("SELECT to_regnamespace(%s)", (stage,))
                    if cur.fetchone()[0] is not None:
                        _assert_owned(cur, stage, marker)
                        cur.execute(
                            sql.SQL("DROP SCHEMA {} CASCADE").format(
                                sql.Identifier(stage)
                            )
                        )
            for table, (_, rows) in tables.items():
                print(f"Loaded {table}: {len(rows):,} original rows", flush=True)
            return
        except NETWORK_ERRORS as exc:
            if not _network_error(exc):
                raise
            if attempt == 4:
                raise
            print(
                f"Connection lost; resuming from committed database checkpoints "
                f"({type(exc).__name__}: {(str(exc).splitlines() or [''])[0]})",
                flush=True,
            )
            time.sleep(2**attempt)
        finally:
            for conn in context["connections"]:
                conn.close()
