"""B14b — exact model/baseline evaluation harness. Offline, synthetic only. No fitting, no B11a.

What this module is
-------------------
A metric engine in exact integers and gcd-reduced rationals, and the report contract those metrics
must ship in. It consumes validated B14a split plans and model envelopes, B10c label rows and B11b
baseline policy records, and it computes nothing that was not preregistered.

The failure it is built against
-------------------------------
**A headline computed on the rows that happened to be evaluable is survivorship, and it always
flatters.** The rows that fail to produce an outcome are not a random sample: a curve with no
observed state, a structurally unavailable exit and a right-censored horizon are exactly the
positions that went wrong in ways the pipeline could not price. Dropping them and reporting the mean
of what is left answers a question nobody asked.

So every headline figure is published **twice**, side by side and each labelled:

- `observed_evaluable` — the figure over rows that produced an outcome;
- `whole_cohort_worst_case` — the same figure with every unevaluable row assigned the worst
  admissible outcome under the caller's declared rule.

A report carrying only one is refused, and so is one that labels either as the other. The truth
about a cohort is somewhere between them, and how far apart they are is the most informative number
in the report.

Three things absent by design
-----------------------------
1. **No default metric, class threshold, calibration bin edge, censoring treatment or performance
   cutoff.** Every one is the caller's and must arrive with a preregistration reference. There is no
   "good enough" line here, because nobody has earned one.
2. **No float.** Every figure is an integer or a numerator/denominator pair. A rate rounded once is
   a rate nobody can reconcile against the counts it came from.
3. **No claim.** `performance_status` is locked to `not_evaluated` and the report status to
   `synthetic_plumbing_only`; profitable, executable, validated and live are refused by name.

Censoring is never a zero. A right-censored outcome, a structurally unavailable exit and a decision
the policy declined are three different facts, none of them a loss, and each is counted in its own
bucket over the whole cohort.
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


ARTIFACT = _load("b14a_model_artifact", "b14a_model_artifact.py")
SPLIT = ARTIFACT.B14A_SPLIT
B13D = SPLIT.B13F.B13D
B11B = SPLIT.B13F.B11B
B10B = SPLIT.B10B

SCHEMA_VERSION = "1.0.0"

rational = B13D.rational
compare_rationals = B13D.compare_rationals
assert_rational = B13D.assert_rational

HEADLINE_RULE = (
    "Every headline figure is published on TWO bases at once: `observed_evaluable`, over the rows "
    "that produced an outcome, and `whole_cohort_worst_case`, with every unevaluable row assigned "
    "the worst admissible outcome under the caller's declared rule. A figure on one basis may never "
    "be presented as the other, and a report carrying only one is refused. Rows that fail to "
    "produce an outcome are not a random sample — they are the positions that went wrong in ways "
    "the pipeline could not price — so a mean over the survivors answers a question nobody asked.")

# --------------------------------------------------------------------------------------------
# Outcome buckets, inherited from B10c
# --------------------------------------------------------------------------------------------

BUCKET_MARKED = "marked_at_horizon"
BUCKET_RIGHT_CENSORED = "right_censored"
BUCKET_STRUCTURAL_EXIT_UNAVAILABLE = "structural_exit_unavailable"
BUCKET_NO_OBSERVED_STATE = "no_observed_state_in_window"
BUCKET_NO_DECISION = "no_decision"
BUCKET_NOT_ENTERED = "not_entered_by_policy"
BUCKETS = (BUCKET_MARKED, BUCKET_RIGHT_CENSORED, BUCKET_STRUCTURAL_EXIT_UNAVAILABLE,
           BUCKET_NO_OBSERVED_STATE, BUCKET_NO_DECISION, BUCKET_NOT_ENTERED)

# The one bucket that carries a realised figure. Every other is an absence, and each absence is a
# different fact: censored, unpriceable, unobserved, undecided, declined.
EVALUABLE_BUCKETS = (BUCKET_MARKED,)

# Buckets where capital was actually deployed and the outcome is simply not known. Only these can
# lose money under a worst-case rule; a decision the policy declined risked nothing.
AT_RISK_BUCKETS = (BUCKET_MARKED, BUCKET_RIGHT_CENSORED, BUCKET_STRUCTURAL_EXIT_UNAVAILABLE,
                   BUCKET_NO_OBSERVED_STATE)

BASIS_OBSERVED = "observed_evaluable"
BASIS_WORST_CASE = "whole_cohort_worst_case"
BASES = (BASIS_OBSERVED, BASIS_WORST_CASE)

# --------------------------------------------------------------------------------------------
# The metric specification — every field is the caller's
# --------------------------------------------------------------------------------------------

METRIC_DEPLOYED_CAPITAL = "deployed_capital_lamports"
METRIC_TOTAL_NET_PNL = "total_net_pnl_lamports"
METRIC_CAPITAL_WEIGHTED_RETURN = "capital_weighted_return"
METRIC_PAIRED_DIFFERENCE = "paired_model_minus_baseline_pnl_lamports"
METRIC_CONCORDANCE = "pairwise_concordance"
METRIC_BRIER = "brier_score_exact"
METRIC_CALIBRATION = "calibration_bins"
METRIC_MAX_DRAWDOWN = "maximum_drawdown_lamports"
METRIC_EXPOSURE = "capacity_and_exposure"
METRIC_COUNTS = "outcome_bucket_counts"
METRICS = (METRIC_DEPLOYED_CAPITAL, METRIC_TOTAL_NET_PNL, METRIC_CAPITAL_WEIGHTED_RETURN,
           METRIC_PAIRED_DIFFERENCE, METRIC_CONCORDANCE, METRIC_BRIER, METRIC_CALIBRATION,
           METRIC_MAX_DRAWDOWN, METRIC_EXPOSURE, METRIC_COUNTS)

# Metrics whose value is a claim about the cohort, and which therefore need both bases.
HEADLINE_METRICS = (METRIC_TOTAL_NET_PNL, METRIC_CAPITAL_WEIGHTED_RETURN, METRIC_PAIRED_DIFFERENCE)

CENSORING_EXCLUDED_AND_COUNTED = "excluded_and_counted"
CENSORING_TREATMENTS = (CENSORING_EXCLUDED_AND_COUNTED,)
# Named so they can be refused explicitly rather than merely be absent from the list above.
CENSORING_TREATMENTS_REFUSED = ("recode_as_zero", "recode_as_loss", "impute_median",
                                "drop_silently", "carry_forward")

WORST_CASE_TOTAL_LOSS = "total_loss_of_deployed_capital"
WORST_CASE_RULES = (WORST_CASE_TOTAL_LOSS,)

METRIC_SPEC_FIELDS = ("preregistration_reference", "metric_family_id", "family_size",
                      "primary_cell", "secondary_cells", "metrics_declared",
                      "censoring_treatment", "worst_case_outcome_rule", "class_threshold",
                      "calibration_bin_edges", "calibration_bin_edges_fitted_on",
                      "multiplicity_adjustment")

CELL_FIELDS = ("policy_id", "horizon_name")

SIDE_FIELDS = ("outcome_bucket", "net_pnl_lamports", "deployed_capital_lamports", "probability",
               "realised_label", "equity_path_lamports")

# Order size, horizon and cost policy live on the ROW, never on a side. A paired comparison whose
# two sides could differ in those is not a paired comparison, and making them per-side
# unrepresentable is stronger than checking them afterwards.
ROW_FIELDS = ("row_id", "group_id", "fold_id", "segment", "horizon_name", "target_id",
              "order_size_lamports", "cost_policy_id", "model", "baseline")

STATUS_SYNTHETIC_PLUMBING_ONLY = "synthetic_plumbing_only"
STATUS_PUBLICATION_GRADE = "publication_grade"
REPORT_STATUSES = (STATUS_SYNTHETIC_PLUMBING_ONLY, STATUS_PUBLICATION_GRADE)
ATTAINABLE_REPORT_STATUSES = (STATUS_SYNTHETIC_PLUMBING_ONLY,)

REPORT_FIELDS = ("schema_version", "headline_rule", "status", "performance_status",
                 "metric_spec_sha256", "primary_cell", "family_size", "bound_hashes",
                 "cohort", "metrics", "grouped_uncertainty", "pairing", "report_sha256")

BOUND_HASH_FIELDS = ("row_evidence_sha256", "split_plan_sha256", "model_artifact_sha256",
                     "baseline_record_sha256", "feature_order_sha256",
                     "label_preregistration_sha256", "metric_spec_sha256",
                     "code_revision", "environment_manifest_sha256")


class EvaluationRefused(ARTIFACT.ArtifactRefused):
    """Raised when a metric cannot be computed without asserting something untrue."""


class SpecificationMissing(EvaluationRefused):
    """Raised when the caller did not preregister something this module refuses to default.

    A separate class because it is not a data problem: the inputs may be perfect and the answer is
    that nobody decided, in advance, what was going to be measured.
    """


# --------------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------------

def _integer(label, value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvaluationRefused(f"{label} must be an integer, got {value!r}")
    return value


def _non_negative(label, value):
    _integer(label, value)
    if value < 0:
        raise EvaluationRefused(f"{label} must not be negative, got {value}")
    return value


def _non_empty(label, value):
    if not isinstance(value, str) or not value:
        raise EvaluationRefused(f"{label} must be a non-empty string, got {value!r}")
    return value


def assert_no_float(record):
    for path, value in SPLIT._walk(record):
        if isinstance(value, float):
            raise EvaluationRefused(
                f"{path} is the float {value!r}. Every figure here is an integer or a "
                "numerator/denominator pair: a rate rounded once is a rate nobody can reconcile "
                "against the counts it came from")
    return True


def assert_cell(cell, label):
    if not isinstance(cell, dict) or set(cell) != set(CELL_FIELDS):
        raise EvaluationRefused(f"{label} must state {list(CELL_FIELDS)}")
    for field in CELL_FIELDS:
        _non_empty(f"{label} {field}", cell[field])
    return cell


def assert_metric_spec(spec):
    """The caller's preregistered specification. Nothing here has a default."""
    if not isinstance(spec, dict):
        raise SpecificationMissing("metric spec must be a mapping")
    missing = [field for field in METRIC_SPEC_FIELDS if field not in spec]
    if missing:
        raise SpecificationMissing(
            f"metric spec does not state {missing}. There is no default metric, class threshold, "
            "calibration bin edge, censoring treatment or performance cutoff: each is a choice "
            "that changes the answer, and a module that supplied one would have made it for "
            "everybody")
    unknown = [field for field in spec if field not in METRIC_SPEC_FIELDS]
    if unknown:
        raise EvaluationRefused(f"metric spec carries undeclared fields {sorted(unknown)}")
    _non_empty("metric spec preregistration_reference", spec["preregistration_reference"])
    _non_empty("metric spec metric_family_id", spec["metric_family_id"])
    _non_empty("metric spec multiplicity_adjustment", spec["multiplicity_adjustment"])

    family_size = _non_negative("metric spec family_size", spec["family_size"])
    if family_size < 1:
        raise EvaluationRefused("a metric family with no cells measures nothing")

    assert_cell(spec["primary_cell"], "primary_cell")
    if not isinstance(spec["secondary_cells"], list):
        raise EvaluationRefused("secondary_cells must be a list")
    for position, cell in enumerate(spec["secondary_cells"]):
        assert_cell(cell, f"secondary_cells[{position}]")
        if cell == spec["primary_cell"]:
            raise EvaluationRefused(
                "a cell is listed as both primary and secondary; exactly one cell is primary and "
                "it was named before anything was measured")
    declared = 1 + len(spec["secondary_cells"])
    if declared > family_size:
        raise EvaluationRefused(
            f"{declared} cells are named but the family declares {family_size}; a family smaller "
            "than the cells it contains understates the multiplicity")

    if spec["censoring_treatment"] in CENSORING_TREATMENTS_REFUSED:
        raise EvaluationRefused(
            f"censoring treatment {spec['censoring_treatment']!r} is refused by name. A "
            "right-censored outcome is not a zero and not a loss: recoding one teaches every "
            "downstream figure that 'we stopped looking' and 'it went to nothing' are the same "
            "event")
    if spec["censoring_treatment"] not in CENSORING_TREATMENTS:
        raise EvaluationRefused(
            f"censoring treatment {spec['censoring_treatment']!r} is not one of "
            f"{list(CENSORING_TREATMENTS)}")
    if spec["worst_case_outcome_rule"] not in WORST_CASE_RULES:
        raise EvaluationRefused(
            f"worst-case rule {spec['worst_case_outcome_rule']!r} is not one of "
            f"{list(WORST_CASE_RULES)}")

    for metric in spec["metrics_declared"]:
        if metric not in METRICS:
            raise EvaluationRefused(f"metric {metric!r} is not one of {list(METRICS)}")
    if not spec["metrics_declared"]:
        raise SpecificationMissing("a specification declaring no metric measures nothing")

    if spec["class_threshold"] is not None:
        assert_rational(spec["class_threshold"], "class_threshold")
    edges = spec["calibration_bin_edges"]
    if edges is not None:
        if not isinstance(edges, list) or len(edges) < 2:
            raise EvaluationRefused("calibration bin edges must be a list of at least two edges")
        for position, edge in enumerate(edges):
            assert_rational(edge, f"calibration_bin_edges[{position}]")
        for left, right in zip(edges, edges[1:]):
            if compare_rationals(left, right) >= 0:
                raise EvaluationRefused("calibration bin edges must strictly increase")
        fitted_on = spec["calibration_bin_edges_fitted_on"]
        if not isinstance(fitted_on, list) or not fitted_on:
            raise SpecificationMissing(
                "calibration bin edges must name the folds they were chosen on. Edges chosen by "
                "looking at the evaluation fold are edges fitted to the answer")
    elif METRIC_CALIBRATION in spec["metrics_declared"]:
        raise SpecificationMissing(
            "the calibration metric was declared but no bin edges were preregistered")
    assert_no_float(spec)
    return spec


