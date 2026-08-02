"""B14c — every guard in the freeze must be able to refuse.

Each test mutates exactly one clause of the frozen document and asserts the validator notices. A
preregistration whose validator cannot be shown to refuse anything is a document, not a freeze.
"""
import copy
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B14C = _load("b14c_model_prereg", "b14c_model_prereg.py")
# One module graph, reached through the validator. A second load by path would give this file a
# different ModelPreregRefused than the validator raises.
Refused = B14C.ModelPreregRefused
FitRefused = B14C.FitRefused


def mutated(**_unused):
    """A copy of the real document, for a test to break in exactly one place."""
    return copy.deepcopy(DOCUMENT)


DOCUMENT = B14C.read_preregistration()


def rehash(document):
    """Re-pin a mutated document so the hash guard does not mask the guard under test.

    Without this every mutation would fail on the hash and every test below would pass for the same
    uninformative reason.
    """
    return B14C.canonical_sha256(document)


def verify(document):
    return B14C.verify_preregistration(document, expected_sha256=rehash(document))


class TestTheRealDocument(unittest.TestCase):
    def test_the_committed_freeze_verifies(self):
        report = B14C.verify_preregistration()
        self.assertEqual(0, report["eligible_windows"])
        self.assertFalse(report["fitting_permitted"])
        self.assertEqual(15, report["configurations_per_horizon"])
        self.assertEqual(60, report["model_selection_family_size"])

    def test_the_pinned_hash_is_the_committed_document(self):
        self.assertEqual(B14C.PREREGISTRATION_CANONICAL_SHA256,
                         B14C.canonical_sha256(B14C.read_preregistration()))

    def test_any_edit_to_the_document_is_refused(self):
        """The pin is the freeze. Every other guard is a second line behind it."""
        document = mutated()
        document["purpose"] = document["purpose"] + " "
        with self.assertRaisesRegex(Refused, "a changed document is a different design"):
            B14C.verify_preregistration(document)

    def test_a_missing_document_is_refused_as_a_refusal(self):
        with self.assertRaises(Refused):
            B14C.read_preregistration(ROOT / "research" / "no_such_prereg.json")

    def test_a_malformed_document_is_refused_as_a_refusal(self):
        with self.assertRaises(Refused):
            B14C.read_preregistration(ROOT / "research" / "B14C_MODEL_PREREGISTRATION.md")


class TestIdentityAndOrderingClaims(unittest.TestCase):
    """The document's claims about what it IS and when it was written.

    All four were mutation survivors: the guards existed and nothing could show they worked.
    """

    def test_a_document_under_another_id_is_refused(self):
        document = mutated()
        document["preregistration_id"] = "B14C_MODEL_AND_SELECTION_V2"
        with self.assertRaisesRegex(Refused, "not the frozen one"):
            verify(document)

    def test_dropping_a_claim_about_its_own_ordering_is_refused(self):
        """'Committed before any fit' is the whole value of a preregistration."""
        for flag in ("committed_before_any_fit", "committed_before_any_outcome_exists"):
            with self.subTest(flag=flag):
                document = mutated()
                document[flag] = False
                with self.assertRaisesRegex(Refused, "claims its own ordering"):
                    verify(document)

    def test_a_changed_horizon_count_is_refused(self):
        """Dropping a horizon shrinks the family, which shrinks the correction."""
        document = mutated()
        document["target"]["secondary_horizons"] = ["h_10000_slots"]
        with self.assertRaisesRegex(Refused, "horizons, expected 4"):
            verify(document)

    def test_a_pair_whose_halves_are_not_a_numerator_and_a_denominator_is_refused(self):
        """A real contract field, in a pair slot where a numerator belongs."""
        document = mutated()
        pairs = document["preprocessing"]["rational_pair_handling"]["pairs"]
        pairs[0][0] = "concentration_total_supply_top_1_units"
        with self.assertRaisesRegex(Refused, "is not a numerator/denominator pair"):
            verify(document)


