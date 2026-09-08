"""T2 — the backtest harness, with every refusal shown to actually fire.

This programme's standing lesson (FINDINGS §8) is that *a layered guard hides its inner
branches*, and that "no test reaches this branch" is never evidence the branch is dead. So
each guard below is exercised on the failing side, not just the passing one. In particular
`LookaheadAuditTests` proves the audit CATCHES a deliberately leaky strategy — an audit that
has never been shown to fail is not evidence of anything.

Hermetic: the suite-wide network guard (tests/_netguard.py) blocks outbound sockets, so every
test here uses synthetic bars or cache-only loading.
"""
import hashlib
import json
import math
import pathlib
import sys
import tempfile
import unittest
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.trading_bot import (  # noqa: E402
    AlwaysFlat, AlwaysShort, Bar, BuyAndHold, CheatingOracle, CostComponent, CostModel,
    Order, OrderType, Oscillator, PaperBroker, PointInTimeView, Refused, Side,
    SlippageProvenance, Strategy, TrailingSmaCross, annualised_sharpe,
    assert_levels_are_point_in_time,
    assert_no_leakage, bars_per_year, cagr, deflated_sharpe, evaluate, expected_max_sharpe,
    load_env_credentials, lookahead_audit, max_drawdown, moments, orders_for_target,
    paired_excess, permutation_test, retail_taker_costs, run_backtest, single_run,
    stress_ladder, validate_series, walk_forward_folds, walk_forward_run, zero_cost_model,
)
from scripts.trading_bot import costs as tb_costs  # noqa: E402
from scripts.trading_bot import data as tb_data  # noqa: E402
from scripts.trading_bot import frozen as tb_frozen  # noqa: E402
from scripts.trading_bot import stats as tb_stats  # noqa: E402

DAY_NS = 86_400 * 1_000_000_000
BASE_NS = 1_700_000_000 * 1_000_000_000


def make_bars(closes, symbol="TEST", start_ns=BASE_NS, step_ns=DAY_NS, opens=None):
    """Bars whose OPEN is what the engine transacts and marks at. Opens default to closes."""
    opens = opens if opens is not None else list(closes)
    bars = []
    for i, (o, c) in enumerate(zip(opens, closes)):
        bars.append(Bar(
            symbol=symbol, ts_ns=start_ns + i * step_ns,
            open_micros=int(o), high_micros=int(max(o, c)) + 1_000,
            low_micros=int(min(o, c)) - 1_000, close_micros=int(c),
            volume_shares=1_000_000,
        ))
    return bars


def geometric(n, start=100_000_000, num=101, den=100):
    price, out = start, []
    for _ in range(n):
        out.append(price)
        price = price * num // den
    return out


class InThenOut(Strategy):
    """Long on the first decidable bar, flat forever after: exactly ONE round trip.

    It exists for the per-side cost tests. `Oscillator` reverses every bar, which makes entry
    and exit turnover equal by construction and so cannot tell a per-side charge apart from a
    doubled one-sided charge. This can."""

    name = "in_then_out"
    warmup_bars = 0

    def on_bar(self, view, state):
        return Fraction(1) if view.index == 0 else Fraction(0)


# ---------------------------------------------------------------------------
# Guardrail 2 — the frozen artifact is consumed, never edited
# ---------------------------------------------------------------------------

class FrozenPinTests(unittest.TestCase):
    def test_pinned_harness_matches_its_preregistered_hash(self):
        prereg = json.loads((ROOT / "research" / "B22B_SLIPPAGE_PREREGISTRATION.json").read_text())
        expected = prereg["pinned_artifact"]["sha256"]
        actual = hashlib.sha256(
            (ROOT / "scripts" / "b22b_slippage_harness.py").read_bytes()
        ).hexdigest()
        self.assertEqual(expected, actual)
        self.assertTrue(expected.startswith("a0f1b4c4"), "the guardrail's short sha must hold")
        self.assertEqual(tb_frozen.PINNED_SHA256, expected)

    def test_pin_verification_refuses_a_modified_artifact(self):
        """The guard must fire on the failing side, not merely exist."""
        original = tb_frozen.PINNED_PATH
        tampered = ROOT / "tests" / "__tampered_b22b.py"
        tampered.write_text("MICROS = 1\n")
        try:
            tb_frozen.PINNED_PATH = tampered
            with self.assertRaises(tb_frozen.PinBroken):
                tb_frozen._load_pinned()
        finally:
            tb_frozen.PINNED_PATH = original
            tampered.unlink()

    def test_rig_consumes_frozen_definitions_rather_than_redefining_them(self):
        self.assertIs(tb_frozen.to_micros, tb_frozen.b22b.to_micros)
        self.assertIs(tb_frozen.atr_micros, tb_frozen.b22b.atr_micros)
        self.assertIs(tb_frozen.Refused, tb_frozen.b22b.Refused)
        self.assertEqual(tb_frozen.LATENCY_LADDER_MS, (0, 100, 500, 1000))

    def test_frozen_fail_closed_behaviour_survives_the_bridge(self):
        with self.assertRaises(Refused):
            tb_frozen.to_micros(None)
        with self.assertRaises(Refused):
            tb_frozen.true_range_micros(10, 5, None)
        with self.assertRaises(Refused):
            tb_frozen.percentile_by_index([], 50, 100)


# ---------------------------------------------------------------------------
# Guardrail 1, layer 1 — the clamped view
# ---------------------------------------------------------------------------

class PointInTimeViewTests(unittest.TestCase):
    def setUp(self):
        self.series = validate_series(make_bars(geometric(20)))
        self.view = PointInTimeView(self.series, 5)

    def test_length_is_the_visible_past_not_the_series(self):
        self.assertEqual(len(self.view), 6)
        self.assertEqual(self.view.index, 5)
        self.assertEqual(self.view.now, self.series[5])

    def test_future_index_refuses(self):
        with self.assertRaises(Refused) as ctx:
            self.view[6]
        self.assertIn("LOOKAHEAD REFUSED", str(ctx.exception))
        with self.assertRaises(Refused):
            self.view[19]

    def test_negative_index_is_relative_to_now_not_to_the_end_of_the_series(self):
        self.assertEqual(self.view[-1], self.series[5])
        self.assertEqual(self.view[-6], self.series[0])
        with self.assertRaises(Refused):
            self.view[-7]

    def test_slicing_and_iteration_refuse(self):
        with self.assertRaises(Refused):
            self.view[0:3]
        with self.assertRaises(Refused):
            list(self.view)

    def test_history_refuses_a_window_that_has_not_printed(self):
        self.assertEqual(len(self.view.history(6)), 6)
        with self.assertRaises(Refused):
            self.view.history(7)
        with self.assertRaises(Refused):
            self.view.history(0)

    def test_view_has_no_dict_and_no_bars_attribute(self):
        self.assertFalse(hasattr(self.view, "__dict__"))
        for name in ("bars", "series", "_series", "data"):
            self.assertFalse(hasattr(self.view, name), name)

    def test_view_refuses_a_mutable_backing_sequence(self):
        with self.assertRaises(Refused):
            PointInTimeView(list(self.series), 3)


