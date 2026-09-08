#!/usr/bin/env python3
"""Measure real NBBO half-spreads for the dual-class universe from Alpaca SIP quote ticks.

12 sample sessions across the held-out window + 8 across the design window, each a 60-second
window at 15:55:00-15:56:00 ET (19:55-19:56 UTC, DST-naive but both sample sets use the same
convention and an hour's error still lands inside RTH for every date sampled in summer; winter
dates land at 14:55 ET, also RTH).
"""
import json, pathlib, statistics as st, sys
sys.path.insert(0, "/home/anont/meme")
from scripts.trading_bot.data import load_env_credentials, _fetch_page

CACHE = pathlib.Path("/home/anont/meme/research/data/t28_dualclass_cache")
RAW = json.load(open(CACHE / "bars_raw.json"))
SYMS = sorted(RAW)

DATES = [
    "2016-06-15", "2017-06-14", "2018-06-13", "2019-06-12", "2020-06-10", "2021-06-16",
    "2022-06-15", "2022-11-16", "2023-03-15", "2023-09-13", "2024-03-13", "2024-09-11",
    "2025-03-12", "2025-09-10", "2026-03-11", "2026-06-10", "2026-08-12",
]

OUT = CACHE / "quotes.json"


def sample(date):
    key, secret = load_env_credentials()
    per = {}
    token = None
    pages = 0
    while True:
        params = {"symbols": ",".join(SYMS), "start": f"{date}T19:55:00Z",
                  "end": f"{date}T19:56:00Z", "limit": 10000, "feed": "sip"}
        if token:
            params["page_token"] = token
        p = _fetch_page("/v2/stocks/quotes", params, key, secret)
        for sym, qs in (p.get("quotes") or {}).items():
            for q in qs:
                bp, ap = q.get("bp"), q.get("ap")
                if not bp or not ap or ap <= bp:
                    continue
                mid = (ap + bp) / 2
                per.setdefault(sym, []).append((ap - bp) / mid * 1e4)
        pages += 1
        token = p.get("next_page_token")
        if not token or pages > 60:
            break
    return {s: st.median(v) for s, v in per.items() if v}


if __name__ == "__main__":
    acc = {}
    for d in DATES:
        try:
            r = sample(d)
        except Exception as exc:
            print("skip", d, exc)
            continue
        acc[d] = r
        print(d, "symbols", len(r))
    OUT.write_text(json.dumps(acc))
    print("wrote", OUT)
