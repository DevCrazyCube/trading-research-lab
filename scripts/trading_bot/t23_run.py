#!/usr/bin/env python3
"""T23 RUN DRIVER. Design window, then the held-out window ONCE. Frozen with the rule.

USAGE
    python3 scripts/trading_bot/t23_run.py design
    python3 scripts/trading_bot/t23_run.py heldout      # spends the held-out window
    python3 scripts/trading_bot/t23_run.py diagnostics

The held-out command refuses to run unless the census verdict on disk is POWERED and unless the
pre-registration's own sha256 matches what was frozen. That refusal is the whole point of the
freeze-then-test protocol: the window is spent once, by a rule nobody may edit afterwards.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import random
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from trading_bot import stats as S  # noqa: E402
from trading_bot import t23_carry as R  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
TB = ROOT / "research" / "trading_bot"
CENSUS = TB / "T23_POWER_CENSUS.json"
PREREG = TB / "T23_PREREGISTRATION.md"
PREREG_SHA = TB / "T23_PREREGISTRATION.sha256"
DESIGN_OUT = TB / "T23_DESIGN_RESULT.json"
HELDOUT_OUT = TB / "T23_HELDOUT_RESULT.json"

DESIGN = ("2020-01", "2022-12")
HELDOUT = ("2023-01", "2026-07")
HELDOUT_CLEAN = ("2023-01", "2024-09")

# ---- the DECLARED trial grid. 12 trials. Frozen in T23_PREREGISTRATION.md. -------------------
TOP_NS = (3, 5, 10, 20)
THRESHOLDS = (5_000_000, 20_000_000, 50_000_000)
DECLARED_TRIALS = len(TOP_NS) * len(THRESHOLDS)
PRIMARY_KEY = "liq20m_top3"

PERM_DRAWS = 10_000
PERM_SEED = 20260819

VENUE_TAIL_BAR_PP = R.VENUE_TAIL_BAR_PP
ACCOUNT_USD = 100_000.0
CAPACITY_FRACTION_OF_DAILY_VOLUME = 0.10


def grid() -> list[R.Config]:
    out = []
    for th in THRESHOLDS:
        for n in TOP_NS:
            out.append(R.Config(top_n=n, threshold_usd=th,
                                name=f"liq{int(th/1e6)}m_top{n}"))
    return out


def months_between(a: str, b: str) -> list[str]:
    out, cur = [], a
    while cur <= b:
        out.append(cur)
        cur = R.ym_add(cur, 1)
    return out


# ---------------------------------------------------------------------------
# permutation nulls
# ---------------------------------------------------------------------------

def _excess_ann(recs) -> float:
    live = [r for r in recs if not r["skipped"]]
    return statistics.fmean([r["excess"] for r in live]) * 12 * 100 if live else float("nan")


def permutation(panel: R.Panel, cfg: R.Config, months: list[str], *, universe: str,
                observed: float, draws: int = PERM_DRAWS, seed: int = PERM_SEED) -> dict:
    """`universe='screened'` draws N at random from the point-in-time SCREENED set -- the hostile
    null, which asks whether the FUNDING RANKING adds anything at all.
    `universe='full'` draws from the whole point-in-time eligible set with no liquidity screen --
    the joint null, which asks whether SCREEN+RANK together beat blind exposure.
    """
    rng = random.Random(seed)
    pool_by_month = {}
    for ym in months:
        screened = R.screen_month(panel, ym, cfg.threshold_usd)
        if universe == "screened":
            pool_by_month[ym] = screened
        else:
            pool_by_month[ym] = R.screen_month(panel, ym, 0.0)
    panel_last = panel.months[-1]
    stat = []
    for _ in range(draws):
        ex = []
        held: set[str] = set()
        for ym in months:
            pool = pool_by_month[ym]
            if len(pool) < 1:
                held = set()
                continue
            picks = rng.sample(pool, min(cfg.top_n, len(pool)))
            per = [R.month_return(panel, s, ym, panel_last) for s in picks]
            w = 1.0 / len(picks)
            gross = sum(p["gross"] for p in per) * w
            tail = sum(p["tail"] for p in per) * w
            new = set(picks)
            turnover = len(new - held) / len(new) if held else 1.0
            cost = turnover * R.ROUND_TRIP_BP / 10_000.0
            net = (gross - tail - cost) / R.CAPITAL_MULTIPLIER
            ex.append(net - panel.tbill_month_return(ym))
            held = new
        stat.append(statistics.fmean(ex) * 12 * 100 if ex else 0.0)
    ge = sum(1 for v in stat if v >= observed)
    stat_sorted = sorted(stat)
    return {
        "null_universe": universe, "draws": draws, "seed": seed,
        "observed_excess_ann_pp": observed,
        "null_mean_pp": statistics.fmean(stat),
        "null_sd_pp": statistics.stdev(stat),
        "null_p05_pp": stat_sorted[int(0.05 * draws)],
        "null_p50_pp": stat_sorted[int(0.50 * draws)],
        "null_p95_pp": stat_sorted[int(0.95 * draws)],
        "p_value": (ge + 1) / (draws + 1),
    }


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def _run_grid(panel: R.Panel, months: list[str]) -> dict:
    out = {}
    for cfg in grid():
        recs = R.run_book(panel, cfg, months)
        out[cfg.name] = {"config": cfg.as_dict(), "summary": R.summarise(recs),
                         "monthly": [{k: v for k, v in r.items() if k != "picks"} for r in recs],
                         "picks": {r["month"]: r.get("picks", []) for r in recs}}
    return out


def cmd_design(_args=None) -> int:
    panel = R.Panel().load()
    months = months_between(*DESIGN)
    res = _run_grid(panel, months)
    controls = {}
    for cfg in (R.Config(top_n=1, threshold_usd=0.0, name="btc_only", mode="btc"),
                R.Config(top_n=0, threshold_usd=20_000_000, name="all_screened_ew", mode="all"),
                R.Config(top_n=0, threshold_usd=0.0, name="all_unscreened_ew", mode="all")):
        recs = R.run_book(panel, cfg, months)
        controls[cfg.name] = {"config": cfg.as_dict(), "summary": R.summarise(recs)}
    trial_sharpes = [res[k]["summary"]["excess_sharpe_ann"] / (12 ** 0.5) for k in res]
    out = {
        "document": "T23_DESIGN_RESULT",
        "window": DESIGN,
        "declared_trials": DECLARED_TRIALS,
        "trials": res,
        "controls": controls,
        "trial_sharpe_variance_per_month": S.sharpe_variance_from_trials(trial_sharpes),
        "primary": PRIMARY_KEY,
    }
    DESIGN_OUT.write_text(json.dumps(out, indent=1, default=str))
    print(f"design window {DESIGN[0]}..{DESIGN[1]}")
    for k, v in res.items():
        s = v["summary"]
        print(f"  {k:16s} n={s['n_months']:3d} gross={s['gross_ann_pct']:+8.2f} "
              f"net={s['net_on_capital_ann_pct']:+8.2f} rf={s['rf_ann_pct']:+6.2f} "
              f"excess={s['excess_ann_pct']:+8.2f} sd={s['excess_sd_ann_pct']:6.2f} "
              f"t={s['t_stat']:+6.2f}")
    for k, v in controls.items():
        s = v["summary"]
        print(f"  [ctl] {k:14s} n={s['n_months']:3d} excess={s['excess_ann_pct']:+8.2f} "
              f"sd={s['excess_sd_ann_pct']:6.2f}")
    return 0


def cmd_heldout(_args=None) -> int:
    census = json.loads(CENSUS.read_text())
    if census["verdict"] != "POWERED":
        raise SystemExit(
            f"REFUSING to spend the held-out window: census verdict is {census['verdict']}. "
            "T23_POWER_GATE.md G1 says the window is NOT spent when the census fails.")
    if PREREG_SHA.exists():
        want = PREREG_SHA.read_text().split()[0]
        got = hashlib.sha256(PREREG.read_bytes()).hexdigest()
        if want != got:
            raise SystemExit(f"PRE-REGISTRATION CHANGED: {got} != {want}")

    design = json.loads(DESIGN_OUT.read_text())
    panel = R.Panel().load()
    months = months_between(*HELDOUT)
    res = _run_grid(panel, months)

    primary_cfg = [c for c in grid() if c.name == PRIMARY_KEY][0]
    prim = res[PRIMARY_KEY]
    live = [r for r in prim["monthly"] if not r["skipped"]]
    ex_monthly = [r["excess"] for r in live]
    observed = prim["summary"]["excess_ann_pct"]

    dsr = S.deflated_sharpe(ex_monthly, trials=DECLARED_TRIALS,
                            sharpe_variance=design["trial_sharpe_variance_per_month"])
    p_screened = permutation(panel, primary_cfg, months, universe="screened", observed=observed)
    p_full = permutation(panel, primary_cfg, months, universe="full", observed=observed)

    med_vol = prim["summary"]["median_pick_volume_usd"]
    capacity_usd = med_vol * CAPACITY_FRACTION_OF_DAILY_VOLUME * primary_cfg.top_n

    clean_months = set(months_between(*HELDOUT_CLEAN))
    clean = [r for r in live if r["month"] in clean_months]
    clean_ex = [r["excess"] for r in clean]

    controls = {}
    for cfg in (R.Config(top_n=1, threshold_usd=0.0, name="btc_only", mode="btc"),
                R.Config(top_n=0, threshold_usd=20_000_000, name="all_screened_ew", mode="all"),
                R.Config(top_n=0, threshold_usd=0.0, name="all_unscreened_ew", mode="all")):
        recs = R.run_book(panel, cfg, months)
        controls[cfg.name] = {"config": cfg.as_dict(), "summary": R.summarise(recs)}

    gates = {
        "H1_excess_over_byyear_tbills_positive": {
            "pass": observed > 0, "value_pp": observed, "threshold_pp": 0.0},
        "H2_clears_venue_tail_bar": {
            "pass": observed > VENUE_TAIL_BAR_PP, "value_pp": observed,
            "threshold_pp": VENUE_TAIL_BAR_PP,
            "note": "THE DECISION GATE. Below this the mechanism is dead regardless of "
                    "significance -- T23_POWER_GATE.md §4."},
        "H3_dsr": {"pass": dsr["dsr"] >= 0.95, "value": dsr["dsr"], "threshold": 0.95,
                   "detail": dsr},
        "H4_permutation_vs_full_universe": {
            "pass": p_full["p_value"] <= 0.05, "value": p_full["p_value"], "threshold": 0.05,
            "detail": p_full},
        "H4b_permutation_vs_screened_universe_DIAGNOSTIC": {
            "pass": p_screened["p_value"] <= 0.05, "value": p_screened["p_value"],
            "threshold": 0.05, "detail": p_screened,
            "declared_interpretation":
                "If H4b FAILS while H4 passes, the edge lives in the LIQUIDITY SCREEN and not in "
                "the funding ranking. Stated before the number existed."},
        "H5_capacity": {
            "pass": capacity_usd >= ACCOUNT_USD, "value_usd": capacity_usd,
            "threshold_usd": ACCOUNT_USD,
            "median_pick_daily_volume_usd": med_vol,
            "fraction_of_daily_volume": CAPACITY_FRACTION_OF_DAILY_VOLUME},
    }
    binding = ["H1_excess_over_byyear_tbills_positive", "H2_clears_venue_tail_bar", "H3_dsr",
               "H4_permutation_vs_full_universe", "H5_capacity"]
    failed = [k for k in binding if not gates[k]["pass"]]
    verdict = "DEAD" if failed else "SURVIVES"

    out = {
        "document": "T23_HELDOUT_RESULT",
        "window": HELDOUT,
        "window_burn_status":
            "PARTIALLY BURNED: T21 searched 2024-10..2026-07, 22 of these 43 months. "
            "The 2023-01..2024-09 sub-window is fully unburned and is reported separately.",
        "primary": PRIMARY_KEY,
        "primary_summary": prim["summary"],
        "primary_monthly": prim["monthly"],
        "primary_picks": prim["picks"],
        "heldout_clean_subwindow": {
            "window": HELDOUT_CLEAN, "n_months": len(clean),
            "excess_ann_pp": statistics.fmean(clean_ex) * 12 * 100 if clean_ex else None,
            "note": "21 months resolves nothing on its own; reported because it is the only part "
                    "of the held-out window T21's parameter search never saw."},
        "all_declared_trials": {k: v["summary"] for k, v in res.items()},
        "controls": controls,
        "gates": gates,
        "gates_failed": failed,
        "verdict": verdict,
    }
    HELDOUT_OUT.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({"verdict": verdict, "gates_failed": failed}, indent=1))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "detail"}
                      for k, v in gates.items()}, indent=1, default=str))
    return 0


def cmd_diagnostics(_args=None) -> int:
    panel = R.Panel().load()
    print(f"symbols with funding: {len(panel.funding_month)}")
    print(f"usdt symbols: {sum(1 for s in panel.funding_month if s.endswith('USDT'))}")
    print(f"months: {panel.months[0]} .. {panel.months[-1]} ({len(panel.months)})")
    for ym in ("2020-06", "2021-06", "2022-06", "2023-06", "2024-06", "2025-06", "2026-06"):
        for th in (5e6, 20e6, 50e6):
            print(f"  {ym} th={th/1e6:.0f}M eligible={len(R.screen_month(panel, ym, th))}")
    return 0


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    return {"design": cmd_design, "heldout": cmd_heldout,
            "diagnostics": cmd_diagnostics}[argv[0]]()


if __name__ == "__main__":
    sys.exit(main())
