"""B15m tests. The maximum is attacked from both sides, and every refusal is driven.

The claim worth breaking here is maximality. A search that returns one short reports a book as
shallower than it was; one that returns one long reports proceeds no counterparty could pay. So the
answer is checked at q and at q+1 on every path, and the whole prefix assumption is scanned by
brute force on small ceilings rather than argued about.
"""
import importlib.util
import json
import pathlib
import random
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


B15M = _load("b15m_liquidity_capacity", "b15m_liquidity_capacity.py")
B15L, B10A, B10B, B9I = B15M.B15L, B15M.B10A, B15M.B10B, B15M.B9I

NATIVE = B15M.NATIVE_QUOTE_MINT
CEILING = 100_000_000
SCHEDULE = {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0, "buyback_fee_bps": 5000}
POLICY = {"base_fee_lamports": 5000, "priority_fee_lamports": 100_000, "tip_lamports": 0,
          "ata_rent_lamports": 2_039_280, "failed_attempts": 0}


def entry_state(**overrides):
    record = {"signature": "Sig1", "delay_slots": 1, "bonding_curve": "C", "mint": "M",
              "context_slot": 1000, "lateness_slots": 0,
              "virtual_quote": 30_000_000_000, "virtual_token": 1_073_000_000_000_000,
              "real_quote": 0, "real_token": 793_100_000_000_000,
              "quote_mint": NATIVE, "mayhem_mode": False, "complete": False}
    record.update(overrides)
    return record


def exit_state(**overrides):
    record = entry_state()
    record.update({"horizon": "h_1000_slots", "context_slot": 2000,
                   "real_quote": 1_000_000_000, "virtual_quote": 31_000_000_000,
                   "virtual_token": 1_038_580_645_161_290,
                   "real_token": 758_680_645_161_290})
    record.update(overrides)
    return record


class TestPreregistration(unittest.TestCase):
    def test_the_freeze_is_pinned(self):
        document = B15M.verify_preregistration()
        self.assertEqual(document["preregistration_id"], "B15M_LIQUIDITY_CAPACITY_V1")
        self.assertTrue(document["committed_before_any_capacity_computed"])

    def test_a_tampered_freeze_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            altered = pathlib.Path(directory) / "altered.json"
            document = json.loads(B15M.PREREG_PATH.read_bytes())
            document["frozen_inputs_unchanged"]["capacity_search_upper_bound_lamports"] = 1
            altered.write_text(json.dumps(document))
            with self.assertRaises(B15M.CapacityRefused) as caught:
                B15M.verify_preregistration(altered)
            self.assertIn("pinned", str(caught.exception))

    def test_an_unreadable_freeze_refuses(self):
        with self.assertRaises(B15M.CapacityRefused) as caught:
            B15M.verify_preregistration(ROOT / "research" / "absent.json")
        self.assertIn("cannot read", str(caught.exception))

    def test_no_execution_surface(self):
        self.assertTrue(B15M.assert_no_execution_surface())

    def test_an_execution_surface_is_caught(self):
        with tempfile.TemporaryDirectory() as directory:
            poisoned = pathlib.Path(directory) / "poisoned.py"
            poisoned.write_text("STATUS_LOCK_KEYS = ()\nx = 'sendTransaction'\n")
            with self.assertRaises(B15M.CapacityRefused) as caught:
                B15M.assert_no_execution_surface(poisoned)
            self.assertIn("sendTransaction", str(caught.exception))

    def test_the_universe_and_inputs_match_b15l(self):
        mine = B15M.verify_preregistration()["frozen_inputs_unchanged"]
        theirs = B15L.verify_preregistration()[
            "frozen_inputs_taken_from_earlier_freezes_unchanged"]
        self.assertEqual(mine["entry_delays_slots"], theirs["entry_delays_slots"])
        self.assertEqual(mine["exit_horizons"], theirs["exit_horizons"])
        self.assertEqual(mine["capacity_search_upper_bound_lamports"],
                         theirs["position_lamports"])
        keys = ("scenario_id", "base_fee_lamports", "priority_fee_lamports", "tip_lamports",
                "ata_rent_lamports", "failed_attempts")
        for a, b in zip(mine["cost_scenarios"], theirs["cost_scenarios"]):
            self.assertEqual({k: a[k] for k in keys}, {k: b[k] for k in keys})

    def test_a_field_named_after_a_return_or_a_recommendation_is_refused(self):
        for word in ("return", "profit", "expected_value", "optimal", "recommended", "best"):
            with self.subTest(word=word):
                with self.assertRaises(B15M.CapacityRefused) as caught:
                    B15M.assert_no_forbidden_words({f"the_{word}_size": 1})
                self.assertIn("not a return and not a recommendation", str(caught.exception))

    def test_the_status_locks_are_exempt(self):
        self.assertTrue(B15M.assert_no_forbidden_words(
            {"performance_status": "not_evaluated", "execution_status": "never_executed"}))


