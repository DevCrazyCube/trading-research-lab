#!/usr/bin/env python3
"""NEWTERR shortint sweep. Frozen harness -- see NEWTERR_shortint_PREREGISTRATION.md.

usage: newterr_shortint_sweep.py <design|holdout|selftest> [--out PATH] [--only S07,S13]

Every gate constant below is pre-registered. Nothing here is fitted.
"""
import json, os, sys
import numpy as np

ROOT = "/home/anont/meme"
PANELS = os.path.join(ROOT, "research/data/newterr_shortint/panels.npz")

# ---- pre-registered constants ---------------------------------------------
WINDOWS = {"design": ("2018-08-01", "2022-12-30"), "holdout": ("2023-01-03", "2026-08-14")}
MIN_PRICE = 5.0
MIN_GDV20 = 10e6
QUANTILE = 0.20          # top/bottom quintile
GROSS = 1.0
TC_ONEWAY = 4.0e-4       # 4 bp of traded notional
BORROW_ETB = 0.006       # 60 bp/yr
BORROW_HTB = 0.10        # 1000 bp/yr
HTB_DTC = 5.0            # published days-to-cover above which a short is HTB-priced
HORIZONS = [1, 5, 10, 21]
LAGS = [1, 2]            # 1 = base spec, 2 = lag-kill
WARMUP = 250


# ---- rolling helpers (nan-aware, along time axis) --------------------------
def _cum(X):
    return np.concatenate([np.zeros((X.shape[0], 1), np.float64), np.cumsum(X, axis=1)], axis=1)


def rmean(X, w, minfrac=0.5):
    V = np.nan_to_num(X, nan=0.0).astype(np.float64)
    C = np.isfinite(X).astype(np.float64)
    cv, cc = _cum(V), _cum(C)
    D = X.shape[1]
    s = cv[:, w:] - cv[:, :-w]
    n = cc[:, w:] - cc[:, :-w]
    out = np.full(X.shape, np.nan, np.float32)
    ok = n >= max(1.0, minfrac * w)
    res = np.divide(s, np.maximum(n, 1.0), out=np.full_like(s, np.nan), where=ok)
    out[:, w - 1:] = res.astype(np.float32)
    return out


def rstd(X, w, minfrac=0.5):
    m1 = rmean(X, w, minfrac).astype(np.float64)
    m2 = rmean(np.square(X.astype(np.float64)).astype(np.float32), w, minfrac).astype(np.float64)
    v = np.maximum(m2 - m1 * m1, 0.0)
    return np.sqrt(v).astype(np.float32)


def rz(X, w):
    m, s = rmean(X, w), rstd(X, w)
    return np.where(s > 0, (X - m) / np.maximum(s, 1e-12), np.nan).astype(np.float32)


def shift(X, k):
    out = np.full_like(X, np.nan)
    if k > 0:
        out[:, k:] = X[:, :-k]
    return out


def rslope(X, w):
    """OLS slope of X on 0..w-1 over a trailing window, nan-aware-ish (uses rmean)."""
    tt = np.arange(w, dtype=np.float64)
    tbar = tt.mean()
    denom = ((tt - tbar) ** 2).sum()
    num = np.zeros(X.shape, np.float64)
    for k in range(w):
        num += (tt[w - 1 - k] - tbar) * np.nan_to_num(shift(X, k), nan=0.0)
    cnt = np.zeros(X.shape, np.float64)
    for k in range(w):
        cnt += np.isfinite(shift(X, k)).astype(np.float64)
    out = np.where(cnt >= w * 0.6, num / denom, np.nan)
    return out.astype(np.float32)


def xrank(v, m):
    """cross-sectional rank of v inside mask m, mapped to [-0.5, 0.5]; nan outside."""
    out = np.full(v.shape, np.nan, np.float64)
    idx = np.flatnonzero(m & np.isfinite(v))
    n = idx.size
    if n < 40:
        return out
    order = np.argsort(v[idx], kind="mergesort")
    r = np.empty(n, np.float64)
    r[order] = np.arange(n, dtype=np.float64)
    out[idx] = r / (n - 1.0) - 0.5
    return out


# ---- load ------------------------------------------------------------------
def load():
    z = np.load(PANELS, allow_pickle=True)
    P = {k: z[k] for k in z.files}
    return P