class TestEligibilityGuards(unittest.TestCase):
    def test_an_opened_window_is_refused(self):
        document = mutated()
        document["eligibility"]["eligible_windows"] = ["some-future-window"]
        with self.assertRaisesRegex(Refused, "eligible_windows is not empty"):
            verify(document)

    def test_declaring_b11a_eligible_is_refused(self):
        document = mutated()
        document["eligibility"]["b11a_eligible"] = True
        with self.assertRaisesRegex(Refused, "b11a_eligible"):
            verify(document)

    def test_permitting_fitting_is_refused(self):
        document = mutated()
        document["eligibility"]["fitting_permitted"] = True
        with self.assertRaisesRegex(Refused, "fitting_permitted"):
            verify(document)

    def test_claiming_the_composition_was_inspected_is_refused(self):
        document = mutated()
        document["b11a_composition_inspected"] = True
        with self.assertRaisesRegex(Refused, "b11a_composition_inspected"):
            verify(document)


class TestFitGate(unittest.TestCase):
    def test_nothing_may_fit_today(self):
        with self.assertRaisesRegex(FitRefused, "no window is eligible"):
            B14C.assert_fit_permitted()

    def test_b11a_is_refused_even_if_a_document_listed_it(self):
        """The permanent refusal must not depend on the list it is protecting."""
        document = mutated()
        document["eligibility"]["eligible_windows"] = ["b11a-fresh-cohort-2026-08-02"]
        with self.assertRaisesRegex(FitRefused, "permanently ineligible"):
            B14C.assert_fit_permitted(document, window_id="b11a-fresh-cohort-2026-08-02",
                                      expected_sha256=rehash(document))

    def test_b11a_is_refused_even_when_the_document_itself_is_unreadable(self):
        """The permanent refusal must not depend on the document that carries it."""
        with self.assertRaisesRegex(FitRefused, "permanently ineligible"):
            B14C.assert_fit_permitted({"not": "a preregistration"}, window_id="B11A")

    def test_adding_a_window_to_the_list_does_not_open_the_gate(self):
        """Fail-closed, and refused by VERIFICATION rather than by a branch in the gate.

        The gate carries exactly one refusal because that is all this document can produce:
        verification pins eligible_windows to empty, so a branch for "the list has one but the
        gate is shut" could never fire. Editing the list is caught here instead, one layer up.
        """
        document = mutated()
        document["eligibility"]["eligible_windows"] = ["w-future"]
        with self.assertRaisesRegex(Refused, "superseding preregistration"):
            B14C.assert_fit_permitted(document, window_id="w-future",
                                      expected_sha256=rehash(document))

    def test_the_gate_returns_nothing_a_caller_can_ignore(self):
        """Every path raises, so no caller can proceed by forgetting to read a return value."""
        import inspect
        source = inspect.getsource(B14C.assert_fit_permitted)
        self.assertNotIn("return True", source)
        self.assertNotIn("return False", source)


class TestArithmeticGuards(unittest.TestCase):
    def test_a_float_anywhere_is_refused(self):
        for path in (("candidate_families", 3, "grid_size"),
                     ("arithmetic", "fixed_quantisation_denominator"),
                     ("selection", "family_accounting", "baseline_family_size")):
            with self.subTest(path=path):
                document = mutated()
                target = document
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = 0.5
                with self.assertRaisesRegex(Refused, "is a float"):
                    verify(document)

    def test_a_float_nested_in_a_grid_is_refused(self):
        document = mutated()
        document["candidate_families"][3]["grid_enumeration"][0]["shrinkage_numerator"] = 0.1
        with self.assertRaisesRegex(Refused, "is a float"):
            verify(document)

    def test_an_understated_family_size_is_refused(self):
        document = mutated()
        document["selection"]["family_accounting"]["configurations_per_horizon"] = 4
        with self.assertRaisesRegex(Refused, "understates the correction"):
            verify(document)

    def test_a_grid_that_enumerates_a_different_count_is_refused(self):
        document = mutated()
        document["candidate_families"][3]["grid_enumeration"].pop()
        with self.assertRaisesRegex(Refused, "cannot disagree"):
            verify(document)

    def test_a_shrunk_baseline_family_is_refused(self):
        document = mutated()
        document["selection"]["family_accounting"]["baseline_family_size"] = 4
        with self.assertRaisesRegex(Refused, "shrinks the correction"):
            verify(document)

    def test_the_two_families_cannot_be_merged_because_neither_size_can_move(self):
        """There is no separate merge check, and there should not be.

        The baseline is pinned to 16 and the model size to 60, so equality is already unreachable.
        A check for it could never fire, and a branch nothing can provoke is one nobody can show
        works. This test pins the reasoning: break either size and the pinning guards catch it.
        """
        document = mutated()
        document["selection"]["family_accounting"]["baseline_family_size"] = 60
        with self.assertRaisesRegex(Refused, "shrinks the correction"):
            verify(document)

    def test_a_mismatched_total_family_size_is_refused(self):
        document = mutated()
        document["selection"]["family_accounting"]["model_selection_family_size"] = 15
        with self.assertRaisesRegex(Refused, "model_selection_family_size"):
            verify(document)


