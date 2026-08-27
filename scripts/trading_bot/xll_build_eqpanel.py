#!/usr/bin/env python3
"""XLL: reduce the 2.4G t17 daily-bar cache to a compact liquid-universe float32 daily panel."""
from __future__ import annotations
import json, os, sys
import numpy as np

ROOT = "/home/anont/meme"
SRC = f"{ROOT}/research/data/t17_cache/daily"
OUT = f"{ROOT}/research/data/xll_cache/eq_daily_panel.npz"
MIN_DAYS = 900
MIN_MED_DV = 3e6   # $3M median daily dollar volume


def main():
    files = sorted(os.path.join(SRC, f) for f in os.listdir(SRC) if f.endswith(".json"))
    print(f"{len(files)} chunks", flush=True)
    all_dates = set()
    kept = {}
    for fi, p in enumerate(files):
        d = json.load(open(p))
        for sym, rows in d.items():
            if len(rows) < MIN_DAYS:
                continue
            dv = np.fromiter((r[4] * r[5] for r in rows[-750:]), np.float64)
            if dv.size == 0 or np.median(dv) < MIN_MED_DV:
                continue
            dates = [r[0] for r in rows]
            close = np.fromiter((r[4] for r in rows), np.float32)
            vol = np.fromiter((r[5] for r in rows), np.float32)
            opn = np.fromiter((r[1] for r in rows), np.float32)
            kept[sym] = (dates, opn, close, vol)
            all_dates.update(dates)
        del d
        if fi % 20 == 0:
            print(f"  chunk {fi} kept={len(kept)}", flush=True)
    dates = sorted(all_dates)
    di = {x: i for i, x in enumerate(dates)}
    syms = sorted(kept)
    NT = len(dates)
    C = np.full((len(syms), NT), np.nan, np.float32)
    O = np.full((len(syms), NT), np.nan, np.float32)
    V = np.zeros((len(syms), NT), np.float32)
    for i, s in enumerate(syms):
        dd, o, c, v = kept[s]
        idx = np.fromiter((di[x] for x in dd), np.int64)
        O[i, idx] = o; C[i, idx] = c; V[i, idx] = v
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez_compressed(OUT, symbols=np.array(syms), dates=np.array(dates), close=C, open=O, vol=V)
    print(f"WROTE {OUT} shape={C.shape} dates {dates[0]}..{dates[-1]}", flush=True)


if __name__ == "__main__":
    main()
