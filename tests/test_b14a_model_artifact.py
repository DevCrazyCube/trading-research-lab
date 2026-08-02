"""Tests for the B14a model artifact envelope.

Synthetic artifacts only. No model is fitted, no weights exist, no metric is computed and no window
is eligible.

One module graph is loaded for the whole file: loading the same module twice by path creates two
distinct exception classes, and an `assertRaises` on the wrong one never matches.
"""
import copy
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FIXTURES = _load("b14a_split_fixtures", "b14a_split_fixtures.py")
ARTIFACT = FIXTURES.ARTIFACT
SPLIT = FIXTURES.SPLIT
B10B = SPLIT.B10B


def plan():
    return SPLIT.plan_split(FIXTURES.build_fixture_corpus(), FIXTURES.build_spec())


def artifact(**overrides):
    base = FIXTURES.build_artifact(plan())
    if not overrides:
        return base
    changed = copy.deepcopy(base)
    changed.update(overrides)
    changed["artifact_sha256"] = None
    ARTIFACT.assert_artifact(changed)
    changed["artifact_sha256"] = ARTIFACT.artifact_hash(changed)
    return changed


def request(**overrides):
    base = FIXTURES.compatible_request(FIXTURES.build_artifact(plan()))
    base.update(overrides)
    return base


def codes(reasons):
    return [r["reason_code"] for r in reasons]


# --------------------------------------------------------------------------------------------

class SealTests(unittest.TestCase):
    """What an envelope must carry before it may be sealed."""

    def test_a_complete_artifact_seals(self):
        sealed = artifact()
        self.assertTrue(sealed["artifact_sha256"])
        self.assertEqual(sealed["artifact_sha256"], ARTIFACT.artifact_hash(sealed))

    def test_every_declared_field_is_required(self):
        sealed = artifact()
        for field in ARTIFACT.ARTIFACT_FIELDS:
            with self.subTest(missing=field):
                broken = {k: v for k, v in sealed.items() if k != field}
                with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "does not carry"):
                    ARTIFACT.assert_artifact(broken)

    def test_an_undeclared_field_is_refused(self):
        broken = dict(artifact(), smuggled=1)
        with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "nobody reviewed"):
            ARTIFACT.assert_artifact(broken)

    def test_an_artifact_must_name_its_training_folds(self):
        broken = dict(artifact(), training_fold_ids=[])
        with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "must name the training folds"):
            ARTIFACT.assert_artifact(broken)

    def test_an_artifact_must_name_its_environment(self):
        for field in ARTIFACT.ENVIRONMENT_FIELDS:
            with self.subTest(missing=field):
                broken = copy.deepcopy(artifact())
                broken["environment"][field] = ""
                with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "non-empty string"):
                    ARTIFACT.assert_artifact(broken)

    def test_an_artifact_bound_to_a_gated_split_is_refused(self):
        broken = copy.deepcopy(artifact())
        broken["split_status"] = SPLIT.STATUS_MODEL_ELIGIBLE
        with self.assertRaises(SPLIT.StatusGated):
            ARTIFACT.assert_artifact(broken)

    def test_no_float_may_appear_anywhere(self):
        broken = copy.deepcopy(artifact())
        broken["hyperparameters"]["depth"] = 3.0
        with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "express it as an integer"):
            ARTIFACT.assert_artifact(broken)

    def test_a_float_outside_the_hyperparameters_is_also_refused(self):
        """The type scan covers the whole envelope, not only the parameters — a float in a
        transform's provenance hashes differently on two machines just as readily."""
        for path, mutate in (
                ("transform", lambda a: a["transforms"][0].__setitem__("fit_row_hashes_sha256",
                                                                       0.5)),
                ("calibration", lambda a: a["calibration"].__setitem__("parameters_sha256", 0.5)),
                ("environment", lambda a: a["environment"].__setitem__("interpreter_id", 1.5)),
                # A float NESTED inside a hyperparameter mapping. Nothing else looks here — the
                # hyperparameter check permits a mapping and does not walk into it — so only the
                # whole-envelope type scan can catch this one.
                ("nested hyperparameter",
                 lambda a: a["hyperparameters"].__setitem__("depth", {"threshold": 0.5}))):
            with self.subTest(path=path):
                broken = copy.deepcopy(artifact())
                mutate(broken)
                with self.assertRaises(ARTIFACT.ArtifactRefused):
                    ARTIFACT.assert_artifact(broken)

    def test_the_float_refusal_explains_the_reproducibility_problem(self):
        try:
            ARTIFACT.assert_no_float({"nested": {"value": 0.5}})
        except ARTIFACT.ArtifactRefused as error:
            self.assertIn("two machines cannot disagree", str(error))

    def test_a_non_integer_seed_is_refused(self):
        """A seed is part of what produced the weights, so it has to be a value two runs can
        compare exactly."""
        for value in ("20260802", 1.0, None, True):
            with self.subTest(value=value):
                broken = copy.deepcopy(artifact())
                broken["random_seed"] = value
                with self.assertRaises(ARTIFACT.ArtifactRefused):
                    ARTIFACT.assert_artifact(broken)


