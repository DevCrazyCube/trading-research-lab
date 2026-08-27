#!/usr/bin/env python3
"""D0821 invention sweep -- theme: CRYPTO SPOT cross-sectional (Binance spot daily klines).

Families
  A  cross-sectional price structure (reversal / idiosyncratic momentum)     5
  B  spot taker-flow microstructure (taker-buy share, ticket size, counts)   6
  C  BTC-dominance / alt rotation (dollar-neutral alt-vs-BTC leg)            4
  D  volume & volatility structure                                          5
  F  stablecoin peg deviation on Binance spot                                2
  G  spot listing-age dynamics                                              3
  E  cross-quote dispersion (TRY / USDC vs USDT)  -- added by xspot_sweep_e   3

Nothing here is a regime conditioner or gate (round-3 proved those are noise).
"""
from __future__ import annotations
import json, os, sys
import numpy as np

sys.path.insert(0, "/home/anont/meme/scripts/trading_bot")
from xspot_lib import (CACHE, ANN, load_panel, roll_mean, roll_sum, roll_std, shift,
                       zscore_ts, build_universe, fwd_open_ret, xs_weights,
                       xs_weights_from_mask, tranche, evaluate, sharpe, tstat,
                       breakeven_bp, STABLE_BASES)

DESIGN = ("2019-01-01", "2023-01-01")
HELDOUT = ("2023-01-01", "2026-08-01")
FEE = 10.0        # bp of traded notional, Binance spot taker
FEE_SHOCK = 20.0
TOPN = 50


