-- Итоговая сводка по таблице :tbl. Запускается в конце load.sh.

select count(*)                      as "строк",
       count(distinct local_authority) as "районов",
       min(lodgement_date)           as "первый сертификат",
       max(lodgement_date)           as "последний сертификат",
       pg_size_pretty(pg_total_relation_size(:'tbl')) as "размер"
from :tbl;
