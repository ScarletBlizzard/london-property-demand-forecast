"""Download original XML metadata and columnar CSV for all catalogue series."""

import csv
import hashlib
import io
import urllib.error
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, timedelta
from urllib.parse import urlencode

from _boe_catalog import BASE
from _boe_support import parallel_map

ENDPOINT = BASE + "_iadb-fromshowcolumns.asp"
MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]
COLUMNS = ["DATE", "SERIES", "VALUE"]
EARLIEST = date(1963, 1, 1)


def api_date(value):
    return f"{value.day:02d}/{MONTHS[value.month - 1]}/{value.year}"


def csv_date(value):
    day, month, year = value.split()
    return date(int(year), MONTHS.index(month) + 1, int(day))


def chunks(values, size):
    return [values[offset : offset + size] for offset in range(0, len(values), size)]


def identifier(codes):
    return hashlib.sha256(",".join(codes).encode("ascii")).hexdigest()[:20]


def parse_metadata(raw, expected):
    root = ET.fromstring(raw)
    if root.tag.split("}")[-1] != "Envelope":
        raise ValueError("Expected a BoE XML Envelope")
    result = {}
    for node in root.iter():
        if "SCODE" not in node.attrib:
            continue
        code = node.attrib["SCODE"]
        if code in result:
            raise ValueError(f"Duplicate XML series: {code}")
        item = dict(node.attrib)
        for child in node.iter():
            for key in ("FREQ_CODE", "FREQ_NAME", "FIRST_OBS", "LAST_OBS"):
                if key in child.attrib:
                    item[key] = child.attrib[key]
        if "FIRST_OBS" not in item or "LAST_OBS" not in item:
            raise ValueError(f"No observation bounds in metadata for {code}")
        first, last = item["FIRST_OBS"], item["LAST_OBS"]
        if bool(first) != bool(last) or (
            first and date.fromisoformat(first) > date.fromisoformat(last)
        ):
            raise ValueError(f"Invalid observation bounds for {code}")
        result[code] = item
    if set(result) != set(expected):
        raise ValueError(
            f"XML series do not match request: missing={sorted(set(expected) - set(result))[:10]}"
        )
    return result


def csv_rows(raw):
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    if next(reader, []) != COLUMNS:
        raise ValueError("Expected the original DATE,SERIES,VALUE CSV header")
    for row in reader:
        if not row:
            continue
        if len(row) != 3:
            raise ValueError("Incomplete CSV row")
        yield tuple(row)


def inspect_csv(raw, codes, start, end):
    counts = Counter()
    bounds = {}
    expected = set(codes)
    for observation_date, code, value in csv_rows(raw):
        if code not in expected:
            raise ValueError(f"Unexpected CSV series: {code}")
        when = csv_date(observation_date)
        if not start <= when <= end:
            raise ValueError(
                f"CSV date outside the requested interval: {observation_date}"
            )
        counts[code] += 1
        previous = bounds.get(code, [when, when])
        bounds[code] = [min(when, previous[0]), max(when, previous[1])]
    return {
        "rows": sum(counts.values()),
        "counts": dict(counts),
        "bounds": {
            code: [d.isoformat() for d in pair] for code, pair in bounds.items()
        },
    }


def mark_split(store, name):
    with store.lock:
        store.manifest.setdefault("split_requests", {})[name] = True
        store.checkpoint()


def may_split(error):
    if isinstance(error, urllib.error.HTTPError):
        return error.code in (414, 500, 502, 503, 504)
    if isinstance(error, urllib.error.URLError):
        return isinstance(error.reason, TimeoutError)
    return True


