#!/usr/bin/env python3
"""Refetch the Yahoo symbols the first pass lost to HTTP 429, slowly."""
import json, pathlib, sys, time, random
sys.path.insert(0, "/home/anont/meme")
from scripts.t29_crosslist.xl_fetch import yahoo_one, OUT
from scripts.t29_crosslist.xl_universe import HOME_SYMBOLS, FX_SYMBOLS, COUNTRY_ETF

for path, want in ((OUT / "home_bars.json", HOME_SYMBOLS),
                   (OUT / "fx_etf_bars.json", FX_SYMBOLS + sorted(set(COUNTRY_ETF.values())))):
    d = json.loads(path.read_text()) if path.exists() else {}
    missing = [s for s in want if s not in d]
    print(path.name, "missing", len(missing), flush=True)
    for rnd in range(4):
        if not missing:
            break
        still = []
        for s in missing:
            r = yahoo_one(s, tries=1)
            if r:
                d[s] = r
            else:
                still.append(s)
            time.sleep(4 + random.random() * 4)
        path.write_text(json.dumps(d))
        print(" round", rnd, "recovered", len(missing) - len(still), "left", len(still),
              flush=True)
        missing = still
        if missing:
            time.sleep(45)
    print(path.name, "final missing:", missing, flush=True)
print("GAPFILL DONE", flush=True)
