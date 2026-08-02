"""B14c engine — the properties the freeze depends on, each shown to be able to fail.

Most tests run against a small corpus built here. One runs the real full-size gate, because a gate
nobody runs is a gate that stops being true.
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


FIXTURES = _load("b14c_model_fixtures", "b14c_model_fixtures.py")
# Reached through the fixtures so there is ONE module graph. A second load by path would give this
# file a different ModelEngineRefused than the engine raises, and every assertRaises would be
# testing a class nobody throws.
ENGINE = FIXTURES.ENGINE
PREREG = ENGINE.PREREG
Refused = ENGINE.ModelEngineRefused
LeakageRefused = ENGINE.LeakageRefused

PAIRS = {"num": "den"}
FEATURES = ("a", "b", "flag", "num")


def small_corpus(fit=80, calibration=80, validation=40, test=40, min_bin=8):
    """A corpus large enough to fit and calibrate, small enough to run in a test."""
    rows = []
    index = 0
    plan = (("fit", fit), ("calibration", calibration), ("validation", validation),
            ("test", test))
    slot = 0
    for segment, count in plan:
        slot += 1000                                    # a gap, so no boundary touches
        for _ in range(count):
            index += 1
            slot += 10
            key = index * 2654435761
            rows.append({
                "row_id": f"r{index:05d}", "t0_slot": slot, "segment": segment,
                "label_status": "observed", "label_value": bool((key % 97) > 40),
                "vector_available": True,
                "features": {"a": key % 97, "b": key % 53, "flag": bool(key % 2),
                             "num": key % 41, "den": 41},
            })
    corpus = {"window_id": "unit-test-fixture", "provenance": ENGINE.SYNTHETIC_CORPUS_MARKER,
              "feature_order": ["a", "b", "flag", "num", "den"], "rational_pairs": dict(PAIRS),
              "min_calibration_bin": min_bin, "rows": rows}
    corpus["row_evidence_sha256"] = FIXTURES.row_evidence(rows)
    return corpus


def row(row_id="x", slot=1, segment="fit", label=True, **features):
    base = {"a": 1, "b": 1, "flag": False, "num": 1, "den": 41}
    base.update(features)
    return {"row_id": row_id, "t0_slot": slot, "segment": segment, "label_status": "observed",
            "label_value": label, "vector_available": True, "features": base}


class TestExactArithmetic(unittest.TestCase):
    def test_a_float_is_refused_at_every_door(self):
        with self.assertRaisesRegex(Refused, "is a float"):
            ENGINE.rational(0.5)
        with self.assertRaisesRegex(Refused, "is a float"):
            ENGINE.rational(1, 2.0)
        with self.assertRaisesRegex(Refused, "may not be serialized"):
            ENGINE.pair(0.25)
        with self.assertRaisesRegex(Refused, "no float may appear"):
            ENGINE.assert_no_float({"a": [1, {"b": 0.5}]})

    def test_a_zero_denominator_is_not_a_number(self):
        with self.assertRaisesRegex(Refused, "zero denominator"):
            ENGINE.rational(1, 0)

    def test_rationals_serialize_as_named_integer_pairs(self):
        self.assertEqual({"numerator": 3, "denominator": 4}, ENGINE.pair(Fraction(6, 8)))

    def test_quantisation_rounds_half_to_even(self):
        """Half-up is biased away from zero, and a bias applied every round accumulates."""
        half = Fraction(1, 2 * ENGINE.QUANTISATION_DENOMINATOR)
        self.assertEqual(Fraction(0), ENGINE.quantise(half))
        self.assertEqual(Fraction(2, ENGINE.QUANTISATION_DENOMINATOR),
                         ENGINE.quantise(Fraction(3, 2 * ENGINE.QUANTISATION_DENOMINATOR)))

    def test_quantisation_is_exact_and_idempotent(self):
        value = ENGINE.quantise(Fraction(1, 3))
        self.assertEqual(value, ENGINE.quantise(value))
        self.assertEqual(ENGINE.QUANTISATION_DENOMINATOR % value.denominator, 0)


class TestFeatureAccess(unittest.TestCase):
    def test_a_rational_pair_is_one_feature_compared_exactly(self):
        self.assertEqual(Fraction(3, 41), ENGINE.feature_value(row(num=3), "num", PAIRS))

    def test_a_zero_denominator_is_missing_not_zero(self):
        """A share of nothing and a share that does not exist are different facts."""
        absent = ENGINE.feature_value(row(num=3, den=0), "num", PAIRS)
        nothing = ENGINE.feature_value(row(num=0, den=41), "num", PAIRS)
        self.assertIs(ENGINE.MISSING, absent)
        self.assertEqual(Fraction(0), nothing)
        self.assertIsNot(absent, nothing, "a share of nothing is not a share that does not exist")

    def test_a_denominator_is_not_offered_as_a_feature_on_its_own(self):
        corpus = small_corpus()
        self.assertNotIn("den", ENGINE.usable_features(corpus))
        self.assertIn("num", ENGINE.usable_features(corpus))

    def test_a_null_reads_as_missing(self):
        self.assertIs(ENGINE.MISSING, ENGINE.feature_value(row(a=None), "a", PAIRS))


class TestCanonicalOrdering(unittest.TestCase):
    def test_rows_are_read_in_canonical_order_not_arrival_order(self):
        rows = [row("b", slot=2), row("a", slot=1)]
        self.assertEqual(["a", "b"], [r["row_id"] for r in ENGINE.canonical_rows(rows)])

    def test_a_duplicate_row_id_breaks_the_total_order_and_is_refused(self):
        with self.assertRaisesRegex(Refused, "not total"):
            ENGINE.canonical_rows([row("a", slot=1), row("a", slot=2)])


class TestChronologyAndLeakage(unittest.TestCase):
    def test_the_real_corpus_is_strictly_chronological(self):
        self.assertEqual(4, len(ENGINE.assert_chronology(small_corpus())))

    def test_touching_segments_are_refused(self):
        corpus = small_corpus()
        rows = [dict(r) for r in corpus["rows"]]
        fit_last = max(r["t0_slot"] for r in rows if r["segment"] == "fit")
        for r in rows:
            if r["segment"] == "calibration":
                r["t0_slot"] = fit_last
        with self.assertRaisesRegex(LeakageRefused, "not a boundary"):
            ENGINE.assert_chronology(dict(corpus, rows=rows))

    def test_an_empty_segment_is_refused(self):
        corpus = small_corpus()
        rows = [r for r in corpus["rows"] if r["segment"] != "calibration"]
        with self.assertRaisesRegex(Refused, "every segment must be used"):
            ENGINE.assert_chronology(dict(corpus, rows=rows))

    def test_thresholds_come_only_from_the_rows_they_are_given(self):
        """Candidates derived from all rows let the evaluation fold choose where the model cuts."""
        training = [row("a", slot=1, a=1), row("b", slot=2, a=3)]
        candidates = ENGINE.threshold_candidates(training, "a", PAIRS)
        self.assertEqual([Fraction(2)], candidates)
        wider = training + [row("c", slot=3, a=99)]
        self.assertNotEqual(candidates, ENGINE.threshold_candidates(wider, "a", PAIRS))


class TestCensoredLabels(unittest.TestCase):
    def test_a_censored_label_is_refused_never_recoded(self):
        for status in ("right_censored", "unavailable", None):
            with self.subTest(status=status):
                with self.assertRaisesRegex(Refused, "never recoded"):
                    ENGINE.label_of({"row_id": "x", "label_status": status})


class TestFitGate(unittest.TestCase):
    def test_a_real_window_may_not_be_fitted(self):
        with self.assertRaises(PREREG.FitRefused):
            ENGINE.assert_synthetic({"window_id": "some-real-window"})

    def test_b11a_may_not_be_fitted(self):
        with self.assertRaisesRegex(PREREG.FitRefused, "permanently ineligible"):
            ENGINE.assert_synthetic({"window_id": "b11a-fresh-cohort-2026-08-02"})

    def test_a_corpus_with_no_provenance_may_not_be_fitted(self):
        with self.assertRaises(PREREG.FitRefused):
            ENGINE.assert_synthetic({})

    def test_an_unknown_segment_name_is_refused(self):
        with self.assertRaisesRegex(Refused, "is not one of"):
            ENGINE.segment_rows(small_corpus(), "holdout")

    def test_only_the_synthetic_marker_passes(self):
        self.assertTrue(ENGINE.assert_synthetic({"provenance": ENGINE.SYNTHETIC_CORPUS_MARKER}))


class TestFamilies(unittest.TestCase):
    def setUp(self):
        self.corpus = small_corpus()
        self.pairs = self.corpus["rational_pairs"]

    def _fit(self, family, hyperparameters):
        document = PREREG.read_preregistration()
        index = [f["id"] for f in document["candidate_families"]].index(family)
        return ENGINE.fit_one(self.corpus, {"family": family, "family_index": index,
                                            "grid_index": 0,
                                            "hyperparameters": hyperparameters})

    def test_every_family_fits_and_predicts_exactly(self):
        for family, hyperparameters in (
                (ENGINE.FAMILY_CONSTANT, {}), (ENGINE.FAMILY_STUMP, {}),
                (ENGINE.FAMILY_CART, {"max_depth": 2, "min_samples_leaf": 8}),
                (ENGINE.FAMILY_BOOSTED, {"rounds": 5, "shrinkage_numerator": 1,
                                         "shrinkage_denominator": 10, "max_depth": 1,
                                         "min_samples_leaf": 8})):
            with self.subTest(family=family):
                fitted = self._fit(family, hyperparameters)
                probability, code = ENGINE.predict(
                    fitted, ENGINE.segment_rows(self.corpus, "test")[0], self.pairs)
                self.assertIsNone(code)
                self.assertIsInstance(probability, Fraction)
                self.assertTrue(0 <= probability <= 1)

    def test_a_deeper_tree_is_never_shallower(self):
        shallow = self._fit(ENGINE.FAMILY_CART, {"max_depth": 1, "min_samples_leaf": 8})
        deep = self._fit(ENGINE.FAMILY_CART, {"max_depth": 3, "min_samples_leaf": 8})
        self.assertLessEqual(shallow["model"]["parameter_count"],
                             deep["model"]["parameter_count"])

    def test_a_leaf_floor_larger_than_the_data_forces_a_constant(self):
        """Correct behaviour, not a bug: no admissible split exists, so the tree is one leaf."""
        fitted = self._fit(ENGINE.FAMILY_CART, {"max_depth": 3, "min_samples_leaf": 10 ** 6})
        self.assertEqual("leaf", fitted["model"]["tree"]["kind"])

    def test_boosting_stays_quantised_every_round(self):
        fitted = self._fit(ENGINE.FAMILY_BOOSTED,
                           {"rounds": 6, "shrinkage_numerator": 1, "shrinkage_denominator": 4,
                            "max_depth": 1, "min_samples_leaf": 8})
        for stump in fitted["model"]["stumps"]:
            for key in ("low", "high"):
                with self.subTest(key=key):
                    self.assertEqual(0, ENGINE.QUANTISATION_DENOMINATOR % stump[key].denominator)

    def test_a_stump_refuses_rather_than_degrading_to_a_constant(self):
        """Reporting one family's number under another family's name is worse than refusing."""
        constant = [row(f"r{i}", slot=i, a=1, b=1, num=1) for i in range(1, 9)]
        with self.assertRaisesRegex(Refused, "silently degraded"):
            ENGINE.fit_stump(constant, ("a", "b"), PAIRS, {})


class TestCalibration(unittest.TestCase):
    def test_calibration_is_monotone(self):
        corpus = small_corpus()
        fitted = ENGINE.fit_one(corpus, {"family": ENGINE.FAMILY_CART, "family_index": 2,
                                         "grid_index": 0,
                                         "hyperparameters": {"max_depth": 3,
                                                             "min_samples_leaf": 8}})
        values = [block["value"] for block in fitted["calibration"]]
        self.assertEqual(values, sorted(values), "PAVA must produce a monotone map")

    def test_every_bin_meets_the_declared_minimum_or_there_is_only_one(self):
        corpus = small_corpus(min_bin=16)
        fitted = ENGINE.fit_one(corpus, {"family": ENGINE.FAMILY_CART, "family_index": 2,
                                         "grid_index": 0,
                                         "hyperparameters": {"max_depth": 3,
                                                             "min_samples_leaf": 8}})
        if len(fitted["calibration"]) > 1:
            for block in fitted["calibration"]:
                self.assertGreaterEqual(block["count"], 16)

    def test_a_calibration_fold_too_thin_collapses_to_one_bin_visibly(self):
        """The defect the first fixture hid: with too few rows every model becomes the base rate.

        It is correct behaviour — a bin of three rows reports no estimate of anything — but it must
        be VISIBLE, because a silent collapse makes every configuration score identically and the
        ranking looks like a tie when it is really an erasure.
        """
        corpus = small_corpus(calibration=20, min_bin=64)
        fitted = ENGINE.fit_one(corpus, {"family": ENGINE.FAMILY_CART, "family_index": 2,
                                         "grid_index": 0,
                                         "hyperparameters": {"max_depth": 3,
                                                             "min_samples_leaf": 8}})
        self.assertEqual(1, len(fitted["calibration"]))

    def test_calibration_reads_only_the_calibration_segment(self):
        """Change the test segment; the calibration map must not move."""
        corpus = small_corpus()
        configuration = {"family": ENGINE.FAMILY_CART, "family_index": 2, "grid_index": 0,
                         "hyperparameters": {"max_depth": 3, "min_samples_leaf": 8}}
        before = ENGINE.fit_one(corpus, configuration)["calibration"]
        rows = [dict(r, label_value=not r["label_value"]) if r["segment"] == "test" else r
                for r in corpus["rows"]]
        after = ENGINE.fit_one(dict(corpus, rows=rows), configuration)["calibration"]
        self.assertEqual(before, after)


class TestAbstention(unittest.TestCase):
    def setUp(self):
        self.corpus = small_corpus()
        self.pairs = self.corpus["rational_pairs"]
        self.fitted = ENGINE.fit_one(self.corpus, {"family": ENGINE.FAMILY_CART, "family_index": 2,
                                                   "grid_index": 0,
                                                   "hyperparameters": {"max_depth": 3,
                                                                       "min_samples_leaf": 8}})

    def test_an_unavailable_vector_abstains(self):
        subject = dict(row("z", slot=99), vector_available=False)
        self.assertEqual((None, ENGINE.ABSTAIN_VECTOR_UNAVAILABLE),
                         ENGINE.predict(self.fitted, subject, self.pairs))

    def test_a_value_outside_the_training_range_abstains(self):
        feature = sorted(self.fitted["used_features"])[0]
        subject = row("z", slot=99, **{feature: 10 ** 9})
        self.assertEqual(ENGINE.ABSTAIN_OUT_OF_RANGE,
                         ENGINE.predict(self.fitted, subject, self.pairs)[1])

    def test_a_null_with_no_fitted_branch_abstains(self):
        feature = sorted(self.fitted["used_features"])[0]
        subject = row("z", slot=99, **{feature: None})
        self.assertEqual(ENGINE.ABSTAIN_UNFITTED_NULL,
                         ENGINE.predict(self.fitted, subject, self.pairs)[1])

    def test_a_zero_denominator_on_the_path_abstains_with_its_own_code(self):
        fitted = dict(self.fitted, used_features={"num"},
                      training_ranges={"num": (Fraction(0), Fraction(1))},
                      training_null_features=set())
        subject = row("z", slot=99, num=3, den=0)
        self.assertEqual(ENGINE.ABSTAIN_DENOMINATOR_ZERO,
                         ENGINE.predict(fitted, subject, self.pairs)[1])

    def test_an_abstention_is_never_a_probability(self):
        """Never both, never neither: an abstention is a declared non-decision."""
        subject = dict(row("z", slot=99), vector_available=False)
        probability, code = ENGINE.predict(self.fitted, subject, self.pairs)
        self.assertIsNone(probability)
        self.assertIsNotNone(code)

    def test_an_ordinary_row_does_not_abstain(self):
        probability, code = ENGINE.predict(
            self.fitted, ENGINE.segment_rows(self.corpus, "test")[0], self.pairs)
        self.assertIsNone(code)
        self.assertIsNotNone(probability)


class TestSelection(unittest.TestCase):
    def test_the_frozen_grid_has_fifteen_configurations(self):
        self.assertEqual(15, len(ENGINE.grid(PREREG.read_preregistration())))

    def test_selection_reads_the_validation_segment_only(self):
        """Change the test labels; the selection must not move."""
        corpus = small_corpus()
        first = ENGINE.select(corpus)["selected"]["configuration"]
        rows = [dict(r, label_value=not r["label_value"]) if r["segment"] == "test" else r
                for r in corpus["rows"]]
        second = ENGINE.select(dict(corpus, rows=rows))["selected"]["configuration"]
        self.assertEqual(first, second)

    def test_the_ranking_is_sorted_by_the_frozen_tie_break_order(self):
        ranking = ENGINE.select(small_corpus())["ranking"]
        keys = [(entry["brier"], entry["parameter_count"],
                 entry["configuration"]["family_index"], entry["configuration"]["grid_index"])
                for entry in ranking]
        self.assertEqual(keys, sorted(keys))

    def test_ties_are_broken_towards_fewer_parameters(self):
        """With a tie on Brier, the simpler model wins — not whichever was enumerated first."""
        ranking = ENGINE.select(small_corpus())["ranking"]
        for earlier, later in zip(ranking, ranking[1:]):
            if earlier["brier"] == later["brier"]:
                self.assertLessEqual(earlier["parameter_count"], later["parameter_count"])

    def test_brier_is_undefined_over_no_evaluated_rows_never_zero(self):
        """A configuration that abstained on everything has not scored perfectly."""
        corpus = small_corpus()
        fitted = ENGINE.fit_one(corpus, {"family": ENGINE.FAMILY_CONSTANT, "family_index": 0,
                                         "grid_index": 0, "hyperparameters": {}})
        blocked = [dict(r, vector_available=False) for r in ENGINE.segment_rows(corpus, "test")]
        self.assertEqual((None, 0), ENGINE.brier(fitted, blocked, corpus["rational_pairs"]))


class TestInvariantsThatWouldOtherwiseGoUnnoticed(unittest.TestCase):
    """Reachable guards that the first mutation sweep showed nothing could provoke."""

    def test_a_residual_that_is_not_quantised_is_refused(self):
        """The boosting invariant: every score is quantised, so every residual scales to an int."""
        rows = [row("a", slot=1)]
        with self.assertRaisesRegex(Refused, "boosting invariant"):
            ENGINE._scaled_residuals({"a": Fraction(1, 7)}, rows)

    def test_a_quantised_residual_scales_to_an_integer(self):
        rows = [row("a", slot=1)]
        residual = Fraction(1) - ENGINE.quantise(Fraction(1, 3))
        self.assertIsInstance(ENGINE._scaled_residuals({"a": residual}, rows)["a"], int)

    def test_selection_refuses_when_nothing_scored(self):
        """Every configuration abstaining is not a tie; there is nothing to select between."""
        corpus = small_corpus()
        rows = [dict(r, vector_available=False) if r["segment"] == "validation" else r
                for r in corpus["rows"]]
        with self.assertRaisesRegex(Refused, "nothing to select between"):
            ENGINE.select(dict(corpus, rows=rows))


class TestTestFoldTouchedOnce(unittest.TestCase):
    def test_a_second_look_at_the_test_segment_is_refused(self):
        corpus = small_corpus()
        selection = ENGINE.select(corpus)
        receipt = set()
        ENGINE.score_test_once(corpus, selection, receipt)
        with self.assertRaisesRegex(LeakageRefused, "selection wearing the word evaluation"):
            ENGINE.score_test_once(corpus, selection, receipt)

    def test_a_fresh_receipt_is_the_callers_to_hold(self):
        corpus = small_corpus()
        selection = ENGINE.select(corpus)
        first = ENGINE.score_test_once(corpus, selection, set())
        second = ENGINE.score_test_once(corpus, selection, set())
        self.assertEqual(first, second, "the same artifact must score the same way")


class TestArtifact(unittest.TestCase):
    def setUp(self):
        self.corpus = small_corpus()
        self.selection = ENGINE.select(self.corpus)
        self.artifact = ENGINE.serialize_artifact(self.corpus, self.selection["selected"])

    def test_the_artifact_carries_no_float(self):
        ENGINE.assert_no_float(self.artifact)
        # And after a serialization round trip, because that is where a float would reappear:
        # json turns Fraction into nothing at all, but a stray float survives as a float.
        def walk(node, path="$"):
            self.assertNotIsInstance(node, float, path)
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{path}[{index}]")
        walk(json.loads(json.dumps(self.artifact)))

    def test_the_artifact_binds_the_preregistration_and_the_feature_order(self):
        self.assertEqual(PREREG.PREREGISTRATION_CANONICAL_SHA256,
                         self.artifact["preregistration_canonical_sha256"])
        self.assertIn("feature_order_sha256", self.artifact)
        self.assertEqual(self.corpus["row_evidence_sha256"],
                         self.artifact["row_evidence_sha256"])

    def test_the_artifact_claims_nothing_it_has_not_earned(self):
        self.assertFalse(self.artifact["eligible_for_b11a"])
        self.assertEqual("not_evaluated", self.artifact["performance_status"])

    def test_a_reordered_feature_order_is_a_different_artifact(self):
        """The same columns in different positions is a different matrix."""
        reordered = dict(self.corpus, feature_order=list(reversed(self.corpus["feature_order"])))
        other = ENGINE.serialize_artifact(reordered, self.selection["selected"])
        self.assertNotEqual(self.artifact["feature_order_sha256"], other["feature_order_sha256"])
        self.assertNotEqual(self.artifact["artifact_sha256"], other["artifact_sha256"])

    def test_the_hash_covers_the_model_itself(self):
        mutated = json.loads(json.dumps(self.artifact))
        mutated.pop("artifact_sha256")
        mutated["parameter_count"] += 1
        self.assertNotEqual(self.artifact["artifact_sha256"], ENGINE.canonical_sha256(mutated))


class TestDeterminism(unittest.TestCase):
    def test_the_artifact_hash_survives_a_permutation_of_the_rows(self):
        corpus = small_corpus()
        first = ENGINE.serialize_artifact(corpus, ENGINE.select(corpus)["selected"])
        shuffled = FIXTURES.permuted(corpus)
        second = ENGINE.serialize_artifact(shuffled, ENGINE.select(shuffled)["selected"])
        self.assertEqual(first["artifact_sha256"], second["artifact_sha256"])

    def test_two_fits_of_the_same_corpus_are_byte_identical(self):
        corpus = small_corpus()
        one = ENGINE.serialize_artifact(corpus, ENGINE.select(corpus)["selected"])
        two = ENGINE.serialize_artifact(corpus, ENGINE.select(corpus)["selected"])
        self.assertEqual(ENGINE.canonical_bytes(one), ENGINE.canonical_bytes(two))

    def test_row_evidence_does_not_depend_on_arrival_order(self):
        corpus = small_corpus()
        self.assertEqual(FIXTURES.row_evidence(corpus["rows"]),
                         FIXTURES.row_evidence(FIXTURES.permuted(corpus)["rows"]))


class TestCrossWindowComparison(unittest.TestCase):
    def test_comparing_across_windows_is_refused(self):
        with self.assertRaisesRegex(Refused, "measures the difference between two windows"):
            ENGINE.refuse_cross_window_comparison("w-model", "b11a")

    def test_the_same_window_compares(self):
        self.assertTrue(ENGINE.refuse_cross_window_comparison("w", "w"))


class TestTheRealGate(unittest.TestCase):
    """The full-size fixture, end to end. Slow on purpose: a gate nobody runs stops being true."""

    def test_the_gate_passes_with_no_findings(self):
        report = FIXTURES.gate()
        self.assertEqual([], report["findings"])
        self.assertTrue(report["passed"])
        self.assertEqual(15, report["configurations_scored"])
        self.assertTrue(report["deterministic_under_permutation"])
        self.assertFalse(report["eligible_for_b11a"])
        self.assertFalse(report["real_window_fitting_permitted"])
        self.assertEqual("not_evaluated", report["performance_status"])
        self.assertGreater(report["calibration_bins"], 1,
                           "a collapsed calibration flattens every model to the base rate")
        self.assertGreaterEqual(len({tuple(sorted(entry["validation_brier"].items()))
                                     for entry in report["ranking"]}), 2,
                                "a fixture that scores every configuration alike proves nothing")
        ENGINE.assert_no_float(report)


class TestNoRealData(unittest.TestCase):
    def test_neither_module_reads_the_chain_or_a_burned_artifact(self):
        for name in ("b14c_model_engine.py", "b14c_model_fixtures.py"):
            source = (ROOT / "scripts" / name).read_text()
            for token in ("b9a_outcomes", "b9c_signature_inventory", "b10b_observed_paths",
                          "requests", "urllib", "socket", "http"):
                with self.subTest(name=name, token=token):
                    self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
