#!/usr/bin/env python3
"""Build a 1h cross-sectional panel of Binance USD-M perp microstructure from the
orphanflush cache (5m klines + 5m metrics) plus the t23 funding cache.

Output: research/data/perpmicro_cache/panel_<sym>.npz per symbol, then a single
stacked panel.npz on a common 1h UTC grid.

Fields per (symbol, hour):
  o,h,l,c            price OHLC (from 5m)
  qv                 quote volume summed over the hour
  ntr                trade count summed
  tbq                taker BUY quote volume summed  (aggressor-buy notional)
  oi                 sum_open_interest        (last 5m obs in hour)
  oiv                sum_open_interest_value  (last)
  ttc                count_toptrader_long_short_ratio (last)
  tts                sum_toptrader_long_short_ratio   (last)
  glsr               count_long_short_ratio  (global accounts) (last)
  tlsr               sum_taker_long_short_vol_ratio (mean over hour)
  fund               funding rate in force / last settled (fwd-filled, from t23)

Everything is causal: a value stamped at hour t uses only data with timestamp <= end of hour t.
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
OUT.mkdir(parents=True, exist_ok=True)
PER = OUT / "sym"
PER.mkdir(exist_ok=True)

HOUR = 3_600_000
T0 = int(dt.datetime(2021, 12, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
T1 = int(dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
NH = (T1 - T0) // HOUR

KF = ["o", "h", "l", "c", "qv", "ntr", "tbq"]
MF = ["oi", "oiv", "ttc", "tts", "glsr", "tlsr"]


def _zrows(p: pathlib.Path):
    try:
        with zipfile.ZipFile(io.BytesIO(p.read_bytes())) as zf:
            txt = zf.read(zf.namelist()[0]).decode("utf-8", "replace")
    except Exception:
        return
    for row in csv.reader(io.StringIO(txt)):
        if row:
            yield row


def _months(t0: int, t1: int):
    d = dt.datetime.fromtimestamp(t0 / 1000, dt.timezone.utc).date().replace(day=1)
    end = dt.datetime.fromtimestamp(t1 / 1000, dt.timezone.utc).date()
    out = []
    while d <= end:
        out.append(f"{d.year:04d}-{d.month:02d}")
        d = (d.replace(day=28) + dt.timedelta(days=8)).replace(day=1)
    return out


def build_symbol(sym: str) -> str:
    kdir = CACHE / "klines5m" / sym
    mdir = CACHE / "metrics" / sym
    if not kdir.is_dir() or not mdir.is_dir():
        return f"{sym} SKIP nodir"

    # ---- klines: aggregate 5m -> 1h
    o = np.full(NH, np.nan); hi = np.full(NH, np.nan); lo = np.full(NH, np.nan)
    c = np.full(NH, np.nan)
    qv = np.zeros(NH); ntr = np.zeros(NH); tbq = np.zeros(NH)
    seen = np.zeros(NH, bool)
    first_ms = np.full(NH, 1 << 62, dtype=np.int64)
    last_ms = np.full(NH, -1, dtype=np.int64)

    for ym in _months(T0, T1):
        p = kdir / f"{sym}-5m-{ym}.zip"
        if not (p.exists() and p.stat().st_size > 0):
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

    if not seen.any():
        return f"{sym} SKIP noklines"
    qv[~seen] = np.nan; ntr[~seen] = np.nan; tbq[~seen] = np.nan

    # ---- metrics: last-in-hour for level fields, mean for tlsr
    m = {k: np.full(NH, np.nan) for k in MF}
    tl_sum = np.zeros(NH); tl_n = np.zeros(NH)
    mlast = np.full(NH, -1, dtype=np.int64)
    day = dt.datetime.fromtimestamp(T0 / 1000, dt.timezone.utc).date()
    endday = dt.datetime.fromtimestamp(T1 / 1000, dt.timezone.utc).date()
    epoch = dt.datetime(1970, 1, 1)
    while day < endday:
        p = mdir / f"{sym}-metrics-{day.isoformat()}.zip"
        day += dt.timedelta(days=1)
        if not (p.exists() and p.stat().st_size > 0):
            continue
        for row in _zrows(p):
            if len(row) < 8 or row[0] == "create_time" or row[0].startswith("create"):
                continue
            try:
                d0 = dt.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            t = int((d0 - epoch).total_seconds() * 1000)
            if t < T0 or t >= T1:
                continue
            i = (t - T0) // HOUR
            try:
                v = [float(x) for x in row[2:8]]
            except ValueError:
                continue
            if not np.isnan(v[5]):
                tl_sum[i] += v[5]; tl_n[i] += 1
            if t >= mlast[i]:
                mlast[i] = t
                m["oi"][i] = v[0]; m["oiv"][i] = v[1]
                m["ttc"][i] = v[2]; m["tts"][i] = v[3]; m["glsr"][i] = v[4]
    with np.errstate(invalid="ignore", divide="ignore"):
        m["tlsr"] = np.where(tl_n > 0, tl_sum / np.maximum(tl_n, 1), np.nan)

    d = {"o": o, "h": hi, "l": lo, "c": c, "qv": qv, "ntr": ntr, "tbq": tbq}
    d.update(m)
    np.savez_compressed(PER / f"{sym}.npz", **{k: v.astype(np.float32) for k, v in d.items()})
    return f"{sym} OK klines={int(seen.sum())} metrics={int((mlast>=0).sum())}"


def load_funding() -> dict:
    """symbol -> (times_ms sorted, rates). Rate stamped at settlement time."""
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
    grid_end = grid + HOUR  # information available at end of bar
    fields = KF + MF + ["fund", "fund_age_h", "fund_next_h"]
    keep = []
    arrs = {f: [] for f in fields}
    for s in syms:
        z = np.load(PER / f"{s}.npz")
        if np.isfinite(z["c"]).sum() < 24 * 90:
            continue
        keep.append(s)
        for f in KF + MF:
            arrs[f].append(z[f])
        # funding: last SETTLED rate strictly at or before end of bar
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
    np.savez_compressed(OUT / "panel1h.npz", **out)
    print("stacked", len(keep), "symbols x", NH, "hours ->", OUT / "panel1h.npz", flush=True)


def main():
    if "--stack" in sys.argv:
        stack(); return 0
    ks = set(os.listdir(CACHE / "klines5m"))
    ms = set(os.listdir(CACHE / "metrics"))
    syms = sorted(ks & ms)
    todo = [s for s in syms if not (PER / f"{s}.npz").exists()]
    print(f"{len(syms)} symbols, {len(todo)} to build", flush=True)
    with ProcessPoolExecutor(max_workers=7) as ex:
        for i, msg in enumerate(ex.map(build_symbol, todo, chunksize=1)):
            print(f"[{i+1}/{len(todo)}] {msg}", flush=True)
    stack()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