def metric_spec_hash(spec):
    return hashlib.sha256(B10B.canonical_json(spec).encode("utf-8")).hexdigest()


def assert_family_binds_frozen_size(spec, frozen_family_size=None):
    """The multiplicity adjustment binds the FROZEN family size, not the cells that got computed.

    Reported alongside the frozen constant rather than derived from it, so a family that quietly
    shrank between preregistration and evaluation is visible as a disagreement rather than as a
    smaller correction.
    """
    frozen = (B11B.MULTIPLICITY_FAMILY_SIZE if frozen_family_size is None else frozen_family_size)
    if spec["family_size"] != frozen:
        raise EvaluationRefused(
            f"the specification declares a family of {spec['family_size']} while the frozen family "
            f"is {frozen}. A family that shrank between preregistration and evaluation shrinks the "
            "correction with it, which is the cheapest way to make a secondary cell look primary")
    return True


def assert_primary_not_promoted(spec, frozen_primary=None):
    """A secondary cell may not become the primary one after the numbers are in."""
    frozen = frozen_primary or {"policy_id": B11B.PRIMARY_POLICY,
                                "horizon_name": B11B.PRIMARY_HORIZON}
    if spec["primary_cell"] != frozen:
        raise EvaluationRefused(
            f"the specification names {spec['primary_cell']} as primary while the frozen primary is "
            f"{frozen}. Promoting a cell after the numbers are in is choosing the hypothesis to "
            "match the result, and the multiplicity correction cannot undo it")
    return True


