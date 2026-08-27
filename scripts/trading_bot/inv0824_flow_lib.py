#!/usr/bin/env python3
"""INVENT 0824 -- theme: ON-CHAIN / SPOT-FLOW, with the published-tether + rho1 lens.

Data: cached free Binance spot daily klines (677 USDT pairs incl. delisted, 2017-08..2026-08,
with trade COUNT n and TAKER-BUY QUOTE volume tbq) + Binance cross-quote panels + Coinbase
Exchange daily close/quote-volume (91 products).  No network, no orders, no money.

Two P&L objects, deliberately disjoint from the killed rounds:
  XS  -- long top-10 / short bottom-10 of the top-50-ADV cross-section, VWAP->VWAP,
         overlapping tranches at holds 1/5/20.
  ROT -- BTC-vs-alt ROTATION: long the equal-weight top-50 alt index, short BTC, dollar
         neutral, sign-timed by an AGGREGATE (market-level) flow series.  This is a
         relative-value book, not a directional bet on crypto.

Signs are declared a priori from the mechanism (recorded in SIGN_RATIONALE), never fitted on
the design window, so the honest analytic bar is one-sided sqrt(2 ln N); the sign-agnostic
sqrt(2 ln 2N) is reported too and the operative bar is the size-matched placebo.
"""
from __future__ import annotations
import numpy as np, datetime as dt, sys

sys.path.insert(0, "/home/anont/meme/scripts/trading_bot")
from inv0822b_xs_lib import (  # noqa: E402
    CACHE, ANN, TOP, EXTREME, ADV_FLOOR, FEE_BP, HOLDS, STABLE_BASES,
    roll_mean, roll_sum_ok, roll_std, shift, load, features, universe,
    extremes_book, tranche, evaluate, sharpe, tstat, breakeven_bp, rho1,
)

# stablecoin bases whose *USDT pair volume is the "dry powder" aggregate
STABLE_DRY = ["USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "PAX", "USDS", "USD1",
              "USDE", "RLUSD", "SUSD", "PYUSD", "XUSD", "BFUSD"]


def zs(x, w):
    """Trailing z-score of a (S,T) panel over w days, using data through day t."""
    m = roll_mean(x, w)
    s = roll_std(x, w)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(s > 0, (x - m) / s, np.nan)


def flow_features(P, F):
    """Flow panels.  Every entry at column t uses information through the CLOSE of day t."""
    qv = F["qv"]; tbq = F["tbq"]; n = F["n"]
    G = {}
    with np.errstate(invalid="ignore", divide="ignore"):
        G["tbs"] = np.where(qv > 0, tbq / qv, np.nan)          # taker-buy share of $ volume
    G["netf"] = 2.0 * G["tbs"] - 1.0                            # net taker imbalance [-1,1]
    G["netd"] = np.where(np.isfinite(qv), (2.0 * tbq - qv), np.nan)   # net taker dollars
    G["adv20"] = roll_mean(qv, 20)
    with np.errstate(invalid="ignore", divide="ignore"):
        G["ticket"] = np.where((n > 0) & (qv > 0), np.log(qv / n), np.nan)
        G["amihud"] = np.where(qv > 0, np.abs(F["r_v"]) / qv * 1e9, np.nan)
        G["lamihud"] = np.log(np.where(G["amihud"] > 0, G["amihud"], np.nan))
        G["lqv"] = np.log(np.where(qv > 0, qv, np.nan))
        G["ln"] = np.log(np.where(n > 0, n, np.nan))
    return G


def roll_corr(a, b, w):
    ma, mb = roll_mean(a, w), roll_mean(b, w)
    va, vb = roll_std(a, w), roll_std(b, w)
    mab = roll_mean(a * b, w)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where((va > 0) & (vb > 0), (mab - ma * mb) / (va * vb), np.nan)


