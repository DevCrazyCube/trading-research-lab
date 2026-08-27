#!/usr/bin/env python3
"""T23 POWER CENSUS. Judged against the frozen `research/trading_bot/T23_POWER_GATE.md`.

Runs BEFORE the pre-registration and BEFORE the held-out window is touched. If G1 fails, the
held-out window is NOT spent and the verdict is DEAD-BY-INSUFFICIENT-POWER -- the same exit
`T9` and `T15` took.

The only thing this script is allowed to compute on the held-out window is its SHAPE: how many
months, how many names, how much volume, how many delistings. It never computes a held-out
return. The dispersion input comes from the DESIGN window (burnable) and from T21's own reported
number, and per the gate's §1a the LARGER of the two is used.

USAGE
    python3 scripts/trading_bot/t23_census.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from trading_bot import t23_carry as R  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "research" / "trading_bot" / "T23_POWER_GATE.md"
GATE_SHA_EXPECTED_FILE = ROOT / "research" / "trading_bot" / "T23_POWER_GATE.sha256"
OUT = ROOT / "research" / "trading_bot" / "T23_POWER_CENSUS.json"
CACHE = ROOT / "research" / "data" / "t23_cache"

Z = 2.80                       # 1.96 + 0.84: two-sided 5%, 80% power
T21_CLAIMED_EDGE_PP = 2.20     # the effect G1 must be able to resolve
T21_REPORTED_SD_PP = 3.08      # the optimistic dispersion input
G2_SEPARATION_PP = 1.20        # 2.20 claimed minus the 1.00 pp venue-tail bar

DESIGN = ("2020-01", "2022-12")
HELDOUT = ("2023-01", "2026-07")
HELDOUT_CLEAN = ("2023-01", "2024-09")   # the months T21's search never saw

PRIMARY = R.Config(top_n=3, threshold_usd=20_000_000, name="liq20m_top3")


def months_between(a: str, b: str) -> list[str]:
    out, cur = [], a
    while cur <= b:
        out.append(cur)
        cur = R.ym_add(cur, 1)
    return out


def main() -> int:
    gate_sha = hashlib.sha256(GATE.read_bytes()).hexdigest()
    expected = None
    if GATE_SHA_EXPECTED_FILE.exists():
        expected = GATE_SHA_EXPECTED_FILE.read_text().split()[0]
    if expected is not None and expected != gate_sha:
        raise SystemExit(f"POWER GATE HAS CHANGED since it was frozen: {gate_sha} != {expected}")

    uni = json.loads((CACHE / "universe.json").read_text())
    expected_sm = uni["symbol_months"]
    present = {"fundingRate": 0, "klines1d": 0, "premium1d": 0}
    for sym, mons in uni["universe"].items():
        for ym in mons:
            for kind in present:
                if (CACHE / "raw" / kind / sym / f"{sym}-{kind}-{ym}.zip").exists():
                    present[kind] += 1

    panel = R.Panel().load()

    # --- G0b: how many names in the held-out window are dead TODAY --------------------------
    # The live endpoint is read ONCE, for a diagnostic count only. No selection ever reads it.
    live_symbols = set()
    live_probe_error = None
    try:
        import requests
        js = requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=30).json()
        live_symbols = {s["symbol"] for s in js.get("symbols", [])
                        if s.get("status") == "TRADING"}
    except Exception as exc:  # noqa: BLE001
        live_probe_error = repr(exc)

    ho_months = months_between(*HELDOUT)
    ho_syms = {s for s in panel.funding_month
               if s.endswith("USDT") and any(m in panel.funding_month[s] for m in ho_months)}
    gone = sorted(s for s in ho_syms if live_symbols and s not in live_symbols)

    # --- design-window run: dispersion only -------------------------------------------------
    design_months = months_between(*DESIGN)
    design_recs = R.run_book(panel, PRIMARY, design_months)
    design_sum = R.summarise(design_recs)

    sd_design_pp = design_sum.get("excess_sd_ann_pct", float("nan"))
    if sd_design_pp != sd_design_pp:  # NaN: max() would silently propagate it
        raise SystemExit("design-window dispersion is NaN; the census cannot judge G1")
    sd_used_pp = max(sd_design_pp, T21_REPORTED_SD_PP)
    sd_basis = "design-window measured" if sd_design_pp >= T21_REPORTED_SD_PP else "T21 reported"

    # Diagnostic, NOT a gate input: the dispersion of the FUNDING-ONLY estimator, i.e. T21's own
    # object, which ignores the mark-to-market of the premium the carrier is short. Reported so
    # that a G1 failure cannot be dismissed as an artefact of adding the basis leg.
    live_design = [r for r in design_recs if not r["skipped"]]
    fo = [r["excess"] + r["dpremium"] / R.CAPITAL_MULTIPLIER for r in live_design]
    import statistics as _st
    sd_funding_only_pp = (_st.stdev(fo) * (12 ** 0.5) * 100) if len(fo) > 1 else float("nan")

    # --- held-out SHAPE only ----------------------------------------------------------------
    ho_shape = []
    for ym in ho_months:
        elig = R.screen_month(panel, ym, PRIMARY.threshold_usd)
        ho_shape.append({"month": ym, "n_eligible": len(elig)})
    ho_usable = [m for m in ho_shape if m["n_eligible"] >= PRIMARY.top_n]
    ho_years = len(ho_usable) / 12.0

    ho_clean_months = set(months_between(*HELDOUT_CLEAN))
    ho_clean_usable = [m for m in ho_usable if m["month"] in ho_clean_months]

    design_usable = [r for r in design_recs if not r["skipped"]]

    mde = Z * sd_used_pp / (ho_years ** 0.5) if ho_years > 0 else float("inf")
    mde_clean = (Z * sd_used_pp / ((len(ho_clean_usable) / 12.0) ** 0.5)
                 if ho_clean_usable else float("inf"))
    mde_whole_panel = Z * sd_used_pp / (((len(design_usable) + len(ho_usable)) / 12.0) ** 0.5)

    # --- G4: quote-volume coverage over held-out symbol-months ------------------------------
    ho_sm = ho_sm_with_vol = 0
    for sym in ho_syms:
        for ym in ho_months:
            if ym in panel.funding_month.get(sym, {}):
                ho_sm += 1
                _, nb = panel.median_quote_volume(sym, R.ym_end(ym))
                if nb >= 1:
                    ho_sm_with_vol += 1

    # --- capacity ---------------------------------------------------------------------------
    med_pick_vol_design = design_sum.get("median_pick_volume_usd", 0.0)

    g0 = present["fundingRate"] / expected_sm
    gates = {
        "G0_data_census": {
            "pass": g0 >= 0.98,
            "symbol_months_expected": expected_sm,
            "present": present,
            "coverage": {k: round(v / expected_sm, 4) for k, v in present.items()},
            "threshold": 0.98,
            "consequence_if_failed": "the test is not run",
        },
        "G0b_survivorship_proof": {
            "pass": len(gone) >= 20,
            "heldout_symbols": len(ho_syms),
            "delisted_since_heldout_window": len(gone),
            "threshold": 20,
            "live_probe_error": live_probe_error,
            "examples": gone[:15],
            "consequence_if_failed": "the test is not run",
        },
        "G1_portfolio_power_BINDING": {
            "pass": mde <= T21_CLAIMED_EDGE_PP,
            "mde_annual_excess_pp": mde,
            "threshold_pp": T21_CLAIMED_EDGE_PP,
            "z": Z,
            "sd_annual_pp_used": sd_used_pp,
            "sd_annual_pp_design_measured": sd_design_pp,
            "sd_annual_pp_T21_reported": T21_REPORTED_SD_PP,
            "sd_basis": sd_basis,
            "heldout_usable_months": len(ho_usable),
            "heldout_years": ho_years,
            "consequence_if_failed":
                "POWER-BLOCKED; the held-out window is NOT spent; DEAD-BY-INSUFFICIENT-POWER",
        },
        "G2_bar_separation_DIAGNOSTIC": {
            "pass": mde <= G2_SEPARATION_PP,
            "mde_annual_excess_pp": mde,
            "threshold_pp": G2_SEPARATION_PP,
            "consequence_if_failed":
                "reported as a failure; does not by itself stop the test",
        },
        "G3_month_count": {
            "pass": len(design_usable) >= 30 and len(ho_usable) >= 36,
            "design_usable_months": len(design_usable),
            "heldout_usable_months": len(ho_usable),
            "thresholds": {"design": 30, "heldout": 36},
            "consequence_if_failed": "the test is not run",
        },
        "G4_cost_resolution": {
            "pass": (ho_sm_with_vol / ho_sm if ho_sm else 0.0) >= 0.95,
            "heldout_symbol_months": ho_sm,
            "with_quote_volume": ho_sm_with_vol,
            "coverage": round(ho_sm_with_vol / ho_sm, 4) if ho_sm else 0.0,
            "threshold": 0.95,
            "consequence_if_failed": "the test is not run",
        },
    }

    failed = [k for k, v in gates.items() if not v["pass"]]
    data_failed = [k for k in failed if k.startswith(("G0", "G3", "G4"))]
    if not gates["G1_portfolio_power_BINDING"]["pass"]:
        verdict = "POWER-BLOCKED"
    elif data_failed:
        verdict = "BLOCKED-ON-DATA"
    else:
        verdict = "POWERED"

    out = {
        "document": "T23_POWER_CENSUS",
        "judged_against": {"file": str(GATE.relative_to(ROOT)), "sha256": gate_sha,
                           "expected_sha256": expected, "matches": expected == gate_sha},
        "windows": {"design": DESIGN, "heldout": HELDOUT, "heldout_clean": HELDOUT_CLEAN},
        "primary_configuration": PRIMARY.as_dict(),
        "panel": {
            "symbols_enumerated": uni["symbols"],
            "symbol_months_enumerated": expected_sm,
            "months_covered": [panel.months[0], panel.months[-1]],
            "usdt_symbols": sum(1 for s in panel.funding_month if s.endswith("USDT")),
        },
        "gates": gates,
        "mde_context": {
            "mde_heldout_full_pp": mde,
            "mde_heldout_clean_pp": mde_clean,
            "mde_whole_panel_single_shot_pp": mde_whole_panel,
            "years_needed_at_T10_arithmetic": (
                (Z / (T21_CLAIMED_EDGE_PP / sd_used_pp)) ** 2 if sd_used_pp else None),
            "note": "years_needed is (z/S)^2 with S the EXCESS-over-T-bills Sharpe implied by "
                    "T21's own claim and the dispersion input actually used.",
            "sd_annual_pp_funding_only_design": sd_funding_only_pp,
            "mde_heldout_full_pp_if_funding_only_sd":
                Z * max(sd_funding_only_pp, T21_REPORTED_SD_PP) / (ho_years ** 0.5)
                if ho_years > 0 else None,
            "years_needed_if_funding_only_sd": (
                (Z / (T21_CLAIMED_EDGE_PP / max(sd_funding_only_pp, T21_REPORTED_SD_PP))) ** 2),
            "funding_only_note":
                "Diagnostic only. T21's estimator ignored the premium mark-to-market; this row "
                "shows the census would reach the same verdict on T21's own noisier-or-quieter "
                "object, so a G1 failure is not an artefact of adding the basis leg.",
        },
        "design_window_summary": design_sum,
        "design_window_eligible_counts": [
            {"month": r["month"], "n_eligible": r["n_eligible"], "n_held": r["n_held"]}
            for r in design_recs],
        "heldout_window_shape_only": ho_shape,
        "capacity": {
            "median_trailing_daily_volume_of_design_picks_usd": med_pick_vol_design,
            "book_size_at_10pct_of_one_days_volume_usd":
                med_pick_vol_design * 0.10 * PRIMARY.top_n,
            "T21_measured_top20_depth_usd": 52862,
            "note": "The rule is dead at any book size where per-name notional exceeds measured "
                    "depth. Reported whatever the statistical verdict.",
        },
        "verdict": verdict,
        "gates_failed": failed,
    }
    OUT.write_text(json.dumps(out, indent=1, sort_keys=False, default=str))
    print(json.dumps({k: out[k] for k in ("verdict", "gates_failed")}, indent=1))
    print(json.dumps(out["mde_context"], indent=1, default=str))
    print(json.dumps(out["gates"]["G1_portfolio_power_BINDING"], indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