# ---------------------------------------------------------------------------
# Guardrail 1, layer 2 — a decision cannot be filled at the price that made it
# ---------------------------------------------------------------------------

class ExecutionLagTests(unittest.TestCase):
    def test_zero_lag_is_refused_and_has_no_override(self):
        bars = make_bars(geometric(50))
        with self.assertRaises(Refused) as ctx:
            run_backtest(bars, BuyAndHold, zero_cost_model(), execution_lag_bars=0)
        self.assertIn("already printed", str(ctx.exception))

    def test_decision_at_bar_i_is_filled_at_bar_i_plus_lag_open(self):
        """Position effective at each mark point traces back to a decision `lag` bars earlier."""
        bars = make_bars(geometric(30))
        result = run_backtest(bars, Oscillator, zero_cost_model(), execution_lag_bars=1)
        decisions = dict(result.targets)
        first_mark = result.warmup_bars + result.execution_lag_bars
        for offset, pos in enumerate(result.positions):
            source = first_mark + offset - result.execution_lag_bars
            self.assertEqual(pos, decisions[source], f"mark {offset}")

    def test_returns_are_open_to_open_so_fill_and_mark_are_the_same_tick(self):
        closes = [100_000_000, 200_000_000, 300_000_000, 400_000_000]
        opens = [100_000_000, 110_000_000, 121_000_000, 133_100_000]
        bars = make_bars(closes, opens=opens)
        result = run_backtest(bars, BuyAndHold, zero_cost_model())
        # Marks start at bar 1 (warmup 0 + lag 1): segments are open[1]->open[2], open[2]->open[3].
        self.assertEqual(result.market_returns, (
            Fraction(opens[2] - opens[1], opens[1]),
            Fraction(opens[3] - opens[2], opens[2]),
        ))
        # The close-to-close move over the same bars is enormous and must appear nowhere.
        self.assertNotIn(Fraction(closes[2] - closes[1], closes[1]), result.market_returns)


# ---------------------------------------------------------------------------
# Guardrail 1, layer 3 — the future-scramble audit, shown to catch a real leak
# ---------------------------------------------------------------------------

class LookaheadAuditTests(unittest.TestCase):
    def test_honest_strategies_pass(self):
        bars = validate_series(make_bars(geometric(200)))
        for factory in (BuyAndHold, AlwaysFlat, AlwaysShort, Oscillator,
                        lambda: TrailingSmaCross(20)):
            report = lookahead_audit(bars, factory, warmup=factory().warmup_bars, lag=1)
            self.assertEqual(report["verdict"], "PASS")
            self.assertGreater(report["decisions_compared"], 0)

    def test_the_audit_catches_a_leak_that_bypasses_the_view_entirely(self):
        """The negative control. CheatingOracle never asks the view for a future bar.

        It closes over the raw series, so layer 1 cannot see it. Only re-running against a
        different future catches it — which is the whole reason layer 3 exists.
        """
        bars = validate_series(make_bars(geometric(200)))
        with self.assertRaises(Refused) as ctx:
            lookahead_audit(bars, CheatingOracle, warmup=0, lag=1)
        self.assertIn("LOOKAHEAD DETECTED", str(ctx.exception))

    def test_a_zero_arg_factory_holding_the_real_bars_is_the_audits_stated_blind_spot(self):
        """Recorded because it is how the first version of this audit was found toothless.

        A factory that closes over the REAL series keeps the real future in both runs, so the
        scramble changes nothing it reads and the audit reports PASS on a strategy that is
        plainly cheating. That is why `build_strategy` exists and why the contract is 'take
        the series as a constructor argument'. Asserting the blind spot keeps it documented
        rather than rediscovered.
        """
        bars = validate_series(make_bars(geometric(200)))
        blind = lookahead_audit(bars, lambda: CheatingOracle(bars), warmup=0, lag=1)
        self.assertEqual(blind["verdict"], "PASS")
        with self.assertRaises(Refused):
            lookahead_audit(bars, CheatingOracle, warmup=0, lag=1)

    def test_run_backtest_refuses_rather_than_reporting_a_leaky_result(self):
        bars = validate_series(make_bars(geometric(200)))
        with self.assertRaises(Refused):
            run_backtest(bars, CheatingOracle, zero_cost_model())

    def test_an_audit_with_no_probes_refuses(self):
        bars = validate_series(make_bars(geometric(60)))
        with self.assertRaises(Refused):
            lookahead_audit(bars, BuyAndHold, warmup=0, lag=1, probes=0)

    def test_audit_is_deterministic(self):
        bars = validate_series(make_bars(geometric(120)))
        a = lookahead_audit(bars, lambda: TrailingSmaCross(10), warmup=9, lag=1, seed=7)
        b = lookahead_audit(bars, lambda: TrailingSmaCross(10), warmup=9, lag=1, seed=7)
        self.assertEqual(a["probe_bars"], b["probe_bars"])
        self.assertEqual(a["decisions_compared"], b["decisions_compared"])

    def test_warmup_is_honoured_so_a_short_window_never_produces_a_decision(self):
        bars = make_bars(geometric(150))
        result = run_backtest(bars, lambda: TrailingSmaCross(100), zero_cost_model())
        self.assertEqual(result.warmup_bars, 99)
        self.assertEqual(min(i for i, _ in result.targets), 99)

    def test_a_strategy_whose_warmup_cannot_be_met_refuses(self):
        bars = make_bars(geometric(50))
        with self.assertRaises(Refused):
            run_backtest(bars, lambda: TrailingSmaCross(100), zero_cost_model())


# ---------------------------------------------------------------------------
# Bar and series integrity
# ---------------------------------------------------------------------------

class SeriesIntegrityTests(unittest.TestCase):
    def test_corrupt_bar_refuses(self):
        with self.assertRaises(Refused):
            Bar("X", BASE_NS, 100, 90, 95, 95, 1).validate()        # low > high... high < open
        with self.assertRaises(Refused):
            Bar("X", BASE_NS, 100, 110, 90, 200, 1).validate()      # close outside range
        with self.assertRaises(Refused):
            Bar("X", BASE_NS, 0, 10, 0, 5, 1).validate()            # non-positive open

    def test_out_of_order_or_duplicate_timestamps_refuse(self):
        bars = make_bars(geometric(5))
        shuffled = [bars[0], bars[2], bars[1], bars[3], bars[4]]
        with self.assertRaises(Refused):
            validate_series(shuffled)
        with self.assertRaises(Refused):
            validate_series([bars[0], bars[0], bars[1]])

    def test_a_mixed_symbol_series_refuses(self):
        a = make_bars(geometric(3), symbol="AAA")
        b = make_bars(geometric(3), symbol="BBB", start_ns=BASE_NS + 10 * DAY_NS)
        with self.assertRaises(Refused):
            validate_series(a + b)

    def test_from_alpaca_crosses_the_float_boundary_exactly_once_per_field(self):
        bar = Bar.from_alpaca("SPY", {
            "t": "2025-03-10T13:30:00Z", "o": 570.12, "h": 571.5, "l": 569.01,
            "c": 570.99, "v": 1234567, "n": 900, "vw": 570.4,
        })
        self.assertEqual(bar.open_micros, 570_120_000)
        self.assertEqual(bar.close_micros, 570_990_000)
        self.assertIsInstance(bar.open_micros, int)
        self.assertEqual(bar.ts_ns % 1_000_000_000, 0)

    def test_a_missing_field_refuses_rather_than_defaulting(self):
        with self.assertRaises(Refused):
            Bar.from_alpaca("SPY", {"t": "2025-03-10T13:30:00Z", "o": 1, "h": 1, "l": 1, "c": 1})


