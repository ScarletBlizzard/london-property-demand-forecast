-- Итоговая сводка по исходным полям TfL: 4 994 LSOA, 33 района.
select count(*) as "строк",
       count(distinct lsoa21cd) as "LSOA",
       count(distinct borough) as "районов",
       count(distinct mean_ptal) as "категорий PTAL",
       round(min(mean_ai), 1) as "min AI",
       round(max(mean_ai), 1) as "max AI",
       pg_size_pretty(pg_total_relation_size('"primary".tfl__ptal_lsoa_2023')) as "размер"
from "primary".tfl__ptal_lsoa_2023;
