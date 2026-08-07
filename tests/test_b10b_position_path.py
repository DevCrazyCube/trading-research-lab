"""B10b — the canonical observed-state position path evaluator.

Every fixture here exists to kill a specific mutation, because each mutation is a way this kind of
engine reports a number nobody could have realised: the future reaching the entry decision, an
ordering that is really insertion order, a foreign mint's states pasted into a path, arithmetic that
shrugs at a lamport, an exit priced against a curve that has stopped trading, a loss clamped to
zero, and a horizon the data never reached being scored as an outcome.
"""
import copy
import importlib.util
import json
import pathlib
import sqlite3
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Loaded through the dataset module rather than separately. Loading each by path would produce TWO
# distinct `b10b_position_path` module objects, so `PathRefused` raised inside the dataset layer
# would not be the `PathRefused` this file catches — the test would report a failure that is really
# an artefact of how the test loaded its subject.
DATASET = _load("b10b_path_dataset", "b10b_path_dataset.py")
B10B = DATASET.B10B
B10A = B10B.B10A
B9I = B10B.B9I
NATIVE = B10B.B9D.NATIVE_QUOTE_MINT

MINT = "MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
OTHER_MINT = "MintBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"

# The fee schedule is deliberately chosen so the protocol fee on the fixture's exits is ODD. At
# 5,000 buyback basis points floor and ceil agree on every EVEN fee, so an even-fee fixture cannot
# tell the two roundings apart — a trap this project has now walked into twice.
SCHEDULE = {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0, "buyback_fee_bps": 5000}
POLICY = {"base_fee_lamports": 5_000, "priority_fee_lamports": 100_000, "tip_lamports": 0,
          "ata_rent_lamports": 2_039_280, "failed_attempts": 0}
ORDER = {"side": B10A.BUY, "quote_lamports": 100_000_000}

LAUNCH_VQ, LAUNCH_VT = 30_000_000_000, 1_073_000_000_000_000
LAUNCH_RT = 793_100_000_000_000


def observation(slot, transaction_index=0, outer_index=0, inner_index=-1, *, mint=MINT,
                virtual_quote=LAUNCH_VQ, virtual_token=LAUNCH_VT, real_quote=5_000_000_000,
                real_token=LAUNCH_RT, complete=False, mayhem_mode=False, quote_mint=NATIVE,
                is_transaction_terminal=True):
    return {"slot": slot, "transaction_index": transaction_index, "outer_index": outer_index,
            "inner_index": inner_index, "mint": mint, "virtual_quote": virtual_quote,
            "virtual_token": virtual_token, "real_quote": real_quote, "real_token": real_token,
            "quote_mint": quote_mint, "mayhem_mode": mayhem_mode, "complete": complete,
            "is_transaction_terminal": is_transaction_terminal}


def t0_state(**overrides):
    base = observation(700, real_quote=1_000_000_000)
    base.update(overrides)
    return base


def evaluate(path, **kwargs):
    kwargs.setdefault("order", ORDER)
    kwargs.setdefault("mint", MINT)
    return B10B.evaluate_position_path(
        kwargs.pop("t0", t0_state()), path, SCHEDULE, POLICY, **kwargs)


def tokens_bought():
    return B9I.tokens_out_for_exact_quote_in(LAUNCH_VQ, LAUNCH_VT, ORDER["quote_lamports"])