# ---------------------------------------------------------------------------
# Accounting — hand-checkable arithmetic
# ---------------------------------------------------------------------------

class AccountingTests(unittest.TestCase):
    def test_always_flat_is_exactly_zero_everywhere(self):
        bars = make_bars(geometric(40))
        r = run_backtest(bars, AlwaysFlat, retail_taker_costs())
        self.assertTrue(all(x == 0 for x in r.returns))
        self.assertTrue(all(c == 0 for c in r.costs))
        self.assertEqual(r.total_turnover(), 0)
        self.assertEqual(r.equity_curve()[-1], 1.0)

    def test_buy_and_hold_turnover_is_exactly_one_round(self):
        bars = make_bars(geometric(40))
        r = run_backtest(bars, BuyAndHold, retail_taker_costs())
        self.assertEqual(r.total_turnover(), Fraction(1))
        self.assertTrue(all(p == 1 for p in r.positions))

    def test_buy_and_hold_gross_equals_the_asset_open_to_open(self):
        prices = geometric(30)
        bars = make_bars(prices)
        r = run_backtest(bars, BuyAndHold, zero_cost_model())
        exact = Fraction(1)
        for g in r.gross_returns:
            exact *= 1 + g
        # marks run from bar 1 to the last bar
        self.assertEqual(exact, Fraction(prices[-1], prices[1]))

    def test_zero_cost_model_charges_nothing_even_on_heavy_turnover(self):
        bars = make_bars(geometric(60))
        r = run_backtest(bars, Oscillator, zero_cost_model())
        self.assertTrue(all(c == 0 for c in r.costs))
        self.assertGreater(r.total_turnover(), 50)

    def test_oscillator_turnover_is_two_per_bar_after_the_first(self):
        bars = make_bars(geometric(21))
        r = run_backtest(bars, Oscillator, zero_cost_model())
        self.assertEqual(r.turnover[0], Fraction(1))
        self.assertTrue(all(t == 2 for t in r.turnover[1:]))

    def test_commission_is_per_share_and_independent_of_account_size(self):
        model = retail_taker_costs(half_spread_bp=0, commission_micros_per_share=3500)
        # 1.0 of equity at $100.00 buys 1/100 shares per dollar; cost fraction = 0.0035/100
        self.assertEqual(
            model.commission_fraction(100_000_000, Fraction(1)),
            Fraction(3500, 100_000_000),
        )
        self.assertEqual(
            model.trade_cost_fraction(100_000_000, entry_turnover=Fraction(1),
                                      exit_turnover=Fraction(0)),
            Fraction(3500, 100_000_000),
        )

    def test_half_spread_is_charged_on_traded_notional_on_both_sides(self):
        model = retail_taker_costs(half_spread_bp="2.5", commission_micros_per_share=0)
        for entry, exit_ in ((Fraction(2), Fraction(0)), (Fraction(0), Fraction(2)),
                             (Fraction(1), Fraction(1))):
            self.assertEqual(
                model.trade_cost_fraction(50_000_000, entry_turnover=entry, exit_turnover=exit_),
                Fraction(2) * Fraction(25, 10) / 10_000,
                f"entry {entry} / exit {exit_} must cost the same 2.5 bp per unit traded",
            )

    def test_borrow_accrues_on_calendar_days_including_the_weekend(self):
        """Fri -> Mon is three calendar days of borrow, not one trading day."""
        model = retail_taker_costs(borrow_annual_rate="0.0365")
        self.assertEqual(model.borrow_cost_fraction(Fraction(-1), Fraction(3)),
                         Fraction(365, 10000) * 3 / 365)
        self.assertEqual(model.borrow_cost_fraction(Fraction(1), Fraction(3)), 0)

    def test_short_position_pays_borrow_over_a_real_weekend_gap(self):
        bars = [
            Bar("X", BASE_NS + 0 * DAY_NS, 100_000_000, 100_001_000, 99_999_000, 100_000_000, 1),
            Bar("X", BASE_NS + 1 * DAY_NS, 100_000_000, 100_001_000, 99_999_000, 100_000_000, 1),
            Bar("X", BASE_NS + 4 * DAY_NS, 100_000_000, 100_001_000, 99_999_000, 100_000_000, 1),
            Bar("X", BASE_NS + 5 * DAY_NS, 100_000_000, 100_001_000, 99_999_000, 100_000_000, 1),
        ]
        model = retail_taker_costs(half_spread_bp=0, borrow_annual_rate="0.0365")
        r = run_backtest(bars, AlwaysShort, model)
        # segments: bar1->bar2 spans 3 calendar days, bar2->bar3 spans 1
        self.assertEqual(r.costs[0], Fraction(365, 10000) * 3 / 365)
        self.assertEqual(r.costs[1], Fraction(365, 10000) * 1 / 365)

    def test_costs_are_never_negative_and_a_negative_input_refuses(self):
        model = retail_taker_costs()
        with self.assertRaises(Refused):
            model.trade_cost_fraction(100_000_000, entry_turnover=Fraction(-1),
                                      exit_turnover=Fraction(0))
        with self.assertRaises(Refused):
            model.borrow_cost_fraction(Fraction(-1), Fraction(-3))
        with self.assertRaises(Refused):
            model.commission_fraction(0, Fraction(1))

    def test_float_equity_curve_agrees_with_the_exact_rational_one(self):
        bars = make_bars(geometric(120))
        r = run_backtest(bars, Oscillator, retail_taker_costs())
        approx, exact = r.equity_curve(), r.equity_curve_exact()
        self.assertEqual(len(approx), len(exact))
        for a, e in zip(approx, exact):
            self.assertAlmostEqual(a, float(e), delta=abs(float(e)) * 1e-12 + 1e-15)

    def test_every_per_bar_return_is_exact(self):
        bars = make_bars(geometric(30))
        r = run_backtest(bars, Oscillator, retail_taker_costs())
        for series in (r.returns, r.gross_returns, r.costs, r.market_returns, r.turnover):
            self.assertTrue(all(isinstance(x, Fraction) for x in series))


# ---------------------------------------------------------------------------
# Cost provenance — no unsourced number, and no assumption wearing a measurement's clothes
# ---------------------------------------------------------------------------

