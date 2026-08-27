#!/usr/bin/env python3
"""D0821 crypto-spot sweep, pass 2: adds cross-quote (E) and cross-venue (H) families
and re-scores the whole pooled search (families A-H) under one multiple-testing null.

Also runs the mandatory SHARED-PRICE PLACEBO (round-3 failure mode 3): every book is
re-evaluated with the signal lagged one extra day, so no signal input can be the fill.
"""
from __future__ import annotations
import json, os, sys
import numpy as np

sys.path.insert(0, "/home/anont/meme/scripts/trading_bot")
from xspot_lib import (CACHE, ANN, load_panel, roll_mean, roll_sum, roll_std, shift,
                       zscore_ts, build_universe, fwd_open_ret, xs_weights,
                       xs_weights_from_mask, tranche, evaluate, sharpe, tstat,
                       breakeven_bp, STABLE_BASES)
import xspot_sweep as S1

OUT = "/home/anont/meme/research/trading_bot/INVENT_D0821_crypto_spot_xs.json"


def safe_div(a, b):
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(np.abs(b) > 0, a / b, np.nan).astype(np.float32)


def align(P, Q, suffix):
    """Row-align quote-panel Q onto P's symbol order by base asset."""
    qs = {s: i for i, s in enumerate(Q["syms"])}
    idx = np.full(len(P["syms"]), -1, np.int64)
    for i, s in enumerate(P["syms"]):
        j = qs.get(s[:-4] + suffix)
        if j is not None:
            idx[i] = j
    return idx


def build_e_h(P, univ):
    syms = list(P["syms"])
    c, qv = P["c"], P["qv"]
    S, T = c.shape
    out = []

    def xs(name, fam, raw, mask, tag):
        out.append((name, fam, np.nan_to_num(xs_weights(shift(raw.astype(np.float32), 1), mask)), tag))

    # ---------- E : cross-quote dispersion inside Binance
    xqp = f"{CACHE}/spotxq_daily.npz"
    if os.path.exists(xqp):
        Q = load_panel(xqp)
        qsyms = list(Q["syms"])
        itry = align(P, Q, "TRY")
        iusdc = align(P, Q, "USDC")
        jrate = qsyms.index("USDTTRY") if "USDTTRY" in qsyms else -1
        ctry = np.full((S, T), np.nan, np.float32)
        vtry = np.zeros((S, T), np.float32)
        cusdc = np.full((S, T), np.nan, np.float32)
        vusdc = np.zeros((S, T), np.float32)
        for i in range(S):
            if itry[i] >= 0:
                ctry[i] = Q["c"][itry[i]]; vtry[i] = Q["qv"][itry[i]]
            if iusdc[i] >= 0:
                cusdc[i] = Q["c"][iusdc[i]]; vusdc[i] = Q["qv"][iusdc[i]]
        rate = Q["c"][jrate] if jrate >= 0 else np.full(T, np.nan, np.float32)
        prem_try = safe_div(safe_div(ctry, rate[None, :]), c) - 1.0
        prem_try[np.abs(prem_try) > 0.5] = np.nan
        mtry = univ & np.isfinite(prem_try) & (safe_div(vtry, rate[None, :]) > 5e4)
        xs("E1_XS_TRYPREM", "E", np.where(mtry, prem_try, np.nan), mtry,
           "Turkish-lira quoted price premium over the USDT quote, cross-sectional")
        agg = np.nanmean(np.where(mtry, prem_try, np.nan), axis=0)
        z = np.nan_to_num(zscore_ts(np.nan_to_num(agg)[None, :], 250)[0])
        ibtc = syms.index("BTCUSDT")
        isbtc = np.zeros(S, bool); isbtc[ibtc] = True
        altm = univ & (~isbtc[:, None])
        btcm = np.zeros((S, T), bool); btcm[ibtc] = univ[ibtc]
        leg = xs_weights_from_mask(altm, btcm)
        out.append(("E2_TS_TRYPREM_AGG", "E",
                    np.nan_to_num(leg * np.clip(shift(z[None, :], 1)[0], -1, 1)[None, :]),
                    "aggregate lira premium z(250) -> alt basket vs BTC"))
        prem_usdc = safe_div(cusdc, c) - 1.0
        prem_usdc[np.abs(prem_usdc) > 0.2] = np.nan
        musdc = univ & np.isfinite(prem_usdc) & (vusdc > 5e4)
        xs("E3_XS_USDCGAP", "E", np.where(musdc, prem_usdc, np.nan), musdc,
           "USDC-quoted minus USDT-quoted price gap on the same venue, cross-sectional")

    # ---------- H : cross-venue (Coinbase vs Binance) spot dispersion
    cbp = f"{CACHE}/coinbase_daily.npz"
    if os.path.exists(cbp):
        B = load_panel(cbp)
        bs = {s.split("-")[0]: i for i, s in enumerate(B["syms"])}
        ccb = np.full((S, T), np.nan, np.float32)
        vcb = np.zeros((S, T), np.float32)
        n = min(T, B["c"].shape[1])
        for i, s in enumerate(syms):
            j = bs.get(s[:-4])
            if j is not None:
                ccb[i, :n] = B["c"][j, :n]; vcb[i, :n] = B["qv"][j, :n]
        ratio = safe_div(ccb, c)
        ratio[(ratio < 0.5) | (ratio > 2.0)] = np.nan
        zr = zscore_ts(np.log(np.maximum(ratio, 1e-9)), 60)
        mcb = univ & np.isfinite(zr) & (vcb > 1e5)
        xs("H1_XS_CBPREM", "H", np.where(mcb, zr, np.nan), mcb,
           "Coinbase-over-Binance price z(60): cross-venue dislocation")
        share = safe_div(vcb, np.maximum(vcb + qv, 1.0))
        dshare = share - shift(share, 10)
        mcb2 = univ & np.isfinite(dshare) & (vcb > 1e5)
        xs("H2_XS_CBVOLSHARE", "H", np.where(mcb2, dshare, np.nan), mcb2,
           "10d change in Coinbase share of combined dollar volume (US-flow tilt)")
    return out