class LeakageTests(unittest.TestCase):
    """The future must be unable to reach the entry decision. Structurally, not by promise."""

    def test_decide_entry_has_no_parameter_a_path_could_arrive_through(self):
        """The boundary is the signature. A later author cannot pass the path without changing
        this function and this test together, which is the point of making it structural."""
        import inspect
        parameters = set(inspect.signature(B10B.decide_entry).parameters)
        self.assertEqual(parameters, {"t0_state", "schedule", "cost_policy", "order",
                                      "entry_policy"})
        for forbidden in ("observations", "path", "future", "marks", "exit_state"):
            self.assertNotIn(forbidden, parameters)

    def test_no_observation_is_reachable_from_the_entry_feature_view(self):
        """Reference-graph reachability, not inspection of the field names. A container smuggled
        into the view would be found however it was named."""
        path = [observation(800), observation(900)]
        view = B10B.entry_feature_view(t0_state(), path)
        reachable = B10B._reachable_object_ids(view, keep=True)
        self.assertFalse({id(o) for o in path} & set(reachable))
        for obj in reachable.values():
            self.assertIsInstance(obj, B10B.ALLOWED_VIEW_TYPES)

    def test_a_container_in_the_view_is_refused_even_when_it_holds_nothing_future(self):
        """The rule is on the shape, not on the contents. A list that happens to be empty today is
        a route that is not empty tomorrow."""
        leaky = t0_state()
        leaky["slot"] = [700]
        with self.assertRaisesRegex(B10B.PathRefused, "only scalars may cross"):
            B10B.entry_feature_view(leaky)

    def test_an_observation_reachable_by_identity_is_caught_even_when_it_is_a_bare_mapping(self):
        """A dict passes the shape check — it is an allowed type — so the identity check is the
        one that has to catch a future observation smuggled in as a plain mapping. Both checks
        exist because neither alone covers the other's case."""
        path = [observation(800)]
        nested = types.MappingProxyType({"slot": 700, "future": path[0]})
        self.assertTrue(B10B.assert_no_future_reachable(nested))
        with self.assertRaisesRegex(B10B.PathRefused, "reachable from the entry feature view"):
            B10B.assert_no_future_reachable(nested, path)

    def test_a_deeply_buried_observation_is_still_found(self):
        path = [observation(800)]
        buried = types.MappingProxyType({"a": {"b": {"c": path[0]}}})
        with self.assertRaisesRegex(B10B.PathRefused, "reachable from the entry feature view"):
            B10B.assert_no_future_reachable(buried, path)

    def test_the_reachability_walk_refuses_to_truncate(self):
        """A truncated walk would report "no leak found" for the graph it did not finish looking
        at, which is the failure mode worth refusing rather than capping quietly."""
        with self.assertRaisesRegex(B10B.PathRefused, "reaches more than"):
            B10B._reachable_object_ids({str(i): i for i in range(50)}, limit=10)

    def test_the_policy_receives_the_frozen_view_and_not_the_decision_state_itself(self):
        """It is not enough that a safe view CAN be built; `decide_entry` must be the thing that
        hands it over. Passing the raw t0 mapping instead would give a policy a mutable object
        carrying every field the caller happened to attach — here, `mint` and the terminality flag
        — and nothing would notice."""
        received = []

        def policy(view):
            received.append(view)
            return dict(ORDER)

        B10B.decide_entry(t0_state(), SCHEDULE, POLICY, entry_policy=policy)
        self.assertEqual(len(received), 1)
        self.assertIsInstance(received[0], types.MappingProxyType)
        self.assertEqual(set(received[0]), set(B10B.ENTRY_FEATURE_FIELDS))
        self.assertNotIn("mint", received[0])
        self.assertNotIn("is_transaction_terminal", received[0])
        with self.assertRaises(TypeError):
            received[0]["slot"] = 1

    def test_the_view_is_immutable(self):
        view = B10B.entry_feature_view(t0_state())
        with self.assertRaises(TypeError):
            view["slot"] = 1

    def test_the_view_exposes_exactly_the_declared_decision_time_fields(self):
        view = B10B.entry_feature_view(t0_state())
        self.assertEqual(set(view), set(B10B.ENTRY_FEATURE_FIELDS))

    def test_the_entry_is_byte_identical_whether_the_token_moons_or_collapses(self):
        """The strongest available end-to-end statement: two paths that could not differ more
        produce the same entry record, byte for byte."""
        moon = [observation(800, real_quote=80_000_000_000)]
        collapse = [observation(800, real_quote=1)]
        seen = []

        def policy(view):
            seen.append(dict(view))
            return dict(ORDER)

        a = evaluate(moon, order=None, entry_policy=policy)
        b = evaluate(collapse, order=None, entry_policy=policy)
        self.assertEqual(json.dumps(a["entry"], sort_keys=True),
                         json.dumps(b["entry"], sort_keys=True))
        self.assertEqual(seen[0], seen[1])
        self.assertNotEqual(B10B.record_hash(a), B10B.record_hash(b),
                            "the OUTCOMES must differ even though the decision does not")

    def test_stating_both_an_order_and_a_policy_is_refused(self):
        with self.assertRaisesRegex(B10B.PathRefused, "exactly one"):
            B10B.decide_entry(t0_state(), SCHEDULE, POLICY, order=ORDER,
                              entry_policy=lambda view: ORDER)

    def test_stating_neither_an_order_nor_a_policy_is_refused(self):
        with self.assertRaisesRegex(B10B.PathRefused, "exactly one"):
            B10B.decide_entry(t0_state(), SCHEDULE, POLICY)


class CanonicalOrderTests(unittest.TestCase):
    """Insertion order is not an ordering. Neither is a sequence somebody sorted on the way in."""

    def test_a_reversed_sequence_is_refused_rather_than_sorted(self):
        path = [observation(800), observation(900), observation(1000)]
        with self.assertRaisesRegex(B10B.PathRefused, "precedes"):
            evaluate(list(reversed(path)))

    def test_two_observations_swapped_in_the_middle_are_refused(self):
        path = [observation(800), observation(1000), observation(900)]
        with self.assertRaisesRegex(B10B.PathRefused, "precedes"):
            evaluate(path)

    def test_a_duplicate_coordinate_is_refused(self):
        path = [observation(800), observation(800)]
        with self.assertRaisesRegex(B10B.PathRefused, "repeats canonical coordinate"):
            evaluate(path)

    def test_ordering_uses_all_four_coordinates_not_just_the_slot(self):
        """Two observations in the same slot are ordered by transaction, then by instruction. A
        slot-only check would accept this reversal, and this artifact puts several trades in one
        slot constantly."""
        same_slot = [observation(800, transaction_index=5), observation(800, transaction_index=2)]
        with self.assertRaisesRegex(B10B.PathRefused, "precedes"):
            evaluate(same_slot)
        deeper = [observation(800, transaction_index=2, outer_index=4, inner_index=6),
                  observation(800, transaction_index=2, outer_index=4, inner_index=3)]
        with self.assertRaisesRegex(B10B.PathRefused, "precedes"):
            evaluate(deeper)

    def test_an_observation_at_or_before_t0_is_refused_as_leakage(self):
        for slot in (700, 699):
            with self.subTest(slot=slot):
                with self.assertRaisesRegex(B10B.PathRefused, "precedes|repeats"):
                    evaluate([observation(slot)])

    def test_a_missing_coordinate_component_is_refused(self):
        for field in B10B.CANONICAL_ORDER:
            with self.subTest(field=field):
                broken = observation(800)
                del broken[field]
                with self.assertRaisesRegex(B10B.PathRefused, f"no {field}"):
                    evaluate([broken])


class CrossMintTests(unittest.TestCase):

    def test_a_foreign_mint_anywhere_in_the_path_is_refused(self):
        path = [observation(800), observation(900, mint=OTHER_MINT), observation(1000)]
        with self.assertRaisesRegex(B10B.PathRefused, "not 'Mint"):
            evaluate(path)

    def test_a_t0_state_for_a_different_mint_is_refused(self):
        with self.assertRaisesRegex(B10B.PathRefused, "t0 state is for mint"):
            evaluate([observation(800)], t0=t0_state(mint=OTHER_MINT))

    def test_an_observation_with_no_mint_at_all_is_refused(self):
        stripped = observation(800)
        del stripped["mint"]
        with self.assertRaisesRegex(B10B.PathRefused, "is for mint None"):
            evaluate([stripped])


