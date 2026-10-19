-- Итоговая сводка по "primary".hmrc__property_transactions. Запускается в конце load.sh.
--
-- "предварительных" ожидаемо 3: последний месяц помечен [provisional estimates],
-- два предыдущих — [provisional]. Если число другое, HMRC сменил разметку релиза
-- и комментарии к колонке provisional пора перечитать.
--
-- "месяцев в ряду" должно совпадать с "строк": ряд непрерывный, по строке на месяц.
--
-- "uk - сумма, макс" — максимальное расхождение uk и суммы четырёх стран.
-- На релизе Sep 2026 оно равно 0, но HMRC предупреждает, что из-за округления
-- до десятков итог может не совпадать с суммой слагаемых, так что небольшое
-- расхождение само по себе не ошибка загрузки.

select count(*)                                   as "строк",
       min(month)                                 as "первый месяц",
       max(month)                                 as "последний месяц",
       (extract(year from max(month)) - extract(year from min(month))) * 12
           + extract(month from max(month)) - extract(month from min(month)) + 1
                                                  as "месяцев в ряду",
       count(*) filter (where provisional)        as "предварительных",
       max(abs(uk - (england + scotland + wales + northern_ireland)))
                                                  as "uk - сумма, макс",
       count(*) filter (
           where england is null or scotland is null or wales is null
                 or northern_ireland is null or uk is null
                 or uk_seasonally_adjusted is null
       )                                          as "с пропусками",
       pg_size_pretty(
           pg_total_relation_size('"primary".hmrc__property_transactions')
       )                                          as "размер"
from "primary".hmrc__property_transactions;
