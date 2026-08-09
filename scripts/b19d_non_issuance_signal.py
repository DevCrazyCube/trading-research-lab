#!/usr/bin/env python3
"""B19D — does ANY non-issuance signal survive complete costs and the capacity gate?

The evaluation machinery for B19D_NON_ISSUANCE_SIGNAL_PREREGISTRATION, which is frozen and
hash-pinned. This module implements that document and adds nothing to it: every signal, delay,
horizon, cost scenario, position size and refusal code below is quoted from it, and the pin is
verified before any evaluation runs.

WRITTEN BEFORE THE EVALUATION WINDOW EXISTS, AND THAT IS THE POINT. B11a has produced no outcome
anyone has read. An implementation written now is written blind: every choice about which cell is
admissible, how a refusal is classified and where a boundary sits is made by someone who could not
have looked, because there is nothing to look at. Written after the data lands the document still
holds, but the implementation's innocence does not, and no amount of care recovers it. That is why
this was built during the collection rather than after it.

DEVELOPMENT IS BURNED OR SYNTHETIC ONLY. The document says any run against B8b/B9/B10/B16 artifacts
is development, may prove the machinery computes what it claims, and may NEVER be reported as an
evaluation result. The fresh window is read ONCE, later, by an explicit evaluation call. A test
asserts this module names no B11a path, rather than the author promising it.

NO FLOAT ANYWHERE. Every quantity is an exact integer in lamports or a count. The median is an
integer order statistic taken by index into a sorted list -- never a mean, because a mean over a
censored heavy-tailed set invites reading it as an expectation, which it is not.
"""
import argparse
import collections
import hashlib
import importlib.util
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PREREG = ROOT / "research" / "B19D_NON_ISSUANCE_SIGNAL_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "768524effaaf4a013deb80ee5879e98b31729fef39bccbbe16270cdfd05b4b59"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B10A = _load("b10a_simulator_kernel", "b10a_simulator_kernel.py")
B15M = _load("b15m_liquidity_capacity", "b15m_liquidity_capacity.py")


class SignalRefused(RuntimeError):
    """A cell that cannot be evaluated. Always carries one of the document's own codes."""


# ------------------------------------------------------------------------------------------------
# Everything below is QUOTED from the frozen document. Nothing here is a choice made by this module.
# ------------------------------------------------------------------------------------------------

# "position_lamports": 100000000 -- 0.1 SOL, fixed from B10a onward, and NOT varied here.
POSITION = 100_000_000

# "entry_delays_slots": [1, 2, 4], inherited from B15D_SHADOW_ROUTE_V1 and B15L unchanged.
ENTRY_DELAYS = (1, 2, 4)

# B15D_SHADOW_ROUTE_V1's optimistic, base and stressed, verbatim. None added, removed or retuned.
SCENARIOS = (
    {"scenario_id": "optimistic", "base_fee_lamports": 5000, "priority_fee_lamports": 1000,
     "tip_lamports": 0, "ata_rent_lamports": 2039280, "failed_attempts": 0},
    {"scenario_id": "base", "base_fee_lamports": 5000, "priority_fee_lamports": 100000,
     "tip_lamports": 0, "ata_rent_lamports": 2039280, "failed_attempts": 0},
    {"scenario_id": "stressed", "base_fee_lamports": 5000, "priority_fee_lamports": 1000000,
     "tip_lamports": 0, "ata_rent_lamports": 2039280, "failed_attempts": 1},
)

# The four B10c horizons with B10c STATE-IN-FORCE semantics, inherited unchanged.
HORIZON_SLOT = "slot_horizon"
HORIZON_OBSERVATION = "observation_horizon"
HORIZON_ADMINISTRATIVE = "administrative_window_end"
HORIZONS = (
    {"name": "h_1000_slots", "kind": HORIZON_SLOT, "slots": 1_000},
    {"name": "h_10000_slots", "kind": HORIZON_SLOT, "slots": 10_000},
    {"name": "h_10_observations", "kind": HORIZON_OBSERVATION, "count": 10},
    {"name": "administrative_window_end", "kind": HORIZON_ADMINISTRATIVE},
)

