#!/usr/bin/env python3
"""Trim panel1h_ext.npz to the names and hours the round-2 sweep can actually use.

439 symbols x 40536 hours is ~700MB of float32 per 10 fields, and the box is shared. The
sweep never trades outside the top-50 by trailing-7d volume, so symbols that never reach the
top-150 by total traded notional are dead weight, and hours before 2022-10 only exist to warm
up a 720h rolling window that the 2023-01 design start does not need that much of.

This keeps the panel EXACTLY as built (no re-derivation, no re-stamping) -- it only drops rows
and leading columns. -> panel1h_ext_trim.npz
"""
from __future__ import annotations

import datetime as dt
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "research" / "data" / "perpmicro_cache" / "panel1h_ext.npz"
DST = ROOT / "research" / "data" / "perpmicro_cache" / "panel1h_ext_trim.npz"

KEEP_SYMS = 150
T_START = int(dt.datetime(2022, 10, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
FIELDS = ["o", "h", "l", "c", "qv", "ntr", "tbq", "fund", "fund_age_h", "fund_next_h"]


def main():
    z = np.load(SRC, allow_pickle=True)
    t = z["t"]
    j0 = int(np.searchsorted(t, T_START))
    qv = z["qv"][:, j0:]
    tot = np.nansum(np.where(np.isfinite(qv), qv, 0.0), axis=1)
    del qv
    order = np.argsort(-tot)
    keep = np.sort(order[:KEEP_SYMS])
    out = {f: z[f][keep][:, j0:].astype(np.float32) for f in FIELDS}
    out["t"] = t[j0:]
    out["symbols"] = z["symbols"][keep]
    np.savez_compressed(DST, **out)
    print(f"{len(keep)} symbols x {len(out['t'])} hours -> {DST}", flush=True)
    print("dropped", int(z['c'].shape[0] - len(keep)), "symbols,",
          j0, "leading hours")
    print("kept examples:", list(out["symbols"][:8]), "...", list(out["symbols"][-4:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
