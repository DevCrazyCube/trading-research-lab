"""Tests for B19D. Nothing here touches a network or the evaluation window.

The interesting tests are not "does it compute a number" -- they are the ones that enforce the
preregistration's own prohibitions against the person implementing it. A study can be undone by its
implementation as easily as by its author, and more quietly.
"""
import hashlib
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b19d", ROOT / "scripts" / "b19d_non_issuance_signal.py")
B = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B)
DOCUMENT = json.loads(pathlib.Path(ROOT / "research" /
                                   "B19D_NON_ISSUANCE_SIGNAL_PREREGISTRATION.json").read_bytes())


class ItImplementsTheFrozenDocumentAndNotSomethingElse(unittest.TestCase):
    def test_the_pin_is_verified_and_a_changed_document_is_refused(self):
        self.assertEqual(B.verify_preregistration()["preregistration_id"],
                         "B19D_NON_ISSUANCE_SIGNAL_V1")
        with self.assertRaisesRegex(B.SignalRefused, "hashes"):
            B.verify_preregistration(expected="0" * 64)

    def test_every_frozen_input_matches_the_document(self):
        frozen = DOCUMENT["frozen_inputs_unchanged"]
        self.assertEqual(list(B.ENTRY_DELAYS), frozen["entry_delays_slots"])
        self.assertEqual(B.POSITION, frozen["position_lamports"])
        self.assertEqual([h["name"] for h in B.HORIZONS], frozen["horizons"])

    def test_the_family_size_matches_and_the_check_can_fail(self):
        self.assertEqual(B.FAMILY_SIZE, DOCUMENT["multiplicity"]["family_size"])
        original = B.SIGNALS
        B.SIGNALS = original[:-1]
        self.addCleanup(setattr, B, "SIGNALS", original)
        with self.assertRaisesRegex(B.SignalRefused, "declares a family"):
            B.verify_preregistration()

    def test_the_signal_ids_are_exactly_the_frozen_set(self):
        frozen = [s["signal_id"] for s in DOCUMENT["candidate_signals_frozen"]["set"]]
        self.assertEqual([s["signal_id"] for s in B.SIGNALS], frozen)

    def test_S5_is_retained_despite_being_known_negative(self):
        """The document's own test of the no-cherry-picking rule, applied to the implementer.

        B16D already measured S5 on the burned corpus and found every priced variant negative.
        The document discloses that and retains the signal anyway, saying the retention IS the
        test. Dropping it here -- for efficiency, for tidiness, for any reason -- would be the
        exact failure the document exists to prevent, committed by whoever writes the code.
        """
        self.assertIn("S5_CREATOR_REENTRY_DELAYED_CONFIRMATION",
                      [s["signal_id"] for s in B.SIGNALS])

    def test_the_primary_result_is_the_one_the_document_pre_committed(self):
        self.assertEqual(B.PRIMARY["signal_id"], "S1_CREATOR_INITIAL_BUY_PRESENT")
        self.assertEqual(B.PRIMARY["delay"], 1)
        self.assertEqual(B.PRIMARY["horizon"], "h_10000_slots")
        self.assertEqual(B.PRIMARY["scenario_id"], "base")

    def test_the_refusal_codes_are_the_documents_own(self):
        frozen = {entry["code"] for entry in DOCUMENT["refusal_codes"]}
        self.assertEqual(set(B.REFUSAL_CODES) & frozen, set(B.REFUSAL_CODES),
                         "a code this module can raise that the document does not define is a "
                         "refusal nobody can audit")


