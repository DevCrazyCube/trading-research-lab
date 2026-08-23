#!/usr/bin/env python3
"""Build the (D, 78, S) intraday cube for INVENT_0823 intraday-microstructure.

Reads the per-symbol 5-minute .npz already cached by rv_fetch (Alpaca SIP, RTH,
adjustment=all) and lays them out day-major so a formula can address bar-of-day
directly.  Carries high/low/trade-count, which the earlier RV sweep's panel did not.

Output: research/data/im0823_cache/cube.npz
    daykey  <U10 [D]
    syms    <U6  [S]
    o,h,l,c,vw  float32 [D,78,S]
    dv          float32 [D,78,S]   dollar volume (v * vw)
    nt          float32 [D,78,S]   trade count
"""
from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
CACHE = ROOT / "research" / "data" / "rv_cache"
OUT = ROOT / "research" / "data" / "im0823_cache"
ET = ZoneInfo("America/New_York")
NSLOT = 78


def main() -> None:
    from trading_bot.rv_fetch import UNIVERSE

    files = [(s, CACHE / f"{s.replace('.', '_')}.npz") for s in UNIVERSE]
    files = [(s, p) for s, p in files if p.exists()]
    syms = [s for s, _ in files]

    ref = np.load(CACHE / "SPY.npz")["t"]
    ts = np.unique(ref)
    # day key + slot for every reference bar
    dts = [datetime.fromtimestamp(int(x), tz=timezone.utc).astimezone(ET) for x in ts]
    daykeys = np.array([d.strftime("%Y-%m-%d") for d in dts])
    mins = np.array([d.hour * 60 + d.minute for d in dts])
    slot = (mins - 570) // 5  # 09:30 -> 0
    keep = (slot >= 0) & (slot < NSLOT)
    ts, daykeys, slot = ts[keep], daykeys[keep], slot[keep].astype(np.int16)

    udays, dayidx = np.unique(daykeys, return_inverse=True)
    D, S = udays.size, len(syms)
    print(f"cube {D} days x {NSLOT} slots x {S} syms", flush=True)

    flat_pos = dayidx.astype(np.int64) * NSLOT + slot  # position in flattened D*78 grid
    G = D * NSLOT

    fields = {k: np.full((G, S), np.nan, dtype=np.float32) for k in ("o", "h", "l", "c", "vw", "dv", "nt")}

    for j, (sym, path) in enumerate(files):
        d = np.load(path)
        t = d["t"]
        pos = np.searchsorted(ts, t)
        ok = (pos < ts.size) & (ts[np.clip(pos, 0, ts.size - 1)] == t)
        pos = flat_pos[pos[ok]]
        fields["o"][pos, j] = d["o"][ok]
        fields["h"][pos, j] = d["h"][ok]
        fields["l"][pos, j] = d["l"][ok]
        fields["c"][pos, j] = d["c"][ok]
        fields["vw"][pos, j] = d["vw"][ok]
        fields["dv"][pos, j] = (d["v"][ok] * d["vw"][ok].astype(np.float64)).astype(np.float32)
        fields["nt"][pos, j] = d["n"][ok].astype(np.float32)
        del d
        if (j + 1) % 25 == 0:
            print(f"  {j+1}/{S}", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUT / "cube.npz",
        daykey=udays,
        syms=np.array(syms),
        **{k: v.reshape(D, NSLOT, S) for k, v in fields.items()},
    )
    print("wrote", OUT / "cube.npz", flush=True)


if __name__ == "__main__":
    main()
