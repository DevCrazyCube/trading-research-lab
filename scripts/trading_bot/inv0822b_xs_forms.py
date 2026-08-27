#!/usr/bin/env python3
"""The 27 cross-sectional crypto-spot formulas of INVENT 0822B.

Every formula returns a coin-space score panel SIG where SIG[:,t] is computed from data
through the CLOSE of day t-1 (the shift is applied here, once, at the end of build()).
Signs are NOT baked in: each formula's sign is fitted on the design window's GROSS P&L
and then frozen, so the multiple-testing bar is the sign-agnostic sqrt(2 ln 2N).
"""
from __future__ import annotations
import numpy as np
from inv0822b_xs_lib import roll_mean, roll_std, roll_sum_ok, shift

HORIZONS = (1, 2, 3, 5, 7, 14, 30, 60, 90, 180)


def _cum(lp, w):
    """Cumulative log return over the w days ending at day t."""
    return lp - shift(lp, w)


def _xsz(x, U):
    """Cross-sectional rank z-score inside the universe (for blends only)."""
    s = np.where(U & np.isfinite(x), x, np.nan)
    out = np.full(s.shape, np.nan)
    for t in range(s.shape[1]):
        col = s[:, t]
        m = np.isfinite(col)
        if m.sum() < 15:
            continue
        v = col[m]
        r = np.argsort(np.argsort(v)).astype(float)
        out[m, t] = (r - r.mean()) / max(r.std(), 1e-9)
    return out


def build(P, F, U, btc_idx):
    """Return {name: (family, SIG)} -- SIG already lagged one day (info <= close t-1)."""
    lvw, rv, qv, n, tbq = F["lvw"], F["r_v"], F["qv"], F["n"], F["tbq"]
    out = {}

    # ---- family H: pure trailing-return horizon ranking (VWAP prices) -------------
    for h in HORIZONS:
        out[f"H{h:03d}_RET"] = ("H", _cum(lvw, h))

    # ---- family X: momentum refinements -----------------------------------------
    out["X1_SKIP30_7"] = ("X", shift(lvw, 7) - shift(lvw, 30))
    out["X2_SKIP90_14"] = ("X", shift(lvw, 14) - shift(lvw, 90))
    b = _xsz(_cum(lvw, 7), U) + _xsz(_cum(lvw, 30), U) + _xsz(_cum(lvw, 90), U)
    out["X3_BLEND_7_30_90"] = ("X", b / 3.0)
    vol60 = roll_std(rv, 60)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["X4_VOLADJ60"] = ("X", np.where(vol60 > 0, _cum(lvw, 60) / vol60, np.nan))
    # BTC-beta residual momentum: beta from a trailing 90d regression of r_v on BTC r_v
    br = rv[btc_idx]
    brm = br[None, :]
    cov = roll_mean(rv * brm, 90) - roll_mean(rv, 90) * roll_mean(brm, 90)
    var = roll_mean(brm * brm, 90) - roll_mean(brm, 90) ** 2
    with np.errstate(invalid="ignore", divide="ignore"):
        beta = np.where(var > 0, cov / var, np.nan)
    beta = np.clip(beta, -4, 4)
    bcum = np.cumsum(np.nan_to_num(br))[None, :] * np.ones((rv.shape[0], 1))
    bc60 = bcum - shift(bcum, 60)
    out["X5_IDIO60"] = ("X", _cum(lvw, 60) - beta * bc60)
    up = (rv > 0).astype(float)
    up[~np.isfinite(rv)] = np.nan
    out["X6_CONSIST60"] = ("X", roll_mean(up, 60))

    # ---- family V: volume / activity ranking -------------------------------------
    adv30 = roll_mean(qv, 30)
    out["V1_ADV_LEVEL"] = ("V", np.log(np.where(adv30 > 0, adv30, np.nan)))
    adv5 = roll_mean(qv, 5); adv60 = roll_mean(qv, 60)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["V2_DVOL_GROWTH"] = ("V", np.log(np.where((adv5 > 0) & (adv60 > 0),
                                                      adv5 / adv60, np.nan)))
        tick = np.where((n > 0) & (qv > 0), qv / n, np.nan)
        out["V3_TICKET"] = ("V", np.log(np.where(roll_mean(tick, 20) > 0,
                                                 roll_mean(tick, 20), np.nan)))
        ts = np.where(qv > 0, tbq / qv, np.nan)
        out["V4_TAKER_SHARE20"] = ("V", roll_mean(ts, 20))
        adv90 = roll_mean(qv, 90)
        out["V5_VOL_TREND"] = ("V", np.log(np.where((adv30 > 0) & (adv90 > 0),
                                                    adv30 / adv90, np.nan)))

    # ---- family S: volatility / distribution shape -------------------------------
    out["S1_VOL30"] = ("S", roll_std(rv, 30))
    v20 = roll_std(rv, 20)
    out["S2_VOLOFVOL60"] = ("S", roll_std(v20, 60))
    mx = np.full(rv.shape, np.nan)
    for t in range(19, rv.shape[1]):
        blk = rv[:, t - 19:t + 1]
        ok = np.isfinite(blk).sum(1) >= 15
        with np.errstate(invalid="ignore"):
            mm = np.nanmax(np.where(np.isfinite(blk), blk, -np.inf), axis=1)
        mx[:, t] = np.where(ok, mm, np.nan)
    out["S3_MAX20"] = ("S", mx)
    m1 = roll_mean(rv, 60); s1 = roll_std(rv, 60)
    m3 = roll_mean((rv - m1) ** 3, 60)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["S4_SKEW60"] = ("S", np.where(s1 > 0, m3 / s1 ** 3, np.nan))
    dn = np.where(np.isfinite(rv), np.minimum(rv, 0.0) ** 2, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["S5_DOWNRATIO60"] = ("S", np.where(s1 > 0,
                                               np.sqrt(roll_mean(dn, 60)) / s1, np.nan))
        illiq = np.where(qv > 0, np.abs(rv) / qv * 1e9, np.nan)
        out["S6_ILLIQ30"] = ("S", np.log(np.where(roll_mean(illiq, 30) > 0,
                                                  roll_mean(illiq, 30), np.nan)))

    # one day of lag: a book entered on day t may only use data through close of t-1
    return {k: (fam, shift(sig, 1)) for k, (fam, sig) in out.items()}
