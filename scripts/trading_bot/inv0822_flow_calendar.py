#!/usr/bin/env python3
"""INVENT_0822 · LARGE-GROSS forced/mechanical flow — event calendar builder.

Free sources only:
  * Wikipedia "List of S&P 500 / 400 / 600 companies" -> the constituent-CHANGE tables
    (effective date, added ticker, removed ticker, reason).  This is the point-in-time
    index membership CHANGE feed that every previous round declared unavailable.
  * SEC EDGAR full-index (form.idx per quarter) -> 424B4 (IPO final prospectus) and
    424B5 (shelf takedown = secondary offering pricing supplement), joined to tickers
    through the SEC's own company_tickers.json.

Nothing here touches a trading endpoint.  Output: JSON event files under
research/data/inv0822_flow/raw/.
"""
from __future__ import annotations

import html
import json
import pathlib
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "research" / "data" / "inv0822_flow" / "raw"
UA = {"User-Agent": "meme-research/1.0 (officialjoy04@gmail.com)"}


def get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------- table parsing
class TableGrab(HTMLParser):
    """Collect every <table> as a list of rows of cell-text, honouring rowspan."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._depth = 0
        self._rows = None
        self._row = None
        self._cell = None
        self._pending: dict[int, tuple[str, int]] = {}
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._rows = []
                self._pending = {}
        elif tag == "tr" and self._depth == 1:
            self._row = []
            self._colidx = 0
        elif tag in ("td", "th") and self._depth == 1 and self._row is not None:
            self._in_cell = True
            self._cell = []
            try:
                self._span = int(a.get("rowspan", "1") or 1)
            except ValueError:
                self._span = 1
            try:
                self._cspan = max(1, int(a.get("colspan", "1") or 1))
            except ValueError:
                self._cspan = 1

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._in_cell:
            txt = re.sub(r"\s+", " ", "".join(self._cell)).strip()
            # place carried-over rowspan cells first
            while self._colidx in self._pending:
                t, n = self._pending[self._colidx]
                self._row.append(t)
                if n > 1:
                    self._pending[self._colidx] = (t, n - 1)
                else:
                    del self._pending[self._colidx]
                self._colidx += 1
            for _ in range(self._cspan):
                self._row.append(txt)
                if self._span > 1:
                    self._pending[self._colidx] = (txt, self._span - 1)
                self._colidx += 1
            self._in_cell = False
            self._cell = None
        elif tag == "tr" and self._depth == 1 and self._row is not None:
            while self._colidx in self._pending:
                t, n = self._pending[self._colidx]
                self._row.append(t)
                if n > 1:
                    self._pending[self._colidx] = (t, n - 1)
                else:
                    del self._pending[self._colidx]
                self._colidx += 1
            self._rows.append(self._row)
            self._row = None
        elif tag == "table":
            if self._depth == 1 and self._rows is not None:
                self.tables.append(self._rows)
                self._rows = None
            self._depth = max(0, self._depth - 1)

    def handle_data(self, data):
        if self._in_cell:
            self._cell.append(data)


MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"])}


def parse_date(s: str) -> str | None:
    s = s.replace(" ", " ").strip()
    s = re.sub(r"\[.*?\]", "", s).strip()
    m = re.match(r"([A-Z][a-z]+)\s+(\d{1,2}),?\s+(\d{4})", s)
    if m and m.group(1) in MONTHS:
        return f"{int(m.group(3)):04d}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
    m = re.match(r"(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})", s)
    if m and m.group(2) in MONTHS:
        return f"{int(m.group(3)):04d}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    return None


TICKER_RE = re.compile(r"^[A-Z][A-Z.\-]{0,6}$")


def clean_ticker(s: str) -> str | None:
    s = re.sub(r"\[.*?\]", "", s).replace(" ", " ").strip()
    s = s.split(" ")[0].strip()
    if not s or s in {"-", "--", "—", "–", "N/A"}:
        return None
    if not TICKER_RE.match(s):
        return None
    return s.replace(".", ".")


def scrape_index_changes(page: str, index_name: str) -> list[dict]:
    url = f"https://en.wikipedia.org/wiki/{page}"
    doc = get(url).decode("utf-8", "replace")
    p = TableGrab()
    p.feed(doc)
    events = []
    for tbl in p.tables:
        if not tbl or len(tbl) < 5:
            continue
        head = " | ".join(tbl[0]).lower()
        if "added" not in head or "removed" not in head or "date" not in head:
            continue
        # column positions
        hdr = [h.lower() for h in tbl[0]]
        # the header is usually two rows: [Date, Added, Added, Removed, Removed, Reason]
        body_start = 1
        if len(tbl) > 1 and all(c.lower() in ("ticker", "security", "date", "reason", "")
                                for c in tbl[1]):
            body_start = 2
        # locate index of the first "added" and "removed" header cell
        try:
            i_add = next(i for i, h in enumerate(hdr) if "added" in h)
            i_rem = next(i for i, h in enumerate(hdr) if "removed" in h)
        except StopIteration:
            continue
        for row in tbl[body_start:]:
            if len(row) < 4:
                continue
            d = parse_date(row[0])
            if not d:
                continue
            add = clean_ticker(row[i_add]) if i_add < len(row) else None
            rem = clean_ticker(row[i_rem]) if i_rem < len(row) else None
            reason = row[-1] if len(row) > max(i_add, i_rem) + 1 else ""
            if add:
                events.append({"index": index_name, "date": d, "ticker": add,
                               "side": "add", "reason": reason[:180]})
            if rem:
                events.append({"index": index_name, "date": d, "ticker": rem,
                               "side": "delete", "reason": reason[:180]})
    # de-dup
    seen, out = set(), []
    for e in events:
        k = (e["index"], e["date"], e["ticker"], e["side"])
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    out.sort(key=lambda e: (e["date"], e["ticker"]))
    return out


def build_index_events():
    pages = [("Historical_components_of_the_S%26P_500", "SP500"),
             ("List_of_S%26P_500_companies", "SP500"),
             ("List_of_S%26P_400_companies", "SP400"),
             ("List_of_S%26P_600_companies", "SP600")]
    allev = []
    for page, name in pages:
        try:
            ev = scrape_index_changes(page, name)
            print(f"{name}: {len(ev)} change-events "
                  f"({min((e['date'] for e in ev), default='-')} .. "
                  f"{max((e['date'] for e in ev), default='-')})")
            allev.extend(ev)
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: FAILED {exc}")
        time.sleep(1.0)
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "index_changes.json").write_text(json.dumps(allev, indent=1))
    print("total", len(allev), "->", RAW / "index_changes.json")


# ---------------------------------------------------------------- EDGAR
def build_edgar(start_year=2015, end_year=2026, forms=("424B4", "424B5")):
    forms = tuple(forms)
    RAW.mkdir(parents=True, exist_ok=True)
    tick = json.loads(get("https://www.sec.gov/files/company_tickers.json").decode())
    cik2t: dict[int, str] = {}
    for v in tick.values():
        cik2t.setdefault(int(v["cik_str"]), v["ticker"])
    print("cik->ticker map:", len(cik2t))
    (RAW / "cik_ticker.json").write_text(json.dumps(cik2t))

    rows = []
    for y in range(start_year, end_year + 1):
        for q in (1, 2, 3, 4):
            url = f"https://www.sec.gov/Archives/edgar/full-index/{y}/QTR{q}/form.idx"
            try:
                blob = get(url, timeout=120).decode("latin-1")
            except Exception as exc:  # noqa: BLE001
                print(f"{y}Q{q}: skip ({exc})")
                time.sleep(0.4)
                continue
            n = 0
            # the filed-date column is yyyymmdd in recent quarters and yyyy-mm-dd in older ones
            pat = re.compile(r"^(\S+)\s+.+?\s{2,}(\d{1,10})\s+(\d{4}-?\d{2}-?\d{2})\s+edgar/")
            for line in blob.splitlines():
                if not line.startswith(forms):   # cheap prefilter; the regex is ~100x slower
                    continue
                m = pat.match(line)
                if not m:
                    continue
                ft, cik, date = m.group(1), m.group(2), m.group(3).replace("-", "")
                if ft not in forms:
                    continue
                t = cik2t.get(int(cik))
                if not t:
                    continue
                rows.append({"form": ft, "cik": int(cik), "ticker": t,
                             "date": f"{date[:4]}-{date[4:6]}-{date[6:]}"})
                n += 1
            print(f"{y}Q{q}: {n} kept (running {len(rows)})", flush=True)
            time.sleep(0.4)
    rows.sort(key=lambda r: (r["date"], r["ticker"]))
    (RAW / "edgar_424.json").write_text(json.dumps(rows))
    print("edgar rows", len(rows))


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "index"
    if what == "index":
        build_index_events()
    elif what == "edgar":
        build_edgar()
