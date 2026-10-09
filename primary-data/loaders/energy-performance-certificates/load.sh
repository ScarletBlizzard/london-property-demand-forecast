#!/bin/bash
#
# Загрузка Energy Performance Certificates (Greater London) в таблицы
# "primary".epc__domestic / epc__non_domestic / epc__display.
# Использование: ./load.sh [domestic|non-domestic|display]   (без аргумента — все три)
# Каждый запуск полностью заменяет таблицу: архив в источнике и так полный.
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "нет .env — скопируйте .env.example и впишите EPC_TOKEN" >&2; exit 1; }
set -a; . ./.env; set +a
: "${EPC_TOKEN:?пустой EPC_TOKEN в .env}"

API=https://api.get-energy-performance-data.communities.gov.uk/api/files

source ../../db.env

mkdir -p data

load() {
    local set=$1
    local name=${set//-/_}
    local zip=data/$set.zip
    local csv=data/$set-london.csv
    local tbl="\"primary\".epc__$name"

    echo "==> [$set] Качаю архив (прерванная загрузка продолжится)"
    local updated
    updated=$(curl -fs -H "Authorization: Bearer $EPC_TOKEN" "$API/$set/csv/info" | python3 -I -c 'import json,sys; print(json.load(sys.stdin)["data"]["lastUpdated"])')
    if [ "$(cat "$zip.version" 2>/dev/null)" != "$updated" ]; then
        rm -f "$zip"
        printf '%s\n' "$updated" > "$zip.version"
    fi
    curl -fL --progress-bar -C - --retry 3 --retry-delay 5 -H "Authorization: Bearer $EPC_TOKEN" -o "$zip" "$API/$set/csv"

    echo "==> [$set] Отбираю Greater London"
    unzip -p "$zip" 'certificates-*.csv' | python3 -I lib/filter_london.py > "$csv"

    echo "==> [$set] Заливаю в $tbl"
    psql "$PGCONN" -w -v ON_ERROR_STOP=1 --single-transaction -q \
         -c "set client_min_messages = warning" \
         -c "set statement_timeout = '4h'" \
         -f "sql/ddl_$name.sql" \
         -c "truncate $tbl" \
         -c "\\copy $tbl from '$csv' with (format csv, header)" \
         -f "sql/indexes_$name.sql"

    echo "==> [$set] Обновляю статистику"
    psql "$PGCONN" -w -v ON_ERROR_STOP=1 -q -c "analyze $tbl"

    psql "$PGCONN" -w -v ON_ERROR_STOP=1 -v tbl="$tbl" -f sql/verify.sql
}

if [ $# -gt 0 ]; then SETS=("$1"); else SETS=(display non-domestic domestic); fi
for s in "${SETS[@]}"; do
    case $s in domestic|non-domestic|display) load "$s" ;; *) echo "неизвестный набор: $s" >&2; exit 2 ;; esac
done
