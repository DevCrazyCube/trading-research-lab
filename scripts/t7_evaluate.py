#!/usr/bin/env python3
"""T7 -- design phase, freeze, and held-out test. Two commands, in that order, never merged.

    python3 scripts/t7_evaluate.py design   # 2016-2021 only. Writes T7_FROZEN_CONFIG.json.
    python3 scripts/t7_evaluate.py test     # refuses unless T7_FROZEN_CONFIG.json exists.

The separation is the point: `test` reads the frozen file and cannot choose anything.

Rule: research/trading_bot/T7_PREREGISTRATION.md
      sha256 7bd072a7565a27b39d83a35afa659fb4c80bdf700dcb84e1100ea0e1816c7cdd
"""

from __future__ import annotations

import datetime
import gzip
import hashlib
import json
import math
import pathlib
import sys
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.t3_pressure_reversal as t3                                       # noqa: E402
import scripts.t7_dividend_dropoff as t7                                        # noqa: E402
from scripts.trading_bot.costs import (CostComponent, CostModel,                # noqa: E402
                                       SlippageProvenance, measured_borrow_annual)
from scripts.trading_bot.stats import (annualised_sharpe, cagr, deflated_sharpe,  # noqa: E402
                                       max_drawdown, moments, permutation_test,
                                       sharpe_variance_from_trials)

OUT = ROOT / "research" / "trading_bot"
FROZEN = OUT / "T7_FROZEN_CONFIG.json"
PREREG_SHA = t7.PREREG_SHA

# Pre-registration section 7: the ONLY eight configurations that will ever be run.
YIELD_MINS = (0.0, 0.005)
UNIVERSES = (500, 300)
SPECIALS = (True, False)          # include special dividends / exclude them

# Pre-registration section 6. T3's own first-party measurement on this exact universe.
H_DESIGN_BP = 1.13
H_TEST_BP = 1.43

SEC31_FRACTION = Fraction(278, 10 ** 7)     # $27.80 per $1,000,000 of SALE notional = 0.278 bp
TAF_MICROS_PER_SHARE = 166                  # $0.000166 per share


# ---------------------------------------------------------------------------
# the cost model -- T6-corrected, PER SIDE, both sides named explicitly
# ---------------------------------------------------------------------------

_AUCTION_SOURCE = (
    "The {leg} leg is an official single-price CLOSING AUCTION print (condition code 6): every "
    "participant clears at one price, so there is no bid-ask to cross. T1 section 2c verified "
    "type=market,tif=cls is accepted by the broker. THIS ZERO IS DECLARED, NOT INHERITED FROM "
    "THE OTHER SIDE -- T6's correction was that an unmeasured exit must never take the entry's "
    "number, and here each side states the same venue fact for itself. It is legitimate ONLY if "
    "the order actually fills AT the print, which is M0 and is UNPERFORMED; the stress ladder "
    "charges a real measured half-spread on this leg at 0.5h / h / 2h / 4h for exactly that "
    "reason."
)


def cost_model(half_spread_bp) -> CostModel:
    """The model at one rung of the ladder. `half_spread_bp` is charged on EVERY one of the four
    legs (buy stock, short SPY, sell stock, cover SPY). Rung 0 is the auction rail as modelled."""
    hs = Fraction(str(half_spread_bp))
    prov = (SlippageProvenance.EXCHANGE_MECHANISM_UNVERIFIED_FILL if hs == 0
            else SlippageProvenance.STRESS_LADDER)

    def half(leg):
        src = (_AUCTION_SOURCE.format(leg=leg) if hs == 0 else
               f"STRESS RUNG, not a measurement of an auction: {float(hs)} bp of half-spread "
               f"charged on the {leg} leg as a multiple of T3's first-party measured median "
               f"quoted half-spread in this exact top-500-ADV universe (1.13 bp 2016-2021, "
               f"1.43 bp 2022-2026, ~20,000 symbol-days per period, T3_HELDOUT_RESULT.json). "
               f"This rung prices M0 being wrong -- i.e. the MOC order not filling at the print.")
        return CostComponent(f"{leg}_half_spread", hs, "bp of notional", prov, src)

    def extra(leg):
        return CostComponent(
            f"{leg}_extra_slippage", Fraction(0), "bp of notional",
            SlippageProvenance.STRESS_LADDER,
            "NOT MEASURED for this population. Zero here makes the model a stated LOWER BOUND on "
            f"{leg} impact, never a claim that impact is absent. At $100k against single-stock "
            "closing auctions clearing $28-130M (T1 2e) the omission is tolerable; the ladder "
            "sweeps it.")

    return CostModel(
        entry_half_spread=half("entry"),
        entry_extra_slippage=extra("entry"),
        exit_half_spread=half("exit"),
        exit_extra_slippage=extra("exit"),
        commission_per_share=CostComponent(
            "commission_per_share", Fraction(TAF_MICROS_PER_SHARE), "micro-dollars per share",
            SlippageProvenance.BROKER_SCHEDULE,
            "FINRA Trading Activity Fee, $0.000166 per share. Broker commission itself is $0 "
            "(Alpaca and every zero-commission US retail broker). TAF is legally a SALE-side fee "
            "only; this field is side-agnostic, so charging it on every share traded OVERCHARGES "
            "by ~2x. That is the conservative direction and it is stated rather than optimised "
            "away. The SEC Section 31 fee is ad valorem and sale-side and cannot be expressed in "
            "a per-share field, so it is charged separately in the runner at $27.80 per $1M -- "
            "the TOP of the 2016-2026 range -- on both sale legs, in both periods."),
        borrow_annual=measured_borrow_annual("etb_general_collateral"),
    )