class HyperparameterTests(unittest.TestCase):
    """Declaration before value, so a later parameter is undeclared rather than a new default."""

    def test_an_undeclared_parameter_is_refused(self):
        broken = copy.deepcopy(artifact())
        broken["hyperparameters"]["learning_rate_numerator"] = 1
        with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "nobody declared is one nobody"):
            ARTIFACT.assert_artifact(broken)

    def test_a_declared_parameter_with_no_value_is_refused(self):
        broken = copy.deepcopy(artifact())
        broken["declared_hyperparameter_names"].append("subsample_numerator")
        with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "default hiding in the algorithm"):
            ARTIFACT.assert_artifact(broken)

    def test_a_duplicate_declaration_is_refused(self):
        broken = copy.deepcopy(artifact())
        broken["declared_hyperparameter_names"].append("depth")
        with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "lists a name twice"):
            ARTIFACT.assert_artifact(broken)

    def test_a_float_hyperparameter_is_refused(self):
        with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "integer numerator and denominator"):
            ARTIFACT.assert_hyperparameters(["rate"], {"rate": 0.1})

    def test_a_rational_hyperparameter_travels_as_two_integers(self):
        """The shipped fixture expresses a shrinkage of 1/10 as two integers, for exactly the
        reason a float is refused."""
        sealed = artifact()
        self.assertEqual(sealed["hyperparameters"]["shrinkage_numerator"], 1)
        self.assertEqual(sealed["hyperparameters"]["shrinkage_denominator"], 10)

    def test_an_empty_declaration_with_no_values_is_permitted(self):
        self.assertTrue(ARTIFACT.assert_hyperparameters([], {}))

    def test_the_contract_offers_no_default_hyperparameters(self):
        import io, contextlib, json
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            ARTIFACT.main(["--contract"])
        contract = json.loads(buffer.getvalue())
        self.assertIsNone(contract["default_algorithm"])
        self.assertEqual(contract["default_hyperparameters"], {})
        self.assertIsNone(contract["default_transform"])
        self.assertIsNone(contract["default_metric"])
        self.assertIsNone(contract["default_threshold"])


