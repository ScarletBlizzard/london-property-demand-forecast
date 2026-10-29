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

## 🏷️ HMRC — Monthly property transactions (£40 000+)

Число завершённых сделок с недвижимостью по Великобритании за месяц — по данным налоговых
баз SDLT (HMRC), LBTT (Revenue Scotland) и LTT (Welsh Revenue Authority). Сделка считается
по дате завершения (completion) и попадает в статистику только при стоимости выше £40 000.
Общенациональный индикатор активности рынка: быстрее Land Registry, но без разбивки по районам.

| | |
| --- | --- |
| **Владелец** | HM Revenue & Customs |
| **Покрытие** | Великобритания, апрель 2005 — н. в., месячная гранулярность |
| **География** | нет разбивки по районам — только UK целиком и четыре страны (Англия, Шотландия, Уэльс, Северная Ирландия) |
| **Формат** | ODS (одна книга, имя файла меняется с каждым релизом) |
| **Данные** | [gov.uk — monthly property transactions](https://www.gov.uk/government/statistics/monthly-property-transactions-completed-in-the-uk-with-value-40000-or-above) · [методика](https://www.gov.uk/government/statistics/monthly-property-transactions-completed-in-the-uk-with-value-40000-or-above/uk-monthly-property-transactions-background-and-references) |
| **Лицензия** | [Open Government License v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) |

**Таблица:** `"primary".hmrc__property_transactions` — 257 месяцев, апрель 2005 — н. в.,
только лист `Residential_monthly` (жилая недвижимость). Квартальные, финансовые годы и
нежилую недвижимость из той же книги не грузим.

Как загрузить и обновлять — [README загрузчика](loaders/hmrc__property-transactions/README.md).

> [!WARNING]
> **Три последних месяца ряда предварительные** и в следующих релизах изменятся:
> последний считается по снимку базы SDLT с дотяжкой на неполученные декларации
> (`[provisional estimates]`), два предыдущих ещё не устоялись (`[provisional]`).
> Пометка в источнике написана прямо в поле с датой — `August 2026 [provisional estimates]` —
> и наивный разбор даты молча выбрасывает три самых свежих месяца. В таблице признак
> вынесен в колонку `provisional`; для обучения модели эти месяцы лучше отбрасывать.
>
> Ссылку на файл нельзя зашивать: имя вложения меняется с каждым релизом
> (`MPT_Tab_Sep_26.ods`), загрузчик каждый раз вытаскивает её со страницы публикации.

> [!NOTE]
> Все значения — число сделок, округлённое до десятков. Пояснение на самом листе
> («rounded and reported by thousand transactions») вводит в заблуждение: это не тысячи
> сделок, домножать ни на что не надо.
>
> Шотландия с апреля 2015 и Уэльс с апреля 2018 приходят не из базы HMRC, а фидами от
> Revenue Scotland и WRA — разрыв методики на этих датах заложен в сам ряд. Колонка
> `uk_seasonally_adjusted` — сезонно сглаженный итог по Великобритании (X-13ARIMA);
> по странам сглаженных рядов источник не даёт.

## 📈 HM Land Registry — UK House Price Index (UK HPI)

Официальный индекс цен на жильё: месячные ряды индекса, средней цены и **объёма
зарегистрированных сделок** по лондонским боро, с разбивками по типу жилья, типу
покупателя, способу оплаты и новизне.

| | |
| --- | --- |
| **Владелец** | HM Land Registry совместно с ONS, Registers of Scotland и Land & Property Services NI |
| **Покрытие** | Великобритания; боро — с января 1995, агрегаты — с 1968 года; месячная гранулярность |
| **География** | страна, регион, county/unitary authority, local authority, лондонское боро |
| **Формат** | CSV (также SPARQL / linked data) |
| **Данные** | [gov.uk — UK House Price Index: data downloads](https://www.gov.uk/government/statistical-data-sets/uk-house-price-index-data-downloads-july-2026) · [обозреватель данных](https://landregistry.data.gov.uk/app/ukhpi) · [описание полей и методика](https://www.gov.uk/government/publications/about-the-uk-house-price-index/about-the-uk-house-price-index) |
| **Лицензия** | [Open Government License v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) |

**Таблица:** `"primary".hm_land_registry__hpi` — 14 607 строк в релизе 2026-07:
33 района (32 боро + City of London) с января 1995 плюс агрегаты London
(`E12000007`), England (`E92000001`) и United Kingdom (`K02000001`) для
нормировки.

Это основной источник целевого признака: `sales_volume` — число
зарегистрированных сделок по боро за месяц. Агрегаты оставлены не только для
нормировки: сезонно сглаженные ряды (`index_sa`, `average_price_sa`) в UK HPI
публикуются лишь на уровне стран и регионов, на уровне боро они всегда пустые.

Как загрузить и обновлять —
[README загрузчика](loaders/hm-land-registry__hpi/README.md).

> [!WARNING]
> **Объём сделок отстаёт от индекса цен на два месяца.** HM Land Registry
> намеренно не публикует `sales_volume` за два последних месяца релиза, чтобы не
> показывать заведомо недобранные объёмы: в релизе 2026-07 индекс есть по
> 2026-07, а объёмы — только по 2026-05. Лаг проверяется при каждой загрузке.
>
> Хвост объёмов вдобавок занижен: каждый релиз пересчитывает предыдущие
> 12 месяцев вверх по мере доезда регистраций (первая оценка месяца строится
> примерно на 40% сделок, вторая — на 80%, третья — на 85%). Последний год
> объёмов для обучения либо отбрасывается, либо досылка моделируется отдельно.

> [!NOTE]
> `cash_sales_volume + mortgage_sales_volume` **не равно** `sales_volume` —
> способ оплаты известен не по всем сделкам (почти половина боро-месяцев расходится).
> А `new_sales_volume + old_sales_volume = sales_volume` сходится точно.
>
> Разбивки по способу оплаты и типу покупателя (`cash_*`, `mortgage_*`, `ftb_*`,
> `foo_*`) начинаются только с января 2012 — они строятся по Regulated Mortgage
> Survey, а не по реестру. Объёмов по типу покупателя источник не даёт вовсе.
>
> База индекса — **январь 2023 = 100**, а не 2015 год, как в старых публикациях.
>
> С `hm_land_registry__price_paid` таблица джойнится по `area_code`, а не по
> имени: в UK HPI боро записаны по ONS (`City of Westminster`), в Price Paid
> Data — капсом (`CITY OF WESTMINSTER`).

## 🏘️ ONS — Price Index of Private Rents (PIPR)

Месячный индекс цен частной аренды от ONS: уровень арендных цен, месячное и годовое
изменение в процентах и средняя арендная плата в фунтах — по районам (local authority),
с разбивкой по числу спален и типу жилья. Строится на административных данных о реальных
договорах, а не на опросах, и охватывает как новые, так и действующие договоры.

| | |
| --- | --- |
| **Владелец** | Office for National Statistics |
| **Покрытие** | Великобритания, январь 2015 — н. в., месячная гранулярность |
| **География** | UK, страны, регионы Англии, местные власти Англии и Уэльса, BRMA Шотландии и Северной Ирландии |
| **Формат** | XLSX (один лист с плоской таблицей) |
| **Данные** | [ons.gov.uk — Price Index of Private Rents, UK: monthly price statistics](https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/priceindexofprivaterentsukmonthlypricestatistics) · [бюллетень](https://www.ons.gov.uk/economy/inflationandpriceindices/bulletins/privaterentandhousepricesuk/latest) · [методика (QMI)](https://www.ons.gov.uk/peoplepopulationandcommunity/housing/methodologies/priceindexofprivaterentsqmi) |
| **Лицензия** | [Open Government License v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) |

**Таблица:** `"primary".ons__pipr` — 4 480 строк: 32 района Лондона x 140 месяцев,
январь 2015 — н. в. Грузится плоско, как в источнике: 40 колонок, четыре метрики
(`index`, `monthly_change`, `annual_change`, `rental_price`) в девяти разрезах.

База индекса — **январь 2023 = 100**, ряд **не сезонно сглажен**, изменения указаны
**в процентах, а не в долях**.

Как загрузить и обновлять — [README загрузчика](loaders/ons__pipr/README.md).

> [!WARNING]
> **City of London в источнике отсутствует** — отбор по кодам `E09` даёт 32 района,
> а не 33. ONS не публикует City of London (и Isles of Scilly) из-за малого объёма
> собранных данных. Признака по аренде для City of London из PIPR не будет вообще.
>
> **PIPR заменил устаревший Index of Private Housing Rental Prices (IPHRP)** — с релиза
> за март 2024. IPHRP больше не обновляется, тащить его в проект не надо. Сцепленная
> историческая серия IPHRP + PIPR у ONS есть, но только для UK, стран и регионов Англии;
> по районам её нет, а методика в январе 2015 менялась.
>
> **Последние два месяца ряда предварительные** (two-month revision policy ONS) и
> пересчитываются в следующих релизах — хвост для обучения лучше отбрасывать.

> [!NOTE]
> Северная Ирландия вошла в сам PIPR только с релиза за **март 2025** (26 марта 2025):
> до него PIPR покрывал Great Britain, а UK-агрегат собирался из PIPR по GB и IPHRP по
> Северной Ирландии. Текущая выгрузка пересчитана назад до января 2015, поэтому внутри
> одного файла ряд однородный, но национальные агрегаты из старых и новых выгрузок
> между собой не совпадут. На лондонские районы это не влияет.

## 💷 ONS CPIH — Consumer Prices Index including owner occupiers' housing costs

Индекс потребительских цен Великобритании с расходами собственников на жильё (OOH) и
налогом на недвижимость. Ведущий показатель инфляции у ONS. Месячная гранулярность.

| | |
| --- | --- |
| **Владелец** | Office for National Statistics |
| **Покрытие** | Великобритания в целом, с 1988 года, месячная гранулярность |
| **География** | нет разбивки — показатель общенациональный |
| **Формат** | JSON (API временных рядов), также CSV/XLSX выгрузкой |
| **Данные** | [ONS — consumer price inflation time series (MM23)](https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/consumerpriceindices) · [API серии: `.../timeseries/l522/mm23/data`](https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/l522/mm23) |
| **Лицензия** | [Open Government License v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) |

**Таблица:** `"primary".ons__cpih` — пять серий MM23 в одной таблице (серия в колонке
`cdid`), около 2 300 месячных наблюдений: `L522` — индекс всех товаров и услуг,
`L55O` — его годовой темп прироста, `CRQO` — индекс без расходов собственников на
жильё, `L5PG` и `L55S` — индекс и годовой темп прироста дивизиона 04 (жильё, вода,
электричество, газ, топливо).

Нужен как **дефлятор**: окно данных идёт с 1995 года, а уровень цен с января 1995 по
август 2026 вырос в 2,19 раза — без перевода цен в реальные модель выучит инфляцию
вместо спроса. Жилищная компонента добавлена как отдельный признак: энергетический
шок 2022 года и всплеск аренды в общем индексе размазаны, а `CRQO` даёт дефлятор, в
котором нет расходов на жильё, — чтобы не делить цены на жильё частично на само себя.

Как загрузить и обновлять — [README загрузчика](loaders/ons__cpih/README.md).

> [!WARNING]
> Индексы начинаются с января 1988, годовые темпы прироста — с января 1989: первые
> 12 месяцев прироста не определены по построению. Сопоставлять серии между собой
> нужно внешним джойном, `inner join` молча отрежет 1988 год.
>
> Дефлировать цены надо индексом, а не темпом прироста: темп округлён до 0,1 п.п.,
> и восстановленный из него уровень накапливает ошибку за 30 лет истории.
>
> Официальная серия CPIH ведётся с 2013 года, история до этого достроена назад
> ретроспективно (у части серий дивизиона 04 ONS сам ставит в заголовке пометку
> `est. pre-97`), поэтому на раннюю часть окна опираться стоит с оглядкой. Статус
> accredited official statistics у CPIH был приостановлен в 2014 году из-за методики
> оценки OOH и возвращён 31 июля 2017.

> [!NOTE]
> Текущая база индекса — `2015 = 100`. При перебазировании ONS пересчитывает всю
> историю и меняет заголовок серии, поэтому таблица всегда перезаливается целиком.
> База хранится в колонке `title` каждой строки, так что смена базы видна в данных.
>
> У JSON-эндпоинта ONS нет `Last-Modified` — версия сверяется по `ETag`, а
> смысловая дата релиза лежит внутри выгрузки (`description.releaseDate`) и попадает
> в колонку `release_date`. Релиз выходит во второй половине месяца за предыдущий
> месяц, так что хвост ряда отстаёт от календаря примерно на месяц.
