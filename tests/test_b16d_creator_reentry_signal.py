"""B16d guards. Synthetic paths and schedules; no burned artifact, no network.

The guards that matter are the ones that would manufacture an edge: entering before the signal was
observable, using the creator's own flow as the follower's result, pricing a cell whose exit book
could not pay, counting a censored cell as zero, and assuming a fee schedule.
"""
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B16D = load("b16d_creator_reentry_signal", "b16d_creator_reentry_signal.py")

CURVE = "Curve1"
CREATOR = "Creator1"
OTHER = "Other1"
NATIVE = B16D.B10A.B9D.NATIVE_QUOTE_MINT
SCHEDULE = {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0, "buyback_fee_bps": 5000}
POLICY = {"base_fee_lamports": 5000, "priority_fee_lamports": 100000, "tip_lamports": 0,
          "ata_rent_lamports": 2039280, "failed_attempts": 0}


def observation(slot, transaction_index=0, real_quote=30_000_000_000,
                real_token=200_000_000_000_000, complete=False):
    return {"slot": slot, "transaction_index": transaction_index, "outer_index": 0,
            "inner_index": 0, "kind": "TradeEvent",
            "virtual_quote": 30_000_000_000 + real_quote, "virtual_token": 1_073_000_000_000_000,
            "real_quote": real_quote, "real_token": real_token, "quote_mint": NATIVE,
            "mayhem_mode": False, "complete": complete}


class TestPreregistrationIsPinned(unittest.TestCase):
    def test_the_shipped_preregistration_verifies(self):
        document = B16D.verify_preregistration()
        self.assertEqual(document["preregistration_id"], "B16D_CREATOR_REENTRY_SIGNAL_V1")

    def test_a_tampered_preregistration_refuses(self):
        import tempfile
        directory = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        document = json.loads(B16D.PREREG.read_bytes())
        document["frozen_timing_variants"]["entry_delays_slots"] = [1, 2, 4, 8]
        altered = directory / "p.json"
        altered.write_text(json.dumps(document))
        with self.assertRaisesRegex(B16D.SignalRefused, "hashes"):
            B16D.verify_preregistration(altered)

    def test_the_frozen_variants_match_the_preregistration(self):
        document = B16D.verify_preregistration()
        self.assertEqual(list(B16D.DELAYS),
                         document["frozen_timing_variants"]["entry_delays_slots"])
        self.assertEqual([name for name, _slots in B16D.HORIZONS],
                         document["frozen_exit_horizons"]["horizons"])
        self.assertEqual(B16D.POSITION,
                         document["frozen_position_sizes"]["primary_lamports"])
        self.assertEqual(list(B16D.GRID),
                         document["frozen_position_sizes"]["sensitivity_grid_lamports"])


