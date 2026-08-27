#!/usr/bin/env python3
"""T26 -- WIDE formula sweep over overnight-equity signals.

One parameterised harness. Every config is evaluated on the DESIGN window only
(2016-01-04 .. 2021-12-31, the split T3 froze). The held-out window
(2022-01-03 .. 2026-08-14) is touched ONLY for the handful of configs that clear the
noise bar, and only after the design sweep has been written to disk.

Two execution rails, because the MOC cutoff is 15:50 and that is not negotiable:

  rail A  "marketable"  -- signal may use the 15:59 last trade; entry is a marketable
                           order at 15:59 paying one measured half-spread; exit is the
                           next opening auction.
  rail B  "MOC-legal"   -- signal uses only information timestamped <= 15:49; entry is
                           the official closing auction via an MOC order lodged before
                           the 15:50 cutoff; exit is the next opening auction.

Costs (T3 / M0 conventions, all charged, never idealised):
  rail A entry   1.13 bp design / 1.43 bp test  (T3's own SIP-quote median half-spread
                 in the final second before the close, top-500-ADV universe)
  auction leg    0.50 bp        (M0: the official print sits ~1 median half-spread off
                 the mid; signed mean +0.18 bp, abs median 1.61 bp on rank 1-50)
  borrow         30 bp/yr on the 50 % short notional, accrued over calendar days held

Usage:
  python3 t26_overnight_sweep.py design       # full sweep, design window only
  python3 t26_overnight_sweep.py null         # joint max-Sharpe null by within-day shuffle
  python3 t26_overnight_sweep.py heldout NAME [NAME...]
"""

from __future__ import annotations

import datetime
import json
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
PANEL = ROOT / "research" / "data" / "t26_cache" / "panel.npz"
OUTDIR = ROOT / "research" / "trading_bot"
WORK = ROOT / "research" / "data" / "t26_cache"

DESIGN_START, DESIGN_END = "2016-01-04", "2021-12-31"
TEST_START, TEST_END = "2022-01-03", "2026-08-14"

HALF_SPREAD_DESIGN_BP = 1.13     # T3 measured, 2016-2021
HALF_SPREAD_TEST_BP = 1.43       # T3 measured, 2022-2026
AUCTION_LEG_BP = 0.50            # M0
BORROW_ANNUAL_BP = 30.0


# ---------------------------------------------------------------------------
# feature construction
# ---------------------------------------------------------------------------

def _roll_sum(x, w):
    """nan-aware trailing sum over `w` rows ENDING at row d-1 (strictly past)."""
    v = np.isfinite(x)
    xz = np.where(v, x, 0.0)
    cs = np.concatenate([np.zeros((1, x.shape[1])), np.cumsum(xz, axis=0)], axis=0)
    cn = np.concatenate([np.zeros((1, x.shape[1])), np.cumsum(v, axis=0)], axis=0)
    out = np.full_like(x, np.nan)
    n = np.full(x.shape, 0.0)
    out[w:] = cs[w:-1] - cs[:-1 - w]
    n[w:] = cn[w:-1] - cn[:-1 - w]
    out[n < w * 0.7] = np.nan
    return out


def _roll_std(x, w):
    v = np.isfinite(x)
    xz = np.where(v, x, 0.0)
    cs = np.concatenate([np.zeros((1, x.shape[1])), np.cumsum(xz, axis=0)], axis=0)
    cs2 = np.concatenate([np.zeros((1, x.shape[1])), np.cumsum(xz * xz, axis=0)], axis=0)
    cn = np.concatenate([np.zeros((1, x.shape[1])), np.cumsum(v, axis=0)], axis=0)
    s = np.full_like(x, np.nan)
    s2 = np.full_like(x, np.nan)
    n = np.zeros(x.shape)
    s[w:] = cs[w:-1] - cs[:-1 - w]
    s2[w:] = cs2[w:-1] - cs2[:-1 - w]
    n[w:] = cn[w:-1] - cn[:-1 - w]
    with np.errstate(invalid="ignore", divide="ignore"):
        var = s2 / n - (s / n) ** 2
    var[n < w * 0.7] = np.nan
    return np.sqrt(np.maximum(var, 0.0))


