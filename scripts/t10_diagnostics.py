#!/usr/bin/env python3
"""T10 EXPLORATORY diagnostics. NOT pre-registered; no verdict follows from anything here.

The verdict is `T10_HELDOUT_RESULT.json` against `T10_PREREGISTRATION.md` section 8. This file
exists to answer one question the gates raised and could not settle: the cross-sectional label
permutation returns p = 0.0020 on a series whose own t-statistic is +0.47. One of those two
numbers is measuring something other than what it is being read as, and it is worth knowing
which.
"""
import json
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import t10_overnight_intraday as t10          # noqa: E402
from trading_bot import stats                 # noqa: E402

OUT = pathlib.Path(t10.OUT)


def main():
    frozen = json.loads(t10.FROZEN.read_text())
    cfg = frozen["chosen"]["cfg"]
    panel, spy, dropped, prev_session = t10.build_panel()
    r = t10.run_config(panel, spy, "B", cfg, half_spread_bp=0.0,
                       prev_session=prev_session, day_lo=t10.TEST_START)
    g = np.asarray(r["gross"])
    days = r["dates"]

    # 1. the permutation's null dispersion, per DAY, against the real book's per-day dispersion
    per_day_obs_sd = float(g.std(ddof=1))
    perm = json.loads((OUT / "T10_HELDOUT_RESULT.json").read_text())["permutation"]
    per_day_null_sd = perm["null_sd"] * math.sqrt(len(days))
    # 2. factor exposure of the long-short book to the market
    spyfull = np.asarray([(1 + spy[d]["on"]) * (1 + spy[d]["id"]) - 1 for d in days if d in spy])
    mask = np.asarray([d in spy for d in days])
    beta = float(np.polyfit(spyfull, g[mask], 1)[0])
    resid = g[mask] - beta * spyfull
    # 3. long block and short block separately
    longs, shorts = [], []
    for _day, dsorted, m in r["members"]:
        arr = np.asarray(dsorted)
        longs.append(float(arr[:m].mean()))
        shorts.append(float(arr[-m:].mean()))
    # 4. the same sort's own signal persistence: mean signal spread is not measured here,
    #    but the realised spread's autocorrelation is a cheap proxy for factor structure
    ac1 = float(np.corrcoef(g[:-1], g[1:])[0, 1])

    out = {
        "NOT_PREREGISTERED": "exploratory; the verdict is in T10_HELDOUT_RESULT.json",
        "n_sessions": len(days),
        "per_day_sd_bp_real_book": per_day_obs_sd * 1e4,
        "per_day_sd_bp_random_partition_null": per_day_null_sd * 1e4,
        "dispersion_ratio_real_over_null": per_day_obs_sd / per_day_null_sd,
        "standard_error_of_mean_bp_real": per_day_obs_sd / math.sqrt(len(days)) * 1e4,
        "standard_error_of_mean_bp_null": perm["null_sd"] * 1e4,
        "market_beta_of_long_short_book": beta,
        "residual_ann_sharpe_after_market": (
            float(np.mean(resid) / np.std(resid, ddof=1)) * math.sqrt(247.26)),
        "long_block_mean_bp": float(np.mean(longs) * 1e4),
        "short_block_mean_bp": float(np.mean(shorts) * 1e4),
        "long_block_t": float(np.mean(longs) / (np.std(longs, ddof=1) / math.sqrt(len(longs)))),
        "short_block_t": float(np.mean(shorts) / (np.std(shorts, ddof=1) / math.sqrt(len(shorts)))),
        "gross_autocorr_lag1": ac1,
        "moments_gross": stats.moments(list(g)),
    }
    (OUT / "T10_DIAGNOSTICS.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
