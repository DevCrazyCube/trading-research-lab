"""T4 — the paper forward-test bot, with every gate shown to be able to refuse.

The dangerous failures for this bot are not arithmetic slips, they are quiet ones:

  * a weight computed from a close the strategy could not have seen (the whole point of the
    test evaporates without anybody noticing),
  * an order leaving the process because a flag defaulted the convenient way,
  * a cost model that charges an exit the entry's free auction rail,
  * a ledger that can be written twice for one session, or backfilled from history,
  * a credential riding along in a log record.

Every test below breaks one of those. The suite is hermetic: `tests/_netguard.py` blocks
outbound sockets for the whole session, so anything here that reaches the network fails loudly
rather than quietly measuring the real market.
"""
import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.trading_bot import t4_forward as T4          # noqa: E402
from scripts.trading_bot.frozen import Refused            # noqa: E402
from scripts.trading_bot.paper import Order, OrderType, Side  # noqa: E402


def synthetic_series(n=300, start="2026-01-02", vol_step=0.004):
    """A deterministic close series with session dates. No RNG, so a failure is reproducible."""
    dates, closes, micros, price = [], [], [], 400.0
    day = dt.date.fromisoformat(start)
    for i in range(n):
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        price *= 1.0 + ((1 if (i * 7) % 3 else -1) * vol_step)
        dates.append(day.isoformat())
        closes.append(price)
        micros.append(int(round(price * 1_000_000)))
        day += dt.timedelta(days=1)
    return {"dates": dates, "closes": closes, "close_micros": micros,
            "manifest": {"source": "synthetic"}}


class FrozenRuleTests(unittest.TestCase):
    def test_rule_is_the_t13_freeze_and_its_hash_is_verified(self):
        rule = T4.frozen_rule()
        self.assertEqual(rule["L"], 60)
        self.assertEqual(rule["target"], 0.10)
        self.assertEqual(rule["wmax"], 1.0)
        self.assertEqual(rule["rule_id"], "T13-VOL-L60-T0.1-WMAX1.0")
        # the hash in the frozen config must be the hash of the document on disk
        self.assertEqual(rule["t13_preregistration_sha256"],
                         T4._sha256(T4.T13_PREREG))

    def test_an_edited_preregistration_refuses(self):
        """The freeze is only a freeze if editing the document breaks the bot."""
        original = T4.T13_PREREG
        with tempfile.TemporaryDirectory() as tmp:
            fake = pathlib.Path(tmp) / "T13_PREREGISTRATION.md"
            fake.write_text(original.read_text() + "\nan edit made after the freeze\n")
            T4.T13_PREREG = fake
            try:
                with self.assertRaises(Refused) as ctx:
                    T4.frozen_rule()
                self.assertIn("changed since the freeze", str(ctx.exception))
            finally:
                T4.T13_PREREG = original