class CostProvenanceTests(unittest.TestCase):
    """B22B has now been RUN, so the old test here -- 'MEASURED_B22B always refuses' -- would
    be asserting a fact that stopped being true. What must stay true is the RULE behind it: the
    label is available only while the artifact backing it is. So the gate is tested on both
    sides, including the side where the artifact is taken away."""

    def test_a_b22b_measurement_is_available_now_that_the_pass_has_run(self):
        component = CostComponent("x", Fraction(5), "bp",
                                  SlippageProvenance.MEASURED_B22B, "B22B result")
        self.assertIs(component.provenance, SlippageProvenance.MEASURED_B22B)

    def test_a_b22b_measurement_refuses_again_if_the_result_artifact_disappears(self):
        original = tb_costs.B22B_RESULT_PATH
        try:
            tb_costs.B22B_RESULT_PATH = original.with_name("_no_such_result.json")
            with self.assertRaises(Refused) as ctx:
                CostComponent("x", Fraction(5), "bp", SlippageProvenance.MEASURED_B22B, "src")
            self.assertIn("does not exist", str(ctx.exception))
        finally:
            tb_costs.B22B_RESULT_PATH = original

    def test_a_partial_b22b_pass_is_not_the_measurement(self):
        """The first pass died at day 11 of 30 with everything in memory. A rig that would have
        accepted that as 'the measurement' is the thing being guarded against here."""
        original = tb_costs.B22B_RESULT_PATH
        partial = pathlib.Path(tempfile.mkdtemp()) / "partial.json"
        partial.write_text(json.dumps({"days_complete": 11}))
        try:
            tb_costs.B22B_RESULT_PATH = partial
            with self.assertRaises(Refused) as ctx:
                CostComponent("x", Fraction(5), "bp", SlippageProvenance.MEASURED_B22B, "src")
            self.assertIn("11 of the 30", str(ctx.exception))
        finally:
            tb_costs.B22B_RESULT_PATH = original

    def test_the_measured_model_does_not_charge_the_ENTRY_spread_twice(self):
        """B22B prices the fill at the far side of the book against a stop set at a traded
        level, so its number already contains the half-spread. The measured model must
        therefore carry a zero ENTRY half_spread, and must say why in the source string.

        The T6 correction is in the second half of this test: that zero is entry-only, and the
        model must NOT extend it to the exit."""
        model = tb_costs.b22b_measured_costs()
        self.assertEqual(model.entry_half_spread.value, Fraction(0))
        self.assertIn("double-count", model.entry_half_spread.source)
        self.assertGreater(model.exit_half_spread.value, 0,
                           "the exit crosses a real spread; B22B never measured it")

    def test_a_measured_cost_is_never_negative_even_where_the_measurement_was_favourable(self):
        for percentile in ("p10", "p25", "p50", "p75", "p90", "p95"):
            component = tb_costs.measured_extra_slippage(percentile=percentile)
            self.assertGreaterEqual(component.value, 0)

    def test_an_absent_latency_rung_refuses_rather_than_defaulting_to_zero(self):
        with self.assertRaises(Refused):
            tb_costs.measured_extra_slippage(latency_ms="250")

    def test_an_unknown_borrow_tier_refuses(self):
        with self.assertRaises(Refused):
            tb_costs.measured_borrow_annual("free")

    def test_the_borrow_tiers_are_ordered_and_the_htb_tier_is_not_the_etb_one(self):
        """One borrow number for US equities is a fiction; the tiers exist because B22G
        measured an order of magnitude between them."""
        etb = tb_costs.measured_borrow_annual("etb_general_collateral").value
        htb = tb_costs.measured_borrow_annual("htb_median").value
        tail = tb_costs.measured_borrow_annual("htb_p90").value
        self.assertLess(etb, htb)
        self.assertLessEqual(htb, tail)

    def test_a_component_with_no_source_refuses(self):
        with self.assertRaises(Refused):
            CostComponent("x", Fraction(5), "bp", SlippageProvenance.STRESS_LADDER, "")

    def test_a_negative_rate_refuses_under_the_adverse_sign_convention(self):
        with self.assertRaises(Refused):
            retail_taker_costs(half_spread_bp=-1)
        with self.assertRaises(Refused):
            retail_taker_costs(borrow_annual_rate=None)

    def test_every_prebuilt_model_carries_a_provenance_and_a_source_on_every_leg(self):
        for model in (retail_taker_costs(), zero_cost_model(),
                      tb_costs.b22b_measured_costs(), tb_costs.zarattini_paper_costs()):
            report = model.to_report()
            for leg in ("entry_half_spread", "entry_extra_slippage", "exit_half_spread",
                        "exit_extra_slippage", "commission_per_share", "borrow_annual"):
                self.assertIn(report[leg]["provenance"], SlippageProvenance.__members__)
                self.assertTrue(report[leg]["source"].strip())

    def test_the_stress_ladder_produces_monotonically_worse_results(self):
        bars = make_bars(geometric(80))
        finals = []
        for _, model in stress_ladder(retail_taker_costs()):
            finals.append(run_backtest(bars, Oscillator, model).equity_curve()[-1])
        self.assertEqual(finals, sorted(finals, reverse=True))

    def test_zarattini_model_is_the_straw_man_it_claims_to_be(self):
        from scripts.trading_bot.costs import zarattini_paper_costs
        model = zarattini_paper_costs()
        self.assertEqual(model.entry_spread_and_slippage_fraction(), 0)
        self.assertEqual(model.exit_spread_and_slippage_fraction(), 0)
        self.assertEqual(model.round_trip_bp(), 0)
        self.assertEqual(model.borrow_cost_fraction(Fraction(-1), Fraction(365)), 0)
        self.assertGreater(model.commission_fraction(100_000_000, Fraction(1)), 0)


# ---------------------------------------------------------------------------
# T6 — the exit leg is not free. These tests exist to CATCH the old behaviour,
# not to lock it in: every one of them fails against the pre-T6 cost model.
# ---------------------------------------------------------------------------

