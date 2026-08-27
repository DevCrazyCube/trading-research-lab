#!/usr/bin/env python3
"""INVENT 0822 -- crypto spot with a STRUCTURAL TETHER: the 28-formula sweep.

Every formula fades a deviation from a fair value that is pinned by a real
economic mechanism (issuer redemption, unwrap/withdrawal, same-venue no-arb,
cross-venue arb).  NO sign is fitted: the direction is structural (fade toward
the anchor), so the honest multiple-testing bar is the one-sided sqrt(2 ln N).
NO thresholds are grid-searched: every band is a round number declared a priori.
ZERO formulas are spent on regime conditioners (round-3 lesson 1).
"""
from __future__ import annotations
import os, json
import numpy as np
import invent0822_tether_lib as L
import invent0822_tether_build as B

OUT = "/home/anont/meme/research/trading_bot"
FEE_BP = 10.0          # Binance spot taker, base tier, per leg per side
FEE_SHOCK = 20.0
FEE_LOW = 1.0          # sensitivity: zero-fee stablecoin-pair promos / maker
SPLIT = 20230101       # design < SPLIT ; held-out >= SPLIT   (matches the prior round)


# ----------------------------------------------------------------- primitives
def band_state(dev, enter, exitb, side="both"):
    """Hysteresis band: fade the deviation, hold until it comes back inside."""
    T = dev.size
    w = np.zeros(T)
    st = 0
    for t in range(T):
        d = dev[t]
        if not np.isfinite(d):
            st = 0; w[t] = 0.0; continue
        if st == 0:
            if d > enter and side in ("both", "prem"):
                st = -1
            elif d < -enter and side in ("both", "disc"):
                st = +1
        else:
            if st == 1 and d > -exitb:
                st = 0
            elif st == -1 and d < exitb:
                st = 0
        w[t] = st
    return w


def lin_fade(dev, scale):
    return -np.clip(dev / scale, -1.0, 1.0)


def roll_stat(x, win, fn):
    T = x.size
    out = np.full(T, np.nan)
    for t in range(win, T):
        w = x[t - win:t]
        w = w[np.isfinite(w)]
        if w.size >= win // 2:
            out[t] = fn(w)
    return out


def shift1(w):
    """signal formed at close[t-1] -> weight held over the day-t period."""
    o = np.zeros_like(w); o[1:] = w[:-1]; return o


def shift2(w):
    o = np.zeros_like(w); o[2:] = w[:-2]; return o


# ----------------------------------------------------------------- universes
def stable_universe(P):
    """OBJECTIVE, survivorship-bias-free screen decided on LISTING-WINDOW data only:
    a *USDT pair whose first 60 live days have median price within 2% of 1.00 and
    daily vol < 1%.  Admits UST (which later went to $0.25) by construction."""
    picks = []
    for sym, i in P.bn_syms.items():
        if not sym.endswith("USDT"):
            continue
        v = P.bn(sym, "c")
        idx = np.where(np.isfinite(v))[0]
        if idx.size < 120:
            continue
        w = v[idx[:60]]
        if abs(np.nanmedian(w) - 1.0) <= 0.02 and np.nanstd(np.diff(np.log(w))) < 0.01:
            picks.append(sym)
    return sorted(picks)


