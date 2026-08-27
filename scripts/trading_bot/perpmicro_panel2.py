#!/usr/bin/env python3
"""EXTENDED 1h panel: klines-only fields + funding, 2022-01 -> 2026-08-17.

The Binance futures-METRICS feed in the orphanflush cache dies at 2024-12 (only ~30 symbols
after that), which is what forced round 1 of this sweep to end its held-out window at
2025-01-01. The 5m KLINES, however, run monthly through 2026-07 plus daily files for
2026-08, for 130-150 symbols, and the t23 funding cache runs through 2026-07.

So every formula built from price / volume / trade count / taker-buy volume / funding can be
tested on 2025-01-01 -> 2026-08-01, a window NOTHING in this theme has ever touched.
That is what this panel exists for.

Output: research/data/perpmicro_cache/panel1h_ext.npz
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import os
import pathlib
import sys
import zipfile
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / "research" / "data" / "orphanflush_cache" / "raw"
FUND_CSV = ROOT / "research" / "data" / "t23_cache" / "panel" / "funding.csv"
OUT = ROOT / "research" / "data" / "perpmicro_cache"
PER = OUT / "sym_ext"
PER.mkdir(parents=True, exist_ok=True)

HOUR = 3_600_000
T0 = int(dt.datetime(2022, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
T1 = int(dt.datetime(2026, 8, 17, tzinfo=dt.timezone.utc).timestamp() * 1000)
NH = (T1 - T0) // HOUR

KF = ["o", "h", "l", "c", "qv", "ntr", "tbq"]


def _zrows(p: pathlib.Path):
    try:
        with zipfile.ZipFile(io.BytesIO(p.read_bytes())) as zf:
            txt = zf.read(zf.namelist()[0]).decode("utf-8", "replace")
    except Exception:
        return
    for row in csv.reader(io.StringIO(txt)):
        if row:
            yield row


def build_symbol(sym: str) -> str:
    kdir = CACHE / "klines5m" / sym
    if not kdir.is_dir():
        return f"{sym} SKIP nodir"

    o = np.full(NH, np.nan); hi = np.full(NH, np.nan); lo = np.full(NH, np.nan)
    c = np.full(NH, np.nan)
    qv = np.zeros(NH); ntr = np.zeros(NH); tbq = np.zeros(NH)
    seen = np.zeros(NH, bool)
    first_ms = np.full(NH, 1 << 62, dtype=np.int64)
    last_ms = np.full(NH, -1, dtype=np.int64)

    # every kline zip in the dir, monthly (SYM-5m-YYYY-MM.zip) or daily (SYM-5m-YYYY-MM-DD.zip)
    for p in sorted(kdir.iterdir()):
        if not (p.suffix == ".zip" and p.stat().st_size > 0):
            continue
        for row in _zrows(p):
            try:
                t = int(float(row[0]))
            except (ValueError, IndexError):
                continue
            if t > 10 ** 14:
                t //= 1000
            if t < T0 or t >= T1:
                continue
            i = (t - T0) // HOUR
            try:
                ro, rh, rl, rc = float(row[1]), float(row[2]), float(row[3]), float(row[4])
                rqv = float(row[7]); rn = float(row[8]); rtbq = float(row[10])
            except (ValueError, IndexError):
                continue
            seen[i] = True
            if t < first_ms[i]:
                first_ms[i] = t; o[i] = ro
            if t > last_ms[i]:
                last_ms[i] = t; c[i] = rc
            hi[i] = rh if np.isnan(hi[i]) else max(hi[i], rh)
            lo[i] = rl if np.isnan(lo[i]) else min(lo[i], rl)
            qv[i] += rqv; ntr[i] += rn; tbq[i] += rtbq

    if seen.sum() < 24 * 120:
        return f"{sym} SKIP short={int(seen.sum())}"
    qv[~seen] = np.nan; ntr[~seen] = np.nan; tbq[~seen] = np.nan
    d = {"o": o, "h": hi, "l": lo, "c": c, "qv": qv, "ntr": ntr, "tbq": tbq}
    np.savez_compressed(PER / f"{sym}.npz", **{k: v.astype(np.float32) for k, v in d.items()})
    return f"{sym} OK bars={int(seen.sum())}"


def load_funding() -> dict:
    out = {}
    with open(FUND_CSV) as f:
        r = csv.reader(f); next(r)
        for row in r:
            try:
                t = int(row[1]); v = float(row[3])
            except (ValueError, IndexError):
                continue
            out.setdefault(row[0], []).append((t, v))
    fin = {}
    for k, v in out.items():
        v.sort()
        fin[k] = (np.array([x[0] for x in v], np.int64), np.array([x[1] for x in v], np.float64))
    return fin


def stack():
    syms = sorted(p.stem for p in PER.glob("*.npz"))
    fund = load_funding()
    grid = T0 + np.arange(NH, dtype=np.int64) * HOUR
    grid_end = grid + HOUR
    fields = KF + ["fund", "fund_age_h", "fund_next_h"]
    keep = []
    arrs = {f: [] for f in fields}
    for s in syms:
        z = np.load(PER / f"{s}.npz")
        if np.isfinite(z["c"]).sum() < 24 * 120:
            continue
        keep.append(s)
        for f in KF:
            arrs[f].append(z[f])
        fu = np.full(NH, np.nan, np.float32)
        age = np.full(NH, np.nan, np.float32)
        nxt = np.full(NH, np.nan, np.float32)
        if s in fund:
            ft, fv = fund[s]
            idx = np.searchsorted(ft, grid_end, side="right") - 1
            ok = idx >= 0
            fu[ok] = fv[idx[ok]].astype(np.float32)
            age[ok] = ((grid_end[ok] - ft[idx[ok]]) / HOUR).astype(np.float32)
            nidx = np.searchsorted(ft, grid_end, side="right")
            ok2 = nidx < len(ft)
            nxt[ok2] = ((ft[nidx[ok2]] - grid_end[ok2]) / HOUR).astype(np.float32)
        arrs["fund"].append(fu); arrs["fund_age_h"].append(age); arrs["fund_next_h"].append(nxt)
    out = {f: np.vstack(arrs[f]).astype(np.float32) for f in fields}
    out["t"] = grid
    out["symbols"] = np.array(keep)
    np.savez_compressed(OUT / "panel1h_ext.npz", **out)
    print("stacked", len(keep), "symbols x", NH, "hours ->", OUT / "panel1h_ext.npz", flush=True)


def main():
    if "--stack" in sys.argv:
        stack(); return 0
    syms = sorted(os.listdir(CACHE / "klines5m"))
    todo = [s for s in syms if not (PER / f"{s}.npz").exists()]
    print(f"{len(syms)} symbols, {len(todo)} to build, NH={NH}", flush=True)
    with ProcessPoolExecutor(max_workers=6) as ex:
        for i, msg in enumerate(ex.map(build_symbol, todo, chunksize=1)):
            print(f"[{i+1}/{len(todo)}] {msg}", flush=True)
    stack()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