def metadata(store, codes, batch_size=150, workers=2):
    result, files, pending = {}, [], set(codes)
    # Reuse completed XML responses even after changing technical batch sizes.
    candidates = [
        name
        for name in store.manifest["files"]
        if name.startswith("metadata_") and name.endswith(".xml")
    ]
    for name in sorted(
        candidates, key=lambda n: (store.folder / n).stat().st_size, reverse=True
    ):
        try:
            raw = (store.folder / name).read_bytes()
            expected = [
                el.attrib["SCODE"]
                for el in ET.fromstring(raw).iter()
                if "SCODE" in el.attrib
            ]
            if expected and set(expected).issubset(pending):
                items = parse_metadata(raw, expected)
                result.update(items)
                files.append(name)
                pending.difference_update(items)
        except ValueError, ET.ParseError:
            # An earlier incomplete response is retained for provenance, but is
            # never counted as successful metadata.
            continue
    print(f"Metadata already saved: {len(result)}/{len(codes)}", flush=True)

    def batch(selected):
        name = f"metadata_{identifier(selected)}.xml"
        try:
            if name in store.manifest.get("split_requests", {}):
                raise ValueError("Previously split request")
            # FIRST_OBS/LAST_OBS describe the entire series even with a one-day
            # request window. Do not make the metadata query scan all observations.
            url = (
                ENDPOINT
                + "?"
                + urlencode(
                    {
                        "CodeVer": "new",
                        "xml.x": "yes",
                        "Datefrom": api_date(
                            date.fromisoformat(store.manifest["as_of"])
                        ),
                        "Dateto": api_date(date.fromisoformat(store.manifest["as_of"])),
                        "SeriesCodes": ",".join(selected),
                        "Omit": "-G",
                        "VPD": "Y",
                        "VFD": "Y",
                    }
                )
            )
            if name in store.manifest["files"]:
                url = store.manifest["files"][name]["url"]
            if len(url) > 1900:
                raise ValueError("Split a long BoE request URL")
            result = parse_metadata(store.get(url, name), selected)
            print(
                f"Metadata: {len(selected)} series ({selected[0]} .. {selected[-1]})",
                flush=True,
            )
            return result, [name]
        except (
            urllib.error.URLError,
            TimeoutError,
            ValueError,
            ET.ParseError,
        ) as error:
            if len(selected) == 1 or not may_split(error):
                raise
            mark_split(store, name)
            middle = len(selected) // 2
            left, left_files = batch(selected[:middle])
            right, right_files = batch(selected[middle:])
            return dict(left, **right), left_files + right_files

    for items, names in parallel_map(
        batch, chunks(sorted(pending), min(batch_size, 25)), workers
    ):
        result.update(items)
        files.extend(names)
    return result, files


def observations(store, series, batch_size=150, workers=2):
    groups = {}
    empty = []
    for code, item in sorted(series.items()):
        if not item["FIRST_OBS"]:
            empty.append(code)
        else:
            if date.fromisoformat(item["FIRST_OBS"]) < EARLIEST:
                raise ValueError(
                    f"{code}: history starts before the supported endpoint date; do not truncate it"
                )
            groups.setdefault(item["FREQ_CODE"], []).append(code)
    jobs = [
        part
        for frequency, codes in groups.items()
        for part in chunks(
            codes, min(batch_size, 20) if frequency == "D" else min(batch_size, 50)
        )
    ]

    def batch(codes, start=None, end=None):
        start = start or min(
            date.fromisoformat(series[code]["FIRST_OBS"]) for code in codes
        )
        end = end or max(date.fromisoformat(series[code]["LAST_OBS"]) for code in codes)
        name = f"observations_{identifier(codes)}_{start}_{end}.csv"
        try:
            if name in store.manifest.get("split_requests", {}):
                raise ValueError("Previously split request")
            url = (
                ENDPOINT
                + "?"
                + urlencode(
                    {
                        "csv.x": "yes",
                        "Datefrom": api_date(start),
                        "Dateto": api_date(end),
                        "SeriesCodes": ",".join(codes),
                        "UsingCodes": "Y",
                        "CSVF": "CN",
                        "VPD": "Y",
                        "VFD": "N",
                    }
                )
            )
            if len(url) > 1900:
                raise ValueError("Split a long BoE request URL")
            raw = store.get(url, name)
            summary = inspect_csv(raw, codes, start, end)
            # A requested bound is itself a published observation according to XML.
            for code in codes:
                for field, position in (("FIRST_OBS", 0), ("LAST_OBS", 1)):
                    bound = series[code][field]
                    if (
                        start <= date.fromisoformat(bound) <= end
                        and summary["bounds"].get(code, [None, None])[position] != bound
                    ):
                        raise ValueError(
                            f"{code}: CSV does not include the published {field}={bound}"
                        )
            print(
                f"CSV: {len(codes)} series, {summary['rows']} rows ({codes[0]} .. {codes[-1]})",
                flush=True,
            )
            return [
                dict(
                    file=name,
                    codes=codes,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    **summary,
                )
            ]
        except (urllib.error.URLError, TimeoutError, ValueError, csv.Error) as error:
            if not may_split(error):
                raise
            if len(codes) > 1:
                mark_split(store, name)
                middle = len(codes) // 2
                return batch(codes[:middle], start, end) + batch(
                    codes[middle:], start, end
                )
            if start < end:
                mark_split(store, name)
                middle = start + (end - start) // 2
                return batch(codes, start, middle) + batch(
                    codes, middle + timedelta(days=1), end
                )
            raise

    parts = []
    for result in parallel_map(batch, jobs, workers):
        parts.extend(result)
    return parts, empty