class TestSignalSelection(unittest.TestCase):
    def trades(self, rows):
        return [{"wallet": w, "bonding_curve": CURVE, "slot": s, "transaction_index": t,
                 "direction": d, "quote_delta_lamports": 1, "token_delta": -1,
                 "outer_index": 0, "inner_index": 0} for w, s, t, d in rows]

    def curves(self, create_slot=100):
        return {CURVE: {"mint": "m", "create_slot": create_slot, "complete_slot": None,
                        "creator": CREATOR, "create_user": CREATOR}}

    def test_the_first_creator_buy_after_the_create_is_the_signal(self):
        trades = self.trades([(CREATOR, 150, 0, "buy"), (CREATOR, 200, 0, "buy")])
        creator, _other = B16D.signals(trades, self.curves(), {CURVE: {CREATOR}})
        self.assertEqual(creator[CURVE]["slot"], 150)

    def test_only_one_signal_per_curve(self):
        trades = self.trades([(CREATOR, 150, 0, "buy"), (CREATOR, 160, 0, "buy"),
                              (CREATOR, 170, 0, "buy")])
        creator, _other = B16D.signals(trades, self.curves(), {CURVE: {CREATOR}})
        self.assertEqual(len(creator), 1)

    def test_a_creator_sell_is_not_a_signal(self):
        trades = self.trades([(CREATOR, 150, 0, "sell")])
        creator, _other = B16D.signals(trades, self.curves(), {CURVE: {CREATOR}})
        self.assertEqual(creator, {})

    def test_a_buy_before_the_create_is_not_a_signal(self):
        trades = self.trades([(CREATOR, 50, 0, "buy")])
        creator, _other = B16D.signals(trades, self.curves(create_slot=100), {CURVE: {CREATOR}})
        self.assertEqual(creator, {})

    def test_a_non_creator_buy_feeds_the_baseline_not_the_signal(self):
        trades = self.trades([(OTHER, 150, 0, "buy")])
        creator, other = B16D.signals(trades, self.curves(), {CURVE: {CREATOR}})
        self.assertEqual(creator, {})
        self.assertEqual(other[CURVE]["slot"], 150)

    def test_the_creator_flow_never_enters_the_followers_outcome(self):
        """The signal supplies only a COORDINATE. Its size and direction are not used."""
        import ast
        source = (ROOT / "scripts" / "b16d_creator_reentry_signal.py").read_text()
        tree = ast.parse(source)
        function = next(node for node in ast.walk(tree)
                        if isinstance(node, ast.FunctionDef) and node.name == "evaluate")
        used = {node.value for node in ast.walk(function)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        for banned in ("quote_delta_lamports", "token_delta", "direction", "wallet"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, used,
                                 "the follower's outcome must not read the creator's own trade")


class TestObservabilityGate(unittest.TestCase):
    def test_an_entry_is_taken_only_at_or_after_the_signal_slot_plus_delay(self):
        path = [observation(100), observation(101), observation(105)]
        self.assertEqual(B16D.first_at_or_after(path, 101)["slot"], 101)
        self.assertEqual(B16D.first_at_or_after(path, 102)["slot"], 105)
        self.assertIsNone(B16D.first_at_or_after(path, 999))

    def test_a_same_slot_only_opportunity_is_refused_and_counted(self):
        """Ordering within a slot is the leader's, not an observer's."""
        signal = {CURVE: {"slot": 100, "transaction_index": 0}}
        path = {CURVE: [observation(100, 0), observation(100, 5)]}
        result = B16D.evaluate(signal, path, {CURVE: SCHEDULE}, (B16D.POSITION,), "t")
        self.assertEqual(result["same_slot_only_opportunities"], 1)
        self.assertEqual(result["refusals"][B16D.D_SAME_SLOT_UNPROVABLE], 1)
        self.assertEqual(result["cells"], {})

    def test_a_later_slot_opportunity_is_admissible(self):
        signal = {CURVE: {"slot": 100, "transaction_index": 0}}
        path = {CURVE: [observation(100, 0), observation(101), observation(2000)]}
        result = B16D.evaluate(signal, path, {CURVE: SCHEDULE}, (B16D.POSITION,), "t")
        self.assertEqual(result["same_slot_only_opportunities"], 0)


class TestRefusalsRatherThanAssumptions(unittest.TestCase):
    def setUp(self):
        self.signal = {CURVE: {"slot": 100, "transaction_index": 0}}
        self.path = {CURVE: [observation(100), observation(101), observation(1200),
                             observation(20000)]}

    def test_a_curve_without_a_decodable_fee_schedule_is_refused(self):
        result = B16D.evaluate(self.signal, self.path, {}, (B16D.POSITION,), "t")
        self.assertEqual(result["refusals"][B16D.D_NO_FEE_SCHEDULE], 1)
        self.assertEqual(result["cells"], {})

    def test_a_cell_with_no_observation_past_the_horizon_is_right_censored(self):
        short = {CURVE: [observation(100), observation(101)]}
        result = B16D.evaluate(self.signal, short, {CURVE: SCHEDULE}, (B16D.POSITION,), "t")
        self.assertGreater(result["refusals"][B16D.D_RIGHT_CENSORED], 0)
        self.assertEqual(result["cells"], {}, "a censored cell carries no outcome, not a zero")

    def test_a_complete_curve_is_refused(self):
        with self.assertRaises(B16D.SignalRefused) as caught:
            B16D.price_follower(observation(101, complete=True), observation(1200), SCHEDULE,
                                POLICY, B16D.POSITION)
        self.assertEqual(str(caught.exception), B16D.D_COMPLETE_AT_ENTRY_OR_EXIT)

    def test_an_exit_book_that_cannot_pay_is_refused(self):
        """The capacity gate: never priced against liquidity our own entry supplied."""
        thin = observation(1200, real_quote=1, real_token=200_000_000_000_000)
        with self.assertRaises(B16D.SignalRefused) as caught:
            B16D.price_follower(observation(101), thin, SCHEDULE, POLICY, B16D.POSITION)
        self.assertEqual(str(caught.exception), B16D.D_CAPACITY_REFUSED)

    def test_a_priceable_round_trip_returns_an_integer(self):
        net = B16D.price_follower(observation(101), observation(1200), SCHEDULE, POLICY,
                                  B16D.POSITION)
        self.assertIsInstance(net, int)


class TestStateSelection(unittest.TestCase):
    def test_the_state_faced_is_the_last_observation_at_or_before_the_instant(self):
        path = [observation(100, real_quote=1), observation(200, real_quote=2),
                observation(300, real_quote=3)]
        self.assertEqual(B16D.state_at(path, 250)["real_quote"], 2)
        self.assertEqual(B16D.state_at(path, 300)["real_quote"], 3)
        self.assertIsNone(B16D.state_at(path, 99))

    def test_the_state_is_never_taken_from_the_future(self):
        path = [observation(100, real_quote=1), observation(500, real_quote=9)]
        self.assertEqual(B16D.state_at(path, 200)["real_quote"], 1,
                         "using the 500-slot state at slot 200 would be hindsight")


class TestReportHonesty(unittest.TestCase):
    def test_the_module_names_no_figure_a_return_or_profit(self):
        source = (ROOT / "scripts" / "b16d_creator_reentry_signal.py").read_text()
        import ast
        tree = ast.parse(source)
        names = {node.name for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name in names:
            for banned in ("profit", "return_", "pnl", "roi", "edge"):
                with self.subTest(name=name, banned=banned):
                    self.assertNotIn(banned, name.lower())

    def test_no_mean_is_computed(self):
        source = (ROOT / "scripts" / "b16d_creator_reentry_signal.py").read_text()
        for banned in ("statistics.mean", "sum(values) / ", "np.mean", "average("):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, source)

    def test_the_summary_reports_counts_at_or_below_zero_and_a_tail_share(self):
        cells = {("base", "h_1000_slots", 1, 100): [
            {"bonding_curve": "a", "net_lamports": -5},
            {"bonding_curve": "b", "net_lamports": 100},
            {"bonding_curve": "c", "net_lamports": 1}]}
        summary = B16D.summarise_cells(cells)
        entry = summary["base|h_1000_slots|delay1|size100"]
        self.assertEqual(entry["cells"], 3)
        self.assertEqual(entry["cells_at_or_below_zero"], 1)
        self.assertEqual(entry["positive_cells"], 2)
        self.assertEqual(entry["share_of_positive_total_in_top_decile_denominator"], 101)
        self.assertEqual(entry["share_of_positive_total_in_top_decile_numerator"], 100)

    def test_the_scenarios_are_b15ds_three_verbatim(self):
        self.assertEqual([s["scenario_id"] for s in B16D.SCENARIOS],
                         ["optimistic", "base", "stressed"])
        base = next(s for s in B16D.SCENARIOS if s["scenario_id"] == "base")
        self.assertEqual(base["priority_fee_lamports"], 100000)
        self.assertEqual(base["ata_rent_lamports"], 2039280)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestFeeScheduleResolution(unittest.TestCase):
    """A curve with two decodable answers has no answer, and is refused rather than guessed."""

    def test_a_single_consistent_schedule_is_accepted(self):
        seen = {CURVE: {json.dumps(SCHEDULE, sort_keys=True)}}
        schedules, ambiguous = B16D.resolve_schedules(seen)
        self.assertEqual(schedules[CURVE], SCHEDULE)
        self.assertEqual(ambiguous, [])

    def test_disagreeing_schedules_are_refused_not_resolved_by_majority(self):
        other = dict(SCHEDULE, creator_fee_bps=0, cashback_fee_bps=30)
        seen = {CURVE: {json.dumps(SCHEDULE, sort_keys=True),
                        json.dumps(other, sort_keys=True)}}
        schedules, ambiguous = B16D.resolve_schedules(seen)
        self.assertEqual(schedules, {}, "a curve with two answers must be priced with neither")
        self.assertEqual(ambiguous, [CURVE])

    def test_a_repeated_identical_schedule_is_still_one_answer(self):
        seen = {CURVE: {json.dumps(SCHEDULE, sort_keys=True)}}
        schedules, ambiguous = B16D.resolve_schedules(seen)
        self.assertEqual(len(schedules), 1)
        self.assertEqual(ambiguous, [])

    def test_a_refused_curve_cannot_be_priced(self):
        signal = {CURVE: {"slot": 100, "transaction_index": 0}}
        path = {CURVE: [observation(100), observation(101), observation(1200),
                        observation(20000)]}
        other = dict(SCHEDULE, creator_fee_bps=0)
        schedules, _ambiguous = B16D.resolve_schedules(
            {CURVE: {json.dumps(SCHEDULE, sort_keys=True), json.dumps(other, sort_keys=True)}})
        result = B16D.evaluate(signal, path, schedules, (B16D.POSITION,), "t")
        self.assertEqual(result["refusals"][B16D.D_NO_FEE_SCHEDULE], 1)
        self.assertEqual(result["cells"], {})
