#!/usr/bin/env python3
"""Extra free daily cache for INVENT_0822B (futures/FX mechanical-roll & seasonal).

Source: Yahoo chart v8 (keyless). Stooq confirmed dead 2026-08-22 (JS PoW challenge).
Raw JSON preserved unmodified. Reuses research/data/ts_cache/raw for symbols already
cached by the earlier term-structure sweeps; only NEW symbols land here.
"""
from __future__ import annotations
import json, pathlib, sys, time, urllib.parse, urllib.request

ROOT = pathlib.Path("/home/anont/meme")
CACHE = ROOT / "research" / "data" / "inv0822b_cache" / "raw"
URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{}"
       "?period1=-2208988800&period2=2000000000&interval=1d&events=div%2Csplit")

# local-currency equity indices, for the FX month-end hedge-rebalancing mechanism
EQ_LOCAL = ["^GDAXI", "^N225", "^FTSE", "^AXJO", "^GSPTSE", "^SSMI", "^STOXX50E"]
# bond legs for the month-end index-extension mechanism
BONDS = ["AGG", "LQD", "BND", "VGIT", "TLH", "GOVT"]
FXX = ["DX=F", "UUP", "FXE", "FXY", "FXB", "FXA", "FXC", "FXF"]
MISC = ["USDJPY=X", "USDCAD=X", "USDCHF=X", "EURUSD=X"]
ALL = EQ_LOCAL + BONDS + FXX + MISC


def fetch(sym, tries=3):
    req = urllib.request.Request(URL.format(urllib.parse.quote(sym)),
                                 headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{sym}: {last!r}")


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    man = {}
    for s in ALL:
        p = CACHE / (s.replace("/", "_") + ".json")
        if p.exists():
            man[s] = {"status": "cached", "bytes": p.stat().st_size}
            continue
        try:
            d = fetch(s)
            p.write_text(json.dumps(d))
            man[s] = {"status": "ok", "bytes": p.stat().st_size}
        except Exception as e:
            man[s] = {"status": "FAIL", "err": repr(e)}
        print(s, man[s]["status"], flush=True)
        time.sleep(0.4)
    (CACHE.parent / "MANIFEST.json").write_text(json.dumps(man, indent=1))
    print(json.dumps({k: v["status"] for k, v in man.items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
