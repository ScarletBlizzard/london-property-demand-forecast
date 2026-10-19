"""Copy complete raw Nomis tables from local PostgreSQL, without using the Nomis API."""

from _nomis_support import connection_settings, copy_batch, read_snapshot, run
from _postgres_transfer import arguments, transfer
from load import raw_tables


def main():
    args = arguments(__doc__, multiple_snapshots=True)
    tables = {}
    for folder in args.snapshot:
        manifest = read_snapshot(folder, "nomis")
        if manifest.get("version") != 2 or manifest.get("status") != "complete":
            raise ValueError(
                "Only complete Nomis v2 snapshots can validate the local database"
            )
        for table, (fields, rows) in raw_tables(folder, manifest).items():
            if table in tables:
                raise ValueError(f"{table}: provided by more than one snapshot")
            tables[table] = {
                "columns": fields,
                "rows": len(rows),
                "dates": sorted(rows.dates),
            }
    transfer(
        connection_settings(args.source_env),
        connection_settings(args.target_env),
        tables,
        check_only=args.check_only,
        batch_size=args.batch_size,
        report_path=args.report,
        copy_batch=copy_batch,
    )


if __name__ == "__main__":
    run(main)