class PerSideCostTests(unittest.TestCase):
    """The defect: `b22b_measured_costs()` carries `half_spread = 0` because the B22B entry
    measurement already contains the spread, and the engine charged that single side-agnostic
    number to `|target - held|`. So every EXIT -- a stop-loss market order or a market-on-close,
    neither of which B22B ever measured -- crossed the spread for free. The round trip came to
    1.63 bp against a defensible 5.59 bp.

    Each test below is written so that it FAILS if the exit ever goes back to inheriting the
    entry."""

    def test_split_turnover_separates_a_reversal_into_an_exit_and_an_entry(self):
        self.assertEqual(tb_costs.split_turnover(Fraction(1), Fraction(-1)),
                         (Fraction(1), Fraction(1)))
        self.assertEqual(tb_costs.split_turnover(Fraction(0), Fraction(1)),
                         (Fraction(1), Fraction(0)))
        self.assertEqual(tb_costs.split_turnover(Fraction(1), Fraction(0)),
                         (Fraction(0), Fraction(1)))
        self.assertEqual(tb_costs.split_turnover(Fraction(1), Fraction(1, 2)),
                         (Fraction(0), Fraction(1, 2)))
        self.assertEqual(tb_costs.split_turnover(Fraction(1, 2), Fraction(1)),
                         (Fraction(1, 2), Fraction(0)))
        self.assertEqual(tb_costs.split_turnover(Fraction(-1), Fraction(-1)),
                         (Fraction(0), Fraction(0)))

    def test_the_split_always_sums_to_the_old_lumped_turnover(self):
        """The decomposition must REALLOCATE turnover, never invent or lose any."""
        grid = [Fraction(n, 4) for n in range(-8, 9)]
        for previous in grid:
            for target in grid:
                entry, exit_ = tb_costs.split_turnover(previous, target)
                self.assertEqual(entry + exit_, abs(target - previous))
                self.assertGreaterEqual(entry, 0)
                self.assertGreaterEqual(exit_, 0)

    def test_a_lumped_turnover_is_refused_rather_than_charged_the_cheaper_side(self):
        """The old call site. It must not silently price an exit at the entry's rate."""
        model = tb_costs.b22b_measured_costs()
        with self.assertRaises(Refused) as ctx:
            model.trade_cost_fraction(50_000_000, Fraction(1))
        self.assertIn("entry_turnover", str(ctx.exception))
        with self.assertRaises(Refused):
            model.trade_cost_fraction(50_000_000)

    def test_a_model_without_an_exit_side_refuses_to_be_built(self):
        with self.assertRaises(Refused) as ctx:
            CostModel(
                entry_half_spread=CostComponent("entry_half_spread", Fraction(0), "bp",
                                                SlippageProvenance.STRESS_LADDER, "s"),
                entry_extra_slippage=CostComponent("entry_extra_slippage", Fraction(1), "bp",
                                                   SlippageProvenance.STRESS_LADDER, "s"),
                commission_per_share=CostComponent("commission_per_share", Fraction(0), "u",
                                                   SlippageProvenance.STRESS_LADDER, "s"),
                borrow_annual=CostComponent("borrow_annual", Fraction(0), "f",
                                            SlippageProvenance.STRESS_LADDER, "s"),
            )
        self.assertIn("exit_half_spread", str(ctx.exception))

    def test_the_measured_exit_costs_MORE_than_the_measured_entry(self):
        """Not a preference: the entry number is a measurement that already contains its
        spread, while the exit is unmeasured AND crosses a spread nobody credited it with."""
        model = tb_costs.b22b_measured_costs()
        self.assertGreater(model.exit_spread_and_slippage_fraction(),
                           model.entry_spread_and_slippage_fraction())
        self.assertGreater(model.exit_extra_slippage.value, 0)
        self.assertIs(model.exit_extra_slippage.provenance,
                      SlippageProvenance.ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG)

    def test_every_tradeable_model_charges_at_least_five_bp_round_trip(self):
        """5 bp is the retail-taker round trip (2 x 2.5 bp half-spread). A model that claims to
        price real trading and comes in under it is claiming price improvement nobody measured.
        The pre-T6 measured model charged 1.63 bp and would fail here."""
        for name, model in (("retail_taker", retail_taker_costs()),
                            ("b22b_measured", tb_costs.b22b_measured_costs())):
            self.assertGreaterEqual(model.round_trip_bp(), Fraction(5), name)

    def test_a_round_trip_in_the_engine_costs_entry_plus_exit_and_not_two_entries(self):
        """End to end. In + out at the same price must cost exactly the sum of the two SIDES."""
        bars = make_bars([100_000_000] * 6)
        model = tb_costs.b22b_measured_costs()
        r = run_backtest(bars, InThenOut, model)
        self.assertEqual(r.total_entry_turnover(), Fraction(1))
        self.assertEqual(r.total_exit_turnover(), Fraction(1))
        self.assertEqual(r.total_turnover(), Fraction(2))
        expected = (model.entry_spread_and_slippage_fraction()
                    + model.exit_spread_and_slippage_fraction())
        self.assertEqual(r.total_cost_fraction(), expected)
        # and the thing that was actually wrong: it is NOT two entries.
        self.assertGreater(r.total_cost_fraction(),
                           2 * model.entry_spread_and_slippage_fraction())

    def test_the_engine_reports_a_split_that_sums_to_its_own_turnover(self):
        bars = make_bars(geometric(40))
        r = run_backtest(bars, Oscillator, tb_costs.b22b_measured_costs())
        self.assertEqual(len(r.entry_turnover), len(r.turnover))
        for entry, exit_, total in zip(r.entry_turnover, r.exit_turnover, r.turnover):
            self.assertEqual(entry + exit_, total)
        self.assertGreater(r.total_exit_turnover(), 0)

    def test_the_stress_ladder_stresses_both_sides(self):
        """A ladder that only moved the entry would leave the unmeasured exit pinned."""
        for bp, model in stress_ladder(retail_taker_costs()):
            self.assertEqual(model.entry_extra_slippage.value, bp)
            self.assertEqual(model.exit_extra_slippage.value, bp)

    def test_the_measured_entry_mean_is_decontaminated_and_the_ladder_is_monotone(self):
        """The headline mean is dragged DOWN by dislocated odd-lot prints, because a print far
        through the stop produces a favourable measured gap. Tightening the filter must never
        make the charged cost cheaper."""
        contaminated = tb_costs.measured_extra_slippage(atr_filter=None)
        one = tb_costs.measured_extra_slippage(atr_filter="1.0").value
        half = tb_costs.measured_extra_slippage(atr_filter="0.5").value
        default = tb_costs.measured_extra_slippage()
        self.assertLess(contaminated.value, one)
        self.assertLess(one, half)
        self.assertLess(half, default.value)
        # +90% on the raw mean: the contamination was worth nearly a doubling of the charge.
        self.assertGreater(default.value, contaminated.value * Fraction(18, 10))
        self.assertIn("CONTAMINATED", contaminated.source)
        self.assertIn("DECONTAMINATED", default.source)
        self.assertIn("TSLA", default.source)

    def test_an_unknown_atr_filter_rung_refuses_rather_than_falling_back(self):
        with self.assertRaises(Refused):
            tb_costs.measured_extra_slippage(atr_filter="0.42")

    def test_the_borrow_string_says_not_shortable_at_alpaca_not_at_any_price(self):
        """'cannot be shorted at any price' is not what an Alpaca flag measures, and 36 of 100
        is the screen INPUT, not the universe the rule met."""
        source = tb_costs.measured_borrow_annual().source
        self.assertIn("NOT SHORTABLE AT ALPACA", source)
        self.assertNotIn("not shortable at any price", source)
        self.assertIn("8 of the 52", source)
        # The old denominator may appear ONLY as the thing being corrected.
        self.assertIn("not 36 of 100", source)
        self.assertIn("LEVERAGED or INVERSE ETPs", source)
        self.assertNotIn("ONDS", source.split("LEVERAGED or INVERSE ETPs")[1].split(")")[0])


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

