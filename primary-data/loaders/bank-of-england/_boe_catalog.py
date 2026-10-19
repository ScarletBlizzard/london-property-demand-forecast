# Чтобы скачать весь BoE, сначала нужно узнать коды всех доступных рядов. Этот модуль
# собирает их из поисковой формы сайта: отдельно проходит дневные, месячные и остальные
# частоты.
#
# Поиск разбит на страницы, причём сайт показывает не все кнопки перехода. Поэтому здесь
# проверяются номера страниц и заявленное число результатов. На выходе получается
# каталог кодов; сами значения показателей скачивает _boe_data.py.

import re
import urllib.error
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlsplit

from _boe_support import parallel_map

BASE = "https://www.bankofengland.co.uk/boeapps/database/"


# Разбирает страницу поиска: достаёт коды рядов, частоты и поля формы для следующего
# запроса.
class CatalogueHTML(HTMLParser):
    # Подготавливает поля и сразу разбирает переданный HTML.
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.hidden = {}
        self.codes = []
        self.frequencies = {}
        self.select = None
        self.option = None
        self.has_next = False
        self.form = None
        self.feed(raw.decode("utf-8-sig"))

    # Находит в HTML ссылки на ряды и элементы поисковой формы.
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.form = attrs.get("name")
        elif tag == "select":
            self.select = attrs.get("name")
        elif tag == "option" and self.select == "Frequency":
            self.option = attrs.get("value")
            if self.option and self.option != "any":
                self.frequencies[self.option] = ""
        elif tag == "input" and self.form == "form1":
            if attrs.get("type", "").lower() == "hidden":
                self.hidden[attrs["name"]] = attrs.get("value", "")
            if attrs.get("name") == "Next":
                self.has_next = True
        elif tag == "a":
            query = parse_qs(urlsplit(attrs.get("href", "")).query)
            for code in query.get("SeriesCodes", []):
                if re.fullmatch(r"[A-Z0-9]+", code):
                    self.codes.append(code)

    # Отмечает конец формы или списка, чтобы не смешивать их содержимое.
    def handle_endtag(self, tag):
        if tag == "form":
            self.form = None
        elif tag == "select":
            self.select = None
        elif tag == "option":
            self.option = None

    # Собирает видимый текст страницы и названия частот.
    def handle_data(self, data):
        self.text.append(data)
        if self.select == "Frequency" and self.option in self.frequencies:
            self.frequencies[self.option] += data.strip()

    # Читает номер страницы и число результатов; отсутствие этих сведений считает
    # ошибкой.
    def page(self):
        text = " ".join(" ".join(self.text).split())
        match = re.search(
            r"Page\s+(\d+),\s+results\s+(\d+)\s+to\s+(\d+)\s+of\s+(\d+)", text
        )
        if not match:
            if re.search(
                r"(?:no (?:matching )?(?:data )?(?:series|results)|0 results)",
                text,
                re.IGNORECASE,
            ):
                return 1, 0, 0, 0
            raise ValueError(
                "BoE catalogue page has no result count; refusing an incomplete catalogue"
            )
        return tuple(map(int, match.groups()))


# Обходит все частоты из формы BoE и возвращает полный каталог рядов.
def discover(store, workers=2):
    form = CatalogueHTML(store.get(BASE + "advsearch.asp", "catalog_form.html"))
    if not form.frequencies:
        raise ValueError("No frequencies in the BoE catalogue form")

    # Проходит страницы одной частоты и проверяет, что коды не пропущены и не
    # повторяются.
    def frequency(item):
        code, label = item
        params = {
            "SearchType": "Advanced",
            "SearchText": "",
            "SearchTextFields": "TC",
            "Frequency": code,
            "Cat1": "any",
            "Cat2": "any",
            "Cat8": "any",
            "Travel": "NIxASx",
        }
        result = []
        expected_page, expected_start, total = 1, 1, None
        files = []
        while True:
            name = f"catalog_{code}_{expected_page:04d}.html"
            alternate = name.replace(".html", "_button.html")
            button = {k: v for k, v in params.items() if not k.startswith("Next.")}
            button.update(
                {f"PageNo{expected_page}.x": "2", f"PageNo{expected_page}.y": "1"}
            )
            if alternate in store.manifest["files"]:
                name = alternate
                raw = store.get(store.manifest["files"][name]["url"], name)
            else:
                try:
                    raw = store.get(
                        BASE + "FromShowColumns.asp?" + urlencode(params), name
                    )
                except urllib.error.URLError, TimeoutError:
                    if expected_page == 1:
                        raise

                    name = alternate
                    raw = store.get(
                        BASE + "FromShowColumns.asp?" + urlencode(button), name
                    )
            page = CatalogueHTML(raw)
            number, first, last, count = page.page()
            if total is None:
                total = count
            if (
                count != total
                or number != expected_page
                or (count and first != expected_start)
            ):
                raise ValueError(
                    f"Catalogue pagination changed for {code}; start a new snapshot"
                )
            codes = list(dict.fromkeys(page.codes))
            if len(codes) != (last - first + 1 if count else 0) or set(
                codes
            ).intersection(result):
                raise ValueError(
                    f"Missing or repeated catalogue entries on {code}, page {number}"
                )
            result.extend(codes)
            files.append(name)
            if number == 1 or number % 10 == 0 or last == total:
                print(f"Catalogue {code} ({label}): {len(result)}/{total}", flush=True)
            if last == total:
                break
            if number >= 16:
                page_size = last - first + 1
                pages = (total + page_size - 1) // page_size
                params = dict(page.hidden)
                params["ActualResNumPerPage"] = "".join(
                    f"{i * page_size + 1}X" for i in range(1, pages + 1)
                )
                params.update(
                    {f"PageNo{number + 1}.x": "1", f"PageNo{number + 1}.y": "1"}
                )
            else:
                if not page.has_next:
                    raise ValueError(f"BoE omitted the next page for {code}")
                params = dict(page.hidden, **{"Next.x": "1", "Next.y": "1"})
            expected_page += 1
            expected_start = last + 1
        return code, {"name": label, "count": total, "codes": result, "files": files}

    groups = dict(parallel_map(frequency, form.frequencies.items(), workers))
    codes = [code for group in groups.values() for code in group["codes"]]
    if not codes or len(codes) != len(set(codes)):
        raise ValueError(
            "Empty catalogue or series occurring under multiple frequencies"
        )
    return groups
