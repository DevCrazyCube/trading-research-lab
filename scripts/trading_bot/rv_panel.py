#!/usr/bin/env python3
"""Assemble the per-symbol .npz bars from rv_fetch into one aligned 5-minute RTH panel.

Output: research/data/rv_cache/panel.npz
    ts     int64  [T]        bar start, unix seconds
    day    int32  [T]        day index 0..D-1
    slot   int16  [T]        bar-of-day index (0 = 09:30 bar)
    syms   <U8    [S]
    close  float32[T,S]
    open   float32[T,S]
    vwap   float32[T,S]      execution price used by the sweep
    dvol   float32[T,S]      dollar volume in the bar

Peak RSS is one symbol at a time plus the panel (~T*S*4*4 bytes).
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

ET = ZoneInfo("America/New_York")
CACHE = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "rv_cache"


def main() -> None:
    files = sorted(p for p in CACHE.glob("*.npz") if p.name != "panel.npz")
    syms = [p.stem.replace("_", ".") if p.stem == "BRK_B" else p.stem for p in files]
    # Union of timestamps, but only keep bars present in the reference (SPY) so the grid is
    # the trading grid rather than a union polluted by one symbol's odd prints.
    ref = CACHE / "SPY.npz"
    if not ref.exists():
        raise SystemExit("SPY.npz missing; the grid reference must be present")
    ts = np.load(ref)["t"]
    ts = np.unique(ts)
    T, S = ts.size, len(files)
    print(f"grid {T} bars x {S} symbols", flush=True)

    close = np.full((T, S), np.nan, dtype=np.float32)
    opn = np.full((T, S), np.nan, dtype=np.float32)
    vwap = np.full((T, S), np.nan, dtype=np.float32)
    dvol = np.zeros((T, S), dtype=np.float32)

    for j, path in enumerate(files):
        d = np.load(path)
        t = d["t"]
        idx = np.searchsorted(ts, t)
        ok = (idx < T) & (ts[np.clip(idx, 0, T - 1)] == t)
        idx = idx[ok]
        close[idx, j] = d["c"][ok]
        opn[idx, j] = d["o"][ok]
        vwap[idx, j] = d["vw"][ok]
        dvol[idx, j] = (d["vw"][ok].astype(np.float64) * d["v"][ok]).astype(np.float32)
        del d

    dts = [datetime.fromtimestamp(int(x), tz=timezone.utc).astimezone(ET) for x in ts]
    daykey = np.array([x.strftime("%Y-%m-%d") for x in dts])
    _, day = np.unique(daykey, return_inverse=True)
    slot = np.array([(x.hour * 60 + x.minute - 570) // 5 for x in dts], dtype=np.int16)

    np.savez_compressed(
        CACHE / "panel.npz", ts=ts, day=day.astype(np.int32), slot=slot,
        daykey=daykey, syms=np.array(syms), close=close, open=opn, vwap=vwap, dvol=dvol,
    )
    cov = np.isfinite(close).mean(axis=0)
    manifest = {s: round(float(c), 4) for s, c in zip(syms, cov)}
    (CACHE / "panel_coverage.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    print("wrote panel.npz", flush=True)
    print("worst coverage:", sorted(manifest.items(), key=lambda kv: kv[1])[:12], flush=True)


if __name__ == "__main__":
    main()