class TheProhibitionsAreEnforcedInCode(unittest.TestCase):
    def test_no_float_appears_in_any_quantity(self):
        """'any float in any quantity' is a listed prohibition. Checked on the AST, not by hope."""
        import ast
        tree = ast.parse((ROOT / "scripts" / "b19d_non_issuance_signal.py").read_text())
        floats = [node for node in ast.walk(tree)
                  if isinstance(node, ast.Constant) and isinstance(node.value, float)]
        self.assertEqual(floats, [], "a float literal in a lamport quantity is forbidden")
        # Scoped to the functions that compute QUANTITIES. A module-level `ROOT / "research"` is
        # pathlib's join operator, not arithmetic, and banning it outright would flag every path.
        numeric = {"order_statistic", "exact_median", "summarise", "evaluate_cell"}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in numeric:
                divisions = [d for d in ast.walk(node) if isinstance(d, ast.BinOp)
                             and isinstance(d.op, ast.Div)]
                with self.subTest(function=node.name):
                    self.assertEqual(divisions, [],
                                     "true division produces a float; use // by index")

    def test_it_names_no_evaluation_window_path(self):
        """Development is burned or synthetic ONLY, and the fresh window is read once, later.

        Asserted rather than promised: this module must not be able to reach research/b11a at all.
        """
        source = (ROOT / "scripts" / "b19d_non_issuance_signal.py").read_text()
        for forbidden in ("b11a", "research/b11a", "b11a_subsample", "b11a_bodies"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_it_performs_no_network_and_no_transaction_construction(self):
        source = (ROOT / "scripts" / "b19d_non_issuance_signal.py").read_text()
        # Precise tokens: a bare "sign" matches "signal" and would fail on this module's own
        # subject matter, which is a test that cannot distinguish what it is checking from what it
        # is about.
        for forbidden in ("urllib", "requests", "socket.", "sendTransaction",
                          "sign_transaction", "Keypair", "private_key"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


class TheMedianIsAnOrderStatisticAndNeverAMean(unittest.TestCase):
    def test_the_median_is_a_value_from_the_data(self):
        values = [-5, 3, 100]
        self.assertEqual(B.exact_median(values), 3)

    def test_an_even_count_takes_the_lower_median_not_an_average(self):
        """An average would invent a value not in the data, and for lamports a fractional one."""
        self.assertEqual(B.exact_median([2, 4]), 2)
        self.assertNotEqual(B.exact_median([2, 4]), 3)

    def test_the_median_is_an_integer_for_integer_input(self):
        self.assertIsInstance(B.exact_median([1, 2, 3, 4]), int)

    def test_order_statistics_are_taken_by_index(self):
        values = list(range(1, 101))
        self.assertEqual(B.order_statistic(values, 1, 10), 10)
        self.assertEqual(B.order_statistic(values, 3, 4), 75)

    def test_no_values_yields_none_rather_than_zero(self):
        """Zero is a break-even outcome. Absence is not, and must never be rendered as one."""
        self.assertIsNone(B.exact_median([]))
        self.assertIsNone(B.order_statistic([], 1, 2))


class CoverageIsReportedBeforeOutcome(unittest.TestCase):
    def test_coverage_exists_even_when_there_is_no_outcome(self):
        report = B.summarise([], {B.N_NO_SIGNAL: 7}, admitted_curves=0, cohort_size=100)
        self.assertIsNone(report["outcome"])
        self.assertEqual(report["coverage"]["cells_refused"], 7)
        self.assertEqual(report["coverage"]["cohort_size"], 100)

    def test_a_censored_cell_is_counted_as_censored_and_never_as_zero(self):
        """The document is explicit. Counting censoring as break-even would drag the median
        toward zero from whichever side happened to be censored more."""
        report = B.summarise([5, 7], {B.N_RIGHT_CENSORED: 40}, admitted_curves=2, cohort_size=100)
        self.assertEqual(report["coverage"]["censored"], 40)
        self.assertEqual(report["coverage"]["cells_admitted"], 2)
        self.assertEqual(report["outcome"]["median"], 5,
                         "the median is over admitted cells only; censored cells carry no outcome")

    def test_survives_costs_is_strictly_greater_than_zero(self):
        self.assertFalse(B.summarise([0, 0, 0], {}, 3, 3)["survives_costs"],
                         "break-even does not survive; the criterion is STRICTLY above zero")
        self.assertTrue(B.summarise([1, 2, 3], {}, 3, 3)["survives_costs"])

    def test_a_surviving_median_is_labelled_as_not_an_edge(self):
        report = B.summarise([1, 2, 3], {}, 3, 3)
        self.assertIn("not a demonstration", report["survives_costs_is_not_an_edge"])

    def test_the_tail_share_is_reported_so_a_lottery_cannot_present_as_an_edge(self):
        outcomes = [-1] * 90 + [1] * 9 + [1_000_000]
        report = B.summarise(outcomes, {}, 100, 100)
        numerator = report["outcome"]["top_5pct_share_of_positive_numerator"]
        denominator = report["outcome"]["top_5pct_share_of_positive_denominator"]
        self.assertGreater(numerator * 2, denominator,
                           "one cell carrying most of the positive total must be visible")


class TheObservabilityGateAndHorizons(unittest.TestCase):
    def path(self, slots):
        """A canonical path. `transaction_index` enumerates, so two observations may share a slot.

        It previously fixed transaction_index at 0, which made the same-slot fixture [10, 10, 30]
        two observations at the IDENTICAL coordinate (10,0,0,0) -- a duplicate, not a same-slot
        pair. Two transactions in one slot always differ in execution position; that is what
        transaction_index is, and it is the whole reason the block phase of the collection exists.
        """
        return [{"slot": s, "transaction_index": i, "outer_index": 0, "inner_index": 0,
                 "kind": "trade", "virtual_quote": 30_000_000_000, "virtual_token": 1_073_000_000,
                 "real_quote": 1_000_000_000, "real_token": 100_000_000, "quote_mint": "So111",
                 "mayhem_mode": False, "complete": False} for i, s in enumerate(slots)]

    def test_first_at_or_after_respects_canonical_order(self):
        path = self.path([10, 20, 30])
        self.assertEqual(B.first_at_or_after(path, 15)["slot"], 20)
        self.assertIsNone(B.first_at_or_after(path, 99))

    def test_state_in_force_is_the_last_at_or_before(self):
        path = self.path([10, 20, 30])
        self.assertEqual(B.state_in_force(path, 25)["slot"], 20)
        self.assertIsNone(B.state_in_force(path, 5))

    def test_a_slot_horizon_beyond_the_last_observation_is_censored(self):
        path = self.path([10, 20])
        horizon = {"name": "h_1000_slots", "kind": B.HORIZON_SLOT, "slots": 1_000}
        self.assertIsNone(B.exit_observation(path, path[0], horizon),
                          "nothing observed at or after the horizon is censoring, not an outcome")

    def test_an_observation_horizon_short_of_the_count_is_censored(self):
        path = self.path([10, 20, 30])
        horizon = {"name": "h_10_observations", "kind": B.HORIZON_OBSERVATION, "count": 10}
        self.assertIsNone(B.exit_observation(path, path[0], horizon))

    def test_the_administrative_horizon_is_the_last_observation(self):
        path = self.path([10, 20, 30])
        horizon = {"name": "administrative_window_end", "kind": B.HORIZON_ADMINISTRATIVE}
        self.assertEqual(B.exit_observation(path, path[0], horizon)["slot"], 30)

    def test_a_same_slot_entry_is_refused_as_unprovable(self):
        """Ordering within a slot is the leader's, not the observer's, so it cannot be proven."""
        path = self.path([10, 10, 30])
        with self.assertRaises(B.SignalRefused) as caught:
            B.evaluate_cell(path, signal_slot=10, horizon=B.HORIZONS[0], delay=0,
                            schedule={"fee_bps": 100}, policy=dict(B.SCENARIOS[1]))
        self.assertEqual(str(caught.exception), B.N_SAME_SLOT_UNPROVABLE)

    def test_a_missing_fee_schedule_is_refused_not_assumed(self):
        """A hardcoded schedule was a real defect in B15F and is forbidden."""
        path = self.path([10, 20])
        with self.assertRaises(B.SignalRefused) as caught:
            B.evaluate_cell(path, signal_slot=10, horizon=B.HORIZONS[0], delay=1,
                            schedule=None, policy=dict(B.SCENARIOS[1]))
        self.assertEqual(str(caught.exception), B.N_NO_FEE_SCHEDULE)


class SignalCoordinates(unittest.TestCase):
    FEATURES = {"curveA": {"creator_initial_buy_present": True, "t0_is_launch_instruction": False,
                           "is_cashback_enabled": True, "t0_slot": 500},
                "curveB": {"creator_initial_buy_present": False, "t0_is_launch_instruction": True,
                           "is_cashback_enabled": False, "t0_slot": 600}}

    def signal(self, signal_id):
        return next(s for s in B.SIGNALS if s["signal_id"] == signal_id)

    def test_a_true_predicate_fires_at_t0(self):
        got = B.signal_coordinate(self.signal("S1_CREATOR_INITIAL_BUY_PRESENT"),
                                  "curveA", self.FEATURES, {})
        self.assertEqual(got, 500)

    def test_the_complement_arm_fires_on_the_other_curves(self):
        self.assertIsNone(B.signal_coordinate(self.signal("S2_NO_CREATOR_INITIAL_BUY"),
                                              "curveA", self.FEATURES, {}))
        self.assertEqual(B.signal_coordinate(self.signal("S2_NO_CREATOR_INITIAL_BUY"),
                                             "curveB", self.FEATURES, {}), 600)

    def test_a_missing_feature_block_does_not_fire(self):
        self.assertIsNone(B.signal_coordinate(self.signal("S1_CREATOR_INITIAL_BUY_PRESENT"),
                                              "unknown", self.FEATURES, {}))

    def test_a_none_valued_field_is_refused_rather_than_read_as_a_negative(self):
        """A null feature is an unanswered question, not a negative answer.

        This test previously asserted the opposite -- that None means "did not fire". The
        preregistration does not decide the case either way, so this is a judgment, and it is
        recorded here rather than left in the code as a silent default. It rests on a fact about
        the corpus: b11b_t0_features sets all three signal fields to a bool unconditionally
        (`bool(creator_buys)`, a `==` comparison, and `bool(_require(...))`, where `_require`
        raises when the field is absent). None is therefore UNREACHABLE from a working adapter,
        and a None that does arrive is a broken adapter rather than an undetermined curve.

        It matters for S1/S2 in particular: they are complements over one field, so a value read
        as a negative lands in S2's numerator. A corpus fault would not merely shrink the cohort,
        it would manufacture support for the non-issuance signal this study exists to test.
        """
        features = {"c": {"creator_initial_buy_present": None, "t0_slot": 1}}
        with self.assertRaisesRegex(B.CorpusContractViolation, "not absent"):
            B.signal_coordinate(self.signal("S1_CREATOR_INITIAL_BUY_PRESENT"),
                                "c", features, {})

    def test_a_present_block_missing_the_declared_field_is_refused(self):
        """The defect this guards: b11b's real record shape makes every t0 signal return None.

        b11b_t0_features returns {"coordinate": {...}, "features": {...}, "grouping": {...}} with
        no `t0_slot` at any level. Handed to the old `.get()` implementation, S1-S4 returned None
        for every curve and the study reported "no admissible cells" -- indistinguishable from a
        real negative result, on the single pass this study is permitted.
        """
        nested = {"c": {"coordinate": {"slot": 1}, "features": {"creator_initial_buy_present": True},
                        "grouping": {}}}
        with self.assertRaisesRegex(B.CorpusContractViolation, "never declares the field"):
            B.signal_coordinate(self.signal("S1_CREATOR_INITIAL_BUY_PRESENT"), "c", nested, {})
        with self.assertRaisesRegex(B.CorpusContractViolation, "never declares the field"):
            B.baseline_coordinate("baseline_launch", "c", nested, {})

    def test_a_corpus_violation_is_not_a_cell_refusal(self):
        """It must not be catchable as one, or a broken corpus reads as a big refusal count."""
        self.assertFalse(issubclass(B.CorpusContractViolation, B.SignalRefused))

    def test_S5_fires_at_the_reentry_trade_not_at_t0(self):
        got = B.signal_coordinate(self.signal("S5_CREATOR_REENTRY_DELAYED_CONFIRMATION"),
                                  "curveA", self.FEATURES, {"curveA": {"slot": 777}})
        self.assertEqual(got, 777)


if __name__ == "__main__":
    unittest.main()
