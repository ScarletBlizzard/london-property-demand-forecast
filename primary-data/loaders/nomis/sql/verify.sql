SELECT count(*) AS population_rows FROM "primary".nomis__population_raw;
SELECT count(*) AS labour_market_rows FROM "primary".nomis__labour_market_raw;
SELECT count(*) AS earnings_rows FROM "primary".nomis__earnings_raw;
SELECT count(*) AS claimant_count_rows FROM "primary".nomis__claimant_count_raw;

SELECT "GEOGRAPHY_TYPECODE", count(*) AS rows,
       count(*) FILTER (WHERE "OBS_VALUE" <> '') AS nonempty_values,
       count(DISTINCT "GEOGRAPHY_CODE") AS boroughs,
       min("DATE") AS first_period, max("DATE") AS last_period,
       count(DISTINCT "GENDER") AS genders,
       count(DISTINCT "AGE") AS ages,
       count(DISTINCT "MEASURE") AS indicators,
       count(DISTINCT "MEASURES") AS measures
FROM "primary".nomis__claimant_count_raw
GROUP BY "GEOGRAPHY_TYPECODE";

-- Read-only coverage checks. Source values are not changed or normalized.
SELECT "GEOGRAPHY_TYPECODE", count(*) AS rows,
       count(DISTINCT "GEOGRAPHY_CODE") AS boroughs,
       min("DATE") AS first_period, max("DATE") AS last_period,
       count(DISTINCT "SEX") AS sex_categories,
       count(DISTINCT "AGE") AS age_categories,
       count(DISTINCT "MEASURES") AS measures
FROM "primary".nomis__population_raw
GROUP BY "GEOGRAPHY_TYPECODE";

SELECT "GEOGRAPHY_TYPECODE", count(*) AS rows,
       count(DISTINCT "GEOGRAPHY_CODE") AS boroughs,
       min("DATE") AS first_period, max("DATE") AS last_period,
       count(DISTINCT "VARIABLE") AS variables,
       count(DISTINCT "MEASURES") AS measures
FROM "primary".nomis__labour_market_raw
GROUP BY "GEOGRAPHY_TYPECODE";

SELECT "GEOGRAPHY_TYPECODE", count(*) AS rows,
       count(DISTINCT "GEOGRAPHY_CODE") AS boroughs,
       min("DATE") AS first_period, max("DATE") AS last_period,
       count(DISTINCT "SEX") AS worker_categories,
       count(DISTINCT "ITEM") AS statistics,
       count(DISTINCT "PAY") AS pay_categories,
       count(DISTINCT "MEASURES") AS measures
FROM "primary".nomis__earnings_raw
GROUP BY "GEOGRAPHY_TYPECODE";

-- The actual history is in a distinct source geography; original missing rows remain.
SELECT "GEOGRAPHY_TYPECODE", min("DATE") AS first_nonempty_period,
       max("DATE") AS last_nonempty_period, count(*) AS nonempty_values
FROM "primary".nomis__population_raw
WHERE "OBS_VALUE" <> ''
GROUP BY "GEOGRAPHY_TYPECODE";

SELECT "GEOGRAPHY_TYPECODE", min("DATE") AS first_nonempty_period,
       max("DATE") AS last_nonempty_period, count(*) AS nonempty_values
FROM "primary".nomis__earnings_raw
WHERE "OBS_VALUE" <> ''
GROUP BY "GEOGRAPHY_TYPECODE";
