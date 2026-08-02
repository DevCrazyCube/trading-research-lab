"""B14d — the last synthetic seam: B14c model output through the B14b evaluation harness.

One invented corpus, one frozen split, one row universe. The model's decisions and the
re-instantiated B11b policy decisions are evaluated over **the same rows**, and every headline
appears on both required bases.

What this module is careful about, and why
------------------------------------------
**B11b's policies are re-instantiated; B11b's figures are never imported.** The policy definitions
are rules — they carry no fitted parameter and import nothing from the window they were first
written for — so they are recomputed here on these rows, using B11b's own frozen code rather than
a paraphrase of it. Its published numbers describe B11a and are not comparable to anything
computed here; `cross_window_comparison` is refused by name.

**A model that abstains a lot can look good.** It deploys nothing on the rows it declines, so its
per-position figure improves while its coverage collapses. Every report here therefore publishes
both entry counts, both evaluable counts, and the abstention count per code, and refuses to
publish at all if those do not reconcile against the cohort. A hidden abstention is a survivorship
filter with a polite name.

**The four B14c segments are three B14a segments.** `fit` and `calibration` are both *training* —
the freeze puts the calibration fold chronologically last inside the training segment, not beside
it. Mapping them anywhere else would let a calibration row be evaluated against.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "1.0.0"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# One module graph. FIXTURES pulls in the engine, which pulls in the validator; EVAL pulls in the
# artifact envelope and the split planner. Loading any of them twice by path would give this file
# exception classes nobody raises.
FIXTURES = _load("b14c_model_fixtures", "b14c_model_fixtures.py")
ENGINE = FIXTURES.ENGINE
PREREG = ENGINE.PREREG
EVAL = _load("b14b_evaluation", "b14b_evaluation.py")
SPLIT = EVAL.SPLIT
B11B = EVAL.B11B

rational = EVAL.rational
compare_rationals = EVAL.compare_rationals


class PairedEvaluationRefused(ENGINE.ModelEngineRefused):
    """The comparison was not one the two sides could honestly be put through."""


# B14c's four segments mapped onto B14a's three. Calibration is training, because the freeze puts
# it chronologically last INSIDE the training segment.
SEGMENT_MAP = {"fit": SPLIT.SEGMENT_TRAIN, "calibration": SPLIT.SEGMENT_TRAIN,
               "validation": SPLIT.SEGMENT_VALIDATION, "test": SPLIT.SEGMENT_TEST}

COMPARATOR_POLICIES = (B11B.P1_ALL_ELIGIBLE, B11B.P0_DO_NOTHING, B11B.P2_RANDOM_CONTROL)
PRIMARY_COMPARATOR = B11B.P1_ALL_ELIGIBLE

# Selection metrics that would make the comparison meaningless if they had been used. Named, so an
# invented one is refused for not being declared rather than slipping past an omission.
REALISED_RETURN_SELECTION_METRICS = (
    "realised_capital_weighted_return", "capital_weighted_return", "total_net_pnl_lamports",
    "net_pnl_lamports", "realised_return", "profit", "pnl")

CLASS_THRESHOLD = Fraction(1, 2)


# --------------------------------------------------------------------------------------------
# Synthetic outcomes — invented here, declared in the open
# --------------------------------------------------------------------------------------------

def synthetic_outcome(row):
    """What happened to this row, as a property of the ROW rather than of any side.

    Invented by a declared integer function of the row id. Not drawn from any burned distribution,
    not tuned, and not consulted by anything that fits: the engine never sees this field.

    Both sides see the same outcome. Whether a side *realises* it depends only on whether that side
    entered, which is the whole point of a paired comparison.
    """
    seed = int(hashlib.sha256(row["row_id"].encode()).hexdigest(), 16)
    if seed % 23 == 0:
        return {"bucket": EVAL.BUCKET_RIGHT_CENSORED, "net_pnl_lamports": None,
                "equity_path_lamports": None}
    if seed % 29 == 0:
        return {"bucket": EVAL.BUCKET_STRUCTURAL_EXIT_UNAVAILABLE, "net_pnl_lamports": None,
                "equity_path_lamports": None}
    if seed % 31 == 0:
        return {"bucket": EVAL.BUCKET_NO_OBSERVED_STATE, "net_pnl_lamports": None,
                "equity_path_lamports": None}
    # A marked outcome, correlated with the label so the mechanics are exercised: a corpus where
    # the outcome is independent of the target would make every comparison a coin toss and prove
    # nothing about the plumbing that carries it.
    magnitude = seed % 40_000_000
    net = magnitude if row["label_value"] else -magnitude
    return {"bucket": EVAL.BUCKET_MARKED, "net_pnl_lamports": net,
            "equity_path_lamports": [0, net // 2, -(magnitude // 3), net]}


def identity_of(row):
    """A synthetic creator and user per row, so R5 has something real to close over.

    Assigned in deliberate clusters rather than drawn independently. Independent draws over a small
    identity space produce the giant-component collapse: with 404 rows over 40 creators and 40
    users, the transitive closure merged EVERYTHING into one group, and a jackknife over one group
    has nothing to leave out — the spread came back empty and looked like a formatting problem
    rather than the degenerate grouping it was.

    Here each row belongs to one cluster, and within a cluster rows share creators and users in
    overlapping ways, so the closure has real work to do and still yields many groups.
    """
    seed = int(hashlib.sha256(row["row_id"].encode()).hexdigest(), 16)
    cluster = seed % 40
    return {"creator": f"creator-{cluster:02d}-{seed % 3}",
            "user": f"user-{cluster:02d}-{(seed // 7) % 3}"}


# --------------------------------------------------------------------------------------------
# Sides
# --------------------------------------------------------------------------------------------

def _side(bucket, net, capital, probability=None, label=None, path=None):
    return {"outcome_bucket": bucket, "net_pnl_lamports": net,
            "deployed_capital_lamports": capital, "probability": probability,
            "realised_label": label, "equity_path_lamports": path}


def _entered_side(row, outcome, probability=None):
    """A side that took the position, so it realises whatever the row did."""
    if outcome["bucket"] != EVAL.BUCKET_MARKED:
        # Censored, unpriceable and unobserved outcomes carry NO realised figure. Passing the
        # position's cost through here as a loss is the recoding B14b exists to prevent.
        return _side(outcome["bucket"], None, B11B.ORDER_SIZE_LAMPORTS, probability)
    return _side(EVAL.BUCKET_MARKED, outcome["net_pnl_lamports"], B11B.ORDER_SIZE_LAMPORTS,
                 probability, int(row["label_value"]), outcome["equity_path_lamports"])


def model_side(fitted, row, pairs):
    """The model's decision: enter, decline, or abstain. Three different facts."""
    probability, code = ENGINE.predict(fitted, row, pairs)
    if code is not None:
        # An abstention is a declared non-decision. Not at risk, no capital, and never a
        # prediction of the negative class.
        return _side(EVAL.BUCKET_NO_DECISION, None, 0), code
    if compare_rationals(_as_pair(probability), _as_pair(CLASS_THRESHOLD)) < 0:
        return _side(EVAL.BUCKET_NOT_ENTERED, None, 0, _as_pair(probability)), None
    return _entered_side(row, synthetic_outcome(row), _as_pair(probability)), None


