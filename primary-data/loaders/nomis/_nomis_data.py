"""Структура страниц Nomis и соответствие наборов таблицам."""

REQUIRED = {"DATE", "GEOGRAPHY", "OBS_VALUE", "RECORD_OFFSET", "RECORD_COUNT"}
TABLE_NAMES = {
    "NM_31_1": "nomis__population_raw",
    "NM_17_5": "nomis__labour_market_raw",
    "NM_30_1": "nomis__earnings_raw",
    "NM_162_1": "nomis__claimant_count_raw",
}


def check_page(columns, rows, offset, total):
    count_column = columns.index("RECORD_COUNT")
    offset_column = columns.index("RECORD_OFFSET")
    for index, row in enumerate(rows, start=offset):
        if int(row[count_column]) != total or int(row[offset_column]) != index:
            raise ValueError("Nomis page counts/offsets differ from the manifest")
