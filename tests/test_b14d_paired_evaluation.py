"""B14d — the integration guards, each shown to be able to refuse.

The seam joins B14c's model output to B14b's evaluation harness over one corpus and one split. What
can go wrong here is not arithmetic — both sides are already exact — but the comparison being made
between two things that were never comparable. Every test below breaks one of those joins.
"""
import importlib.util
import json
import pathlib
import unittest
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B14D = _load("b14d_paired_evaluation", "b14d_paired_evaluation.py")
# One module graph, through the seam. Loading the engine or the evaluator again by path would give
# this file exception classes nobody raises.
ENGINE = B14D.ENGINE
EVAL = B14D.EVAL
PREREG = B14D.PREREG
SPLIT = B14D.SPLIT
B11B = B14D.B11B
Refused = B14D.PairedEvaluationRefused

_BUNDLE = None


def bundle():
    """The seam, run once for the whole file. It is the expensive part."""
    global _BUNDLE
    if _BUNDLE is None:
        _BUNDLE = B14D.compare_all()
    return _BUNDLE


def subject(row_id="s1", label=True):
    return {"row_id": row_id, "label_value": label}


class TestSegmentMapping(unittest.TestCase):
    def test_calibration_maps_to_training_not_beside_it(self):
        """The freeze puts the calibration fold chronologically last INSIDE training."""
        self.assertEqual(SPLIT.SEGMENT_TRAIN, B14D.SEGMENT_MAP["fit"])
        self.assertEqual(SPLIT.SEGMENT_TRAIN, B14D.SEGMENT_MAP["calibration"])
        self.assertEqual(SPLIT.SEGMENT_VALIDATION, B14D.SEGMENT_MAP["validation"])
        self.assertEqual(SPLIT.SEGMENT_TEST, B14D.SEGMENT_MAP["test"])

    def test_every_engine_segment_is_mapped(self):
        self.assertEqual(sorted(ENGINE.SEGMENTS), sorted(B14D.SEGMENT_MAP))


class TestPolicyReinstantiation(unittest.TestCase):
    """The policy DEFINITIONS are portable; B11b's figures are not."""

    def test_p0_never_enters_and_risks_nothing(self):
        side = B14D.policy_side(B11B.P0_DO_NOTHING, subject())
        self.assertEqual(EVAL.BUCKET_NOT_ENTERED, side["outcome_bucket"])
        self.assertEqual(0, side["deployed_capital_lamports"])
        self.assertIsNone(side["net_pnl_lamports"])

    def test_p1_enters_every_row_at_the_frozen_order_size(self):
        side = B14D.policy_side(B11B.P1_ALL_ELIGIBLE, subject())
        self.assertEqual(B11B.ORDER_SIZE_LAMPORTS, side["deployed_capital_lamports"])

    def test_p2_uses_b11bs_own_frozen_hash_rule(self):
        """Recomputed from B11b's code, not from a paraphrase that could drift from it."""
        for identifier in ("a", "b", "c", "d", "e"):
            with self.subTest(identifier=identifier):
                entered = (B14D.policy_side(B11B.P2_RANDOM_CONTROL, subject(identifier))
                           ["deployed_capital_lamports"] > 0)
                self.assertEqual(B11B.mint_hash_selected(identifier), entered)

    def test_p2_is_a_strict_subset_of_p1(self):
        """B11b's own invariant: entries(P2) is a subset of entries(P1)."""
        for index in range(60):
            identifier = f"row-{index}"
            with self.subTest(identifier=identifier):
                if B14D.policy_side(B11B.P2_RANDOM_CONTROL,
                                    subject(identifier))["deployed_capital_lamports"]:
                    self.assertTrue(B14D.policy_side(B11B.P1_ALL_ELIGIBLE, subject(identifier))
                                    ["deployed_capital_lamports"])

    def test_an_unknown_policy_is_refused(self):
        with self.assertRaisesRegex(Refused, "portable comparator policies"):
            B14D.policy_side("P9_invented", subject())

    def test_the_comparator_set_is_the_three_portable_ones(self):
        self.assertEqual((B11B.P1_ALL_ELIGIBLE, B11B.P0_DO_NOTHING, B11B.P2_RANDOM_CONTROL),
                         B14D.COMPARATOR_POLICIES)
        self.assertEqual(B11B.P1_ALL_ELIGIBLE, B14D.PRIMARY_COMPARATOR)