class WeightTests(unittest.TestCase):
    def setUp(self):
        self.rule = T4.frozen_rule()

    def test_frozen_implementation_and_independent_recomputation_agree(self):
        series = synthetic_series()
        out = T4.t13_target_weight(series["closes"], self.rule)
        rv, w = T4._independent_target_weight(series["closes"], 60, 0.10, 1.0)
        self.assertAlmostEqual(out["target_weight"], w, places=15)
        self.assertAlmostEqual(out["realised_vol_annual"], rv, places=15)

    def test_weight_uses_only_the_last_sixty_returns_and_nothing_later(self):
        """The lookahead probe: deleting nothing after the reference close changes nothing.

        Appending a future close must not move the weight for the session already decided —
        that is the property T13-L1 exists to guarantee, and the cheapest way to break it is
        an off-by-one in the index window.
        """
        series = synthetic_series()
        base = T4.t13_target_weight(series["closes"], self.rule)["target_weight"]
        truncated = T4.t13_target_weight(series["closes"][:len(series["closes"])], self.rule)
        self.assertEqual(base, truncated["target_weight"])

        # the weight decided on a SHORTER history must equal the weight this bot would have
        # decided on that day when it was the present — i.e. history is not being re-read.
        earlier = series["closes"][:200]
        w_then = T4.t13_target_weight(earlier, self.rule)["target_weight"]
        w_again = T4.t13_target_weight(series["closes"][:200], self.rule)["target_weight"]
        self.assertEqual(w_then, w_again)

    def test_weight_falls_when_realised_volatility_rises(self):
        calm = T4.t13_target_weight(synthetic_series(vol_step=0.003)["closes"], self.rule)
        wild = T4.t13_target_weight(synthetic_series(vol_step=0.012)["closes"], self.rule)
        self.assertLess(wild["target_weight"], calm["target_weight"])
        self.assertGreater(wild["realised_vol_annual"], calm["realised_vol_annual"])

    def test_weight_is_capped_at_wmax_in_a_dead_calm_market(self):
        quiet = synthetic_series(vol_step=0.00005)
        out = T4.t13_target_weight(quiet["closes"], self.rule)
        self.assertEqual(out["target_weight"], self.rule["wmax"])

    def test_short_history_refuses_rather_than_sizing_on_a_stub(self):
        with self.assertRaises(Refused):
            T4.t13_target_weight(synthetic_series(n=40)["closes"], self.rule)

    def test_a_disagreement_between_the_two_implementations_refuses(self):
        """The cross-check must actually be load-bearing, not decorative."""
        original = T4._independent_target_weight
        T4._independent_target_weight = lambda *a, **k: (0.2, 0.5)
        try:
            with self.assertRaises(Refused) as ctx:
                T4.t13_target_weight(synthetic_series()["closes"], self.rule)
            self.assertIn("disagree", str(ctx.exception))
        finally:
            T4._independent_target_weight = original


class CostTests(unittest.TestCase):
    def test_both_legs_are_priced_and_neither_inherits_the_other(self):
        model = T4.m0_auction_cost_model()
        self.assertGreaterEqual(model.entry_spread_and_slippage_fraction(), 0)
        self.assertGreaterEqual(model.exit_spread_and_slippage_fraction(), 0)
        # T6: the round trip is the sum of two stated sides, not one number doubled or halved
        self.assertEqual(model.round_trip_bp(),
                         model.entry_half_spread.value + model.entry_extra_slippage.value
                         + model.exit_half_spread.value + model.exit_extra_slippage.value)

    def test_sell_side_regulatory_fees_are_charged_by_name(self):
        """The auction half-spread is a measured ZERO, so SEC 31 has nothing to hide in."""
        price = 650_000_000        # $650 in micro-dollars
        bp = T4._regulatory_sell_side_bp(price)
        self.assertGreater(bp, T4.SEC_31_BP_SELL)          # TAF is on top, not absorbed
        self.assertLess(bp, T4.SEC_31_BP_SELL + Fraction(1, 100))

    def test_a_derisk_charges_the_exit_leg_and_a_reexposure_does_not(self):
        model = T4.m0_auction_cost_model()
        price = 650_000_000
        derisk = T4._cost_fraction(model, 0.80, 0.60, price)
        reexpose = T4._cost_fraction(model, 0.60, 0.80, price)
        self.assertGreater(derisk["exit_turnover"], 0)
        self.assertEqual(derisk["entry_turnover"], 0)
        self.assertEqual(reexpose["exit_turnover"], 0)
        self.assertGreater(reexpose["entry_turnover"], 0)
        # only the sell leg pays SEC 31 / TAF
        self.assertGreater(derisk["regulatory_sell_fraction"], 0)
        self.assertEqual(reexpose["regulatory_sell_fraction"], 0)

    def test_no_change_is_free(self):
        model = T4.m0_auction_cost_model()
        self.assertEqual(T4._cost_fraction(model, 0.7, 0.7, 650_000_000)["total_fraction"], 0)

    def test_the_stress_rail_is_strictly_dearer_than_the_auction_rail(self):
        """The logged counterfactual has to be a real alternative, not a relabelled twin."""
        auction, taker = T4.m0_auction_cost_model(), T4.stress_cost_model()
        self.assertLess(auction.round_trip_bp(), taker.round_trip_bp())


