#!/usr/bin/env python3
"""B11b metrics — the frozen baseline metric set over B10c label rows.

Offline, read-only, no network. Pure library: no model fitting, no server, no UI, no live RPC, no
signing. Freeze: `research/B11B_BASELINE_EVALUATION_PREREGISTRATION.json`.

TWO PROPERTIES CARRY THIS FILE
==============================

**The denominator is always the whole cohort.** A vetoed curve, a curve no policy entered, a curve
the pipeline declined, and a horizon whose value is unobservable are all counted, and all contribute
zero deployed capital. Narrowing the cohort to the rows that happen to carry a value is the
commonest way a backtest flatters itself; `assert_denominator_preserved` refuses a census that does
not sum to the cohort.

**Absence is never quietly a loss.** A right-censored, structurally-unavailable or
no-observed-state row has a NULL value and never enters a mean. What is offered instead is an
explicit, labelled `worst_case_lower_bound_return` in which every entered-but-unmarked position is
assigned a total loss. That is a BOUND and is named as one. There is no matching upper bound: an
unobserved value is bounded below by zero and not above.

NO FLOAT, ANYWHERE
==================

Every ratio is an exact reduced integer pair and every comparison is a cross-multiplication. The
median of an even-sized set of rationals is `(ad + cb) / (2bd)`, which is exact. `float` does not
appear in this module and a test walks the output to prove it.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B11B = _load("b11b_t0_features", "b11b_t0_features.py")
B10C = _load("b10c_outcome_labels", "b10c_outcome_labels.py")
B10B = B11B.B10B
ContractRefused = B11B.ContractRefused

METRIC_SET_VERSION = "1.0.0"

# Per-policy disposition. `not_entered_by_policy` is separate from B10c's `no_decision`: the
# pipeline declining a curve and a policy declining an eligible curve are different facts, and
# merging them would hide which of the two a result depends on.
BUCKET_MARKED = "marked_at_horizon"
BUCKET_RIGHT_CENSORED = "right_censored"
BUCKET_STRUCTURAL = "structural_exit_unavailable"
BUCKET_NO_OBSERVED = "no_observed_state_in_window"
BUCKET_NO_DECISION = "no_decision"
BUCKET_NOT_ENTERED = "not_entered_by_policy"
BUCKETS = (BUCKET_MARKED, BUCKET_RIGHT_CENSORED, BUCKET_STRUCTURAL, BUCKET_NO_OBSERVED,
           BUCKET_NO_DECISION, BUCKET_NOT_ENTERED)


# --------------------------------------------------------------------------------------------
# Exact rationals, built by hand so the absence of float is visible rather than trusted
# --------------------------------------------------------------------------------------------

def reduce_rational(numerator, denominator):
    if denominator == 0:
        raise ContractRefused("a rational with a zero denominator is not a number")
    if denominator < 0:
        numerator, denominator = -numerator, -denominator
    divisor = math.gcd(abs(numerator), denominator)
    return numerator // divisor, denominator // divisor


def rational_less(left, right):
    """`a/b < c/d` by cross-multiplication. Both denominators are positive after reduction."""
    return left[0] * right[1] < right[0] * left[1]


def rational_mean(left, right):
    return reduce_rational(left[0] * right[1] + right[0] * left[1], 2 * left[1] * right[1])


def rational_median(values):
    """Exact median of a list of `(numerator, denominator)` pairs, or None when empty."""
    if not values:
        return None
    ordered = sorted(values, key=_RationalKey)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return reduce_rational(*ordered[middle])
    return rational_mean(reduce_rational(*ordered[middle - 1]), reduce_rational(*ordered[middle]))


class _RationalKey:
    """Ordering by cross-multiplication. `sort` needs a key object; it must not become a float."""

    __slots__ = ("value",)

    def __init__(self, value):
        self.value = reduce_rational(*value)

    def __lt__(self, other):
        return rational_less(self.value, other.value)


# --------------------------------------------------------------------------------------------
# The metric set
# --------------------------------------------------------------------------------------------

def evaluate(rows, *, policy_id, horizon_name, entered_mints, split_keys, cohort_curves,
             label_semantics=B11B.LABEL_SEMANTICS):
    """Every frozen metric for one policy at one horizon.

    `rows` are B10c label rows for exactly this horizon, one per curve in the cohort. `entered_mints`
    is the set the policy chose at t0; a curve outside it is `not_entered_by_policy`, which is
    counted, never dropped.
    """
    if label_semantics != B11B.LABEL_SEMANTICS:
        raise ContractRefused(
            f"label semantics {label_semantics!r} is not {B11B.LABEL_SEMANTICS!r}. B10c values a "
            "slot horizon at the LAST observation at or before t0+H; b10b's exit rule fires at the "
            "FIRST reachable exit at or after it. Reporting one under the other's name would be a "
            "different quantity wearing the same label")
    if policy_id not in B11B.POLICY_IDS:
        raise ContractRefused(f"unknown policy {policy_id!r}")
    rows = list(rows)
    for row in rows:
        if row["horizon_name"] != horizon_name:
            raise ContractRefused(
                f"row for horizon {row['horizon_name']!r} passed to a {horizon_name!r} evaluation")

    census = {bucket: 0 for bucket in BUCKETS}
    marked, entered_unmarked = [], []
    deployed = 0
    for row in rows:
        if row["outcome_status"] == B10C.OUTCOME_NO_DECISION:
            census[BUCKET_NO_DECISION] += 1
            continue
        if row["mint"] not in entered_mints:
            census[BUCKET_NOT_ENTERED] += 1
            continue
        deployed += row["entry_outlay_lamports"]
        if row["outcome_status"] == B10C.OUTCOME_MARKED:
            census[BUCKET_MARKED] += 1
            marked.append(row)
        else:
            census[{B10C.OUTCOME_RIGHT_CENSORED: BUCKET_RIGHT_CENSORED,
                    B10C.OUTCOME_STRUCTURAL_UNAVAILABLE: BUCKET_STRUCTURAL,
                    B10C.OUTCOME_NO_OBSERVED_STATE: BUCKET_NO_OBSERVED}[row["outcome_status"]]] += 1
            entered_unmarked.append(row)

    net_total = sum(r["realizable_net_lamports"] - r["entry_outlay_lamports"] for r in marked)
    capital_marked = sum(r["capital_denominator_lamports"] for r in marked)
    capital_unmarked = sum(r["entry_outlay_lamports"] for r in entered_unmarked)

    metrics = {
        "metric_set_version": METRIC_SET_VERSION,
        "model_family": B11B.MODEL_FAMILY,
        "label_semantics": label_semantics,
        "policy_id": policy_id,
        "horizon_name": horizon_name,
        "is_primary": (policy_id == B11B.PRIMARY_POLICY
                       and horizon_name == B11B.PRIMARY_HORIZON),
        "cohort_curves": cohort_curves,
        "disposition_census": census,
        "entered_positions": census[BUCKET_MARKED] + census[BUCKET_RIGHT_CENSORED]
                             + census[BUCKET_STRUCTURAL] + census[BUCKET_NO_OBSERVED],
        "deployed_capital_lamports": deployed,
        "total_net_lamports": net_total,
        "capital_weighted_net_return": (
            None if capital_marked == 0 else list(reduce_rational(net_total, capital_marked))),
        "worst_case_lower_bound_return": (
            None if capital_marked + capital_unmarked == 0 else
            list(reduce_rational(net_total - capital_unmarked,
                                 capital_marked + capital_unmarked))),
        "worst_case_lower_bound_note":
            "every entered position without an observed value counted as a total loss. A BOUND, "
            "not an estimate. No upper bound exists: an unobserved value is bounded below by zero "
            "and not above",
        "median_position_return": _as_list(rational_median(
            [(r["net_return_numerator"], r["net_return_denominator"]) for r in marked])),
        "median_position_max_drawdown": _as_list(rational_median(
            [(r["max_drawdown_ratio_numerator"], r["max_drawdown_ratio_denominator"])
             for r in marked if r["max_drawdown_ratio_numerator"] is not None])),
        "worst_position_max_drawdown": _as_list(_rational_max(
            [(r["max_drawdown_ratio_numerator"], r["max_drawdown_ratio_denominator"])
             for r in marked if r["max_drawdown_ratio_numerator"] is not None])),
        "capacity_positions_fully_executable": sum(
            1 for r in marked if r["liquidity_state"] == B10B.L0_FULL),
        "capacity_positions_size_constrained": sum(
            1 for r in marked if r["liquidity_state"] == B10B.L2_SIZE_CONSTRAINED),
        "grouped_uncertainty": _grouped_uncertainty(marked, split_keys),
        "reported_alone_is_forbidden":
            "the return is computed over marked rows only; quoting it without the disposition "
            "census quotes a number conditioned on markedness, and markedness correlates with the "
            "outcomes it describes",
    }
    assert_denominator_preserved(metrics)
    metrics["metrics_sha256"] = hashlib.sha256(
        B10B.canonical_json(metrics).encode("utf-8")).hexdigest()
    return metrics


def _as_list(pair):
    return None if pair is None else list(pair)


def _rational_max(values):
    if not values:
        return None
    best = reduce_rational(*values[0])
    for value in values[1:]:
        candidate = reduce_rational(*value)
        if rational_less(best, candidate):
            best = candidate
    return best


def _grouped_uncertainty(marked, split_keys):
    """Leave-one-group-out jackknife over `creator ∪ user`, assumption-free.

    No distribution is assumed and no interval is claimed. The range says how much of the result
    rests on any single actor cluster, which is exactly the `PLAN.md` promotion criterion that
    results must not be dominated by one creator or wallet cluster.
    """
    groups = {}
    for row in marked:
        key = split_keys.get(row["mint"])
        if key is None:
            raise ContractRefused(
                f"no creator-union-user split key for {row['mint']}; R5 requires the grouping and a "
                "missing key would silently drop a position from the uncertainty estimate")
        groups.setdefault(key, []).append(row)
    if not groups:
        return {"group_count": 0, "largest_group_position_share": None,
                "leave_one_group_out_min_return": None,
                "leave_one_group_out_max_return": None}

    total_net = sum(r["realizable_net_lamports"] - r["entry_outlay_lamports"] for r in marked)
    total_capital = sum(r["capital_denominator_lamports"] for r in marked)
    largest = max(len(rows) for rows in groups.values())

    low = high = None
    for rows in groups.values():
        net = total_net - sum(
            r["realizable_net_lamports"] - r["entry_outlay_lamports"] for r in rows)
        capital = total_capital - sum(r["capital_denominator_lamports"] for r in rows)
        if capital == 0:
            # Removing this group removes the whole book. There is no return to report for that
            # replicate, and inventing one would be the only way to keep the range looking tight.
            continue
        value = reduce_rational(net, capital)
        low = value if low is None or rational_less(value, low) else low
        high = value if high is None or rational_less(high, value) else high
    return {
        "group_count": len(groups),
        "largest_group_position_share": list(reduce_rational(largest, len(marked))),
        "leave_one_group_out_min_return": _as_list(low),
        "leave_one_group_out_max_return": _as_list(high),
    }


def assert_denominator_preserved(metrics):
    """The census must account for every curve in the cohort. No filtering, ever."""
    total = sum(metrics["disposition_census"].values())
    if total != metrics["cohort_curves"]:
        raise ContractRefused(
            f"the disposition census sums to {total} but the cohort has "
            f"{metrics['cohort_curves']} curves. Narrowing the cohort to the rows that carry a "
            "value is the commonest way a backtest flatters itself")
    return True


def assert_no_censored_as_loss(metrics, rows):
    """The headline return must be computed over marked rows only, and nothing else.

    Recomputed independently from the rows rather than checked against the module's own
    intermediate values, so a mistake cannot validate itself.
    """
    marked = [r for r in rows if r["outcome_status"] == B10C.OUTCOME_MARKED
              and r["horizon_name"] == metrics["horizon_name"]]
    census = metrics["disposition_census"]
    if census[BUCKET_MARKED] > len(marked):
        raise ContractRefused(
            f"{census[BUCKET_MARKED]} rows counted as marked but only {len(marked)} are marked at "
            "this horizon; an unobservable outcome has been counted as an observed one")
    unobserved = (census[BUCKET_RIGHT_CENSORED] + census[BUCKET_STRUCTURAL]
                  + census[BUCKET_NO_OBSERVED])
    if unobserved and metrics["capital_weighted_net_return"] == metrics[
            "worst_case_lower_bound_return"]:
        raise ContractRefused(
            "the headline return equals the worst-case bound while unobserved positions exist; "
            "the bound has leaked into the headline and censored rows are being counted as losses")
    return True


def family_table(all_metrics):
    """Every policy x horizon cell, with the single primary marked and the family size declared."""
    cells = [{"policy_id": m["policy_id"], "horizon_name": m["horizon_name"],
              "is_primary": m["is_primary"], "metrics_sha256": m["metrics_sha256"]}
             for m in all_metrics]
    primaries = [c for c in cells if c["is_primary"]]
    if len(primaries) > 1:
        raise ContractRefused(
            f"{len(primaries)} cells claim to be primary; exactly one may be, and it was named "
            "before any result existed")
    return {
        "family_size_declared": B11B.MULTIPLICITY_FAMILY_SIZE,
        "primary": primaries[0] if primaries else None,
        "bonferroni_alpha_if_ever_tested": [5, 100 * B11B.MULTIPLICITY_FAMILY_SIZE],
        "secondary_may_not_be_promoted":
            "every non-primary cell is reported in this table only, and may not become the "
            "headline after the fact",
        "no_test_performed": True,
        "cells": cells,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true")
    args = parser.parse_args(argv)
    if not args.contract:
        parser.error("this module is a library; run `--contract`")
    print(json.dumps({
        "metric_set_version": METRIC_SET_VERSION,
        "buckets": list(BUCKETS),
        "primary": {"policy": B11B.PRIMARY_POLICY, "horizon": B11B.PRIMARY_HORIZON,
                    "metric": B11B.PRIMARY_METRIC},
        "family_size": B11B.MULTIPLICITY_FAMILY_SIZE,
        "label_semantics": B11B.LABEL_SEMANTICS,
        "forbidden_label_semantics": B11B.FORBIDDEN_LABEL_SEMANTICS,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"ContractRefused: {error}", file=sys.stderr)
        sys.exit(2)