def build_bases(P):
    close = P["close"].astype(np.float32)
    vol = P["vol"].astype(np.float32)
    S, D = close.shape
    B = {}
    B["S"], B["D"] = S, D
    B["close"] = close
    B["dates"] = np.array([str(x) for x in P["dates"]])
    B["symbols"] = np.array([str(x) for x in P["symbols"]])

    with np.errstate(all="ignore"):
        prev = shift(close, 1)
        R1 = close / prev - 1.0
        R1 = np.where(np.isfinite(R1) & (np.abs(R1) < 1.0), R1, np.nan)  # >100% 1d moves: bad data / unadjusted CA
        B["R1"] = R1.astype(np.float32)
        for k in (1, 5, 20):
            B["ret%d" % k] = (close / shift(close, k) - 1.0).astype(np.float32)
        dvol = close * vol
        B["gdv20"] = np.exp(rmean(np.log(np.where(dvol > 0, dvol, np.nan)).astype(np.float32), 20)).astype(np.float32)
        B["advsh20"] = rmean(np.where(vol > 0, vol, np.nan).astype(np.float32), 20)

        svt = P["sv_total"].astype(np.float32)
        svs = P["sv_short"].astype(np.float32)
        sve = P["sv_exempt"].astype(np.float32)
        svr = np.where(svt > 0, svs / svt, np.nan).astype(np.float32)
        B["svr"] = svr
        B["exr"] = np.where(svt > 0, sve / svt, np.nan).astype(np.float32)
        B["offex"] = np.where((vol > 0) & (svt > 0), svt / vol, np.nan).astype(np.float32)
        B["svs"] = svs
        B["svt"] = svt

        B["svr5"] = rmean(svr, 5)
        B["svr20m"] = rmean(svr, 20)
        B["svr20s"] = rstd(svr, 20)
        B["svr60"] = rmean(svr, 60)
        B["svr250"] = rmean(svr, 250)
        B["svrz20"] = np.where(B["svr20s"] > 0, (svr - B["svr20m"]) / np.maximum(B["svr20s"], 1e-9), np.nan).astype(np.float32)
        B["svrslope10"] = rslope(svr, 10)
        B["exr5"] = rmean(B["exr"], 5)
        B["exr60"] = rmean(B["exr"], 60)
        B["offex5"] = rmean(B["offex"], 5)
        B["offex60"] = rmean(B["offex"], 60)

        # ---- short interest, keyed to DISSEMINATION not settlement ----------
        si_pos, si_prev = P["si_pos"].astype(np.float64), P["si_prev"].astype(np.float64)
        si_dtc = P["si_dtc"].astype(np.float64)
        avail = P["si_avail_idx"].astype(int)
        K = si_pos.shape[1]
        sichg = si_pos / np.where(si_prev > 0, si_prev, np.nan) - 1.0
        siacc = sichg - np.concatenate([np.full((S, 1), np.nan), sichg[:, :-1]], 1)
        dtcchg = si_dtc - np.concatenate([np.full((S, 1), np.nan), si_dtc[:, :-1]], 1)
        # z of SI over own trailing 12 prints (settlement axis)
        siz = np.full_like(si_pos, np.nan)
        for k in range(12, K):
            w = si_pos[:, k - 12:k]
            mu = np.nanmean(w, 1)
            sd = np.nanstd(w, 1)
            siz[:, k] = np.where(sd > 0, (si_pos[:, k] - mu) / np.maximum(sd, 1e-9), np.nan)

        kmap = np.full(D, -1, int)
        cur = -1
        for j in range(D):
            while cur + 1 < K and 0 <= avail[cur + 1] <= j:
                cur += 1
            kmap[j] = cur
        valid = kmap >= 0
        km = np.maximum(kmap, 0)

        def tod(M):
            out = M[:, km].astype(np.float32)
            out[:, ~valid] = np.nan
            return out

        B["SIP"] = tod(si_pos)
        B["SIDTC"] = tod(si_dtc)
        B["SICHG"] = tod(sichg)
        B["SIACC"] = tod(siacc)
        B["SIZ12"] = tod(siz)
        B["DTCCHG"] = tod(dtcchg)
        B["SIPREV"] = tod(si_prev)
        # first session on which the CURRENT print was public
        sav = np.where(valid, avail[km], 0)
        B["sav"] = sav

        B["dtc_live"] = (B["SIP"] / np.maximum(B["advsh20"], 1.0)).astype(np.float32)
        B["si_dollar"] = (B["SIP"] * close / np.maximum(B["gdv20"], 1.0)).astype(np.float32)
        B["dsi_adv"] = ((B["SIP"] - B["SIPREV"]) / np.maximum(B["advsh20"], 1.0)).astype(np.float32)

        # since-last-settlement aggregates of the daily short-volume tape
        CS = _cum(np.nan_to_num(svr, nan=0.0).astype(np.float64))
        CN = _cum(np.isfinite(svr).astype(np.float64))
        netsh = np.where(np.isfinite(svs) & np.isfinite(svt), 2.0 * svs - svt, 0.0)
        CX = _cum(netsh.astype(np.float64))
        j = np.arange(D)
        lo = np.maximum(sav, 0)
        s_ = CS[:, j + 1] - CS[:, lo]
        n_ = CN[:, j + 1] - CN[:, lo]
        B["svr_since"] = np.where(n_ >= 3, s_ / np.maximum(n_, 1), np.nan).astype(np.float32)
        x_ = CX[:, j + 1] - CX[:, lo]
        B["netshort_since"] = np.where(n_ >= 3, x_ / np.maximum(B["advsh20"] * n_, 1.0), np.nan).astype(np.float32)

        # borrow rate panel
        B["brate"] = np.where(np.isfinite(B["SIDTC"]) & (B["SIDTC"] > HTB_DTC), BORROW_HTB, BORROW_ETB).astype(np.float32)

        # base universe mask
        nclose = np.isfinite(close)
        run = np.zeros(close.shape, np.int32)
        acc = np.zeros(S, np.int32)
        for jj in range(D):
            acc = np.where(nclose[:, jj], acc + 1, 0)
            run[:, jj] = acc
        isetf = P["is_etf"].astype(bool)
        univ = (
            (~isetf)[:, None]
            & (close >= MIN_PRICE)
            & (B["gdv20"] >= MIN_GDV20)
            & (run >= 60)
            & np.isfinite(B["R1"])
        )
        B["univ"] = univ
    return B


