#!/usr/bin/env python3
"""INVENT_0825 funding-settlement-window formulas.

Every formula returns (mask, w_raw, entry_bar, exit_bar, fund_cross).
Fills: open of the bar AFTER the last bar the signal reads.  Never same-bar.
"""
import numpy as np
from f0825_lib import Panel

BAR = 1          # 5 minutes
H30 = 6
H15 = 3
H60 = 12
H120 = 24


def _safe(P, b):
    return np.clip(b, 0, P.NT - 1)


def xs_weights(P, mask, x):
    """per-stamp demeaned rank weights, dollar-neutral, sum|w| = 1."""
    w = np.zeros(x.shape)
    ok = mask & np.isfinite(x)
    order = np.argsort(P.ev_g[ok], kind="stable")
    idx = np.where(ok)[0][order]
    g = P.ev_g[idx]
    bnd = np.flatnonzero(np.diff(g)) + 1
    for a, b in zip(np.r_[0, bnd], np.r_[bnd, len(idx)]):
        sl = idx[a:b]
        if sl.size < 6:
            continue
        r = np.argsort(np.argsort(x[sl])).astype(float)
        r = r - r.mean()
        s = np.abs(r).sum()
        if s > 0:
            w[sl] = r / s
    return w


def ts_weights(P, mask, sgn):
    """equal-weight across the symbols trading at each stamp, sum|w| = 1."""
    w = np.zeros(sgn.shape)
    ok = mask & np.isfinite(sgn) & (sgn != 0)
    cnt = np.zeros(P.NS)
    np.add.at(cnt, P.ev_g[ok], 1.0)
    c = cnt[P.ev_g]
    w[ok] = sgn[ok] / np.maximum(c[ok], 1.0)
    return w


# --------------------------- feature builders ------------------------------ #

def feat_oi_pre(P, n):
    """OI change over n bars ending at bar B-1 (known at B-1)."""
    s, B = P.ev_s, P.ev_b
    a = P.oi[s, _safe(P, B - 1 - n)]
    b = P.oi[s, _safe(P, B - 1)]
    with np.errstate(invalid="ignore", divide="ignore"):
        x = b / a - 1.0
    x[~np.isfinite(x)] = np.nan
    return x.astype(np.float64)


def feat_oi_post(P, n):
    s, B = P.ev_s, P.ev_b
    a = P.oi[s, _safe(P, B)]
    b = P.oi[s, _safe(P, B + n)]
    with np.errstate(invalid="ignore", divide="ignore"):
        x = b / a - 1.0
    x[~np.isfinite(x)] = np.nan
    return x.astype(np.float64)


_CS = {}


def _cs(P, key):
    if key not in _CS:
        _CS[key] = np.cumsum(np.nan_to_num(getattr(P, key), nan=0.0).astype(np.float64),
                             axis=1)
    return _CS[key]


def _win_sum(P, key, s, lo, hi):
    """sum of arr[s, lo:hi] per event, via cumulative sums."""
    cs = _cs(P, key)
    return cs[s, hi - 1] - np.where(lo > 0, cs[s, lo - 1], 0.0)


def feat_taker_pre(P, n):
    """taker buy imbalance over the n bars ending at B-1 (known at B-1)."""
    s, B = P.ev_s, P.ev_b
    lo = _safe(P, B - n); hi = _safe(P, B)
    q = _win_sum(P, "qv", s, lo, hi)
    t = _win_sum(P, "tbq", s, lo, hi)
    with np.errstate(invalid="ignore", divide="ignore"):
        x = (2.0 * t - q) / q
    x[~np.isfinite(x)] = np.nan
    return x.astype(np.float64)


def feat_vol_spike(P, n, base=288):
    s, B = P.ev_s, P.ev_b
    q = _win_sum(P, "qv", s, _safe(P, B - n), _safe(P, B)) / n
    qb = _win_sum(P, "qv", s, _safe(P, B - base), _safe(P, B)) / base
    with np.errstate(invalid="ignore", divide="ignore"):
        x = q / qb
    x[~np.isfinite(x)] = np.nan
    return x.astype(np.float64)


def feat_ret_pre(P, n):
    """return from open(B-n) to close(B-1); known at B-1."""
    s, B = P.ev_s, P.ev_b
    a = P.o[s, _safe(P, B - n)]; b = P.c[s, _safe(P, B - 1)]
    with np.errstate(invalid="ignore", divide="ignore"):
        x = b / a - 1.0
    x[~np.isfinite(x)] = np.nan
    return x.astype(np.float64)


def feat_stampbar(P):
    """body of the stamp bar: close(B)/open(B) - 1; known at close of bar B."""
    s, B = P.ev_s, P.ev_b
    a = P.o[s, B]; b = P.c[s, B]
    with np.errstate(invalid="ignore", divide="ignore"):
        x = b / a - 1.0
    x[~np.isfinite(x)] = np.nan
    return x.astype(np.float64)


# ------------------------------- formulas ---------------------------------- #

