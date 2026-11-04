"""Шаг 6. Залить data/consolidated/*.csv в схему "primary" БД первичных данных.

Таблицы:
    "primary".mps__crime_borough  <- data/consolidated/borough_2010-04_2026-09.csv
    "primary".mps__crime_ward     <- data/consolidated/ward_2010-04_2026-09.csv
    "primary".mps__crime_lsoa     <- data/consolidated/lsoa_2010-04_2026-09.csv

Запуск из папки загрузчика:
    python3 scripts/06_load_to_postgres.py                # залить все три таблицы
    python3 scripts/06_load_to_postgres.py --only borough  # одну: borough, ward, lsoa
    python3 scripts/06_load_to_postgres.py --dry-run       # проверить файлы, без БД

Как работает:
  * Пишет только в существующую схему "primary", новых схем не создаёт.
  * Каждая таблица грузится в своей транзакции: CREATE TABLE -> COPY ->
    первичный ключ -> индекс по месяцу -> комментарии -> сверка с CSV -> COMMIT.
    При ошибке или расхождении транзакция откатывается, таблицы не остаётся.
  * Если таблица уже существует, скрипт её не трогает и пропускает.

Подключение: параметры из общего ../../db.env, переменные окружения важнее.
Пароль: из ~/.pgpass или переменной PGPASSWORD, см. ../../DB.md.
"""

import argparse
import os
import re
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # папка загрузчика
DATA = os.path.abspath(os.environ.get("DATA_DIR") or os.path.join(HERE, "data"))
CONS = os.path.join(DATA, "consolidated")
DB_ENV = os.path.join(HERE, "..", "..", "db.env")
SCHEMA = "primary"  # зарезервированное слово, в SQL пишется в кавычках
CHUNK_BYTES = 16 * 1024 * 1024

# Код в колонке source -> из какого исходного файла взята строка.
# Используется только для комментария к колонке source в БД.
SOURCES = {
    "3kv": "Borough_historical_2010-04_2024-04_3kv.csv",
    "pg2": "Borough_historical_2020-10_2024-09_pg2.csv",
    "byz": "Borough_24m_2024-10_2026-09_byz.csv",
    "11j": "Ward_historical_2010-04_2024-04_11j.csv",
    "mmy": "Ward_historical_2020-10_2024-09_mmy.csv",
    "w4e": "Ward_24m_2024-10_2026-09_w4e.csv",
    "t25": "LSOA_historical_2019-03_2024-04_t25.csv",
    "04d": "LSOA_historical_2020-10_2024-09_04d.csv",
    "7gv": "LSOA_24m_2024-10_2026-09_7gv.csv",
}

COMMON_NOTE = (
    "Длинный формат: строка на территорию, категорию, подкатегорию и месяц, "
    "нули как в источнике. На перекрывающихся месяцах взят самый свежий выпуск. "
    "Названия территорий и категорий как в источнике, без очистки и склейки. "
    "Источник: London Datastore (data.london.gov.uk), Metropolitan Police Service."
)

