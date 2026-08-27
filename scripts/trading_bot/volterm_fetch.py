#!/usr/bin/env python3
"""Free daily cache for the VOLATILITY-ETP TERM-STRUCTURE / ROLL sweep.

Source: Yahoo chart API v8 (keyless, free) -- the same surface ts_fetch.py uses.
Stooq is behind a JS proof-of-work challenge and is not usable headlessly.

Raw JSON is written unmodified to research/data/volterm_cache/raw/<sym>.json.
Symbols already present from ts_cache are copied in by the caller and skipped here.

Usage:  python3 scripts/trading_bot/volterm_fetch.py [--force]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

CACHE = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "volterm_cache"
RAW = CACHE / "raw"
URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{}"
       "?period1=-2208988800&period2=2000000000&interval=1d&events=div%2Csplit")

# --- the universe -----------------------------------------------------------
# CBOE volatility indices: the term structure of 30-day-equivalent implied vol.
VOL_IDX = ["^VIX", "^VIX9D", "^VIX3M", "^VIX6M", "^VVIX", "^VIX1D"]

# Long-vol ETPs (all hold VIX futures and MUST roll daily).
LONG_VOL = [
    "VXX",     # iPath B S&P500 VIX Short-Term (1x, constant 30d)
    "VIXY",    # ProShares VIX Short-Term (1x, constant 30d)
    "UVXY",    # ProShares Ultra VIX Short-Term (2x -> 1.5x from 2018-02-28)
    "UVIX",    # Volatility Shares 2x Long VIX Short-Term (2022-03)
    "VXZ",     # iPath B S&P500 VIX Mid-Term (1x, constant ~5m)
    "VIXM",    # ProShares VIX Mid-Term (1x, constant ~5m)
]

# Short-vol ETPs (long positions -- no stock borrow needed to be short vol).
SHORT_VOL = [
    "SVXY",    # ProShares Short VIX Short-Term (-1x -> -0.5x from 2018-02-28)
    "SVIX",    # Volatility Shares -1x Short VIX Short-Term (2022-06)
    "ZIVB",    # -0.5x mid-term (2022)
]

# Other VRP-harvesting vehicles, same mechanism family, different wrapper.
VRP_FUNDS = ["PUTW", "SVOL", "XYLD", "JEPI"]

# Benchmarks / hedge legs / collateral.
BENCH = ["SPY", "^GSPC", "SHY", "BIL", "SHV", "TLT", "^IRX"]

ALL = VOL_IDX + LONG_VOL + SHORT_VOL + VRP_FUNDS + BENCH


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
            print(f"  {sym:10s} cached", flush=True)
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
            first = res[0]["meta"].get("firstTradeDate")
            manifest[sym] = {"status": "ok", "n": n, "bytes": path.stat().st_size,
                             "firstTradeDate": first}
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
