-- Таблица первичных данных: UK House Price Index (UK HPI), месячные ряды
-- по 33 лондонским боро плюс агрегаты London / England / United Kingdom.
--
-- Колонки идут в том же порядке, что и в полной выгрузке
-- UK-HPI-full-file-<YYYY>-<MM>.csv, имена переведены в snake_case:
-- AveragePrice -> average_price, IndexSA -> index_sa, FTBPrice -> ftb_price,
-- 1m%Change -> change_1m_pct, Detached12m%Change -> detached_change_12m_pct.
-- Порядок сверяется машинно перед каждой заливкой: lib/check_header.py.
--
-- Официальное описание полей — раздел 8.2 "Format of data" в
-- https://www.gov.uk/government/publications/about-the-uk-house-price-index/about-the-uk-house-price-index
-- Там же: 4.4 — политика ревизий, 8.4 — сезонное сглаживание, 8.6 — объёмы сделок.
--
-- Общее по всем колонкам:
--   *_price         — средняя цена в фунтах, целое, без дефлятора;
--   *_index         — индекс цен, база январь 2023 = 100, один знак после запятой;
--   *_change_1m_pct, *_change_12m_pct — процентное изменение средней цены
--                     к предыдущему месяцу и к тому же месяцу год назад;
--   *_sales_volume  — число ЗАРЕГИСТРИРОВАННЫХ сделок за месяц.
-- Пустое значение в источнике приезжает как NULL.

create table if not exists "primary".hm_land_registry__hpi (
    date                         date not null,
    region_name                  text not null,
    area_code                    text not null,
    average_price                integer,
    index                        numeric,
    index_sa                     numeric,
    change_1m_pct                numeric,
    change_12m_pct               numeric,
    average_price_sa             integer,
    sales_volume                 integer,
    detached_price               integer,
    detached_index               numeric,
    detached_change_1m_pct       numeric,
    detached_change_12m_pct      numeric,
    semi_detached_price          integer,
    semi_detached_index          numeric,
    semi_detached_change_1m_pct  numeric,
    semi_detached_change_12m_pct numeric,
    terraced_price               integer,
    terraced_index               numeric,
    terraced_change_1m_pct       numeric,
    terraced_change_12m_pct      numeric,
    flat_price                   integer,
    flat_index                   numeric,
    flat_change_1m_pct           numeric,
    flat_change_12m_pct          numeric,
    cash_price                   integer,
    cash_index                   numeric,
    cash_change_1m_pct           numeric,
    cash_change_12m_pct          numeric,
    cash_sales_volume            integer,
    mortgage_price               integer,
    mortgage_index               numeric,
    mortgage_change_1m_pct       numeric,
    mortgage_change_12m_pct      numeric,
    mortgage_sales_volume        integer,
    ftb_price                    integer,
    ftb_index                    numeric,
    ftb_change_1m_pct            numeric,
    ftb_change_12m_pct           numeric,
    foo_price                    integer,
    foo_index                    numeric,
    foo_change_1m_pct            numeric,
    foo_change_12m_pct           numeric,
    new_price                    integer,
    new_index                    numeric,
    new_change_1m_pct            numeric,
    new_change_12m_pct           numeric,
    new_sales_volume             integer,
    old_price                    integer,
    old_index                    numeric,
    old_change_1m_pct            numeric,
    old_change_12m_pct           numeric,
    old_sales_volume             integer,
    primary key (area_code, date)
);

comment on table "primary".hm_land_registry__hpi is
    'UK House Price Index (UK HPI), полная месячная выгрузка UK-HPI-full-file-<YYYY>-<MM>.csv, '
    'отфильтрованная по Лондону: 33 боро (area_code E09......) плюс агрегаты '
    'London (E12000007), England (E92000001) и United Kingdom (K02000001) для нормировки. '
    'Боро — с января 1995 по месяц релиза; у агрегатов есть обратный ряд с 1968 года. '
    'Колонки и значения как в источнике, без очистки; имена приведены к snake_case. '
    'Владелец: HM Land Registry совместно с ONS, Registers of Scotland и '
    'Land & Property Services NI. Лицензия OGL v3.0. '
    'Описание полей: https://www.gov.uk/government/publications/about-the-uk-house-price-index/about-the-uk-house-price-index (раздел 8.2). '
    'ВАЖНО: любой релиз пересчитывает предыдущие 12 месяцев (раздел 4.4), а объёмы сделок '
    'за два последних месяца релиза не публикуются вовсе (раздел 8.6) — см. комментарий к sales_volume.';

