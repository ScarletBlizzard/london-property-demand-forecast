-- Таблица первичных данных: ONS — Price Index of Private Rents (PIPR),
-- месячная статистика частной аренды по районам Лондона.
--
-- Грузится плоско и как есть, одной таблицей: имена колонок — snake_case от шапки
-- листа "Table 1" выгрузки ONS, порядок колонок тот же. Порядок сверяется машинно
-- перед каждой заливкой (lib/check_columns.py), потому что \copy раскладывает поля
-- по порядку, а не по именам.
--
-- Что значат показатели — в комментариях к колонкам ниже; официальные описания:
--   бюллетень:      https://www.ons.gov.uk/economy/inflationandpriceindices/bulletins/privaterentandhousepricesuk/latest
--   методика (QMI): https://www.ons.gov.uk/peoplepopulationandcommunity/housing/methodologies/priceindexofprivaterentsqmi
--   выгрузка:       https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/priceindexofprivaterentsukmonthlypricestatistics
--
-- Единственное, что меняется при загрузке (см. lib/sheet_to_csv.py):
--   * "Time period" из excel-серийного номера дня -> date первого числа месяца;
--   * маркеры [x] (данных нет) и [z] (не применимо) в числовых колонках -> NULL.
-- Для Лондона встречается только [x], и ровно там, где его не может не быть:
-- monthly_change пуст в январе 2015 (нет предыдущего месяца), annual_change —
-- во всём 2015 году (нет того же месяца 2014-го). Проверяется в sql/verify.sql.

create table if not exists "primary".ons__pipr (
    time_period                     date not null,
    area_code                       text not null,
    area_name                       text,
    region_or_country_name          text,
    "index"                         numeric,  -- в кавычках для читаемости: index в PostgreSQL не зарезервирован
    monthly_change                  numeric,
    annual_change                   numeric,
    rental_price                    numeric,
    index_one_bed                   numeric,
    monthly_change_one_bed          numeric,
    annual_change_one_bed           numeric,
    rental_price_one_bed            numeric,
    index_two_bed                   numeric,
    monthly_change_two_bed          numeric,
    annual_change_two_bed           numeric,
    rental_price_two_bed            numeric,
    index_three_bed                 numeric,
    monthly_change_three_bed        numeric,
    annual_change_three_bed         numeric,
    rental_price_three_bed          numeric,
    index_four_or_more_bed          numeric,
    monthly_change_four_or_more_bed numeric,
    annual_change_four_or_more_bed  numeric,
    rental_price_four_or_more_bed   numeric,
    index_detached                  numeric,
    monthly_change_detached         numeric,
    annual_change_detached          numeric,
    rental_price_detached           numeric,
    index_semidetached              numeric,
    monthly_change_semidetached     numeric,
    annual_change_semidetached      numeric,
    rental_price_semidetached       numeric,
    index_terraced                  numeric,
    monthly_change_terraced         numeric,
    annual_change_terraced          numeric,
    rental_price_terraced           numeric,
    index_flat_maisonette           numeric,
    monthly_change_flat_maisonette  numeric,
    annual_change_flat_maisonette   numeric,
    rental_price_flat_maisonette    numeric,
    primary key (time_period, area_code)
);

comment on table "primary".ons__pipr is
    'ONS Price Index of Private Rents (PIPR): месячный индекс частной аренды, месячное и годовое '
    'изменение в процентах и уровни средней арендной платы, по районам (local authority). '
    'Оставлены только районы Лондона (area_code вида E09......): 32 боро x 140 месяцев, с января '
    '2015. '
    'City of London (E09000001) в источнике НЕТ: ONS не публикует его и Isles of Scilly из-за малого '
    'объёма собранных данных, поэтому районов 32, а не 33. '
    'Ряд не сезонно сглажен, база индекса — январь 2023 = 100. '
    'PIPR заменил устаревший Index of Private Housing Rental Prices (IPHRP): IPHRP больше не '
    'обновляется, смешивать два ряда нельзя (методика сменилась, ONS отдельно предупреждает об '
    'осторожности при сравнении с данными до 2015 года). '
    'Северная Ирландия вошла в сам PIPR только с релиза за март 2025 (26 марта 2025); до него PIPR '
    'покрывал Great Britain, а UK-агрегат собирался из PIPR по GB и IPHRP по Северной Ирландии. На '
    'лондонские районы это не влияет, на национальные агрегаты в полной выгрузке — влияет. '
    'Последние два месяца ряда предварительные (two-month revision policy ONS). '
    'Источник: '
    'https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/priceindexofprivaterentsukmonthlypricestatistics '
    'Методика (QMI): '
    'https://www.ons.gov.uk/peoplepopulationandcommunity/housing/methodologies/priceindexofprivaterentsqmi '
    'Лицензия: Open Government Licence v3.0, Crown copyright.';

