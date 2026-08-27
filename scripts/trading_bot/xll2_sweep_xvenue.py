#!/usr/bin/env python3
"""XLL-2, block B: CROSS-VENUE lead-lag between Hyperliquid and Binance USD-M perps.

The first XLL sweep tested BTC -> alt transmission *inside one venue*. It never tested one
VENUE leading another, because it had no second venue on disk. It does now: t25_cache holds
hourly Hyperliquid funding + premium prints for 107 coins (2023-07 onwards), and xll_cache
holds Binance USD-M 5-minute closes for 138 perps (2023-01 onwards).

Hyperliquid's PREMIUM is (HL mark - oracle index) / index. Its change over the last hour is
literally "how far Hyperliquid's price moved relative to the global index" -- i.e. a
cross-venue price dislocation. The question this block asks: does a dislocation on venue A
predict the next hour's return on venue B?

Same discipline as every other block: design window only, empirical shared-shift null,
per-side costs charged on realised turnover, Sharpe on day-aggregated P&L.
"""
from __future__ import annotations
import json, os, time, glob
import numpy as np

ROOT = "/home/anont/meme"
PERP5M = f"{ROOT}/research/data/xll_cache/perp5m_panel.npz"
HLDIR = f"{ROOT}/research/data/t25_cache/hl"
UNIV = f"{ROOT}/research/data/t25_cache/universe.json"
CACHE = f"{ROOT}/research/data/xll2_cache/xvenue_1h_panel.npz"
OUTJ = f"{ROOT}/research/trading_bot/SWEEP_xll_leadlag_v2_xvenue.json"

DESIGN_END_MS = 1751328000000        # 2025-07-01 00:00 UTC -- same split as the first crypto block
COST_BP_PER_SIDE = 6.0               # Binance USD-M VIP0 taker 5bp + 1bp slippage rung
N_NULL = 200
rng = np.random.default_rng(20260820)


