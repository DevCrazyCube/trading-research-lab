"""Tests for B19C. No network, no evaluation window.

The failure this study is most exposed to is reporting a BOUND as a MEASUREMENT. A cell at the
ceiling has an unknown capacity above it, and folding that into a distribution understates the
upper tail by construction while looking like a complete answer.
"""
import ast
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("b19c", ROOT / "scripts" / "b19c_capacity_wall.py")
B = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B)
DOCUMENT = json.loads((ROOT / "research" /
                       "B19C_CAPACITY_WALL_SIZE_DEPENDENCE_PREREGISTRATION.json").read_bytes())


class ItImplementsTheFrozenDocument(unittest.TestCase):
    def test_the_pin_is_verified_and_a_changed_document_is_refused(self):
        self.assertEqual(B.verify_preregistration()["preregistration_id"],
                         "B19C_CAPACITY_WALL_SIZE_DEPENDENCE_V1")
        with self.assertRaisesRegex(B.CapacityRefused, "hashes"):
            B.verify_preregistration(expected="0" * 64)

    def test_the_ceiling_is_exactly_one_hundred_times_the_old_one(self):
        self.assertEqual(B.NEW_CEILING, B.OLD_CEILING * 100)
        self.assertEqual(B.NEW_CEILING, DOCUMENT["the_raised_ceiling"]["new_search_ceiling_lamports"])

    def test_the_grid_matches_the_frozen_grid_exactly(self):
        self.assertEqual(list(B.GRID), DOCUMENT["the_wall_shape"]["grid_lamports"])

    def test_the_first_three_grid_members_are_b15ms_own(self):
        """Retained so the two studies can be read against each other."""
        self.assertEqual(list(B.GRID)[:3], [1_000_000, 10_000_000, 100_000_000])

    def test_a_drifted_ceiling_is_refused(self):
        original = B.NEW_CEILING
        B.NEW_CEILING = original + 1
        self.addCleanup(setattr, B, "NEW_CEILING", original)
        with self.assertRaisesRegex(B.CapacityRefused, "this module searches to"):
            B.verify_preregistration()

    def test_the_censoring_statement_is_verbatim_and_drift_is_refused(self):
        """Required beside every figure. A paraphrase would misdescribe the population."""
        self.assertEqual(B.CENSORING_STATEMENT,
                         DOCUMENT["reporting"]["censoring_statement_required_verbatim"])
        original = B.CENSORING_STATEMENT
        B.CENSORING_STATEMENT = original.replace("29%", "30%")
        self.addCleanup(setattr, B, "CENSORING_STATEMENT", original)
        with self.assertRaisesRegex(B.CapacityRefused, "drifted from the document"):
            B.verify_preregistration()

    def test_the_refusal_codes_are_the_documents_own(self):
        frozen = {entry["code"] for entry in DOCUMENT["refusal_codes"]}
        self.assertTrue(set(B.REFUSAL_CODES).issubset(frozen))


class NoFormulaIsReimplemented(unittest.TestCase):
    def test_the_search_is_b15ms_not_a_second_copy(self):
        """A reimplemented search would make the differential compare two of my own mistakes."""
        source = (ROOT / "scripts" / "b19c_capacity_wall.py").read_text()
        self.assertIn("B15M.external_capacity", source)
        self.assertIn("B15M.assert_maximal", source)
        self.assertIn("B15M.capacity_via_b10b", source)
        self.assertIn("B15M.assert_prefix_shape", source)

    def test_no_bisection_is_written_here(self):
        tree = ast.parse((ROOT / "scripts" / "b19c_capacity_wall.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.While):
                self.fail("a search loop here would be a second implementation of B15M's")

    def test_no_float_literal_anywhere(self):
        tree = ast.parse((ROOT / "scripts" / "b19c_capacity_wall.py").read_text())
        floats = [n for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and isinstance(n.value, float)]
        self.assertEqual(floats, [])

    def test_it_names_no_evaluation_window_path(self):
        source = (ROOT / "scripts" / "b19c_capacity_wall.py").read_text()
        self.assertNotIn("b11a", source)


class ABoundIsNotAMeasurement(unittest.TestCase):
    def test_cap_hit_is_true_at_and_above_the_ceiling(self):
        self.assertTrue(B.cap_hit(B.NEW_CEILING))
        self.assertFalse(B.cap_hit(B.NEW_CEILING - 1))

    def test_cap_hit_cells_are_excluded_from_the_order_statistics(self):
        """Including a bound as though it were a value understates the upper tail by construction."""
        capacities = [10, 20, 30, B.NEW_CEILING, B.NEW_CEILING]
        report = B.summarise(capacities, {}, {})
        stats = report["capacity_order_statistics_measured_only"]
        self.assertEqual(stats["max"], 30, "the ceiling must not appear as a measured maximum")
        self.assertEqual(report["counts"]["cap_hit_at_new_ceiling"], 2)

    def test_the_report_says_the_ceiling_is_not_a_value(self):
        report = B.summarise([B.NEW_CEILING], {}, {})
        self.assertIn("unmeasured above", report["ceiling_is_not_a_value"])

    def test_every_report_carries_the_censoring_statement(self):
        self.assertEqual(B.summarise([1], {}, {})["censoring"], B.CENSORING_STATEMENT)

    def test_the_report_states_it_is_not_a_sizing_proposal(self):
        self.assertIn("is proposed, recommended or implied",
                      B.summarise([1], {}, {})["not_a_sizing_proposal"])

    def test_newly_measured_cells_are_counted_separately(self):
        capacities = [50, B.OLD_CEILING, B.OLD_CEILING * 5, B.NEW_CEILING]
        counts = B.summarise(capacities, {}, {})["counts"]
        self.assertEqual(counts["newly_measured_cells"], 2,
                         "cells at or above the OLD ceiling but below the new one are the ones "
                         "this study exists to measure")

    def test_all_cap_hit_yields_no_measured_statistics_rather_than_a_fabricated_one(self):
        report = B.summarise([B.NEW_CEILING, B.NEW_CEILING], {}, {})
        self.assertNotIn("capacity_order_statistics_measured_only", report)


class ThePreviouslyCapHitSubgroup(unittest.TestCase):
    def test_it_is_reported_separately_from_the_population(self):
        """'mixing it into the whole-population distribution would hide the answer inside the
        question' -- this subgroup is the entire reason the study exists."""
        report = B.summarise([1, 2], {}, {}, previously_cap_hit=[B.OLD_CEILING * 3,
                                                                 B.NEW_CEILING])
        group = report["previously_cap_hit_subgroup"]
        self.assertEqual(group["cells"], 2)
        self.assertEqual(group["still_cap_hit_at_the_raised_ceiling"], 1)
        self.assertEqual(group["now_measured"], 1)

    def test_a_subgroup_still_entirely_cap_hit_reports_no_statistics(self):
        report = B.summarise([1], {}, {}, previously_cap_hit=[B.NEW_CEILING])
        self.assertIsNone(report["previously_cap_hit_subgroup"]["measured_capacity_order_statistics"])


class QuantitiesAreIntegers(unittest.TestCase):
    def test_a_non_integer_capacity_is_a_documented_refusal(self):
        with self.assertRaisesRegex(B.CapacityRefused, B.W_FLOAT_PRESENT):
            B.assert_integer("capacity", 1.5)

    def test_a_bool_is_not_an_integer_quantity(self):
        with self.assertRaisesRegex(B.CapacityRefused, B.W_FLOAT_PRESENT):
            B.assert_integer("capacity", True)

    def test_an_integer_passes(self):
        self.assertEqual(B.assert_integer("capacity", 7), 7)