comment on column "primary".ons__pipr.time_period is
    'Месяц наблюдения — первое число месяца. В источнике это колонка "Time period" в виде '
    'excel-серийного номера дня (42005 = 2015-01-01); гранулярность месячная, день всегда 1. '
    'Диапазон: с 2015-01-01, по одному новому месяцу на релиз. Вместе с area_code — первичный ключ. '
    'ВНИМАНИЕ: два последних месяца ряда предварительные и пересчитываются в следующих релизах ONS, '
    'так что хвост в обучении модели лучше не использовать.';
comment on column "primary".ons__pipr.area_code is
    'Код территории ONS (колонка "Area code"). В таблице остаются только районы Лондона — коды вида '
    'E09...... (London borough); так же отбирает Лондон загрузчик EPC. Ключ для джойна с другими '
    'источниками по районам. '
    'В полной выгрузке есть и другие уровни: K02000001 — UK, K03000001 — Great Britain, '
    'E92/W92/S92/N92 — страны, E12 — регионы Англии, E06/E07/E08 — остальные местные власти Англии, '
    'W06 — Уэльс, S33 — Broad Rental Market Area Шотландии; у восьми BRMA Северной Ирландии кода нет '
    'вообще, в источнике там текстовый маркер [z].';
comment on column "primary".ons__pipr.area_name is
    'Имя района по ONS (колонка "Area name"), например "Barking and Dagenham", "Kensington and '
    'Chelsea". Написание ONS — через "and", не через "&". Для Лондона 32 уникальных имени.';
comment on column "primary".ons__pipr.region_or_country_name is
    'Регион или страна, в которые входит район (колонка "Region or country name"). В этой таблице '
    'всегда "London", других значений быть не может; колонка оставлена как в источнике. '
    'В полной выгрузке у самих агрегатов (UK, Great Britain, страны, регионы Англии) тут стоит '
    'текстовый маркер [z] — не применимо.';

comment on column "primary".ons__pipr."index" is
    'Индекс арендных цен всего частного арендного фонда района (без разбивки) (колонка "Index"). База '
    '— январь 2023 = 100 (в данных ровно 100 у каждого района в 2023-01). Безразмерный, не сезонно '
    'сглажен. '
    'Основной признак источника: уровень арендных цен района, приведённый к общей базе, сопоставим и '
    'между районами, и во времени. По Лондону наблюдался диапазон примерно 74…140. В выгрузке до 15 '
    'знаков после запятой, но осмысленных знаков 6: ONS округляет до 6, а показывает 1.';
comment on column "primary".ons__pipr.monthly_change is
    'Изменение индекса всего частного арендного фонда района (без разбивки) к предыдущему месяцу, В '
    'ПРОЦЕНТАХ (колонка "Monthly change"). '
    'Проценты, а не доли: 1.203854 означает +1.2% к предыдущему месяцу. '
    'NULL в январе 2015 — это первый месяц ряда, сравнивать не с чем (в источнике [x]).';
comment on column "primary".ons__pipr.annual_change is
    'Изменение индекса всего частного арендного фонда района (без разбивки) к тому же месяцу прошлого '
    'года, В ПРОЦЕНТАХ (колонка "Annual change"). '
    'Проценты, а не доли. Главный показатель инфляции аренды в этом источнике. '
    'NULL за все 12 месяцев 2015 года: данных за 2014-й в PIPR нет (в источнике [x]). По Лондону '
    'наблюдался диапазон примерно от -11.8% до +32.7%.';
comment on column "primary".ons__pipr.rental_price is
    'Средняя (average в терминах ONS) арендная плата по всему фонду района, фунтов стерлингов в месяц '
    '(колонка "Rental price"). Источник округляет до целого фунта, дробной части не бывает. '
    'Уровень цены, а не индекс: между районами сравним напрямую, но на состав жилфонда района не '
    'поправлен, поэтому для динамики надёжнее index и annual_change. По Лондону наблюдался диапазон '
    'примерно 900…3700 фунтов в месяц.';