def _as_pair(value):
    value = Fraction(value)
    return rational(value.numerator, value.denominator)


def policy_side(policy_id, row):
    """A B11b policy's decision, from B11b's own frozen rule rather than a paraphrase."""
    if policy_id == B11B.P0_DO_NOTHING:
        return _side(EVAL.BUCKET_NOT_ENTERED, None, 0)
    if policy_id == B11B.P1_ALL_ELIGIBLE:
        return _entered_side(row, synthetic_outcome(row))
    if policy_id == B11B.P2_RANDOM_CONTROL:
        if B11B.mint_hash_selected(row["row_id"]):
            return _entered_side(row, synthetic_outcome(row))
        return _side(EVAL.BUCKET_NOT_ENTERED, None, 0)
    raise PairedEvaluationRefused(
        f"{policy_id!r} is not one of the portable comparator policies "
        f"{list(COMPARATOR_POLICIES)}")


# --------------------------------------------------------------------------------------------
# Building the shared row universe
# --------------------------------------------------------------------------------------------

def build_rows(corpus, fitted, policy_id, horizon=None, cost_policy_id="synthetic_cost_policy_v1"):
    """One row per test subject, carrying BOTH sides. The universe is shared by construction.

    Both sides live on the same row, so they cannot be computed over different subjects — which is
    stronger than comparing two row sets afterwards and checking they matched.
    """
    ENGINE.assert_synthetic(corpus)
    horizon = B11B.PRIMARY_HORIZON if horizon is None else horizon
    pairs = corpus["rational_pairs"]
    subjects = ENGINE.segment_rows(corpus, "test")
    identities = [dict(identity_of(row), row_id=row["row_id"]) for row in subjects]
    groups = SPLIT.identity_groups(identities)

    rows, abstentions = [], {}
    for subject in subjects:
        side, code = model_side(fitted, subject, pairs)
        if code is not None:
            abstentions[code] = abstentions.get(code, 0) + 1
        rows.append({
            "row_id": subject["row_id"],
            "group_id": SPLIT.group_of(groups, subject["row_id"]),
            "fold_id": "synthetic-fold-1",
            "segment": SEGMENT_MAP[subject["segment"]],
            "horizon_name": horizon,
            "target_id": "profitable_at_horizon_after_costs",
            "order_size_lamports": B11B.ORDER_SIZE_LAMPORTS,
            "cost_policy_id": cost_policy_id,
            "model": side,
            "baseline": policy_side(policy_id, subject),
        })
    return rows, dict(sorted(abstentions.items())), groups