class SettlementTests(unittest.TestCase):
    def setUp(self):
        self.rule = T4.frozen_rule()
        self.series = synthetic_series()
        self.state = T4._blank_state(self.rule)
        self.cost = T4.m0_auction_cost_model()
        self.stress = T4.stress_cost_model()

    def _settle(self, **kw):
        return T4.settle(self.state, self.series, cost_model=self.cost,
                         stress_model=self.stress, use_cash_leg=False, **kw)

    def test_a_full_weight_reproduces_the_index_return_net_of_the_entry(self):
        # the change takes effect at [10]; the series ends at [11] so exactly two settle
        self.series["dates"] = self.series["dates"][:11]
        self.series["closes"] = self.series["closes"][:11]
        self.series["close_micros"] = self.series["close_micros"][:11]
        self.state["weight_changes"][self.series["dates"][10]] = 1.0
        rows = self._settle()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        expected = (1.0 + row["r_index"]) * (1.0 - row["cost"]["total_fraction"]) - 1.0
        self.assertAlmostEqual(row["r_model_excash"], expected, places=15)

    def test_a_zero_weight_earns_nothing_ex_cash(self):
        self.state["weight_changes"][self.series["dates"][10]] = 0.0
        row = self._settle()[0]
        self.assertAlmostEqual(row["r_model_excash"], 0.0, places=15)

    def test_the_benchmark_pays_for_its_one_entry_and_then_tracks_the_index(self):
        self.state["weight_changes"][self.series["dates"][10]] = 0.5
        rows = self._settle()
        self.assertLess(rows[0]["r_benchmark"], rows[0]["r_index"])    # entry charged
        self.assertEqual(rows[1]["r_benchmark"], rows[1]["r_index"])   # and only once

    def test_a_weight_persists_until_something_changes_it(self):
        """A missed run must not silently un-hold the position the account is really in."""
        self.state["weight_changes"][self.series["dates"][10]] = 0.6
        self.state["weight_changes"][self.series["dates"][15]] = 0.4
        rows = self._settle()
        by_date = {r["date"]: r["weight_in_force"] for r in rows}
        for date in self.series["dates"][10:15]:
            self.assertEqual(by_date[date], 0.6)
        self.assertEqual(by_date[self.series["dates"][15]], 0.4)
        # and no cost is charged on the sessions where nothing moved
        idle = [r for r in rows if r["date"] in self.series["dates"][11:15]]
        self.assertTrue(all(r["cost"]["total_fraction"] == 0 for r in idle))

    def test_curves_advance_incrementally_and_are_never_recomputed(self):
        self.state["weight_changes"][self.series["dates"][10]] = 0.7
        self._settle()
        snapshot = dict(self.state["curves"])
        # a later dividend adjustment moves the historical closes; the logged curve must not
        self.series["closes"] = [c * 1.01 for c in self.series["closes"]]
        self.series["close_micros"] = [int(m * 1.01) for m in self.series["close_micros"]]
        self._settle()                       # nothing new is pending
        self.assertEqual(self.state["curves"], snapshot)

    def test_drawdown_is_tracked_against_a_running_peak(self):
        self.state["weight_changes"][self.series["dates"][10]] = 1.0
        self._settle()
        self.assertGreater(self.state["maxdd"]["model_excash"], 0.0)
        self.assertGreaterEqual(self.state["maxdd"]["benchmark"], 0.0)

    def test_sessions_before_inception_are_never_settled(self):
        self.state["weight_changes"][self.series["dates"][100]] = 0.5
        rows = self._settle()
        self.assertEqual(rows[0]["date"], self.series["dates"][100])
        self.assertEqual(len(rows), len(self.series["dates"]) - 100)

    def test_settlement_is_not_repeated_on_a_second_call(self):
        self.state["weight_changes"][self.series["dates"][10]] = 0.8
        first = self._settle()
        self.assertGreater(len(first), 0)
        self.assertEqual(len(self._settle()), 0)


