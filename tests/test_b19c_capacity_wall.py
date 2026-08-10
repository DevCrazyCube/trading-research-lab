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

    def test_the_prefix_check_costs_time_LINEAR_in_the_ceiling(self):
        """The defect the substring check above could never have found, measured rather than read.

        `assertIn("B15M.assert_prefix_shape", source)` confirms the call is WRITTEN. It cannot
        confirm the call can RETURN. b15m.assert_prefix_shape scans every integer lamport from the
        resolution floor to the ceiling, so its cost is linear in the ceiling -- fine at B15M's
        100,000,000, and ten billion iterations per cell at B19C's raised 10,000,000,000. The B11a
        window yields 23,592 cells; the study is infeasible by five orders of magnitude, and no
        test noticed because none of them ever ran it above a ceiling of one million.

        This measures the scaling at two SMALL ceilings and asserts it is linear, so the
        extrapolation to the production ceiling is a property of the code rather than an argument
        about it. Deliberately not asserting a wall-clock bound: that would be a flaky test on a
        shared machine. Ten-times the ceiling must cost at least four times the work -- a loose
        bound that constant-time or logarithmic behaviour would fail and linear behaviour passes
        with room to spare.
        """
        entry = {"virtual_quote": 30_000_000_000, "virtual_token": 1_073_000_000_000_000,
                 "real_quote": 0, "real_token": 793_100_000_000_000,
                 "quote_mint": B.B15M.NATIVE_QUOTE_MINT, "mayhem_mode": False, "complete": False,
                 "slot": 437_300_000}
        exit_state = dict(entry)
        exit_state["real_quote"] = 5_000_000_000
        counted = {}
        original = B.B15M.is_payable
        for ceiling in (10_000, 100_000):
            calls = {"n": 0}

            def counting(*args, _calls=calls, **kwargs):
                _calls["n"] += 1
                return original(*args, **kwargs)

            B.B15M.is_payable = counting
            try:
                B.B15M.assert_prefix_shape(entry, exit_state, ceiling)
            except Exception:                                             # noqa: BLE001
                pass
            finally:
                B.B15M.is_payable = original
            counted[ceiling] = calls["n"]

        self.assertGreaterEqual(
            counted[100_000], counted[10_000] * 4,
            f"a ten-fold ceiling cost {counted[100_000]} against {counted[10_000]}; the prefix "
            "check must be understood as LINEAR in the ceiling, because that is what makes B19C's "
            "hundred-fold raise infeasible rather than merely slow")
        self.assertGreater(counted[10_000], 1_000,
                           "the scan must actually run, or this test measures nothing")

    def test_no_bisection_is_written_here(self):
        tree = ast.parse((ROOT / "scripts" / "b19c_capacity_wall.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.While):
                self.fail("a search loop here would be a second implementation of B15M's")

    def test_the_whole_grid_is_reported_and_no_size_is_selected(self):
        """The no-fishing property, guarded positively rather than left true-by-construction.

        `test_no_bisection_is_written_here` forbids `while`, which proves a NARROWER thing: that
        B15M's search is not reimplemented here, so the differential compares two independent
        routes. It does NOT constrain selection over the grid, which needs no loop at all --
        `max(GRID, key=...)`, `sorted(...)[-1]` or a `for` tracking a best all pass a while-only
        check. Reporting every size and ranking none is the property that keeps this a description
        of a shape rather than a search for the size that reads best; it is asserted here.
        """
        entry = {"virtual_quote": 30_000_000_000, "virtual_token": 1_073_000_000_000_000,
                 "real_quote": 0, "real_token": 793_100_000_000_000,
                 "quote_mint": B.B15M.NATIVE_QUOTE_MINT, "mayhem_mode": False, "complete": False,
                 "slot": 437_300_000}
        executability = B.grid_executability(entry, dict(entry, slot=entry["slot"] + 1))
        self.assertEqual(sorted(executability), sorted(B.GRID),
                         "every frozen size must be reported, never a subset")

    def test_nothing_ranks_or_selects_over_the_grid(self):
        """No `max`/`min`/`sorted` may be keyed over GRID, and no field may name a chosen size."""
        source = (ROOT / "scripts" / "b19c_capacity_wall.py").read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            name = getattr(function, "id", None) or getattr(function, "attr", None)
            if name not in ("max", "min", "sorted"):
                continue
            referenced = {child.id for child in ast.walk(node)
                          if isinstance(child, ast.Name)}
            self.assertNotIn(
                "GRID", referenced,
                f"line {node.lineno}: {name}() keyed over GRID would select a size, and the "
                "study reports the whole grid rather than choosing from it")
        for forbidden in ("best_size", "selected_size", "optimal_size", "recommended_size"):
            self.assertNotIn(forbidden, source,
                             "a field naming a chosen size turns a reported shape into a pick")

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
