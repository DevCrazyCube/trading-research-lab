#!/usr/bin/env python3
"""XLL crypto block: a WIDE sweep of cross-asset lead-lag formulas on Binance USD-M perps.

One parameterised harness. Every config produces a weight matrix W (S,T) known at t-1 and is
scored on the DESIGN window only. The noise bar is EMPIRICAL: the same configs are re-scored
against time-shifted returns (shift >= 1 day, both signs), which destroys any lead-lag relation
while preserving each config's own turnover/autocorrelation structure and the CORRELATION
BETWEEN CONFIGS -- so max-over-configs under that null is the honest expected-max, not the
sqrt(2 ln N) idealisation that assumes independence.
"""
from __future__ import annotations
import gc, json, os, sys, time
import numpy as np

try:
    os.nice(10)                     # this box runs several other agents' sweeps concurrently
except OSError:
    pass

ROOT = "/home/anont/meme"
PANEL = f"{ROOT}/research/data/xll_cache/perp5m_panel.npz"
OUTJ = f"{ROOT}/research/trading_bot/SWEEP_xll_crypto.json"

BARS_PER_YEAR_5M = 365 * 24 * 12
DESIGN_END_MS = 1751328000000     # 2025-07-01
COST_BP_PER_SIDE = 6.0            # 5bp Binance USD-M VIP0 taker (BROKER_SCHEDULE) + 1bp slippage
                                  # (STRESS_LADDER). NOT a measurement of our own fills.
MIN_ADV_USD = 2e6                 # trailing-24h quote volume floor for tradability
N_NULL = 96

rng = np.random.default_rng(20260820)


# ----------------------------------------------------------------- data / context
class Ctx:
    pass


def rolling_sum(a, w, axis=-1):
    """Causal rolling sum over the last w points; NaN-free input assumed."""
    cs = np.cumsum(a.astype(np.float64), axis=axis)
    out = cs.copy()
    sl_hi = [slice(None)] * a.ndim
    sl_lo = [slice(None)] * a.ndim
    sl_hi[axis] = slice(w, None)
    sl_lo[axis] = slice(None, -w)
    out[tuple(sl_hi)] = cs[tuple(sl_hi)] - cs[tuple(sl_lo)]
    return out


