"""Tests for B19B. No network, no evaluation window.

As with B19D, the tests that matter enforce the document's prohibitions against the implementer.
The drawdown rules are where this study could most easily be quietly broken, because a fraction
compared as a float is indistinguishable from one compared exactly until it lands on a boundary.
"""
import ast
import importlib.util
import itertools
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("b19b", ROOT / "scripts" / "b19b_exit_timing_policy.py")
B = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B)
DOCUMENT = json.loads((ROOT / "research" /
                       "B19B_EXIT_TIMING_POLICY_PREREGISTRATION.json").read_bytes())


# DERIVED from b9d, not written here. I first assumed the wrapped-SOL mint and every entry was
# refused as "not native SOL" -- the frozen regime marks native with the System Program address.
_B9D = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("b9d_for_mint", ROOT / "scripts" / "b9d_transaction_bodies.py"))
_B9D.__spec__.loader.exec_module(_B9D)
NATIVE = _B9D.NATIVE_QUOTE_MINT
B10BP = B.B10BP


def path(rows):
    """rows: (slot, real_quote, complete). Everything else held constant.

    `transaction_index` enumerates rather than sitting at 0, so two observations may share a slot
    without becoming the same canonical coordinate. Two transactions in one slot always differ in
    execution position -- that is what a transaction index is.
    """
    return [{"slot": s, "transaction_index": i, "outer_index": 0, "inner_index": 0, "kind": "trade",
             # Reserves borrowed from b10a's own known-good fixture. My first attempt invented
             # them and every entry was X_ENTRY_UNPRICEABLE, so the rule under test was never
             # reached -- a fixture that refuses before the code you meant to exercise.
             "virtual_quote": 30_000_000_000, "virtual_token": 1_073_000_000_000_000,
             "real_quote": q, "real_token": 793_100_000_000_000, "quote_mint": NATIVE,
             "mayhem_mode": False, "complete": c} for i, (s, q, c) in enumerate(rows)]


class ItImplementsTheFrozenDocument(unittest.TestCase):
    def test_the_pin_is_verified_and_a_changed_document_is_refused(self):
        self.assertEqual(B.verify_preregistration()["preregistration_id"],
                         "B19B_EXIT_TIMING_POLICY_V1")
        with self.assertRaisesRegex(B.ExitRefused, "hashes"):
            B.verify_preregistration(expected="0" * 64)

    def test_the_rule_set_matches_the_frozen_list_in_content_and_order(self):
        frozen = [r["rule_id"] for r in DOCUMENT["frozen_exit_rules"]["set"]]
        self.assertEqual([r["rule_id"] for r in B.EXIT_RULES], frozen)

    def test_a_reordered_rule_set_is_refused(self):
        original = B.EXIT_RULES
        B.EXIT_RULES = tuple(reversed(original))
        self.addCleanup(setattr, B, "EXIT_RULES", original)
        with self.assertRaisesRegex(B.ExitRefused, "does not match the frozen list"):
            B.verify_preregistration()

    def test_the_family_size_matches_the_document(self):
        self.assertEqual(B.FAMILY_SIZE, DOCUMENT["multiplicity"]["family_size"])
        self.assertEqual(B.FAMILY_SIZE, 24)

    def test_all_three_drawdown_fractions_are_present_none_selected(self):
        """A fixed grid REPORTED IN FULL. Keeping one and dropping the others would turn a grid
        into a choice, which is the thing the grid exists to prevent."""
        fractions = {(r["numerator"], r["denominator"]) for r in B.EXIT_RULES
                     if r["kind"] == "peak_drawdown"}
        self.assertEqual(fractions, {(1, 10), (1, 4), (1, 2)})

    def test_the_frozen_inputs_match_the_document(self):
        frozen = DOCUMENT["frozen_inputs_unchanged"]
        self.assertEqual(list(B.ENTRY_DELAYS), frozen["entry_delays_slots"])
        self.assertEqual(B.POSITION, frozen["position_lamports"])
        self.assertEqual([s["scenario_id"] for s in B.SCENARIOS],
                         [s["scenario_id"] for s in frozen["cost_scenarios"]])


