#!/bin/bash
#
# Загрузка ONS CPIH (Consumer Prices Index including owner occupiers' housing costs)
# в таблицу "primary".ons__cpih.
# Использование: ./load.sh   (аргументов нет — таблица всегда перезаливается целиком)
#
# Каждая серия качается целиком, с начала доступной истории: догружать по месяцам
# нечего, а при перебазировании индекса ONS пересчитывает всю историю, так что
# частичная досылка всё равно оставила бы в таблице смесь двух баз.
set -euo pipefail
cd "$(dirname "$0")"

TBL='"primary".ons__cpih'
CSV=data/cpih.csv
BASE=https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries

# Серии датасета MM23. Зачем именно эти — в README.md.
#   L522 CPIH INDEX 00: ALL ITEMS                     — основной дефлятор
#   L55O CPIH ANNUAL RATE 00: ALL ITEMS               — годовой темп прироста
#   CRQO CPIH INDEX: Excl owner occupiers' housing costs — дефлятор без жилищной части
#   L5PG CPIH INDEX 04: Housing, water, electricity, gas and other fuels
#   L55S CPIH ANNUAL RATE 04: HOUSING, WATER AND FUELS
# Чтобы добавить серию, допишите её CDID сюда: остальной код не трогается.
SERIES=(L522 L55O CRQO L5PG L55S)

source ../../db.env

mkdir -p data

[ $# -eq 0 ] || {
    echo "аргументы не нужны: таблица перезаливается целиком, всеми сериями сразу" >&2
    exit 2
}

# Качает одну серию в data/<cdid>.json и дописывает путь в JSONS.
#
# Версия. У JSON-эндпоинта ONS нет Last-Modified (отдаются только Cache-Control и
# ETag), поэтому сверяем по ETag: он слабый (W/"...--gzip", зависит от сжатия), но
# условный GET эндпоинт поддерживает и на совпадении отвечает 304. Худшее, что
# бывает при ротации кэша Cloudflare, — лишнее скачивание 120 КБ.
# Смысловая версия данных лежит внутри самого JSON — description.releaseDate, дата
# публикации релиза MM23; она едет в колонку release_date и печатается конвертером.
fetch() {
    local cdid=$1
    local lower url json etag
    lower=$(printf '%s' "$cdid" | tr '[:upper:]' '[:lower:]')
    url="$BASE/$lower/mm23/data"
    json="data/$lower.json"

    echo "==> [$cdid] Проверяю версию в источнике"
    etag=$(curl -fsIL --retry 3 --retry-delay 5 "$url" \
           | tr -d '\r' | sed -n 's/^[Ee][Tt]ag: *//p' | tail -1)

    if [ -s "$json" ] && [ -n "$etag" ] \
       && [ "$(cat "$json.version" 2>/dev/null)" = "$etag" ]; then
        echo "==> [$cdid] Не менялся с прошлой загрузки, качать не нужно"
    else
        echo "==> [$cdid] Качаю JSON"
        curl -fL --progress-bar --retry 3 --retry-delay 5 -o "$json" "$url"
        printf '%s\n' "$etag" > "$json.version"
    fi

    JSONS+=("$json")
}

JSONS=()
for s in "${SERIES[@]}"; do fetch "$s"; done

# Источник отдаёт JSON, в базу грузим через \copy ... format csv — отсюда конвертер.
# Он же проверяет выгрузки: неизвестный месяц, нечисловое значение, повтор месяца
# внутри серии роняют загрузку до обращения к базе. Порядок колонок в CSV задан
# в lib/cpih_to_csv.py и совпадает с порядком в sql/ddl.sql.
echo "==> Собираю CSV из ${#JSONS[@]} серий"
python3 -I lib/cpih_to_csv.py "${JSONS[@]}" > "$CSV"

echo "==> Заливаю в $TBL"
psql "$PGCONN" -w -v ON_ERROR_STOP=1 --single-transaction -q \
     -c "set client_min_messages = warning" \
     -f sql/ddl.sql \
     -c "truncate $TBL" \
     -c "\\copy $TBL from '$CSV' with (format csv, header)"

echo "==> Обновляю статистику"
psql "$PGCONN" -w -v ON_ERROR_STOP=1 -q -c "analyze $TBL"

psql "$PGCONN" -w -v ON_ERROR_STOP=1 -f sql/verify.sql
