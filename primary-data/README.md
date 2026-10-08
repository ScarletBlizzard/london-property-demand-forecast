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
| **Покрытие** | Англия и Уэльс |
| **Формат** | CSV |
| **Данные** | [get-energy-performance-data.communities.gov.uk](https://get-energy-performance-data.communities.gov.uk) |
| **Лицензия** | [Open Government License v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) |

**Таблицы:** `"primary".epc__domestic`, `epc__non_domestic`, `epc__display` — только
Greater London.

Как загрузить и обновлять —
[README загрузчика](loaders/energy-performance-certificates__certificates/README.md).

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
