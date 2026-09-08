#!/usr/bin/env python3
"""T12 diagnostics -- the hostile follow-up on the S2 (raw discount level) trials.

The pre-registered PRIMARY (trial 4) is dead on three gates. Trials 5 and 6 -- the naive
`long the widest raw discount, short the narrowest' form -- came out strongly positive out of
sample. This module exists to attack that number, not to celebrate it. Nothing here can change
the T12 verdict: the primary was declared in advance and it is what the verdict runs on. What
this produces is either an explanation or a pre-registration target for somebody else.

Attacks, in order of how likely each is to be the whole story:
  1. DISTRIBUTION HARVESTING -- rerun on the raw CEFConnect close, which excludes distributions.
     Wide-discount funds distribute most; if the edge is the yield differential it dies here.
  2. NAV vs DISCOUNT decomposition -- did the P&L come from the discount narrowing (the claimed
     mechanism) or from the wide-discount funds' ASSETS outperforming (a factor bet)?
  3. PERSISTENCE -- does the wide-discount decile's discount actually narrow, or does it stay
     wide while the fund pays out? A mean-reversion claim requires the former.
  4. COMPOSITION -- what is in the two legs? A book that is long muni CEFs and short equity CEFs
     is an asset-class bet wearing a discount label.
  5. EXECUTABILITY -- is the SHORT leg borrowable at all? Section 2d measured 52 % of the
     universe shortable; the premium decile is the half that matters.
  6. SURVIVORSHIP -- the panel is 100 % survivors by construction. Bound the attrition.
"""

from __future__ import annotations

import json
import math
import pathlib
import statistics
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.t3_pressure_reversal as t3                                        # noqa: E402
import scripts.t12_cef_discount as t12                                           # noqa: E402
import scripts.t12_evaluate as E                                                 # noqa: E402
from scripts.trading_bot import stats as S                                        # noqa: E402

OUT = ROOT / "research" / "trading_bot"