# ---- signal roster ---------------------------------------------------------
def signals(B):
    """id -> (mechanism, fn(t, m) -> score vector; +score = LONG)."""
    def col(name):
        return lambda t, m, _n=name: B[_n][:, t].astype(np.float64)

    def neg(name):
        return lambda t, m, _n=name: -B[_n][:, t].astype(np.float64)

    def rnk(name, sign=1.0):
        return lambda t, m, _n=name, _s=sign: _s * xrank(B[_n][:, t].astype(np.float64), m)

    def inter(a, b, sign=1.0):
        def f(t, m, _a=a, _b=b, _s=sign):
            return _s * xrank(B[_a][:, t].astype(np.float64), m) * xrank(B[_b][:, t].astype(np.float64), m)
        return f

    def cond(name, sign, condname, condsign):
        def f(t, m, _n=name, _s=sign, _c=condname, _cs=condsign):
            c = B[_c][:, t].astype(np.float64)
            mm = m & np.isfinite(c) & (_cs * c > 0)
            return _s * xrank(B[_n][:, t].astype(np.float64), mm)
        return f

    R = {}
    R["S01"] = ("published days-to-cover: short sellers are informed, follow the crowd", rnk("SIDTC", -1.0))
    R["S02"] = ("crowding on a live (non-stale) ADV denominator", rnk("dtc_live", -1.0))
    R["S03"] = ("shorts ADDING is the informed flow, not the level", rnk("SICHG", -1.0))
    R["S04"] = ("SI change in units of days of volume", rnk("dsi_adv", -1.0))
    R["S05"] = ("acceleration of short building", rnk("SIACC", -1.0))
    R["S06"] = ("crowding vs the name's own 12-print history", rnk("SIZ12", -1.0))
    R["S07"] = ("squeeze fuel: crowded shorts in a RISING name are forced buyers", cond("SIDTC", +1.0, "ret20", +1.0))
    R["S08"] = ("covering-exhaustion bounce in a crowded LOSER", cond("SIDTC", +1.0, "ret20", -1.0))
    R["S09"] = ("shorts pressing a loser keeps working (DTC x momentum)", inter("SIDTC", "ret20", -1.0))
    R["S10"] = ("same interaction on the FLOW rather than the level", inter("SICHG", "ret20", -1.0))
    R["S11"] = ("change in the cover-time itself", rnk("DTCCHG", -1.0))
    R["S12"] = ("dollar crowding, size-neutral", rnk("si_dollar", -1.0))

    R["S13"] = ("today's short-volume share is informed directional flow", rnk("svr", -1.0))
    R["S14"] = ("smoothed short-volume share", rnk("svr5", -1.0))
    R["S15"] = ("short-flow momentum, name-demeaned by construction (5d-60d)", lambda t, m: -xrank((B["svr5"][:, t] - B["svr60"][:, t]).astype(np.float64), m))
    R["S16"] = ("today's SVR spike vs the name's own 20d", rnk("svrz20", -1.0))
    R["S17"] = ("slow-demeaned SVR (5d-250d): removes the permanent MM component", lambda t, m: -xrank((B["svr5"][:, t] - B["svr250"][:, t]).astype(np.float64), m))
    R["S18"] = ("opposite sign: MM inventory absorbs an SVR spike and it reverts", rnk("svrz20", +1.0))
    R["S19"] = ("shorting INTO STRENGTH vs into weakness are different trades", inter("svrz20", "ret1", -1.0))
    R["S20"] = ("shorts pressed a loser -> covering bounce", cond("svr5", +1.0, "ret5", -1.0))
    R["S21"] = ("a rally WITH short fuel keeps going; without it there is none", cond("svr5", +1.0, "ret5", +1.0))
    R["S22"] = ("the SVR trend rather than its level", rnk("svrslope10", -1.0))
    R["S23"] = ("Rule 201 SSR names are already down and constrained", rnk("exr5", +1.0))
    R["S24"] = ("discrete SSR-trigger event (1d exempt ratio > 3x its 60d mean)", lambda t, m: xrank(((B["exr"][:, t] > 3.0 * B["exr60"][:, t]).astype(np.float64) + 1e-9 * B["exr"][:, t]).astype(np.float64), m))

    R["S25"] = ("retail-dominated (high off-exchange) tape is the fade side", rnk("offex5", -1.0))
    R["S26"] = ("off-exchange share momentum (5d-60d)", lambda t, m: -xrank((B["offex5"][:, t] - B["offex60"][:, t]).astype(np.float64), m))
    R["S27"] = ("retail chasing is the fade (offex x ret5)", inter("offex5", "ret5", -1.0))
    R["S28"] = ("internalised BUY pressure: non-short off-exchange notional vs ADV", lambda t, m: xrank((((B["svt"][:, t] - B["svs"][:, t]) * B["close"][:, t]) / np.maximum(B["gdv20"][:, t], 1.0)).astype(np.float64), m))

    R["S29"] = ("crowded AND covering (SVR falling since the print) -> long", lambda t, m: xrank(B["SIDTC"][:, t].astype(np.float64), m) * (-xrank(B["svr_since"][:, t].astype(np.float64), m)))
    R["S30"] = ("shorts building BETWEEN prints (cumulative net short volume / ADV)", rnk("netshort_since", -1.0))
    R["S31"] = ("the staleness correction is itself the signal (live DTC - published DTC)", lambda t, m: -xrank((B["dtc_live"][:, t] - B["SIDTC"][:, t]).astype(np.float64), m))
    return R