def build_spec(policy_id):
    """The metric spec. Every field is stated; nothing has a default."""
    return {
        "preregistration_reference": "B14C_MODEL_AND_SELECTION_V1 on a synthetic corpus; the "
                                     "B11b policy DEFINITIONS re-instantiated on these rows, "
                                     "never B11b's figures",
        "metric_family_id": f"b14d_synthetic_model_vs_{policy_id}",
        "family_size": B11B.MULTIPLICITY_FAMILY_SIZE,
        "primary_cell": {"policy_id": B11B.PRIMARY_POLICY, "horizon_name": B11B.PRIMARY_HORIZON},
        "secondary_cells": [{"policy_id": B11B.P2_RANDOM_CONTROL,
                             "horizon_name": B11B.PRIMARY_HORIZON}],
        "metrics_declared": list(EVAL.METRICS),
        "censoring_treatment": EVAL.CENSORING_EXCLUDED_AND_COUNTED,
        "worst_case_outcome_rule": EVAL.WORST_CASE_TOTAL_LOSS,
        "class_threshold": _as_pair(CLASS_THRESHOLD),
        "calibration_bin_edges": [rational(0, 1), rational(1, 4), rational(1, 2), rational(3, 4),
                                  rational(1, 1)],
        "calibration_bin_edges_fitted_on": ["synthetic-fold-1-train"],
        "multiplicity_adjustment": "bonferroni over the frozen family size; no test is run here",
    }


def build_split_plan(rows, groups):
    """A plan naming exactly the groups the rows carry, so grouped uncertainty is over real ones."""
    known = sorted(groups)
    return {
        "schema_version": SPLIT.SCHEMA_VERSION, "purge_rule": SPLIT.PURGE_RULE,
        "embargo_rule": SPLIT.EMBARGO_RULE, "r5_rule": SPLIT.R5_RULE,
        "status": SPLIT.STATUS_RESEARCH_PLUMBING_ONLY,
        "target_id": "profitable_at_horizon_after_costs", "horizon_id": B11B.PRIMARY_HORIZON,
        "purge_slots": 50, "embargo_slots": 100,
        "preregistration_reference": "B14C_MODEL_AND_SELECTION_V1, synthetic corpus",
        "folds": [{"fold_id": "synthetic-fold-1",
                   "ranges": {s: {"first_slot_inclusive": 1, "last_slot_inclusive": 2}
                              for s in SPLIT.SEGMENTS},
                   "rows": {s: [] for s in SPLIT.SEGMENTS},
                   "row_counts": {s: 0 for s in SPLIT.SEGMENTS},
                   "groups": {SPLIT.SEGMENT_TEST: known, SPLIT.SEGMENT_TRAIN: [],
                              SPLIT.SEGMENT_VALIDATION: []}}],
        "accounting": {}, "exclusions": [],
        "row_evidence_sha256": "e" * 64,
        "plan_sha256": "p" * 64,
    }


