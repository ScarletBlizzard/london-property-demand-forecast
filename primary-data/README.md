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

## 👮 police.uk — Street-level crime

Зарегистрированные преступления по всем 43 полицейским силам Англии, Уэльса и Северной
Ирландии, по месяцам — включая и Metropolitan Police, и City of London Police.

| | |
| --- | --- |
| **Владелец** | Home Office (data.police.uk) |
| **Покрытие** | Англия, Уэльс, Северная Ирландия; скользящее окно ~3 года, месячная гранулярность |
| **География** | LSOA (координаты анонимизированы snap-to-point) |
| **Формат** | CSV |
| **Данные** | [data.police.uk/data](https://data.police.uk/data/) |
| **Лицензия** | [Open Government License v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) |

Отсюда берём **общее число преступлений по району за месяц** — в первую очередь чтобы закрыть
пробел по City of London Police.

> [!WARNING]
> Все преступления сведены в **14 укрупнённых категорий**, и `Burglary` среди них —
> без разделения на жилые и нежилые помещения. Выделить взломы жилья по этому источнику
> нельзя — для этого нужен MPS Recorded Crime.
>
> Окно скачивания — последние ~3 года; за более ранние периоды нужны архивные выгрузки.
> Данные ретроспективно уточняются (переклассификация преступлений, уточнение локаций),
> поэтому фиксируем дату выгрузки.

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

## 📰 The GDELT Project — Global Knowledge Graph (GKG)

Глобальная база знаний, извлекающая из новостных публикаций сведения о людях, организациях,
местах, темах и эмоциональной тональности материалов. GDELT 2.0 обрабатывает новости на 65 языках
и обновляет данные каждые 15 минут. Чтобы не скачивать полные массивы GKG, нужные записи можно
выбрать в BigQuery по датам, упоминаниям Лондона и темам недвижимости, оставив только необходимые
поля. Результат запроса можно агрегировать по дням или месяцам.

| | |
| --- | --- |
| **Владелец** | The GDELT Project |
| **Покрытие** | Новости со всего мира, 65 языков; GDELT 2.0 — с февраля 2015 года |
| **Формат** | BigQuery; результаты выборки доступны для выгрузки в CSV |
| **Данные** | [GDELT 2.0 GKG в BigQuery](https://console.cloud.google.com/bigquery?project=gdelt-bq&d=gdeltv2&p=gdelt-bq&page=dataset) · [описание данных](https://gdeltproject.org/data.html) |
| **Лицензия** | Свободное использование и распространение без платы; при использовании нужно указать The GDELT Project и ссылку на [сайт проекта](https://www.gdeltproject.org/) |

**Таблица:** `"primary".gdelt__gkg_london` — выбранные записи и поля GKG для новостных
упоминаний Лондона и недвижимости.

Для экономии объёма в BigQuery следует использовать партиционированную таблицу
`gdelt-bq.gdeltv2.gkg_partitioned`, ограничивать партиции по `_PARTITIONTIME` и выбирать только
необходимые столбцы (например, `DATE`, `V2Locations`, `V2Themes`, `V2Tone`). Бесплатный лимит BigQuery — 1 TiB
обработанных данных в месяц; перед запуском объём сканирования нужно оценивать для конкретного
запроса. Фильтр по Лондону и темам снижает число результатов, но сам по себе не гарантирует
снижение объёма сканирования.

`V2Tone` — тональность статьи целиком, а не отдельного фрагмента о недвижимости. Упоминание
Лондона также не гарантирует географическую привязку к конкретному боро. Эти записи можно
использовать для новостных признаков по Лондону, а месячные признаки формировать на следующем шаге.

## 🚇 TfL — Public Transport Accessibility Levels (PTAL)

Индекс транспортной доступности Лондона от Transport for London. Считается из времени
пешком до остановок и станций, частоты сообщения на них и среднего времени ожидания;
скорость поездки, пересадки и загруженность транспорта не учитываются. Публикуется в
двух видах: непрерывный Accessibility Index и его разбивка на категории 0…6b.

| | |
| --- | --- |
| **Владелец** | Transport for London |
| **Покрытие** | Greater London целиком; статический срез, не ряд |
| **География** | сетка 100×100 м, LSOA, MSOA, Ward |
| **Формат** | CSV (также GeoJSON, Shapefile, ArcGIS REST) |
| **Данные** | [релиз 2023 — ArcGIS-портал TfL](https://gis-tfl.opendata.arcgis.com/datasets/TfL::lsoa-aggregated-ptal-stats-2023) · [релиз 2015 — London Datastore](https://data.london.gov.uk/dataset/public-transport-accessibility-levels-24rz6) · [методика расчёта](https://data.london.gov.uk/download/24rz6/86bbffe1-8af1-49ba-ac9b-b3eacaf68137/connectivity-assessment-guide.pdf) |
| **Лицензия** | релиз 2023 — [OGL v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/), `Contains OS data © Crown copyright and database right 2023`; релиз 2015 — [OGL v2.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/2/) |

**Таблицы:** `"primary".tfl__ptal_lsoa_2023` — 4 994 LSOA по границам 2021 года,
`"primary".tfl__ptal_lsoa_2015` — 4 835 LSOA по границам 2011 года.

Рабочий признак — релиз 2023. Релиз 2015 посчитан по периоду 2008–2014 и не знает ни
Elizabeth line, ни продления Northern line до Battersea, ни Barking Riverside; он нужен
только для сопоставления двух срезов.

Грузим уровень LSOA, а не боро: до боро сворачивается запросом, обратно — нет. На уровне
боро признак почти бесполезен — `AvPTAI` коррелирует с долей квартир в сделках.
Ценность PTAL в том, что он **экзогенен**:
доля квартир и медианная цена выводятся из тех же сделок, которые мы предсказываем, и в
сервисе их на будущий месяц взять негде, а PTAL может подставляться в прогноз на любую дату.

Как загрузить и обновлять — [README загрузчика](loaders/tfl__ptal/README.md).

> [!WARNING]
> В релизе 2023 колонка `borough` битая: атрибуция расходится у 434 LSOA из 4 994 (8,7%),
> всегда на соседний боро. Боро надо выводить из `lsoa21nm` или из официального lookup
> LSOA21 → LAD с [geoportal.statistics.gov.uk](https://geoportal.statistics.gov.uk).
>
> Разницу между релизами нельзя трактовать как изменение доступности: она смешивает
> новую инфраструктуру с сокращением автобусного обслуживания после пандемии и
> возможными правками методики. У Wandsworth AI падает на 13%, хотя в сентябре 2021
> там открыли две новые станции Northern line. Для временной оси надёжнее кодировать
> даты открытия линий руками.