class StatisticsTests(unittest.TestCase):
    def test_norm_cdf_and_ppf_invert_to_full_double_precision(self):
        for p in (1e-9, 0.001, 0.02, 0.3, 0.5, 0.7, 0.97, 0.999, 1 - 1e-9):
            self.assertAlmostEqual(tb_stats.norm_cdf(tb_stats.norm_ppf(p)), p, places=13)
        self.assertAlmostEqual(tb_stats.norm_cdf(0.0), 0.5, places=15)
        self.assertAlmostEqual(tb_stats.norm_ppf(0.975), 1.959963984540054, places=10)
        with self.assertRaises(Refused):
            tb_stats.norm_ppf(0.0)

    def test_moments_uses_non_excess_kurtosis(self):
        m = moments([1, -1] * 200)
        self.assertAlmostEqual(m["mean"], 0.0, places=12)
        self.assertAlmostEqual(m["skew"], 0.0, places=12)
        self.assertAlmostEqual(m["kurtosis"], 1.0, places=12)  # non-excess; a normal gives 3

    def test_sharpe_of_a_constant_series_refuses_rather_than_dividing_by_zero(self):
        with self.assertRaises(Refused):
            annualised_sharpe([Fraction(1, 100)] * 50, 252)

    def test_annualisation_requires_an_explicit_periods_per_year(self):
        with self.assertRaises(Refused):
            annualised_sharpe([0.01, -0.005] * 50, 0)
        self.assertEqual(bars_per_year("1Day"), 252)
        self.assertEqual(bars_per_year("30Min"), 252 * 13)
        with self.assertRaises(Refused):
            bars_per_year("7Min")

    def test_max_drawdown_finds_the_peak_to_trough(self):
        dd = max_drawdown([1.0, 1.5, 0.75, 1.2])
        self.assertAlmostEqual(dd["max_drawdown"], -0.5)
        self.assertEqual((dd["peak_index"], dd["trough_index"]), (1, 2))

    def test_cagr_uses_calendar_span_not_bar_count(self):
        one_year = int(365.25 * DAY_NS)
        self.assertAlmostEqual(cagr([1.0, 2.0], 0, one_year), 1.0, places=9)
        self.assertAlmostEqual(cagr([1.0, 4.0], 0, 2 * one_year), 1.0, places=9)
        with self.assertRaises(Refused):
            cagr([1.0, 2.0], 100, 100)

    def test_expected_max_sharpe_is_the_chance_ceiling_and_grows_with_the_search(self):
        self.assertEqual(expected_max_sharpe(1, 0.0), 0.0)
        # trials=2, unit variance: (1-g)*Z(0.5) + g*Z(1 - 1/(2e)); Z(0.5) = 0
        expected = tb_stats.EULER_MASCHERONI * tb_stats.norm_ppf(1 - 1 / (2 * math.e))
        self.assertAlmostEqual(expected_max_sharpe(2, 1.0), expected, places=12)
        ladder = [expected_max_sharpe(n, 0.01) for n in (2, 5, 10, 50, 200)]
        self.assertEqual(ladder, sorted(ladder))

    def test_expected_max_sharpe_refuses_to_silently_undo_the_deflation(self):
        with self.assertRaises(Refused):
            expected_max_sharpe(10, 0.0)

    def test_dsr_of_a_zero_mean_symmetric_series_is_one_half(self):
        result = deflated_sharpe([1, -1] * 250, trials=1)
        self.assertAlmostEqual(result["dsr"], 0.5, places=12)
        self.assertEqual(result["name"], "probabilistic Sharpe (single trial)")

    def test_dsr_matches_the_bailey_lopez_de_prado_formula_computed_independently(self):
        returns = [1.0] * 60 + [-1.0] * 40
        n, mean = 100, 0.2
        var = sum((x - mean) ** 2 for x in returns) / (n - 1)
        sr = mean / math.sqrt(var)
        m2 = sum((x - mean) ** 2 for x in returns) / n
        skew = (sum((x - mean) ** 3 for x in returns) / n) / m2 ** 1.5
        kurt = (sum((x - mean) ** 4 for x in returns) / n) / m2 ** 2
        z = (sr - 0.0) * math.sqrt(n - 1) / math.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr * sr)
        got = deflated_sharpe(returns, trials=1)
        self.assertAlmostEqual(got["z"], z, places=10)
        self.assertAlmostEqual(got["dsr"], tb_stats.norm_cdf(z), places=12)
        self.assertAlmostEqual(got["skew"], skew, places=12)
        self.assertAlmostEqual(got["kurtosis_non_excess"], kurt, places=12)

    def test_more_trials_deflate_harder(self):
        returns = [0.01, 0.02, -0.005, 0.015, -0.01] * 60
        one = deflated_sharpe(returns, trials=1)["dsr"]
        many = deflated_sharpe(returns, trials=100, sharpe_variance=0.02)["dsr"]
        self.assertGreater(one, many)

    def test_dsr_refuses_the_wrong_object(self):
        """FINDINGS 5c false-FAIL: a classifier / self-differenced series has no Sharpe."""
        with self.assertRaises(Refused) as ctx:
            deflated_sharpe([0.0] * 100, trials=1)
        self.assertIn("zero-variance", str(ctx.exception))

    def test_permutation_p_is_add_one_corrected_and_never_exactly_zero(self):
        report = permutation_test([1, 0] * 100, [0.01, -0.01] * 100, trials=500, seed=1)
        self.assertGreater(report["p_right_tail"], 0.0)
        self.assertLessEqual(report["p_right_tail"], 1.0)

    def test_constant_exposure_has_no_timing_information(self):
        report = permutation_test([1] * 200, [0.01, -0.005] * 100, trials=500, seed=3)
        self.assertEqual(report["p_right_tail"], 1.0)
        self.assertTrue(report["degenerate_exposure"])

    def test_permutation_is_seed_reproducible(self):
        args = ([1, -1, 0, 1] * 50, [0.01, 0.02, -0.03, 0.005] * 50)
        a = permutation_test(*args, trials=500, seed=11)
        b = permutation_test(*args, trials=500, seed=11)
        self.assertEqual(a["p_right_tail"], b["p_right_tail"])
        self.assertNotEqual(a["p_right_tail"],
                            permutation_test(*args, trials=500, seed=12)["p_right_tail"])

    def test_permutation_refuses_misaligned_or_underpowered_input(self):
        with self.assertRaises(Refused):
            permutation_test([1, 1], [0.1], trials=1000)
        with self.assertRaises(Refused):
            permutation_test([1, 0] * 10, [0.1, 0.2] * 10, trials=10)

    def test_paired_excess_refuses_unaligned_series(self):
        with self.assertRaises(Refused):
            paired_excess([0.1, 0.2], [0.1])


# ---------------------------------------------------------------------------
# The FINDINGS 5c rule, enforced in code rather than remembered
# ---------------------------------------------------------------------------

class BenchmarkDisciplineTests(unittest.TestCase):
    def test_evaluate_requires_a_benchmark(self):
        bars = make_bars(geometric(60))
        r = run_backtest(bars, Oscillator, zero_cost_model())
        with self.assertRaises(Refused) as ctx:
            evaluate(r, None, periods_per_year=252, trials=1)
        self.assertIn("false-PASS", str(ctx.exception))

    def test_buy_and_hold_against_itself_refuses_the_paired_dsr(self):
        """The wiring smoke test's known answer: a self-difference has nothing to test."""
        bars = make_bars(geometric(200))
        cost = zero_cost_model()
        a = run_backtest(bars, BuyAndHold, cost)
        b = run_backtest(bars, BuyAndHold, cost)
        report = evaluate(a, b, periods_per_year=252, trials=1, permutation_trials=500)
        self.assertIn("refused", report["paired_excess_dsr"])
        self.assertIn("why_this_is_correct_behaviour", report["paired_excess_dsr"])

    def test_the_raw_dsr_is_reported_but_named_as_the_flattering_instrument(self):
        """A monotonically rising asset makes the RAW dsr pass while the paired one refuses."""
        bars = make_bars(geometric(200))
        cost = zero_cost_model()
        a = run_backtest(bars, BuyAndHold, cost)
        b = run_backtest(bars, BuyAndHold, cost)
        report = evaluate(a, b, periods_per_year=252, trials=1, permutation_trials=500)
        self.assertIn("raw_dsr_DO_NOT_DECIDE_ON_THIS", report)
        self.assertEqual(report["decision_instrument"], "paired_excess_dsr")

    def test_evaluate_refuses_a_benchmark_run_over_different_bars(self):
        long_bars, short_bars = make_bars(geometric(100)), make_bars(geometric(60))
        cost = zero_cost_model()
        with self.assertRaises(Refused):
            evaluate(run_backtest(long_bars, BuyAndHold, cost),
                     run_backtest(short_bars, BuyAndHold, cost),
                     periods_per_year=252, trials=1)


