"""Tests for the B14b exact evaluation harness.

Synthetic rows only. No model is fitted, no window is eligible, no real metric is published and no
B11a outcome is read.

One module graph is loaded for the whole file: loading the same module twice by path creates two
distinct exception classes, and an `assertRaises` on the wrong one never matches.
"""
import copy
import importlib.util
import pathlib
import unittest
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FIXTURES = _load("b14b_evaluation_fixtures", "b14b_evaluation_fixtures.py")
EVAL = FIXTURES.EVAL
SPLIT = EVAL.SPLIT
ARTIFACT = EVAL.ARTIFACT
B11B = EVAL.B11B
B10B = EVAL.B10B

MARKED = EVAL.BUCKET_MARKED
OBSERVED, WORST = EVAL.BASIS_OBSERVED, EVAL.BASIS_WORST_CASE
rational = EVAL.rational
side = FIXTURES.side
row = FIXTURES.row


def fraction(value):
    return Fraction(value["numerator"], value["denominator"])


def spec(**overrides):
    base = FIXTURES.build_spec()
    base.update(overrides)
    return base


def evaluate(rows=None, metric_spec=None, plan=None, **kwargs):
    rows = FIXTURES.build_fixture_corpus() if rows is None else rows
    return EVAL.evaluate(rows, metric_spec or FIXTURES.build_spec(),
                         FIXTURES.build_bound_hashes(),
                         split_plan=plan if plan is not None else FIXTURES.build_split_plan(rows),
                         **kwargs)


# --------------------------------------------------------------------------------------------

class TwoBasesTests(unittest.TestCase):
    """A headline over the survivors answers a question nobody asked."""

    def setUp(self):
        self.report = evaluate()

    def test_both_bases_are_published(self):
        for basis in EVAL.BASES:
            with self.subTest(basis=basis):
                self.assertIn(basis, self.report["metrics"])

    def test_every_headline_metric_appears_on_both_bases(self):
        for metric in EVAL.HEADLINE_METRICS:
            for basis in EVAL.BASES:
                with self.subTest(metric=metric, basis=basis):
                    self.assertIn(metric, self.report["metrics"][basis])

    def test_a_report_with_only_one_basis_is_refused(self):
        broken = copy.deepcopy(self.report)
        del broken["metrics"][WORST]
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "both of"):
            EVAL.assert_report(broken)

    def test_a_headline_metric_on_one_basis_alone_is_refused(self):
        """The survivorship this rule exists to prevent, in its most plausible form: the figure is
        computed on both, and only the flattering one is published."""
        broken = copy.deepcopy(self.report)
        del broken["metrics"][WORST][EVAL.METRIC_TOTAL_NET_PNL]
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "survivorship this rule exists"):
            EVAL.assert_report(broken)

    def test_the_worst_case_is_never_better_than_the_observed_figure(self):
        for participant in ("model", "baseline"):
            with self.subTest(participant=participant):
                observed = self.report["metrics"][OBSERVED][EVAL.METRIC_TOTAL_NET_PNL][participant]
                worst = self.report["metrics"][WORST][EVAL.METRIC_TOTAL_NET_PNL][participant]
                self.assertLessEqual(worst, observed)

    def test_the_two_bases_genuinely_differ(self):
        """If they ever stopped differing, mislabelling one as the other would be invisible."""
        self.assertNotEqual(self.report["metrics"][OBSERVED][EVAL.METRIC_TOTAL_NET_PNL],
                            self.report["metrics"][WORST][EVAL.METRIC_TOTAL_NET_PNL])

    def test_the_worst_case_assigns_total_loss_to_at_risk_rows_only(self):
        rows = [row("censored", "g1", side(EVAL.BUCKET_RIGHT_CENSORED, None, 700_000),
                    side(EVAL.BUCKET_RIGHT_CENSORED, None, 700_000)),
                row("declined", "g2", side(EVAL.BUCKET_NOT_ENTERED, None, 0),
                    side(EVAL.BUCKET_NOT_ENTERED, None, 0), order=0)]
        report = evaluate(rows)
        # The censored row loses its deployed capital; the declined row risked nothing.
        self.assertEqual(report["metrics"][WORST][EVAL.METRIC_TOTAL_NET_PNL]["model"], -700_000)
        self.assertEqual(report["metrics"][OBSERVED][EVAL.METRIC_TOTAL_NET_PNL]["model"], 0)

    def test_the_headline_rule_travels_on_the_report(self):
        self.assertEqual(self.report["headline_rule"], EVAL.HEADLINE_RULE)
        broken = copy.deepcopy(self.report)
        broken["headline_rule"] = "the mean of what we could measure"
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "not the one this module applies"):
            EVAL.assert_report(broken)


