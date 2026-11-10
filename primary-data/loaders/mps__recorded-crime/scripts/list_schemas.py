"""Показать схемы БД первичных данных. Только чтение: сессия в режиме read-only.

Запуск из папки загрузчика: python3 scripts/list_schemas.py

Подключение: параметры из общего ../../db.env, пароль из ~/.pgpass или PGPASSWORD.
"""

import os
import re

import psycopg

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # папка загрузчика
DB_ENV = os.path.join(HERE, "..", "..", "db.env")
ENV_LINE = re.compile(r"^export\s+(\w+)=\$\{(\w+):-(.*)\}\s*$")

SQL = """
select n.nspname                                   as schema,
       pg_get_userbyid(n.nspowner)                 as owner,
       count(c.oid) filter (where c.relkind in ('r','p'))  as tables,
       count(c.oid) filter (where c.relkind in ('v','m'))  as views,
       pg_size_pretty(coalesce(sum(pg_total_relation_size(c.oid))
                      filter (where c.relkind in ('r','p','m')), 0)) as size,
       has_schema_privilege(n.oid, 'USAGE')        as usage,
       has_schema_privilege(n.oid, 'CREATE')       as can_create
from pg_namespace n
left join pg_class c on c.relnamespace = n.oid
where n.nspname not like 'pg\\_%' and n.nspname <> 'information_schema'
group by n.oid, n.nspname, n.nspowner
order by n.nspname
"""


def load_db_env():
    """Как `source ../../db.env`: значение из окружения важнее значения из файла."""
    with open(DB_ENV, encoding="utf-8") as f:
        for line in f:
            m = ENV_LINE.match(line.strip())
            if m and m.group(1) == m.group(2):
                os.environ.setdefault(m.group(1), m.group(3).strip('"'))


load_db_env()
with psycopg.connect(
    os.environ.get("PGCONN", ""),
    application_name="list_schemas",
    options="-c default_transaction_read_only=on",
) as conn:
    cur = conn.execute(SQL)
    cols = [d.name for d in cur.description]
    rows = cur.fetchall()

widths = [max(len(str(x)) for x in [c, *(r[i] for r in rows)]) for i, c in enumerate(cols)]
print(" | ".join(c.ljust(w) for c, w in zip(cols, widths)))
print("-+-".join("-" * w for w in widths))
for r in rows:
    print(" | ".join(str(v).ljust(w) for v, w in zip(r, widths)))
