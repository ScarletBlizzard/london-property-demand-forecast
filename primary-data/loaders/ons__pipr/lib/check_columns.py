#!/usr/bin/env python3
"""
Машинная сверка порядка колонок: шапка CSV против create table в sql/ddl.sql.

Использование: python3 -I lib/check_columns.py sql/ddl.sql data/pipr-london.csv

\\copy складывает поля в колонки по порядку, а не по имени, поэтому любое
расхождение между выгрузкой и DDL молча разъехалось бы по таблице. Скрипт
вызывается из load.sh перед заливкой и валит загрузку с кодом 1, если
имена или их порядок разошлись.
"""

import csv
import re
import sys


def ddl_columns(path):
    """Имена колонок в порядке объявления из блока create table ... (...);"""
    with open(path, encoding="utf-8") as fh:
        sql = fh.read()
    sql = re.sub(r"--[^\n]*", "", sql)  # комментарии -- ...
    body = re.search(r"create table[^(]*\((.*?)\n\);", sql, re.DOTALL | re.IGNORECASE)
    if not body:
        sys.exit(f"{path}: не нашёлся блок create table (...);")
    names = []
    for line in body.group(1).splitlines():
        line = line.strip().strip(",")
        if not line:
            continue
        name = line.split()[0]
        if name.lower() in ("primary", "constraint", "unique", "check", "foreign"):
            continue  # табличные ограничения, а не колонки
        names.append(name.strip('"'))
    return names


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__.strip())
    ddl, csv_path = sys.argv[1], sys.argv[2]

    expected = ddl_columns(ddl)
    with open(csv_path, encoding="utf-8", newline="") as fh:
        actual = next(csv.reader(fh, strict=True))

    if expected == actual:
        print(f"==> Сверка колонок: ок, {len(actual)} колонок в том же порядке")
        return

    print(f"РАСХОЖДЕНИЕ: в {ddl} {len(expected)} колонок, в {csv_path} {len(actual)}")
    for i in range(max(len(expected), len(actual))):
        e = expected[i] if i < len(expected) else "—"
        a = actual[i] if i < len(actual) else "—"
        print(f"  {i + 1:>3} {'ok ' if e == a else 'РАЗН'} ddl={e:<34} csv={a}")
    sys.exit(1)


main()
