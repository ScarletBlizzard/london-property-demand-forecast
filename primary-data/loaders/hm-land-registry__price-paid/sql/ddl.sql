-- Таблица первичных данных: HM Land Registry — Price Paid Data (Greater London).

create table if not exists "primary".hm_land_registry__price_paid (
    transaction_unique_identifier  uuid,
    price                          bigint,
    date_of_transfer               timestamp,
    postcode                       text,
    property_type                  text,
    old_new                        text,
    duration                       text,
    paon                           text,
    saon                           text,
    street                         text,
    locality                       text,
    town_city                      text,
    district                       text,
    county                         text,
    ppd_category_type              text,
    record_status                  text
);

comment on table "primary".hm_land_registry__price_paid is
    'HM Land Registry Price Paid Data, pp-complete.csv. '
    'Отфильтровано county = ''GREATER LONDON'' (32 боро + City of London). '
    'Колонки и значения как в источнике, без очистки. OGL v3.0.';

comment on column "primary".hm_land_registry__price_paid.transaction_unique_identifier is
    'GUID публикации сделки. В источнике записан в фигурных скобках, хранится как uuid: '
    'текстом индекс первичного ключа вдвое больше. Идентифицирует сделку, а не объект — '
    'повторная продажа того же дома получит другой GUID';
comment on column "primary".hm_land_registry__price_paid.price             is 'Цена сделки в фунтах, целое';
comment on column "primary".hm_land_registry__price_paid.date_of_transfer  is 'Дата перехода права. Время всегда 00:00';
comment on column "primary".hm_land_registry__price_paid.property_type     is 'D=detached, S=semi-detached, T=terraced, F=flat/maisonette, O=other';
comment on column "primary".hm_land_registry__price_paid.old_new           is 'Y=новостройка, N=вторичка';
comment on column "primary".hm_land_registry__price_paid.duration          is 'F=freehold, L=leasehold';
comment on column "primary".hm_land_registry__price_paid.paon              is 'Primary Addressable Object Name — номер/название дома';
comment on column "primary".hm_land_registry__price_paid.saon              is 'Secondary Addressable Object Name — квартира, офис и т.п.';
comment on column "primary".hm_land_registry__price_paid.district          is 'Лондонское боро. 33 значения: 32 боро + City of London';
comment on column "primary".hm_land_registry__price_paid.county            is 'Всегда GREATER LONDON — таблица отфильтрована по нему';
comment on column "primary".hm_land_registry__price_paid.ppd_category_type is
    'A=standard price paid (сделки по рыночной цене между частными лицами), '
    'B=additional price paid (репоссессии, покупки не у частных лиц, аренда на срок и т.п.)';
comment on column "primary".hm_land_registry__price_paid.record_status     is
    'A=addition, C=change, D=delete. Значимо только для monthly-файлов; в pp-complete всегда A';