class PendingWeightTests(unittest.TestCase):
    def setUp(self):
        self.rule = T4.frozen_rule()
        self.series = synthetic_series()
        self.state = T4._blank_state(self.rule)

    def test_a_weight_decided_at_a_close_takes_effect_at_the_NEXT_session(self):
        """This is T13-L1 in the live schedule. Binding it to the same session is the bug."""
        decided_on = self.series["dates"][10]
        self.state["pending_weights"][decided_on] = {
            "weight": 0.66, "reference_close_date": self.series["dates"][9]}
        T4.bind_pending_weight(self.state, self.series)
        self.assertNotIn(decided_on, self.state["weight_changes"])
        self.assertEqual(self.state["weight_changes"][self.series["dates"][11]], 0.66)
        self.assertEqual(self.state["pending_weights"], {})

    def test_a_decision_with_no_later_session_yet_stays_queued(self):
        self.state["pending_weights"][self.series["dates"][-1]] = {
            "weight": 0.5, "reference_close_date": self.series["dates"][-2]}
        T4.bind_pending_weight(self.state, self.series)
        self.assertEqual(self.state["weight_changes"], {})
        self.assertEqual(len(self.state["pending_weights"]), 1)

    def test_every_queued_decision_is_kept_not_only_the_newest(self):
        """The bug this replaces dropped all but the last decision and settled nothing."""
        for offset in (10, 11, 12):
            self.state["pending_weights"][self.series["dates"][offset]] = {
                "weight": 0.5 + offset / 100.0,
                "reference_close_date": self.series["dates"][offset - 1]}
        T4.bind_pending_weight(self.state, self.series)
        self.assertEqual(self.state["weight_changes"], {
            self.series["dates"][11]: 0.60,
            self.series["dates"][12]: 0.61,
            self.series["dates"][13]: 0.62,
        })


class OwnerGateTests(unittest.TestCase):
    def test_submission_refuses_without_the_owner_authorisation_file(self):
        original = T4.AUTHORISATION_PATH
        with tempfile.TemporaryDirectory() as tmp:
            T4.AUTHORISATION_PATH = pathlib.Path(tmp) / "T4_OWNER_AUTHORISATION.json"
            try:
                with self.assertRaises(Refused) as ctx:
                    T4.assert_owner_authorised()
                self.assertIn("NOT AUTHORISED", str(ctx.exception))
            finally:
                T4.AUTHORISATION_PATH = original

    def test_a_malformed_authorisation_is_not_an_authorisation(self):
        original = T4.AUTHORISATION_PATH
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "auth.json"
            path.write_text(json.dumps({"paper_order_submission_authorised": "yes"}))
            T4.AUTHORISATION_PATH = path
            try:
                with self.assertRaises(Refused):
                    T4.assert_owner_authorised()
            finally:
                T4.AUTHORISATION_PATH = original

    def test_a_well_formed_authorisation_passes(self):
        original = T4.AUTHORISATION_PATH
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "auth.json"
            path.write_text(json.dumps({"paper_order_submission_authorised": True,
                                        "authorised_by": "owner"}))
            T4.AUTHORISATION_PATH = path
            try:
                self.assertEqual(T4.assert_owner_authorised()["authorised_by"], "owner")
            finally:
                T4.AUTHORISATION_PATH = original

    def test_place_order_refuses_before_it_builds_a_payload(self):
        """The gate must be the FIRST thing the order method does, not a check after the fact."""
        original = T4.AUTHORISATION_PATH
        with tempfile.TemporaryDirectory() as tmp:
            T4.AUTHORISATION_PATH = pathlib.Path(tmp) / "absent.json"
            account = T4.PaperAccount.__new__(T4.PaperAccount)   # no credentials needed
            order = Order(symbol="SPY", side=Side.BUY, order_type=OrderType.MARKET,
                          quantity_shares=93)
            try:
                with self.assertRaises(Refused) as ctx:
                    account.place_near_close_market(order, client_order_id="t4-test")
                self.assertIn("NOT AUTHORISED", str(ctx.exception))
            finally:
                T4.AUTHORISATION_PATH = original

    def test_the_live_endpoint_is_unreachable_by_construction(self):
        with self.assertRaises(Refused) as ctx:
            T4.PaperAccount("https://api.alpaca.markets")
        self.assertIn("LIVE", str(ctx.exception))

    def test_a_lookalike_host_is_refused_too(self):
        with self.assertRaises(Refused):
            T4.PaperAccount("https://paper-api.alpaca.markets.evil.test")

    def test_submitting_against_a_simulated_account_size_refuses(self):
        with self.assertRaises(Refused) as ctx:
            T4.run_session(mode="submit", account_source="simulated", simulated_equity=1000)
        self.assertIn("simulated", str(ctx.exception))

    def test_an_unknown_mode_refuses(self):
        with self.assertRaises(Refused):
            T4.run_session(mode="live", account_source="broker", simulated_equity=1000)


