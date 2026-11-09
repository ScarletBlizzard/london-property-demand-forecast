# 📖 Источники первичных данных

Каждый источник загружается в схему `primary` [БД первичных данных](DB.md) **отдельной таблицей**,
максимально близко к исходному виду — без предварительной очистки и агрегации.
Итоговый датасет собирается из этих таблиц на следующем шаге.

> [!IMPORTANT]
> Правила именования таблиц с первичными данными в схеме primary:
> [имя_источника]__[имя_таблицы]

> [!NOTE]
> Прежде чем добавлять новый источник, проверьте лицензию: используем только данные,
> разрешённые к свободному использованию (Open Government License и аналоги).

---

## 🏠 HM Land Registry — Price Paid Data

Сделки с недвижимостью по всей Великобритании с 1995 года.

| | |
| --- | --- |
| **Владелец** | UK Government |
| **Покрытие** | Великобритания, 1995 — н. в. |
| **Формат** | CSV |
| **Данные** | [gov.uk — price paid data downloads](https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads) |
| **Лицензия** | [Open Government License v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) |

**Таблица:** `"primary".hm_land_registry__price_paid` — ~4.0 млн сделок, 1995 — н. в.,
33 района (32 боро + City of London).

Как загрузить и обновлять —
[README загрузчика](loaders/hm-land-registry__price-paid/README.md).

> [!NOTE]
> Данные досылаются с лагом в несколько месяцев: последние 1–2 месяца в выборке
> занижены. Для прогноза хвост лучше отбрасывать.

## ⚡ Energy Performance Certificates

Энергетические сертификаты жилых и нежилых зданий, а также общественных зданий Англии и Уэльса.

| | |
| --- | --- |
| **Владелец** | UK Government |
| **Покрытие** | Англия и Уэльс, данные с 2008 (запуск реестра) |
| **Формат** | CSV |
| **Данные** | [get-energy-performance-data.communities.gov.uk](https://get-energy-performance-data.communities.gov.uk) |
| **Лицензия** | [Open Government License v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) |

**Таблицы:** `"primary".epc__domestic`, `epc__non_domestic`, `epc__display` — только
Greater London.

Как загрузить и обновлять —
[README загрузчика](loaders/energy-performance-certificates/README.md).

## 🚨 MPS Recorded Crime: Geographic Breakdown

Зарегистрированные преступления полиции Лондона (Metropolitan Police Service) с разбивкой
по географии и категориям преступлений, по месяцам.

| | |
| --- | --- |
| **Владелец** | Metropolitan Police Service / London Datastore (GLA) |
| **Покрытие** | Лондон (кроме City of London), с 2001 года, месячная гранулярность |
| **География** | Borough, Ward, LSOA |
| **Формат** | CSV |
| **Данные** | [data.london.gov.uk — recorded crime summary](https://data.london.gov.uk/dataset/recorded_crime_summary) |
| **Лицензия** | [Open Government License v2.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/2/) |

Из этого источника нам нужны **общее число преступлений по району за месяц** и отдельно
**взломы жилья** (`Burglary` → residential) за месяц.

> [!WARNING]
> Metropolitan Police **не обслуживает City of London** — этот район патрулирует отдельная
> структура, City of London Police, и её преступления в данный источник не попадают.
> Для покрытия City of London используем [police.uk](#-policeuk--street-level-crime).
>
> На уровне LSOA часть данных скрыта по требованиям защиты персональных данных —
> в частности, детализация по residential burglary. Для разбивки по взломам жилья
> берём уровень Borough или Ward.


## 🏦 Bank of England — Interactive Statistical Database

Макроэкономические и кредитные показатели Банка Англии: ключевая ставка, одобрения ипотек,
ставки по ипотечным продуктам, объёмы ипотечного кредитования. Месячная гранулярность.

| | |
| --- | --- |
| **Владелец** | Bank of England |
| **Покрытие** | Великобритания в целом, с 1975 года (по разным сериям — см. ниже) |
| **География** | нет разбивки — показатели общенациональные |
| **Формат** | CSV (есть URL-эндпоинт для выгрузки), XML |
| **Данные** | [bankofengland.co.uk — Interactive Statistical Database](https://www.bankofengland.co.uk/boeapps/database/) |
| **Лицензия** | [Open Government License v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) |


## 🚇 TfL — Public Transport Accessibility Levels (PTAL)

Индекс транспортной доступности Лондона от Transport for London. Считается из времени
пешком до остановок и станций, частоты сообщения на них и среднего времени ожидания;
скорость поездки, пересадки и загруженность транспорта не учитываются. Публикуется в
двух видах: непрерывный Accessibility Index и его разбивка на категории 0…6b.

| | |
| --- | --- |
| **Владелец** | Transport for London |
| **Покрытие** | Greater London целиком; статический срез, не ряд |
| **География** | сетка 100×100 м, LSOA, MSOA, Ward; Borough для релиза 2015 |
| **Формат** | CSV (также GeoJSON, Shapefile, ArcGIS REST) |
| **Данные** | [релиз 2023 — ArcGIS-портал TfL](https://gis-tfl.opendata.arcgis.com/datasets/TfL::lsoa-aggregated-ptal-stats-2023) · [релиз 2015 — London Datastore](https://data.london.gov.uk/dataset/public-transport-accessibility-levels-24rz6) · [методика расчёта](https://data.london.gov.uk/download/24rz6/86bbffe1-8af1-49ba-ac9b-b3eacaf68137/connectivity-assessment-guide.pdf) |
| **Лицензия** | релиз 2023 — [OGL v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/), `Contains OS data © Crown copyright and database right 2023`; релиз 2015 — [OGL v2.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/2/) |

**Таблицы:** `"primary".tfl__ptal_lsoa_2023`,
`"primary".tfl__ptal_lsoa_2015`,
`"primary".tfl__ptal_borough_2015` — готовый PTAL 2015 по 33 районам.

В итоговом датасете релиз 2015 применяется до января 2023, затем — релиз 2023.

Как загрузить и обновлять — [README загрузчика](loaders/tfl__ptal/README.md).
