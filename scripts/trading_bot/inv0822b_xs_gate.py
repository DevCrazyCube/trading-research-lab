#!/usr/bin/env python3
"""STEP 1 of INVENT 0822B -- the rho1(bounce) gate, run BEFORE any P&L is computed.

For a cross-sectional book ranked on trailing RETURNS, the object that bid-ask bounce
corrupts is the coin's own daily return series: a bounced price series has rho1(r) -> -0.5
and a "reversal" signal built on it is just fading the half-spread.  The gate is therefore
run per coin on the return series each family consumes, and on the price the book is
EXECUTED at.  Gate: mean rho1 > -0.35.

Also runs the harness self-test (a synthetic panel with a planted cross-sectional effect,
and a pure-bounce panel with no effect at all).
"""
from __future__ import annotations
import json, sys, numpy as np
sys.path.insert(0, "/home/anont/meme/scripts/trading_bot")
from inv0822b_xs_lib import (load, features, universe, fwd_ret, fwd_ret_px,
                             extremes_book, tranche, evaluate, sharpe, rho1, shift,
                             breakeven_bp, ANN)

OUT = "/home/anont/meme/research/trading_bot/INVENT_0822B_cryptoXS_GATE.json"


def main():
    P = load(); F = features(P); U = universe(P, F)
    S, T = U.shape
    res = {}

    # ---------------- rho1 per coin, close vs vwap, weighted by universe days -------
    for tag, key in (("close_to_close", "r_c"), ("vwap_to_vwap", "r_v")):
        r = F[key]
        vals, wts = [], []
        for s in range(S):
            days = U[s]
            if days.sum() < 120:
                continue
            x = np.where(days, r[s], np.nan)
            v = rho1(x)
            if np.isfinite(v):
                vals.append(v); wts.append(days.sum())
        vals = np.array(vals); wts = np.array(wts, float)
        res[f"rho1_{tag}"] = dict(
            n_coins=int(vals.size),
            mean=float(vals.mean()), wmean=float((vals * wts).sum() / wts.sum()),
            median=float(np.median(vals)),
            p05=float(np.percentile(vals, 5)), p95=float(np.percentile(vals, 95)),
            frac_below_m035=float((vals < -0.35).mean()),
        )

    # rho1 by liquidity tercile (bounce should be worst in the thin names)
    adv = np.where(U, F["qv"], np.nan)
    madv = np.nanmedian(np.where(U, adv, np.nan), axis=1)
    ok = np.isfinite(madv) & (U.sum(1) >= 120)
    idx = np.where(ok)[0]
    order = idx[np.argsort(madv[idx])]
    terc = {}
    for name, sl in (("thin", order[:len(order) // 3]),
                     ("mid", order[len(order) // 3:2 * len(order) // 3]),
                     ("thick", order[2 * len(order) // 3:])):
        for tag, key in (("close", "r_c"), ("vwap", "r_v")):
            v = [rho1(np.where(U[s], F[key][s], np.nan)) for s in sl]
            v = np.array([x for x in v if np.isfinite(x)])
            terc[f"{name}_{tag}"] = dict(n=int(v.size), mean=float(v.mean()),
                                         median=float(np.median(v)),
                                         adv_median=float(np.nanmedian(madv[sl])))
    res["rho1_by_liquidity_tercile"] = terc

    # ---------------- the decisive execution test ---------------------------------
    # A one-day cross-sectional reversal signal, built on CLOSES and on VWAPs, executed
    # three ways.  If the gross P&L only exists when signal price == execution price,
    # it is the half-spread being measured, not an effect.
    rv_fwd = fwd_ret(F)
    rc_fwd = fwd_ret_px(F["c"])
    ro_fwd = fwd_ret_px(np.where(np.isfinite(F["c"]), P["o"].astype(np.float64), np.nan))
    tbl = {}
    for sig_tag, lp in (("close", F["lc"]), ("vwap", F["lvw"])):
        sig = shift(-(lp - shift(lp, 1)), 1)          # -r(t-1), known at close t-1
        w = extremes_book(sig, U)
        for ex_tag, rr in (("close_to_close", rc_fwd), ("open_to_open", ro_fwd),
                           ("vwap_to_vwap", rv_fwd)):
            g, nt, dw = evaluate(w, rr)
            tbl[f"sig_{sig_tag}__exec_{ex_tag}"] = dict(
                gross_sharpe=sharpe(g), net_sharpe=sharpe(nt),
                turnover=float(dw.mean()), breakeven_bp=breakeven_bp(g, dw))
    res["one_day_reversal_signal_x_execution"] = tbl

    # ---------------- self-test ----------------------------------------------------
    rng = np.random.default_rng(11)
    n, tt = 60, 1600
    # (a) planted effect: tomorrow's return contains +8bp * yesterday's rank
    base = rng.normal(0, 0.04, (n, tt))
    lp = np.cumsum(base, axis=1)
    Us = np.ones((n, tt), bool); Us[:, -1] = False
    sig_true = shift(base, 1)
    r_plant = base.copy()
    rk = np.zeros((n, tt))
    for t in range(1, tt):
        v = sig_true[:, t]
        m = np.isfinite(v)
        if m.sum() < 10:
            continue
        o = np.argsort(np.argsort(v[m])).astype(float)
        rk[m, t] = (o - o.mean()) / max(o.std(), 1e-9)
    r_plant = base + 0.0008 * rk
    w = extremes_book(shift(base, 1), Us)
    g, ntt, dw = evaluate(w, r_plant)
    st = dict(planted_gross_sharpe=sharpe(g), planted_net_sharpe=sharpe(ntt),
              planted_turnover=float(dw.mean()))
    # (b) pure bid-ask bounce: true price is a random walk, observed price flips side.
    #     half-spread sized so rho1(observed returns) ~ -0.35, i.e. a genuinely
    #     bounce-dominated series with NO real effect in it.
    true_lp = np.cumsum(rng.normal(0, 0.03, (n, tt)), axis=1)
    hs = 0.022
    obs = true_lp + hs * rng.choice([-1.0, 1.0], size=(n, tt))
    r_obs = np.diff(obs, axis=1, prepend=np.nan)
    rfwd = np.full((n, tt), np.nan)
    rfwd[:, :-1] = np.exp(obs[:, 1:] - obs[:, :-1]) - 1.0
    # WITH the one-day gap this harness enforces (signal <= close t-1, entry day t)
    wb = extremes_book(shift(-r_obs, 1), Us)
    gb, nb, dwb = evaluate(wb, rfwd)
    st.update(bounce_gross_sharpe_gap1=sharpe(gb), bounce_net_sharpe_gap1=sharpe(nb),
              bounce_rho1=float(np.mean([rho1(r_obs[i]) for i in range(n)])),
              bounce_breakeven_bp_gap1=breakeven_bp(gb, dwb))
    # WITHOUT the gap (signal price == execution price) -- what the gap protects against
    wb0 = extremes_book(-r_obs, Us)
    gb0, nb0, dwb0 = evaluate(wb0, rfwd)
    st.update(bounce_gross_sharpe_gap0=sharpe(gb0),
              bounce_breakeven_bp_gap0=breakeven_bp(gb0, dwb0))
    # (b2) time-averaged (VWAP-like) prices on a pure random walk: manufactures fake
    #      MOMENTUM at lag 1.  Does the one-day gap protect against that too?
    intr = rng.normal(0, 0.03 / np.sqrt(24), (n, tt * 24))
    lvl = np.cumsum(intr, axis=1).reshape(n, tt, 24)   # ONE continuous intraday path
    avg = lvl.mean(2)
    r_avg = np.diff(avg, axis=1, prepend=np.nan)
    rfa = np.full((n, tt), np.nan)
    rfa[:, :-1] = np.exp(avg[:, 1:] - avg[:, :-1]) - 1.0
    wa = extremes_book(shift(r_avg, 1), Us)
    ga, na, dwa = evaluate(wa, rfa)
    st.update(avgprice_rho1=float(np.mean([rho1(r_avg[i]) for i in range(n)])),
              avgprice_mom_gross_gap1=sharpe(ga),
              avgprice_mom_gross_gap0=sharpe(evaluate(extremes_book(r_avg, Us), rfa)[0]))
    # (c) no-effect control
    wc = extremes_book(shift(rng.normal(0, 1, (n, tt)), 1), Us)
    gc, nc, _ = evaluate(wc, base)
    st.update(control_gross_sharpe=sharpe(gc))
    res["self_test"] = st

    res["universe"] = dict(mean_size=float(U.sum(0).mean()),
                           coins_ever=int(U.any(1).sum()),
                           first_day=str(P["dates"][np.argmax(U.sum(0) > 0)]),
                           n_days=int(T))
    with open(OUT, "w") as f:
        json.dump(res, f, indent=1, default=float)
    print(json.dumps(res, indent=1, default=float)[:4000])


if __name__ == "__main__":
    main()