def build_bound_hashes(corpus, artifact, spec, policy_id):
    """What every figure in the report is bound to. A figure that cannot name these is not one."""
    return {
        "row_evidence_sha256": corpus["row_evidence_sha256"],
        "split_plan_sha256": hashlib.sha256(
            f"synthetic-split::{corpus['window_id']}".encode()).hexdigest(),
        "model_artifact_sha256": artifact["artifact_sha256"],
        "baseline_record_sha256": hashlib.sha256(
            f"b11b-policy-definition::{policy_id}".encode()).hexdigest(),
        "feature_order_sha256": artifact["feature_order_sha256"],
        "label_preregistration_sha256": PREREG.PREREGISTRATION_CANONICAL_SHA256,
        "metric_spec_sha256": EVAL.metric_spec_hash(spec),
        "code_revision": "synthetic-b14d",
        "environment_manifest_sha256": hashlib.sha256(b"synthetic-environment").hexdigest(),
    }


# --------------------------------------------------------------------------------------------
# The refusals this seam owes
# --------------------------------------------------------------------------------------------

def assert_selection_was_not_realised_return(metric_name):
    """A model selected on realised return has already chosen the fold's luckiest configuration."""
    if metric_name.lower() in REALISED_RETURN_SELECTION_METRICS:
        raise PairedEvaluationRefused(
            f"the model was selected on {metric_name!r}, a realised-return metric. Over a "
            "validation fold that picks whichever configuration caught its few largest winners, "
            "and comparing it against a policy afterwards launders the selection into a result")
    return True


def assert_shared_row_universe(reports):
    """Every comparison must run over the same subjects, or the difference is a sample change."""
    universes = {name: tuple(sorted(report["row_ids"])) for name, report in reports.items()}
    distinct = set(universes.values())
    if len(distinct) > 1:
        sizes = {name: len(rows) for name, rows in universes.items()}
        raise PairedEvaluationRefused(
            f"the comparisons run over different row universes ({sizes}). A difference between "
            "two figures computed on two sets of subjects measures the sets")
    return True


def assert_shared_split(reports):
    """Different splits mean different training histories behind the same headline."""
    plans = {report["report"]["bound_hashes"]["split_plan_sha256"] for report in reports.values()}
    if len(plans) > 1:
        raise PairedEvaluationRefused(
            "the comparisons bind different split plans; the same headline over two splits is two "
            "different experiments reported as one")
    return True


def assert_comparable_assumptions(reports):
    """Horizon, target and cost policy must be identical across every comparison."""
    for field in ("horizon_name", "target_id", "cost_policy_id"):
        values = {report["report"]["cohort"][field] for report in reports.values()}
        if len(values) > 1:
            raise PairedEvaluationRefused(
                f"the comparisons disagree on {field}: {sorted(values)}. A cohort mixing "
                "horizons, targets or cost policies is not one cohort")
    return True


def assert_abstentions_reconcile(report, abstentions, rows):
    """No hidden abstentions: the published counts must add up to the cohort.

    A model whose declined rows quietly vanish reports a per-position figure over a survivorship
    filter, and nothing downstream can tell.
    """
    declared = sum(abstentions.values())
    counted = report["metrics"]["cohort_wide"][EVAL.METRIC_COUNTS]["model"][EVAL.BUCKET_NO_DECISION]
    if declared != counted:
        raise PairedEvaluationRefused(
            f"{declared} abstentions were recorded but {counted} rows are marked no_decision; an "
            "abstention that does not appear in the census is a survivorship filter with a polite "
            "name")
    total = sum(report["metrics"]["cohort_wide"][EVAL.METRIC_COUNTS]["model"].values())
    if total != len(rows):
        raise PairedEvaluationRefused(
            f"the model bucket census sums to {total} over {len(rows)} rows; every row must land "
            "in exactly one bucket")
    return True


def assert_no_float(node, path="$"):
    ENGINE.assert_no_float(node, path)
    return True


# --------------------------------------------------------------------------------------------
# Differences
# --------------------------------------------------------------------------------------------

def _fraction(value):
    return None if value is None else Fraction(value["numerator"], value["denominator"])


def exact_differences(report):
    """Model minus baseline, exactly, on both bases. Undefined stays undefined."""
    differences = {}
    for basis in EVAL.BASES:
        block = report["metrics"][basis]
        entry = {}
        pnl = block[EVAL.METRIC_TOTAL_NET_PNL]
        entry[EVAL.METRIC_TOTAL_NET_PNL] = pnl["model"] - pnl["baseline"]
        capital = block[EVAL.METRIC_DEPLOYED_CAPITAL]
        entry[EVAL.METRIC_DEPLOYED_CAPITAL] = capital["model"] - capital["baseline"]
        returns = block[EVAL.METRIC_CAPITAL_WEIGHTED_RETURN]
        model_return = _fraction(returns["model"])
        baseline_return = _fraction(returns["baseline"])
        if model_return is None or baseline_return is None:
            # Undefined over no deployed capital. A difference against an undefined figure is not
            # zero, and publishing zero would read as "no difference" rather than "no denominator".
            entry[EVAL.METRIC_CAPITAL_WEIGHTED_RETURN] = None
        else:
            entry[EVAL.METRIC_CAPITAL_WEIGHTED_RETURN] = ENGINE.pair(
                model_return - baseline_return)
        entry[EVAL.METRIC_PAIRED_DIFFERENCE] = dict(block[EVAL.METRIC_PAIRED_DIFFERENCE])
        differences[basis] = entry
    return differences