# ---------------------------------------------------------------------------
# the strategy -- one observation per event-day
# ---------------------------------------------------------------------------

def load_panel():
    with gzip.open(t7.CACHE / "panel.json.gz", "rt") as fh:
        blob = json.load(fh)
    if blob.get("preregistration_sha256") != PREREG_SHA:
        raise SystemExit("panel was not built under the frozen pre-registration; refusing")
    return blob["panel"], blob["stats"]


_UNI = {}


def universe_sets(top_n):
    if top_n not in _UNI:
        _UNI[top_n] = {m: set(v) for m, v in t3.build_universe(top_n).items()}
    return _UNI[top_n]


def _gap_days(cum, ex):
    return max(1, (datetime.date.fromisoformat(ex) - datetime.date.fromisoformat(cum)).days)


def run_config(panel, *, yield_min, top_n, include_special, half_spread_bp,
               charge_regulatory=True, charge_borrow=True, day_filter=None):
    """Returns a dict of aligned series. One observation per surviving event-day.

    gross(t) = 0.5 * mean_i r_total(i,t) - 0.5 * r_spy(t)      (dollar neutral, 100% gross)
    """
    model = cost_model(half_spread_bp)
    entry_frac = model.entry_spread_and_slippage_fraction()
    exit_frac = model.exit_spread_and_slippage_fraction()
    borrow = model.borrow_annual.value
    uni = universe_sets(top_n)

    dates, gross, net, control, dropoff_num, dropoff_den, counts, yields = \
        [], [], [], [], [], [], [], []
    for day in sorted(panel):
        if day_filter and not day_filter(day):
            continue
        rec = panel[day]
        cum = rec["cum"]
        allowed = uni.get(cum[:7], set()) & uni.get(day[:7], set())
        evs = [e for e in rec["events"]
               if e[0] in allowed
               and e[3] / e[1] >= yield_min
               and (include_special or not e[4])]
        if not evs:
            continue
        r_spy = rec["spy"]
        k = len(evs)
        r_stock = sum((e[2] - e[1] + e[3]) / e[1] for e in evs) / k
        g = 0.5 * r_stock - 0.5 * r_spy

        cost = 0.0
        # spread/slippage: 1.0 of notional opened (0.5 stock + 0.5 SPY), 1.0 closed
        cost += float(entry_frac) * 1.0 + float(exit_frac) * 1.0
        if charge_regulatory:
            # SEC Section 31 on the two SALE legs: stock sold at the ex-close, SPY sold short
            # at the cum-close. 0.5 notional each.
            cost += float(SEC31_FRACTION) * 1.0
            # FINRA TAF on every share traded (see cost_model docstring: side-agnostic field,
            # so this over-charges by ~2x, which is the conservative direction).
            inv_buy = sum(1.0 / e[1] for e in evs) / k
            inv_sell = sum(1.0 / e[2] for e in evs) / k
            taf = TAF_MICROS_PER_SHARE / 1e6
            cost += taf * 0.5 * (inv_buy + inv_sell)          # stock buy + stock sell
            cost += taf * 1.0 / rec["spy_price"]              # SPY short + SPY cover
        if charge_borrow:
            cost += 0.5 * float(borrow) * _gap_days(cum, day) / 365.25

        ctrl = [c for c in rec["control"] if c[0] in allowed]
        ctrl_r = (sum(c[1] for c in ctrl) / len(ctrl) - r_spy) if ctrl else 0.0

        dates.append(day)
        gross.append(g)
        net.append(g - cost)
        control.append(ctrl_r)
        counts.append(k)
        yields.append(sum(e[3] / e[1] for e in evs) / k)
        # drop-off ratio, aggregated in DOLLARS across every event: sum(market-adjusted price
        # drop) / sum(dividend). The event-weighted mean of a per-event ratio is dominated by
        # tiny-dividend names, so the dollar aggregate is the honest headline.
        dropoff_num.append(sum(e[1] * (1.0 + r_spy) - e[2] for e in evs))
        dropoff_den.append(sum(e[3] for e in evs))

    return {"dates": dates, "gross": gross, "net": net, "control": control,
            "counts": counts, "yields": yields,
            "dropoff_num": dropoff_num, "dropoff_den": dropoff_den,
            "cost_model": model.to_report()}


