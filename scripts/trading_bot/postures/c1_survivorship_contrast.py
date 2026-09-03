#!/usr/bin/env python3
"""POSTURE C1 side-check -- how much does survivorship bias alone move the
median-vs-mean gap? Runs the identical statistic on the repo's EXISTING Stooq
snapshot panel, which contains only tickers still listed in Aug 2026 (verified:
TWTR, SIVB, FRC, BBBY, ATVI, VMW all absent). Read-only."""
import numpy as np, json

z = np.load("/home/anont/meme/research/data/xll_cache/eq_daily_panel.npz", allow_pickle=True)
syms, dates, close, vol = z["symbols"], z["dates"], z["close"].astype(np.float64), z["vol"].astype(np.float64)
S, D = close.shape
ret = np.full((S, D), np.nan)
ret[:, 1:] = close[:, 1:] / close[:, :-1] - 1.0
ret[~np.isfinite(ret)] = np.nan
ret[np.abs(ret) > 5.0] = np.nan
dv = close * vol
dvf = np.where(np.isfinite(dv), dv, 0.0)
cs = np.cumsum(dvf, axis=1)
adv = np.full((S, D), np.nan)
adv[:, 22:] = (cs[:, 21:-1] - cs[:, :-22]) / 21.0
live = np.isfinite(ret)
out = {"panel": "research/data/xll_cache/eq_daily_panel.npz (SURVIVORSHIP-BIASED: "
                "Stooq snapshot of tickers still listed Aug-2026)",
       "symbols": int(S), "dates": [str(dates[0]), str(dates[-1])], "sessions": int(D)}
rank = np.where(np.isfinite(adv) & live, adv, -1.0)
order = np.argsort(-rank, axis=0)
for tag, k in (("top500", 500), ("top1000", 1000)):
    m = np.zeros((S, D), bool)
    sel = order[:k, :]
    for j in range(D):
        c = sel[:, j]; c = c[rank[c, j] > 0]; m[c, j] = True
    m &= live
    x = np.where(m, ret, np.nan)
    lg = np.log1p(x)
    with np.errstate(invalid="ignore"):
        ew = np.nanmean(x, axis=0); md = np.nanmedian(x, axis=0)
        sig = np.nanstd(lg, axis=0)
    bad = m.sum(axis=0) < 30
    ew[bad] = np.nan; md[bad] = np.nan
    v = np.isfinite(ew) & np.isfinite(md)
    g = (ew[v] - md[v])
    rng = np.random.default_rng(20260903)
    idx = rng.integers(0, g.size, size=(5000, g.size))
    ci = np.percentile(g[idx].mean(axis=1), [2.5, 97.5])
    out[tag] = {
        "days": int(v.sum()), "avg_names": round(float(m.sum(axis=0)[v].mean()), 1),
        "EW_mean_pp_per_day": round(float(ew[v].mean()) * 100, 4),
        "MEDIAN_pp_per_day": round(float(md[v].mean()) * 100, 4),
        "GAP_pp_per_day": round(float(g.mean()) * 100, 4),
        "GAP_ci95_pp": [round(ci[0] * 100, 4), round(ci[1] * 100, 4)],
        "xsec_log_dispersion_pct_per_day": round(float(sig[v].mean()) * 100, 3),
        "MECHANICAL_gap_if_lognormal_pp_per_day":
            round(float(np.expm1(sig[v] ** 2 / 2).mean()) * 100, 4),
        "EXCESS_SKEW_RATIO_gap_over_mechanical":
            round(float(g.mean() / np.expm1(sig[v] ** 2 / 2).mean()), 3),
        "compound_EW_pct": round((float(np.prod(1 + ew[v])) - 1) * 100, 1),
        "compound_daily_median_pct": round((float(np.prod(1 + md[v])) - 1) * 100, 1),
    }
print(json.dumps(out, indent=2))
json.dump(out, open("/home/anont/meme/research/postures/c1_equity_skew/survivorship_biased_contrast.json", "w"), indent=2)