# ---------------------------------------------------------------------------
# Walk-forward
# ---------------------------------------------------------------------------

class WalkForwardTests(unittest.TestCase):
    def test_folds_are_sequential_non_overlapping_and_purged(self):
        folds = walk_forward_folds(1000, n_folds=5, warmup_bars=20, purge_bars=10,
                                   embargo_bars=5)
        self.assertEqual(len(folds), 5)
        for fold in folds:
            self.assertLess(fold.train_end + fold.purged_bars, fold.test_start)
            self.assertLessEqual(fold.test_start, fold.test_end)
        for prev, cur in zip(folds, folds[1:]):
            self.assertLess(prev.test_end, cur.test_start)
        self.assertEqual(assert_no_leakage(folds)["verdict"], "PASS")

    def test_the_last_fold_reaches_the_end_of_the_sample(self):
        folds = walk_forward_folds(1000, n_folds=4, warmup_bars=0, purge_bars=0, embargo_bars=0)
        self.assertEqual(folds[-1].test_end, 999)

    def test_anchored_train_windows_expand_and_rolling_ones_do_not(self):
        anchored = walk_forward_folds(1000, n_folds=4, warmup_bars=10, purge_bars=0,
                                      embargo_bars=0, anchored=True)
        rolling = walk_forward_folds(1000, n_folds=4, warmup_bars=10, purge_bars=0,
                                     embargo_bars=0, anchored=False)
        self.assertTrue(all(f.train_start == 0 for f in anchored))
        self.assertEqual([f.train_length for f in anchored],
                         sorted(f.train_length for f in anchored))
        self.assertGreater(rolling[-1].train_start, 0)

    def test_gaps_must_be_stated_explicitly(self):
        with self.assertRaises(Refused):
            walk_forward_folds(1000, n_folds=3, warmup_bars=10, purge_bars=None, embargo_bars=0)
        with self.assertRaises(Refused):
            walk_forward_folds(1000, n_folds=3, warmup_bars=10, purge_bars=-1, embargo_bars=0)

    def test_a_sample_too_short_for_the_folds_refuses(self):
        with self.assertRaises(Refused):
            walk_forward_folds(40, n_folds=10, warmup_bars=20, purge_bars=0, embargo_bars=0)

    def test_test_slice_prepends_the_warmup_so_no_fold_starts_cold(self):
        series = validate_series(make_bars(geometric(500)))
        folds = walk_forward_folds(len(series), n_folds=3, warmup_bars=30, purge_bars=0,
                                   embargo_bars=0)
        for fold in folds:
            bars = fold.test_slice(series)
            self.assertEqual(len(bars), fold.test_length + 30)
            self.assertEqual(bars[30].ts_ns, series[fold.test_start].ts_ns)

    def test_a_fold_that_cannot_warm_up_refuses_rather_than_starting_cold(self):
        series = validate_series(make_bars(geometric(200)))
        folds = walk_forward_folds(len(series), n_folds=2, warmup_bars=0, purge_bars=0,
                                   embargo_bars=0)
        greedy = type(folds[0])(
            index=0, train_start=0, train_end=1, test_start=2, test_end=50,
            purged_bars=0, embargoed_bars=0, warmup_bars=100,
        )
        with self.assertRaises(Refused):
            greedy.test_slice(series)

    def test_the_independent_leakage_check_fires_on_a_bad_fold(self):
        good = walk_forward_folds(500, n_folds=2, warmup_bars=0, purge_bars=0, embargo_bars=0)
        bad = [type(good[0])(index=0, train_start=0, train_end=100, test_start=50, test_end=200,
                             purged_bars=0, embargoed_bars=0, warmup_bars=0)]
        with self.assertRaises(Refused):
            assert_no_leakage(bad)


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------

class EndToEndTests(unittest.TestCase):
    def test_walk_forward_buy_and_hold_smoke_test(self):
        bars = make_bars(geometric(800))
        report = walk_forward_run(
            bars, BuyAndHold, retail_taker_costs(), periods_per_year=252,
            n_folds=4, trials=1, permutation_trials=500,
        )
        self.assertEqual(report["walk_forward"]["leakage_check"]["verdict"], "PASS")
        self.assertEqual(len(report["walk_forward"]["folds"]), 4)
        for fold in report["walk_forward"]["folds"]:
            self.assertEqual(fold["lookahead_audit"], "PASS")
        self.assertEqual(report["decision_instrument"],
                         "pooled_out_of_sample.paired_excess_dsr")
        self.assertIn("refused", report["pooled_out_of_sample"]["paired_excess_dsr"])
        self.assertEqual(report["provenance"]["sha256"], tb_frozen.PINNED_SHA256)

    def test_a_real_strategy_produces_a_complete_report(self):
        bars = make_bars(geometric(800, num=1013, den=1000))
        report = walk_forward_run(
            bars, Oscillator, retail_taker_costs(), periods_per_year=252,
            n_folds=3, trials=12, sharpe_variance=0.01, permutation_trials=500,
        )
        pooled = report["pooled_out_of_sample"]
        self.assertIn("dsr", pooled["paired_excess_dsr"])
        self.assertEqual(pooled["paired_excess_dsr"]["trials"], 12)
        self.assertIn("p_right_tail", pooled["permutation"])
        self.assertGreater(pooled["n_out_of_sample_segments"], 0)

    def test_out_of_sample_segments_are_not_double_counted(self):
        bars = make_bars(geometric(600))
        report = walk_forward_run(bars, Oscillator, zero_cost_model(), periods_per_year=252,
                                  n_folds=4, trials=1, permutation_trials=500)
        per_fold = sum(f["strategy"]["n_segments"] for f in report["walk_forward"]["folds"])
        self.assertEqual(per_fold, report["pooled_out_of_sample"]["n_out_of_sample_segments"])

    def test_walk_forward_refuses_a_leaky_strategy(self):
        bars = validate_series(make_bars(geometric(400)))
        with self.assertRaises(Refused):
            walk_forward_run(bars, CheatingOracle, zero_cost_model(),
                             periods_per_year=252, n_folds=2, trials=1)

    def test_benchmark_is_forced_onto_the_strategys_warmup(self):
        """Regression: an SMA(100) against buy-and-hold once paired two different date ranges.

        The benchmark has warmup 0, so it began marking 99 bars before the strategy did, and
        the two legs had different segment counts. A paired difference over different ranges
        cancels nothing -- it adds the benchmark's extra period in as 'excess'.
        """
        bars = make_bars(geometric(900))
        report = walk_forward_run(
            bars, lambda: TrailingSmaCross(100), retail_taker_costs(),
            periods_per_year=252, n_folds=3, trials=1, permutation_trials=500,
        )
        for fold in report["walk_forward"]["folds"]:
            self.assertEqual(fold["strategy"]["n_segments"], fold["benchmark"]["n_segments"])

    def test_a_declared_search_without_its_variance_refuses_instead_of_undeflating(self):
        """trials>1 with no cross-trial variance must refuse, not silently report PSR."""
        bars = make_bars(geometric(600, num=1013, den=1000))
        report = walk_forward_run(
            bars, Oscillator, retail_taker_costs(), periods_per_year=252,
            n_folds=3, trials=40, sharpe_variance=None, permutation_trials=500,
        )
        dsr = report["pooled_out_of_sample"]["paired_excess_dsr"]
        self.assertIn("refused", dsr)
        self.assertIn("undeflated", dsr["refused"] + dsr["why_a_refusal_here_is_correct"])

    def test_a_refused_deflation_does_not_discard_the_paired_sharpe(self):
        """Regression: one shared try block threw away a statistic that had already succeeded."""
        bars = make_bars(geometric(600, num=1013, den=1000))
        report = walk_forward_run(
            bars, Oscillator, retail_taker_costs(), periods_per_year=252,
            n_folds=3, trials=40, sharpe_variance=None, permutation_trials=500,
        )
        pooled = report["pooled_out_of_sample"]
        self.assertIn("refused", pooled["paired_excess_dsr"])
        self.assertIsInstance(pooled["paired_excess_annualised_sharpe"], float)

    def test_single_run_is_labelled_in_sample(self):
        bars = make_bars(geometric(300))
        report = single_run(bars, Oscillator, retail_taker_costs(), periods_per_year=252,
                            trials=1, permutation_trials=500)
        self.assertIn("IN-SAMPLE", report["sample"])

    def test_cli_selftest_runs_without_network_or_credentials(self):
        from scripts.trading_bot.__main__ import main
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["selftest"]), 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["buy_and_hold"]["lookahead_audit"], "PASS")
        self.assertEqual(payload["buy_and_hold"]["total_turnover"], 1.0)


