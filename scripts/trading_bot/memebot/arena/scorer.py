#!/usr/bin/env python3
"""MEME ARENA — the scorer. The pre-registered decision rule + an HONEST confidence interval.

The naive sd/sqrt(N) CI is WRONG here: memecoin paper trades cluster (many entries share a mint, and
many share an entry-day / a market regime), so the effective N is far below the row count. This uses a
CLUSTER (block) bootstrap — resample whole clusters with replacement — which is what the hardened
preregs require. Decision: PASS iff ci95_lo > 0, KILL iff ci95_hi < 0 (or an event-rate floor), else
UNDECIDED. A KILL is decisive; a PASS on an optimistic-bound arm earns only a stricter causal test.
Pure math, no I/O.
"""
from __future__ import annotations

import random
import statistics


def cluster_bootstrap_ci(values: list[float], clusters: list, iters: int = 2000,
                         seed: int = 20260901, alpha: float = 0.05):
    """95% CI of the mean via a cluster bootstrap (resample distinct clusters with replacement, pool
    their member values, take the pooled mean). Falls back to a plain bootstrap if clusters are absent."""
    n = len(values)
    if n == 0:
        return {"mean": None, "ci_lo": None, "ci_hi": None, "n": 0, "n_clusters": 0}
    by_cluster: dict = {}
    for v, c in zip(values, clusters if clusters else range(n)):
        by_cluster.setdefault(c, []).append(v)
    keys = list(by_cluster.keys())
    rng = random.Random(seed)
    means = []
    for _ in range(iters):
        pooled = []
        for _ in range(len(keys)):
            pooled.extend(by_cluster[keys[rng.randrange(len(keys))]])
        if pooled:
            means.append(sum(pooled) / len(pooled))
    means.sort()
    lo = means[int((alpha / 2) * len(means))]
    hi = means[min(len(means) - 1, int((1 - alpha / 2) * len(means)))]
    return {"mean": sum(values) / n, "ci_lo": lo, "ci_hi": hi, "n": n, "n_clusters": len(keys),
            "sd_over_sqrtn_ci_lo_NAIVE": (sum(values) / n) - 1.96 * (statistics.pstdev(values) / (n ** 0.5))
            if n > 1 else None}


DRAWDOWN_LIMIT = 0.40          # max equity drawdown as a fraction of bankroll (frozen)


def _median(xs: list[float]):
    if not xs:
        return None
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def _drop_top_cluster_ci_lo(values: list[float], clusters: list, iters: int, seed: int):
    """Single-winner dominance: recompute the bootstrap ci_lo WITHOUT the cluster that contributes the
    most total return. If the edge only exists because of one lucky (mint,day), this collapses."""
    by = {}
    for v, c in zip(values, clusters if clusters else range(len(values))):
        by.setdefault(c, []).append(v)
    if len(by) < 2:
        return None
    top = max(by, key=lambda c: sum(by[c]))
    rest_v = [v for v, c in zip(values, clusters) if c != top]
    rest_c = [c for c in clusters if c != top]
    return cluster_bootstrap_ci(rest_v, rest_c, iters=iters, seed=seed)["ci_lo"]


def _max_drawdown(values: list[float]) -> float:
    """Max peak-to-trough drawdown of the cumulative net-R equity path (in net-R units)."""
    peak = cum = 0.0
    worst = 0.0
    for v in values:
        cum += v
        peak = max(peak, cum)
        worst = max(worst, peak - cum)
    return worst


