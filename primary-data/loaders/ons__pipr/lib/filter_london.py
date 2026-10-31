#!/usr/bin/env python3
"""
Читает со stdin плоский CSV из lib/sheet_to_csv.py и пишет в stdout заголовок
и строки Greater London — районы с кодами area_code вида E09...... .

Так же отбирает Лондон загрузчик EPC
(../energy-performance-certificates/lib/filter_london.py).
"""

import csv
import sys

CODE_COLUMN = "area_code"
LONDON_PREFIX = "E09"

writer = csv.writer(sys.stdout, lineterminator="\n")
reader = csv.reader(sys.stdin, strict=True)

header = next(reader)
writer.writerow(header)
if CODE_COLUMN not in header:
    sys.exit(f"в шапке нет колонки {CODE_COLUMN}: {header}")
CODE = header.index(CODE_COLUMN)

kept = 0
for n, row in enumerate(reader, start=2):
    if len(row) != len(header):
        sys.exit(
            f"строка {n}: {len(row)} полей вместо {len(header)} — "
            f"выгрузка оборвана или повреждена"
        )
    if row[CODE].startswith(LONDON_PREFIX):
        writer.writerow(row)
        kept += 1

if not kept:
    sys.exit(
        f"ни одной строки с кодом {LONDON_PREFIX}... — проверьте колонку {CODE_COLUMN}"
    )
print(f"Greater London: {kept} строк", file=sys.stderr)