PAIRED_DIFFERENCE_NOTE = (
    "The paired difference on the observed basis is structurally ZERO for any entry-selection "
    "comparison, and that is not a fault in the plumbing. Order size, horizon and cost policy live "
    "on the ROW, so when both sides enter they take the same position and realise the same "
    "outcome; a paired row cannot differ. A selective model differs from a policy only in WHICH "
    "rows it enters, so all of its effect lands in coverage and in the whole-cohort basis. Read "
    "the entry counts and both bases: a paired difference of zero here means the metric had "
    "nothing to measure, not that the two sides performed alike. The metric acquires content only "
    "when the sides can differ in order size or exit rule, which this contract deliberately makes "
    "unrepresentable."
)


def entry_counts(rows):
    """Both sides' entries and evaluables, always published together.

    A model that abstains heavily deploys nothing on the rows it declines, so its per-position
    figure improves while its coverage collapses. These two numbers are what make that visible.
    """
    counts = {}
    for side in ("model", "baseline"):
        counts[side] = {
            "entered": sum(1 for row in rows
                           if row[side]["outcome_bucket"] in EVAL.AT_RISK_BUCKETS),
            "evaluable": sum(1 for row in rows
                             if row[side]["outcome_bucket"] in EVAL.EVALUABLE_BUCKETS),
            "declined": sum(1 for row in rows
                            if row[side]["outcome_bucket"] == EVAL.BUCKET_NOT_ENTERED),
            "abstained": sum(1 for row in rows
                             if row[side]["outcome_bucket"] == EVAL.BUCKET_NO_DECISION),
        }
    return counts


# --------------------------------------------------------------------------------------------
# One comparison
# --------------------------------------------------------------------------------------------

def compare(corpus, fitted, artifact, policy_id, selection_metric="brier_score_exact_rational"):
    """The model against one re-instantiated B11b policy, over one shared row universe."""
    assert_selection_was_not_realised_return(selection_metric)
    ENGINE.refuse_cross_window_comparison(corpus["window_id"], corpus["window_id"])
    rows, abstentions, groups = build_rows(corpus, fitted, policy_id)
    spec = build_spec(policy_id)
    plan = build_split_plan(rows, groups)
    bound = build_bound_hashes(corpus, artifact, spec, policy_id)
    report = EVAL.evaluate(rows, spec, bound, split_plan=plan,
                           frozen_family_size=B11B.MULTIPLICITY_FAMILY_SIZE,
                           frozen_primary={"policy_id": B11B.PRIMARY_POLICY,
                                           "horizon_name": B11B.PRIMARY_HORIZON})
    assert_abstentions_reconcile(report, abstentions, rows)
    result = {
        "policy_id": policy_id,
        "is_primary_comparator": policy_id == PRIMARY_COMPARATOR,
        "report": report,
        "row_ids": sorted(row["row_id"] for row in rows),
        "abstentions": abstentions,
        "entry_counts": entry_counts(rows),
        "exact_differences": exact_differences(report),
    }
    assert_no_float(result)
    return result


def compare_all(corpus=None, policies=COMPARATOR_POLICIES, receipt=None):
    """Every comparator, over one corpus, one fit and one shared universe."""
    corpus = FIXTURES.build_corpus() if corpus is None else corpus
    selection = ENGINE.select(corpus)
    fitted = selection["selected"]["fitted"]
    artifact = ENGINE.serialize_artifact(corpus, selection["selected"])
    # The test segment is read once, through the engine's own receipt, before any comparison uses
    # it. A second pass with the same receipt refuses.
    test_result = ENGINE.score_test_once(corpus, selection,
                                         set() if receipt is None else receipt)
    comparisons = {policy: compare(corpus, fitted, artifact, policy) for policy in policies}
    assert_shared_row_universe(comparisons)
    assert_shared_split(comparisons)
    assert_comparable_assumptions(comparisons)
    return {"corpus": corpus, "selection": selection, "artifact": artifact,
            "test_result": test_result, "comparisons": comparisons}