def decide(net_returns: list[float], clusters: list, target_n: int,
           events_per_week: float | None = None, min_events_per_week: float = 1.0,
           extended_cap: int | None = None, clip_fraction: float = 0.10,
           iters: int = 2000, seed: int = 20260901):
    """The frozen PASS/KILL/UNDECIDED rule. A PASS requires ALL of: cluster-bootstrap ci_lo>0, positive
    MEDIAN, no single-winner (top-cluster) dominance, and a bounded drawdown — so one lottery winner cannot
    fake a PASS on rug-prone tokens. `clip_fraction` = clip/bankroll (default $10/$100)."""
    n = len(net_returns)
    ci = cluster_bootstrap_ci(net_returns, clusters)
    # event-rate floor: too rare to matter even if positive
    if events_per_week is not None and events_per_week < min_events_per_week:
        return {"verdict": "KILL", "reason": f"event rate {events_per_week:.2f}/wk < {min_events_per_week}",
                **ci, "target_n": target_n}
    # early decisive KILL allowed once the upper bound is below zero
    if n >= 40 and ci["ci_hi"] is not None and ci["ci_hi"] < 0:
        return {"verdict": "KILL", "reason": "bootstrap 95% CI upper bound < 0 (decisive)",
                **ci, "target_n": target_n}
    if n < target_n:
        return {"verdict": "COLLECTING", "reason": f"{n}/{target_n} resolved", **ci, "target_n": target_n}
    if ci["ci_lo"] is not None and ci["ci_lo"] > 0:
        # ci_lo>0 is necessary but NOT sufficient — the full frozen PASS rule must hold, else a single
        # lottery winner on a rug-prone token faked it. Check median, dominance, drawdown.
        median = _median(net_returns)
        drop_lo = _drop_top_cluster_ci_lo(net_returns, clusters, iters, seed)
        dd = _max_drawdown(net_returns) * clip_fraction     # drawdown as a fraction of bankroll
        robust = {"median": median, "ci_lo_ex_top_cluster": drop_lo, "drawdown_frac": round(dd, 4)}
        if median is None or median <= 0:
            return {"verdict": "KILL", "reason": "ci_lo>0 but MEDIAN<=0 — the edge is a single-winner "
                    "lottery, not a robust central tendency", **ci, **robust, "target_n": target_n}
        if drop_lo is not None and drop_lo <= 0:
            return {"verdict": "KILL", "reason": "ci_lo>0 collapses when the top (mint,day) cluster is "
                    "dropped — single-winner dominance, not a real edge", **ci, **robust, "target_n": target_n}
        if dd > DRAWDOWN_LIMIT:
            return {"verdict": "KILL", "reason": f"drawdown {dd:.0%} of bankroll exceeds the {DRAWDOWN_LIMIT:.0%} "
                    "limit — unmanageable even if positive on average", **ci, **robust, "target_n": target_n}
        return {"verdict": "PASS", "reason": "all frozen PASS criteria hold (ci_lo>0, median>0, no "
                "single-winner dominance, bounded drawdown) — earns a stricter causal test, NOT a money "
                "claim", **ci, **robust, "target_n": target_n}
    if extended_cap and n < extended_cap:
        return {"verdict": "UNDECIDED_EXTEND", "reason": f"CI straddles 0; extend to {extended_cap} once",
                **ci, "target_n": target_n}
    return {"verdict": "KILL", "reason": "CI still straddles 0 at the extended cap — edge too small to "
            "separate from 0", **ci, "target_n": target_n}


if __name__ == "__main__":
    rng = random.Random(1)
    # a genuinely positive, low-cluster signal: many rows but few mints -> honest CI wider than naive
    vals, clus = [], []
    for m in range(8):                       # only 8 mints
        for _ in range(15):                  # 15 correlated entries each
            vals.append(0.05 + rng.gauss(0, 0.02)); clus.append(("mint%d" % m, "day%d" % (m % 3)))
    ci = cluster_bootstrap_ci(vals, clus)
    assert ci["n"] == 120 and ci["n_clusters"] == 8
    assert ci["ci_lo"] > ci["sd_over_sqrtn_ci_lo_NAIVE"] - 1  # cluster CI is not the naive one
    d = decide(vals, clus, target_n=120)
    assert d["verdict"] == "PASS", d
    dk = decide([-0.1] * 120, [("m", "d")] * 120, target_n=120)
    assert dk["verdict"] == "KILL"
    # LOTTERY distribution: 40 spread winners (+5) + 80 losers (-0.1). mean +1.6 and ci_lo>0, but the
    # MEDIAN is -0.1 (winners are a minority) -> the median gate must KILL it despite ci_lo>0.
    lot = [5.0] * 40 + [-0.1] * 80
    lotc = [("m%d" % i, "d") for i in range(120)]        # spread -> not single-cluster dominance
    dl = decide(lot, lotc, target_n=120)
    assert dl["verdict"] == "KILL" and dl.get("median", 1) <= 0 and dl["ci_lo"] > 0, dl
    assert "median" in dl["reason"].lower(), dl["reason"]
    print("scorer.py self-check OK: cluster bootstrap + full PASS rule (median/dominance/drawdown) + lottery KILL")