class TestFamilyGuards(unittest.TestCase):
    def test_repeated_family_indices_are_refused(self):
        document = mutated()
        document["candidate_families"][2]["index"] = 1
        with self.assertRaisesRegex(Refused, "not a total order"):
            verify(document)

    def test_duplicate_family_ids_are_refused(self):
        document = mutated()
        document["candidate_families"][1]["id"] = document["candidate_families"][0]["id"]
        document["candidate_families"][1]["index"] = 1
        with self.assertRaisesRegex(Refused, "share an id"):
            verify(document)

    def test_a_dropped_family_is_refused(self):
        document = mutated()
        document["candidate_families"].pop()
        with self.assertRaisesRegex(Refused, "candidate families"):
            verify(document)


class TestSelectionGuards(unittest.TestCase):
    def test_touching_the_test_fold_twice_is_refused(self):
        document = mutated()
        document["selection"]["test_fold_touches"] = 2
        with self.assertRaisesRegex(Refused, "exactly once"):
            verify(document)

    def test_a_primary_metric_that_is_also_forbidden_is_refused(self):
        document = mutated()
        document["selection"]["primary_metric"]["name"] = "realised_capital_weighted_return"
        with self.assertRaisesRegex(Refused, "forbidden list"):
            verify(document)

    def test_a_metric_with_no_direction_is_refused(self):
        document = mutated()
        document["selection"]["primary_metric"]["direction"] = "best"
        with self.assertRaisesRegex(Refused, "no direction"):
            verify(document)

    def test_a_tie_break_order_that_cannot_be_total_is_refused(self):
        document = mutated()
        document["selection"]["tie_breaks_in_strict_order"] = ["1. lower exact Brier"]
        with self.assertRaisesRegex(Refused, "enumeration accident"):
            verify(document)


class TestCalibrationGuards(unittest.TestCase):
    def test_selectable_calibration_is_refused(self):
        document = mutated()
        document["calibration"]["is_selectable"] = True
        with self.assertRaisesRegex(Refused, "doubles the family"):
            verify(document)

    def test_calibration_permitted_on_an_evaluation_fold_is_refused(self):
        for fold in ("validation folds", "test fold"):
            with self.subTest(fold=fold):
                document = mutated()
                document["calibration"]["never_fitted_on"].remove(fold)
                with self.assertRaisesRegex(Refused, "calibrated against the answer"):
                    verify(document)


class TestAbstentionGuards(unittest.TestCase):
    def test_a_dropped_abstention_code_is_refused(self):
        document = mutated()
        document["abstention"]["codes"].pop()
        with self.assertRaisesRegex(Refused, "abstention codes"):
            verify(document)

    def test_an_at_risk_abstention_is_refused(self):
        document = mutated()
        document["abstention"]["at_risk"] = True
        with self.assertRaisesRegex(Refused, "risked nothing"):
            verify(document)

    def test_a_tunable_abstention_rate_is_refused(self):
        document = mutated()
        document["abstention"]["abstention_rate_is_not_a_knob"] = False
        with self.assertRaisesRegex(Refused, "tunable"):
            verify(document)


