-- Запросы для быстрой проверки уже загруженной таблицы BoE.
-- Показывают общее число строк и рядов, затем число записей и пропусков по каждому ряду.
-- Их можно выполнять в SQL-клиенте после загрузки; все запросы только читают данные.
-- Эта сводка помогает заметить проблемы с объёмом, но не заменяет сверку с исходными CSV.

SELECT count(*) AS rows FROM "primary".bank_of_england__raw;
SELECT count(DISTINCT "SERIES") AS series FROM "primary".bank_of_england__raw;
SELECT "SERIES", count(*) AS rows,
       count(*) FILTER (WHERE "VALUE" = '') AS empty_values,
       count(*) FILTER (WHERE "VALUE" = '..') AS unavailable_values
FROM "primary".bank_of_england__raw
GROUP BY "SERIES"
ORDER BY "SERIES";
