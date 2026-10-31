-- Итоговая сводка по "primary".ons__pipr. Запускается в конце load.sh.
--
-- Ожидаемые значения (на релизе 16 сентября 2026; с каждым релизом растут только
-- "строк" и "месяцев", остальное меняться не должно):
--   районов                   32  — все боро, кроме City of London: его ONS не публикует
--   регионов                   1  — всегда London
--   база != 100                0  — в январе 2023 индекс обязан быть ровно 100 у каждого района
--   City of London             0  — подтверждение, что E09000001 в источнике по-прежнему нет
--   NULL monthly              32  — только январь 2015, первый месяц ряда
--   NULL annual              384  — только 2015 год: 32 района x 12 месяцев
--   NULL monthly вне 2015-01   0
--   NULL annual после 2015     0
--
-- Если два последних счётчика перестали быть нулями, в выгрузке появились настоящие
-- пропуски ([x] или [z] в источнике) — тогда комментарии к колонкам в sql/ddl.sql
-- и README загрузчика пора перечитать.

select count(*)                                      as "строк",
       count(distinct area_code)                     as "районов",
       count(distinct area_name)                     as "имён районов",
       count(distinct region_or_country_name)        as "регионов",
       count(distinct time_period)                   as "месяцев",
       min(time_period)                              as "первый месяц",
       max(time_period)                              as "последний месяц",
       count(*) filter (
           where time_period = date '2023-01-01' and "index" <> 100
       )                                             as "база != 100",
       count(*) filter (where area_code = 'E09000001')
                                                     as "City of London",
       count(*) filter (where monthly_change is null)
                                                     as "NULL monthly",
       count(*) filter (where annual_change is null)
                                                     as "NULL annual",
       count(*) filter (
           where monthly_change is null and time_period <> date '2015-01-01'
       )                                             as "NULL monthly вне 2015-01",
       count(*) filter (
           where annual_change is null and time_period >= date '2016-01-01'
       )                                             as "NULL annual после 2015",
       min(rental_price)                             as "min аренда, £",
       max(rental_price)                             as "max аренда, £",
       round(min(annual_change), 1)                  as "min годовой рост, %",
       round(max(annual_change), 1)                  as "max годовой рост, %",
       pg_size_pretty(
           pg_total_relation_size('"primary".ons__pipr')
       )                                             as "размер"
from "primary".ons__pipr;