class CensoringTests(unittest.TestCase):
    """A censored outcome is not a zero and not a loss."""

    def test_a_censored_side_may_not_carry_a_realised_figure(self):
        for bucket in (EVAL.BUCKET_RIGHT_CENSORED, EVAL.BUCKET_STRUCTURAL_EXIT_UNAVAILABLE,
                       EVAL.BUCKET_NO_OBSERVED_STATE, EVAL.BUCKET_NO_DECISION):
            for value in (0, -1, 1):
                with self.subTest(bucket=bucket, value=value):
                    with self.assertRaisesRegex(EVAL.EvaluationRefused, "recoding this module"):
                        EVAL.assert_side(side(bucket, value, 1_000), "side")

    def test_a_censored_side_may_not_carry_a_class_label(self):
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "has no class"):
            EVAL.assert_side(side(EVAL.BUCKET_RIGHT_CENSORED, None, 1_000, label=0), "side")

    def test_every_recoding_treatment_is_refused_by_name(self):
        for treatment in EVAL.CENSORING_TREATMENTS_REFUSED:
            with self.subTest(treatment=treatment):
                with self.assertRaisesRegex(EVAL.EvaluationRefused, "refused by name"):
                    EVAL.assert_metric_spec(spec(censoring_treatment=treatment))

    def test_censored_rows_stay_out_of_the_observed_numerator(self):
        rows = [row("good", "g1", side(MARKED, 100, 1_000), side(MARKED, 50, 1_000)),
                row("censored", "g2", side(EVAL.BUCKET_RIGHT_CENSORED, None, 1_000),
                    side(EVAL.BUCKET_RIGHT_CENSORED, None, 1_000))]
        report = evaluate(rows)
        self.assertEqual(report["metrics"][OBSERVED][EVAL.METRIC_TOTAL_NET_PNL]["model"], 100)
        self.assertEqual(report["metrics"][OBSERVED][EVAL.METRIC_DEPLOYED_CAPITAL]["model"], 1_000)

    def test_censored_rows_stay_in_the_whole_cohort_denominator(self):
        """Out of the numerator, into the count. Those are different things and both matter."""
        report = evaluate()
        observed = report["metrics"][OBSERVED][EVAL.METRIC_DEPLOYED_CAPITAL]["model"]
        worst = report["metrics"][WORST][EVAL.METRIC_DEPLOYED_CAPITAL]["model"]
        self.assertGreater(worst, observed)
        counts = report["metrics"]["cohort_wide"][EVAL.METRIC_COUNTS]["model"]
        self.assertEqual(sum(counts.values()), report["cohort"]["rows"])

    def test_every_bucket_is_counted_over_the_whole_cohort(self):
        counts = evaluate()["metrics"]["cohort_wide"][EVAL.METRIC_COUNTS]
        for participant in ("model", "baseline"):
            with self.subTest(participant=participant):
                self.assertEqual(set(counts[participant]), set(EVAL.BUCKETS))

    def test_an_undeclared_censoring_treatment_is_refused(self):
        """The refused-by-name list catches the recodings anyone would reach for; this catches the
        one nobody thought of."""
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "is not one of"):
            EVAL.assert_metric_spec(spec(censoring_treatment="handled_sensibly"))

    def test_a_declined_decision_may_not_deploy_capital(self):
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "risked nothing"):
            EVAL.assert_side(side(EVAL.BUCKET_NOT_ENTERED, None, 500), "side")


class DenominatorTests(unittest.TestCase):
    """The denominator decides the answer, so it is never quietly filtered."""

    def test_the_capital_weighted_return_uses_the_capital_of_its_own_basis(self):
        report = evaluate()
        for basis in EVAL.BASES:
            with self.subTest(basis=basis):
                pnl = report["metrics"][basis][EVAL.METRIC_TOTAL_NET_PNL]["model"]
                capital = report["metrics"][basis][EVAL.METRIC_DEPLOYED_CAPITAL]["model"]
                self.assertEqual(
                    fraction(report["metrics"][basis][EVAL.METRIC_CAPITAL_WEIGHTED_RETURN]
                             ["model"]),
                    Fraction(pnl, capital))

    def test_a_return_over_no_capital_is_undefined_not_zero(self):
        self.assertIsNone(EVAL.capital_weighted_return(0, 0))
        self.assertIsNone(EVAL.capital_weighted_return(100, 0))

    def test_the_two_bases_use_different_denominators(self):
        report = evaluate()
        self.assertNotEqual(report["metrics"][OBSERVED][EVAL.METRIC_DEPLOYED_CAPITAL]["model"],
                            report["metrics"][WORST][EVAL.METRIC_DEPLOYED_CAPITAL]["model"])


