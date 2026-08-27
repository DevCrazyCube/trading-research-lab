#!/usr/bin/env python3
"""
INVENT 0822 -- THEME: LOW-TURNOVER, sleeve B.
Bond/equity allocation drift, term-structure harvesting, and DURATION-TETHERED
relative value on a WEEKLY clock.

Why this sleeve exists. DEEPMINE_etf_structural_rv killed 51 ETF-RV formulas and said
so explicitly: "This family does not need better execution. It needs a different
business." -- 45 of 51 lost money at a LITERALLY ZERO spread because of turnover alone.
The different business is a slower clock on a claim whose tether is a *curve*, not a
share-count. Two Treasury ETFs of the same maturity bucket, a duration-neutral
2s10s30s butterfly, and a TIPS-vs-nominal breakeven are all claims on the SAME
discount curve; the tether is arbitrage in the underlying bonds, and it is economic,
not statistical.

Every RV candidate must clear the rho1(ds) > -0.35 gate (OU_MEAN_REVERSION lesson 4)
in ADDITION to Hurst < 0.5 and an ADF rejection, or the "reversion" is bid-ask bounce.

Data: research/data/ratescredit_cache/etf_daily.json (adjusted closes, total return).
Design 2002-07-30..2016-12-31 ; held-out 2017-01-03..2026-08-14 (declared before any
number was computed; sleeve-A's 2016/2022 split is not usable here because these
series start in 2002 and a 2016 cut would waste 14 years of design data).

Usage: python3 invent0822_slow_ts.py design|holdout|all
"""
import json, os, sys, math
import numpy as np

DATA = "/home/anont/meme/research/data/ratescredit_cache"
RES = "/home/anont/meme/research/trading_bot"

DESIGN = ("2002-07-30", "2016-12-31")
HOLDOUT = ("2017-01-03", "2026-08-14")
HS = 3.0e-4        # 3 bp one-way half-spread, bond/equity ETFs (conservative for TLT/IEF/HYG)
HS_STRESS = 5.0e-4
FEE = 0.5e-4
HOLD = 5           # weekly clock: 5 overlapping daily sub-books
ZWIN = 250
ZCAP = 2.0

# approximate effective durations (yrs) -- used only to build duration-neutral legs.
DUR = dict(SHY=1.9, VGSH=1.9, SCHO=1.9, IEI=4.5, IEF=7.4, VGIT=5.3, TLH=12.5, TLT=16.5,
           VGLT=15.5, SPTL=15.8, ZROZ=25.5, EDV=24.0, TIP=6.7, SCHP=6.9, LQD=8.4,
           VCIT=6.3, IGIB=6.4, HYG=3.2, JNK=3.3, AGG=6.0, BND=6.0, GOVT=5.8)


# ------------------------------------------------------------------ data
def load():
    d = json.load(open(os.path.join(DATA, "etf_daily.json")))
    import datetime as dt
    ser = {}
    for k, v in d.items():
        ts = np.asarray(v["t"], dtype=np.int64)
        px = np.asarray(v["adjclose"], dtype=np.float64)
        ds = np.array([dt.datetime.utcfromtimestamp(int(x)).strftime("%Y-%m-%d") for x in ts])
        ok = np.isfinite(px) & (px > 0)
        ser[k] = (ds[ok], px[ok])
    # union calendar from SPY
    dates = ser["SPY"][0]
    dates = dates[(dates >= "2002-07-30")]
    idx = {x: i for i, x in enumerate(dates)}
    P = {}
    for k, (ds, px) in ser.items():
        a = np.full(len(dates), np.nan)
        for x, p in zip(ds, px):
            i = idx.get(x)
            if i is not None:
                a[i] = p
        P[k] = a
    return dates, P


def rets(p):
    r = np.full(len(p), np.nan)
    r[1:] = p[1:] / p[:-1] - 1.0
    return r


# ------------------------------------------------------------------ stats
def sharpe_t(x):
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 200:
        return dict(n=int(n), sharpe=0.0, t=0.0, mean_bps=0.0)
    mu, sd = float(x.mean()), float(x.std(ddof=1))
    if sd <= 0:
        return dict(n=int(n), sharpe=0.0, t=0.0, mean_bps=0.0)
    return dict(n=int(n), sharpe=mu / sd * math.sqrt(252), t=mu / sd * math.sqrt(n),
                mean_bps=mu * 1e4)