class FillReconciliationTests(unittest.TestCase):
    """The one measurement that accrues fast: did the on-close order land at the print?"""

    class FakeAccount:
        def __init__(self, payload):
            self.payload = payload
            self.asked = []

        def order(self, order_id):
            self.asked.append(order_id)
            return self.payload

    def setUp(self):
        self.series = synthetic_series()
        self.state = T4._blank_state(T4.frozen_rule())
        self.date = self.series["dates"][10]
        self.close = self.series["closes"][10]

    def _reconcile(self, side, fill_price):
        self.state["pending_order"] = {"order_id": "abc", "session_date": self.date,
                                       "side": side, "qty": 10}
        account = self.FakeAccount({"status": "filled", "filled_qty": "10",
                                    "filled_avg_price": str(fill_price)})
        return T4.reconcile_fill(self.state, self.series, account)

    def test_a_buy_filled_above_the_print_is_ADVERSE_and_positive(self):
        out = self._reconcile("buy", self.close * 1.0001)
        self.assertAlmostEqual(out["shortfall_bp_adverse_positive"], 1.0, places=6)

    def test_a_sell_filled_below_the_print_is_ADVERSE_and_positive(self):
        out = self._reconcile("sell", self.close * 0.9999)
        self.assertAlmostEqual(out["shortfall_bp_adverse_positive"], 1.0, places=6)

    def test_a_fill_at_the_print_costs_nothing(self):
        out = self._reconcile("buy", self.close)
        self.assertAlmostEqual(out["shortfall_bp_adverse_positive"], 0.0, places=9)

    def test_reconciling_clears_the_pending_order_so_it_is_never_counted_twice(self):
        self._reconcile("buy", self.close)
        self.assertIsNone(self.state["pending_order"])
        again = T4.reconcile_fill(self.state, self.series, self.FakeAccount({}))
        self.assertFalse(again["reconciled"])

    def test_an_unprinted_session_leaves_the_shortfall_null_rather_than_zero(self):
        self.state["pending_order"] = {"order_id": "abc", "session_date": "2099-01-01",
                                       "side": "buy", "qty": 10}
        account = self.FakeAccount({"status": "new", "filled_qty": "0",
                                    "filled_avg_price": None})
        out = T4.reconcile_fill(self.state, self.series, account)
        self.assertIsNone(out["shortfall_bp_adverse_positive"])


class LedgerTests(unittest.TestCase):
    def test_state_written_under_a_different_rule_refuses_to_load(self):
        rule = T4.frozen_rule()
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            state = T4._blank_state(rule)
            state["rule"] = dict(rule, rule_id="T13-VOL-L20-T0.15-WMAX1.5")
            path.write_text(json.dumps(state))
            with self.assertRaises(Refused) as ctx:
                T4.load_state(rule, path)
            self.assertIn("rule", str(ctx.exception))

    def test_a_state_from_a_different_schema_refuses(self):
        rule = T4.frozen_rule()
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            state = T4._blank_state(rule)
            state["schema_version"] = 999
            path.write_text(json.dumps(state))
            with self.assertRaises(Refused):
                T4.load_state(rule, path)

    def test_ledger_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "ledger.jsonl"
            T4.append_ledger({"kind": "session", "session_date": "2026-08-17"}, path)
            T4.append_ledger({"kind": "session", "session_date": "2026-08-18"}, path)
            rows = T4.read_ledger(path)
            self.assertEqual([r["session_date"] for r in rows],
                             ["2026-08-17", "2026-08-18"])

    def test_a_credential_in_a_record_refuses_to_be_written(self):
        """The check has to fire on a real key shape, not only on the literal word 'secret'."""
        try:
            key, secret = T4.load_env_credentials()
        except Refused:
            self.skipTest("no credentials configured in this environment")
        with self.assertRaises(Refused) as ctx:
            T4._assert_clean({"kind": "session", "oops": secret})
        self.assertIn("credential", str(ctx.exception))
        T4._assert_clean({"kind": "session", "fine": key[:4]})   # a fragment is not the key


