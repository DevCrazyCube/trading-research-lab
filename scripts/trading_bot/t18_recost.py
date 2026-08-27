#!/usr/bin/env python3
"""T18 RECOST -- the T17 held-out run, re-priced with a MEASURED exit leg. Hashed with T18.

WHAT CHANGES AND WHAT DOES NOT
==============================
Exactly two inputs change against `T17_HELDOUT_RESULT.json`, and both are the ones T17's own
report named as the unresolved quantities:

  1. the EXIT leg's price. T17 drew it from B22B's ENTRY distribution
     (`ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG`) and added a 2.5 bp exit half-spread on notional.
     T18 measured it: a stop-loss market order's realised NBBO fill against the stop level, and
     a market-on-close's realised official print against the last-bar mark the backtest credits.
  2. the ENTRY-BAR stop tie-break. T17 offered two bar readings 9.4 Sharpe points apart. T18
     measured, at tick level, how often the disputed bars really traded through the stop AFTER
     the entry filled, and that measured rate is applied here.

EVERYTHING ELSE IS T17's. The universe, the selection, the cached 1-minute paths, the sizing,
the 4x gross cap, the compounding, the ENTRY slippage draws (same pool, same keys, same LCG),
the statistics, the permutation machinery. `scripts/trading_bot/t17_orb.py` and
`t17_run.py` are hashed by T17's pre-registration and are NOT edited: `replay`, `summarise`
and `permutation` are IMPORTED from `t17_run` and used unchanged. Only the per-stock-day
simulator is re-implemented here, because the frozen one takes a single exit-slippage magnitude
and cannot express a stop-versus-close distinction, and its `entry_bar_stop_rule` has no
measured rung.

THE CONTROL THAT MAKES THAT REIMPLEMENTATION HONEST
===================================================
`--control` runs this file's simulator with T17's own settings -- the entry pool for both legs,
`entry_bar_stop_rule="close"`, T17's bar-open gap-through exit base, T17's exit half-spread --
and asserts it reproduces the published held-out Sharpe of the primary configuration to 1e-9.
If the reimplementation drifted, the run refuses instead of publishing a number.

WHY THE EXIT HALF-SPREAD IS NOT CHARGED ON TOP OF THE MEASURED EXIT
==================================================================
The measured exit slippage is the gap from a TRADED level (the stop trigger print) to the price
a market order actually receives on the other side of the book. It therefore already contains
the half-spread, for the same reason B22B's entry number does and `b22b_measured_costs()` sets
the ENTRY half-spread to zero rather than double-charging it. Charging 2.5 bp again would be
the same double-count in the other direction. That is a substantive choice in the strategy's
favour, so the ladder below carries a rung (`plus_exit_half_spread`) that charges it anyway,
on top of T17's own adverse bar-gap exit base, as the conservative bound.

USAGE
    python3 scripts/trading_bot/t18_recost.py control
    python3 scripts/trading_bot/t18_recost.py run
"""

from __future__ import annotations

import json
import math
import pathlib
import sys
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from trading_bot import costs as COSTS  # noqa: E402
from trading_bot import frozen as PINNED  # noqa: E402
from trading_bot import stats as STATS  # noqa: E402
from trading_bot import t17_orb as ORB  # noqa: E402
from trading_bot import t17_run as T17RUN  # noqa: E402
from trading_bot import t18_exit_ticks as T18  # noqa: E402

CACHE = ROOT / "research" / "data" / "t17_cache"
OUT = ROOT / "research" / "trading_bot"

# Draw keys. The ENTRY key scheme is T17's, verbatim, so the entry friction on every stock-day
# is the SAME draw it was in the published run and the comparison isolates the exit.
EXIT_KEY_OFFSET = 500_000_003          # T17's own offset, re-used for the EXIT pool
TIE_BREAK_KEY_OFFSET = 900_000_011     # new: the entry-bar Bernoulli
SLIP_SEED = T17RUN.SLIP_SEED

