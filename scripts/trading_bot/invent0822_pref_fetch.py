#!/usr/bin/env python3
"""Fetch daily bars for same-issuer PREFERRED series + their common, and a quote snapshot.

DATA endpoint only.  Cached to research/data/inv0822_cache/.
"""
from __future__ import annotations

import gzip
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / "research" / "data" / "inv0822_cache"
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
            req = urllib.request.Request(url, headers=H)
            with urllib.request.urlopen(req, timeout=120) as fh:
                return json.load(fh)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503):
                time.sleep(2 * (attempt + 1))
                continue
            raise
    raise RuntimeError("give up " + url)


def main():
    assets = json.load(gzip.open(CACHE / "assets.json.gz"))
    by_sym = {a["symbol"]: a for a in assets}
    pr = [a["symbol"] for a in assets if re.match(r"^[A-Z]+\.PR[A-Z]$", a["symbol"])]
    roots = sorted({s.split(".")[0] for s in pr})
    commons = [r for r in roots if r in by_sym]
    syms = sorted(set(pr) | set(commons))
    print(f"{len(pr)} preferred series, {len(commons)} commons, {len(syms)} symbols")

    feed = "sip"
    out = {}
    B = 100
    for k in range(0, len(syms), B):
        chunk = syms[k:k + B]
        page = None
        while True:
            p = dict(symbols=",".join(chunk), timeframe="1Day",
                     start="2018-01-01", end="2026-08-20", adjustment="all",
                     limit=10000, feed=feed)
            if page:
                p["page_token"] = page
            js = get("/v2/stocks/bars", p)
            for s, bars in (js.get("bars") or {}).items():
                out.setdefault(s, []).extend(bars)
            page = js.get("next_page_token")
            if not page:
                break
        print(f"  chunk {k//B}: {len(out)} symbols so far", flush=True)

    slim = {s: {b["t"][:10]: b["c"] for b in bs} for s, bs in out.items()}
    with gzip.open(CACHE / "pref_bars.json.gz", "wt") as fh:
        json.dump(slim, fh)
    print("bars written", len(slim))

    # quote snapshot -> measured half-spread per symbol (point-in-time vendor snapshot)
    q = {}
    for k in range(0, len(syms), B):
        chunk = syms[k:k + B]
        js = get("/v2/stocks/quotes/latest", dict(symbols=",".join(chunk), feed=feed))
        for s, v in (js.get("quotes") or {}).items():
            bid, ask = v.get("bp") or 0, v.get("ap") or 0
            if bid > 0 and ask > bid:
                q[s] = dict(bid=bid, ask=ask, half_bp=(ask - bid) / (ask + bid) * 1e4)
    with gzip.open(CACHE / "pref_quotes.json.gz", "wt") as fh:
        json.dump(q, fh)
    print("quotes written", len(q))

    flags = {s: dict(shortable=bool(by_sym[s].get("shortable")),
                     easy_to_borrow=bool(by_sym[s].get("easy_to_borrow")),
                     name=by_sym[s].get("name")) for s in syms if s in by_sym}
    with gzip.open(CACHE / "pref_flags.json.gz", "wt") as fh:
        json.dump(flags, fh)
    print("done")


if __name__ == "__main__":
    main()