class TestResolutionFloor(unittest.TestCase):
    """The reason the admissible set is not a prefix of [0, ceiling], and it is not liquidity."""

    def test_a_one_lamport_buy_acquires_nothing_at_any_reserves(self):
        for virtual_quote, virtual_token in ((30_000_000_000, 1_073_000_000_000_000),
                                             (1_000, 1_000_000), (10 ** 12, 10 ** 15)):
            with self.subTest(virtual_quote=virtual_quote):
                self.assertEqual(
                    B9I.tokens_out_for_exact_quote_in(virtual_quote, virtual_token, 1), 0)

    def test_the_floor_is_the_smallest_input_acquiring_a_token(self):
        entry = entry_state()
        floor = B15M.minimum_effective_quote(entry, CEILING)
        self.assertGreaterEqual(B15M.tokens_for(entry, floor), 1)
        self.assertEqual(B15M.tokens_for(entry, floor - 1), 0)

    def test_the_floor_is_none_when_even_the_ceiling_buys_nothing(self):
        # A valid curve so thin that 0.1 SOL still rounds to zero tokens. virtual_token=0 would be
        # an IMPOSSIBLE curve and is refused elsewhere; this is a possible one that buys nothing.
        entry = entry_state(virtual_token=1, virtual_quote=10 ** 18)
        self.assertIsNone(B15M.minimum_effective_quote(entry, CEILING))

    def test_capacity_is_zero_when_nothing_can_be_acquired(self):
        entry = entry_state(virtual_token=1, virtual_quote=10 ** 18)
        self.assertEqual(B15M.external_capacity(entry, exit_state(), CEILING), 0)

    def test_the_prefix_shape_holds_above_the_floor(self):
        self.assertTrue(B15M.assert_prefix_shape(entry_state(), exit_state(real_quote=1_000_000),
                                                 3000))

    def test_a_wrong_floor_is_caught(self):
        """The floor must actually be the floor: everything below it acquires zero tokens."""
        entry = entry_state()
        original = B15M.minimum_effective_quote
        try:
            B15M.minimum_effective_quote = lambda _entry, _ceiling: 500
            with self.assertRaises(B15M.CapacityRefused) as caught:
                B15M.assert_prefix_shape(entry, exit_state(), 1000)
            self.assertIn(B15M.M_NON_MONOTONE, str(caught.exception))
            self.assertIn("the floor is wrong", str(caught.exception))
        finally:
            B15M.minimum_effective_quote = original

    def test_a_non_contiguous_admissible_set_above_the_floor_is_caught(self):
        entry = entry_state()
        original = B15M.is_payable
        try:
            # Payable only at even inputs: a set no bisection could search correctly. The PAYABILITY
            # half is what must be a prefix; full admissibility is an interval by construction.
            B15M.is_payable = lambda _e, _x, quote_in: quote_in % 2 == 0
            with self.assertRaises(B15M.CapacityRefused) as caught:
                B15M.assert_prefix_shape(entry, exit_state(), 100)
            self.assertIn(B15M.M_NON_MONOTONE, str(caught.exception))
            self.assertIn("not a contiguous run", str(caught.exception))
        finally:
            B15M.is_payable = original


