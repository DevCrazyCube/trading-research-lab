#!/usr/bin/env python3
"""INVENT_0822B / AUCTION IMBALANCE AS A SIGNAL SOURCE -- formula engine.

Pre-registration: research/trading_bot/INVENT_0822B_auction_PREREGISTRATION.md
  sha256 1377e0f207ca1c5fd0c4bb33feae10b498e0ac15075e35bee082181c8e36d4e3

N = 54 formulas (block S: 18 predictors x 2 MOO-entry outcomes; block M: 9 predictors x 2
MOC-entry outcomes). Design 2016-2021, held-out 2022-01-01+. Size-matched placebo null by
circular time shift of the signal matrix.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "research" / "data" / "auc0822_cache"
OUTDIR = ROOT / "research" / "trading_bot"

DESIGN_END = "2021-12-31"
HELD_START = "2022-01-01"
MIN_PRICE = 3.0
MAX_GAP = 0.20          # raw-price split guard on the overnight leg
MAX_DAY = 0.25          # raw-price split guard on the print-to-print day leg
MIN_NAMES = 50
WINSOR_Z = 3.0
N_PLACEBO = 300
SEED = 20260822

ANN = 252.0


# ---------------------------------------------------------------------------- helpers
def zscore_rows(sig, mask):
    """Cross-sectional winsorised z, demeaned, scaled to sum|w| = 2. NaN outside mask."""
    x = np.where(mask, sig, np.nan)
    mu = np.nanmean(x, axis=1, keepdims=True)
    sd = np.nanstd(x, axis=1, keepdims=True)
    sd = np.where(sd > 0, sd, np.nan)
    z = (x - mu) / sd
    z = np.clip(z, -WINSOR_Z, WINSOR_Z)
    z = z - np.nanmean(z, axis=1, keepdims=True)
    z = np.nan_to_num(z, nan=0.0)
    g = np.abs(z).sum(axis=1, keepdims=True)
    g = np.where(g > 0, g, np.nan)
    w = 2.0 * z / g
    return np.nan_to_num(w, nan=0.0)


def roll_mean(a, k):
    """Trailing mean over k rows INCLUDING the current row, NaN-aware."""
    out = np.full_like(a, np.nan)
    fin = np.isfinite(a)
    v = np.where(fin, a, 0.0)
    cs = np.cumsum(v, axis=0)
    cn = np.cumsum(fin.astype(np.float64), axis=0)
    out[k - 1:] = (cs[k - 1:] - np.vstack([np.zeros((1, a.shape[1])), cs[:-k]])) / \
                  np.maximum(cn[k - 1:] - np.vstack([np.zeros((1, a.shape[1])), cn[:-k]]), 1e-9)
    n = (cn[k - 1:] - np.vstack([np.zeros((1, a.shape[1])), cn[:-k]]))
    out[k - 1:][n < k * 0.6] = np.nan
    return out


def roll_std(a, k):
    m1 = roll_mean(a, k)
    m2 = roll_mean(a * a, k)
    v = m2 - m1 * m1
    return np.sqrt(np.maximum(v, 0.0))


def lag(a, k=1):
    out = np.full_like(a, np.nan)
    if k > 0:
        out[k:] = a[:-k]
    elif k < 0:
        out[:k] = a[-k:]
    else:
        out[:] = a
    return out


def stats(r):
    r = r[np.isfinite(r)]
    n = r.size
    if n < 100:
        return dict(n=n, mean_bp=float("nan"), sharpe=float("nan"), t=float("nan"))
    m = float(r.mean())
    s = float(r.std(ddof=1))
    t = m / s * np.sqrt(n) if s > 0 else float("nan")
    return dict(n=int(n), mean_bp=m * 1e4, sharpe=m / s * np.sqrt(ANN) if s > 0 else float("nan"),
                t=float(t))


def rho1_pooled(a, mask):
    """rho1 of the first difference of a per-symbol series, pooled across symbols."""
    x = np.where(mask, a, np.nan)
    dx = x[1:] - x[:-1]
    p = dx[1:]
    q = dx[:-1]
    ok = np.isfinite(p) & np.isfinite(q)
    if ok.sum() < 1000:
        return float("nan")
    pp = p[ok] - p[ok].mean()
    qq = q[ok] - q[ok].mean()
    den = np.sqrt((pp * pp).sum() * (qq * qq).sum())
    return float((pp * qq).sum() / den) if den > 0 else float("nan")


# ---------------------------------------------------------------------------- main
def main():
    z = np.load(CACHE / "panel.npz", allow_pickle=False)
    dates = [str(d) for d in z["dates"]]
    p29, p49, p59 = z["p29"], z["p49"], z["p59"]
    po, pc = z["po"], z["pc"]
    ca, in_uni = z["ca"], z["in_uni"]
    D, S = p59.shape
    print(f"[eng] panel {D}x{S}", file=sys.stderr)

    with np.errstate(divide="ignore", invalid="ignore"):
        l29, l49, l59 = np.log(p29), np.log(p49), np.log(p59)
        lo, lcl = np.log(po), np.log(pc)
    for a in (l29, l49, l59, lo, lcl):
        a[~np.isfinite(a)] = np.nan

    px_ok = (p59 >= MIN_PRICE)
    base = in_uni & px_ok & (~ca) & np.isfinite(l59) & np.isfinite(lcl) & np.isfinite(lo)

    # ---- primitives -------------------------------------------------------------------
    d = lcl - l59                       # close-auction dislocation
    d49 = lcl - l49
    e = l59 - l49                       # imbalance-publication window drift
    f = l49 - l29                       # pre-publication drift
    x = lcl - lo                        # print-to-print day
    q = lo - lag(lcl, 1)                # open-auction gap
    u = lo - lag(l59, 1)                # total off-hours
    ptc = (lcl - lag(lcl, 1)) - (l59 - lag(l59, 1))   # print vs continuous daily divergence
    p49c = l49 - lag(lcl, 1)            # 15:49 vs prior close print

    # split guard on the raw-price cross-day legs
    guard = (np.abs(np.nan_to_num(q, nan=0.0)) <= MAX_GAP) & \
            (np.abs(np.nan_to_num(x, nan=0.0)) <= MAX_DAY)
    base = base & guard

    d5 = roll_mean(np.where(base, d, np.nan), 5)
    d20 = roll_mean(np.where(base, d, np.nan), 20)
    dsd = roll_std(np.where(base, d, np.nan), 60)

    # ---- outcomes ---------------------------------------------------------------------
    # block S: signal dated t, entry at O_{t+1}
    DAYN = lag(lcl - lo, -1)                       # ln(C_{t+1}/O_{t+1})
    OON = lag(lo, -2) - lag(lo, -1)                # ln(O_{t+2}/O_{t+1})
    # block M: signal legal at 15:50 on t, entry at C_t
    ON = lag(lo, -1) - lcl                         # ln(O_{t+1}/C_t)
    CC = lag(lcl, -1) - lcl                        # ln(C_{t+1}/C_t)

    # a symbol must be tradeable on every day the leg touches
    b1 = base & lag(base, -1)
    b2 = base & lag(base, -1) & lag(base, -2)
    OUTCOMES = {
        "DAY_t1": (DAYN, b1, "flat"),      # MOO t+1 -> MOC t+1
        "OO_t1":  (OON, b2, "hold"),       # MOO t+1 -> MOO t+2
        "ON_t":   (ON, b1, "flat"),        # MOC t   -> MOO t+1
        "CC_t":   (CC, b1, "hold"),        # MOC t   -> MOC t+1
    }

    S_PRED = {
        "S01_d":            d,
        "S02_e":            e,
        "S03_f":            f,
        "S04_e_minus_f":    e - f,
        "S05_d_dev5":       d - d5,
        "S06_d_dev20":      d - d20,
        "S07_d_volnorm":    d / np.where(dsd > 0, dsd, np.nan),
        "S08_d49":          d49,
        "S09_q":            q,
        "S10_u":            u,
        "S11_q_minus_dlag": q - lag(d, 1),
        "S12_x":            x,
        "S13_d_plus_dlag":  d + lag(d, 1),
        "S14_d_shrunk":     np.sign(d) * np.sqrt(np.abs(d)),
        "S15_d_change":     d - lag(d, 1),
        "S16_e_plus_d":     e + d,
        "S17_d_mean5":      d5,
        "S18_print_vs_cont": ptc,
    }
    M_PRED = {
        "M01_f":            f,
        "M02_dlag":         lag(d, 1),
        "M03_q":            q,
        "M04_q_minus_dlag": q - lag(d, 1),
        "M05_u":            u,
        "M06_d_mean5_lag":  lag(d5, 1),
        "M07_x_lag":        lag(x, 1),
        "M08_p49_vs_close": p49c,
        "M09_dlag_plus_q":  lag(d, 1) + q,
    }
    GRID = [(f"{k}|{o}", v, o) for k, v in S_PRED.items() for o in ("DAY_t1", "OO_t1")] + \
           [(f"{k}|{o}", v, o) for k, v in M_PRED.items() for o in ("ON_t", "CC_t")]
    N = len(GRID)
    print(f"[eng] N formulas = {N}", file=sys.stderr)

    dates_arr = np.array(dates)
    des = dates_arr <= DESIGN_END
    hel = dates_arr >= HELD_START

    # ---- precompute weights + outcome matrices ---------------------------------------
    ret_of = {}
    for name, (R, msk, _) in OUTCOMES.items():
        RR = np.where(msk & np.isfinite(R), R, np.nan)
        # cross-sectional winsorisation of the outcome at +/- 0.1%/99.9% per day
        lo_q = np.nanpercentile(np.where(np.isfinite(RR), RR, np.nan), 0.1, axis=1, keepdims=True)
        hi_q = np.nanpercentile(np.where(np.isfinite(RR), RR, np.nan), 99.9, axis=1, keepdims=True)
        RR = np.clip(RR, lo_q, hi_q)
        ret_of[name] = np.nan_to_num(RR, nan=0.0), msk & np.isfinite(R)

    rng = np.random.default_rng(SEED)
    shifts = rng.integers(30, D - 30, size=N_PLACEBO)

    results = {}
    placebo_t = np.full((N_PLACEBO, N), np.nan)

    for gi, (fname, sig, oname) in enumerate(GRID):
        R, rmask = ret_of[oname]
        m = rmask & np.isfinite(sig)
        nday = m.sum(axis=1)
        ok_day = nday >= MIN_NAMES
        mm = m & ok_day[:, None]
        W = zscore_rows(sig, mm)
        r = (W * R).sum(axis=1)
        r = np.where(ok_day, r, np.nan)

        # turnover
        hold = OUTCOMES[oname][2] == "hold"
        if hold:
            turn = np.abs(W - lag(W, 1)).sum(axis=1)
        else:
            turn = 2.0 * np.abs(W).sum(axis=1)

        row = {"formula": fname, "outcome": oname, "hold": hold}
        for tag, sel in (("design", des), ("held", hel)):
            rr = np.where(sel, r, np.nan)
            st = stats(rr)
            tt = np.where(sel & ok_day, turn, np.nan)
            st["turnover"] = float(np.nanmean(tt)) if np.isfinite(tt).any() else float("nan")
            for c in (0.0, 0.5, 1.0):
                netr = rr - np.where(sel, turn, 0.0) * c * 1e-4
                s2 = stats(netr)
                st[f"net{c}_sharpe"] = s2["sharpe"]
                st[f"net{c}_t"] = s2["t"]
                st[f"net{c}_bp"] = s2["mean_bp"]
            row[tag] = st
        results[fname] = row

        rdes_full = np.where(des, 1.0, 0.0)
        # placebo: circular time shift of the WEIGHTS only
        for pi, k in enumerate(shifts):
            Wp = np.roll(W, int(k), axis=0)
            rp = (Wp * R).sum(axis=1)
            rp = np.where(ok_day & (rdes_full > 0), rp, np.nan)
            st = stats(rp)
            placebo_t[pi, gi] = st["t"]
        if (gi + 1) % 6 == 0:
            print(f"[eng] {gi+1}/{N} done", file=sys.stderr)

    maxabs = np.nanmax(np.abs(placebo_t), axis=1)
    null = {
        "n_draws": int(N_PLACEBO),
        "median_max_abs_t": float(np.nanmedian(maxabs)),
        "p95_max_abs_t": float(np.nanpercentile(maxabs, 95)),
        "p99_max_abs_t": float(np.nanpercentile(maxabs, 99)),
        "mean_max_abs_t": float(np.nanmean(maxabs)),
        "analytic_bar_one_sided": float(np.sqrt(2 * np.log(N))),
        "analytic_bar_two_sided": float(np.sqrt(2 * np.log(2 * N))),
    }

    # ---- rho1 bounce diagnostics -------------------------------------------------------
    rho = {nm: rho1_pooled(arr, base) for nm, arr in
           (("d_close_dislocation", d), ("d49", d49), ("e_imbalance_window", e),
            ("f_pre_publication", f), ("q_open_gap", q), ("x_print_day", x),
            ("u_offhours", u), ("ptc_print_vs_cont", ptc))}

    out = {
        "prereg_sha256": "1377e0f207ca1c5fd0c4bb33feae10b498e0ac15075e35bee082181c8e36d4e3",
        "n_formulas": N,
        "design_window": [dates[0], DESIGN_END],
        "held_window": [HELD_START, dates[-1]],
        "panel": {"days": int(D), "symbols": int(S),
                  "usable_symbol_days": int(base.sum())},
        "null": null,
        "rho1_first_difference": rho,
        "results": results,
    }
    (OUTDIR / "INVENT_0822B_auction.json").write_text(json.dumps(out, indent=1))
    np.save(CACHE / "placebo_t.npy", placebo_t)
    print(json.dumps(null, indent=1))

    rank = sorted(results.values(), key=lambda r: -abs(r["design"]["t"] or 0))
    print("\n== TOP 12 BY DESIGN |t| (gross) ==")
    for r in rank[:12]:
        dd, hh = r["design"], r["held"]
        print(f"{r['formula']:26s} des SR {dd['sharpe']:+6.2f} t {dd['t']:+6.2f} "
              f"| held SR {hh['sharpe']:+6.2f} t {hh['t']:+6.2f} "
              f"| held net0.5 SR {hh['net0.5_sharpe']:+6.2f} turn {hh['turnover']:.2f}")


if __name__ == "__main__":
    main()
