"""Шаг 1. Скачать файлы источника из london_crime_files.csv в data/raw/.

Запуск из папки загрузчика: python3 scripts/01_download.py

Файлы качаются по одному: пауза 1,5 с, User-Agent браузера, до 3 повторов
при сетевых ошибках. Уже скачанные файлы с совпадающим размером пропускаются,
ничего не перезаписывается. На ответы 401/403/407/429/451 или при недоступности
хоста скрипт останавливается и завершается с ошибкой.
"""

import csv
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # папка загрузчика
DATA = os.path.abspath(os.environ.get("DATA_DIR") or os.path.join(HERE, "data"))
LINKS = os.path.join(HERE, "london_crime_files.csv")
RAW = os.path.join(DATA, "raw")
LOG = os.path.join(DATA, "download_log.json")

# Python с python.org на macOS не видит системные корневые сертификаты.
# Берём системный набор macOS, проверка сертификата остаётся включённой.
if not os.environ.get("SSL_CERT_FILE") and os.path.exists("/etc/ssl/cert.pem"):
    SSL_CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
else:
    SSL_CTX = ssl.create_default_context()

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)
PAUSE = 1.5
RETRIES = 3  # повторов после первой попытки
STOP_CODES = {401, 403, 407, 429, 451}


def expected_bytes(s):
    m = re.match(r"\s*([\d.,]+)\s*(kB|KB|MB|GB|B)\s*$", s)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    mult = {"B": 1, "kB": 1000, "KB": 1000, "MB": 1000**2, "GB": 1000**3}[m.group(2)]
    return v * mult


def size_matches(actual, exp_str, tol=0.03):
    exp = expected_bytes(exp_str)
    if exp is None:
        return None
    # портал может считать kB как 1000 или 1024 байт: проверяем оба варианта
    if "kB" in exp_str:
        alt = exp * 1.024
    elif "MB" in exp_str:
        alt = exp * 1.048576
    else:
        alt = exp
    return any(abs(actual - base) / base <= tol for base in (exp, alt))


class Stop(Exception):
    pass


def fetch(url, dest_part):
    last_err = None
    for attempt in range(1 + RETRIES):
        if attempt:
            time.sleep(PAUSE * (attempt + 1))
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": UA,
                "Accept": "text/csv,application/octet-stream,*/*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as r:
                final_url = r.geturl()
                clen = r.headers.get("Content-Length")
                ctype = r.headers.get("Content-Type")
                n = 0
                with open(dest_part, "wb") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        n += len(chunk)
                if clen is not None and int(clen) != n:
                    raise OSError(f"truncated: got {n} of {clen} bytes")
                return {
                    "status": r.status,
                    "final_url": final_url,
                    "bytes": n,
                    "content_length": clen,
                    "content_type": ctype,
                    "attempts": attempt + 1,
                }
        except urllib.error.HTTPError as e:
            host = urlparse(e.geturl() or url).hostname
            if e.code in STOP_CODES:
                raise Stop(f"HTTP {e.code} from host {host} ({e.geturl()})") from e
            if 500 <= e.code < 600:
                last_err = f"HTTP {e.code} from host {host}"
                continue
            return {
                "status": e.code,
                "error": f"HTTP {e.code} from host {host}",
                "attempts": attempt + 1,
            }
        except OSError as e:  # сетевые ошибки, таймауты, обрыв загрузки
            last_err = f"{type(e).__name__}: {getattr(e, 'reason', e)}"
            continue
    host = urlparse(url).hostname
    raise Stop(f"host {host} unavailable after {1 + RETRIES} attempts: {last_err}")


def main():
    os.makedirs(RAW, exist_ok=True)
    with open(LINKS, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    log = []
    first_request = True
    stopped = None
    for row in rows:
        name, url, size_s = row["локальное_имя"], row["url"], row["размер"]
        dest = os.path.join(RAW, name)
        rec = {"локальное_имя": name, "url": url, "размер": size_s}
        if os.path.exists(dest):
            actual = os.path.getsize(dest)
            ok = size_matches(actual, size_s)
            rec["result"] = "skipped_exists" if ok else "skipped_exists_size_mismatch"
            rec["bytes"] = actual
            print(f"SKIP  {name}: exists ({actual} B), size match={ok}", flush=True)
            log.append(rec)
            continue
        if stopped:
            rec["result"] = "not_attempted"
            log.append(rec)
            continue
        if not first_request:
            time.sleep(PAUSE)
        first_request = False
        part = dest + ".part"
        try:
            info = fetch(url, part)
        except Stop as e:
            stopped = str(e)
            rec.update(result="stopped", error=stopped)
            print(f"STOP  {name}: {stopped}", flush=True)
            if os.path.exists(part):
                os.remove(part)
            log.append(rec)
            continue
        rec.update(info)
        if "error" in info:
            rec["result"] = "failed"
            if os.path.exists(part):
                os.remove(part)
            print(f"FAIL  {name}: {info['error']}", flush=True)
        elif os.path.exists(dest):  # на всякий случай не перезаписываем
            rec["result"] = "exists_race_not_overwritten"
            os.remove(part)
        else:
            os.rename(part, dest)
            rec["result"] = "downloaded"
            final_host = urlparse(info["final_url"]).hostname
            print(
                f"OK    {name}: {info['bytes']} B, {info['content_type']}, "
                f"attempts={info['attempts']}, final={final_host}",
                flush=True,
            )
        log.append(rec)
    with open(LOG, "w", encoding="utf-8") as f:
        json.dump({"stopped": stopped, "files": log}, f, ensure_ascii=False, indent=1)
    print("STOPPED:", stopped if stopped else "no", flush=True)
    failed = [r["локальное_имя"] for r in log if r.get("result") == "failed"]
    if stopped or failed:
        sys.exit(f"Скачаны не все файлы. Остановка: {stopped}. Ошибки: {failed}")


if __name__ == "__main__":
    main()