class TestWorthSomethingBound(unittest.TestCase):
    """B10b's rule, adopted: a size that cannot be sold for one lamport is not liquidity."""

    def test_an_empty_book_reports_zero_not_a_token_sized_capacity(self):
        entry = entry_state()
        empty = exit_state(real_quote=0, virtual_quote=entry["virtual_quote"],
                          virtual_token=entry["virtual_token"], real_token=entry["real_token"])
        # Payable, because selling a handful of tokens draws exactly nothing.
        self.assertTrue(B15M.is_payable(entry, empty, 2))
        self.assertEqual(B15M.gross_draw(entry, empty, 2), 0)
        # And therefore not admissible, and the capacity is zero.
        self.assertFalse(B15M.is_admissible(entry, empty, 2))
        self.assertEqual(B15M.external_capacity(entry, empty, CEILING), 0)

    def test_payability_and_admissibility_differ_only_by_that_bound(self):
        entry, exit_ = entry_state(), exit_state(real_quote=1_000_000)
        for quote_in in (2, 100, 10_000, 1_000_000):
            with self.subTest(quote_in=quote_in):
                payable = B15M.is_payable(entry, exit_, quote_in)
                worth = B15M.gross_draw(entry, exit_, quote_in) >= 1
                self.assertEqual(B15M.is_admissible(entry, exit_, quote_in), payable and worth)

    def test_the_gross_draw_is_non_decreasing(self):
        entry, exit_ = entry_state(), exit_state(real_quote=10 ** 12)
        previous = -1
        for quote_in in range(0, 5000, 37):
            draw = B15M.gross_draw(entry, exit_, quote_in)
            self.assertGreaterEqual(draw, previous)
            previous = draw

    def test_the_zero_gross_rule_matches_b10b(self):
        """B10b returns L1M_NO_EXECUTABLE_SIZE for a zero gross; this study returns zero capacity."""
        entry = entry_state()
        empty = exit_state(real_quote=0, virtual_quote=entry["virtual_quote"],
                          virtual_token=entry["virtual_token"], real_token=entry["real_token"])
        marked = B10B.mark_to_exit(
            {**{k: empty[k] for k in ("virtual_quote", "virtual_token", "real_quote", "real_token",
                                      "quote_mint", "mayhem_mode", "complete")},
             "slot": empty["context_slot"]},
            B15M.tokens_for(entry, CEILING), SCHEDULE, POLICY)
        self.assertEqual(marked["liquidity"], B10B.L1M_NO_EXECUTABLE_SIZE)
        self.assertEqual(B15M.external_capacity(entry, empty, CEILING), 0)