# (name, entry-bar rule, exit-base mode, charge exit half-spread, commission micros/share,
#  charge mode, ENTRY slippage source). EIGHT, declared before any T18 PnL exists.
DECLARED_CONFIGURATIONS = (
    ("t18/measured_exit/R", "measured", "trigger_level", False, 0, "empirical", "b22b"),
    ("t18/measured_exit/R/entry_bar_close", "close", "trigger_level", False, 0,
     "empirical", "b22b"),
    ("t18/measured_exit/R/entry_bar_full_bar", "full_bar", "trigger_level", False, 0,
     "empirical", "b22b"),
    ("t18/measured_exit/R/plus_exit_half_spread", "measured", "t17_bar_gap", True, 0,
     "empirical", "b22b"),
    ("t18/measured_exit/R/paper_commission", "measured", "trigger_level", False, 3500,
     "empirical", "b22b"),
    ("t18/measured_exit/R/tie_break_upper_ci", "measured_upper", "trigger_level", False, 0,
     "empirical", "b22b"),
    # The other legitimate transfer of the same measurement: everything as a fraction of
    # NOTIONAL rather than of R. T17 reported both because its verdict differed between them.
    ("t18/measured_exit/notional", "measured", "trigger_level", False, 0, "mean", "b22b"),
    # DIAGNOSTIC, and declared as a trial rather than smuggled in as a footnote: the ENTRY leg
    # re-measured on T17's OWN selected stock-days instead of transferred from B22B's more
    # liquid 2025 most-actives pool. If the two disagree, the transfer -- not the exit -- is the
    # larger error, and that has to be visible.
    ("t18/measured_entry_and_exit/R", "measured", "trigger_level", False, 0,
     "empirical", "t18"),
)
PRIMARY = "t18/measured_exit/R"
T17_DECLARED_TRIALS = T17RUN.DECLARED_TRIALS          # 6
CUMULATIVE_TRIALS = T17_DECLARED_TRIALS + len(DECLARED_CONFIGURATIONS)


# --------------------------------------------------------------------------- draws

class Pool(ORB.EmpiricalSlippage):
    """A keyed draw from an ARBITRARY measured pool, using T17's own LCG and key arithmetic.

    Subclassed rather than rewritten so the random stream is provably the same machinery that
    produced the published numbers; only the pool of measured values differs.
    """

    def __init__(self, values, seed: int):
        if len(values) < 100:
            raise PINNED.Refused(
                f"a measured pool of {len(values)} observations is too small to draw a "
                "held-out cost distribution from; refusing rather than extrapolating")
        self.values = sorted(values)
        self.seed = seed & 0xFFFFFFFFFFFFFFFF
        self.state = self.seed
        self.n = len(self.values)

    def _hash(self, key: int) -> int:
        return T17RUN._lcg(T17RUN._lcg(self.seed ^ (key * 0x9E3779B97F4A7C15 & (2 ** 64 - 1))))

    def draw_keyed(self, r_micros: int, key: int) -> int:
        return self.values[(self._hash(key) >> 33) % self.n] * r_micros // 10000

    def uniform_keyed(self, key: int) -> float:
        """A keyed U[0,1) for the entry-bar Bernoulli. Same stream, different consumer."""
        return ((self._hash(key) >> 33) % 1_000_000) / 1_000_000.0


def entry_pool() -> "Pool":
    """B22B's decontaminated ENTRY distribution, in the SAME object shape as the new pools.

    The values and the draw arithmetic are T17's: `ORB.EmpiricalSlippage` reads and filters the
    same file, `Pool` sorts identically, and the keyed hash is `t17_run.KeyedSlippage`'s. The
    control run asserts that this reproduces the published number rather than assuming it.
    """
    return Pool(ORB.EmpiricalSlippage(SLIP_SEED).values, SLIP_SEED)


