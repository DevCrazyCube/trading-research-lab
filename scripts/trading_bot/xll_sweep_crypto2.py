#!/usr/bin/env python3
"""XLL crypto ADDENDUM: the one structural finding from the main sweep, tested at slower horizons.

D2 (illiquid alts lag BTC) was the only crypto formula with a large design gross Sharpe that
does NOT contain an own-return term -- so it is not the 5-minute bid-ask-bounce reversal that
inflates the whole B/C family. Its problem is turnover: at 5m it pays ~6bp/bar of fees against
~0.1bp/bar of signal. This addendum asks the only question that matters about it: does the SAME
transmission survive when the holding period is long enough to amortise the fee?

These are 8 ADDITIONAL formulas. They widen the family, so the noise bar is recomputed over the
addendum's own null and the report states the combined count.
"""
from __future__ import annotations
import gc, json, os, sys, time
import numpy as np

sys.path.insert(0, "/home/anont/meme/scripts/trading_bot")
import xll_sweep_crypto as X

OUTJ = "/home/anont/meme/research/trading_bot/SWEEP_xll_crypto_addendum.json"
N_NULL = 96
rng = np.random.default_rng(20260821)


def configs():
    F = []
    def add(name, freq, desc, fn):
        F.append((name, freq, desc, fn))

    def illiq(c):
        # NO own-return term: purely "BTC moved, the thin-book names have not caught up yet".
        return -X.rank_xs(np.broadcast_to(c.adv, c.r.shape), c.tradable) * np.sign(X.lag(c.r[c.ib]))[None, :]

    def illiq_mag(c):
        return -X.rank_xs(np.broadcast_to(c.adv, c.r.shape), c.tradable) * X.lag(c.r[c.ib])[None, :]

    for f, lbl in ((6, "30m"), (12, "1h"), (48, "4h"), (288, "1d")):
        add(f"Z1_illiq_lag_btc_sign_{lbl}", f,
            f"long thin-book alts / short liquid alts on the SIGN of BTC's last {lbl} move, held {lbl} (no own-return term)", illiq)
    for f, lbl in ((12, "1h"), (48, "4h")):
        add(f"Z2_illiq_lag_btc_mag_{lbl}", f,
            f"same illiquidity-tier transmission but scaled by the SIZE of BTC's last {lbl} move, held {lbl}", illiq_mag)
    for f, lbl in ((48, "4h"), (288, "1d")):
        add(f"Z3_illiq_lag_btc_2bar_{lbl}", f,
            f"illiquidity-tier transmission on BTC's last TWO {lbl} bars (slower lead window)",
            lambda c: -X.rank_xs(np.broadcast_to(c.adv, c.r.shape), c.tradable) * np.sign(X.roll_k(c.r[c.ib][None, :], 2)))

    # J1/J2 in the main sweep came back identically zero: score() masks W by c.tradable and
    # build_ctx sets tradable[BTC]=False (BTC is the leader, not a leg), so a BTC-only book was
    # erased. Re-run here with BTC re-enabled -- these are the REVERSE-direction tests, "do the
    # alts lead BTC", and a silently-zero result would have hidden them entirely.
    def altlead(k):
        def f(c):
            m = np.where(c.tradable, c.r, 0.0).sum(0) / np.maximum(c.tradable.sum(0), 1)
            sig = X.roll_k(m[None, :], k)[0] - X.roll_k(c.r[c.ib][None, :], k)[0]
            W = np.zeros_like(c.r)
            W[c.ib] = sig
            c.tradable[c.ib] = True          # BTC is the only leg of this book
            return W
        return f
    add("J1b_alts_lead_btc_k1_5m", 1, "trade BTC ALONE on the gap between the equal-weight alt complex and BTC over the last 5m (reverse lead-lag)", altlead(1))
    add("J2b_alts_lead_btc_k6_30m", 6, "trade BTC alone on the alt-complex-minus-BTC gap over the last 3h, 30m rebalance", altlead(6))
    add("J3b_alts_lead_btc_k1_4h", 48, "trade BTC alone on the alt-complex-minus-BTC gap over the last 4h", altlead(1))
    return F


def main():
    F = configs()
    byf = {}
    for cfg in F:
        byf.setdefault(cfg[1], []).append(cfg)
    results, nulls, names = [], [], []
    for freq in sorted(byf):
        c = X.build_ctx(freq)
        T = c.r.shape[1]
        bpd = max(1, int(round(24 * 60 / (5 * freq))))
        s = rng.integers(bpd, max(bpd + 1, T // 8), size=N_NULL // 2)
        shifts = np.concatenate([s, -s])
        print(f"[freq={freq}] T={T}", flush=True)
        for name, _f, desc, fn in byf[freq]:
            W = fn(c)
            res, W, _ = X.score(c, W, name)
            res["freq_5m_units"] = freq
            res["formula_desc"] = desc
            results.append(res); names.append(name)
            nulls.append(X.null_sharpes(c, W, shifts))
            print(f"  {name:32s} gross={res['gross_sharpe']:+7.2f} net={res['net_sharpe']:+9.2f} "
                  f"tno={res['turnover_per_bar']:.3f} bp/bar={res['gross_bp_per_bar']:+.4f} "
                  f"cost={res['cost_bp_per_bar']:.4f} HOgross={res['holdout_gross_sharpe']:+.2f} "
                  f"HOnet={res['holdout_net_sharpe']:+.2f}", flush=True)
            del W; gc.collect()
        del c; gc.collect()
    NULL = np.array(nulls); mx = NULL.max(axis=0)
    out = dict(block="crypto_perp_leadlag_ADDENDUM_slow_horizons",
               design_window=["2023-01-01", "2025-06-30"], holdout_window=["2025-07-01", "2026-08-17"],
               cost_bp_per_side=X.COST_BP_PER_SIDE,
               cost_provenance="BROKER_SCHEDULE (Binance USD-M VIP0 taker 5bp) + STRESS_LADDER (1bp slippage). NOT a measurement of our own fills.",
               n_formulas=len(results),
               null=dict(n_draws=int(NULL.shape[1]), method="time-shifted returns (>=1 day, both signs), shared shift per draw",
                         sd_single_config_sharpe=float(NULL.std()),
                         expected_max_sharpe=float(mx.mean()), p95_max_sharpe=float(np.percentile(mx, 95)),
                         naive_sqrt2lnN=float(np.sqrt(2 * np.log(max(len(results), 2))) * NULL.std())),
               results=sorted(results, key=lambda r: -r["gross_sharpe"]))
    json.dump(out, open(OUTJ, "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "results"}, indent=1))
    print("WROTE", OUTJ)


if __name__ == "__main__":
    main()
