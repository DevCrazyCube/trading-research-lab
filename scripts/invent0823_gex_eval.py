#!/usr/bin/env python3
"""INVENT-0823 gamma sweep evaluation.

24 pre-registered formulas x 2 horizons = 48 cells, on a 49-name liquid
single-name + sector-ETF universe.

  signal  : built from option bars through the CLOSE of day t
  entry   : OPEN of day t+1        (>= 17.5 h after the signal print)
  exit    : CLOSE of t+1 (h='intraday')  or  OPEN of t+2 (h='day')

Nulls: (a) analytic max-|t| bar for 48 tests, (b) size-matched ADV-slot SIGNAL
PERMUTATION placebo, 500 draws, max |Sharpe| over the same 48 cells.

Usage:  invent0823_gex_eval.py design|heldout|both
"""
import gzip
import json
import math
import os
import sys

import numpy as np

ROOT = "/home/anont/meme"
OUT = os.path.join(ROOT, "research/data/inv0823_gex")
PANEL = os.path.join(OUT, "panel.json.gz")

DESIGN = ("2024-02-01", "2025-06-30")
HELDOUT = ("2025-07-01", "2026-08-21")
COSTS = (1.0, 3.0, 5.5)   # bp per side; 3.0 is the primary liquid-taker rail
SEED = 20260823


# ------------------------------------------------------------------ panel ---
def load():
    with gzip.open(PANEL, "rt") as f:
        p = json.load(f)
    unds = sorted(p)
    days = sorted({r["d"] for u in unds for r in p[u]})
    di = {d: i for i, d in enumerate(days)}
    ui = {u: i for i, u in enumerate(unds)}
    T, N = len(days), len(unds)
    F = {}

    def arr():
        return np.full((T, N), np.nan)

    keys = ["S", "adj_c", "adj_o", "adj_h", "adj_l", "adv", "net_gex", "gross_gex",
            "cg", "pg", "cvol", "pvol", "charm", "vanna", "Kpin", "Kcw", "Kpw",
            "flip", "otm_call_g", "otm_put_g", "put_surge_raw", "call_surge_raw",
            "iv1", "dte1", "front_gex"]
    for k in keys:
        F[k] = arr()
    for u in unds:
        j = ui[u]
        for r in p[u]:
            i = di[r["d"]]
            for k in keys:
                v = r.get(k)
                if v is not None:
                    F[k][i, j] = v
    F["_days"] = days
    F["_unds"] = unds
    return F


# ---------------------------------------------------------------- helpers ---
def roll_mean(x, w):
    T, N = x.shape
    out = np.full_like(x, np.nan)
    for i in range(w - 1, T):
        s = x[i - w + 1:i + 1]
        out[i] = np.nanmean(s, axis=0)
    return out


def roll_std(x, w):
    T, N = x.shape
    out = np.full_like(x, np.nan)
    for i in range(w - 1, T):
        s = x[i - w + 1:i + 1]
        out[i] = np.nanstd(s, axis=0)
    return out


def lag(x, k):
    out = np.full_like(x, np.nan)
    if k > 0:
        out[k:] = x[:-k]
    return out


def xs_rank_norm(x):
    """cross-sectional rank -> [-1, 1], NaN-safe, zero-mean."""
    T, N = x.shape
    out = np.full_like(x, np.nan)
    for i in range(T):
        row = x[i]
        m = np.isfinite(row)
        n = m.sum()
        if n < 8:
            continue
        v = row[m]
        order = v.argsort().argsort().astype(float)
        r = 2.0 * order / (n - 1) - 1.0
        r -= r.mean()
        out[i, m] = r
    return out


