#!/usr/bin/env python3
"""T34 — Time-Series-Momentum / Trend-Following CONVEXITY on LIQUID crypto perps.

WHY: the memecoin work found the "momentum entry + let winners run + cut losers"
structure has a POSITIVE GROSS edge (+2.2%) but dies on the ~3% memecoin toll +
unexitable liquidity. Liquid crypto perps (BTC/ETH/SOL/majors) have ~0.02-0.05%
taker fee and deep books, so the SAME structure could keep its edge NET. This tests
that honestly, in-sample vs held-out, net of realistic costs, vs BTC-hold + a
random-timing null.

DATA: 100% from the already-cached free Binance USD-M 5m panel
      research/data/xll_cache/perp5m_panel.npz  (138 perps, 2023-01-01..2026-08-17).
      No network fetch. 5m closes are aggregated to daily UTC bars.

TWO ENGINES:
  (A) Continuous risk-parity TSMOM portfolio  (Moskowitz-Ooi-Pedersen construction):
      pos_i = sign(trailing-L return) * (vol_target / ex-ante-vol_i), rebalanced daily,
      equal risk budget across an inverse-vol-weighted, trailing-liquidity-screened basket.
      Gives portfolio net Sharpe / annual return / max drawdown. Lookback L picked on the
      IN-SAMPLE window ONLY, frozen, then reported on the HELD-OUT window.
  (B) Discrete Donchian-breakout + ATR-trailing-stop trade log (the direct memecoin analog:
      momentum entry, let winners run via trailing exit, cut losers via the stop). Gives the
      R-distribution to test CONVEXITY (few big winners paying many small losers).

COSTS: 3.5 bp per side (2.5 bp VIP0-ish taker fee + 1 bp slippage) => 7 bp round trip. NOT zeroed.

HARD LIMITS honoured: paper/measurement only. No orders/wallet/account. No git-commit here.
Free cached data only. No network crawl in the request loop.
"""
from __future__ import annotations
import json, sys, pathlib
import numpy as np
import datetime as dt

ROOT = pathlib.Path("/home/anont/meme")
PANEL = ROOT / "research/data/xll_cache/perp5m_panel.npz"
OUTDIR = ROOT / "research/trading_bot"
CACHE = ROOT / "research/data/t34_cache"
CACHE.mkdir(parents=True, exist_ok=True)

COST_PER_SIDE = 0.00035          # 2.5bp taker + 1bp slippage
RTRIP = 2 * COST_PER_SIDE
DAY_MS = 86_400_000
ANN = 365.0                      # crypto trades every day
IS_OOS_SPLIT = dt.date(2025, 3, 1)   # design (pick L) < split <= held-out
MIN_HIST = 60                    # days listed before eligible
TOPN = 20                        # trailing-ADV liquidity screen -> book size
VOL_SPAN = 40                    # EWMA span (days) for ex-ante vol
VOL_TARGET = 0.40                # 40% annual per-instrument risk unit (scale only; cancels in Sharpe)
LEV_CAP = 4.0                    # cap per-instrument vol-scaled position
rng = np.random.default_rng(34)


