# Основная команда загрузчика Nomis: скачивает данные или читает уже готовую выгрузку,
# после чего при необходимости записывает её в PostgreSQL.
#
# У населения, рынка труда, заработков и Claimant Count разные столбцы, поэтому каждый
# набор попадает в свою таблицу primary. Строки читаются порциями, чтобы не держать всю
# выгрузку в памяти. Здесь связываются скачивание, проверка файлов и запись в БД;
# расчётов над показателями нет.

import sys
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(DIRECTORY))
from _nomis_download import (
    REQUIRED,
    TABLE_NAMES,
    check_page,
    download,
)
from _nomis_support import arguments, read_page, read_snapshot, replace_tables, run


# Даёт повторный доступ к строкам сохранённого набора без загрузки всех файлов в память.
class RawRows:
    # Проверяет список страниц и запоминает столбцы, периоды и ожидаемое число строк.
    def __init__(self, folder, settings):
        self.folder = folder
        self.queries = settings.get("queries", [settings])
        self.columns = None
        self.dates = set(settings.get("dates", []))
        self.count = 0
        for query in self.queries:
            self.dates.update(query.get("dates", []))
            total = query["record_count"]
            self.count += total
            pages = query["pages"]
            if total and not pages:
                raise ValueError("Nomis: incomplete download")
            if pages and isinstance(pages[0], dict):
                next_offset = 0
                for page in pages:
                    if page["offset"] != next_offset or page["rows"] <= 0:
                        raise ValueError("Nomis: incomplete page sequence")
                    next_offset += page["rows"]
                if next_offset != total:
                    raise ValueError("Nomis: incomplete download")
            if pages and self.columns is None:
                filename = (
                    pages[0]["filename"] if isinstance(pages[0], dict) else pages[0]
                )
                if Path(filename).name != filename:
                    raise ValueError("Invalid snapshot page filename")
                self.columns, _ = read_page(folder / filename, REQUIRED)
        if not self.count:
            raise ValueError("Nomis: refusing an empty dataset")

    def __len__(self):
        return self.count

    # Читает страницы по очереди и проверяет их структуру и непрерывность записей.
    def batches(self):
        for query in self.queries:
            offset = 0
            for page in query["pages"]:
                filename = page["filename"] if isinstance(page, dict) else page
                if Path(filename).name != filename:
                    raise ValueError("Invalid snapshot page filename")
                columns, rows = read_page(self.folder / filename, REQUIRED)
                if columns != self.columns:
                    raise ValueError("Nomis: CSV headers differ between pages")
                if isinstance(page, dict) and len(rows) != page["rows"]:
                    raise ValueError("Nomis: incomplete page")
                check_page(columns, rows, offset, query["record_count"])
                offset += len(rows)
                yield rows
            if offset != query["record_count"]:
                raise ValueError("Nomis: incomplete download")

    def __iter__(self):
        for batch in self.batches():
            yield from batch


# Сопоставляет наборам из готовой выгрузки имена таблиц и доступ к исходным строкам.
def raw_tables(folder, manifest):
    if manifest.get("version", 1) >= 2 and manifest.get("status") != "complete":
        raise ValueError("Snapshot is incomplete; use --resume before loading it")
    tables = {}
    for dataset, settings in manifest["datasets"].items():
        rows = RawRows(folder, settings)
        tables[TABLE_NAMES[dataset]] = (rows.columns, rows)
    return tables


# Выбирает режим работы: план, скачивание, проверку файлов или загрузку в PostgreSQL.
def main():
    args = arguments(
        "Collect the full raw dimensions of our configured Nomis datasets for London."
    )
    folder, manifest = (
        (args.snapshot, read_snapshot(args.snapshot, "nomis"))
        if args.snapshot
        else download(args)
    )
    print(f"Raw files: {folder}", flush=True)
    if args.plan:
        return
    tables = raw_tables(folder, manifest)
    if args.download_only:
        for table, (columns, rows) in tables.items():
            count = sum(len(batch) for batch in rows.batches())
            print(
                f"Validated {table}: {count:,} rows, {len(columns)} original columns",
                flush=True,
            )
    else:
        if manifest.get("version", 1) >= 2:
            from _nomis_database import load_snapshot

            load_snapshot(
                args.env_file,
                folder,
                manifest,
                tables,
                allow_smaller=args.allow_smaller_replacement,
                workers=args.db_workers,
            )
        else:
            replace_tables(
                args.env_file, tables, allow_smaller=args.allow_smaller_replacement
            )


if __name__ == "__main__":
    run(main)