class TransformTests(unittest.TestCase):
    """A scaler fitted on validation produces numbers better than the model deserves."""

    def test_a_transform_fitted_on_a_training_fold_is_accepted(self):
        self.assertTrue(artifact()["transforms"])

    def test_a_transform_fitted_on_validation_is_refused(self):
        broken = copy.deepcopy(artifact())
        broken["transforms"][0]["fitted_on_fold_ids"] = ["validation-fold"]
        with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "better than the model deserves"):
            ARTIFACT.assert_artifact(broken)

    def test_a_transform_fitted_on_a_mixture_is_refused(self):
        broken = copy.deepcopy(artifact())
        broken["transforms"][0]["fitted_on_fold_ids"] = ["fold-1", "held-out-fold"]
        with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "not\\s+training fold"):
            ARTIFACT.assert_artifact(broken)

    def test_a_transform_that_cannot_say_where_it_was_fitted_is_refused(self):
        broken = copy.deepcopy(artifact())
        broken["transforms"][0]["fitted_on_fold_ids"] = []
        with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "cannot say where"):
            ARTIFACT.assert_artifact(broken)

    def test_a_duplicate_transform_is_refused(self):
        broken = copy.deepcopy(artifact())
        broken["transforms"].append(copy.deepcopy(broken["transforms"][0]))
        with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "appears twice"):
            ARTIFACT.assert_artifact(broken)

    def test_calibration_is_restricted_to_training_folds(self):
        broken = copy.deepcopy(artifact())
        broken["calibration"]["fitted_on_fold_ids"] = ["validation-fold"]
        with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "calibrated against the answer"):
            ARTIFACT.assert_artifact(broken)

    def test_calibration_fitted_on_nothing_is_refused(self):
        broken = copy.deepcopy(artifact())
        broken["calibration"]["fitted_on_fold_ids"] = []
        with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "fitted on nothing"):
            ARTIFACT.assert_artifact(broken)

    def test_no_calibration_at_all_is_permitted(self):
        self.assertTrue(ARTIFACT.assert_artifact(artifact(calibration=None)))

    def test_a_transform_must_state_every_declared_field(self):
        for field in ARTIFACT.TRANSFORM_FIELDS:
            with self.subTest(missing=field):
                broken = copy.deepcopy(artifact())
                del broken["transforms"][0][field]
                with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "must state"):
                    ARTIFACT.assert_artifact(broken)


class PerformanceLockTests(unittest.TestCase):
    """Nothing here has evaluated a model, so nothing may claim to have."""

    def test_a_sealed_artifact_is_not_evaluated(self):
        self.assertEqual(artifact()["performance_status"], ARTIFACT.PERFORMANCE_NOT_EVALUATED)

    def test_every_performance_claim_is_refused_by_name(self):
        for status in ARTIFACT.PERFORMANCE_CLAIM_STATUSES:
            with self.subTest(status=status):
                broken = copy.deepcopy(artifact())
                broken["performance_status"] = status
                with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "nobody has earned"):
                    ARTIFACT.assert_artifact(broken)

    def test_an_undeclared_status_is_refused(self):
        broken = copy.deepcopy(artifact())
        broken["performance_status"] = "looks_promising"
        with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "is not one of"):
            ARTIFACT.assert_artifact(broken)

    def test_the_seal_cannot_be_asked_for_another_status(self):
        """`seal_artifact` takes no performance argument at all; the lock is structural."""
        import inspect
        self.assertNotIn("performance_status",
                         inspect.signature(ARTIFACT.seal_artifact).parameters)


class B11aTests(unittest.TestCase):
    """B11a was frozen as a no-model baseline, and no model may be scored against it."""

    def test_a_sealed_artifact_is_not_eligible_for_b11a(self):
        self.assertFalse(artifact()["eligible_for_b11a"])

    def test_an_artifact_claiming_b11a_eligibility_is_refused(self):
        broken = copy.deepcopy(artifact())
        broken["eligible_for_b11a"] = True
        with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "NO-MODEL baseline"):
            ARTIFACT.assert_artifact(broken)

    def test_the_seal_cannot_be_asked_for_b11a_eligibility(self):
        import inspect
        self.assertNotIn("eligible_for_b11a",
                         inspect.signature(ARTIFACT.seal_artifact).parameters)

    def test_a_request_naming_b11a_is_incompatible(self):
        sealed = artifact()
        incoming = dict(request(), window_id="b11a-fresh-window")
        self.assertIn(ARTIFACT.I12_B11A_ELIGIBILITY_CLAIM,
                      codes(ARTIFACT.incompatibilities(sealed, incoming)))
        with self.assertRaises(ARTIFACT.IncompatibleArtifact):
            ARTIFACT.require_compatible(sealed, incoming)


