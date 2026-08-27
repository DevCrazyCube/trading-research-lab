#!/usr/bin/env python3
"""Align the cached rv_cache 5-minute bars (130 US ETFs + mega-caps, 2021-01..2026-08)
onto one common RTH grid and cache it as a single npz.

Nothing is fetched. Input: research/data/rv_cache/<SYM>.npz (t,o,h,l,c,v,vw,n).
Output: research/data/xll2_cache/intraday5m_panel.npz
"""
from __future__ import annotations
import os, glob, json
import numpy as np

ROOT = "/home/anont/meme"
SRC = f"{ROOT}/research/data/rv_cache"
OUTD = f"{ROOT}/research/data/xll2_cache"
OUT = f"{OUTD}/intraday5m_panel.npz"


def main():
    os.makedirs(OUTD, exist_ok=True)
    files = sorted(glob.glob(f"{SRC}/*.npz"))
    syms = [os.path.basename(f)[:-4] for f in files]
    # SPY is the most complete tape -> master grid
    master = np.load(f"{SRC}/SPY.npz")["t"].astype(np.int64)
    T = len(master)
    O = np.full((len(syms), T), np.nan, np.float32)
    C = np.full((len(syms), T), np.nan, np.float32)
    V = np.zeros((len(syms), T), np.float32)
    cov = {}
    for i, f in enumerate(files):
        z = np.load(f)
        t = z["t"].astype(np.int64)
        pos = np.searchsorted(master, t)
        ok = (pos < T)
        pos = pos[ok]
        hit = master[pos] == t[ok]
        pos = pos[hit]
        src = np.nonzero(ok)[0][hit]
        O[i, pos] = z["o"][src]
        C[i, pos] = z["c"][src]
        V[i, pos] = np.nan_to_num(z["v"][src] * z["c"][src])   # dollar volume
        cov[syms[i]] = float(hit.mean())
        z.close()
    np.savez_compressed(OUT, symbols=np.array(syms), t=master, o=O, c=C, dv=V)
    print(f"wrote {OUT}  syms={len(syms)} bars={T}")
    print("worst coverage:", sorted(cov.items(), key=lambda kv: kv[1])[:6])
    json.dump(cov, open(f"{OUTD}/coverage.json", "w"), indent=1)


if __name__ == "__main__":
    main()