class PairingTests(unittest.TestCase):
    """Selection on evaluability is selection on an outcome of the comparison."""

    def test_the_paired_cohort_is_exactly_the_rows_both_sides_produced(self):
        report = evaluate()
        rows = FIXTURES.build_fixture_corpus()
        expected = sorted(r["row_id"] for r in rows
                          if r["model"]["outcome_bucket"] == MARKED
                          and r["baseline"]["outcome_bucket"] == MARKED)
        self.assertEqual(report["pairing"]["paired_row_ids"], expected)

    def test_a_hand_picked_paired_cohort_is_refused(self):
        rows = FIXTURES.build_fixture_corpus()
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "an outcome of the comparison"):
            EVAL.assert_paired_cohort(rows, [rows[0]["row_id"]])

    def test_the_evaluability_asymmetry_is_published(self):
        report = evaluate()
        self.assertEqual(report["pairing"]["model_evaluable_only"], 1)
        self.assertEqual(report["pairing"]["baseline_evaluable_only"], 1)
        self.assertTrue(report["pairing"]["selection_on_evaluability_possible"])

    def test_an_asymmetric_cohort_reports_it_rather_than_hiding_it(self):
        rows = [row("both", "g1", side(MARKED, 10, 100), side(MARKED, 5, 100)),
                row("model-only", "g2", side(MARKED, 10, 100),
                    side(EVAL.BUCKET_RIGHT_CENSORED, None, 100))]
        report = evaluate(rows)
        self.assertEqual(report["pairing"]["model_evaluable_only"], 1)
        self.assertEqual(report["pairing"]["evaluability_asymmetry"], 1)
        self.assertEqual(report["metrics"][OBSERVED][EVAL.METRIC_PAIRED_DIFFERENCE]["rows"], 1)

    def test_the_paired_difference_is_the_sum_of_per_decision_differences(self):
        rows = [row("a", "g1", side(MARKED, 300, 100), side(MARKED, 100, 100)),
                row("b", "g2", side(MARKED, -50, 100), side(MARKED, 20, 100))]
        report = evaluate(rows)
        self.assertEqual(report["metrics"][OBSERVED][EVAL.METRIC_PAIRED_DIFFERENCE]["value"],
                         (300 - 100) + (-50 - 20))

    def test_the_paired_difference_sign_follows_model_minus_baseline(self):
        losing = evaluate([row("a", "g1", side(MARKED, 10, 100), side(MARKED, 90, 100))])
        winning = evaluate([row("a", "g1", side(MARKED, 90, 100), side(MARKED, 10, 100))])
        self.assertLess(losing["metrics"][OBSERVED][EVAL.METRIC_PAIRED_DIFFERENCE]["value"], 0)
        self.assertGreater(winning["metrics"][OBSERVED][EVAL.METRIC_PAIRED_DIFFERENCE]["value"], 0)

    def test_order_size_horizon_and_cost_policy_cannot_differ_between_sides(self):
        """Made unrepresentable rather than checked: they live on the row."""
        for field in ("order_size_lamports", "cost_policy_id", "horizon_name"):
            with self.subTest(field=field):
                self.assertNotIn(field, EVAL.SIDE_FIELDS)
                self.assertIn(field, EVAL.ROW_FIELDS)
        broken = side(MARKED, 10, 100)
        broken["order_size_lamports"] = 999
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "not a paired comparison"):
            EVAL.assert_side(broken, "side")

    def test_a_cohort_mixing_horizons_is_refused(self):
        rows = FIXTURES.build_fixture_corpus()
        rows[1] = dict(rows[1], horizon_name="h_60_slots")
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "different questions"):
            evaluate(rows)

    def test_a_cohort_mixing_cost_policies_is_refused(self):
        rows = FIXTURES.build_fixture_corpus()
        rows[1] = dict(rows[1], cost_policy_id="another_cost_policy")
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "different questions"):
            evaluate(rows)