def build_ctx(freq, truncate_frac=None):
    """truncate_frac exists for the LOOKAHEAD AUDIT only: everything from that fraction of the
    sample onward is replaced by reversed, rescaled data. A config whose weights on the surviving
    PREFIX move as a result is reading the future."""
    z = np.load(PANEL, allow_pickle=True)
    syms = list(z["symbols"])
    grid = z["grid"]
    close = z["close"]
    qv = z["qv"]
    tbqv = z["tbqv"]
    z.close()
    # The cached kline download is partial: most of the 138 symbols have <50% bar coverage and
    # can never be tradable. Dropping them costs no cross-section and cuts every array ~2.5x,
    # which matters because this box runs several other agents' sweeps at the same time.
    cov = np.isfinite(close).mean(1)
    keep = np.where((cov > 0.40) | (np.array(syms) == "BTCUSDT") | (np.array(syms) == "ETHUSDT"))[0]
    syms = [syms[i] for i in keep]
    close = close[keep]; qv = qv[keep]; tbqv = tbqv[keep]

    if truncate_frac:
        cut = int(close.shape[1] * truncate_frac)
        close = close.copy(); qv = qv.copy(); tbqv = tbqv.copy()
        close[:, cut:] = close[:, cut:][:, ::-1] * 1.37
        qv[:, cut:] = qv[:, cut:][:, ::-1]
        tbqv[:, cut:] = tbqv[:, cut:][:, ::-1]

    if freq > 1:
        n = (close.shape[1] // freq) * freq
        close = close[:, freq - 1:n:freq]
        qv = rolling_sum(qv[:, :n], freq, axis=1)[:, freq - 1::freq].astype(np.float32)
        tbqv = rolling_sum(tbqv[:, :n], freq, axis=1)[:, freq - 1::freq].astype(np.float32)
        grid = grid[freq - 1:n:freq]

    lc = np.log(close, out=np.full_like(close, np.nan), where=close > 0)
    r = np.diff(lc, axis=1).astype(np.float32)
    grid = grid[1:]
    valid = np.isfinite(r)
    r = np.where(valid, r, 0.0).astype(np.float32)
    qv = qv[:, 1:]
    tbqv = tbqv[:, 1:]

    # trailing-24h dollar volume, causal (shifted one bar)
    w24 = max(1, (24 * 60) // (5 * freq))
    adv = rolling_sum(qv, w24, axis=1).astype(np.float32)
    adv = np.concatenate([np.zeros((adv.shape[0], 1), np.float32), adv[:, :-1]], axis=1)

    c = Ctx()
    c.freq = freq
    c.syms = syms
    c.grid = grid
    c.r = r
    c.valid = valid
    c.qv = qv
    c.tbqv = tbqv
    c.adv = adv
    c.bars_per_year = BARS_PER_YEAR_5M / freq
    c.ib = syms.index("BTCUSDT")
    c.ie = syms.index("ETHUSDT") if "ETHUSDT" in syms else None
    c.majors = [syms.index(s) for s in ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT") if s in syms]
    c.design = grid < DESIGN_END_MS

    # tradability: valid return, valid previous return, liquid
    tr = valid.copy()
    tr[:, 1:] &= valid[:, :-1]
    tr &= adv > MIN_ADV_USD
    tr[c.ib] = False                     # BTC is the leader, not a leg
    c.tradable = tr

    # rolling beta to BTC from DAILY returns (60d), broadcast onto bars -- cheap + robust
    c.beta = _daily_beta(c)
    del close, lc, valid, adv
    c.valid = None
    gc.collect()
    return c


def _daily_beta(c, lookback=60):
    bpd = int(round(24 * 60 / (5 * c.freq)))
    T = c.r.shape[1]
    nd = T // bpd
    rd = c.r[:, :nd * bpd].reshape(c.r.shape[0], nd, bpd).sum(2).astype(np.float64)
    b = rd[c.ib]
    xy = rolling_sum(rd * b[None, :], lookback, axis=1)
    xx = rolling_sum(b * b, lookback)
    beta_d = np.where(xx[None, :] > 0, xy / np.maximum(xx[None, :], 1e-12), 1.0)
    beta_d = np.clip(beta_d, 0.0, 3.0)
    beta_d[:, :lookback] = 1.0
    beta_d = np.concatenate([np.ones((rd.shape[0], 1)), beta_d[:, :-1]], axis=1)  # causal
    out = np.repeat(beta_d, bpd, axis=1).astype(np.float32)
    if out.shape[1] < T:
        out = np.concatenate([out, np.repeat(out[:, -1:], T - out.shape[1], axis=1)], axis=1)
    return out[:, :T]


# ----------------------------------------------------------------- helpers
def lag(a, k=1):
    out = np.zeros_like(a)
    if a.ndim == 1:
        out[k:] = a[:-k]
    else:
        out[:, k:] = a[:, :-k]
    return out


def roll_k(a, k):
    """Causal sum of the last k values (value at t uses t-k..t-1)."""
    if k == 1:                      # fast path: no cumsum, no float64 temporaries
        return lag(a, 1)
    s = rolling_sum(a, k, axis=-1).astype(np.float32)
    return lag(s, 1)


def xs_demean(W, tr):
    W = np.where(tr, W, 0.0)
    n = tr.sum(0)
    m = np.where(n > 0, W.sum(0) / np.maximum(n, 1), 0.0)
    W = np.where(tr, W - m[None, :], 0.0)
    return W


def gross1(W):
    s = np.abs(W).sum(0)
    return np.where(s > 0, W / np.maximum(s, 1e-12), 0.0).astype(np.float32)


def zscore_ts(x, w):
    m = roll_k(x, w) / w
    v = roll_k(x * x, w) / w - m * m
    return np.where(v > 1e-18, (lag(x, 1) - m) / np.sqrt(np.maximum(v, 1e-18)), 0.0)


def rank_xs(X, tr):
    """Cross-sectional rank in [-1,1] over tradable names, 0 elsewhere."""
    S = tr.shape[0]
    order = np.argsort(np.argsort(np.where(tr, X, -1e30), axis=0), axis=0).astype(np.float32)
    n = tr.sum(0).astype(np.float32)
    rk = order - (S - n)[None, :]                    # masked names sort to the bottom S-n slots
    out = np.where(tr & (n[None, :] > 2), 2.0 * rk / np.maximum(n[None, :] - 1, 1) - 1.0, 0.0)
    return out.astype(np.float32)


# ----------------------------------------------------------------- scoring
def score(c, W, name):
    W = gross1(np.where(c.tradable, W, 0.0))
    r = c.r
    d = c.design
    pr = np.einsum("it,it->t", W, r).astype(np.float64)
    dW = np.abs(W - lag(W, 1)).sum(0)
    cost = dW * (COST_BP_PER_SIDE * 1e-4)
    ann = np.sqrt(c.bars_per_year)

    def sh(x, m):
        x = x[m]
        x = x[np.isfinite(x)]
        if x.size < 100 or x.std() == 0:
            return 0.0
        return float(x.mean() / x.std() * ann)

    active = (np.abs(W).sum(0) > 0)
    res = dict(
        name=name, n_bars=int(d.sum()), active_frac=float(active[d].mean()),
        gross_sharpe=sh(pr, d), net_sharpe=sh(pr - cost, d),
        gross_bp_per_bar=float(pr[d].mean() * 1e4),
        turnover_per_bar=float(dW[d].mean()),
        cost_bp_per_bar=float(cost[d].mean() * 1e4),
        holdout_gross_sharpe=sh(pr, ~d), holdout_net_sharpe=sh(pr - cost, ~d),
    )
    return res, W, pr


def null_sharpes(c, W, shifts):
    """Re-score W against time-shifted returns. Positive shift = returns pulled from the future
    beyond the signal's horizon; negative = anti-causal. Both destroy lead-lag."""
    r = c.r
    d = c.design
    ann = np.sqrt(c.bars_per_year)
    out = []
    for s in shifts:
        if s > 0:
            pr = np.einsum("it,it->t", W[:, :-s], r[:, s:])
            m = d[:-s]
        else:
            k = -s
            pr = np.einsum("it,it->t", W[:, k:], r[:, :-k])
            m = d[k:]
        x = pr[m].astype(np.float64)
        out.append(0.0 if x.size < 100 or x.std() == 0 else float(x.mean() / x.std() * ann))
    return out


# ----------------------------------------------------------------- formulas
def make_configs():
    """(name, freq, description, builder). freq is in 5-minute units."""
    F = []

    def add(name, freq, desc, fn):
        F.append((name, freq, desc, fn))

    # ---- A. leader time-series push, directional (no XS neutralisation)
    add("A1_btc_push_dir_5m", 1, "long every liquid alt when BTC's last 5m return is up, short when down (equal weight, directional)",
        lambda c: np.where(c.tradable, np.sign(lag(c.r[c.ib]))[None, :], 0.0))
    add("A2_btc_push_dir_30m", 6, "same, BTC's last 30m return sign drives a 30m-held equal-weight alt book",
        lambda c: np.where(c.tradable, np.sign(lag(c.r[c.ib]))[None, :], 0.0))
    add("A3_btc_push_dir_4h", 48, "BTC's last 4h return sign drives a 4h-held equal-weight alt book",
        lambda c: np.where(c.tradable, np.sign(lag(c.r[c.ib]))[None, :], 0.0))

    # ---- B. beta catch-up gap, cross-sectionally neutral (the classic lead-lag)
    def betagap(k):
        def f(c):
            g = c.beta * roll_k(c.r[c.ib][None, :], k) - roll_k(c.r, k)
            return xs_demean(g, c.tradable)
        return f
    add("B1_betagap_k1_5m", 1, "alt is long by how far its beta-implied move from BTC's last bar exceeds its own realised move (XS-neutral)", betagap(1))
    add("B2_betagap_k3_5m", 1, "same catch-up gap measured over BTC's last 3 bars (15m) at 5m rebalancing", betagap(3))
    add("B3_betagap_k12_5m", 1, "catch-up gap over the last 1h of BTC vs alt, 5m rebalancing", betagap(12))
    add("B4_betagap_k1_30m", 6, "catch-up gap at 30m bars, one-bar lookback", betagap(1))
    add("B5_betagap_k1_1h", 12, "catch-up gap at 1h bars", betagap(1))
    add("B6_betagap_k1_4h", 48, "catch-up gap at 4h bars", betagap(1))
    add("B7_betagap_k1_1d", 288, "catch-up gap at daily bars", betagap(1))

    # ---- C. rank / robustness variants of the gap
    add("C1_betagap_rank_5m", 1, "cross-sectional RANK of the 1-bar catch-up gap instead of its raw size",
        lambda c: rank_xs(c.beta * roll_k(c.r[c.ib][None, :], 1) - roll_k(c.r, 1), c.tradable))
    add("C2_gap_beta1_5m", 1, "catch-up gap assuming beta==1 for every alt (no beta estimation at all)",
        lambda c: xs_demean(roll_k(c.r[c.ib][None, :], 1) - roll_k(c.r, 1), c.tradable))
    add("C3_gap_volscaled_5m", 1, "catch-up gap divided by the alt's trailing 1d return volatility (risk-parity legs)",
        lambda c: xs_demean((c.beta * roll_k(c.r[c.ib][None, :], 1) - roll_k(c.r, 1))
                            / np.sqrt(np.maximum(roll_k(c.r * c.r, 288) / 288, 1e-12)), c.tradable))

    # ---- D. leader push with NO own-return term (pure transmission, XS-neutral)
    add("D1_btcpush_beta_xs_5m", 1, "BTC's last-bar return times the alt's beta, cross-sectionally demeaned -- high-beta alts get the push, no own-return term",
        lambda c: xs_demean(c.beta * lag(c.r[c.ib])[None, :], c.tradable))
    add("D2_btcpush_illiq_5m", 1, "BTC's last-bar return weighted by INVERSE liquidity rank -- the thin-book alts are the ones that lag",
        lambda c: -rank_xs(np.broadcast_to(c.adv, c.r.shape), c.tradable) * np.sign(lag(c.r[c.ib]))[None, :])
    add("D3_majors_push_xs_30m", 6, "equal-weight BTC/ETH/BNB/SOL/XRP basket return over the last 30m times beta, XS-demeaned",
        lambda c: xs_demean(c.beta * lag(c.r[c.majors].mean(0))[None, :], c.tradable))

    # ---- E. order-flow lead (taker-buy imbalance of the leader)
    def imb(c, i):
        q = c.qv[i]
        return np.where(q > 0, c.tbqv[i] / np.maximum(q, 1e-9) - 0.5, 0.0)
    add("E1_btc_takerimb_dir_5m", 1, "BTC aggressor imbalance (taker-buy share minus half) last bar, directional across all alts",
        lambda c: np.where(c.tradable, lag(imb(c, c.ib))[None, :], 0.0))
    add("E2_btc_takerimb_beta_xs_5m", 1, "BTC aggressor imbalance times alt beta, cross-sectionally demeaned",
        lambda c: xs_demean(c.beta * lag(imb(c, c.ib))[None, :], c.tradable))
    add("E3_btc_takerimb_1h", 12, "BTC aggressor imbalance at 1h aggregation, directional across alts",
        lambda c: np.where(c.tradable, lag(imb(c, c.ib))[None, :], 0.0))

    # ---- F. rotation leader: ETH-vs-BTC leads the alt complex
    add("F1_ethbtc_rot_30m", 6, "when ETH outperformed BTC over the last 30m, go long the alt complex and short nothing else (XS-demeaned by beta)",
        lambda c: xs_demean(c.beta * lag(c.r[c.ie] - c.r[c.ib])[None, :], c.tradable) if c.ie is not None else np.zeros_like(c.r))
    add("F2_ethbtc_rot_4h", 48, "same ETH-minus-BTC rotation signal at 4h", 
        lambda c: xs_demean(c.beta * lag(c.r[c.ie] - c.r[c.ib])[None, :], c.tradable) if c.ie is not None else np.zeros_like(c.r))

    # ---- G. sign flip: overshoot / fade
    add("G1_betagap_FADE_5m", 1, "the SIGN-FLIPPED catch-up gap: alts that already ran past their beta-implied move keep running",
        lambda c: -xs_demean(c.beta * roll_k(c.r[c.ib][None, :], 1) - roll_k(c.r, 1), c.tradable))
    add("G2_gap_after_bigbtc_5m", 1, "catch-up gap, but only armed on bars where BTC's last move exceeded 2 trailing sigma",
        lambda c: xs_demean(c.beta * roll_k(c.r[c.ib][None, :], 1) - roll_k(c.r, 1), c.tradable)
                  * (np.abs(zscore_ts(c.r[c.ib], 288)) > 2.0)[None, :])
    add("G3_gap_calm_only_5m", 1, "catch-up gap armed only on CALM bars (BTC move under 1 trailing sigma) -- the complement of G2",
        lambda c: xs_demean(c.beta * roll_k(c.r[c.ib][None, :], 1) - roll_k(c.r, 1), c.tradable)
                  * (np.abs(zscore_ts(c.r[c.ib], 288)) < 1.0)[None, :])

    # ---- H. time-of-day conditioning on the same transmission
    def hourmask(c, lo, hi):
        h = ((c.grid // 3600000) % 24).astype(np.int64)
        return ((h >= lo) & (h < hi))
    add("H1_gap_asia_hours_5m", 1, "catch-up gap traded only during 00:00-08:00 UTC (Asia session)",
        lambda c: xs_demean(c.beta * roll_k(c.r[c.ib][None, :], 1) - roll_k(c.r, 1), c.tradable) * hourmask(c, 0, 8)[None, :])
    add("H2_gap_us_hours_5m", 1, "catch-up gap traded only during 13:00-21:00 UTC (US session)",
        lambda c: xs_demean(c.beta * roll_k(c.r[c.ib][None, :], 1) - roll_k(c.r, 1), c.tradable) * hourmask(c, 13, 21)[None, :])

    # ---- I. liquidity-tier lead-lag: the liquid basket leads the illiquid tail
    def tierlead(k):
        def f(c):
            liq = rank_xs(np.broadcast_to(c.adv, c.r.shape), c.tradable)
            top = (liq > 0.6)
            lead = np.where(top, c.r, 0.0).sum(0) / np.maximum(top.sum(0), 1)
            g = c.beta * roll_k(lead[None, :], k) - roll_k(c.r, k)
            return xs_demean(np.where(liq < 0.0, g, 0.0), c.tradable)
        return f
    add("I1_liqtier_lead_k1_5m", 1, "the top-liquidity-quintile alt basket leads; trade only the bottom-half-liquidity names on their catch-up gap", tierlead(1))
    add("I2_liqtier_lead_k6_5m", 1, "same tier lead-lag with a 30m leader lookback, 5m rebalance", tierlead(6))

    # ---- J. reverse direction: does the alt complex lead BTC?
    def altlead(k):
        def f(c):
            m = np.where(c.tradable, c.r, 0.0).sum(0) / np.maximum(c.tradable.sum(0), 1)
            sig = roll_k(m[None, :], k)[0] - roll_k(c.r[c.ib][None, :], k)[0]
            W = np.zeros_like(c.r)
            W[c.ib] = sig
            return W
        return f
    add("J1_alts_lead_btc_k1_5m", 1, "trade BTC ALONE on the gap between the equal-weight alt complex and BTC over the last 5m (reverse lead-lag)", altlead(1))
    add("J2_alts_lead_btc_k6_30m", 6, "trade BTC alone on the alt-complex-minus-BTC gap over the last 3h, 30m rebalance", altlead(6))

    # ---- K. multi-lag distributed transmission
    add("K1_gap_multilag_5m", 1, "catch-up gap summed over BTC lookbacks 1, 3 and 12 bars (distributed-lag transmission)",
        lambda c: xs_demean(sum(c.beta * roll_k(c.r[c.ib][None, :], k) - roll_k(c.r, k) for k in (1, 3, 12)), c.tradable))
    add("K2_gap_accel_5m", 1, "gap over BTC's last bar MINUS the gap over the previous 3 bars (transmission acceleration)",
        lambda c: xs_demean((c.beta * roll_k(c.r[c.ib][None, :], 1) - roll_k(c.r, 1))
                            - lag(c.beta * roll_k(c.r[c.ib][None, :], 3) - roll_k(c.r, 3), 1), c.tradable))
    return F


# ----------------------------------------------------------------- main
def main():
    configs = make_configs()
    by_freq = {}
    for cfg in configs:
        by_freq.setdefault(cfg[1], []).append(cfg)

    results = []
    null_by_freq = {}
    for freq in sorted(by_freq):
        t0 = time.time()
        c = build_ctx(freq)
        T = c.r.shape[1]
        bpd = max(1, int(round(24 * 60 / (5 * freq))))
        lo, hi = bpd, max(bpd + 1, T // 10)
        shifts = rng.integers(lo, hi, size=N_NULL // 2)
        shifts = np.concatenate([shifts, -shifts])
        nulls = []
        print(f"[freq={freq}] ctx {c.r.shape} tradable={c.tradable.mean():.2f} ({time.time()-t0:.0f}s)", flush=True)
        for name, _f, desc, fn in by_freq[freq]:
            try:
                W = fn(c)
            except Exception as e:
                print(f"  {name}: BUILD FAILED {e}", flush=True)
                continue
            res, W, _pr = score(c, W, name)
            res["freq_5m_units"] = freq
            res["formula_desc"] = desc
            results.append(res)
            nulls.append(null_sharpes(c, W, shifts))
            gc.collect()
            print(f"  {name:28s} gross={res['gross_sharpe']:+6.2f} net={res['net_sharpe']:+8.2f} "
                  f"tno={res['turnover_per_bar']:.3f} bp/bar={res['gross_bp_per_bar']:+.3f}", flush=True)
            del W
        null_by_freq[freq] = (np.array(nulls), [x[0] for x in by_freq[freq]])
        del c

    # empirical expected-max under the null, pooled across ALL configs per null draw
    all_names = []
    cols = []
    for freq, (arr, names) in null_by_freq.items():
        if arr.size == 0:
            continue
        all_names += names
        cols.append(arr)
    NULL = np.vstack(cols)                       # (n_configs, n_draws)
    maxnull = NULL.max(axis=0)
    exp_max = float(maxnull.mean())
    p95_max = float(np.percentile(maxnull, 95))
    sd_null = float(NULL.std())

    out = dict(
        block="crypto_perp_5m_leadlag",
        panel=PANEL,
        design_window=["2023-01-01", "2025-06-30"],
        holdout_window=["2025-07-01", "2026-08-17"],
        cost_bp_per_side=COST_BP_PER_SIDE,
        cost_provenance="BROKER_SCHEDULE (Binance USD-M VIP0 taker 5bp) + STRESS_LADDER (1bp slippage). NOT a measurement of our own fills.",
        n_formulas=len(results),
        null=dict(n_draws=int(NULL.shape[1]), method="time-shifted returns (>=1 day, both signs), same shift for every config so cross-config correlation is preserved",
                  sd_single_config_sharpe=sd_null,
                  expected_max_sharpe=exp_max, p95_max_sharpe=p95_max,
                  naive_sqrt2lnN=float(np.sqrt(2 * np.log(max(len(results), 2)))) * sd_null),
        results=sorted(results, key=lambda r: -abs(r["gross_sharpe"])),
    )
    os.makedirs(os.path.dirname(OUTJ), exist_ok=True)
    json.dump(out, open(OUTJ, "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "results"}, indent=1))
    print(f"WROTE {OUTJ}")


if __name__ == "__main__":
    main()
