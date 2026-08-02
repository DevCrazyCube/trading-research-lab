"""B14b fixture corpus and structural report — synthetic rows only. No metric is published.

Every row below is invented. No model was fitted, no window is eligible, no real corpus was read and
B11a was never accessed. The gate publishes **counts and checks** — how many rows were paired, how
many bases were published, which refusals fired — and **no metric value and no return
distribution**, because there is nothing to measure and a number here would be read as a result.

The corpus exercises the seams that only appear together: a row where the model produced an outcome
and the baseline did not, a right-censored row that must stay out of every numerator while staying
in every denominator's count, a declined decision that risked nothing, and an equity path that
recovered after a deep fall so a drawdown taken from the endpoints would miss it.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ONE module graph, for the reason B14a's fixtures learned the hard way: a second load gives a
# second set of exception classes, and every `except` here would silently stop matching.
EVAL = _load("b14b_evaluation", "b14b_evaluation.py")
SPLIT = EVAL.SPLIT
ARTIFACT = EVAL.ARTIFACT
B11B = EVAL.B11B
B10B = EVAL.B10B

HORIZON = B11B.PRIMARY_HORIZON
TARGET = "synthetic_target_a"
COST_POLICY = "synthetic_cost_policy_v1"


def rational(numerator, denominator):
    return EVAL.rational(numerator, denominator)


def side(bucket, pnl=None, capital=0, probability=None, label=None, path=None):
    return {"outcome_bucket": bucket, "net_pnl_lamports": pnl,
            "deployed_capital_lamports": capital, "probability": probability,
            "realised_label": label, "equity_path_lamports": path}


def row(row_id, group, model, baseline, order=1_000_000, segment=SPLIT.SEGMENT_TEST,
        fold="fold-1"):
    return {"row_id": row_id, "group_id": group, "fold_id": fold, "segment": segment,
            "horizon_name": HORIZON, "target_id": TARGET, "order_size_lamports": order,
            "cost_policy_id": COST_POLICY, "model": model, "baseline": baseline}


def build_fixture_corpus():
    """A deterministic synthetic corpus, one entry per seam worth exercising."""
    marked = EVAL.BUCKET_MARKED
    rows = []

    # 1. Ordinary paired rows, both sides evaluable, with probabilities and labels so the ranking
    #    and calibration metrics have something to work on.
    for index, (model_pnl, baseline_pnl, numerator, label) in enumerate((
            (250_000, 100_000, 9, 1), (-80_000, -120_000, 7, 0), (400_000, 150_000, 8, 1),
            (-50_000, 20_000, 3, 0), (120_000, 90_000, 6, 1), (-200_000, -60_000, 2, 0))):
        rows.append(row(
            f"paired-{index}", f"group-{index}",
            side(marked, model_pnl, 1_000_000, rational(numerator, 10), label,
                 [0, model_pnl // 2, model_pnl]),
            # The baseline deploys a DIFFERENT amount on purpose: with equal denominators, a
            # return divided by the wrong side's capital is exactly the same number.
            side(marked, baseline_pnl, 800_000)))

    # 2. The model produced an outcome and the baseline did not. Dropping this row silently is how
    #    a comparison cohort gets selected on an outcome of the comparison.
    rows.append(row("model-only", "group-6",
                    side(marked, 300_000, 1_000_000, rational(7, 10), 1, [0, 300_000]),
                    side(EVAL.BUCKET_RIGHT_CENSORED, None, 1_000_000)))

    # 3. The reverse asymmetry, so the report's asymmetry figure is not trivially one-sided.
    rows.append(row("baseline-only", "group-7",
                    side(EVAL.BUCKET_STRUCTURAL_EXIT_UNAVAILABLE, None, 1_000_000),
                    side(marked, 50_000, 1_000_000)))

    # 4. Neither side evaluable: no observed state at all.
    rows.append(row("neither", "group-8",
                    side(EVAL.BUCKET_NO_OBSERVED_STATE, None, 1_000_000),
                    side(EVAL.BUCKET_NO_OBSERVED_STATE, None, 1_000_000)))

    # 5. A decision the policy declined. Nothing was deployed, so nothing can be lost even under
    #    the worst-case rule — which is why `not_entered_by_policy` is not an at-risk bucket.
    rows.append(row("declined", "group-9",
                    side(EVAL.BUCKET_NOT_ENTERED, None, 0),
                    side(EVAL.BUCKET_NOT_ENTERED, None, 0), order=0))

    # 6. An equity path that fell deeply and recovered. Endpoint arithmetic would report no
    #    drawdown at all.
    rows.append(row("recovered", "group-10",
                    side(marked, 10_000, 1_000_000, rational(5, 10), 1,
                         [0, 500_000, -700_000, 10_000]),
                    side(marked, 5_000, 1_000_000)))

    return rows


def build_spec():
    return {
        "preregistration_reference": "synthetic fixture; stands in for a frozen metric family",
        "metric_family_id": "synthetic_family_v1",
        "family_size": B11B.MULTIPLICITY_FAMILY_SIZE,
        "primary_cell": {"policy_id": B11B.PRIMARY_POLICY, "horizon_name": B11B.PRIMARY_HORIZON},
        "secondary_cells": [{"policy_id": "P3_creator_initial_buy_present",
                             "horizon_name": B11B.PRIMARY_HORIZON}],
        "metrics_declared": list(EVAL.METRICS),
        "censoring_treatment": EVAL.CENSORING_EXCLUDED_AND_COUNTED,
        "worst_case_outcome_rule": EVAL.WORST_CASE_TOTAL_LOSS,
        "class_threshold": rational(1, 2),
        "calibration_bin_edges": [rational(0, 1), rational(1, 2), rational(1, 1)],
        "calibration_bin_edges_fitted_on": ["fold-1-train"],
        "multiplicity_adjustment": "bonferroni over the frozen family size; no test is run here",
    }


def build_split_plan(rows):
    """A minimal plan whose groups are exactly the ones the rows name."""
    groups = sorted({r["group_id"] for r in rows})
    return {
        "schema_version": SPLIT.SCHEMA_VERSION,
        "purge_rule": SPLIT.PURGE_RULE, "embargo_rule": SPLIT.EMBARGO_RULE,
        "r5_rule": SPLIT.R5_RULE, "status": SPLIT.STATUS_RESEARCH_PLUMBING_ONLY,
        "target_id": TARGET, "horizon_id": HORIZON, "purge_slots": 50, "embargo_slots": 100,
        "preregistration_reference": "synthetic fixture",
        "folds": [{"fold_id": "fold-1",
                   "ranges": {s: {"first_slot_inclusive": 1, "last_slot_inclusive": 2}
                              for s in SPLIT.SEGMENTS},
                   "rows": {s: [] for s in SPLIT.SEGMENTS},
                   "row_counts": {s: 0 for s in SPLIT.SEGMENTS},
                   "groups": {SPLIT.SEGMENT_TEST: groups,
                              SPLIT.SEGMENT_TRAIN: [], SPLIT.SEGMENT_VALIDATION: []}}],
        "accounting": {}, "exclusions": [], "row_evidence_sha256": "e" * 64,
        "plan_sha256": "p" * 64,
    }


def build_bound_hashes():
    return {"row_evidence_sha256": "r" * 64, "split_plan_sha256": "p" * 64,
            "model_artifact_sha256": "a" * 64, "baseline_record_sha256": "b" * 64,
            "feature_order_sha256": "o" * 64, "label_preregistration_sha256": "l" * 64,
            "metric_spec_sha256": "m" * 64, "code_revision": "synthetic-revision",
            "environment_manifest_sha256": "n" * 64}


def check():
    """Structural counts and checks only. No metric value and no return distribution."""
    rows = build_fixture_corpus()
    spec = build_spec()
    plan = build_split_plan(rows)
    report = EVAL.evaluate(rows, spec, build_bound_hashes(), split_plan=plan)

    out = {
        "schema_version": EVAL.SCHEMA_VERSION,
        "status": report["status"],
        "performance_status": report["performance_status"],
        "rows": report["cohort"]["rows"],
        "groups": report["cohort"]["groups"],
        "paired_rows": report["pairing"]["paired_rows"],
        "model_evaluable_only": report["pairing"]["model_evaluable_only"],
        "baseline_evaluable_only": report["pairing"]["baseline_evaluable_only"],
        "neither_evaluable": report["pairing"]["neither_evaluable"],
        "outcome_bucket_counts": report["metrics"]["cohort_wide"][EVAL.METRIC_COUNTS],
        "bases_published": sorted(b for b in report["metrics"] if b in EVAL.BASES),
        "headline_metrics_on_both_bases": 0,
        "worst_case_never_better_than_observed": False,
        "censored_rows_absent_from_every_numerator": False,
        "declined_rows_risk_nothing": False,
        "drawdown_uses_the_path_not_the_endpoints": False,
        "jackknife_groups": report["grouped_uncertainty"]["groups"],
        "order_independent": False,
        "metric_values_reported": False,
        "metric_values_reported_reason":
            "nothing has been fitted or evaluated against a real window; a figure here would be "
            "read as a result for a model that does not exist",
        "refusals_verified": {},
        "model_fitted": False,
        "b11a_outcomes_read": False,
        "errors": [],
    }

    both = sum(1 for metric in EVAL.HEADLINE_METRICS
               if all(metric in report["metrics"][basis] for basis in EVAL.BASES))
    out["headline_metrics_on_both_bases"] = both
    if both != len(EVAL.HEADLINE_METRICS):
        out["errors"].append({"error": "a headline metric was published on one basis only"})

    observed = report["metrics"][EVAL.BASIS_OBSERVED][EVAL.METRIC_TOTAL_NET_PNL]
    worst = report["metrics"][EVAL.BASIS_WORST_CASE][EVAL.METRIC_TOTAL_NET_PNL]
    out["worst_case_never_better_than_observed"] = (
        worst["model"] <= observed["model"] and worst["baseline"] <= observed["baseline"])
    if not out["worst_case_never_better_than_observed"]:
        out["errors"].append({"error": "the worst case flattered the observed figure"})

    # Every censored row's capital appears in the whole-cohort denominator and its P&L appears in
    # no observed numerator. Checked by rebuilding the sums from the rows.
    censored_capital = sum(r["model"]["deployed_capital_lamports"] for r in rows
                           if r["model"]["outcome_bucket"] in EVAL.AT_RISK_BUCKETS
                           and r["model"]["outcome_bucket"] not in EVAL.EVALUABLE_BUCKETS)
    observed_capital = report["metrics"][EVAL.BASIS_OBSERVED][EVAL.METRIC_DEPLOYED_CAPITAL]["model"]
    worst_capital = report["metrics"][EVAL.BASIS_WORST_CASE][EVAL.METRIC_DEPLOYED_CAPITAL]["model"]
    out["censored_rows_absent_from_every_numerator"] = (
        censored_capital > 0 and worst_capital - observed_capital == censored_capital)
    if not out["censored_rows_absent_from_every_numerator"]:
        out["errors"].append({"error": "censored capital did not move between the two bases"})

    declined = [r for r in rows if r["model"]["outcome_bucket"] == EVAL.BUCKET_NOT_ENTERED]
    out["declined_rows_risk_nothing"] = bool(declined) and all(
        r["model"]["deployed_capital_lamports"] == 0 for r in declined)
    if not out["declined_rows_risk_nothing"]:
        out["errors"].append({"error": "a declined decision deployed capital"})

    recovered = next(r for r in rows if r["row_id"] == "recovered")
    path_drawdown = EVAL.maximum_drawdown(recovered["model"]["equity_path_lamports"])
    endpoints = max(0, recovered["model"]["equity_path_lamports"][0]
                    - recovered["model"]["equity_path_lamports"][-1])
    out["drawdown_uses_the_path_not_the_endpoints"] = path_drawdown > endpoints
    if not out["drawdown_uses_the_path_not_the_endpoints"]:
        out["errors"].append({"error": "the drawdown was taken from the endpoints"})

    shuffled = EVAL.evaluate(list(reversed(rows)), spec, build_bound_hashes(), split_plan=plan)
    out["order_independent"] = shuffled["report_sha256"] == report["report_sha256"]
    if not out["order_independent"]:
        out["errors"].append({"error": "the report depends on row order"})

    refusals = {
        "censoring_recoded_as_loss": lambda: EVAL.assert_metric_spec(
            dict(spec, censoring_treatment="recode_as_loss")),
        "family_size_shrunk": lambda: EVAL.assert_family_binds_frozen_size(
            dict(spec, family_size=2)),
        "secondary_cell_promoted": lambda: EVAL.assert_primary_not_promoted(
            dict(spec, primary_cell=spec["secondary_cells"][0])),
        "paired_cohort_hand_picked": lambda: EVAL.assert_paired_cohort(
            rows, [r["row_id"] for r in rows][:3]),
        "unpublished_calibration_edges": lambda: EVAL.assert_metric_spec(
            dict(spec, calibration_bin_edges_fitted_on=[])),
        "report_claiming_publication_grade": lambda: EVAL.assert_report(
            dict(report, status=EVAL.STATUS_PUBLICATION_GRADE)),
        "report_claiming_performance": lambda: EVAL.assert_report(
            dict(report, performance_status="profitable")),
    }
    for name, thunk in refusals.items():
        try:
            thunk()
            out["refusals_verified"][name] = False
            out["errors"].append({"error": f"{name} was accepted"})
        except EVAL.EvaluationRefused:
            out["refusals_verified"][name] = True

    out["determinism"] = {"report_sha256": report["report_sha256"],
                          "metric_spec_sha256": report["metric_spec_sha256"]}
    return out


def gate_failures(report):
    """Why this run does not pass the gate. Pure, so the gate's own logic can be tested."""
    failures = []
    if report["errors"]:
        failures.append(f"{len(report['errors'])} integrity errors: {report['errors'][:5]}")
    if sorted(report["bases_published"]) != sorted(EVAL.BASES):
        failures.append("both bases must be published")
    if report["headline_metrics_on_both_bases"] != len(EVAL.HEADLINE_METRICS):
        failures.append("every headline metric must appear on both bases")
    for field in ("worst_case_never_better_than_observed",
                  "censored_rows_absent_from_every_numerator", "declined_rows_risk_nothing",
                  "drawdown_uses_the_path_not_the_endpoints", "order_independent"):
        if not report[field]:
            failures.append(f"{field} did not hold")
    if not all(report["refusals_verified"].values()):
        failures.append("a refusal that must fire did not")
    if report["status"] not in EVAL.ATTAINABLE_REPORT_STATUSES:
        failures.append("the report shipped with an unattainable status")
    if report["performance_status"] != ARTIFACT.PERFORMANCE_NOT_EVALUATED:
        failures.append("the report carries a performance claim")
    if report["metric_values_reported"] or report["model_fitted"] \
            or report["b11a_outcomes_read"]:
        failures.append("this pass reports no metric, fits no model and reads no B11a outcome")
    if not report["model_evaluable_only"] or not report["baseline_evaluable_only"]:
        failures.append("no fixture exercised an evaluability asymmetry")
    return failures


def assert_clean():
    report = check()
    failures = gate_failures(report)
    if failures:
        raise EVAL.EvaluationRefused("; ".join(failures))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args(argv)
    report = assert_clean() if args.gate else check()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"EvaluationRefused: {error}", file=sys.stderr)
        sys.exit(2)
