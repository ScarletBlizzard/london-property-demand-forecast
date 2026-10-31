#!/usr/bin/env python3
"""
Конвертер выгрузок ONS CPIH из JSON в один CSV для \\copy.

Принимает пути к файлам, скачанным с
https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/<cdid>/mm23/data
и пишет в stdout CSV с заголовком — по строке на (серия, месяц).

Берётся только массив months: quarters и years — агрегаты тех же наблюдений,
в первичных данных они не нужны. Сводка по каждой серии идёт в stderr.

Только стандартная библиотека. Запускать как: python3 -I lib/cpih_to_csv.py <json>...
"""

import csv
import itertools
import json
import sys

# Порядок колонок обязан совпадать с порядком в sql/ddl.sql — иначе \copy разложит
# значения не по тем колонкам (типы numeric/date частично поймают ошибку, но не везде).
COLUMNS = [
    "cdid",
    "title",
    "unit",
    "key_note",
    "period",
    "date",
    "year",
    "month",
    "value",
    "release_date",
    "update_date",
]

MONTHS = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}


def fail(msg):
    sys.exit(f"cpih_to_csv: {msg}")


def read_series(path):
    """Разбирает один файл выгрузки в (описание серии, список месячных строк)."""
    with open(path, encoding="utf-8") as fh:
        try:
            doc = json.load(fh)
        except json.JSONDecodeError as exc:
            fail(
                f"{path}: это не JSON ({exc}) — вероятно, ONS отдал HTML-страницу ошибки"
            )

    meta = doc.get("description") or {}
    cdid = meta.get("cdid")
    if not cdid:
        fail(f"{path}: в description нет cdid — формат выгрузки изменился")

    months = doc.get("months")
    if not months:
        fail(f"{path}: пустой или отсутствующий массив months для серии {cdid}")

    rows = []
    for n, obs in enumerate(months, start=1):
        month_name = obs.get("month")
        if month_name not in MONTHS:
            fail(f"{cdid}, наблюдение {n}: неизвестный месяц {month_name!r}")
        try:
            year = int(obs["year"])
        except KeyError, TypeError, ValueError:
            fail(f"{cdid}, наблюдение {n}: нечитаемый год {obs.get('year')!r}")

        value = (obs.get("value") or "").strip()
        if value:
            try:
                float(value)
            except ValueError:
                fail(f"{cdid}, {obs.get('date')}: значение {value!r} не число")

        rows.append(
            {
                "cdid": cdid,
                "title": meta.get("title", ""),
                "unit": meta.get("unit", ""),
                "key_note": meta.get("keyNote", ""),
                "period": f"{year:04d}-{MONTHS[month_name]:02d}-01",
                "date": obs.get("date", ""),
                "year": year,
                "month": month_name,
                "value": value,
                "release_date": meta.get("releaseDate", ""),
                "update_date": obs.get("updateDate", ""),
            }
        )

    periods = [r["period"] for r in rows]
    if len(set(periods)) != len(periods):
        fail(f"{cdid}: в months повторяются месяцы — выгрузка повреждена")
    if periods != sorted(periods):
        rows.sort(key=lambda r: r["period"])
        print(
            f"    [{cdid}] months пришли не по порядку, отсортировано", file=sys.stderr
        )

    return meta, rows


def main(paths):
    if not paths:
        fail("нужен хотя бы один путь к JSON-выгрузке")

    writer = csv.DictWriter(sys.stdout, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()

    seen = set()
    total = 0
    for path in paths:
        meta, rows = read_series(path)
        cdid = rows[0]["cdid"]
        if cdid in seen:
            fail(f"серия {cdid} передана дважды")
        seen.add(cdid)

        # Пропуски месяцев внутри ряда — не ошибка формата, но знать о них надо:
        # у годовых темпов прироста первые 12 месяцев истории отсутствуют по построению.
        months_n = [int(r["period"][:4]) * 12 + int(r["period"][5:7]) for r in rows]
        gaps = sum(b - a - 1 for a, b in itertools.pairwise(months_n) if b - a != 1)
        gap_note = f", пропущено месяцев: {gaps}" if gaps else ""

        print(
            f"    [{cdid}] {rows[0]['period'][:7]}..{rows[-1]['period'][:7]}, "
            f"{len(rows)} набл.{gap_note}, релиз {meta.get('releaseDate', '?')} "
            f"— {meta.get('title', '')}",
            file=sys.stderr,
        )

        writer.writerows(rows)
        total += len(rows)

    print(f"    итого {total} строк по {len(seen)} сериям", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
