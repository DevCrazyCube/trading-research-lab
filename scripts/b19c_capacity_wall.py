#!/usr/bin/env python3
"""B19C — above the 0.1 SOL ceiling, is external-liquidity capacity a CLIFF or a SLOPE?

The evaluation machinery for B19C_CAPACITY_WALL_SIZE_DEPENDENCE_PREREGISTRATION, frozen and
hash-pinned. Every constant below is quoted from that document and the pin is checked before
anything runs.

NO FORMULA IS REIMPLEMENTED HERE, and that is the document's instruction rather than a convenience.
B15M already computes external capacity, proves the result maximal, verifies the prefix shape and
cross-checks against B10b's max_executable_tokens -- all parameterised by a ceiling. This study is
B15M's arithmetic with ONE number changed: the search interval's upper end, 100000000 -> 10000000000,
exactly 100x. Rewriting the search here would create a second implementation to keep in agreement
with the first, and the differential test would then be comparing two of my own mistakes.

THE CEILING IS A CEILING, NOT A TARGET. A cell reaching 10 SOL is reported as CAP-HIT AT THE NEW
CEILING with its true capacity stated as UNMEASURED ABOVE IT -- never as equal to it. That is the
same discipline B15M applied one level down, and the reason the old study's cap-hit cells are the
entire subject of this one: a bound reported as a value is a number that looks measured and is not.

NOT A SIZING PROPOSAL. No order of any size is proposed, recommended or implied. The frozen position
remains 100000000 lamports and this study does not vary it. The grid measures what the observed book
could have absorbed; it does not suggest trading any of those amounts.

WRITTEN BEFORE THE EVALUATION WINDOW EXISTS, like B19B and B19D.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PREREG = ROOT / "research" / "B19C_CAPACITY_WALL_SIZE_DEPENDENCE_PREREGISTRATION.json"
PREREG_CANONICAL_SHA256 = "519102ba451da9c8556ce321c992312ddbeb5f9b7ab99d3dd9bfa10f976b76fe"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B15M = _load("b15m_liquidity_capacity", "b15m_liquidity_capacity.py")


class CapacityRefused(RuntimeError):
    """A cell that cannot be measured. Always one of the document's own codes."""


# ------------------------------------------------------------------------------------------------
# Quoted from the frozen document
# ------------------------------------------------------------------------------------------------

NEW_CEILING = 10_000_000_000          # 10 SOL, a round decimal landmark two orders above the size
OLD_CEILING = 100_000_000             # B15M's ceiling, retained so the two studies can be compared
POSITION = 100_000_000                # frozen and NOT varied here

# B15M's grid extended upward by the same round decimal-and-half-decimal pattern it already used.
# The first three members are B15M's own, retained so the two studies read against each other.
GRID = (1_000_000, 10_000_000, 100_000_000, 500_000_000, 1_000_000_000, 5_000_000_000,
        10_000_000_000)

ENTRY_DELAYS = (1, 2, 4)
EXIT_HORIZONS = ("h_1000_slots", "h_10000_slots")

SCENARIOS = (
    {"scenario_id": "optimistic", "base_fee_lamports": 5000, "priority_fee_lamports": 1000,
     "tip_lamports": 0, "ata_rent_lamports": 2039280, "failed_attempts": 0},
    {"scenario_id": "base", "base_fee_lamports": 5000, "priority_fee_lamports": 100000,
     "tip_lamports": 0, "ata_rent_lamports": 2039280, "failed_attempts": 0},
    {"scenario_id": "stressed", "base_fee_lamports": 5000, "priority_fee_lamports": 1000000,
     "tip_lamports": 0, "ata_rent_lamports": 2039280, "failed_attempts": 1},
)

W_NOT_IN_B15M_UNIVERSE = "W_NOT_IN_B15M_UNIVERSE"
W_NON_MONOTONE = "W_NON_MONOTONE"
W_MAXIMALITY_UNPROVEN = "W_MAXIMALITY_UNPROVEN"
W_CONSTRAINT_VIOLATED = "W_CONSTRAINT_VIOLATED"
W_DISAGREES_WITH_B15M = "W_DISAGREES_WITH_B15M"
W_IMPOSSIBLE_RESERVES = "W_IMPOSSIBLE_RESERVES"
W_FLOAT_PRESENT = "W_FLOAT_PRESENT"
W_DIFFERENTIAL_DISAGREEMENT = "W_DIFFERENTIAL_DISAGREEMENT"
REFUSAL_CODES = (W_NOT_IN_B15M_UNIVERSE, W_NON_MONOTONE, W_MAXIMALITY_UNPROVEN,
                 W_CONSTRAINT_VIOLATED, W_DISAGREES_WITH_B15M, W_IMPOSSIBLE_RESERVES,
                 W_FLOAT_PRESENT, W_DIFFERENTIAL_DISAGREEMENT)