TABLES = {
    "borough": {
        "table": "mps__crime_borough",
        "file": "borough_2010-04_2026-09.csv",
        "columns": [
            ("borough", "text"),
            ("major_category", "text"),
            ("minor_category", "text"),
            ("month", "date"),
            ("count", "integer"),
            ("source", "text"),
        ],
        "pk": ["borough", "major_category", "minor_category", "month"],
        "comment": (
            "MPS Borough Level Crime, помесячно 2010-04..2026-09. "
            "Собрано из трёх файлов: 2010-04..2020-09 из 3kv, 2020-10..2024-09 "
            "из pg2, 2024-10..2026-09 из byz. Кроме районов есть строки аэропорта "
            "и Unknown. " + COMMON_NOTE
        ),
        "col_comments": {
            "borough": (
                "Район или подразделение полиции, как в источнике: "
                "BoroughName в 3kv, BOCU в pg2 и byz"
            ),
        },
    },
    "ward": {
        "table": "mps__crime_ward",
        "file": "ward_2010-04_2026-09.csv",
        "columns": [
            ("ward_code", "text"),
            ("ward_name", "text"),
            ("borough", "text"),
            ("major_category", "text"),
            ("minor_category", "text"),
            ("month", "date"),
            ("count", "integer"),
            ("source", "text"),
        ],
        "pk": [
            "ward_code",
            "ward_name",
            "borough",
            "major_category",
            "minor_category",
            "month",
        ],
        "comment": (
            "MPS Ward Level Crime, помесячно 2010-04..2026-09, коды вардов в "
            "современных границах. Собрано из трёх файлов: 2010-04..2020-09 из 11j, "
            "2020-10..2024-09 из mmy, 2024-10..2026-09 из w4e. В источнике один код "
            "варда может встречаться с разными написаниями названия или под разными "
            "районами, поэтому они входят в первичный ключ. Есть служебные коды N/K "
            "и NON ATHENA FORCE и старые коды E05000. " + COMMON_NOTE
        ),
        "col_comments": {"ward_code": "Код варда ONS, как в источнике"},
    },
    "lsoa": {
        "table": "mps__crime_lsoa",
        "file": "lsoa_2010-04_2026-09.csv",
        "columns": [
            ("lsoa_code", "text"),
            ("lsoa_name", "text"),
            ("borough_code", "text"),
            ("major_category", "text"),
            ("minor_category", "text"),
            ("month", "date"),
            ("count", "integer"),
            ("source", "text"),
        ],
        "pk": ["lsoa_code", "major_category", "minor_category", "month"],
        "comment": (
            "MPS LSOA Level Crime, помесячно 2010-04..2026-09. Собрано из трёх "
            "файлов: 2010-04..2020-09 из t25, 2020-10..2024-09 из 04d, "
            "2024-10..2026-09 из 7gv. " + COMMON_NOTE
        ),
        "col_comments": {
            "lsoa_code": "Код LSOA ONS, как в источнике",
            "borough_code": "Код района ONS E09, как в источнике",
        },
    },
}

MONTH_COMMENT = "Первое число месяца, к которому относятся данные"
COUNT_COMMENT = "Число зарегистрированных преступлений за месяц"
SOURCE_COMMENT = "Код исходного файла: " + "; ".join(
    f"{k} = {v}" for k, v in SOURCES.items()
)

# Последние три поля строки: month (ГГГГ-ММ), count, source. Они никогда не в кавычках.
LINE_RE = re.compile(rb",(\d{4}-\d{2}),(\d+),([0-9A-Za-z]+)\n")
LINE_REPL = rb",\1-01,\2,\3\n"  # месяц ГГГГ-ММ -> дата ГГГГ-ММ-01

# Строка db.env вида: export PGHOST=${PGHOST:-значение}
ENV_LINE = re.compile(r"^export\s+(\w+)=\$\{(\w+):-(.*)\}\s*$")


def load_db_env():
    """Подставить параметры из общего db.env так же, как `source ../../db.env`
    в bash-загрузчиках: значение из окружения важнее значения из файла."""
    with open(DB_ENV, encoding="utf-8") as f:
        for line in f:
            m = ENV_LINE.match(line.strip())
            if m and m.group(1) == m.group(2):
                os.environ.setdefault(m.group(1), m.group(3).strip('"'))


def read_blocks(path, expected_header):
    """Читает CSV блоками по целым строкам. Отдаёт (блок с исправленным месяцем,
    итоги по месяцам {месяц: [строк, сумма]}, прочитано байт)."""
    with open(path, "rb") as f:
        header = f.readline().decode("utf-8").rstrip("\r\n")
        if header != expected_header:
            raise ValueError(
                f"{path}: заголовок {header!r}, ожидался {expected_header!r}"
            )
        carry = b""
        while True:
            block = f.read(CHUNK_BYTES)
            buf = carry + block
            if not block:
                if not buf:
                    return
                part = buf if buf.endswith(b"\n") else buf + b"\n"
                carry = b""
            else:
                cut = buf.rfind(b"\n") + 1
                part, carry = buf[:cut], buf[cut:]
                if not part:
                    continue
            fixed, n = LINE_RE.subn(LINE_REPL, part)
            if n != part.count(b"\n"):
                bad = next(
                    line
                    for line in part.split(b"\n")
                    if line and not LINE_RE.search(line + b"\n")
                )
                raise ValueError(f"{path}: строка не по формату: {bad[:200]!r}")
            totals = defaultdict(lambda: [0, 0])
            for m in LINE_RE.finditer(part):
                t = totals[m.group(1).decode()]
                t[0] += 1
                t[1] += int(m.group(2))
            yield fixed, totals, f.tell()
            if not block:
                return