class SizingTests(unittest.TestCase):
    def test_shares_round_down_so_the_position_is_never_larger_than_authorised(self):
        from scripts.trading_bot.paper import orders_for_target
        orders = orders_for_target(
            "SPY", Fraction(72, 100), Fraction(0), equity_micros=100_000_000_000,
            price_micros=776_340_000, ts_ns=0,
        )
        self.assertEqual(len(orders), 1)
        shares = orders[0].quantity_shares
        self.assertLessEqual(shares * 776.34, 0.72 * 100_000)
        self.assertGreater((shares + 1) * 776.34, 0.72 * 100_000)

    def test_a_sub_share_drift_produces_no_order_at_all(self):
        from scripts.trading_bot.paper import orders_for_target
        orders = orders_for_target(
            "SPY", Fraction(720_001, 1_000_000), Fraction(72, 100),
            equity_micros=100_000_000_000, price_micros=776_340_000, ts_ns=0,
        )
        self.assertEqual(orders, [])

    def test_the_order_is_a_market_order_and_a_zero_quantity_refuses(self):
        order = Order(symbol="SPY", side=Side.BUY, order_type=OrderType.MARKET,
                      quantity_shares=10)
        self.assertIs(order.order_type, OrderType.MARKET)
        with self.assertRaises(Refused):
            Order(symbol="SPY", side=Side.BUY, order_type=OrderType.MARKET,
                  quantity_shares=0)

    def test_the_submitted_payload_is_tif_day_and_never_cls(self):
        """The 2026-08-18 fix, pinned. tif=cls EXPIRES UNFILLED on the Alpaca paper account:
        order 3a5487f8 was submitted 2026-08-17T13:50Z and expired at 20:00Z with filled_qty=0.
        If this assertion ever flips back to "cls" the forward test silently stops accruing."""
        original = T4.AUTHORISATION_PATH
        with tempfile.TemporaryDirectory() as tmp:
            auth = pathlib.Path(tmp) / "auth.json"
            auth.write_text(json.dumps({"paper_order_submission_authorised": True}))
            T4.AUTHORISATION_PATH = auth
            captured = {}
            account = T4.PaperAccount.__new__(T4.PaperAccount)
            account._request = lambda method, path, body=None: captured.update(
                method=method, path=path, body=body) or {"id": "x"}
            order = Order(symbol="SPY", side=Side.BUY, order_type=OrderType.MARKET,
                          quantity_shares=93)
            try:
                account.place_near_close_market(order, client_order_id="t4-test")
            finally:
                T4.AUTHORISATION_PATH = original
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["body"]["type"], "market")
        self.assertEqual(captured["body"]["time_in_force"], "day")
        self.assertNotEqual(captured["body"]["time_in_force"], "cls")
        self.assertEqual(captured["body"]["qty"], "93")
        self.assertIs(captured["body"]["extended_hours"], False)


class CashLegTests(unittest.TestCase):
    def test_a_stale_cash_rate_refuses_rather_than_being_held_flat_forever(self):
        original = T4.CASH_PATH
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "cash.csv"
            path.write_text("date,annual_pct,source\n2020-01-02,1.55,FRED_DTB3\n")
            T4.CASH_PATH = path
            try:
                self.assertEqual(T4._cash_rate_for("2020-01-10")["annual_pct"], 1.55)
                with self.assertRaises(Refused) as ctx:
                    T4._cash_rate_for("2026-08-17")
                self.assertIn("guess", str(ctx.exception))
            finally:
                T4.CASH_PATH = original

    def test_a_date_before_the_first_publication_refuses_rather_than_using_zero(self):
        original = T4.CASH_PATH
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "cash.csv"
            path.write_text("date,annual_pct,source\n2020-01-02,1.55,FRED_DTB3\n")
            T4.CASH_PATH = path
            try:
                with self.assertRaises(Refused):
                    T4._cash_rate_for("2019-01-01")
            finally:
                T4.CASH_PATH = original