# --------------------------------------------------------------- signals ----
def build_signals(F):
    S = F["S"]
    adv = F["adv"]
    net = F["net_gex"]
    gross = F["gross_gex"]
    c = F["adj_c"]
    r1 = c / lag(c, 1) - 1.0

    sig = {}
    G1 = net / adv
    sig["G1_GEXNORM"] = G1
    m60, s60 = roll_mean(G1, 60), roll_std(G1, 60)
    G2 = (G1 - m60) / np.where(s60 > 0, s60, np.nan)
    sig["G2_GEXZ"] = G2
    sig["G3_GAMMA_REV_INTERACT"] = -np.sign(net) * r1
    sig["G4_DGEX1"] = G2 - lag(G2, 1)
    sig["G5_DGEX5"] = G2 - lag(G2, 5)
    G6 = net / gross
    sig["G6_GEXFRAC"] = G6

    P1 = (F["Kpin"] - S) / S
    sig["P1_PIN_DIST"] = P1
    sig["P2_PIN_X_GEX"] = P1 * np.clip(xs_rank_norm(G1), 0, None)
    dte = F["dte1"]
    opex_week = dte <= 7
    exp_eve = dte == 1
    sig["P3_PIN_OPEXWEEK"] = np.where(opex_week, P1, np.nan)
    sig["P4_PIN_EXPIRY_DAY"] = np.where(exp_eve, P1, np.nan)

    F1 = (S - F["flip"]) / S
    sig["F1_FLIP_DIST"] = F1
    sg = np.sign(F1)
    sig["F2_FLIP_CROSS"] = sg - lag(sg, 3)
    sig["F3_WALL_ASYM"] = ((F["Kcw"] - S) - (S - F["Kpw"])) / S
    sig["F4_FLIP_X_GEX"] = F1 * G6

    with np.errstate(divide="ignore", invalid="ignore"):
        S1 = np.log(np.where(F["cg"] > 0, F["cg"], np.nan)
                    / np.where(F["pg"] > 0, F["pg"], np.nan))
    sig["S1_CPRATIO"] = S1
    sig["S2_DCP1"] = S1 - lag(S1, 1)
    sig["S3_DCP5"] = S1 - lag(S1, 5)
    ps, cs = F["put_surge_raw"], F["call_surge_raw"]
    sig["S4_PUT_SURGE"] = ps / np.where(roll_mean(ps, 20) > 0, roll_mean(ps, 20), np.nan)
    sig["S5_CALL_SURGE"] = cs / np.where(roll_mean(cs, 20) > 0, roll_mean(cs, 20), np.nan)
    sig["S6_SKEW_TILT"] = (F["otm_call_g"] - F["otm_put_g"]) / gross

    sig["C1_CHARM"] = F["charm"] * S / adv
    div = F["iv1"] - lag(F["iv1"], 5)
    sig["C2_VANNA"] = F["vanna"] * S * div / adv
    frontshare = F["front_gex"] / gross
    # C3: signal is the front-month share measured on the expiry eve; the row it
    # sits on is the EXPIRY SESSION itself, so entry (t+1 open) is the first
    # session after the monthly roll-off.
    is_expiry_session = lag(dte, 1) == 1
    sig["C3_OPEX_ROLLOFF"] = np.where(is_expiry_session, lag(frontshare, 1), np.nan)
    sig["C4_PREOPEX"] = np.where(opex_week, frontshare / np.maximum(dte, 1), np.nan)

    # controls (not scored against the bar)
    ctrl = {}
    r5 = c / lag(c, 5) - 1.0
    for nm in ("G2_GEXZ", "S2_DCP1", "P1_PIN_DIST", "F1_FLIP_DIST", "S1_CPRATIO",
               "G6_GEXFRAC", "S3_DCP5", "C1_CHARM", "S6_SKEW_TILT", "S4_PUT_SURGE"):
        ctrl["R_" + nm] = residualise(sig[nm], [r1, r5])
    return sig, ctrl


def residualise(x, factors):
    """cross-sectional OLS residual of x on [1] + factors, per day."""
    T, N = x.shape
    out = np.full_like(x, np.nan)
    for i in range(T):
        m = np.isfinite(x[i])
        for f in factors:
            m &= np.isfinite(f[i])
        if m.sum() < 12:
            continue
        y = x[i, m]
        X = np.column_stack([np.ones(m.sum())] + [f[i, m] for f in factors])
        try:
            b, *_ = np.linalg.lstsq(X, y, rcond=None)
        except np.linalg.LinAlgError:
            continue
        out[i, m] = y - X @ b
    return out


# ------------------------------------------------------------- portfolio ----
def returns(F):
    o, c = F["adj_o"], F["adj_c"]
    # entry open(t+1), exit close(t+1)
    r_intra = np.full_like(o, np.nan)
    r_intra[:-1] = c[1:] / o[1:] - 1.0
    # entry open(t+1), exit open(t+2)
    r_day = np.full_like(o, np.nan)
    r_day[:-2] = o[2:] / o[1:-1] - 1.0
    # placebo: one-day-gap re-entry (skip a whole session, then trade the same way)
    r_gap = np.full_like(o, np.nan)
    r_gap[:-2] = c[2:] / o[2:] - 1.0
    r_gapday = np.full_like(o, np.nan)
    r_gapday[:-3] = o[3:] / o[2:-1] - 1.0
    return {"intraday": r_intra, "day": r_day, "gap": r_gap, "gap_day": r_gapday}


