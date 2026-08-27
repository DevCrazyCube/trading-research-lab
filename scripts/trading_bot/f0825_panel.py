#!/usr/bin/env python3
"""Build a 5m perp panel (price/flow/OI) + exact funding stamps for the
funding-settlement-window micro-dynamics study (INVENT_0825).

Universe is chosen from PRE-DESIGN (2022) hourly volume only -> no lookahead.
Panel window 2023-01-01 .. 2026-08-16 UTC at 5m.
"""
import os, sys, io, zipfile, datetime as dt
import numpy as np

ROOT = "/home/anont/meme"
K5 = f"{ROOT}/research/data/orphanflush_cache/raw/klines5m"
MET = f"{ROOT}/research/data/orphanflush_cache/raw/metrics"
OUT = f"{ROOT}/research/data/fund0825_cache"
os.makedirs(OUT, exist_ok=True)

T0 = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
T1 = int(dt.datetime(2026, 8, 16, tzinfo=dt.timezone.utc).timestamp() * 1000)
STEP = 300_000
NT = (T1 - T0) // STEP
GRID = T0 + STEP * np.arange(NT, dtype=np.int64)


def pick_universe(n=50):
    d = np.load(f"{ROOT}/research/data/perpmicro_cache/panel1h_ext.npz", allow_pickle=True)
    syms, t, qv = d["symbols"], d["t"], d["qv"]
    yr = np.array([dt.datetime.fromtimestamp(x / 1000, dt.timezone.utc).year for x in t])
    med = np.nanmedian(qv[:, yr == 2022], axis=1)
    have = set(os.listdir(K5))
    ok = [(s, v) for s, v in zip(syms, med) if s in have and np.isfinite(v)]
    ok.sort(key=lambda x: -x[1])
    return [s for s, _ in ok[:n]]


def load_klines(sym):
    """-> (open, close, qv, tbq, ntr) float32 on GRID, NaN where missing."""
    o = np.full(NT, np.nan, np.float32); c = np.full(NT, np.nan, np.float32)
    q = np.full(NT, np.nan, np.float32); b = np.full(NT, np.nan, np.float32)
    n = np.full(NT, np.nan, np.float32)
    dpath = f"{K5}/{sym}"
    if not os.path.isdir(dpath):
        return o, c, q, b, n
    for fn in sorted(os.listdir(dpath)):
        if not fn.endswith(".zip"):
            continue
        ym = fn.split("-5m-")[-1][:7]
        y, m = int(ym[:4]), int(ym[5:7])
        if y < 2023 or (y, m) > (2026, 8):
            continue
        try:
            z = zipfile.ZipFile(f"{dpath}/{fn}")
            raw = z.read(z.namelist()[0]).decode()
        except Exception:
            continue
        lines = raw.splitlines()
        if lines and not lines[0][0].isdigit():
            lines = lines[1:]
        if not lines:
            continue
        arr = np.array([ln.split(",") for ln in lines], dtype=object)
        try:
            ot = arr[:, 0].astype(np.int64)
        except Exception:
            continue
        idx = (ot - T0) // STEP
        good = (idx >= 0) & (idx < NT) & (ot == T0 + idx * STEP)
        idx = idx[good]
        o[idx] = arr[good, 1].astype(np.float64)
        c[idx] = arr[good, 4].astype(np.float64)
        q[idx] = arr[good, 7].astype(np.float64)
        n[idx] = arr[good, 8].astype(np.float64)
        b[idx] = arr[good, 10].astype(np.float64)
    return o, c, q, b, n


def load_oi(sym):
    oi = np.full(NT, np.nan, np.float32)
    dpath = f"{MET}/{sym}"
    if not os.path.isdir(dpath):
        return oi
    for fn in sorted(os.listdir(dpath)):
        if not fn.endswith(".zip"):
            continue
        ds = fn.split("-metrics-")[-1][:10]
        if ds < "2023-01-01" or ds > "2026-08-16":
            continue
        try:
            z = zipfile.ZipFile(f"{dpath}/{fn}")
            raw = z.read(z.namelist()[0]).decode()
        except Exception:
            continue
        lines = raw.splitlines()
        if lines and lines[0].startswith("create_time"):
            lines = lines[1:]
        for ln in lines:
            p = ln.split(",")
            if len(p) < 4:
                continue
            try:
                ts = int(dt.datetime.strptime(p[0], "%Y-%m-%d %H:%M:%S")
                         .replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
                v = float(p[3])  # sum_open_interest_value (USD notional)
            except Exception:
                continue
            i = (ts - T0) // STEP
            if 0 <= i < NT and ts == T0 + i * STEP:
                oi[i] = v
    return oi


def main():
    syms = pick_universe(50)
    print(len(syms), "symbols", flush=True)
    S = len(syms)
    O = np.full((S, NT), np.nan, np.float32); C = np.full((S, NT), np.nan, np.float32)
    Q = np.full((S, NT), np.nan, np.float32); B = np.full((S, NT), np.nan, np.float32)
    N = np.full((S, NT), np.nan, np.float32); OI = np.full((S, NT), np.nan, np.float32)
    for i, s in enumerate(syms):
        O[i], C[i], Q[i], B[i], N[i] = load_klines(s)
        OI[i] = load_oi(s)
        print(i, s, "cov", round(float(np.isfinite(C[i]).mean()), 3),
              "oi", round(float(np.isfinite(OI[i]).mean()), 3), flush=True)
    np.savez_compressed(f"{OUT}/panel5m.npz", o=O, c=C, qv=Q, tbq=B, ntr=N, oi=OI,
                        t=GRID, symbols=np.array(syms))
    print("saved", flush=True)


if __name__ == "__main__":
    main()