# The five candidate signals, frozen. Each is a predicate over a BOOLEAN field of the B11b v1.0.0
# t0 feature contract, or a definition inherited verbatim from an already-frozen preregistration.
#
# S5 IS RETAINED DESPITE BEING KNOWN NEGATIVE. B16D measured it on the burned corpus and found the
# observable edge dominated by selection with every priced variant negative. The document discloses
# that and keeps it anyway, saying its retention "is the test of that rule" -- so dropping it here
# because we know it loses would be precisely the failure the document exists to prevent, performed
# by the person implementing the document.
SIGNALS = (
    {"signal_id": "S1_CREATOR_INITIAL_BUY_PRESENT", "kind": "t0_boolean",
     "field": "creator_initial_buy_present", "expect": True},
    {"signal_id": "S2_NO_CREATOR_INITIAL_BUY", "kind": "t0_boolean",
     "field": "creator_initial_buy_present", "expect": False},
    {"signal_id": "S3_T0_IS_LAUNCH_INSTRUCTION", "kind": "t0_boolean",
     "field": "t0_is_launch_instruction", "expect": True},
    {"signal_id": "S4_CASHBACK_ENABLED", "kind": "t0_boolean",
     "field": "is_cashback_enabled", "expect": True},
    {"signal_id": "S5_CREATOR_REENTRY_DELAYED_CONFIRMATION", "kind": "creator_reentry"},
)

# The two frozen non-model baselines, inherited from B16D unchanged, computed on the same
# denominator and the same machinery.
BASELINES = ("baseline_launch", "baseline_any_buy")

# The document's own refusal codes. A cell is refused with one of these or not at all.
N_NO_SIGNAL = "N_NO_SIGNAL"
N_SAME_SLOT_UNPROVABLE = "N_SAME_SLOT_UNPROVABLE"
N_NO_ENTRY_OBSERVATION = "N_NO_ENTRY_OBSERVATION"
N_NO_FEE_SCHEDULE = "N_NO_FEE_SCHEDULE"
N_FEE_SCHEDULE_AMBIGUOUS = "N_FEE_SCHEDULE_AMBIGUOUS"
N_RIGHT_CENSORED = "N_RIGHT_CENSORED"
N_COMPLETE_AT_ENTRY_OR_EXIT = "N_COMPLETE_AT_ENTRY_OR_EXIT"
N_CAPACITY_REFUSED = "N_CAPACITY_REFUSED"
N_ENTRY_UNPRICEABLE = "N_ENTRY_UNPRICEABLE"
N_EXIT_UNPRICEABLE = "N_EXIT_UNPRICEABLE"
REFUSAL_CODES = (N_NO_SIGNAL, N_SAME_SLOT_UNPROVABLE, N_NO_ENTRY_OBSERVATION, N_NO_FEE_SCHEDULE,
                 N_FEE_SCHEDULE_AMBIGUOUS, N_RIGHT_CENSORED, N_COMPLETE_AT_ENTRY_OR_EXIT,
                 N_CAPACITY_REFUSED, N_ENTRY_UNPRICEABLE, N_EXIT_UNPRICEABLE)

# "primary_result": ONE pre-committed figure. S1 at delay 1, horizon h_10000_slots, base scenario.
PRIMARY = {"signal_id": "S1_CREATOR_INITIAL_BUY_PRESENT", "delay": 1,
           "horizon": "h_10000_slots", "scenario_id": "base"}

# "family_definition": signals x horizons; "family_size": 20.
FAMILY_SIZE = len(SIGNALS) * len(HORIZONS)


def verify_preregistration(path=PREREG, expected=PREREG_CANONICAL_SHA256):
    """The document, or a refusal. Nothing evaluates against an unpinned specification."""
    document = json.loads(pathlib.Path(path).read_bytes())
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise SignalRefused(
            f"the B19D preregistration hashes {actual}, pinned {expected}. A study may not run "
            "against a specification that has changed since it was frozen")
    if len(SIGNALS) * len(HORIZONS) != document["multiplicity"]["family_size"]:
        raise SignalRefused(
            f"this module crosses {len(SIGNALS)} signals with {len(HORIZONS)} horizons, but the "
            f"document declares a family of {document['multiplicity']['family_size']}")
    return document


# ------------------------------------------------------------------------------------------------
# Signal coordinates
# ------------------------------------------------------------------------------------------------