def book(sigmat, ret, mask=None):
    """rank-neutral dollar-neutral book. returns (daily pnl, turnover, active)."""
    w = xs_rank_norm(sigmat)
    ok = np.isfinite(w) & np.isfinite(ret)
    w = np.where(ok, w, 0.0)
    g = np.abs(w).sum(axis=1)
    w = np.divide(w, np.where(g > 0, g, np.nan)[:, None],
                  out=np.zeros_like(w), where=(g > 0)[:, None])
    pnl = (w * np.where(np.isfinite(ret), ret, 0.0)).sum(axis=1)
    act = g > 0
    return w, pnl, act


def stats(pnl, act, turn_per_day):
    p = pnl[act]
    n = p.size
    if n < 40:
        return None
    mu, sd = p.mean(), p.std(ddof=1)
    if sd <= 0:
        return None
    sr = mu / sd * math.sqrt(252.0)
    t = mu / (sd / math.sqrt(n))
    out = {"n": int(n), "gross_bp": mu * 1e4, "sharpe": sr, "t": t,
           "turnover": turn_per_day}
    for cbp in COSTS:
        net_mu = mu - turn_per_day * cbp * 1e-4
        out[f"net_sr_{cbp}"] = net_mu / sd * math.sqrt(252.0)
    out["breakeven_bp"] = (mu * 1e4 / turn_per_day) if turn_per_day > 0 else float("nan")
    return out


def turnover_of(w, horizon):
    """traded notional per active day."""
    if horizon == "intraday":
        return 2.0   # fully in and out every session
    d = np.abs(w[1:] - w[:-1]).sum(axis=1)
    act = (np.abs(w).sum(axis=1) > 0)[1:]
    return float(np.mean(d[act])) if act.any() else 0.0


def evaluate(sig, F, rets, lo, hi, horizons=("intraday", "day")):
    days = np.array(F["_days"])
    win = (days >= lo) & (days <= hi)
    res = {}
    for name, x in sig.items():
        xs = np.where(win[:, None], x, np.nan)
        for h in horizons:
            w, pnl, act = book(xs, rets[h])
            st = stats(pnl, act, turnover_of(w, h))
            if st:
                res[f"{name}|{h}"] = st
    return res


# ------------------------------------------------------------------ nulls ---
def adv_slot_permute_null(sig_names, sig, F, rets, lo, hi, draws=2000, nslot=5):
    """Size-matched placebo null by ADV-SLOT SIGNAL PERMUTATION.

    On every day the signal values are shuffled WITHIN ADV-decile slots, so the
    placebo book has the same cross-sectional size profile, the same liquidity
    profile and the same gross leverage as the real book -- only the name->signal
    assignment is destroyed. (Rotate-the-returns is known-broken and is not used.)

    Because rank-normalising a row and then permuting it is identical to permuting
    it and then rank-normalising, the weights of the permuted book are exactly the
    permuted weights of the real book, which makes the whole null vectorisable.

    ONE permutation per (draw, day) is shared by all formulas, so the null keeps
    the real cross-formula correlation instead of assuming independence.
    Statistic: max |Sharpe| over the full 2 x N-formula grid, per draw."""
    rng = np.random.default_rng(SEED)
    days = np.array(F["_days"])
    win = (days >= lo) & (days <= hi)
    adv = F["adv"]
    T, N = adv.shape
    slot_idx = []          # per day: list of arrays of column indices
    for i in range(T):
        if not win[i]:
            slot_idx.append([])
            continue
        idx = np.where(np.isfinite(adv[i]))[0]
        if idx.size < nslot:
            slot_idx.append([])
            continue
        order = idx[adv[i, idx].argsort()]
        slot_idx.append([g for g in np.array_split(order, nslot) if g.size > 1])

    # real weights, once
    W = {}
    for nm in sig_names:
        W[nm] = xs_rank_norm(np.where(win[:, None], sig[nm], np.nan))

    horizons = ("intraday", "day")
    R = {h: np.where(np.isfinite(rets[h]), rets[h], 0.0) for h in horizons}
    OKR = {h: np.isfinite(rets[h]) for h in horizons}

    maxes, maxt = [], []
    percell = {}
    base = np.arange(N)
    for d in range(draws):
        P = np.tile(base, (T, 1))
        for i in range(T):
            for g in slot_idx[i]:
                P[i, g] = g[rng.permutation(g.size)]
        rows = np.arange(T)[:, None]
        best = bestt = 0.0
        for nm in sig_names:
            wp = W[nm][rows, P]
            for h in horizons:
                w = np.where(np.isfinite(wp) & OKR[h], wp, 0.0)
                g = np.abs(w).sum(axis=1)
                act = g > 0
                n = int(act.sum())
                if n < 40:
                    continue
                w = w / np.where(g > 0, g, 1.0)[:, None]
                pnl = (w * R[h]).sum(axis=1)[act]
                sd = pnl.std(ddof=1)
                if sd > 0:
                    sr = abs(pnl.mean() / sd * math.sqrt(252.0))
                    tt = abs(pnl.mean() / (sd / math.sqrt(n)))
                    best = max(best, sr)
                    bestt = max(bestt, tt)
                    percell.setdefault(f"{nm}|{h}", {"sr": [], "t": [], "n": n})
                    percell[f"{nm}|{h}"]["sr"].append(sr)
                    percell[f"{nm}|{h}"]["t"].append(tt)
        maxes.append(best)
        maxt.append(bestt)
        if (d + 1) % 100 == 0:
            print(f"  null draw {d+1}/{draws} SRp95={np.percentile(maxes,95):.3f} "
                  f"tp95={np.percentile(maxt,95):.3f}", flush=True)
    return maxes, maxt, percell


