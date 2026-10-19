"""Copy the complete raw BoE table from local PostgreSQL without contacting BoE."""

import sys
from pathlib import Path

from _boe_support import connection_settings, read_snapshot, run
from load import COLUMNS, PREVIOUS_COLUMNS, TABLE, csv_rows, validate_snapshot

# Reuse only the generic PostgreSQL transport; no Nomis tables or API code is imported.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nomis"))
from _postgres_transfer import arguments, transfer


def main():
    args = arguments(__doc__)
    manifest = read_snapshot(args.snapshot, "bank-of-england")
    validate_snapshot(args.snapshot, manifest)
    dates = {
        row[0]
        for part in manifest["parts"]
        for row in csv_rows((args.snapshot / part["file"]).read_bytes())
    }
    tables = {
        TABLE: {
            "columns": COLUMNS,
            "rows": manifest["total_rows"],
            "dates": sorted(dates),
            "previous_columns": PREVIOUS_COLUMNS,
        }
    }
    transfer(
        connection_settings(args.source_env),
        connection_settings(args.target_env),
        tables,
        check_only=args.check_only,
        batch_size=args.batch_size,
        report_path=args.report,
    )


if __name__ == "__main__":
    run(main)