def build_panel():
    if os.path.exists(CACHE):
        return
    z = np.load(PERP5M, allow_pickle=True)
    syms = [str(s) for s in z["symbols"]]
    grid = z["grid"].astype(np.int64)
    C = z["close"].astype(np.float32)
    QV = z["qv"].astype(np.float32)
    TB = z["tbqv"].astype(np.float32)
    z.close()
    # hourly close = the 5m close stamped at :55 of each hour
    off = int(np.argmax((grid % 3600000) == 3300000))
    sel = np.arange(off, len(grid), 12)
    hgrid = grid[sel] + 300000                       # the hour ENDS here; value known at this instant
    Ch = C[:, sel]
    QVh = np.add.reduceat(np.nan_to_num(QV), np.maximum(sel - 11, 0), axis=1)[:, :len(sel)] if False else None
    # simple hourly quote volume: sum the 12 five-minute buckets ending at sel
    idx0 = sel - 11
    ok = idx0 >= 0
    QVh = np.zeros_like(Ch)
    TBh = np.zeros_like(Ch)
    for j in range(12):
        take = idx0[ok] + j
        QVh[:, ok] += np.nan_to_num(QV[:, take])
        TBh[:, ok] += np.nan_to_num(TB[:, take])

    u = json.load(open(UNIV))
    coin2bin = {d["coin"]: d["binance"] for d in u["download_universe"]}
    files = sorted(glob.glob(f"{HLDIR}/*.json"))
    hl_prem = np.full(Ch.shape, np.nan, np.float32)
    hl_fund = np.full(Ch.shape, np.nan, np.float32)
    sidx = {s: i for i, s in enumerate(syms)}
    n_map = 0
    for f in files:
        d = json.load(open(f))
        coin = d["coin"]
        b = coin2bin.get(coin)
        if b is None or b not in sidx:
            continue
        i = sidx[b]
        pr = d["prints"]
        if not pr:
            continue
        ts = np.array([p[0] for p in pr], np.int64)
        fu = np.array([float(p[1]) for p in pr], np.float32)
        pm = np.array([float(p[2]) for p in pr], np.float32)
        # HL stamps the print a few hundred ms after the hour boundary; snap to that hour's END
        ts = (ts // 3600000) * 3600000 + 3600000
        pos = np.searchsorted(hgrid, ts)
        keep = (pos < len(hgrid))
        pos = pos[keep]
        hit = hgrid[pos] == ts[keep]
        src = np.nonzero(keep)[0][hit]
        hl_prem[i, pos[hit]] = pm[src]
        hl_fund[i, pos[hit]] = fu[src]
        n_map += 1
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    np.savez_compressed(CACHE, symbols=np.array(syms), t=hgrid, close=Ch, qv=QVh, tbqv=TBh,
                        hl_prem=hl_prem, hl_fund=hl_fund)
    print(f"panel: {Ch.shape} hours, {n_map} coins mapped to Hyperliquid, "
          f"HL coverage {np.isfinite(hl_prem).mean():.3f}")


def rolling_sum(a, w, axis=-1):
    cs = np.cumsum(a.astype(np.float64), axis=axis)
    out = cs.copy()
    hi = [slice(None)] * a.ndim
    lo = [slice(None)] * a.ndim
    hi[axis] = slice(w, None)
    lo[axis] = slice(None, -w)
    out[tuple(hi)] = cs[tuple(hi)] - cs[tuple(lo)]
    return out


def lag(a, k=1):
    out = np.zeros_like(a)
    if a.ndim == 1:
        out[k:] = a[:-k]
    else:
        out[:, k:] = a[:, :-k]
    return out


def xs_demean(W, tr):
    W = np.where(tr, W, 0.0)
    n = tr.sum(0)
    m = np.where(n > 0, W.sum(0) / np.maximum(n, 1), 0.0)
    return np.where(tr, W - m[None, :], 0.0).astype(np.float32)


def gross1(W):
    s = np.abs(W).sum(0)
    return np.where(s > 0, W / np.maximum(s, 1e-12), 0.0).astype(np.float32)


def rank_xs(X, tr):
    S = tr.shape[0]
    order = np.argsort(np.argsort(np.where(tr, X, -1e30), axis=0), axis=0).astype(np.float32)
    n = tr.sum(0).astype(np.float32)
    rk = order - (S - n)[None, :]
    return np.where(tr & (n[None, :] > 2), 2.0 * rk / np.maximum(n[None, :] - 1, 1) - 1.0, 0.0).astype(np.float32)


def smooth_hold(W, h):
    return W if h <= 1 else (rolling_sum(W, h, axis=1) / float(h)).astype(np.float32)


class Ctx:
    pass


def build_ctx(truncate_frac=None):
    z = np.load(CACHE, allow_pickle=True)
    syms = [str(s) for s in z["symbols"]]
    t = z["t"].astype(np.int64)
    C = z["close"].astype(np.float32)
    QV = z["qv"].astype(np.float32)
    TB = z["tbqv"].astype(np.float32)
    P = z["hl_prem"].astype(np.float32)
    FU = z["hl_fund"].astype(np.float32)
    z.close()
    if truncate_frac:
        cut = int(C.shape[1] * truncate_frac)
        for A in (C, QV, TB, P, FU):
            A[:, cut:] = A[:, cut:][:, ::-1]
        C[:, cut:] *= 1.37

    lc = np.log(C, out=np.full_like(C, np.nan), where=C > 0)
    r = np.zeros_like(lc)
    r[:, 1:] = lc[:, 1:] - lc[:, :-1]
    valid = np.isfinite(r)
    r = np.nan_to_num(r).astype(np.float32)

    # EXECUTION leg: signal known at the close of hour t -> hold hour t+1
    R = np.zeros_like(r)
    R[:, :-1] = r[:, 1:]
    exec_ok = np.zeros_like(valid)
    exec_ok[:, :-1] = valid[:, 1:]

    have_hl = np.isfinite(P)
    adv = lag((rolling_sum(np.nan_to_num(QV), 168, axis=1) / 168.0).astype(np.float32), 1)

    c = Ctx()
    c.syms = syms; c.t = t; c.idx = {s: i for i, s in enumerate(syms)}
    c.r = r; c.R = R
    c.prem = np.nan_to_num(P)
    c.fund_hl = np.nan_to_num(FU)
    c.qv = np.nan_to_num(QV); c.tb = np.nan_to_num(TB)
    c.adv = adv
    c.day = (t // 86400000).astype(np.int64)
    d0 = c.day - c.day.min()
    c.dayid = d0
    c.n_days = int(d0.max() + 1)
    c.design_bar = t < DESIGN_END_MS
    c.day_design = np.zeros(c.n_days, bool)
    c.day_design[d0[c.design_bar]] = True
    # only hours where HL actually printed AND the coin traded on Binance
    c.tradable = exec_ok & valid & have_hl & (adv > 3e5)
    c.liquid = c.tradable & (adv > 1e7)
    c.have_hl = have_hl
    return c


def roll_k(a, k):
    return rolling_sum(a, k, axis=-1).astype(np.float32)


def make_configs(c):
    F = []

    def add(name, desc, fn, hold=1):
        F.append((name, desc, fn, hold))

    P = c.prem
    dP1 = P - lag(P, 1)
    dP4 = P - lag(P, 4)
    dP24 = P - lag(P, 24)
    pmean24 = roll_k(P, 24) / 24.0
    psd = np.sqrt(np.maximum(roll_k((P - pmean24) ** 2, 168) / 168.0, 1e-14))

    # ---- level of the cross-venue basis
    add("V1_hlprem_level_h1", "long the coins that trade RICHEST on Hyperliquid relative to the index, short the cheapest, on Binance (cross-venue basis catch-up), held 1h",
        lambda c: xs_demean(P, c.tradable), 1)
    add("V2_hlprem_level_FADE", "SIGN-FLIPPED: short what is rich on Hyperliquid (the dislocation mean-reverts rather than propagates)",
        lambda c: -xs_demean(P, c.tradable), 1)
    add("V3_hlprem_level_h4", "same cross-venue basis level, held 4 hours", lambda c: xs_demean(P, c.tradable), 4)
    add("V4_hlprem_level_h24", "same cross-venue basis level, held 24 hours", lambda c: xs_demean(P, c.tradable), 24)
    add("V5_hlprem_rank", "cross-sectional RANK of the Hyperliquid premium instead of its size",
        lambda c: rank_xs(P, c.tradable), 4)
    add("V6_hlprem_z168", "Hyperliquid premium as a z-score against its own trailing week (each coin vs its own normal basis)",
        lambda c: xs_demean(np.clip((P - pmean24) / psd, -5, 5), c.tradable), 4)

    # ---- CHANGE in the basis = venue A's price moving away from the index
    add("W1_hldislocation_1h", "Hyperliquid's price moved away from the index over the last hour; go WITH that move on Binance (venue A leads venue B)",
        lambda c: xs_demean(dP1, c.tradable), 1)
    add("W2_hldislocation_1h_FADE", "same one-hour Hyperliquid dislocation traded the other way (Binance does NOT follow, it reverts)",
        lambda c: -xs_demean(dP1, c.tradable), 1)
    add("W3_hldislocation_4h", "Hyperliquid's dislocation from the index over the last 4 hours, followed on Binance", lambda c: xs_demean(dP4, c.tradable), 4)
    add("W4_hldislocation_24h", "Hyperliquid's dislocation over the last 24 hours, followed on Binance", lambda c: xs_demean(dP24, c.tradable), 24)
    add("W5_hldislocation_1h_rank", "cross-sectional rank of the one-hour Hyperliquid dislocation", lambda c: rank_xs(dP1, c.tradable), 1)
    add("W6_hldislocation_1h_liquid", "the one-hour Hyperliquid dislocation traded only on the coins with a deep Binance book (>$10M/h)",
        lambda c: xs_demean(dP1, c.liquid), 1)
    add("W7_hldislocation_bigonly", "the one-hour dislocation armed only when it exceeds 2 trailing sigma of that coin's basis (big cross-venue gaps only)",
        lambda c: xs_demean(np.where(np.abs(dP1) > 2.0 * psd, dP1, 0.0), c.tradable), 1)
    add("W8_hldislocation_accel", "the last hour's dislocation MINUS the previous three hours' (cross-venue transmission acceleration)",
        lambda c: xs_demean(dP1 - (dP4 - dP1) / 3.0, c.tradable), 1)

    # ---- funding as the cross-venue signal
    add("Y1_hlfunding_level", "long the coins paying the most funding on Hyperliquid (venue-A crowding as a directional tell), held 8h",
        lambda c: xs_demean(c.fund_hl, c.tradable), 8)
    add("Y2_hlfunding_FADE", "short the coins paying the most Hyperliquid funding (crowding unwinds)",
        lambda c: -xs_demean(c.fund_hl, c.tradable), 8)
    add("Y3_hlfunding_change_24h", "the 24-hour CHANGE in Hyperliquid funding (venue-A positioning is shifting)",
        lambda c: xs_demean(c.fund_hl - lag(c.fund_hl, 24), c.tradable), 8)

    # ---- venue A's basis vs venue B's own flow: a genuinely cross-venue interaction
    tbi = np.where(c.qv > 0, c.tb / np.maximum(c.qv, 1e-9) - 0.5, 0.0).astype(np.float32)
    add("Z1_prem_x_binance_flow", "Hyperliquid's dislocation TIMES Binance's own taker-buy imbalance: the two venues agreeing",
        lambda c: xs_demean(dP1 * tbi, c.tradable), 1)
    add("Z2_prem_vs_binance_flow", "Hyperliquid's dislocation MINUS Binance's taker imbalance (standardised): the two venues DISagreeing",
        lambda c: xs_demean(np.sign(dP1) * (np.abs(dP1) > psd) - 4.0 * tbi, c.tradable), 1)
    add("Z3_binanceflow_only", "CONTROL: Binance's own taker imbalance alone, no cross-venue term at all",
        lambda c: xs_demean(tbi, c.tradable), 1)
    add("Z4_btc_hlprem_leads_alts", "BTC's Hyperliquid premium (one venue's view of the majors) times each alt's BTC beta -- majors' cross-venue basis leading the complex",
        lambda c: xs_demean(np.ones_like(c.r) * P[c.idx["BTCUSDT"]][None, :], c.tradable) if "BTCUSDT" in c.idx else np.zeros_like(c.r), 4)
    return F


def score(c, W, hold):
    W = smooth_hold(W, hold)
    W = gross1(np.where(c.tradable, W, 0.0))
    pr = np.einsum("it,it->t", W, c.R).astype(np.float64)
    dW = np.abs(W - lag(W, 1))
    cost = dW.sum(0).astype(np.float64) * (COST_BP_PER_SIDE * 1e-4)
    tno = dW.sum(0).astype(np.float64)
    g = np.bincount(c.dayid, weights=pr, minlength=c.n_days)
    n = np.bincount(c.dayid, weights=pr - cost, minlength=c.n_days)
    tn = np.bincount(c.dayid, weights=tno, minlength=c.n_days)
    cs = np.bincount(c.dayid, weights=cost, minlength=c.n_days)
    d = c.day_design
    ann = np.sqrt(365.0)

    def sh(x, m):
        x = x[m]
        x = x[np.isfinite(x)]
        return 0.0 if x.size < 60 or x.std() == 0 else float(x.mean() / x.std() * ann)

    be = float(g[d].mean() / max(tn[d].mean(), 1e-12) * 1e4) if tn[d].mean() > 0 else 0.0
    be_h = float(g[~d].mean() / max(tn[~d].mean(), 1e-12) * 1e4) if tn[~d].mean() > 0 else 0.0
    return dict(n_days=int(d.sum()),
                gross_sharpe=sh(g, d), net_sharpe=sh(n, d),
                gross_bp_per_day=float(g[d].mean() * 1e4),
                turnover_per_day=float(tn[d].mean()),
                cost_bp_per_day=float(cs[d].mean() * 1e4),
                breakeven_bp_per_side_design=be,
                holdout_gross_sharpe=sh(g, ~d), holdout_net_sharpe=sh(n, ~d),
                breakeven_bp_per_side_holdout=be_h), W


def null_sharpes(c, W, shifts):
    d = c.day_design; ann = np.sqrt(365.0); out = []
    for s in shifts:
        if s > 0:
            pr = np.einsum("it,it->t", W[:, :-s], c.R[:, s:]); dd = c.dayid[:-s]
        else:
            k = -s
            pr = np.einsum("it,it->t", W[:, k:], c.R[:, :-k]); dd = c.dayid[k:]
        g = np.bincount(dd, weights=pr.astype(np.float64), minlength=c.n_days)[d]
        g = g[np.isfinite(g)]
        out.append(0.0 if g.size < 60 or g.std() == 0 else float(g.mean() / g.std() * ann))
    return out


def main():
    t0 = time.time()
    build_panel()
    c = build_ctx()
    n_hl = int((c.have_hl.sum(1) > 100).sum())
    print(f"ctx syms={len(c.syms)} hours={c.r.shape[1]} coins_with_HL={n_hl} "
          f"tradable/hr={c.tradable.sum(0)[c.design_bar].mean():.1f} "
          f"design_days={c.day_design.sum()} holdout_days={(~c.day_design).sum()} ({time.time()-t0:.0f}s)", flush=True)
    T = c.r.shape[1]
    base = rng.integers(24, T // 8, size=N_NULL // 2)
    shifts = np.concatenate([base, -base])

    results, nulls = [], []
    for name, desc, fn, hold in make_configs(c):
        try:
            W = fn(c)
        except Exception as e:
            print(f"  {name}: BUILD FAILED {type(e).__name__} {e}", flush=True)
            continue
        res, Wn = score(c, W, hold)
        res.update(name=name, formula_desc=desc, hold_hours=hold)
        results.append(res)
        nulls.append(null_sharpes(c, Wn, shifts))
        print(f"  {name:26s} gross={res['gross_sharpe']:+6.2f} net={res['net_sharpe']:+8.2f} "
              f"tno/d={res['turnover_per_day']:6.2f} be={res['breakeven_bp_per_side_design']:5.2f}bp", flush=True)
        del W, Wn

    NULL = np.array(nulls)
    maxnull = NULL.max(axis=0)
    out = dict(block="crypto_cross_venue_hl_binance_1h", panel=CACHE,
               design_window=["2023-07-18", "2025-06-30"], holdout_window=["2025-07-01", "2026-08-17"],
               execution="signal known at the close of hour t; position held over hour t+1; Sharpe on day-aggregated P&L",
               cost_bp_per_side=COST_BP_PER_SIDE,
               cost_provenance="BROKER_SCHEDULE (Binance USD-M VIP0 taker 5bp) + STRESS_LADDER (1bp slippage). NOT a measurement of our own fills.",
               known_bias="Hyperliquid universe is the CURRENT HL listing; 55 delisted coins are flagged in t25 and simply absent here (survivorship). Books are XS-demeaned and dollar-neutral.",
               n_formulas=len(results),
               null=dict(n_draws=int(NULL.shape[1]),
                         method="time-shifted returns (>=1 day, both signs), one shared shift per draw so cross-config correlation is preserved",
                         sd_single_config_sharpe=float(NULL.std()),
                         expected_max_sharpe=float(maxnull.mean()),
                         p95_max_sharpe=float(np.percentile(maxnull, 95)),
                         naive_sqrt2lnN=float(np.sqrt(2 * np.log(max(len(results), 2))) * NULL.std())),
               results=sorted(results, key=lambda r: -abs(r["gross_sharpe"])))
    json.dump(out, open(OUTJ, "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "results"}, indent=1))
    print("WROTE", OUTJ, f"({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