class TestLeakageAndComparisonGuards(unittest.TestCase):
    def test_a_dropped_leakage_constraint_is_refused(self):
        document = mutated()
        document["leakage_constraints"].pop(0)
        with self.assertRaisesRegex(Refused, "leakage constraints"):
            verify(document)

    def test_dropping_the_cross_window_refusal_is_refused(self):
        document = mutated()
        document["comparison_against_b11b"]["forbidden_comparison"]["id"] = "something_else"
        with self.assertRaisesRegex(Refused, "subtracts two windows"):
            verify(document)

    def test_a_comparator_that_is_not_among_the_policies_is_refused(self):
        document = mutated()
        document["comparison_against_b11b"]["primary_comparator"] = "P9_invented"
        with self.assertRaisesRegex(Refused, "not among the comparator policies"):
            verify(document)

    def test_preregistering_a_pass_fail_gate_is_refused(self):
        document = mutated()
        document["comparison_against_b11b"]["evidence_statement"]["is_a_pass_fail_gate"] = True
        with self.assertRaisesRegex(Refused, "none is earned"):
            verify(document)


class TestStatusLocks(unittest.TestCase):
    def test_every_lock_is_load_bearing(self):
        for key, value in (("performance_status", "evaluated"), ("publication_grade", True),
                           ("model_eligible", True), ("eligible_for_b11a", True)):
            with self.subTest(key=key):
                document = mutated()
                document["status_locks"][key] = value
                with self.assertRaisesRegex(Refused, key):
                    verify(document)

    def test_every_forbidden_status_name_must_stay_refused(self):
        for name in B14C.FORBIDDEN_STATUS_NAMES:
            with self.subTest(name=name):
                document = mutated()
                document["status_locks"]["refused_status_names"].remove(name)
                with self.assertRaisesRegex(Refused, "refused by name"):
                    verify(document)


class TestFeatureContractBinding(unittest.TestCase):
    def test_the_contract_yields_exactly_ninety_nine_names(self):
        names = B14C.contract_feature_names()
        self.assertEqual(99, len(names))
        self.assertEqual("concentration_owner_grouping_available", names[70])
        self.assertEqual("concentration_creator_share_available", names[93])

    def test_a_cited_field_absent_from_the_contract_is_refused(self):
        document = mutated()
        document["preprocessing"]["rational_pair_handling"]["pairs"][0][0] = "invented_numerator"
        with self.assertRaisesRegex(Refused, "binds to nothing"):
            verify(document)

    def test_a_pair_joining_two_different_quantities_is_refused(self):
        document = mutated()
        pairs = document["preprocessing"]["rational_pair_handling"]["pairs"]
        pairs[0] = [pairs[0][0], pairs[1][1]]
        with self.assertRaisesRegex(Refused, "not a number anyone declared"):
            verify(document)

    def test_a_dropped_pair_is_refused(self):
        document = mutated()
        document["preprocessing"]["rational_pair_handling"]["pairs"].pop()
        with self.assertRaisesRegex(Refused, "rational pairs"):
            verify(document)

    def test_a_feature_contract_that_moved_is_refused(self):
        with self.assertRaisesRegex(Refused, "not the one it was written against"):
            B14C.contract_feature_names(ROOT / "research" / "B14C_MODEL_PREREGISTRATION.md")

    def test_a_missing_feature_contract_is_refused_as_a_refusal(self):
        with self.assertRaises(Refused):
            B14C.contract_feature_names(ROOT / "research" / "no_such_contract.md")


class TestExceptionChain(unittest.TestCase):
    def test_a_refusal_is_catchable_as_the_project_base(self):
        """The trap this project has hit five times: a refusal nobody's handler catches."""
        self.assertTrue(issubclass(Refused, B14C.B14B.EvaluationRefused))
        self.assertTrue(issubclass(Refused, B14C.ARTIFACT.ArtifactRefused))
        self.assertTrue(issubclass(FitRefused, Refused))
        with self.assertRaises(B14C.ARTIFACT.ArtifactRefused):
            B14C.assert_fit_permitted()


class TestNoModelHere(unittest.TestCase):
    def test_the_validator_carries_no_fitting_code(self):
        """A validator that could also fit would be the thing it is guarding against."""
        source = (ROOT / "scripts" / "b14c_model_prereg.py").read_text()
        for token in ("def fit", "def train", "def predict", "sklearn", "numpy", "torch"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_the_report_publishes_no_metric_and_no_composition(self):
        report = B14C.verify_preregistration()
        text = json.dumps(report)
        for token in ("score", "brier", "return", "pnl", "accuracy", "auc", "profit"):
            with self.subTest(token=token):
                self.assertNotIn(token, text.lower())


if __name__ == "__main__":
    unittest.main()
