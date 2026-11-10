"""Загрузка готовых страниц Nomis в PostgreSQL."""

from pathlib import Path

from _nomis_data import REQUIRED, TABLE_NAMES, check_page
from _nomis_support import arguments, read_page, read_snapshot, replace_tables, run


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
                raise ValueError("Nomis: incomplete snapshot")
            if pages and isinstance(pages[0], dict):
                next_offset = 0
                for page in pages:
                    if page["offset"] != next_offset or page["rows"] <= 0:
                        raise ValueError("Nomis: incomplete page sequence")
                    next_offset += page["rows"]
                if next_offset != total:
                    raise ValueError("Nomis: incomplete snapshot")
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
                raise ValueError("Nomis: incomplete snapshot")

    def __iter__(self):
        for batch in self.batches():
            yield from batch


def raw_tables(folder, manifest):
    if manifest.get("version", 1) >= 2 and manifest.get("status") != "complete":
        raise ValueError("Snapshot is incomplete; provide a complete set of files")
    if not manifest["datasets"] or not set(manifest["datasets"]) <= TABLE_NAMES.keys():
        raise ValueError(
            "The snapshot must contain one or more configured Nomis datasets"
        )
    tables = {}
    for dataset, settings in manifest["datasets"].items():
        rows = RawRows(folder, settings)
        tables[TABLE_NAMES[dataset]] = (rows.columns, rows)
    return tables


def main():
    args = arguments("Load saved Nomis CSV/TSV files into PostgreSQL.")
    folder = args.snapshot
    manifest = read_snapshot(folder, "nomis")
    tables = raw_tables(folder, manifest)
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
