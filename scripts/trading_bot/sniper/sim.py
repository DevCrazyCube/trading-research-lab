#!/usr/bin/env python3
"""Paper backtest/replay harness for the sniper stack. Wires DataProvider -> SurgeDetector ->
ConvexityStrategy -> DryRunExecutor over a replay of 1s bars, then reports the HONEST scorecard:
bankroll curve, per-trade R distribution (is it convex?), win rate, net after realistic cost, and a
random-entry null for comparison. PAPER ONLY — nothing signs/sends/holds a wallet.

Run as a module (types.py shadows stdlib `types` on a bare path):
    python3 -m scripts.trading_bot.sniper.sim [--mints N] [--preset convex_core] [--seed 0]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import statistics as st

from .types import Bar, EntrySignal, OrderIntent
from .signals import SurgeDetector, SurgeConfig, PARAM_GRID
from .strategy import ConvexityStrategy, PRESETS
from .execution import DryRunExecutor

CACHE = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                     "research", "data", "memebot_cache", "bitquery_candles")


# ---------- stopgap replay from the on-disk cache (swap for data/ReplayProvider once it lands) ----------
def replay_bars(cache_dir: str = CACHE, limit_mints: int | None = None):
    """Yield (mint, Bar) across ALL cached mints in GLOBAL time order (so concurrent coins interleave
    exactly as they happened). Per-mint order is preserved, which is what the detector/strategy need."""
    files = sorted(glob.glob(os.path.join(cache_dir, "*.jsonl")))
    if limit_mints:
        files = files[:limit_mints]
    rows: list[tuple[int, str, Bar]] = []
    for f in files:
        mint = os.path.basename(f)[:-6]
        try:
            for line in open(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if "t" not in d or "c" not in d:
                    continue
                o = float(d.get("o", d["c"])); h = float(d.get("h", d["c"]))
                lo = float(d.get("l", d["c"])); c = float(d["c"])
                # Drop DEGENERATE / glitch bars: the free 1s bonding-curve tape carries occasional
                # wrong-side USD ticks that fabricate fake 1000x candles (they produced a +9291R
                # phantom winner). Require positive OHLC and a sane intrabar range (<=10x high/low).
                if min(o, h, lo, c) <= 0:
                    continue
                if h / lo > 10.0:
                    continue
                bar = Bar(t=int(d["t"]), o=o, h=h, l=lo, c=c, v=float(d.get("v", 0.0)),
                          buys=int(d.get("buys", 0)), sells=int(d.get("sells", 0)),
                          buy_vol=float(d.get("buy_vol", 0.0)), sell_vol=float(d.get("sell_vol", 0.0)),
                          dex=d.get("dex"))
                rows.append((bar.t, mint, bar))
        except OSError:
            continue
    rows.sort(key=lambda r: r[0])
    for _, mint, bar in rows:
        yield mint, bar


def _venue_liq(sig: EntrySignal | None, bar: Bar) -> float:
    if sig is not None:
        return sig.liq_usd_per_s
    return max(1.0, bar.v)  # coarse liquidity hint from this bar's volume


def run_sim(preset: str = "convex_core", surge_cfg: SurgeConfig | None = None,
            limit_mints: int | None = None, random_null: bool = True, seed: int = 0) -> dict:
    det = SurgeDetector(config=surge_cfg)
    strat = ConvexityStrategy(config=PRESETS.get(preset))
    ex = DryRunExecutor()
    # wire the open-position debounce so the detector won't re-fire on a mint we already hold
    open_mints: set[str] = set()
    det.position_open = lambda m: m in open_mints

    last_bar: dict[str, Bar] = {}
    for mint, bar in replay_bars(limit_mints=limit_mints):
        last_bar[mint] = bar
        # 1) exits first, on the open book for this mint
        for intent in strat.on_bar(mint, bar):
            fill = ex.execute(intent, liq_usd_per_s=_venue_liq(None, bar))
            strat.apply_fill(fill)
            open_mints.discard(mint)
        # 2) entry signal
        sig = det.update(bar, mint=mint)
        if sig is not None and mint not in open_mints:
            intent = strat.on_signal(sig)
            if intent is not None:
                fill = ex.execute(intent, liq_usd_per_s=_venue_liq(sig, bar))
                pos = strat.apply_fill(fill)
                if pos is not None:
                    open_mints.add(mint)

    # force-close any positions still open at replay end, at their last seen bar close
    for pos in list(strat.open_positions()):
        bar = last_bar.get(pos.mint)
        if bar is None:
            continue
        intent = OrderIntent(mint=pos.mint, side="sell", ts=float(bar.t), ref_price_usd=bar.c,
                             usd_size=pos.entry.usd_size, venue=pos.venue, tag="exit:replay_end")
        fill = ex.execute(intent, liq_usd_per_s=max(1.0, bar.v))
        strat.apply_fill(fill)

    closed = strat.closed_positions()
    rs = [p.realized_r for p in closed if p.realized_r is not None]
    scorecard = _scorecard(rs, strat.book_summary())

    if random_null and rs:
        scorecard["random_null"] = _random_null(limit_mints, len(rs), preset, seed)
    return scorecard


def _scorecard(rs: list[float], book: dict) -> dict:
    if not rs:
        return {"n_trades": 0, "note": "no resolved trades in replay window", "book": book}
    rs_sorted = sorted(rs)
    wins = [r for r in rs if r > 0]
    top5_share = (sum(sorted(wins, reverse=True)[:5]) / sum(r for r in rs if r > 0)) if wins else 0.0
    return {
        "n_trades": len(rs),
        "win_rate": round(len(wins) / len(rs), 4),
        "mean_R": round(st.mean(rs), 4),
        "median_R": round(st.median(rs), 4),
        "sum_R": round(sum(rs), 3),
        "best_R": round(max(rs), 3),
        "worst_R": round(min(rs), 3),
        "p90_R": round(rs_sorted[int(0.90 * (len(rs) - 1))], 3),
        "p95_R": round(rs_sorted[int(0.95 * (len(rs) - 1))], 3),
        "convex_top5_win_share": round(top5_share, 3),
        "convex": top5_share >= 0.5 and st.median(rs) < st.mean(rs),
        "book": book,
        "framing": "PAPER replay, in-sample on cached bars. NOT a verdict — measures whether the "
                   "convexity structure nets positive on this data. Real orders/wallet stay owner-gated.",
    }


def _random_null(limit_mints, n_target, preset, seed) -> dict:
    """Random-entry null: enter random mints at random bars (same book/exec), same n scale."""
    import random
    rng = random.Random(seed)
    strat = ConvexityStrategy(config=PRESETS.get(preset))
    ex = DryRunExecutor()
    open_mints: set[str] = set()
    seen: set[str] = set()
    last_bar: dict[str, Bar] = {}
    bars = list(replay_bars(limit_mints=limit_mints))
    n_mints = len({m for m, _ in bars}) or 1
    p_enter = min(1.0, (n_target * 1.6) / n_mints)  # ~match the real-entry count, per new-mint
    for mint, bar in bars:
        last_bar[mint] = bar
        for intent in strat.on_bar(mint, bar):
            fill = ex.execute(intent, liq_usd_per_s=max(1.0, bar.v)); strat.apply_fill(fill); open_mints.discard(mint)
        first_sight = mint not in seen
        seen.add(mint)
        if first_sight and mint not in open_mints and rng.random() < p_enter:
            # random ENTRY timing, but through the SAME sizing/registration/exit machinery via a
            # synthetic signal (so it opens correctly and uses identical exits — only entry is random).
            sig = EntrySignal(mint=mint, ts=float(bar.t), ref_price_usd=bar.c, surge_bps=0.0,
                              buy_frac=0.5, liq_usd_per_s=max(1.0, bar.v), venue=bar.dex, reason="null")
            intent = strat.on_signal(sig)
            if intent is not None:
                fill = ex.execute(intent, liq_usd_per_s=max(1.0, bar.v))
                if strat.apply_fill(fill) is not None:
                    open_mints.add(mint)
    for pos in list(strat.open_positions()):
        bar = last_bar.get(pos.mint)
        if bar:
            fill = ex.execute(OrderIntent(mint=pos.mint, side="sell", ts=float(bar.t), ref_price_usd=bar.c,
                              usd_size=pos.entry.usd_size, venue=pos.venue, tag="exit:replay_end"),
                              liq_usd_per_s=max(1.0, bar.v)); strat.apply_fill(fill)
    rs = [p.realized_r for p in strat.closed_positions() if p.realized_r is not None]
    if not rs:
        return {"n_trades": 0}
    return {"n_trades": len(rs), "mean_R": round(st.mean(rs), 4), "median_R": round(st.median(rs), 4),
            "win_rate": round(len([r for r in rs if r > 0]) / len(rs), 4)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mints", type=int, default=None)
    ap.add_argument("--preset", default="convex_core")
    ap.add_argument("--surge", default=None, help="a PARAM_GRID name (BALANCED/TIGHT/WIDE/FAST/SLOW)")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    scfg = PARAM_GRID.get(a.surge) if a.surge else None
    out = run_sim(preset=a.preset, surge_cfg=scfg, limit_mints=a.mints, seed=a.seed)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
