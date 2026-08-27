#!/usr/bin/env python3
"""STEP 1 of INVENT 0824 -- the rho1(delta-spread) BOUNCE GATE, run BEFORE any P&L.

Any object whose P&L is a convergence trade on a PRICE SPREAD must first clear
rho1(delta s) > ~-0.35.  A spread that is nothing but non-synchronous bid-ask measurement
error has rho1(delta s) -> -0.50 and a high gross Sharpe from fading its own bounce.

Objects measured here:
  * cross-venue Coinbase-minus-Binance log price (the published Coinbase Premium) -- the
    only PRICE object this round trades (family D3/D4);
  * wrapped/staked vs underlying (WBTC/BTC, WBETH/ETH, BETH/ETH, BNSOL/SOL) -- the
    "real structural tether" the brief asks about, re-measured fresh;
  * the alt-EW / BTC log ratio traded by the ROT book;
  * the stablecoin volume share and Coinbase volume share -- NOT price spreads, reported
    so the contrast is on the record.
Also reports synchronicity and whether the tether's dispersion is wider than the spread.
"""
from __future__ import annotations
import json, numpy as np, datetime as dt, sys
sys.path.insert(0, "/home/anont/meme/scripts/trading_bot")
from inv0824_flow_lib import (load, features, flow_features, universe, coinbase_overlay,
                              aggregates, rho1, roll_std, shift, rm1, sh1)

OUT = "/home/anont/meme/research/trading_bot/INVENT_0824_onchainflow_GATE.json"
FEE_BP = 10.0


def d_rho(x):
    x = np.asarray(x, float)
    xx = x.copy()
    # consecutive-day differences only; NaN gaps are dropped, never bridged
    idx = np.where(np.isfinite(x))[0]
    if idx.size < 60:
        return np.nan, 0
    dd = np.diff(xx[idx])
    gap = np.diff(idx) == 1
    dd = dd[gap]
    return rho1(dd), int(dd.size)


def main():
    P = load(); F = features(P); G = flow_features(P, F)
    U = universe(P, F)
    CBC, CBQ = coinbase_overlay(P, F)
    A = aggregates(P, F, G, U)
    syms = list(P["syms"])
    res = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(), "objects": {}}

    # ---- cross-venue price spread, per base, de-medianed -------------------------------
    with np.errstate(invalid="ignore", divide="ignore"):
        prem_raw = np.log(CBC / F["c"])
    ok = np.isfinite(prem_raw)
    med = np.full(prem_raw.shape[1], np.nan)
    for t in range(prem_raw.shape[1]):
        m = ok[:, t]
        if m.sum() >= 8:
            med[t] = np.median(prem_raw[m, t])
    prem = prem_raw - med[None, :]
    xv = {}
    for b in ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "LINK", "LTC", "AVAX", "DOT"]:
        try:
            i = syms.index(b + "USDT")
        except ValueError:
            continue
        r_, n_ = d_rho(prem[i])
        s = prem[i][np.isfinite(prem[i])]
        xv[b] = dict(rho1_dspread=r_, n=n_, sd_bp=float(s.std() * 1e4) if s.size else None,
                     mean_bp=float(s.mean() * 1e4) if s.size else None)
    res["objects"]["cross_venue_coinbase_premium"] = dict(
        kind="PRICE SPREAD (published anchor: Coinbase Premium Index)", per_name=xv,
        median_rho1=float(np.nanmedian([v["rho1_dspread"] for v in xv.values()])) if xv else None,
        median_sd_bp=float(np.nanmedian([v["sd_bp"] for v in xv.values() if v["sd_bp"] is not None])) if xv else None)

    # ---- wrapped / staked vs underlying -------------------------------------------------
    pairs = [("WBTCUSDT", "BTCUSDT"), ("WBETHUSDT", "ETHUSDT"), ("BETHUSDT", "ETHUSDT"),
             ("BNSOLUSDT", "SOLUSDT"), ("WBTCBTC", "__ONE__"), ("WBETHETH", "__ONE__"),
             ("BETHETH", "__ONE__")]
    wr = {}
    for a, b in pairs:
        if a not in syms:
            continue
        ia = syms.index(a)
        la = np.log(np.where(F["c"][ia] > 0, F["c"][ia], np.nan))
        if b == "__ONE__":
            s = la
        else:
            if b not in syms:
                continue
            ib = syms.index(b)
            lb = np.log(np.where(F["c"][ib] > 0, F["c"][ib], np.nan))
            s = la - lb
        r_, n_ = d_rho(s)
        ss = s[np.isfinite(s)]
        wr[a + "/" + b] = dict(rho1_dspread=r_, n=n_,
                               sd_bp=float(ss.std() * 1e4) if ss.size else None,
                               mean_bp=float(ss.mean() * 1e4) if ss.size else None)
    res["objects"]["wrapped_vs_underlying"] = dict(
        kind="PRICE SPREAD (structural tether: unwrap/redeem)", per_pair=wr)

    # ---- rotation ratio (the ROT book's own object) -------------------------------------
    ib = A["ib"]
    lr = np.cumsum(np.nan_to_num(A["alt_r"])) - np.cumsum(np.nan_to_num(A["btc_r"]))
    r_, n_ = d_rho(lr)
    res["objects"]["alt_ew_over_btc_log_ratio"] = dict(
        kind="PRICE RATIO, NO TETHER (rotation book object)", rho1_dspread=r_, n=n_)

    # ---- the NON-price flow objects ------------------------------------------------------
    for nm, x in [("stablecoin_volume_share", A["stab_share"]),
                  ("btc_volume_dominance", A["btc_vdom"]),
                  ("alt_aggregate_taker_imbalance", A["alt_netf"])]:
        r_, n_ = d_rho(np.asarray(x, float))
        res["objects"][nm] = dict(kind="VOLUME/FLOW SERIES (not a price spread)",
                                  rho1_dchange=r_, n=n_)

    # aggregate coinbase volume share
    qv = F["qv"]
    agg_us = np.full(qv.shape[1], np.nan)
    for t in range(qv.shape[1]):
        m = U[:, t] & np.isfinite(CBQ[:, t]) & np.isfinite(qv[:, t])
        if m.sum() >= 8:
            agg_us[t] = CBQ[m, t].sum() / (CBQ[m, t].sum() + qv[m, t].sum())
    r_, n_ = d_rho(agg_us)
    res["objects"]["coinbase_aggregate_volume_share"] = dict(
        kind="VOLUME/FLOW SERIES (not a price spread)", rho1_dchange=r_, n=n_,
        first_day=str(P["dates"][np.isfinite(agg_us).argmax()]),
        n_days=int(np.isfinite(agg_us).sum()))

    res["gate_rule"] = ("a PRICE-SPREAD object is admitted only if rho1(delta s) > -0.35; "
                        "flow/volume series are exempt (they are not bid-ask objects) but "
                        "are reported for contrast")
    with open(OUT, "w") as f:
        json.dump(res, f, indent=1, default=float)
    print(json.dumps(res, indent=1, default=float)[:6000])


if __name__ == "__main__":
    main()
