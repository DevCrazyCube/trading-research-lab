#!/usr/bin/env python3
"""
NEWTERR xs_equity: build a split/dividend-adjusted daily OHLCV panel from the
t17 Alpaca cache (survivorship-mitigated: delisted symbols retained), plus a
RegSHO daily short-volume panel aligned to the same (date, symbol) grid.

Writes research/data/newterr_xseq_cache/panel.npz

Raw t17 bars are UNADJUSTED (verified: AAPL 2020-08-31 drops 504 -> 127).
We adjust with the t7 corporate-actions cache (980 forward + 5637 reverse
splits, 386k cash dividends, 2016-2026).
"""
import gzip, json, os, glob, sys
import numpy as np

DATA = "/home/anont/meme/research/data"
OUT = os.path.join(DATA, "newterr_xseq_cache")
os.makedirs(OUT, exist_ok=True)

MIN_PRICE_EVER = 3.0
MIN_MAXDV = 3e6  # symbol must reach $3M dollar-volume on some day, else drop early


def build():
    # ---------- 1. date axis ----------
    chunks = sorted(glob.glob(os.path.join(DATA, "t17_cache/daily/chunk_*.json")))
    print(f"{len(chunks)} chunks", flush=True)

    dates = set()
    for f in chunks:
        d = json.load(open(f))
        for sym, rows in d.items():
            for r in rows:
                dates.add(r[0])
    dates = sorted(dates)
    didx = {d: i for i, d in enumerate(dates)}
    T = len(dates)
    print(f"T={T} dates {dates[0]}..{dates[-1]}", flush=True)

    # ---------- 2. corporate actions -> per-symbol adjustment factors ----------
    ca = json.load(gzip.open(os.path.join(DATA, "t7_cache/corporate_actions_all.json.gz")))
    # split events: on ex_date, price divides by (new/old)
    split_ev = {}  # sym -> list[(date, ratio)]  ratio = new_rate/old_rate
    for k in ("forward_splits", "reverse_splits"):
        for e in ca.get(k, []):
            s, dt = e.get("symbol"), e.get("ex_date")
            if not s or dt not in didx:
                continue
            try:
                ratio = float(e["new_rate"]) / float(e["old_rate"])
            except Exception:
                continue
            if ratio <= 0 or not np.isfinite(ratio):
                continue
            split_ev.setdefault(s, []).append((dt, ratio))
    div_ev = {}
    for e in ca.get("cash_dividends", []):
        s, dt = e.get("symbol"), e.get("ex_date")
        if not s or dt not in didx:
            continue
        try:
            r = float(e["rate"])
        except Exception:
            continue
        if r > 0:
            div_ev.setdefault(s, []).append((dt, r))
    print(f"split symbols={len(split_ev)} div symbols={len(div_ev)}", flush=True)

    # ---------- 3. first pass: keep only symbols that ever get liquid ----------
    keep = {}
    for ci, f in enumerate(chunks):
        d = json.load(open(f))
        for sym, rows in d.items():
            if not rows:
                continue
            mx = 0.0
            px = 0.0
            for r in rows:
                c = r[4]
                v = r[5]
                if c and v:
                    dv = c * v
                    if dv > mx:
                        mx = dv
                    if c > px:
                        px = c
            if mx >= MIN_MAXDV and px >= MIN_PRICE_EVER:
                keep[sym] = f
        if ci % 40 == 0:
            print(f"  scan {ci}/{len(chunks)} keep={len(keep)}", flush=True)
    syms = sorted(keep)
    N = len(syms)
    sidx = {s: i for i, s in enumerate(syms)}
    print(f"N={N} liquid-ever symbols", flush=True)

    O = np.full((T, N), np.nan, np.float32)
    H = np.full((T, N), np.nan, np.float32)
    L = np.full((T, N), np.nan, np.float32)
    C = np.full((T, N), np.nan, np.float32)
    V = np.full((T, N), np.nan, np.float32)

    for ci, f in enumerate(chunks):
        d = json.load(open(f))
        for sym, rows in d.items():
            j = sidx.get(sym)
            if j is None:
                continue
            for r in rows:
                i = didx.get(r[0])
                if i is None:
                    continue
                O[i, j] = r[1]; H[i, j] = r[2]; L[i, j] = r[3]; C[i, j] = r[4]; V[i, j] = r[5]
        if ci % 40 == 0:
            print(f"  fill {ci}/{len(chunks)}", flush=True)
        del d

    # ---------- 4. apply split adjustment (back-adjust prices before ex-date) ----------
    # cumulative factor f[i] such that adjusted price = raw * f ; f=1 from last split on.
    nsplit_applied = 0
    for sym, evs in split_ev.items():
        j = sidx.get(sym)
        if j is None:
            continue
        fac = np.ones(T, np.float64)
        for dt, ratio in evs:
            i = didx[dt]
            fac[:i] /= ratio           # pre-ex prices scaled down by ratio
            nsplit_applied += 1
        f32 = fac.astype(np.float32)
        O[:, j] *= f32; H[:, j] *= f32; L[:, j] *= f32; C[:, j] *= f32
        V[:, j] /= f32                 # share count scales inversely
    print(f"applied {nsplit_applied} split events", flush=True)

    # ---------- 5. dividend adjustment factor series (applied to returns) ----------
    # divadj[i,j] = dividend paid ex on date i, in SPLIT-ADJUSTED dollars
    DIV = np.zeros((T, N), np.float32)
    for sym, evs in div_ev.items():
        j = sidx.get(sym)
        if j is None:
            continue
        for dt, r in evs:
            DIV[didx[dt], j] += r
    # scale dividends by the same split factor
    for sym, evs in split_ev.items():
        j = sidx.get(sym)
        if j is None:
            continue
        fac = np.ones(T, np.float64)
        for dt, ratio in evs:
            fac[: didx[dt]] /= ratio
        DIV[:, j] *= fac.astype(np.float32)

    np.savez_compressed(
        os.path.join(OUT, "panel.npz"),
        dates=np.array(dates), syms=np.array(syms),
        O=O, H=H, L=L, C=C, V=V, DIV=DIV,
    )
    print("wrote panel.npz", flush=True)

    # ---------- 6. RegSHO aligned ----------
    SV = np.full((T, N), np.nan, np.float32)
    TV = np.full((T, N), np.nan, np.float32)
    sess = sorted(glob.glob(os.path.join(DATA, "t16_panels/finra_regsho_daily/raw/session=*")))
    print(f"regsho sessions {len(sess)}", flush=True)
    for k, sd in enumerate(sess):
        dt = sd.split("session=")[1]
        i = didx.get(dt)
        if i is None:
            continue
        g = glob.glob(os.path.join(sd, "*.csv.gz"))
        if not g:
            continue
        with gzip.open(g[0], "rt") as fh:
            fh.readline()
            for line in fh:
                p = line.split(",")
                if len(p) < 5:
                    continue
                j = sidx.get(p[1])
                if j is None:
                    continue
                try:
                    SV[i, j] = float(p[2]); TV[i, j] = float(p[4])
                except Exception:
                    pass
        if k % 300 == 0:
            print(f"  regsho {k}/{len(sess)}", flush=True)
    np.savez_compressed(os.path.join(OUT, "regsho.npz"), SV=SV, TV=TV)
    print("wrote regsho.npz", flush=True)


if __name__ == "__main__":
    build()