# Required VERBATIM beside every figure. Reproduced here so it cannot drift from the document, and
# checked against it at verification time.
CENSORING_STATEMENT = (
    "conditioned on cells where BOTH an entry and an exit account checkpoint exist; B15f schedules "
    "from B15a, which B15k measured holding 29% of the launches B15i observes, so this population "
    "is censored by the recorders and not by the market")


def verify_preregistration(path=PREREG, expected=PREREG_CANONICAL_SHA256):
    document = json.loads(pathlib.Path(path).read_bytes())
    actual = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != expected:
        raise CapacityRefused(
            f"the B19C preregistration hashes {actual}, pinned {expected}")
    ceiling = document["the_raised_ceiling"]
    if NEW_CEILING != ceiling["new_search_ceiling_lamports"]:
        raise CapacityRefused(
            f"this module searches to {NEW_CEILING}, the document freezes "
            f"{ceiling['new_search_ceiling_lamports']}")
    if OLD_CEILING != ceiling["old_ceiling_lamports"]:
        raise CapacityRefused("the old ceiling does not match the document")
    if list(GRID) != document["the_wall_shape"]["grid_lamports"]:
        raise CapacityRefused("the grid does not match the frozen grid")
    if CENSORING_STATEMENT != document["reporting"]["censoring_statement_required_verbatim"]:
        raise CapacityRefused(
            "the censoring statement has drifted from the document's verbatim text. It is required "
            "beside every figure, so a paraphrase would misdescribe what the population is")
    return document


