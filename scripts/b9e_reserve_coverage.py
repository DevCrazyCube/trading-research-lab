#!/usr/bin/env python3
"""B9e cohort reserve-coverage gate.

Implements `research/B9E_RESERVE_COVERAGE_PREREGISTRATION.md`. Offline, read-only, no network.

`verify_decoded_artifact` proves that the reserve rows which exist are structurally sound and
continuous. This answers the different question of how much of the frozen cohort has a usable
history at all. The distinction matters because a broken chain does not produce inconsistent rows,
it produces MISSING ones: `advance_curve_chain` refuses to advance past a break, so a
partially-broken curve's surviving observations are perfectly self-consistent and pass every
existing gate. Measuring over "curves that have reserve paths" is therefore measuring over the
curves whose histories happened to survive, which is a selection rule correlated with the very
behaviour under study.

The thresholds are deliberately not defaulted. `assert_reserve_coverage` raises until they are
ratified, because a gate that passes by default is not a gate.
"""
import argparse
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_b9d():
    """Load the B9d module by path, matching how the test suite loads it.

    The scripts directory is a collection of standalone programs rather than a package, so an
    ordinary import would depend on how the interpreter happened to be invoked.
    """
    spec = importlib.util.spec_from_file_location(
        "b9d_transaction_bodies", ROOT / "scripts" / "b9d_transaction_bodies.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B9D = _load_b9d()
FreezeViolation = B9D.FreezeViolation

# The decoder prefixes every reserve-chain outcome with this before persisting it.
RESERVE_CHAIN_PREFIX = "reserve chain: "

# Reason texts produced by `advance_curve_chain`, matched as prefixes because the continuity
# mismatch appends the two disagreeing states. These are pinned by a test that generates each one
# through the real function and asserts the constant still matches, so a rewording in B9d fails the
# B9e suite instead of silently reclassifying broken curves as complete.
LEFT_TRUNCATED_REASON = "first TradeEvent has no preceding CreateEvent anchor"
BREAK_REASONS = (
    "duplicate CreateEvent would replace an existing curve anchor",
    "curve reserve chain was previously broken and cannot be repaired",
    "curve reserve continuity mismatch",
)

# Ordered: the first match wins, so a curve that is both left-truncated and later broken is broken.
STATUSES = ("broken", "left_truncated", "anchored_complete", "absent")


def cohort_curves(b9a_path=None):
    """The frozen cohort's bonding curves, refusing an ambiguous mint -> curve identity."""
    identity = B9D.tradable_cohort_identity(b9a_path or B9D.B9A_PATH)
    curves = set(identity.values())
    if len(curves) != len(identity):
        raise FreezeViolation(
            f"frozen cohort maps {len(identity):,} mints onto {len(curves):,} distinct bonding "
            "curves; reserve coverage cannot be attributed per curve while identity is ambiguous")
    return curves


def chain_failures_by_curve(database):
    """Every persisted reserve-chain failure, grouped by the curve its context names."""
    grouped = {}
    for curve, reason, slot, index, outer, inner in database.execute(
            "SELECT json_extract(context_json,'$.bonding_curve'),reason,"
            "slot,transaction_index,outer_index,inner_index "
            "FROM classification_failure WHERE reason LIKE ?", (RESERVE_CHAIN_PREFIX + "%",)):
        if not curve:
            raise FreezeViolation(
                f"reserve-chain failure at ({slot},{index},{outer},{inner}) names no bonding "
                "curve in its context; the discontinuity cannot be attributed")
        grouped.setdefault(curve, []).append(
            {"reason": reason[len(RESERVE_CHAIN_PREFIX):],
             "coordinates": [slot, index, outer, inner]})
    return grouped


def observations_by_curve(database):
    """Per curve: how many observations exist and whether one of them is a launch anchor.

    An anchor is an observation with a NULL before-state, which is exactly what
    `advance_curve_chain` returns for a `CreateEvent`.
    """
    grouped = {}
    for curve, total, anchors in database.execute(
            "SELECT bonding_curve,count(*),"
            "sum(CASE WHEN virtual_quote_before IS NULL THEN 1 ELSE 0 END) "
            "FROM reserve_observation GROUP BY bonding_curve"):
        grouped[curve] = {"observations": total, "anchored": bool(anchors)}
    return grouped


def classify_curve(curve, observation, failures):
    """Exactly one status per curve, per §3 of the preregistration."""
    reasons = [entry["reason"] for entry in failures]
    if any(reason.startswith(BREAK_REASONS) for reason in reasons):
        return "broken"
    if any(reason.startswith(LEFT_TRUNCATED_REASON) for reason in reasons):
        return "left_truncated"
    if observation:
        if not observation["anchored"]:
            # Not a classification the decoder can produce: a chain that starts without an anchor
            # always records the truncation notice first. Reaching here means the failure row that
            # explains these observations is missing, so the status cannot be established.
            raise FreezeViolation(
                f"curve {curve} has {observation['observations']:,} reserve observation(s) with no "
                "launch anchor and no recorded truncation; its coverage status is unattributable")
        return "anchored_complete"
    return "absent"


def cohort_reserve_coverage(database, b9a_path=None):
    """Classify every frozen cohort curve. The counts must account for the whole cohort."""
    curves = cohort_curves(b9a_path)
    observations = observations_by_curve(database)
    failures = chain_failures_by_curve(database)

    outside = sorted((set(observations) | set(failures)) - curves)
    if outside:
        raise FreezeViolation(
            f"{len(outside):,} curve(s) with reserve evidence are outside the frozen cohort; "
            f"first {outside[0]}")

    statuses = {curve: classify_curve(curve, observations.get(curve), failures.get(curve, []))
                for curve in sorted(curves)}
    counts = {status: 0 for status in STATUSES}
    for curve, status in statuses.items():
        # The real omission risk is a status this tally does not know about: `counts[status] += 1`
        # on an unrecognised key would raise KeyError, and a `.get`-style tally would silently drop
        # the curve from every bucket while the totals still looked plausible. Name it instead.
        if status not in counts:
            raise FreezeViolation(
                f"curve {curve} received unknown coverage status {status!r}; it belongs to no "
                f"bucket and would vanish from the cohort tally")
        counts[status] += 1
    # Structural invariant rather than a live check: `statuses` is keyed by the cohort itself and
    # every curve takes exactly one branch above. Kept so that stops being true loudly.
    if sum(counts.values()) != len(curves):
        raise FreezeViolation(
            f"coverage statuses account for {sum(counts.values()):,} curves, cohort has "
            f"{len(curves):,}")
    return {"cohort_curves": len(curves), "counts": counts, "statuses": statuses,
            "failures": failures}


def assert_reserve_coverage(database, minimum_anchored_complete_fraction=None,
                            eligible_statuses=None, b9a_path=None):
    """Fail closed unless measured coverage satisfies the RATIFIED preregistered thresholds.

    Both parameters default to `None` and raise. A gate whose threshold defaults to something
    permissive passes on the day someone forgets to set it, which is the day it matters.
    """
    if minimum_anchored_complete_fraction is None or eligible_statuses is None:
        raise FreezeViolation(
            "B9e coverage thresholds are not ratified: set minimum_anchored_complete_fraction and "
            "eligible_statuses in research/B9E_RESERVE_COVERAGE_PREREGISTRATION.md §5 before any "
            "measurement consumes these reserve paths")
    eligible = tuple(eligible_statuses)
    unknown = sorted(set(eligible) - set(STATUSES))
    if unknown or not eligible:
        raise FreezeViolation(f"eligible_statuses must be a non-empty subset of {STATUSES}: "
                              f"{list(eligible)}")
    if "broken" in eligible:
        raise FreezeViolation(
            "a broken chain has a hole at a known coordinate; any statistic over it is computed "
            "across a discontinuity, so it can never be eligible")
    if not 0 < minimum_anchored_complete_fraction <= 1:
        raise FreezeViolation(
            "minimum_anchored_complete_fraction must be a fraction in (0, 1]: "
            f"{minimum_anchored_complete_fraction!r}")

    coverage = cohort_reserve_coverage(database, b9a_path)
    total = coverage["cohort_curves"]
    # Denominator is the FULL cohort, never the observed curves. A fraction over observed curves is
    # precisely the biased quantity this gate exists to detect.
    fraction = coverage["counts"]["anchored_complete"] / total
    if fraction < minimum_anchored_complete_fraction:
        raise FreezeViolation(
            f"cohort reserve coverage {fraction:.4f} is below the preregistered minimum "
            f"{minimum_anchored_complete_fraction:.4f}: "
            f"{coverage['counts']['anchored_complete']:,} of {total:,} curves are "
            "anchored_complete")
    coverage["anchored_complete_fraction"] = fraction
    coverage["eligible_statuses"] = list(eligible)
    coverage["eligible_curves"] = sum(count for status, count in coverage["counts"].items()
                                      if status in eligible)
    return coverage


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("artifact", help="path to the B9d evidence artifact (opened read-only)")
    parser.add_argument("--b9a", default=None, help="override the frozen B9a cohort path")
    parser.add_argument("--minimum-anchored-complete", type=float, default=None,
                        help="ratified minimum fraction; omit to measure without gating")
    parser.add_argument("--eligible", default=None,
                        help="comma-separated ratified eligible statuses")
    parser.add_argument("--per-curve", action="store_true",
                        help="include the full per-curve status map")
    args = parser.parse_args(argv)

    database = B9D.connect(args.artifact, readonly=True)
    try:
        if args.minimum_anchored_complete is None and args.eligible is None:
            report = cohort_reserve_coverage(database, args.b9a)
        else:
            report = assert_reserve_coverage(
                database, args.minimum_anchored_complete,
                args.eligible.split(",") if args.eligible else None, args.b9a)
    finally:
        database.close()
    if not args.per_curve:
        report.pop("statuses", None)
        report.pop("failures", None)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FreezeViolation as error:
        print(f"FreezeViolation: {error}", file=sys.stderr)
        sys.exit(2)