def load_features():
    z = np.load(PANEL, allow_pickle=True)
    days = [str(d) for d in z["days"]]
    syms = [str(s) for s in z["syms"]]
    O = z["O"].astype(np.float64)
    C = z["C"].astype(np.float64)
    ON = z["O_next"].astype(np.float64)
    P29 = z["P29"].astype(np.float64)
    P49 = z["P49"].astype(np.float64)
    P59 = z["P59"].astype(np.float64)
    ADV = z["ADV"].astype(np.float64)
    U500 = z["U500"].astype(bool)
    CA = z["CA"].astype(bool)
    CA_next = z["CA_next"].astype(bool)
    halfday = z["halfday_exit"].astype(bool)
    del z

    for M in (O, C, ON, P29, P49, P59):
        M[~np.isfinite(M)] = np.nan
        M[M <= 0] = np.nan

    nD, nS = C.shape
    F = {}

    with np.errstate(invalid="ignore", divide="ignore"):
        # --- available at 15:49 ---
        Cprev = np.full_like(C, np.nan); Cprev[1:] = C[:-1]
        Oprev = np.full_like(O, np.nan); Oprev[1:] = O[:-1]
        P59prev = np.full_like(P59, np.nan); P59prev[1:] = P59[:-1]

        F["p20_early"] = P49 / P29 - 1.0                 # 15:29 -> 15:49
        F["day49"] = P49 / O - 1.0                       # open auction -> 15:49
        F["gap"] = O / Cprev - 1.0                       # last night's realised overnight
        F["prev_day"] = Cprev / Oprev - 1.0              # yesterday's intraday
        F["prev_aucdev"] = Cprev / P59prev - 1.0         # yesterday's MOC-imbalance proxy

        c2c = C / Cprev - 1.0
        c2c[CA] = np.nan
        c2c[np.abs(c2c) > 0.35] = np.nan
        c2c_lag = np.full_like(c2c, np.nan); c2c_lag[1:] = c2c[:-1]

        gap_raw = F["gap"].copy()
        gap_raw[CA] = np.nan
        gap_raw[np.abs(gap_raw) > 0.35] = np.nan
        F["gap"] = gap_raw

        F["mom5"] = _roll_sum(c2c, 5)
        F["mom21"] = _roll_sum(c2c, 21)
        F["mom21_ex5"] = F["mom21"] - F["mom5"]
        F["vol21"] = _roll_std(c2c, 21)
        F["ovn5"] = _roll_sum(gap_raw, 5)
        F["ovn21"] = _roll_sum(gap_raw, 21)
        F["adv"] = ADV
        F["logadv"] = np.log(np.maximum(ADV, 1.0))

        # --- available only at 15:59 ---
        F["p10"] = P59 / P49 - 1.0                       # T3, window 10
        F["p30"] = P59 / P29 - 1.0                       # T3, window 30
        F["day59"] = P59 / O - 1.0                       # full session move
        F["accel"] = F["p10"] - F["p30"] / 3.0
        F["late_vs_early"] = F["p10"] - F["p20_early"]

    # --- targets ---
    with np.errstate(invalid="ignore", divide="ignore"):
        RET_A = ON / P59 - 1.0                           # 15:59 entry
        RET_B = ON / C - 1.0                             # closing-auction entry
    for M in (RET_A, RET_B):
        M[np.abs(M) > 0.35] = np.nan

    # --- one base validity mask shared by EVERY config (makes the joint null exact) ---
    need = ["p20_early", "day49", "gap", "prev_day", "prev_aucdev", "mom5", "mom21",
            "vol21", "ovn5", "adv", "p10", "p30", "day59"]
    valid = U500 & np.isfinite(RET_A) & np.isfinite(RET_B) & (~CA_next)
    for k in need:
        valid &= np.isfinite(F[k])
    valid &= ~halfday[:, None]
    valid[-1, :] = False

    # calendar-day gap to the exit, for the borrow accrual
    dts = [datetime.date.fromisoformat(d) for d in days]
    calgap = np.ones(nD)
    for i in range(nD - 1):
        calgap[i] = max(1, (dts[i + 1] - dts[i]).days)

    dow = np.array([d.weekday() for d in dts])
    tom = np.zeros(nD, dtype=bool)
    months = np.array([d[:7] for d in days])
    for m in np.unique(months):
        idx = np.where(months == m)[0]
        tom[idx[:3]] = True
        tom[idx[-1]] = True

    # market context from SPY (a member of the panel)
    j_spy = syms.index("SPY")
    spy_day = F["day59"][:, j_spy]
    spy_c2c = np.where(np.isfinite(C[:, j_spy]), C[:, j_spy], np.nan)
    spy_r = np.full(nD, np.nan)
    spy_r[1:] = spy_c2c[1:] / spy_c2c[:-1] - 1.0
    spy_vol21 = np.full(nD, np.nan)
    for i in range(21, nD):
        w = spy_r[i - 21:i]
        w = w[np.isfinite(w)]
        if w.size >= 15:
            spy_vol21[i] = w.std(ddof=1)

    ctx = {"days": days, "syms": syms, "calgap": calgap, "dow": dow, "tom": tom,
           "spy_day": spy_day, "spy_vol21": spy_vol21}
    return F, RET_A, RET_B, valid, ctx