class ZeroPool:
    """No price slippage in the fill. Used only by the NOTIONAL transfer, whose friction is
    charged by `replay`'s mean branch as a fraction of notional instead."""

    def __init__(self, like):
        self._like = like

    def draw_keyed(self, r_micros: int, key: int) -> int:
        return 0

    def uniform_keyed(self, key: int) -> float:
        return self._like.uniform_keyed(key)


def t18_entry_pool(records) -> "Pool":
    """The ENTRY leg as measured on T17's OWN selected stock-days, decontaminated at the same
    0.1-ATR rung B22B uses. Used only by the declared diagnostic configuration."""
    values = [r["entry"][str(T18.VERDICT_LATENCY_MS)]["slippage_r_bp"] for r in records
              if r.get("outcome") in ("STOPPED", "CLOSE")
              and r.get("entry_through_atr", 9e9) <= T18.DECONTAMINATION_ATR]
    return Pool(values, SLIP_SEED)


# --------------------------------------------------------------------------- the simulator

def simulate_stock_day(direction, entry_level, r_micros, bars, entry_slip_micros,
                       stop_slip_micros, moc_slip_micros, entry_bar_stop_rule,
                       tie_break_u=None, p_tie_break=None, exit_base_mode="trigger_level"):
    """T17's frozen `simulate_stock_day`, with the two measured quantities substituted.

    Identical in every other respect -- gap-through entry fills, the adverse same-bar ordering
    from the second bar on, NO_TRIGGER as a distinct outcome, integer micro-dollars.

    entry_bar_stop_rule
        "close"          T17's frozen default: the entry bar stops out only if it CLOSES through.
        "full_bar"       T17's adverse sensitivity: the entry bar's whole low/high counts.
        "measured"       the disputed bars -- full_bar says hit, close says not -- stop out with
                         the tick-MEASURED probability `p_tie_break`, drawn from a keyed uniform
                         so a permutation cannot redraw its own friction.
        "measured_upper" the same, at the upper end of the measurement's binomial interval.

    exit_base_mode
        "trigger_level"  the fill is the stop level minus the MEASURED slippage, because the
                         measurement priced a market order against exactly that level and its
                         distribution already contains the gap-throughs.
        "t17_bar_gap"    T17's own min(stop, bar open) adverse base, kept for the control run
                         and for the conservative rung.
    """
    if direction not in ("long", "short"):
        raise PINNED.Refused(f"direction must be long or short, got {direction!r}")
    if r_micros <= 0:
        raise PINNED.Refused("R must be positive")
    if not bars:
        raise PINNED.Refused("no intraday bars: a stock-day with no data is missing, not flat")
    if entry_bar_stop_rule not in ("close", "full_bar", "measured", "measured_upper"):
        raise PINNED.Refused(f"unknown entry_bar_stop_rule {entry_bar_stop_rule!r}")
    if exit_base_mode not in ("trigger_level", "t17_bar_gap"):
        raise PINNED.Refused(f"unknown exit_base_mode {exit_base_mode!r}")

    sign = 1 if direction == "long" else -1

    entry_index = None
    for i, b in enumerate(bars):
        touched = (b["h"] >= entry_level) if sign > 0 else (b["l"] <= entry_level)
        if touched:
            entry_index = i
            break
    if entry_index is None:
        return {"outcome": "NO_TRIGGER"}

    b = bars[entry_index]
    base = max(entry_level, b["o"]) if sign > 0 else min(entry_level, b["o"])
    fill = base + sign * entry_slip_micros
    stop_level = fill - sign * r_micros

    for j in range(entry_index, len(bars)):
        bj = bars[j]
        if j == entry_index:
            closed_through = (bj["c"] <= stop_level) if sign > 0 else (bj["c"] >= stop_level)
            spanned = (bj["l"] <= stop_level) if sign > 0 else (bj["h"] >= stop_level)
            if entry_bar_stop_rule == "close":
                hit = closed_through
            elif entry_bar_stop_rule == "full_bar":
                hit = spanned
            else:
                if p_tie_break is None or tie_break_u is None:
                    raise PINNED.Refused(
                        "the measured tie-break rule needs both the measured rate and a keyed "
                        "draw; absence is a refusal, not a coin flip")
                hit = closed_through or (spanned and tie_break_u < p_tie_break)
        else:
            hit = (bj["l"] <= stop_level) if sign > 0 else (bj["h"] >= stop_level)
        if hit:
            if exit_base_mode == "trigger_level":
                exit_base = stop_level
            elif j == entry_index:
                exit_base = (min(stop_level, bj["c"]) if sign > 0
                             else max(stop_level, bj["c"]))
            else:
                exit_base = min(stop_level, bj["o"]) if sign > 0 else max(stop_level, bj["o"])
            exit_price = exit_base - sign * stop_slip_micros
            return {"outcome": "STOPPED", "entry": fill, "exit": exit_price,
                    "pnl_per_share": sign * (exit_price - fill),
                    "slip_micros": entry_slip_micros + stop_slip_micros,
                    "entry_index": entry_index, "exit_index": j}

    close = bars[-1]["c"]
    exit_price = close - sign * moc_slip_micros
    return {"outcome": "CLOSE", "entry": fill, "exit": exit_price,
            "pnl_per_share": sign * (exit_price - fill),
            "slip_micros": entry_slip_micros + moc_slip_micros,
            "entry_index": entry_index, "exit_index": len(bars) - 1}


