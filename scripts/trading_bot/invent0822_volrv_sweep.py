"""INVENT 0822 -- VOL theme sweep: the volatility-ETP MECHANICAL TETHER family.

THEME. Volatility-family signals from FREE proxies, re-aimed at the ONE class this
programme has found survivable (structurally-anchored mean reversion) instead of the
two forms already killed:
  - vol curve as a DIRECTIONAL equity signal  -> INVENT_D0821_volterm, 43 formulas, NOISE
  - vol-ETP roll CARRY / curve timing         -> NEWTERR_volatility_etp_term_structure,
                                                 39 formulas, NOISE
  - implied surface -> underlying (reliv / ownvrp / crosssec / dispersion)
                                              -> NEWTERR_optimp, 109 formulas, NOISE

WHAT IS NEW HERE. Not the vol curve as a predictor of anything. The vol-ETP complex as a
set of DIFFERENT WRAPPERS ON ONE PUBLISHED INDEX, tied by prospectus arithmetic:

    VIXY (+1x ETF), VXX (+1x ETN), UVXY (+1.5x ETF), SVXY (-0.5x ETF)
        all track S&P 500 VIX Short-Term Futures Index TR (SPVXSTR)
    VIXM (+1x ETF), VXZ (+1x ETN)
        both track the mid-term index (SPVXMTR)

Because each is a DAILY-RESET product, its NAV return over one full session equals
k * (index return) - fee/day EXACTLY, path-independently.  Therefore for any two of them

    e_t  =  r_A,t  -  k * r_B,t   ==  (a constant fee differential)  in NAV terms.

Every non-constant part of e_t is a MARKET-PRICE-vs-NAV dislocation of one wrapper against
another: an ETN creation halt, a premium/discount, a stale close. It carries no information
about volatility. A-priori sign, fixed before any result: FADE it -- short whichever wrapper
outran its own contractual multiple.

This is the ETF-sibling / dual-class tether class, applied to the one complex where the
tether is not an approximation but an identity. It has not been tested by this programme.

Free data only. Cached Yahoo adjusted closes in research/data/volterm_cache/raw/.
No network call. numpy only.
"""
import json
import math
import sys

import numpy as np

sys.path.insert(0, "/home/anont/meme/scripts/trading_bot")
from invent0822_volrv_panel import PAIRS, build_pair, load, k_for  # noqa: E402

DESIGN_LO, DESIGN_HI = "20111004", "20211231"
HOLD_LO, HOLD_HI = "20220101", "20260820"

SYMS = ["VXX", "VIXY", "UVXY", "SVXY", "VXZ", "VIXM"]

# conservative half-spreads in bp/side, anchored to median daily $ volume 2024-26
# (VXX 218M, UVXY 268M, SVXY 73M, VIXY 64M, VIXM 2.0M, VXZ 0.5M) with the Dyhrberg
# liquid-taker 2.5bp as the floor. +0.5bp fee/side. Borrow accrues on short legs.
HALF_SPREAD = {"VXX": 3.0, "UVXY": 3.0, "VIXY": 5.0, "SVXY": 6.0, "VIXM": 15.0, "VXZ": 30.0}
FEE_BP = 0.5
BORROW_ANN = {"VXX": 0.05, "UVXY": 0.05, "VIXY": 0.05, "SVXY": 0.02, "VIXM": 0.05, "VXZ": 0.05}

# ProShares leverage change effective 2018-02-28; guard the transition sessions.
GUARD = {"20180226", "20180227", "20180228", "20180301", "20180302", "20180305"}

EVAL_PAIRS = ["VXX_VIXY", "VXZ_VIXM", "UVXY_VIXY", "SVXY_VIXY", "UVXY_VXX", "SVXY_VXX"]
LIQUID_PAIRS = ["VXX_VIXY", "UVXY_VIXY", "SVXY_VIXY", "UVXY_VXX", "SVXY_VXX"]