# ---- portfolio -------------------------------------------------------------
def weights(B, fn, j0, j1):
    S, D = B["S"], B["D"]
    W = np.zeros((S, D), np.float32)
    univ = B["univ"]
    ns = []
    for t in range(j0, j1 + 1):
        m = univ[:, t]
        if m.sum() < 100:
            continue
        sc = fn(t, m)
        ok = np.isfinite(sc) & m
        n = int(ok.sum())
        if n < 100:
            continue
        idx = np.flatnonzero(ok)
        v = sc[idx]
        k = max(10, int(round(QUANTILE * n)))
        order = np.argsort(v, kind="mergesort")
        lo = idx[order[:k]]
        hi = idx[order[-k:]]
        W[hi, t] = (GROSS / 2.0) / k
        W[lo, t] = -(GROSS / 2.0) / k
        ns.append(n)
    return W, (float(np.mean(ns)) if ns else 0.0), len(ns)


def simulate(B, W, H, LAG, j0, j1):
    S, D = B["S"], B["D"]
    CW = _cum(W.astype(np.float64))          # (S, D+1), CW[:,j] = sum_{m<j} W[:,m]
    R1 = np.nan_to_num(B["R1"], nan=0.0).astype(np.float64)
    brate = B["brate"].astype(np.float64)
    us = np.arange(j0, j1 + 1)
    net = np.zeros(us.size)
    gross_pnl = np.zeros(us.size)
    tc = np.zeros(us.size)
    bc = np.zeros(us.size)
    Pprev = None
    for n, u in enumerate(us):
        a = u - LAG          # CW index for sum_{m<=u-LAG-1}
        b = u - LAG - H
        if b < 0:
            continue
        Pu = (CW[:, a] - CW[:, b]) / H
        if Pprev is None:
            ap, bp = u - 1 - LAG, u - 1 - LAG - H
            Pprev = (CW[:, ap] - CW[:, bp]) / H if bp >= 0 else np.zeros(S)
        g = float(np.dot(Pu, R1[:, u]))
        turn = float(np.abs(Pu - Pprev).sum())
        borrow = float(np.dot(np.maximum(-Pu, 0.0), brate[:, u]) / 252.0)
        gross_pnl[n] = g
        tc[n] = TC_ONEWAY * turn
        bc[n] = borrow
        net[n] = g - tc[n] - borrow
        Pprev = Pu
    return net, gross_pnl, tc, bc