class ExactArithmeticTests(unittest.TestCase):
    """Checked against Fraction, which knows nothing about this implementation."""

    def test_the_brier_score_matches_an_independent_oracle(self):
        observations = [(rational(9, 10), 1), (rational(3, 10), 0), (rational(1, 2), 1)]
        expected = sum((Fraction(p["numerator"], p["denominator"]) - y) ** 2
                       for p, y in observations) / len(observations)
        self.assertEqual(fraction(EVAL.brier(observations)), expected)

    def test_the_brier_score_over_nothing_is_undefined_not_zero(self):
        self.assertIsNone(EVAL.brier([]))

    def test_concordance_counts_only_comparable_pairs(self):
        """Two identical outcomes cannot rank each other, and counting them would let a model that
        separates nothing score one half by default."""
        result = EVAL.concordance([(rational(9, 10), 1), (rational(1, 10), 1)])
        self.assertEqual(result["comparable_pairs"], 0)
        self.assertIsNone(result["concordance"])

    def test_concordance_is_exact_and_counts_score_ties_as_half(self):
        pairs = [(rational(9, 10), 1), (rational(1, 10), 0), (rational(5, 10), 1),
                 (rational(5, 10), 0)]
        result = EVAL.concordance(pairs)
        self.assertEqual(result["comparable_pairs"],
                         result["concordant"] + result["discordant"] + result["tied_score"])
        self.assertEqual(result["tied_score"], 1)
        expected = Fraction(2 * result["concordant"] + result["tied_score"],
                            2 * result["comparable_pairs"])
        self.assertEqual(fraction(result["concordance"]), expected)

    def test_a_perfect_ranking_scores_one_and_a_reversed_one_scores_zero(self):
        good = EVAL.concordance([(rational(9, 10), 1), (rational(1, 10), 0)])
        bad = EVAL.concordance([(rational(1, 10), 1), (rational(9, 10), 0)])
        self.assertEqual(fraction(good["concordance"]), Fraction(1))
        self.assertEqual(fraction(bad["concordance"]), Fraction(0))

    def test_the_drawdown_is_taken_from_the_path_not_the_endpoints(self):
        """A position that ended flat after losing four fifths of its value is not the same risk as
        one that never moved."""
        self.assertEqual(EVAL.maximum_drawdown([0, 500, -700, 0]), 1_200)
        self.assertEqual(EVAL.maximum_drawdown([0, 0, 0]), 0)
        self.assertEqual(EVAL.maximum_drawdown([100, 40]), 60)

    def test_no_float_may_appear_in_a_report(self):
        report = evaluate()
        self.assertTrue(EVAL.assert_no_float(report))
        report["metrics"][OBSERVED][EVAL.METRIC_TOTAL_NET_PNL]["model"] = 1.5
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "reconcile against the counts"):
            EVAL.assert_no_float(report)

    def test_a_float_model_score_is_refused(self):
        """Caught by B13d's rational validator, which this module re-exports rather than
        reimplements — so the refusal carries B13d's class, an ANCESTOR of this module's. Every
        refusal in the project descends from one base, and that is what a caller catches."""
        with self.assertRaises(B10B.FreezeViolation):
            EVAL.assert_side(side(MARKED, 10, 100, probability=0.9, label=1), "side")
        with self.assertRaisesRegex(B10B.FreezeViolation, "numerator/denominator pair"):
            EVAL.assert_side(side(MARKED, 10, 100, probability=0.9, label=1), "side")

    def test_every_refusal_in_the_chain_shares_one_base(self):
        """The modules build on each other, so their exception classes form a chain. A caller who
        catches the project base catches all of them; one who catches only the newest misses the
        validators it inherited."""
        for klass in (EVAL.EvaluationRefused, EVAL.SpecificationMissing, ARTIFACT.ArtifactRefused,
                      SPLIT.SplitRefused, SPLIT.StatusGated):
            with self.subTest(klass=klass.__name__):
                self.assertTrue(issubclass(klass, B10B.FreezeViolation))
        self.assertTrue(issubclass(EVAL.EvaluationRefused, ARTIFACT.ArtifactRefused))
        self.assertFalse(issubclass(EVAL.SPLIT.B13F.B13D.ConcentrationRefused,
                                    EVAL.EvaluationRefused))

    def test_a_probability_outside_zero_and_one_is_refused(self):
        for value in (rational(-1, 10), rational(11, 10)):
            with self.subTest(value=value):
                with self.assertRaisesRegex(EVAL.EvaluationRefused, "outside"):
                    EVAL.assert_side(side(MARKED, 10, 100, probability=value, label=1), "side")

    def test_the_exact_ratio_boundary_holds_at_zero_and_one(self):
        for value in (rational(0, 1), rational(1, 1)):
            with self.subTest(value=value):
                self.assertTrue(EVAL.assert_side(
                    side(MARKED, 10, 100, probability=value, label=1), "side"))