def assert_side(side, label):
    if not isinstance(side, dict) or set(side) != set(SIDE_FIELDS):
        raise EvaluationRefused(
            f"{label} must state exactly {list(SIDE_FIELDS)}; order size, horizon and cost policy "
            "belong to the ROW, because a paired comparison whose sides could differ in them is "
            "not a paired comparison")
    if side["outcome_bucket"] not in BUCKETS:
        raise EvaluationRefused(
            f"{label} outcome bucket {side['outcome_bucket']!r} is not one of {list(BUCKETS)}")
    _non_negative(f"{label} deployed_capital_lamports", side["deployed_capital_lamports"])
    if side["outcome_bucket"] in EVALUABLE_BUCKETS:
        _integer(f"{label} net_pnl_lamports", side["net_pnl_lamports"])
    elif side["net_pnl_lamports"] is not None:
        raise EvaluationRefused(
            f"{label} is {side['outcome_bucket']!r} yet carries a net P&L of "
            f"{side['net_pnl_lamports']!r}. Censored, unpriceable and unobserved outcomes have no "
            "realised figure; supplying one is the recoding this module exists to prevent")
    if side["outcome_bucket"] not in AT_RISK_BUCKETS and side["deployed_capital_lamports"]:
        raise EvaluationRefused(
            f"{label} is {side['outcome_bucket']!r} yet deployed "
            f"{side['deployed_capital_lamports']} lamports; a decision the policy declined risked "
            "nothing")
    if side["probability"] is not None:
        assert_rational(side["probability"], f"{label} probability")
        if (compare_rationals(side["probability"], rational(0, 1)) < 0
                or compare_rationals(side["probability"], rational(1, 1)) > 0):
            raise EvaluationRefused(f"{label} probability is outside [0, 1]")
    if side["realised_label"] is not None and side["realised_label"] not in (0, 1):
        raise EvaluationRefused(f"{label} realised_label must be 0, 1 or null")
    if side["realised_label"] is not None and side["outcome_bucket"] not in EVALUABLE_BUCKETS:
        raise EvaluationRefused(
            f"{label} is {side['outcome_bucket']!r} yet carries a realised label; an outcome "
            "nobody observed has no class")
    path = side["equity_path_lamports"]
    if path is not None:
        if not isinstance(path, list) or not path:
            raise EvaluationRefused(f"{label} equity path must be a non-empty list or null")
        for position, value in enumerate(path):
            _integer(f"{label} equity_path_lamports[{position}]", value)
    return side