def fmt_size(n):
    return f"{n / 1e6:,.0f} МБ".replace(",", " ")


def spaced(text):
    """1,234,567 -> 1 234 567"""
    return text.replace(",", " ")


def dry_run(cfg):
    path = os.path.join(CONS, cfg["file"])
    header = ",".join(c for c, _ in cfg["columns"])
    size, t0 = os.path.getsize(path), time.time()
    totals = defaultdict(lambda: [0, 0])
    for _, part_totals, pos in read_blocks(path, header):
        for m, (r, s) in part_totals.items():
            totals[m][0] += r
            totals[m][1] += s
        print(f"\r  прочитано {pos * 100 // size:3d}%", end="", flush=True)
    rows = sum(r for r, _ in totals.values())
    total = sum(s for _, s in totals.values())
    months = sorted(totals)
    print(
        spaced(
            f"\r  OK: {rows:,} строк, месяцев {len(months)} "
            f"({months[0]}..{months[-1]}), сумма {total:,}, {time.time() - t0:.0f} с"
        )
    )


def load(conn, cfg):
    from psycopg import sql

    S, T = sql.Identifier(SCHEMA), sql.Identifier(cfg["table"])
    full = f'"{SCHEMA}".{cfg["table"]}'
    path = os.path.join(CONS, cfg["file"])
    header = ",".join(c for c, _ in cfg["columns"])

    if conn.execute("select to_regclass(%s)", [full]).fetchone()[0] is not None:
        print(f"  {full} уже существует, пропускаю. Ничего не меняю.")
        return None

    size, t0 = os.path.getsize(path), time.time()
    expected = defaultdict(lambda: [0, 0])
    with conn.transaction():
        cols_sql = sql.SQL(", ").join(
            sql.SQL("{} {} NOT NULL").format(sql.Identifier(c), sql.SQL(t))
            for c, t in cfg["columns"]
        )
        conn.execute(sql.SQL("CREATE TABLE {}.{} ({})").format(S, T, cols_sql))

        col_list = sql.SQL(", ").join(sql.Identifier(c) for c, _ in cfg["columns"])
        copy_sql = sql.SQL("COPY {}.{} ({}) FROM STDIN (FORMAT csv)").format(
            S, T, col_list
        )
        with conn.cursor() as cur, cur.copy(copy_sql) as cp:
            for fixed, part_totals, pos in read_blocks(path, header):
                cp.write(fixed)
                for m, (r, s) in part_totals.items():
                    expected[m][0] += r
                    expected[m][1] += s
                el = time.time() - t0
                speed = pos / 1e6 / max(el, 1e-9)
                print(
                    f"\r  COPY {pos * 100 // size:3d}%  {fmt_size(pos)} из "
                    f"{fmt_size(size)}  {speed:.1f} МБ/с  {el:.0f} с   ",
                    end="",
                    flush=True,
                )
        print()

        print("  строю первичный ключ и индекс...", flush=True)
        pk_cols = sql.SQL(", ").join(sql.Identifier(c) for c in cfg["pk"])
        conn.execute(
            sql.SQL("ALTER TABLE {}.{} ADD CONSTRAINT {} PRIMARY KEY ({})").format(
                S, T, sql.Identifier(cfg["table"] + "_pkey"), pk_cols
            )
        )
        conn.execute(
            sql.SQL("CREATE INDEX {} ON {}.{} (month)").format(
                sql.Identifier(cfg["table"] + "_month_idx"), S, T
            )
        )

        conn.execute(
            sql.SQL("COMMENT ON TABLE {}.{} IS {}").format(
                S, T, sql.Literal(cfg["comment"])
            )
        )
        col_comments = {
            "month": MONTH_COMMENT,
            "count": COUNT_COMMENT,
            "source": SOURCE_COMMENT,
            **cfg["col_comments"],
        }
        for col, text in col_comments.items():
            conn.execute(
                sql.SQL("COMMENT ON COLUMN {}.{}.{} IS {}").format(
                    S, T, sql.Identifier(col), sql.Literal(text)
                )
            )

        print("  сверяю базу с CSV...", flush=True)
        check_sql = sql.SQL(
            "SELECT to_char(month, 'YYYY-MM'), count(*), sum(count) "
            "FROM {}.{} GROUP BY 1"
        ).format(S, T)
        got = {m: [r, s] for m, r, s in conn.execute(check_sql)}
        problems = [
            m
            for m in sorted(set(expected) | set(got))
            if expected.get(m) != got.get(m)
        ]
        if problems:
            for m in problems[:10]:
                print(f"    {m}: CSV строк/сумма={expected.get(m)}, база={got.get(m)}")
            raise RuntimeError(
                f"{full}: расхождение с CSV в {len(problems)} месяцах, откатываю"
            )
        # выход из блока transaction() = COMMIT

    conn.execute(sql.SQL("ANALYZE {}.{}").format(S, T))
    rows = sum(r for r, _ in expected.values())
    total = sum(s for _, s in expected.values())
    months = sorted(expected)
    tbl_size = conn.execute(
        "select pg_size_pretty(pg_total_relation_size(%s::regclass))", [full]
    ).fetchone()[0]
    print(
        spaced(
            f"  ГОТОВО: {rows:,} строк, {len(months)} месяцев "
            f"{months[0]}..{months[-1]}, сумма {total:,}, размер в базе {tbl_size}, "
            f"{time.time() - t0:.0f} с"
        )
    )
    return rows, total, len(months), tbl_size


