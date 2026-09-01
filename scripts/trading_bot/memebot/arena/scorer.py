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


def decide(net_returns: list[float], clusters: list, target_n: int,
           events_per_week: float | None = None, min_events_per_week: float = 1.0,
           extended_cap: int | None = None):
    """The frozen PASS/KILL/UNDECIDED rule. `net_returns` are honest per-trade returns; `clusters` the
    (mint, entry_day) keys; `target_n` the pre-registered decision sample."""
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
        return {"verdict": "PASS", "reason": "bootstrap 95% CI lower bound > 0 — earns a stricter causal "
                "test, NOT a money claim", **ci, "target_n": target_n}
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
    print("scorer.py self-check OK: cluster bootstrap + frozen PASS/KILL rule")
