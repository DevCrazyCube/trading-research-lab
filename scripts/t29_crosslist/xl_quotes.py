#!/usr/bin/env python3
"""Point-in-time NBBO half-spreads for the US legs, sampled from Alpaca SIP quote ticks --
same method and clock convention as T28's dc_quotes.py (60s window at 19:55-19:56Z).
Sampled in BOTH windows so the design-window cost is a design-window measurement."""
import json, pathlib, statistics as st, sys
sys.path.insert(0, "/home/anont/meme")
from scripts.trading_bot.data import load_env_credentials, _fetch_page
from scripts.t29_crosslist.xl_universe import US_SYMBOLS, COUNTRY_ETF

CACHE = pathlib.Path("/home/anont/meme/research/data/t29_crosslist_cache")
OUT = CACHE / "quotes.json"
SYMS = sorted(set(US_SYMBOLS) | set(COUNTRY_ETF.values()))
DATES = ["2016-06-15", "2017-06-14", "2018-06-13", "2019-06-12", "2020-06-10", "2021-06-16",
         "2021-11-17", "2022-06-15", "2022-11-16", "2023-03-15", "2023-09-13", "2024-03-13",
         "2024-09-11", "2025-03-12", "2025-09-10", "2026-03-11", "2026-06-10", "2026-08-12"]


def sample(date):
    key, secret = load_env_credentials()
    per, token, pages = {}, None, 0
    for i in range(0, len(SYMS), 100):
        token = None
        while True:
            params = {"symbols": ",".join(SYMS[i:i + 100]), "start": f"{date}T19:55:00Z",
                      "end": f"{date}T19:56:00Z", "limit": 10000, "feed": "sip"}
            if token:
                params["page_token"] = token
            p = _fetch_page("/v2/stocks/quotes", params, key, secret)
            for sym, qs in (p.get("quotes") or {}).items():
                for q in qs:
                    bp, ap = q.get("bp"), q.get("ap")
                    if not bp or not ap or ap <= bp:
                        continue
                    per.setdefault(sym, []).append((ap - bp) / ((ap + bp) / 2) * 1e4)
            pages += 1
            token = p.get("next_page_token")
            if not token or pages > 400:
                break
    return {s: st.median(v) for s, v in per.items() if v}


if __name__ == "__main__":
    acc = json.loads(OUT.read_text()) if OUT.exists() else {}
    for d in DATES:
        if d in acc:
            continue
        try:
            acc[d] = sample(d)
        except Exception as exc:
            print("skip", d, repr(exc)[:120], flush=True)
            continue
        OUT.write_text(json.dumps(acc))
        print(d, "symbols", len(acc[d]), flush=True)
    print("wrote", OUT, flush=True)