# ------------------------------------------------------------------ panel
def build_panel():
    data = {s: load(s) for s in SYMS}
    pan = {}
    for name, A, B, kb, ka, _idx in PAIRS:
        if name not in EVAL_PAIRS:
            continue
        rows = [r for r in build_pair(name, A, B, kb, ka, data[A], data[B])
                if r["day"] not in GUARD]
        pan[name] = {"A": A, "B": B, "rows": rows,
                     "day": np.array([r["day"] for r in rows]),
                     "e": np.array([r["e"] for r in rows]),
                     "k": np.array([r["k"] for r in rows]),
                     "rA": np.array([r["rA"] for r in rows]),
                     "rB": np.array([r["rB"] for r in rows])}
    # cross-wrapper panel: the four SPVXSTR wrappers on a common calendar
    xs_syms = ["VIXY", "VXX", "UVXY", "SVXY"]
    days = sorted(set.intersection(*[set(data[s]) for s in xs_syms]))
    ihat = {s: [] for s in xs_syms}
    xdays = []
    for i in range(1, len(days)):
        d0, d1 = days[i - 1], days[i]
        if d1 in GUARD:
            continue
        xdays.append(d1)
        for s in xs_syms:
            kk = {"VIXY": 1.0, "VXX": 1.0,
                  "UVXY": k_for(d1, 2.0, 1.5), "SVXY": k_for(d1, -1.0, -0.5)}[s]
            r = data[s][d1]["adj"] / data[s][d0]["adj"] - 1.0
            ihat[s].append(r / kk)          # each wrapper's implied index return
    X = {"day": np.array(xdays), "syms": xs_syms,
         "ihat": np.array([ihat[s] for s in xs_syms]),           # (4, T)
         "k": np.array([[{"VIXY": 1.0, "VXX": 1.0,
                          "UVXY": k_for(d, 2.0, 1.5),
                          "SVXY": k_for(d, -1.0, -0.5)}[s] for d in xdays]
                        for s in xs_syms])}
    return pan, X


# ------------------------------------------------------------------ helpers
def roll_z(x, win):
    """causal z-score: mean/sd of the PRIOR `win` observations, excluding today."""
    z = np.full(len(x), np.nan)
    for t in range(win, len(x)):
        w = x[t - win:t]
        sd = w.std()
        if sd > 0:
            z[t] = (x[t] - w.mean()) / sd
    return z


def sharpe_stats(r):
    r = np.asarray(r, float)
    r = r[np.isfinite(r)]
    if len(r) < 60 or r.std() == 0:
        return dict(n=len(r), sr=float("nan"), t=float("nan"), yrs=len(r) / 252.0,
                    mean_bp=float("nan"), worst=float("nan"), maxdd=float("nan"))
    yrs = len(r) / 252.0
    sr = r.mean() / r.std() * math.sqrt(252)
    eq = np.cumsum(r)
    dd = float((eq - np.maximum.accumulate(eq)).min())
    return dict(n=len(r), sr=float(sr), t=float(sr * math.sqrt(yrs)), yrs=yrs,
                mean_bp=float(r.mean() * 1e4), worst=float(r.min()), maxdd=dd)


def leg_cost_bp(A, B, k):
    """round-trip-per-rebalance cost in bp of GROSS notional, one entry+one exit."""
    ga = 1.0 / (1.0 + abs(k))
    gb = abs(k) / (1.0 + abs(k))
    return 2.0 * (ga * (HALF_SPREAD[A] + FEE_BP) + gb * (HALF_SPREAD[B] + FEE_BP))


