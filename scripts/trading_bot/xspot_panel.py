#!/usr/bin/env python3
"""Assemble per-symbol Binance SPOT 1d npz files into one compact daily panel.

Output: research/data/xspot_cache/spot_daily.npz
  syms (S,) str, days (T,) int64 (UTC midnight ms), and (S,T) float32 fields
  o h l c v qv n tbq   (NaN / 0 where the symbol did not trade)
"""
from __future__ import annotations
import json, os, sys
import numpy as np

CACHE = "/home/anont/meme/research/data/xspot_cache"
DAY = 86_400_000


def build(symdir, out, t0="2017-08-01", t1="2026-08-21"):
    import datetime as dt
    d0 = int(dt.datetime.fromisoformat(t0).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    d1 = int(dt.datetime.fromisoformat(t1).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    grid = np.arange(d0, d1, DAY, dtype=np.int64)
    NT = grid.size
    files = sorted(f for f in os.listdir(symdir) if f.endswith(".npz"))
    syms = [f[:-4] for f in files]
    S = len(syms)
    print(f"symbols={S} days={NT}", flush=True)
    F = {k: np.full((S, NT), np.nan, np.float32) for k in ("o", "h", "l", "c")}
    for k in ("v", "qv", "n", "tbq"):
        F[k] = np.zeros((S, NT), np.float32)
    keep = np.zeros(S, bool)
    for i, f in enumerate(files):
        z = np.load(os.path.join(symdir, f))
        t = z["t"]
        m = (t >= d0) & (t < d1) & ((t - d0) % DAY == 0)
        if m.sum() < 30:
            continue
        idx = ((t[m] - d0) // DAY).astype(np.int64)
        for k in ("o", "h", "l", "c", "v", "qv", "n", "tbq"):
            F[k][i, idx] = z[k][m]
        keep[i] = True
    kk = np.where(keep)[0]
    syms = [syms[i] for i in kk]
    out_d = {k: F[k][kk] for k in F}
    np.savez_compressed(out, syms=np.array(syms), days=grid, **out_d)
    print(f"kept {len(syms)} symbols -> {out}", flush=True)


if __name__ == "__main__":
    symdir = sys.argv[1] if len(sys.argv) > 1 else f"{CACHE}/sym"
    out = sys.argv[2] if len(sys.argv) > 2 else f"{CACHE}/spot_daily.npz"
    build(symdir, out)