class ExecutableSizeTests(unittest.TestCase):
    """The exit is constrained by what the reserve can pay, and the bound is proven, not assumed."""

    def test_the_executable_size_is_maximal_and_the_next_token_overdraws(self):
        held = tokens_bought()
        size, gross = B10B.max_executable_tokens(LAUNCH_VQ, LAUNCH_VT, 50_000_000, held)
        self.assertLessEqual(gross, 50_000_000)
        self.assertGreater(
            B9I.quote_out_for_tokens_in(LAUNCH_VQ, LAUNCH_VT, size + 1), 50_000_000)
        self.assertEqual(gross, B9I.quote_out_for_tokens_in(LAUNCH_VQ, LAUNCH_VT, size))

    def test_a_reserve_that_can_pay_for_everything_leaves_nothing_unrealizable(self):
        held = tokens_bought()
        size, _ = B10B.max_executable_tokens(LAUNCH_VQ, LAUNCH_VT, 10 ** 15, held)
        self.assertEqual(size, held)

    def test_a_constrained_exit_reports_the_remainder_as_tokens_and_never_values_it(self):
        held = tokens_bought()
        mark = B10B.mark_to_exit(observation(800, real_quote=50_000_000), held, SCHEDULE, POLICY)
        self.assertEqual(mark["liquidity"], B10B.L2_SIZE_CONSTRAINED)
        self.assertLess(mark["tokens_executable"], held)
        self.assertEqual(mark["tokens_executable"] + mark["tokens_unrealizable"], held)
        self.assertLessEqual(mark["gross_exit_lamports"], 50_000_000)

    def test_a_reserve_that_can_pay_nothing_is_the_mechanical_floor_and_costs_nothing(self):
        """`L1m` is the arithmetic floor, not the economic L1 of EXECUTABLE_RETURN.md §3, whose
        threshold is deliberately unfrozen. Nothing can be sold, so no transaction is submitted and
        no fee is charged — an invented cost is the same error as an invented proceed."""
        mark = B10B.mark_to_exit(observation(800, real_quote=0), tokens_bought(), SCHEDULE, POLICY)
        self.assertEqual(mark["liquidity"], B10B.L1M_NO_EXECUTABLE_SIZE)
        self.assertEqual(mark["realizable_net_lamports"], 0)
        self.assertEqual(mark["gross_exit_lamports"], 0)
        self.assertIsNone(mark["execution_costs"])
        self.assertEqual(mark["tokens_unrealizable"], tokens_bought())

    def test_the_size_bound_is_the_real_reserve_not_the_virtual_one(self):
        """A virtual-reserve bound would never bind: the sell formula's output approaches the
        virtual quote reserve asymptotically, so it can never exceed it however large the size."""
        enormous = 10 ** 18
        self.assertLess(B9I.quote_out_for_tokens_in(LAUNCH_VQ, LAUNCH_VT, enormous), LAUNCH_VQ)
        mark = B10B.mark_to_exit(
            observation(800, real_quote=1_000), enormous, SCHEDULE, POLICY)
        self.assertLessEqual(mark["gross_exit_lamports"], 1_000)


class OneLamportTests(unittest.TestCase):
    """An evaluator insensitive to a lamport is not doing integer arithmetic."""

    def test_one_lamport_of_reserve_moves_the_constrained_exit_and_the_hash(self):
        base = evaluate([observation(800, real_quote=50_000_000)])
        moved = evaluate([observation(800, real_quote=50_000_001)])
        self.assertNotEqual(base["marks"][0]["mark"]["tokens_executable"],
                            moved["marks"][0]["mark"]["tokens_executable"])
        self.assertNotEqual(B10B.record_hash(base), B10B.record_hash(moved))

    def test_one_lamport_of_stated_cost_moves_the_realisable_value_by_exactly_one(self):
        """Costs pass through undamped. Note the converse is NOT asserted for reserves: the curve
        formulas floor, so a one-lamport reserve change legitimately need not move a quotient, and
        a test demanding that it must would be pinning a falsehood."""
        full = [observation(800, real_quote=10 ** 15)]
        base = evaluate(full)
        moved = B10B.evaluate_position_path(
            t0_state(), full, SCHEDULE,
            dict(POLICY, priority_fee_lamports=POLICY["priority_fee_lamports"] + 1),
            mint=MINT, order=ORDER)
        self.assertEqual(base["marks"][0]["realizable_net_lamports"] - 1,
                         moved["marks"][0]["realizable_net_lamports"])

    def test_one_lamport_of_order_size_moves_the_entry_and_everything_downstream(self):
        path = [observation(800, real_quote=10 ** 15)]
        base = evaluate(path)
        moved = evaluate(path, order=dict(ORDER, quote_lamports=ORDER["quote_lamports"] + 1))
        self.assertNotEqual(base["entry"]["tokens_out"], moved["entry"]["tokens_out"])
        self.assertNotEqual(base["marks"][0]["realizable_net_lamports"],
                            moved["marks"][0]["realizable_net_lamports"])

    def test_the_fixture_fee_is_odd_so_floor_and_ceil_buyback_cannot_agree(self):
        """At 5,000 basis points floor and ceil agree on every EVEN fee, so an even-fee fixture
        silently certifies the wrong rounding. This project has walked into that twice."""
        mark = B10B.mark_to_exit(
            observation(800, real_quote=10 ** 15), tokens_bought(), SCHEDULE, POLICY)
        self.assertEqual(mark["curve_fees"]["fee"] % 2, 1)