# --------------------------------------------------------------------------- outcome matrix

def build_outcomes(days, selection, entry_pool, stop_pool, moc_pool, rule, p_tie_break,
                   exit_base_mode, seed=SLIP_SEED):
    """T17's `build_outcomes`, key-for-key, with the T18 simulator underneath."""
    matrix, census = {}, {"sessions": 0, "no_path_file": 0, "no_path_symbol": 0, "stock_days": 0}
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
                key = di * 1_000_003 + rank * 97 + (1 if d == "long" else 2)
                e = entry_pool.draw_keyed(r_micros, key)
                x = stop_pool.draw_keyed(r_micros, key + EXIT_KEY_OFFSET)
                m = moc_pool.draw_keyed(r_micros, key + EXIT_KEY_OFFSET)
                u = entry_pool.uniform_keyed(key + TIE_BREAK_KEY_OFFSET)
                res = simulate_stock_day(d, level, r_micros, bars, e, x, m, rule,
                                         tie_break_u=u, p_tie_break=p_tie_break,
                                         exit_base_mode=exit_base_mode)
                res["entry_level"] = level
                both[d] = res
            rows.append({"symbol": sym, "relvol": relvol, "candle": direction,
                         "r_micros": r_micros, "long": both["long"], "short": both["short"]})
            census["stock_days"] += 1
        if rows:
            matrix[day] = rows
            census["sessions"] += 1
    return matrix, census


# --------------------------------------------------------------------------- cost models

def _component(name, value_bp, provenance, source):
    return COSTS.CostComponent(name, Fraction(value_bp), "bp of notional", provenance, source)


