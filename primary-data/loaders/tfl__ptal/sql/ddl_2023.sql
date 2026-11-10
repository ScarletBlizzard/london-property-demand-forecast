-- Таблица первичных данных: TfL — Public Transport Accessibility Levels (PTAL),
-- релиз 2023, агрегация по LSOA (границы 2021 года).
--
-- Колонки и значения как в источнике, без очистки и переименования.
-- Методика расчёта AI и PTAL — Connectivity Assessment Guide (TfL):
-- https://data.london.gov.uk/download/24rz6/86bbffe1-8af1-49ba-ac9b-b3eacaf68137/connectivity-assessment-guide.pdf

create table if not exists "primary".tfl__ptal_lsoa_2023 (
    fid           integer,
    lsoa21cd      text not null primary key,
    lsoa21nm      text,
    borough       text,
    mean_ai       numeric,
    median_ai     numeric,
    min_ai        numeric,
    max_ai        numeric,
    mean_ptal     text,
    shape_leng    numeric,
    shape__area   numeric,
    shape__length numeric
);

comment on table "primary".tfl__ptal_lsoa_2023 is
    'TfL Public Transport Accessibility Levels, релиз 2023, уровень LSOA 2021. '
    'Покрытие — Greater London целиком, 4994 LSOA, один статический срез. '
    'Источник: https://gis-tfl.opendata.arcgis.com/datasets/TfL::lsoa-aggregated-ptal-stats-2023 '
    'OGL v3.0 + Contains OS data © Crown copyright and database right 2023.';

comment on column "primary".tfl__ptal_lsoa_2023.fid is
    'Технический номер строки из ArcGIS, смысла в данных не несёт';
comment on column "primary".tfl__ptal_lsoa_2023.lsoa21cd is
    'Код LSOA по границам Census 2021 (E01......). Ключ для джойна. '
    'Внимание: часть кодов отличается от LSOA 2011, которыми размечен релиз 2015 — '
    'для сопоставления релизов нужен официальный lookup LSOA11 -> LSOA21 с geoportal.statistics.gov.uk';
comment on column "primary".tfl__ptal_lsoa_2023.lsoa21nm is
    'Название LSOA по ONS, сохранённое как в источнике';
comment on column "primary".tfl__ptal_lsoa_2023.borough is
    'Название района по данным TfL. Используется для агрегации PTAL по районам. '
    'В названиях может использоваться & вместо and';
comment on column "primary".tfl__ptal_lsoa_2023.mean_ai is
    'Accessibility Index, среднее по ячейкам сетки 100x100 м внутри LSOA. '
    'AI считается из времени пешком до остановок и станций, частоты сообщения на них '
    '(equivalent doorstep frequency) и среднего времени ожидания. '
    'Скорость поездки, пересадки и загруженность транспорта НЕ учитываются. '
    'Непрерывная величина, в моделях использовать её, а не категорию mean_ptal';
comment on column "primary".tfl__ptal_lsoa_2023.median_ai is
    'Медиана AI по ячейкам сетки внутри LSOA';
comment on column "primary".tfl__ptal_lsoa_2023.min_ai is
    'Минимум AI внутри LSOA. Вместе с max_ai даёт внутреннюю неоднородность зоны — '
    'в одном LSOA могут быть и кварталы у станции, и глухие дворы';
comment on column "primary".tfl__ptal_lsoa_2023.max_ai is
    'Максимум AI внутри LSOA';
comment on column "primary".tfl__ptal_lsoa_2023.mean_ptal is
    'mean_ai, разложенный в категории PTAL: 0, 1a, 1b, 2, 3, 4, 5, 6a, 6b — '
    'от худшей доступности к лучшей. В релизе 2023 категория 0 в Лондоне не встречается, '
    'минимум 1a. Лексикографическая сортировка текста случайно совпадает с правильным '
    'порядком категорий, так что order by mean_ptal корректен';
comment on column "primary".tfl__ptal_lsoa_2023.shape_leng is
    'Периметр полигона LSOA из ArcGIS. Дублирует shape__length, обе колонки оставлены как в источнике';
comment on column "primary".tfl__ptal_lsoa_2023.shape__area is
    'Площадь полигона LSOA из ArcGIS, кв. м';
comment on column "primary".tfl__ptal_lsoa_2023.shape__length is
    'Периметр полигона LSOA из ArcGIS, м';
