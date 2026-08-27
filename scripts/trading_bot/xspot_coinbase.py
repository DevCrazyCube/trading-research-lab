#!/usr/bin/env python3
"""Fetch free Coinbase Exchange daily candles for the cross-venue spot dispersion family."""
from __future__ import annotations
import json, os, time, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import requests
from requests.adapters import HTTPAdapter

CACHE = "/home/anont/meme/research/data/xspot_cache"
OUT = f"{CACHE}/coinbase_daily.npz"
API = "https://api.exchange.coinbase.com"
SESS = requests.Session()
SESS.mount("https://", HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=2))
SESS.headers["User-Agent"] = "research/1.0"
DAY = 86400


def products():
    r = SESS.get(f"{API}/products", timeout=60)
    r.raise_for_status()
    return [p["id"] for p in r.json() if p.get("quote_currency") == "USD"]


def candles(pid, t0, t1):
    out = []
    s = t0
    while s < t1:
        e = min(s + 295 * DAY, t1)
        for attempt in range(5):
            try:
                r = SESS.get(f"{API}/products/{pid}/candles",
                             params={"granularity": 86400,
                                     "start": dt.datetime.fromtimestamp(s, dt.timezone.utc).isoformat(),
                                     "end": dt.datetime.fromtimestamp(e, dt.timezone.utc).isoformat()},
                             timeout=60)
                if r.status_code == 429:
                    time.sleep(1.0 + attempt)
                    continue
                if r.status_code != 200:
                    break
                out += r.json()
                break
            except Exception:
                time.sleep(0.5 + attempt)
        s = e
        time.sleep(0.12)
    return out


def main():
    bases = json.load(open(f"{CACHE}/cb_bases.json"))
    prods = set(products())
    want = [f"{b}-USD" for b in bases if f"{b}-USD" in prods]
    print(f"coinbase products matched: {len(want)}", flush=True)
    t0 = int(dt.datetime(2017, 8, 1, tzinfo=dt.timezone.utc).timestamp())
    t1 = int(dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc).timestamp())
    grid = np.arange(t0, t1, DAY)
    idxmap = {int(t): i for i, t in enumerate(grid)}
    C = np.full((len(want), grid.size), np.nan, np.float32)
    V = np.zeros((len(want), grid.size), np.float32)

    def work(j):
        rows = candles(want[j], t0, t1)
        for row in rows:
            i = idxmap.get(int(row[0]))
            if i is not None:
                C[j, i] = row[4]          # close
                V[j, i] = row[5] * row[4]  # base volume x close ~ dollar volume
        return want[j], len(rows)

    with ThreadPoolExecutor(max_workers=6) as ex:
        for k, (p, n) in enumerate(ex.map(work, range(len(want)))):
            if (k + 1) % 10 == 0:
                print(f"  {k+1}/{len(want)} {p} {n}", flush=True)
    np.savez_compressed(OUT, syms=np.array(want), days=(grid.astype(np.int64) * 1000), c=C, qv=V)
    print("DONE", OUT, flush=True)


if __name__ == "__main__":
    main()
