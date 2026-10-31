#!/usr/bin/env python3
"""
Сверяет порядок колонок в sql/ddl.sql с заголовком выгрузки UK HPI.

\\copy грузит CSV позиционно: если HM Land Registry вставит колонку в середину
файла, заливка молча разъедется по типам или упадёт в середине. Поэтому перед
каждой заливкой заголовок сверяется машинно.

Имя колонки в CSV приводится к имени в таблице одним правилом, без списка
соответствий:
  AveragePrice     -> average_price      (границы CamelCase)
  IndexSA          -> index_sa
  FTBPrice         -> ftb_price          (аббревиатура + слово)
  1m%Change        -> change_1m_pct      (суффикс со знаком процента)
  Detached12m%Change -> detached_change_12m_pct

Использование: python3 -I lib/check_header.py data/<файл>.csv sql/ddl.sql
"""

import re
import sys

# Границы CamelCase: "aB" -> "a_B", "ABc" -> "A_Bc".
_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
# Суффиксы вида "1m%Change" / "12m%Change", возможно с префиксом-разбивкой.
_CHANGE = re.compile(r"(?P<prefix>.*?)(?P<months>\d+)m%Change\Z")
# Первая колонка в "create table ... ( <колонка> ..." и далее по строкам.
_DDL_COLUMN = re.compile(r"^\s{4}([a-z_][a-z0-9_]*)\s")


def to_column(name: str) -> str:
    """Имя колонки CSV -> ожидаемое имя колонки в таблице."""
    change = _CHANGE.fullmatch(name)
    if change:
        prefix = change["prefix"]
        tail = f"change_{change['months']}m_pct"
        return f"{_snake(prefix)}_{tail}" if prefix else tail
    return _snake(name)


def _snake(name: str) -> str:
    return _BOUNDARY.sub("_", name).lower()


def ddl_columns(path: str) -> list[str]:
    """Колонки из create table в порядке объявления."""
    columns: list[str] = []
    inside = False
    with open(path, encoding="utf-8") as ddl:
        for line in ddl:
            if not inside:
                inside = line.lstrip().startswith("create table")
                continue
            if line.startswith(");"):
                break
            found = _DDL_COLUMN.match(line)
            if found and found[1] not in ("primary", "constraint"):
                columns.append(found[1])
    return columns


def main() -> int:
    if len(sys.argv) != 3:
        sys.exit(f"использование: {sys.argv[0]} <csv> <ddl.sql>")
    csv_path, ddl_path = sys.argv[1], sys.argv[2]

    with open(csv_path, encoding="utf-8-sig") as src:
        header = src.readline().rstrip("\r\n").split(",")
    # Страховка от завершающей запятой в заголовке: пустое имя — не колонка.
    header = [h for h in header if h]

    expected = [to_column(h) for h in header]
    actual = ddl_columns(ddl_path)

    if expected == actual:
        print(
            f"OK: порядок и имена {len(actual)} колонок ddl.sql совпадают с заголовком CSV"
        )
        return 0

    print(
        f"РАСХОЖДЕНИЕ: в CSV {len(expected)} колонок, в ddl.sql {len(actual)}",
        file=sys.stderr,
    )
    for i in range(max(len(expected), len(actual))):
        got = actual[i] if i < len(actual) else "—"
        want = expected[i] if i < len(expected) else "—"
        mark = "  " if got == want else "!!"
        print(
            f"{mark} {i + 1:3d}  csv={header[i] if i < len(header) else '—':24s}"
            f" ожидается={want:28s} в ddl={got}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
