SELECT count(*) AS rows FROM "primary".bank_of_england__raw;
SELECT count(DISTINCT "SERIES") AS series FROM "primary".bank_of_england__raw;
SELECT "SERIES", count(*) AS rows,
       count(*) FILTER (WHERE "VALUE" = '') AS empty_values,
       count(*) FILTER (WHERE "VALUE" = '..') AS unavailable_values
FROM "primary".bank_of_england__raw
GROUP BY "SERIES"
ORDER BY "SERIES";
