# Этот модуль отвечает за получение данных из API Nomis. Список четырёх наборов и
# дополнительных исторических географий берётся из datasets.json, а даты и категории —
# из справочников самого источника.
#
# Сначала составляется план для 33 районов Лондона и проверяется ожидаемое число строк.
# Затем CSV/TSV скачиваются страницами с сохранением прогресса. Проверка версии данных
# помогает не собрать одну выгрузку из разных публикаций Nomis. Подключения к БД здесь
# нет.

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import prod
from pathlib import Path
from urllib.parse import urlencode

from _nomis_support import (
    fetch,
    new_snapshot,
    read_csv,
    read_snapshot,
    read_tsv,
    save_manifest,
)

DIRECTORY = Path(__file__).resolve().parent
BASE = "https://www.nomisweb.co.uk/api/v01/dataset/"
GEOGRAPHY = "2013265927TYPE424"
PAGE_SIZE = 25000
REQUIRED = {"DATE", "GEOGRAPHY", "OBS_VALUE", "RECORD_OFFSET", "RECORD_COUNT"}
BOROUGHS = {f"E090000{i:02d}" for i in range(1, 34)}
TABLE_NAMES = {
    "NM_31_1": "nomis__population_raw",
    "NM_17_5": "nomis__labour_market_raw",
    "NM_30_1": "nomis__earnings_raw",
    "NM_162_1": "nomis__claimant_count_raw",
}


# Достаёт список кодов категорий из JSON-справочника Nomis.
def codelist(raw):
    return json.loads(raw)["structure"]["codelists"]["codelist"][0]["code"]


# Читает отметки последнего обновления и пересмотра набора.
def revision(raw):
    family = json.loads(raw)["structure"]["keyfamilies"]["keyfamily"][0]
    return {
        a["annotationtitle"]: a["annotationtext"]
        for a in family.get("annotations", {}).get("annotation", [])
        if a["annotationtitle"] in ("LastUpdated", "LastRevised")
    }


# Проверяет номера записей, заявленное число строк и принадлежность районов Лондону.
def check_page(columns, rows, offset, total):
    count_column = columns.index("RECORD_COUNT")
    offset_column = columns.index("RECORD_OFFSET")
    geography_column = (
        columns.index("GEOGRAPHY_CODE") if "GEOGRAPHY_CODE" in columns else None
    )
    for index, row in enumerate(rows, start=offset):
        if int(row[count_column]) != total or int(row[offset_column]) != index:
            raise ValueError(
                "Nomis page counts/offsets changed during download; retry a fresh snapshot"
            )
        if geography_column is not None and row[geography_column] not in BOROUGHS:
            raise ValueError(
                "Nomis returned a territory outside the 33 London boroughs"
            )


# Скачивает и сохраняет один JSON-справочник выбранного набора.
def metadata(folder, manifest, dataset, path, name):
    return fetch(
        BASE + dataset + "/" + path, folder, dataset + "_" + name + ".json", manifest
    )


# Выбирает все доступные категории и даты, проверяет географию и рассчитывает объём
# запросов.
def plan(args):
    configs = json.loads((DIRECTORY / "datasets.json").read_text(encoding="utf-8"))
    selected = getattr(args, "dataset", None)
    if selected:
        unknown = set(selected) - configs.keys()
        if unknown:
            raise ValueError(f"Unknown Nomis datasets: {sorted(unknown)}")
        configs = {key: value for key, value in configs.items() if key in selected}
    folder, manifest = new_snapshot(DIRECTORY, "nomis")
    manifest.update(
        version=2,
        status="planning",
        datasets={},
        page_size=PAGE_SIZE,
        scope={
            "boroughs": sorted(BOROUGHS),
            "from_year": args.from_year,
            "to_year": args.to_year,
            "selection": "all source dimension categories and measures",
        },
    )
    save_manifest(folder, manifest)
    for dataset, config in configs.items():
        definition = metadata(folder, manifest, dataset, "def.sdmx.json", "definition")
        family = json.loads(definition)["structure"]["keyfamilies"]["keyfamily"][0]
        dimensions = [
            d["conceptref"].lower()
            for d in family["components"]["dimension"]
            if d["conceptref"].upper() not in ("GEOGRAPHY", "FREQ")
        ]
        categories = {}
        for dimension in dimensions:
            raw = metadata(
                folder, manifest, dataset, dimension + ".def.sdmx.json", dimension
            )
            categories[dimension] = [str(c["value"]) for c in codelist(raw)]
        times = codelist(
            metadata(folder, manifest, dataset, "time.def.sdmx.json", "time")
        )
        dates = [
            str(c["value"])
            for c in times
            if (args.from_year is None or int(str(c["value"])[:4]) >= args.from_year)
            and (args.to_year is None or int(str(c["value"])[:4]) <= args.to_year)
        ]
        if not dates:
            raise ValueError(f"No periods in the selected range for {dataset}")
        settings = dict(
            config,
            categories=categories,
            dates=dates,
            revision=revision(definition),
            queries=[],
        )
        manifest["datasets"][dataset] = settings
        selections = [("current", GEOGRAPHY, dates)]
        history = config.get("historical_geography")
        if history:
            historical_dates = [d for d in dates if int(d[:4]) < history["before_year"]]
            if historical_dates:
                selections.append(("historical", history["selector"], historical_dates))
        for query_id, geography, query_dates in selections:
            geo = codelist(
                metadata(
                    folder,
                    manifest,
                    dataset,
                    "geography/" + geography + ".def.sdmx.json",
                    query_id + "_geography",
                )
            )
            gss_codes = {
                str(a["annotationtext"])
                for c in geo
                for a in c.get("annotations", {}).get("annotation", [])
                if a["annotationtitle"] == "GeogCode"
            }
            if len(geo) != 33 or gss_codes != BOROUGHS:
                raise ValueError(
                    f"{dataset}/{query_id}: geography does not contain exactly the 33 London boroughs"
                )

            params = {
                "geography": geography,
                "date": ",".join(query_dates),
                "setallwherenotspecified": "true",
                "ExcludeMissingValues": "false",
                "ExcludeZeroValues": "false",
            }
            sample_params = dict(params, RecordLimit="1", RecordOffset="0")
            output_format = config.get("format", "csv")
            reader = read_tsv if output_format == "tsv" else read_csv
            raw = fetch(
                BASE
                + dataset
                + ".data."
                + output_format
                + "?"
                + urlencode(sample_params),
                folder,
                f"{dataset}_{query_id}_count." + output_format,
                manifest,
            )
            columns, rows = reader(raw, REQUIRED | {"GEOGRAPHY_CODE"}, allow_empty=True)
            total = int(rows[0][columns.index("RECORD_COUNT")]) if rows else 0
            expected = (
                len(BOROUGHS)
                * len(query_dates)
                * prod(len(values) for values in categories.values())
            )
            if total != expected:
                raise ValueError(
                    f"{dataset}/{query_id}: API reports {total:,} rows, "
                    f"but all dates, boroughs and categories require {expected:,}"
                )
            check_page(columns, rows, 0, total)
            settings["queries"].append(
                {
                    "id": query_id,
                    "params": params,
                    "dates": query_dates,
                    "record_count": total,
                    "expected_record_count": expected,
                    "columns": columns,
                    "format": output_format,
                    "pages": [],
                }
            )
            print(
                f"Plan {dataset}/{query_id}: {total:,} rows; all categories { {k: len(v) for k, v in categories.items()} }",
                flush=True,
            )
        settings["record_count"] = sum(q["record_count"] for q in settings["queries"])
        save_manifest(folder, manifest)
    manifest["status"] = "planned"
    manifest["record_count"] = sum(
        s["record_count"] for s in manifest["datasets"].values()
    )
    save_manifest(folder, manifest)
    print(
        f"Total planned: {manifest['record_count']:,} raw rows. Snapshot: {folder}",
        flush=True,
    )
    return folder, manifest