def nw_t(x, lags=HOLD):
    """Newey-West t: a `HOLD`-day overlapping book has built-in autocorrelation, so the
    naive t is mechanically inflated."""
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 200:
        return 0.0
    e = x - x.mean()
    s = float(e @ e) / n
    for L in range(1, min(lags, n - 1) + 1):
        s += 2.0 * (1.0 - L / (lags + 1.0)) * float(e[L:] @ e[:-L]) / n
    return float(x.mean() / math.sqrt(s / n)) if s > 0 else 0.0


def hurst(level):
    """R/S Hurst of the spread. R/S is an INCREMENT-process estimator, so it is fed the
    first differences of the level: H<0.5 == anti-persistent increments == mean reverting,
    H==0.5 == random walk. (Feeding it the level itself returns ~1.0 for everything.)"""
    x = np.diff(level[np.isfinite(level)])
    x = x[np.isfinite(x)]
    if len(x) < 256:
        return float("nan")
    out_n, out_rs = [], []
    for w in (16, 32, 64, 128, 256):
        k = len(x) // w
        if k < 4:
            break
        rs = []
        for j in range(k):
            seg = x[j * w:(j + 1) * w]
            y = seg - seg.mean()
            z = np.cumsum(y)
            R = z.max() - z.min()
            S = seg.std(ddof=1)
            if S > 0:
                rs.append(R / S)
        if rs:
            out_n.append(math.log(w)); out_rs.append(math.log(float(np.mean(rs))))
    if len(out_n) < 3:
        return float("nan")
    A = np.vstack([np.ones(len(out_n)), np.array(out_n)]).T
    b, *_ = np.linalg.lstsq(A, np.array(out_rs), rcond=None)
    return float(b[1])


def adf_t(s, lags=1):
    s = s[np.isfinite(s)]
    if len(s) < 100:
        return float("nan")
    ds = np.diff(s)
    y = ds[lags:]
    X = [np.ones(len(y)), s[lags:-1]]
    for L in range(1, lags + 1):
        X.append(ds[lags - L:-L])
    X = np.vstack(X).T
    b, res, rank, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ b
    dof = len(y) - X.shape[1]
    s2 = float(resid @ resid) / dof
    XtXi = np.linalg.pinv(X.T @ X)
    se = math.sqrt(max(s2 * XtXi[1, 1], 1e-30))
    return float(b[1] / se)


def rho1_dspread(s):
    s = s[np.isfinite(s)]
    ds = np.diff(s)
    ds = ds[np.isfinite(ds)]
    if len(ds) < 50:
        return float("nan")
    a, b = ds[:-1], ds[1:]
    a = a - a.mean(); b = b - b.mean()
    den = math.sqrt(float(a @ a) * float(b @ b))
    return float((a @ b) / den) if den > 0 else float("nan")


def ou_halflife(s):
    s = s[np.isfinite(s)]
    if len(s) < 100:
        return float("nan")
    x, y = s[:-1], s[1:]
    A = np.vstack([np.ones(len(x)), x]).T
    b, *_ = np.linalg.lstsq(A, y, rcond=None)
    phi = float(b[1])
    if not (0 < phi < 1):
        return float("nan")
    return math.log(2) / (-math.log(phi))


def roll(x, w, fn):
    out = np.full(len(x), np.nan)
    for i in range(w - 1, len(x)):
        seg = x[i - w + 1:i + 1]
        if np.isfinite(seg).sum() >= w * 0.8:
            out[i] = fn(seg[np.isfinite(seg)])
    return out


def rmean(x, w):
    m = np.isfinite(x).astype(float)
    xf = np.where(np.isfinite(x), x, 0.0)
    cs = np.concatenate([[0.0], np.cumsum(xf)])
    cn = np.concatenate([[0.0], np.cumsum(m)])
    out = np.full(len(x), np.nan)
    s = cs[w:] - cs[:-w]; n = cn[w:] - cn[:-w]
    v = np.where(n >= w * 0.8, s / np.maximum(n, 1), np.nan)
    out[w - 1:] = v
    return out


def rstd(x, w):
    m1 = rmean(x, w); m2 = rmean(x * x, w)
    return np.sqrt(np.maximum(m2 - m1 * m1, 0.0))