class CalibrationTests(unittest.TestCase):
    """Bin edges chosen by looking at the evaluation fold are edges fitted to the answer."""

    def test_edges_must_name_the_folds_they_were_chosen_on(self):
        with self.assertRaisesRegex(EVAL.SpecificationMissing, "fitted to the answer"):
            EVAL.assert_metric_spec(spec(calibration_bin_edges_fitted_on=[]))

    def test_declaring_the_metric_without_edges_is_refused(self):
        with self.assertRaisesRegex(EVAL.SpecificationMissing, "no bin edges were preregistered"):
            EVAL.assert_metric_spec(spec(calibration_bin_edges=None,
                                         calibration_bin_edges_fitted_on=None))

    def test_edges_must_strictly_increase(self):
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "strictly increase"):
            EVAL.assert_metric_spec(spec(calibration_bin_edges=[rational(1, 2), rational(1, 2)]))

    def test_bins_report_exact_observed_rates(self):
        observations = [(rational(1, 10), 0), (rational(2, 10), 1), (rational(9, 10), 1)]
        bins = EVAL.calibration_bins(observations, [rational(0, 1), rational(1, 2),
                                                    rational(1, 1)])
        self.assertEqual(bins[0]["count"], 2)
        self.assertEqual(fraction(bins[0]["observed_rate"]), Fraction(1, 2))
        self.assertEqual(fraction(bins[0]["mean_predicted"]), Fraction(3, 20))
        self.assertEqual(bins[1]["count"], 1)

    def test_an_empty_bin_reports_no_rate_rather_than_zero(self):
        bins = EVAL.calibration_bins([(rational(9, 10), 1)],
                                     [rational(0, 1), rational(1, 2), rational(1, 1)])
        self.assertEqual(bins[0]["count"], 0)
        self.assertIsNone(bins[0]["observed_rate"])
        self.assertIsNone(bins[0]["mean_predicted"])

    def test_the_report_carries_where_the_edges_came_from(self):
        report = evaluate()
        self.assertEqual(report["metrics"]["cohort_wide"][EVAL.METRIC_CALIBRATION]
                         ["edges_fitted_on"], ["fold-1-train"])


class SpecificationTests(unittest.TestCase):
    """Nothing here has a default."""

    def test_every_field_is_required(self):
        for field in EVAL.METRIC_SPEC_FIELDS:
            with self.subTest(missing=field):
                broken = {k: v for k, v in spec().items() if k != field}
                with self.assertRaises(EVAL.SpecificationMissing):
                    EVAL.assert_metric_spec(broken)

    def test_the_refusal_says_why_there_is_no_default(self):
        broken = {k: v for k, v in spec().items() if k != "class_threshold"}
        try:
            EVAL.assert_metric_spec(broken)
        except EVAL.SpecificationMissing as error:
            self.assertIn("made it for everybody", str(error))

    def test_a_specification_declaring_no_metric_measures_nothing(self):
        with self.assertRaisesRegex(EVAL.SpecificationMissing, "measures nothing"):
            EVAL.assert_metric_spec(spec(metrics_declared=[]))

    def test_a_missing_specification_is_distinguishable_from_bad_data(self):
        self.assertTrue(issubclass(EVAL.SpecificationMissing, EVAL.EvaluationRefused))

    def test_the_contract_offers_no_defaults(self):
        import io, contextlib, json
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            EVAL.main(["--contract"])
        contract = json.loads(buffer.getvalue())
        for field in ("default_metric", "default_class_threshold",
                      "default_calibration_bin_edges", "default_performance_cutoff"):
            with self.subTest(field=field):
                self.assertIsNone(contract[field])


