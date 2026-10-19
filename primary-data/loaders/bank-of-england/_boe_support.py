# Общие операции загрузчика BoE вынесены сюда, чтобы не повторять их в каждом модуле:
# скачивание ответов, работа с файлами и подключение к PostgreSQL.
#
# Для каждой выгрузки ведётся manifest.json — список файлов, их контрольных сумм и
# пройденных шагов. Он позволяет продолжать работу после остановки и обнаруживать
# изменённые файлы. Этот модуль не выбирает показатели и не преобразует их значения.

import hashlib
import http.client
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


# Обрабатывает порции параллельно и отменяет ещё не начатые задачи при остановке.
def parallel_map(function, items, workers):
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        yield from pool.map(function, items)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


# Хранит состояние одной выгрузки и согласует запись прогресса между потоками.
class SnapshotStore:
    # Создаёт новую папку выгрузки или открывает и проверяет существующую.
    def __init__(self, directory, resume=None):
        self.lock = threading.RLock()
        self.pending_files = 0
        if resume:
            self.folder = Path(resume)
            self.manifest = read_snapshot(self.folder, "bank-of-england")
            if self.manifest.get("format_version") != 2:
                raise ValueError(
                    "Only all-series snapshots (format_version=2) can be resumed"
                )
        else:
            self.folder, self.manifest = new_snapshot(directory, "bank-of-england")
            self.manifest.update(
                format_version=2,
                as_of=datetime.now(UTC).date().isoformat(),
                status="downloading",
            )
            self.checkpoint()

    # Сохраняет прогресс через временный файл, чтобы не оставить обрезанный JSON.
    def checkpoint(self, **updates):
        with self.lock:
            self.manifest.update(updates)
            temporary = self.folder / "manifest.json.tmp"
            temporary.write_text(
                json.dumps(self.manifest, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            temporary.replace(self.folder / "manifest.json")
            self.pending_files = 0

    # Возвращает проверенный сохранённый ответ либо скачивает его и регистрирует файл.
    def get(self, url, name):
        if Path(name).name != name:
            raise ValueError("Invalid download filename")
        with self.lock:
            cached = self.manifest["files"].get(name)
        if cached:
            raw = (self.folder / name).read_bytes()
            if (
                cached["url"] != url
                or hashlib.sha256(raw).hexdigest() != cached["sha256"]
            ):
                raise ValueError(f"Cached file does not match request: {name}")
            return raw

        partial = {"files": {}}
        raw = fetch(url, self.folder, name, partial)
        with self.lock:
            self.manifest["files"][name] = partial["files"][name]
            self.pending_files += 1

            if "series" not in self.manifest or self.pending_files >= 8:
                self.checkpoint()
        return raw


# Создаёт отдельную папку и начальное описание новой выгрузки.
def new_snapshot(directory, source):
    timestamp = datetime.now(UTC)
    folder = (
        directory
        / "data"
        / (timestamp.strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8])
    )
    folder.mkdir(parents=True)
    return folder, {
        "source": source,
        "downloaded_at": timestamp.isoformat(),
        "files": {},
    }


# Скачивает исходный ответ, сохраняет его с контрольной суммой и повторяет временные
# сетевые ошибки.
def fetch(url, folder, name, manifest):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AI-year-project/1.0 (public statistical data research)"
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
                metadata = {
                    "url": url,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "content_type": response.headers.get("Content-Type"),
                    "last_modified": response.headers.get("Last-Modified"),
                }
            if not raw:
                raise ValueError(f"Empty response: {url}")
            (folder / name).write_bytes(raw)
            manifest["files"][name] = metadata
            return raw
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 502, 503, 504) or attempt == 2:
                raise
            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    time.sleep(int(retry_after))
                    continue
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            http.client.IncompleteRead,
        ):
            if attempt == 2:
                raise
        time.sleep(2**attempt)


# Записывает описание выгрузки в manifest.json.
def save_manifest(folder, manifest):
    (folder / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# Читает описание выгрузки и проверяет источник и контрольные суммы сохранённых файлов.
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


# Собирает параметры PostgreSQL; значения из указанного env-файла имеют приоритет.
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


# Открывает соединение с PostgreSQL и при local_only разрешает только локальный сервер.
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


# Запускает команду, а при ошибке печатает короткое сообщение и завершает её с кодом 1.
def run(main):
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        import sys

        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