# ---------------------------------------------------------------------------
# cross-sectional helpers (all operate row-wise on the valid set)
# ---------------------------------------------------------------------------

def _xs_z(x, valid):
    out = np.full_like(x, np.nan)
    xm = np.where(valid, x, np.nan)
    mu = np.nanmean(xm, axis=1, keepdims=True)
    sd = np.nanstd(xm, axis=1, keepdims=True)
    sd[sd == 0] = np.nan
    out = (xm - mu) / sd
    return out


def _xs_rank(x, valid):
    """row-wise rank in [0,1] over the valid entries; NaN elsewhere."""
    nD, nS = x.shape
    out = np.full((nD, nS), np.nan)
    xm = np.where(valid, x, np.inf)
    order = np.argsort(xm, axis=1, kind="stable")
    n = valid.sum(axis=1)
    for i in range(nD):
        k = n[i]
        if k < 2:
            continue
        out[i, order[i, :k]] = np.arange(k) / (k - 1.0)
    return out


def _xs_resid(y, x, valid):
    """row-wise OLS residual of y on x (with intercept) across the valid cross-section."""
    ym = np.where(valid, y, np.nan)
    xm = np.where(valid, x, np.nan)
    my = np.nanmean(ym, axis=1, keepdims=True)
    mx = np.nanmean(xm, axis=1, keepdims=True)
    dy, dx = ym - my, xm - mx
    num = np.nansum(dy * dx, axis=1, keepdims=True)
    den = np.nansum(dx * dx, axis=1, keepdims=True)
    den[den == 0] = np.nan
    return dy - (num / den) * dx


def _tercile_mask(x, valid, which):
    """rows x names -> bool mask selecting the requested tercile of x within each row."""
    r = _xs_rank(x, valid)
    if which == "hi":
        return valid & (r >= 2.0 / 3.0)
    if which == "lo":
        return valid & (r <= 1.0 / 3.0)
    return valid & (r > 1.0 / 3.0) & (r < 2.0 / 3.0)


# ---------------------------------------------------------------------------
# weight construction
# ---------------------------------------------------------------------------

def weights_decile(sig, sel, cut, min_names=100, fixed_k=None):
    """long the LOWEST `cut` of sig, short the HIGHEST. 50 % / 50 %, equal weight."""
    nD, nS = sig.shape
    W = np.zeros((nD, nS))
    sm = np.where(sel, sig, np.inf)
    order = np.argsort(sm, axis=1, kind="stable")
    n = sel.sum(axis=1)
    for i in range(nD):
        ni = n[i]
        if ni < min_names:
            continue
        k = fixed_k if fixed_k is not None else max(1, int(ni * cut))
        if 2 * k > ni:
            continue
        o = order[i]
        W[i, o[:k]] = 0.5 / k
        W[i, o[ni - k:ni]] = -0.5 / k
    return W


def weights_grouped_decile(sig, sel, cut, groups, min_names=100):
    """rank and cut WITHIN each group, then pool -- a neutrality constraint."""
    nD, nS = sig.shape
    W = np.zeros((nD, nS))
    for g in groups:
        Wg = weights_decile(sig, g, cut, min_names=20)
        W += Wg
    live = np.abs(W).sum(axis=1)
    ok = (sel.sum(axis=1) >= min_names) & (live > 0)
    W[~ok] = 0.0
    W[ok] /= live[ok, None]
    return W


