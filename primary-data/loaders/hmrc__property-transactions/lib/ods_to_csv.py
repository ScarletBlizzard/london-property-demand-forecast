#!/usr/bin/env python3
"""
Достаёт из книги ODS (argv[1]) лист Residential_monthly и печатает его в stdout
как CSV с заголовком:

    month,month_label,england,scotland,wales,northern_ireland,uk,
    uk_seasonally_adjusted,provisional

ODS — это zip с content.xml внутри, так что хватает стандартной библиотеки.
Подводные камни листа, из-за которых тут столько проверок:
  * в книге 314 служебных листов с мусорными именами вида
    "'file://fastpkai2/tgi/.../MPT_Work_File_Dec_21.xlsx'#SDLT_Data" — остатки
    внешних ссылок рабочего файла HMRC. Один из них называется
    "'file://.../MPT_Work_File_Dec_21.xlsx'#Residential_monthly", так что лист
    ищется по точному совпадению имени, а не по вхождению подстроки;
  * первые 5 строк листа — пояснения, заголовок идёт шестым;
  * у последних трёх месяцев признак предварительности написан прямо в поле с
    датой: "June 2026 [provisional]", "August 2026 [provisional estimates]".
    Наивный разбор даты молча выбрасывает три самых свежих месяца, поэтому
    суффикс срезаем, а сам признак выносим в колонку provisional;
  * последняя содержательная строка листа — "End of worksheet";
  * пустые ячейки и строки схлопнуты в number-columns-repeated /
    number-rows-repeated: без их обработки колонки съезжают, а при наивном
    разворачивании лист раздувается до 1 048 576 строк;
  * имена месяцев английские, поэтому разбираем их по своей таблице, а не
    через strptime("%B") — он зависит от локали.
"""

import csv
import itertools
import sys
import xml.etree.ElementTree as ET
import zipfile

NS_TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
NS_OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
NS_TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"

SHEET = "Residential_monthly"
HEADER = [
    "Month and year",
    "England",
    "Scotland",
    "Wales",
    "Northern Ireland",
    "UK",
    "UK (seasonally adjusted)",
]
OUT_HEADER = [
    "month",
    "month_label",
    "england",
    "scotland",
    "wales",
    "northern_ireland",
    "uk",
    "uk_seasonally_adjusted",
    "provisional",
]
END_OF_SHEET = "End of worksheet"
FIRST_MONTH = (2005, 4)

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

# Длинный прогон пустых ячеек в number-columns-repeated — это хвост строки до
# края листа (1024 колонки), а не пропуск внутри данных.
BLANK_RUN = 100


def tag(namespace, name):
    return f"{{{namespace}}}{name}"


def read_cell(cell):
    """Ячейка как (office:value, видимый текст)."""
    text = "\n".join("".join(p.itertext()) for p in cell.findall(tag(NS_TEXT, "p")))
    return cell.get(tag(NS_OFFICE, "value")), text.replace("\xa0", " ").strip()


def read_row(row):
    cells = []
    for cell in row:
        if cell.tag not in (
            tag(NS_TABLE, "table-cell"),
            tag(NS_TABLE, "covered-table-cell"),
        ):
            continue
        repeat = int(cell.get(tag(NS_TABLE, "number-columns-repeated"), 1))
        value = read_cell(cell)
        if not value[1] and repeat > BLANK_RUN:
            break
        cells.extend([value] * repeat)
    while cells and not cells[-1][1]:
        cells.pop()
    return cells


def read_sheet(path, name):
    with zipfile.ZipFile(path) as book:
        content = ET.fromstring(book.read("content.xml"))

    found = [
        table
        for table in content.iter(tag(NS_TABLE, "table"))
        if table.get(tag(NS_TABLE, "name")) == name
    ]
    if len(found) != 1:
        sys.exit(
            f"в книге {len(found)} листов с именем {name!r} вместо одного — "
            f"состав релиза изменился"
        )
    sheet = found[0]

    rows = []
    for row in sheet.iter(tag(NS_TABLE, "table-row")):
        cells = read_row(row)
        if not cells:  # пустая строка; в конце листа она одна, но с repeat ~1e6
            continue
        repeat = int(row.get(tag(NS_TABLE, "number-rows-repeated"), 1))
        if repeat != 1:
            sys.exit(f"непустая строка повторяется {repeat} раз: {cells!r}")
        rows.append(cells)
    return rows


def parse_month(label):
    """'August 2026 [provisional estimates]' -> ('2026-08-01', True)."""
    name, bracket, _ = label.partition("[")
    parts = name.split()
    if len(parts) != 2 or parts[0] not in MONTHS or not parts[1].isdigit():
        sys.exit(f"не разбирается месяц: {label!r}")
    return f"{int(parts[1]):04d}-{MONTHS[parts[0]]:02d}-01", bool(bracket)


def as_int(cell, where):
    value, text = cell
    if value is None:
        sys.exit(f"{where}: ожидалось число, в ячейке {text!r}")
    number = float(value)
    if number != int(number):
        sys.exit(f"{where}: нецелое значение {text!r}")
    return int(number)


def main():
    if len(sys.argv) != 2:
        sys.exit("использование: ods_to_csv.py <файл.ods>")

    rows = read_sheet(sys.argv[1], SHEET)

    header = next(
        (n for n, row in enumerate(rows) if [c[1] for c in row] == HEADER), None
    )
    if header is None:
        sys.exit(
            f"на листе {SHEET} не нашёлся заголовок {HEADER} — "
            f"структура листа изменилась, загрузчик нужно перечитать"
        )

    out = []
    seen_end = False
    for row in rows[header + 1 :]:
        if [c[1] for c in row] == [END_OF_SHEET]:
            seen_end = True
            break
        if len(row) != len(HEADER):
            sys.exit(
                f"строка {row[0][1]!r}: {len(row)} полей вместо {len(HEADER)} — "
                f"структура листа изменилась"
            )
        month, provisional = parse_month(row[0][1])
        values = [as_int(c, row[0][1]) for c in row[1:]]
        out.append([month, row[0][1], *values, "true" if provisional else "false"])

    if not seen_end:
        sys.exit(f"не нашлась строка {END_OF_SHEET!r} — выгрузка оборвана")
    if not out:
        sys.exit("на листе нет данных")

    first = (int(out[0][0][:4]), int(out[0][0][5:7]))
    if first != FIRST_MONTH:
        sys.exit(f"ряд начинается с {out[0][1]!r}, а не с April 2005")

    for previous, current in itertools.pairwise(out):
        year, month = int(previous[0][:4]), int(previous[0][5:7])
        expected = f"{year + month // 12:04d}-{month % 12 + 1:02d}-01"
        if current[0] != expected:
            sys.exit(f"разрыв в ряду: после {previous[1]!r} идёт {current[1]!r}")

    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(OUT_HEADER)
    writer.writerows(out)


main()
