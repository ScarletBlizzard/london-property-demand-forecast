-- Таблица первичных данных: HMRC — Monthly property transactions completed in
-- the UK with value of £40,000 or above, лист Residential_monthly книги ODS.
--
-- Колонки и значения как в источнике, без очистки и агрегации. Добавлены только
-- разобранная дата месяца (month) и вынесенный из подписи признак
-- предварительности (provisional) — исходная подпись сохранена в month_label.
--
-- Страница публикации:
-- https://www.gov.uk/government/statistics/monthly-property-transactions-completed-in-the-uk-with-value-40000-or-above
-- Методика (источники данных, предварительные оценки, grossing factor,
-- сезонное сглаживание, округление, разбивка по странам):
-- https://www.gov.uk/government/statistics/monthly-property-transactions-completed-in-the-uk-with-value-40000-or-above/uk-monthly-property-transactions-background-and-references

create table if not exists "primary".hmrc__property_transactions (
    month                  date not null primary key,
    month_label            text not null,
    england                integer,
    scotland               integer,
    wales                  integer,
    northern_ireland       integer,
    uk                     integer,
    uk_seasonally_adjusted integer,
    provisional            boolean not null
);

comment on table "primary".hmrc__property_transactions is
    'HMRC Monthly property transactions completed in the UK with value of £40,000 or above, '
    'лист Residential_monthly: число завершённых сделок с ЖИЛОЙ недвижимостью по месяцам, '
    'с апреля 2005. Сделка считается по дате завершения (date of completion), '
    'в статистику попадают только сделки стоимостью выше £40 000. '
    'Разбивки по районам нет: только Великобритания целиком и четыре страны. '
    'Все значения — число сделок, округлённое до десятков. Пояснение на самом листе '
    '("statistics are rounded and reported by thousand transactions") вводит в заблуждение: '
    'это не тысячи сделок, домножать ни на что не надо, см. раздел Rounding в методике. '
    'Источник (ссылка на вложение ODS меняется с каждым релизом, её берёт load.sh): '
    'https://www.gov.uk/government/statistics/monthly-property-transactions-completed-in-the-uk-with-value-40000-or-above '
    'Методика: .../uk-monthly-property-transactions-background-and-references. OGL v3.0.';

comment on column "primary".hmrc__property_transactions.month is
    'Месяц ряда, первое число (2026-08-01 = август 2026). Разобран из подписи month_label. '
    'Ряд непрерывный, с 2005-04-01; непрерывность проверяет lib/ods_to_csv.py при разборе';
comment on column "primary".hmrc__property_transactions.month_label is
    'Подпись месяца ровно как в источнике, вместе с пометкой в квадратных скобках: '
    '"April 2005", "June 2026 [provisional]", "August 2026 [provisional estimates]". '
    'Оставлена, чтобы отличать свежую оценку по снимку базы ([provisional estimates], '
    'последний месяц) от просто ещё не устоявшихся месяцев ([provisional], два предыдущих)';
comment on column "primary".hmrc__property_transactions.england is
    'Число сделок с жилой недвижимостью в Англии за месяц, округлено до десятков. '
    'Источник — база SDLT (Stamp Duty Land Tax) HMRC по данным налоговых деклараций покупателей. '
    'Разбивка между Англией и Северной Ирландией — по заявленному в декларации местоположению '
    'объекта; где оно не указано, сделки разносятся между двумя странами пропорционально';
comment on column "primary".hmrc__property_transactions.scotland is
    'Число сделок с жилой недвижимостью в Шотландии за месяц, округлено до десятков. '
    'После передачи налогов на недвижимость Шотландии с 1 апреля 2015 HMRC эти данные не собирает: '
    'цифры приходят месячным фидом от Revenue Scotland (налог LBTT)';
comment on column "primary".hmrc__property_transactions.wales is
    'Число сделок с жилой недвижимостью в Уэльсе за месяц, округлено до десятков. '
    'После передачи налогов Уэльсу с 1 апреля 2018 данные приходят от Welsh Revenue Authority '
    '(налог LTT): с июля 2021 месячным фидом, последний месяц оценивается по grossing factor '
    'за последний полный финансовый год';
comment on column "primary".hmrc__property_transactions.northern_ireland is
    'Число сделок с жилой недвижимостью в Северной Ирландии за месяц, округлено до десятков. '
    'Источник — та же база SDLT, что и по Англии (см. комментарий к england о разносе сделок '
    'без указанного местоположения)';
comment on column "primary".hmrc__property_transactions.uk is
    'Число сделок с жилой недвижимостью по Великобритании за месяц, БЕЗ сезонного сглаживания, '
    'округлено до десятков. Из-за округления слагаемых может отличаться от '
    'england + scotland + wales + northern_ireland на пару десятков — это не ошибка загрузки';
comment on column "primary".hmrc__property_transactions.uk_seasonally_adjusted is
    'То же число сделок по Великобритании, но сезонно сглаженное (seasonally adjusted): '
    'из ряда убран регулярный годовой цикл (летом сделок больше, зимой меньше), поправки сделаны '
    'и на календарь — положение Пасхи и число рабочих дней в месяце. Считается HMRC в X-13ARIMA. '
    'Для сравнения соседних месяцев берите эту колонку, для абсолютных объёмов — uk. '
    'Разбивки по странам в сглаженном виде источник не даёт. С апреля 2024 ряд пересчитан '
    'после ревизии модели сглаживания';
comment on column "primary".hmrc__property_transactions.provisional is
    'true, если у месяца в источнике стоит пометка в квадратных скобках, то есть цифра '
    'предварительная и в следующих релизах изменится. Так помечены три последних месяца ряда: '
    'последний — [provisional estimates] (считается по снимку базы SDLT, который HMRC делает '
    'во вторую неделю месяца, и дотягивается вверх grossing factor на неполученные декларации), '
    'два предыдущих — [provisional] (статистика перестаёт меняться примерно через 3 месяца). '
    'Для обучения модели предварительные месяцы лучше отбрасывать; '
    'точный вид пометки — в month_label';
