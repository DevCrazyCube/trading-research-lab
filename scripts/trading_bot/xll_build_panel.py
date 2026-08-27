#!/usr/bin/env python3
"""Cross-asset lead-lag (XLL): build a compact 5m Binance USD-M perp panel from cached klines.

Reduces research/data/orphanflush_cache/raw/klines5m (2.7G of monthly/daily zips) to a single
float32 npz on a fixed 5m grid. Streams one symbol at a time; peak RSS is one preallocated
matrix, not the raw zips.
"""
from __future__ import annotations
import io, os, sys, zipfile
import numpy as np

ROOT = "/home/anont/meme"
KL = f"{ROOT}/research/data/orphanflush_cache/raw/klines5m"
OUT = f"{ROOT}/research/data/xll_cache/perp5m_panel.npz"

T0 = 1672531200000   # 2023-01-01 00:00 UTC
T1 = 1787011200000   # 2026-08-18 00:00 UTC
STEP = 300_000
GRID = np.arange(T0, T1, STEP, dtype=np.int64)
NT = GRID.size


def symbol_files(sym):
    d = os.path.join(KL, sym)
    return sorted(os.path.join(d, f) for f in os.listdir(d))


def load_symbol(sym):
    """Return (idx, close, qv, tbqv) arrays for grid slots this symbol covers."""
    idxs, cls, qvs, tbs = [], [], [], []
    for p in symbol_files(sym):
        tag = os.path.basename(p).split("-5m-")[1].replace(".zip", "")
        # cheap prefilter: skip files entirely before 2023
        if tag[:4] < "2023":
            continue
        try:
            with zipfile.ZipFile(p) as z:
                name = z.namelist()[0]
                buf = z.read(name)
        except Exception:
            continue
        txt = buf.decode("utf-8", "replace")
        for line in txt.splitlines():
            if not line or line[0] not in "0123456789":
                continue
            f = line.split(",")
            try:
                t = int(f[0])
            except ValueError:
                continue
            if t < T0 or t >= T1 or (t - T0) % STEP:
                continue
            idxs.append((t - T0) // STEP)
            cls.append(float(f[4]))
            qvs.append(float(f[7]))
            tbs.append(float(f[10]))
    if not idxs:
        return None
    return (np.asarray(idxs, np.int64), np.asarray(cls, np.float32),
            np.asarray(qvs, np.float32), np.asarray(tbs, np.float32))


def main():
    syms = []
    for s in sorted(os.listdir(KL)):
        fs = os.listdir(os.path.join(KL, s))
        months = sorted(f.split("-5m-")[1].replace(".zip", "") for f in fs)
        monthly = [m for m in months if len(m) == 7]
        if monthly and monthly[0] <= "2023-01":
            syms.append(s)
    print(f"universe candidates: {len(syms)}", flush=True)

    close = np.full((len(syms), NT), np.nan, np.float32)
    qv = np.zeros((len(syms), NT), np.float32)
    tbqv = np.zeros((len(syms), NT), np.float32)
    keep = []
    for i, s in enumerate(syms):
        r = load_symbol(s)
        if r is None:
            print(f"  skip {s}: no bars", flush=True)
            continue
        idx, c, q, tb = r
        close[len(keep), idx] = c
        qv[len(keep), idx] = q
        tbqv[len(keep), idx] = tb
        keep.append(s)
        if len(keep) % 20 == 0:
            print(f"  {len(keep)}/{len(syms)} loaded ({s}) cov={np.isfinite(close[len(keep)-1]).mean():.2f}", flush=True)
    n = len(keep)
    close, qv, tbqv = close[:n], qv[:n], tbqv[:n]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez_compressed(OUT, symbols=np.array(keep), grid=GRID, close=close, qv=qv, tbqv=tbqv)
    print(f"WROTE {OUT}  shape={close.shape}", flush=True)


if __name__ == "__main__":
    main()