def assert_row(row):
    if not isinstance(row, dict):
        raise EvaluationRefused(f"row must be a mapping, got {type(row).__name__}")
    missing = [field for field in ROW_FIELDS if field not in row]
    if missing:
        raise EvaluationRefused(f"row does not state {missing}")
    unknown = [field for field in row if field not in ROW_FIELDS]
    if unknown:
        raise EvaluationRefused(f"row carries undeclared fields {sorted(unknown)}")
    for field in ("row_id", "group_id", "fold_id", "segment", "horizon_name", "target_id",
                  "cost_policy_id"):
        _non_empty(f"row {field}", row[field])
    _non_negative("row order_size_lamports", row["order_size_lamports"])
    if row["segment"] not in SPLIT.SEGMENTS:
        raise EvaluationRefused(f"row segment {row['segment']!r} is not one of "
                                f"{list(SPLIT.SEGMENTS)}")
    assert_side(row["model"], f"row {row['row_id']} model")
    assert_side(row["baseline"], f"row {row['row_id']} baseline")
    return row


def ordered_rows(rows):
    if isinstance(rows, (dict, str, bytes)):
        raise EvaluationRefused("rows must be a sequence of row mappings")
    seen, out = set(), []
    for row in rows:
        assert_row(row)
        if row["row_id"] in seen:
            raise EvaluationRefused(
                f"row_id {row['row_id']!r} appears twice; the same decision counted twice moves "
                "every total it enters")
        seen.add(row["row_id"])
        out.append(row)
    return sorted(out, key=lambda r: r["row_id"])


