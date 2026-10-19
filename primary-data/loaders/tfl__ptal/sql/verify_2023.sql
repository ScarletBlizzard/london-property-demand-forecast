-- Итоговая сводка по "primary".tfl__ptal_lsoa_2023. Запускается в конце load.sh.
--
-- "битый borough" — число LSOA, где колонка borough из источника не совпадает
-- с боро из имени lsoa21nm. Ожидаемое значение 434 из 4994; если оно изменилось,
-- TfL что-то поправил в источнике и комментарии к колонке borough пора перечитать.
-- Написание нормализуется: в borough боро идут через "&", у ONS — через "and".
--
-- "боро по lsoa21nm" ожидаемо 34, а не 33: в источнике опечатка "ZBarking and Dagenham".

select count(*)                                                as "строк",
       count(distinct lsoa21cd)                                as "LSOA",
       count(distinct regexp_replace(lsoa21nm, '\s+\S+$', ''))  as "боро по lsoa21nm",
       count(*) filter (
           where replace(borough, ' & ', ' and ')
                 <> regexp_replace(lsoa21nm, '\s+\S+$', '')
       )                                                       as "битый borough",
       count(distinct mean_ptal)                               as "категорий PTAL",
       round(min(mean_ai), 1)                                  as "min AI",
       round(max(mean_ai), 1)                                  as "max AI",
       pg_size_pretty(
           pg_total_relation_size('"primary".tfl__ptal_lsoa_2023')
       )                                                       as "размер"
from "primary".tfl__ptal_lsoa_2023;