def t18_cost_model(charge_exit_half_spread: bool, commission_micros_per_share: int,
                   measurement: dict, notional_mode: bool = False) -> COSTS.CostModel:
    """T6's model with the exit side replaced by the T18 measurement.

    In the empirical (price-slippage) mode that this driver runs, `replay` charges ONLY the exit
    half-spread on notional -- both legs' price slippage is already inside the fill. So the exit
    half-spread is the single notional term, and it is zero unless the conservative rung asks
    for it.
    """
    base = COSTS.b22b_measured_costs(commission_micros_per_share=commission_micros_per_share)
    if charge_exit_half_spread:
        return base
    if notional_mode:
        # The measured exit as a fraction of NOTIONAL, read out of costs.py rather than
        # recomputed here, so the number the report quotes is the number the cost module says.
        half, extra = COSTS.measured_exit_leg_t18("blend")
        return COSTS.CostModel(
            entry_half_spread=base.entry_half_spread,
            entry_extra_slippage=base.entry_extra_slippage,
            exit_half_spread=half, exit_extra_slippage=extra,
            commission_per_share=base.commission_per_share,
            borrow_annual=base.borrow_annual)
    stop = measurement["exit_stop_leg"][str(T18.VERDICT_LATENCY_MS)]["r_bp_decontaminated"]
    return COSTS.CostModel(
        entry_half_spread=base.entry_half_spread,
        entry_extra_slippage=base.entry_extra_slippage,
        exit_half_spread=_component(
            "exit_half_spread", 0, COSTS.SlippageProvenance.MEASURED_B22B,
            "ZERO ON PURPOSE, AND ONLY BECAUSE THE EXIT IS NOW MEASURED: T18 priced the exit "
            f"fill at the far side of the book against the stop level over {stop['n']} measured "
            "stop exits, so the half-spread is already inside the price slippage this run "
            "charges to the fill. Charging it again here would double-count it, exactly as "
            "charging one on the B22B entry would. The `plus_exit_half_spread` rung charges it "
            "anyway as the conservative bound.",
        ),
        exit_extra_slippage=_component(
            "exit_extra_slippage", 0, COSTS.SlippageProvenance.MEASURED_B22B,
            "carried in the FILL PRICE by the T18 measured draw, not as a notional fraction.",
        ),
        commission_per_share=base.commission_per_share,
        borrow_annual=base.borrow_annual)


# --------------------------------------------------------------------------- run

def _days(selection, lo, hi):
    return [d for d in sorted(selection) if lo <= d <= hi]


def _pools(measurement, records):
    """The three measured draw pools, in basis points of R, and WHICH filtering is used.

    THE DECONTAMINATION DIRECTION IS NOT THE SAME ON THE EXIT AS ON THE ENTRY, AND THIS IS THE
    RULE FOR IT, FROZEN BEFORE ANY HELD-OUT NUMBER EXISTS.
    On the ENTRY, dropping trigger prints more than 0.1 ATR through the level removes dislocated
    odd-lot prints that all sit in the FAVOURABLE tail, so the filter makes the charged cost more
    adverse and B22B/T6 simply apply it. On the EXIT the same filter can cut either way: it also
    removes genuine fast moves that gapped through the stop, and those are the expensive fills.
    So the pool is chosen by an explicit, pre-registered tie-break rather than by taste:

        the pool charged is whichever of {unfiltered, decontaminated} has the MORE ADVERSE mean.

    Both are reported, with the chosen one named, so the choice is auditable and cannot be made
    after seeing a Sharpe.
    """
    lat = str(T18.VERDICT_LATENCY_MS)
    entry = entry_pool()                              # B22B's own pool, unchanged
    clean_entry = [r for r in records
                   if r.get("entry_through_atr", 9e9) <= T18.DECONTAMINATION_ATR]

    stop_raw = [r["exit"][lat]["slippage_r_bp"] for r in records
                if r.get("outcome") == "STOPPED"]
    stop_clean = [r["exit"][lat]["slippage_r_bp"] for r in clean_entry
                  if r.get("outcome") == "STOPPED"
                  and r.get("exit_through_atr", 9e9) <= T18.DECONTAMINATION_ATR]
    # The MOC pool is measured on EVERY triggered stock-day, not only the ones whose stop never
    # fired: the print-versus-mark gap is a property of the session, and conditioning it on the
    # position having survived to the close would condition the exit cost on the trade having
    # been a winner.
    moc_raw = [r["moc"]["slippage_r_bp"] for r in records
               if r.get("outcome") in ("STOPPED", "CLOSE") and "moc" in r]
    moc_clean = [r["moc"]["slippage_r_bp"] for r in clean_entry
                 if r.get("outcome") in ("STOPPED", "CLOSE") and "moc" in r]

    def worse(raw, clean, what):
        if not raw or not clean:
            raise PINNED.Refused(f"{what}: an empty pool has no mean; refusing")
        m_raw, m_clean = sum(raw) / len(raw), sum(clean) / len(clean)
        chosen = ("unfiltered", raw, m_raw) if m_raw >= m_clean else ("decontaminated", clean,
                                                                      m_clean)
        return {"basis": chosen[0], "values": chosen[1],
                "mean_unfiltered_r_bp": m_raw, "n_unfiltered": len(raw),
                "mean_decontaminated_r_bp": m_clean, "n_decontaminated": len(clean)}

    stop = worse(stop_raw, stop_clean, "stop exit pool")
    moc = worse(moc_raw, moc_clean, "MOC exit pool")
    return (entry, Pool(stop["values"], SLIP_SEED), Pool(moc["values"], SLIP_SEED),
            {"stop": {k: v for k, v in stop.items() if k != "values"},
             "moc": {k: v for k, v in moc.items() if k != "values"}})