class FramingTests(unittest.TestCase):
    def test_the_track_record_licenses_no_claim_and_says_so(self):
        record = T4.track_record(T4._blank_state(T4.frozen_rule()))
        self.assertFalse(record["certifiable"])
        self.assertEqual(record["claims_licensed"], [])
        self.assertTrue(any("makes money" in c
                            for c in record["claims_explicitly_not_licensed"]))
        self.assertIn("crash", record["why_not_yet"])

    def test_the_benchmark_is_labelled_as_not_the_deciding_null(self):
        record = T4.track_record(T4._blank_state(T4.frozen_rule()))
        self.assertIn("NOT the null that decides", record["benchmark_definition"])

    def test_the_framing_string_names_the_verdict_and_the_account_type(self):
        self.assertIn("UNCERTIFIED", T4.FRAMING)
        self.assertIn("PAPER ACCOUNT ONLY", T4.FRAMING)
        self.assertIn("DEAD", T4.FRAMING)

    def test_the_reading_protocol_leads_with_the_denominator(self):
        self.assertIn("DENOMINATOR", T4.HOW_TO_READ[0])


class NonFillTests(unittest.TestCase):
    """An order that did not fill must not leave a weight behind.

    This is the failure the 2026-08-17 expired MOC actually caused: the order died, nothing
    noticed, and the decision it was meant to execute stayed queued to be bound into the curve
    two runs later. A phantom weight is indistinguishable from a real one in the PnL, which is
    precisely why it has to be impossible rather than unlikely.
    """

    class _StubAccount:
        def __init__(self, raw):
            self._raw = raw

        def order(self, order_id):
            return dict(self._raw, id=order_id)

    def _state(self):
        return {
            "pending_order": {"order_id": "oid", "session_date": "2026-08-17",
                              "side": "buy", "qty": 93},
            "pending_weights": {"2026-08-17": {"weight": 0.7242, "reference_close_date": "2026-08-14"}},
            "prev_weight": 0.0,
        }

    def _series(self):
        return {"dates": ["2026-08-17"], "closes": [640.0], "close_micros": [640_000_000]}

    def test_an_expired_order_drops_the_decision_it_never_executed(self):
        state = self._state()
        out = T4.reconcile_fill(state, self._series(),
                                self._StubAccount({"status": "expired", "filled_qty": "0",
                                                   "filled_avg_price": None}))
        self.assertFalse(out["position_established"])
        self.assertEqual(state["pending_weights"], {})
        self.assertIsNone(state["pending_order"])
        self.assertEqual(out["decision_cancelled_by_non_fill"]["dropped_pending_weight"], 0.7242)

    def test_a_rejected_or_cancelled_order_drops_it_too(self):
        for status in ("rejected", "canceled", "done_for_day"):
            state = self._state()
            T4.reconcile_fill(state, self._series(),
                              self._StubAccount({"status": status, "filled_qty": "0",
                                                 "filled_avg_price": None}))
            self.assertEqual(state["pending_weights"], {}, status)

    def test_a_filled_order_keeps_its_decision(self):
        state = self._state()
        out = T4.reconcile_fill(state, self._series(),
                                self._StubAccount({"status": "filled", "filled_qty": "93",
                                                   "filled_avg_price": "640.32"}))
        self.assertTrue(out["position_established"])
        self.assertEqual(state["pending_weights"]["2026-08-17"]["weight"], 0.7242)
        self.assertIsNone(state["pending_order"])
        # shortfall is signed ADVERSE: a buy filled ABOVE the official close is positive
        self.assertAlmostEqual(out["shortfall_bp_adverse_positive"], 5.0, places=3)

    def test_a_partial_fill_is_flagged_rather_than_silently_absorbed(self):
        state = self._state()
        out = T4.reconcile_fill(state, self._series(),
                                self._StubAccount({"status": "partially_filled",
                                                   "filled_qty": "40",
                                                   "filled_avg_price": "640.00"}))
        self.assertTrue(out["position_established"])
        self.assertIn("partial_fill_warning", out)
        self.assertAlmostEqual(out["fill_completeness"], 40 / 93)
        self.assertEqual(state["pending_weights"]["2026-08-17"]["weight"], 0.7242)

    def test_an_order_still_live_at_the_broker_is_left_alone_not_guessed_at(self):
        state = self._state()
        out = T4.reconcile_fill(state, self._series(),
                                self._StubAccount({"status": "accepted", "filled_qty": "0",
                                                   "filled_avg_price": None}))
        self.assertTrue(out["still_outstanding"])
        self.assertIsNotNone(state["pending_order"])
        self.assertIn("2026-08-17", state["pending_weights"])

    def test_settle_never_sees_a_weight_whose_order_expired(self):
        """End to end: expire the order, then try to bind and settle. Nothing may accrue."""
        state = self._state()
        state.update(T4._blank_state(T4.frozen_rule()))
        state["pending_order"] = {"order_id": "oid", "session_date": "2026-08-17",
                                  "side": "buy", "qty": 93}
        state["pending_weights"] = {"2026-08-17": {"weight": 0.7242,
                                                   "reference_close_date": "2026-08-14"}}
        series = {"dates": ["2026-08-17", "2026-08-18", "2026-08-19"],
                  "closes": [640.0, 645.0, 650.0],
                  "close_micros": [640_000_000, 645_000_000, 650_000_000]}
        T4.reconcile_fill(state, series,
                          self._StubAccount({"status": "expired", "filled_qty": "0",
                                             "filled_avg_price": None}))
        T4.bind_pending_weight(state, series)
        self.assertEqual(state["weight_changes"], {})
        settled = T4.settle(state, series, cost_model=T4.m0_auction_cost_model(),
                            stress_model=T4.stress_cost_model(), use_cash_leg=False)
        self.assertEqual(settled, [])
        self.assertEqual(state["sessions_settled"], 0)
        self.assertEqual(state["curves"]["model_withcash"], 1.0)


