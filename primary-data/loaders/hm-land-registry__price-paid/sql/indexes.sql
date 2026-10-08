-- Индексы для "primary".hm_land_registry__price_paid.

set maintenance_work_mem = '512MB';
set statement_timeout = '30min';

-- Основной рабочий индекс: целевая переменная проекта — число сделок по району
-- за месяц. Покрывает и запросы с фильтром только по district.
create index if not exists hm_land_registry__price_paid_district_date_idx
    on "primary".hm_land_registry__price_paid (district, date_of_transfer);

-- Временные срезы по всему Лондону, без фильтра по району.
create index if not exists hm_land_registry__price_paid_date_idx
    on "primary".hm_land_registry__price_paid (date_of_transfer);

-- Джойны с EPC и геопривязкой идут по почтовому индексу.
create index if not exists hm_land_registry__price_paid_postcode_idx
    on "primary".hm_land_registry__price_paid (postcode);

-- Первичный ключ. Land Registry документирует GUID как уникальный
do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'hm_land_registry__price_paid_pkey'
          and conrelid = '"primary".hm_land_registry__price_paid'::regclass
    ) then
        alter table "primary".hm_land_registry__price_paid
            add constraint hm_land_registry__price_paid_pkey
            primary key (transaction_unique_identifier);
    end if;
end $$;