def main():
    E.assert_frozen()
    grid, panel, bars, tickers, dropped = E.build_panel()
    k_split = next(i for i, d in enumerate(grid) if d >= E.SPLIT)
    uni = {r["Ticker"]: r for r in t12.universe()}
    flags = t12.alpaca_asset_flags(sorted(uni))

    rets_adj = E.weekly_returns(bars, grid)
    raw_px, nav_px = defaultdict(dict), defaultdict(dict)
    for d, row in panel.items():
        for t, r in row.items():
            raw_px[t][d] = r["price"]
            nav_px[t][d] = r["nav"]
    rets_raw = E.weekly_returns(raw_px, grid)
    rets_nav = E.weekly_returns(nav_px, grid)

    base = E.cef_cost_model(
        json.loads((OUT / "T12_FRICTION_CENSUS.json").read_text())
        ["measured_quoted_half_spread"]["median_half_spread_bp"])
    V = json.loads((OUT / "T12_HELDOUT_RESULT.json").read_text())[
        "history_gate"]["sharpe_variance_across_design_trials"]

    doc = {"preregistration_sha256": E.PREREG_SHA,
           "scope": "DIAGNOSTIC ONLY -- cannot change the T12 verdict (primary = trial 4)"}

    for cfg in [c for c in E.TRIALS if c["family"] == "S2"]:
        tag = f"trial{cfg['id']}_S2_H{cfg['H']}"
        row = {"cfg": cfg}

        # 1. distribution harvesting
        for name, rets in (("adjusted_total_return", rets_adj),
                           ("raw_close_no_distributions", rets_raw)):
            w, tr = E.run_config(cfg, panel, grid, rets, base, k_lo=k_split,
                                 k_hi=len(grid) - 1)
            row[name] = E.summarise(w)
            row[name]["gross"] = E.summarise(w, "gross")
        row["distribution_share_of_edge_bp"] = (
            row["adjusted_total_return"]["mean_bp"]
            - row["raw_close_no_distributions"]["mean_bp"])

        # 2. NAV leg
        wn, _ = E.run_config(cfg, panel, grid, rets_nav, base, k_lo=k_split,
                             k_hi=len(grid) - 1)
        row["nav_leg_gross"] = E.summarise(wn, "gross")

        # DSR on the held-out net series, at the declared trial count
        w, _ = E.run_config(cfg, panel, grid, rets_adj, base, k_lo=k_split,
                            k_hi=len(grid) - 1)
        row["dsr_trials6"] = S.deflated_sharpe([x["net"] for x in w],
                                               trials=len(E.TRIALS), sharpe_variance=V)
        row["permutation"] = E.decile_label_permutation(
            cfg, panel, grid, rets_adj, k_split, len(grid) - 1, n=2000)
        doc[tag] = row
        print(f"{tag}: adj {row['adjusted_total_return']['mean_bp']:+.2f} bp/wk | "
              f"raw-close {row['raw_close_no_distributions']['mean_bp']:+.2f} | "
              f"NAV leg {row['nav_leg_gross']['mean_bp']:+.2f} | "
              f"DSR {row['dsr_trials6']['dsr']:.4f} | "
              f"perm p {row['permutation']['p_right_tail']:.4f} "
              f"disp {row['permutation']['dispersion_ratio']:.2f}")

    # 3/4/5. persistence, composition, executability -- on trial 6, held out
    cfg = next(c for c in E.TRIALS if c["id"] == 6)
    H = cfg["H"]
    narrow, comp_long, comp_short, short_ok, long_ok = [], defaultdict(int), defaultdict(int), 0, 0
    n_long_total = n_short_total = 0
    disc_long_entry, disc_long_exit, disc_short_entry, disc_short_exit = [], [], [], []
    k = k_split
    while k + 1 + H <= len(grid) - 1:
        sig = E.signal_at(panel, grid, k, cfg, None)
        lo, hi = E.deciles(sig)
        if lo and hi:
            kx = k + H
            for t in lo:
                comp_long[uni.get(t, {}).get("Strategy") or "?"] += 1
                n_long_total += 1
                long_ok += 1 if (flags.get(t) or {}).get("tradable") else 0
                if t in panel[grid[kx]]:
                    disc_long_entry.append(panel[grid[k]][t]["discount"])
                    disc_long_exit.append(panel[grid[kx]][t]["discount"])
            for t in hi:
                comp_short[uni.get(t, {}).get("Strategy") or "?"] += 1
                n_short_total += 1
                short_ok += 1 if (flags.get(t) or {}).get("shortable") else 0
                if t in panel[grid[kx]]:
                    disc_short_entry.append(panel[grid[k]][t]["discount"])
                    disc_short_exit.append(panel[grid[kx]][t]["discount"])
        k += H
    doc["trial6_persistence_heldout"] = {
        "long_leg_mean_discount_at_entry_pct": statistics.fmean(disc_long_entry),
        "long_leg_mean_discount_after_H_pct": statistics.fmean(disc_long_exit),
        "long_leg_mean_narrowing_pp": statistics.fmean(disc_long_exit)
                                      - statistics.fmean(disc_long_entry),
        "short_leg_mean_discount_at_entry_pct": statistics.fmean(disc_short_entry),
        "short_leg_mean_discount_after_H_pct": statistics.fmean(disc_short_exit),
        "short_leg_mean_narrowing_pp": statistics.fmean(disc_short_exit)
                                       - statistics.fmean(disc_short_entry),
        "note": ("A mean-reversion claim REQUIRES the long leg's discount to narrow (become "
                 "less negative) and the short leg's premium to shrink. If both legs sit still "
                 "the P&L is carry or beta, not reversion."),
    }
    doc["trial6_composition_heldout"] = {
        "long_leg_top_strategies": dict(sorted(comp_long.items(), key=lambda x: -x[1])[:8]),
        "short_leg_top_strategies": dict(sorted(comp_short.items(), key=lambda x: -x[1])[:8]),
        "long_leg_name_slots": n_long_total, "short_leg_name_slots": n_short_total,
    }
    doc["trial6_executability_live_flags"] = {
        "long_leg_slots_tradable": long_ok, "long_leg_slots": n_long_total,
        "short_leg_slots_shortable_at_alpaca": short_ok, "short_leg_slots": n_short_total,
        "short_leg_shortable_share": round(short_ok / max(1, n_short_total), 4),
        "note": ("LIVE flags applied retrospectively -- NOT a backtest screen, and it is "
                 "look-ahead by construction. It bounds what could be put on TODAY."),
    }
    print("\npersistence (trial 6, held out): long leg discount "
          f"{doc['trial6_persistence_heldout']['long_leg_mean_discount_at_entry_pct']:.2f}% -> "
          f"{doc['trial6_persistence_heldout']['long_leg_mean_discount_after_H_pct']:.2f}%  |  "
          "short leg "
          f"{doc['trial6_persistence_heldout']['short_leg_mean_discount_at_entry_pct']:.2f}% -> "
          f"{doc['trial6_persistence_heldout']['short_leg_mean_discount_after_H_pct']:.2f}%")
    print("short leg shortable at Alpaca: "
          f"{doc['trial6_executability_live_flags']['short_leg_shortable_share'] * 100:.1f}%")
    print("long leg strategies :", doc["trial6_composition_heldout"]["long_leg_top_strategies"])
    print("short leg strategies:", doc["trial6_composition_heldout"]["short_leg_top_strategies"])

    # 6. survivorship -- bound the attrition with a NAMED heuristic, labelled as one
    doc["survivorship_probe"] = survivorship_probe()
    print("\nsurvivorship probe:", json.dumps(doc["survivorship_probe"], indent=1)[:900])

    path = OUT / "T12_DIAGNOSTICS.json"
    path.write_text(json.dumps(doc, indent=2, default=str) + "\n")
    print(f"\nwrote {path}")


