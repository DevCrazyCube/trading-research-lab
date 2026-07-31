"""B9f classification-failure coverage gate.

The gate's substance is its denominator and its refusal to bucket. Most of these tests are about
population arithmetic and about what the gate declines to accept, not about row validity.
"""
import contextlib
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b9f_failure_coverage", ROOT / "scripts" / "b9f_failure_coverage.py")
B9F = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B9F)
B9D = B9F.B9D

ZERO_CEILINGS = {name: 0 for name in B9F.CATEGORY_NAMES}


class FailureFixture(unittest.TestCase):

    def setUp(self):
        self.path = pathlib.Path(tempfile.mkdtemp()) / "failures.sqlite"
        self.database = B9D.connect(str(self.path))
        B9D.schema(self.database)
        self.addCleanup(self.database.close)
        self.next_index = 0

    def add_instruction(self, target=1, idl_name="buy", program_id=None):
        self.next_index += 1
        index = self.next_index
        self.database.execute(
            "INSERT INTO instruction (slot,transaction_index,outer_index,inner_index,signature,"
            "program_id,discriminator,idl_name,target,accounts_json,data_len) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (700, index, 0, -1, f"sig-{index}", program_id or B9D.PUMP_PROGRAM, "00" * 8,
             idl_name, target, "[]", 16))
        return (700, index, 0, -1, f"sig-{index}")

    def add_failure(self, reason, coordinates=None, signature=None):
        slot, index, outer, inner, sig = coordinates or self.add_instruction(idl_name=None)
        self.database.execute(
            "INSERT INTO classification_failure (signature,slot,transaction_index,outer_index,"
            "inner_index,program_id,discriminator,reason,context_json) VALUES (?,?,?,?,?,?,?,?,?)",
            (signature or sig, slot, index, outer, inner, B9D.PUMP_PROGRAM, "00" * 8, reason,
             "{}"))
        return (slot, index, outer, inner, sig)


class CategoryVocabularyTests(unittest.TestCase):
    """Categories are matched against the decoder's own prose, so they must track it.

    Reasons are generated through their real producers wherever a producer can be called directly.
    A rewording in B9d then fails this suite instead of quietly creating an unrecognised category
    -- or, worse, matching an existing one and being counted as something it is not.
    """

    def test_the_classifier_reasons_still_match_their_categories(self):
        short = B9D.classify_instruction(B9D.PUMP_PROGRAM, b"\x01\x02", {})[3]
        self.assertEqual(B9F.categorise(short), "short_discriminator")
        unknown = B9D.classify_instruction(B9D.PUMP_PROGRAM, bytes(range(16)), {})[3]
        self.assertEqual(B9F.categorise(unknown), "unknown_discriminator")

    def test_the_eventless_reserve_reason_still_matches_its_category(self):
        unresolved = B9D.unresolved_eventless_reserve_transition(
            B9D.PUMPSWAP_PROGRAM, "init_boost", False, {})
        self.assertEqual(B9F.categorise(unresolved["reason"]), "eventless_reserve_candidate")

    def test_a_reserve_chain_reason_is_delegated_not_categorised(self):
        """B9e owns curve breaks. Counting one here as well would double-charge it."""
        _, _, reason = B9D.advance_curve_chain({}, "mint", "TradeEvent", {
            "virtual_quote_reserves": 1, "virtual_token_reserves": 1, "real_quote_reserves": 1,
            "real_token_reserves": 1, "quote_amount": 0, "token_amount": 0, "is_buy": True})
        self.assertEqual(B9F.categorise(B9F.DELEGATED_PREFIX + reason), B9F.DELEGATED_CATEGORY)

    def test_every_declared_category_is_distinct_and_none_is_dead(self):
        """A category that matches nothing is dead weight that reads as coverage."""
        for name, prefix in B9F.FAILURE_CATEGORIES:
            with self.subTest(category=name):
                self.assertEqual(B9F.categorise(prefix + " something specific"), name)
        prefixes = [prefix for _, prefix in B9F.FAILURE_CATEGORIES]
        self.assertEqual(len(set(prefixes)), len(prefixes))

    def test_an_unrecognised_reason_is_not_bucketed(self):
        """`other` is where an unrecognised failure class goes to stop being noticed."""
        self.assertIsNone(B9F.categorise("something nobody has written yet"))


