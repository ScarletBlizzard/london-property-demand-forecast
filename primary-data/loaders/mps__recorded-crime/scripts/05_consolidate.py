"""Шаг 5. Собрать единую хронологию 2010-04..2026-09 по Borough, Ward и LSOA.

Запуск из папки загрузчика: python3 scripts/05_consolidate.py

Правила сборки:
  * длинный формат: строка на территорию, категорию, подкатегорию и месяц,
    нули как в источнике;
  * названия территорий и категорий как в источнике, без очистки и склейки;
  * если месяц есть в нескольких файлах, берётся самый свежий выпуск.

Пишет data/consolidated/{borough,ward,lsoa}_2010-04_2026-09.csv. Файлы создаются
только новыми: если они уже есть, скрипт остановится и ничего не испортит.
После записи файлы перечитываются с диска и сверяются: число строк,
непрерывность месяцев, суммы по месяцам.
"""

import csv
import os
import re
from collections import defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # папка загрузчика
DATA = os.path.abspath(os.environ.get("DATA_DIR") or os.path.join(HERE, "data"))
RAW = os.path.join(DATA, "raw")
OUT = os.path.join(DATA, "consolidated")
START, END = "201004", "202609"

LEVELS = {
    # файлы перечислены от самого свежего выпуска к самому старому
    "borough": {
        "files": [
            "Borough_24m_2024-10_2026-09_byz.csv",
            "Borough_historical_2020-10_2024-09_pg2.csv",
            "Borough_historical_2010-04_2024-04_3kv.csv",
        ],
        "out_cols": ["borough", "major_category", "minor_category"],
        "map": {
            "borough": ["BOCU", "BoroughName"],
            "major_category": ["Group", "MajorText"],
            "minor_category": ["SubGroup", "MinorText"],
        },
    },
    "ward": {
        "files": [
            "Ward_24m_2024-10_2026-09_w4e.csv",
            "Ward_historical_2020-10_2024-09_mmy.csv",
            "Ward_historical_2010-04_2024-04_11j.csv",
        ],
        "out_cols": [
            "ward_code",
            "ward_name",
            "borough",
            "major_category",
            "minor_category",
        ],
        "map": {
            "ward_code": ["WardCode"],
            "ward_name": ["WardName"],
            "borough": ["LookUp_BoroughName"],
            "major_category": ["Group", "MajorText"],
            "minor_category": ["SubGroup", "MinorText"],
        },
    },
    "lsoa": {
        "files": [
            "LSOA_24m_2024-10_2026-09_7gv.csv",
            "LSOA_historical_2020-10_2024-09_04d.csv",
            "LSOA_historical_2019-03_2024-04_t25.csv",
        ],
        "out_cols": [
            "lsoa_code",
            "lsoa_name",
            "borough_code",
            "major_category",
            "minor_category",
        ],
        "map": {
            "lsoa_code": ["LSOA Code"],
            "lsoa_name": ["LSOA Name"],
            "borough_code": ["Borough"],
            "major_category": ["Group", "Major Category"],
            "minor_category": ["SubGroup", "Minor Category"],
        },
    },
}


def ym_add(ym, k):
    y, m = divmod(int(ym[:4]) * 12 + int(ym[4:]) - 1 + k, 12)
    return f"{y:04d}{m + 1:02d}"


ALL = []
x = START
while x <= END:
    ALL.append(x)
    x = ym_add(x, 1)

os.makedirs(OUT, exist_ok=True)
report = {}
for level, cfg in LEVELS.items():
    frames, months_of = {}, {}
    for fn in cfg["files"]:
        df = pd.read_csv(
            os.path.join(RAW, fn), dtype=str, keep_default_na=False, encoding="utf-8"
        )
        months_of[fn] = {c for c in df.columns if re.fullmatch(r"\d{6}", c)}
        frames[fn] = df
    # на перекрытиях берём самый свежий выпуск
    pick = {}
    for m in ALL:
        src = next((fn for fn in cfg["files"] if m in months_of[fn]), None)
        assert src, f"{level}: month {m} not covered"
        pick[m] = src
    out_path = os.path.join(OUT, f"{level}_2010-04_2026-09.csv")
    expected_rows, expected_tot, windows = 0, {}, defaultdict(list)
    with open(out_path, "x", encoding="utf-8", newline="") as f:  # "x": не перезаписывать
        first = True
        for m in ALL:
            fn = pick[m]
            df = frames[fn]
            windows[fn].append(m)
            ids = {}
            for oc in cfg["out_cols"]:
                src_col = next(c for c in cfg["map"][oc] if c in df.columns)
                ids[oc] = df[src_col]
            part = pd.DataFrame(ids)
            part["month"] = f"{m[:4]}-{m[4:]}"
            part["count"] = pd.to_numeric(df[m], errors="raise").astype("int64")
            part["source"] = fn.rsplit("_", 1)[1].removesuffix(".csv")
            part.to_csv(f, header=first, index=False, lineterminator="\n")
            first = False
            expected_rows += len(part)
            expected_tot[m] = int(part["count"].sum())
    del frames
    report[level] = {
        "path": out_path,
        "expected_rows": expected_rows,
        "expected_tot": expected_tot,
        "windows": {fn: (w[0], w[-1], len(w)) for fn, w in windows.items()},
    }
    print(f"{level}: written {expected_rows} rows -> {out_path}", flush=True)

# сверка: перечитываем записанные файлы с диска
print("\nverification (re-read from disk):")
for level, r in report.items():
    rows, tot, prev, cats = 0, defaultdict(int), "", set()
    with open(r["path"], encoding="utf-8", newline="") as f:
        rd = csv.reader(f)
        h = next(rd)
        im, ic = h.index("month"), h.index("count")
        ima, imi = h.index("major_category"), h.index("minor_category")
        for row in rd:
            rows += 1
            m = row[im]
            assert m >= prev, f"{level}: not chronological at row {rows}"
            prev = m
            tot[m.replace("-", "")] += int(row[ic])
            cats.add((row[ima], row[imi]))
    months = sorted(tot)
    ok_months = months == ALL
    ok_tot = all(tot[m] == r["expected_tot"][m] for m in ALL)
    ok_rows = rows == r["expected_rows"]
    ws = sorted({c for p in cats for c in p if c != c.strip()})
    size_mb = os.path.getsize(r["path"]) / 1e6
    print(
        f"  {level}: rows={rows} ok={ok_rows}; "
        f"months {months[0]}..{months[-1]} n={len(months)} contiguous={ok_months}; "
        f"monthly totals match source={ok_tot}; distinct major/minor pairs={len(cats)}; "
        f"size={size_mb:.1f} MB; names with stray spaces={ws}"
    )
    for fn, (a, b, n) in r["windows"].items():
        print(f"      {fn}: {a}..{b} ({n} мес.)")
