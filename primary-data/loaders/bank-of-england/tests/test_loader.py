"""Lossless ingestion, complete catalogue pagination and resumable downloads."""

import csv
import hashlib
import http.client
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DIRECTORY))
import _boe_support as support
from _boe_catalog import discover
from _boe_data import csv_rows, inspect_csv, may_split, metadata, parse_metadata

spec = importlib.util.spec_from_file_location("boe_loader", DIRECTORY / "load.py")
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


def catalogue_page(number, first, last, total, codes, next_button=False):
    links = "".join(
        f'<a href="fromshowcolumns.asp?SeriesCodes={code}">{code}</a>' for code in codes
    )
    next_control = '<input name="Next" type="image">' if next_button else ""
    return (
        f"Page {number}, results {first} to {last} of {total}"
        + links
        + f'<form name="form1"><input type="hidden" name="ShadowPage" value="{number}">'
        + '<input type="hidden" name="Frequency" value="M">'
        + next_control
        + "</form>"
    ).encode()


def make_snapshot(folder):
    """Small complete source fixture with duplicate rows and nonnumeric values."""
    files = {
        "catalog_form.html": b'<select name="Frequency"><option value="any">All</option><option value="M">Monthly</option></select>',
        "catalog_M_0001.html": catalogue_page(1, 1, 3, 3, ["A", "B", "EMPTY"]),
        "metadata.xml": b"""<Envelope xmlns="http://www.gesmes.org/xml/2002-08-01">
          <Cube SCODE="A" DESC="A"><Cube FREQ_CODE="M" FREQ_NAME="Monthly"/><Cube FIRST_OBS="2023-01-31" LAST_OBS="2023-02-28"/></Cube>
          <Cube SCODE="B" DESC="B"><Cube FREQ_CODE="M" FREQ_NAME="Monthly"/><Cube FIRST_OBS="2023-01-31" LAST_OBS="2023-01-31"/></Cube>
          <Cube SCODE="EMPTY" DESC="No observations"><Cube FREQ_CODE="M" FREQ_NAME="Monthly"/><Cube FIRST_OBS="" LAST_OBS=""/></Cube>
        </Envelope>""",
        "observations.csv": b"DATE,SERIES,VALUE\r\n31 Jan 2023,A,001.2300\r\n31 Jan 2023,A,001.2300\r\n28 Feb 2023,A,0\r\n31 Jan 2023,B,\r\n31 Jan 2023,B,..\r\n",
    }
    for name, raw in files.items():
        (folder / name).write_bytes(raw)
    start, end = loader.date(2023, 1, 31), loader.date(2023, 2, 28)
    part = dict(
        file="observations.csv",
        codes=["A", "B"],
        start=start.isoformat(),
        end=end.isoformat(),
        **inspect_csv(files["observations.csv"], ["A", "B"], start, end),
    )
    manifest = {
        "source": "bank-of-england",
        "format_version": 2,
        "as_of": "2023-03-01",
        "status": "complete",
        "catalogue": {
            "M": {
                "name": "Monthly",
                "count": 3,
                "codes": ["A", "B", "EMPTY"],
                "files": ["catalog_M_0001.html"],
            }
        },
        "series": parse_metadata(files["metadata.xml"], ["A", "B", "EMPTY"]),
        "metadata_files": ["metadata.xml"],
        "parts": [part],
        "no_observations": ["EMPTY"],
        "total_rows": 5,
        "files": {
            name: {
                "url": "https://www.bankofengland.co.uk/" + name,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            for name, raw in files.items()
        },
    }
    support.save_manifest(folder, manifest)
    return manifest


class RawTests(unittest.TestCase):
    def test_original_values_and_duplicates(self):
        rows = list(
            csv_rows(
                b"DATE,SERIES,VALUE\r\n31 Jan 2023,A,001.2300\r\n31 Jan 2023,A,001.2300\r\n31 Jan 2023,B,\r\n31 Jan 2023,B,..\r\n"
            )
        )
        self.assertEqual(
            rows,
            [("31 Jan 2023", "A", "001.2300")] * 2
            + [("31 Jan 2023", "B", ""), ("31 Jan 2023", "B", "..")],
        )

    def test_html_wide_and_malformed_csv_rejected(self):
        for raw in (
            b"<html>Error</html>",
            b"DATE,A,B\n2023,1,2",
            b"DATE,SERIES,VALUE\n2023,A",
            b'DATE,SERIES,VALUE\n2023,A,"open',
        ):
            with self.assertRaises((ValueError, csv.Error)):
                list(csv_rows(raw))

    def test_unrequested_series_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unexpected CSV series"):
            inspect_csv(
                b"DATE,SERIES,VALUE\n31 Jan 2023,B,1",
                ["A"],
                loader.date(2023, 1, 1),
                loader.date(2023, 12, 31),
            )

    def test_empty_period_keeps_a_valid_header_without_inventing_rows(self):
        self.assertEqual(list(csv_rows(b"DATE,SERIES,VALUE\r\r\n\r\n")), [])

    def test_complete_snapshot_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            manifest = make_snapshot(folder)
            self.assertEqual(loader.validate_snapshot(folder, manifest), 5)
            support.read_snapshot(folder, "bank-of-england")
            (folder / "observations.csv").write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "checksum"):
                support.read_snapshot(folder, "bank-of-england")

    def test_partial_and_legacy_snapshots_cannot_load(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            manifest = make_snapshot(folder)
            for updates in ({"status": "downloading"}, {"format_version": 1}):
                with self.assertRaisesRegex(ValueError, "completed all-series"):
                    loader.validate_snapshot(folder, dict(manifest, **updates))

    def test_missing_frequency_or_series_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            manifest = make_snapshot(folder)
            for field, value in (
                ("catalogue", {}),
                ("series", {}),
                ("no_observations", []),
            ):
                with self.assertRaises(ValueError):
                    loader.validate_snapshot(folder, dict(manifest, **{field: value}))

    def test_duplicate_parts_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            manifest = make_snapshot(folder)
            manifest["parts"] *= 2
            with self.assertRaisesRegex(ValueError, "Repeated"):
                loader.validate_snapshot(folder, manifest)

    def test_missing_last_observation_is_detected_even_with_matching_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            manifest = make_snapshot(folder)
            raw = (
                (folder / "observations.csv")
                .read_bytes()
                .replace(b"28 Feb 2023,A,0\r\n", b"")
            )
            (folder / "observations.csv").write_bytes(raw)
            manifest["files"]["observations.csv"]["sha256"] = hashlib.sha256(
                raw
            ).hexdigest()
            part = manifest["parts"][0]
            part.update(
                inspect_csv(
                    raw,
                    part["codes"],
                    loader.date.fromisoformat(part["start"]),
                    loader.date.fromisoformat(part["end"]),
                )
            )
            manifest["total_rows"] = part["rows"]
            with self.assertRaisesRegex(ValueError, "published bounds"):
                loader.validate_snapshot(folder, manifest)

    def test_full_pagination_beyond_ui_limit(self):
        class Store:
            def __init__(self):
                self.manifest = {"files": {}}

            def get(self, url, name):
                if name == "catalog_form.html":
                    return b'<select name="Frequency"><option value="M">Monthly</option></select>'
                query = parse_qs(urlsplit(url).query)
                number = int(query.get("ShadowPage", ["0"])[0]) + 1
                if number > 16:
                    assert "PageNo17.x" in query and "ActualResNumPerPage" in query
                return catalogue_page(
                    number, number, number, 17, [f"A{number}"], number < 16
                )

        result = discover(Store(), workers=1)
        self.assertEqual(result["M"]["codes"], [f"A{i}" for i in range(1, 18)])

    def test_resume_uses_verified_cached_response(self):
        with tempfile.TemporaryDirectory() as directory:
            store = support.SnapshotStore(Path(directory))

            def fake_fetch(url, folder, name, manifest):
                raw = b"original"
                (folder / name).write_bytes(raw)
                manifest["files"][name] = {
                    "url": url,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
                return raw

            with patch.object(support, "fetch", side_effect=fake_fetch) as fetch:
                store.get("https://example.test/data", "data.csv")
                resumed = support.SnapshotStore(Path(directory), store.folder)
                self.assertEqual(
                    resumed.get("https://example.test/data", "data.csv"), b"original"
                )
                self.assertEqual(fetch.call_count, 1)

    def test_metadata_reuses_old_batch_sizes(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            manifest = make_snapshot(folder)
            (folder / "metadata.xml").rename(folder / "metadata_cached.xml")
            manifest["files"]["metadata_cached.xml"] = manifest["files"].pop(
                "metadata.xml"
            )
            items, files = metadata(
                SimpleNamespace(folder=folder, manifest=manifest),
                ["A", "B", "EMPTY"],
                batch_size=1,
            )
            self.assertEqual(items, manifest["series"])
            self.assertEqual(files, ["metadata_cached.xml"])

    def test_rate_limits_and_auth_errors_are_not_split_into_more_requests(self):
        for status in (401, 403, 404, 429):
            self.assertFalse(
                may_split(HTTPError("https://example.test", status, "error", {}, None))
            )
        self.assertTrue(
            may_split(HTTPError("https://example.test", 500, "error", {}, None))
        )

    def test_connection_reset_and_incomplete_body_are_retried_without_saving_partial_data(
        self,
    ):
        for error in (
            ConnectionResetError("reset"),
            http.client.IncompleteRead(b"partial", 100),
        ):
            with (
                self.subTest(error=type(error).__name__),
                tempfile.TemporaryDirectory() as directory,
            ):
                folder = Path(directory)
                response = MagicMock()
                response.__enter__.return_value = response
                response.read.return_value = b"complete"
                response.headers = {"Content-Type": "application/csv"}
                manifest = {"files": {}}
                with (
                    patch.object(
                        support.urllib.request, "urlopen", side_effect=[error, response]
                    ) as request,
                    patch.object(support.time, "sleep"),
                ):
                    self.assertEqual(
                        support.fetch(
                            "https://example.test/data", folder, "data.csv", manifest
                        ),
                        b"complete",
                    )
                self.assertEqual(request.call_count, 2)
                self.assertEqual((folder / "data.csv").read_bytes(), b"complete")
                self.assertEqual(
                    manifest["files"]["data.csv"]["sha256"],
                    hashlib.sha256(b"complete").hexdigest(),
                )

    def test_local_only_blocks_remote_before_connect(self):
        with (
            patch.object(
                loader, "connection_settings", return_value={"host": "db.example.test"}
            ),
            patch.object(loader, "connect") as connect,
        ):
            with self.assertRaisesRegex(ValueError, "non-local"):
                loader.replace_table(None, Path("."), {}, local_only=True)
            connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