class TestCapacitySearch(unittest.TestCase):
    def test_the_capacity_satisfies_its_own_constraints(self):
        entry, exit_ = entry_state(), exit_state(real_quote=1_000_000)
        capacity = B15M.external_capacity(entry, exit_, CEILING)
        self.assertTrue(B15M.is_admissible(entry, exit_, capacity))

    def test_the_capacity_is_maximal(self):
        entry, exit_ = entry_state(), exit_state(real_quote=1_000_000)
        capacity = B15M.external_capacity(entry, exit_, CEILING)
        self.assertLess(capacity, CEILING)
        self.assertFalse(B15M.is_admissible(entry, exit_, capacity + 1))

    def test_the_capacity_matches_a_brute_force_scan_on_a_small_ceiling(self):
        entry, exit_ = entry_state(), exit_state(real_quote=100)
        ceiling = 4000
        expected = max(q for q in range(0, ceiling + 1)
                       if B15M.is_admissible(entry, exit_, q))
        self.assertEqual(B15M.external_capacity(entry, exit_, ceiling), expected)

    def test_a_deep_book_hits_the_ceiling_and_is_reported_as_such(self):
        entry, exit_ = entry_state(), exit_state(real_quote=10 ** 15, virtual_quote=10 ** 14)
        self.assertEqual(B15M.external_capacity(entry, exit_, CEILING), CEILING)

    def test_a_book_with_no_quote_has_zero_capacity(self):
        entry, exit_ = entry_state(), exit_state(real_quote=0)
        self.assertEqual(B15M.external_capacity(entry, exit_, CEILING), 0)

    def test_an_answer_one_short_of_the_maximum_is_refused(self):
        """Off-by-one from below. The guard is a named function precisely so this is reachable."""
        entry, exit_ = entry_state(), exit_state(real_quote=1_000_000)
        capacity = B15M.external_capacity(entry, exit_, CEILING)
        with self.assertRaises(B15M.CapacityRefused) as caught:
            B15M.assert_maximal(entry, exit_, capacity - 1, CEILING)
        self.assertIn(B15M.M_MAXIMALITY_UNPROVEN, str(caught.exception))

    def test_an_answer_one_past_the_maximum_is_refused(self):
        """Off-by-one from above: proceeds no counterparty could pay."""
        entry, exit_ = entry_state(), exit_state(real_quote=1_000_000)
        capacity = B15M.external_capacity(entry, exit_, CEILING)
        with self.assertRaises(B15M.CapacityRefused) as caught:
            B15M.assert_maximal(entry, exit_, capacity + 1, CEILING)
        self.assertIn(B15M.M_CONSTRAINT_VIOLATED, str(caught.exception))

    def test_the_true_maximum_passes_the_guard(self):
        entry, exit_ = entry_state(), exit_state(real_quote=1_000_000)
        capacity = B15M.external_capacity(entry, exit_, CEILING)
        self.assertTrue(B15M.assert_maximal(entry, exit_, capacity, CEILING))

    def test_a_cap_hit_answer_is_not_asked_to_prove_the_next_integer(self):
        """At the ceiling there is no next integer to test, and the guard must not invent one."""
        entry, exit_ = entry_state(), exit_state(real_quote=10 ** 15, virtual_quote=10 ** 14)
        self.assertTrue(B15M.assert_maximal(entry, exit_, CEILING, CEILING))

    def test_impossible_reserves_refuse(self):
        for label, state in (("entry", entry_state(virtual_quote=0)),
                             ("exit", exit_state(virtual_token=0))):
            with self.subTest(label=label):
                entry = state if label == "entry" else entry_state()
                exit_ = state if label == "exit" else exit_state()
                with self.assertRaises(B15M.CapacityRefused) as caught:
                    B15M.external_capacity(entry, exit_, CEILING)
                self.assertIn(B15M.M_IMPOSSIBLE_RESERVES, str(caught.exception))

    def test_negative_real_reserves_refuse(self):
        with self.assertRaises(B15M.CapacityRefused) as caught:
            B15M.external_capacity(entry_state(real_token=-1), exit_state(), CEILING)
        self.assertIn(B15M.M_IMPOSSIBLE_RESERVES, str(caught.exception))

    def test_a_float_reserve_refuses(self):
        with self.assertRaises(B15M.CapacityRefused) as caught:
            B15M.external_capacity(entry_state(real_quote=1.5), exit_state(), CEILING)
        self.assertIn(B15M.M_FLOAT_PRESENT, str(caught.exception))

    def test_the_entry_token_reserve_binds_as_well_as_the_exit_quote(self):
        """Both constraints matter: a curve with almost no tokens caps the input too."""
        entry = entry_state(real_token=1)
        deep = exit_state(real_quote=10 ** 15, virtual_quote=10 ** 14)
        capacity = B15M.external_capacity(entry, deep, CEILING)
        self.assertLess(capacity, CEILING)
        self.assertLessEqual(B15M.tokens_for(entry, capacity), 1)


