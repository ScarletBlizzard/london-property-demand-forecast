"""Шаг 2. Проверить скачанные файлы и записать data/manifest.csv.

Запуск из папки загрузчика: python3 scripts/02_check_files.py

Для каждого файла из london_crime_files.csv проверяет размер, кодировку,
число строк, месяцы, пропуски, географию и категории. Подробности по каждому
файлу пишет в data/details.json: их читают шаги 3 и 4.
"""

import csv
import io
import json
import os
import re
from collections import Counter

import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # папка загрузчика
DATA = os.path.abspath(os.environ.get("DATA_DIR") or os.path.join(HERE, "data"))
LINKS = os.path.join(HERE, "london_crime_files.csv")
RAW = os.path.join(DATA, "raw")
MANIFEST = os.path.join(DATA, "manifest.csv")
DETAILS = os.path.join(DATA, "details.json")


def exp_bytes(s):
    m = re.match(r"\s*([\d.]+)\s*(kB|MB)\s*$", s)
    v, u = float(m.group(1)), m.group(2)
    return v * (1024 if u == "kB" else 1024**2)


def detect_encoding(b):
    if b.startswith(b"\xef\xbb\xbf"):
        try:
            return "utf-8-sig (BOM)", b[3:].decode("utf-8"), None
        except UnicodeDecodeError:
            pass
    try:
        return "utf-8", b.decode("utf-8"), None
    except UnicodeDecodeError as e:
        bad = b[max(0, e.start - 30) : e.start + 30]
        info = f"invalid utf-8 at byte {e.start}: {bad!r}"
        for enc in ("cp1252", "latin-1"):
            try:
                return enc, b.decode(enc), info
            except UnicodeDecodeError:
                continue


def ym_ok(c):
    return bool(re.fullmatch(r"(19|20)\d{2}(0[1-9]|1[0-2])", c.strip()))


def ym_add(ym, k):
    y, m = divmod(int(ym[:4]) * 12 + int(ym[4:]) - 1 + k, 12)
    return f"{y:04d}{m + 1:02d}"


def ym_range(a, b):
    out, x = [], a
    while x <= b:
        out.append(x)
        x = ym_add(x, 1)
    return out


def fmt_ym(x):
    return f"{x[:4]}-{x[4:]}"


def ranges(months):
    """['201004', '201005', ...] -> '2010-04..2010-05, ...'"""
    months = sorted(set(months))
    if not months:
        return ""
    out, start, prev = [], months[0], months[0]
    for m in months[1:]:
        if m == ym_add(prev, 1):
            prev = m
            continue
        out.append((start, prev))
        start = prev = m
    out.append((start, prev))
    return ", ".join(
        fmt_ym(a) if a == b else f"{fmt_ym(a)}..{fmt_ym(b)}" for a, b in out
    )


ROLE_PATTERNS = [
    ("geo_code", r"(?i)^(ward ?code|lsoa ?code|borough ?code|.*code)$"),
    ("major", r"(?i)^(majortext|major ?category|major|group|crime ?group)$"),
    ("minor", r"(?i)^(minortext|minor ?category|minor|subgroup|sub ?group|crime ?type)$"),
    ("borough", r"(?i)^(boroughname|borough|bocu|lookup_boroughname|borough ?name)$"),
    ("geo_name", r"(?i)^(ward ?name|lsoa ?name)$"),
]


def roles(cols):
    r = {}
    for c in cols:
        for role, pat in ROLE_PATTERNS:
            if re.match(pat, c.strip()) and role not in r:
                r[role] = c
                break
    return r


def strip_all(frame):
    return frame.apply(lambda s: s.str.strip())


with open(LINKS, encoding="utf-8-sig", newline="") as f:
    links = list(csv.DictReader(f))

