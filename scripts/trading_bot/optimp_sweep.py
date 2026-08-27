#!/usr/bin/env python3
"""NEWTERR-OPTIMP: options-IMPLIED surface as a SIGNAL to trade the UNDERLYING.

Territory: never swept by this programme. We do NOT buy options. We read free
Cboe implied-vol indices (each one is a model-free integral over a live listed
option chain) and use them to size a position in the underlying cash ETF.

Data (all free, all cached under research/data/optimp_cache):
  * 21 Cboe implied-vol / skew indices, daily, full history from cdn.cboe.com
  * Yahoo daily OHLC for the 15 underlyings those indices are written on

THE THREE GATES
  G0 MECHANISM  every formula carries a one-sentence causal WHY *and a
                PRE-SPECIFIED SIGN*. The sign is never read off the data.
  G1 LAG-KILL   headline is L=2 (signal from close t, enter at close t+1,
                earn ret t+2) because the Cboe indices print at 16:15 ET,
                AFTER the 16:00 cash close -- an L=1 backtest is not tradable.
                L=3 is the kill test.  L=1 is printed only as a staleness
                diagnostic: a formula that lives at L=1 and dies at L=2 was
                trading the 15-minute print gap.
  G2 STATS      design window only for selection; holdout untouched until the
                selection rule has run.  Costs charged on both legs, per-side,
                plus easy-to-borrow borrow fee on every short day.
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import sys

import numpy as np

CACHE = pathlib.Path("/home/anont/meme/research/data/optimp_cache")
OUT = pathlib.Path("/home/anont/meme/research/trading_bot")

# ---------------------------------------------------------------- costs
# Per-SIDE cost in bp of notional, charged on |change in weight|.  Anchored on
# M0_AUCTION_FILLS tier-A close-print half-spread (mean 1.34bp) plus a slippage
# pad; widened for the thinner underlyings.  Borrow in annual %, charged on
# every short day -- indicative easy-to-borrow ETF rates.
COST_BP = {
    "SPY": 1.5, "QQQ": 1.5, "IWM": 2.0, "DIA": 2.0, "EEM": 2.5, "EWZ": 4.0,
    "GLD": 2.0, "USO": 4.0, "SLV": 3.0, "TLT": 2.0, "FXI": 3.5, "GDX": 3.0,
    "XLE": 2.5, "EFA": 2.5, "AAPL": 2.0,
}
BORROW_PCT = {
    "SPY": 0.30, "QQQ": 0.30, "IWM": 0.50, "DIA": 0.50, "GLD": 0.40,
    "TLT": 0.50, "EEM": 0.60, "EFA": 0.60, "XLE": 0.75, "SLV": 1.00,
    "GDX": 1.00, "FXI": 1.50, "EWZ": 1.50, "USO": 2.00, "AAPL": 0.30,
}

DESIGN = ("2012-06-01", "2019-12-31")
HOLDOUT = ("2020-01-01", "2026-08-19")
W = 252  # trailing window for every causal z-score / percentile


# ---------------------------------------------------------------- loaders
def load_cboe(sym):
    rows = []
    with open(CACHE / f"cboe_{sym}.csv") as f:
        hdr = f.readline().strip().split(",")
        ci = len(hdr) - 1  # CLOSE is always last column (or the only value col)
        for line in f:
            p = line.strip().split(",")
            if len(p) != len(hdr):
                continue
            try:
                v = float(p[ci])
            except ValueError:
                continue
            if v <= 0:
                continue
            m, d, y = p[0].split("/")
            rows.append((f"{y}-{m}-{d}", v))
    rows.sort()
    return dict(rows)


def load_yahoo(sym):
    j = json.load(open(CACHE / f"yh_{sym}.json"))
    r = j["chart"]["result"][0]
    ts = r["timestamp"]
    adj = r["indicators"].get("adjclose")
    px = adj[0]["adjclose"] if adj else r["indicators"]["quote"][0]["close"]
    import datetime as dt
    out = {}
    for t, p in zip(ts, px):
        if p is None:
            continue
        d = dt.datetime.utcfromtimestamp(t + 3600 * 8).strftime("%Y-%m-%d")
        out[d] = float(p)
    return out


CBOE_SYMS = ["VIX", "VIX9D", "VIX3M", "VIX6M", "VVIX", "SKEW", "VXN", "RVX",
             "VXD", "OVX", "GVZ", "VXEEM", "VXEWZ", "VXSLV", "VXTLT",
             "VXAPL", "VXXLE", "VXFXI", "VXGDX", "VXEFA"]
ETF_SYMS = list(COST_BP)


def build_panel():
    iv = {s: load_cboe(s) for s in CBOE_SYMS}
    px = {s: load_yahoo(s) for s in ETF_SYMS}
    # calendar = dates where VIX and SPY both exist, from the last common start
    starts = [min(d) for d in iv.values()] + [min(d) for d in px.values()]
    start = max(max(starts), "2011-03-16")
    dates = sorted(set(iv["VIX"]) & set(px["SPY"]))
    dates = [d for d in dates if d >= start]
    n = len(dates)
    IV = {}
    for s, d in iv.items():
        a = np.full(n, np.nan)
        for i, dt_ in enumerate(dates):
            if dt_ in d:
                a[i] = d[dt_]
        IV[s] = ffill(a)
    PX = {}
    for s, d in px.items():
        a = np.full(n, np.nan)
        for i, dt_ in enumerate(dates):
            if dt_ in d:
                a[i] = d[dt_]
        PX[s] = ffill(a)
    return dates, IV, PX


def ffill(a):
    out = a.copy()
    last = np.nan
    for i in range(len(out)):
        if np.isnan(out[i]):
            out[i] = last
        else:
            last = out[i]
    return out


# ---------------------------------------------------------------- primitives
def roll_mean(x, w):
    c = np.concatenate([[0.0], np.nancumsum(np.nan_to_num(x))])
    k = np.concatenate([[0.0], np.cumsum(~np.isnan(x))])
    out = np.full(len(x), np.nan)
    for i in range(w - 1, len(x)):
        cnt = k[i + 1] - k[i + 1 - w]
        if cnt >= w * 0.8:
            out[i] = (c[i + 1] - c[i + 1 - w]) / cnt
    return out


def roll_std(x, w):
    m = roll_mean(x, w)
    m2 = roll_mean(x * x, w)
    v = m2 - m * m
    return np.sqrt(np.maximum(v, 1e-12))


def zc(x, w=W):
    """Causal z-score using the trailing w observations INCLUDING today."""
    return (x - roll_mean(x, w)) / roll_std(x, w)


def pctc(x, w=W):
    """Causal percentile rank of today within trailing w, mapped to [-1,1]."""
    out = np.full(len(x), np.nan)
    for i in range(w - 1, len(x)):
        win = x[i + 1 - w:i + 1]
        if np.isnan(win).sum() > w * 0.2 or np.isnan(x[i]):
            continue
        out[i] = 2.0 * (np.nanmean(win <= x[i])) - 1.0
    return out


def d(x, k):
    out = np.full(len(x), np.nan)
    out[k:] = x[k:] - x[:-k]
    return out


def rv(px, w):
    """Annualised realised vol in VIX units (percent)."""
    lr = np.full(len(px), np.nan)
    lr[1:] = np.log(px[1:] / px[:-1])
    return roll_std(lr, w) * math.sqrt(252) * 100.0


def resid_on(y, x, w=W):
    """Causal rolling OLS residual of y on x (with intercept)."""
    out = np.full(len(y), np.nan)
    for i in range(w - 1, len(y)):
        yy = y[i + 1 - w:i + 1]
        xx = x[i + 1 - w:i + 1]
        m = ~(np.isnan(yy) | np.isnan(xx))
        if m.sum() < w * 0.8:
            continue
        A = np.vstack([xx[m], np.ones(m.sum())]).T
        b, *_ = np.linalg.lstsq(A, yy[m], rcond=None)
        out[i] = y[i] - (b[0] * x[i] + b[1])
    return out


def wclip(z):
    """z-score -> weight in [-1, 1]."""
    return np.clip(z, -2.0, 2.0) / 2.0


# ---------------------------------------------------------------- evaluation
def evaluate(weights, rets, syms, lag, mask):
    """weights: dict sym -> array of target weight (signal known at close t).
    Return net daily pnl array with entry lag `lag` (position taken at close
    t+lag-1, earns ret[t+lag])."""
    n = len(mask)
    pnl = np.zeros(n)
    for s in syms:
        w = np.nan_to_num(weights[s])
        # position that earns ret[t+lag] was established at close t+lag-1
        pos = np.zeros(n)
        pos[lag:] = w[:n - lag]
        gross = pos * np.nan_to_num(rets[s])
        turn = np.abs(np.diff(pos, prepend=0.0))
        cost = turn * COST_BP[s] * 1e-4
        borrow = np.maximum(-pos, 0.0) * BORROW_PCT[s] / 100.0 / 252.0
        pnl += gross - cost - borrow
    return pnl * mask


def stats(pnl, mask):
    x = pnl[mask.astype(bool)]
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 100 or x.std() == 0:
        return dict(n=n, sharpe=0.0, t=0.0, ann_ret=0.0)
    sh = x.mean() / x.std() * math.sqrt(252)
    yrs = n / 252.0
    return dict(n=n, sharpe=float(sh), t=float(sh * math.sqrt(yrs)),
                ann_ret=float(x.mean() * 252), hit=float((x > 0).mean()),
                maxdd=float(maxdd(np.cumsum(x))))


def maxdd(eq):
    peak = np.maximum.accumulate(eq)
    return float((eq - peak).min())


# ---------------------------------------------------------------- formulas
def build_formulas(dates, IV, PX):
    n = len(dates)
    rets = {}
    for s in ETF_SYMS:
        r = np.full(n, np.nan)
        r[1:] = PX[s][1:] / PX[s][:-1] - 1.0
        rets[s] = r
    RV20 = {s: rv(PX[s], 20) for s in ETF_SYMS}
    RV5 = {s: rv(PX[s], 5) for s in ETF_SYMS}

    V = IV
    F = []  # (name, family, mech, sign, {sym: signal z}, note)

    def add(name, fam, mech, sign, sig_by_sym):
        F.append(dict(name=name, family=fam, mech=mech, sign=sign,
                      sig=sig_by_sym))

    S = "SPY"
    # ---- A. implied-vol TERM STRUCTURE of the SAME underlying (SPX chain)
    add("A1_TS9_level", "termstruct",
        "Short-dated SPX put demand spikes VIX9D above VIX; once that protection "
        "is bought and paid for, dealers are long downside gamma and buy dips, "
        "so the forced-selling channel is closed and spot drifts up.",
        +1, {S: zc(V["VIX9D"] / V["VIX"])})
    add("A2_TS3_level", "termstruct",
        "Backwardation of VIX vs VIX3M means the whole hedging book has rolled "
        "into the front; the marginal hedger has already transacted.",
        +1, {S: zc(V["VIX"] / V["VIX3M"])})
    add("A3_TS6_level", "termstruct",
        "Same mechanism one tenor out: 3M rich to 6M means intermediate hedges "
        "are already on.",
        +1, {S: zc(V["VIX3M"] / V["VIX6M"])})
    add("A4_TS3_chg5", "termstruct",
        "A curve STEEPENING INTO BACKWARDATION over a week is hedging in "
        "progress, not hedging done: dealers short the new puts must sell spot "
        "to delta-hedge while the flow is live.",
        -1, {S: zc(d(V["VIX"] / V["VIX3M"], 5))})
    add("A5_TS_fly", "termstruct",
        "A kink at the front (9D-2*VIX+3M) is event-dated protection concentrated "
        "in one expiry -- the most mechanical form of 'already hedged'.",
        +1, {S: zc(V["VIX9D"] - 2 * V["VIX"] + V["VIX3M"])})
    add("A6_TS9_chg5", "termstruct",
        "Front-end steepening in progress: same live-flow mechanism as A4 at the "
        "9-day tenor.",
        -1, {S: zc(d(V["VIX9D"] / V["VIX"], 5))})

    # ---- B. VARIANCE RISK PREMIUM (implied vs realised, same underlying)
    add("B1_VRP20", "vrp",
        "VIX minus 20d realised is the fee variance sellers collect; when the fee "
        "is fat those sellers are solvent and keep supplying gamma, damping "
        "downside.",
        +1, {S: zc(V["VIX"] - RV20[S])})
    add("B2_VRP5", "vrp",
        "Same premium at the one-week tenor where the option supply is thinnest.",
        +1, {S: zc(V["VIX9D"] - RV5[S])})
    add("B3_VRP_ratio", "vrp",
        "Scale-free version of B1: a ratio does not confound the premium with the "
        "vol level.",
        +1, {S: zc(V["VIX"] / np.maximum(RV20[S], 1e-6))})
    add("B4_VRP_chg5", "vrp",
        "A COLLAPSING premium is realised catching implied -- vol sellers are "
        "being run over and must buy back gamma, which means selling spot.",
        -1, {S: zc(d(V["VIX"] - RV20[S], 5))})
    add("B5_IVrank", "vrp",
        "High IV percentile is capitulation pricing: protection has been bought "
        "at the top of its own year, so the incremental hedger is exhausted.",
        +1, {S: pctc(V["VIX"])})
    add("B6_RVrank_less_IVrank", "vrp",
        "Realised sitting high in its own distribution while implied does not is "
        "an UNDER-hedged tape -- the hedging still has to happen.",
        -1, {S: zc(pctc(RV20[S]) - pctc(V["VIX"]))})

    # ---- C. SKEW / tail price
    add("C1_SKEW_level", "skew",
        "Cboe SKEW is the price of the left tail; a rich tail means crash "
        "insurance is already owned, so a shock produces less forced de-risking.",
        +1, {S: zc(V["SKEW"])})
    add("C2_SKEW_chg5", "skew",
        "Tail price RISING is the purchase happening now; the dealer short those "
        "puts sells spot to hedge while it happens.",
        -1, {S: zc(d(V["SKEW"], 5))})
    add("C3_SKEW_resid", "skew",
        "SKEW orthogonalised to VIX isolates tail demand from level demand -- the "
        "same 'already hedged' mechanism with the level confound removed.",
        +1, {S: zc(resid_on(V["SKEW"], V["VIX"]))})
    add("C4_SKEW_vs_VIX_z", "skew",
        "Tail rich relative to the level: put wing bid without an ATM bid is "
        "pure tail-hedging demand.",
        +1, {S: zc(V["SKEW"]) - zc(V["VIX"])})

    # ---- D. VOL-OF-VOL / convexity demand
    add("D1_VVIX_over_VIX", "volofvol",
        "VVIX/VIX is the price of convexity: buying VIX calls forces the dealer "
        "short them to buy VIX futures, which is a synthetic equity sale. Rich "
        "convexity means that sale has already been made.",
        +1, {S: zc(V["VVIX"] / V["VIX"])})
    add("D2_VVIX_over_VIX_chg5", "volofvol",
        "Convexity being bid RIGHT NOW is the hedge in flight.",
        -1, {S: zc(d(V["VVIX"] / V["VIX"], 5))})
    add("D3_VVIX_level", "volofvol",
        "Absolute vol-of-vol: crowding in VIX upside.",
        +1, {S: zc(V["VVIX"])})

    # ---- E. DEALER GAMMA SIGN conditioning spot autocorrelation
    #     (proxy: curve shape as a stand-in for the sign of dealer gamma)
    def gamma_cond(gsign_arr, sym):
        rr = rets[sym] / np.maximum(RV20[sym] / 100.0 / math.sqrt(252), 1e-6)
        return np.tanh(np.nan_to_num(rr) / 2.0) * -gsign_arr

    g_ts3 = np.sign(np.nan_to_num(V["VIX3M"] - V["VIX"]))
    g_ts9 = np.sign(np.nan_to_num(V["VIX"] - V["VIX9D"]))
    g_vvx = -np.sign(np.nan_to_num(zc(V["VVIX"] / V["VIX"])))
    add("E1_gamma_sign_TS3", "gammasign",
        "Contango (VIX3M>VIX) is the regime in which dealers are net LONG index "
        "gamma and hedge by trading against the move, so daily returns "
        "mean-revert; backwardation flips the sign and returns trend.",
        +1, {S: gamma_cond(g_ts3, S)})
    add("E2_gamma_sign_TS9", "gammasign",
        "Same gamma-sign switch read at the 9-day tenor, where the gamma "
        "actually lives.",
        +1, {S: gamma_cond(g_ts9, S)})
    add("E3_gamma_sign_VVIX", "gammasign",
        "Vol-of-vol as the gamma-sign proxy: high VVIX/VIX is the short-gamma "
        "regime.",
        +1, {S: gamma_cond(g_vvx, S)})
    add("E4_CONTROL_uncond_reversal", "control",
        "NO options information -- unconditional 1-day reversal. Control: if the "
        "gamma-sign formulas do not beat this, the options surface added nothing.",
        +1, {S: gamma_cond(np.ones(n), S)})

    # ---- F. RELATIVE IMPLIED VOL: an asset's OWN chain vs the index chain
    RELPAIRS = [
        ("QQQ", "VXN", "VIX"), ("IWM", "RVX", "VIX"), ("DIA", "VXD", "VIX"),
        ("EEM", "VXEEM", "VIX"), ("EWZ", "VXEWZ", "VIX"),
        ("USO", "OVX", "VIX"), ("GLD", "GVZ", "VIX"),
        ("SLV", "VXSLV", "GVZ"), ("TLT", "VXTLT", "VIX"),
        ("FXI", "VXFXI", "VIX"), ("GDX", "VXGDX", "GVZ"),
        ("XLE", "VXXLE", "VIX"), ("EFA", "VXEFA", "VIX"),
        ("AAPL", "VXAPL", "VXN"),
    ]
    for sym, own, base in RELPAIRS:
        add(f"F_RELIV_{sym}", "reliv",
            f"When {sym}'s own listed chain ({own}) is expensive relative to the "
            f"benchmark chain ({base}), the hedgers who care about {sym} "
            "specifically have already paid up; the dealer facing them is long "
            f"{sym} gamma and buys {sym} dips.",
            +1, {sym: zc(V[own] / V[base])})

    # ---- G. own-chain VRP per asset (implied vs that asset's realised)
    for sym, own, _ in RELPAIRS:
        add(f"G_OWNVRP_{sym}", "ownvrp",
            f"{sym}'s own variance risk premium: {own} minus {sym}'s realised "
            "vol is the fee its own vol sellers collect, and a fat fee keeps them "
            "supplying gamma in that name.",
            +1, {sym: zc(V[own] - RV20[sym])})

    # ---- H. CROSS-SECTIONAL long/short across the 14 chains (a true RV book)
    XS_UNIV = [p[0] for p in RELPAIRS]

    def xs_book(score_by_sym, sign):
        M = np.vstack([np.nan_to_num(score_by_sym[s], nan=0.0) for s in XS_UNIV])
        valid = np.vstack([~np.isnan(score_by_sym[s]) for s in XS_UNIV])
        out = {}
        Wt = np.zeros_like(M)
        for t in range(M.shape[1]):
            m = valid[:, t]
            if m.sum() < 6:
                continue
            v = M[m, t]
            r = np.argsort(np.argsort(v)).astype(float)
            r = 2.0 * r / (len(v) - 1) - 1.0  # -1..1 cross-sectional rank
            r = r - r.mean()
            r = r / np.abs(r).sum() * 1.0  # gross = 1.0 total
            Wt[m, t] = sign * r
        for i, s in enumerate(XS_UNIV):
            out[s] = Wt[i]
        return out

    ownvrp = {s: zc(V[o] - RV20[s]) for s, o, _ in RELPAIRS}
    reliv = {s: zc(V[o] / V[b]) for s, o, b in RELPAIRS}
    ivmom = {s: zc(d(np.log(V[o]), 5)) for s, o, _ in RELPAIRS}
    ivrank = {s: pctc(V[o]) for s, o, _ in RELPAIRS}
    ivmom20 = {s: zc(d(np.log(V[o]), 20)) for s, o, _ in RELPAIRS}
    skew_like = {s: zc(V[o] / np.maximum(RV5[s], 1e-6)) for s, o, _ in RELPAIRS}

    add("H1_XS_ownVRP", "crosssec",
        "Cross-section of the SAME mechanism as G: long the chains paying the "
        "fattest variance premium, short the thinnest. Market-neutral by "
        "construction, so it isolates the option-chain signal from beta.",
        +1, xs_book(ownvrp, +1))
    add("H2_XS_RELIV", "crosssec",
        "Cross-section of F: long the names whose own protection is richest vs "
        "their benchmark chain.",
        +1, xs_book(reliv, +1))
    add("H3_XS_IVmom5", "crosssec",
        "Long the chains where implied vol is FALLING, short where it is rising: "
        "a rising own-IV is protection being bought now and the dealer hedging "
        "that purchase sells the underlying.",
        +1, xs_book(ivmom, -1))
    add("H4_XS_IVrank", "crosssec",
        "Long the chains at the top of their own IV percentile (hedging "
        "exhausted), short those at the bottom (hedging still to come).",
        +1, xs_book(ivrank, +1))
    add("H5_XS_IVmom20", "crosssec",
        "One-month version of H3: slower protection-buying flow.",
        +1, xs_book(ivmom20, -1))
    add("H6_XS_IVoverRV5", "crosssec",
        "Own implied over own SHORT realised: the most acute form of 'insurance "
        "is expensive relative to what is actually happening'.",
        +1, xs_book(skew_like, +1))

    # ---- I. IMPLIED CORRELATION (index chain vs component chains)
    comp = 0.45 * V["VXN"] ** 2 + 0.35 * V["VXD"] ** 2 + 0.20 * V["RVX"] ** 2
    icorr = V["VIX"] ** 2 / np.maximum(comp, 1e-9)
    add("I1_impcorr_level", "dispersion",
        "Index vol rich to component vol is implied correlation: it is the "
        "signature of MACRO hedging done with index puts, i.e. protection bought "
        "at the index level rather than name by name.",
        +1, {S: zc(icorr)})
    add("I2_impcorr_chg5", "dispersion",
        "Implied correlation RISING is the macro hedge being put on now; the "
        "dealer delta-hedges it by selling index futures.",
        -1, {S: zc(d(icorr, 5))})
    add("I3_impcorr_resid", "dispersion",
        "Implied correlation orthogonalised to VIX: correlation demand stripped "
        "of the vol level.",
        +1, {S: zc(resid_on(icorr, V["VIX"]))})

    return F, rets, XS_UNIV


# ---------------------------------------------------------------- main
def main():
    dates, IV, PX = build_panel()
    n = len(dates)
    print(f"panel {n} rows {dates[0]} .. {dates[-1]}", file=sys.stderr)
    F, rets, XS_UNIV = build_formulas(dates, IV, PX)
    dt = np.array(dates)
    des = ((dt >= DESIGN[0]) & (dt <= DESIGN[1])).astype(float)
    hol = ((dt >= HOLDOUT[0]) & (dt <= HOLDOUT[1])).astype(float)

    def tail(z, thr=1.5):
        """Second, structurally different response: act only in the tails.
        A linear z-weight and a tail-threshold weight are different bets on
        WHERE in the distribution the mechanism bites, so both are swept and
        both are counted in N."""
        w = np.zeros_like(z)
        w[z > thr] = 1.0
        w[z < -thr] = -1.0
        w[np.isnan(z)] = 0.0
        return w

    variants = []
    for f in F:
        variants.append((f, "lin"))
        if f["family"] != "crosssec":
            variants.append((f, "tail"))

    results = []
    for f, resp in variants:
        syms = list(f["sig"])
        if f["family"] == "crosssec":
            wts = {s: f["sign"] * np.nan_to_num(f["sig"][s]) for s in syms}
        elif resp == "tail":
            wts = {s: f["sign"] * tail(f["sig"][s]) for s in syms}
        else:
            wts = {s: f["sign"] * wclip(f["sig"][s]) for s in syms}
        nm = f["name"] if resp == "lin" else f["name"] + "~tail"
        row = dict(name=nm, family=f["family"], response=resp, mech=f["mech"],
                   sign=f["sign"], syms=syms)
        for lag in (1, 2, 3):
            p = evaluate(wts, rets, syms, lag, np.ones(n))
            row[f"design_L{lag}"] = stats(p, des)
            row[f"holdout_L{lag}"] = stats(p, hol)
            if lag == 2:
                row["_pnl"] = p
        results.append(row)

    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(CACHE / "pnl_L2.npz",
                        **{r["name"]: r.pop("_pnl") for r in results},
                        dates=dt)
    json.dump(results, open(OUT / "NEWTERR_optimp_raw.json", "w"), indent=1)

    N = len(results)
    bar = math.sqrt(2 * math.log(N))
    print(f"\nN={N}  expected max |t| under null = {bar:.2f} SE\n")
    reveal = bool(os.environ.get("REVEAL_HOLDOUT"))
    print(f"{'formula':28s} {'fam':11s} {'dL1':>6s} {'dL2':>6s} {'dL3':>6s} "
          f"{'d_t2':>6s} {'PASS':>5s}" + (f" {'hL2':>6s} {'h_t2':>6s}" if reveal else ""))
    for r in sorted(results, key=lambda x: -x["design_L2"]["t"]):
        d1, d2, d3 = (r[f"design_L{k}"]["sharpe"] for k in (1, 2, 3))
        ok = (r["design_L2"]["t"] >= bar and d3 >= 0.5 * d2
              and r["design_L3"]["t"] > 0 and d1 <= 2.0 * d2 and d2 > 0)
        r["passes_design_gates"] = bool(ok)
        line = (f"{r['name']:28s} {r['family']:11s} {d1:6.2f} {d2:6.2f} "
                f"{d3:6.2f} {r['design_L2']['t']:6.2f} {'YES' if ok else '.':>5s}")
        if reveal:
            line += f" {r['holdout_L2']['sharpe']:6.2f} {r['holdout_L2']['t']:6.2f}"
        print(line)
    json.dump(results, open(OUT / "NEWTERR_optimp_raw.json", "w"), indent=1)


if __name__ == "__main__":
    main()