def nw_t(x, lag):
    x = np.asarray(x, float)
    n = x.size
    if n < 30:
        return 0.0, 0.0
    mu = x.mean()
    e = x - mu
    g0 = float(np.dot(e, e) / n)
    var = g0
    for L in range(1, lag + 1):
        gl = float(np.dot(e[L:], e[:-L]) / n)
        var += 2.0 * (1.0 - L / (lag + 1.0)) * gl
    var = max(var, 1e-18)
    se = np.sqrt(var / n)
    return mu / se, se


def run(window, only=None, out=None):
    P = load()
    B = build_bases(P)
    dates = B["dates"]
    d0, d1 = WINDOWS[window]
    j0 = int(np.searchsorted(dates, d0))
    j1 = int(np.searchsorted(dates, d1, side="right")) - 1
    j0 = max(j0, WARMUP + 30)
    print(f"window {window}: {dates[j0]} .. {dates[j1]}  ({j1-j0+1} sessions)", flush=True)

    R = signals(B)
    ids = sorted(R)
    if only:
        ids = [i for i in ids if i in only]
    rows = []
    for sid in ids:
        mech, fn = R[sid]
        W, nuniv, ndays = weights(B, fn, j0 - 40, j1)
        for H in HORIZONS:
            rec = {"id": sid, "mechanism": mech, "H": H, "n_univ": round(nuniv, 1), "n_days_scored": ndays}
            for LAG in LAGS:
                net, g, tc, bc = simulate(B, W, H, LAG, j0, j1)
                nz = net[net != 0]
                t, se = nw_t(net, H + 1)
                tg, _ = nw_t(g, H + 1)
                sh = float(net.mean() / net.std() * np.sqrt(252)) if net.std() > 0 else 0.0
                shg = float(g.mean() / g.std() * np.sqrt(252)) if g.std() > 0 else 0.0
                rec[f"lag{LAG}"] = {
                    "sharpe_net": round(sh, 3), "sharpe_gross": round(shg, 3),
                    "t_nw": round(float(t), 3), "t_nw_gross": round(float(tg), 3),
                    "mean_bp_day": round(float(net.mean()) * 1e4, 4),
                    "cost_bp_day": round(float(tc.mean()) * 1e4, 4),
                    "borrow_bp_day": round(float(bc.mean()) * 1e4, 4),
                    "n": int(net.size), "n_active": int(nz.size),
                }
            l1, l2 = rec["lag1"], rec["lag2"]
            rec["lag_retention"] = round(l2["sharpe_gross"] / l1["sharpe_gross"], 3) if l1["sharpe_gross"] != 0 else 0.0
            rows.append(rec)
            print(f"  {sid} H={H:2d}  gross SR {l1['sharpe_gross']:+.2f} tg {l1['t_nw_gross']:+.2f} | "
                  f"net SR {l1['sharpe_net']:+.2f} t {l1['t_nw']:+.2f} | "
                  f"lag2 grSR {l2['sharpe_gross']:+.2f} ret {rec['lag_retention']:+.2f} | "
                  f"cost {l1['cost_bp_day']:.2f}bp borrow {l1['borrow_bp_day']:.2f}bp", flush=True)
    N = len(rows)
    bar = float(np.sqrt(2 * np.log(max(N, 2))))
    res = {"window": window, "range": [str(dates[j0]), str(dates[j1])], "n_sessions": int(j1 - j0 + 1),
           "n_cells": N, "expected_max_t_under_null": round(bar, 3),
           "promotion_bar": round(bar + 0.5, 3), "rows": rows}
    if out:
        json.dump(res, open(out, "w"), indent=1)
        print("WROTE", out, flush=True)
    return res


if __name__ == "__main__":
    win = sys.argv[1]
    out = None
    only = None
    for i, a in enumerate(sys.argv):
        if a == "--out":
            out = sys.argv[i + 1]
        if a == "--only":
            only = set(sys.argv[i + 1].split(","))
    run(win, only=only, out=out)
