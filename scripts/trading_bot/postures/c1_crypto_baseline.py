#!/usr/bin/env python3
"""POSTURE C1 -- re-measure the CRYPTO baseline like-for-like.

The headline gap (0.5707 pp/day) was built from a MEDIAN of LOG returns against
a MEAN of SIMPLE returns. Those are two different transforms, so part of that gap
is Jensen, not skew. Recompute both sides in the same units so the equity
comparison is apples-to-apples. Read-only on the existing judge cache.
"""
import numpy as np, json, sys

Z = np.load("/home/anont/meme/scripts/trading_bot/eventstudy/judge/_cache.npz",
            allow_pickle=True)
syms, days, close, qv = list(Z["syms"]), Z["days"], Z["close"], Z["qv"]
S, D = close.shape

lr = np.full_like(close, np.nan)
lr[:, 1:] = np.log(close[:, 1:] / close[:, :-1])
simple = np.expm1(lr)
liq = (qv >= 1e6) & np.isfinite(lr)
MINN = 30

def series(mask, arr, fn):
    x = np.where(mask, arr, np.nan)
    with np.errstate(invalid="ignore"):
        out = fn(x, axis=0)
    out[mask.sum(axis=0) < MINN] = np.nan
    return out

ew_liq_s = series(liq, simple, np.nanmean)
md_liq_s = series(liq, simple, np.nanmedian)
md_liq_l = series(liq, lr, np.nanmedian)
ew_liq_l = series(liq, lr, np.nanmean)
v = np.isfinite(ew_liq_s) & np.isfinite(md_liq_s) & np.isfinite(md_liq_l)
T = int(v.sum())
nbar = float(liq.sum(axis=0)[v].mean())

def boot(g, n=5000, seed=20260903):
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(g), size=(n, len(g)))
    m = g[idx].mean(axis=1)
    return np.percentile(m, [2.5, 97.5])

gap_mixed = (ew_liq_s[v] - md_liq_l[v]) * 100.0     # as originally reported
gap_like  = (ew_liq_s[v] - md_liq_s[v]) * 100.0     # like-for-like, both simple
res = {
  "panel": {"symbols": S, "days_total": int(D), "days_used": T,
            "avg_liquid_names_per_day": round(nbar, 1)},
  "pp_per_day": {
    "EW_mean_simple_liquid":  round(float(np.nanmean(ew_liq_s[v])) * 100, 4),
    "MEDIAN_simple_liquid":   round(float(np.nanmean(md_liq_s[v])) * 100, 4),
    "MEDIAN_log_liquid":      round(float(np.nanmean(md_liq_l[v])) * 100, 4),
    "EW_mean_log_liquid":     round(float(np.nanmean(ew_liq_l[v])) * 100, 4),
  },
  "gap_pp_per_day": {
    "as_reported_mean_simple_minus_median_LOG": round(float(gap_mixed.mean()), 4),
    "like_for_like_both_SIMPLE":                round(float(gap_like.mean()), 4),
    "jensen_share_of_reported_gap": round(1 - float(gap_like.mean()) / float(gap_mixed.mean()), 4),
    "ci95_like_for_like": [round(x, 4) for x in boot(gap_like)],
  },
  "compounded_over_sample_pct": {
    "EW_liquid_basket": round((float(np.nanprod(1 + ew_liq_s[v])) - 1) * 100, 2),
    "daily_cross_sectional_MEDIAN_simple": round((float(np.nanprod(1 + md_liq_s[v])) - 1) * 100, 4),
    "daily_cross_sectional_MEDIAN_log": round((float(np.exp(np.nansum(md_liq_l[v]))) - 1) * 100, 4),
  },
}

# per-name buy-and-hold while liquid-eligible: the typical NAME's outcome
name_comp = []
for i in range(S):
    m = liq[i] & np.isfinite(simple[i])
    if m.sum() < 60:
        continue
    name_comp.append(float(np.prod(1 + simple[i][m])) - 1)
name_comp = np.array(name_comp)
res["per_name_buyhold_while_liquid"] = {
    "n_names": int(name_comp.size),
    "median_pct": round(float(np.median(name_comp)) * 100, 2),
    "mean_pct": round(float(name_comp.mean()) * 100, 2),
    "share_negative": round(float((name_comp < 0).mean()), 4),
}

# top-k share of the EW basket's total arithmetic return
w = np.where(liq, 1.0, 0.0)
n_t = w.sum(axis=0); n_t[n_t == 0] = np.nan
contrib = np.nansum(np.where(liq, simple, 0.0) / n_t, axis=1)
tot = contrib.sum()
order = np.sort(contrib)[::-1]
for pct in (0.01, 0.05):
    k = max(1, int(round(pct * S)))
    res.setdefault("top_share_of_total_EW_return", {})[f"top_{int(pct*100)}pct"] = {
        "k_names": k, "share": round(float(order[:k].sum() / tot), 4)}
res["top_share_of_total_EW_return"]["total_arith_sum"] = round(float(tot), 4)

print(json.dumps(res, indent=2))
json.dump(res, open("/home/anont/meme/research/postures/c1_equity_skew/crypto_baseline.json", "w"), indent=2)
