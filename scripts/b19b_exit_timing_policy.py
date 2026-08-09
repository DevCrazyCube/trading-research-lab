#!/usr/bin/env python3
"""B19B — does the CHOICE of exit coordinate change the executable outcome at all?

The evaluation machinery for B19B_EXIT_TIMING_POLICY_PREREGISTRATION, frozen and hash-pinned. This
module implements that document and adds nothing: the eight exit rules, three entry delays, three
cost scenarios, position size, family size and refusal codes are all quoted from it, and the pin is
verified before anything runs.

WHY THE RULES HAVE NO FREE PARAMETERS. The document's own reasoning, which is the reason this study
can exist at all: "a rule with a free numeric cut invites choosing the cut from the answer. Removing
the free parameter removes the temptation mechanically rather than forbidding it in prose." Every
rule here is parameter-free, inherited verbatim, or a member of a fixed grid REPORTED IN FULL with
no member selected. The three drawdown fractions are all reported; none is the answer.

The accepted cost, stated in the document rather than discovered later: genuinely adaptive exit
rules are out of scope. That is deliberate.

WRITTEN BEFORE THE EVALUATION WINDOW EXISTS. Same as B19D: development is burned or synthetic only,
the fresh window is read once, later, and a test asserts this module names no path to it.

NO FLOAT ANYWHERE. The drawdown fractions are exact rationals compared by CROSS-MULTIPLICATION --
`realizable * denominator <= peak * numerator` -- never by dividing. A fraction evaluated as a float
would make the trigger depend on binary rounding at the boundary, which is precisely where it fires.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PREREG = ROOT / "research" / "B19B_EXIT_TIMING_POLICY_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "80017c689b69d986263920cfad20fdbf61fb1b29cf33f876c0fd917525bac6e7"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B10A = _load("b10a_simulator_kernel", "b10a_simulator_kernel.py")
B15M = _load("b15m_liquidity_capacity", "b15m_liquidity_capacity.py")


class ExitRefused(RuntimeError):
    """A cell that cannot be evaluated. Always one of the document's own codes."""


# ------------------------------------------------------------------------------------------------
# Quoted from the frozen document. Nothing below is a choice made here.
# ------------------------------------------------------------------------------------------------

POSITION = 100_000_000                      # 0.1 SOL, fixed from B10a onward; not varied here
ENTRY_DELAYS = (1, 2, 4)                    # B15D_SHADOW_ROUTE_V1, inherited unchanged

SCENARIOS = (
    {"scenario_id": "optimistic", "base_fee_lamports": 5000, "priority_fee_lamports": 1000,
     "tip_lamports": 0, "ata_rent_lamports": 2039280, "failed_attempts": 0},
    {"scenario_id": "base", "base_fee_lamports": 5000, "priority_fee_lamports": 100000,
     "tip_lamports": 0, "ata_rent_lamports": 2039280, "failed_attempts": 0},
    {"scenario_id": "stressed", "base_fee_lamports": 5000, "priority_fee_lamports": 1000000,
     "tip_lamports": 0, "ata_rent_lamports": 2039280, "failed_attempts": 1},
)

# The eight rules, complete. No rule may be added, removed or reparameterised after any outcome.
# The three drawdown fractions are a FIXED GRID reported in full -- none is selected, and selecting
# one after seeing results is the failure the grid exists to prevent.
EXIT_RULES = (
    {"rule_id": "E_FIXED_H1000", "kind": "slot_horizon", "slots": 1_000},
    {"rule_id": "E_FIXED_H10000", "kind": "slot_horizon", "slots": 10_000},
    {"rule_id": "E_FIRST_OBSERVATION", "kind": "first_observation"},
    {"rule_id": "E_FIRST_EXTERNALLY_PAYABLE", "kind": "first_externally_payable"},
    {"rule_id": "E_COMPLETE_OR_HORIZON", "kind": "complete_or_horizon", "slots": 10_000},
    {"rule_id": "E_PEAK_DRAWDOWN_1_10", "kind": "peak_drawdown", "numerator": 1, "denominator": 10},
    {"rule_id": "E_PEAK_DRAWDOWN_1_4", "kind": "peak_drawdown", "numerator": 1, "denominator": 4},
    {"rule_id": "E_PEAK_DRAWDOWN_1_2", "kind": "peak_drawdown", "numerator": 1, "denominator": 2},
)