class TestDifferentialAgainstB10b(unittest.TestCase):
    """The two routes must agree because they are the same condition, not because they usually do."""

    def test_the_routes_agree_across_a_range_of_books(self):
        for real_quote in (0, 1, 100, 10_000, 1_000_000, 100_000_000, 10 ** 12):
            with self.subTest(real_quote=real_quote):
                entry, exit_ = entry_state(), exit_state(real_quote=real_quote)
                self.assertEqual(B15M.external_capacity(entry, exit_, CEILING),
                                 B15M.capacity_via_b10b(entry, exit_, CEILING))

    def test_the_routes_agree_when_the_entry_token_reserve_binds(self):
        for real_token in (1, 1_000, 10 ** 9):
            with self.subTest(real_token=real_token):
                entry = entry_state(real_token=real_token)
                exit_ = exit_state(real_quote=10 ** 14, virtual_quote=10 ** 13)
                self.assertEqual(B15M.external_capacity(entry, exit_, CEILING),
                                 B15M.capacity_via_b10b(entry, exit_, CEILING))

    def test_b10b_token_maximum_is_the_same_condition_as_payability(self):
        """The theorem the differential test rests on, checked directly."""
        exit_ = exit_state(real_quote=1_000_000)
        token_cap, _gross = B10B.max_executable_tokens(
            exit_["virtual_quote"], exit_["virtual_token"], exit_["real_quote"], 10 ** 15)
        for tokens in (0, 1, token_cap - 1, token_cap, token_cap + 1, token_cap * 2):
            if tokens < 0:
                continue
            with self.subTest(tokens=tokens):
                draw = B9I.quote_out_for_tokens_in(
                    exit_["virtual_quote"], exit_["virtual_token"], tokens)
                self.assertEqual(draw <= exit_["real_quote"], tokens <= token_cap)


class TestGrid(unittest.TestCase):
    def test_an_executable_size_reports_exact_proceeds_and_costs(self):
        entry, exit_ = entry_state(), exit_state(real_quote=10 ** 12, virtual_quote=10 ** 11)
        row = B15M.grid_row(entry, exit_, 1_000_000, SCHEDULE, POLICY)
        self.assertTrue(row["liquidity_executable"])
        self.assertEqual(row["tokens_acquired"], B15M.tokens_for(entry, 1_000_000))
        self.assertIsInstance(row["net_after_costs_lamports"], int)
        self.assertEqual(row["non_negative"], row["net_after_costs_lamports"] >= 0)

    def test_an_unexecutable_size_reports_no_proceeds_rather_than_zero(self):
        entry, exit_ = entry_state(), exit_state(real_quote=0)
        row = B15M.grid_row(entry, exit_, 100_000_000, SCHEDULE, POLICY)
        self.assertFalse(row["liquidity_executable"])
        self.assertIsNone(row["gross_exit_lamports"])
        self.assertIsNone(row["net_after_costs_lamports"])
        self.assertIsNone(row["non_negative"])

    def test_a_negative_net_is_reported_not_clamped(self):
        # Exit reserves equal to entry's, so the curve did not run up and the round trip is pure
        # cost. The ATA rent alone exceeds a 0.001 SOL position.
        entry = entry_state()
        flat = exit_state(virtual_quote=entry["virtual_quote"],
                         virtual_token=entry["virtual_token"],
                         real_quote=10 ** 12, real_token=entry["real_token"])
        row = B15M.grid_row(entry, flat, 1_000_000, SCHEDULE, POLICY)
        self.assertTrue(row["liquidity_executable"])
        self.assertLess(row["net_after_costs_lamports"], 0)
        self.assertFalse(row["non_negative"])

    def test_every_grid_size_is_an_exact_integer(self):
        grid = B15M.verify_preregistration()[
            "secondary_estimand_separately_named"]["grid_lamports"]
        for size in grid:
            self.assertIsInstance(size, int)
        self.assertEqual(grid, sorted(grid))
        self.assertEqual(grid[-1], CEILING)

    def test_a_disagreement_between_the_predicate_and_b10a_stops_the_run(self):
        entry, exit_ = entry_state(), exit_state(real_quote=10 ** 12, virtual_quote=10 ** 11)
        original = B15M.is_admissible
        try:
            B15M.is_admissible = lambda *_args: True      # claim a complete curve is payable
            with self.assertRaises(B15M.CapacityRefused) as caught:
                B15M.grid_row(entry, exit_state(complete=True, real_quote=10 ** 12),
                              1_000_000, SCHEDULE, POLICY)
            self.assertIn(B15M.M_DIFFERENTIAL_DISAGREEMENT, str(caught.exception))
        finally:
            B15M.is_admissible = original


