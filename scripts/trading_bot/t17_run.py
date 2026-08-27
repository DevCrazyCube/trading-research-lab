#!/usr/bin/env python3
"""T17 RUN DRIVER. Simulates the frozen ORB rule and reports. Hashed with the rule.

USAGE
    python3 scripts/trading_bot/t17_run.py census
    python3 scripts/trading_bot/t17_run.py design
    python3 scripts/trading_bot/t17_run.py heldout        # ONCE. Guarded by a sentinel file.

The held-out stage refuses to run a second time: it writes `T17_HELDOUT_RESULT.json` and
then refuses while that file exists, because "run it again with one thing changed" is how a
held-out window stops being held out.

WHAT IS CHARGED
    MEAN mode      -- the T6 per-side model (`costs.b22b_measured_costs`) as a fraction of
                      notional on each leg: entry 1.5452 bp measured + exit 2.5 bp half-
                      spread + exit 1.5452 bp adverse proxy = 5.59 bp round trip.
    EMPIRICAL mode -- a per-trade draw from B22B's measured entry-slippage distribution in
                      basis points of R, applied to the fill PRICE on both legs (the exit
                      draw is the same `ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG`), plus the exit
                      half-spread on notional. This is the mode that carries the fat tail.
    ZERO mode      -- DIAGNOSTIC ONLY, per B19P. If a strategy loses here, no execution
                      improvement can rescue it. Never a trading assumption.

THE OUTCOME MATRIX, AND WHY BOTH DIRECTIONS ARE SIMULATED
---------------------------------------------------------
Every selected stock-day is simulated LONG and SHORT and both results are cached. The live
strategy uses the direction the opening candle assigned; the permutation null uses a coin.
Precomputing both is what makes 2,000 permutations affordable, and -- more importantly --
it makes the permutation *exact* rather than a re-simulation with its own new randomness:
the only thing that differs between the observed run and a permuted one is the direction.

Slippage draws are keyed on (day, rank, direction), not on draw order, for the same reason:
a permutation must not silently redraw its own friction.

BORROW is not charged: every position opens and closes inside one session and US equity
borrow accrues on overnight balances. The constraint the short leg really faces is
availability, not rate -- reported separately, never priced in silently.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from trading_bot import costs as COSTS  # noqa: E402
from trading_bot import frozen as PINNED  # noqa: E402
from trading_bot import stats as STATS  # noqa: E402
from trading_bot import t17_orb as ORB  # noqa: E402

CACHE = ROOT / "research" / "data" / "t17_cache"
OUT = ROOT / "research" / "trading_bot"
START_EQUITY_MICROS = 100_000 * PINNED.MICROS
PERMUTATIONS = 2000
PERM_SEED = 1720260817
SLIP_SEED = 1700000001
DECLARED_TRIALS = 6      # {mean, empirical} x {zero, T6, T6 + $0.0035/share}, declared first


def _lcg(x: int) -> int:
    return (6364136223846793005 * x + 1442695040888963407) & (2 ** 64 - 1)


class KeyedSlippage(ORB.EmpiricalSlippage):
    """The same measured distribution, indexed by a KEY instead of by draw order."""

    def draw_keyed(self, r_micros: int, key: int) -> int:
        h = _lcg(_lcg(self.seed ^ (key * 0x9E3779B97F4A7C15 & (2 ** 64 - 1))))
        return self.values[(h >> 33) % self.n] * r_micros // 10000


# ---------------------------------------------------------------- outcome matrix

def build_outcomes(days, selection, mode, seed=SLIP_SEED,
                   entry_bar_stop_rule="close"):
    """For every selected stock-day, the LONG and the SHORT result, in micro-dollars."""
    slip = KeyedSlippage(seed) if mode == "empirical" else None
    if slip is not None:
        slip.seed = seed
    matrix, census = {}, {"sessions": 0, "no_path_file": 0, "no_path_symbol": 0,
                          "stock_days": 0}
    for di, day in enumerate(days):
        picks = selection.get(day) or []
        if not picks:
            continue
        p = CACHE / "paths" / f"{day}.json"
        if not p.exists():
            census["no_path_file"] += 1
            continue
        raw = json.loads(p.read_text())
        rows = []
        for rank, (relvol, sym, direction, or_high, or_low, atr) in enumerate(picks):
            r_micros = PINNED.r_unit_micros(atr)
            path = raw.get(sym)
            if not path:
                census["no_path_symbol"] += 1
                continue
            bars = [{"o": PINNED.to_micros(b[1]), "h": PINNED.to_micros(b[2]),
                     "l": PINNED.to_micros(b[3]), "c": PINNED.to_micros(b[4])} for b in path]
            both = {}
            for d in ("long", "short"):
                level = or_high if d == "long" else or_low
                if mode == "empirical":
                    key = di * 1_000_003 + rank * 97 + (1 if d == "long" else 2)
                    e = slip.draw_keyed(r_micros, key)
                    x = slip.draw_keyed(r_micros, key + 500_000_003)
                else:
                    e = x = 0
                res = ORB.simulate_stock_day(d, level, r_micros, bars, e, x,
                                             entry_bar_stop_rule)
                res["entry_level"] = level
                both[d] = res
            rows.append({"symbol": sym, "relvol": relvol, "candle": direction,
                         "r_micros": r_micros, "long": both["long"], "short": both["short"]})
            census["stock_days"] += 1
        if rows:
            matrix[day] = rows
            census["sessions"] += 1
    return matrix, census


# ---------------------------------------------------------------- replay

def replay(matrix, days, cost, mode, direction_seed=None, keep_trades=False,
           gross_cap_mode="pro_rata"):
    """Walk the sessions with real compounding equity and integer share counts."""
    equity = START_EQUITY_MICROS
    daily, trades = [], []
    rng = direction_seed
    n_trades = 0
    for day in days:
        rows = matrix.get(day)
        if not rows:
            continue
        sized = []
        for r in rows:
            if rng is not None:
                rng = _lcg(rng)
                d = "long" if (rng >> 33) & 1 else "short"
            else:
                d = r["candle"]
            res = r[d]
            sized.append({"symbol": r["symbol"], "direction": d, "res": res,
                          "entry_level": res["entry_level"], "r_micros": r["r_micros"],
                          "shares": ORB.position_shares(equity, r["r_micros"])})
        taken = ORB.apply_gross_cap(sized, equity, gross_cap_mode)
        pnl = 0
        for item in taken:
            res = item["res"]
            if res["outcome"] == "NO_TRIGGER":
                if keep_trades:
                    trades.append({"day": day, "symbol": item["symbol"],
                                   "outcome": "NO_TRIGGER"})
                continue
            gross = res["pnl_per_share"] * item["shares"]
            # price_micros * shares IS micro-dollars of notional. Dividing by MICROS here
            # would produce whole dollars and undercharge every cost by a factor of 1e6 --
            # caught by a synthetic test before this file was frozen.
            entry_notional = res["entry"] * item["shares"]
            exit_notional = res["exit"] * item["shares"]
            if mode == "empirical":
                charge = int(Fraction(exit_notional) * cost.exit_half_spread.value * COSTS.BP)
            elif mode == "mean":
                charge = int(Fraction(entry_notional)
                             * cost.entry_spread_and_slippage_fraction()
                             + Fraction(exit_notional)
                             * cost.exit_spread_and_slippage_fraction())
            elif mode == "zero":
                charge = 0
            else:
                raise PINNED.Refused(f"unknown cost mode {mode!r}")
            commission = int(Fraction(2 * item["shares"]) * cost.commission_per_share.value)
            net = gross - charge - commission
            pnl += net
            n_trades += 1
            if keep_trades:
                trades.append({"day": day, "symbol": item["symbol"],
                               "direction": item["direction"], "outcome": res["outcome"],
                               "shares": item["shares"], "gross": gross, "charge": charge,
                               "commission": commission, "net": net,
                               "net_r": (net / item["shares"]) / item["r_micros"]
                               if item["shares"] else None,
                               "gross_r": res["pnl_per_share"] / item["r_micros"],
                               "slip_r": res.get("slip_micros", 0) / item["r_micros"],
                               "charge_r": (charge / item["shares"]) / item["r_micros"]
                               if item["shares"] else None})
        ret = pnl / equity
        equity += pnl
        daily.append(ret)
        if equity <= 0:
            break
    return {"daily_returns": daily, "final_equity_micros": equity,
            "n_trades": n_trades, "trades": trades}


# ---------------------------------------------------------------- statistics

def summarise(daily, label):
    m = STATS.moments(daily)
    eq, peak, mdd = 1.0, 1.0, 0.0
    for r in daily:
        eq *= (1.0 + r)
        peak = max(peak, eq)
        mdd = max(mdd, 1.0 - eq / peak)
    years = len(daily) / 252.0
    return {"label": label, "n_days": len(daily), "years": years,
            "mean_daily": m["mean"], "sd_daily": m["sd"],
            "annualised_return": (eq ** (1 / years) - 1) if eq > 0 else -1.0,
            "annualised_vol": m["sd"] * math.sqrt(252),
            "annualised_sharpe": STATS.annualised_sharpe(daily, 252),
            "max_drawdown": mdd, "final_multiple": eq,
            "t_stat": (m["mean"] / m["sd"] * math.sqrt(m["n"])) if m["sd"] > 0 else None,
            "skew": m["skew"], "kurtosis_non_excess": m["kurtosis"]}


def permutation(matrix, days, cost, mode, observed_mean, n=PERMUTATIONS):
    ge, stats = 0, []
    for i in range(n):
        d = replay(matrix, days, cost, mode, direction_seed=PERM_SEED + i * 7919)["daily_returns"]
        mu = sum(d) / len(d) if d else 0.0
        stats.append(mu)
        if mu >= observed_mean:
            ge += 1
    stats.sort()
    return {"permutations": n, "n_ge_observed": ge, "p_value": (ge + 1) / (n + 1),
            "null_mean_daily_p50": stats[n // 2], "null_mean_daily_p95": stats[95 * n // 100],
            "observed_mean_daily": observed_mean}


# ---------------------------------------------------------------- stages

def _days(selection, lo, hi):
    return [d for d in sorted(selection) if lo <= d <= hi]


DECLARED_CONFIGURATIONS = (
    # (name, slippage mode, cost model, gross-cap mode). SIX, declared before any T17 PnL
    # exists, and the DSR trial count is asserted against this tuple's length at run time.
    ("mean/zero_diagnostic", "mean", "zero", "pro_rata"),
    ("mean/T6_measured", "mean", "T6", "pro_rata"),
    ("mean/T6_plus_paper_commission", "mean", "T6c", "pro_rata"),
    ("empirical/T6_measured", "empirical", "T6", "pro_rata"),
    ("empirical/T6_plus_paper_commission", "empirical", "T6c", "pro_rata"),
    ("empirical/T6_measured/truncate", "empirical", "T6", "truncate"),
)
PRIMARY_CONFIGURATION = "empirical/T6_measured"


def _cost_models():
    """T6 is the honest model. `zero` is a DIAGNOSTIC and is never a trading assumption.

    The zero diagnostic is only ever paired with the MEAN slippage mode, because the
    empirical mode carries slippage in the FILL PRICE -- a "zero-cost" run off the empirical
    outcome matrix would still be paying measured slippage while calling itself frictionless,
    which is a mislabelled number and this rig does not produce one.
    """
    return {"T6": COSTS.b22b_measured_costs(),
            "T6c": COSTS.b22b_measured_costs(commission_micros_per_share=3500),
            "zero": COSTS.zero_cost_model()}


def _run_all(days, selection, keep_primary=False):
    models = _cost_models()
    matrices, census = {}, {}
    for mode in ("mean", "empirical"):
        matrices[mode], census[mode] = build_outcomes(days, selection, mode)
    results = {}
    for name, mode, cname, capmode in DECLARED_CONFIGURATIONS:
        charge_mode = "zero" if cname == "zero" else mode
        keep = keep_primary and name == PRIMARY_CONFIGURATION
        res = replay(matrices[mode], days, models[cname], charge_mode,
                     keep_trades=keep, gross_cap_mode=capmode)
        s = summarise(res["daily_returns"], name)
        s["n_trades"] = res["n_trades"]
        s["gross_cap_mode"] = capmode
        results[name] = (s, res, matrices[mode], models[cname], mode)
    return results, census, models


def stage_design():
    selection = json.loads((CACHE / "selection.json").read_text())
    days = _days(selection, ORB.DESIGN_START, ORB.DESIGN_END)
    results, census, _ = _run_all(days, selection)
    report = {"window": [ORB.DESIGN_START, ORB.DESIGN_END], "n_sessions": len(days),
              "census": census,
              "configurations": {k: v[0] for k, v in results.items()}}
    (OUT / "T17_DESIGN_RESULT.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: {kk: v[kk] for kk in
                          ("annualised_sharpe", "annualised_return", "max_drawdown",
                           "n_trades", "n_days")}
                      for k, v in report["configurations"].items()}, indent=1))


def stage_heldout(window="heldout"):
    sentinel = OUT / ("T17_HELDOUT_RESULT.json" if window == "heldout"
                      else "T17_POSTPAPER_RESULT.json")
    if sentinel.exists():
        raise PINNED.Refused(
            f"{sentinel.name} already exists. The held-out window is spent. Re-running it "
            "with anything changed is how a held-out window stops being one."
        )
    design = json.loads((OUT / "T17_DESIGN_RESULT.json").read_text())
    trial_sharpes = [v["annualised_sharpe"] / math.sqrt(252)
                     for v in design["configurations"].values()]
    # NOT a chained comparison: `a != b != c` is `(a != b) and (b != c)`, which with two
    # equal constants is always False and silently inert. Written out so it actually fires.
    if (len(trial_sharpes) != DECLARED_TRIALS
            or len(DECLARED_CONFIGURATIONS) != DECLARED_TRIALS):
        raise PINNED.Refused(
            f"declared {DECLARED_TRIALS} trials, design report has {len(trial_sharpes)}")
    svar = STATS.sharpe_variance_from_trials(trial_sharpes)

    selection = json.loads((CACHE / "selection.json").read_text())
    lo, hi = ((ORB.HELDOUT_START, ORB.HELDOUT_END) if window == "heldout"
              else (ORB.POSTPAPER_START, ORB.POSTPAPER_END))
    days = _days(selection, lo, hi)
    results, census, models = _run_all(days, selection, keep_primary=True)
    report = {"window": [lo, hi], "n_sessions": len(days), "census": census,
              "declared_trials": DECLARED_TRIALS, "sharpe_variance_from_design": svar,
              "cost_model_round_trip_bp": float(models["T6"].round_trip_bp()),
              "configurations": {}}
    for name, (s, res, matrix, cost, mode) in results.items():
        try:
            s["dsr"] = STATS.deflated_sharpe(res["daily_returns"], trials=DECLARED_TRIALS,
                                             sharpe_variance=svar)
        except PINNED.Refused as exc:
            s["dsr"] = {"refused": str(exc)}
        report["configurations"][name] = s
    s, res, matrix, cost, mode = results[PRIMARY_CONFIGURATION]
    report["primary_configuration"] = PRIMARY_CONFIGURATION
    report["permutation"] = permutation(matrix, days, cost, mode, s["mean_daily"])
    report["trade_distribution"] = trade_stats(res["trades"])
    report["gates"] = {
        "net_mean_above_zero": s["mean_daily"] > 0,
        "permutation_p_below_0p05": report["permutation"]["p_value"] < 0.05,
        "dsr_at_least_0p95": bool(s["dsr"].get("dsr", 0) >= 0.95),
    }
    report["verdict"] = "SURVIVES" if all(report["gates"].values()) else "DEAD"
    sentinel.write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("configurations", "census")}, indent=1)[:5000])
    print(json.dumps({k: {kk: v.get(kk) for kk in ("annualised_sharpe", "annualised_return",
                                                   "max_drawdown", "n_trades")}
                      for k, v in report["configurations"].items()}, indent=1))


def stage_sensitivity(window="heldout"):
    """POST-PRIMARY, and labelled as such. Never a gate, never the headline.

    Runs only after the primary held-out result exists, and appends to it. Three questions
    the primary run cannot answer on its own:

      full_bar_entry_stop -- how much of the answer is the entry-bar granularity assumption
                             (see `simulate_stock_day.__doc__`).
      long_only           -- B22G found 8 of the 52 names B22B screened are hard-to-borrow
                             and not shortable at Alpaca, and this rule's SHORT leg is the
                             majority of its signals. Point-in-time shortability is not
                             obtainable, so the bound is computed by deleting the short leg
                             entirely: the truth is between long_only and the primary.
      slippage_percentile -- the T6 mean replaced by B22B's p90 and p95 adverse rungs.
    """
    sentinel = OUT / ("T17_HELDOUT_RESULT.json" if window == "heldout"
                      else "T17_POSTPAPER_RESULT.json")
    if not sentinel.exists():
        raise PINNED.Refused(f"{sentinel.name} does not exist; run the primary stage first")
    report = json.loads(sentinel.read_text())
    selection = json.loads((CACHE / "selection.json").read_text())
    lo, hi = report["window"]
    days = _days(selection, lo, hi)
    models = _cost_models()
    out = {}

    m_full, _ = build_outcomes(days, selection, "empirical", entry_bar_stop_rule="full_bar")
    r = replay(m_full, days, models["T6"], "empirical")
    out["full_bar_entry_stop"] = summarise(r["daily_returns"], "full_bar_entry_stop")
    out["full_bar_entry_stop"]["n_trades"] = r["n_trades"]

    m, _ = build_outcomes(days, selection, "empirical")
    long_only = {d: [row for row in rows if row["candle"] == "long"] for d, rows in m.items()}
    r = replay(long_only, days, models["T6"], "empirical")
    out["long_only"] = summarise(r["daily_returns"], "long_only")
    out["long_only"]["n_trades"] = r["n_trades"]
    short_only = {d: [row for row in rows if row["candle"] == "short"] for d, rows in m.items()}
    r = replay(short_only, days, models["T6"], "empirical")
    out["short_only"] = summarise(r["daily_returns"], "short_only")
    out["short_only"]["n_trades"] = r["n_trades"]

    for pct in ("p90", "p95"):
        cost = COSTS.CostModel(
            entry_half_spread=models["T6"].entry_half_spread,
            entry_extra_slippage=COSTS.measured_extra_slippage("100", pct, None),
            exit_half_spread=models["T6"].exit_half_spread,
            exit_extra_slippage=COSTS.measured_extra_slippage("100", pct, None),
            commission_per_share=models["T6"].commission_per_share,
            borrow_annual=models["T6"].borrow_annual)
        m_mean, _ = build_outcomes(days, selection, "mean")
        r = replay(m_mean, days, cost, "mean")
        out[f"slippage_{pct}_every_trade"] = summarise(r["daily_returns"], pct)
        out[f"slippage_{pct}_every_trade"]["n_trades"] = r["n_trades"]
        out[f"slippage_{pct}_every_trade"]["round_trip_bp"] = float(cost.round_trip_bp())

    report["sensitivities_POST_HOC"] = out
    sentinel.write_text(json.dumps(report, indent=1))
    print(json.dumps({k: {kk: v.get(kk) for kk in
                          ("annualised_sharpe", "annualised_return", "max_drawdown",
                           "n_trades")} for k, v in out.items()}, indent=1))


def trade_stats(trades):
    done = [t for t in trades if t.get("outcome") in ("STOPPED", "CLOSE")]
    if not done:
        return {"n": 0}
    nr = sorted(t["net_r"] for t in done if t["net_r"] is not None)
    gr = sorted(t["gross_r"] for t in done)
    n = len(nr)

    def pct(v, q):
        return v[min(n - 1, q * n // 100)]
    slip = [t.get("slip_r", 0.0) for t in done]
    chg = [t.get("charge_r") or 0.0 for t in done]
    return {"n": n, "n_no_trigger": len(trades) - n,
            "mean_price_slippage_r": sum(slip) / n,
            "mean_notional_charge_r": sum(chg) / n,
            "mean_total_friction_r": (sum(slip) + sum(chg)) / n,
            "price_slippage_r_p95": sorted(slip)[95 * n // 100],
            "price_slippage_r_max": max(slip),
            "win_rate_net": sum(1 for x in nr if x > 0) / n,
            "mean_net_r": sum(nr) / n, "mean_gross_r": sum(gr) / len(gr),
            "cost_in_r": sum(gr) / len(gr) - sum(nr) / n,
            "net_r_p1": pct(nr, 1), "net_r_p5": pct(nr, 5), "net_r_p25": pct(nr, 25),
            "net_r_p50": pct(nr, 50), "net_r_p75": pct(nr, 75), "net_r_p95": pct(nr, 95),
            "net_r_p99": pct(nr, 99), "net_r_min": nr[0], "net_r_max": nr[-1],
            "stopped_share": sum(1 for t in done if t["outcome"] == "STOPPED") / n}


if __name__ == "__main__":
    stage = sys.argv[1]
    if stage == "design":
        stage_design()
    elif stage == "heldout":
        stage_heldout("heldout")
    elif stage == "postpaper":
        stage_heldout("postpaper")
    elif stage == "sensitivity":
        stage_sensitivity(sys.argv[2] if len(sys.argv) > 2 else "heldout")
    else:
        raise SystemExit(f"unknown stage {stage!r}")