class NoFloatReachesAQuantity(unittest.TestCase):
    def test_no_float_literal_anywhere(self):
        tree = ast.parse((ROOT / "scripts" / "b19b_exit_timing_policy.py").read_text())
        floats = [n for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and isinstance(n.value, float)]
        self.assertEqual(floats, [])

    def test_the_drawdown_comparison_uses_cross_multiplication_not_division(self):
        """The one place a fraction could silently become a float.

        `realizable / peak <= n / d` and `realizable * d <= peak * n` agree everywhere except at
        the boundary, and the boundary is exactly where the rule fires.
        """
        tree = ast.parse((ROOT / "scripts" / "b19b_exit_timing_policy.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "select_exit":
                divisions = [d for d in ast.walk(node) if isinstance(d, ast.BinOp)
                             and isinstance(d.op, ast.Div)]
                self.assertEqual(divisions, [], "a fraction must be compared by multiplication")

    def test_it_names_no_evaluation_window_path(self):
        source = (ROOT / "scripts" / "b19b_exit_timing_policy.py").read_text()
        for forbidden in ("b11a", "research/b11a"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


class TheRulesSelectWhatTheyClaim(unittest.TestCase):
    # Every rate STATED. b10a refuses a schedule missing any of them rather than defaulting one --
    # its own rule, and it caught this fixture twice: first for the wrong native mint, then for an
    # absent cashback rate. A fixture that refuses before the code under test is reached proves
    # nothing about that code.
    SCHEDULE = {"fee_bps": 100, "creator_fee_bps": 0, "cashback_fee_bps": 0, "buyback_fee_bps": 0}
    POLICY = dict(B.SCENARIOS[1])

    def test_first_observation_is_strictly_after_entry(self):
        p = path([(10, 30_000_000_000, False), (20, 30_000_000_000, False),
                  (30, 30_000_000_000, False)])
        got = B.select_exit(B.EXIT_RULES[2], p, p[0], 1000, self.SCHEDULE, self.POLICY)
        self.assertEqual(got["slot"], 20, "strictly after, never the entry observation itself")

    def test_first_observation_with_nothing_after_entry_never_triggers(self):
        p = path([(10, 30_000_000_000, False)])
        self.assertIsNone(B.select_exit(B.EXIT_RULES[2], p, p[0], 1000, self.SCHEDULE, self.POLICY))

    def test_a_slot_horizon_beyond_the_path_never_triggers(self):
        p = path([(10, 30_000_000_000, False), (20, 30_000_000_000, False)])
        self.assertIsNone(B.select_exit(B.EXIT_RULES[0], p, p[0], 1000, self.SCHEDULE, self.POLICY))

    def test_a_slot_horizon_uses_state_in_force_not_the_next_observation(self):
        p = path([(10, 30_000_000_000, False), (500, 30_000_000_000, False),
                  (2_000, 30_000_000_000, False)])
        got = B.select_exit(B.EXIT_RULES[0], p, p[0], 1000, self.SCHEDULE, self.POLICY)
        self.assertEqual(got["slot"], 500, "the last observation at or BEFORE slot 1,010")

    def test_complete_or_horizon_prefers_completion_when_it_occurs_first(self):
        p = path([(10, 30_000_000_000, False), (50, 30_000_000_000, True),
                  (20_000, 30_000_000_000, False)])
        got = B.select_exit(B.EXIT_RULES[4], p, p[0], 1000, self.SCHEDULE, self.POLICY)
        self.assertEqual(got["slot"], 50)

    def test_complete_or_horizon_falls_back_to_the_horizon(self):
        p = path([(10, 30_000_000_000, False), (5_000, 30_000_000_000, False),
                  (20_000, 30_000_000_000, False)])
        got = B.select_exit(B.EXIT_RULES[4], p, p[0], 1000, self.SCHEDULE, self.POLICY)
        self.assertEqual(got["slot"], 5_000, "state in force at entry+10,000")

    def test_a_rule_that_never_triggers_is_a_documented_refusal_not_a_zero(self):
        p = path([(10, 30_000_000_000, False)])
        with self.assertRaises(B.ExitRefused) as caught:
            B.evaluate_cell(B.EXIT_RULES[2], p, signal_slot=9, delay=1,
                            schedule=self.SCHEDULE, policy=self.POLICY)
        self.assertEqual(str(caught.exception), B.X_RULE_NEVER_TRIGGERED)

    def test_a_complete_curve_at_entry_is_refused(self):
        p = path([(10, 30_000_000_000, True), (20, 30_000_000_000, False)])
        with self.assertRaises(B.ExitRefused) as caught:
            B.evaluate_cell(B.EXIT_RULES[2], p, signal_slot=9, delay=1,
                            schedule=self.SCHEDULE, policy=self.POLICY)
        self.assertEqual(str(caught.exception), B.X_COMPLETE_AT_ENTRY)


class ReportingDiscipline(unittest.TestCase):
    def test_the_median_is_a_value_from_the_data_never_a_mean(self):
        self.assertEqual(B.exact_median([2, 4]), 2)
        self.assertEqual(B.exact_median([-9, 0, 9]), 0)

    def test_absence_is_none_not_zero(self):
        self.assertIsNone(B.exact_median([]))

    def test_coverage_is_present_even_with_no_outcome(self):
        report = B.summarise([], {B.X_RULE_NEVER_TRIGGERED: 12}, cohort_size=50)
        self.assertIsNone(report["outcome"])
        self.assertEqual(report["coverage"]["censored_rule_never_triggered"], 12)

    def test_a_never_triggered_cell_is_censored_and_not_counted_as_zero(self):
        report = B.summarise([7, 9], {B.X_RULE_NEVER_TRIGGERED: 30}, cohort_size=50)
        self.assertEqual(report["coverage"]["censored_rule_never_triggered"], 30)
        self.assertEqual(report["outcome"]["median"], 7)

    def test_no_figure_may_be_called_a_return(self):
        self.assertIn("is a return", B.summarise([1], {}, 1)["not_a_return"])


class RowPermutationInvariance(unittest.TestCase):
    """The document's `determinism.row_permutation`, enforced rather than assumed.

    "the output must be identical under any permutation of the input rows, checked by running the
    whole computation over shuffled inputs and comparing field for field."

    This is satisfied ARCHITECTURALLY by sorting once at the adapter boundary and asserting the
    postcondition here: the study either gets a canonical path and returns one answer, or it gets a
    permuted one and REFUSES. What it must never do is silently return a different number, which is
    what every path helper here did before -- `first_at_or_after`, `state_in_force`,
    `path.index(entry)` and the running peak all read list order.

    Refusal is the honest reading of "identical output" for a module that is handed a path rather
    than building one. A module that sorted its input would satisfy the letter of the requirement
    while hiding the fact that its caller had lost the ordering.
    """
    SCHEDULE = {"fee_bps": 100, "creator_fee_bps": 0, "cashback_fee_bps": 0, "buyback_fee_bps": 0}
    POLICY = dict(B.SCENARIOS[1])
    ROWS = [(10, 30_000_000_000, False), (500, 31_000_000_000, False),
            (2_000, 29_000_000_000, False), (12_000, 33_000_000_000, False)]

    def _cell(self, p):
        return B.evaluate_cell(B.EXIT_RULES[0], p, signal_slot=10, delay=1,
                               schedule=self.SCHEDULE, policy=self.POLICY)

    def test_the_canonical_order_is_evaluated_identically_every_time(self):
        canonical = path(self.ROWS)
        first = self._cell(canonical)
        for _ in range(5):
            self.assertEqual(self._cell(path(self.ROWS)), first,
                             "the same rows in canonical order must give the same integer")

    def test_every_non_canonical_permutation_refuses_rather_than_answering(self):
        """Not one permutation may return a number. A wrong number is worse than no number."""
        canonical = path(self.ROWS)
        checked = 0
        for permutation in itertools.permutations(range(len(canonical))):
            if list(permutation) == sorted(permutation):
                continue
            shuffled = [canonical[i] for i in permutation]
            with self.assertRaises(B10BP.PathRefused):
                self._cell(shuffled)
            checked += 1
        self.assertEqual(checked, 23, "all 4!-1 non-identity permutations must be covered")

    def test_a_permuted_path_never_silently_yields_a_different_result(self):
        """The measured regression, stated as what was actually observed rather than as a guess.

        With the guard disabled and reserves that vary across the path
        ((10, 30 SOL), (500, 60), (2000, 20), (12000, 33)), E_FIXED_H1000 on the canonical order
        returns an outcome of -4,904,911 lamports; under permutation (0, 2, 3, 1) the SAME rows
        return X_RULE_NEVER_TRIGGERED. The cell moves between the outcome set and the coverage
        table, which changes the denominator AND the set the median is taken over.

        Honest scope: across the rule set and the fixtures tried, permutation flipped
        outcome-versus-refusal but was NOT observed turning one integer into a different integer.
        That is a weaker fault than a silently wrong number and it is still a fault -- a
        coverage table is a result here, and the document requires it reported before any outcome.
        """
        varied = path([(10, 30_000_000_000, False), (500, 60_000_000_000, False),
                       (2_000, 20_000_000_000, False), (12_000, 33_000_000_000, False)])
        permuted = [varied[0], varied[2], varied[3], varied[1]]
        self.assertIsInstance(self._cell(varied), int, "the canonical order yields an outcome")
        with self.assertRaises(B10BP.PathRefused) as caught:
            self._cell(permuted)
        self.assertIn("precedes", str(caught.exception))