manifest, details = [], {}
for L in links:
    name, level, kit = L["локальное_имя"], L["уровень"], L["набор"]
    p = os.path.join(RAW, name)
    rec = {"набор": kit, "уровень": level, "локальное_имя": name}
    if not os.path.exists(p):
        rec["проблемы"] = "файл не скачан"
        manifest.append(rec)
        continue
    with open(p, "rb") as fh:
        b = fh.read()
    eb = exp_bytes(L["размер"])
    rec["размер_заявлен"] = L["размер"]
    rec["размер_байт"] = len(b)
    rec["размер_откл_%"] = round((len(b) - eb) / eb * 100, 2)
    rec["размер_ок"] = abs(len(b) - eb) / eb <= 0.02
    enc, text, enc_info = detect_encoding(b)
    rec["кодировка"] = enc
    problems = []
    if enc_info:
        problems.append(enc_info)
    crlf = text.count("\r\n")
    # структура CSV
    rdr = list(csv.reader(io.StringIO(text)))
    header = [h.strip() for h in rdr[0]]
    body = [r for r in rdr[1:] if any(x.strip() for x in r)]
    blank = len(rdr) - 1 - len(body)
    widths = Counter(len(r) for r in body)
    if set(widths) != {len(header)}:
        problems.append(f"разная ширина строк: header={len(header)}, rows={dict(widths)}")
    if blank:
        problems.append(f"пустых строк: {blank}")
    rec["строк_данных"] = len(body)
    rec["больше_1_строки"] = len(rdr) > 1 and len(body) >= 1
    month_cols = [c for c in header if ym_ok(c)]
    id_cols = [c for c in header if not ym_ok(c)]
    rl = roles(id_cols)
    df = pd.DataFrame(body, columns=header) if body else pd.DataFrame(columns=header)
    month_col_name = None
    if month_cols:
        months = sorted(month_cols)
        month_col_name = f"широкий формат: {len(month_cols)} колонок-месяцев ГГГГММ"
        if month_cols != months:
            month_col_name += " (в заголовке не по порядку)"
        vals = df[month_cols].apply(
            lambda s: pd.to_numeric(s.str.strip().replace("", "0"), errors="coerce")
        )
        nonnum = int(vals.isna().sum().sum())
        if nonnum:
            problems.append(f"нечисловых значений в месяцах: {nonnum}")
        neg = int((vals < 0).sum().sum())
        if neg:
            problems.append(f"отрицательных значений: {neg}")
        month_tot = {m: float(vals[m].sum()) for m in months}
    else:
        # запасной вариант: длинный формат с колонкой месяца
        cand = [c for c in id_cols if re.search(r"(?i)month|date|period", c)]
        months, month_tot = [], {}
        if cand:
            month_col_name = cand[0]
            parsed = pd.to_datetime(df[cand[0]], errors="coerce")
            months = sorted(set(parsed.dropna().dt.strftime("%Y%m")))
        else:
            problems.append("не найдена колонка месяца")
    rec["колонок"] = len(header)
    rec["колонки"] = "; ".join(id_cols) + (
        f"; {months[0]}..{months[-1]}" if month_cols else ""
    )
    rec["колонка_месяца"] = month_col_name
    rec["мин_месяц"] = fmt_ym(months[0]) if months else ""
    rec["макс_месяц"] = fmt_ym(months[-1]) if months else ""
    rec["месяцев"] = len(months)
    gaps = sorted(set(ym_range(months[0], months[-1])) - set(months)) if months else []
    rec["пропуски_внутри"] = ranges(gaps) if gaps else "нет"
    if month_cols:
        zero_m = [m for m in months if month_tot[m] == 0]
        if zero_m:
            problems.append(f"месяцы с нулевой суммой: {ranges(zero_m)}")
    gcol = rl.get("geo_code") or rl.get("geo_name") or rl.get("borough")
    rec["гео_колонка"] = gcol or ""
    rec["гео_уникальных"] = int(df[gcol].str.strip().nunique()) if gcol else ""
    rec["колонки_категорий"] = " / ".join(
        x for x in (rl.get("major"), rl.get("minor")) if x
    )
    rec["категорий_major"] = (
        int(df[rl["major"]].str.strip().nunique()) if "major" in rl else ""
    )
    rec["категорий_minor"] = (
        int(df[rl["minor"]].str.strip().nunique()) if "minor" in rl else ""
    )
    key = list(id_cols)
    dups = int(df.duplicated(subset=key).sum()) if key else 0
    if dups:
        problems.append(f"дублей по ключу {key}: {dups}")
    rec["переводы_строк"] = "CRLF" if crlf else "LF"
    rec["проблемы"] = " | ".join(problems)
    manifest.append(rec)
    # подробности для сравнения файлов на шагах 3 и 4
    d = {
        "набор": kit,
        "уровень": level,
        "header": header,
        "id_cols": id_cols,
        "roles": rl,
        "months": months,
        "month_tot": month_tot,
        "rows": len(body),
    }
    for role in ("major", "minor", "borough", "geo_code", "geo_name"):
        if role in rl:
            d[role] = sorted(set(df[rl[role]].str.strip()))
    if "major" in rl and "minor" in rl:
        d["pairs"] = sorted(
            set(zip(df[rl["major"]].str.strip(), df[rl["minor"]].str.strip()))
        )
        if month_cols:
            g = pd.concat([strip_all(df[[rl["major"]]]), vals], axis=1)
            g = g.groupby(rl["major"]).sum()
            d["major_month_tot"] = {
                mj: {m: float(g.loc[mj, m]) for m in months} for mj in g.index
            }
            g2 = pd.concat([strip_all(df[[rl["major"], rl["minor"]]]), vals], axis=1)
            g2 = g2.groupby([rl["major"], rl["minor"]]).sum()
            d["pair_month_tot"] = {
                f"{a} || {b}": {m: float(g2.loc[(a, b), m]) for m in months}
                for a, b in g2.index
            }
    if "borough" in rl and month_cols:
        g3 = pd.concat([strip_all(df[[rl["borough"]]]), vals], axis=1)
        g3 = g3.groupby(rl["borough"]).sum()
        d["borough_month_tot"] = {
            bo: {m: float(g3.loc[bo, m]) for m in months} for bo in g3.index
        }
    details[name] = d

