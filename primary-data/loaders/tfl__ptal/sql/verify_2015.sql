-- Итоговая сводка по "primary".tfl__ptal_lsoa_2015. Запускается в конце load.sh.
--
-- Ожидаемые значения: 4835 строк, 8 категорий PTAL (1a..6b, нулевой в Лондоне нет).

select count(*)                      as "строк",
       count(distinct lsoa2011)      as "LSOA",
       count(distinct ptal)           as "категорий PTAL",
       round(min(av_ptai_2015), 1)   as "min AI",
       round(max(av_ptai_2015), 1)   as "max AI",
       pg_size_pretty(
           pg_total_relation_size('"primary".tfl__ptal_lsoa_2015')
       )                             as "размер"
from "primary".tfl__ptal_lsoa_2015;