X_NOT_IN_B15M_UNIVERSE = "X_NOT_IN_B15M_UNIVERSE"
X_NO_ENTRY_OBSERVATION = "X_NO_ENTRY_OBSERVATION"
X_RULE_NEVER_TRIGGERED = "X_RULE_NEVER_TRIGGERED"
X_EXIT_UNPRICEABLE = "X_EXIT_UNPRICEABLE"
X_CAPACITY_REFUSED = "X_CAPACITY_REFUSED"
X_ENTRY_UNPRICEABLE = "X_ENTRY_UNPRICEABLE"
X_COMPLETE_AT_ENTRY = "X_COMPLETE_AT_ENTRY"
REFUSAL_CODES = (X_NOT_IN_B15M_UNIVERSE, X_NO_ENTRY_OBSERVATION, X_RULE_NEVER_TRIGGERED,
                 X_EXIT_UNPRICEABLE, X_CAPACITY_REFUSED, X_ENTRY_UNPRICEABLE, X_COMPLETE_AT_ENTRY)

FAMILY_SIZE = len(EXIT_RULES) * len(ENTRY_DELAYS)
PRIMARY = {"delay": 1, "scenario_id": "base",
           "figure": "exact integer median net outcome per rule"}


def verify_preregistration(path=PREREG, expected=PREREG_CANONICAL_SHA256):
    document = json.loads(pathlib.Path(path).read_bytes())
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise ExitRefused(
            f"the B19B preregistration hashes {actual}, pinned {expected}. A study may not run "
            "against a specification that has changed since it was frozen")
    declared = document["multiplicity"]["family_size"]
    if FAMILY_SIZE != declared:
        raise ExitRefused(
            f"this module crosses {len(EXIT_RULES)} rules with {len(ENTRY_DELAYS)} delays, but the "
            f"document declares a family of {declared}")
    frozen = [rule["rule_id"] for rule in document["frozen_exit_rules"]["set"]]
    if [rule["rule_id"] for rule in EXIT_RULES] != frozen:
        raise ExitRefused("the rule set does not match the frozen list, in content or in order")
    return document


# ------------------------------------------------------------------------------------------------
# Path helpers, canonical order
# ------------------------------------------------------------------------------------------------

def first_at_or_after(path, slot):
    for observation in path:
        if observation["slot"] >= slot:
            return observation
    return None


def state_in_force(path, slot):
    """B10c STATE-IN-FORCE: the last observation at or BEFORE the coordinate."""
    chosen = None
    for observation in path:
        if observation["slot"] <= slot:
            chosen = observation
        else:
            break
    return chosen


def _state(observation):
    return {"virtual_quote": observation["virtual_quote"],
            "virtual_token": observation["virtual_token"],
            "real_quote": observation["real_quote"], "real_token": observation["real_token"],
            "quote_mint": observation["quote_mint"], "mayhem_mode": observation["mayhem_mode"],
            "complete": observation["complete"], "slot": observation["slot"]}


def realizable_external_quote(observation, tokens, schedule, policy):
    """What the OBSERVED external book would pay for the held position, or None.

    External-only and our own buy's contribution is NOT carried forward: pricing an exit against
    liquidity our own entry supplied would let the position pay for itself.
    """
    state = _state(observation)
    if state["complete"]:
        return None
    if not B15M.is_admissible(state, state, POSITION):
        return None
    try:
        sold = B10A.price_exit(state, tokens, schedule, policy)
    except Exception:                                                     # noqa: BLE001
        return None
    if sold.get("status") != B10A.STATUS_PRICED:
        return None
    return sold["lamports_into_wallet"]


# ------------------------------------------------------------------------------------------------
# The eight rules. Each returns the exit observation, or None meaning the rule never triggered.
# ------------------------------------------------------------------------------------------------