# ----------------------------------------------------------------- build daily bars
def build_daily():
    dcache = CACHE / "daily.npz"
    if dcache.exists():
        z = np.load(dcache, allow_pickle=True)
        return [str(s) for s in z["symbols"]], z["days"], z["close"], z["high"], z["low"], z["qv"]
    z = np.load(PANEL, allow_pickle=True)
    syms = [str(s) for s in z["symbols"]]
    grid = z["grid"].astype(np.int64)
    close5 = z["close"].astype(np.float64)
    qv5 = z["qv"].astype(np.float64)
    day_idx = (grid // DAY_MS)
    udays = np.unique(day_idx)
    S = len(syms); D = len(udays)
    dclose = np.full((S, D), np.nan)
    dhigh = np.full((S, D), np.nan)
    dlow = np.full((S, D), np.nan)
    dqv = np.zeros((S, D))
    pos = {d: k for k, d in enumerate(udays)}
    # group columns by day
    order = np.argsort(day_idx, kind="stable")
    di_sorted = day_idx[order]
    bounds = np.searchsorted(di_sorted, udays, side="left")
    bounds = np.append(bounds, len(di_sorted))
    for k in range(D):
        cols = order[bounds[k]:bounds[k + 1]]
        cols = cols[np.argsort(grid[cols])]  # chronological within day
        c = close5[:, cols]
        q = qv5[:, cols]
        valid = np.isfinite(c) & (c > 0)
        # last finite close of the day
        for s in range(S):
            v = valid[s]
            if v.any():
                cc = c[s, v]
                dclose[s, k] = cc[-1]
                dhigh[s, k] = np.nanmax(cc)
                dlow[s, k] = np.nanmin(cc)
        dqv[:, k] = np.nansum(np.where(valid, q, 0.0), axis=1)
    days = udays.astype(np.int64)  # day number since epoch
    np.savez_compressed(dcache, symbols=np.array(syms), days=days,
                        close=dclose, high=dhigh, low=dlow, qv=dqv)
    return syms, days, dclose, dhigh, dlow, dqv


def day_to_date(dnum):
    return dt.date(1970, 1, 1) + dt.timedelta(days=int(dnum))


# ----------------------------------------------------------------- metrics helpers
def sharpe(daily_ret):
    r = np.asarray(daily_ret, float)
    r = r[np.isfinite(r)]
    if len(r) < 5 or r.std() == 0:
        return 0.0
    return r.mean() / r.std() * np.sqrt(ANN)


def ann_return(daily_ret):
    r = np.asarray(daily_ret, float); r = r[np.isfinite(r)]
    return r.mean() * ANN


def max_drawdown(daily_ret):
    r = np.asarray(daily_ret, float); r = np.nan_to_num(r)
    eq = np.cumsum(r)             # additive (vol-unit) equity
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    return float(dd.min())


def ewma_vol(rets, span):
    a = 2.0 / (span + 1.0)
    out = np.full(len(rets), np.nan)
    var = np.nan
    for i, x in enumerate(rets):
        if not np.isfinite(x):
            out[i] = var
            continue
        var = x * x if not np.isfinite(var) else (1 - a) * var + a * x * x
        out[i] = var
    return np.sqrt(out) * np.sqrt(ANN)


# ----------------------------------------------------------------- ENGINE A: continuous TSMOM
def run_continuous(syms, days, close, qv, L, split_idx, eligible_mask):
    """Return dict with daily portfolio net returns split IS/OOS, plus per-instrument net Sharpe."""
    S, D = close.shape
    ret = np.full((S, D), np.nan)
    ret[:, 1:] = close[:, 1:] / close[:, :-1] - 1.0
    ret[~np.isfinite(ret)] = np.nan

    # ex-ante vol per instrument (causal)
    vol = np.full((S, D), np.nan)
    for s in range(S):
        vol[s] = ewma_vol(np.nan_to_num(ret[s], nan=np.nan), VOL_SPAN)

    # momentum signal at t uses close[t]/close[t-L]-1  (known at close t); trade ret[t+1]
    port_ret = np.full(D, np.nan)
    prev_w = np.zeros(S)
    for t in range(L + 1, D - 1):
        elig = eligible_mask[:, t]
        w = np.zeros(S)
        idx = np.where(elig)[0]
        if len(idx) == 0:
            port_ret[t + 1] = 0.0
            # decay to zero -> pay to exit
            port_ret[t + 1] -= np.abs(prev_w).sum() * COST_PER_SIDE / max(1, len(idx) if idx.size else 1)
            prev_w = np.zeros(S)
            continue
        for s in idx:
            base = close[s, t]
            past = close[s, t - L]
            v = vol[s, t]
            if not (np.isfinite(base) and np.isfinite(past) and past > 0 and np.isfinite(v) and v > 0):
                continue
            sig = np.sign(base / past - 1.0)
            scale = min(LEV_CAP, VOL_TARGET / v)
            w[s] = sig * scale
        # equal risk budget: average across eligible book
        n = len(idx)
        w = w / n
        # gross pnl next day
        rn = ret[:, t + 1]
        pnl = np.nansum(w * np.where(np.isfinite(rn), rn, 0.0))
        # costs on turnover
        turn = np.abs(w - prev_w).sum()
        pnl -= turn * COST_PER_SIDE
        port_ret[t + 1] = pnl
        prev_w = w

    is_ret = port_ret[1:split_idx]
    oos_ret = port_ret[split_idx:]
    return port_ret, is_ret, oos_ret


# ----------------------------------------------------------------- ENGINE B: discrete Donchian+ATR
def run_discrete(syms, days, close, high, low, eligible_mask, entryN=55, exitN=20, atrN=20, atr_k=2.0):
    """Turtle-style: enter on N-day breakout, trail-exit on opposite exitN extreme,
    hard stop at atr_k*ATR. Returns per-trade R list (with dates/sym) split by exit date."""
    S, D = close.shape
    trades = []
    for s in range(S):
        c = close[s]; h = high[s]; lo = low[s]
        # ATR (using 5m-derived daily high/low; true range)
        tr = np.full(D, np.nan)
        for t in range(1, D):
            if np.isfinite(h[t]) and np.isfinite(lo[t]) and np.isfinite(c[t - 1]):
                tr[t] = max(h[t] - lo[t], abs(h[t] - c[t - 1]), abs(lo[t] - c[t - 1]))
        atr = np.full(D, np.nan)
        for t in range(atrN, D):
            w = tr[t - atrN + 1:t + 1]
            if np.isfinite(w).sum() >= atrN // 2:
                atr[t] = np.nanmean(w)
        in_pos = 0; entry_px = np.nan; entry_atr = np.nan; entry_t = -1; stop = np.nan; trail = np.nan
        for t in range(entryN + 1, D):
            if not eligible_mask[s, t]:
                if in_pos != 0:  # forced flat when it leaves the universe
                    exitpx = c[t]
                    _close_trade(trades, syms[s], entry_t, t, days, in_pos, entry_px, exitpx, entry_atr, atr_k)
                    in_pos = 0
                continue
            up = np.nanmax(h[t - entryN:t])   # prior N-day high (excl today)
            dn = np.nanmin(lo[t - entryN:t])
            px = c[t]; a = atr[t]
            if not (np.isfinite(px) and np.isfinite(a) and a > 0):
                continue
            if in_pos == 0:
                if np.isfinite(up) and px > up:
                    in_pos = 1; entry_px = px; entry_atr = a; entry_t = t; trail = np.nanmin(lo[t - exitN:t])
                elif np.isfinite(dn) and px < dn:
                    in_pos = -1; entry_px = px; entry_atr = a; entry_t = t; trail = np.nanmax(h[t - exitN:t])
            elif in_pos == 1:
                hardstop = entry_px - atr_k * entry_atr
                trail = max(trail, np.nanmin(lo[t - exitN:t])) if np.isfinite(np.nanmin(lo[t - exitN:t])) else trail
                exitlvl = max(hardstop, trail)
                if px <= exitlvl or (np.isfinite(dn) and px < dn):
                    _close_trade(trades, syms[s], entry_t, t, days, 1, entry_px, px, entry_atr, atr_k)
                    in_pos = 0
            elif in_pos == -1:
                hardstop = entry_px + atr_k * entry_atr
                trail = min(trail, np.nanmax(h[t - exitN:t])) if np.isfinite(np.nanmax(h[t - exitN:t])) else trail
                exitlvl = min(hardstop, trail)
                if px >= exitlvl or (np.isfinite(up) and px > up):
                    _close_trade(trades, syms[s], entry_t, t, days, -1, entry_px, px, entry_atr, atr_k)
                    in_pos = 0
    return trades


def _close_trade(trades, sym, et, xt, days, dir_, epx, xpx, eatr, atr_k):
    risk = atr_k * eatr
    if risk <= 0 or not np.isfinite(risk):
        return
    gross = (xpx - epx) * dir_
    cost = (epx + xpx) * COST_PER_SIDE     # round-trip cost in price units
    net = gross - cost
    R = net / risk
    trades.append({"sym": sym, "entry_day": int(days[et]), "exit_day": int(days[xt]),
                   "dir": int(dir_), "R": float(R), "bars": int(xt - et)})


# ----------------------------------------------------------------- null: random timing
def random_null_continuous(port_builder, n=200):
    sr = []
    for _ in range(n):
        sr.append(port_builder())
    return sr


def main():
    print("building daily bars from cached 5m panel ...", flush=True)
    syms, days, close, high, low, qv = build_daily()
    S, D = close.shape
    dates = [day_to_date(d) for d in days]
    split_idx = next(i for i, d in enumerate(dates) if d >= IS_OOS_SPLIT)
    print(f"  {S} symbols, {D} daily bars {dates[0]}..{dates[-1]}; IS/OOS split idx {split_idx} ({dates[split_idx]})")

    # ---- eligibility: >=MIN_HIST listed days AND top-N trailing-30d ADV, causal
    listed = np.isfinite(close)
    hist = np.cumsum(listed, axis=1)  # days seen so far
    adv = np.full((S, D), np.nan)
    for s in range(S):
        for t in range(D):
            lo = max(0, t - 30)
            w = qv[s, lo:t]
            adv[s, t] = np.nanmean(w) if w.size else np.nan
    eligible = np.zeros((S, D), bool)
    for t in range(D):
        ok = (hist[:, t] >= MIN_HIST) & np.isfinite(adv[:, t]) & (adv[:, t] > 0) & np.isfinite(close[:, t])
        idx = np.where(ok)[0]
        if len(idx) > TOPN:
            top = idx[np.argsort(-adv[idx, t])[:TOPN]]
            m = np.zeros(S, bool); m[top] = True
            eligible[:, t] = m
        else:
            eligible[:, t] = ok
    print(f"  median eligible book size: {int(np.median(eligible.sum(axis=0)))}")

    # ============ ENGINE A: pick L in-sample, freeze, report held-out ============
    Ls = [30, 60, 90, 120, 180, 250]
    is_perf = {}
    port_by_L = {}
    for L in Ls:
        port_ret, is_ret, oos_ret = run_continuous(syms, days, close, qv, L, split_idx, eligible)
        port_by_L[L] = (port_ret, is_ret, oos_ret)
        is_perf[L] = sharpe(is_ret)
        print(f"  [A] L={L:3d}  IS net Sharpe={is_perf[L]:.3f}")
    L_star = max(is_perf, key=is_perf.get)
    port_ret, is_ret, oos_ret = port_by_L[L_star]
    print(f"  [A] PICKED L*={L_star} (best IS). Now the only number that matters: HELD-OUT.")

    # per-instrument net Sharpe at L* (continuous, single-instrument vol-scaled)
    per_inst = {}
    ret = np.full((S, D), np.nan); ret[:, 1:] = close[:, 1:] / close[:, :-1] - 1.0
    for s in range(S):
        v = ewma_vol(ret[s], VOL_SPAN)
        pr = np.full(D, np.nan); pw = 0.0
        for t in range(L_star + 1, D - 1):
            if not eligible[s, t]:
                pr[t + 1] = 0.0; pw = 0.0; continue
            base, past, vv = close[s, t], close[s, t - L_star], v[t]
            if not (np.isfinite(base) and np.isfinite(past) and past > 0 and np.isfinite(vv) and vv > 0):
                pr[t + 1] = 0.0; continue
            w = np.sign(base / past - 1) * min(LEV_CAP, VOL_TARGET / vv)
            rn = ret[s, t + 1]
            pnl = w * (rn if np.isfinite(rn) else 0.0) - abs(w - pw) * COST_PER_SIDE
            pr[t + 1] = pnl; pw = w
        if eligible[s].any():
            per_inst[syms[s]] = {"is_sharpe": round(sharpe(pr[1:split_idx]), 3),
                                 "oos_sharpe": round(sharpe(pr[split_idx:]), 3)}

    # BTC buy-and-hold benchmark (vol-scaled to same target for fair Sharpe/return comparison)
    bi = syms.index("BTCUSDT")
    btc_ret = ret[bi].copy()
    btc_daily = np.where(np.isfinite(btc_ret), btc_ret, 0.0)
    btc_is = btc_daily[1:split_idx]; btc_oos = btc_daily[split_idx:]

    # random-timing null for engine A: same vol-scaling & book, but momentum sign randomized daily
    def build_random_port():
        pr = np.full(D, np.nan); pw = np.zeros(S)
        vol = np.vstack([ewma_vol(ret[s], VOL_SPAN) for s in range(S)])
        for t in range(L_star + 1, D - 1):
            elig = eligible[:, t]; idx = np.where(elig)[0]
            if not len(idx):
                pr[t + 1] = 0.0; pw = np.zeros(S); continue
            w = np.zeros(S)
            for s in idx:
                vv = vol[s, t]
                if np.isfinite(vv) and vv > 0 and np.isfinite(close[s, t]):
                    w[s] = rng.choice([-1, 1]) * min(LEV_CAP, VOL_TARGET / vv)
            w /= len(idx)
            rn = ret[:, t + 1]
            pr[t + 1] = np.nansum(w * np.where(np.isfinite(rn), rn, 0.0)) - np.abs(w - pw).sum() * COST_PER_SIDE
            pw = w
        return pr
    print("  [A] running 200-draw random-timing null (held-out) ...", flush=True)
    null_oos_sr = [sharpe(build_random_port()[split_idx:]) for _ in range(200)]
    null_mean, null_p95 = float(np.mean(null_oos_sr)), float(np.percentile(null_oos_sr, 95))

    # ============ ENGINE B: discrete convexity R-distribution ============
    print("  [B] running discrete Donchian(55)/ATR(2x) convexity trade log ...", flush=True)
    trades = run_discrete(syms, days, close, high, low, eligible)
    def rdist(tr):
        R = np.array([x["R"] for x in tr])
        if len(R) == 0:
            return {}
        wins = R[R > 0]; losses = R[R <= 0]
        gross_win = wins.sum(); gross_loss = -losses.sum()
        return {"n": len(R), "win_rate": round((R > 0).mean(), 3),
                "mean_R": round(float(R.mean()), 3), "median_R": round(float(np.median(R)), 3),
                "best_R": round(float(R.max()), 2), "worst_R": round(float(R.min()), 2),
                "profit_factor": round(float(gross_win / gross_loss), 3) if gross_loss > 0 else None,
                "pct_winners_of_total_profit": round(float(gross_win / (gross_win + 1e-9)), 3),
                "expectancy_R": round(float(R.mean()), 3),
                "top5_share_of_gross_win": round(float(np.sort(wins)[-5:].sum() / gross_win), 3) if len(wins) >= 5 else None}
    is_tr = [t for t in trades if day_to_date(t["exit_day"]) < IS_OOS_SPLIT]
    oos_tr = [t for t in trades if day_to_date(t["exit_day"]) >= IS_OOS_SPLIT]
    dist_all, dist_is, dist_oos = rdist(trades), rdist(is_tr), rdist(oos_tr)

    # discrete equity curve (net R summed, equal risk fraction per trade) -> Sharpe on trade sequence
    def trade_sharpe(tr):
        R = np.array([x["R"] for x in sorted(tr, key=lambda z: z["exit_day"])])
        if len(R) < 5 or R.std() == 0:
            return 0.0
        # per-trade Sharpe annualized by trades/year
        yrs = (max(t["exit_day"] for t in tr) - min(t["entry_day"] for t in tr)) / 365.0
        tpy = len(R) / yrs if yrs > 0 else len(R)
        return float(R.mean() / R.std() * np.sqrt(tpy))
    # random null for B: shuffle exit signs (destroys let-winners-run asymmetry)
    allR = np.array([t["R"] for t in oos_tr])
    null_expect = []
    if len(allR):
        base_abs = np.abs(allR)
        for _ in range(200):
            signs = rng.choice([-1, 1], size=len(allR))
            null_expect.append((base_abs * signs).mean())
    b_null_mean = float(np.mean(null_expect)) if null_expect else 0.0

    # one worked example: the single best held-out trade
    worked = max(oos_tr, key=lambda t: t["R"]) if oos_tr else (max(trades, key=lambda t: t["R"]) if trades else None)
    if worked:
        worked = {**worked, "entry_date": str(day_to_date(worked["entry_day"])),
                  "exit_date": str(day_to_date(worked["exit_day"]))}

    # ---- portfolio summary table
    def summ(r):
        return {"net_sharpe": round(sharpe(r), 3), "ann_return_volunits": round(ann_return(r), 3),
                "max_dd_volunits": round(max_drawdown(r), 3), "n_days": int(np.isfinite(r).sum())}

    results = {
        "meta": {"panel": str(PANEL), "symbols": S, "daily_bars": D,
                 "window": f"{dates[0]}..{dates[-1]}", "is_oos_split": str(IS_OOS_SPLIT),
                 "cost_per_side_bp": COST_PER_SIDE * 1e4, "roundtrip_bp": RTRIP * 1e4,
                 "book_topN": TOPN, "vol_target": VOL_TARGET, "note": "vol-unit returns; Sharpe/DD scale-free"},
        "engineA_continuous_tsmom": {
            "lookback_IS_sharpe": {str(k): round(v, 3) for k, v in is_perf.items()},
            "L_star_picked_in_sample": L_star,
            "in_sample": summ(is_ret), "held_out": summ(oos_ret),
            "btc_hold_in_sample": summ(btc_is), "btc_hold_held_out": summ(btc_oos),
            "random_null_heldout_sharpe_mean": round(null_mean, 3),
            "random_null_heldout_sharpe_p95": round(null_p95, 3),
            "held_out_beats_null_p95": bool(sharpe(oos_ret) > null_p95),
        },
        "engineB_discrete_convexity": {
            "spec": "Donchian entry N=55, trail exit N=20, hard stop 2x ATR(20); R = net/(2*ATR_entry)",
            "R_dist_all": dist_all, "R_dist_in_sample": dist_is, "R_dist_held_out": dist_oos,
            "trade_sharpe_all": round(trade_sharpe(trades), 3) if trades else 0.0,
            "trade_sharpe_held_out": round(trade_sharpe(oos_tr), 3) if oos_tr else 0.0,
            "heldout_mean_R": dist_oos.get("mean_R"),
            "random_signflip_null_mean_R": round(b_null_mean, 4),
            "worked_example_best_heldout_trade": worked,
        },
        "per_instrument_continuous_Lstar": per_inst,
    }
    (OUTDIR / "T34_CRYPTO_TSMOM.json").write_text(json.dumps(results, indent=2, default=str))
    print("\nwrote", OUTDIR / "T34_CRYPTO_TSMOM.json")

    # ---- printed table
    A = results["engineA_continuous_tsmom"]; B = results["engineB_discrete_convexity"]
    print("\n" + "=" * 78)
    print("ENGINE A — continuous risk-parity TSMOM portfolio (net of 7bp round-trip)")
    print("=" * 78)
    print(f"  IS lookback sweep (net Sharpe): " + "  ".join(f"L{k}={v:.2f}" for k, v in is_perf.items()))
    print(f"  L* picked in-sample = {L_star}")
    print(f"  {'':14s}{'IS Sharpe':>11s}{'OOS Sharpe':>12s}{'OOS annRet':>12s}{'OOS maxDD':>11s}")
    print(f"  {'TSMOM':14s}{A['in_sample']['net_sharpe']:>11.2f}{A['held_out']['net_sharpe']:>12.2f}"
          f"{A['held_out']['ann_return_volunits']:>12.2f}{A['held_out']['max_dd_volunits']:>11.2f}")
    print(f"  {'BTC hold':14s}{A['btc_hold_in_sample']['net_sharpe']:>11.2f}{A['btc_hold_held_out']['net_sharpe']:>12.2f}"
          f"{A['btc_hold_held_out']['ann_return_volunits']:>12.2f}{A['btc_hold_held_out']['max_dd_volunits']:>11.2f}")
    print(f"  random-timing null (OOS Sharpe): mean={A['random_null_heldout_sharpe_mean']:.2f} "
          f"p95={A['random_null_heldout_sharpe_p95']:.2f}  -> TSMOM beats p95: {A['held_out_beats_null_p95']}")
    print("\n" + "=" * 78)
    print("ENGINE B — discrete Donchian/ATR convexity (R-distribution)")
    print("=" * 78)
    for lbl, d in [("ALL", dist_all), ("IN-SAMPLE", dist_is), ("HELD-OUT", dist_oos)]:
        if d:
            print(f"  {lbl:10s} n={d['n']:4d} win%={d['win_rate']:.2f} meanR={d['mean_R']:+.3f} "
                  f"medR={d['median_R']:+.3f} PF={d['profit_factor']} bestR={d['best_R']:+.1f} "
                  f"worstR={d['worst_R']:+.1f} top5%ofwins={d.get('top5_share_of_gross_win')}")
    print(f"  held-out trade Sharpe={B['trade_sharpe_held_out']}  vs sign-flip null meanR={B['random_signflip_null_mean_R']:+.4f}")
    if worked:
        print(f"  worked example (best held-out trade): {worked['sym']} {['?','LONG','','SHORT'][worked['dir']+1] if worked['dir']==1 else 'SHORT'} "
              f"{worked['entry_date']}->{worked['exit_date']} ({worked['bars']}d) R={worked['R']:+.2f}")
    print("=" * 78)


if __name__ == "__main__":
    main()