comment on column "primary".ons__pipr.index_one_bed is
    'Индекс арендных цен жилья с одной спальней (колонка "Index one bed"). База — январь 2023 = 100 '
    '(в данных ровно 100 у каждого района в 2023-01). Безразмерный, не сезонно сглажен.';
comment on column "primary".ons__pipr.monthly_change_one_bed is
    'Изменение индекса жилья с одной спальней к предыдущему месяцу, В ПРОЦЕНТАХ (колонка "Monthly '
    'change one bed").';
comment on column "primary".ons__pipr.annual_change_one_bed is
    'Изменение индекса жилья с одной спальней к тому же месяцу прошлого года, В ПРОЦЕНТАХ (колонка '
    '"Annual change one bed").';
comment on column "primary".ons__pipr.rental_price_one_bed is
    'Средняя (average в терминах ONS) арендная плата по жилью с одной спальней, фунтов стерлингов в '
    'месяц (колонка "Rental price one bed"). Источник округляет до целого фунта, дробной части не '
    'бывает.';

comment on column "primary".ons__pipr.index_two_bed is
    'Индекс арендных цен жилья с двумя спальнями (колонка "Index two bed"). База — январь 2023 = 100 '
    '(в данных ровно 100 у каждого района в 2023-01). Безразмерный, не сезонно сглажен.';
comment on column "primary".ons__pipr.monthly_change_two_bed is
    'Изменение индекса жилья с двумя спальнями к предыдущему месяцу, В ПРОЦЕНТАХ (колонка "Monthly '
    'change two bed").';
comment on column "primary".ons__pipr.annual_change_two_bed is
    'Изменение индекса жилья с двумя спальнями к тому же месяцу прошлого года, В ПРОЦЕНТАХ (колонка '
    '"Annual change two bed").';
comment on column "primary".ons__pipr.rental_price_two_bed is
    'Средняя (average в терминах ONS) арендная плата по жилью с двумя спальнями, фунтов стерлингов в '
    'месяц (колонка "Rental price two bed"). Источник округляет до целого фунта, дробной части не '
    'бывает.';

comment on column "primary".ons__pipr.index_three_bed is
    'Индекс арендных цен жилья с тремя спальнями (колонка "Index three bed"). База — январь 2023 = '
    '100 (в данных ровно 100 у каждого района в 2023-01). Безразмерный, не сезонно сглажен.';
comment on column "primary".ons__pipr.monthly_change_three_bed is
    'Изменение индекса жилья с тремя спальнями к предыдущему месяцу, В ПРОЦЕНТАХ (колонка "Monthly '
    'change three bed").';
comment on column "primary".ons__pipr.annual_change_three_bed is
    'Изменение индекса жилья с тремя спальнями к тому же месяцу прошлого года, В ПРОЦЕНТАХ (колонка '
    '"Annual change three bed").';
comment on column "primary".ons__pipr.rental_price_three_bed is
    'Средняя (average в терминах ONS) арендная плата по жилью с тремя спальнями, фунтов стерлингов в '
    'месяц (колонка "Rental price three bed"). Источник округляет до целого фунта, дробной части не '
    'бывает.';

comment on column "primary".ons__pipr.index_four_or_more_bed is
    'Индекс арендных цен жилья с четырьмя и более спальнями (колонка "Index four or more bed"). База '
    '— январь 2023 = 100 (в данных ровно 100 у каждого района в 2023-01). Безразмерный, не сезонно '
    'сглажен.';
comment on column "primary".ons__pipr.monthly_change_four_or_more_bed is
    'Изменение индекса жилья с четырьмя и более спальнями к предыдущему месяцу, В ПРОЦЕНТАХ (колонка '
    '"Monthly change four or more bed").';
comment on column "primary".ons__pipr.annual_change_four_or_more_bed is
    'Изменение индекса жилья с четырьмя и более спальнями к тому же месяцу прошлого года, В ПРОЦЕНТАХ '
    '(колонка "Annual change four or more bed").';
comment on column "primary".ons__pipr.rental_price_four_or_more_bed is
    'Средняя (average в терминах ONS) арендная плата по жилью с четырьмя и более спальнями, фунтов '
    'стерлингов в месяц (колонка "Rental price four or more bed"). Источник округляет до целого '
    'фунта, дробной части не бывает.';