def weights_continuous(sig, sel, kind="z", clip=3.0, min_names=100):
    """dollar-neutral continuous book: weight proportional to -(z or centred rank)."""
    if kind == "z":
        s = _xs_z(sig, sel)
        s = np.clip(s, -clip, clip)
    else:
        s = (_xs_rank(sig, sel) - 0.5) * 2.0
    s = np.where(sel & np.isfinite(s), s, 0.0)
    s = s - np.where(sel, 1, 0) * (s.sum(axis=1, keepdims=True) /
                                   np.maximum(sel.sum(axis=1, keepdims=True), 1))
    s = np.where(sel, s, 0.0)
    gross = np.abs(s).sum(axis=1, keepdims=True)
    gross[gross == 0] = np.nan
    W = -s / gross          # sign: low signal -> long, to match the decile convention
    W[~np.isfinite(W)] = 0.0
    W[sel.sum(axis=1) < min_names] = 0.0
    return W


def weights_leg(sig, sel, cut, leg, min_names=100):
    """one decile against the equal-weighted cross-section (long-only / short-only alpha)."""
    nD, nS = sig.shape
    W = np.zeros((nD, nS))
    sm = np.where(sel, sig, np.inf)
    order = np.argsort(sm, axis=1, kind="stable")
    n = sel.sum(axis=1)
    for i in range(nD):
        ni = n[i]
        if ni < min_names:
            continue
        k = max(1, int(ni * cut))
        o = order[i, :ni]
        pick = o[:k] if leg == "long" else o[ni - k:ni]
        s = 1.0 if leg == "long" else -1.0
        W[i, pick] += s / k
        W[i, o] -= s / ni
    return W


# ---------------------------------------------------------------------------
# the config table
# ---------------------------------------------------------------------------