class CoverageTests(FailureFixture):

    def test_the_denominator_is_the_target_population_not_the_failures(self):
        """A rate over observed failures cannot fall, so it measures nothing."""
        for _ in range(9):
            self.add_instruction(idl_name="buy")
        self.add_failure(B9F.FAILURE_CATEGORIES[1][1] + "Pump discriminator ab; not dropped")
        coverage = B9F.failure_coverage(self.database)
        self.assertEqual(coverage["target_instructions"], 10)
        self.assertEqual(coverage["counts"]["unknown_discriminator"], 1)
        self.assertAlmostEqual(coverage["rates"]["unknown_discriminator"], 0.1)

    def test_a_target_instruction_that_is_neither_named_nor_explained_is_refused(self):
        """The silent omission this gate exists for: the decoder did not understand the row and
        did not record that it had not. Walking the failure table can never reveal it."""
        self.add_instruction(idl_name=None)
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9F.failure_coverage(self.database)
        self.assertIn("neither named nor explained", str(ctx.exception))

    def test_a_non_target_instruction_may_be_unnamed(self):
        """B9d does not pretend a third-party program has a Pump IDL, so an unnamed non-target row
        is correct rather than a silent omission."""
        self.add_instruction(target=0, idl_name=None, program_id="SomeOtherProgram")
        self.add_instruction(idl_name="buy")
        self.assertEqual(B9F.failure_coverage(self.database)["target_instructions"], 1)

    def test_an_uncategorised_failure_class_is_refused(self):
        self.add_failure("a brand new kind of problem nobody declared")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9F.failure_coverage(self.database)
        self.assertIn("match no declared category", str(ctx.exception))

    def test_reserve_chain_failures_are_reported_separately_and_never_double_counted(self):
        self.add_instruction(idl_name="buy")
        self.add_failure(B9F.DELEGATED_PREFIX + "curve reserve continuity mismatch: previous=...")
        coverage = B9F.failure_coverage(self.database)
        self.assertEqual(coverage["delegated_to_b9e"], 1)
        self.assertEqual(sum(coverage["counts"].values()), 0)
        self.assertNotIn(B9F.DELEGATED_CATEGORY, coverage["counts"])

    def test_a_failure_with_no_parent_instruction_is_refused(self):
        self.add_instruction(idl_name="buy")
        self.database.execute(
            "INSERT INTO classification_failure (signature,slot,transaction_index,outer_index,"
            "inner_index,program_id,discriminator,reason,context_json) VALUES (?,?,?,?,?,?,?,?,?)",
            ("sig-orphan", 999, 0, 0, -1, B9D.PUMP_PROGRAM, "00" * 8,
             B9F.FAILURE_CATEGORIES[0][1], "{}"))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9F.failure_coverage(self.database)
        self.assertIn("no parent instruction", str(ctx.exception))

    def test_a_failure_at_an_impossible_coordinate_is_refused(self):
        self.add_instruction(idl_name="buy")
        self.database.execute(
            "INSERT INTO classification_failure (signature,slot,transaction_index,outer_index,"
            "inner_index,program_id,discriminator,reason,context_json) VALUES (?,?,?,?,?,?,?,?,?)",
            ("sig-bad", 700, -5, 0, -2, B9D.PUMP_PROGRAM, "00" * 8,
             B9F.FAILURE_CATEGORIES[0][1], "{}"))
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9F.failure_coverage(self.database)
        self.assertIn("no valid canonical coordinate", str(ctx.exception))

    def test_an_outer_instruction_coordinate_is_not_treated_as_impossible(self):
        """`inner_index` is -1 for an outer instruction; only -2 and below are malformed."""
        self.add_failure(B9F.FAILURE_CATEGORIES[0][1])
        self.assertEqual(B9F.failure_coverage(self.database)["counts"]["short_discriminator"], 1)

    def test_an_empty_target_population_is_refused_rather_than_reported_as_clean(self):
        """Zero failures over zero instructions is vacuous, not a pass."""
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9F.failure_coverage(self.database)
        self.assertIn("vacuous", str(ctx.exception))