def assert_single_cohort(rows):
    """One horizon, one target, one cost policy. A mixed cohort is not one comparison."""
    for field in ("horizon_name", "target_id", "cost_policy_id"):
        values = sorted({row[field] for row in rows})
        if len(values) > 1:
            raise EvaluationRefused(
                f"the cohort mixes {field} {values}; one purge span, one label window and one cost "
                "policy per comparison, or the figures are averages over different questions")
    return True


# --------------------------------------------------------------------------------------------
# Exact metric primitives
# --------------------------------------------------------------------------------------------

def capital_weighted_return(net_pnl_lamports, deployed_capital_lamports):
    """Net P&L over deployed capital, exactly. Undefined over nothing, never zero."""
    if deployed_capital_lamports <= 0:
        return None
    return rational(net_pnl_lamports, deployed_capital_lamports)


def maximum_drawdown(path):
    """Largest peak-to-trough fall along a published equity path, in lamports.

    Computed on the path rather than on the endpoints, because a position that ended flat after
    losing four fifths of its value is not the same risk as one that never moved.
    """
    peak, worst = path[0], 0
    for value in path:
        peak = max(peak, value)
        worst = max(worst, peak - value)
    return worst


def concordance(pairs):
    """Exact pairwise ranking agreement over comparable, uncensored outcomes.

    `pairs` are (score, outcome) with score an exact rational and outcome an integer. Only pairs
    whose OUTCOMES differ are comparable: two identical outcomes cannot rank each other, and
    counting them would let a model that separates nothing score one half by default on them.
    Ties in the SCORE count as half, expressed exactly as (2·concordant + tied)/(2·comparable).
    """
    concordant = discordant = tied_score = 0
    comparable = 0
    for index, (score_a, outcome_a) in enumerate(pairs):
        for score_b, outcome_b in pairs[index + 1:]:
            if outcome_a == outcome_b:
                continue
            comparable += 1
            order = compare_rationals(score_a, score_b)
            if order == 0:
                tied_score += 1
            elif (order > 0) == (outcome_a > outcome_b):
                concordant += 1
            else:
                discordant += 1
    value = (rational(2 * concordant + tied_score, 2 * comparable) if comparable else None)
    return {"comparable_pairs": comparable, "concordant": concordant, "discordant": discordant,
            "tied_score": tied_score, "concordance": value}


def brier(observations):
    """Mean squared error of exact rational probabilities against 0/1 outcomes, exactly.

    Summed as one rational over a common denominator rather than as a mean of rounded terms; a
    Brier score assembled from rounded squares is a different number from the one it claims to be.
    """
    if not observations:
        return None
    numerator, denominator = 0, 1
    for probability, outcome in observations:
        difference = rational(probability["numerator"] - outcome * probability["denominator"],
                              probability["denominator"])
        term_numerator = difference["numerator"] ** 2
        term_denominator = difference["denominator"] ** 2
        numerator = numerator * term_denominator + term_numerator * denominator
        denominator = denominator * term_denominator
    return rational(numerator, denominator * len(observations))


def calibration_bins(observations, edges):
    """Counts and exact rates per preregistered bin. Bin edges are never chosen here."""
    bins = []
    for left, right in zip(edges, edges[1:]):
        members = [(p, y) for p, y in observations
                   if compare_rationals(p, left) >= 0 and compare_rationals(p, right) < 0]
        positives = sum(y for _, y in members)
        mean_predicted = None
        if members:
            numerator, denominator = 0, 1
            for probability, _ in members:
                numerator = (numerator * probability["denominator"]
                             + probability["numerator"] * denominator)
                denominator = denominator * probability["denominator"]
            mean_predicted = rational(numerator, denominator * len(members))
        bins.append({
            "lower_inclusive": dict(left), "upper_exclusive": dict(right),
            "count": len(members), "positives": positives,
            "observed_rate": rational(positives, len(members)) if members else None,
            "mean_predicted": mean_predicted,
        })
    return bins


def jackknife_over_groups(values_by_group):
    """Leave-one-group-out spread of a summed quantity, in exact rationals.

    Grouped rather than per row, because rows sharing a creator or a trader are not independent
    observations — leaving one row out of a group leaves the rest of that actor's behaviour in, and
    the resulting spread is far too narrow.

    A spread, never a p-value: nothing here has earned a test.
    """
    groups = sorted(values_by_group)
    if len(groups) < 2:
        return {"groups": len(groups), "estimates": [], "minimum": None, "maximum": None,
                "note": "a jackknife over fewer than two groups has nothing to leave out"}
    total = sum(values_by_group[group] for group in groups)
    estimates = [{"omitted_group": group,
                  "value": rational(total - values_by_group[group], 1)} for group in groups]
    ordered = sorted(estimates, key=lambda e: e["value"]["numerator"])
    return {"groups": len(groups), "estimates": estimates,
            "minimum": dict(ordered[0]["value"]), "maximum": dict(ordered[-1]["value"]),
            "note": "leave-one-group-out spread over the split plan's exact-identity groups; a "
                    "spread and never a p-value"}


