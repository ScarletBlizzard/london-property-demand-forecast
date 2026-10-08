-- Таблица первичных данных: Energy Performance Certificates, набор display — общественные здания, Display Energy Certificates.
--
-- Значения полей описаны в глоссарии источника:
-- https://get-energy-performance-data.communities.gov.uk/guidance

create table if not exists "primary".epc__display (
    certificate_number             text primary key,
    address1                       text,
    address2                       text,
    address3                       text,
    posttown                       text,
    postcode                       text,
    address                        text,
    constituency                   text,
    constituency_label             text,
    local_authority                text,
    local_authority_label          text,
    current_operational_rating     text,
    yr1_operational_rating         text,
    yr2_operational_rating         text,
    electric_co2                   text,
    heating_co2                    text,
    renewables_co2                 text,
    property_type                  text,
    inspection_date                text,
    lodgement_date                 text,
    lodgement_datetime             text,
    main_benchmark                 text,
    main_heating_fuel              text,
    special_energy_uses            text,
    renewable_sources              text,
    total_floor_area               text,
    annual_thermal_fuel_usage      text,
    typical_thermal_fuel_usage     text,
    typical_thermal_use            text,
    annual_electrical_fuel_usage   text,
    typical_electrical_fuel_usage  text,
    renewables_fuel_thermal        text,
    renewables_electrical          text,
    yr1_electricity_co2            text,
    yr2_electricity_co2            text,
    yr1_heating_co2                text,
    yr2_heating_co2                text,
    yr1_renewables_co2             text,
    yr2_renewables_co2             text,
    aircon_present                 text,
    aircon_kw_rating               text,
    estimated_aircon_kw_rating     text,
    ac_inspection_commissioned     text,
    building_environment           text,
    building_category              text,
    operational_rating_band        text,
    nominated_date                 text,
    or_assessment_end_date         text,
    occupancy_level                text,
    report_type                    text,
    other_fuel                     text,
    country                        text,
    uprn                           text,
    uprn_source                    text
);

comment on table "primary".epc__display is
    'Energy Performance Certificates, набор display, certificates-*.csv, только Greater London';

-- Рабочие индексы: срезы по району и джойн с price paid по почтовому индексу.
create index if not exists epc__display_local_authority_idx on "primary".epc__display (local_authority);
create index if not exists epc__display_postcode_idx on "primary".epc__display (postcode);