def series_report(dates, rets, label, periods_per_year):
    m = moments(rets)
    n = m["n"]
    sr = m["mean"] / m["sd"]
    curve = [1.0]
    for r in rets:
        curve.append(curve[-1] * (1.0 + r))
    ns = [int(datetime.datetime.fromisoformat(d).timestamp()) * 1_000_000_000 for d in dates]
    return {
        "label": label,
        "n_event_days": n,
        "mean_per_day_bp": m["mean"] * 1e4,
        "sd_per_day_bp": m["sd"] * 1e4,
        "t_stat": sr * math.sqrt(n),
        "sharpe_per_observation": sr,
        "periods_per_year_used": periods_per_year,
        "annualised_sharpe": annualised_sharpe(rets, periods_per_year),
        "annualised_return_pct": m["mean"] * periods_per_year * 100,
        "cagr_pct": cagr(curve, ns[0], ns[-1] + 86_400 * 1_000_000_000) * 100,
        "max_drawdown_pct": max_drawdown(curve)["max_drawdown"] * 100,
        "skew": m["skew"],
        "kurtosis_non_excess": m["kurtosis"],
        "final_equity": curve[-1],
    }


def periods_per_year_of(dates):
    """Observations per year, COMPUTED from the panel. The book is flat on days with no ex-date,
    so annualising at 252 would claim more compounding opportunities than the strategy has."""
    a = datetime.date.fromisoformat(dates[0])
    b = datetime.date.fromisoformat(dates[-1])
    years = (b - a).days / 365.25
    return max(1, round(len(dates) / years))


# ---------------------------------------------------------------------------
# the pre-registered cross-sectional label permutation
# ---------------------------------------------------------------------------

def label_permutation(panel, cfg, *, day_filter, trials=10_000, seed=20260817):
    """Replace the day's k real ex-dividend names with k names drawn without replacement from the
    SAME day's non-ex-dividend universe members, and recompute the portfolio return.

    The pseudo-events have no dividend to add back -- which is precisely H0: under a drop-off
    ratio of 1, an ex-dividend stock's TOTAL return is indistinguishable from an ordinary
    stock's price return. Every permutation trades the same days, holds the same number of
    names, and faces the same market move; only WHICH stocks are labelled changes. The -0.5*r_spy
    hedge term is identical in the observed and permuted statistics and therefore cancels.
    """
    import numpy as np

    uni = universe_sets(cfg["top_n"])
    rng = np.random.default_rng(seed)
    obs_terms, null = [], np.zeros(trials)
    n_days = 0
    for day in sorted(panel):
        if not day_filter(day):
            continue
        rec = panel[day]
        cum = rec["cum"]
        allowed = uni.get(cum[:7], set()) & uni.get(day[:7], set())
        evs = [e for e in rec["events"]
               if e[0] in allowed
               and e[3] / e[1] >= cfg["yield_min"]
               and (cfg["include_special"] or not e[4])]
        if not evs:
            continue
        pool = np.asarray([c[1] for c in rec["control"] if c[0] in allowed], dtype=float)
        k = len(evs)
        if pool.size < k:
            raise SystemExit(f"{day}: control pool {pool.size} smaller than {k} events; the "
                             "permutation cannot draw a same-size pseudo-basket. Refusing.")
        obs_terms.append(0.5 * sum((e[2] - e[1] + e[3]) / e[1] for e in evs) / k
                         - 0.5 * rec["spy"])
        pick = np.argpartition(rng.random((trials, pool.size)), k - 1, axis=1)[:, :k]
        null += 0.5 * pool[pick].mean(axis=1) - 0.5 * rec["spy"]
        n_days += 1
    null /= n_days
    obs = float(np.mean(obs_terms))
    ge = int((null >= obs).sum())
    return {"observed_mean_bp": obs * 1e4, "trials": trials, "seed": seed, "n_days": n_days,
            "p_right_tail": (ge + 1) / (trials + 1),
            "null_mean_bp": float(null.mean()) * 1e4,
            "null_sd_bp": float(null.std(ddof=1)) * 1e4,
            "null_p95_bp": float(np.quantile(null, 0.95)) * 1e4}