class UnavailableExitTests(unittest.TestCase):

    def test_a_completed_curve_is_structural_unavailability_and_never_a_mark(self):
        result = evaluate([observation(800, complete=True)])
        mark = result["marks"][0]
        self.assertEqual(mark["liquidity"], B10B.L3_STRUCTURAL_UNAVAILABLE)
        self.assertEqual(mark["reason"], B10B.REASON_CURVE_COMPLETE)
        self.assertIsNone(mark["realizable_net_lamports"])
        self.assertFalse(mark["evaluable"])
        self.assertEqual(result["terminal_state"], B10B.TERMINAL_STRUCTURAL_UNAVAILABILITY)

    def test_observations_after_completion_are_dropped_and_counted_not_priced(self):
        path = [observation(800), observation(900, complete=True), observation(1000)]
        result = evaluate(path)
        self.assertEqual(result["observations_dropped_after_completion"], 1)
        self.assertEqual(len(result["marks"]), 2)

    def test_a_rule_that_never_fired_before_completion_is_unavailable_not_censored(self):
        path = [observation(800, real_quote=1), observation(900, complete=True)]
        result = evaluate(path, exit_rules=[
            {"name": "full", "kind": B10B.RULE_FIRST_FULL_SIZE_EXIT}])
        self.assertEqual(result["exit_rules"][0]["outcome"], B10B.RULE_STRUCTURALLY_UNAVAILABLE)

    def test_an_exit_is_never_priced_inside_another_partys_transaction(self):
        """Our exit is its own transaction and cannot land inside somebody else's, so a state that
        exists only part-way through one is not a state we could have traded against."""
        path = [observation(800, outer_index=1, is_transaction_terminal=False),
                observation(800, outer_index=2)]
        result = evaluate(path)
        self.assertEqual(result["marks"][0]["reason"], B10B.REASON_INTRA_TRANSACTION)
        self.assertFalse(result["marks"][0]["evaluable"])
        self.assertIsNone(result["marks"][0]["mark"])
        self.assertTrue(result["marks"][1]["evaluable"])

    def test_entry_into_an_already_complete_t0_is_refused(self):
        with self.assertRaisesRegex(B10A.SimulationRefused, "already complete"):
            evaluate([observation(800)], t0=t0_state(complete=True))


class NegativeValueTests(unittest.TestCase):

    def test_a_net_below_zero_is_reported_and_never_clamped(self):
        """The case that matters most on a small position. Clamping to zero would hide it."""
        mark = B10B.mark_to_exit(observation(800, real_quote=50_000), tokens_bought(),
                                 SCHEDULE, POLICY)
        self.assertLess(mark["realizable_net_lamports"], 0)
        self.assertEqual(
            mark["realizable_net_lamports"],
            mark["gross_exit_lamports"] - mark["curve_fees"]["charged_total"]
            - mark["execution_costs"]["total"])

    def test_the_round_trip_net_is_reported_against_the_entry_outlay(self):
        result = evaluate([observation(800, real_quote=50_000)])
        mark = result["marks"][0]
        self.assertEqual(
            mark["net_versus_entry_lamports"],
            mark["realizable_net_lamports"] - result["entry"]["lamports_out_of_wallet"])
        self.assertLess(mark["net_versus_entry_lamports"], 0)

    def test_a_negative_value_path_still_produces_a_defined_drawdown_in_lamports(self):
        path = [observation(800, real_quote=10 ** 15), observation(900, real_quote=50_000)]
        drawdown = evaluate(path)["drawdown"]
        self.assertGreater(drawdown["max_drawdown_lamports"], 0)
        self.assertEqual(drawdown["max_drawdown_lamports"],
                         drawdown["max_drawdown_peak_lamports"] - drawdown["trough_lamports"])

    def test_a_ratio_is_withheld_when_the_peak_was_never_positive(self):
        """A drawdown ratio against a peak of zero or less is undefined, not small. Reporting 0.0
        or infinity there would invent a figure for a position that never had value to lose."""
        path = [observation(800, real_quote=50_000), observation(900, real_quote=40_000)]
        drawdown = evaluate(path)["drawdown"]
        self.assertLess(drawdown["peak_lamports"], 0)
        self.assertIsNone(drawdown["max_drawdown_ratio_numerator"])
        self.assertIsNone(drawdown["max_drawdown_ratio_denominator"])


class DrawdownTests(unittest.TestCase):

    def test_the_drawdown_is_peak_to_trough_on_the_realisable_net_value_path(self):
        path = [observation(800, real_quote=200_000_000),
                observation(900, real_quote=10 ** 15),
                observation(1000, real_quote=300_000_000),
                observation(1100, real_quote=900_000_000)]
        result = evaluate(path)
        values = [mark["realizable_net_lamports"] for mark in result["marks"]]
        peak, worst, worst_peak = None, 0, None
        for value in values:
            peak = value if peak is None or value > peak else peak
            if peak - value > worst:
                worst, worst_peak = peak - value, peak
        self.assertEqual(result["drawdown"]["max_drawdown_lamports"], worst)
        self.assertEqual(result["drawdown"]["max_drawdown_peak_lamports"], worst_peak)
        self.assertEqual(result["drawdown"]["peak_lamports"], max(values))
        self.assertEqual(result["drawdown"]["series"], "realizable_net_exit_value")

    def test_the_running_peak_never_falls(self):
        path = [observation(800 + 100 * i, real_quote=quote) for i, quote in
                enumerate((10 ** 15, 200_000_000, 900_000_000, 100_000_000))]
        peaks = [mark["running_peak_lamports"] for mark in evaluate(path)["marks"]]
        self.assertEqual(peaks, sorted(peaks))

    def test_the_ratio_is_an_exact_integer_pair_and_never_a_float(self):
        path = [observation(800, real_quote=10 ** 15), observation(900, real_quote=50_000_000)]
        drawdown = evaluate(path)["drawdown"]
        self.assertIsInstance(drawdown["max_drawdown_ratio_numerator"], int)
        self.assertIsInstance(drawdown["max_drawdown_ratio_denominator"], int)
        self.assertGreater(drawdown["max_drawdown_ratio_denominator"], 0)

    def test_unevaluable_marks_do_not_enter_the_value_path(self):
        path = [observation(800, real_quote=10 ** 15),
                observation(900, outer_index=1, is_transaction_terminal=False),
                observation(1000, real_quote=200_000_000)]
        result = evaluate(path)
        self.assertEqual(result["drawdown"]["evaluable_points"], 2)
        self.assertIsNone(result["marks"][1]["running_peak_lamports"])


