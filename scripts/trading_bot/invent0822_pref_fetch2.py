#!/usr/bin/env python3
"""Second pass for Family B: RAW closes + a MEASURED half-spread from historical NBBO quotes.

Two things the first pass could not do:

1. RAW (unadjusted) closes.  The spread object for a same-issuer preferred pair is the log
   PRICE RATIO, and that is only stationary on raw prices: `adjustment=all` subtracts each
   series' own dividends, so two preferreds with different coupons acquire a deterministic
   divergence in their adjusted ratio which is a pure artefact.  Raw for the LEVEL, adjusted
   for the RETURN.

2. A measured half-spread.  The real-time `quotes/latest` endpoint is 403 on these
   credentials (no real-time SIP subscription), but the HISTORICAL quote tape is entitled.
   Half-spread is therefore measured from NBBO quotes sampled in short windows on several
   past sessions -- a first-party measurement, not an assumption.
"""
from __future__ import annotations

import gzip
import json
import pathlib
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / "research" / "data" / "inv0822_tether"
CACHE.mkdir(parents=True, exist_ok=True)
HOST = "https://data.alpaca.markets"


def creds():
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k] = v.strip().strip('"').strip("'")
    return {"APCA-API-KEY-ID": env["ALPACA_API_KEY_ID"],
            "APCA-API-SECRET-KEY": env["ALPACA_API_SECRET_KEY"]}


H = creds()


def get(path, params):
    url = f"{HOST}{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=H),
                                        timeout=120) as fh:
                return json.load(fh)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503):
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise RuntimeError("give up " + url)


def universe():
    assets = json.load(gzip.open(CACHE / "assets.json.gz"))
    by_sym = {a["symbol"]: a for a in assets}
    pr = [a["symbol"] for a in assets if re.match(r"^[A-Z]+\.PR[A-Z]$", a["symbol"])]
    commons = sorted({s.split(".")[0] for s in pr} & set(by_sym))
    return sorted(set(pr) | set(commons)), by_sym


def fetch_raw(syms):
    out = {}
    B = 100
    for k in range(0, len(syms), B):
        chunk = syms[k:k + B]
        page = None
        while True:
            p = dict(symbols=",".join(chunk), timeframe="1Day", start="2018-01-01",
                     end="2026-08-20", adjustment="raw", limit=10000, feed="sip")
            if page:
                p["page_token"] = page
            js = get("/v2/stocks/bars", p)
            for s, bars in (js.get("bars") or {}).items():
                out.setdefault(s, []).extend(bars)
            page = js.get("next_page_token")
            if not page:
                break
        print(f"  raw chunk {k // B}: {len(out)}", flush=True)
    slim = {s: {b["t"][:10]: b["c"] for b in bs} for s, bs in out.items()}
    with gzip.open(CACHE / "pref_bars_raw.json.gz", "wt") as fh:
        json.dump(slim, fh)
    print("raw bars written", len(slim), flush=True)
    return slim


SAMPLE_WINDOWS = [
    ("2026-08-18T15:45:00Z", "2026-08-18T15:47:00Z"),
    ("2026-08-11T18:00:00Z", "2026-08-11T18:02:00Z"),
    ("2026-07-22T14:30:00Z", "2026-07-22T14:32:00Z"),
    ("2026-06-17T19:30:00Z", "2026-06-17T19:32:00Z"),
    ("2026-05-13T16:15:00Z", "2026-05-13T16:17:00Z"),
    ("2026-03-11T17:00:00Z", "2026-03-11T17:02:00Z"),
]


def fetch_spreads(syms):
    per = {}
    B = 50
    for (t0, t1) in SAMPLE_WINDOWS:
        for k in range(0, len(syms), B):
            chunk = syms[k:k + B]
            page = None
            while True:
                p = dict(symbols=",".join(chunk), start=t0, end=t1, limit=10000, feed="sip")
                if page:
                    p["page_token"] = page
                js = get("/v2/stocks/quotes", p)
                for s, qs in (js.get("quotes") or {}).items():
                    for q in qs:
                        bid, ask = q.get("bp") or 0, q.get("ap") or 0
                        if bid > 0 and ask > bid and (ask - bid) / ask < 0.25:
                            per.setdefault(s, []).append((ask - bid) / (ask + bid) * 1e4)
                page = js.get("next_page_token")
                if not page:
                    break
        print(f"  quotes window {t0[:10]}: {len(per)} symbols", flush=True)
    hs = {s: dict(median_half_bp=statistics.median(v), n_quotes=len(v))
          for s, v in per.items() if len(v) >= 5}
    with gzip.open(CACHE / "pref_halfspread.json.gz", "wt") as fh:
        json.dump(hs, fh)
    print("half-spreads measured for", len(hs), "symbols", flush=True)
    if hs:
        allv = sorted(v["median_half_bp"] for v in hs.values())
        print("  median of medians %.1f bp, p25 %.1f, p75 %.1f, p90 %.1f" % (
            statistics.median(allv), allv[len(allv) // 4], allv[3 * len(allv) // 4],
            allv[int(0.9 * len(allv))]), flush=True)
    return hs


def main():
    syms, by_sym = universe()
    print(f"{len(syms)} symbols", flush=True)
    if "--spreads-only" not in sys.argv:
        fetch_raw(syms)
    fetch_spreads(syms)
    flags = {s: dict(shortable=bool(by_sym[s].get("shortable")),
                     easy_to_borrow=bool(by_sym[s].get("easy_to_borrow")),
                     name=by_sym[s].get("name")) for s in syms if s in by_sym}
    with gzip.open(CACHE / "pref_flags.json.gz", "wt") as fh:
        json.dump(flags, fh)
    print("done", flush=True)


if __name__ == "__main__":
    main()