class CeilingTests(FailureFixture):

    def test_the_gate_refuses_to_run_without_ratified_ceilings(self):
        self.add_instruction(idl_name="buy")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9F.assert_failure_coverage(self.database)
        self.assertIn("not ratified", str(ctx.exception))

    def test_a_partial_ceiling_mapping_is_refused_rather_than_treated_as_unbounded(self):
        """A category silently exempted from its own gate is the failure this prevents."""
        self.add_instruction(idl_name="buy")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9F.assert_failure_coverage(self.database, {"unknown_discriminator": 0})
        self.assertIn("missing", str(ctx.exception))

    def test_an_unknown_ceiling_name_is_refused(self):
        self.add_instruction(idl_name="buy")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9F.assert_failure_coverage(self.database, dict(ZERO_CEILINGS, invented=3))
        self.assertIn("unknown", str(ctx.exception))

    def test_the_delegated_category_cannot_be_given_a_b9f_ceiling(self):
        self.add_instruction(idl_name="buy")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9F.assert_failure_coverage(
                self.database, dict(ZERO_CEILINGS, **{B9F.DELEGATED_CATEGORY: 5}))
        self.assertIn("governed by B9e", str(ctx.exception))

    def test_a_category_over_its_ceiling_fails_closed_and_names_itself(self):
        self.add_instruction(idl_name="buy")
        self.add_failure(B9F.FAILURE_CATEGORIES[1][1] + "Pump discriminator ab; not dropped")
        with self.assertRaises(B9D.FreezeViolation) as ctx:
            B9F.assert_failure_coverage(self.database, ZERO_CEILINGS)
        self.assertIn("unknown_discriminator=1 exceeds 0", str(ctx.exception))
        report = B9F.assert_failure_coverage(
            self.database, dict(ZERO_CEILINGS, unknown_discriminator=1))
        self.assertEqual(report["counts"]["unknown_discriminator"], 1)

    def test_a_delegated_failure_does_not_consume_any_categorys_ceiling(self):
        self.add_instruction(idl_name="buy")
        self.add_failure(B9F.DELEGATED_PREFIX + "curve reserve chain was previously broken")
        report = B9F.assert_failure_coverage(self.database, ZERO_CEILINGS)
        self.assertEqual(report["delegated_to_b9e"], 1)


class CommandLineTests(FailureFixture):

    def run_cli(self, *argv):
        self.database.commit()
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = B9F.main([str(self.path), *argv])
        return code, json.loads(captured.getvalue())

    def test_measuring_without_ceilings_reports_but_does_not_gate(self):
        self.add_instruction(idl_name="buy")
        self.add_failure(B9F.FAILURE_CATEGORIES[1][1] + "Pump discriminator ab; not dropped")
        code, report = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(report["counts"]["unknown_discriminator"], 1)

    def test_supplying_ceilings_gates(self):
        self.add_instruction(idl_name="buy")
        self.add_failure(B9F.FAILURE_CATEGORIES[1][1] + "Pump discriminator ab; not dropped")
        with self.assertRaises(B9D.FreezeViolation):
            self.run_cli("--ceilings", json.dumps(ZERO_CEILINGS))


class PreregistrationDocumentTests(unittest.TestCase):

    PATH = ROOT / "research" / "B9F_FAILURE_COVERAGE_PREREGISTRATION.md"

    def test_the_document_defines_every_category_the_code_can_assign(self):
        text = self.PATH.read_text(encoding="utf-8")
        for name in B9F.CATEGORY_NAMES:
            self.assertIn(f"`{name}`", text)
        self.assertIn(f"`{B9F.DELEGATED_CATEGORY}`", text)

    def test_the_document_records_no_measured_outcome_counts(self):
        text = self.PATH.read_text(encoding="utf-8")
        self.assertIn("no measured outcome counts", text)
        self.assertIn("### Verified facts", text)
        self.assertIn("### Open questions", text)

    def test_the_document_still_declares_the_ceilings_unratified(self):
        """If this starts failing because someone ratified them, update it in the same commit that
        wires the numbers into the code -- not separately."""
        text = self.PATH.read_text(encoding="utf-8")
        self.assertIn("NOT ratified", text)


if __name__ == "__main__":
    unittest.main()
