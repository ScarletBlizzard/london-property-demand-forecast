"""Шаг 3. Сравнить файлы одного уровня: категории, коды территорий, суммы на перекрытиях.

Запуск из папки загрузчика: python3 scripts/03_compare_schemas.py

Читает data/details.json, который создаёт шаг 2. Ничего не пишет, только печатает.
"""

import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # папка загрузчика
DATA = os.path.abspath(os.environ.get("DATA_DIR") or os.path.join(HERE, "data"))
DETAILS = os.path.join(DATA, "details.json")

with open(DETAILS, encoding="utf-8") as f:
    D = json.load(f)
short = {n: n.split("_")[-1].replace(".csv", "") for n in D}
levels = {"Borough": [], "Ward": [], "LSOA": []}
for n, d in D.items():
    if d["уровень"] in levels:
        levels[d["уровень"]].append(n)


def norm(s):
    return " ".join(s.upper().split())


for lvl, files in levels.items():
    print(f"\n######## {lvl}")
    for n in files:
        d = D[n]
        geo = d.get("geo_code") or d.get("borough")
        print(
            f"  {short[n]:10} {d['набор'][:4]} {d['months'][0]}..{d['months'][-1]} "
            f"rows={d['rows']} major={len(d.get('major', []))} "
            f"pairs={len(d.get('pairs', []))} geo={len(geo)}"
        )
    # наборы пар категория/подкатегория без учёта регистра и лишних пробелов
    P = {n: {(norm(a), norm(b)) for a, b in D[n].get("pairs", [])} for n in files}
    allp = sorted(set().union(*P.values()))
    print("  -- категории (major || minor): в каких файлах есть")
    for p in allp:
        have = [short[n] for n in files if p in P[n]]
        if len(have) != len(files):
            print(f"     {p[0][:40]:40} || {p[1][:45]:45} : {','.join(have)}")
    in_all = sum(1 for p in allp if all(p in P[n] for n in files))
    print(f"     (во всех файлах уровня: {in_all} пар)")
    # пересечение кодов территорий
    G = {n: set(D[n].get("geo_code") or D[n].get("borough")) for n in files}
    print("  -- гео: пересечение кодов с каждым файлом")
    for a in files:
        cells = " ".join(f"{short[b]}:{len(G[a] & G[b])}" for b in files)
        print(f"     {short[a]:10} {cells}")
    # суммы по месяцам на перекрытиях
    print(
        "  -- сумма по всем строкам за общие месяцы (файл A vs B): "
        "совпадающих месяцев / общих, макс. расхождение %"
    )
    for i, a in enumerate(files):
        for b in files[i + 1 :]:
            ta, tb = D[a]["month_tot"], D[b]["month_tot"]
            common = sorted(set(ta) & set(tb))
            if not common:
                continue
            eq = sum(1 for m in common if ta[m] == tb[m])
            mx = max(abs(ta[m] - tb[m]) / max(tb[m], 1) * 100 for m in common)
            print(
                f"     {short[a]:10} vs {short[b]:10} {common[0]}..{common[-1]}: "
                f"{eq}/{len(common)}, max {mx:.2f}%"
            )