class TestOrderStatistics(unittest.TestCase):
    def test_the_statistics_are_exact_integers_by_index(self):
        values = list(range(1, 11))
        stats = B15M.order_statistics(values)
        self.assertEqual(stats["min"], 1)
        self.assertEqual(stats["max"], 10)
        self.assertEqual(stats["median"], values[(10 - 1) * 1 // 2])
        for key, value in stats.items():
            self.assertIsInstance(value, int, key)

    def test_no_mean_is_published(self):
        stats = B15M.order_statistics([1, 2, 3])
        for banned in ("mean", "average", "expected"):
            self.assertNotIn(banned, json.dumps(stats).lower())

    def test_an_empty_set_yields_none_not_zero(self):
        self.assertIsNone(B15M.order_statistics([]))


class TestCircularDependence(unittest.TestCase):
    def test_a_self_funded_exit_is_detected(self):
        """The observed book holds nothing, but our own buy would have funded the sale."""
        entry = entry_state()
        exit_ = exit_state(real_quote=0, virtual_quote=entry["virtual_quote"],
                           virtual_token=entry["virtual_token"],
                           real_token=entry["real_token"])
        self.assertEqual(B15M.external_capacity(entry, exit_, CEILING), 0)
        self.assertTrue(B15M.self_contributed_exit_payable(entry, exit_, CEILING))

    def test_a_book_with_liquidity_is_not_circular(self):
        entry, exit_ = entry_state(), exit_state(real_quote=10 ** 12, virtual_quote=10 ** 11)
        self.assertGreater(B15M.external_capacity(entry, exit_, CEILING), 0)

    def test_the_check_takes_no_cost_policy(self):
        """Payability is a reserve question, so no fee or priority assumption can enter it.

        Checked on the SIGNATURE, not the source: an earlier version grepped the body and tripped on
        the docstring that explains why the policy is absent.
        """
        import inspect
        parameters = set(inspect.signature(B15M.self_contributed_exit_payable).parameters)
        self.assertEqual(parameters, {"entry", "exit_state", "position_lamports"})


class TestStudyRun(unittest.TestCase):
    def _inputs(self, real_quote=10 ** 12, virtual_quote=10 ** 11):
        entries, exits, schedules = {}, {}, {}
        for index in range(3):
            signature = f"Sig{index}"
            schedules[signature] = SCHEDULE
            for delay in (1, 2, 4):
                entries[(signature, delay)] = entry_state(
                    signature=signature, delay_slots=delay,
                    bonding_curve=f"C{index}", mint=f"M{index}")
                for horizon in ("h_1000_slots", "h_10000_slots"):
                    exits[(signature, delay, horizon)] = exit_state(
                        signature=signature, delay_slots=delay, horizon=horizon,
                        bonding_curve=f"C{index}", mint=f"M{index}",
                        real_quote=real_quote, virtual_quote=virtual_quote)
        return entries, exits, schedules

    def test_capacity_is_reported_per_horizon_and_delay(self):
        entries, exits, schedules = self._inputs()
        report = B15M.run(entries=entries, exits=exits, schedules=schedules)
        self.assertEqual(len(report["capacity_by_horizon_delay"]), 2 * 3)
        for key, group in report["capacity_by_horizon_delay"].items():
            self.assertEqual(group["cells"], 3, key)
            self.assertIsNotNone(group["external_liquidity_capacity_lamports"])
            self.assertIsNotNone(group["curve_resolution_floor_lamports"])

    def test_the_grid_is_reported_per_scenario_horizon_and_delay(self):
        entries, exits, schedules = self._inputs()
        report = B15M.run(entries=entries, exits=exits, schedules=schedules)
        self.assertEqual(len(report["grid_by_scenario_horizon_delay"]), 3 * 2 * 3)
        for group in report["grid_by_scenario_horizon_delay"].values():
            self.assertEqual(len(group["by_size"]), 7)

    def test_the_report_carries_every_required_label(self):
        entries, exits, schedules = self._inputs()
        report = B15M.run(entries=entries, exits=exits, schedules=schedules)
        self.assertEqual(report["label"], "LIQUIDITY_CAPACITY_DIAGNOSTIC")
        self.assertFalse(report["executable"])
        self.assertEqual(report["landing_probability"], "unmeasured")
        self.assertEqual(report["competitor_response"], "unmeasured")
        self.assertEqual(report["performance_status"], "not_evaluated")
        self.assertEqual(report["execution_status"], "never_executed")
        self.assertIn("censored by the recorders", report["censoring_statement"])

    def test_nothing_is_aggregated_across_horizons_or_scenarios(self):
        entries, exits, schedules = self._inputs()
        report = B15M.run(entries=entries, exits=exits, schedules=schedules)
        for key in report["capacity_by_horizon_delay"]:
            self.assertEqual(len(key.split("|")), 2)
        for key in report["grid_by_scenario_horizon_delay"]:
            self.assertEqual(len(key.split("|")), 3)
        self.assertNotIn("total", report)
        self.assertNotIn("all_horizons", report)

    def test_a_cell_outside_the_b15l_universe_is_refused_and_counted(self):
        entries, exits, schedules = self._inputs()
        del entries[("Sig0", 1)]
        report = B15M.run(entries=entries, exits=exits, schedules=schedules)
        self.assertEqual(report["refusals"][B15M.M_NOT_IN_B15L_UNIVERSE], 2)

    def test_a_mayhem_cell_is_refused_by_b15ls_own_gate(self):
        entries, exits, schedules = self._inputs()
        exits[("Sig0", 1, "h_1000_slots")] = exit_state(
            signature="Sig0", delay_slots=1, horizon="h_1000_slots",
            bonding_curve="C0", mint="M0", mayhem_mode=True)
        report = B15M.run(entries=entries, exits=exits, schedules=schedules)
        self.assertGreaterEqual(report["refusals"][B15M.M_NOT_IN_B15L_UNIVERSE], 1)

    def test_the_result_is_identical_under_row_permutation(self):
        entries, exits, schedules = self._inputs()
        first = B15M.run(entries=entries, exits=exits, schedules=schedules)
        second = B15M.run(
            entries=dict(random.Random(1).sample(list(entries.items()), len(entries))),
            exits=dict(random.Random(2).sample(list(exits.items()), len(exits))),
            schedules=dict(random.Random(3).sample(list(schedules.items()), len(schedules))))
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_the_run_is_deterministic_when_repeated(self):
        entries, exits, schedules = self._inputs()
        one = B15M.run(entries=entries, exits=exits, schedules=schedules)
        two = B15M.run(entries=entries, exits=exits, schedules=schedules)
        self.assertEqual(json.dumps(one, sort_keys=True), json.dumps(two, sort_keys=True))

    def test_a_zero_liquidity_book_reports_zero_capacity_not_a_refusal(self):
        entries, exits, schedules = self._inputs(real_quote=0, virtual_quote=10 ** 11)
        report = B15M.run(entries=entries, exits=exits, schedules=schedules)
        for group in report["capacity_by_horizon_delay"].values():
            self.assertEqual(group["zero_capacity_cells"], group["cells"])
            self.assertEqual(group["external_liquidity_capacity_lamports"]["max"], 0)

    def test_the_differential_check_runs_by_default(self):
        entries, exits, schedules = self._inputs()
        original = B15M.capacity_via_b10b
        try:
            B15M.capacity_via_b10b = lambda *_args: -1     # forced disagreement
            report = B15M.run(entries=entries, exits=exits, schedules=schedules)
            self.assertGreater(report["refusals"][B15M.M_DIFFERENTIAL_DISAGREEMENT], 0)
        finally:
            B15M.capacity_via_b10b = original

    def test_the_real_artifacts_load_and_the_universe_is_not_empty(self):
        entries = B15L.load_entries()
        exits = B15L.load_exits()
        self.assertGreater(len(entries), 0)
        self.assertGreater(len(exits), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
