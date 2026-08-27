#!/usr/bin/env python3
"""Free daily OHLCV cache for the futures term-structure / carry sweep.

Source: Yahoo chart API v8 (keyless, free). Stooq is behind a JS proof-of-work
challenge as of 2026-08-20 and is NOT usable headlessly, so Yahoo is the whole
free-data surface here.

Raw JSON responses are written unmodified to research/data/ts_cache/raw/<sym>.json
(AGENTS.md: preserve raw, derive reproducibly). The sweep reads only the cache.

Usage:  python3 scripts/trading_bot/ts_fetch.py [--force]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CACHE = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "ts_cache"
RAW = CACHE / "raw"
URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{}"
       "?period1=-2208988800&period2=2000000000&interval=1d&events=div%2Csplit")

# --- the universe -----------------------------------------------------------
COMMOD_FUT = [
    "CL=F", "BZ=F", "NG=F", "HO=F", "RB=F",              # energy
    "GC=F", "SI=F", "HG=F", "PL=F", "PA=F",              # metals
    "ZC=F", "ZS=F", "ZW=F", "ZL=F", "ZM=F", "ZO=F",      # grains/oilseeds
    "KC=F", "SB=F", "CC=F", "CT=F", "OJ=F",              # softs
    "LE=F", "HE=F", "GF=F",                              # livestock
]
EQ_FUT = ["ES=F", "NQ=F", "YM=F", "RTY=F"]
EQ_SPOT = ["^GSPC", "^NDX", "^DJI", "^RUT"]
RATE_FUT = ["ZT=F", "ZF=F", "ZN=F", "ZB=F"]
YIELDS = ["^IRX", "^FVX", "^TNX", "^TYX"]
FX_FUT = ["6E=F", "6J=F", "6B=F", "6A=F", "6C=F", "6S=F", "DX=F"]
FX_SPOT = ["EURUSD=X", "JPY=X", "GBPUSD=X", "AUDUSD=X", "CAD=X", "CHF=X"]
VOL = ["^VIX", "^VIX9D", "^VIX3M", "^VIX6M", "^VVIX"]
ETF = [
    "USO", "USL", "BNO", "UNG", "UNL", "UGA",            # energy roll ladders
    "DBC", "GSG", "DJP", "PDBC", "COMT", "FTGC",         # broad commodity
    "DBA", "DBB", "DBE", "CORN", "WEAT", "SOYB", "CANE", # sector/single
    "GLD", "SLV", "IAU", "PPLT", "CPER",                 # metals spot-ish
    "SPY", "TLT", "IEF", "SHY", "VIXY", "SVXY",          # financial legs
]
ALL = COMMOD_FUT + EQ_FUT + EQ_SPOT + RATE_FUT + YIELDS + FX_FUT + FX_SPOT + VOL + ETF


def fetch(sym: str, tries: int = 3) -> dict:
    req = urllib.request.Request(
        URL.format(urllib.parse.quote(sym)),
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"},
    )
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2.0 * (i + 1))
    raise RuntimeError(f"{sym}: {last!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for sym in ALL:
        path = RAW / (sym.replace("/", "_") + ".json")
        if path.exists() and not args.force:
            manifest[sym] = {"status": "cached", "bytes": path.stat().st_size}
            continue
        try:
            raw = fetch(sym)
            res = raw.get("chart", {}).get("result")
            if not res:
                manifest[sym] = {"status": "empty"}
                print(f"  {sym:10s} EMPTY", flush=True)
                continue
            path.write_text(json.dumps(raw))
            n = len(res[0].get("timestamp") or [])
            manifest[sym] = {"status": "ok", "n": n, "bytes": path.stat().st_size}
            print(f"  {sym:10s} {n:6d} bars", flush=True)
        except Exception as e:  # noqa: BLE001
            manifest[sym] = {"status": "error", "err": repr(e)[:200]}
            print(f"  {sym:10s} ERR {e!r}"[:160], flush=True)
        time.sleep(0.7)
    (CACHE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    ok = sum(1 for v in manifest.values() if v["status"] in ("ok", "cached"))
    print(f"cached {ok}/{len(ALL)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
