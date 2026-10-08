#!/usr/bin/env python3
"""
Читает со stdin склеенные годовые certificates-*.csv и пишет в stdout
заголовок и строки Greater London (коды районов local_authority E09......).
"""
import csv
import sys

writer = csv.writer(sys.stdout, quoting=csv.QUOTE_ALL, lineterminator="\n")
reader = csv.reader(sys.stdin, strict=True)

header = next(reader)
writer.writerow(header)
LA = header.index("local_authority")

for n, row in enumerate(reader, start=2):
    if row == header:       # заголовок следующего годового файла
        continue
    if len(row) != len(header):
        sys.exit(f"строка {n}: {len(row)} полей вместо {len(header)} — "
                 f"выгрузка оборвана или повреждена")
    if row[LA].startswith("E09"):
        writer.writerow(row)