# ---------------------------------------------------------------------------
# Guardrail 3 — credentials and endpoints
# ---------------------------------------------------------------------------

class EndpointAndCredentialTests(unittest.TestCase):
    def test_env_values_are_unwrapped_from_quotes(self):
        tmp = ROOT / "tests" / "__t2_env_fixture"
        tmp.write_text(
            '# comment\nALPACA_API_KEY_ID="PK_QUOTED"\n'
            "ALPACA_API_SECRET_KEY='sk_single'\nOTHER=x\n"
        )
        try:
            import os
            saved = {k: os.environ.pop(k, None)
                     for k in ("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY")}
            try:
                self.assertEqual(load_env_credentials(tmp), ("PK_QUOTED", "sk_single"))
            finally:
                for k, v in saved.items():
                    if v is not None:
                        os.environ[k] = v
        finally:
            tmp.unlink()

    def test_empty_or_absent_credentials_refuse(self):
        tmp = ROOT / "tests" / "__t2_env_empty"
        tmp.write_text('ALPACA_API_KEY_ID=""\nALPACA_API_SECRET_KEY=""\n')
        try:
            import os
            saved = {k: os.environ.pop(k, None)
                     for k in ("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY")}
            try:
                with self.assertRaises(Refused):
                    load_env_credentials(tmp)
            finally:
                for k, v in saved.items():
                    if v is not None:
                        os.environ[k] = v
        finally:
            tmp.unlink()

    def test_the_live_trading_host_is_unreachable_from_the_data_loader(self):
        with self.assertRaises(Refused) as ctx:
            tb_data.assert_data_host("https://api.alpaca.markets")
        self.assertIn("LIVE trading endpoint", str(ctx.exception))
        self.assertEqual(tb_data.assert_data_host(tb_data.ALPACA_DATA_HOST),
                         tb_data.ALPACA_DATA_HOST)

    def test_the_broker_is_paper_only_and_refuses_the_live_host_at_construction(self):
        with self.assertRaises(Refused):
            PaperBroker("https://api.alpaca.markets")
        broker = PaperBroker()
        self.assertTrue(broker.host.startswith("https://paper-api.alpaca.markets"))

    def test_order_submission_is_owner_gated_and_refuses(self):
        broker = PaperBroker()
        order = Order("SPY", Side.BUY, OrderType.MARKET, 10)
        with self.assertRaises(Refused) as ctx:
            broker.submit(order)
        self.assertIn("owner sign-off", str(ctx.exception))

    def test_offline_loading_refuses_rather_than_reaching_the_network(self):
        with self.assertRaises(Refused) as ctx:
            tb_data.load_bars("NOPE", "2020-01-01", "2020-02-01", "1Day",
                              cache_dir=ROOT / "tests" / "__no_such_cache",
                              allow_network=False)
        self.assertIn("allow_network=False", str(ctx.exception))

    def test_point_in_time_level_filter_refuses_on_an_adjusted_series(self):
        with self.assertRaises(Refused) as ctx:
            assert_levels_are_point_in_time({"adjustment": "all"})
        self.assertIn("lookahead", str(ctx.exception))
        assert_levels_are_point_in_time({"adjustment": "raw"})    # must not raise


class OrderTranslationTests(unittest.TestCase):
    def test_orders_round_share_count_down_so_risk_is_never_exceeded(self):
        orders = orders_for_target("SPY", Fraction(1), Fraction(0),
                                   equity_micros=1_000_000_000, price_micros=300_000_000,
                                   ts_ns=BASE_NS)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].quantity_shares, 3)          # 1000/300 = 3.33 -> 3
        self.assertIs(orders[0].side, Side.BUY)

    def test_no_order_is_emitted_for_no_change_or_a_sub_share_change(self):
        self.assertEqual(orders_for_target("SPY", Fraction(1), Fraction(1),
                                           1_000_000_000, 300_000_000, BASE_NS), [])
        self.assertEqual(orders_for_target("SPY", Fraction(1, 1000), Fraction(0),
                                           1_000_000_000, 300_000_000, BASE_NS), [])

    def test_a_reduction_becomes_a_sell(self):
        orders = orders_for_target("SPY", Fraction(-1), Fraction(1),
                                   1_000_000_000, 100_000_000, BASE_NS)
        self.assertIs(orders[0].side, Side.SELL)
        self.assertEqual(orders[0].quantity_shares, 20)

    def test_malformed_orders_refuse(self):
        with self.assertRaises(Refused):
            Order("SPY", Side.BUY, OrderType.MARKET, 0)
        with self.assertRaises(Refused):
            Order("SPY", Side.BUY, OrderType.LIMIT, 10)
        with self.assertRaises(Refused):
            Order("SPY", Side.BUY, OrderType.STOP, 10)
        with self.assertRaises(Refused):
            Order("SPY", Side.BUY, OrderType.MARKET, 10, limit_micros=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