comment on column "primary".hm_land_registry__hpi.date is
    'Месяц, к которому относится статистика: всегда первое число месяца. '
    'В источнике дата записана как DD/MM/YYYY, поэтому COPY выполняется с datestyle = ''ISO, DMY''';
comment on column "primary".hm_land_registry__hpi.region_name is
    'Название территории. Для боро — 33 значения, написание ONS: '
    '"Barking and Dagenham", "City of London", "City of Westminster". '
    'Внимание: с district в hm_land_registry__price_paid напрямую не джойнится — '
    'там боро записаны капсом ("CITY OF WESTMINSTER"), джойнить надо по коду или через upper()';
comment on column "primary".hm_land_registry__hpi.area_code is
    'Код территории ONS. E09000001..E09000033 — лондонские боро (E09000001 = City of London), '
    'E12000007 — регион London, E92000001 — England, K02000001 — United Kingdom. '
    'Ключ для джойна с остальными источниками (у EPC это local_authority, у PTAL — lookup LSOA -> LAD)';
comment on column "primary".hm_land_registry__hpi.average_price is
    'Средняя цена сделки по территории за месяц, фунты, целое. Не медиана: '
    'на уровне боро чувствительна к единичным дорогим сделкам (особенно в City of London)';
comment on column "primary".hm_land_registry__hpi.index is
    'Индекс цен по территории, база январь 2023 = 100. Один знак после запятой. '
    'Это hedonic-индекс (с поправкой на состав жилья), в отличие от average_price';
comment on column "primary".hm_land_registry__hpi.index_sa is
    'Сезонно сглаженный индекс цен, база январь 2023 = 100. '
    'ВСЕГДА NULL на уровне боро: сезонное сглаживание публикуется только для стран и регионов '
    '(раздел 8.4 описания). Непустой только у E12000007 / E92000001 / K02000001 — '
    'это и есть причина, по которой агрегаты оставлены в таблице';
comment on column "primary".hm_land_registry__hpi.change_1m_pct is
    'Изменение average_price к предыдущему месяцу, проценты, один знак. '
    'NULL в первом месяце ряда территории';
comment on column "primary".hm_land_registry__hpi.change_12m_pct is
    'Изменение average_price к тому же месяцу год назад, проценты. NULL в первые 12 месяцев ряда';
comment on column "primary".hm_land_registry__hpi.average_price_sa is
    'Сезонно сглаженная средняя цена, фунты. ВСЕГДА NULL на уровне боро, как и index_sa';
comment on column "primary".hm_land_registry__hpi.sales_volume is
    'ЦЕЛЕВОЙ ПРИЗНАК: число зарегистрированных сделок по территории за месяц, целое. '
    'Считается по электронному реестру на момент выгрузки, поэтому: '
    '(1) за ДВА ПОСЛЕДНИХ МЕСЯЦА РЕЛИЗА значение NULL — HM Land Registry намеренно их не публикует, '
    'чтобы не показывать заведомо недобранные объёмы (раздел 8.6), хотя index и average_price за эти '
    'месяцы уже есть; (2) предыдущие 12 месяцев пересчитываются в каждом релизе вверх, по мере '
    'доезда регистраций (раздел 4.4: первая оценка месяца строится примерно на 40% сделок, '
    'вторая — на 80%, третья — на 85%). Для обучения модели хвост надо отбрасывать или '
    'моделировать досылку отдельно';
