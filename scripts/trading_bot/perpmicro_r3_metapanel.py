#!/usr/bin/env python3
"""Build an hourly OI / long-short-ratio metrics panel on the SAME grid as
panel1h_ext_trim.npz (150 symbols x 33984 hours, 2022-10-01 -> 2026-08-16).

Source: research/data/orphanflush_cache/raw/metrics/<SYM>/<SYM>-metrics-YYYY-MM-DD.zip
(Binance USD-M futures daily metrics dumps, 5-minute grid).

Columns: create_time, symbol, sum_open_interest, sum_open_interest_value,
         count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
         count_long_short_ratio, sum_taker_long_short_vol_ratio
      -> oi, oiv, ttc, tts, glsr, tlsr

Hourly aggregation: LAST 5-min observation inside the hour for the stock variables
(oi, oiv, ttc, tts, glsr) and the MEAN for the flow variable (tlsr, a per-interval ratio).
Everything is therefore known at the CLOSE of the hour, same convention as panel1h.npz.
"""
from __future__ import annotations

import io
import os
import pathlib
import zipfile
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
MET = ROOT / "research" / "data" / "orphanflush_cache" / "raw" / "metrics"
EXT = ROOT / "research" / "data" / "perpmicro_cache" / "panel1h_ext_trim.npz"
OUT = ROOT / "research" / "data" / "perpmicro_cache" / "panel1h_r3meta.npz"

HOUR = 3_600_000
COLS = ["oi", "oiv", "ttc", "tts", "glsr", "tlsr"]


def _one(args):
    sym, t0, nh = args
    d = MET / sym
    acc_last = {k: np.full(nh, np.nan, np.float64) for k in COLS[:5]}
    tl_sum = np.zeros(nh, np.float64)
    tl_cnt = np.zeros(nh, np.float64)
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".zip"):
            continue
        try:
            with zipfile.ZipFile(d / fn) as z:
                name = z.namelist()[0]
                raw = z.read(name).decode("utf-8", "replace")
        except Exception:
            continue
        lines = raw.splitlines()
        if len(lines) < 2:
            continue
        start = 1 if lines[0].startswith("create_time") else 0
        for ln in lines[start:]:
            f = ln.split(",")
            if len(f) < 8:
                continue
            ts = f[0]
            try:
                # "YYYY-MM-DD HH:MM:SS"
                y = int(ts[0:4]); mo = int(ts[5:7]); da = int(ts[8:10])
                hh = int(ts[11:13]); mi = int(ts[14:16])
            except Exception:
                continue
            # days since epoch (civil-from-days inverse)
            yy = y - (mo <= 2)
            era = (yy if yy >= 0 else yy - 399) // 400
            yoe = yy - era * 400
            doy = (153 * (mo + (-3 if mo > 2 else 9)) + 2) // 5 + da - 1
            doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
            days = era * 146097 + doe - 719468
            ms = (days * 86400 + hh * 3600) * 1000
            j = (ms - t0) // HOUR
            if j < 0 or j >= nh:
                continue
            j = int(j)
            try:
                oi = float(f[2]); oiv = float(f[3]); ttc = float(f[4])
                tts = float(f[5]); glsr = float(f[6]); tlsr = float(f[7])
            except Exception:
                continue
            # LAST observation wins (files are read in date order, rows in time order)
            acc_last["oi"][j] = oi
            acc_last["oiv"][j] = oiv
            acc_last["ttc"][j] = ttc
            acc_last["tts"][j] = tts
            acc_last["glsr"][j] = glsr
            if tlsr == tlsr:
                tl_sum[j] += tlsr
                tl_cnt[j] += 1.0
    with np.errstate(invalid="ignore", divide="ignore"):
        tl = np.where(tl_cnt > 0, tl_sum / np.maximum(tl_cnt, 1), np.nan)
    return sym, np.stack([acc_last["oi"], acc_last["oiv"], acc_last["ttc"],
                          acc_last["tts"], acc_last["glsr"], tl]).astype(np.float32)


def main():
    ext = np.load(EXT, allow_pickle=True)
    syms = [str(s) for s in ext["symbols"]]
    t = ext["t"].astype(np.int64)
    nh = len(t)
    t0 = int(t[0])
    have = set(os.listdir(MET))
    todo = [(s, t0, nh) for s in syms if s in have]
    print(f"symbols on grid {len(syms)}, with metrics {len(todo)}, hours {nh}", flush=True)

    out = {k: np.full((len(syms), nh), np.nan, np.float32) for k in COLS}
    idx = {s: i for i, s in enumerate(syms)}
    done = 0
    with ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as ex:
        for sym, arr in ex.map(_one, todo, chunksize=1):
            i = idx[sym]
            for k, row in zip(COLS, arr):
                out[k][i] = row
            done += 1
            if done % 10 == 0:
                print(f"  {done}/{len(todo)}", flush=True)

    for k in COLS:
        print(k, "finite frac", float(np.isfinite(out[k]).mean()))
    np.savez_compressed(OUT, t=t, symbols=np.array(syms), **out)
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
