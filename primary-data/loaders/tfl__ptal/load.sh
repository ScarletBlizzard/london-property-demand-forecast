#!/bin/bash
#
# Загрузка TfL — Public Transport Accessibility Levels (PTAL), уровень LSOA,
# в таблицы "primary".tfl__ptal_lsoa_2023 / tfl__ptal_lsoa_2015.
# Использование: ./load.sh [2023|2015]   (без аргумента — оба релиза)
# Каждый запуск полностью заменяет таблицу: релиз в источнике неизменен,
# пересчёта по месяцам тут нет, так что догружать нечего.
set -euo pipefail
cd "$(dirname "$0")"

TBL_PREFIX='"primary".tfl__ptal_lsoa_'

source ../../db.env

mkdir -p data

# Релиз 2023 лежит на ArcGIS-портале TfL, релиз 2015 — на London Datastore.
# Ссылки стабильные: id айтема и слой в пути не меняются между обновлениями.
# Каталог ArcGIS целиком: https://gis-tfl.opendata.arcgis.com/api/feed/dcat-us/1.1.json
url_for() {
    case $1 in
        2023) echo "https://gis-tfl.opendata.arcgis.com/api/download/v1/items/a1ac85edd51a42c9a7f86e2763bb7bdf/csv?layers=30" ;;
        2015) echo "https://data.london.gov.uk/download/24rz6/77d9b319-931e-4090-bf8e-f578938bd352/LSOA2011%20AvPTAI2015.csv" ;;
        *)    echo "неизвестный релиз: $1" >&2; return 2 ;;
    esac
}

load() {
    local rel=$1
    local url csv tbl last_modified
    url=$(url_for "$rel")
    csv=data/ptal-lsoa-$rel.csv
    tbl="$TBL_PREFIX$rel"

    # Оба источника отдают Last-Modified, по нему и сверяем. Файлы маленькие
    echo "==> [$rel] Проверяю версию в источнике"
    last_modified=$(curl -fsIL --retry 3 --retry-delay 5 "$url" \
                    | tr -d '\r' | sed -n 's/^[Ll]ast-[Mm]odified: *//p' | tail -1)

    if [ -s "$csv" ] && [ -n "$last_modified" ] \
       && [ "$(cat "$csv.version" 2>/dev/null)" = "$last_modified" ]; then
        echo "==> [$rel] Не менялся с $last_modified, качать не нужно"
    else
        echo "==> [$rel] Качаю CSV"
        curl -fL --progress-bar --retry 3 --retry-delay 5 -o "$csv" "$url"
        printf '%s\n' "$last_modified" > "$csv.version"
    fi

    # format csv + header: у файла 2023 в начале BOM, он уезжает вместе со строкой
    # заголовка. Порядок колонок в ddl совпадает с порядком в выгрузке.
    echo "==> [$rel] Заливаю в $tbl"
    psql "$PGCONN" -w -v ON_ERROR_STOP=1 --single-transaction -q \
         -c "set client_min_messages = warning" \
         -f "sql/ddl_$rel.sql" \
         -c "truncate $tbl" \
         -c "\\copy $tbl from '$csv' with (format csv, header)"

    echo "==> [$rel] Обновляю статистику"
    psql "$PGCONN" -w -v ON_ERROR_STOP=1 -q -c "analyze $tbl"

    psql "$PGCONN" -w -v ON_ERROR_STOP=1 -f "sql/verify_$rel.sql"
}

if [ $# -gt 0 ]; then RELEASES=("$1"); else RELEASES=(2023 2015); fi
for r in "${RELEASES[@]}"; do
    case $r in 2023|2015) load "$r" ;; *) echo "неизвестный релиз: $r" >&2; exit 2 ;; esac
done