comment on column "primary".hm_land_registry__hpi.detached_price is
    'Средняя цена отдельно стоящего дома (detached), фунты. '
    'NULL у City of London за весь ряд: отдельно стоящих домов там в сделках нет';
comment on column "primary".hm_land_registry__hpi.detached_index is
    'Индекс цен на detached, база январь 2023 = 100';
comment on column "primary".hm_land_registry__hpi.detached_change_1m_pct is
    'Изменение detached_price к предыдущему месяцу, проценты';
comment on column "primary".hm_land_registry__hpi.detached_change_12m_pct is
    'Изменение detached_price к тому же месяцу год назад, проценты';
comment on column "primary".hm_land_registry__hpi.semi_detached_price is
    'Средняя цена дома на два хозяина (semi-detached), фунты. NULL у City of London за весь ряд';
comment on column "primary".hm_land_registry__hpi.semi_detached_index is
    'Индекс цен на semi-detached, база январь 2023 = 100';
comment on column "primary".hm_land_registry__hpi.semi_detached_change_1m_pct is
    'Изменение semi_detached_price к предыдущему месяцу, проценты';
comment on column "primary".hm_land_registry__hpi.semi_detached_change_12m_pct is
    'Изменение semi_detached_price к тому же месяцу год назад, проценты';
comment on column "primary".hm_land_registry__hpi.terraced_price is
    'Средняя цена дома в террасной застройке (terraced), фунты. '
    'У City of London ряд рваный — есть только месяцы, где такие сделки были';
comment on column "primary".hm_land_registry__hpi.terraced_index is
    'Индекс цен на terraced, база январь 2023 = 100';
comment on column "primary".hm_land_registry__hpi.terraced_change_1m_pct is
    'Изменение terraced_price к предыдущему месяцу, проценты';
comment on column "primary".hm_land_registry__hpi.terraced_change_12m_pct is
    'Изменение terraced_price к тому же месяцу год назад, проценты';
comment on column "primary".hm_land_registry__hpi.flat_price is
    'Средняя цена квартиры (flat / maisonette), фунты. '
    'Для Лондона это основной сегмент: заполнен у всех 33 боро за весь ряд';
comment on column "primary".hm_land_registry__hpi.flat_index is
    'Индекс цен на квартиры, база январь 2023 = 100';
comment on column "primary".hm_land_registry__hpi.flat_change_1m_pct is
    'Изменение flat_price к предыдущему месяцу, проценты';
comment on column "primary".hm_land_registry__hpi.flat_change_12m_pct is
    'Изменение flat_price к тому же месяцу год назад, проценты';
comment on column "primary".hm_land_registry__hpi.cash_price is
    'Средняя цена сделок без ипотеки (оплата деньгами), фунты. '
    'Разбивка по способу оплаты начинается с ЯНВАРЯ 2012, раньше NULL';
comment on column "primary".hm_land_registry__hpi.cash_index is
    'Индекс цен сделок без ипотеки, база январь 2023 = 100. С января 2012';
comment on column "primary".hm_land_registry__hpi.cash_change_1m_pct is
    'Изменение cash_price к предыдущему месяцу, проценты';
comment on column "primary".hm_land_registry__hpi.cash_change_12m_pct is
    'Изменение cash_price к тому же месяцу год назад, проценты';
comment on column "primary".hm_land_registry__hpi.cash_sales_volume is
    'Число сделок без ипотеки за месяц. С января 2012. '
    'ВНИМАНИЕ: cash_sales_volume + mortgage_sales_volume НЕ РАВНО sales_volume — '
    'способ оплаты известен не по всем сделкам (прямо оговорено в разделе 8.6). '
    'Хвост обрезан сильнее и неровнее, чем у sales_volume';
comment on column "primary".hm_land_registry__hpi.mortgage_price is
    'Средняя цена сделок с ипотекой, фунты. С января 2012';
comment on column "primary".hm_land_registry__hpi.mortgage_index is
    'Индекс цен сделок с ипотекой, база январь 2023 = 100. С января 2012';