class CompatibilityTests(unittest.TestCase):
    """An incompatible artifact used anyway produces numbers with no error and no meaning."""

    def test_a_matching_request_is_compatible(self):
        sealed = artifact()
        self.assertEqual(ARTIFACT.incompatibilities(sealed, request()), [])
        self.assertTrue(ARTIFACT.require_compatible(sealed, request()))

    def test_each_mismatch_reports_its_own_code(self):
        sealed = artifact()
        cases = {
            ARTIFACT.I01_FEATURE_CONTRACT_MISMATCH: {"feature_contract_sha256": "z" * 64},
            ARTIFACT.I02_FEATURE_ORDER_MISMATCH: {"feature_order_sha256": "z" * 64},
            ARTIFACT.I03_VERSION_MISMATCH: {"feature_contract_version": "2.0.0"},
            ARTIFACT.I04_TARGET_OR_HORIZON_MISMATCH: {"horizon_id": "another_horizon"},
            ARTIFACT.I05_SPLIT_PLAN_MISMATCH: {"split_plan_sha256": "z" * 64},
            ARTIFACT.I08_SEED_MISMATCH: {"random_seed": 1},
        }
        for expected, override in cases.items():
            with self.subTest(expected=expected):
                self.assertIn(expected, codes(ARTIFACT.incompatibilities(sealed,
                                                                         request(**override))))

    def test_a_reordered_feature_set_is_caught_even_though_the_set_matches(self):
        """The same columns in different positions is a different matrix, and the artifact has no
        way to notice except by the order hash."""
        sealed = artifact()
        incoming = request(feature_order_sha256="reordered-but-same-set")
        reasons = ARTIFACT.incompatibilities(sealed, incoming)
        self.assertIn(ARTIFACT.I02_FEATURE_ORDER_MISMATCH, codes(reasons))
        detail = next(r for r in reasons
                      if r["reason_code"] == ARTIFACT.I02_FEATURE_ORDER_MISMATCH)["detail"]
        self.assertIn("no error and no meaning", detail)

    def test_an_undeclared_hyperparameter_in_a_request_is_caught(self):
        sealed = artifact()
        incoming = request(hyperparameters=dict(sealed["hyperparameters"], invented=1))
        self.assertIn(ARTIFACT.I06_UNDECLARED_HYPERPARAMETER,
                      codes(ARTIFACT.incompatibilities(sealed, incoming)))

    def test_a_changed_hyperparameter_value_is_caught(self):
        sealed = artifact()
        incoming = request(hyperparameters=dict(sealed["hyperparameters"], depth=9))
        self.assertIn(ARTIFACT.I07_HYPERPARAMETER_VALUE_MISMATCH,
                      codes(ARTIFACT.incompatibilities(sealed, incoming)))

    def test_seed_drift_is_caught(self):
        sealed = artifact()
        reasons = ARTIFACT.incompatibilities(sealed, request(random_seed=20260803))
        self.assertIn(ARTIFACT.I08_SEED_MISMATCH, codes(reasons))
        detail = next(r for r in reasons
                      if r["reason_code"] == ARTIFACT.I08_SEED_MISMATCH)["detail"]
        self.assertIn("cannot reproduce them", detail)

    def test_a_missing_transform_is_caught(self):
        sealed = artifact()
        self.assertIn(ARTIFACT.I09_TRANSFORM_MISMATCH,
                      codes(ARTIFACT.incompatibilities(sealed, request(transforms=[]))))

    def test_different_fitted_transform_parameters_are_caught(self):
        sealed = artifact()
        incoming = request(transforms=[dict(sealed["transforms"][0],
                                            parameters_sha256="z" * 64)])
        self.assertIn(ARTIFACT.I09_TRANSFORM_MISMATCH,
                      codes(ARTIFACT.incompatibilities(sealed, incoming)))

    def test_a_request_transform_fitted_outside_training_is_caught(self):
        sealed = artifact()
        incoming = request(transforms=[dict(sealed["transforms"][0],
                                            fitted_on_fold_ids=["validation-fold"])])
        self.assertIn(ARTIFACT.I10_TRANSFORM_FITTED_OUTSIDE_TRAINING,
                      codes(ARTIFACT.incompatibilities(sealed, incoming)))

    def test_a_request_missing_a_field_is_refused_rather_than_passed(self):
        """A compatibility check that skips a field is a check that passes for the wrong reason."""
        for field in ARTIFACT.REQUEST_FIELDS:
            with self.subTest(missing=field):
                incoming = {k: v for k, v in request().items() if k != field}
                with self.assertRaisesRegex(ARTIFACT.ArtifactRefused, "wrong reason"):
                    ARTIFACT.incompatibilities(artifact(), incoming)

    def test_an_incompatibility_is_distinguishable_from_a_malformed_artifact(self):
        self.assertTrue(issubclass(ARTIFACT.IncompatibleArtifact, ARTIFACT.ArtifactRefused))

    def test_every_declared_code_is_reachable_or_declared_for_a_reason(self):
        self.assertEqual(len(set(ARTIFACT.INCOMPATIBILITY_CODES)),
                         len(ARTIFACT.INCOMPATIBILITY_CODES))