def binomial_upper(k: int, n: int, z: float = 1.96) -> float:
    """Wilson upper bound. The tie-break rate is a proportion, so its uncertainty is binomial."""
    if n == 0:
        raise PINNED.Refused("a proportion of zero observations has no interval")
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return min(1.0, centre + half)


def sample_agreement(matrices, records):
    """Does the re-costed SIMULATION agree with the TICK TRUTH on the stock-days both saw?

    The re-cost transfers a measured distribution onto ~19,000 simulated stock-days. On the
    ~1,000 stock-days that were actually measured, the two can be compared directly, per trade,
    in R. A simulation that is systematically kinder than the tick truth on the days it can be
    checked against has no claim on the days it cannot.
    """
    truth = {}
    for r in records:
        if r.get("outcome") not in ("STOPPED", "CLOSE"):
            continue
        if r.get("entry_through_atr", 9e9) > T18.DECONTAMINATION_ATR:
            continue
        if r["outcome"] == "STOPPED" and r.get("exit_through_atr", 9e9) > T18.DECONTAMINATION_ATR:
            continue
        sign = 1 if r["direction"] == "long" else -1
        ex = (r["exit"][str(T18.VERDICT_LATENCY_MS)]["fill_micros"] if r["outcome"] == "STOPPED"
              else r["moc"]["fill_micros"])
        truth[(r["day"], r["symbol"])] = {
            "net_r": sign * (ex - r["entry_fill_micros"]) / r["r_micros"],
            "outcome": r["outcome"]}
    out = {"n_measured_stock_days": len(truth),
           "tick_truth_mean_net_r": (sum(v["net_r"] for v in truth.values()) / len(truth)
                                     if truth else None),
           "tick_truth_stopped_share": (sum(1 for v in truth.values()
                                            if v["outcome"] == "STOPPED") / len(truth)
                                        if truth else None)}
    for name, matrix in matrices.items():
        vals, stopped, matched = [], 0, 0
        for day, rows in matrix.items():
            for row in rows:
                key = (day, row["symbol"])
                if key not in truth:
                    continue
                res = row[row["candle"]]
                if res["outcome"] == "NO_TRIGGER":
                    continue
                matched += 1
                vals.append(res["pnl_per_share"] / row["r_micros"])
                stopped += res["outcome"] == "STOPPED"
        out[name] = {"n_matched": matched,
                     "sim_mean_net_r": sum(vals) / len(vals) if vals else None,
                     "sim_stopped_share": stopped / matched if matched else None}
    return out


