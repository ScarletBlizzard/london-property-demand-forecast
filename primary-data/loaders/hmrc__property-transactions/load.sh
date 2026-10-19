#!/bin/bash
#
# Загрузка HMRC — Monthly property transactions completed in the UK with value
# of £40,000 or above, лист Residential_monthly, в таблицу
# "primary".hmrc__property_transactions.
# Использование: ./load.sh
# Каждый запуск полностью заменяет таблицу: источник — одна книга ODS со всем
# рядом с апреля 2005, и в каждом релизе HMRC пересчитывает хвост ряда, так что
# догружать нечего, а перезаливать надо целиком.
set -euo pipefail
cd "$(dirname "$0")"

TBL='"primary".hmrc__property_transactions'
ODS=data/mpt.ods
CSV=data/residential-monthly.csv

# Имя файла вложения меняется с каждым релизом (MPT_Tab_Sep_26.ods), поэтому
# ссылку берём со страницы публикации. $PAGE — человеческая версия страницы,
# $API — она же в Content API gov.uk, из неё список вложений читается как JSON.
PAGE=https://www.gov.uk/government/statistics/monthly-property-transactions-completed-in-the-uk-with-value-40000-or-above
API=https://www.gov.uk/api/content/government/statistics/monthly-property-transactions-completed-in-the-uk-with-value-40000-or-above

source ../../db.env

mkdir -p data

echo "==> Ищу вложение ODS на странице публикации"
echo "    $PAGE"
URL=$(curl -fsL --retry 3 --retry-delay 5 "$API" | python3 -I lib/attachment_url.py)
echo "    $URL"

# Вложение отдаёт Last-Modified, по нему и сверяем версию. В ключ версии входит
# и сама ссылка: новый релиз — это новый файл с новым именем.
LAST_MODIFIED=$(curl -fsIL --retry 3 --retry-delay 5 "$URL" \
                | tr -d '\r' | sed -n 's/^[Ll]ast-[Mm]odified: *//p' | tail -1)
VERSION="$URL $LAST_MODIFIED"

if [ -s "$ODS" ] && [ -n "$LAST_MODIFIED" ] \
   && [ "$(cat "$ODS.version" 2>/dev/null)" = "$VERSION" ]; then
    echo "==> Не менялся с $LAST_MODIFIED, качать не нужно"
else
    echo "==> Качаю книгу ODS (меньше 100 КБ)"
    curl -fL --progress-bar --retry 3 --retry-delay 5 -o "$ODS" "$URL"
    printf '%s\n' "$VERSION" > "$ODS.version"
fi

# В книге 7 содержательных листов, грузим только Residential_monthly —
# остальные (non-residential, квартальные, финансовые годы) проекту не нужны,
# см. README. Порядок колонок в sql/ddl.sql совпадает с заголовком этого CSV.
echo "==> Разбираю лист Residential_monthly"
python3 -I lib/ods_to_csv.py "$ODS" > "$CSV"
echo "    строк с данными: $(($(wc -l < "$CSV") - 1))"

echo "==> Заливаю в $TBL"
psql "$PGCONN" -w -v ON_ERROR_STOP=1 --single-transaction -q \
     -c "set client_min_messages = warning" \
     -f sql/ddl.sql \
     -c "truncate $TBL" \
     -c "\\copy $TBL from '$CSV' with (format csv, header)"

echo "==> Обновляю статистику"
psql "$PGCONN" -w -v ON_ERROR_STOP=1 -q -c "analyze $TBL"

echo "==> Результат"
psql "$PGCONN" -w -v ON_ERROR_STOP=1 -f sql/verify.sql