def main():
    P = load_panel()
    univ = build_universe(P, top=S1.TOPN)
    sigs = S1.build_signals(P, univ) + build_e_h(P, univ)
    print(f"pooled formulas: {len(sigs)}", flush=True)
    obj = S1.run(P, univ, sigs, "pooled", OUT)

    # ---- shared-price placebo: lag every book one extra day
    lag = [(n + "__LAG1", f, shift(w.astype(np.float32), 1), d) for n, f, w, d in sigs]
    objl = S1.run(P, univ, lag, "placebo_lag1",
                  OUT.replace(".json", "_PLACEBO.json"))
    pl = {r["name"][:-6]: r for r in objl["rows"]}
    for r in obj["rows"]:
        p = pl.get(r["name"])
        if p:
            r["lag1_d_net"] = p["d_net"]; r["lag1_h_net"] = p["h_net"]
            r["lag1_d_gross"] = p["d_gross"]; r["lag1_h_gross"] = p["h_gross"]
    json.dump(obj, open(OUT, "w"), indent=1)

    for r in obj["rows"]:
        print(f"{r['name']:24s} {r['family']} Dgr {r['d_gross']:+5.2f} Dnet {r['d_net']:+5.2f} "
              f"Hgr {r['h_gross']:+5.2f} Hnet {r['h_net']:+5.2f} Ht {r['h_t']:+5.2f} "
              f"BEh {r['h_be_bp']:+6.1f} turn {r['d_turn']:.2f} LAG1 D {r.get('lag1_d_net',0):+5.2f} H {r.get('lag1_h_net',0):+5.2f}",
              flush=True)
    print("null:", obj["null"], flush=True)


if __name__ == "__main__":
    main()