def select_exit(rule, path, entry, tokens, schedule, policy):
    index = path.index(entry)
    after = path[index + 1:]

    if rule["kind"] == "slot_horizon":
        target = entry["slot"] + rule["slots"]
        if path[-1]["slot"] < target:
            return None                      # right-censored under this rule
        return state_in_force(path, target)

    if rule["kind"] == "first_observation":
        return after[0] if after else None

    if rule["kind"] == "first_externally_payable":
        # B15m used external payability as an ADMISSIBILITY GATE at a fixed horizon; here the same
        # predicate is a TIMING TRIGGER. Same arithmetic, different use -- and that difference is
        # the question this rule exists to ask.
        for observation in path[index:]:
            if realizable_external_quote(observation, tokens, schedule, policy) is not None:
                return observation
        return None

    if rule["kind"] == "complete_or_horizon":
        target = entry["slot"] + rule["slots"]
        for observation in after:
            if observation["slot"] > target:
                break
            if observation["complete"]:
                return observation
        if path[-1]["slot"] < target:
            return None
        return state_in_force(path, target)

    if rule["kind"] == "peak_drawdown":
        # EXACT RATIONAL, BY CROSS-MULTIPLICATION. `realizable * denominator <= peak * numerator`
        # rather than `realizable / peak <= numerator / denominator`. A float comparison would make
        # the trigger depend on binary rounding exactly at the boundary, which is where it fires.
        peak = None
        for observation in after:
            realizable = realizable_external_quote(observation, tokens, schedule, policy)
            if realizable is None:
                continue
            if peak is None or realizable > peak:
                peak = realizable
            if peak is not None and realizable * rule["denominator"] <= peak * rule["numerator"]:
                return observation
        return None

    raise ExitRefused(f"unknown rule kind {rule['kind']!r}")


def evaluate_cell(rule, path, signal_slot, delay, schedule, policy, size=POSITION):
    """One (rule, delay, scenario) cell. Exact integer lamports, or a documented refusal."""
    entry = first_at_or_after(path, signal_slot + delay)
    if entry is None:
        raise ExitRefused(X_NO_ENTRY_OBSERVATION)
    if entry["complete"]:
        raise ExitRefused(X_COMPLETE_AT_ENTRY)
    entry_state = _state(entry)
    try:
        bought = B10A.price_entry(entry_state, {"side": B10A.BUY, "quote_lamports": size},
                                  schedule, policy)
    except Exception as error:                                            # noqa: BLE001
        raise ExitRefused(X_ENTRY_UNPRICEABLE) from error
    tokens = bought["tokens_out"]
    exit_ = select_exit(rule, path, entry, tokens, schedule, policy)
    if exit_ is None:
        raise ExitRefused(X_RULE_NEVER_TRIGGERED)
    exit_state = _state(exit_)
    if not B15M.is_admissible(entry_state, exit_state, size):
        raise ExitRefused(X_CAPACITY_REFUSED)
    try:
        sold = B10A.price_exit(exit_state, tokens, schedule, policy)
    except Exception as error:                                            # noqa: BLE001
        raise ExitRefused(X_EXIT_UNPRICEABLE) from error
    if sold.get("status") != B10A.STATUS_PRICED:
        raise ExitRefused(X_EXIT_UNPRICEABLE)
    return sold["lamports_into_wallet"] - bought["lamports_out_of_wallet"]


# ------------------------------------------------------------------------------------------------
# Reporting -- identical discipline to B19D, deliberately
# ------------------------------------------------------------------------------------------------

def order_statistic(values, numerator, denominator):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) * numerator // denominator]


def exact_median(values):
    """Lower median by integer index. NEVER a mean."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


def summarise(outcomes, refusals, cohort_size):
    censored = refusals.get(X_RULE_NEVER_TRIGGERED, 0)
    coverage = {
        "cohort_size": cohort_size,
        "cells_admitted": len(outcomes),
        "cells_refused": sum(refusals.values()),
        "refused_by_code": {code: refusals.get(code, 0) for code in REFUSAL_CODES
                            if refusals.get(code)},
        "censored_rule_never_triggered": censored,
    }
    if not outcomes:
        return {"coverage": coverage, "outcome": None,
                "note": "no admissible cells; there is no outcome to report"}
    positives = [value for value in outcomes if value > 0]
    top = sorted(positives, reverse=True)[:max(1, len(positives) // 20)]
    return {
        "coverage": coverage,
        "outcome": {
            "min": min(outcomes), "p10": order_statistic(outcomes, 1, 10),
            "p25": order_statistic(outcomes, 1, 4), "median": exact_median(outcomes),
            "p75": order_statistic(outcomes, 3, 4), "p90": order_statistic(outcomes, 9, 10),
            "max": max(outcomes),
            "at_or_below_zero": sum(1 for value in outcomes if value <= 0),
            "top_5pct_share_of_positive_numerator": sum(top),
            "top_5pct_share_of_positive_denominator": sum(positives),
        },
        "not_a_return": ("no figure here is a return, a profit, an expected value or a "
                         "performance result, and none may be described as one"),
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
            "exit_rules": [rule["rule_id"] for rule in EXIT_RULES],
            "delays": list(ENTRY_DELAYS),
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
