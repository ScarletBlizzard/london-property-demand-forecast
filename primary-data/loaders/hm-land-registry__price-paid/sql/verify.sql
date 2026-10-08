-- Итоговая сводка по "primary".hm_land_registry__price_paid.
-- Запускается в конце load.sh и load_year.sh.

select count(*)                    as "строк",
       min(date_of_transfer)::date as "первая сделка",
       max(date_of_transfer)::date as "последняя сделка",
       count(distinct district)    as "районов",
       pg_size_pretty(
           pg_total_relation_size('"primary".hm_land_registry__price_paid')
       )                           as "размер"
from "primary".hm_land_registry__price_paid;
