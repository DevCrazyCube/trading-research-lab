#!/usr/bin/env python3
"""Fetch free daily bars (Yahoo chart API) for the calendar/session sweep. Cache to disk."""
import json, os, pathlib, time, urllib.request, sys

CACHE = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "calendar_cache"
CACHE.mkdir(parents=True, exist_ok=True)

TICKERS = [
    # US equity index / size
    "SPY","QQQ","IWM","DIA","MDY","OEF","RSP",
    # international
    "EFA","EEM","EWJ","VGK","FXI","EWZ",
    # bonds / credit
    "TLT","IEF","SHY","LQD","HYG","TIP","AGG",
    # commodities / metals
    "GLD","SLV","USO","DBC","UNG",
    # sectors
    "XLF","XLK","XLE","XLV","XLP","XLY","XLI","XLU","XLB",
    # real assets / fx / vol
    "VNQ","UUP","FXE","FXY","VXX",
    # crypto proxy
    "BTC-USD","ETH-USD",
]

def fetch(sym):
    dest = CACHE / f"{sym.replace('-','_')}.json"
    if dest.exists() and dest.stat().st_size > 1000:
        return "cached"
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
           f"?period1=631152000&period2=1790000000&interval=1d&events=div%2Csplit")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        d = json.load(r)
    res = d["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose", q["close"])
    rows = []
    for i, t in enumerate(ts):
        o,h,l,c,v,a = q["open"][i],q["high"][i],q["low"][i],q["close"][i],q["volume"][i],adj[i]
        if c is None or a is None or o is None:
            continue
        rows.append([time.strftime("%Y-%m-%d", time.gmtime(t)), o,h,l,c,v,a])
    dest.write_text(json.dumps({"symbol": sym, "rows": rows}))
    return f"{len(rows)} rows {rows[0][0]}..{rows[-1][0]}"

import urllib.parse
for s in TICKERS:
    try:
        print(s, fetch(s), flush=True)
    except Exception as e:
        print(s, "ERR", type(e).__name__, e, flush=True)
    time.sleep(1.2)
