-- Таблица первичных данных: Energy Performance Certificates, набор non-domestic — нежилые здания.
--
-- Значения полей описаны в глоссарии источника:
-- https://get-energy-performance-data.communities.gov.uk/guidance

create table if not exists "primary".epc__non_domestic (
    certificate_number          text,
    address1                    text,
    address2                    text,
    address3                    text,
    posttown                    text,
    postcode                    text,
    address                     text,
    constituency                text,
    constituency_label          text,
    local_authority             text,
    local_authority_label       text,
    asset_rating                text,
    asset_rating_band           text,
    property_type               text,
    inspection_date             text,
    lodgement_date              text,
    lodgement_datetime          text,
    transaction_type            text,
    new_build_benchmark         text,
    existing_stock_benchmark    text,
    building_level              text,
    main_heating_fuel           text,
    other_fuel_desc             text,
    special_energy_uses         text,
    renewable_sources           text,
    floor_area                  text,
    standard_emissions          text,
    target_emissions            text,
    typical_emissions           text,
    building_emissions          text,
    aircon_present              text,
    aircon_kw_rating            text,
    estimated_aircon_kw_rating  text,
    ac_inspection_commissioned  text,
    building_environment        text,
    report_type                 text,
    primary_energy_value        text,
    uprn                        text,
    uprn_source                 text
);

comment on table "primary".epc__non_domestic is
    'Energy Performance Certificates, набор non-domestic, certificates-*.csv. '
    'Отфильтровано local_authority like ''E09%'' (33 района Greater London). '
    'Колонки и значения как в источнике, без очистки. Все поля text. OGL v3.0.';

-- Ключ и индексы снимаем перед заливкой, собираем после — sql/indexes_non_domestic.sql.
alter table "primary".epc__non_domestic drop constraint if exists epc__non_domestic_pkey;
drop index if exists "primary".epc__non_domestic_local_authority_idx;
drop index if exists "primary".epc__non_domestic_postcode_idx;