# --------------------------------------------------------------------------------------------
# Pairing
# --------------------------------------------------------------------------------------------

def pairing_summary(rows):
    """Which rows can be compared, and how the two sides disagree about evaluability.

    Published rather than quietly resolved. If the model is evaluable on rows where the baseline is
    not, dropping the mismatches selects the comparison cohort on an outcome of the comparison —
    and the asymmetry is exactly the number that shows it.
    """
    both = [r for r in rows if r["model"]["outcome_bucket"] in EVALUABLE_BUCKETS
            and r["baseline"]["outcome_bucket"] in EVALUABLE_BUCKETS]
    model_only = [r for r in rows if r["model"]["outcome_bucket"] in EVALUABLE_BUCKETS
                  and r["baseline"]["outcome_bucket"] not in EVALUABLE_BUCKETS]
    baseline_only = [r for r in rows if r["baseline"]["outcome_bucket"] in EVALUABLE_BUCKETS
                     and r["model"]["outcome_bucket"] not in EVALUABLE_BUCKETS]
    neither = [r for r in rows if r["model"]["outcome_bucket"] not in EVALUABLE_BUCKETS
               and r["baseline"]["outcome_bucket"] not in EVALUABLE_BUCKETS]
    return {
        "cohort_rows": len(rows),
        "paired_rows": len(both),
        "model_evaluable_only": len(model_only),
        "baseline_evaluable_only": len(baseline_only),
        "neither_evaluable": len(neither),
        "paired_row_ids": sorted(r["row_id"] for r in both),
        "evaluability_asymmetry": len(model_only) - len(baseline_only),
        "selection_on_evaluability_possible": bool(model_only or baseline_only),
    }


def assert_paired_cohort(rows, paired_row_ids):
    """The paired cohort is exactly the rows where BOTH sides produced an outcome.

    Refused rather than trusted: a caller-supplied cohort is a caller-chosen one, and the choice
    that flatters is always available.
    """
    expected = sorted(r["row_id"] for r in rows
                      if r["model"]["outcome_bucket"] in EVALUABLE_BUCKETS
                      and r["baseline"]["outcome_bucket"] in EVALUABLE_BUCKETS)
    if sorted(paired_row_ids) != expected:
        raise EvaluationRefused(
            "the paired cohort is not exactly the rows where both sides produced an outcome. "
            "Choosing which mismatches to keep selects the comparison cohort on an outcome of the "
            "comparison")
    return True


# --------------------------------------------------------------------------------------------
# The two bases
# --------------------------------------------------------------------------------------------

def _worst_case_pnl(side, rule):
    """The worst admissible outcome for a side whose result is unknown."""
    if side["outcome_bucket"] in EVALUABLE_BUCKETS:
        return side["net_pnl_lamports"]
    # A side outside AT_RISK_BUCKETS deployed nothing — `assert_side` refuses any other — so the
    # rule below already yields zero for it. There is deliberately no separate branch: one that
    # cannot change the answer is dead code, and the invariant is enforced where it belongs.
    if rule == WORST_CASE_TOTAL_LOSS:
        return -side["deployed_capital_lamports"]
    raise EvaluationRefused(f"no worst-case rule named {rule!r}")


def _side_totals(rows, side_name, basis, rule):
    deployed = 0
    pnl = 0
    for row in rows:
        side = row[side_name]
        if basis == BASIS_OBSERVED:
            if side["outcome_bucket"] not in EVALUABLE_BUCKETS:
                continue
            deployed += side["deployed_capital_lamports"]
            pnl += side["net_pnl_lamports"]
        else:
            deployed += side["deployed_capital_lamports"]
            pnl += _worst_case_pnl(side, rule)
    return deployed, pnl


# --------------------------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------------------------

