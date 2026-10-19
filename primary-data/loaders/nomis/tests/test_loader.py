"""Technical checks for lossless nomis CSV loading."""

import csv
import gzip
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DIRECTORY))
import _nomis_download as downloader
import _nomis_support as _support

spec = importlib.util.spec_from_file_location("nomis_loader", DIRECTORY / "load.py")
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)
SOURCE = "nomis"


class RawTests(unittest.TestCase):
    def test_only_connection_failures_are_retried(self):
        import _nomis_database as database
        import psycopg

        self.assertTrue(
            database._network_error(psycopg.OperationalError("connection lost"))
        )
        self.assertTrue(
            database._network_error(psycopg.InterfaceError("connection closed"))
        )
        self.assertTrue(
            database._network_error(psycopg.errors.AdminShutdown("server restarting"))
        )
        self.assertFalse(
            database._network_error(psycopg.errors.QueryCanceled("statement timeout"))
        )
        self.assertFalse(
            database._network_error(psycopg.errors.LockNotAvailable("lock timeout"))
        )
        self.assertFalse(
            database._network_error(psycopg.errors.OutOfMemory("out of memory"))
        )

    def test_connection_reset_retries_and_gzip_retains_exact_response(self):
        raw = b"DATE,VALUE\r\n2023,001.2300\r\n"
        response = io.BytesIO(raw)
        response.headers = {"Content-Type": "text/csv"}
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            manifest = {"files": {}}
            with (
                patch.object(
                    _support.urllib.request,
                    "urlopen",
                    side_effect=[ConnectionResetError(), response],
                ) as get,
                patch.object(_support.time, "sleep"),
            ):
                self.assertEqual(
                    _support.fetch(
                        "https://www.nomisweb.co.uk/test",
                        folder,
                        "page.csv.gz",
                        manifest,
                    ),
                    raw,
                )
            self.assertEqual(get.call_count, 2)
            self.assertEqual(_support.csv_bytes(folder / "page.csv.gz"), raw)
            self.assertEqual(
                manifest["files"]["page.csv.gz"]["response_sha256"],
                hashlib.sha256(raw).hexdigest(),
            )

    def test_nomis_tsv_preserves_literal_unescaped_quotes_and_whitespace(self):
        raw = b'"DATE"\t"VARIABLE_NAME"\t"OBS_VALUE"\n"2004-12"\t"% of economically inactive male student" "\t\n"2004-12"\t"a,b"\t001.2300\n'
        columns, rows = _support.read_tsv(raw, {"DATE", "OBS_VALUE"})
        self.assertEqual(columns, ["DATE", "VARIABLE_NAME", "OBS_VALUE"])
        self.assertEqual(
            rows[0], ("2004-12", '% of economically inactive male student" ', "")
        )
        self.assertEqual(rows[1], ("2004-12", "a,b", "001.2300"))
        with self.assertRaises(ValueError):
            _support.read_tsv(b'"DATE"\t"OBS_VALUE"\n"2004"\n', {"DATE"})

    def test_csv_preserves_empty_zero_formatting_duplicates_and_quoted_text(self):
        raw = b'DATE,VALUE,NOTE\r\n31 Jan 2023,001.2300," a,b "\r\n31 Jan 2023,001.2300," a,b "\r\nunknown,,"line1\nline2"\r\nother,0,NA\r\nother,..,suppressed\r\n'
        columns, rows = _support.read_csv(raw, {"DATE"})
        self.assertEqual(columns, ["DATE", "VALUE", "NOTE"])
        self.assertEqual(
            rows,
            [
                ("31 Jan 2023", "001.2300", " a,b "),
                ("31 Jan 2023", "001.2300", " a,b "),
                ("unknown", "", "line1\nline2"),
                ("other", "0", "NA"),
                ("other", "..", "suppressed"),
            ],
        )

    def test_incomplete_csv_and_html_rejected(self):
        for raw in (
            b"<html>Error</html>",
            b"DATE,V\n2023",
            b"DATE,V,V\n2023,1,2",
            b'DATE,V\n2023,"open',
        ):
            with self.assertRaises((ValueError, csv.Error)):
                _support.read_csv(raw, {"DATE", "V"})

    def test_snapshot_checks_source_and_file_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "data.csv").write_bytes(b"changed")
            (folder / "manifest.json").write_text(
                json.dumps(
                    {
                        "source": SOURCE,
                        "files": {"data.csv": {"sha256": "not-the-file-hash"}},
                    }
                )
            )
            with self.assertRaisesRegex(ValueError, "Expected a"):
                _support.read_snapshot(folder, "other-source")
            with self.assertRaisesRegex(ValueError, "checksum"):
                _support.read_snapshot(folder, SOURCE)

    def test_nomis_pages_keep_fields_and_detect_missing_rows(self):
        columns = [
            "DATE",
            "GEOGRAPHY",
            "OBS_VALUE",
            "RECORD_OFFSET",
            "RECORD_COUNT",
            "EXTRA_SOURCE_COLUMN",
        ]
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for index, value in enumerate(["", "0"]):
                with (folder / f"{index}.csv").open("w", newline="") as file:
                    writer = csv.writer(file)
                    writer.writerow(columns)
                    writer.writerow(
                        ["2023-03", "001", value, str(index), "2", "original"]
                    )
            settings = {"pages": ["0.csv", "1.csv"], "record_count": 2}
            manifest = {"datasets": {"NM_17_5": settings}}
            result_columns, rows = loader.raw_tables(folder, manifest)[
                "nomis__labour_market_raw"
            ]
            self.assertEqual(result_columns, columns)
            self.assertEqual(
                next(iter(rows)), ("2023-03", "001", "", "0", "2", "original")
            )
            self.assertEqual(list(rows)[1][2], "0")
            settings["pages"] = ["0.csv"]
            with self.assertRaisesRegex(ValueError, "incomplete"):
                list(loader.raw_tables(folder, manifest)["nomis__labour_market_raw"][1])

    def test_multiple_geographies_keep_original_offsets_empty_fields_and_duplicates(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            columns = [
                "DATE",
                "GEOGRAPHY",
                "GEOGRAPHY_CODE",
                "OBS_VALUE",
                "RECORD_OFFSET",
                "RECORD_COUNT",
                "GEOGRAPHY_TYPECODE",
            ]
            queries = []
            for name, geotype, value in [
                ("current", "424", ""),
                ("historical", "464", "001.2300"),
            ]:
                output = io.StringIO(newline="")
                writer = csv.writer(output)
                writer.writerow(columns)
                writer.writerow(["2000", "001", "E09000001", value, "0", "1", geotype])
                raw = output.getvalue().encode()
                filename = name + ".csv.gz"
                (folder / filename).write_bytes(gzip.compress(raw))
                queries.append(
                    {
                        "dates": ["2000"],
                        "record_count": 1,
                        "pages": [{"filename": filename, "offset": 0, "rows": 1}],
                    }
                )
            manifest = {
                "version": 2,
                "status": "complete",
                "datasets": {"NM_31_1": {"queries": queries}},
            }
            _cols, rows = loader.raw_tables(folder, manifest)["nomis__population_raw"]
            self.assertEqual(len(rows), 2)
            self.assertEqual([r[3] for r in rows], ["", "001.2300"])
            self.assertEqual([r[4] for r in rows], ["0", "0"])
            self.assertEqual(list(rows), list(rows))
            self.assertEqual(rows.dates, {"2000"})
            manifest["status"] = "downloading"
            with self.assertRaisesRegex(ValueError, "incomplete"):
                loader.raw_tables(folder, manifest)
            manifest["status"] = "complete"
            queries[1]["pages"][0]["offset"] = 1
            with self.assertRaisesRegex(ValueError, "incomplete"):
                loader.raw_tables(folder, manifest)

    def test_full_plan_has_all_dimensions_and_adds_raw_history(self):
        def code(values):
            return json.dumps(
                {"structure": {"codelists": {"codelist": [{"code": values}]}}}
            ).encode()

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "datasets.json").write_text(
                json.dumps(
                    {
                        "NM_31_1": {
                            "name": "population",
                            "historical_geography": {
                                "selector": "2013265927TYPE464",
                                "before_year": 2001,
                            },
                        }
                    }
                )
            )
            calls = []
            missing_rows = 0

            def fetch(url, target, name, manifest):
                calls.append(url)
                if "/geography/" in url:
                    raw = code(
                        [
                            {
                                "value": i,
                                "annotations": {
                                    "annotation": [
                                        {
                                            "annotationtitle": "GeogCode",
                                            "annotationtext": f"E090000{i:02d}",
                                        }
                                    ]
                                },
                            }
                            for i in range(1, 34)
                        ]
                    )
                elif ".data.csv?" in url:
                    params = parse_qs(urlparse(url).query)
                    self.assertEqual(params["setallwherenotspecified"], ["true"])
                    self.assertEqual(params["ExcludeMissingValues"], ["false"])
                    self.assertEqual(params["ExcludeZeroValues"], ["false"])
                    self.assertFalse({"sex", "age", "measures"} & params.keys())
                    count = (
                        33 * 3 * 2 * 2 * len(params["date"][0].split(","))
                        - missing_rows
                    )
                    raw = f"DATE,GEOGRAPHY,GEOGRAPHY_CODE,OBS_VALUE,RECORD_OFFSET,RECORD_COUNT\n2000,1,E09000001,,0,{count}\n".encode()
                elif url.endswith("/def.sdmx.json"):
                    raw = json.dumps(
                        {
                            "structure": {
                                "keyfamilies": {
                                    "keyfamily": [
                                        {
                                            "components": {
                                                "dimension": [
                                                    {"conceptref": x}
                                                    for x in [
                                                        "GEOGRAPHY",
                                                        "SEX",
                                                        "AGE",
                                                        "MEASURES",
                                                        "FREQ",
                                                    ]
                                                ]
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    ).encode()
                elif "/time." in url:
                    raw = code([{"value": 2000}, {"value": 2001}])
                else:
                    raw = code(
                        [{"value": i} for i in range(3 if "/sex." in url else 2)]
                    )
                (target / name).write_bytes(raw)
                manifest["files"][name] = {"sha256": hashlib.sha256(raw).hexdigest()}
                return raw

            with (
                patch.object(downloader, "DIRECTORY", folder),
                patch.object(downloader, "fetch", fetch),
            ):
                _, manifest = downloader.plan(
                    SimpleNamespace(from_year=None, to_year=None)
                )
            settings = manifest["datasets"]["NM_31_1"]
            self.assertEqual(settings["dates"], ["2000", "2001"])
            self.assertEqual(settings["queries"][1]["dates"], ["2000"])
            self.assertEqual(settings["categories"]["sex"], ["0", "1", "2"])
            self.assertEqual(manifest["record_count"], 1188)
            self.assertEqual(settings["queries"][0]["expected_record_count"], 792)
            # A dataset selector must not fetch or load any other configured source.
            configs = json.loads((folder / "datasets.json").read_text())
            configs["NM_162_1"] = {"name": "Claimant count"}
            (folder / "datasets.json").write_text(json.dumps(configs))
            calls.clear()
            with (
                patch.object(downloader, "DIRECTORY", folder),
                patch.object(downloader, "fetch", fetch),
            ):
                _, selected = downloader.plan(
                    SimpleNamespace(from_year=None, to_year=None, dataset=["NM_31_1"])
                )
                self.assertEqual(set(selected["datasets"]), {"NM_31_1"})
                self.assertFalse(any("NM_162_1" in url for url in calls))
                with self.assertRaisesRegex(ValueError, "Unknown Nomis datasets"):
                    downloader.plan(
                        SimpleNamespace(
                            from_year=None, to_year=None, dataset=["NM_TYPO"]
                        )
                    )
            (folder / "datasets.json").write_text(
                json.dumps({"NM_31_1": configs["NM_31_1"]})
            )
            missing_rows = 1
            with (
                patch.object(downloader, "DIRECTORY", folder),
                patch.object(downloader, "fetch", fetch),
                self.assertRaisesRegex(
                    ValueError, "all dates, boroughs and categories require"
                ),
            ):
                downloader.plan(SimpleNamespace(from_year=None, to_year=None))

    def test_resume_downloads_only_missing_pages_and_checks_revisions(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            columns = [
                "DATE",
                "GEOGRAPHY",
                "GEOGRAPHY_CODE",
                "OBS_VALUE",
                "RECORD_OFFSET",
                "RECORD_COUNT",
            ]
            query = {
                "id": "current",
                "params": {},
                "dates": ["2023"],
                "columns": columns,
                "record_count": 3,
                "pages": [],
            }
            manifest = {
                "source": "nomis",
                "version": 2,
                "status": "downloading",
                "page_size": 2,
                "files": {},
                "datasets": {"NM_31_1": {"queries": [query], "revision": {}}},
            }

            def page(target, dataset, q, offset, size):
                output = io.StringIO(newline="")
                writer = csv.writer(output)
                writer.writerow(columns)
                for i in range(offset, min(offset + size, 3)):
                    writer.writerow(["2023", "1", "E09000001", "0", i, 3])
                raw = gzip.compress(output.getvalue().encode())
                name = f"{offset}.csv.gz"
                (target / name).write_bytes(raw)
                return {
                    "filename": name,
                    "offset": offset,
                    "rows": min(size, 3 - offset),
                }, {name: {"sha256": hashlib.sha256(raw).hexdigest()}}

            first, files = page(folder, "NM_31_1", query, 0, 2)
            query["pages"].append(first)
            manifest["files"].update(files)
            _support.save_manifest(folder, manifest)
            args = SimpleNamespace(resume=folder, plan=False, workers=1)
            with (
                patch.object(downloader, "verify_revisions") as verify,
                patch.object(downloader, "fetch_page", side_effect=page) as get,
            ):
                _, result = downloader.download(args)
            self.assertEqual(get.call_count, 1)
            self.assertEqual(get.call_args.args[3], 2)
            self.assertEqual(verify.call_count, 2)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(
                len(
                    list(loader.raw_tables(folder, result)["nomis__population_raw"][1])
                ),
                3,
            )

    def test_count_changes_and_other_regions_are_rejected(self):
        columns = ["RECORD_OFFSET", "RECORD_COUNT", "GEOGRAPHY_CODE"]
        with self.assertRaises(ValueError):
            downloader.check_page(columns, [("0", "3", "E09000001")], 0, 2)
        with self.assertRaises(ValueError):
            downloader.check_page(columns, [("0", "2", "E08000001")], 0, 2)

    def test_selected_dataset_checkpoint_and_snapshot_arguments(self):
        import _nomis_database as database

        manifest = {
            "version": 2,
            "status": "complete",
            "datasets": {
                "NM_162_1": {
                    "queries": [
                        {
                            "id": "current",
                            "record_count": 1,
                            "pages": [
                                {"offset": 0, "rows": 1, "filename": "page.csv.gz"}
                            ],
                        }
                    ]
                }
            },
            "files": {"page.csv.gz": {"sha256": "original"}},
        }
        self.assertEqual(database._pages(manifest)[0].dataset, "NM_162_1")
        manifest["datasets"] = {}
        with self.assertRaisesRegex(ValueError, "configured Nomis datasets"):
            database._pages(manifest)
        manifest["datasets"] = {"NM_TYPO": {}}
        with self.assertRaisesRegex(ValueError, "configured Nomis datasets"):
            database._pages(manifest)
        for option in ["--snapshot", "--resume"]:
            with (
                patch.object(
                    sys, "argv", ["load.py", option, "saved", "--dataset", "NM_162_1"]
                ),
                patch("sys.stderr", io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                _support.arguments("test")


if __name__ == "__main__":
    unittest.main()