cols = [
    "набор",
    "уровень",
    "локальное_имя",
    "размер_заявлен",
    "размер_байт",
    "размер_откл_%",
    "размер_ок",
    "кодировка",
    "переводы_строк",
    "больше_1_строки",
    "строк_данных",
    "колонок",
    "колонки",
    "колонка_месяца",
    "мин_месяц",
    "макс_месяц",
    "месяцев",
    "пропуски_внутри",
    "гео_колонка",
    "гео_уникальных",
    "колонки_категорий",
    "категорий_major",
    "категорий_minor",
    "проблемы",
]
os.makedirs(DATA, exist_ok=True)
with open(MANIFEST, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in manifest:
        w.writerow(r)
with open(DETAILS, "w", encoding="utf-8") as f:
    json.dump(details, f, ensure_ascii=False)

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 50)
pd.set_option("display.max_colwidth", 60)
shown = [
    "локальное_имя",
    "размер_байт",
    "размер_откл_%",
    "размер_ок",
    "кодировка",
    "переводы_строк",
    "строк_данных",
    "мин_месяц",
    "макс_месяц",
    "месяцев",
    "пропуски_внутри",
    "гео_колонка",
    "гео_уникальных",
    "категорий_major",
    "категорий_minor",
]
print(pd.DataFrame(manifest)[shown].to_string(index=False))
print()
for r in manifest:
    print(f"{r['локальное_имя']}: колонки = {r.get('колонки')}")
    if r.get("проблемы"):
        print(f"   ПРОБЛЕМЫ: {r['проблемы']}")