# ----------------------------------------------------------------- main
def main():
    P = L.Panels()
    dates = P.dates()
    S, tri, xv = B.build(P)
    T = P.T
    des = dates < SPLIT
    hld = dates >= SPLIT

    formulas = {}   # name -> dict(w=(T,K), ret=(T,K), legs=(K,), fam, note)

    # ================= FAMILY A : stablecoin peg (fair = $1, redemption anchor)
    stab = stable_universe(P)
    K = len(stab)
    devA = np.full((T, K), np.nan); rA = np.full((T, K), np.nan)
    rAc = np.full((T, K), np.nan); qvA = np.full((T, K), np.nan)
    for j, sym in enumerate(stab):
        c = P.bn(sym, "c"); o = P.bn(sym, "o"); qv = P.bn(sym, "qv")
        devA[:, j] = np.log(c)
        rA[:-1, j] = np.log(o[1:] / o[:-1])
        rAc[:-1, j] = np.log(c[1:] / c[:-1])
        qvA[:, j] = qv
    legsA = np.ones(K)
    bp = 1e-4

    def addA(name, wraw, note=""):
        formulas[name] = dict(w=L.normalize_eq(np.apply_along_axis(shift1, 0, wraw)),
                              w_lag=L.normalize_eq(np.apply_along_axis(shift2, 0, wraw)),
                              ret=rA, legs=legsA, fam="A", note=note, K=K)

    addA("A1_PEG_LIN20", lin_fade(devA, 20 * bp), "linear fade, full size at 20bp")
    addA("A2_PEG_BAND20", np.column_stack([band_state(devA[:, j], 20 * bp, 5 * bp) for j in range(K)]),
         "enter 20bp / exit 5bp")
    addA("A3_PEG_BAND50", np.column_stack([band_state(devA[:, j], 50 * bp, 15 * bp) for j in range(K)]),
         "enter 50bp / exit 15bp")
    addA("A4_PEG_BAND100", np.column_stack([band_state(devA[:, j], 100 * bp, 25 * bp) for j in range(K)]),
         "enter 100bp / exit 25bp")
    addA("A5_PEG_DISC_ONLY", np.column_stack([band_state(devA[:, j], 20 * bp, 5 * bp, "disc") for j in range(K)]),
         "buy the discount only (arb = buy cheap, redeem at $1)")
    addA("A6_PEG_PREM_ONLY", np.column_stack([band_state(devA[:, j], 20 * bp, 5 * bp, "prem") for j in range(K)]),
         "sell the premium only (arb = mint at $1, sell rich)")
    z90 = np.full((T, K), np.nan)
    for j in range(K):
        m = roll_stat(devA[:, j], 90, np.mean); sd = roll_stat(devA[:, j], 90, np.std)
        z90[:, j] = (devA[:, j] - m) / np.where(sd > 1e-6, sd, np.nan)
    addA("A7_PEG_Z90_FITTEDMEAN", -np.clip(np.nan_to_num(z90) / 2.0, -1, 1),
         "CONTRAST: fitted 90d mean instead of the $1 anchor")
    xsd = devA - np.nanmean(np.where(np.isfinite(devA), devA, np.nan), axis=1, keepdims=True)
    addA("A8_PEG_XS_DEMEAN", lin_fade(np.nan_to_num(xsd, nan=0.0) * np.isfinite(devA), 20 * bp),
         "cross-sectional demean (strips the common USDT factor)")
    ddev = np.full((T, K), np.nan); ddev[1:] = devA[1:] - devA[:-1]
    ev = np.zeros((T, K))
    for j in range(K):
        hold = 0; sgn = 0
        for t in range(T):
            if hold > 0:
                ev[t, j] = sgn; hold -= 1; continue
            if np.isfinite(ddev[t, j]) and abs(ddev[t, j]) > 50 * bp:
                sgn = -np.sign(devA[t, j]); hold = 4; ev[t, j] = sgn
    addA("A9_PEG_EVENT5", ev, "after a >50bp one-day peg move: fade, hold 5d fixed")
    addA("A10_PEG_SQRT", -np.sign(np.nan_to_num(devA)) * np.minimum(1.0, np.sqrt(np.abs(np.nan_to_num(devA)) / (20 * bp))),
         "concave (sqrt) sizing in the deviation")
    b20 = np.column_stack([band_state(devA[:, j], 20 * bp, 5 * bp) for j in range(K)])
    lw = np.where(np.abs(b20) > 0, np.nan_to_num(qvA), 0.0)
    lw = lw / np.maximum(lw.sum(axis=1, keepdims=True), 1e-9)
    formulas["A11_PEG_BAND20_LIQW"] = dict(
        w=np.apply_along_axis(shift1, 0, np.sign(b20) * lw),
        w_lag=np.apply_along_axis(shift2, 0, np.sign(b20) * lw),
        ret=rA, legs=legsA, fam="A", K=K,
        note="enter 20bp, sized by trailing $volume share instead of equally")
    age = np.cumsum(np.isfinite(devA), axis=0)
    addA("A12_PEG_BAND20_SEASONED", b20 * (age >= 250),
         "enter 20bp, only issuers with >=250 days of quoted history")

    # A13: the peg trade is short a solvency put -- cap it structurally.
    w13 = np.zeros((T, K))
    for j in range(K):
        st = 0
        for t in range(T):
            d = devA[t, j]
            if not np.isfinite(d):
                st = 0; w13[t, j] = 0; continue
            if st == 0:
                if abs(d) > 20 * bp and abs(d) < 300 * bp:
                    st = -int(np.sign(d))
            else:
                if abs(d) < 5 * bp or abs(d) > 300 * bp:
                    st = 0
            w13[t, j] = st
    addA("A13_PEG_BAND20_SOLVSTOP", w13,
         "enter 20bp, HARD STOP if the deviation exceeds 300bp (issuer-solvency repricing)")

    w14 = np.zeros((T, K))
    for j in range(K):
        hold = 0; sgn = 0
        for t in range(T):
            if hold > 0:
                w14[t, j] = sgn if np.isfinite(devA[t, j]) else 0; hold -= 1; continue
            if np.isfinite(devA[t, j]) and abs(devA[t, j]) > 20 * bp:
                sgn = -np.sign(devA[t, j]); hold = 9; w14[t, j] = sgn
    addA("A14_PEG_HOLD10", w14, "enter 20bp, exit on a fixed 10-day clock (not on the level)")

    sd60 = np.full((T, K), np.nan)
    for j in range(K):
        sd60[:, j] = roll_stat(devA[:, j], 60, np.std)
    hyb = -np.clip(np.nan_to_num(devA / np.where(sd60 > 1e-6, sd60, np.nan)) / 2.0, -1, 1)
    addA("A15_PEG_ANCHOR_FITSCALE", hyb,
         "$1 anchor for the MEAN, fitted 60d sd for the SIZE (hybrid vs A7)")

    # ================= FAMILY B : wrapped / staked vs underlying
    def add1(name, dev, ret, legs, fam, note, w=None):
        wr = lin_fade(dev, 30 * bp) if w is None else w
        wr = np.nan_to_num(wr)[:, None]
        formulas[name] = dict(w=np.apply_along_axis(shift1, 0, wr),
                              w_lag=np.apply_along_axis(shift2, 0, wr),
                              ret=ret[:, None], legs=np.array([legs], float),
                              fam=fam, note=note, K=1)

    if "B:WBTCUSDT" in S:
        v = S["B:WBTCUSDT"]
        add1("B1_WBTC_LIN30", v["dev_c"], v["ret_o"], 2, "B", "wBTC/BTC parity, linear fade at 30bp")
        add1("B2_WBTC_BAND30", None, v["ret_o"], 2, "B", "wBTC/BTC enter 30bp / exit 10bp",
             w=band_state(v["dev_c"], 30 * bp, 10 * bp))
        add1("B3_WBTC_DISC_ONLY", None, v["ret_o"], 2, "B",
             "buy wBTC only at a discount (unwrap to BTC is the arb)",
             w=band_state(v["dev_c"], 30 * bp, 10 * bp, "disc"))
    if "B:WBETHUSDT" in S:
        v = S["B:WBETHUSDT"]
        r = v["dev_c"]
        cm = np.full(T, np.nan)
        run = -np.inf
        for t in range(T):
            if np.isfinite(r[t]):
                run = max(run, r[t]); cm[t] = run
        devcm = r - cm       # <= 0 : wBETH below its accrued fair value
        add1("B4_WBETH_CUMMAX", None, v["ret_o"], 2, "B",
             "fair = running max of the accrual ratio; buy 30bp below it",
             w=band_state(devcm + 0.0, 30 * bp, 10 * bp, "disc"))
        tr = np.full(T, np.nan)
        for t in range(60, T):
            y = r[t - 60:t]
            ok = np.isfinite(y)
            if ok.sum() >= 40:
                x = np.arange(60)[ok]
                A = np.column_stack([np.ones(x.size), x])
                b, *_ = np.linalg.lstsq(A, y[ok], rcond=None)
                tr[t] = b[0] + b[1] * 60
        add1("B5_WBETH_TREND60", r - tr, v["ret_o"], 2, "B",
             "fair = 60d accrual-trend extrapolation, linear fade at 30bp")
    if "B:BNSOLUSDT" in S:
        v = S["B:BNSOLUSDT"]
        r = v["dev_c"]
        cm = np.full(T, np.nan); run = -np.inf
        for t in range(T):
            if np.isfinite(r[t]):
                run = max(run, r[t]); cm[t] = run
        add1("B8_BNSOL_CUMMAX", None, v["ret_o"], 2, "B",
             "BNSOL/SOL: fair = running max of the accrual ratio; buy 30bp below it",
             w=band_state(r - cm, 30 * bp, 10 * bp, "disc"))
        tr = np.full(T, np.nan)
        for t in range(60, T):
            y = r[t - 60:t]; ok = np.isfinite(y)
            if ok.sum() >= 40:
                x = np.arange(60)[ok]
                A = np.column_stack([np.ones(x.size), x])
                b, *_ = np.linalg.lstsq(A, y[ok], rcond=None)
                tr[t] = b[0] + b[1] * 60
        add1("B9_BNSOL_TREND60", r - tr, v["ret_o"], 2, "B",
             "BNSOL/SOL: fair = 60d accrual-trend extrapolation, linear fade at 30bp")
    if "B:XAUTUSDT" in S:
        v = S["B:XAUTUSDT"]
        add1("B10_GOLDTOKEN_RV", v["dev_c"], v["ret_o"], 2, "B",
             "XAUT vs PAXG: two independently redeemable 1-oz gold claims, parity fade at 30bp")
    if "B:BETHUSDT" in S:
        v = S["B:BETHUSDT"]
        add1("B6_BETH_LIN30", v["dev_c"], v["ret_o"], 2, "B",
             "BETH/ETH parity fade (withdrawal anchor opened at Shapella)")
    if "B1_WBTC_LIN30" in formulas and "B4_WBETH_CUMMAX" in formulas:
        wa = formulas["B2_WBTC_BAND30"]; wb = formulas["B4_WBETH_CUMMAX"]
        formulas["B7_WRAP_BOOK"] = dict(
            w=L.normalize_eq(np.column_stack([wa["w"][:, 0], wb["w"][:, 0]])),
            w_lag=L.normalize_eq(np.column_stack([wa["w_lag"][:, 0], wb["w_lag"][:, 0]])),
            ret=np.column_stack([S["B:WBTCUSDT"]["ret_o"], S["B:WBETHUSDT"]["ret_o"]]),
            legs=np.array([2.0, 2.0]), fam="B", K=2,
            note="joint wrapped book: wBTC band + wBETH cummax")

    # ================= FAMILY C : triangular cross-quote (same venue, same instant)
    for tag in ("USDC", "TRY"):
        g = tri[tag]["gap"]; ro = tri[tag]["ro"]
        mv = np.nanmedian(np.where(np.isfinite(tri[tag]["qv"]), tri[tag]["qv"], np.nan), axis=1)
        keep = np.argsort(-np.nan_to_num(mv))[:40]
        g = g[keep].T; ro = ro[keep].T          # (T, k)
        k = g.shape[1]
        gd = g - np.nanmean(np.where(np.isfinite(g), g, np.nan), axis=1, keepdims=True)
        formulas[f"C1_TRI_{tag}_XS"] = dict(
            w=L.normalize_eq(np.apply_along_axis(shift1, 0, lin_fade(np.nan_to_num(gd) * np.isfinite(g), 10 * bp))),
            w_lag=L.normalize_eq(np.apply_along_axis(shift2, 0, lin_fade(np.nan_to_num(gd) * np.isfinite(g), 10 * bp))),
            ret=ro, legs=np.full(k, 2.0), fam="C", K=k,
            note=f"per-coin {tag}-vs-USDT no-arb gap, XS-demeaned, fade at 10bp")
        wb_ = np.column_stack([band_state(g[:, j], 30 * bp, 10 * bp) for j in range(k)])
        formulas[f"C2_TRI_{tag}_BAND30"] = dict(
            w=L.normalize_eq(np.apply_along_axis(shift1, 0, wb_)),
            w_lag=L.normalize_eq(np.apply_along_axis(shift2, 0, wb_)),
            ret=ro, legs=np.full(k, 2.0), fam="C", K=k,
            note=f"per-coin {tag} no-arb gap, enter 30bp / exit 10bp")
        agg = np.nanmedian(np.where(np.isfinite(g), g, np.nan), axis=1)
        if tag == "USDC":
            tr_c, tr_o = P.bn("USDCUSDT", "c"), P.bn("USDCUSDT", "o")
            sgn = -1.0   # gap>0 => X rich in USDT => USDC cheap in USDT terms => buy USDCUSDT
        else:
            tr_c, tr_o = P.xq("USDTTRY", "c"), P.xq("USDTTRY", "o")
            sgn = +1.0
        rr = np.full(T, np.nan); rr[:-1] = np.log(tr_o[1:] / tr_o[:-1])
        add1(f"C3_TRI_{tag}_AGG", None, rr, 1, "C",
             f"basket-implied {tag} stable price vs the quoted pair, enter 10bp / exit 3bp",
             w=sgn * band_state(agg, 10 * bp, 3 * bp))

    # ================= FAMILY D : cross-venue same asset (Coinbase vs Binance)
    nb = xv["nb"]; rc = xv["rc"]
    mv = np.nanmedian(np.where(np.isfinite(xv["qv"]), xv["qv"], np.nan), axis=1)
    keep = np.argsort(-np.nan_to_num(mv))[:30]
    nbk = nb[keep].T; rck = rc[keep].T
    k = nbk.shape[1]
    formulas["D1_XV_NUMNEUT_LIN"] = dict(
        w=L.normalize_eq(np.apply_along_axis(shift1, 0, lin_fade(np.nan_to_num(nbk) * np.isfinite(nbk), 30 * bp))),
        w_lag=L.normalize_eq(np.apply_along_axis(shift2, 0, lin_fade(np.nan_to_num(nbk) * np.isfinite(nbk), 30 * bp))),
        ret=rck, legs=np.full(k, 2.0), fam="D", K=k,
        note="Coinbase-vs-Binance basis, BTC-numeraire-neutral, linear fade at 30bp")
    wb_ = np.column_stack([band_state(nbk[:, j], 50 * bp, 15 * bp) for j in range(k)])
    formulas["D2_XV_NUMNEUT_BAND50"] = dict(
        w=L.normalize_eq(np.apply_along_axis(shift1, 0, wb_)),
        w_lag=L.normalize_eq(np.apply_along_axis(shift2, 0, wb_)),
        ret=rck, legs=np.full(k, 2.0), fam="D", K=k,
        note="cross-venue numeraire-neutral basis, enter 50bp / exit 15bp")
    nbd = nbk - np.nanmean(np.where(np.isfinite(nbk), nbk, np.nan), axis=1, keepdims=True)
    formulas["D3_XV_XS"] = dict(
        w=L.normalize_eq(np.apply_along_axis(shift1, 0, lin_fade(np.nan_to_num(nbd) * np.isfinite(nbk), 30 * bp))),
        w_lag=L.normalize_eq(np.apply_along_axis(shift2, 0, lin_fade(np.nan_to_num(nbd) * np.isfinite(nbk), 30 * bp))),
        ret=rck, legs=np.full(k, 2.0), fam="D", K=k,
        note="cross-venue basis, XS-demeaned across coins")
    uu = xv["usdt_usd"]                       # log(USDT/USD) implied by BTC across venues
    ucusd_o = P.bn("USDCUSDT", "o")
    rr = np.full(T, np.nan); rr[:-1] = np.log(ucusd_o[1:] / ucusd_o[:-1])
    add1("D4_XV_USDT_IMPLIED", None, rr, 1, "D",
         "cross-venue-implied USDT/USD deviation from $1, executed on the USDCUSDT pair",
         w=band_state(uu, 30 * bp, 10 * bp))
    add1("D5_XV_USDT_IMPLIED_LIN", uu, rr, 1, "D",
         "same cross-venue USDT/USD signal, linear fade at 30bp instead of a band")

    # ================================================================= scoring
    rows = []
    pnl_des, pnl_des_gross, dmasks = [], [], []
    idxT = np.arange(T)
    for name, f in formulas.items():
        r = dict(name=name, fam=f["fam"], K=f["K"], note=f.get("note", ""))
        bk = L.book_pnl(f["w"], f["ret"], f["legs"], FEE_BP)
        bkl = L.book_pnl(f["w_lag"], f["ret"], f["legs"], FEE_BP)
        bks = L.book_pnl(f["w"], f["ret"], f["legs"], FEE_SHOCK)
        bkw = L.book_pnl(f["w"], f["ret"], f["legs"], FEE_LOW)
        # ---- window: fixed calendar split when the data spans it, else own 60/40
        live = np.any(np.isfinite(f["ret"]), axis=1)
        li = np.where(live)[0]
        d_msk, h_msk = live & des, live & hld
        if d_msk.sum() >= 250 and h_msk.sum() >= 250:
            r["split"] = "calendar-2023-01-01"
        else:
            cut = li[int(0.60 * li.size)]
            d_msk = live & (idxT < cut); h_msk = live & (idxT >= cut)
            r["split"] = f"own-60/40@{int(dates[cut])}"
        r["design_from"] = int(dates[np.where(d_msk)[0][0]]) if d_msk.sum() else None
        r["design_to"] = int(dates[np.where(d_msk)[0][-1]]) if d_msk.sum() else None
        r["held_from"] = int(dates[np.where(h_msk)[0][0]]) if h_msk.sum() else None
        r["held_to"] = int(dates[np.where(h_msk)[0][-1]]) if h_msk.sum() else None
        for tag, msk in (("D", d_msk), ("H", h_msk)):
            g = L.stats(bk["gross"], msk); n = L.stats(bk["net"], msk)
            r[tag + "gr"] = g["sharpe"]; r[tag + "gt"] = g["t"]
            r[tag + "net"] = n["sharpe"]; r[tag + "nt"] = n["t"]
            r[tag + "n"] = g["n"]
            r[tag + "mean_gross_bp"] = g.get("mean_bp")
            tu = float(np.mean(bk["turn"][msk]))
            r[tag + "turn"] = round(tu, 4)
            r[tag + "BE_bp"] = round(g["mean_bp"] / tu, 2) if tu > 1e-9 and np.isfinite(g.get("mean_bp", np.nan)) else None
            r[tag + "net20"] = L.stats(bks["net"], msk)["sharpe"]
            r[tag + "net1"] = L.stats(bkw["net"], msk)["sharpe"]
            r[tag + "lag_net"] = L.stats(bkl["net"], msk)["sharpe"]
            r[tag + "days_on"] = round(float(np.mean(np.abs(f["w"][msk]).sum(axis=1) > 0)), 3)
        r["tail_design"] = L.tail_stats(bk["net"], d_msk)
        r["tail_held"] = L.tail_stats(bk["net"], h_msk)
        rows.append(r)
        pnl_des.append(bk["net"])
        pnl_des_gross.append(bk["gross"])
        dmasks.append(d_msk)

    N = len(rows)
    # The multiple-testing null is scored on GROSS P&L: cost is a deterministic
    # drag, and sign-flipping a series with a big negative drift manufactures a
    # huge |Sharpe| in every replicate, which would inflate the bar (lesson 2 also
    # says the bar must be cleared on GROSS first).
    nb_boot = L.block_signflip_maxsharpe_masks(pnl_des_gross, dmasks, nrep=2000, block=10)
    nb_boot_net = L.block_signflip_maxsharpe_masks(pnl_des, dmasks, nrep=2000, block=10)
    ndes = int(np.median([m.sum() for m in dmasks]))
    se = float(np.sqrt(365.0 / max(ndes, 1)))
    seA = float(np.sqrt(365.0 / max(int(dmasks[0].sum()), 1)))
    bar = dict(N=N, median_design_days=ndes,
               bootstrap_max_abs_sharpe_GROSS=nb_boot,
               bootstrap_max_abs_sharpe_net=nb_boot_net,
               se_one_formula=round(se, 3), se_familyA=round(seA, 3),
               analytic_1sided=round(float(np.sqrt(2 * np.log(N)) * se), 3),
               analytic_2sided=round(float(np.sqrt(2 * np.log(2 * N)) * se), 3),
               analytic_1sided_famA=round(float(np.sqrt(2 * np.log(N)) * seA), 3),
               programme_cumulative_959=round(float(np.sqrt(2 * np.log(959)) * se), 3))

    # ---- how many INDEPENDENT depeg episodes does each window actually contain?
    epi = {"design": 0, "held": 0, "detail": []}
    for j, sym in enumerate(stab):
        dv = devA[:, j]
        big = np.isfinite(dv) & (np.abs(dv) > 100 * bp)
        t = 0
        while t < T:
            if big[t]:
                t0 = t
                last = t
                while t < T and (t - last) <= 30:
                    if big[t]:
                        last = t
                    t += 1
                epi["detail"].append(dict(sym=sym, start=int(dates[t0]), end=int(dates[last]),
                                          peak_bp=round(float(np.nanmax(np.abs(dv[t0:last + 1]))) * 1e4, 1)))
                epi["design" if dates[t0] < SPLIT else "held"] += 1
            else:
                t += 1

    # ---- attribution: how much of family A is the single UST catastrophe?
    attrib = {}
    if "USTUSDT" in stab:
        ju = stab.index("USTUSDT")
        for nm in ("A2_PEG_BAND20", "A12_PEG_BAND20_SEASONED", "A13_PEG_BAND20_SOLVSTOP",
                   "A5_PEG_DISC_ONLY"):
            f = formulas[nm]
            w2 = f["w"].copy(); w2[:, ju] = 0.0   # UST simply never traded; others unchanged
            b2 = L.book_pnl(w2, f["ret"], f["legs"], FEE_BP)
            b0 = L.book_pnl(f["w"], f["ret"], f["legs"], FEE_BP)
            live = np.any(np.isfinite(f["ret"]), axis=1)
            m = live & des
            wf = f["w"]
            ust_days = int(np.sum(np.abs(wf[:, ju]) > 0))
            ust_pnl = float(np.nansum(np.where(np.isfinite(f["ret"][:, ju]),
                                               wf[:, ju] * f["ret"][:, ju], 0.0)) * 1e4)
            attrib[nm] = dict(design_net_with_UST=L.stats(b0["net"], m)["sharpe"],
                              design_net_without_UST=L.stats(b2["net"], m)["sharpe"],
                              days_positioned_in_UST=ust_days,
                              total_UST_leg_pnl_bp=round(ust_pnl, 1))

    diags = json.load(open(os.path.join(OUT, "INVENT_0822_crypto_tether_DIAG.json")))
    res = dict(theme="crypto spot, structural tether", date="2026-08-22",
               split=SPLIT, fee_bp=FEE_BP, stable_universe=stab,
               n_formulas=N, noise_bar=bar, ust_attribution=attrib,
               depeg_episodes=epi, formulas=rows, diagnostics=diags)
    with open(os.path.join(OUT, "INVENT_0822_crypto_tether.json"), "w") as fh:
        json.dump(res, fh, indent=1, default=float)

    rows.sort(key=lambda r: -(r["Dnet"] if r["Dnet"] == r["Dnet"] else -9))
    hdr = (f"{'formula':26s} {'f':1s} {'Dgr':>6s} {'Dnet':>6s} {'Dt':>6s} {'Hgr':>6s} "
           f"{'Hnet':>6s} {'Ht':>6s} {'BEd':>7s} {'BEh':>7s} {'turn':>6s} {'on':>5s} {'lagD':>6s}")
    print(hdr); print("-" * len(hdr))
    for r in rows:
        fmt = lambda v: (f"{v:6.2f}" if isinstance(v, float) and v == v else "   nan")
        be = lambda v: (f"{v:7.1f}" if v is not None and v == v else "    nan")
        print(f"{r['name']:26s} {r['fam']:1s} {fmt(r['Dgr'])} {fmt(r['Dnet'])} {fmt(r['Dnt'])} "
              f"{fmt(r['Hgr'])} {fmt(r['Hnet'])} {fmt(r['Hnt'])} "
              f"{be(r['DBE_bp'])} {be(r['HBE_bp'])} "
              f"{r['Dturn']:6.3f} {r['Ddays_on']:5.2f} {fmt(r['Dlag_net'])}")
    print()
    print("N formulas:", N, " noise bar:", json.dumps(bar))
    print("stablecoin universe:", stab)
    print("depeg episodes (>100bp, 30d-separated):", epi["design"], "design /", epi["held"], "held-out")
    for e in epi["detail"]:
        print("   ", e)
    print("UST attribution:", json.dumps(attrib, indent=1))
    for r in rows:
        if r["name"] in ("A12_PEG_BAND20_SEASONED", "A2_PEG_BAND20", "A6_PEG_PREM_ONLY",
                         "A3_PEG_BAND50", "D4_XV_USDT_IMPLIED"):
            print(r["name"], "D-tail", r["tail_design"], "| H-tail", r["tail_held"])


if __name__ == "__main__":
    main()