# ------------------------------------------------------------------ books
def book_from_weights(w, r, hold=HOLD, hs=HS):
    """w[t] is the TARGET weight vector decided using data through t; it is entered at
    t+1 and held `hold` days as one of `hold` overlapping sub-books."""
    T, K = w.shape
    b = np.zeros((T, K))
    for k in range(hold):
        s = 1 + k
        b[s:] += w[:T - s]
    b /= hold
    prev = np.zeros_like(b); prev[1:] = b[:-1]
    dw = np.abs(b - prev)
    rr = np.where(np.isfinite(r), r, 0.0)
    gross = (b * rr).sum(axis=1)
    turn = dw.sum(axis=1)
    cost = turn * (hs + FEE)
    cost5 = turn * (HS_STRESS + FEE)
    return gross, cost, cost5, turn


def zpos(spread):
    mu = rmean(spread, ZWIN); sd = rstd(spread, ZWIN)
    z = (spread - mu) / np.maximum(sd, 1e-9)
    return -np.clip(z, -ZCAP, ZCAP) / ZCAP     # long the cheap leg, unit max gross


# ------------------------------------------------------------------ candidates
RESULTS = []


def add(name, family, mech, gross, cost, cost5, turn, mask_d, mask_h, diag=None, note=""):
    for tag, m in (("design", mask_d), ("holdout", mask_h)):
        g = sharpe_t(gross[m]); n = sharpe_t((gross - cost)[m]); n5 = sharpe_t((gross - cost5)[m])
        gm = float(np.nanmean(gross[m])); tm = float(np.nanmean(turn[m]))
        row = dict(name=name, family=family, mechanism=mech, window=tag,
                   gross_sharpe=g["sharpe"], gross_t=g["t"], gross_bps=g["mean_bps"],
                   gross_t_nw=nw_t(gross[m]), net_t_nw=nw_t((gross - cost)[m]),
                   net_sharpe=n["sharpe"], net_t=n["t"], net_bps=n["mean_bps"],
                   net_sharpe_5bp=n5["sharpe"], turnover_per_day=tm,
                   breakeven_cost_bps=(gm / tm * 1e4) if tm > 0 else 0.0,
                   cost_share_of_gross=(float(np.nanmean(cost[m])) / gm) if gm > 0 else float("nan"),
                   n=g["n"], note=note)
        if diag:
            row.update(diag)
        RESULTS.append(row)


def _diag(s, m):
    sd = s[m]
    sd = sd[np.isfinite(sd)]
    r1, hu, af = rho1_dspread(sd), hurst(sd), adf_t(sd)
    return dict(rho1_dspread=r1, hurst=hu, adf_t=af, halflife_d=ou_halflife(sd),
                gate_pass=bool((r1 > -0.35) and (hu < 0.5) and (af < -2.86)))


def rv_pair(name, A, B, P, dates, md, mh, hedge="dur", mech=""):
    if A not in P or B not in P:
        print(f"  skip {name}: missing series"); return
    a, b = P[A], P[B]
    k = DUR[A] / DUR[B] if hedge == "dur" else 1.0
    s = np.log(a) - k * np.log(b)
    ra, rb = rets(a), rets(b)
    w = zpos(s)
    W = np.vstack([w, -k * w]).T
    R = np.vstack([ra, rb]).T
    g, c, c5, t = book_from_weights(W, R)
    dd = _diag(s, md); dh = _diag(s, mh)
    diag = dict(hedge_ratio=k, **dd)
    diag.update({f"ho_{q}": v for q, v in dh.items()})
    add(name, "rv_tether", mech, g, c, c5, t, md, mh, diag=diag, note=f"{A}/{B}")


def rv_butterfly(name, A, Bel, C, P, md, mh, mech=""):
    """Duration-neutral 3-leg curvature trade: long the belly Bel against a
    duration-matched barbell of the wings A (short) and C (long)."""
    for k in (A, Bel, C):
        if k not in P:
            print(f"  skip {name}: missing {k}"); return
    dA, dB, dC = DUR[A], DUR[Bel], DUR[C]
    # wing weights wa, wc with wa*dA + wc*dC = dB and wa*dA == wc*dC (equal duration halves)
    wa = 0.5 * dB / dA
    wc = 0.5 * dB / dC
    s = np.log(P[Bel]) - wa * np.log(P[A]) - wc * np.log(P[C])
    w = zpos(s)
    W = np.vstack([w, -wa * w, -wc * w]).T
    R = np.vstack([rets(P[Bel]), rets(P[A]), rets(P[C])]).T
    g, c, c5, t = book_from_weights(W, R)
    dd = _diag(s, md); dh = _diag(s, mh)
    diag = dict(hedge_ratio=float(wa), **dd)
    diag.update({f"ho_{q}": v for q, v in dh.items()})
    add(name, "rv_tether", mech, g, c, c5, t, md, mh, diag=diag, note=f"{Bel} vs {A}+{C}")