class MultiplicityTests(unittest.TestCase):
    """The correction binds the frozen family, not the cells that happened to be computed."""

    def test_the_frozen_family_is_sixteen(self):
        self.assertEqual(B11B.MULTIPLICITY_FAMILY_SIZE, 16)
        self.assertEqual(spec()["family_size"], 16)
        self.assertTrue(EVAL.assert_family_binds_frozen_size(spec()))

    def test_a_shrunken_family_is_refused(self):
        for size in (1, 2, 15):
            with self.subTest(size=size):
                with self.assertRaisesRegex(EVAL.EvaluationRefused, "shrinks the correction"):
                    EVAL.assert_family_binds_frozen_size(spec(family_size=size))

    def test_an_inflated_family_is_refused_too(self):
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "shrank between preregistration"):
            EVAL.assert_family_binds_frozen_size(spec(family_size=64))

    def test_the_primary_cell_may_not_be_promoted_after_the_numbers_are_in(self):
        promoted = spec(primary_cell={"policy_id": "P3_creator_initial_buy_present",
                                      "horizon_name": B11B.PRIMARY_HORIZON})
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "choosing the hypothesis to match"):
            EVAL.assert_primary_not_promoted(promoted)

    def test_the_frozen_primary_is_b11bs(self):
        self.assertEqual(spec()["primary_cell"],
                         {"policy_id": B11B.PRIMARY_POLICY,
                          "horizon_name": B11B.PRIMARY_HORIZON})
        self.assertTrue(EVAL.assert_primary_not_promoted(spec()))

    def test_a_cell_may_not_be_both_primary_and_secondary(self):
        broken = spec()
        broken["secondary_cells"] = [dict(broken["primary_cell"])]
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "exactly one cell is primary"):
            EVAL.assert_metric_spec(broken)

    def test_more_cells_than_the_family_declares_is_refused(self):
        broken = spec(family_size=1)
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "understates the multiplicity"):
            EVAL.assert_metric_spec(broken)

    def test_the_report_carries_the_family_and_the_primary_it_was_computed_under(self):
        report = evaluate()
        self.assertEqual(report["family_size"], 16)
        self.assertEqual(report["primary_cell"], spec()["primary_cell"])
        broken = copy.deepcopy(report)
        broken["family_size"] = 2
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "disagrees with the specification"):
            EVAL.assert_report(broken, spec())


class GroupedUncertaintyTests(unittest.TestCase):
    """Rows sharing an actor are not independent observations."""

    def test_the_jackknife_leaves_out_whole_groups(self):
        report = evaluate()
        self.assertEqual(report["grouped_uncertainty"]["groups"],
                         len(report["grouped_uncertainty"]["estimates"]))
        omitted = [e["omitted_group"] for e in report["grouped_uncertainty"]["estimates"]]
        self.assertEqual(sorted(omitted), omitted)

    def test_a_jackknife_over_one_group_has_nothing_to_leave_out(self):
        result = EVAL.jackknife_over_groups({"only": 100})
        self.assertEqual(result["estimates"], [])
        self.assertIn("nothing to leave out", result["note"])

    def test_each_estimate_omits_exactly_its_group(self):
        result = EVAL.jackknife_over_groups({"a": 10, "b": 20, "c": 30})
        values = {e["omitted_group"]: fraction(e["value"]) for e in result["estimates"]}
        self.assertEqual(values, {"a": Fraction(50), "b": Fraction(40), "c": Fraction(30)})
        self.assertEqual(fraction(result["minimum"]), Fraction(30))
        self.assertEqual(fraction(result["maximum"]), Fraction(50))

    def test_it_is_a_spread_and_never_a_test(self):
        result = EVAL.jackknife_over_groups({"a": 10, "b": 20})
        self.assertIn("never a p-value", result["note"])
        text = B10B.canonical_json(result).lower()
        for banned in ("p_value", "pvalue", "significan", "confidence_interval"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, text)

    def test_a_group_the_split_plan_does_not_know_is_refused(self):
        """Grouped uncertainty over invented groups is a spread over nothing."""
        rows = FIXTURES.build_fixture_corpus()
        plan = FIXTURES.build_split_plan(rows)
        rows[0] = dict(rows[0], group_id="a-group-nobody-planned")
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "spread over nothing"):
            evaluate(rows, plan=plan)

    def test_rows_of_one_group_move_together(self):
        rows = [row("a", "shared", side(MARKED, 100, 1_000), side(MARKED, 10, 1_000)),
                row("b", "shared", side(MARKED, 200, 1_000), side(MARKED, 20, 1_000)),
                row("c", "other", side(MARKED, 5, 1_000), side(MARKED, 1, 1_000))]
        result = EVAL.jackknife_over_groups({"shared": 300, "other": 5})
        values = {e["omitted_group"]: fraction(e["value"]) for e in result["estimates"]}
        self.assertEqual(values["shared"], Fraction(5))
        self.assertEqual(len(evaluate(rows)["grouped_uncertainty"]["estimates"]), 2)


