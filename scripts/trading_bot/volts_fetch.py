#!/usr/bin/env python3
"""Extra free daily symbols for the INVENT_D0821 vol-term-structure DIRECTIONAL sweep.

Everything else (^VIX/^VIX9D/^VIX3M/^VIX6M/^VVIX/SPY/^GSPC/TLT/SHY) is already
cached under research/data/volterm_cache/raw and is reused unchanged.

This adds only the equity legs and the sibling implied-vol indices that the
volatility-ETP sweep did not need:

  QQQ, IWM   -- tradable high-beta / small-cap legs for curve-driven rotation
  ^VXN, ^RVX -- CBOE 30d implied vol on NDX and RUT (sibling curves)
  ^VXD       -- CBOE 30d implied vol on DJIA
  ^SKEW      -- kept only as a control input, not a term-structure signal

Source: Yahoo chart API v8 (keyless, free), same surface as volterm_fetch.py.
Usage:  python3 scripts/trading_bot/volts_fetch.py [--force]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
import urllib.parse
import urllib.request

CACHE = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "volts_cache"
RAW = CACHE / "raw"
URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{}"
       "?period1=-2208988800&period2=2000000000&interval=1d&events=div%2Csplit")

SYMS = ["QQQ", "IWM", "^VXN", "^RVX", "^VXD", "^SKEW"]


def fetch(sym: str, tries: int = 3) -> dict:
    req = urllib.request.Request(
        URL.format(urllib.parse.quote(sym)),
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"},
    )
    last = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2.0 * (k + 1))
    raise RuntimeError(f"{sym}: {last}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    man = {}
    for s in SYMS:
        p = RAW / (s + ".json")
        if p.exists() and not a.force:
            man[s] = {"status": "cached", "bytes": p.stat().st_size}
            print(s, "cached", flush=True)
            continue
        try:
            d = fetch(s)
            res = d["chart"]["result"][0]
            p.write_text(json.dumps(d))
            man[s] = {"status": "ok", "n": len(res.get("timestamp") or []),
                      "bytes": p.stat().st_size}
            print(s, man[s], flush=True)
        except Exception as e:  # noqa: BLE001
            man[s] = {"status": "fail", "err": str(e)}
            print(s, "FAIL", e, flush=True)
        time.sleep(1.5)
    (CACHE / "MANIFEST.json").write_text(json.dumps(man, indent=2))


if __name__ == "__main__":
    main()