def rebal_premium(name, legs, P, md, mh, mech="", vol_weight=False, drift_reset=252):
    """Monthly-rebalanced portfolio MINUS the same portfolio left to drift.
    The difference IS the rebalancing (diversification) return -- a structural
    consequence of relative-price mean reversion, not a forecast."""
    R = np.vstack([rets(P[k]) for k in legs]).T
    T, K = R.shape
    if vol_weight:
        iv = np.vstack([1.0 / np.maximum(rstd(rets(P[k]), 60), 1e-6) for k in legs]).T
        tgt = iv / np.nansum(iv, axis=1, keepdims=True)
    else:
        base = np.array([0.6, 0.4] if K == 2 else [1.0 / K] * K)
        tgt = np.broadcast_to(base, (T, K)).copy()
    Rf = np.where(np.isfinite(R), R, 0.0)
    # rebalanced: reset to target every 21 days
    wr = np.full((T, K), np.nan)
    wd = np.full((T, K), np.nan)
    cur_r = None; cur_d = None
    ret_r = np.full(T, np.nan); ret_d = np.full(T, np.nan)
    turn_r = np.zeros(T); turn_d = np.zeros(T)
    for t in range(T):
        if not np.isfinite(tgt[t]).all():
            continue
        if cur_r is None:
            cur_r = tgt[t].copy(); cur_d = tgt[t].copy()
            continue
        ret_r[t] = float(cur_r @ Rf[t]); ret_d[t] = float(cur_d @ Rf[t])
        gr = cur_r * (1 + Rf[t]); gr = gr / gr.sum()
        gd = cur_d * (1 + Rf[t]); gd = gd / gd.sum()
        cur_r, cur_d = gr, gd
        if t % 21 == 0:
            turn_r[t] = float(np.abs(tgt[t] - cur_r).sum())
            cur_r = tgt[t].copy()
        if t % drift_reset == 0:
            turn_d[t] = float(np.abs(tgt[t] - cur_d).sum())
            cur_d = tgt[t].copy()
    diff = ret_r - ret_d
    turn = turn_r - turn_d
    cost = np.maximum(turn, 0) * (HS + FEE)
    cost5 = np.maximum(turn, 0) * (HS_STRESS + FEE)
    add(name, "rebal_premium", mech, diff, cost, cost5, np.maximum(turn, 0), md, mh,
        note="+".join(legs))


def static_carry(name, A, B, P, md, mh, mech="", note=""):
    """duration-matched long A / short B, constant weight. This is a BETA, reported as
    a reference line, not claimed as alpha."""
    k = DUR[A] / DUR[B]
    ra, rb = rets(P[A]), rets(P[B])
    g = np.where(np.isfinite(ra), ra, 0.0) - k * np.where(np.isfinite(rb), rb, 0.0)
    g = np.where(np.isfinite(ra) & np.isfinite(rb), g, np.nan)
    turn = np.zeros(len(g))
    add(name, "static_reference", mech, g, turn, turn, turn, md, mh, note=note)


