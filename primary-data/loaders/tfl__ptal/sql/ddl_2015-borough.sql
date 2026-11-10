-- Готовая агрегация TfL по 33 районам: Borough AvPTAI2015.csv.
create table if not exists "primary".tfl__ptal_borough_2015 (
    borough_code  text primary key,
    borough_name  text,
    av_ptai_2015  numeric,
    ptal          text
);

comment on table "primary".tfl__ptal_borough_2015 is
    'TfL Public Transport Accessibility Levels, 2015 PTAL Borough. '
    'Готовые значения по 32 боро и City of London; порядок полей как в CSV. '
    'Источник: https://data.london.gov.uk/download/24rz6/8e520b81-dd06-4ce6-aaa0-972dccf84b57/Borough%20AvPTAI2015.csv. '
    'OGL v2.0. Не равно простому среднему av_ptai_2015 по LSOA района.';
