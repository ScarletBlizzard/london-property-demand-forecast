# ⚡ Загрузчик: Energy Performance Certificates

Наполняет таблицы `"primary".epc__domestic`, `epc__non_domestic`, `epc__display`
сертификатами по Greater London (районы `local_authority` с кодом `E09...`).
Подключение к БД и пароль — в [DB.md](../../DB.md).

Нужны `psql`, `curl`, `unzip` и `python3`, сторонние библиотеки не требуются.

## Токен API

Нужен bearer-токен от [get-energy-performance-data.communities.gov.uk](https://get-energy-performance-data.communities.gov.uk).
Токен личный и для его получения требуется регистрация на сайте. Токен необходимо положить в `.env` рядом со скриптом:

```bash
cp .env.example .env   # и впишите EPC_TOKEN
```

## Как пользоваться

```bash
cd primary-data/loaders/energy-performance-certificates

./load.sh                # все три набора
./load.sh domestic       # один набор: domestic | non-domestic | display
```

Каждый запуск полностью заменяет таблицу — полный архив в источнике пересобирается
1-го числа каждого месяца, поэтому запускать имеет смысл раз в месяц. Если архив не
менялся (`lastUpdated` из `/info`), повторно он не скачивается. Прерванная загрузка
на следующем запуске продолжается с того же места.

Размеры архивов: domestic ~8 ГБ, non-domestic ~0,25 ГБ, display ~0,1 ГБ.
Архив читается потоком (`unzip -p`), распаковка на диск не нужна.

Параметры подключения берутся из общего [db.env](../../db.env). Чтобы залить в другую базу,
переопределите `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` в окружении.

## Что загружается

Только `certificates-*.csv` из архива. Файлы `recommendations-*.csv` (рекомендации по
улучшению, без привязки к району) не грузим.

## Файлы

| Файл | Назначение |
| --- | --- |
| `load.sh` | скачивание, фильтр, заливка |
| `lib/filter_london.py` | отбор Greater London из склеенных годовых CSV |
| `sql/ddl_domestic.sql` | схема, первичный ключ и индексы `epc__domestic` |
| `sql/ddl_non_domestic.sql` | то же для `epc__non_domestic` |
| `sql/ddl_display.sql` | то же для `epc__display` |
| `sql/verify.sql` | итоговая сводка по таблице |
| `.env.example` | шаблон для `.env` с токеном |
