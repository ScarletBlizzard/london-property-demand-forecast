#!/usr/bin/env python3
"""
Отбирает сделки Greater London из выгрузки Land Registry.
"""

import csv
import sys

COUNTY = 13  # номер колонки с нуля: county — 14-я в выгрузке
FIELDS = 16

if len(sys.argv) != 2:
    sys.exit(f"использование: {sys.argv[0]} <csv-файл>")

writer = csv.writer(sys.stdout, quoting=csv.QUOTE_ALL, lineterminator="\n")
total = 0

with open(sys.argv[1], newline="", encoding="utf-8", errors="replace") as f:
    for row in csv.reader(f):
        if len(row) != FIELDS:
            sys.exit(
                f"строка {total + 1}: {len(row)} полей вместо {FIELDS} — "
                f"выгрузка оборвана или повреждена"
            )
        total += 1
        if row[COUNTY].strip().upper() == "GREATER LONDON":
            writer.writerow(row)