def main():
    ap = argparse.ArgumentParser(description="Заливка consolidated CSV в PostgreSQL")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="только проверить файлы, без подключения к БД",
    )
    ap.add_argument("--only", choices=list(TABLES), help="залить только одну таблицу")
    args = ap.parse_args()
    todo = {args.only: TABLES[args.only]} if args.only else TABLES

    if args.dry_run:
        for key, cfg in todo.items():
            print(f"[{key}] {cfg['file']}")
            dry_run(cfg)
        return

    try:
        import psycopg
    except ImportError:
        sys.exit("Нет драйвера psycopg: python3 -m pip install 'psycopg[binary]'")

    load_db_env()
    try:
        conn = psycopg.connect(
            os.environ.get("PGCONN", ""), application_name="mps_recorded_crime_loader"
        )
    except psycopg.OperationalError as e:
        sys.exit(
            f"Не удалось подключиться: {e}\n"
            "Пароль берётся из ~/.pgpass или PGPASSWORD, см. ../../DB.md"
        )
    with conn:
        conn.autocommit = True
        conn.execute("SET client_encoding = 'UTF8'")
        conn.execute("SET statement_timeout = 0")
        conn.execute("SET maintenance_work_mem = '256MB'")
        print(f"Подключено: {conn.info.user}@{conn.info.host}/{conn.info.dbname}")
        schema_oid = conn.execute(
            "select to_regnamespace(%s)", [f'"{SCHEMA}"']
        ).fetchone()[0]
        if schema_oid is None:
            sys.exit(f'Схемы "{SCHEMA}" нет в базе. Новых схем скрипт не создаёт.')
        results = {}
        for key, cfg in todo.items():
            print(f'\n[{key}] {cfg["file"]} -> "{SCHEMA}".{cfg["table"]}')
            results[key] = load(conn, cfg)

    print("\nИтог:")
    for key, res in results.items():
        name = f'"{SCHEMA}".{TABLES[key]["table"]}'
        if res is None:
            print(f"  {name}: пропущена, уже существовала")
        else:
            rows, total, n_months, tbl_size = res
            print(spaced(f"  {name}: {rows:,} строк, {n_months} мес., сумма {total:,}, {tbl_size}"))


if __name__ == "__main__":
    main()
