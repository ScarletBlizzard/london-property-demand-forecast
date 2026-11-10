#!/bin/bash
#
# Полная загрузка MPS Recorded Crime (Borough, Ward, LSOA) в схему "primary":
# скачать -> проверить -> собрать хронологию 2010-04..2026-09 -> залить в БД.
# Повторный запуск безопасен: скачанное не перекачивается, собранное не
# пересобирается, существующие таблицы не трогаются.
set -euo pipefail
cd "$(dirname "$0")"

source ../../db.env

DATA_DIR=${DATA_DIR:-data}

if ! python3 -c "import pandas, psycopg" 2>/dev/null; then
    echo "Нужны pandas и psycopg: python3 -m pip install pandas 'psycopg[binary]'" >&2
    exit 1
fi

echo "==> 1/4 Качаю файлы источника в $DATA_DIR/raw"
python3 scripts/01_download.py

echo "==> 2/4 Проверяю скачанные файлы, пишу $DATA_DIR/manifest.csv"
python3 scripts/02_check_files.py

echo "==> 3/4 Собираю хронологию в $DATA_DIR/consolidated"
built=0
for level in borough ward lsoa; do
    if [ -f "$DATA_DIR/consolidated/${level}_2010-04_2026-09.csv" ]; then
        built=$((built + 1))
    fi
done
if [ "$built" = 3 ]; then
    echo "    уже собрано, пропускаю"
elif [ "$built" = 0 ]; then
    python3 scripts/05_consolidate.py
else
    echo "В $DATA_DIR/consolidated собраны не все уровни. Удалите эту папку и запустите снова." >&2
    exit 1
fi

echo "==> 4/4 Заливаю в БД"
python3 scripts/06_load_to_postgres.py