# Проверяет, не изменил ли Nomis публикацию с момента составления плана.
def verify_revisions(folder, manifest, suffix):
    for dataset, settings in manifest["datasets"].items():
        raw = metadata(
            folder, manifest, dataset, "def.sdmx.json", "definition_" + suffix
        )
        if revision(raw) != settings["revision"]:
            raise ValueError(
                f"{dataset}: source was revised during download; start a fresh snapshot"
            )


# Скачивает одну страницу, проверяет её полноту и возвращает сведения для продолжения.
def fetch_page(folder, dataset, query, offset, page_size):
    local = {"files": {}}
    params = dict(query["params"], RecordLimit=str(page_size), RecordOffset=str(offset))
    output_format = query.get("format", "csv")
    reader = read_tsv if output_format == "tsv" else read_csv
    name = f"{dataset}_{query['id']}_{offset:09d}.{output_format}.gz"
    raw = fetch(
        BASE + dataset + ".data." + output_format + "?" + urlencode(params),
        folder,
        name,
        local,
    )
    columns, rows = reader(raw, REQUIRED | {"GEOGRAPHY_CODE"})
    if columns != query["columns"] or len(rows) != min(
        page_size, query["record_count"] - offset
    ):
        raise ValueError(f"{dataset}/{query['id']}: incomplete page or changed columns")
    check_page(columns, rows, offset, query["record_count"])
    return {"filename": name, "offset": offset, "rows": len(rows)}, local["files"]


# Выполняет новый или сохранённый план, скачивая только ещё не полученные страницы.
def download(args):
    if args.resume:
        folder, manifest = args.resume, read_snapshot(args.resume, "nomis")
        if manifest.get("version") != 2 or manifest.get("status") not in (
            "planned",
            "downloading",
            "complete",
        ):
            raise ValueError(
                "Only a completed plan or resumable v2 download can be resumed"
            )
        if manifest["status"] == "complete":
            return folder, manifest
        verify_revisions(folder, manifest, "resume")
        save_manifest(folder, manifest)
    else:
        folder, manifest = plan(args)
    if args.plan:
        return folder, manifest
    manifest["status"] = "downloading"
    save_manifest(folder, manifest)
    for dataset, settings in manifest["datasets"].items():
        for query in settings["queries"]:
            done = {p["offset"] for p in query["pages"]}
            offsets = [
                i
                for i in range(0, query["record_count"], manifest["page_size"])
                if i not in done
            ]
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                pending = {
                    pool.submit(
                        fetch_page, folder, dataset, query, i, manifest["page_size"]
                    ): i
                    for i in offsets
                }
                try:
                    for future in as_completed(pending):
                        page, files = future.result()
                        manifest["files"].update(files)
                        query["pages"].append(page)
                        query["pages"].sort(key=lambda p: p["offset"])
                        save_manifest(folder, manifest)
                        count = sum(p["rows"] for p in query["pages"])
                        print(
                            f"Downloaded {dataset}/{query['id']}: {count:,}/{query['record_count']:,}",
                            flush=True,
                        )
                except BaseException:
                    for future in pending:
                        future.cancel()
                    raise
    verify_revisions(folder, manifest, "finished")
    manifest["status"] = "complete"
    save_manifest(folder, manifest)
    return folder, manifest
