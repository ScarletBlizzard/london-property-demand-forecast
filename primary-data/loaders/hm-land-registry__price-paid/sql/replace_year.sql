-- Заменяет один год в "primary".hm_land_registry__price_paid.
--
-- Ожидает переменную :y — первое число года (напр. '2026-01-01')
-- и файл data/london.csv, который готовит load_year.sh.

begin;

create temp table stg (
    like "primary".hm_land_registry__price_paid
) on commit drop;

\copy stg from 'data/london.csv' with (format csv)

-- Сначала убираем все строки с приехавшими в выгрузке GUID, где бы они ни лежали.
-- Т.к. сделку могли задним числом перенести в другой год
delete from "primary".hm_land_registry__price_paid
where transaction_unique_identifier in (
    select transaction_unique_identifier from stg
    where date_of_transfer >= :'y'::date
      and date_of_transfer <  :'y'::date + interval '1 year'
);

-- exists() — защита от пустой выгрузки: если в stg нет ни строки за этот год,
-- удаление не сработает и существующие данные останутся на месте.
delete from "primary".hm_land_registry__price_paid
where date_of_transfer >= :'y'::date
  and date_of_transfer <  :'y'::date + interval '1 year'
  and exists (
      select 1 from stg
      where date_of_transfer >= :'y'::date
        and date_of_transfer <  :'y'::date + interval '1 year'
  );

insert into "primary".hm_land_registry__price_paid
select * from stg
where date_of_transfer >= :'y'::date
  and date_of_transfer <  :'y'::date + interval '1 year';

select count(*)                    as "стало за год",
       count(distinct district)    as "районов",
       min(date_of_transfer)::date as "первая сделка",
       max(date_of_transfer)::date as "последняя сделка"
from "primary".hm_land_registry__price_paid
where date_of_transfer >= :'y'::date
  and date_of_transfer <  :'y'::date + interval '1 year';

-- Делаем одной транзакцией - либо год заменится целиком, либо не изменится ничего.
commit;