def survivorship_probe():
    """A LOWER BOUND on CEF attrition 2021-2026, by a stated name heuristic.

    CEFConnect has no delisted list, so the panel is 100 % survivors. Alpaca's INACTIVE
    us_equity list is a partial record of what stopped trading. Counting the inactive symbols
    whose asset NAME matches the closed-end-fund naming conventions of the LIVE 360 gives a
    lower bound on how many funds the panel is missing. It is a heuristic and it is labelled
    one: it will miss funds whose names do not match and will over-count some ETFs/BDCs.
    """
    import re
    live = {r["Ticker"]: (r.get("Name") or "") for r in t12.universe()}
    pat = re.compile(
        r"(closed[- ]end|municipal|muni |income fund|income trust|term trust|"
        r"opportunit(y|ies) fund|dividend .*fund|senior floating|high income|"
        r"premium .*fund|convertible .*fund|infrastructure fund)", re.I)
    inactive = t3._get(t3.TRADING_HOST, "/v2/assets",
                       {"asset_class": "us_equity", "status": "inactive"})
    hits = [a for a in inactive if pat.search(a.get("name") or "")]
    return {
        "alpaca_inactive_us_equity": len(inactive),
        "inactive_matching_cef_name_heuristic": len(hits),
        "live_cef_universe": len(live),
        "implied_lower_bound_attrition_share": round(
            len(hits) / max(1, len(hits) + len(live)), 4),
        "sample_of_matches": sorted({a["symbol"] for a in hits})[:25],
        "HEURISTIC_WARNING": (
            "A NAME MATCH IS NOT A CLASSIFICATION. This over-counts (open-end/ETF/BDC names "
            "collide) and under-counts (many CEF names carry none of these words), and Alpaca's "
            "inactive list is itself partial. It is reported as an ORDER OF MAGNITUDE for how "
            "much of the 2021 CEF population the survivor-only panel cannot see, not as a "
            "measurement of it."),
    }


if __name__ == "__main__":
    main()
