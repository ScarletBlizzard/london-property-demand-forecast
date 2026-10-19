#!/usr/bin/env python3
"""
Читает со stdin JSON страницы публикации из Content API gov.uk и печатает в
stdout ссылку на единственное вложение в формате ODS.

Имя файла меняется с каждым релизом (MPT_Tab_Sep_26.ods, MPT_Tab_Oct_26.ods...),
поэтому ссылку нельзя зашивать в загрузчик — её каждый раз берём со страницы.
"""

import json
import sys

page = json.load(sys.stdin)
attachments = page.get("details", {}).get("attachments", [])

ods = [
    a["url"]
    for a in attachments
    if a.get("url")
    and (
        a.get("content_type") == "application/vnd.oasis.opendocument.spreadsheet"
        or a["url"].lower().endswith(".ods")
    )
]

if len(ods) != 1:
    sys.exit(
        f"на странице публикации {len(ods)} вложений ODS вместо одного: {ods} — "
        f"состав релиза изменился, загрузчик нужно перечитать"
    )

print(ods[0])
