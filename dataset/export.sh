#!/bin/bash
# Собирает CSV одним SELECT, не меняя БД.
set -euo pipefail
cd "$(dirname "$0")"

source ../primary-data/db.env

mkdir -p data
snapshot=$(mktemp data/.borough-month.XXXXXX)
trap 'rm -f "$snapshot"' EXIT

# -X отключает пользовательский psqlrc, read-only запрещает запись в БД.
export PGOPTIONS="${PGOPTIONS:-} -c default_transaction_read_only=on"
echo "Собираю датасет из первичных данных…"
psql "$PGCONN" -X -w -v ON_ERROR_STOP=1 --quiet --csv \
    --file dataset.sql > "$snapshot"

rows=$(($(wc -l < "$snapshot") - 1))
if [ "$rows" -le 0 ]; then
    echo "Ошибка: запрос не вернул строк; прежний снимок сохранён" >&2
    exit 1
fi
mv "$snapshot" data/borough-month.csv
echo "Сохранено: dataset/data/borough-month.csv ($rows строк)"