def publication(bundle):
    """What a reader gets. Structural counts, exact figures, and no claim above plumbing."""
    comparisons = bundle["comparisons"]
    published = {}
    for policy, comparison in comparisons.items():
        report = comparison["report"]
        published[policy] = {
            "is_primary_comparator": comparison["is_primary_comparator"],
            "report_sha256": report["report_sha256"],
            "bases_published": sorted(b for b in report["metrics"] if b in EVAL.BASES),
            "entry_counts": comparison["entry_counts"],
            "abstentions": comparison["abstentions"],
            "pairing": {"paired_rows": report["pairing"]["paired_rows"],
                        "model_evaluable_only": report["pairing"]["model_evaluable_only"],
                        "baseline_evaluable_only": report["pairing"]["baseline_evaluable_only"],
                        "neither_evaluable": report["pairing"]["neither_evaluable"]},
            "outcome_bucket_counts": report["metrics"]["cohort_wide"][EVAL.METRIC_COUNTS],
            "exact_differences": comparison["exact_differences"],
            "grouped_uncertainty": {
                "groups": report["grouped_uncertainty"]["groups"],
                "minimum": report["grouped_uncertainty"]["minimum"],
                "maximum": report["grouped_uncertainty"]["maximum"],
                "note": report["grouped_uncertainty"]["note"]},
            "status": report["status"],
            "performance_status": report["performance_status"],
        }
    result = {
        "schema_version": SCHEMA_VERSION,
        "window_id": bundle["corpus"]["window_id"],
        "provenance": bundle["corpus"]["provenance"],
        "artifact_sha256": bundle["artifact"]["artifact_sha256"],
        "selected": {
            "family": bundle["selection"]["selected"]["configuration"]["family"],
            "grid_index": bundle["selection"]["selected"]["configuration"]["grid_index"]},
        "selection_metric": "brier_score_exact_rational",
        "primary_comparator": PRIMARY_COMPARATOR,
        "paired_difference_note": PAIRED_DIFFERENCE_NOTE,
        "comparisons": published,
        "b11b_figures_imported": False,
        "eligible_for_b11a": False,
        "real_window_fitting_permitted": False,
        "performance_status": "not_evaluated",
    }
    assert_no_float(result)
    return result


# --------------------------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------------------------

def _expect(findings, label, exception, thunk):
    try:
        thunk()
    except exception:
        return
    except Exception as error:                                            # noqa: BLE001
        findings.append(f"{label}: raised {type(error).__name__}, not {exception.__name__}")
        return
    findings.append(f"{label}: did NOT refuse")


def check_refusals(bundle):
    """Every refusal this seam owes the brief, each shown to fire."""
    findings = []
    comparisons = bundle["comparisons"]
    corpus = bundle["corpus"]

    _expect(findings, "a cross-window comparison", ENGINE.ModelEngineRefused,
            lambda: ENGINE.refuse_cross_window_comparison(corpus["window_id"], "b11a"))
    _expect(findings, "selection by realised return", PairedEvaluationRefused,
            lambda: assert_selection_was_not_realised_return("capital_weighted_return"))
    _expect(findings, "an unshared row universe", PairedEvaluationRefused,
            lambda: assert_shared_row_universe(_with_shorter_universe(comparisons)))
    _expect(findings, "an unshared split", PairedEvaluationRefused,
            lambda: assert_shared_split(_with_other_split(comparisons)))
    _expect(findings, "a mismatched horizon", PairedEvaluationRefused,
            lambda: assert_comparable_assumptions(_with_other_horizon(comparisons)))
    _expect(findings, "a mismatched cost policy", PairedEvaluationRefused,
            lambda: assert_comparable_assumptions(_with_other_cost(comparisons)))
    _expect(findings, "a hidden abstention", PairedEvaluationRefused,
            lambda: assert_abstentions_reconcile(
                comparisons[PRIMARY_COMPARATOR]["report"], {}, [1]))
    _expect(findings, "an unknown comparator policy", PairedEvaluationRefused,
            lambda: policy_side("P9_invented", {"row_id": "x", "label_value": True}))
    _expect(findings, "a float in the publication", ENGINE.ModelEngineRefused,
            lambda: assert_no_float({"metric": 0.5}))
    _expect(findings, "fitting a real window", PREREG.FitRefused,
            lambda: build_rows({"window_id": "a-real-window"}, None, PRIMARY_COMPARATOR))
    _expect(findings, "a censored side carrying a realised figure", EVAL.EvaluationRefused,
            lambda: EVAL.assert_side(
                _side(EVAL.BUCKET_RIGHT_CENSORED, -100, B11B.ORDER_SIZE_LAMPORTS), "censored"))
    _expect(findings, "a second read of the test segment", ENGINE.LeakageRefused,
            lambda: _score_twice(bundle))
    return findings


