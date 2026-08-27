#!/usr/bin/env python3
"""DATA FACT probe: does the free Yahoo feed serve PER-CONTRACT futures history,
and can a historical FRONT-month curve be reconstructed from it?

Writes research/data/inv0822b_cache/contract_probe.json
"""
from __future__ import annotations
import datetime, json, pathlib, time, urllib.parse, urllib.request

OUT = pathlib.Path("/home/anont/meme/research/data/inv0822b_cache/contract_probe.json")
URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{}"
       "?period1=-2208988800&period2=2000000000&interval=1d")
MON = {1:'F',2:'G',3:'H',4:'J',5:'K',6:'M',7:'N',8:'Q',9:'U',10:'V',11:'X',12:'Z'}


def probe(sym):
    req = urllib.request.Request(URL.format(urllib.parse.quote(sym)),
                                 headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.load(r)
        res = d["chart"]["result"][0]
        ts = res["timestamp"]
        return {"ok": True, "n": len(ts),
                "first": str(datetime.date.fromtimestamp(ts[0])),
                "last": str(datetime.date.fromtimestamp(ts[-1]))}
    except Exception as e:
        return {"ok": False, "err": type(e).__name__ + ":" + str(e)[:60]}


def main():
    out = {}
    roots = [("CL", ".NYM", range(1, 13)), ("NG", ".NYM", range(1, 13)),
             ("GC", ".CMX", [2, 4, 6, 8, 10, 12]), ("ZC", ".CBT", [3, 5, 7, 9, 12]),
             ("6E", ".CME", [3, 6, 9, 12]), ("ES", ".CME", [3, 6, 9, 12])]
    for root, suf, months in roots:
        for y in [24, 25, 26, 27]:
            for m in months:
                sym = f"{root}{MON[m]}{y}{suf}"
                out[sym] = probe(sym)
                time.sleep(0.25)
        print(root, "done", flush=True)
    OUT.write_text(json.dumps(out, indent=1))
    ok = {k: v for k, v in out.items() if v.get("ok")}
    print(f"served {len(ok)}/{len(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