class StatusTests(unittest.TestCase):
    """Nothing here has been evaluated, and the cluster gate is still open."""

    def test_a_report_ships_as_synthetic_plumbing_only(self):
        report = evaluate()
        self.assertEqual(report["status"], EVAL.STATUS_SYNTHETIC_PLUMBING_ONLY)
        self.assertEqual(report["performance_status"], ARTIFACT.PERFORMANCE_NOT_EVALUATED)

    def test_publication_grade_is_refused_and_names_the_open_gate(self):
        broken = dict(evaluate(), status=EVAL.STATUS_PUBLICATION_GRADE)
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "funding-cluster gate"):
            EVAL.assert_report(broken)

    def test_every_performance_claim_is_refused(self):
        for claim in ARTIFACT.PERFORMANCE_CLAIM_STATUSES:
            with self.subTest(claim=claim):
                broken = dict(evaluate(), performance_status=claim)
                with self.assertRaisesRegex(EVAL.EvaluationRefused, "nobody here has earned"):
                    EVAL.assert_report(broken)

    def test_the_report_binds_everything_that_produced_it(self):
        report = evaluate()
        for field in EVAL.BOUND_HASH_FIELDS:
            with self.subTest(field=field):
                broken = copy.deepcopy(report)
                broken["bound_hashes"][field] = ""
                with self.assertRaisesRegex(EVAL.EvaluationRefused, "not reproducible"):
                    EVAL.assert_report(broken)

    def test_row_hash_drift_changes_the_report_hash(self):
        base = evaluate()
        hashes = FIXTURES.build_bound_hashes()
        hashes["row_evidence_sha256"] = "z" * 64
        drifted = EVAL.evaluate(FIXTURES.build_fixture_corpus(), FIXTURES.build_spec(), hashes)
        self.assertNotEqual(base["report_sha256"], drifted["report_sha256"])

    def test_a_report_computed_under_another_spec_is_refused(self):
        report = evaluate()
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "different metric spec"):
            EVAL.assert_report(report, spec(metric_family_id="another_family"))

    def test_no_b11a_outcome_is_read(self):
        """Asserted against the source, not promised: this module opens no file and connects to no
        database, so there is no path by which an outcome could reach it."""
        source = (ROOT / "scripts" / "b14b_evaluation.py").read_text()
        for banned in ("open(", "sqlite3", ".connect(", "requests", "urllib", "socket"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, source)
        import io, contextlib, json
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            EVAL.main(["--contract"])
        self.assertFalse(json.loads(buffer.getvalue())["b11a_outcomes_read"])


class DeterminismTests(unittest.TestCase):
    """Row order is irrelevant, and the report hash proves it."""

    def test_row_order_does_not_change_the_report(self):
        rows = FIXTURES.build_fixture_corpus()
        forward = evaluate(rows)
        backward = evaluate(list(reversed(rows)))
        self.assertEqual(forward["report_sha256"], backward["report_sha256"])

    def test_a_duplicate_row_id_is_refused(self):
        rows = FIXTURES.build_fixture_corpus()
        rows.append(copy.deepcopy(rows[0]))
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "moves every total"):
            evaluate(rows)

    def test_the_report_hash_covers_everything_but_itself(self):
        report = evaluate()
        self.assertEqual(report["report_sha256"], EVAL.report_hash(report))

    def test_changing_one_outcome_changes_the_report_hash(self):
        rows = FIXTURES.build_fixture_corpus()
        base = evaluate(rows)
        rows[0]["model"]["net_pnl_lamports"] += 1
        self.assertNotEqual(base["report_sha256"], evaluate(rows)["report_sha256"])

    def test_an_undeclared_report_field_is_refused(self):
        broken = dict(evaluate(), notes="a note")
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "undeclared fields"):
            EVAL.assert_report(broken)

    def test_an_undeclared_row_field_is_refused(self):
        rows = FIXTURES.build_fixture_corpus()
        rows[0] = dict(rows[0], extra=1)
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "undeclared fields"):
            evaluate(rows)

    def test_ordered_rows_returns_a_canonical_order(self):
        """Driven directly. The report's sums are order-independent anyway, so a lost sort would
        not move a hash — and the first field that publishes a row list would inherit an order
        nobody chose."""
        rows = FIXTURES.build_fixture_corpus()
        ordered = EVAL.ordered_rows(list(reversed(rows)))
        self.assertEqual([r["row_id"] for r in ordered],
                         sorted(r["row_id"] for r in rows))

    def test_the_fixtures_expose_one_module_graph(self):
        """A second load would give a second set of exception classes, and every `except` in the
        gate would silently stop matching. B14a's fixtures shipped that bug before a test caught
        it."""
        self.assertIs(FIXTURES.SPLIT, EVAL.SPLIT)
        self.assertIs(FIXTURES.ARTIFACT, EVAL.ARTIFACT)
        self.assertIs(FIXTURES.EVAL.SPLIT, SPLIT)

    def test_rows_must_be_a_sequence(self):
        with self.assertRaisesRegex(EVAL.EvaluationRefused, "must be a sequence"):
            EVAL.ordered_rows(FIXTURES.build_fixture_corpus()[0])


