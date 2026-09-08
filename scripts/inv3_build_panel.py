#!/usr/bin/env python3
"""INVENT-R3 (event-calendar theme): build a compact daily OHLCV panel from the t17 cache.

Two streaming passes over research/data/t17_cache/daily/chunk_*.json so peak RSS stays
well under 2 GB:
  pass 1 -- per-symbol coverage + median dollar volume (cheap scalars only)
  pass 2 -- dense float32 matrices for the selected symbols only

Output: research/data/inv3_cache/panel.npz
  dates  (T,)  YYYY-MM-DD strings
  syms   (N,)
  o,h,l,c,v  (N,T) float32, NaN where the symbol did not trade
"""
import glob
import json
import os
import sys

import numpy as np

T17 = "/home/anont/meme/research/data/t17_cache/daily"
OUT = "/home/anont/meme/research/data/inv3_cache"
MIN_DAYS = 250
MIN_MEDIAN_DOLLAR_VOL = 5e6  # $5M/day median over the symbol's own life


def main():
    os.makedirs(OUT, exist_ok=True)
    chunks = sorted(glob.glob(os.path.join(T17, "chunk_*.json")))
    print(f"{len(chunks)} chunks", flush=True)

    # ---- pass 1: coverage + liquidity, and the global date axis -------------
    keep = []
    all_dates = set()
    for i, path in enumerate(chunks):
        with open(path) as fh:
            d = json.load(fh)
        for sym, rows in d.items():
            if len(rows) < MIN_DAYS:
                continue
            dv = np.fromiter((r[5] * r[4] for r in rows), dtype=np.float64, count=len(rows))
            med = float(np.median(dv))
            if med < MIN_MEDIAN_DOLLAR_VOL:
                continue
            keep.append(sym)
            all_dates.update(r[0] for r in rows)
        del d
        if i % 25 == 0:
            print(f"  pass1 chunk {i} keep={len(keep)}", flush=True)

    dates = np.array(sorted(all_dates))
    didx = {dt: k for k, dt in enumerate(dates)}
    keepset = set(keep)
    syms = np.array(sorted(keepset))
    sidx = {s: k for k, s in enumerate(syms)}
    N, T = len(syms), len(dates)
    print(f"pass1 done: {N} symbols x {T} dates", flush=True)

    arrs = {k: np.full((N, T), np.nan, dtype=np.float32) for k in "ohlcv"}

    # ---- pass 2 ------------------------------------------------------------
    for i, path in enumerate(chunks):
        with open(path) as fh:
            d = json.load(fh)
        for sym, rows in d.items():
            if sym not in keepset:
                continue
            r = sidx[sym]
            cols = np.fromiter((didx[x[0]] for x in rows), dtype=np.int64, count=len(rows))
            for j, k in enumerate("ohlcv"):
                arrs[k][r, cols] = np.fromiter((x[j + 1] for x in rows),
                                               dtype=np.float64, count=len(rows))
        del d
        if i % 25 == 0:
            print(f"  pass2 chunk {i}", flush=True)

    np.savez_compressed(os.path.join(OUT, "panel.npz"), dates=dates, syms=syms, **arrs)
    print("wrote", os.path.join(OUT, "panel.npz"), flush=True)


if __name__ == "__main__":
    sys.exit(main())
