#!/usr/bin/env python3
"""Fetch daily OPEN prices for the bond-ETF RV universe.

WHY.  The design run's edge collapses from gross Sharpe 6.2 at L=1 to 0.9 at L=2, and the
spreads carry rho1(d spread) of -0.20 to -0.53.  Both are the signature of close-print noise:
the signal is computed FROM close(t) and the L=1 book is filled AT close(t), so the same
bid-ask realisation that makes the spread look cheap is the price you pay.  A half-spread
charge does not fix a signal that is CORRELATED with which side of the spread printed.

The clean discriminator on free daily data is to make the signal price and the entry price
DIFFERENT PRINTS.  Signal from close(t); fill at open(t+1); exit at open(t+2).  Any edge that
survives that is not the close-print bounce.  Yahoo's chart payload already carries `open`;
the original ratescredit fetcher discarded it.  This adds it, unadjusted, alongside the
existing adjusted-close total-return series.
"""
from __future__ import annotations

import json
import pathlib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / "research" / "data" / "ratescredit_cache"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-daily-fetch"}

SYMS = [
    "HYG", "JNK", "USHY", "HYLB", "SJNK", "SHYG", "ANGL",
    "LQD", "USIG", "IGIB", "VCIT", "IGSB", "VCSH", "SPIB", "VCLT",
    "TLT", "VGLT", "SPTL", "IEF", "VGIT", "SHY", "VGSH", "SCHO", "IEI", "SCHR",
    "TLH", "GOVT", "EDV", "ZROZ",
    "AGG", "BND", "MBB", "TIP", "SCHP", "MUB", "TFI", "EMB", "BKLN", "SRLN",
    "PFF", "PGX", "SPY",
]


def main() -> None:
    p = CACHE / "etf_open.json"
    out = json.loads(p.read_text()) if p.exists() else {}
    for i, s in enumerate(SYMS):
        if s in out:
            continue
        u = (f"https://query1.finance.yahoo.com/v8/finance/chart/{s}"
             f"?period1=0&period2=1790000000&interval=1d")
        try:
            raw = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read()
            r = json.loads(raw)["chart"]["result"][0]
            q = r["indicators"]["quote"][0]
            out[s] = {"t": r["timestamp"], "open": q["open"], "close": q["close"]}
            print(f"[{i+1}/{len(SYMS)}] {s}: {len(r['timestamp'])} rows", flush=True)
        except Exception as e:                                # noqa: BLE001
            print(f"  {s}: FAIL {e}", flush=True)
        time.sleep(1.2)
        if i % 8 == 7:
            p.write_text(json.dumps(out))
    p.write_text(json.dumps(out))
    print(f"wrote {p} ({len(out)} symbols)", flush=True)


if __name__ == "__main__":
    main()