def _score_twice(bundle):
    receipt = set()
    ENGINE.score_test_once(bundle["corpus"], bundle["selection"], receipt)
    ENGINE.score_test_once(bundle["corpus"], bundle["selection"], receipt)


def _mutate(comparisons, policy, mutator):
    copy = dict(comparisons)
    copy[policy] = mutator(dict(comparisons[policy]))
    return copy


def _with_shorter_universe(comparisons):
    return _mutate(comparisons, B11B.P0_DO_NOTHING,
                   lambda entry: dict(entry, row_ids=entry["row_ids"][:-1]))


def _with_other_split(comparisons):
    def mutator(entry):
        report = json.loads(json.dumps(entry["report"]))
        report["bound_hashes"]["split_plan_sha256"] = "0" * 64
        return dict(entry, report=report)
    return _mutate(comparisons, B11B.P0_DO_NOTHING, mutator)


def _with_other_horizon(comparisons):
    def mutator(entry):
        report = json.loads(json.dumps(entry["report"]))
        report["cohort"]["horizon_name"] = "h_10000_slots"
        return dict(entry, report=report)
    return _mutate(comparisons, B11B.P0_DO_NOTHING, mutator)


def _with_other_cost(comparisons):
    def mutator(entry):
        report = json.loads(json.dumps(entry["report"]))
        report["cohort"]["cost_policy_id"] = "a_different_cost_policy"
        return dict(entry, report=report)
    return _mutate(comparisons, B11B.P0_DO_NOTHING, mutator)


def gate(corpus=None):
    """The whole seam, twice, plus every refusal. Deterministic or it is a finding."""
    corpus = FIXTURES.build_corpus() if corpus is None else corpus
    # The bundle is built once and reused for the refusal checks. Running the whole seam a third
    # time to re-derive something already in hand is a third of the gate's wall clock for nothing.
    bundle = compare_all(corpus)
    first = publication(bundle)
    second = publication(compare_all(FIXTURES.permuted(corpus)))
    findings = []
    if ENGINE.canonical_bytes(first) != ENGINE.canonical_bytes(second):
        findings.append("the publication changes when the rows are permuted")

    findings += check_refusals(bundle)

    for policy, published in first["comparisons"].items():
        if sorted(published["bases_published"]) != sorted(EVAL.BASES):
            findings.append(f"{policy}: does not publish both bases")
        if published["grouped_uncertainty"]["groups"] < 2:
            findings.append(
                f"{policy}: grouped uncertainty over {published['grouped_uncertainty']['groups']} "
                "group(s) has nothing to leave out; the R5 closure has collapsed")
        for side in ("model", "baseline"):
            if side not in published["entry_counts"]:
                findings.append(f"{policy}: {side} entry counts are not published")
    if not first["comparisons"][PRIMARY_COMPARATOR]["abstentions"]:
        findings.append("no abstention was recorded, so the abstention accounting proves nothing")
    if first["b11b_figures_imported"] is not False:
        findings.append("a B11b figure was imported")

    report = {
        "schema_version": SCHEMA_VERSION,
        "publication": first,
        "deterministic_under_permutation": ENGINE.canonical_bytes(first)
        == ENGINE.canonical_bytes(second),
        "refusals_checked": 12,
        "findings": findings,
        "passed": not findings,
    }
    assert_no_float(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--publish", action="store_true", help="run the seam and print the report")
    parser.add_argument("--gate", action="store_true", help="run the gate; non-zero on a finding")
    args = parser.parse_args(argv)
    if args.gate:
        report = gate()
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["passed"] else 2
    if not args.publish:
        parser.error("nothing to do; --publish runs the seam, --gate checks it")
    print(json.dumps(publication(compare_all()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PREREG.ModelPreregRefused as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(2)