# ---------------------------------------------------------------------------
# design / test
# ---------------------------------------------------------------------------

def _dropoff(res):
    num, den = sum(res["dropoff_num"]), sum(res["dropoff_den"])
    return {"dollar_weighted_dropoff_ratio": num / den,
            "sum_market_adjusted_drop": num, "sum_dividends": den,
            "n_events": sum(res["counts"]),
            "mean_yield_pct": sum(y * c for y, c in zip(res["yields"], res["counts"]))
                              / sum(res["counts"]) * 100}


def design():
    panel, pstats = load_panel()
    keep = lambda d: d <= t3.DESIGN_END                                        # noqa: E731
    days = [d for d in sorted(panel) if keep(d)]
    print(f"design event-days available: {len(days)}", flush=True)
    ppy = periods_per_year_of(days)
    print(f"periods per year, computed: {ppy}", flush=True)

    grid, results = [], []
    for ym in YIELD_MINS:
        for top in UNIVERSES:
            for sp in SPECIALS:
                res = run_config(panel, yield_min=ym, top_n=top, include_special=sp,
                                 half_spread_bp=0, day_filter=keep)
                rep = series_report(res["dates"], res["net"],
                                    f"y{ym}_top{top}_special{sp}", ppy)
                rep.update({"yield_min": ym, "top_n": top, "include_special": sp,
                            "gross_mean_per_day_bp": moments(res["gross"])["mean"] * 1e4,
                            "control_mean_per_day_bp": moments(res["control"])["mean"] * 1e4,
                            "mean_events_per_day": sum(res["counts"]) / len(res["counts"]),
                            "dropoff": _dropoff(res)})
                results.append(rep)
                grid.append(rep["sharpe_per_observation"])
                print(f"  yield>={ym:<6} top={top} special={str(sp):<5}: "
                      f"net {rep['mean_per_day_bp']:+.3f} bp/day t={rep['t_stat']:+.2f} "
                      f"SR={rep['annualised_sharpe']:+.2f} n={rep['n_event_days']} "
                      f"dropoff={rep['dropoff']['dollar_weighted_dropoff_ratio']:.4f}", flush=True)

    best = max(results, key=lambda r: r["annualised_sharpe"])
    frozen = {
        "preregistration_sha256": PREREG_SHA,
        "design_period": [t3.START, t3.DESIGN_END],
        "trials_declared": 8,
        "trial_sharpes_per_observation": grid,
        "sharpe_variance_across_trials": sharpe_variance_from_trials(grid),
        "frozen_config": {"yield_min": best["yield_min"], "top_n": best["top_n"],
                          "include_special": best["include_special"]},
        "design_periods_per_year": ppy,
        "design_results": results,
        "panel_stats": pstats,
        "note": ("Frozen by highest design-period NET annualised Sharpe at the primary cost rung, "
                 "as pre-registered. The held-out period 2022-01-03..2026-08-14 has not been "
                 "evaluated at the time this file was written."),
    }
    FROZEN.write_text(json.dumps(frozen, indent=2))
    print("\nFROZEN:", json.dumps(frozen["frozen_config"]), flush=True)
    print("sha256:", hashlib.sha256(FROZEN.read_bytes()).hexdigest(), flush=True)