# ------------------------------------------------------------------ book builders
def pair_book(P, sig, lag, hold=1):
    """sig[t] is the fade signal computed from information through close t.
    lag=0: fill at close t, earn t->t+1 (reference only, 0-min slack).
    lag=1: fill at close t+1, earn t+1->t+2  (HEADLINE).
    Returns (days, gross_ret, net_ret, turnover_per_day)."""
    e = P["e"]
    k = P["k"]
    T = len(e)
    w = np.zeros(T)                       # weight applied to -(e) at t+1
    for t in range(T):
        s = sig[t]
        if not np.isfinite(s) or s == 0:
            continue
        for h in range(hold):
            j = t + lag + h
            if j < T:
                w[j] += -s / hold
    gr = np.zeros(T)
    gr[1:] = w[:-1] * e[1:] / (1.0 + np.abs(k[1:]))   # gross exposure normalised to 1
    # cost: charged on |dw| at each rebalance, plus borrow on the short leg
    dw = np.abs(np.diff(np.concatenate([[0.0], w])))
    c = leg_cost_bp(P["A"], P["B"], float(np.median(np.abs(k)))) / 2.0  # per side of |dw|
    cost = dw * c * 1e-4
    bor = (BORROW_ANN[P["A"]] / 252.0 * np.abs(w) / (1 + np.abs(k))
           + BORROW_ANN[P["B"]] / 252.0 * np.abs(w) * np.abs(k) / (1 + np.abs(k))) * 0.5
    net = gr - cost - bor
    return P["day"], gr, net, float(np.mean(dw))


def pool(books, days_list, lo, hi):
    """equal-risk pool: each book scaled by its trailing-60d sd (causal), then averaged
    on the union calendar."""
    allday = sorted(set().union(*[set(d) for d in days_list]))
    idx = {d: i for i, d in enumerate(allday)}
    acc = np.zeros(len(allday))
    cnt = np.zeros(len(allday))
    for bk, dd in zip(books, days_list):
        sd = np.full(len(bk), np.nan)
        for t in range(60, len(bk)):
            s = bk[t - 60:t].std()
            sd[t] = s if s > 0 else np.nan
        sc = bk / sd
        for t in range(len(bk)):
            if np.isfinite(sc[t]):
                i = idx[dd[t]]
                acc[i] += sc[t]
                cnt[i] += 1
    out_d, out_r = [], []
    for i, d in enumerate(allday):
        if cnt[i] > 0 and lo <= d <= hi:
            out_d.append(d)
            out_r.append(acc[i] / cnt[i])
    return np.array(out_d), np.array(out_r)


def win(days, r, lo, hi):
    m = (days >= lo) & (days <= hi)
    return r[m]


