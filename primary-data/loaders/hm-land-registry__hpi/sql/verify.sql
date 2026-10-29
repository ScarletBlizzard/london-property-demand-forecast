-- Итоговая сводка по "primary".hm_land_registry__hpi. Запускается в конце load.sh.
--
-- Что проверяем:
--   "боро" ожидаемо 33 (32 боро + City of London), "агрегатов" — 3
--     (London E12000007, England E92000001, United Kingdom K02000001);
--   "лаг объёмов, мес" — на сколько месяцев sales_volume отстаёт от index.
--     HM Land Registry намеренно не публикует объёмы за два последних месяца
--     релиза, так что ожидаемое значение 2. Если стало другим — политика
--     публикации изменилась, и комментарии к sales_volume пора перечитать;
--   "cash+mortgage <> всего" — доля месяцев боро, где разбивка по способу оплаты
--     не сходится с общим объёмом. Это норма (способ оплаты известен не по всем
--     сделкам), цифра нужна просто чтобы не принять её за ошибку загрузки;
--   "new+old <> всего" ожидаемо 0: разбивка новостройка/вторичка сходится точно.

select count(*)                                              as "строк",
       count(*) filter (where area_code like 'E09%')          as "строк по боро",
       count(distinct area_code) filter
            (where area_code like 'E09%')                     as "боро",
       count(distinct area_code) filter
            (where area_code not like 'E09%')                 as "агрегатов",
       min(date) filter (where area_code like 'E09%')         as "первый месяц боро",
       max(date)                                              as "месяц релиза",
       max(date) filter (where sales_volume is not null)      as "последний месяц с объёмами",
       (extract(year  from max(date)) * 12 + extract(month from max(date)))
       - (select extract(year  from max(date)) * 12 + extract(month from max(date))
          from "primary".hm_land_registry__hpi
          where sales_volume is not null)                     as "лаг объёмов, мес",
       count(*) filter (
           where area_code like 'E09%'
             and index_sa is not null
       )                                                      as "боро с index_sa (ждём 0)",
       count(*) filter (
           where area_code like 'E09%'
             and sales_volume is not null
             and cash_sales_volume is not null
             and mortgage_sales_volume is not null
             and cash_sales_volume + mortgage_sales_volume <> sales_volume
       )                                                      as "cash+mortgage <> всего",
       count(*) filter (
           where area_code like 'E09%'
             and sales_volume is not null
             and new_sales_volume is not null
             and old_sales_volume is not null
             and new_sales_volume + old_sales_volume <> sales_volume
       )                                                      as "new+old <> всего",
       pg_size_pretty(
           pg_total_relation_size('"primary".hm_land_registry__hpi')
       )                                                      as "размер"
from "primary".hm_land_registry__hpi;

-- Хвост целевого признака: последние 6 месяцев релиза по боро.
-- Видно, что index есть у всех 33 боро, а sales_volume в последних двух месяцах NULL.
select date                                            as "месяц",
       count(*) filter (where index is not null)        as "боро с индексом",
       count(*) filter (where sales_volume is not null) as "боро с объёмом",
       sum(sales_volume)                                as "сделок всего"
from "primary".hm_land_registry__hpi
where area_code like 'E09%'
  and date > (select max(date) from "primary".hm_land_registry__hpi) - interval '6 months'
group by date
order by date;