def build_configs(F, valid, ctx):
    """name -> (rail, W, day_mask, short_notional). Nothing here reads a return."""
    cfg = {}
    V = valid
    z = lambda k: _xs_z(F[k], V)  # noqa: E731

    vol_hi = _tercile_mask(F["vol21"], V, "hi")
    vol_lo = _tercile_mask(F["vol21"], V, "lo")
    vol_mid = _tercile_mask(F["vol21"], V, "mid")
    adv_hi = _tercile_mask(F["adv"], V, "hi")
    adv_lo = _tercile_mask(F["adv"], V, "lo")
    adv_mid = _tercile_mask(F["adv"], V, "mid")
    big_move = _tercile_mask(np.abs(F["day59"]), V, "hi")

    allday = np.ones(len(ctx["days"]), dtype=bool)

    def add(name, rail, W, dmask=None, short_notional=0.5):
        cfg[name] = (rail, W, allday if dmask is None else dmask, short_notional)

    # ---------- rail A: 15:59 marketable entry ----------
    add("A01_T3_p10_c10", "A", weights_decile(F["p10"], V, 0.10))
    add("A02_T3_p30_c10", "A", weights_decile(F["p30"], V, 0.10))
    add("A03_T3_p10_c20", "A", weights_decile(F["p10"], V, 0.20))
    add("A04_dayfade", "A", weights_decile(F["day59"], V, 0.10))
    add("A05_daycont", "A", weights_decile(-F["day59"], V, 0.10))
    add("A06_accel_fade", "A", weights_decile(F["accel"], V, 0.10))
    add("A07_late_vs_early", "A", weights_decile(F["late_vs_early"], V, 0.10))
    add("A08_p10_resid_day", "A", weights_decile(_xs_resid(F["p10"], F["day59"], V), V, 0.10))
    add("A09_p10_over_vol", "A", weights_decile(F["p10"] / np.maximum(F["vol21"], 1e-5), V, 0.10))
    add("A10_p10_x_vol", "A", weights_decile(F["p10"] * F["vol21"], V, 0.10))
    add("A11_p10_z_plus_day_z", "A", weights_decile(z("p10") + z("day59"), V, 0.10))
    add("A12_p10_minus_gap", "A", weights_decile(z("p10") + z("gap"), V, 0.10))
    add("A13_p10_rank_cont", "A", weights_continuous(F["p10"], V, kind="rank"))
    add("A14_p10_z_cont", "A", weights_continuous(F["p10"], V, kind="z"))
    add("A15_p10_top20", "A", weights_decile(F["p10"], V, 0.0, fixed_k=20))
    add("A16_p10_c02", "A", weights_decile(F["p10"], V, 0.02))
    add("A17_p10_c30", "A", weights_decile(F["p10"], V, 0.30))
    add("A18_p10_hivol", "A", weights_decile(F["p10"], vol_hi, 0.10, min_names=40))
    add("A19_p10_lovol", "A", weights_decile(F["p10"], vol_lo, 0.10, min_names=40))
    add("A20_p10_hiadv", "A", weights_decile(F["p10"], adv_hi, 0.10, min_names=40))
    add("A21_p10_loadv", "A", weights_decile(F["p10"], adv_lo, 0.10, min_names=40))
    add("A22_p10_bigmove", "A", weights_decile(F["p10"], big_move, 0.10, min_names=40))
    add("A23_p10_volneutral", "A",
        weights_grouped_decile(F["p10"], V, 0.10, [vol_lo, vol_mid, vol_hi]))
    add("A24_p10_advneutral", "A",
        weights_grouped_decile(F["p10"], V, 0.10, [adv_lo, adv_mid, adv_hi]))
    add("A25_gapfade", "A", weights_decile(F["gap"], V, 0.10))
    add("A26_gapcont", "A", weights_decile(-F["gap"], V, 0.10))
    add("A27_aucdev_lag_fade", "A", weights_decile(F["prev_aucdev"], V, 0.10))
    add("A28_aucdev_lag_cont", "A", weights_decile(-F["prev_aucdev"], V, 0.10))
    add("A29_mom5_rev", "A", weights_decile(F["mom5"], V, 0.10))
    add("A30_mom21_cont", "A", weights_decile(-F["mom21_ex5"], V, 0.10))
    add("A31_ovn5_rev", "A", weights_decile(F["ovn5"], V, 0.10))
    add("A32_ovn5_cont", "A", weights_decile(-F["ovn5"], V, 0.10))
    add("A33_prevday_fade", "A", weights_decile(F["prev_day"], V, 0.10))
    add("A34_p10_long_leg", "A", weights_leg(F["p10"], V, 0.10, "long"), None, 0.5)
    add("A35_p10_short_leg", "A", weights_leg(F["p10"], V, 0.10, "short"), None, 0.5)

    # time-series conditioners: same book, fewer nights
    W_t3 = weights_decile(F["p10"], V, 0.10)
    sv = ctx["spy_vol21"]
    fin = np.isfinite(sv)
    hi_thr = np.nanquantile(sv[fin], 2.0 / 3.0)
    lo_thr = np.nanquantile(sv[fin], 1.0 / 3.0)
    add("A36_p10_hivolregime", "A", W_t3, fin & (sv >= hi_thr))
    add("A37_p10_lovolregime", "A", W_t3, fin & (sv <= lo_thr))
    add("A38_p10_downmkt", "A", W_t3, np.isfinite(ctx["spy_day"]) & (ctx["spy_day"] < 0))
    add("A39_p10_upmkt", "A", W_t3, np.isfinite(ctx["spy_day"]) & (ctx["spy_day"] > 0))
    add("A40_p10_tom", "A", W_t3, ctx["tom"])
    add("A41_p10_nontom", "A", W_t3, ~ctx["tom"])
    add("A42_p10_no_friday", "A", W_t3, ctx["dow"] != 4)
    add("A43_p10_friday", "A", W_t3, ctx["dow"] == 4)

    # ---------- rail B: MOC-legal, information <= 15:49, entry at the closing auction ----------
    add("B01_T3pre_p20early", "B", weights_decile(F["p20_early"], V, 0.10))
    add("B02_day49_fade", "B", weights_decile(F["day49"], V, 0.10))
    add("B03_gapfade", "B", weights_decile(F["gap"], V, 0.10))
    add("B04_aucdev_lag_fade", "B", weights_decile(F["prev_aucdev"], V, 0.10))
    add("B05_mom5_rev", "B", weights_decile(F["mom5"], V, 0.10))
    add("B06_combo_pre", "B", weights_decile(_xs_z(F["p20_early"], V) + _xs_z(F["day49"], V),
                                             V, 0.10))
    add("B07_ovn5_rev", "B", weights_decile(F["ovn5"], V, 0.10))
    add("B08_prevday_fade", "B", weights_decile(F["prev_day"], V, 0.10))
    return cfg


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------