class GateTests(unittest.TestCase):
    """The fixture report's own conditions, and its silence about performance."""

    def clean_report(self):
        return {"errors": [], "bases_published": list(EVAL.BASES),
                "headline_metrics_on_both_bases": len(EVAL.HEADLINE_METRICS),
                "worst_case_never_better_than_observed": True,
                "censored_rows_absent_from_every_numerator": True,
                "declined_rows_risk_nothing": True,
                "drawdown_uses_the_path_not_the_endpoints": True, "order_independent": True,
                "refusals_verified": {"censoring_recoded_as_loss": True},
                "status": EVAL.STATUS_SYNTHETIC_PLUMBING_ONLY,
                "performance_status": ARTIFACT.PERFORMANCE_NOT_EVALUATED,
                "metric_values_reported": False, "model_fitted": False,
                "b11a_outcomes_read": False,
                "model_evaluable_only": 1, "baseline_evaluable_only": 1}

    def test_a_clean_report_passes(self):
        self.assertEqual(FIXTURES.gate_failures(self.clean_report()), [])

    def test_every_gate_condition_can_fail(self):
        cases = {
            "integrity errors": {"errors": [{"error": "x"}]},
            "both bases": {"bases_published": [OBSERVED]},
            "every headline metric": {"headline_metrics_on_both_bases": 1},
            "worst_case_never_better_than_observed":
                {"worst_case_never_better_than_observed": False},
            "censored_rows_absent_from_every_numerator":
                {"censored_rows_absent_from_every_numerator": False},
            "declined_rows_risk_nothing": {"declined_rows_risk_nothing": False},
            "drawdown_uses_the_path_not_the_endpoints":
                {"drawdown_uses_the_path_not_the_endpoints": False},
            "order_independent": {"order_independent": False},
            "refusal that must fire": {"refusals_verified": {"a": False}},
            "unattainable status": {"status": EVAL.STATUS_PUBLICATION_GRADE},
            "performance claim": {"performance_status": "profitable"},
            "reports no metric": {"metric_values_reported": True},
            "evaluability asymmetry": {"model_evaluable_only": 0},
        }
        for expected, override in cases.items():
            with self.subTest(condition=expected):
                report = self.clean_report()
                report.update(override)
                failures = FIXTURES.gate_failures(report)
                self.assertTrue(any(expected in failure for failure in failures),
                                f"{expected!r} not in {failures}")

    def test_the_shipped_corpus_passes_its_own_gate(self):
        report = FIXTURES.assert_clean()
        self.assertEqual(report["errors"], [])
        self.assertFalse(report["metric_values_reported"])
        self.assertFalse(report["model_fitted"])
        self.assertFalse(report["b11a_outcomes_read"])

    def test_the_gate_report_publishes_no_metric_value(self):
        """A figure here would be read as a result for a model that does not exist. Scanned over
        field names, since the report carries hex digests that match metric words by accident."""
        def names(value, found=None):
            found = [] if found is None else found
            if isinstance(value, dict):
                for key, child in value.items():
                    found.append(str(key).lower())
                    names(child, found)
            elif isinstance(value, list):
                for child in value:
                    names(child, found)
            return found

        keys = names(FIXTURES.check())
        for banned in ("pnl", "return", "brier", "concordance", "drawdown_lamports", "profit",
                       "sharpe", "capital_weighted"):
            with self.subTest(banned=banned):
                self.assertFalse([k for k in keys if banned in k],
                                 f"{banned!r} appears in a gate-report field name")


if __name__ == "__main__":
    unittest.main()