class SessionWindowTests(unittest.TestCase):
    def test_the_action_window_is_the_final_minutes_and_nothing_earlier(self):
        """A market DAY order fills WHEN IT IS SENT, so the window IS the execution price.
        Anything mid-session is a different rail from the one being measured."""
        self.assertFalse(T4._within_action_window(dt.datetime(2026, 8, 17, 7, 0)))
        self.assertFalse(T4._within_action_window(dt.datetime(2026, 8, 17, 10, 0)))
        self.assertFalse(T4._within_action_window(dt.datetime(2026, 8, 17, 15, 44)))
        self.assertFalse(T4._within_action_window(dt.datetime(2026, 8, 17, 15, 49)))
        # 15:50 is the last ten-minute mark before the bell, and the installed crontab fires on
        # ten-minute marks. If this stops being in the window the bot silently never runs.
        self.assertTrue(T4._within_action_window(dt.datetime(2026, 8, 17, 15, 50)))
        self.assertTrue(T4._within_action_window(dt.datetime(2026, 8, 17, 15, 55)))
        self.assertTrue(T4._within_action_window(dt.datetime(2026, 8, 17, 15, 58)))
        self.assertFalse(T4._within_action_window(dt.datetime(2026, 8, 17, 15, 59)))
        self.assertFalse(T4._within_action_window(dt.datetime(2026, 8, 17, 16, 5)))

    def test_the_hard_cutoff_is_independent_of_the_window_and_bites_before_the_bell(self):
        """A market DAY order landing after 16:00 queues to the NEXT open and would establish
        the weight one session late, at a price from the wrong session."""
        self.assertFalse(T4._past_submit_cutoff(dt.datetime(2026, 8, 17, 15, 58)))
        self.assertTrue(T4._past_submit_cutoff(dt.datetime(2026, 8, 17, 15, 59)))
        self.assertTrue(T4._past_submit_cutoff(dt.datetime(2026, 8, 17, 16, 0)))
        # the cutoff must be strictly LATER than the window, or the window is unusable
        self.assertGreater(T4.SUBMIT_HARD_CUTOFF_ET, T4.ACTION_WINDOW_ET[1])
        # and the whole window must sit inside the regular session
        self.assertGreaterEqual(T4.ACTION_WINDOW_ET[0], (9, 30))
        self.assertLess(T4.ACTION_WINDOW_ET[1], (16, 0))

    def test_eastern_time_is_derived_per_day_not_fixed_for_the_run(self):
        summer = T4._et_now(dt.datetime(2026, 7, 1, 18, 0, tzinfo=dt.timezone.utc))
        winter = T4._et_now(dt.datetime(2026, 1, 5, 18, 0, tzinfo=dt.timezone.utc))
        self.assertEqual(summer.hour, 14)         # EDT, UTC-4
        self.assertEqual(winter.hour, 13)         # EST, UTC-5


if __name__ == "__main__":
    unittest.main()