# ------------------------------------------------------------------ the sweep
def run():
    pan, X = build_panel()
    FORM = []            # (name, group, why, {lag: (days, gross, net)})

    def add(name, group, why, mk):
        FORM.append({"name": name, "group": group, "why": why, "mk": mk})

    # ---- GROUP P: pairwise one-day replication-residual fade -------------------
    for pname in EVAL_PAIRS:
        P = pan[pname]
        z = roll_z(P["e"], 60)
        lin = np.clip(np.nan_to_num(z, nan=0.0), -3, 3) / 3.0
        for tag, sig in (("LIN", lin),
                         ("TH2", np.sign(np.nan_to_num(z, nan=0.0)) *
                          (np.abs(np.nan_to_num(z, nan=0.0)) >= 2.0))):
            add(f"P_{pname}_{tag}", "P_pairfade",
                "wrapper outran its contractual multiple for one session; fade the "
                "dislocation back to the tether",
                (lambda P=P, sig=sig: {L: pair_book(P, sig, L) for L in (0, 1, 2)}))

    # ---- GROUP L: pairwise CUMULATIVE premium (level, not one-day change) ------
    # M_t = cumulative sum of e  ~ the wrapper's accumulated price-vs-price premium.
    # Detrend by its own trailing MA; fade the z-score of the deviation.
    for pname in LIQUID_PAIRS:
        P = pan[pname]
        M = np.cumsum(P["e"])
        for winlen in (20, 60):
            dev = np.full(len(M), np.nan)
            for t in range(winlen, len(M)):
                dev[t] = M[t] - M[t - winlen:t].mean()
            z = roll_z(np.nan_to_num(dev, nan=0.0), 120)
            sig = np.sign(np.nan_to_num(z, nan=0.0)) * (np.abs(np.nan_to_num(z, nan=0.0)) >= 2.0)
            add(f"L_{pname}_{winlen}", "L_premlevel",
                "an accumulated wrapper premium (ETN creation halt, persistent "
                "discount) must collapse back to the index tether",
                (lambda P=P, sig=sig: {L: pair_book(P, sig, L, hold=5) for L in (0, 1, 2)}))

    # ---- GROUP X: cross-wrapper disagreement on ONE index ----------------------
    # four wrappers must agree on one number (the index return). Fade the disagreement.
    ih = X["ihat"]
    disp = ih - ih.mean(axis=0, keepdims=True)          # (4,T) wrapper-specific error
    kk = X["k"]

    def xs_book(sig4, lag, hold=1, lvl=False):
        T = ih.shape[1]
        w = np.zeros((4, T))
        for t in range(T):
            s = sig4[:, t]
            if not np.all(np.isfinite(s)):
                continue
            s = s - s.mean()
            n = np.abs(s).sum()
            if n == 0:
                continue
            s = s / n
            for h in range(hold):
                j = t + lag + h
                if j < T:
                    w[:, j] += -s / hold
        # book return: weight on each wrapper's IMPLIED index return, so the book is
        # index-neutral by construction (weights sum to zero in implied-index space)
        gr = np.zeros(T)
        gr[1:] = (w[:, :-1] * disp[:, 1:]).sum(axis=0)
        dw = np.abs(np.diff(np.concatenate([np.zeros((4, 1)), w], axis=1), axis=1))
        hs = np.array([[HALF_SPREAD[s] + FEE_BP] for s in X["syms"]])
        # a weight w in implied-index space is |w/k| of actual notional
        cost = (dw / np.abs(kk) * hs * 1e-4).sum(axis=0)
        bor = (np.abs(w) / np.abs(kk) *
               np.array([[BORROW_ANN[s] / 252.0] for s in X["syms"]]) * 0.5).sum(axis=0)
        return X["day"], gr, gr - cost - bor, float(dw.sum(axis=0).mean())

    zx = np.array([roll_z(disp[i], 60) for i in range(4)])
    zx = np.nan_to_num(zx, nan=0.0)
    add("X_DISAGREE_LIN", "X_crosswrap",
        "the four wrappers on one index must agree; fade whichever disagreed",
        (lambda: {L: xs_book(np.clip(zx, -3, 3) / 3.0, L) for L in (0, 1, 2)}))
    add("X_DISAGREE_TH2", "X_crosswrap",
        "same, only when one wrapper is >=2 sigma out of line",
        (lambda: {L: xs_book(np.sign(zx) * (np.abs(zx) >= 2.0), L) for L in (0, 1, 2)}))
    add("X_DISAGREE_RANK", "X_crosswrap",
        "same, expressed as a cross-sectional rank tilt rather than a z tilt",
        (lambda: {L: xs_book(np.argsort(np.argsort(disp, axis=0), axis=0) - 1.5, L)
                  for L in (0, 1, 2)}))
    Mx = np.cumsum(disp, axis=1)
    for winlen in (20, 60, 120):
        devx = np.full_like(Mx, np.nan)
        for t in range(winlen, Mx.shape[1]):
            devx[:, t] = Mx[:, t] - Mx[:, t - winlen:t].mean(axis=1)
        zl = np.nan_to_num(np.array([roll_z(np.nan_to_num(devx[i], nan=0.0), 120)
                                     for i in range(4)]), nan=0.0)
        add(f"X_PREMLVL_{winlen}", "X_crosswrap",
            "accumulated per-wrapper premium against the complex mean; fade it",
            (lambda zl=zl: {L: xs_book(np.clip(zl, -3, 3) / 3.0, L, hold=5)
                            for L in (0, 1, 2)}))

    # ---- GROUP H: holding horizon on the pooled one-day fade -------------------
    for hold in (3, 5):
        for pname in ("UVXY_VIXY", "SVXY_VIXY", "VXX_VIXY"):
            P = pan[pname]
            z = np.nan_to_num(roll_z(P["e"], 60), nan=0.0)
            sig = np.clip(z, -3, 3) / 3.0
            add(f"H{hold}_{pname}", "H_horizon",
                "if the dislocation is a slow wrapper premium and not a bounce, a "
                "multi-day hold should keep the edge",
                (lambda P=P, sig=sig, hold=hold:
                 {L: pair_book(P, sig, L, hold=hold) for L in (0, 1, 2)}))

    # ---- GROUP S: tether-specification controls (counted in N) -----------------
    # S1: empirical rolling beta instead of the contractual multiple
    for pname in ("UVXY_VIXY", "SVXY_VIXY"):
        P = pan[pname]
        rA, rB = P["rA"], P["rB"]
        beta = np.full(len(rA), np.nan)
        for t in range(120, len(rA)):
            a, b = rA[t - 120:t], rB[t - 120:t]
            v = (b * b).sum()
            if v > 0:
                beta[t] = (a * b).sum() / v
        eb = rA - np.nan_to_num(beta, nan=0.0) * rB
        Pb = dict(P)
        Pb["e"] = eb
        z = np.nan_to_num(roll_z(eb, 60), nan=0.0)
        add(f"S_BETA_{pname}", "S_spec",
            "does the FITTED multiple tether better than the CONTRACTUAL one? "
            "a-priori: no, the contract is the truth",
            (lambda Pb=Pb, z=z: {L: pair_book(Pb, np.clip(z, -3, 3) / 3.0, L)
                                 for L in (0, 1, 2)}))
    # S2: log-return tether (the WRONG algebra for a daily-reset product)
    for pname in ("UVXY_VIXY", "SVXY_VIXY"):
        P = pan[pname]
        el = np.log1p(P["rA"]) - P["k"] * np.log1p(P["rB"])
        Pl = dict(P)
        Pl["e"] = el
        z = np.nan_to_num(roll_z(el, 60), nan=0.0)
        add(f"S_LOG_{pname}", "S_spec",
            "log-space tether: deliberately the wrong algebra for a daily-reset "
            "product; if it scores like the right one, the 'tether' is not doing the work",
            (lambda Pl=Pl, z=z: {L: pair_book(Pl, np.clip(z, -3, 3) / 3.0, L)
                                 for L in (0, 1, 2)}))

    # ---------------------------------------------------------------- evaluate
    out = []
    for F in FORM:
        books = F["mk"]()
        rec = {"name": F["name"], "group": F["group"], "why": F["why"]}
        for L, (dd, gr, net, tov) in books.items():
            for wname, (lo, hi) in (("design", (DESIGN_LO, DESIGN_HI)),
                                    ("holdout", (HOLD_LO, HOLD_HI))):
                sg = sharpe_stats(win(dd, gr, lo, hi))
                sn = sharpe_stats(win(dd, net, lo, hi))
                rec[f"{wname}_L{L}_gross"] = sg
                rec[f"{wname}_L{L}_net"] = sn
            rec[f"turnover_L{L}"] = tov
        # single-day-dominance diagnostic on the design gross book
        dd, gr, net, _ = books[1]
        g = win(dd, gr, DESIGN_LO, DESIGN_HI)
        dg = win(dd, gr, DESIGN_LO, DESIGN_HI)
        if len(g) > 10:
            top = np.sort(np.abs(dg))[-1]
            rec["design_top1day_share_of_meanabs"] = float(top / (np.abs(dg).sum() + 1e-12))
        out.append(rec)
    return pan, X, out


if __name__ == "__main__":
    pan, X, out = run()
    with open("/home/anont/meme/research/trading_bot/INVENT_0822_vol_RAW.json", "w") as f:
        json.dump(out, f, indent=1)
    print("N formulas =", len(out))
    rows = sorted(out, key=lambda r: -(r["design_L1_gross"]["sr"]
                                       if np.isfinite(r["design_L1_gross"]["sr"]) else -9))
    print("%-26s %6s %6s %6s %6s %6s %6s" %
          ("name", "gL0", "gL1", "gL2", "nL1", "hgL1", "hnL1"))
    for r in rows:
        print("%-26s %+6.2f %+6.2f %+6.2f %+6.2f %+6.2f %+6.2f" % (
            r["name"], r["design_L0_gross"]["sr"], r["design_L1_gross"]["sr"],
            r["design_L2_gross"]["sr"], r["design_L1_net"]["sr"],
            r["holdout_L1_gross"]["sr"], r["holdout_L1_net"]["sr"]))
