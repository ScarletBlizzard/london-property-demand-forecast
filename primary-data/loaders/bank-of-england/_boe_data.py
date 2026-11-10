"""Чтение исходных CSV без отбора и преобразования значений."""

import csv
import io

COLUMNS = ["DATE", "SERIES", "VALUE"]


def csv_rows(raw):
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    if next(reader, []) != COLUMNS:
        raise ValueError("Expected the original DATE,SERIES,VALUE CSV header")
    for row in reader:
        if not row:
            continue
        if len(row) != 3:
            raise ValueError("Incomplete CSV row")
        yield tuple(row)
