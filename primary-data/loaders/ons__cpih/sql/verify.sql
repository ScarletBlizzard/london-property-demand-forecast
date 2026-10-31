-- Итоговая сводка по "primary".ons__cpih. Запускается в конце load.sh.
--
-- По строке на серию. Что смотреть:
--   * "пропуск месяцев" — сколько месяцев внутри интервала серии отсутствует.
--     Ожидается 0: ряд MM23 непрерывный. Любое другое число — повод открыть выгрузку.
--   * "первый" у индексов ожидается 1988-01, у годовых темпов прироста — 1989-01:
--     первые 12 месяцев прироста не определены по построению.
--   * "последний" отстаёт от текущего месяца примерно на месяц — релиз MM23 выходит
--     во второй половине следующего месяца.
--   * "релиз" одинаков у всех серий: это дата публикации всего MM23.

select cdid                                                         as "серия",
       count(*)                                                     as "набл.",
       min(period)                                                  as "первый",
       max(period)                                                  as "последний",
       (extract(year  from max(period)) - extract(year  from min(period))) * 12
       + extract(month from max(period)) - extract(month from min(period))
       + 1 - count(*)                                               as "пропуск месяцев",
       min(value)                                                   as "min",
       max(value)                                                   as "max",
       (array_agg(value order by period desc))[1]                   as "последнее знач.",
       max(release_date)::date                                      as "релиз",
       min(title)                                                   as "заголовок в ONS"
from "primary".ons__cpih
group by cdid
order by cdid;

select count(*)                   as "строк всего",
       count(distinct cdid)       as "серий",
       count(*) filter (where value is null) as "пустых значений",
       pg_size_pretty(
           pg_total_relation_size('"primary".ons__cpih')
       )                          as "размер"
from "primary".ons__cpih;