def build(P):
    """-> dict name -> (w, entry, exit, fund_cross, kind)"""
    S, B = P.ev_s, P.ev_b
    base = (B - 288 >= 0) & (B + H120 + H30 + 2 < P.NT)
    px_ok = np.isfinite(P.o[S, _safe(P, B)])
    m0 = base & px_ok
    F = {}

    r1 = P.ev_r1                      # previous stamp's rate  (known pre-stamp)
    r0 = P.ev_r                       # rate settled AT this stamp (post only)
    s1 = np.sign(r1)
    s0 = np.sign(r0)

    def add(name, w, e, x, fc, kind):
        F[name] = (w, _safe(P, e), _safe(P, x), fc, kind)

    T = np.ones(len(B), bool)
    Fa = np.zeros(len(B), bool)

    # --- A: pre-settlement positioning drift (signal = LAST stamp's rate) ----
    add("A1_PRE_FADE_30", ts_weights(P, m0, -s1), B - H30, B, T, "TS")
    add("A2_PRE_FADE_15", ts_weights(P, m0, -s1), B - H15, B, T, "TS")
    add("A3_PRE_FADE_60", ts_weights(P, m0, -s1), B - H60, B, T, "TS")
    add("A4_PRE_FADE_30_FLAT", ts_weights(P, m0, -s1), B - H30, B - 1, Fa, "TS")
    add("A5_PRE_FOLLOW_30", ts_weights(P, m0, s1), B - H30, B, T, "TS")
    # threshold fixed a priori at the Binance 0.01%/8h baseline -- no lookahead
    big = m0 & (np.abs(r1) > 1e-4)
    add("A6_PRE_FADE_30_BIG", ts_weights(P, big, -s1), B - H30, B, T, "TS")

    # --- B: post-settlement reaction (signal = the rate just settled) --------
    add("B1_POST_FADE_30", ts_weights(P, m0, -s0), B + 1, B + 1 + H30, Fa, "TS")
    add("B2_POST_FOLLOW_30", ts_weights(P, m0, s0), B + 1, B + 1 + H30, Fa, "TS")
    add("B3_POST_FADE_120", ts_weights(P, m0, -s0), B + 1, B + 1 + H120, Fa, "TS")
    add("B4_POST_FADE_15", ts_weights(P, m0, -s0), B + 1, B + 1 + H15, Fa, "TS")

    # --- C: cross-sectional funding-magnitude books around the stamp --------
    add("C1_XS_PRE_MAG_30", xs_weights(P, m0, -r1), B - H30, B, T, "XS")
    add("C2_XS_POST_MAG_30", xs_weights(P, m0, -r0), B + 1, B + 1 + H30, Fa, "XS")
    add("C3_XS_POST_MAG_15", xs_weights(P, m0, -r0), B + 1, B + 1 + H15, Fa, "XS")
    add("C4_XS_POST_MAG_120", xs_weights(P, m0, -r0), B + 1, B + 1 + H120, Fa, "XS")

    # --- D: funding-sign-flip reactions -------------------------------------
    flip = m0 & (s0 != s1) & (s0 != 0) & (s1 != 0)
    add("D1_FLIP_FOLLOW_120", ts_weights(P, flip, s0), B + 1, B + 1 + H120, Fa, "TS")
    add("D2_FLIP_FADE_120", ts_weights(P, flip, -s0), B + 1, B + 1 + H120, Fa, "TS")
    flipneg = m0 & (s1 > 0) & (s0 < 0)
    add("D3_FLIP_TO_NEG_LONG", ts_weights(P, flipneg, np.ones_like(s0)),
        B + 1, B + 1 + H120, Fa, "TS")

    # --- E: the settlement bar itself ---------------------------------------
    sb = feat_stampbar(P)
    add("E1_STAMPBAR_FADE", xs_weights(P, m0, -sb), B + 1, B + 1 + H30, Fa, "XS")
    add("E2_STAMPBAR_MOM", xs_weights(P, m0, sb), B + 1, B + 1 + H30, Fa, "XS")
    add("E3_STAMPBAR_FADE_15", xs_weights(P, m0, -sb), B + 1, B + 1 + H15, Fa, "XS")

    # --- F: OI unwind / build around settlement -----------------------------
    oip = feat_oi_pre(P, H30)
    oiq = feat_oi_post(P, H30)
    add("F1_XS_OI_UNWIND_PRE", xs_weights(P, m0, -oip), B, B + H30, T, "XS")
    add("F2_XS_OI_BUILD_PRE", xs_weights(P, m0, oip), B, B + H30, T, "XS")
    add("F3_XS_OI_POST", xs_weights(P, m0, oiq), B + 1 + H30, B + 1 + H30 + H120, Fa, "XS")
    add("F4_XS_OI_SQUEEZE", xs_weights(P, m0, oip * (-np.sign(r1))), B, B + H30, T, "XS")

    # --- G: pre-stamp flow / run-up / volume --------------------------------
    tk = feat_taker_pre(P, H30)
    add("G1_XS_TAKER_PRE_FADE", xs_weights(P, m0, -tk), B, B + H30, T, "XS")
    add("G2_XS_TAKER_PRE_MOM", xs_weights(P, m0, tk), B, B + H30, T, "XS")
    rp = feat_ret_pre(P, H60)
    add("G3_XS_RUNUP_FADE_1H", xs_weights(P, m0, -rp), B, B + H60, T, "XS")
    vs = feat_vol_spike(P, H30)
    add("G4_XS_VOLSPIKE_FADE", xs_weights(P, m0, -vs), B, B + H30, T, "XS")
    return F
