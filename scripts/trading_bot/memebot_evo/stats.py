#!/usr/bin/env python3
"""The anti-overfitting arithmetic -- expectancy, the K-corrected noise bar, and the kill rule.

This is the honest core. A genetic search over K genomes is K silent hypothesis tests; the best of K
pure-noise strategies has an expected t-statistic of about sqrt(2 ln K) purely by luck. So a survivor
is only interesting if its forward t-stat CLEARS that bar -- and even then only "REAL" once it repeats
on a FRESH out-of-sample slice it was not selected on (adjudicated in engine.py).

Everything here is pure stdlib arithmetic over a realised-R stream. No model, no fit.
"""

from __future__ import annotations

import math
import statistics


def expectancy(rs: list) -> dict:
    """Win-rate / avg-win / avg-loss / EXPECTANCY over a realised-R stream (mirror of memebot.scoring)."""
    n = len(rs)
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    avg_win = statistics.fmean(wins) if wins else 0.0
    avg_loss = statistics.fmean([abs(r) for r in losses]) if losses else 0.0
    return {
        "n": n,
        "win_rate": len(wins) / n if n else 0.0,
        "avg_win_R": avg_win,
        "avg_loss_R": avg_loss,
        "expectancy_R": (len(wins) / n * avg_win - len(losses) / n * avg_loss) if n else 0.0,
        "mean_R": statistics.fmean(rs) if rs else None,
        "cum_R": sum(rs),
    }


def t_stat(rs: list) -> dict:
    """Per-trade mean R, its standard error, and t = mean/SE. Needs n>=2 for an SE."""
    n = len(rs)
    if n < 2:
        return {"n": n, "mean_R": (rs[0] if n == 1 else None), "se": None, "t": None}
    mean = statistics.fmean(rs)
    sd = statistics.stdev(rs)
    se = sd / math.sqrt(n)
    return {"n": n, "mean_R": mean, "se": se, "t": (mean / se) if se > 0 else None}


def noise_bar(k: int) -> float:
    """Expected-max-under-null in SE units for K independent trials: sqrt(2 ln K).

    This is the same analytic bar the equity programme uses (FORMULA_SWEEP_MASTER). A genome whose
    forward t-stat does not exceed this is indistinguishable from the luckiest of K noise strategies.
    """
    k = max(2, int(k))
    return math.sqrt(2.0 * math.log(k))


def clears_bar(rs: list, k: int) -> dict:
    """Does this genome's forward R stream beat the K-corrected noise bar (one-sided, positive edge)?"""
    ts = t_stat(rs)
    bar = noise_bar(k)
    t = ts["t"]
    beats = (t is not None) and (t > bar)
    return {**ts, "K": k, "noise_bar_SE": bar, "beats_noise_bar": bool(beats)}


def kill_bound(rs: list) -> dict:
    """One-sided upper 95% bound on mean R. If it is < 0 the forward expectancy is significantly
    negative (the memebot HALT rule)."""
    ts = t_stat(rs)
    if ts["se"] is None or ts["mean_R"] is None:
        return {**ts, "upper95": None, "significantly_negative": False}
    upper95 = ts["mean_R"] + 1.645 * ts["se"]
    return {**ts, "upper95": upper95, "significantly_negative": upper95 < 0}