comment on column "primary".hm_land_registry__hpi.mortgage_change_1m_pct is
    'Изменение mortgage_price к предыдущему месяцу, проценты';
comment on column "primary".hm_land_registry__hpi.mortgage_change_12m_pct is
    'Изменение mortgage_price к тому же месяцу год назад, проценты';
comment on column "primary".hm_land_registry__hpi.mortgage_sales_volume is
    'Число сделок с ипотекой за месяц. С января 2012. В сумме с cash_sales_volume '
    'не даёт sales_volume — см. комментарий к cash_sales_volume';
comment on column "primary".hm_land_registry__hpi.ftb_price is
    'FTB = first time buyer. Средняя цена сделок, где покупатель приобретает жильё впервые, фунты. '
    'Разбивка по типу покупателя идёт из Regulated Mortgage Survey, то есть ТОЛЬКО по ипотечным '
    'сделкам, и начинается с января 2012';
comment on column "primary".hm_land_registry__hpi.ftb_index is
    'Индекс цен сделок first time buyer, база январь 2023 = 100. С января 2012';
comment on column "primary".hm_land_registry__hpi.ftb_change_1m_pct is
    'Изменение ftb_price к предыдущему месяцу, проценты';
comment on column "primary".hm_land_registry__hpi.ftb_change_12m_pct is
    'Изменение ftb_price к тому же месяцу год назад, проценты';
comment on column "primary".hm_land_registry__hpi.foo_price is
    'FOO = former owner occupier, покупатель, который уже владел жильём (не инвестор-арендодатель). '
    'Средняя цена таких сделок, фунты. С января 2012. '
    'Объёмов сделок в разбивке по типу покупателя источник НЕ даёт — только цены и индексы';
comment on column "primary".hm_land_registry__hpi.foo_index is
    'Индекс цен сделок former owner occupier, база январь 2023 = 100. С января 2012';
comment on column "primary".hm_land_registry__hpi.foo_change_1m_pct is
    'Изменение foo_price к предыдущему месяцу, проценты';
comment on column "primary".hm_land_registry__hpi.foo_change_12m_pct is
    'Изменение foo_price к тому же месяцу год назад, проценты';
comment on column "primary".hm_land_registry__hpi.new_price is
    'Средняя цена новостройки (new build), фунты. Есть с начала ряда, с 1995 года';
comment on column "primary".hm_land_registry__hpi.new_index is
    'Индекс цен на новостройки, база январь 2023 = 100';
comment on column "primary".hm_land_registry__hpi.new_change_1m_pct is
    'Изменение new_price к предыдущему месяцу, проценты';
comment on column "primary".hm_land_registry__hpi.new_change_12m_pct is
    'Изменение new_price к тому же месяцу год назад, проценты';
comment on column "primary".hm_land_registry__hpi.new_sales_volume is
    'Число сделок с новостройками за месяц. Ряд РВАНЫЙ и обрезан сильнее остальных: '
    'регистрация новостройки требует создания новой записи в реестре и идёт дольше '
    '(раздел 4.4), плюс в отдельных боро в отдельные месяцы новостроек просто не продавали. '
    'new_sales_volume + old_sales_volume = sales_volume там, где обе части непустые';
comment on column "primary".hm_land_registry__hpi.old_price is
    'Средняя цена вторичного жилья (existing resold property), фунты. С 1995 года';
comment on column "primary".hm_land_registry__hpi.old_index is
    'Индекс цен на вторичное жильё, база январь 2023 = 100';
comment on column "primary".hm_land_registry__hpi.old_change_1m_pct is
    'Изменение old_price к предыдущему месяцу, проценты';
comment on column "primary".hm_land_registry__hpi.old_change_12m_pct is
    'Изменение old_price к тому же месяцу год назад, проценты';
comment on column "primary".hm_land_registry__hpi.old_sales_volume is
    'Число сделок с вторичным жильём за месяц. Хвост обрезан так же, как у sales_volume — '
    'два последних месяца релиза пустые';
