#!/bin/bash
#
# Загрузка UK House Price Index (UK HPI) по лондонским боро
# в таблицу "primary".hm_land_registry__hpi.
# Использование: ./load.sh [<релиз>]   (например ./load.sh 2026-07)
# Без аргумента релиз определяется сам: берётся самый свежий из доступных.
# Каждый запуск полностью заменяет таблицу — релиз пересчитывает предыдущие
# 12 месяцев, так что догрузка «только нового хвоста» дала бы устаревшие числа.
set -euo pipefail
cd "$(dirname "$0")"

TBL='"primary".hm_land_registry__hpi'

source ../../db.env

mkdir -p data

# Полная выгрузка лежит на публичном S3 HM Land Registry, имя файла содержит
# месяц релиза. Ссылки на все файлы релиза перечислены на странице gov.uk
# «UK House Price Index: data downloads <месяц год>», но сама ссылка на CSV
# стабильна и строится по шаблону.
url_for() {
    echo "https://publicdata.landregistry.gov.uk/market-trend-data/house-price-index-data/UK-HPI-full-file-$1.csv"
}

# YYYY-MM, на $1 месяцев назад. Сначала день месяца сбрасывается в 1, иначе
# 31-го числа вычитание месяца уезжает не туда. Первая форма — BSD/macOS date,
# вторая — GNU date.
month_back() {
    date -v1d -v-"$1"m +%Y-%m 2>/dev/null \
        || date -d "$(date +%Y-%m-01) -$1 month" +%Y-%m
}

# Релизы выходят с лагом примерно в два месяца, а в кризисных ситуациях
# публикация сдвигается — поэтому пробуем месяцы по очереди, от текущего назад.
find_release() {
    local i release code
    for i in $(seq 0 12); do
        release=$(month_back "$i")
        code=$(curl -sIL --retry 2 --retry-delay 3 --max-time 60 \
                    -o /dev/null -w '%{http_code}' "$(url_for "$release")")
        if [ "$code" = 200 ]; then
            printf '%s\n' "$release"
            return 0
        fi
    done
    echo "не нашёл полную выгрузку UK HPI ни за один из последних 13 месяцев" >&2
    return 1
}

load() {
    local release=$1
    local url csv london last_modified
    url=$(url_for "$release")
    csv=data/uk-hpi-full-file-$release.csv
    london=data/london-$release.csv

    # S3 отдаёт Last-Modified, по нему и сверяем: файл релиза может переехать
    # (переиздание с исправлениями) при том же имени.
    echo "==> [$release] Проверяю версию в источнике"
    last_modified=$(curl -fsIL --retry 3 --retry-delay 5 --max-time 60 "$url" \
                    | tr -d '\r' | sed -n 's/^[Ll]ast-[Mm]odified: *//p' | tail -1)

    if [ -s "$csv" ] && [ -n "$last_modified" ] \
       && [ "$(cat "$csv.version" 2>/dev/null)" = "$last_modified" ]; then
        echo "==> [$release] Не менялся с $last_modified, качать не нужно"
    else
        echo "==> [$release] Качаю полную выгрузку (~35 МБ)"
        curl -fL --progress-bar --retry 3 --retry-delay 5 -o "$csv" "$url"
        printf '%s\n' "$last_modified" > "$csv.version"
    fi

    # \copy грузит CSV позиционно, поэтому порядок колонок в ddl.sql сверяется
    # с заголовком файла до заливки, а не после.
    echo "==> [$release] Сверяю заголовок выгрузки с ddl.sql"
    python3 -I lib/check_header.py "$csv" sql/ddl.sql

    echo "==> [$release] Отбираю Лондон и агрегаты для нормировки"
    python3 -I lib/filter_london.py "$csv" > "$london"

    # datestyle DMY — в источнике дата записана как DD/MM/YYYY.
    echo "==> [$release] Заливаю в $TBL"
    psql "$PGCONN" -w -v ON_ERROR_STOP=1 --single-transaction -q \
         -c "set client_min_messages = warning" \
         -c "set datestyle = 'ISO, DMY'" \
         -f sql/ddl.sql \
         -c "truncate $TBL" \
         -c "\\copy $TBL from '$london' with (format csv, header)"

    echo "==> [$release] Обновляю статистику"
    psql "$PGCONN" -w -v ON_ERROR_STOP=1 -q -c "analyze $TBL"

    psql "$PGCONN" -w -v ON_ERROR_STOP=1 -f sql/verify.sql
}

if [ $# -gt 0 ]; then
    case $1 in
        [0-9][0-9][0-9][0-9]-[0-9][0-9]) RELEASE=$1 ;;
        *) echo "релиз задаётся как YYYY-MM, например 2026-07: $1" >&2; exit 2 ;;
    esac
else
    RELEASE=$(find_release)
    echo "==> Самый свежий доступный релиз: $RELEASE"
fi

load "$RELEASE"