class TestOutcomesBelongToTheRow(unittest.TestCase):
    def test_both_sides_see_the_same_outcome_for_a_row(self):
        """A position is a position. Two sides that entered the same row realise the same thing."""
        for index in range(40):
            identifier = f"row-{index}"
            if not B11B.mint_hash_selected(identifier):
                continue
            with self.subTest(identifier=identifier):
                one = B14D.policy_side(B11B.P1_ALL_ELIGIBLE, subject(identifier))
                two = B14D.policy_side(B11B.P2_RANDOM_CONTROL, subject(identifier))
                self.assertEqual(one, two)

    def test_a_censored_outcome_carries_no_realised_figure(self):
        """Passing the position's cost through as a loss is the recoding B14b exists to prevent."""
        censored = {"bucket": EVAL.BUCKET_RIGHT_CENSORED, "net_pnl_lamports": None,
                    "equity_path_lamports": None}
        side = B14D._entered_side(subject(), censored)
        self.assertIsNone(side["net_pnl_lamports"])
        self.assertIsNone(side["realised_label"])
        self.assertEqual(B11B.ORDER_SIZE_LAMPORTS, side["deployed_capital_lamports"])
        EVAL.assert_side(side, "censored entered side")

    def test_b14b_refuses_a_censored_side_that_claims_a_figure(self):
        bad = B14D._side(EVAL.BUCKET_RIGHT_CENSORED, -100, B11B.ORDER_SIZE_LAMPORTS)
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "recoding this module exists"):
            EVAL.assert_side(bad, "censored")

    def test_the_engine_never_sees_the_outcome(self):
        """The label drives the fit; the P&L must not be reachable from any feature."""
        source = (ROOT / "scripts" / "b14c_model_engine.py").read_text()
        for token in ("net_pnl", "synthetic_outcome", "equity_path"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


class TestAbstentionAccounting(unittest.TestCase):
    def test_an_abstention_deploys_nothing_and_is_not_at_risk(self):
        side = B14D._side(EVAL.BUCKET_NO_DECISION, None, 0)
        EVAL.assert_side(side, "abstention")
        self.assertNotIn(EVAL.BUCKET_NO_DECISION, EVAL.AT_RISK_BUCKETS)

    def test_the_published_counts_reconcile(self):
        comparison = bundle()["comparisons"][B14D.PRIMARY_COMPARATOR]
        report = comparison["report"]
        census = report["metrics"]["cohort_wide"][EVAL.METRIC_COUNTS]["model"]
        self.assertEqual(sum(comparison["abstentions"].values()),
                         census[EVAL.BUCKET_NO_DECISION])
        self.assertEqual(report["cohort"]["rows"], sum(census.values()))

    def test_a_hidden_abstention_is_refused(self):
        report = bundle()["comparisons"][B14D.PRIMARY_COMPARATOR]["report"]
        with self.assertRaisesRegex(Refused, "survivorship filter"):
            B14D.assert_abstentions_reconcile(report, {}, [1])

    def test_a_census_that_does_not_cover_the_cohort_is_refused(self):
        comparison = bundle()["comparisons"][B14D.PRIMARY_COMPARATOR]
        with self.assertRaisesRegex(Refused, "exactly one bucket"):
            B14D.assert_abstentions_reconcile(comparison["report"], comparison["abstentions"],
                                              [1] * 99999)

    def test_abstentions_actually_occurred(self):
        """An accounting rule that never has anything to account for proves nothing."""
        self.assertTrue(bundle()["comparisons"][B14D.PRIMARY_COMPARATOR]["abstentions"])


class TestComparabilityGuards(unittest.TestCase):
    def setUp(self):
        self.comparisons = bundle()["comparisons"]

    def test_the_real_comparisons_share_everything_that_matters(self):
        self.assertTrue(B14D.assert_shared_row_universe(self.comparisons))
        self.assertTrue(B14D.assert_shared_split(self.comparisons))
        self.assertTrue(B14D.assert_comparable_assumptions(self.comparisons))

    def test_an_unshared_row_universe_is_refused(self):
        with self.assertRaisesRegex(Refused, "measures the sets"):
            B14D.assert_shared_row_universe(B14D._with_shorter_universe(self.comparisons))

    def test_an_unshared_split_is_refused(self):
        with self.assertRaisesRegex(Refused, "two different experiments"):
            B14D.assert_shared_split(B14D._with_other_split(self.comparisons))

    def test_a_mismatched_horizon_is_refused(self):
        with self.assertRaisesRegex(Refused, "horizon_name"):
            B14D.assert_comparable_assumptions(B14D._with_other_horizon(self.comparisons))

    def test_a_mismatched_cost_policy_is_refused(self):
        with self.assertRaisesRegex(Refused, "cost_policy_id"):
            B14D.assert_comparable_assumptions(B14D._with_other_cost(self.comparisons))

    def test_the_row_universe_is_shared_by_construction(self):
        """Both sides live on the SAME row, so they cannot be computed over different subjects."""
        rows, _abstentions, _groups = B14D.build_rows(
            bundle()["corpus"], bundle()["selection"]["selected"]["fitted"], B11B.P1_ALL_ELIGIBLE)
        for row in rows[:5]:
            with self.subTest(row=row["row_id"]):
                self.assertIn("model", row)
                self.assertIn("baseline", row)


class TestSelectionMetricGuard(unittest.TestCase):
    def test_selecting_by_realised_return_is_refused(self):
        for metric in B14D.REALISED_RETURN_SELECTION_METRICS:
            with self.subTest(metric=metric):
                with self.assertRaisesRegex(Refused, "launders the selection into a result"):
                    B14D.assert_selection_was_not_realised_return(metric)

    def test_the_metric_actually_used_passes(self):
        self.assertTrue(
            B14D.assert_selection_was_not_realised_return("brier_score_exact_rational"))

    def test_the_check_is_case_insensitive(self):
        with self.assertRaises(Refused):
            B14D.assert_selection_was_not_realised_return("Capital_Weighted_Return")


class TestCrossWindow(unittest.TestCase):
    def test_comparing_across_windows_is_refused(self):
        with self.assertRaisesRegex(ENGINE.ModelEngineRefused, "two windows"):
            ENGINE.refuse_cross_window_comparison("synthetic-b14c-fixture", "b11a")

    def test_the_publication_states_no_b11b_figure_was_imported(self):
        self.assertFalse(B14D.publication(bundle())["b11b_figures_imported"])

    def test_no_b11b_figure_is_reachable_from_this_module(self):
        """The policy definitions are imported; nothing that carries a B11a number is."""
        source = (ROOT / "scripts" / "b14d_paired_evaluation.py").read_text()
        for token in ("b11b_baseline_metrics", "B11A_", "b11a_outcomes", "unlock_evidence"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


class TestFitGateStaysShut(unittest.TestCase):
    def test_a_real_window_cannot_be_evaluated_through_this_seam(self):
        with self.assertRaises(PREREG.FitRefused):
            B14D.build_rows({"window_id": "a-real-window"}, None, B11B.P1_ALL_ELIGIBLE)

    def test_b11a_is_refused_by_name(self):
        with self.assertRaisesRegex(PREREG.FitRefused, "permanently ineligible"):
            B14D.build_rows({"window_id": "b11a-fresh-cohort-2026-08-02"}, None,
                            B11B.P1_ALL_ELIGIBLE)

    def test_eligible_windows_is_still_empty(self):
        self.assertEqual([], PREREG.read_preregistration()["eligibility"]["eligible_windows"])


class TestDifferencesAndCounts(unittest.TestCase):
    def setUp(self):
        self.comparison = bundle()["comparisons"][B14D.PRIMARY_COMPARATOR]

    def test_differences_are_published_on_both_bases(self):
        self.assertEqual(sorted(EVAL.BASES), sorted(self.comparison["exact_differences"]))

    def test_a_difference_against_an_undefined_return_is_not_zero(self):
        """P0 deploys nothing, so its capital-weighted return does not exist."""
        p0 = bundle()["comparisons"][B11B.P0_DO_NOTHING]
        for basis in EVAL.BASES:
            with self.subTest(basis=basis):
                self.assertIsNone(
                    p0["exact_differences"][basis][EVAL.METRIC_CAPITAL_WEIGHTED_RETURN])

    def test_both_entry_counts_are_published(self):
        counts = self.comparison["entry_counts"]
        for side in ("model", "baseline"):
            with self.subTest(side=side):
                for field in ("entered", "evaluable", "declined", "abstained"):
                    self.assertIn(field, counts[side])

    def test_the_model_declines_more_than_the_all_in_policy(self):
        """The coverage difference is where a selective model's effect actually lands."""
        counts = self.comparison["entry_counts"]
        self.assertLess(counts["model"]["entered"], counts["baseline"]["entered"])

    def test_the_paired_difference_is_structurally_zero_and_says_so(self):
        """Not a bug: order size lives on the row, so a paired row cannot differ.

        Pinned as a test because a reader who saw a zero here without the note would conclude the
        two sides performed alike, when the metric simply had nothing to measure.
        """
        observed = self.comparison["exact_differences"][EVAL.BASIS_OBSERVED]
        self.assertEqual(0, observed[EVAL.METRIC_PAIRED_DIFFERENCE]["value"])
        self.assertIn("structurally ZERO", B14D.PAIRED_DIFFERENCE_NOTE)
        self.assertIn("paired_difference_note", B14D.publication(bundle()))

    def test_the_whole_cohort_basis_is_not_the_observed_one(self):
        """If the two bases agreed everywhere, publishing both would be decoration."""
        differing = [basis for basis in EVAL.BASES]
        self.assertNotEqual(
            self.comparison["exact_differences"][differing[0]][EVAL.METRIC_TOTAL_NET_PNL],
            self.comparison["exact_differences"][differing[1]][EVAL.METRIC_TOTAL_NET_PNL])


class TestGroupedUncertainty(unittest.TestCase):
    def test_the_jackknife_has_more_than_one_group_to_leave_out(self):
        """The defect this replaced: R5's closure collapsed 404 rows into a single component.

        With identities drawn independently over a small space the transitive closure produces a
        giant component, the jackknife has nothing to omit, and the empty spread reads as a
        formatting problem rather than the degenerate grouping it is.
        """
        for policy, published in B14D.publication(bundle())["comparisons"].items():
            with self.subTest(policy=policy):
                self.assertGreater(published["grouped_uncertainty"]["groups"], 1)
                self.assertIsNotNone(published["grouped_uncertainty"]["minimum"])

    def test_grouping_is_the_r5_closure_over_creator_and_user_pooled(self):
        rows = [dict(B14D.identity_of({"row_id": f"r{i}"}), row_id=f"r{i}") for i in range(200)]
        groups = SPLIT.identity_groups(rows)
        self.assertGreater(len(groups), 1)
        self.assertEqual(200, sum(len(members) for members in groups.values()))

    def test_two_rows_sharing_a_creator_land_in_one_group(self):
        rows = [{"row_id": "a", "creator": "c1", "user": "u1"},
                {"row_id": "b", "creator": "c1", "user": "u2"},
                {"row_id": "c", "creator": "c2", "user": "u3"}]
        groups = SPLIT.identity_groups(rows)
        self.assertEqual(SPLIT.group_of(groups, "a"), SPLIT.group_of(groups, "b"))
        self.assertNotEqual(SPLIT.group_of(groups, "a"), SPLIT.group_of(groups, "c"))


class TestNoFloat(unittest.TestCase):
    def test_the_publication_carries_no_float(self):
        published = B14D.publication(bundle())
        B14D.assert_no_float(published)

        def walk(node, path="$"):
            self.assertNotIsInstance(node, float, path)
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{path}[{index}]")
        walk(json.loads(json.dumps(published)))

    def test_a_float_is_refused(self):
        with self.assertRaises(ENGINE.ModelEngineRefused):
            B14D.assert_no_float({"metric": 0.5})


class TestTheGate(unittest.TestCase):
    """The whole seam twice, plus every refusal. Slow on purpose."""

    def test_the_gate_passes_with_no_findings(self):
        report = B14D.gate()
        self.assertEqual([], report["findings"])
        self.assertTrue(report["passed"])
        self.assertTrue(report["deterministic_under_permutation"])
        published = report["publication"]
        self.assertFalse(published["eligible_for_b11a"])
        self.assertFalse(published["real_window_fitting_permitted"])
        self.assertFalse(published["b11b_figures_imported"])
        self.assertEqual("not_evaluated", published["performance_status"])
        self.assertEqual(sorted(B14D.COMPARATOR_POLICIES), sorted(published["comparisons"]))


if __name__ == "__main__":
    unittest.main()
