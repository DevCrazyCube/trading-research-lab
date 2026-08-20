#!/usr/bin/env python3
"""Per-symbol half-spread proxy for the ETF-structural-RV deep mine.

WHY THIS EXISTS. `rv_sweep.py` charges one flat 1.0 bp/side across every leg. For a book that
is SPY against SPY-like ETFs that is defensible. This deep mine trades ETFs against SINGLE
NAMES and against thin ETFs (GDXJ, XHB, SIVR, VTWO), whose spreads are nothing like SPY's, and
a market-neutral RV rule pays BOTH legs. A flat rung would systematically flatter exactly the
configs that trade the thin leg hardest.

WHAT IS AND IS NOT MEASURED. This host has no free quote history, so a QUOTED spread cannot be
measured here. What is used instead:

  headline_half_bp = max(1.0 bp, 2 x half_tick_bp),  half_tick_bp = (0.5 cent / price) * 1e4

  * the half-tick term is ARITHMETIC, not an estimate: a US equity or ETF cannot quote tighter
    than one cent, so half a cent over the price is a hard lower bound on the half-spread, and
    for one-tick-wide mega-cap ETFs it is also the right answer.
  * the 2x is an ADVERSITY MULTIPLIER, declared as a judgement and not as a measurement: a
    marketable child order does not always rest at the touch, and stressed minutes quote wider.
  * the 1.0 bp floor makes this model charge NO LESS than rv_sweep's flat rung on any leg, so a
    config cannot look better here purely by being re-costed.

CROSS-CHECK, recorded but NOT used in the headline: the Roll (1984) covariance estimator on
5-minute returns, s = 2*sqrt(-cov(r_t, r_{t-1})). It is reported per symbol so a reader can see
where the tick model and an independent estimator disagree. It is not the headline because on
5-minute bars of trending mega-caps the serial covariance is frequently POSITIVE, at which
point Roll is undefined rather than small -- an undefined estimator must not silently become a
zero cost.

An earlier version of this file used the Corwin-Schultz high-low estimator on daily bars. It
returned an 11 bp half-spread for SPY, which is roughly a hundred times the truth; CS is
designed for illiquid daily data where the spread is a large share of the range, and it breaks
in exactly this universe. That attempt is recorded here rather than deleted, because the
failure is the reason the tick model is the headline.

PROVENANCE LABEL: TICK_FLOOR_TIMES_ADVERSITY_NOT_A_QUOTE_MEASUREMENT.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

CACHE = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "rv_cache"
OUT = CACHE / "spread_proxy.json"
ADVERSITY = 2.0
FLOOR_BP = 1.0
CAP_BP = 25.0


def main():
    rows = {}
    for p in sorted(CACHE.glob("*.npz")):
        if p.name in ("panel.npz", "design_daily.npz"):
            continue
        d = np.load(p)
        c = d["c"].astype(np.float64)
        t = d["t"].astype(np.int64)
        if c.size < 500:
            continue
        px = float(np.nanmedian(c))
        # Roll cross-check on 5-minute returns, same-session pairs only
        lc = np.log(c)
        r = np.diff(lc)
        same = np.diff((t - 5 * 3600) // 86400) == 0
        r = np.where(same, r, np.nan)
        r0, r1 = r[:-1], r[1:]
        m = np.isfinite(r0) & np.isfinite(r1)
        cov = float(np.cov(r0[m], r1[m])[0, 1]) if m.sum() > 1000 else np.nan
        roll_half_bp = (np.sqrt(-cov) * 1e4) if (np.isfinite(cov) and cov < 0) else None
        tick_bp = 0.005 / px * 1e4   # $0.005 over the price, in bp
        head = float(np.clip(max(FLOOR_BP, ADVERSITY * tick_bp), FLOOR_BP, CAP_BP))
        rows[p.stem] = {
            "median_px": round(px, 2),
            "half_tick_bp": round(tick_bp, 4),
            "roll_half_bp_5min": (None if roll_half_bp is None else round(float(roll_half_bp), 3)),
            "roll_serial_cov_sign": ("negative" if (np.isfinite(cov) and cov < 0) else "positive_or_nan"),
            "headline_half_bp": round(head, 3),
        }
        del d
    n_roll = sum(1 for v in rows.values() if v["roll_half_bp_5min"] is not None)
    payload = {
        "provenance": "TICK_FLOOR_TIMES_ADVERSITY_NOT_A_QUOTE_MEASUREMENT",
        "formula": "headline_half_bp = clip(max(1.0, 2.0 * (0.5c/price)*1e4), 1.0, 25.0)",
        "adversity_multiplier": ADVERSITY,
        "floor_bp": FLOOR_BP,
        "roll_cross_check_defined_for": n_roll,
        "roll_cross_check_undefined_for": len(rows) - n_roll,
        "roll_note": "Roll is undefined (positive serial covariance) for the rest; undefined is "
                     "NOT zero and those symbols fall back to the tick model like everyone else.",
        "n_symbols": len(rows),
        "symbols": rows,
    }
    OUT.write_text(json.dumps(payload, indent=1, sort_keys=True))
    worst = sorted(rows.items(), key=lambda kv: -kv[1]["headline_half_bp"])[:10]
    best = sorted(rows.items(), key=lambda kv: kv[1]["headline_half_bp"])[:6]
    print("widest:", [(k, v["headline_half_bp"]) for k, v in worst], flush=True)
    print("tightest:", [(k, v["headline_half_bp"]) for k, v in best], flush=True)
    print(f"roll defined for {n_roll}/{len(rows)}", flush=True)
    print("wrote", OUT, len(rows), flush=True)


if __name__ == "__main__":
    main()