def evaluate(rows, spec, bound_hashes, split_plan=None, frozen_family_size=None,
             frozen_primary=None):
    """One evaluation report. Computes only what was declared, on both bases, and claims nothing."""
    spec = assert_metric_spec(spec)
    assert_family_binds_frozen_size(spec, frozen_family_size)
    assert_primary_not_promoted(spec, frozen_primary)
    rows = ordered_rows(rows)
    assert_single_cohort(rows)
    if split_plan is not None:
        SPLIT.assert_no_association_evidence(split_plan)
        known = {group for fold in split_plan["folds"] for segment in SPLIT.SEGMENTS
                 for group in fold["groups"][segment]}
        unknown = sorted({row["group_id"] for row in rows} - known)
        if unknown:
            raise EvaluationRefused(
                f"{len(unknown)} rows carry group ids the split plan does not know (first: "
                f"{unknown[0]}); grouped uncertainty computed over invented groups is a spread "
                "over nothing")

    pairing = pairing_summary(rows)
    assert_paired_cohort(rows, pairing["paired_row_ids"])
    rule = spec["worst_case_outcome_rule"]
    declared = list(spec["metrics_declared"])
    metrics = {}

    for basis in BASES:
        block = {}
        model_deployed, model_pnl = _side_totals(rows, "model", basis, rule)
        baseline_deployed, baseline_pnl = _side_totals(rows, "baseline", basis, rule)
        if METRIC_DEPLOYED_CAPITAL in declared:
            block[METRIC_DEPLOYED_CAPITAL] = {"model": model_deployed,
                                              "baseline": baseline_deployed}
        if METRIC_TOTAL_NET_PNL in declared:
            block[METRIC_TOTAL_NET_PNL] = {"model": model_pnl, "baseline": baseline_pnl}
        if METRIC_CAPITAL_WEIGHTED_RETURN in declared:
            block[METRIC_CAPITAL_WEIGHTED_RETURN] = {
                "model": capital_weighted_return(model_pnl, model_deployed),
                "baseline": capital_weighted_return(baseline_pnl, baseline_deployed)}
        if METRIC_PAIRED_DIFFERENCE in declared:
            if basis == BASIS_OBSERVED:
                paired = [r for r in rows if r["row_id"] in set(pairing["paired_row_ids"])]
                difference = sum(r["model"]["net_pnl_lamports"]
                                 - r["baseline"]["net_pnl_lamports"] for r in paired)
                block[METRIC_PAIRED_DIFFERENCE] = {"value": difference,
                                                   "rows": len(paired)}
            else:
                difference = sum(_worst_case_pnl(r["model"], rule)
                                 - _worst_case_pnl(r["baseline"], rule) for r in rows)
                block[METRIC_PAIRED_DIFFERENCE] = {"value": difference, "rows": len(rows)}
        metrics[basis] = block

    observed = [r for r in rows if r["model"]["outcome_bucket"] in EVALUABLE_BUCKETS]
    extra = {}
    if METRIC_CONCORDANCE in declared:
        pairs = [(r["model"]["probability"], r["model"]["realised_label"]) for r in observed
                 if r["model"]["probability"] is not None
                 and r["model"]["realised_label"] is not None]
        extra[METRIC_CONCORDANCE] = concordance(pairs)
    if METRIC_BRIER in declared or METRIC_CALIBRATION in declared:
        graded = [(r["model"]["probability"], r["model"]["realised_label"]) for r in observed
                  if r["model"]["probability"] is not None
                  and r["model"]["realised_label"] is not None]
        if METRIC_BRIER in declared:
            extra[METRIC_BRIER] = brier(graded)
        if METRIC_CALIBRATION in declared:
            extra[METRIC_CALIBRATION] = {
                "bins": calibration_bins(graded, spec["calibration_bin_edges"]),
                "edges_fitted_on": list(spec["calibration_bin_edges_fitted_on"])}
    if METRIC_MAX_DRAWDOWN in declared:
        drawdowns = [maximum_drawdown(r["model"]["equity_path_lamports"]) for r in rows
                     if r["model"]["equity_path_lamports"]]
        extra[METRIC_MAX_DRAWDOWN] = {"paths": len(drawdowns),
                                      "worst": max(drawdowns) if drawdowns else None}
    if METRIC_EXPOSURE in declared:
        extra[METRIC_EXPOSURE] = {
            "orders": len(rows),
            "total_order_size_lamports": sum(r["order_size_lamports"] for r in rows),
            "largest_order_size_lamports": max((r["order_size_lamports"] for r in rows),
                                               default=0),
            "distinct_groups": len({r["group_id"] for r in rows}),
        }
    if METRIC_COUNTS in declared:
        extra[METRIC_COUNTS] = {
            side: {bucket: sum(1 for r in rows if r[side]["outcome_bucket"] == bucket)
                   for bucket in BUCKETS}
            for side in ("model", "baseline")}
    metrics["cohort_wide"] = extra

    by_group = {}
    for row in rows:
        if row["model"]["outcome_bucket"] in EVALUABLE_BUCKETS:
            by_group[row["group_id"]] = (by_group.get(row["group_id"], 0)
                                         + row["model"]["net_pnl_lamports"])
    report = {
        "schema_version": SCHEMA_VERSION,
        "headline_rule": HEADLINE_RULE,
        "status": STATUS_SYNTHETIC_PLUMBING_ONLY,
        "performance_status": ARTIFACT.PERFORMANCE_NOT_EVALUATED,
        "metric_spec_sha256": metric_spec_hash(spec),
        "primary_cell": dict(spec["primary_cell"]),
        "family_size": spec["family_size"],
        "bound_hashes": dict(bound_hashes),
        "cohort": {
            "rows": len(rows),
            "horizon_name": rows[0]["horizon_name"] if rows else None,
            "target_id": rows[0]["target_id"] if rows else None,
            "cost_policy_id": rows[0]["cost_policy_id"] if rows else None,
            "groups": len({r["group_id"] for r in rows}),
            "censoring_treatment": spec["censoring_treatment"],
            "worst_case_outcome_rule": rule,
        },
        "metrics": metrics,
        "grouped_uncertainty": jackknife_over_groups(by_group),
        "pairing": pairing,
        "report_sha256": None,
    }
    assert_report(report, spec)
    report["report_sha256"] = report_hash(report)
    return report