def run(control_only: bool = False):
    """`control_only` runs the reproduction check ALONE, and deliberately touches no T18
    measurement: it is meant to be runnable BEFORE the held-out ticks are collected, so that the
    simulator is proven against T17 before it is ever pointed at a corrected number."""
    selection = json.loads((CACHE / "selection.json").read_text())
    days = _days(selection, ORB.HELDOUT_START, ORB.HELDOUT_END)
    if control_only:
        entry_pool_obj = entry_pool()
        measurement = records = pool_basis = None
        stop_pool = moc_pool = t18_entry_pool_obj = entry_pool_obj
    else:
        measurement = json.loads((OUT / "T18_EXIT_MEASUREMENT.json").read_text())
        records = T18.load_records("heldout")
        entry_pool_obj, stop_pool, moc_pool, pool_basis = _pools(measurement, records)
        t18_entry_pool_obj = t18_entry_pool(records)

    t17 = json.loads((OUT / "T17_HELDOUT_RESULT.json").read_text())
    published = t17["configurations"][T17RUN.PRIMARY_CONFIGURATION]["annualised_sharpe"]

    # ---- CONTROL: this file's simulator, run with T17's own settings, must reproduce T17.
    m, _ = build_outcomes(days, selection, entry_pool_obj, entry_pool_obj, entry_pool_obj,
                          "close", None, "t17_bar_gap")
    control = T17RUN.replay(m, days, COSTS.b22b_measured_costs(), "empirical")
    control_sharpe = T17RUN.summarise(control["daily_returns"], "control")["annualised_sharpe"]
    if abs(control_sharpe - published) > 1e-9:
        raise PINNED.Refused(
            f"the T18 simulator does not reproduce T17: control Sharpe {control_sharpe!r} "
            f"against the published {published!r}. Refusing to publish a corrected number from "
            "a rig that cannot reproduce the number it corrects.")
    print(f"CONTROL OK: reproduces T17 primary Sharpe {control_sharpe:.10f}")
    if control_only:
        return

    tie = measurement["entry_bar_tie_break"]["disputed"]
    p_hit = tie["p_tick_hit"]
    p_hit_upper = binomial_upper(tie["tick_hit"], tie["n"])

    trial_sharpes_t17 = [v["annualised_sharpe"] / math.sqrt(252)
                         for v in json.loads((OUT / "T17_DESIGN_RESULT.json").read_text())
                         ["configurations"].values()]

    report = {"window": [ORB.HELDOUT_START, ORB.HELDOUT_END], "n_sessions": len(days),
              "control_reproduces_t17_sharpe": control_sharpe,
              "t17_published_primary_sharpe": published,
              "measured_inputs": {
                  "tie_break_p_tick_hit": p_hit,
                  "tie_break_p_tick_hit_wilson_upper95": p_hit_upper,
                  "tie_break_numerator": tie["tick_hit"], "tie_break_denominator": tie["n"],
                  "stop_exit_pool_n": stop_pool.n,
                  "stop_exit_pool_mean_r_bp": sum(stop_pool.values) / stop_pool.n,
                  "moc_exit_pool_n": moc_pool.n,
                  "moc_exit_pool_mean_r_bp": sum(moc_pool.values) / moc_pool.n,
                  "entry_pool_n": entry_pool_obj.n,
                  "entry_pool_mean_r_bp": sum(entry_pool_obj.values) / entry_pool_obj.n,
                  "t18_entry_pool_n": t18_entry_pool_obj.n,
                  "t18_entry_pool_mean_r_bp": (sum(t18_entry_pool_obj.values)
                                               / t18_entry_pool_obj.n),
                  "pool_selection": pool_basis},
              "declared_configurations": [c[0] for c in DECLARED_CONFIGURATIONS],
              "configurations": {}}

    keep, matrices = {}, {}
    for (name, rule, base_mode, half_spread, commission, mode,
         entry_source) in DECLARED_CONFIGURATIONS:
        rate = p_hit_upper if rule == "measured_upper" else p_hit
        effective_rule = "measured" if rule == "measured_upper" else rule
        e_pool = t18_entry_pool_obj if entry_source == "t18" else entry_pool_obj
        if mode == "mean":
            # The notional transfer: no price slippage in the fill at all, every friction
            # charged as a fraction of notional by `replay`'s mean branch.
            zero = ZeroPool(e_pool)
            matrix, census = build_outcomes(days, selection, zero, zero, zero,
                                            effective_rule, rate, base_mode)
        else:
            matrix, census = build_outcomes(days, selection, e_pool, stop_pool, moc_pool,
                                            effective_rule, rate, base_mode)
        cost = t18_cost_model(half_spread, commission, measurement, notional_mode=(mode == "mean"))
        res = T17RUN.replay(matrix, days, cost, mode, keep_trades=(name == PRIMARY))
        s = T17RUN.summarise(res["daily_returns"], name)
        s["n_trades"] = res["n_trades"]
        s["tie_break_rate_applied"] = rate
        s["exit_base_mode"] = base_mode
        s["exit_half_spread_charged_bp"] = float(cost.exit_half_spread.value)
        s["commission_micros_per_share"] = commission
        s["charge_mode"] = mode
        s["entry_slippage_source"] = entry_source
        s["round_trip_bp_notional_terms"] = float(cost.round_trip_bp())
        report["configurations"][name] = s
        keep[name] = (res, matrix, cost)
        matrices[name] = matrix

    # ---- certification, at three trial counts, all reported
    trial_sharpes_t18 = [report["configurations"][c[0]]["annualised_sharpe"] / math.sqrt(252)
                         for c in DECLARED_CONFIGURATIONS]
    svar_t17 = STATS.sharpe_variance_from_trials(trial_sharpes_t17)
    svar_all = STATS.sharpe_variance_from_trials(trial_sharpes_t17 + trial_sharpes_t18)
    report["sharpe_variance_t17_design"] = svar_t17
    report["sharpe_variance_cumulative"] = svar_all
    for name in report["configurations"]:
        daily = keep[name][0]["daily_returns"]
        cert = {}
        cert["dsr_trials_6_t17_basis"] = STATS.deflated_sharpe(
            daily, trials=T17_DECLARED_TRIALS, sharpe_variance=svar_t17)
        cert["dsr_trials_12_cumulative"] = STATS.deflated_sharpe(
            daily, trials=CUMULATIVE_TRIALS, sharpe_variance=svar_all)
        cert["psr_trials_1"] = STATS.deflated_sharpe(daily, trials=1)
        report["configurations"][name]["certification"] = cert

    report["sample_agreement"] = sample_agreement(matrices, records)

    res, matrix, cost = keep[PRIMARY]
    s = report["configurations"][PRIMARY]
    report["primary_configuration"] = PRIMARY
    report["permutation"] = T17RUN.permutation(matrix, days, cost, "empirical", s["mean_daily"])
    report["trade_distribution"] = T17RUN.trade_stats(res["trades"])
    report["gates_as_frozen_by_t17"] = {
        "net_mean_above_zero": s["mean_daily"] > 0,
        "permutation_p_below_0p05": report["permutation"]["p_value"] < 0.05,
        "dsr_at_least_0p95_cumulative": bool(
            s["certification"]["dsr_trials_12_cumulative"]["dsr"] >= 0.95),
        "dsr_at_least_0p95_t17_basis": bool(
            s["certification"]["dsr_trials_6_t17_basis"]["dsr"] >= 0.95),
        "psr_trials_1_at_least_0p95": bool(s["certification"]["psr_trials_1"]["dsr"] >= 0.95),
    }
    report["verdict"] = ("SURVIVES" if (report["gates_as_frozen_by_t17"]["net_mean_above_zero"]
                                        and report["gates_as_frozen_by_t17"]["permutation_p_below_0p05"]
                                        and report["gates_as_frozen_by_t17"]["dsr_at_least_0p95_cumulative"])
                        else "DEAD")
    (OUT / "T18_RECOST_RESULT.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: {kk: v.get(kk) for kk in
                          ("annualised_sharpe", "annualised_return", "max_drawdown", "n_trades")}
                      for k, v in report["configurations"].items()}, indent=1))
    print(json.dumps({"verdict": report["verdict"], "gates": report["gates_as_frozen_by_t17"],
                      "permutation": report["permutation"],
                      "measured_inputs": report["measured_inputs"]}, indent=1))


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "run"
    try:
        run(control_only=(stage == "control"))
    except PINNED.Refused as exc:
        sys.stderr.write(f"REFUSED: {exc}\n")
        sys.exit(2)