# ------------------------------------------------------------------ coinbase overlay
def coinbase_overlay(P, F):
    """Match Coinbase *-USD products to Binance *USDT pairs on the base symbol.

    Returns (cb_close, cb_qv) aligned to the Binance (S,T) grid, NaN where absent."""
    z = np.load(f"{CACHE}/coinbase_daily.npz", allow_pickle=False)
    cs = list(z["syms"]); cd = list(z["days"])
    cc = z["c"].astype(np.float64); cq = z["qv"].astype(np.float64)
    dpos = {int(d): j for j, d in enumerate(cd)}
    S, T = F["qv"].shape
    out_c = np.full((S, T), np.nan); out_q = np.full((S, T), np.nan)
    cbi = {str(s).split("-")[0]: i for i, s in enumerate(cs)}
    cols = np.array([dpos.get(int(d), -1) for d in P["days"]])
    have = cols >= 0
    for i, sym in enumerate(P["syms"]):
        if not sym.endswith("USDT"):
            continue
        b = sym[:-4]
        j = cbi.get(b)
        if j is None:
            continue
        out_c[i, have] = cc[j, cols[have]]
        out_q[i, have] = cq[j, cols[have]]
    out_c[~np.isfinite(out_c) | (out_c <= 0)] = np.nan
    out_q[~np.isfinite(out_q) | (out_q <= 0)] = np.nan
    return out_c, out_q


# ------------------------------------------------------------------ aggregates
def aggregates(P, F, G, U):
    """Market-level (1,T) flow series built from the tradable universe only."""
    syms = list(P["syms"])
    base = np.array([s[:-4] if s.endswith("USDT") else "" for s in syms])
    is_usdt = np.array([s.endswith("USDT") for s in syms])
    qv = np.where(np.isfinite(F["qv"]), F["qv"], 0.0)
    netd = np.where(np.isfinite(G["netd"]), G["netd"], 0.0)

    tot = qv[is_usdt].sum(0)
    stab = np.isin(base, STABLE_DRY) & is_usdt
    stab_qv = qv[stab].sum(0)
    A = {}
    with np.errstate(invalid="ignore", divide="ignore"):
        A["stab_share"] = np.where(tot > 0, stab_qv / tot, np.nan)
        A["stab_lqv"] = np.log(np.where(stab_qv > 0, stab_qv, np.nan))
        A["stab_netf"] = np.where(stab_qv > 0, netd[stab].sum(0) / stab_qv, np.nan)
    ib = syms.index("BTCUSDT")
    btc_qv = qv[ib]
    with np.errstate(invalid="ignore", divide="ignore"):
        A["btc_vdom"] = np.where(tot > 0, btc_qv / tot, np.nan)
        A["btc_netf"] = np.where(btc_qv > 0, netd[ib] / btc_qv, np.nan)

    # equal-weight alt index return + alt aggregate flow, from the day's universe
    Ualt = U.copy(); Ualt[ib] = False
    r = F["r_v"]
    S, T = U.shape
    alt_r = np.full(T, np.nan); alt_netf = np.full(T, np.nan); breadth = np.full(T, np.nan)
    for t in range(T):
        m = Ualt[:, t] & np.isfinite(r[:, t])
        if m.sum() >= 10:
            alt_r[t] = r[m, t].mean()
            breadth[t] = float((r[m, t] > r[ib, t]).mean()) if np.isfinite(r[ib, t]) else np.nan
        m2 = Ualt[:, t] & np.isfinite(G["netd"][:, t]) & (F["qv"][:, t] > 0)
        if m2.sum() >= 10:
            A_qv = F["qv"][m2, t].sum()
            alt_netf[t] = G["netd"][m2, t].sum() / A_qv if A_qv > 0 else np.nan
    A["alt_r"] = alt_r
    A["alt_netf"] = alt_netf
    A["breadth"] = breadth
    A["btc_r"] = r[ib]
    A["ib"] = ib
    return A


def zs1(x, w):
    return zs(np.asarray(x, float)[None, :], w)[0]


def rm1(x, w):
    return roll_mean(np.asarray(x, float)[None, :], w)[0]


def sh1(x, k):
    return shift(np.asarray(x, float)[None, :], k)[0]


# ------------------------------------------------------------------ ROT book
def rot_book(sig1d, U, ib, band=0.0):
    """Long EW alt index / short BTC, dollar neutral, scaled by sign(sig) (0 inside band).

    sig1d[t] must use information through the close of day t-1 (caller shifts)."""
    S, T = U.shape
    w = np.zeros((S, T))
    Ualt = U.copy(); Ualt[ib] = False
    s = np.asarray(sig1d, float)
    d = np.where(np.isfinite(s), np.sign(np.where(np.abs(s) > band, s, 0.0)), 0.0)
    for t in range(T):
        if d[t] == 0.0 or not U[ib, t]:
            continue
        m = np.where(Ualt[:, t])[0]
        if m.size < 10:
            continue
        w[m, t] = d[t] * 0.5 / m.size
        w[ib, t] = -d[t] * 0.5
    return w
