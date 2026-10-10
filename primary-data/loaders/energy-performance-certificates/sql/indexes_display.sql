-- Первичный ключ и индексы для "primary".epc__display.
-- Запускается из load.sh сразу после \copy, в той же транзакции.

set maintenance_work_mem = '512MB';

-- certificate_number в выгрузке уникален. Идентифицирует сертификат, а не здание:
-- при повторной сертификации того же объекта номер будет другим.
alter table "primary".epc__display add constraint epc__display_pkey primary key (certificate_number);

-- Срезы по району и джойнов с price paid по почтовому индексу.
create index epc__display_local_authority_idx on "primary".epc__display (local_authority);
create index epc__display_postcode_idx on "primary".epc__display (postcode);