def signal_coordinate(signal, curve, features, reentry):
    """The slot at which this signal became observable, or None if it never fired.

    A t0 boolean fires at the curve's CREATE coordinate: the value is known at t0 by construction,
    so the earliest instant an observer could have acted on it is t0 itself. S5 fires at the
    creator's first re-entry buy, which is B16D's definition and is inherited whole.
    """
    if signal["kind"] == "t0_boolean":
        block = features.get(curve)
        if block is None:
            return None
        value = block.get(signal["field"])
        if value is None or bool(value) is not signal["expect"]:
            return None
        return block.get("t0_slot")
    if signal["kind"] == "creator_reentry":
        trade = reentry.get(curve)
        return None if trade is None else trade["slot"]
    raise SignalRefused(f"unknown signal kind {signal['kind']!r}")


def baseline_coordinate(baseline, curve, features, first_non_creator_buy):
    """The two frozen comparators, on the same machinery and the same denominator."""
    if baseline == "baseline_launch":
        block = features.get(curve)
        return None if block is None else block.get("t0_slot")
    if baseline == "baseline_any_buy":
        trade = first_non_creator_buy.get(curve)
        return None if trade is None else trade["slot"]
    raise SignalRefused(f"unknown baseline {baseline!r}")


# ------------------------------------------------------------------------------------------------
# Path helpers. Canonical order, never insertion order.
# ------------------------------------------------------------------------------------------------

def first_at_or_after(path, slot):
    for observation in path:
        if observation["slot"] >= slot:
            return observation
    return None


def state_in_force(path, slot):
    """B10c STATE-IN-FORCE: the last observation at or BEFORE the horizon, or None."""
    chosen = None
    for observation in path:
        if observation["slot"] <= slot:
            chosen = observation
        else:
            break
    return chosen


def exit_observation(path, entry_observation, horizon):
    """The observation the horizon selects, or None when the cell is right-censored.

    A censored cell carries no outcome and is NEVER counted as zero -- the document is explicit,
    and counting a censored cell as break-even would quietly move the median toward zero from
    whichever side had more censoring.
    """
    index = path.index(entry_observation)
    if horizon["kind"] == HORIZON_SLOT:
        target = entry_observation["slot"] + horizon["slots"]
        if path[-1]["slot"] < target:
            return None                       # nothing observed at or after the horizon
        return state_in_force(path, target)
    if horizon["kind"] == HORIZON_OBSERVATION:
        wanted = index + horizon["count"]
        return path[wanted] if wanted < len(path) else None
    if horizon["kind"] == HORIZON_ADMINISTRATIVE:
        return path[-1] if path[-1] is not entry_observation else None
    raise SignalRefused(f"unknown horizon kind {horizon['kind']!r}")


# ------------------------------------------------------------------------------------------------
# One cell
# ------------------------------------------------------------------------------------------------

def evaluate_cell(path, signal_slot, horizon, delay, schedule, policy, size=POSITION):
    """The net outcome of one (curve, delay, horizon, scenario), or a refusal code.

    Returns an exact integer in lamports. Every failure path raises with one of the document's
    codes, so a cell is never silently dropped and the coverage table adds up.
    """
    if schedule is None:
        raise SignalRefused(N_NO_FEE_SCHEDULE)
    entry = first_at_or_after(path, signal_slot + delay)
    if entry is None:
        raise SignalRefused(N_NO_ENTRY_OBSERVATION)
    if entry["slot"] == signal_slot:
        # Ordering within a slot is decided by the leader, not by what an observer had seen, so
        # same-slot capture cannot be PROVEN. Refused, and counted as an inadmissible variant.
        raise SignalRefused(N_SAME_SLOT_UNPROVABLE)
    exit_ = exit_observation(path, entry, horizon)
    if exit_ is None:
        raise SignalRefused(N_RIGHT_CENSORED)
    if entry["complete"] or exit_["complete"]:
        raise SignalRefused(N_COMPLETE_AT_ENTRY_OR_EXIT)
    entry_state = _state(entry)
    exit_state = _state(exit_)
    if not B15M.is_admissible(entry_state, exit_state, size):
        raise SignalRefused(N_CAPACITY_REFUSED)
    try:
        bought = B10A.price_entry(entry_state, {"side": B10A.BUY, "quote_lamports": size},
                                  schedule, policy)
    except Exception as error:                                            # noqa: BLE001
        raise SignalRefused(N_ENTRY_UNPRICEABLE) from error
    try:
        sold = B10A.price_exit(exit_state, bought["tokens_out"], schedule, policy)
    except Exception as error:                                            # noqa: BLE001
        raise SignalRefused(N_EXIT_UNPRICEABLE) from error
    if sold.get("status") != B10A.STATUS_PRICED:
        raise SignalRefused(N_EXIT_UNPRICEABLE)
    return sold["lamports_into_wallet"] - bought["lamports_out_of_wallet"]


