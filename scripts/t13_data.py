#!/usr/bin/env python3
"""T13 — data layer for the risk-shaping (distribution-shape) test.

Stdlib only, like the rest of `scripts/trading_bot`. Fetches, normalises and hashes the four
series the T13 pre-registration names, and writes them to `research/data/t13_cache/` with a
manifest so every number downstream is reproducible from a sha256.

    python scripts/t13_data.py build          # fetch + normalise + manifest
    python scripts/t13_data.py verify         # re-hash what is on disk

SERIES
    spx_price.csv    ^GSPC daily close, Yahoo chart API, 1927-12-30 -> today. PRICE ONLY.
    spy_tr.csv       SPY daily adjusted close, Yahoo, 1993-01-29 -> today. TOTAL RETURN.
    sp500tr.csv      ^SP500TR daily close, Yahoo, 1988-01-04 -> today. TOTAL RETURN.
    cash.csv         daily cash yield, annualised percent, spliced:
                       1928-01-03..1933-12-31  NBER 3-month commercial paper, monthly (M13002US...)
                       1934-01-01..1953-12-31  FRED TB3MS, 3-month bill, monthly
                       1954-01-04..today       FRED DTB3, 3-month bill, daily
                     Monthly values are held flat within the month (step, never interpolated
                     forward across a value that had not been published).

KNOWN IMPRECISIONS, recorded here rather than in a message that can drift:
  * DTB3/TB3MS are quoted on a BANK DISCOUNT basis. Treating them as a simple annualised yield
    UNDERSTATES the cash return by roughly 2-4% relative. The filter sits in cash, so this is
    the conservative direction for the filter's claim and it is left uncorrected.
  * ^GSPC is price-only. It is used for the SIGNAL and for the 1928-1989 design window only.
    Every held-out return number is computed on a total-return series.
  * Yahoo adjusted closes are retroactive: today's adjustment factors are applied to 1993 bars.
    That is correct for total return and wrong for price LEVELS. Nothing here filters on a level.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import time
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "research" / "data" / "t13_cache"
UA = "Mozilla/5.0 (X11; Linux x86_64)"

YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=-2208988800&period2=2000000000&interval=1d"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"


class Refused(Exception):
    """Absence is refusal, never zero (FINDINGS §8)."""


def _get(url: str, attempts: int = 4) -> bytes:
    last = ""
    for k in range(attempts):
        out = subprocess.run(
            ["curl", "-sS", "--fail", "--http1.1", "--max-time", "90", "-A", UA, url],
            capture_output=True,
        )
        if out.returncode == 0 and out.stdout:
            return out.stdout
        last = out.stderr.decode()[:200] or "empty body"
        time.sleep(2 * (k + 1))
    raise Refused(f"fetch failed {url}: {last}")


def _yahoo_daily(symbol: str, field: str) -> list[tuple[str, float]]:
    """field: 'close' (raw) or 'adjclose' (total return)."""
    raw = json.loads(_get(YAHOO.format(sym=symbol.replace("^", "%5E"))))
    res = raw["chart"]["result"]
    if not res:
        raise Refused(f"no result for {symbol}: {raw['chart'].get('error')}")
    r = res[0]
    ts = r["timestamp"]
    if field == "adjclose":
        vals = r["indicators"]["adjclose"][0]["adjclose"]
    else:
        vals = r["indicators"]["quote"][0]["close"]
    tz = r["meta"]["exchangeTimezoneName"]
    rows: list[tuple[str, float]] = []
    for t, v in zip(ts, vals):
        if v is None:
            continue  # a null close is missing data, not a zero return
        # Yahoo daily stamps are the session open in exchange time; UTC date is enough to
        # recover the trading date because US sessions never cross a UTC date at 09:30 ET.
        d = dt.datetime.fromtimestamp(t, dt.UTC)
        if tz.startswith("America"):
            d = d - dt.timedelta(hours=5)
        rows.append((d.date().isoformat(), float(v)))
    rows.sort()
    # de-duplicate: a partial last bar can repeat the previous date
    dedup: list[tuple[str, float]] = []
    for d, v in rows:
        if dedup and dedup[-1][0] == d:
            dedup[-1] = (d, v)
        else:
            dedup.append((d, v))
    if len(dedup) < 1000:
        raise Refused(f"{symbol}: only {len(dedup)} bars, refusing")
    return dedup


def _raw(name: str, url: str) -> bytes:
    """Raw-response cache. FRED throttles hard; a retry storm is not more honest than a cache."""
    p = CACHE / "raw" / name
    if p.exists() and p.stat().st_size > 0:
        return p.read_bytes()
    body = _get(url)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(body)
    return body


def _fred(series_id: str) -> list[tuple[str, float]]:
    text = _raw(f"fred_{series_id}.csv", FRED.format(sid=series_id)).decode()
    rows = []
    for rec in csv.DictReader(text.splitlines()):
        keys = list(rec.keys())
        d, v = rec[keys[0]], rec[keys[1]]
        if v in (".", "", None):
            continue
        rows.append((d, float(v)))
    if not rows:
        raise Refused(f"FRED {series_id} returned no usable rows")
    return sorted(rows)


def _write(name: str, header: list[str], rows: list[tuple]) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / name
    with p.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    return {"file": name, "rows": len(rows), "first": rows[0][0], "last": rows[-1][0], "sha256": h}


def build() -> dict:
    man = {"built_utc": dt.datetime.now(dt.UTC).isoformat(), "series": []}

    spx = _yahoo_daily("^GSPC", "close")
    man["series"].append(_write("spx_price.csv", ["date", "close"], spx))

    spy = _yahoo_daily("SPY", "adjclose")
    man["series"].append(_write("spy_tr.csv", ["date", "adjclose"], spy))

    tr = _yahoo_daily("^SP500TR", "close")
    man["series"].append(_write("sp500tr.csv", ["date", "close"], tr))

    # --- cash: splice three sources, latest-available-wins, never interpolated ---
    nber = _fred("M13002US35620M156NNBR")   # 3-month commercial paper, monthly, 1857-1971
    tb3ms = _fred("TB3MS")                  # 3-month bill, monthly, 1934-
    dtb3 = _fred("DTB3")                    # 3-month bill, daily, 1954-

    monthly: dict[str, tuple[float, str]] = {}
    for d, v in nber:
        if d < "1934-01-01":
            monthly[d[:7]] = (v, "NBER_CP_3M")
    for d, v in tb3ms:
        if d < "1954-01-01":
            monthly[d[:7]] = (v, "FRED_TB3MS")

    cash: list[tuple[str, float, str]] = []
    for d, v in dtb3:
        cash.append((d, v, "FRED_DTB3"))
    # expand the monthly part onto month-start stamps; the reader holds the last value flat
    for ym in sorted(monthly):
        v, src = monthly[ym]
        cash.append((f"{ym}-01", v, src))
    cash.sort()
    man["series"].append(_write("cash.csv", ["date", "annual_pct", "source"], cash))

    (CACHE / "MANIFEST.json").write_text(json.dumps(man, indent=2) + "\n")
    return man


def verify() -> dict:
    man = json.loads((CACHE / "MANIFEST.json").read_text())
    bad = []
    for s in man["series"]:
        h = hashlib.sha256((CACHE / s["file"]).read_bytes()).hexdigest()
        if h != s["sha256"]:
            bad.append(s["file"])
    if bad:
        raise Refused(f"hash mismatch: {bad}")
    return man


# ---------------------------------------------------------------- readers used downstream

def read_series(name: str) -> tuple[list[str], list[float]]:
    dates, vals = [], []
    with (CACHE / name).open() as fh:
        for rec in csv.reader(fh):
            if rec[0] == "date":
                continue
            dates.append(rec[0])
            vals.append(float(rec[1]))
    return dates, vals


def read_cash_daily(dates: list[str]) -> list[float]:
    """Annualised percent cash yield aligned to `dates`, held flat from the last publication.

    Refuses rather than defaulting to zero if a date precedes the first published rate.
    """
    stamps, rates = [], []
    with (CACHE / "cash.csv").open() as fh:
        for rec in csv.reader(fh):
            if rec[0] == "date":
                continue
            stamps.append(rec[0])
            rates.append(float(rec[1]))
    out, j, cur = [], 0, None
    for d in dates:
        while j < len(stamps) and stamps[j] <= d:
            cur = rates[j]
            j += 1
        if cur is None:
            raise Refused(f"no cash rate published on or before {d}")
        out.append(cur)
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    m = build() if cmd == "build" else verify()
    print(json.dumps(m, indent=2))