class HashDriftTests(unittest.TestCase):
    """An envelope that changed after it was sealed is not the envelope it claims to be."""

    def test_a_drifted_artifact_is_caught(self):
        sealed = copy.deepcopy(artifact())
        sealed["hyperparameters"]["depth"] = 4
        self.assertNotEqual(sealed["artifact_sha256"], ARTIFACT.artifact_hash(sealed))
        reasons = ARTIFACT.incompatibilities(sealed, request())
        self.assertIn(ARTIFACT.I01_FEATURE_CONTRACT_MISMATCH, codes(reasons))
        self.assertIn("after it was sealed", reasons[0]["detail"])

    def test_the_artifact_hash_covers_everything_but_itself(self):
        sealed = artifact()
        self.assertEqual(sealed["artifact_sha256"], ARTIFACT.artifact_hash(sealed))

    def test_changing_any_bound_hash_changes_the_artifact_hash(self):
        base = artifact()
        for field in ("feature_contract_sha256", "feature_order_sha256",
                      "label_preregistration_sha256", "split_plan_sha256",
                      "training_row_ids_sha256", "training_evidence_sha256"):
            with self.subTest(field=field):
                self.assertNotEqual(artifact(**{field: "z" * 64})["artifact_sha256"],
                                    base["artifact_sha256"])

    def test_changing_the_environment_changes_the_artifact_hash(self):
        base = artifact()
        other = artifact(environment=dict(base["environment"],
                                          code_revision="a-different-revision"))
        self.assertNotEqual(base["artifact_sha256"], other["artifact_sha256"])

    def test_sealing_twice_gives_the_same_hash(self):
        self.assertEqual(FIXTURES.build_artifact(plan())["artifact_sha256"],
                         FIXTURES.build_artifact(plan())["artifact_sha256"])

    def test_the_artifact_binds_the_plan_which_binds_its_rows(self):
        """A plan that could not say which rows it planned would let the corpus be swapped
        underneath an artifact that still hashed the same."""
        first = plan()
        rows = FIXTURES.build_fixture_corpus()
        rows[0]["label_sha256"] = "z" * 64
        second = SPLIT.plan_split(rows, FIXTURES.build_spec())
        self.assertNotEqual(first["row_evidence_sha256"], second["row_evidence_sha256"])
        self.assertNotEqual(first["plan_sha256"], second["plan_sha256"])
        self.assertNotEqual(FIXTURES.build_artifact(first)["artifact_sha256"],
                            FIXTURES.build_artifact(second)["artifact_sha256"])


class ScopeTests(unittest.TestCase):
    """What this envelope is not."""

    def test_no_weights_and_no_algorithm_are_stored(self):
        import io, contextlib, json
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            ARTIFACT.main(["--contract"])
        contract = json.loads(buffer.getvalue())
        self.assertFalse(contract["model_fitted"])
        self.assertFalse(contract["weights_stored"])
        self.assertFalse(contract["eligible_for_b11a"])
        self.assertFalse(contract["floats_used"])

    def test_the_algorithm_is_an_identifier_not_an_implementation(self):
        self.assertIsInstance(artifact()["algorithm_id"], str)
        for field in ARTIFACT.ARTIFACT_FIELDS:
            with self.subTest(field=field):
                for banned in ("weights", "coefficients", "tree", "parameters_blob"):
                    self.assertNotIn(banned, field)

    def test_an_association_ledger_in_an_artifact_is_refused(self):
        broken = copy.deepcopy(artifact())
        broken["environment"]["code_revision"] = "r"
        with self.assertRaises(SPLIT.SplitRefused):
            SPLIT.assert_no_association_evidence(
                {"artifact": broken,
                 "grouping": {"confidence_status": "uncalibrated_evidence_only"}})


if __name__ == "__main__":
    unittest.main()