def evaluate(W, dmask, rail, short_notional, RET_A, RET_B, ctx, rows, half_spread_bp,
             auction_bp=AUCTION_LEG_BP, borrow_bp=BORROW_ANNUAL_BP):
    RET = RET_A if rail == "A" else RET_B
    R = np.where(np.isfinite(RET), RET, 0.0)
    live = (np.abs(W).sum(axis=1) > 0) & dmask
    sel = rows & live
    if sel.sum() < 50:
        return None
    gross = (W[sel] * R[sel]).sum(axis=1)
    entry = half_spread_bp if rail == "A" else auction_bp
    turn = np.abs(W[sel]).sum(axis=1)          # gross notional traded, 1.0 for a 50/50 book
    cost = turn * (entry + auction_bp) / 1e4
    cost = cost + short_notional * (borrow_bp / 1e4) * ctx["calgap"][sel] / 365.25
    net = gross - cost
    return {"dates": np.array(ctx["days"])[sel], "gross": gross, "net": net,
            "cost": cost}


def stats(x):
    n = x.size
    mu = float(np.mean(x))
    sd = float(np.std(x, ddof=1))
    if sd == 0 or n < 3:
        return {"n": n, "mean_bp": mu * 1e4, "sharpe": 0.0, "t": 0.0}
    return {"n": n, "mean_bp": mu * 1e4, "sd_bp": sd * 1e4,
            "sharpe": mu / sd * math.sqrt(252.0),
            "t": mu / (sd / math.sqrt(n)),
            "hit": float((x > 0).mean())}


def window_rows(days, lo, hi):
    d = np.array(days)
    return (d >= lo) & (d <= hi)