def analytic_bar(n):
    """expected max |t| over n independent two-sided tests."""
    from statistics import NormalDist
    nd = NormalDist()
    return nd.inv_cdf(1 - 0.5 * (1 - (1 - 0.05) ** (1.0 / n)))


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "design"
    F = load()
    print(f"panel {len(F['_days'])} days x {len(F['_unds'])} names", flush=True)
    sig, ctrl = build_signals(F)
    rets = returns(F)
    out = {"universe": F["_unds"], "days": [F["_days"][0], F["_days"][-1]],
           "n_formulas": len(sig), "n_cells": 2 * len(sig)}

    if what in ("design", "both"):
        lo, hi = DESIGN
        out["design"] = evaluate(sig, F, rets, lo, hi)
        out["design_ctrl"] = evaluate(ctrl, F, rets, lo, hi)
        out["design_gapplacebo"] = evaluate(sig, F, rets, lo, hi,
                                            horizons=("gap", "gap_day"))
        out["analytic_bar_t"] = analytic_bar(2 * len(sig))
        mx, mt, pc = adv_slot_permute_null(
            list(sig), sig, F, rets, lo, hi,
            draws=int(os.environ.get("NULL_DRAWS", 2000)))
        out["placebo_null"] = {
            "draws": len(mx),
            "max_sharpe": {"mean": float(np.mean(mx)),
                           "p50": float(np.percentile(mx, 50)),
                           "p95": float(np.percentile(mx, 95)),
                           "p99": float(np.percentile(mx, 99)),
                           "max": float(np.max(mx))},
            "max_t": {"mean": float(np.mean(mt)),
                      "p50": float(np.percentile(mt, 50)),
                      "p95": float(np.percentile(mt, 95)),
                      "p99": float(np.percentile(mt, 99)),
                      "max": float(np.max(mt))}}
        # per-cell placebo p-value for the strongest cells
        json.dump({"max_sharpe": mx, "max_t": mt, "percell": pc},
                  open(os.path.join(ROOT, "research/trading_bot/"
                                    "INVENT_0823_gamma_nulldraws.json"), "w"))
        # degeneracy diagnostic
        days = np.array(F["_days"])
        win = (days >= lo) & (days <= hi)
        deg = {}
        for nm in ("G1_GEXNORM", "G6_GEXFRAC"):
            x = sig[nm][win]
            fin = np.isfinite(x)
            pos = (x > 0) & fin
            deg[nm] = {"frac_positive": float(pos.sum() / max(fin.sum(), 1)),
                       "n_obs": int(fin.sum())}
            byname = {}
            for j, u in enumerate(F["_unds"]):
                col = x[:, j]
                f2 = np.isfinite(col)
                if f2.sum() > 50:
                    byname[u] = float((col[f2] > 0).mean())
            deg[nm]["frac_positive_by_name"] = byname
        out["degeneracy"] = deg

    if what in ("heldout", "both"):
        lo, hi = HELDOUT
        out["heldout"] = evaluate(sig, F, rets, lo, hi)
        out["heldout_ctrl"] = evaluate(ctrl, F, rets, lo, hi)
        out["heldout_gapplacebo"] = evaluate(sig, F, rets, lo, hi,
                                             horizons=("gap", "gap_day"))

    p = os.path.join(ROOT, f"research/trading_bot/INVENT_0823_gamma_{what}.json")
    json.dump(out, open(p, "w"), indent=1)
    print("WROTE", p, flush=True)


if __name__ == "__main__":
    main()
