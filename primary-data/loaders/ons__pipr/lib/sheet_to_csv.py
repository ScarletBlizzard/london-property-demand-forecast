#!/usr/bin/env python3
"""
Разворачивает лист XLSX-выгрузки ONS PIPR в плоский CSV на stdout.

Использование: python3 -I lib/sheet_to_csv.py data/pipr.xlsx ["Table 1"]

Лист выбирается по точному имени из xl/workbook.xml, а не по номеру: порядок
листов в выгрузке ONS не гарантирован, а перед таблицей идут ещё
"Cover sheet", "Contents" и "Notes".

XLSX — это zip с XML внутри, поэтому хватает стандартной библиотеки
(у проекта dependencies = []). Лист с данными весит под 100 МБ в распакованном
виде, так что он читается потоково через ET.iterparse.

Что меняется по сравнению с источником:
  * строка заголовка приводится к snake_case (Time period -> time_period);
  * "Time period" из excel-овского серийного номера дня разворачивается
    в ISO-дату первого числа месяца (42005 -> 2015-01-01);
  * маркеры пропусков [x] (нет данных) и [z] (не применимо) в числовых
    колонках становятся пустым значением, то есть NULL в базе;
    в текстовых колонках они остаются как есть ([z] в area_code — это
    северноирландские BRMA, у которых нет кода local authority).
Больше ничего: ни агрегации, ни отбора строк, ни округления.
"""

import csv
import datetime
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RELS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# Лист с данными. В выгрузке он один ("Contents" обещает ровно одну таблицу),
# но имя передаётся вторым аргументом, если ONS его переименует.
DEFAULT_SHEET = "Table 1"

# Первая колонка таблицы — по ней ищется строка заголовка:
# над ней в листе лежат заголовок таблицы и строка про сноски.
FIRST_HEADER_CELL = "Time period"

# Колонки, которые остаются текстом; во всех остальных [x]/[z] -> NULL.
TEXT_COLUMNS = 4

# Excel считает дни от 1900-01-01 = 1, но с «лишним» 29 февраля 1900 года,
# поэтому серийный номер отсчитывается от 1899-12-30.
EXCEL_EPOCH = datetime.date(1899, 12, 30)

MISSING = ("[x]", "[z]")


def snake(name):
    """Time period -> time_period, Index four or more bed -> index_four_or_more_bed."""
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def column_index(ref):
    """A1 -> 0, AN42 -> 39."""
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def excel_date(value):
    """Серийный номер дня -> ISO-дата. Готовую ISO-дату пропускает как есть."""
    if "-" in value:
        return value[:10]
    return (EXCEL_EPOCH + datetime.timedelta(days=int(float(value)))).isoformat()


def sheet_path(zf, wanted):
    """Путь к XML листа с именем wanted внутри архива."""
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    targets = {e.get("Id"): e.get("Target") for e in rels}
    names = []
    for sheet in ET.fromstring(zf.read("xl/workbook.xml")).iter(MAIN + "sheet"):
        names.append(sheet.get("name"))
        if sheet.get("name") == wanted:
            target = targets[sheet.get(RELS + "id")].lstrip("/")
            return target if target.startswith("xl/") else "xl/" + target
    sys.exit(f"в выгрузке нет листа {wanted!r}; есть только: {names}")


def shared_strings(zf):
    """Таблица общих строк: ячейки с t="s" ссылаются в неё номером."""
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return [
        "".join(t.text or "" for t in si.iter(MAIN + "t"))
        for si in root.iter(MAIN + "si")
    ]


def rows(zf, path, strings):
    """Потоково отдаёт (номер строки, {номер колонки: значение})."""
    with zf.open(path) as fh:
        for _, el in ET.iterparse(fh, events=("end",)):
            if el.tag != MAIN + "row":
                continue
            cells = {}
            for c in el.iter(MAIN + "c"):
                kind = c.get("t")
                if kind == "inlineStr":
                    value = "".join(t.text or "" for t in c.iter(MAIN + "t"))
                else:
                    v = c.find(MAIN + "v")
                    value = "" if v is None or v.text is None else v.text
                    if kind == "s":
                        value = strings[int(value)]
                cells[column_index(c.get("r"))] = value.strip()
            yield int(el.get("r")), cells
            el.clear()


def main():
    if not 2 <= len(sys.argv) <= 3:
        sys.exit(__doc__.strip())
    xlsx = sys.argv[1]
    wanted = sys.argv[2] if len(sys.argv) == 3 else DEFAULT_SHEET

    zf = zipfile.ZipFile(xlsx)
    strings = shared_strings(zf)
    writer = csv.writer(sys.stdout, lineterminator="\n")

    header = None
    width = 0
    written = 0
    for number, cells in rows(zf, sheet_path(zf, wanted), strings):
        if header is None:
            if cells.get(0) != FIRST_HEADER_CELL:
                continue  # заголовок таблицы и строка про сноски над шапкой
            width = max(cells) + 1
            while width > 1 and not cells.get(width - 1):
                width -= 1  # в шапке бывает хвост из пустых ячеек
            header = [snake(cells.get(i, "")) for i in range(width)]
            if "" in header:
                sys.exit(f"строка {number}: в шапке есть колонка без имени: {header}")
            writer.writerow(header)
            continue

        if not any(cells.get(i) for i in range(width)):
            continue  # пустая строка-разделитель в конце листа
        row = [cells.get(i, "") for i in range(width)]
        if max(cells) + 1 > width:
            sys.exit(
                f"строка {number}: {max(cells) + 1} колонок вместо {width} — "
                f"структура листа {wanted!r} изменилась, проверьте sql/ddl.sql"
            )
        row[0] = excel_date(row[0])
        for i in range(TEXT_COLUMNS, width):
            if row[i] in MISSING:
                row[i] = ""
        writer.writerow(row)
        written += 1

    if header is None:
        sys.exit(
            f"на листе {wanted!r} не нашлась шапка со столбцом {FIRST_HEADER_CELL!r}"
        )
    if not written:
        sys.exit(f"на листе {wanted!r} нет ни одной строки данных")
    print(f"{wanted}: {written} строк, {width} колонок", file=sys.stderr)


main()
