#!/usr/bin/env python3
"""T17 POWER CENSUS. Judged against `T17_POWER_GATE.md`, sha256 03d257ce..., hashed first.

Run BEFORE the held-out window is spent. Writes `T17_POWER_CENSUS.json`. If G1 fails the
window is NOT spent -- that is the whole point of the gate, and it is what T15 taught.
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from trading_bot import costs as COSTS  # noqa: E402
from trading_bot import t17_orb as ORB  # noqa: E402
from trading_bot import t17_run as RUN  # noqa: E402

CACHE = ROOT / "research" / "data" / "t17_cache"
OUT = ROOT / "research" / "trading_bot"
Z = 2.80


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def main():
    gate_hash = sha(OUT / "T17_POWER_GATE.md")
    selection = json.loads((CACHE / "selection.json").read_text())
    census_rows = json.loads((CACHE / "selection_census.json").read_text())
    by_day = {c["day"]: c for c in census_rows}

    def window(lo, hi):
        return [d for d in sorted(selection) if lo <= d <= hi]

    design = window(ORB.DESIGN_START, ORB.DESIGN_END)
    heldout = window(ORB.HELDOUT_START, ORB.HELDOUT_END)
    postpaper = window(ORB.POSTPAPER_START, ORB.POSTPAPER_END)

    def count(days):
        full = [d for d in days if len(selection.get(d) or []) >= ORB.TOP_N]
        picks = sum(len(selection.get(d) or []) for d in days)
        return {"sessions": len(days), "sessions_with_full_top20": len(full),
                "selected_stock_days": picks}

    # ---- G0: data census -------------------------------------------------
    paths_present, paths_missing, sym_present, sym_missing = 0, 0, 0, 0
    for d in heldout:
        p = CACHE / "paths" / f"{d}.json"
        if not p.exists():
            paths_missing += 1
            continue
        paths_present += 1
        raw = json.loads(p.read_text())
        for row in selection[d]:
            if raw.get(row[1]):
                sym_present += 1
            else:
                sym_missing += 1
    served = sym_present / max(1, sym_present + sym_missing)
    heldout_counts = count(heldout)
    g0 = (heldout_counts["sessions_with_full_top20"] >= 900) and (served >= 0.98)

    # ---- G1: portfolio power ---------------------------------------------
    years = len(heldout) / 252.0
    mde_sharpe = Z / math.sqrt(years)
    g1 = mde_sharpe <= 1.405

    # ---- G2 / G3: trade count and per-trade MDE, DESIGN WINDOW ONLY -------
    cost = COSTS.b22b_measured_costs()
    matrix, mcensus = RUN.build_outcomes(design, selection, "empirical")
    res = RUN.replay(matrix, design, cost, "empirical", keep_trades=True)
    done = [t for t in res["trades"] if t.get("outcome") in ("STOPPED", "CLOSE")]
    nr = [t["net_r"] for t in done if t["net_r"] is not None]
    n = len(nr)
    mean_r = sum(nr) / n if n else None
    sd_r = math.sqrt(sum((x - mean_r) ** 2 for x in nr) / (n - 1)) if n > 1 else None
    mde_r = Z * sd_r / math.sqrt(n) if n > 1 else None
    days_with_trades = len({t["day"] for t in done})
    # same-day cluster inflation: sqrt of the mean trades per session
    cluster = math.sqrt(n / days_with_trades) if days_with_trades else None

    # scale the design-window MDE to the held-out trade count for a like-for-like read
    heldout_est_trades = int(n * len(heldout) / max(1, len(design)))
    mde_r_heldout = Z * sd_r / math.sqrt(heldout_est_trades) if sd_r else None
    g2 = (heldout_est_trades >= 2000) and (len(heldout) >= 500)
    g3 = bool(mde_r is not None and mde_r <= 0.080)

    # ---- G4: cost resolution ---------------------------------------------
    slip = json.loads((OUT / "T17_SLIPPAGE_EMPIRICAL.json").read_text())
    rop = sorted(r["r_over_price"] for r in slip)
    m = len(rop)
    r_bp_median = rop[m // 2] * 10000
    r_bp_mean = sum(rop) / m * 10000
    round_trip_bp = float(cost.round_trip_bp())
    g4 = m >= 100

    # The same quantity measured on T17's OWN selected stock-days, which is the population
    # the strategy actually trades. B22B's 429 came from a 2025 most-actives pool that skews
    # to low-priced, high-ATR names; the point-in-time top-20-by-relative-volume selection
    # over ten years does not, so the two are reported side by side rather than conflated.
    own = []
    for d in design + heldout:
        for row in selection.get(d) or []:
            atr, level = row[5], row[3]
            if level > 0:
                own.append((atr // 10) * 10000 / level)   # R as bp of the breakout level
    own.sort()
    k = len(own)
    own_stats = ({"n": k, "r_bp_p10": own[k // 10], "r_bp_p50": own[k // 2],
                  "r_bp_p90": own[9 * k // 10], "r_bp_mean": sum(own) / k} if k else {"n": 0})

    report = {
        "document": "T17_POWER_CENSUS",
        "judged_against": {"file": "research/trading_bot/T17_POWER_GATE.md",
                           "sha256": gate_hash,
                           "expected_sha256": ("03d257ce8ff6c92c09b0be4c896dacc6a424c8925"
                                               "d96a805e2fc25a80fec6465"),
                           "matches": gate_hash == ("03d257ce8ff6c92c09b0be4c896dacc6a424c89"
                                                    "25d96a805e2fc25a80fec6465")},
        "windows": {"design": {"dates": [ORB.DESIGN_START, ORB.DESIGN_END], **count(design)},
                    "heldout": {"dates": [ORB.HELDOUT_START, ORB.HELDOUT_END],
                                **heldout_counts},
                    "postpaper": {"dates": [ORB.POSTPAPER_START, ORB.POSTPAPER_END],
                                  **count(postpaper)}},
        "G0_data_census": {
            "pass": bool(g0),
            "heldout_sessions_with_full_top20": heldout_counts["sessions_with_full_top20"],
            "threshold_sessions": 900,
            "path_files_present": paths_present, "path_files_missing": paths_missing,
            "selected_stock_days_served": sym_present,
            "selected_stock_days_missing": sym_missing,
            "served_fraction": served, "threshold_served": 0.98},
        "G1_portfolio_power": {
            "pass": bool(g1), "heldout_sessions": len(heldout), "heldout_years": years,
            "mde_annualised_sharpe": mde_sharpe, "threshold": 1.405,
            "z": Z,
            "years_needed_for_claimed_sharpe_2p81": (Z / 2.81) ** 2,
            "note": ("The claimed Sharpe needs under a year to certify. What this window has "
                     "to be able to see is a HALVED version of it, which is the threshold.")},
        "G2_trade_count": {
            "pass": bool(g2), "design_trades": n,
            "heldout_estimated_trades": heldout_est_trades, "threshold_trades": 2000,
            "heldout_sessions": len(heldout), "threshold_sessions": 500},
        "G3_per_trade_mde": {
            "pass": bool(g3), "design_trades": n,
            "mean_net_r_design": mean_r, "sd_net_r_design": sd_r,
            "mde_r_design": mde_r, "threshold_r": 0.080,
            "trades_per_session_design": n / days_with_trades if days_with_trades else None,
            "same_day_cluster_inflation_factor": cluster,
            "mde_r_design_cluster_adjusted": mde_r * cluster if mde_r and cluster else None,
            "mde_r_heldout_projected": mde_r_heldout,
            "caveat": ("Same-session trades share a market factor, so the unadjusted per-trade "
                       "MDE overstates the evidence. Both are given. G1, on the daily "
                       "portfolio series, is the binding gate.")},
        "G4_cost_resolution": {
            "pass": bool(g4), "stock_days_measured": m, "threshold": 100,
            "r_as_bp_of_notional_median": r_bp_median,
            "r_as_bp_of_notional_mean": r_bp_mean,
            "t6_round_trip_bp_of_notional": round_trip_bp,
            "t6_round_trip_in_R_at_median": round_trip_bp / r_bp_median,
            "t6_round_trip_in_R_at_mean": round_trip_bp / r_bp_mean,
            "paper_edge_at_its_own_filter_R": 0.08,
            "paper_edge_best_bucket_R": 0.38,
            "cost_as_multiple_of_paper_headline_edge":
                (round_trip_bp / r_bp_median) / 0.08,
            "r_on_T17_own_selection": own_stats,
            "t6_round_trip_in_R_on_T17_own_selection_median":
                (round_trip_bp / own_stats["r_bp_p50"]) if own_stats.get("n") else None},
        "design_census": mcensus,
        "verdict": ("PASS" if all([g0, g1, g2, g3, g4]) else "POWER-BLOCKED"),
        "gates_failed": [k for k, v in
                         [("G0", g0), ("G1", g1), ("G2", g2), ("G3", g3), ("G4", g4)]
                         if not v],
    }
    (OUT / "T17_POWER_CENSUS.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "design_census"}, indent=1))


if __name__ == "__main__":
    main()
