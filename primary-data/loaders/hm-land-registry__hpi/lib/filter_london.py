#!/usr/bin/env python3
"""
Отбирает из полной выгрузки UK HPI (UK-HPI-full-file-<YYYY>-<MM>.csv) строки
Лондона и агрегаты для нормировки, пишет результат в stdout вместе с заголовком.

Что остаётся:
  * E09...... — 33 лондонских боро (32 боро + City of London), рабочая гранулярность;
  * E12000007 — регион London, E92000001 — England, K02000001 — United Kingdom:
    только на этих уровнях публикуются сезонно сглаженные ряды (IndexSA,
    AveragePriceSA), на уровне боро они всегда пустые.

Использование: python3 -I lib/filter_london.py data/<файл>.csv > data/london.csv
"""

import csv
import sys

# Агрегаты, которые оставляем помимо боро. Great Britain (K03000001) и
# England and Wales (K04000001) не берём: это промежуточные склейки, для
# нормировки лондонских рядов они ничего не добавляют к London/England/UK.
AGGREGATES = frozenset({"E12000007", "E92000001", "K02000001"})

if len(sys.argv) != 2:
    sys.exit(f"использование: {sys.argv[0]} <uk-hpi-full-file.csv>")

with open(sys.argv[1], newline="", encoding="utf-8-sig") as src:
    reader = csv.reader(src, strict=True)
    writer = csv.writer(sys.stdout, lineterminator="\n")

    header = next(reader)
    writer.writerow(header)
    area_code = header.index("AreaCode")

    kept = 0
    for n, row in enumerate(reader, start=2):
        if len(row) != len(header):
            sys.exit(
                f"строка {n}: {len(row)} полей вместо {len(header)} — "
                f"выгрузка оборвана или повреждена"
            )
        if row[area_code].startswith("E09") or row[area_code] in AGGREGATES:
            writer.writerow(row)
            kept += 1

if kept == 0:
    sys.exit("в выгрузке не нашлось ни одной строки по Лондону — проверьте файл")
print(f"отобрано строк: {kept}", file=sys.stderr)