comment on column "primary".ons__pipr.index_detached is
    'Индекс арендных цен отдельно стоящих домов (detached) (колонка "Index detached"). База — январь '
    '2023 = 100 (в данных ровно 100 у каждого района в 2023-01). Безразмерный, не сезонно сглажен.';
comment on column "primary".ons__pipr.monthly_change_detached is
    'Изменение индекса отдельно стоящих домов (detached) к предыдущему месяцу, В ПРОЦЕНТАХ (колонка '
    '"Monthly change detached").';
comment on column "primary".ons__pipr.annual_change_detached is
    'Изменение индекса отдельно стоящих домов (detached) к тому же месяцу прошлого года, В ПРОЦЕНТАХ '
    '(колонка "Annual change detached").';
comment on column "primary".ons__pipr.rental_price_detached is
    'Средняя (average в терминах ONS) арендная плата по отдельно стоящим домам (detached), фунтов '
    'стерлингов в месяц (колонка "Rental price detached"). Источник округляет до целого фунта, '
    'дробной части не бывает.';

comment on column "primary".ons__pipr.index_semidetached is
    'Индекс арендных цен домов на двух хозяев (semi-detached) (колонка "Index semidetached"). База — '
    'январь 2023 = 100 (в данных ровно 100 у каждого района в 2023-01). Безразмерный, не сезонно '
    'сглажен.';
comment on column "primary".ons__pipr.monthly_change_semidetached is
    'Изменение индекса домов на двух хозяев (semi-detached) к предыдущему месяцу, В ПРОЦЕНТАХ '
    '(колонка "Monthly change semidetached").';
comment on column "primary".ons__pipr.annual_change_semidetached is
    'Изменение индекса домов на двух хозяев (semi-detached) к тому же месяцу прошлого года, В '
    'ПРОЦЕНТАХ (колонка "Annual change semidetached").';
comment on column "primary".ons__pipr.rental_price_semidetached is
    'Средняя (average в терминах ONS) арендная плата по домам на двух хозяев (semi-detached), фунтов '
    'стерлингов в месяц (колонка "Rental price semidetached"). Источник округляет до целого фунта, '
    'дробной части не бывает.';

comment on column "primary".ons__pipr.index_terraced is
    'Индекс арендных цен домов в террасной застройке (terraced) (колонка "Index terraced"). База — '
    'январь 2023 = 100 (в данных ровно 100 у каждого района в 2023-01). Безразмерный, не сезонно '
    'сглажен.';
comment on column "primary".ons__pipr.monthly_change_terraced is
    'Изменение индекса домов в террасной застройке (terraced) к предыдущему месяцу, В ПРОЦЕНТАХ '
    '(колонка "Monthly change terraced").';
comment on column "primary".ons__pipr.annual_change_terraced is
    'Изменение индекса домов в террасной застройке (terraced) к тому же месяцу прошлого года, В '
    'ПРОЦЕНТАХ (колонка "Annual change terraced").';
comment on column "primary".ons__pipr.rental_price_terraced is
    'Средняя (average в терминах ONS) арендная плата по домам в террасной застройке (terraced), '
    'фунтов стерлингов в месяц (колонка "Rental price terraced"). Источник округляет до целого фунта, '
    'дробной части не бывает.';

comment on column "primary".ons__pipr.index_flat_maisonette is
    'Индекс арендных цен квартир и мезонетов (flat / maisonette) (колонка "Index flat maisonette"). '
    'База — январь 2023 = 100 (в данных ровно 100 у каждого района в 2023-01). Безразмерный, не '
    'сезонно сглажен.';
comment on column "primary".ons__pipr.monthly_change_flat_maisonette is
    'Изменение индекса квартир и мезонетов (flat / maisonette) к предыдущему месяцу, В ПРОЦЕНТАХ '
    '(колонка "Monthly change flat maisonette").';
comment on column "primary".ons__pipr.annual_change_flat_maisonette is
    'Изменение индекса квартир и мезонетов (flat / maisonette) к тому же месяцу прошлого года, В '
    'ПРОЦЕНТАХ (колонка "Annual change flat maisonette").';
comment on column "primary".ons__pipr.rental_price_flat_maisonette is
    'Средняя (average в терминах ONS) арендная плата по квартирам и мезонетам (flat / maisonette), '
    'фунтов стерлингов в месяц (колонка "Rental price flat maisonette"). Источник округляет до целого '
    'фунта, дробной части не бывает.';