class RightCensoringTests(unittest.TestCase):
    """A horizon the observation window never reached is censored, never scored."""

    def test_a_slot_horizon_beyond_the_last_observation_is_right_censored(self):
        result = evaluate([observation(800), observation(900)], exit_rules=[
            {"name": "far", "kind": B10B.RULE_SLOT_HORIZON, "slots": 1_000_000}])
        rule = result["exit_rules"][0]
        self.assertEqual(rule["outcome"], B10B.RULE_RIGHT_CENSORED)
        self.assertIsNone(rule["realizable_net_lamports"])
        self.assertIn("right-censored", rule["censoring"])

    def test_a_reachable_slot_horizon_triggers_at_the_first_observation_at_or_past_it(self):
        path = [observation(800), observation(900), observation(1000)]
        rule = evaluate(path, exit_rules=[
            {"name": "near", "kind": B10B.RULE_SLOT_HORIZON, "slots": 150}])["exit_rules"][0]
        self.assertEqual(rule["outcome"], B10B.RULE_TRIGGERED)
        self.assertEqual(rule["at"]["slot"], 900)

    def test_an_observation_horizon_longer_than_the_path_is_right_censored(self):
        result = evaluate([observation(800)], exit_rules=[
            {"name": "ten", "kind": B10B.RULE_OBSERVATION_HORIZON, "count": 10}])
        self.assertEqual(result["exit_rules"][0]["outcome"], B10B.RULE_RIGHT_CENSORED)
        self.assertEqual(result["exit_rules"][0]["detail"]["available_evaluable_observations"], 1)

    def test_an_observation_horizon_counts_only_evaluable_states(self):
        path = [observation(800, outer_index=1, is_transaction_terminal=False),
                observation(800, outer_index=2), observation(900)]
        rule = evaluate(path, exit_rules=[
            {"name": "two", "kind": B10B.RULE_OBSERVATION_HORIZON, "count": 2}])["exit_rules"][0]
        self.assertEqual(rule["at"]["slot"], 900)

    def test_a_threshold_never_crossed_is_right_censored_not_a_loss(self):
        result = evaluate([observation(800, real_quote=10 ** 15)], exit_rules=[
            {"name": "stop", "kind": B10B.RULE_NET_AT_OR_BELOW, "lamports": -10 ** 12}])
        self.assertEqual(result["exit_rules"][0]["outcome"], B10B.RULE_RIGHT_CENSORED)

    def test_a_path_that_simply_runs_out_is_terminally_right_censored(self):
        result = evaluate([observation(800), observation(900)])
        self.assertEqual(result["terminal_state"], B10B.TERMINAL_RIGHT_CENSORED)
        self.assertEqual(result["terminal_coordinate"]["slot"], 900)

    def test_an_unknown_rule_kind_is_refused_rather_than_ignored(self):
        with self.assertRaisesRegex(B10B.PathRefused, "is not one of"):
            evaluate([observation(800)], exit_rules=[{"name": "x", "kind": "sell_the_top"}])

    def test_a_rule_missing_its_parameter_is_refused_rather_than_defaulted(self):
        with self.assertRaisesRegex(B10B.PathRefused, "needs an integer"):
            evaluate([observation(800)],
                     exit_rules=[{"name": "h", "kind": B10B.RULE_SLOT_HORIZON}])


