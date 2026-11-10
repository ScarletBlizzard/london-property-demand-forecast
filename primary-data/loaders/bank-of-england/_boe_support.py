"""Проверка готовой выгрузки и подключение к PostgreSQL."""

import hashlib
import json
import os
from pathlib import Path


def read_snapshot(folder, source):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest["source"] != source:
        raise ValueError(f"Expected a {source} snapshot")
    for name, metadata in manifest["files"].items():
        if Path(name).name != name:
            raise ValueError("Invalid snapshot filename")
        if (
            hashlib.sha256((folder / name).read_bytes()).hexdigest()
            != metadata["sha256"]
        ):
            raise ValueError(f"Snapshot checksum mismatch: {name}")
    return manifest


def connection_settings(env_file):
    names = {
        "PGHOST": "host",
        "PGPORT": "port",
        "PGDATABASE": "dbname",
        "PGUSER": "user",
        "PGPASSWORD": "password",
        "PGSSLMODE": "sslmode",
        "PGPASSFILE": "passfile",
    }
    settings = {key: os.environ[key] for key in names if key in os.environ}
    if env_file:
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if not separator or key.strip() not in names:
                raise ValueError(
                    "Environment file must contain literal PG*=value lines, not shell commands"
                )
            settings[key.strip()] = value
    if any(not settings.get(key) for key in ("PGHOST", "PGDATABASE", "PGUSER")):
        raise ValueError(
            "Explicit PGHOST, PGDATABASE and PGUSER are required; use --env-file or environment variables"
        )
    return {names[key]: value for key, value in settings.items()}


def connect(env_file, local_only=False):
    import psycopg

    settings = connection_settings(env_file)
    if local_only:
        if settings["host"] not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("--local-only refuses a non-local PostgreSQL host")

        settings["hostaddr"] = "::1" if settings["host"] == "::1" else "127.0.0.1"
    print(
        f"Connecting to {settings['host']}:{settings.get('port', '5432')}/{settings['dbname']} as {settings['user']}",
        flush=True,
    )
    return psycopg.connect(
        **settings, connect_timeout=10, application_name="primary-data-loader"
    )


def run(main):
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        import sys

        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
