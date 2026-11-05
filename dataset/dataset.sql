-- Продажи жилья по районам Лондона: июнь 2010 — сентябрь 2025.

WITH
-- Cправочник 33 районов + PTAL (2015)
boroughs AS (
    SELECT borough_code,
           borough_name AS borough,
           CASE WHEN borough_name = 'Westminster' THEN 'CITY OF WESTMINSTER'
                ELSE upper(borough_name) END AS district,
           round(av_ptai_2015, 2) AS ptal_2015
    FROM "primary".tfl__ptal_borough_2015
),
-- PERCENTILE_CONT(0.5) — медиана цены.
sales AS (
    SELECT date_trunc('month', date_of_transfer)::date AS month,
           district,
           count(*)::int AS sales_count,
           round(percentile_cont(0.5) WITHIN GROUP (ORDER BY price)::numeric, 2) AS price_median
    FROM "primary".hm_land_registry__price_paid
    WHERE ppd_category_type = 'A'
      AND date_of_transfer >= date '2009-06-01'
      AND date_of_transfer < date '2025-10-01'
    GROUP BY month, district
),
ptal_2023 AS (
    SELECT borough,
           round(avg(mean_ai), 2) AS ptal
    FROM "primary".tfl__ptal_lsoa_2023
    GROUP BY borough
),
crime AS (
    SELECT month, borough, sum(count)::numeric AS crime_count
    FROM "primary".mps__crime_borough
    WHERE month BETWEEN date '2010-04-01' AND date '2025-09-01'
    GROUP BY month, borough
),
pay AS (
    SELECT "DATE"::int AS year,
           "GEOGRAPHY_CODE" AS borough_code,
           CASE WHEN trim("OBS_VALUE") = '' THEN NULL
                ELSE "OBS_VALUE"::numeric END AS mean_pay
    FROM "primary".nomis__earnings_raw
    WHERE "SEX_NAME" = 'Total'
      AND "PAY_NAME" = 'Annual pay - gross'
      AND "ITEM_NAME" = 'Mean'
      AND "MEASURES_NAME" = 'Value'
),
population AS (
    SELECT "DATE"::int AS year,
           "GEOGRAPHY_CODE" AS borough_code,
           CASE WHEN trim("OBS_VALUE") = '' THEN NULL
                ELSE "OBS_VALUE"::numeric END AS population
    FROM "primary".nomis__population_raw
    WHERE "SEX_NAME" = 'Total'
      AND "AGE_NAME" = 'All ages'
      AND "MEASURES_NAME" = 'Value'
),
bank_daily AS (
    SELECT to_date("DATE", 'DD Mon YYYY') AS day,
           "VALUE"::numeric AS rate
    FROM "primary".bank_of_england__raw
    WHERE "SERIES" = 'IUDBEDR'
),
bank_monthly AS (
    SELECT date_trunc('month', day)::date AS month,
           rate,
           row_number() OVER (
               PARTITION BY date_trunc('month', day)
               ORDER BY day DESC
           ) AS day_number
    FROM bank_daily
    WHERE day >= date '2010-05-01'
      AND day < date '2025-09-01'
),
-- Медианы EPC по району и году; ниже присоединяем предыдущий год.
housing AS (
    SELECT extract(year FROM lodgement_date::date)::int AS year,
           local_authority AS borough_code,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY number_habitable_rooms::numeric)
               FILTER (WHERE number_habitable_rooms::numeric > 0)::numeric AS rooms_median,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY total_floor_area::numeric)
               FILTER (WHERE total_floor_area::numeric > 0)::numeric AS floor_area_median,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY current_energy_efficiency::numeric)
               FILTER (WHERE current_energy_efficiency::numeric > 0)::numeric AS energy_efficiency_median,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY energy_consumption_current::numeric)::numeric
               AS energy_consumption_median,
           -- NULLIF превращает пустую строку высоты в NULL перед приведением к числу.
           percentile_cont(0.5) WITHIN GROUP (ORDER BY nullif(floor_height, '')::numeric)
               FILTER (WHERE nullif(floor_height, '')::numeric > 0)::numeric AS floor_height_median
    FROM "primary".epc__domestic
    WHERE lodgement_date::date >= date '2009-01-01'
      AND lodgement_date::date < date '2025-01-01'
    GROUP BY year, borough_code
)
SELECT s.month,
       b.borough,
       b.borough_code,
       s.sales_count,
       s.price_median,
       previous.sales_count AS sales_count_lag12,
       previous.price_median AS price_median_lag12,
       extract(year FROM s.month)::int AS year,
       extract(month FROM s.month)::int AS month_num,
       CASE WHEN s.month < date '2023-01-01' THEN b.ptal_2015
            ELSE t.ptal END AS ptal,
       round(1000 * c.crime_count / p.population, 2) AS crime_per_1000_lag2,
       h.rooms_median AS rooms_median_epc_prev_year,
       round(h.floor_area_median, 2) AS floor_area_median_epc_prev_year,
       round(h.energy_efficiency_median, 2) AS energy_efficiency_median_epc_prev_year,
       round(h.energy_consumption_median, 2) AS energy_consumption_median_epc_prev_year,
       round(h.floor_height_median, 2) AS floor_height_median_epc_prev_year,
       bank.rate AS bank_rate,
       pay.mean_pay AS mean_pay_prev_year,
       p.population::int AS population_prev_2_years
FROM sales AS s
JOIN boroughs AS b ON b.district = s.district
-- Повторный JOIN той же таблицы: продажи этого района ровно год назад.
LEFT JOIN sales AS previous
       ON previous.district = s.district
      AND previous.month = s.month - interval '1 year'
LEFT JOIN ptal_2023 AS t ON replace(t.borough, ' & ', ' and ') = b.borough
LEFT JOIN crime AS c ON c.borough = b.borough
                   AND c.month = s.month - interval '2 months'
LEFT JOIN pay ON pay.borough_code = b.borough_code
             AND pay.year = extract(year FROM s.month)::int - 1
LEFT JOIN population AS p ON p.borough_code = b.borough_code
                        AND p.year = extract(year FROM s.month)::int - 2
LEFT JOIN bank_monthly AS bank ON bank.month = s.month - interval '1 month'
                             AND bank.day_number = 1
LEFT JOIN housing AS h ON h.borough_code = b.borough_code
                     AND h.year = extract(year FROM s.month)::int - 1
WHERE s.month BETWEEN date '2010-06-01' AND date '2025-09-01'
ORDER BY s.month, b.borough;