def test():
    if not FROZEN.exists():
        raise SystemExit("T7_FROZEN_CONFIG.json is absent. The design phase must run and freeze a "
                         "configuration BEFORE the held-out period is touched. Refusing.")
    frozen = json.loads(FROZEN.read_text())
    cfg = frozen["frozen_config"]
    print("frozen config:", cfg, " file sha256:",
          hashlib.sha256(FROZEN.read_bytes()).hexdigest(), flush=True)

    panel, pstats = load_panel()
    keep = lambda d: d >= t3.TEST_START                                        # noqa: E731
    days = [d for d in sorted(panel) if keep(d)]
    print(f"held-out event-days available: {len(days)}", flush=True)
    ppy = periods_per_year_of(days)

    def run(h, **kw):
        return run_config(panel, yield_min=cfg["yield_min"], top_n=cfg["top_n"],
                          include_special=cfg["include_special"], half_spread_bp=h,
                          day_filter=keep, **kw)

    primary = run(0)
    out = {
        "preregistration_sha256": PREREG_SHA,
        "frozen_config": cfg,
        "frozen_file_sha256": hashlib.sha256(FROZEN.read_bytes()).hexdigest(),
        "test_period": [t3.TEST_START, t3.END],
        "periods_per_year_used": ppy,
        "mean_events_per_day": sum(primary["counts"]) / len(primary["counts"]),
        "cost_model_primary_rung": primary["cost_model"],
        "sec31_bp_of_sale_notional": float(SEC31_FRACTION) * 1e4,
        "net": series_report(primary["dates"], primary["net"],
                             "net, auction rail + regulatory + borrow", ppy),
        "gross_zero_cost": series_report(primary["dates"], primary["gross"],
                                         "gross, zero cost (B19P diagnostic)", ppy),
        "equal_weight_non_exdiv_control": series_report(
            primary["dates"], primary["control"],
            "equal-weight NON-ex-dividend universe, market-adjusted, same days", ppy),
        "dropoff_heldout": _dropoff(primary),
    }

    # ---- stress ladder: h charged on EVERY one of the four legs
    h = H_TEST_BP
    ladder = {}
    for name, kw in {
        "zero cost (B19P diagnostic: no spread, no reg fee, no borrow)":
            dict(h=0, charge_regulatory=False, charge_borrow=False),
        "PRIMARY: auction rail, spread 0, + SEC31 + TAF + borrow": dict(h=0),
        "0.5h per leg (h = 1.43 bp measured, T3)": dict(h=0.5 * h),
        "h per leg -- M0 wrong, MOC fills at the touch": dict(h=h),
        "2h per leg": dict(h=2 * h),
        "4h per leg": dict(h=4 * h),
    }.items():
        hh = kw.pop("h")
        r = run(hh, **kw)
        mm = moments(r["net"])
        ladder[name] = {"mean_per_day_bp": mm["mean"] * 1e4,
                        "t_stat": mm["mean"] / mm["sd"] * math.sqrt(mm["n"]),
                        "annualised_sharpe": annualised_sharpe(r["net"], ppy),
                        "annualised_return_pct": mm["mean"] * ppy * 100}
    out["stress_ladder"] = ladder

    # ---- DSR. The book IS the paired difference: it is long the ex-dividend basket and short
    # SPY on every observation, so the common market move is already cancelled inside the series.
    sv = frozen["sharpe_variance_across_trials"]
    out["dsr_trials_8"] = deflated_sharpe(primary["net"], trials=8, sharpe_variance=sv)
    out["dsr_trials_24_sensitivity"] = deflated_sharpe(primary["net"], trials=24,
                                                       sharpe_variance=sv)

    # ---- the pre-registered cross-sectional label permutation
    out["label_permutation"] = label_permutation(panel, cfg, day_filter=keep)

    # ---- wiring check only: constant exposure permutes to itself, p MUST be 1.0
    out["exposure_timing_permutation_WIRING_CHECK_ONLY"] = permutation_test(
        [1.0] * len(primary["net"]), primary["net"], trials=10_000, seed=20260817)

    mg = moments(primary["gross"])
    out["gross_t_stat"] = mg["mean"] / mg["sd"] * math.sqrt(mg["n"])

    # ---- year by year, so no single year can be carrying it unnoticed
    by_year = {}
    for d, r in zip(primary["dates"], primary["net"]):
        by_year.setdefault(d[:4], []).append(r)
    out["net_by_year"] = {
        y: {"n": len(v), "mean_bp": moments(v)["mean"] * 1e4,
            "t": moments(v)["mean"] / moments(v)["sd"] * math.sqrt(len(v))}
        for y, v in sorted(by_year.items())}

    verdict = []
    if out["net"]["mean_per_day_bp"] <= 0:
        verdict.append("KILL 1: net mean per event-day <= 0")
    if out["label_permutation"]["p_right_tail"] >= 0.05:
        verdict.append("KILL 2: label-permutation p >= 0.05")
    if out["dsr_trials_8"]["dsr"] < 0.95:
        verdict.append("KILL 3: DSR < 0.95 at trials=8")
    out["kill_conditions_triggered"] = verdict
    out["verdict"] = "DEAD" if verdict else "SURVIVES"

    (OUT / "T7_HELDOUT_RESULT.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items()
                      if k not in ("stress_ladder", "cost_model_primary_rung")}, indent=2)[:5000])
    print("\nSTRESS LADDER:", json.dumps(ladder, indent=2), flush=True)
    print("\nVERDICT:", out["verdict"], verdict, flush=True)


if __name__ == "__main__":
    {"design": design, "test": test}[sys.argv[1]]()
