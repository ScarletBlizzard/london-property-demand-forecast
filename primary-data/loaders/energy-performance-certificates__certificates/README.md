# ⚡ Загрузчик: Energy Performance Certificates

Наполняет таблицы `"primary".epc__domestic`, `epc__non_domestic`, `epc__display`
сертификатами по Greater London (районы `local_authority` с кодом `E09...`).
Подключение к БД и пароль — в [DB.md](../../DB.md).

Нужны `psql`, `curl`, `unzip` и `python3`, сторонние библиотеки не требуются.

## Токен API

Нужен bearer-токен от [get-energy-performance-data.communities.gov.uk](https://get-energy-performance-data.communities.gov.uk).
Токен лежит в `.env` рядом со скриптом (файл в `.gitignore`, **не коммитим**):

```bash
cp .env.example .env   # и впишите EPC_TOKEN
```

## Как пользоваться

```bash
cd primary-data/loaders/energy-performance-certificates__certificates

./load.sh                # все три набора
./load.sh domestic       # один набор: domestic | non-domestic | display
```

Каждый запуск полностью заменяет таблицу — полный архив в источнике пересобирается
1-го числа каждого месяца, поэтому запускать имеет смысл раз в месяц. Если архив не
менялся (`lastUpdated` из `/info`), повторно он не скачивается.

Размеры архивов: domestic ~8 ГБ, non-domestic ~0,25 ГБ, display ~0,1 ГБ.
Архив читается потоком (`unzip -p`), распаковка на диск не нужна.

Чтобы залить в другую базу, переопределите `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`.

## Что загружается

Только `certificates-*.csv` из архива. Файлы `recommendations-*.csv` (рекомендации по
улучшению, без привязки к району) не грузим. Колонки — как в источнике, все `text`;
типы приводим при сборке датасета. Индексы: `local_authority`, `postcode`
(джойн с Price Paid по почтовому индексу).

## Файлы

| Файл | Назначение |
| --- | --- |
| `load.sh` | скачивание, фильтр, заливка |
| `lib/filter_london.py` | отбор Greater London из склеенных годовых CSV |
| `sql/verify.sql` | итоговая сводка по таблице |
| `.env.example` | шаблон для `.env` с токеном |