def assert_integer(label, value):
    """W_FLOAT_PRESENT is a refusal code, so a non-integer is a documented failure, not a crash."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise CapacityRefused(f"{W_FLOAT_PRESENT}: {label} is {type(value).__name__}")
    return value


# ------------------------------------------------------------------------------------------------
# The primary estimand
# ------------------------------------------------------------------------------------------------

def capacity(entry, exit_state, ceiling=NEW_CEILING, prefix_check=None):
    """The greatest q whose tokens can be sold in full against the OBSERVED exit state.

    B15M's own search, maximality proof, prefix verification and B10b differential, called with the
    raised ceiling. Every guarantee is B15M's; nothing is re-derived, and the differential therefore
    compares two INDEPENDENT routes rather than two copies of the same mistake.

    Monotonicity is VERIFIED per cell rather than assumed. The document is explicit that bisection
    is used only if the prefix shape holds, and B15M's own history is the reason: a bisection whose
    precondition is inherited by argument rather than checked is a search that can silently return
    a non-maximal answer on the one cell where the argument does not apply.
    """
    try:
        B15M.assert_reserves_possible(entry, "entry")
        B15M.assert_reserves_possible(exit_state, "exit")
    except Exception as error:                                            # noqa: BLE001
        raise CapacityRefused(f"{W_IMPOSSIBLE_RESERVES}: {error}") from error
    # DEFAULT IS THE SCAN, and it stays the scan. B19C_CAPACITY_WALL_SIZE_DEPENDENCE_V1 is frozen
    # and unspent; nothing here changes what it does. B19G_CAPACITY_WALL_HISTORICAL_V3 passes
    # B15M.assert_prefix_shape_by_theorem explicitly, because the scan cannot run at this ceiling
    # at all -- ten billion evaluations per cell. A caller that passes nothing gets the brute force.
    check = B15M.assert_prefix_shape if prefix_check is None else prefix_check
    try:
        check(entry, exit_state, ceiling)
    except Exception as error:                                            # noqa: BLE001
        raise CapacityRefused(f"{W_NON_MONOTONE}: {error}") from error
    found = B15M.external_capacity(entry, exit_state, ceiling)
    assert_integer("capacity", found)
    if found > 0 and not B15M.is_admissible(entry, exit_state, found):
        raise CapacityRefused(W_CONSTRAINT_VIOLATED)
    try:
        B15M.assert_maximal(entry, exit_state, found, ceiling)
    except Exception as error:                                            # noqa: BLE001
        raise CapacityRefused(f"{W_MAXIMALITY_UNPROVEN}: {error}") from error
    other = B15M.capacity_via_b10b(entry, exit_state, ceiling)
    if other != found:
        raise CapacityRefused(
            f"{W_DIFFERENTIAL_DISAGREEMENT}: the q-side search returned {found} and the B10b "
            f"token-side route returned {other}; the two must agree exactly on every cell")
    return found


def cap_hit(value, ceiling=NEW_CEILING):
    """A bound is not a measurement. True means the true capacity is UNMEASURED ABOVE the ceiling."""
    return value >= ceiling


def reproduces_b15m(entry, exit_state):
    """Every cell whose B15M capacity was strictly below the OLD ceiling must reproduce it exactly.

    Raising the interval's upper end may not change an answer that was already interior to the
    smaller interval. If it does, the search depends on its bound, which would invalidate both.
    """
    old = B15M.external_capacity(entry, exit_state, OLD_CEILING)
    if old >= OLD_CEILING:
        return None                       # was cap-hit under the old ceiling; nothing to reproduce
    new = B15M.external_capacity(entry, exit_state, NEW_CEILING)
    if new != old:
        raise CapacityRefused(
            f"{W_DISAGREES_WITH_B15M}: a sub-ceiling cell measured {old} at the old ceiling and "
            f"{new} at the raised one")
    return old


def grid_executability(entry, exit_state, grid=GRID):
    """For each frozen size, whether the observed book could absorb it. Counts, not an adjective.

    "cliff_versus_slope_is_reported_not_concluded" -- the study states the counts at each size and
    lets a reader do the reading. No size is selected, ranked or called optimal.
    """
    return {size: bool(B15M.is_admissible(entry, exit_state, size)) for size in grid}


# ------------------------------------------------------------------------------------------------
# Reporting
# ------------------------------------------------------------------------------------------------

def order_statistic(values, numerator, denominator):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) * numerator // denominator]


def exact_median(values):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


def summarise(capacities, refusals, grid_counts, previously_cap_hit=None):
    """Counts first, then order statistics, with the censoring statement attached verbatim."""
    measured = [value for value in capacities if not cap_hit(value)]
    counts = {
        "cells": len(capacities) + sum(refusals.values()),
        "zero_capacity_cells": sum(1 for value in capacities if value == 0),
        "cap_hit_at_old_ceiling": sum(1 for value in capacities if value >= OLD_CEILING),
        "cap_hit_at_new_ceiling": sum(1 for value in capacities if cap_hit(value)),
        "newly_measured_cells": sum(1 for value in capacities
                                    if OLD_CEILING <= value < NEW_CEILING),
        "refusals_by_code": {code: refusals.get(code, 0) for code in REFUSAL_CODES
                             if refusals.get(code)},
    }
    report = {
        "counts": counts,
        "grid_executable_counts": dict(grid_counts),
        "censoring": CENSORING_STATEMENT,
        "ceiling_is_not_a_value": (
            "a cell at the ceiling is CAP-HIT; its true capacity is unmeasured above "
            f"{NEW_CEILING} and is never reported as equal to it"),
        "not_a_sizing_proposal": (
            "no order of any size is proposed, recommended or implied; the frozen position "
            f"remains {POSITION} lamports and is not varied here"),
    }
    if measured:
        report["capacity_order_statistics_measured_only"] = {
            "min": min(measured), "p10": order_statistic(measured, 1, 10),
            "p25": order_statistic(measured, 1, 4), "median": exact_median(measured),
            "p75": order_statistic(measured, 3, 4), "p90": order_statistic(measured, 9, 10),
            "max": max(measured),
            "note": "cap-hit cells are EXCLUDED from these statistics, because including a bound "
                    "as though it were a value would understate the upper tail by construction",
        }
    if previously_cap_hit is not None:
        # "this subgroup is the entire reason the study exists, and mixing it into the whole-
        # population distribution would hide the answer inside the question"
        still = [value for value in previously_cap_hit if cap_hit(value)]
        now = [value for value in previously_cap_hit if not cap_hit(value)]
        report["previously_cap_hit_subgroup"] = {
            "cells": len(previously_cap_hit),
            "still_cap_hit_at_the_raised_ceiling": len(still),
            "now_measured": len(now),
            "measured_capacity_order_statistics": {
                "min": min(now), "p25": order_statistic(now, 1, 4),
                "median": exact_median(now), "p75": order_statistic(now, 3, 4),
                "max": max(now),
            } if now else None,
        }
    return report


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
            "new_ceiling_lamports": NEW_CEILING,
            "old_ceiling_lamports": OLD_CEILING,
            "grid_lamports": list(GRID),
            "delays": list(ENTRY_DELAYS),
            "horizons": list(EXIT_HORIZONS),
            "scenarios": [s["scenario_id"] for s in SCENARIOS],
            "refusal_codes": list(REFUSAL_CODES),
            "censoring_statement": CENSORING_STATEMENT,
        }, indent=2))
        return 0
    parser.error("the evaluation pass is not wired to a window here; --verify is offline only")


if __name__ == "__main__":
    sys.exit(main())