def assert_report(report, spec=None):
    """Every gate on a finished report, in one call."""
    if not isinstance(report, dict):
        raise EvaluationRefused(f"report must be a mapping, got {type(report).__name__}")
    missing = [field for field in REPORT_FIELDS if field not in report]
    if missing:
        raise EvaluationRefused(f"report does not carry {missing}")
    unknown = [field for field in report if field not in REPORT_FIELDS]
    if unknown:
        raise EvaluationRefused(f"report carries undeclared fields {sorted(unknown)}")
    if report["headline_rule"] != HEADLINE_RULE:
        raise EvaluationRefused("the headline rule on this report is not the one this module "
                                "applies")
    if report["status"] not in ATTAINABLE_REPORT_STATUSES:
        raise EvaluationRefused(
            f"a report may not ship with status {report['status']!r}. Nothing here has been "
            "evaluated against a real window, and publication grade also waits on the "
            "funding-cluster gate. " + SPLIT._gate_sentence())
    if report["performance_status"] != ARTIFACT.PERFORMANCE_NOT_EVALUATED:
        raise EvaluationRefused(
            f"a report may not claim {report['performance_status']!r}; profitable, executable, "
            "validated and live are claims nobody here has earned")

    missing_hashes = [field for field in BOUND_HASH_FIELDS
                      if not report["bound_hashes"].get(field)]
    if missing_hashes:
        raise EvaluationRefused(
            f"the report does not bind {missing_hashes}. A figure that cannot name the rows, the "
            "split, the model, the metric spec and the code that produced it is not reproducible")

    published = set(report["metrics"])
    if not set(BASES).issubset(published):
        raise EvaluationRefused(
            f"the report publishes {sorted(published)} but both of {list(BASES)} are required. "
            + HEADLINE_RULE)
    for basis in BASES:
        for metric in HEADLINE_METRICS:
            here = metric in report["metrics"][basis]
            there = metric in report["metrics"][BASES[1 - BASES.index(basis)]]
            if here != there:
                raise EvaluationRefused(
                    f"{metric} is published on {basis} but not on the other basis; a figure on one "
                    "basis presented alone is the survivorship this rule exists to prevent")
    if spec is not None:
        if report["metric_spec_sha256"] != metric_spec_hash(spec):
            raise EvaluationRefused("the report was computed under a different metric spec")
        if report["family_size"] != spec["family_size"]:
            raise EvaluationRefused("the report's family size disagrees with the specification")
        if report["primary_cell"] != spec["primary_cell"]:
            raise EvaluationRefused("the report's primary cell disagrees with the specification")
    assert_no_float(report)
    SPLIT.assert_no_association_evidence(report)
    return report


def report_hash(report):
    return hashlib.sha256(B10B.canonical_json(
        {k: v for k, v in report.items() if k != "report_sha256"}).encode("utf-8")).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", action="store_true")
    args = parser.parse_args(argv)
    if not args.contract:
        parser.error("this module is a library; run `--contract`")
    print(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "headline_rule": HEADLINE_RULE,
        "bases": list(BASES),
        "headline_metrics": list(HEADLINE_METRICS),
        "metrics": list(METRICS),
        "outcome_buckets": list(BUCKETS),
        "evaluable_buckets": list(EVALUABLE_BUCKETS),
        "at_risk_buckets": list(AT_RISK_BUCKETS),
        "censoring_treatments": list(CENSORING_TREATMENTS),
        "censoring_treatments_refused_by_name": list(CENSORING_TREATMENTS_REFUSED),
        "worst_case_rules": list(WORST_CASE_RULES),
        "report_statuses": list(REPORT_STATUSES),
        "attainable_report_statuses": list(ATTAINABLE_REPORT_STATUSES),
        "frozen_family_size": B11B.MULTIPLICITY_FAMILY_SIZE,
        "frozen_primary_cell": {"policy_id": B11B.PRIMARY_POLICY,
                                "horizon_name": B11B.PRIMARY_HORIZON},
        "default_metric": None,
        "default_class_threshold": None,
        "default_calibration_bin_edges": None,
        "default_performance_cutoff": None,
        "model_fitted": False,
        "b11a_outcomes_read": False,
        "floats_used": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except B10B.FreezeViolation as error:
        print(f"EvaluationRefused: {error}", file=sys.stderr)
        sys.exit(2)
