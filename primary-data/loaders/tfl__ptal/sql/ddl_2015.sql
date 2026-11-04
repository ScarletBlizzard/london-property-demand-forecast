-- Таблица первичных данных: TfL — Public Transport Accessibility Levels (PTAL),
-- релиз 2015, агрегация по LSOA (границы 2011 года).
--
-- Базовый период расчёта — январь 2008 — декабрь 2014, то есть срез описывает сеть
-- до открытия Elizabeth line (май 2022), продления Northern line до Battersea
-- (сентябрь 2021) и Barking Riverside (июль 2022). В итоговом датасете используется
-- отдельный готовый borough-набор 2015; этот LSOA-срез оставлен для анализа.
--
-- Колонки и значения как в источнике, без очистки и переименования.
-- Методика расчёта AI и PTAL — Connectivity Assessment Guide (TfL):
-- https://data.london.gov.uk/download/24rz6/86bbffe1-8af1-49ba-ac9b-b3eacaf68137/connectivity-assessment-guide.pdf

create table if not exists "primary".tfl__ptal_lsoa_2015 (
    lsoa2011     text not null primary key,
    av_ptai_2015 numeric,
    ptal         text,
    ptai_high    numeric,
    ptai_low     numeric
);

comment on table "primary".tfl__ptal_lsoa_2015 is
    'TfL Public Transport Accessibility Levels, релиз 2015 (базовый период 2008-2014), '
    'уровень LSOA 2011. Покрытие — Greater London целиком, 4835 LSOA, один статический срез. '
    'Источник: https://data.london.gov.uk/dataset/public-transport-accessibility-levels-24rz6 '
    'OGL v2.0 — обратите внимание, у релиза 2023 лицензия другая (v3.0).';

comment on column "primary".tfl__ptal_lsoa_2015.lsoa2011 is
    'Код LSOA по границам Census 2011 (E01......). Ключ для джойна. '
    'С релизом 2023 (LSOA 2021) напрямую сходится 4659 кодов из 4835; '
    'для полного сопоставления нужен официальный lookup LSOA11 -> LSOA21 с geoportal.statistics.gov.uk';
comment on column "primary".tfl__ptal_lsoa_2015.av_ptai_2015 is
    'Accessibility Index, среднее по ячейкам сетки 100x100 м внутри LSOA. '
    'Аналог mean_ai в таблице tfl__ptal_lsoa_2023. '
    'AI считается из времени пешком до остановок и станций, частоты сообщения на них '
    'и среднего времени ожидания; скорость поездки, пересадки и загруженность не учитываются. '
    'ВАЖНО: разницу av_ptai_2015 и mean_ai за 2023 нельзя трактовать как чистое изменение '
    'транспортной доступности — она смешивает новую инфраструктуру с сокращением автобусного '
    'обслуживания после пандемии и возможными правками методики за восемь лет между релизами. '
    'Контрольный пример: у Wandsworth AI падает на 13%, хотя в сентябре 2021 там открыли '
    'две новые станции Northern line';
comment on column "primary".tfl__ptal_lsoa_2015.ptal is
    'av_ptai_2015, разложенный в категории PTAL: 0, 1a, 1b, 2, 3, 4, 5, 6a, 6b — '
    'от худшей доступности к лучшей. Категория 0 в данных не встречается, минимум 1a';
comment on column "primary".tfl__ptal_lsoa_2015.ptai_high is
    'Верхняя граница AI внутри LSOA. Аналог max_ai в релизе 2023';
comment on column "primary".tfl__ptal_lsoa_2015.ptai_low is
    'Нижняя граница AI внутри LSOA. Аналог min_ai в релизе 2023';
