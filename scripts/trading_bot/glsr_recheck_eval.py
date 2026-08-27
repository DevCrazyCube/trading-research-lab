#!/usr/bin/env python3
"""Re-run the incumbent XS_GLSR_Z leg on the (corrected) full cross-section.

Signal = lg_z = zscore(log(count_long_short_ratio), 168h), cross-sectional quintile
(long top 20% of signed signal, short bottom 20%), dollar-neutral, gross=1, H=24h,
open-to-open next-bar fill, funding accrued, cost 5.5 bp/side on turnover. This is the
EXACT construction the sweep/basket harness uses for XS_GLSR_Z (perpmicro_sweep.py
build_features -> p.lg_z, weights_from_signal quintile, evaluate).

Sign is FROZEN at the leg's design orientation (auto-picked on the design window, then
applied to every window) -- the fade sign -1.

Reports net Sharpe by sub-window at top_n=50 (deployable) and top_n=120 (upper bound),
plus the live cross-section size (median live names) per window, which is the whole point:
before backfill the terminal window collapses to ~28 A-B names; after backfill it should
carry the real top-N-by-volume universe.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import perpmicro_sweep as ps

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXT = ROOT / "research" / "data" / "perpmicro_cache" / "panel1h_ext_trim.npz"
META = ROOT / "research" / "data" / "perpmicro_cache" / "panel1h_r3meta.npz"

WINS = {
    "design_2023-01_2024-06": ("2023-01-01", "2024-06-01"),
    "hold_2024-06_2025-01":   ("2024-06-01", "2025-01-01"),
    "terminal_2025-01_2026-08": ("2025-01-01", "2026-08-16"),
    "full_2023-01_2026-08":   ("2023-01-01", "2026-08-16"),
}


def load_panel():
    ext = np.load(EXT, allow_pickle=True)
    meta = np.load(META, allow_pickle=True)
    # grids must be identical (metapanel was built on ext's grid)
    assert list(ext["symbols"]) == list(meta["symbols"]), "symbol grids differ"
    assert np.array_equal(ext["t"], meta["t"]), "time grids differ"
    pan = {k: ext[k] for k in ["o", "h", "l", "c", "qv", "ntr", "tbq",
                               "fund", "fund_age_h", "fund_next_h", "t", "symbols"]}
    for k in ["oi", "oiv", "ttc", "tts", "glsr", "tlsr"]:
        pan[k] = meta[k]
    return pan


def live_names(p, wmask):
    """median count of live universe names inside the window."""
    n = p.univ.sum(0)
    return float(np.median(n[wmask])) if wmask.any() else 0.0


def glsr_finite_names(p, wmask):
    fin = np.isfinite(p.lg_z) & p.univ
    n = fin.sum(0)
    return float(np.median(n[wmask])) if wmask.any() else 0.0


def run_at(pan, top_n):
    ps.TOP_N = top_n
    p = ps.build_features(pan)
    x = p.lg_z
    # freeze the fade sign on the design window (auto-pick), apply to all
    m_des = ps.window_mask(p.t, *WINS["design_2023-01_2024-06"])
    pnl, pf, dh = ps.evaluate(x, p, 24, "quintile")
    NH = p.NH
    ndays = NH // 24
    dm_des = m_des[:ndays * 24].reshape(-1, 24).any(axis=1)
    g_des = (ps.to_daily(pnl, NH) + ps.to_daily(pf, NH))[dm_des]
    sign = 1.0 if np.nanmean(g_des) >= 0 else -1.0
    out = {}
    for tag, (a, b) in WINS.items():
        wm = ps.window_mask(p.t, a, b)
        dm = wm[:ndays * 24].reshape(-1, 24).any(axis=1)
        dp = ps.to_daily(pnl, NH)[dm]
        df = ps.to_daily(pf, NH)[dm]
        dt_ = ps.to_daily(dh, NH)[dm]
        gross = dp + df
        og = sign * gross
        net = og - dt_ * ps.COST_SIDE_BP * 1e-4
        out[tag] = {
            "sign": sign,
            "n_days": int(len(net)),
            "median_live_names": round(live_names(p, wm), 1),
            "median_glsr_names": round(glsr_finite_names(p, wm), 1),
            "sharpe_gross": round(ps.sharpe(og), 3),
            "sharpe_net": round(ps.sharpe(net), 3),
            "ann_ret_net_pct": round(float(np.nanmean(net) * 365) * 100, 2),
            "turnover_per_day": round(float(np.nanmean(dt_)), 3),
            "breakeven_bp_side": round(float(np.nanmean(og) / max(np.nanmean(dt_), 1e-9) * 1e4), 2),
        }
    return out


def main():
    pan = load_panel()
    result = {"panel": str(META), "cost_side_bp": ps.COST_SIDE_BP,
              "top50_deployable": run_at(pan, 50),
              "top120_upperbound": run_at(pan, 120)}
    print(json.dumps(result, indent=2))
    outp = ROOT / "research" / "trading_bot" / "XS_GLSR_Z_RECHECK_result.json"
    outp.write_text(json.dumps(result, indent=2))
    print("wrote", outp)


if __name__ == "__main__":
    main()
