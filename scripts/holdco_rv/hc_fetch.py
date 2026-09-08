#!/usr/bin/env python3
"""Fetch daily bars (raw + adjusted) for the holdco/corporate-structure RV universe."""
import json, pathlib, sys
sys.path.insert(0, "/home/anont/meme")
from scripts.trading_bot.data import load_env_credentials, _fetch_page
from scripts.holdco_rv.hc_universe import all_symbols

OUT = pathlib.Path("/home/anont/meme/research/data/holdco_cache")
OUT.mkdir(parents=True, exist_ok=True)
SYMS = all_symbols()
START, END = "2015-01-02", "2026-08-18"


def fetch(adjustment):
    key, secret = load_env_credentials()
    out, token, pages = {}, None, 0
    for i in range(0, len(SYMS), 60):
        chunk = ",".join(SYMS[i:i + 60])
        token = None
        while True:
            params = {"symbols": chunk, "timeframe": "1Day", "start": START, "end": END,
                      "limit": 10000, "feed": "sip", "adjustment": adjustment}
            if token:
                params["page_token"] = token
            p = _fetch_page("/v2/stocks/bars", params, key, secret)
            for sym, bars in (p.get("bars") or {}).items():
                out.setdefault(sym, []).extend(bars)
            pages += 1
            token = p.get("next_page_token")
            if not token:
                break
            if pages > 600:
                raise SystemExit("paging runaway")
    print(adjustment, "pages", pages, "symbols", len(out), "/", len(SYMS))
    print("  missing:", [s for s in SYMS if s not in out])
    return out


for adj in ("raw", "all"):
    path = OUT / f"bars_{adj}.json"
    if path.exists():
        print("cached", path)
        continue
    d = fetch(adj)
    path.write_text(json.dumps(d))
    print("wrote", path, sum(len(v) for v in d.values()), "bars")
