"""Verify durable page retries, resume and atomic publication in an isolated schema."""

import argparse
import csv
import gzip
import hashlib
import io
import sys
import tempfile
from collections import Counter
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _nomis_database as database
from test_loader import _support, loader


def encode(columns, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(columns)
    writer.writerows(rows)
    return gzip.compress(stream.getvalue().encode("utf-8"), mtime=0)


def fixture(source, folder):
    original = _support.read_snapshot(source, "nomis")
    manifest = {
        "source": "nomis",
        "version": 2,
        "status": "complete",
        "test_fixture": True,
        "datasets": {},
        "files": {},
    }
    for dataset, config in original["datasets"].items():
        filename = config["queries"][0]["pages"][0]["filename"]
        columns, source_rows = _support.read_page(source / filename, loader.REQUIRED)
        rows = [list(row) for row in source_rows[:2200]]
        rows[1][columns.index("OBS_VALUE")] = "001.2300"
        rows[2][columns.index("OBS_VALUE")] = " 0 "
        rows[3][columns.index("OBS_STATUS_NAME")] = 'literal " quote\tand\nКириллица  '
        for index, row in enumerate(rows):
            row[columns.index("RECORD_OFFSET")] = str(index)
            row[columns.index("RECORD_COUNT")] = str(len(rows))
        pages = []
        for offset in range(0, len(rows), 1100):
            name = f"{dataset}_{offset}.csv.gz"
            stored = encode(columns, rows[offset : offset + 1100])
            (folder / name).write_bytes(stored)
            manifest["files"][name] = {"sha256": hashlib.sha256(stored).hexdigest()}
            pages.append(
                {
                    "filename": name,
                    "offset": offset,
                    "rows": min(1100, len(rows) - offset),
                }
            )
        dates = sorted({row[columns.index("DATE")] for row in rows})
        manifest["datasets"][dataset] = {
            "dates": dates,
            "record_count": len(rows),
            "queries": [
                {
                    "id": "current",
                    "dates": dates,
                    "record_count": len(rows),
                    "columns": columns,
                    "pages": pages,
                }
            ],
        }
    _support.save_manifest(folder, manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    args = parser.parse_args()
    settings = _support.connection_settings(args.env_file)
    target = "nomis_test_" + uuid4().hex
    scratch = loader.DIRECTORY / "data" / "test-tmp"
    scratch.mkdir(exist_ok=True)
    owned_stages = {}

    def check(expected):
        with psycopg.connect(**settings, connect_timeout=10) as conn:
            for table, (columns, rows) in expected.items():
                cur = conn.execute(
                    sql.SQL("SELECT * FROM {}").format(sql.Identifier(target, table))
                )
                assert [c.name for c in cur.description] == columns
                assert Counter(cur.fetchall()) == Counter(rows), table

    with (
        tempfile.TemporaryDirectory(dir=scratch) as temporary,
        psycopg.connect(**settings, connect_timeout=10, autocommit=True) as admin,
    ):
        folder = Path(temporary)
        manifest = fixture(args.snapshot, folder)
        tables = loader.raw_tables(folder, manifest)
        page_count = len(database._pages(manifest))
        expected = {
            name: (columns, list(rows)) for name, (columns, rows) in tables.items()
        }
        initial = {
            name: (columns, rows[:1]) for name, (columns, rows) in expected.items()
        }
        unrelated = {"unrelated": (["VALUE"], [("keep",)])}
        # A one-dataset refresh must also leave the other configured Nomis tables intact.
        unrelated.update(
            {
                name: (["VALUE"], [("keep original Nomis data",)])
                for name in loader.TABLE_NAMES.values()
                if name not in tables
            }
        )
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(target)))
        try:
            _support.replace_tables(
                args.env_file, {**initial, **unrelated}, schema=target
            )
            stage, marker = database.checkpoint_identity(manifest, target)
            owned_stages[stage] = marker
            real_copy = database.copy_batch
            real_upload = database._upload_page
            attempts = []

            def transient_copy(*args):
                real_copy(*args)
                attempts.append(1)
                if len(attempts) == 1:
                    raise psycopg.OperationalError(
                        "test connection loss before page commit"
                    )

            def stop_after_commit(*args):
                real_upload(*args)
                raise RuntimeError("test process interruption after page commit")

            with (
                patch.object(database, "copy_batch", transient_copy),
                patch.object(database, "_upload_page", stop_after_commit),
            ):
                try:
                    database.load_snapshot(
                        args.env_file,
                        folder,
                        manifest,
                        tables,
                        workers=1,
                        target_schema=target,
                    )
                except RuntimeError as exc:
                    assert "test process interruption" in str(exc)
                else:
                    raise AssertionError("Expected interrupted upload")
            assert len(attempts) == 2
            check({**initial, **unrelated})
            saved = set(
                admin.execute(
                    sql.SQL("SELECT dataset, query_id, record_offset FROM {}").format(
                        sql.Identifier(stage, "_pages")
                    )
                ).fetchall()
            )
            assert len(saved) == 1
            print(
                "PASS: failed page transaction retried; committed page survived interruption; live tables unchanged",
                flush=True,
            )
            uploaded = []

            def track(page, context):
                uploaded.append(page.key)
                return real_upload(page, context)

            with patch.object(database, "_upload_page", track):
                database.load_snapshot(
                    args.env_file,
                    folder,
                    manifest,
                    tables,
                    workers=2,
                    target_schema=target,
                )
            assert saved.isdisjoint(uploaded) and len(uploaded) == page_count - 1
            check({**expected, **unrelated})
            assert (
                admin.execute("SELECT to_regnamespace(%s)", (stage,)).fetchone()[0]
                is None
            )
            print(
                "PASS: resumed only missing pages; every original field and duplicate preserved; staging removed",
                flush=True,
            )

            # A changed fixture proves rollback after an earlier live table was already inserted.
            first_dataset = next(
                ds
                for ds in manifest["datasets"]
                if loader.TABLE_NAMES[ds] == min(tables)
            )
            name = manifest["datasets"][first_dataset]["queries"][0]["pages"][0][
                "filename"
            ]
            columns, rows = _support.read_page(folder / name, loader.REQUIRED)
            values = list(rows[0])
            values[columns.index("OBS_VALUE")] = "final-rollback-check"
            rows[0] = tuple(values)
            stored = encode(columns, rows)
            (folder / name).write_bytes(stored)
            manifest["files"][name]["sha256"] = hashlib.sha256(stored).hexdigest()
            _support.save_manifest(folder, manifest)
            changed = loader.raw_tables(folder, manifest)
            stage, marker = database.checkpoint_identity(manifest, target)
            owned_stages[stage] = marker
            last = sql.Identifier(target, max(tables))
            function = sql.Identifier(target, "skip_insert")
            admin.execute(
                sql.SQL(
                    "CREATE FUNCTION {}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$"
                ).format(function)
            )
            admin.execute(
                sql.SQL(
                    "CREATE TRIGGER skip_insert BEFORE INSERT ON {} FOR EACH ROW EXECUTE FUNCTION {}()"
                ).format(last, function)
            )
            try:
                database.load_snapshot(
                    args.env_file,
                    folder,
                    manifest,
                    changed,
                    workers=2,
                    target_schema=target,
                )
            except ValueError as exc:
                assert "Incomplete insertion" in str(exc)
            else:
                raise AssertionError("Expected final publication failure")
            check({**expected, **unrelated})
            assert (
                admin.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(
                        sql.Identifier(stage, "_pages")
                    )
                ).fetchone()[0]
                == page_count
            )
            admin.execute(sql.SQL("DROP TRIGGER skip_insert ON {}").format(last))
            admin.execute(sql.SQL("DROP FUNCTION {}()").format(function))
            print(
                "PASS: final replacement rolled back all live tables; all completed pages retained for retry",
                flush=True,
            )

            real_finish = database._finish
            finished = []

            def lose_commit_ack(*args):
                real_finish(*args)
                finished.append(1)
                raise psycopg.OperationalError(
                    "test lost acknowledgement of successful final commit"
                )

            with (
                patch.object(
                    database,
                    "_upload_page",
                    side_effect=AssertionError("Completed page uploaded again"),
                ),
                patch.object(database, "_finish", lose_commit_ack),
            ):
                database.load_snapshot(
                    args.env_file,
                    folder,
                    manifest,
                    changed,
                    workers=2,
                    target_schema=target,
                )
            assert len(finished) == 1
            check(
                {
                    **{
                        name: (cols, list(rows))
                        for name, (cols, rows) in changed.items()
                    },
                    **unrelated,
                }
            )
            assert (
                admin.execute("SELECT to_regnamespace(%s)", (stage,)).fetchone()[0]
                is None
            )
            print(
                "PASS: lost final COMMIT acknowledgement recovered without uploading or publishing twice",
                flush=True,
            )
        finally:
            for stage, marker in owned_stages.items():
                if (
                    admin.execute("SELECT to_regnamespace(%s)", (stage,)).fetchone()[0]
                    is not None
                ):
                    with admin.cursor() as cur:
                        database._assert_owned(cur, stage, marker)
                        cur.execute(
                            sql.SQL("DROP SCHEMA {} CASCADE").format(
                                sql.Identifier(stage)
                            )
                        )
            admin.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(target))
            )
            print(
                "Removed isolated test schemas; primary was never modified", flush=True
            )


if __name__ == "__main__":
    main()