def main():
    dates, P = load()
    md = (dates >= DESIGN[0]) & (dates <= DESIGN[1])
    mh = (dates >= HOLDOUT[0]) & (dates <= HOLDOUT[1])
    print(f"dates {dates[0]}..{dates[-1]} n={len(dates)} design={md.sum()} holdout={mh.sum()}")

    TETH = ("Two claims on the SAME discount curve. The tether is arbitrage in the "
            "underlying bonds, which is economic, not statistical.")
    BE = ("A TIPS-vs-nominal spread IS expected inflation, which a credible inflation "
          "target anchors -- a rare case of a mean that an institution actively defends.")
    DIV = ("Rebalancing a diversified pair harvests relative-price variance. It is an "
           "algebraic consequence of the geometric/arithmetic mean gap, not a forecast.")
    TP = ("Term premium: a lender bearing duration must be paid for it.")

    # ---- rebalancing / diversification return (structural, no forecast) ----
    rebal_premium("REBAL_6040_SPY_TLT", ["SPY", "TLT"], P, md, mh, DIV)
    rebal_premium("REBAL_INVVOL_SPY_TLT", ["SPY", "TLT"], P, md, mh, DIV, vol_weight=True)
    rebal_premium("REBAL_INVVOL_SPY_TLT_GLD", ["SPY", "TLT", "GLD"], P, md, mh, DIV, vol_weight=True)
    rebal_premium("REBAL_EW_SPY_TLT_LQD_GLD", ["SPY", "TLT", "LQD", "GLD"], P, md, mh, DIV)

    # ---- duration-tethered RV on a weekly clock ----
    rv_butterfly("RV_BFLY_2s10s30s", "SHY", "IEF", "TLT", P, md, mh, mech=TETH)
    rv_butterfly("RV_BFLY_2s5s10s", "SHY", "IEI", "IEF", P, md, mh, mech=TETH)
    rv_pair("RV_BELLY_vs_LONG", "IEF", "TLT", P, dates, md, mh, mech=TETH)
    rv_pair("RV_BELLY_vs_SHORT", "IEF", "SHY", P, dates, md, mh, mech=TETH)
    rv_pair("RV_BREAKEVEN_TIP_IEF", "TIP", "IEF", P, dates, md, mh, mech=BE)
    rv_pair("RV_STRIPS_ZROZ_EDV", "ZROZ", "EDV", P, dates, md, mh, hedge="unit", mech=TETH)
    rv_pair("RV_GOVT_VGIT_IEF", "VGIT", "IEF", P, dates, md, mh, mech=TETH)
    rv_pair("RV_SHORTGOV_SCHO_VGSH", "SCHO", "VGSH", P, dates, md, mh, hedge="unit", mech=TETH)
    rv_pair("RV_LONGGOV_VGLT_TLT", "VGLT", "TLT", P, dates, md, mh, mech=TETH)
    rv_pair("RV_IG_IGIB_VCIT", "IGIB", "VCIT", P, dates, md, mh, hedge="unit", mech=TETH)
    rv_pair("RV_HY_HYG_JNK", "HYG", "JNK", P, dates, md, mh, hedge="unit", mech=TETH)
    rv_pair("RV_AGG_BND", "AGG", "BND", P, dates, md, mh, hedge="unit", mech=TETH)
    rv_pair("RV_MBS_MBB_VMBS", "MBB", "VMBS", P, dates, md, mh, hedge="unit", mech=TETH)
    rv_pair("RV_TIPS_TIP_SCHP", "TIP", "SCHP", P, dates, md, mh, hedge="unit", mech=TETH)
    rv_pair("RV_MUNI_MUB_TFI", "MUB", "TFI", P, dates, md, mh, hedge="unit", mech=TETH)
    rv_pair("RV_IGBROAD_LQD_USIG", "LQD", "USIG", P, dates, md, mh, hedge="unit", mech=TETH)
    rv_pair("RV_EMSOV_EMB_PCY", "EMB", "PCY", P, dates, md, mh, hedge="unit", mech=TETH)
    rv_pair("RV_LOAN_BKLN_SRLN", "BKLN", "SRLN", P, dates, md, mh, hedge="unit", mech=TETH)
    rv_pair("RV_PREF_PFF_PGX", "PFF", "PGX", P, dates, md, mh, hedge="unit", mech=TETH)

    # ---- static references (betas, not alpha claims) ----
    static_carry("REF_TERM_TLT_SHY", "TLT", "SHY", P, md, mh, TP, "duration-matched long-vs-short")
    static_carry("REF_CREDIT_HYG_IEF", "HYG", "IEF", P, md, mh,
                 "Credit risk premium; a beta, reported for context.", "dur-matched HY vs UST")

    out = dict(design=DESIGN, holdout=HOLDOUT, hs_bps=HS * 1e4, hold_days=HOLD,
               rows=RESULTS)
    json.dump(out, open(os.path.join(RES, "INVENT_0822_slowturn_TS.json"), "w"),
              indent=1, default=float)
    hdr = (f"{'name':<24s}{'win':<9s}{'gSR':>7s}{'gt':>7s}{'gtNW':>7s}{'nSR':>7s}{'nt':>7s}"
           f"{'turn':>8s}{'rho1':>8s}{'H':>6s}{'adf':>7s}{'hl':>7s}")
    print(hdr)
    for r in RESULTS:
        print(f"{r['name']:<24s}{r['window']:<9s}{r['gross_sharpe']:7.2f}{r['gross_t']:7.2f}"
              f"{r['gross_t_nw']:7.2f}"
              f"{r['net_sharpe']:7.2f}{r['net_t']:7.2f}{r['turnover_per_day']:8.4f}"
              f"{r.get('rho1_dspread',float('nan')):8.3f}{r.get('hurst',float('nan')):6.2f}"
              f"{r.get('adf_t',float('nan')):7.2f}{r.get('halflife_d',float('nan')):7.1f}")


if __name__ == "__main__":
    main()