class ContractTests(unittest.TestCase):
    """The label and the limitations are part of the record, not part of a document elsewhere."""

    def test_the_label_is_distinct_from_b10a_and_travels_with_every_record(self):
        result = evaluate([observation(800)])
        self.assertEqual(result["outcome_label"], "SIMULATED_OBSERVED_PATH")
        self.assertNotEqual(result["outcome_label"], B10A.OUTCOME_SIMULATED)
        self.assertEqual(result["calibration"], "uncalibrated")

    def test_every_record_states_that_the_later_states_are_observed_not_counterfactual(self):
        result = evaluate([observation(800)])
        joined = " ".join(result["limitations"])
        self.assertIn("OBSERVED", joined)
        self.assertIn("without our hypothetical trade", joined)
        self.assertIn("NOT modelled", joined)
        self.assertIn("No reserve delta is added to any later state", joined)

    def test_no_reserve_delta_is_ever_added_to_a_later_observed_state(self):
        """The mark must be a pure function of the observed state and the size held. If our own
        entry impact were being propagated forward, the same observed state would price
        differently after a bigger entry."""
        state = observation(800, real_quote=10 ** 15)
        small = B10B.mark_to_exit(state, 1_000_000_000, SCHEDULE, POLICY)
        self.assertEqual(
            small["gross_exit_lamports"],
            B9I.quote_out_for_tokens_in(state["virtual_quote"], state["virtual_token"],
                                        1_000_000_000))

    def test_the_evaluator_does_not_mutate_its_inputs(self):
        t0, path = t0_state(), [observation(800), observation(900)]
        order, schedule, policy = dict(ORDER), dict(SCHEDULE), dict(POLICY)
        before = copy.deepcopy((t0, path, order, schedule, policy))
        B10B.evaluate_position_path(t0, path, schedule, policy, mint=MINT, order=order)
        self.assertEqual(before, (t0, path, order, schedule, policy))

    def test_an_incomplete_cost_policy_is_refused_never_defaulted(self):
        for field in B10A.REQUIRED_POLICY_FIELDS:
            with self.subTest(field=field):
                policy = {k: v for k, v in POLICY.items() if k != field}
                with self.assertRaises(B10A.SimulationRefused):
                    B10B.evaluate_position_path(t0_state(), [observation(800)], SCHEDULE, policy,
                                                mint=MINT, order=ORDER)

    def test_an_out_of_regime_observation_fails_closed(self):
        for override in ({"quote_mint": "OtherMint111"}, {"mayhem_mode": True}):
            with self.subTest(**override):
                with self.assertRaises(B10A.SimulationRefused):
                    evaluate([observation(800, **override)])

    def test_the_serialisation_is_byte_stable_and_carries_no_float(self):
        result = evaluate([observation(800, real_quote=200_000_000), observation(900)])
        blob = B10B.canonical_json(result)
        self.assertEqual(blob, B10B.canonical_json(json.loads(blob)))
        self.assertEqual(B10B.record_hash(result), B10B.record_hash(json.loads(blob)))

        def no_float(node, where):
            if isinstance(node, float):
                self.fail(f"a float reached the record at {where}: {node!r}")
            if isinstance(node, dict):
                for key, value in node.items():
                    no_float(value, f"{where}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    no_float(value, f"{where}[{index}]")

        no_float(json.loads(blob), "record")

    def test_the_arithmetic_invariants_hold_and_are_checked_independently(self):
        path = [observation(800, real_quote=200_000_000), observation(900, real_quote=10 ** 15),
                observation(1000, real_quote=50_000)]
        self.assertTrue(B10B.assert_path_arithmetic(evaluate(path)))

    def test_a_tampered_record_is_caught_by_the_invariant_check(self):
        result = evaluate([observation(800, real_quote=200_000_000)])
        result["marks"][0]["mark"]["realizable_net_lamports"] += 1
        with self.assertRaisesRegex(B10B.PathRefused, "realizable net"):
            B10B.assert_path_arithmetic(result)

    def test_a_tampered_drawdown_is_caught_by_the_invariant_check(self):
        result = evaluate([observation(800, real_quote=200_000_000), observation(900)])
        result["marks"][1]["drawdown_lamports"] += 1
        with self.assertRaisesRegex(B10B.PathRefused, "drawdown disagrees"):
            B10B.assert_path_arithmetic(result)


class DatasetTests(unittest.TestCase):
    """The corpus layer: terminality, completion granularity and the coverage partition."""

    def derived(self, observations, completions=()):
        database = sqlite3.connect(":memory:")
        database.executescript(DATASET.SCHEMA)
        database.executemany(
            "INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", observations)
        for curve in sorted({row[0] for row in observations}):
            DATASET._insert_curve(database, curve, dict(completions).get(curve))
        return database

    def row(self, curve, slot, transaction_index, outer_index, inner_index, kind,
            real_quote=5_000_000_000, complete=0, terminal=1, quote_mint=NATIVE, mayhem=0):
        return (curve, slot, transaction_index, outer_index, inner_index, MINT, kind,
                LAUNCH_VQ, LAUNCH_VT, real_quote, LAUNCH_RT, quote_mint, mayhem, complete,
                terminal)

    def test_states_load_in_canonical_order_not_insertion_order(self):
        rows = [self.row("C", 900, 0, 0, -1, "TradeEvent"),
                self.row("C", 700, 0, 0, -1, "CreateEvent"),
                self.row("C", 800, 0, 0, -1, "TradeEvent")]
        states = DATASET.load_states(self.derived(rows), "C")
        self.assertEqual([s["slot"] for s in states], [700, 800, 900])

    def test_a_curve_without_exactly_one_create_event_is_refused(self):
        with self.assertRaisesRegex(B10B.PathRefused, "CreateEvent observations"):
            self.derived([self.row("C", 700, 0, 0, -1, "TradeEvent")])

    def test_a_non_sol_quote_curve_is_classified_out_of_regime_not_dropped(self):
        rows = [self.row("C", 700, 0, 0, -1, "CreateEvent", quote_mint="OtherMint111"),
                self.row("C", 800, 0, 0, -1, "TradeEvent", quote_mint="OtherMint111")]
        derived = self.derived(rows)
        self.assertEqual(
            derived.execute("SELECT regime FROM curve").fetchone()[0], DATASET.REGIME_NON_SOL)
        self.assertEqual(DATASET.validate(derived)["coverage"]["on_out_of_regime_curves"], 2)

    def test_the_coverage_partition_sums_to_the_observation_total(self):
        rows = [self.row("A", 700, 0, 0, -1, "CreateEvent"),
                self.row("A", 800, 0, 0, -1, "TradeEvent"),
                self.row("A", 900, 0, 0, -1, "TradeEvent"),
                self.row("B", 700, 1, 0, -1, "CreateEvent")]
        report = DATASET.validate(self.derived(rows))
        self.assertTrue(report["coverage"]["partition_sums_to_total"])
        self.assertEqual(report["coverage"]["observations_total"], 4)
        self.assertEqual(report["curves"]["without_any_trade_observation"], 1)
        self.assertEqual(report["arithmetic"]["errors"], [])

    def test_t0_advances_past_a_launch_transaction_that_also_carries_a_trade(self):
        """A launch that includes the creator's own buy publishes a mid-transaction launch state
        no transaction of ours could have faced. 910 of the 1,136 curves are shaped this way."""
        rows = [self.row("A", 700, 0, 2, -1, "CreateEvent", terminal=0),
                self.row("A", 700, 0, 4, -1, "TradeEvent"),
                self.row("A", 800, 0, 0, -1, "TradeEvent")]
        report = DATASET.validate(self.derived(rows))
        self.assertEqual(report["curves"]["t0_advanced_past_mid_transaction_launch"], 1)
        self.assertEqual(report["coverage"]["at_or_before_t0_on_evaluated_curves"], 2)
        self.assertEqual(report["coverage"]["supplied_to_evaluator"], 1)

    def test_completion_applies_from_its_own_transaction_inclusive(self):
        """`CompleteEvent` fires at an inner index after the trade that completed the curve. An
        exclusive comparison would publish one tradable state per completed curve that never
        existed for us, and it would be the highest-valued state on the whole path."""
        self.assertFalse(DATASET.is_complete_at(700, 5, None))
        self.assertFalse(DATASET.is_complete_at(700, 4, (700, 5)))
        self.assertTrue(DATASET.is_complete_at(700, 5, (700, 5)),
                        "the completing transaction's own state is already unreachable for us")
        self.assertTrue(DATASET.is_complete_at(700, 6, (700, 5)))
        self.assertTrue(DATASET.is_complete_at(701, 0, (700, 5)))
        self.assertFalse(DATASET.is_complete_at(699, 999, (700, 5)))

    def test_the_coverage_partition_check_can_be_made_to_report_failure(self):
        """A gate that reports on its own completeness is worth exactly as much as a test that can
        make it say no."""
        balanced = {"observations_total": 10, "on_out_of_regime_curves": 4,
                    "on_curves_without_a_later_observation": 2,
                    "on_curves_where_entry_was_refused": 1,
                    "at_or_before_t0_on_evaluated_curves": 1, "supplied_to_evaluator": 2}
        self.assertIsNone(DATASET.coverage_partition_error(balanced))
        lost = DATASET.coverage_partition_error(dict(balanced, supplied_to_evaluator=1))
        self.assertIsNotNone(lost)
        self.assertEqual((lost["partition"], lost["total"]), (9, 10))

    def test_a_curve_completing_inside_its_launch_transaction_offers_no_open_state(self):
        rows = [self.row("A", 700, 0, 2, -1, "CreateEvent", complete=1, terminal=0),
                self.row("A", 700, 0, 4, -1, "TradeEvent", complete=1)]
        report = DATASET.validate(self.derived(rows, completions=[("A", (700, 0))]))
        self.assertEqual(report["curves"]["no_later_observation"], 1)
        self.assertEqual(report["curves"]["evaluated"], 0)


class RealDatasetTests(unittest.TestCase):
    """Against the built corpus when it is present. Skipped rather than faked when it is not."""

    PATH = ROOT / "research" / "b10b_observed_paths.sqlite"

    def setUp(self):
        if not self.PATH.exists():
            self.skipTest("derived corpus not built; run b10b_path_dataset.py build")
        self.database = sqlite3.connect(f"file:{self.PATH}?mode=ro", uri=True)

    def tearDown(self):
        self.database.close()

    def test_the_corpus_covers_every_curve_and_records_its_own_content_hash(self):
        metadata = dict(self.database.execute("SELECT key, value FROM metadata"))
        self.assertEqual(metadata["curves"], "1136")
        self.assertEqual(metadata["observations"], "94389")
        self.assertEqual(metadata["canonical_order"], "slot,transaction_index,outer_index,"
                                                      "inner_index")
        self.assertEqual(metadata["content_sha256"], DATASET.content_hash(self.database))

    def test_every_curve_is_in_strictly_increasing_canonical_order(self):
        for curve, in self.database.execute(
                "SELECT bonding_curve FROM curve ORDER BY bonding_curve LIMIT 200"):
            keys = [B10B.canonical_key(state)
                    for state in DATASET.load_states(self.database, curve)]
            self.assertEqual(keys, sorted(set(keys)), curve)

    def test_the_out_of_regime_count_agrees_with_b10a_measured_independently(self):
        """b10a's replay gate counted 743 out-of-regime TRADE observations over the same artifact,
        reached by a different route. 743 trades plus their 10 CreateEvents is this corpus's 753,
        so the two modules agree on the regime boundary rather than each defining its own."""
        trades = self.database.execute(
            "SELECT COUNT(*) FROM observation WHERE kind='TradeEvent' AND quote_mint != ?",
            (NATIVE,)).fetchone()[0]
        self.assertEqual(trades, 743)


class MaximalityProofFoundUntestedByMutationTests(unittest.TestCase):
    """The proof that verifies the search, which nothing verified.

    A mutation sweep killed both bisection mutants — `(low + high) // 2` instead of
    `(low + high + 1) // 2`, and `<` instead of `<=` — so the SEARCH is well tested and returns
    the right answer. All three checks that PROVE the answer survived.

    That distinction is the finding. `max_executable_tokens` does not trust its bisection: it
    re-checks that the selected size does not overdraw, and that `low + 1` is not also executable.
    Those checks can only fire when the search is wrong, and since the search is correct they never
    fire in ordinary operation — the check-that-cannot-fire shape, arriving through correctness
    rather than through an always-false condition.

    B15M's frozen preregistration leans on this: *"bisection is used ONLY if monotonicity is
    verified… a failure refuses the cell rather than returning a search result over a set that is
    not a prefix."* Until now no test could distinguish that guarantee from its absence.

    These fire it by making the arithmetic lie — patching `quote_out_for_tokens_in` so the search
    reaches a wrong answer — which is exactly the situation the proof exists for.
    """

    VQ, VT = LAUNCH_VQ, LAUNCH_VT

    def patch_quote_out(self, replacement):
        real = B9I.quote_out_for_tokens_in
        B9I.quote_out_for_tokens_in = replacement
        self.addCleanup(setattr, B9I, "quote_out_for_tokens_in", real)
        return real

    def test_the_honest_case_returns_a_maximal_size(self):
        """Baseline. `tokens_held` must exceed what the reserve can pay, or the answer is capped
        by holdings and there is no `low + 1` for the proof to check — which is how the first
        version of this test passed vacuously."""
        reserve, held = 1_000_000_000, 10**14
        self.assertGreater(B9I.quote_out_for_tokens_in(self.VQ, self.VT, held), reserve,
                           "the reserve must bind, not the holdings")
        tokens, gross = B10B.max_executable_tokens(self.VQ, self.VT, reserve, held)
        self.assertLessEqual(gross, reserve)
        self.assertGreater(B9I.quote_out_for_tokens_in(self.VQ, self.VT, tokens + 1), reserve,
                           "one more token must overdraw, or the answer was not maximal")

    def test_a_result_that_OVERDRAWS_the_reserve_is_refused(self):
        """Everything is unaffordable, so the search never improves `low` past 0 — and pricing 0
        still overdraws. A pure stub: no call counting, no ordering assumptions."""
        self.patch_quote_out(lambda vq, vt, tokens: 10**18)
        with self.assertRaisesRegex(B10B.PathRefused, "size search is wrong"):
            B10B.max_executable_tokens(self.VQ, self.VT, 1_000_000_000, 10**13)

    def test_a_result_that_UNDER_SELECTS_is_refused(self):
        """The other direction, and it can only be reached by INCONSISTENT arithmetic.

        A pure stub cannot trigger this, and working that out is the finding. With any
        deterministic `quote_out_for_tokens_in`, bisection always evaluates `low + 1` before it
        stops: the loop only ends when `low == high`, and the step before that tests
        `(low + low + 2) // 2 == low + 1`. So if the search settled below `tokens_held`, `low + 1`
        was just measured as unaffordable — and a pure function will say so again at the check.

        The guard therefore defends against arithmetic that answers differently on two calls: a
        formula that is not a function of its inputs, a mutated dependency, a racing reserve. That
        is unreachable in normal operation, which is exactly why nothing had tested it, and it is
        reachable here only by simulating the inconsistency it exists for.

        This stub answers "unaffordable" the first time it is asked about 6 and "affordable"
        afterwards, so the search rejects 6 and settles on 5, then the maximality re-check finds 6
        executable after all.
        """
        asked = {"six": 0}

        def inconsistent(vq, vt, tokens):
            if tokens == 6:
                asked["six"] += 1
                return 10**18 if asked["six"] == 1 else 0
            return 0 if tokens <= 5 else 10**18

        self.patch_quote_out(inconsistent)
        with self.assertRaisesRegex(B10B.PathRefused, "also executable"):
            B10B.max_executable_tokens(self.VQ, self.VT, 1_000, 10**13)
        self.assertGreaterEqual(asked["six"], 2,
                                "the re-check must ask again rather than reuse the search's answer")

    def test_non_positive_virtual_reserves_are_refused_BY_THEIR_OWN_GUARD(self):
        """Zero and negative are refused by DIFFERENT guards, so the message is asserted.

        Negative is caught earlier by the non-negative-integer check; only zero reaches the
        curve-is-undefined branch. Asserting merely "it raises" credits the wrong one.
        """
        for field in ("vq", "vt"):
            with self.subTest(field=field, value=0):
                vq = 0 if field == "vq" else self.VQ
                vt = 0 if field == "vt" else self.VT
                with self.assertRaisesRegex(B10B.PathRefused, "curve is undefined"):
                    B10B.max_executable_tokens(vq, vt, 1_000, 1_000)
            with self.subTest(field=field, value=-1):
                vq = -1 if field == "vq" else self.VQ
                vt = -1 if field == "vt" else self.VT
                with self.assertRaisesRegex(B10B.PathRefused, "non-negative integer"):
                    B10B.max_executable_tokens(vq, vt, 1_000, 1_000)


class InputGuardsFoundUntestedByMutationTests(unittest.TestCase):
    """The validation ring around the path logic — the same split found in b11b, b12a and b9i."""

    def test_a_string_is_not_an_observation_sequence(self):
        """A string is iterable, so without this it is walked character by character and each
        character asked for its canonical key — a failure far from its cause."""
        for bad in ("an observation", {"slot": 1}, b"bytes"):
            with self.subTest(kind=type(bad).__name__):
                with self.assertRaisesRegex(B10B.PathRefused, "sequence of observation mappings"):
                    B10B.assert_canonical_sequence(bad, mint=MINT, after=None)

    def test_a_non_integer_canonical_coordinate_is_refused(self):
        for field in ("slot", "transaction_index", "outer_index", "inner_index"):
            for value in (1.0, "1", True, None):
                with self.subTest(field=field, value=value):
                    record = observation(700)
                    record[field] = value
                    with self.assertRaisesRegex(B10B.PathRefused, "must be an integer"):
                        B10B.canonical_key(record)

    def test_a_non_scalar_may_not_be_REACHABLE_from_the_entry_view(self):
        """Two different guards, two different messages, and the mutant targets the second.

        `entry_feature_view` refuses a container among the t0 FIELDS ("only scalars may cross");
        `assert_no_future_reachable` refuses one anywhere in the reference GRAPH ("only mappings
        and scalars may be reachable"). A test calling the first credits it for the second's work,
        which is how this mutant survived a test that looked like it covered it.
        """
        import types as _types
        with self.assertRaisesRegex(B10B.PathRefused, "only mappings and scalars may be reachable"):
            B10B.assert_no_future_reachable(_types.MappingProxyType({"a": [1, 2]}))
        with self.assertRaisesRegex(B10B.PathRefused, "only mappings and scalars may be reachable"):
            B10B.assert_no_future_reachable(_types.MappingProxyType({"a": {"b": {1, 2}}}))

    def test_an_entry_policy_that_is_not_callable_is_refused(self):
        with self.assertRaisesRegex(B10B.PathRefused, "must be callable"):
            B10B.decide_entry(t0_state(), SCHEDULE, POLICY, entry_policy="not a function")

    def test_a_negative_tokens_held_is_refused_BY_MARK_TO_EXIT_ITSELF(self):
        """The same message is raised by `max_executable_tokens`, so asserting the text credits
        whichever guard happens to run — and with mark_to_exit's removed, the search's fires and
        the test still passes.

        A COMPLETE curve distinguishes them: mark_to_exit returns early for a complete curve
        without ever reaching the search, so only its own guard can refuse here.
        """
        complete = t0_state(complete=True)
        self.assertEqual(
            B10B.mark_to_exit(complete, 0, SCHEDULE, POLICY)["reason"],
            B10B.REASON_CURVE_COMPLETE,
            "a complete curve must return early, or this does not isolate the guard")
        with self.assertRaisesRegex(B10B.PathRefused, "tokens_held must be"):
            B10B.mark_to_exit(complete, -1, SCHEDULE, POLICY)


if __name__ == "__main__":
    unittest.main()
