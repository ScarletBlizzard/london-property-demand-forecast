"""Шаг 4. Разобрать спорные места: переименования подкатегорий, имена районов, коды вардов.

Запуск из папки загрузчика: python3 scripts/04_probe_categories.py

Читает data/details.json, который создаёт шаг 2. Ничего не пишет, только печатает.
"""

import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # папка загрузчика
DATA = os.path.abspath(os.environ.get("DATA_DIR") or os.path.join(HERE, "data"))
DETAILS = os.path.join(DATA, "details.json")

with open(DETAILS, encoding="utf-8") as f:
    D = json.load(f)


def S(key):
    """Полное имя файла по короткому коду, например '3kv'."""
    return next(n for n in D if n.endswith(key + ".csv"))


def nz(series):
    ms = [m for m, v in sorted(series.items()) if v]
    if not ms:
        return "all zero"
    return f"{ms[0]}..{ms[-1]} sum={sum(series.values()):.0f}"


watch = [
    "DOMESTIC BURGLARY",
    "BURGLARY - RESIDENTIAL",
    "RES BURGLARY OF A HOME",
    "RES BURGLARY OF UNCONNECTED BUILDING",
    "BURGLARY IN A DWELLING",
    "PUBLIC FEAR ALARM OR DISTRESS",
    "PUBLIC FEAR, ALARM OR DISTRESS",
    "DEATH SERIOUS INJURY ILLEGAL DRIVING",
    "STALKING AND HARASSMENT",
    "FRAUD AND FORGERY",
    "NFIB",
]
probe = [
    ("Borough", ["3kv", "pg2", "byz"]),
    ("Ward", ["11j", "mmy", "w4e"]),
    ("LSOA", ["e0e053d0", "t25", "04d", "7gv"]),
]
for lvl, keys in probe:
    print(f"\n#### {lvl}: ненулевые месяцы спорных подкатегорий")
    for k in keys:
        pm = D[S(k)].get("pair_month_tot", {})
        for p, ser in pm.items():
            if p.split(" || ")[1].upper() in watch:
                print(f"  {k:9} {p[:70]:70} {nz(ser)}")

# имена районов
b = {k: set(D[S(k)]["borough"]) for k in ["3kv", "pg2", "byz", "8f024edd"]}
print("\n#### районы, которых нет во всех основных файлах:")
for nm in sorted(set().union(*b.values())):
    have = [k for k in b if nm in b[k]]
    if len(have) != 4:
        print(f"  {nm:40} {have}")
for k in ["pg2", "byz"]:
    bm = D[S(k)]["borough_month_tot"]
    for nm in bm:
        if nm not in b["3kv"]:
            print(f"  {k} {nm}: {nz(bm[nm])}")
for nm in b["3kv"] - b["pg2"]:
    print(f"  3kv {nm}: {nz(D[S('3kv')]['borough_month_tot'][nm])}")

# коды вардов
print("\n#### префиксы кодов вардов")
for k in ["1f9dd143", "11j", "mmy", "w4e", "b03b8f4a"]:
    c = D[S(k)]["geo_code"]
    print(f"  {k:9}", dict(Counter(x[:6] for x in c)))
extra = sorted(set(D[S("w4e")]["geo_code"]) - set(D[S("11j")]["geo_code"]))
print("  w4e/mmy коды, которых нет в 11j:", extra)
boroughs_11j = sorted(D[S("11j")]["borough"])
print("  boroughs in 11j LookUp:", boroughs_11j[:5], "...", len(boroughs_11j))

# расхождение вардов 11j и mmy по категориям на общих месяцах
print("\n#### Ward 11j vs mmy: суммы за 2020-10..2024-04 по major")
a, c = D[S("11j")]["major_month_tot"], D[S("mmy")]["major_month_tot"]
common = [m for m in D[S("11j")]["months"] if m in D[S("mmy")]["months"]]
for mj in sorted(set(a) | set(c)):
    sa = sum(a.get(mj, {}).get(m, 0) for m in common)
    sc = sum(c.get(mj, {}).get(m, 0) for m in common)
    print(f"  {mj:40} 11j={sa:9.0f} mmy={sc:9.0f} diff={sc - sa:+.0f}")


def total(key):
    return sum(D[S(key)]["month_tot"][m] for m in common)


print("  Borough 3kv vs pg2 за те же месяцы:", total("3kv"), total("pg2"))
print("  LSOA t25 vs 04d за те же месяцы:", total("t25"), total("04d"))
extra_lsoa = sorted(set(D[S("04d")]["geo_code"]) - set(D[S("t25")]["geo_code"]))
print("  LSOA extra codes 04d-t25:", extra_lsoa)
