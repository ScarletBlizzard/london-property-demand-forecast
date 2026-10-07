#!/bin/bash
#
# Обновление одного года HM Land Registry — Price Paid Data (Greater London).
# Год заменяется целиком, поэтому дублей не возникает при любом числе запусков
set -euo pipefail
cd "$(dirname "$0")"

THIS_YEAR=$(date +%Y)
YEAR=${1:-}
if [[ ! "$YEAR" =~ ^[0-9]{4}$ ]] || [ "$YEAR" -lt 1995 ] || [ "$YEAR" -gt "$THIS_YEAR" ]; then
    echo "использование: $0 YYYY   (1995–$THIS_YEAR, например $0 $THIS_YEAR)" >&2
    exit 2
fi

URL="http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/pp-$YEAR.csv"
TBL='"primary".hm_land_registry__price_paid'
CSV=data/pp-$YEAR.csv
LONDON=data/london.csv

export PGHOST=${PGHOST:-rc1b-5l8v7vnu5f1or9d4.mdb.yandexcloud.net}
export PGPORT=${PGPORT:-6432}
export PGDATABASE=${PGDATABASE:-106-primary}
export PGUSER=${PGUSER:-team-member}
export PGSSLMODE=require

mkdir -p data

echo "==> Качаю pp-$YEAR.csv"
LAST_MODIFIED=$(curl -fsIL "$URL" | tr -d '\r' | sed -n 's/^[Ll]ast-[Mm]odified: *//p' | tail -1)
if [ -z "$LAST_MODIFIED" ] || [ "$(cat "$CSV.version" 2>/dev/null)" != "$LAST_MODIFIED" ]; then
    rm -f "$CSV"
fi

curl -fL -C - --retry 3 --retry-delay 5 -o "$CSV" "$URL"
printf '%s\n' "$LAST_MODIFIED" > "$CSV.version"

echo "==> Проверяю схему"
psql -w -v ON_ERROR_STOP=1 -q -f sql/ddl.sql

echo "==> Отбираю Greater London"
python3 lib/filter_london.py "$CSV" > "$LONDON"

echo "==> Заменяю $YEAR"
psql -w -v ON_ERROR_STOP=1 -v y="$YEAR-01-01" -f sql/replace_year.sql

echo "==> Обновляю статистику"
psql -w -v ON_ERROR_STOP=1 -q -c "analyze $TBL"

echo "==> Результат"
psql -w -v ON_ERROR_STOP=1 -f sql/verify.sql