def dayidx(days, iso):
    import datetime as dt
    ms = int(dt.datetime.fromisoformat(iso).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    return int(np.searchsorted(days, ms))


def safe_div(a, b):
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(np.abs(b) > 0, a / b, np.nan)
    return out.astype(np.float32)


def build_signals(P, univ):
    """Return list of (name, family, weights (S,T), tag) -- column t uses data <= t-1."""
    syms = list(P["syms"])
    c, o, h, l = P["c"], P["o"], P["h"], P["l"]
    qv, n, tbq, v = P["qv"], P["n"], P["tbq"], P["v"]
    S, T = c.shape
    alive = np.isfinite(c) & (c > 0)
    cprev = shift(c, 1)
    ret1 = safe_div(c - cprev, cprev)
    ret1[np.abs(ret1) > 3] = np.nan
    lr = np.log1p(np.clip(ret1, -0.95, 5.0)).astype(np.float32)

    ibtc = syms.index("BTCUSDT")
    lrb = lr[ibtc]
    out = []

    def add(name, fam, w, tag=""):
        out.append((name, fam, np.nan_to_num(w), tag))

    def xs(name, fam, raw, tag=""):
        add(name, fam, xs_weights(shift(raw.astype(np.float32), 1), univ), tag)

    # ---------------- family A : cross-sectional price structure
    sig20 = roll_std(lr, 20)
    xs("A1_XS_REV1", "A", -ret1, "1-day cross-sectional reversal (control)")
    xs("A2_XS_REV_VOLADJ", "A", -safe_div(ret1, sig20), "vol-normalised 1-day reversal")
    qv20 = roll_mean(qv, 20)
    volsup = safe_div(qv, qv20)                 # today's volume vs its own 20d norm
    xs("A3_XS_REV_UNSUP", "A", -safe_div(ret1, np.sqrt(np.maximum(volsup, 0.05))),
       "fade 1-day moves that were NOT supported by volume")
    # idiosyncratic 28d momentum: residual of 28d return to 60d BTC beta
    cov = roll_mean(lr * lrb[None, :], 60) - roll_mean(lr, 60) * roll_mean(lrb[None, :], 60)
    varb = roll_mean((lrb * lrb)[None, :], 60) - roll_mean(lrb[None, :], 60) ** 2
    beta = safe_div(cov, varb)
    r28 = roll_sum(lr, 28)
    r28b = roll_sum(lrb[None, :], 28)
    xs("A4_XS_IDIOMOM28", "A", r28 - beta * r28b, "28d return residual to trailing BTC beta")
    xs("A5_XS_ACCEL", "A", roll_sum(lr, 7) - roll_sum(lr, 28) / 4.0,
       "momentum acceleration: 7d minus a quarter of 28d")
    xs("A6_XS_REV5", "A", -roll_sum(lr, 5), "5-day cross-sectional reversal (weekly horizon)")
    hi90 = np.full_like(c, np.nan)
    for t in range(90, T):
        hi90[:, t] = np.nanmax(c[:, t - 89:t + 1], axis=1)
    xs("A7_XS_NEAR90HIGH", "A", np.log(np.maximum(safe_div(c, hi90), 1e-6)),
       "closeness to the trailing 90-day high")

    # ---------------- family B : spot taker-flow microstructure
    tshare = safe_div(2.0 * tbq - qv, qv)       # +1 all taker-buy, -1 all taker-sell
    tshare[~np.isfinite(tshare)] = np.nan
    xs("B1_XS_TBQ_IMB", "B", roll_mean(tshare, 3), "3d mean spot taker-buy imbalance")
    xs("B2_XS_TBQ_CHG", "B", roll_mean(tshare, 5) - roll_mean(tshare, 20),
       "taker-buy imbalance: 5d minus 20d")
    ticket = np.log(np.maximum(safe_div(qv, n), 1e-9)).astype(np.float32)
    xs("B3_XS_TICKET_Z", "B", zscore_ts(ticket, 60), "average trade size vs own 60d (big-ticket tilt)")
    lgn = np.log(np.maximum(n, 1.0)).astype(np.float32)
    lgq = np.log(np.maximum(qv, 1.0)).astype(np.float32)
    xs("B4_XS_TRADECT_SURGE", "B",
       (roll_mean(lgn, 3) - roll_mean(lgn, 60)) - (roll_mean(lgq, 3) - roll_mean(lgq, 60)),
       "many small trades: trade-count surge net of dollar-volume surge")
    z3 = np.tanh(zscore_ts(roll_mean(lr, 3), 60))
    zf = np.tanh(zscore_ts(roll_mean(tshare, 3), 60))
    xs("B5_XS_ABSORB", "B", zf - z3,
       "taker buying not yet reflected in price (flow z minus return z = absorption)")
    netflow = safe_div(roll_sum(2.0 * tbq - qv, 5), roll_mean(qv, 60) * 5.0)
    xs("B6_XS_NETTAKER_$", "B", netflow, "5d net taker dollar flow scaled by 60d ADV")
    xs("B7_XS_TAKER_TREND", "B", roll_mean(tshare, 20),
       "slow 20d taker-buy imbalance (persistent spot accumulation)")

    # ---------------- family C : BTC dominance / alt rotation (dollar-neutral leg)
    isbtc = np.zeros(S, bool); isbtc[ibtc] = True
    altm = univ & (~isbtc[:, None])
    btcm = np.zeros((S, T), bool); btcm[ibtc] = univ[ibtc]
    leg = xs_weights_from_mask(altm, btcm)      # +alt basket / -BTC, unit gross
    qvu = np.where(univ, qv, 0.0)
    dom = safe_div(qvu[ibtc], qvu.sum(0))
    dom_chg = np.nan_to_num(dom - shift(dom[None, :], 5)[0])
    ts1 = np.nan_to_num(zscore_ts(dom_chg[None, :], 250)[0])
    add("C1_TS_VOLDOM", "C", leg * np.clip(shift(ts1[None, :], 1)[0], -1, 1)[None, :],
        "5d change in BTC share of universe spot dollar volume -> alt vs BTC")
    ma20 = roll_mean(c, 20)
    above = np.where(univ & np.isfinite(ma20), (c > ma20).astype(np.float32), np.nan)
    breadth = np.nanmean(np.where(univ, above, np.nan), axis=0)
    br_chg = np.nan_to_num(breadth - shift(breadth[None, :], 5)[0])
    ts2 = np.nan_to_num(zscore_ts(br_chg[None, :], 250)[0])
    add("C2_TS_ALTBREADTH", "C", leg * np.clip(shift(ts2[None, :], 1)[0], -1, 1)[None, :],
        "5d change in the fraction of the universe above its own 20d MA -> alt vs BTC")
    altret = np.nanmean(np.where(altm, lr, np.nan), axis=0)
    spread10 = np.nan_to_num(roll_sum(lrb[None, :], 10)[0] - roll_sum(np.nan_to_num(altret)[None, :], 10)[0])
    ts3 = np.nan_to_num(zscore_ts(spread10[None, :], 250)[0])
    add("C3_TS_BTC_ALT_MR", "C", leg * np.clip(shift(ts3[None, :], 1)[0], -1, 1)[None, :],
        "10d BTC-minus-alt return spread, mean-reverting -> alt vs BTC")
    xs("C4_XS_BAB", "C", -beta, "bet against BTC beta in spot")

    # ---------------- family D : volume & volatility structure
    xs("D1_XS_VOLSURGE", "D", np.log(np.maximum(safe_div(roll_mean(qv, 3), roll_mean(qv, 60)), 1e-6)),
       "3d vs 60d dollar-volume surge")
    rng = safe_div(h - l, c)
    xs("D2_XS_RANGECOMP", "D", -safe_div(roll_mean(rng, 10), roll_mean(rng, 60)),
       "range compression: 10d vs 60d intraday range")
    upq = np.where(ret1 > 0, qv, 0.0).astype(np.float32)
    dnq = np.where(ret1 < 0, qv, 0.0).astype(np.float32)
    xs("D3_XS_UPVOL_ASYM", "D", safe_div(roll_sum(upq, 20) - roll_sum(dnq, 20), roll_sum(qv, 20)),
       "20d up-day minus down-day dollar volume (accumulation)")
    amih = safe_div(np.abs(ret1), np.maximum(qv, 1.0)) * 1e6
    xs("D4_XS_AMIHUD", "D", np.log(np.maximum(roll_mean(amih, 20), 1e-12)),
       "Amihud illiquidity |ret|/dollar-volume, 20d")
    cl = safe_div(c - l, np.maximum(h - l, 1e-12)) - 0.5
    xs("D5_XS_CLOSELOC", "D", roll_mean(cl, 5), "5d mean close location inside the daily range")
    xs("D6_XS_ATTN_TREND", "D", roll_mean(lgq, 10) - roll_mean(lgq, 90),
       "attention trend: 10d vs 90d log dollar volume")

    # ---------------- family F : stablecoin peg deviation (Binance spot)
    market = univ.astype(np.float64)                     # long-only unit-gross spot basket
    market /= np.maximum(market.sum(0), 1.0)[None, :]
    peg_syms = [s for s in ("USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "BUSDUSDT") if s in syms]
    pidx = [syms.index(s) for s in peg_syms]
    dev = np.nanmean(np.where(np.isfinite(c[pidx]), c[pidx] - 1.0, np.nan), axis=0)
    pz = np.nan_to_num(zscore_ts(np.nan_to_num(dev)[None, :], 250)[0])
    add("F1_TS_PEGDEV", "F", market * np.clip(shift(pz[None, :], 1)[0], -1, 1)[None, :],
        "stablecoin-vs-USDT peg premium z -> long/short the spot basket")
    pv = np.nansum(np.where(np.isfinite(qv[pidx]), qv[pidx], 0.0), axis=0)
    pvz = np.nan_to_num(zscore_ts(np.log(np.maximum(pv, 1.0))[None, :] -
                                  roll_mean(np.log(np.maximum(pv, 1.0))[None, :], 60), 250)[0])
    add("F2_TS_STABVOL", "F", market * np.clip(shift(pvz[None, :], 1)[0], -1, 1)[None, :],
        "stablecoin-pair volume surge (on-ramp proxy) -> long/short the spot basket")

    # ---------------- family G : spot listing-age dynamics
    first = np.full(S, 10 ** 9, np.int64)
    for i in range(S):
        w = np.where(alive[i])[0]
        if w.size:
            first[i] = w[0]
    age = np.arange(T)[None, :] - first[:, None]
    tradeable = np.isfinite(o) & (o > 0)
    tradeable[:, :-1] &= (np.isfinite(o) & (o > 0))[:, 1:]
    liq = roll_mean(qv, 10) > 2e5
    d1ret = np.full(S, np.nan, np.float32)
    for i in range(S):
        if first[i] < T:
            d1ret[i] = ret1[i, min(first[i] + 1, T - 1)]
    young = (age >= 2) & (age <= 7) & tradeable & liq
    lm = young & (d1ret < 0)[:, None]
    sm = young & (d1ret > 0)[:, None]
    add("G1_NL_D1_FADE", "G", xs_weights_from_mask(lm, sm),
        "fade the first-day listing move over days 2-7")
    newc = (age >= 3) & (age <= 60) & tradeable & liq
    oldc = (age > 240) & tradeable & liq & univ
    add("G2_NL_AGE_TILT", "G", xs_weights_from_mask(newc, oldc),
        "long names younger than 60 days, short mature names")
    q7 = roll_mean(qv, 7)
    q7first = np.full((S, T), np.nan, np.float32)
    for i in range(S):
        f = first[i]
        if f + 9 < T:
            q7first[i, :] = np.nanmean(qv[i, f + 1:f + 8])
    decay = np.log(np.maximum(safe_div(q7, q7first), 1e-6))
    mid = (age >= 8) & (age <= 40) & tradeable & liq
    add("G3_NL_VOLDECAY", "G", xs_weights(np.where(mid, shift(decay, 1), np.nan), mid),
        "post-listing volume decay ranked inside the 8-40 day cohort")
    return out


def run(P, univ, sigs, tag, outjson):
    days = P["days"]
    r = fwd_open_ret(P)
    d0, d1 = dayidx(days, DESIGN[0]), dayidx(days, DESIGN[1])
    h0, h1 = dayidx(days, HELDOUT[0]), dayidx(days, HELDOUT[1])
    res, pnl_design, pnl_hold = [], [], []
    for name, fam, w, desc in sigs:
        H = 1
        wt = tranche(w, H)
        gross, _, dw, exp_net = evaluate(wt, r, FEE)
        # orient the sign on the DESIGN window with zero-cost P&L, then freeze it.
        # cost is sign-invariant, so it must be subtracted AFTER the flip.
        sgn = 1.0 if np.nanmean(gross[d0:d1]) >= 0 else -1.0
        gross, exp_net = gross * sgn, exp_net * sgn
        net = gross - dw * FEE * 1e-4
        net_s = gross - dw * FEE_SHOCK * 1e-4
        # beta attribution: strip net exposure x equal-weight universe return
        uw = np.where(univ, 1.0, 0.0)
        uw = uw / np.maximum(uw.sum(0), 1)[None, :]
        mret = (uw * np.nan_to_num(r)).sum(0)
        net_beta = net - exp_net * mret
        row = dict(
            name=name, family=fam, desc=desc, sign=sgn,
            d_gross=sharpe(gross[d0:d1]), d_net=sharpe(net[d0:d1]),
            d_net_shock=sharpe(net_s[d0:d1]), d_t=tstat(net[d0:d1]),
            d_turn=float(np.nanmean(dw[d0:d1])),
            h_gross=sharpe(gross[h0:h1]), h_net=sharpe(net[h0:h1]),
            h_net_shock=sharpe(net_s[h0:h1]), h_t=tstat(net[h0:h1]),
            h_be_bp=breakeven_bp(gross[h0:h1], dw[h0:h1]),
            d_be_bp=breakeven_bp(gross[d0:d1], dw[d0:d1]),
            d_net_betastrip=sharpe(net_beta[d0:d1]), h_net_betastrip=sharpe(net_beta[h0:h1]),
            mean_abs_exp=float(np.nanmean(np.abs(exp_net[d0:d1]))),
        )
        res.append(row)
        pnl_design.append(net[d0:d1]); pnl_hold.append(net[h0:h1])
    order = sorted(range(len(res)), key=lambda i: -res[i]["d_net"])
    res = [res[i] for i in order]
    pnl_design = [pnl_design[i] for i in order]
    pnl_hold = [pnl_hold[i] for i in order]
    P_d = np.array(pnl_design)
    null = null_max(P_d)
    obj = dict(theme="crypto_spot_xs", tag=tag, n=len(res), design=DESIGN, heldout=HELDOUT,
               fee_bp=FEE, fee_shock_bp=FEE_SHOCK, topn=TOPN, null=null, rows=res)
    json.dump(obj, open(outjson, "w"), indent=1)
    np.savez_compressed(outjson.replace(".json", "_pnl.npz"),
                        names=np.array([r0["name"] for r0 in res]),
                        design=P_d, hold=np.array(pnl_hold))
    return obj


def null_max(P_d, nrep=2000, block=10, seed=7):
    """Sign-flip block bootstrap of max |Sharpe| across the whole search."""
    rng = np.random.default_rng(seed)
    N, T = P_d.shape
    nb = int(np.ceil(T / block))
    mx = np.empty(nrep)
    for i in range(nrep):
        s = rng.choice([-1.0, 1.0], size=nb)
        s = np.repeat(s, block)[:T]
        X = P_d * s[None, :]
        mu = X.mean(1); sd = X.std(1)
        sh = np.where(sd > 0, mu / np.maximum(sd, 1e-12) * ANN, 0.0)
        mx[i] = np.abs(sh).max()
    return dict(E_max=float(mx.mean()), p95=float(np.percentile(mx, 95)),
                p99=float(np.percentile(mx, 99)),
                analytic_2N=float(np.sqrt(2 * np.log(2 * N)) * (1.0 / np.sqrt(T / 365.0))),
                se_one=float(1.0 / np.sqrt(T / 365.0)), N=int(N), T=int(T))


if __name__ == "__main__":
    P = load_panel()
    print("panel", P["c"].shape, flush=True)
    univ = build_universe(P, top=TOPN)
    print("universe mean size", float(univ.sum(0).mean()), flush=True)
    sigs = build_signals(P, univ)
    print(f"formulas: {len(sigs)}", flush=True)
    obj = run(P, univ, sigs, "main", "/home/anont/meme/research/trading_bot/INVENT_D0821_crypto_spot_xs.json")
    for r0 in obj["rows"]:
        print(f"{r0['name']:24s} {r0['family']} D {r0['d_net']:+6.2f} H {r0['h_net']:+6.2f} "
              f"Ht {r0['h_t']:+5.2f} turn {r0['d_turn']:.2f}", flush=True)
    print("null:", obj["null"], flush=True)