def _state(observation):
    return {"virtual_quote": observation["virtual_quote"],
            "virtual_token": observation["virtual_token"],
            "real_quote": observation["real_quote"], "real_token": observation["real_token"],
            "quote_mint": observation["quote_mint"], "mayhem_mode": observation["mayhem_mode"],
            "complete": observation["complete"], "slot": observation["slot"]}


# ------------------------------------------------------------------------------------------------
# Reporting. Coverage FIRST, then order statistics, and never a mean.
# ------------------------------------------------------------------------------------------------

def order_statistic(values, numerator, denominator):
    """An exact integer order statistic by index into the sorted values. No interpolation."""
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * numerator // denominator
    return ordered[index]


def exact_median(values):
    """The lower median by integer index. NEVER a mean.

    For an even count this is the lower of the two central values rather than their average --
    an average would introduce a value that is not in the data, and for lamports it would also
    introduce a fraction. The document says exact integer median by integer index; this is that.
    """
    if not values:
        return None
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


def summarise(outcomes, refusals, admitted_curves, cohort_size):
    """Coverage before outcome, always.

    The document requires coverage reported FIRST so that no outcome can be read without the share
    of the cohort it came from. This returns them in one object with coverage populated even when
    there is no outcome at all, because "no admissible cells" is itself the result in that case.
    """
    censored = refusals.get(N_RIGHT_CENSORED, 0)
    coverage = {
        "cohort_size": cohort_size,
        "cells_admitted": len(outcomes),
        "curves_admitted": admitted_curves,
        "cells_refused": sum(refusals.values()),
        "refused_by_code": {code: refusals.get(code, 0) for code in REFUSAL_CODES
                            if refusals.get(code)},
        "censored": censored,
    }
    if not outcomes:
        return {"coverage": coverage, "outcome": None,
                "note": "no admissible cells; there is no outcome to report"}
    positives = [value for value in outcomes if value > 0]
    total_positive = sum(positives)
    top = sorted(positives, reverse=True)[:max(1, len(positives) // 20)]
    return {
        "coverage": coverage,
        "outcome": {
            "min": min(outcomes),
            "p10": order_statistic(outcomes, 1, 10),
            "p25": order_statistic(outcomes, 1, 4),
            "median": exact_median(outcomes),
            "p75": order_statistic(outcomes, 3, 4),
            "p90": order_statistic(outcomes, 9, 10),
            "max": max(outcomes),
            "at_or_below_zero": sum(1 for value in outcomes if value <= 0),
            "strictly_above_zero": len(positives),
            # A lottery shape must not present as an edge: the share of all positive outcome
            # carried by the top 5% of positive cells is reported beside every figure.
            "top_5pct_share_of_positive_numerator": sum(top),
            "top_5pct_share_of_positive_denominator": total_positive,
        },
        # "a signal SURVIVES COSTS ... if the exact integer MEDIAN ... is STRICTLY GREATER THAN
        # ZERO". Zero is break-even, an accounting identity, not a fitted cut.
        "survives_costs": exact_median(outcomes) > 0,
        "survives_costs_is_not_an_edge": (
            "a median above zero on one window describes that window. It is not a demonstration "
            "of edge, not a return, and not grounds to trade. It would license a next study."),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true",
                        help="offline: check the preregistration pin and the frozen constants")
    args = parser.parse_args(argv)
    if args.verify:
        document = verify_preregistration()
        print(json.dumps({
            "preregistration": document["preregistration_id"],
            "canonical_sha256": PREREG_CANONICAL_SHA256,
            "signals": [s["signal_id"] for s in SIGNALS],
            "delays": list(ENTRY_DELAYS),
            "horizons": [h["name"] for h in HORIZONS],
            "scenarios": [s["scenario_id"] for s in SCENARIOS],
            "position_lamports": POSITION,
            "family_size": FAMILY_SIZE,
            "primary": PRIMARY,
            "refusal_codes": list(REFUSAL_CODES),
        }, indent=2))
        return 0
    parser.error("the evaluation pass is not wired to a window here; --verify is offline only")


if __name__ == "__main__":
    sys.exit(main())
