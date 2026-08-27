#!/usr/bin/env python3
"""Second pass: RAW (unadjusted) daily closes for the preferred universe.

The spread object for a same-issuer preferred pair is the log PRICE RATIO, and that is only
stationary on RAW prices: adjustment=all subtracts each series' own dividends, so two
preferreds with different coupons acquire a deterministic divergence in their adjusted ratio
that is a pure artefact.  Raw closes for the LEVEL, adjusted closes for the RETURN.
"""
from __future__ import annotations

import gzip
import json
import re

from scripts.trading_bot.invent0822_pref_fetch import CACHE, get


def main():
    assets = json.load(gzip.open(CACHE / "assets.json.gz"))
    by_sym = {a["symbol"]: a for a in assets}
    pr = [a["symbol"] for a in assets if re.match(r"^[A-Z]+\.PR[A-Z]$", a["symbol"])]
    commons = sorted({s.split(".")[0] for s in pr} & set(by_sym))
    syms = sorted(set(pr) | set(commons))
    out = {}
    B = 100
    for k in range(0, len(syms), B):
        chunk = syms[k:k + B]
        page = None
        while True:
            p = dict(symbols=",".join(chunk), timeframe="1Day",
                     start="2018-01-01", end="2026-08-20", adjustment="raw",
                     limit=10000, feed="sip")
            if page:
                p["page_token"] = page
            js = get("/v2/stocks/bars", p)
            for s, bars in (js.get("bars") or {}).items():
                out.setdefault(s, []).extend(bars)
            page = js.get("next_page_token")
            if not page:
                break
        print(f"  raw chunk {k//B}: {len(out)}", flush=True)
    slim = {s: {b["t"][:10]: b["c"] for b in bs} for s, bs in out.items()}
    with gzip.open(CACHE / "pref_bars_raw.json.gz", "wt") as fh:
        json.dump(slim, fh)
    print("raw bars written", len(slim))


if __name__ == "__main__":
    main()
