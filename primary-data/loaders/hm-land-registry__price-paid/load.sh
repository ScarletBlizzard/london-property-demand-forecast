#!/bin/bash
#
# Полная загрузка HM Land Registry — Price Paid Data (Greater London) 
# в таблицу "primary".hm_land_registry__price_paid.
set -euo pipefail
cd "$(dirname "$0")"

URL="http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/pp-complete.csv"
TBL='"primary".hm_land_registry__price_paid'
CSV=data/pp-complete.csv
LONDON=data/london.csv
RELOAD=${RELOAD:-0}

source ../../db.env

mkdir -p data

echo "==> Качаю pp-complete.csv (~5.2 ГиБ, прерванная загрузка продолжится)"
LAST_MODIFIED=$(curl -fsIL "$URL" | tr -d '\r' | sed -n 's/^[Ll]ast-[Mm]odified: *//p' | tail -1)
if [ -z "$LAST_MODIFIED" ] || [ "$(cat "$CSV.version" 2>/dev/null)" != "$LAST_MODIFIED" ]; then
    rm -f "$CSV"
fi

curl -fL -C - --retry 3 --retry-delay 5 -o "$CSV" "$URL"
printf '%s\n' "$LAST_MODIFIED" > "$CSV.version"

echo "==> Создаю таблицу"
psql "$PGCONN" -w -v ON_ERROR_STOP=1 -q -f sql/ddl.sql

ROWS=$(psql "$PGCONN" -w -v ON_ERROR_STOP=1 -At -c "select count(*) from $TBL")
if [ "$ROWS" != 0 ] && [ "$RELOAD" != 1 ]; then
    echo "В таблице уже $ROWS строк. Чтобы перезалить: RELOAD=1 $0" >&2
    exit 1
fi

echo "==> Отбираю Greater London"
python3 lib/filter_london.py "$CSV" > "$LONDON"

echo "==> Заливаю в $TBL"
psql "$PGCONN" -w -v ON_ERROR_STOP=1 --single-transaction \
     -c "truncate $TBL" \
     -c "\\copy $TBL from '$LONDON' with (format csv)"

echo "==> Строю индексы и первичный ключ"
psql "$PGCONN" -w -v ON_ERROR_STOP=1 -q -f sql/indexes.sql

echo "==> Обновляю статистику"
psql "$PGCONN" -w -v ON_ERROR_STOP=1 -q -c "analyze $TBL"

echo "==> Результат"
psql "$PGCONN" -w -v ON_ERROR_STOP=1 -f sql/verify.sql
