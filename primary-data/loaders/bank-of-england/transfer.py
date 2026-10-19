# Команда для переноса готовой таблицы BoE из локального PostgreSQL в рабочую БД. Она
# нужна, когда данные уже скачаны и повторно обращаться к сайту долго и незачем.
#
# Сохранённая выгрузка задаёт ожидаемые столбцы, число строк и даты, а сами значения
# читаются из локальной БД. Общий механизм копирования находится в
# nomis/_postgres_transfer.py; отсюда ему передаётся только таблица BoE. Параметр
# --check-only запускает сверку без записи.

import sys
from pathlib import Path

from _boe_support import connection_settings, read_snapshot, run
from load import COLUMNS, PREVIOUS_COLUMNS, TABLE, csv_rows, validate_snapshot

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nomis"))
from _postgres_transfer import arguments, transfer


# Проверяет выгрузку BoE, собирает ожидаемую структуру и запускает перенос одной
# таблицы.
def main():
    args = arguments(
        "Copy the complete raw BoE table from local PostgreSQL without contacting BoE."
    )
    manifest = read_snapshot(args.snapshot, "bank-of-england")
    validate_snapshot(args.snapshot, manifest)
    dates = {
        row[0]
        for part in manifest["parts"]
        for row in csv_rows((args.snapshot / part["file"]).read_bytes())
    }
    tables = {
        TABLE: {
            "columns": COLUMNS,
            "rows": manifest["total_rows"],
            "dates": sorted(dates),
            "previous_columns": PREVIOUS_COLUMNS,
        }
    }
    transfer(
        connection_settings(args.source_env),
        connection_settings(args.target_env),
        tables,
        check_only=args.check_only,
        batch_size=args.batch_size,
        report_path=args.report,
    )


if __name__ == "__main__":
    run(main)