# ---------------------------------------------------------------------------

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "design"
    F, RET_A, RET_B, valid, ctx = load_features()
    print(f"valid symbol-nights: {int(valid.sum()):,}", flush=True)
    cfg = build_configs(F, valid, ctx)
    print(f"configs: {len(cfg)}", flush=True)
    rows_design = window_rows(ctx["days"], DESIGN_START, DESIGN_END)
    rows_test = window_rows(ctx["days"], TEST_START, TEST_END)

    if cmd == "design":
        res = {}
        for name, (rail, W, dmask, sn) in cfg.items():
            r = evaluate(W, dmask, rail, sn, RET_A, RET_B, ctx, rows_design,
                         HALF_SPREAD_DESIGN_BP)
            if r is None:
                print(f"  {name}: too few nights", flush=True)
                continue
            res[name] = {"rail": rail, "net": stats(r["net"]), "gross": stats(r["gross"]),
                         "mean_cost_bp": float(np.mean(r["cost"]) * 1e4)}
            print(f"  {name:26s} rail {rail}  n={res[name]['net']['n']:5d} "
                  f"net {res[name]['net']['mean_bp']:+7.2f} bp  SR {res[name]['net']['sharpe']:+6.2f} "
                  f"t {res[name]['net']['t']:+5.2f}   gross SR {res[name]['gross']['sharpe']:+6.2f}",
                  flush=True)
            np.save(WORK / f"net_design_{name}.npy", r["net"])
        json.dump(res, open(WORK / "design_results.json", "w"), indent=1)
        print("design sweep written", flush=True)

    elif cmd == "null":
        reps = int(sys.argv[2]) if len(sys.argv) > 2 else 300
        rng = np.random.default_rng(20260820)
        names = list(cfg)
        drow = np.where(rows_design)[0]
        RA = np.where(np.isfinite(RET_A), RET_A, 0.0)[drow]
        RB = np.where(np.isfinite(RET_B), RET_B, 0.0)[drow]
        VD = valid[drow]
        vidx = [np.where(VD[i])[0] for i in range(VD.shape[0])]
        prep = []
        for name in names:
            rail, W, dmask, sn = cfg[name]
            live = ((np.abs(W).sum(axis=1) > 0) & dmask & rows_design)[drow]
            li = np.where(live)[0]
            prep.append((name, rail, W[drow][li], li))
        maxes, maxt, per_name = [], [], {n: [] for n in names}
        for b in range(reps):
            PA = RA.copy()
            PB = RB.copy()
            for i in range(VD.shape[0]):
                ix = vidx[i]
                if ix.size < 2:
                    continue
                perm = rng.permutation(ix.size)
                PA[i, ix] = RA[i, ix[perm]]
                PB[i, ix] = RB[i, ix[perm]]
            best, bestt = -9e9, -9e9
            for name, rail, Wl, li in prep:
                P = PA if rail == "A" else PB
                g = (Wl * P[li]).sum(axis=1)
                sd = g.std(ddof=1)
                if sd == 0:
                    s = t = 0.0
                else:
                    s = g.mean() / sd * math.sqrt(252.0)
                    t = g.mean() / (sd / math.sqrt(g.size))
                per_name[name].append(s)
                best = max(best, s)
                bestt = max(bestt, t)
            maxes.append(best)
            maxt.append(bestt)
            if (b + 1) % 25 == 0:
                print(f"  null rep {b+1}/{reps}  max-SR p50={np.quantile(maxes,0.5):.3f} "
                      f"p95={np.quantile(maxes,0.95):.3f} | max-t p50={np.quantile(maxt,0.5):.2f} "
                      f"p95={np.quantile(maxt,0.95):.2f}", flush=True)

        def q(v):
            return {"mean": float(np.mean(v)), "p50": float(np.quantile(v, .50)),
                    "p90": float(np.quantile(v, .90)), "p95": float(np.quantile(v, .95)),
                    "p99": float(np.quantile(v, .99)), "max": float(np.max(v))}
        out = {"reps": reps, "n_configs": len(names),
               "max_sharpe_null": q(maxes), "max_t_null": q(maxt),
               "per_name_sd": {n: float(np.std(v, ddof=1)) for n, v in per_name.items()},
               "per_name_p95": {n: float(np.quantile(v, 0.95)) for n, v in per_name.items()}}
        json.dump(out, open(WORK / "null_results.json", "w"), indent=1)
        print(json.dumps({"max_sharpe_null": out["max_sharpe_null"],
                          "max_t_null": out["max_t_null"]}, indent=1), flush=True)

    elif cmd == "heldout":
        picks = sys.argv[2:]
        res = {}
        for name in picks:
            rail, W, dmask, sn = cfg[name]
            r = evaluate(W, dmask, rail, sn, RET_A, RET_B, ctx, rows_test,
                         HALF_SPREAD_TEST_BP)
            if r is None:
                print(f"  {name}: too few nights"); continue
            # cost sensitivity: 2x the measured spread, and the zero-cost bound
            r2 = evaluate(W, dmask, rail, sn, RET_A, RET_B, ctx, rows_test,
                          HALF_SPREAD_TEST_BP * 2, auction_bp=AUCTION_LEG_BP * 2)
            r0 = evaluate(W, dmask, rail, sn, RET_A, RET_B, ctx, rows_test, 0.0,
                          auction_bp=0.0, borrow_bp=0.0)
            res[name] = {"rail": rail, "net": stats(r["net"]), "gross": stats(r0["net"]),
                         "net_2x_cost": stats(r2["net"]),
                         "mean_cost_bp": float(np.mean(r["cost"]) * 1e4)}
            s = res[name]
            print(f"  {name:26s} HELD OUT n={s['net']['n']:5d} net {s['net']['mean_bp']:+7.2f} bp "
                  f"SR {s['net']['sharpe']:+6.2f} t {s['net']['t']:+5.2f} | "
                  f"2x-cost SR {s['net_2x_cost']['sharpe']:+6.2f} | zero-cost SR "
                  f"{s['gross']['sharpe']:+6.2f}", flush=True)
            np.save(WORK / f"net_test_{name}.npy", r["net"])
        prev = {}
        p = WORK / "heldout_results.json"
        if p.exists():
            prev = json.load(open(p))
        prev.update(res)
        json.dump(prev, open(p, "w"), indent=1)

    else:
        raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    main()
