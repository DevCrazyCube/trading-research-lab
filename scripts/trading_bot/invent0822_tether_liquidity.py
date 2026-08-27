#!/usr/bin/env python3
"""INVENT 0822 crypto-tether: does the stablecoin-peg edge survive a liquidity floor?

The 10 bp Binance spot taker charge is only credible on pairs that actually
trade.  Several stablecoin pairs in the survivorship-free universe are thin
(sUSD $0.17M/day, USDS $0.05M/day, USDP $0.84M/day).  This re-runs the three
leading peg formulas under a trailing-30d median-$volume floor applied AT THE
SIGNAL DATE (no lookahead).
"""
from __future__ import annotations
import os, json
import numpy as np
import invent0822_tether_lib as L
import invent0822_tether_sweep as SW

OUT = "/home/anont/meme/research/trading_bot"
bp = 1e-4


def main():
    P = L.Panels(); dates = P.dates(); T = P.T
    stab = SW.stable_universe(P); K = len(stab)
    dev = np.full((T, K), np.nan); rA = np.full((T, K), np.nan); qv = np.full((T, K), np.nan)
    for j, s in enumerate(stab):
        c, o, q = P.bn(s, "c"), P.bn(s, "o"), P.bn(s, "qv")
        dev[:, j] = np.log(c); rA[:-1, j] = np.log(o[1:] / o[:-1]); qv[:, j] = q
    age = np.cumsum(np.isfinite(dev), axis=0)
    liq = np.full((T, K), np.nan)
    for j in range(K):
        x = qv[:, j]
        for t in range(30, T):
            w = x[t - 30:t]; w = w[np.isfinite(w)]
            if w.size >= 15:
                liq[t, j] = np.median(w)
    des = dates < SW.SPLIT; hld = dates >= SW.SPLIT
    live = np.any(np.isfinite(rA), axis=1)
    out = {"median_dollar_volume": {s: round(float(np.nanmedian(qv[:, j])), 0) for j, s in enumerate(stab)},
           "grid": []}
    for thr in (0.0, 5e6, 25e6):
        for nm, side, seas in (("A2_PEG_BAND20", "both", False),
                               ("A12_PEG_BAND20_SEASONED", "both", True),
                               ("A6_PEG_PREM_ONLY", "prem", False)):
            w = np.column_stack([SW.band_state(dev[:, j], 20 * bp, 5 * bp, side) for j in range(K)])
            if seas:
                w = w * (age >= 250)
            w = w * (np.nan_to_num(liq) >= thr)
            ws = np.zeros_like(w); ws[1:] = w[:-1]
            bk = L.book_pnl(L.normalize_eq(ws), rA, np.ones(K), SW.FEE_BP)
            d = L.stats(bk["net"], live & des); h = L.stats(bk["net"], live & hld)
            g = L.stats(bk["gross"], live & des); gh = L.stats(bk["gross"], live & hld)
            out["grid"].append(dict(floor_musd=thr / 1e6, formula=nm,
                                    Dgross=g["sharpe"], Dnet=d["sharpe"], Dnet_t=d["t"],
                                    Hgross=gh["sharpe"], Hnet=h["sharpe"], Hnet_t=h["t"],
                                    days_on=int(np.sum(np.abs(ws).sum(1) > 0))))
            print(out["grid"][-1])
    with open(os.path.join(OUT, "INVENT_0822_crypto_tether_LIQUIDITY.json"), "w") as fh:
        json.dump(out, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
