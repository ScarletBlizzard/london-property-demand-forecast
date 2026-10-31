#!/bin/bash
#
# Загрузка ONS — Price Index of Private Rents (PIPR), районы Лондона,
# в таблицу "primary".ons__pipr.
# Использование: ./load.sh
# Каждый запуск полностью заменяет таблицу: ONS публикует всю историю с января
# 2015 года в одном файле и пересчитывает последние два месяца, так что
# догружать нечего, а повторный запуск безопасен.
set -euo pipefail
cd "$(dirname "$0")"

TBL='"primary".ons__pipr'

# Страница выгрузки на ONS. Прямой ссылки на "последний файл" у ONS нет: у каждого
# релиза свой адрес вида .../<дата релиза>/<имя файла>.xlsx, а .../latest/... отдаёт
# 404. Поэтому адрес собирается из двух JSON-ручек самого сайта:
#   <LANDING>/data        -> список релизов, свежий первый
#   <релиз>/data          -> имя файла выгрузки
ONS=https://www.ons.gov.uk
LANDING=/economy/inflationandpriceindices/datasets/priceindexofprivaterentsukmonthlypricestatistics

SHEET='Table 1'
XLSX=data/pipr.xlsx
CSV=data/pipr-london.csv

source ../../db.env

mkdir -p data

echo "==> Ищу свежий релиз на ONS"
edition=$(curl -fsL --retry 3 --retry-delay 5 "$ONS$LANDING/data" \
          | python3 -I -c 'import json,sys; print(json.load(sys.stdin)["datasets"][0]["uri"])')
file=$(curl -fsL --retry 3 --retry-delay 5 "$ONS$edition/data" \
       | python3 -I -c 'import json,sys; print(json.load(sys.stdin)["downloads"][0]["file"])')
url="$ONS/file?uri=$edition/$file"
echo "==> Релиз: $edition"

# Версия файла. Last-Modified ONS за CDN не отдаёт, поэтому основной маркер —
# адрес релиза (у каждого месяца свой), а ETag (sha1 содержимого) добавляется,
# чтобы поймать правку файла внутри того же релиза.
headers=$(curl -fsIL --retry 3 --retry-delay 5 "$url" | tr -d '\r')
last_modified=$(printf '%s\n' "$headers" | sed -n 's/^[Ll]ast-[Mm]odified: *//p' | tail -1)
etag=$(printf '%s\n' "$headers" | sed -n 's/^[Ee][Tt]ag: *//p' | tail -1)
version="$edition ${last_modified:-${etag:-нет маркера версии}}"

if [ -s "$XLSX" ] && [ "$(cat "$XLSX.version" 2>/dev/null)" = "$version" ]; then
    echo "==> Файл не менялся ($version), качать не нужно"
else
    echo "==> Качаю XLSX (~19 МБ)"
    curl -fL --progress-bar --retry 3 --retry-delay 5 -o "$XLSX" "$url"
    printf '%s\n' "$version" > "$XLSX.version"
fi

# Лист выбирается по точному имени: перед таблицей в книге идут Cover sheet,
# Contents и Notes, и порядок листов ONS не гарантирует.
echo "==> Разворачиваю лист '$SHEET' и отбираю Greater London"
python3 -I lib/sheet_to_csv.py "$XLSX" "$SHEET" | python3 -I lib/filter_london.py > "$CSV"

# \copy раскладывает поля по порядку, а не по именам, поэтому порядок колонок
# в ddl.sql сверяется с шапкой выгрузки до заливки, а не после.
echo "==> Сверяю колонки ddl.sql с шапкой выгрузки"
python3 -I lib/check_columns.py sql/ddl.sql "$CSV"

echo "==> Заливаю в $TBL"
psql "$PGCONN" -w -v ON_ERROR_STOP=1 --single-transaction -q \
     -c "set client_min_messages = warning" \
     -f sql/ddl.sql \
     -c "truncate $TBL" \
     -c "\\copy $TBL from '$CSV' with (format csv, header)"

echo "==> Обновляю статистику"
psql "$PGCONN" -w -v ON_ERROR_STOP=1 -q -c "analyze $TBL"

psql "$PGCONN" -w -v ON_ERROR_STOP=1 -f sql/verify.sql
