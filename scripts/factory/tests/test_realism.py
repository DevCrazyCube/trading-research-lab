"""Tests for scripts/factory/realism.py — the drift-aware account simulator.

  * the known answers the contract names: the EUR 2 minimum fee on a EUR 300 order = 66.7 bp; a lot
    step that rounds a target to zero; the ideal venue with a trade on every print reproduces
    `engine.backtest`'s gross (price + carry) return;
  * hand-worked accounts: one instrument with every friction; two instruments on a monthly mask with
    hand-computed DRIFT; a Friday -> Monday financing gap;
  * an independent pure-Python reference account, compared on random cases (masks, bands, lots,
    minimum fees, exec prices, carry, contributions);
  * "unknown is not zero": `VenueSpec`, `from_json`, and the real landscape file.

Run:  cd /home/anont/meme && research/factory/.venv/bin/python -m pytest scripts/factory/tests/test_realism.py -q
"""
from __future__ import annotations

import json
import math
import pathlib

import numpy as np
import pandas as pd
import pytest

from scripts.factory import portfolio
from scripts.factory.engine import Refused, backtest
from scripts.factory.panel import PanelBundle
from scripts.factory.realism import ALWAYS_REQUIRED, COST_FIELDS, AccountResult, VenueSpec, simulate_account

VENUES_JSON = pathlib.Path(__file__).resolve().parents[3] / "research" / "factory" / "landscape" / "venues.json"


def panel_of(prices: dict, ppy: int = 365, carry=None, tbill=None, meta=None, start="2024-01-01", freq="D",
             index=None) -> PanelBundle:
    n = len(next(iter(prices.values())))
    idx = index if index is not None else pd.date_range(start, periods=n, freq=freq, tz="UTC")
    m = {"periods_per_year": ppy}
    m.update(meta or {})
    return PanelBundle(
        "REAL", pd.DataFrame(prices, index=idx, dtype=float),
        carry=None if carry is None else pd.DataFrame(carry, index=idx, dtype=float),
        tbill=None if tbill is None else pd.Series(tbill, index=idx, dtype=float, name="tbill"), meta=m,
    )


def weights(panel: PanelBundle, cols: dict) -> pd.DataFrame:
    return pd.DataFrame(cols, index=panel.prices.index, dtype=float)


def rows(panel: PanelBundle, *true_rows: int) -> pd.Series:
    """A rebalance mask that is True on the given row positions only."""
    mask = np.zeros(len(panel.prices), dtype=bool)
    mask[list(true_rows)] = True
    return pd.Series(mask, index=panel.prices.index)


def frictionless(**kw) -> VenueSpec:
    """An explicit zero-friction venue with a FINITE leverage cap, to be overridden field by field."""
    base = dict(fee_bp=0.0, min_fee=0.0, half_spread_bp=0.0, lot_step=0.0, min_notional=0.0, contract_notional=1.0,
                financing_long_bp_year=0.0, financing_short_bp_year=0.0, leverage_cap=1e9)
    base.update(kw)
    return VenueSpec(**base)


# --------------------------------------------------------------------------------------------------
# The three known answers named in the contract
# --------------------------------------------------------------------------------------------------
def test_minimum_fee_on_a_small_order_is_66_7_bp():
    # EUR 1,000 account, target 30 % -> a EUR 300 order. Commission 5 bp = EUR 0.15, below the EUR 2 minimum:
    #   fee = max(2.00, 0.15) = EUR 2.00 = 2/300 = 66.7 bp of the order (and 20 bp of the account).
    panel = panel_of({"ETF": [10.0, 10.0, 10.0]})
    w = weights(panel, {"ETF": [0.3, 0.3, 0.3]})
    venue = frictionless(fee_bp=5.0, min_fee=2.0, leverage_cap=1.0)
    res = simulate_account(panel, w, equity0=1000.0, venue=venue, rebalance_mask=rows(panel, 1))   # one trade, print 1
    assert isinstance(res, AccountResult)
    assert res.units["ETF"].tolist() == [0.0, 30.0, 30.0]                # bought at print 1 (decision 0, lag 1)
    assert res.flows["fees"].tolist() == [0.0, 2.0, 0.0] and res.cost_breakdown["fees"] == 2.0
    assert res.cost_breakdown["traded_notional"] == pytest.approx(300.0)
    assert res.cost_breakdown["fees_bp_of_traded_notional"] == pytest.approx(66.6667, abs=1e-3)
    assert res.equity.tolist() == [1000.0, 998.0, 998.0]
    assert res.meta["n_orders"] == 1 and res.meta["n_orders_at_min_fee"] == 1
    # the cost of the trade is booked in the first row the position earns: net[2] = 998/1000 - 1 = -20 bp
    assert res.net.tolist() == pytest.approx([0.0, 0.0, -0.002]) and res.gross.tolist() == [0.0, 0.0, 0.0]
    # the same book on EUR 10,000: order 3,000 -> max(2, 1.50) = 2 -> 6.67 bp ; on EUR 100,000: 30,000 -> 15 -> 5 bp
    mid = simulate_account(panel, w, equity0=10_000.0, venue=venue, rebalance_mask=rows(panel, 1))
    big = simulate_account(panel, w, equity0=100_000.0, venue=venue, rebalance_mask=rows(panel, 1))
    assert mid.cost_breakdown["fees_bp_of_traded_notional"] == pytest.approx(6.6667, abs=1e-3)
    assert big.cost_breakdown["fees"] == pytest.approx(15.0) and big.meta["n_orders_at_min_fee"] == 0
    assert big.cost_breakdown["fees_bp_of_traded_notional"] == pytest.approx(5.0)
    # WITHOUT a mask the account re-balances on every print: the fee just paid lowered equity to 998, so "30 %"
    # is now 29.94 units — a EUR 0.60 order that costs another EUR 2 minimum fee. A no-trade band stops that.
    every = simulate_account(panel, w, equity0=1000.0, venue=venue)
    assert every.units["ETF"].tolist() == pytest.approx([0.0, 30.0, 29.94]) and every.cost_breakdown["fees"] == 4.0
    banded = simulate_account(panel, w, equity0=1000.0, venue=venue, no_trade_band=0.05)
    assert banded.units["ETF"].tolist() == [0.0, 30.0, 30.0] and banded.cost_breakdown["fees"] == 2.0
    assert banded.meta["n_trades_skipped_in_band"] == 1


def test_lot_step_that_rounds_the_target_to_zero_leaves_the_account_flat_and_says_so():
    # price 500, whole units only. 30 % of EUR 1,000 = EUR 300 = 0.6 unit -> rounds to 0: nothing is bought.
    panel = panel_of({"FUT": [500.0, 500.0, 550.0, 605.0]})
    w = weights(panel, {"FUT": [0.3, 0.3, 0.3, 0.3]})
    venue = frictionless(lot_step=1.0, fee_bp=5.0, min_fee=2.0, leverage_cap=1.0)
    res = simulate_account(panel, w, equity0=1000.0, venue=venue)
    assert (res.units["FUT"] == 0.0).all() and (res.equity == 1000.0).all() and (res.net == 0.0).all()
    # tried on each of the three trade rows (prints 1, 2, 3), rounded to zero each time, no order ever sent
    assert res.meta["n_orders"] == 0 and res.meta["n_targets_rounded_to_zero"] == 3
    assert res.meta["targets_rounded_to_zero_by_instrument"] == {"FUT": 3}
    # the ideal book made money (the price rose 21 %): the whole of it is tracking error
    assert res.ideal_net.sum() == pytest.approx(0.3 * 0.10 + 0.3 * 0.10) and res.tracking["mean_gap_ann"] < 0
    # EUR 2,000: 600/500 = 1.2 -> 1 unit (towards zero) ; EUR 5,000: 1500/500 = 3 units exactly
    assert simulate_account(panel, w, equity0=2000.0, venue=venue).units["FUT"].iloc[1] == 1.0
    assert simulate_account(panel, w, equity0=5000.0, venue=venue).units["FUT"].iloc[1] == 3.0
    # shorts round towards zero too: -0.3 * 2,000 / 500 = -1.2 -> -1
    short = simulate_account(panel, -w, equity0=2000.0, venue=venue)
    assert short.units["FUT"].iloc[1] == -1.0
    # a fractional lot step: 0.1 units -> 300/500 = 0.6 exactly (no float under-rounding to 0.5)
    tenth = simulate_account(panel, w, equity0=1000.0, venue=frictionless(lot_step=0.1))
    assert tenth.units["FUT"].iloc[1] == pytest.approx(0.6, abs=1e-12)


def random_case(seed: int):
    rng = np.random.default_rng(seed)
    T, N = int(rng.integers(40, 120)), int(rng.integers(1, 6))
    idx = pd.date_range("2022-01-03", periods=T, freq="B" if seed % 4 == 0 else "D", tz="UTC")
    cols = [f"k{j}" for j in range(N)]
    px = 50 * np.exp(np.cumsum(rng.normal(0, 0.02, (T, N)), axis=0))
    carry = None if seed % 3 == 0 else pd.DataFrame(rng.normal(0, 3e-4, (T, N)), index=idx, columns=cols)
    meta = {"periods_per_year": 365}
    kw = {}
    if seed % 2:
        meta["exec_prices_strictly_after_decision"] = True
        kw["exec_prices"] = pd.DataFrame(px * np.exp(rng.normal(0, 0.004, (T, N))), index=idx, columns=cols)
        kw["extra_lag"] = int(rng.integers(0, 3))
    else:
        kw["lag"] = int(rng.integers(1, 4))
    w = rng.normal(0, 0.4, (T, N))
    w[: int(rng.integers(0, 6))] = np.nan
    w[rng.random((T, N)) < 0.15] = 0.0
    return PanelBundle("REAL", pd.DataFrame(px, index=idx, columns=cols), carry=carry, meta=meta), \
        pd.DataFrame(w, index=idx, columns=cols), kw


@pytest.mark.parametrize("seed", range(24))
def test_ideal_venue_with_a_trade_on_every_print_reproduces_the_engine(seed):
    """VenueSpec.ideal(), fractional units, a trade on every print: the account IS the frictionless backtest —
    its net return equals `backtest`'s gross (price + carry) to 1e-8 (in fact to ~1e-12)."""
    panel, w, kw = random_case(seed)
    sim = simulate_account(panel, w, equity0=1000.0, venue=VenueSpec.ideal(), **kw)
    ref = backtest(panel, w, cost_bp_side=0.0, **kw)
    np.testing.assert_allclose(sim.net.to_numpy(), ref.gross.to_numpy(), rtol=0, atol=1e-8)
    np.testing.assert_allclose(sim.net.to_numpy(), (ref.price_pnl + ref.carry).to_numpy(), rtol=0, atol=1e-8)
    np.testing.assert_allclose(sim.net.to_numpy(), ref.gross.to_numpy(), rtol=0, atol=1e-11)     # far tighter in fact
    np.testing.assert_allclose(sim.gross.to_numpy(), ref.gross.to_numpy(), rtol=0, atol=1e-11)
    np.testing.assert_allclose(sim.held.to_numpy(), ref.held.to_numpy(), rtol=0, atol=1e-11)
    np.testing.assert_allclose(sim.gross_leverage.to_numpy(), ref.gross_leverage.to_numpy(), rtol=0, atol=1e-10)
    assert sim.tracking["tracking_error_ann"] < 1e-9 and abs(sim.tracking["mean_gap_ann"]) < 1e-9
    # and the equity curve is the compounded net: no contributions, no costs
    np.testing.assert_allclose(sim.equity.to_numpy(), 1000.0 * np.cumprod(1.0 + ref.gross.to_numpy()), rtol=1e-10)
    for k in ("fees", "spread", "financing"):
        assert sim.cost_breakdown[k] == 0.0
    assert sim.meta["venue"][panel.prices.columns[0]]["venue_id"] == "IDEAL"
    # the size of the account does not matter when nothing is lumpy
    other = simulate_account(panel, w, equity0=7.0, venue=VenueSpec.ideal(), **kw)
    np.testing.assert_allclose(other.net.to_numpy(), sim.net.to_numpy(), rtol=0, atol=1e-11)


def test_ideal_venue_is_explicit_and_complete():
    ideal = VenueSpec.ideal()
    assert ideal.unknown_fields() == ["funded"] and ideal.venue_id == "IDEAL" and ideal.leverage_cap == math.inf
    for name in ("fee_bp", "min_fee", "half_spread_bp", "lot_step", "min_notional", "financing_long_bp_year",
                 "financing_short_bp_year", "cash_interest_bp_year", "cash_interest_threshold"):
        assert getattr(ideal, name) == 0.0
    assert ideal.contract_notional == 1.0 and VenueSpec.ideal(funded=True).unknown_fields() == []
    assert all(note["status"] == "given" for note in ideal.notes.values())
    panel = panel_of({"A": [10.0, 10.0, 12.0]})
    res = simulate_account(panel, weights(panel, {"A": [7.0, 7.0, 7.0]}), equity0=100.0, venue=ideal)
    assert res.meta["n_prints_leverage_capped"] == 0 and res.meta["max_margin_utilisation"] == 0.0   # no cap at all
    assert res.net.iloc[2] == pytest.approx(7.0 * 0.2)
    json.dumps(res.meta)                                                 # inf is recorded as the string "inf"


# --------------------------------------------------------------------------------------------------
# Hand-worked accounts
# --------------------------------------------------------------------------------------------------
def test_hand_worked_account_with_every_friction():
    # prices 100, 100, 110, 110, 99 (daily) ; targets 0.5, 0.5, 0.5, 0, 0 ; lag 1 ; trade rows: prints 1 and 4.
    # venue: 10 bp commission, EUR 1 minimum, 5 bp half-spread, fractional units, long financing 365 bp/yr = 1 bp/day.
    #   t=1: target w[0] = 0.5: buy 0.5*1000/100 = 5 units, order EUR 500
    #        fee = max(1, 0.50) = 1.00 ; spread = 500 * 5 bp = 0.25                -> equity 998.75
    #   t=2: price 110: +5*10 = +50.00 ; financing 500 * 1 bp * 1 day = 0.05       -> 1048.70 ; not a trade row
    #        net[2] = 1048.70 / 1000 - 1 = +4.87 %      gross[2] = 50/1000 = +5.00 %   (ideal: 0.5 * 10 % = +5.00 %)
    #   t=3: price 110: 0 ; financing 550 * 1 bp = 0.055                           -> 1048.645
    #        net[3] = 1048.645 / 1048.70 - 1 = -0.0052446 %
    #   t=4: price 99: 5 * -11 = -55.00 ; financing 0.055                          -> 993.59
    #        net[4] = 993.59 / 1048.645 - 1 = -5.25011 %   (the position DRIFTED to 52.4 %: the engine says -5.00 %)
    #        trade row, target w[3] = 0: sell 5 units, order EUR 495: fee max(1, 0.495) = 1 ; spread 0.2475 -> 992.3425
    panel = panel_of({"A": [100.0, 100.0, 110.0, 110.0, 99.0]})
    w = weights(panel, {"A": [0.5, 0.5, 0.5, 0.0, 0.0]})
    venue = VenueSpec(fee_bp=10.0, min_fee=1.0, half_spread_bp=5.0, lot_step=0.0, min_notional=0.0, contract_notional=1.0,
                      financing_long_bp_year=365.0, leverage_cap=1.0)
    res = simulate_account(panel, w, equity0=1000.0, venue=venue, rebalance_mask=rows(panel, 1, 4))
    np.testing.assert_allclose(res.equity, [1000.0, 998.75, 1048.70, 1048.645, 992.3425], rtol=0, atol=1e-9)
    np.testing.assert_allclose(res.net, [0, 0, 0.0487, 1048.645 / 1048.70 - 1, 993.59 / 1048.645 - 1], rtol=0, atol=1e-12)
    np.testing.assert_allclose(res.gross, [0, 0, 0.05, 0.0, -55.0 / 1048.645], rtol=0, atol=1e-12)
    assert res.units["A"].tolist() == [0.0, 5.0, 5.0, 5.0, 0.0]
    np.testing.assert_allclose(res.held["A"], [0, 0, 0.5, 550 / 1048.70, 550 / 1048.645], rtol=0, atol=1e-12)
    np.testing.assert_allclose(res.gross_leverage, res.held["A"].abs(), rtol=0, atol=0)
    np.testing.assert_allclose(res.flows["price_pnl"], [0, 0, 50.0, 0.0, -55.0], atol=1e-12)
    np.testing.assert_allclose(res.flows["financing"], [0, 0, 0.05, 0.055, 0.055], atol=1e-12)
    np.testing.assert_allclose(res.flows["fees"], [0, 1.0, 0, 0, 1.0], atol=1e-12)
    np.testing.assert_allclose(res.flows["spread"], [0, 0.25, 0, 0, 0.2475], atol=1e-12)
    np.testing.assert_allclose(res.turnover, [0, 0.5, 0, 0, 495 / 993.59], atol=1e-12)
    cb = res.cost_breakdown
    assert cb["fees"] == pytest.approx(2.0) and cb["spread"] == pytest.approx(0.4975)
    assert cb["financing"] == pytest.approx(0.16) and cb["price_pnl"] == pytest.approx(-5.0) and cb["carry"] == 0.0
    # accounting identity: start + price P&L + carry - financing - fees - spread = end
    assert 1000.0 + cb["price_pnl"] + cb["carry"] - cb["financing"] - cb["fees"] - cb["spread"] == pytest.approx(992.3425)
    np.testing.assert_allclose(res.ideal_net, [0, 0, 0.05, 0.0, -0.05], atol=1e-12)
    assert res.meta["final_equity"] == pytest.approx(992.3425) and res.meta["ruined_at"] is None
    assert res.meta["max_margin_utilisation"] == pytest.approx(550 / 1048.645, rel=1e-9)
    assert res.meta["rebalance_mask"] == "2 trade rows of 5" and res.meta["n_trade_rows"] == 2 and res.meta["delay"] == 1
    assert cb["calendar_years"] == pytest.approx(4 / 365)
    json.dumps(res.meta)
    json.dumps(res.cost_breakdown)
    json.dumps(res.tracking)


def test_two_instruments_on_a_monthly_mask_drift_between_rebalances():
    # prints: 30 Jan, 31 Jan, 1 Feb, 28 Feb, 29 Feb, 1 Mar, 4 Mar 2024. Constant target 60 % A / 40 % B, lag 1,
    # ideal venue, EUR 1,000. Monthly mask = first print of each month: rows 0, 2, 5.
    #   A: 100, 100, 110, 121, 121, 110, 110        B: 50, 50, 50, 45, 45, 54, 54
    # row 0: a trade row, but no decision exists yet (delay 1): nothing happens.
    # row 2 (1 Feb): buy A 600/110 = 5.454545 units, B 400/50 = 8 units.
    # row 3 (28 Feb): A +10 %, B -10 %: P&L = 5.454545*11 - 8*5 = +60 - 40 = +20 -> 1,020 ; net = +2.0000 %
    #                 (weights were at target, so this equals the engine: 0.6*0.10 - 0.4*0.10)
    #                 NOT a trade row: the weights DRIFT to A 660/1020 = 64.7059 %, B 360/1020 = 35.2941 %.
    # row 5 (1 Mar):  A -9.0909 %, B +20 %: P&L = 5.454545*(-11) + 8*9 = -60 + 72 = +12 -> 1,032 ; net = 12/1020 = +1.17647 %
    #                 the engine, which silently re-balanced back to 60/40, books 0.6*(-0.090909) + 0.4*0.20 = +2.54545 %.
    #                 trade row: back to 60/40 of 1,032: A 619.2/110 = 5.629091 units, B 412.8/54 = 7.644444 units ;
    #                 traded: A +0.174545*110 = 19.20, B -0.355556*54 = 19.20 -> turnover 38.4/1032 = 3.7209 %.
    idx = pd.DatetimeIndex(["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-28", "2024-02-29", "2024-03-01",
                            "2024-03-04"], tz="UTC")
    panel = panel_of({"A": [100.0, 100, 110, 121, 121, 110, 110], "B": [50.0, 50, 50, 45, 45, 54, 54]}, ppy=252, index=idx)
    w = weights(panel, {"A": [0.6] * 7, "B": [0.4] * 7})
    mask = portfolio.rebalance_rows(idx, "monthly")
    assert mask.tolist() == [True, False, True, False, False, True, False]
    res = simulate_account(panel, w, equity0=1000.0, venue=VenueSpec.ideal(), rebalance_mask=mask)
    assert res.equity.tolist() == pytest.approx([1000, 1000, 1000, 1020, 1020, 1032, 1032], abs=1e-9)
    np.testing.assert_allclose(res.net, [0, 0, 0, 0.02, 0, 12 / 1020, 0], rtol=0, atol=1e-12)
    np.testing.assert_allclose(res.units["A"], [0, 0, 600 / 110, 600 / 110, 600 / 110, 619.2 / 110, 619.2 / 110], atol=1e-12)
    np.testing.assert_allclose(res.units["B"], [0, 0, 8, 8, 8, 412.8 / 54, 412.8 / 54], atol=1e-12)
    np.testing.assert_allclose(res.held["A"], [0, 0, 0, 0.6, 660 / 1020, 660 / 1020, 0.6], atol=1e-12)
    np.testing.assert_allclose(res.held["B"], [0, 0, 0, 0.4, 360 / 1020, 360 / 1020, 0.4], atol=1e-12)
    np.testing.assert_allclose(res.turnover, [0, 0, 1.0, 0, 0, 38.4 / 1032, 0], atol=1e-12)
    assert res.meta["n_orders"] == 4 and res.meta["n_trade_rows"] == 2
    # the weight engine on the same targets: same first interval, a different second one (it re-balanced back to
    # 60/40 in between). Under "target" that re-balancing is free: no turnover after the entry.
    eng = backtest(panel, w, lag=1, cost_bp_side=0.0)
    assert eng.net.iloc[3] == pytest.approx(0.02) and eng.net.iloc[5] == pytest.approx(0.6 * (110 / 121 - 1) + 0.4 * 0.2)
    assert eng.net.iloc[5] == pytest.approx(0.0254545, abs=1e-7) and eng.turnover_target.iloc[3:].sum() == 0.0
    # Under "drift" (the default) the engine books those trades. (It entered one print earlier than the masked
    # account — at print 1 — so it also lived through row 2, A +10 %: it stands at 0.66/1.06, 0.4/1.06 -> row 3: 0.045283.)
    #   row 4, after +10 % / -10 %: the SAME drifted weights the account shows, 64.7 % / 35.3 %:
    #          |0.6 - 0.647059| + |0.4 - 0.352941| = 0.094118
    #   row 6, after -9.09 % / +20 %: A stands at 0.6*0.909091/1.0254545 = 0.531915, B at 0.48/1.0254545 = 0.468085 -> 0.136170
    # That is 0.2756 of re-balancing against the account's single 0.0372 on 1 March: the engine restores on EVERY
    # print, the schedule once a month — for a scheduled book the drift model over-charges and the account is right.
    np.testing.assert_allclose(
        eng.turnover,
        [0, 0, 1.0, 2 * (0.66 / 1.06 - 0.6), 2 * (0.66 / 1.02 - 0.6), 0, 2 * (0.48 / (1 + 0.6 * (110 / 121 - 1) + 0.08) - 0.4)],
        atol=1e-12)
    assert eng.turnover.iloc[3] == pytest.approx(0.045283, abs=1e-6)
    assert eng.turnover.iloc[4] == pytest.approx(0.094118, abs=1e-6) and eng.turnover.iloc[6] == pytest.approx(0.136170, abs=1e-6)
    assert eng.turnover.iloc[3:].sum() > 7 * res.turnover.iloc[3:].sum()
    np.testing.assert_allclose(res.held.iloc[4], [0.66 / 1.02, 0.36 / 1.02], atol=1e-12)     # the account's drifted weights
    # --- a no-trade band on the trade row of 1 March: current weights are A 600/1032 = 58.14 %, B 432/1032 = 41.86 %
    #     band 10 %: |0.60 - 0.5814| = 0.0186 <= 0.10*0.60 and |0.40 - 0.4186| = 0.0186 <= 0.10*0.40 -> nothing trades
    wide = simulate_account(panel, w, equity0=1000.0, venue=VenueSpec.ideal(), rebalance_mask=mask, no_trade_band=0.10)
    assert wide.units.iloc[-1].tolist() == pytest.approx([600 / 110, 8.0]) and wide.meta["n_trades_skipped_in_band"] == 2
    #     band 4 %: A's limit is 0.024 (0.0186 inside -> skipped), B's is 0.016 (0.0186 outside -> traded to 40 %)
    mixed = simulate_account(panel, w, equity0=1000.0, venue=VenueSpec.ideal(), rebalance_mask=mask, no_trade_band=0.04)
    assert mixed.units.iloc[-1].tolist() == pytest.approx([600 / 110, 412.8 / 54])
    assert mixed.meta["n_trades_skipped_in_band"] == 1 and mixed.turnover.iloc[5] == pytest.approx(19.2 / 1032)
    #     band 2 %: both limits (0.012, 0.008) are inside the deviation -> both trade, as with no band
    tight = simulate_account(panel, w, equity0=1000.0, venue=VenueSpec.ideal(), rebalance_mask=mask, no_trade_band=0.02)
    np.testing.assert_allclose(tight.units.to_numpy(), res.units.to_numpy(), atol=1e-12)


def test_the_mask_marks_trade_rows_and_the_target_is_the_one_decided_delay_prints_earlier():
    # targets change every print: 0.1, 0.2, 0.3, 0.4, 0.5, 0.6 ; flat price 10 ; EUR 1,000 ; ideal venue.
    panel = panel_of({"A": [10.0] * 6})
    w = weights(panel, {"A": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]})
    # lag 1, trade row 3 -> target w[2] = 0.3 -> 30 units
    lag1 = simulate_account(panel, w, equity0=1000.0, venue=VenueSpec.ideal(), rebalance_mask=rows(panel, 3))
    assert lag1.units["A"].tolist() == pytest.approx([0, 0, 0, 30.0, 30.0, 30.0])
    # lag 2, trade row 3 -> target w[1] = 0.2 -> 20 units
    lag2 = simulate_account(panel, w, equity0=1000.0, venue=VenueSpec.ideal(), rebalance_mask=rows(panel, 3), lag=2)
    assert lag2.units["A"].tolist() == pytest.approx([0, 0, 0, 20.0, 20.0, 20.0])
    # exec prices, extra_lag 0, trade row 3 -> target w[3] = 0.4, at the EXEC price of row 3 (20) -> 20 units
    certified = panel_of({"A": [10.0] * 6}, meta={"exec_prices_strictly_after_decision": True})
    ex = pd.DataFrame({"A": [20.0] * 6}, index=panel.prices.index)
    e0 = simulate_account(certified, w, equity0=1000.0, venue=VenueSpec.ideal(), rebalance_mask=rows(panel, 3), exec_prices=ex)
    assert e0.units["A"].tolist() == pytest.approx([0, 0, 0, 20.0, 20.0, 20.0])
    # a True row before any decision exists trades nothing; an all-False mask never trades
    early = simulate_account(panel, w, equity0=1000.0, venue=VenueSpec.ideal(), rebalance_mask=rows(panel, 0), lag=3)
    never = simulate_account(panel, w, equity0=1000.0, venue=VenueSpec.ideal(), rebalance_mask=rows(panel))
    assert (early.units == 0).all().all() and (never.units == 0).all().all() and never.meta["n_trade_rows"] == 0
    # the helper that builds trade rows from decision rows: monthly decisions, filled one print later
    idx = pd.date_range("2024-01-30", periods=40, freq="D", tz="UTC")
    trade = portfolio.rebalance_rows(idx, "monthly", offset=1)
    assert trade[trade].index.tolist() == [idx[1], idx[3], idx[32]]      # 31 Jan (row 0 + 1), 2 Feb, 2 Mar
    for bad in (rows(panel, 1).to_numpy(), rows(panel, 1).iloc[:-1], rows(panel, 1).astype(float),
                rows(panel, 1).astype(object)):
        with pytest.raises(Refused, match="rebalance_mask"):
            simulate_account(panel, w, equity0=1000.0, venue=VenueSpec.ideal(), rebalance_mask=bad)
    with pytest.raises(Refused, match="no_trade_band"):
        simulate_account(panel, w, equity0=1000.0, venue=VenueSpec.ideal(), no_trade_band=-0.1)


def test_a_scheduled_book_differs_from_the_weight_engine_and_trades_more_than_it_admits():
    """Why the simulator is the official engine for scheduled books: on a monthly schedule the weight engine
    (targets held with `rebalance_on`, restored for free on every print) understates turnover and follows a
    different return path than units that drift."""
    rng = np.random.default_rng(3)
    idx = pd.date_range("2021-01-04", periods=520, freq="B", tz="UTC")
    cols = list("abcdef")
    px = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, (520, 6)), axis=0)), index=idx, columns=cols)
    panel = PanelBundle("REAL", px, meta={"periods_per_year": 252})
    raw = pd.DataFrame(1.0 / 6.0, index=idx, columns=cols)                # a long-only, equal-weight book...
    raw.iloc[260:, 0], raw.iloc[260:, 1] = 0.25, 1.0 / 12.0               # ...whose targets change once, after a year
    held_targets = portfolio.rebalance_on(raw, "monthly")
    eng = backtest(panel, held_targets, lag=1, cost_bp_side=0.0)
    mask = portfolio.rebalance_rows(idx, "monthly", offset=1)                                     # decisions + 1 print
    sim = simulate_account(panel, held_targets, equity0=1e6, venue=VenueSpec.ideal(), rebalance_mask=mask)
    same_from_raw = simulate_account(panel, raw, equity0=1e6, venue=VenueSpec.ideal(), rebalance_mask=mask)
    np.testing.assert_allclose(same_from_raw.net.to_numpy(), sim.net.to_numpy(), atol=1e-13)    # the mask picks the rows
    assert sim.meta["n_trade_rows"] == int(mask.sum()) == 24
    understated = 1.0 - eng.turnover_target.sum() / sim.turnover.sum()
    overstated = eng.turnover.sum() / sim.turnover.sum() - 1.0
    print(f"\n[measured] monthly long-only book, 6 instruments, 520 business days: turnover in sides — weight engine "
          f"'target' model {eng.turnover_target.sum():.3f} ({understated:.1%} below the account), drift-aware account "
          f"(monthly trades) {sim.turnover.sum():.3f}, weight engine 'drift' model (restores every print) "
          f"{eng.turnover.sum():.3f} ({overstated:.1%} above the account); max |net difference| on one print "
          f"{float((sim.net - eng.net).abs().max()):.5f}")
    assert eng.turnover_target.sum() == pytest.approx(1.0 + 2.0 / 12.0)   # the entry and the one target change: 1.1667
    assert 0.2 < understated < 0.8                                        # "target" misses every drift trade
    assert overstated > 0.5                                               # "drift" restores daily what the book restores monthly
    gap = (sim.net - eng.net).abs()
    assert gap.max() > 1e-5 and abs(sim.net.sum() - eng.net.sum()) < 0.05  # a different path, a similar total
    # with a trade on EVERY print the two coincide again
    daily = simulate_account(panel, held_targets, equity0=1e6, venue=VenueSpec.ideal())
    np.testing.assert_allclose(daily.net.to_numpy(), eng.net.to_numpy(), atol=1e-11)


def test_financing_accrues_in_calendar_time_friday_to_monday():
    # Wed 3, Thu 4, Fri 5, Mon 8, Tue 9 Jan 2024. Flat prices. Long A 0.5 (EUR 500) at 365 bp/yr = 1 bp per DAY,
    # short B 0.4 (EUR 400) at 730 bp/yr = 2 bp per DAY. Bought at print 1 (Thu).
    #   Fri (1 day)  : 500*1bp + 400*2bp = 0.05 + 0.08 = 0.13
    #   Mon (3 days) : 3 * 0.13 = 0.39      <- the weekend
    #   Tue (1 day)  : 0.13
    idx = pd.DatetimeIndex(["2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"], tz="UTC")
    panel = panel_of({"A": [10.0] * 5, "B": [40.0] * 5}, ppy=252, index=idx)
    w = weights(panel, {"A": [0.5] * 5, "B": [-0.4] * 5})
    venue = frictionless(financing_long_bp_year=365.0, financing_short_bp_year=730.0, leverage_cap=2.0)
    res = simulate_account(panel, w, equity0=1000.0, venue=venue, rebalance_mask=rows(panel, 1))
    assert res.units.iloc[1].tolist() == [50.0, -10.0]
    np.testing.assert_allclose(res.flows["financing"], [0, 0, 0.13, 0.39, 0.13], atol=1e-12)
    assert res.equity.iloc[-1] == pytest.approx(1000.0 - 0.65)
    assert res.meta["financing_day_count"].startswith("ACT/365")
    # the engine's hold costs say the same, print by print: (0.5*1bp + 0.4*2bp) * days = 1.3 bp, 3.9 bp, 1.3 bp
    ref = backtest(panel, w, cost_bp_side=0.0, hold_cost_long_bp_year=365.0, hold_cost_short_bp_year=730.0)
    np.testing.assert_allclose(ref.hold_cost.iloc[2:], [0.00013, 0.00039, 0.00013], atol=1e-15)
    np.testing.assert_allclose(res.flows["financing"].iloc[2:] / 1000.0, ref.hold_cost.iloc[2:], atol=1e-7)


# --------------------------------------------------------------------------------------------------
# An independent reference account (plain Python, written from the docstring) on random cases
# --------------------------------------------------------------------------------------------------
def reference_account(panel, w, equity0, spec: dict, *, delay: int, price_frame, mask=None, band=0.0,
                      contribution=0.0):
    """A second, deliberately naive implementation of the documented loop: dicts and floats, one instrument
    at a time. `spec` holds one venue for all instruments. Complete panels only (no missing prices)."""
    names = list(panel.prices.columns)
    stamps = list(panel.prices.index)
    px = {n: [float(v) for v in price_frame[n]] for n in names}
    tgt = {n: [0.0 if v != v else float(v) for v in w[n]] for n in names}
    carry = None if panel.carry is None else {n: [float(v) for v in panel.carry[n]] for n in names}
    units = {n: 0.0 for n in names}
    equity = float(equity0)
    equity_path, net_path, fee_path, units_path = [], [], [], []
    previous_pre = None
    for t in range(len(stamps)):
        if t > 0:
            gap_days = (stamps[t].date() - stamps[t - 1].date()).days
            pnl = 0.0
            for n in names:
                start = units[n] * spec["m"] * px[n][t - 1]
                pnl += units[n] * spec["m"] * (px[n][t] - px[n][t - 1])
                if carry is not None:
                    pnl += start * carry[n][t]
                rate = spec["fin_long"] if start > 0 else spec["fin_short"]
                pnl -= abs(start) * rate / 1e4 * gap_days / 365.0
            equity += pnl
            net_path.append(equity / previous_pre - 1.0)
            if contribution and (stamps[t].year, stamps[t].month) != (stamps[t - 1].year, stamps[t - 1].month):
                equity += contribution
        else:
            net_path.append(0.0)
        pre = equity
        fees_now = 0.0
        s = t - delay
        if s >= 0 and (mask is None or bool(mask.iloc[t])):
            plan = {}
            for n in names:
                f = tgt[n][s]
                now = units[n] * spec["m"] * px[n][t]
                if band > 0:
                    trade = abs(f - now / pre) > band * max(abs(f), 1e-4)
                else:
                    trade = f * pre != now
                plan[n] = (trade, f * pre if trade else now, now)
            fixed = sum(abs(now) / spec["cap"] for trade, want, now in plan.values() if not trade)
            moving = sum(abs(want) / spec["cap"] for trade, want, now in plan.values() if trade)
            scale = 1.0
            if moving > 0 and fixed + moving > pre * (1.0 + 1e-12):
                scale = max(0.0, (pre - fixed) / moving)
            for n in names:
                trade, want, now = plan[n]
                if not trade:
                    continue
                raw = want * scale / (spec["m"] * px[n][t])
                new = raw
                if spec["lot"] > 0:
                    new = math.floor(abs(raw) / spec["lot"] + 1e-9) * spec["lot"]
                    new = -new if raw < 0 else new
                notional = abs(new - units[n]) * spec["m"] * px[n][t]
                if notional <= 1e-12 * pre:
                    continue
                if notional < spec["min_notional"] and new != 0:
                    continue
                fees_now += max(spec["min_fee"], spec["fee_bp"] / 1e4 * notional) + spec["hs_bp"] / 1e4 * notional
                units[n] = new
            equity -= fees_now
        previous_pre = pre
        equity_path.append(equity)
        fee_path.append(fees_now)
        units_path.append([units[n] for n in names])
    return np.array(equity_path), np.array(net_path), np.array(fee_path), np.array(units_path)


N_REFERENCE_CASES = 72


def draw_reference_case(seed: int):
    panel, w, kw = random_case(500 + seed)
    rng = np.random.default_rng(900 + seed)
    spec = {
        "fee_bp": float(rng.choice([0.0, 2.0, 10.0])), "min_fee": float(rng.choice([0.0, 0.5, 2.0])),
        "hs_bp": float(rng.choice([0.0, 1.0, 8.0])), "lot": float(rng.choice([0.0, 0.0, 0.01, 0.5])),
        "min_notional": float(rng.choice([0.0, 5.0, 60.0, 400.0])), "m": float(rng.choice([1.0, 1.0, 5.0])),
        "fin_long": float(rng.choice([0.0, 150.0, 400.0])), "fin_short": float(rng.choice([0.0, 150.0, 400.0])),
        "cap": float(rng.choice([1.0, 3.0, 1e9])),
    }
    venue = VenueSpec(fee_bp=spec["fee_bp"], min_fee=spec["min_fee"], half_spread_bp=spec["hs_bp"], lot_step=spec["lot"],
                      min_notional=spec["min_notional"], contract_notional=spec["m"],
                      financing_long_bp_year=spec["fin_long"], financing_short_bp_year=spec["fin_short"],
                      leverage_cap=spec["cap"])
    idx = panel.prices.index
    choice = int(rng.integers(0, 4))
    mask = [None, portfolio.rebalance_rows(idx, "weekly", offset=1), portfolio.rebalance_rows(idx, "monthly"),
            pd.Series(rng.random(len(idx)) < 0.3, index=idx)][choice]
    band = float(rng.choice([0.0, 0.0, 0.05, 0.25]))
    contribution = float(rng.choice([0.0, 0.0, 50.0]))
    equity0 = float(rng.choice([1_500.0, 20_000.0, 500_000.0]))
    w = w * float(rng.choice([0.3, 1.0]))
    return panel, w, kw, spec, venue, mask, band, contribution, equity0


@pytest.mark.parametrize("seed", range(N_REFERENCE_CASES))
def test_simulator_equals_an_independent_reference_account(seed):
    panel, w, kw, spec, venue, mask, band, contribution, equity0 = draw_reference_case(seed)
    sim = simulate_account(panel, w, equity0=equity0, venue=venue, rebalance_mask=mask, no_trade_band=band,
                           monthly_contribution=contribution, **kw)
    if sim.meta["ruined_at"] is not None:
        pytest.skip("account ruined: the reference does not model the stop")
    delay = kw["extra_lag"] if "exec_prices" in kw else kw["lag"]
    eq, net, fees, units = reference_account(panel, w, equity0, spec, delay=delay,
                                             price_frame=kw.get("exec_prices", panel.prices), mask=mask, band=band,
                                             contribution=contribution)
    np.testing.assert_allclose(sim.equity.to_numpy(), eq, rtol=1e-10, atol=1e-8)
    np.testing.assert_allclose(sim.net.to_numpy(), net, rtol=0, atol=1e-10)
    np.testing.assert_allclose((sim.flows["fees"] + sim.flows["spread"]).to_numpy(), fees, rtol=1e-9, atol=1e-9)
    np.testing.assert_allclose(sim.units.to_numpy(), units, rtol=1e-9, atol=1e-9)


def test_the_reference_cases_exercise_every_feature():
    seen = {"mask": 0, "band": 0, "lot": 0, "min_fee_paid": 0, "min_notional_skip": 0, "capped": 0, "exec": 0,
            "contribution": 0, "financing": 0, "rounded_to_zero": 0, "carry": 0, "ruined": 0}
    for seed in range(N_REFERENCE_CASES):
        panel, w, kw, spec, venue, mask, band, contribution, equity0 = draw_reference_case(seed)
        sim = simulate_account(panel, w, equity0=equity0, venue=venue, rebalance_mask=mask, no_trade_band=band,
                               monthly_contribution=contribution, **kw)
        seen["mask"] += mask is not None
        seen["band"] += sim.meta["n_trades_skipped_in_band"] > 0
        seen["lot"] += spec["lot"] > 0
        seen["min_fee_paid"] += sim.meta["n_orders_at_min_fee"] > 0
        seen["min_notional_skip"] += sim.meta["n_orders_skipped_min_notional"] > 0
        seen["capped"] += sim.meta["n_prints_leverage_capped"] > 0
        seen["exec"] += "exec_prices" in kw
        seen["contribution"] += sim.cost_breakdown["contributions"] > 0
        seen["financing"] += sim.cost_breakdown["financing"] > 0
        seen["rounded_to_zero"] += sim.meta["n_targets_rounded_to_zero"] > 0
        seen["carry"] += panel.carry is not None
        seen["ruined"] += sim.meta["ruined_at"] is not None
    assert seen["ruined"] <= N_REFERENCE_CASES // 5, seen
    for key, count in seen.items():
        if key != "ruined":
            assert count >= 6, f"feature {key!r} is exercised by only {count} of {N_REFERENCE_CASES} reference cases: {seen}"


# --------------------------------------------------------------------------------------------------
# Each friction on its own
# --------------------------------------------------------------------------------------------------
def test_half_spread_and_percentage_fee():
    # EUR 100,000, target 1.0 at price 20: order 100,000. fee 2 bp = 20 (> min 1) ; half-spread 3 bp = 30.
    panel = panel_of({"A": [20.0, 20.0, 20.0]})
    res = simulate_account(panel, weights(panel, {"A": [1.0, 1.0, 1.0]}), equity0=100_000.0, rebalance_mask=rows(panel, 1),
                           venue=frictionless(fee_bp=2.0, min_fee=1.0, half_spread_bp=3.0, leverage_cap=1.0))
    assert res.cost_breakdown["fees"] == pytest.approx(20.0) and res.cost_breakdown["spread"] == pytest.approx(30.0)
    assert res.equity.iloc[-1] == pytest.approx(99_950.0)


def test_carry_is_paid_on_start_notional_like_the_engine():
    # carry +2 bp per print on A (FX-style positive carry). Long 0.5 of EUR 1,000 = EUR 500 -> +0.10 per print.
    panel = panel_of({"A": [10.0] * 4}, carry={"A": [0.0002] * 4})
    w = weights(panel, {"A": [0.5] * 4})
    res = simulate_account(panel, w, equity0=1000.0, venue=frictionless(), rebalance_mask=rows(panel, 1))
    np.testing.assert_allclose(res.flows["carry"], [0, 0, 0.10, 0.10], atol=1e-12)
    assert res.cost_breakdown["carry"] == pytest.approx(0.20)
    ref = backtest(panel, w, cost_bp_side=0.0)
    assert res.net.iloc[2] == pytest.approx(ref.net.iloc[2], abs=1e-15) == pytest.approx(0.0001)
    assert res.gross.iloc[2] == pytest.approx(0.0001)


def test_min_notional_skips_small_orders_but_never_blocks_a_full_close():
    # EUR 1,000, min order EUR 100. target 0.05 -> EUR 50 order: not sent. target 0.30 -> EUR 300: sent.
    # then target 0.32 -> a EUR 20 top-up: not sent. target 0 -> the close goes through whatever its size.
    panel = panel_of({"A": [10.0] * 7})
    w = weights(panel, {"A": [0.05, 0.30, 0.32, 0.0, 0.0, 0.0, 0.0]})
    res = simulate_account(panel, w, equity0=1000.0, venue=frictionless(min_notional=100.0))
    assert res.units["A"].tolist() == [0.0, 0.0, 30.0, 30.0, 0.0, 0.0, 0.0]
    assert res.meta["n_orders_skipped_min_notional"] == 2 and res.meta["n_orders"] == 2
    # a position worth less than the minimum can still be closed: 0.05 with min 40 -> EUR 50 in, EUR 50 out
    small = simulate_account(panel, weights(panel, {"A": [0.05, 0.0, 0, 0, 0, 0, 0]}), equity0=1000.0,
                             venue=frictionless(min_notional=40.0))
    assert small.units["A"].tolist() == [0.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    tiny = simulate_account(panel, weights(panel, {"A": [0.05, 0.0, 0, 0, 0, 0, 0]}), equity0=1000.0,
                            venue=frictionless(min_notional=60.0))
    assert (tiny.units["A"] == 0).all() and tiny.meta["n_orders_skipped_min_notional"] == 1


def test_contract_notional_multiplier():
    # a micro future: one contract = 5 x price. price 400 -> EUR 2,000 per contract. EUR 10,000, target 0.5:
    #   desired 5,000 / 2,000 = 2.5 -> 2 contracts (lot 1). Price +10 points -> P&L = 2 * 5 * 10 = +100.
    panel = panel_of({"MES": [400.0, 400.0, 410.0]})
    res = simulate_account(panel, weights(panel, {"MES": [0.5, 0.5, 0.5]}), equity0=10_000.0, rebalance_mask=rows(panel, 1),
                           venue=frictionless(contract_notional=5.0, lot_step=1.0, leverage_cap=5.0))
    assert res.units["MES"].tolist() == [0.0, 2.0, 2.0] and res.flows["price_pnl"].iloc[2] == pytest.approx(100.0)
    assert res.held["MES"].iloc[2] == pytest.approx(0.4)                 # 4,000 of 10,000: the rounding is visible


def test_leverage_cap_cuts_targets_and_is_reported():
    # target 3.0 with a cap of 2.0: the order is cut to 2x equity = EUR 2,000 -> 20 units at price 100.
    panel = panel_of({"A": [100.0, 100.0, 100.0, 80.0]})
    w = weights(panel, {"A": [3.0, 3.0, 3.0, 3.0]})
    res = simulate_account(panel, w, equity0=1000.0, venue=frictionless(leverage_cap=2.0), rebalance_mask=rows(panel, 1))
    assert res.units["A"].iloc[1] == pytest.approx(20.0) and res.meta["n_prints_leverage_capped"] == 1
    assert res.held["A"].iloc[2] == pytest.approx(2.0)
    # the price falls 20 %: equity 1000 - 400 = 600 against a position of 1,600 -> 2.67x: over the cap, REPORTED
    assert res.equity.iloc[3] == pytest.approx(600.0) and res.meta["n_prints_over_cap"] == 1
    assert res.meta["max_margin_utilisation"] == pytest.approx(1600 / 2.0 / 600.0, rel=1e-12)
    # per-class caps: A at 2x and B at 10x -> margin = 2,000/2 + 5,000/10 = 1,500 > 1,000 -> both cut by 2/3
    panel2 = panel_of({"A": [100.0] * 3, "B": [50.0] * 3})
    w2 = weights(panel2, {"A": [2.0] * 3, "B": [5.0] * 3})
    mixed = simulate_account(panel2, w2, equity0=1000.0, rebalance_mask=rows(panel2, 1),
                             venue={"A": frictionless(leverage_cap=2.0), "B": frictionless(leverage_cap=10.0)})
    assert mixed.units.iloc[1].tolist() == pytest.approx([2000 * (2 / 3) / 100, 5000 * (2 / 3) / 50])
    assert mixed.meta["max_margin_utilisation"] == pytest.approx(1.0, rel=1e-9)


def test_ruin_stops_the_account():
    # 5x long, price -30 % in one print: P&L = -1,500 on EUR 1,000 -> equity -500: the account is finished.
    panel = panel_of({"A": [100.0, 100.0, 70.0, 140.0, 140.0]})
    res = simulate_account(panel, weights(panel, {"A": [5.0] * 5}), equity0=1000.0, venue=frictionless(leverage_cap=10.0))
    assert res.equity.tolist() == [1000.0, 1000.0, -500.0, -500.0, -500.0]
    assert res.net.tolist() == pytest.approx([0.0, 0.0, -1.5, 0.0, 0.0])
    assert res.meta["ruined_at"] == panel.prices.index[2].isoformat() and (res.units.iloc[2:] == 0).all().all()


def test_monthly_contribution():
    # daily prints from 30 Jan: the first prints of February and March each add EUR 100. Flat prices, no costs:
    # the time-weighted return is untouched, equity ends at 1,000 + 200, and positions scale with the new money.
    panel = panel_of({"A": [10.0] * 40}, start="2024-01-30")
    w = weights(panel, {"A": [0.5] * 40})
    res = simulate_account(panel, w, equity0=1000.0, venue=VenueSpec.ideal(), monthly_contribution=100.0)
    idx = panel.prices.index
    paid = res.flows["contribution"]
    assert paid[paid > 0].index.tolist() == [idx[2], idx[31]]            # 2024-02-01 and 2024-03-01
    assert res.equity.iloc[-1] == pytest.approx(1200.0) and (res.net == 0.0).all()
    assert res.cost_breakdown["contributions"] == 200.0
    assert res.units["A"].iloc[1] == pytest.approx(50.0) and res.units["A"].iloc[2] == pytest.approx(55.0)
    # with moving prices the time-weighted net still equals the engine's: contributions are not returns
    panel2, w2, kw = random_case(8)
    a = simulate_account(panel2, w2, equity0=500.0, venue=VenueSpec.ideal(), monthly_contribution=250.0, **kw)
    np.testing.assert_allclose(a.net.to_numpy(), backtest(panel2, w2, cost_bp_side=0.0, **kw).net.to_numpy(), atol=1e-11)
    assert a.cost_breakdown["contributions"] > 0


def test_missing_price_policy():
    # prices 100, 100, NaN, 121 ; long 0.5 from print 1 (5 units).
    panel = panel_of({"A": [100.0, 100.0, np.nan, 121.0]})
    w = weights(panel, {"A": [0.5] * 4})
    with pytest.raises(Refused, match="has no price"):
        simulate_account(panel, w, equity0=1000.0, venue=frictionless(), rebalance_mask=rows(panel, 1))
    res = simulate_account(panel, w, equity0=1000.0, venue=frictionless(), missing_return="zero", rebalance_mask=rows(panel, 1))
    # the position is carried at 100 through the gap and the +21 % is realised when the price returns:
    #   5 * (121 - 100) = +105 -> 1,105. (The ENGINE books 0 for both NaN-return rows: a stated difference.)
    assert res.equity.tolist() == [1000.0, 1000.0, 1000.0, 1105.0] and res.meta["n_missing_price_held"] == 1
    assert res.net.iloc[3] == pytest.approx(0.105)
    assert backtest(panel, w, cost_bp_side=0.0, missing_return="zero").net.iloc[3] == 0.0
    # an order that cannot be priced on a trade row is not sent; the next trade row tries again
    panel2 = panel_of({"A": [100.0, np.nan, 100.0, 110.0]})
    late = simulate_account(panel2, weights(panel2, {"A": [0.5] * 4}), equity0=1000.0, venue=frictionless(),
                            missing_return="zero", rebalance_mask=rows(panel2, 1, 2))
    assert late.units["A"].tolist() == [0.0, 0.0, 5.0, 5.0] and late.meta["n_orders_skipped_no_price"] == 1
    # ...but only on a trade row: with the mask on print 1 alone the order is simply never sent
    lost = simulate_account(panel2, weights(panel2, {"A": [0.5] * 4}), equity0=1000.0, venue=frictionless(),
                            missing_return="zero", rebalance_mask=rows(panel2, 1))
    assert (lost.units["A"] == 0).all() and lost.meta["n_orders_skipped_no_price"] == 1


def test_timing_refusals_are_the_engines_and_inputs_are_validated():
    panel, w, kw = random_case(5)                                       # an exec-price case
    assert "exec_prices" in kw
    bad_meta = PanelBundle("REAL", panel.prices, carry=panel.carry, meta={"periods_per_year": 365})
    with pytest.raises(Refused, match="exec_prices refused"):
        simulate_account(bad_meta, w, equity0=1000.0, venue=VenueSpec.ideal(), **kw)
    with pytest.raises(Refused, match="lag"):
        simulate_account(panel, w, equity0=1000.0, venue=VenueSpec.ideal(), lag=0)
    for bad in (dict(equity0=0.0), dict(equity0=-5.0), dict(equity0=float("nan")), dict(monthly_contribution=-1.0),
                dict(no_trade_band=float("inf")), dict(missing_return="ffill")):
        call = dict(equity0=1000.0, venue=VenueSpec.ideal())
        call.update(bad)
        with pytest.raises(Refused):
            simulate_account(panel, w, **kw, **call)
    with pytest.raises(Refused, match="VenueSpec"):
        simulate_account(panel, w, equity0=1000.0, venue={"k0": VenueSpec.ideal()} if len(w.columns) > 1 else "x", **kw)
    with pytest.raises(TypeError):
        simulate_account(panel, w, equity0=1000.0, venue=VenueSpec.ideal(), rebalance="every_print", **kw)   # old API


def test_tracking_error_against_the_ideal_book_and_a_supplied_one():
    panel, w, kw = random_case(12)
    venue = frictionless(fee_bp=10.0, min_fee=1.0, half_spread_bp=5.0)
    res = simulate_account(panel, w, equity0=1000.0, venue=venue, **kw)
    assert res.tracking["mean_gap_ann"] < 0 and res.tracking["tracking_error_ann"] > 0 and res.tracking["corr"] > 0.9
    gap = (res.net - res.ideal_net).to_numpy()
    assert res.tracking["tracking_error_ann"] == pytest.approx(gap.std(ddof=1) * math.sqrt(365), rel=1e-12)
    assert res.tracking["mean_gap_ann"] == pytest.approx(gap.mean() * 365, rel=1e-12)
    costed = backtest(panel, w, cost_bp_side=15.0, **kw).net
    vs = simulate_account(panel, w, equity0=1000.0, venue=venue, ideal_net=costed, **kw)
    assert vs.tracking["ideal"] == "supplied by the caller" and vs.ideal_net.equals(costed.rename("ideal_net"))
    assert abs(vs.tracking["mean_gap_ann"]) < abs(res.tracking["mean_gap_ann"])     # a costed ideal is closer
    idx = panel.prices.index
    win = simulate_account(panel, w, equity0=1000.0, venue=venue, window=(idx[20], None), **kw)
    assert win.tracking["n_obs"] == len(idx) - 20
    with pytest.raises(Refused, match="ideal_net"):
        simulate_account(panel, w, equity0=1000.0, venue=venue, ideal_net=costed.iloc[1:], **kw)


def test_a_small_account_pays_more_than_a_large_one_for_the_same_book():
    """The point of the realism pass: the same weights, three account sizes, a EUR 2 minimum fee."""
    panel, w, kw = random_case(20)
    w = (w.fillna(0.0).rolling(10, min_periods=1).mean()).round(2)      # a slower book
    venue = frictionless(fee_bp=5.0, min_fee=2.0, half_spread_bp=2.0)
    drag = {e: simulate_account(panel, w, equity0=e, venue=venue, no_trade_band=0.2, **kw).cost_breakdown["frictions_bp_year"]
            for e in (1_000.0, 5_000.0, 10_000.0)}
    assert drag[1_000.0] > drag[5_000.0] > drag[10_000.0] > 0
    # and the no-trade band is what keeps the small account alive: without it the fee drag is far larger
    no_band = simulate_account(panel, w, equity0=1_000.0, venue=venue, **kw).cost_breakdown["frictions_bp_year"]
    assert no_band > 1.5 * drag[1_000.0]


def test_the_result_feeds_stats_summarize_like_a_backtest_result():
    from scripts.factory import stats

    panel, w, kw = random_case(30)
    res = simulate_account(panel, w, equity0=10_000.0, venue=frictionless(fee_bp=3.0, half_spread_bp=1.0),
                           rebalance_mask=portfolio.rebalance_rows(panel.prices.index, "weekly", offset=1), **kw)
    st = stats.summarize(res.net, periods_per_year=365, window=(panel.prices.index[10], None), gross=res.gross,
                         turnover=res.turnover, gross_leverage=res.gross_leverage)
    assert list(st) == list(stats.STAT_KEYS) and st["n_obs"] == len(res.net) - 10
    assert st["turnover_sides_per_year"] > 0 and np.isfinite(st["breakeven_cost_bp_side"])
    assert st["avg_gross_leverage"] == pytest.approx(res.gross_leverage.iloc[10:].mean())
    assert (res.gross - res.net).iloc[1:].sum() > 0                       # gross is before the frictions


# --------------------------------------------------------------------------------------------------
# Cash yield, reported separately
# --------------------------------------------------------------------------------------------------
def test_cash_yield_is_reported_separately_for_a_funded_account():
    # A FUNDED long (an ETF bought with cash): 30 % of EUR 1,000 at a flat price, daily prints.
    #   carry panel = -1 bp per print (the excess-return financing leg), tbill = +1 bp per print.
    #   venue pays 365 bp/yr = 1 bp per DAY on cash above EUR 500.
    # Excess account: -300 * 1 bp = -0.03 per print.
    # Cash yield:  idle cash 700 -> (700 - 500) * 1 bp = 0.02  +  the funded leg handed back 300 * 1 bp = 0.03  = 0.05
    # Total per print = -0.03 + 0.05 = +0.02: a flat ETF earns nothing, the idle cash above the threshold earns 1 bp.
    panel = panel_of({"ETF": [10.0] * 4}, carry={"ETF": [-0.0001] * 4}, tbill=[0.0001] * 4)
    w = weights(panel, {"ETF": [0.3] * 4})
    venue = frictionless(leverage_cap=1.0, cash_interest_bp_year=365.0, cash_interest_threshold=500.0, funded=True)
    one_trade = rows(panel, 1)
    res = simulate_account(panel, w, equity0=1000.0, venue=venue, report_total=True, rebalance_mask=one_trade)
    np.testing.assert_allclose(res.flows["carry"], [0, 0, -0.03, -0.03], atol=1e-12)
    assert res.flows["cash_yield"].iloc[2] == pytest.approx(0.05, abs=1e-12)
    # row 3: equity is 999.97, idle = 699.97 -> 0.019997 + 0.03
    assert res.flows["cash_yield"].iloc[3] == pytest.approx((699.97 - 500) * 1e-4 + 0.03, abs=1e-12)
    # row 1: nothing is held yet over (0, 1], all EUR 1,000 is idle: (1000 - 500) * 1 bp = 0.05
    assert res.flows["cash_yield"].iloc[0] == 0.0 and res.flows["cash_yield"].iloc[1] == pytest.approx(0.05, abs=1e-12)
    assert res.cost_breakdown["cash_yield"] == pytest.approx(0.05 + 0.05 + 0.049997, abs=1e-9)
    assert res.equity.iloc[-1] == pytest.approx(1000.0 - 0.06)           # the yield is NOT mixed into equity
    # a MARGINED account (CFD): cash stays as collateral; nothing is handed back; all 1,000 is idle
    cfd = simulate_account(panel, w, equity0=1000.0, venue=venue.with_overrides(funded=False), report_total=True,
                           rebalance_mask=one_trade)
    assert cfd.flows["cash_yield"].iloc[2] == pytest.approx((1000 - 500) * 1e-4, abs=1e-12)
    # below the threshold nothing is paid
    poor = simulate_account(panel, w, equity0=400.0, venue=venue.with_overrides(funded=False), report_total=True,
                            rebalance_mask=one_trade)
    assert (poor.flows["cash_yield"] == 0).all()
    assert "cash_yield" not in simulate_account(panel, w, equity0=1000.0, venue=venue).flows.columns
    # cash interest accrues on calendar days too: over a weekend the same idle cash earns three days
    idx = pd.DatetimeIndex(["2024-01-04", "2024-01-05", "2024-01-08"], tz="UTC")
    wk = panel_of({"ETF": [10.0] * 3}, index=idx, tbill=[0.0] * 3)
    flat = simulate_account(wk, weights(wk, {"ETF": [0.0] * 3}), equity0=1000.0, venue=venue.with_overrides(funded=False),
                            report_total=True)
    np.testing.assert_allclose(flat.flows["cash_yield"], [0.0, 0.05, 0.15], atol=1e-12)
    panel2 = panel_of({"ETF": [10.0] * 4, "B": [5.0] * 4}, tbill=[0.0001] * 4)
    with pytest.raises(Refused, match="one cash rate"):
        simulate_account(panel2, weights(panel2, {"ETF": [0.3] * 4, "B": [0.1] * 4}), equity0=1000.0,
                         venue={"ETF": venue, "B": venue.with_overrides(cash_interest_bp_year=10.0)}, report_total=True)


# --------------------------------------------------------------------------------------------------
# Unknown is not zero
# --------------------------------------------------------------------------------------------------
def test_an_unknown_field_refuses_the_simulation_it_affects():
    panel = panel_of({"A": [10.0] * 4})
    long_w = weights(panel, {"A": [0.5] * 4})
    with pytest.raises(Refused) as exc:
        simulate_account(panel, long_w, equity0=1000.0, venue=VenueSpec())
    for name in ALWAYS_REQUIRED + ("financing_long_bp_year",):
        assert name in str(exc.value)
    assert "financing_short_bp_year" not in str(exc.value)               # the book is never short: not affected
    for name in ALWAYS_REQUIRED:
        spec = frictionless().with_overrides(**{name: None})
        with pytest.raises(Refused, match=name):
            simulate_account(panel, long_w, equity0=1000.0, venue=spec)
    no_short = frictionless().with_overrides(financing_short_bp_year=None)
    assert simulate_account(panel, long_w, equity0=1000.0, venue=no_short).meta["n_orders"] == 1
    with pytest.raises(Refused, match="financing_short_bp_year"):
        simulate_account(panel, -long_w, equity0=1000.0, venue=no_short)
    no_long = frictionless().with_overrides(financing_long_bp_year=None)
    with pytest.raises(Refused, match="financing_long_bp_year"):
        simulate_account(panel, long_w, equity0=1000.0, venue=no_long)
    assert simulate_account(panel, -long_w, equity0=1000.0, venue=no_long).meta["n_orders"] == 1
    # the cash-yield report needs its own three fields — and only when it is asked for
    with pytest.raises(Refused) as exc:
        simulate_account(panel, long_w, equity0=1000.0, venue=frictionless(), report_total=True)
    for name in ("cash_interest_bp_year", "cash_interest_threshold", "funded"):
        assert name in str(exc.value)
    with pytest.raises(Refused, match="funded"):                         # ideal() leaves `funded` to the caller
        simulate_account(panel, long_w, equity0=1000.0, venue=VenueSpec.ideal(), report_total=True)
    assert simulate_account(panel, long_w, equity0=1000.0, venue=VenueSpec.ideal(funded=False), report_total=True)


def test_venue_spec_validation_and_overrides():
    spec = VenueSpec()
    assert spec.unknown_fields() == list(COST_FIELDS) + ["funded"]
    for bad in (dict(fee_bp=-1.0), dict(min_fee=float("nan")), dict(leverage_cap=0.0), dict(contract_notional=0.0),
                dict(lot_step="1"), dict(half_spread_bp=True), dict(funded="yes"), dict(fee_bp=math.inf),
                dict(min_notional=math.inf)):
        with pytest.raises(Refused):
            VenueSpec(**bad)
    assert VenueSpec(leverage_cap=math.inf).leverage_cap == math.inf     # only the cap may be unbounded
    filled = spec.with_overrides(fee_bp=1.5, funded=True)
    assert filled.fee_bp == 1.5 and filled.funded is True and spec.fee_bp is None       # the original is untouched
    assert filled.notes["fee_bp"] == {"status": "override", "value": 1.5, "was": None}
    with pytest.raises(Refused, match="unknown VenueSpec field"):
        spec.with_overrides(commission=1.0)
    with pytest.raises(Refused, match="UNKNOWN"):
        spec.require(["fee_bp"])
    filled.require(["fee_bp", "funded"])
    # an overridden field is named in the result's meta
    panel = panel_of({"A": [10.0] * 3})
    res = simulate_account(panel, weights(panel, {"A": [0.5] * 3}), equity0=1000.0,
                           venue=VenueSpec().with_overrides(fee_bp=1.0, min_fee=0.0, half_spread_bp=0.0, lot_step=0.0,
                                                            min_notional=0.0, contract_notional=1.0,
                                                            financing_long_bp_year=0.0, leverage_cap=1.0))
    assert "fee_bp" in res.meta["venue"]["A"]["overridden"] and res.meta["venue"]["A"]["fee_bp"] == 1.0


def test_from_json_is_tolerant_and_never_guesses(tmp_path):
    doc = {
        "schema": {"version": 1},
        "venues": [
            {"venue_id": "other"},
            {
                "venue_id": "demo",
                "fee_bp_taker": {"fx_cfd": 0.2, "share_cfd": None, "note": "prose"},
                "min_fee_per_order": {"fx_cfd": {"amount": 2.0, "currency": "USD"},
                                      "share_cfd": {"amount": 3.0, "currency": "EUR"},
                                      "stable": {"amount": 1.0, "currency": "EURC"}},
                "typical_half_spread_bp": {"fx_cfd": "UNKNOWN", "share_cfd": "0.8"},
                "lot_step": "0.01 lot (1,000 base units)",
                "min_order_notional": None,
                "contract_multiplier": {"value": 1},
                "financing_long_bp_year": {"fx_cfd": {"benchmark": "tom-next", "markup_bp": 200, "detail": "..."},
                                           "share_cfd": {"benchmark": "BM", "markup_bp": None}},
                "financing_short_bp_year": 150,
                "leverage_caps": {"fx_cfd": 30, "share_cfd": "5 (isolated only)"},
                "cash_interest_threshold": {"EUR": 10000, "USD": 12000, "rate_above": "BM - 0.5%"},
                "cash_interest_bp_year": -5,
                "funded": False,
            },
        ],
    }
    path = tmp_path / "venues.json"
    path.write_text(json.dumps(doc))
    fx = VenueSpec.from_json(path, "demo", instrument_class="fx_cfd", currency="USD")
    assert fx.fee_bp == 0.2 and fx.min_fee == 2.0 and fx.financing_long_bp_year == 200.0
    assert fx.financing_short_bp_year == 150.0 and fx.leverage_cap == 30.0 and fx.contract_notional == 1.0
    assert fx.cash_interest_threshold == 12000.0 and fx.funded is False
    assert fx.venue_id == "demo" and fx.instrument_class == "fx_cfd" and fx.currency == "USD"
    # unknowns: "UNKNOWN", prose, null, a missing key, and a negative number (never a silent zero)
    assert fx.half_spread_bp is None and fx.lot_step is None and fx.min_notional is None
    assert fx.cash_interest_bp_year is None and "negative" in fx.notes["cash_interest_bp_year"]["why"]
    assert fx.notes["lot_step"]["status"] == "unknown" and "free text" in fx.notes["lot_step"]["why"]
    assert fx.notes["fee_bp"]["status"] == "ok" and fx.notes["fee_bp"]["json_key"] == "fee_bp_taker"
    assert set(fx.unknown_fields()) == {"half_spread_bp", "lot_step", "min_notional", "cash_interest_bp_year"}
    # a EUR simulation must not read a USD minimum fee as EUR — nor a EURC one (whole-word currency match)
    fx_eur = VenueSpec.from_json(path, "demo", instrument_class="fx_cfd", currency="EUR")
    assert fx_eur.min_fee is None and "quoted in 'USD'" in fx_eur.notes["min_fee"]["why"]
    assert fx_eur.cash_interest_threshold == 10000.0
    assert VenueSpec.from_json(path, "demo", instrument_class="stable", currency="EUR").min_fee is None
    share = VenueSpec.from_json(path, "demo", instrument_class=("share_etf_cfd", "share_cfd"), currency="EUR")
    assert share.fee_bp is None and share.min_fee == 3.0 and share.half_spread_bp == 0.8
    assert share.financing_long_bp_year is None and share.leverage_cap is None
    # no class given: class-keyed objects are unknown, plain numbers still load
    bare = VenueSpec.from_json(path, "demo", currency="EUR")
    assert bare.fee_bp is None and "instrument_class" in bare.notes["fee_bp"]["why"] and bare.financing_short_bp_year == 150.0
    empty = VenueSpec.from_json(path, "other")
    assert empty.unknown_fields() == list(COST_FIELDS) + ["funded"]
    # a spec loaded from a sparse file refuses to simulate until its gaps are filled explicitly
    panel = panel_of({"A": [10.0] * 3})
    w = weights(panel, {"A": [0.5] * 3})
    with pytest.raises(Refused, match="half_spread_bp"):
        simulate_account(panel, w, equity0=1000.0, venue=fx)
    ok = fx.with_overrides(half_spread_bp=0.5, lot_step=0.0, min_notional=0.0)
    assert simulate_account(panel, w, equity0=1000.0, venue=ok).meta["venue"]["A"]["overridden"] == \
        ["half_spread_bp", "lot_step", "min_notional"]
    with pytest.raises(Refused, match="not found"):
        VenueSpec.from_json(path, "nope")
    with pytest.raises(Refused, match="cannot read"):
        VenueSpec.from_json(tmp_path / "missing.json", "demo")
    (tmp_path / "broken.json").write_text("{not json")
    with pytest.raises(Refused, match="cannot read"):
        VenueSpec.from_json(tmp_path / "broken.json", "demo")
    # other layouts: {"venues": {id: {...}}}, {id: {...}} and a bare list
    for layout in ({"venues": {"demo": doc["venues"][1]}}, {"demo": doc["venues"][1]}, doc["venues"]):
        alt = tmp_path / "alt.json"
        alt.write_text(json.dumps(layout))
        assert VenueSpec.from_json(alt, "demo", instrument_class="fx_cfd", currency="USD") == fx


@pytest.mark.skipif(not VENUES_JSON.exists(), reason="landscape/venues.json not present")
def test_the_real_venue_file_loads_and_its_gaps_refuse():
    """The landscape file is another builder's and may change: this only checks that every venue loads without
    raising, that nothing unknown comes back as a number, and that an incomplete spec refuses to simulate."""
    try:
        doc = json.loads(VENUES_JSON.read_text())
    except ValueError:
        pytest.skip("landscape/venues.json is being rewritten")
    venues = doc.get("venues", doc) if isinstance(doc, dict) else doc
    if isinstance(venues, dict):
        ids = [k for k, v in venues.items() if isinstance(v, dict)]
    else:
        ids = [v.get("venue_id", v.get("id")) for v in venues if isinstance(v, dict)]
    ids = [i for i in ids if isinstance(i, str)]
    if not ids:
        pytest.skip("no venue entries recognised in landscape/venues.json")
    panel = panel_of({"A": [10.0] * 3})
    w = weights(panel, {"A": [0.5] * 3})
    for vid in ids:
        for currency in ("EUR", "USD"):
            spec = VenueSpec.from_json(VENUES_JSON, vid, currency=currency)
            assert isinstance(spec, VenueSpec) and spec.venue_id == vid
            for name in COST_FIELDS:
                value = getattr(spec, name)
                assert value is None or (isinstance(value, float) and math.isfinite(value) and value >= 0)
                assert spec.notes[name]["status"] == ("ok" if value is not None else "unknown")
            missing = [n for n in ALWAYS_REQUIRED + ("financing_long_bp_year",) if getattr(spec, n) is None]
            if missing:
                with pytest.raises(Refused, match="UNKNOWN"):
                    simulate_account(panel, w, equity0=1000.0, venue=spec)


# --------------------------------------------------------------------------------------------------
# One pass through every engine-side module, the way the runner will chain them
# --------------------------------------------------------------------------------------------------
def test_end_to_end_chain_of_the_engine_side_modules():
    from scripts.factory import audit, mtest, stats

    rng = np.random.default_rng(42)
    T, N = 900, 6
    idx = pd.date_range("2018-01-01", periods=T, freq="D", tz="UTC")
    cols = [f"m{j}" for j in range(N)]
    # persistent drifts that flip every ~150 prints: something a trend rule can earn
    drift = np.repeat(rng.choice([-0.0015, 0.0015], size=(T // 150 + 1, N)), 150, axis=0)[:T]
    px = 100 * np.exp(np.cumsum(drift + rng.normal(0, 0.01, (T, N)), axis=0))
    panel = PanelBundle("E2E", pd.DataFrame(px, index=idx, columns=cols),
                        carry=pd.DataFrame(-1e-4, index=idx, columns=cols), meta={"periods_per_year": 365})

    def trend(p, lookback):
        return np.sign(p.prices.pct_change(lookback, fill_method=None)) / len(p.prices.columns)

    def noise(p, seed):
        return pd.DataFrame(np.random.default_rng(seed).choice([-1.0, 1.0], size=p.prices.shape) / len(p.prices.columns),
                            index=p.prices.index, columns=p.prices.columns)

    rules = {f"TREND.{lb}": (trend, {"lookback": lb}) for lb in (20, 40, 80)}
    rules.update({f"NOISE.{s}": (noise, {"seed": s}) for s in range(5)})
    window = (idx[200], None)
    # 1. audit every rule (the seeded noise rule is deterministic and does not look at prices: it passes too)
    for rid, (fn, params) in rules.items():
        res = audit.future_scramble_audit(fn, panel, params, [300, 600, 850], np.random.default_rng(1))
        assert res.passed, (rid, res.detail)
    books = {rid: fn(panel, **params) for rid, (fn, params) in rules.items()}
    # 2. score each rule on the window; multiple testing across the 8
    nets = {}
    for rid, w in books.items():
        r1 = backtest(panel, w, lag=1, cost_bp_side=5.0)
        r2 = backtest(panel, w, lag=2, cost_bp_side=5.0)
        nets[rid] = r1.net
        st = stats.summarize(r1.net, periods_per_year=365, window=window, gross=r1.gross, turnover=r1.turnover,
                             gross_leverage=r1.gross_leverage)
        assert list(st) == list(stats.STAT_KEYS) and st["n_obs"] == T - 200
        prox = audit.lag_sensitivity(r1.net, r2.net, 365, window=window)
        assert prox["flag"] is False or rid.startswith("NOISE")
    frame = pd.DataFrame(nets).loc[idx[200]:]
    sm = mtest.stepm(frame, alpha=0.05, seed=7, reps=400)                # block: the default ceil(2*700^(1/3)) = 18
    assert sm["block"] == 18 and sm["block_source"].startswith("default")
    assert set(sm["superior"]) <= {"TREND.20", "TREND.40", "TREND.80"} and len(sm["superior"]) >= 1
    p_vals = pd.Series({rid: stats.summarize(n, periods_per_year=365, window=window)["p_one_sided"] for rid, n in nets.items()})
    bh = mtest.bh_fdr(p_vals, q=0.10)
    assert set(bh["reject"][bh["reject"]].index) >= set(sm["superior"])
    assert 0.0 <= mtest.pbo_cscv(frame, S=8)["pbo"] <= 1.0
    null = mtest.circular_shift_null(panel, books, window=window, cost_bp_side=5.0, seed=3, n_rep=40, min_shift=150)
    assert null["observed_argmax_id"].startswith("TREND")
    # 3. the primary book from the three audited trend rules: ensemble -> vol target -> engine -> evidence table
    trend_books = {rid: w for rid, w in books.items() if rid.startswith("TREND")}
    ens = portfolio.ensemble(trend_books, {rid: "TREND" for rid in trend_books}, panel, vol_window=60, target=0.10)
    book = portfolio.vol_target(ens, panel, 0.10, vol_window=60, max_gross=3.0)
    assert (book.abs().sum(axis=1) <= 3.0 + 1e-9).all()
    res = backtest(panel, portfolio.apply_buffer(book, 0.10), lag=1, cost_bp_side=5.0, hold_cost_long_bp_year=100.0,
                   hold_cost_short_bp_year=100.0)
    table = stats.evidence_table(res.net, {"FULL": window, "LAST": (idx[600], None)}, 365, gross=res.gross,
                                 turnover=res.turnover, gross_leverage=res.gross_leverage)
    assert table.loc["FULL", "sharpe"] > 0.5 and table.loc["FULL", "n_obs"] == 700
    contrib = stats.contribution_by_instrument(res, window=window)
    assert contrib["abs_share"].sum() == pytest.approx(1.0) and contrib["abs_share"].max() < 0.6
    assert stats.sharpe_ci_bootstrap(res.net, periods_per_year=365, reps=300, seed=1, window=window)["hi"] > 0
    assert portfolio.margin_utilisation(book, {"x": 0.2}, {c: "x" for c in cols}).max() <= 0.6 + 1e-9
    # 4. the same targets in real accounts: units, a 10 % no-trade band, EUR 1 minimum fee
    venue = VenueSpec(fee_bp=5.0, min_fee=1.0, half_spread_bp=2.0, lot_step=0.001, min_notional=5.0, contract_notional=1.0,
                      financing_long_bp_year=100.0, financing_short_bp_year=100.0, leverage_cap=5.0)
    acct = simulate_account(panel, book, equity0=5000.0, venue=venue, window=window, no_trade_band=0.10)
    assert acct.tracking["corr"] > 0.95 and acct.tracking["mean_gap_ann"] < 0
    assert acct.meta["n_orders"] > 0 and acct.meta["ruined_at"] is None and acct.meta["n_trades_skipped_in_band"] > 0
    large = simulate_account(panel, book, equity0=500_000.0, venue=venue, window=window, no_trade_band=0.10)
    assert 0 < large.cost_breakdown["frictions_bp_year"] < acct.cost_breakdown["frictions_bp_year"]
    assert large.meta["n_orders_at_min_fee"] < acct.meta["n_orders_at_min_fee"]
    # without the band the EUR 5,000 account pays the minimum fee on every print for every instrument
    churn = simulate_account(panel, book, equity0=5000.0, venue=venue, window=window)
    assert churn.cost_breakdown["fees"] > 3 * acct.cost_breakdown["fees"]


# --------------------------------------------------------------------------------------------------
# The engine's drift-aware turnover model against the account that actually trades every print
# --------------------------------------------------------------------------------------------------
def slow_book(seed: int):
    """A realistic slow book: 5 instruments at 2 % volatility per print, targets that move a little each print
    around +/-0.2..0.4 (gross ~1.3), with or without carry, on panel prints (lag 1 or 2) or exec prints."""
    rng = np.random.default_rng(7000 + seed)
    T, N = 400, 5
    idx = pd.date_range("2021-01-04", periods=T, freq="B" if seed % 2 else "D", tz="UTC")
    cols = [f"s{j}" for j in range(N)]
    px = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.02, (T, N)), axis=0))
    carry = pd.DataFrame(rng.normal(0, 2e-4, (T, N)), index=idx, columns=cols) if seed % 3 else None
    base = rng.choice([-0.3, 0.2, 0.4], size=N)
    w = base + np.cumsum(rng.normal(0, 0.002, (T, N)), axis=0)
    meta = {"periods_per_year": 252}
    kw = {}
    if seed % 4 == 3:
        meta["exec_prices_strictly_after_decision"] = True
        kw["exec_prices"] = pd.DataFrame(px * np.exp(rng.normal(0, 0.003, (T, N))), index=idx, columns=cols)
        kw["extra_lag"] = 0
    else:
        kw["lag"] = 1 + seed % 2
    return PanelBundle("SLOW", pd.DataFrame(px, index=idx, columns=cols), carry=carry, meta=meta), \
        pd.DataFrame(w, index=idx, columns=cols), kw


def account_cost_booked_like_the_engine(sim: AccountResult) -> np.ndarray:
    """The account's fee at print t as a fraction of its pre-trade equity, moved to row t+1 — the row in which
    the engine books the cost of the trade done at print t."""
    fees = sim.flows["fees"].to_numpy()
    pre_trade_equity = sim.equity.to_numpy() + fees + sim.flows["spread"].to_numpy()
    out = np.zeros(len(fees))
    out[1:] = (fees / pre_trade_equity)[:-1]
    return out


@pytest.mark.parametrize("seed", range(24))
def test_engine_drift_model_cost_matches_the_account_that_trades_every_print(seed):
    """VenueSpec.ideal() plus a proportional fee, a trade on every print, no band: the account pays for restoring
    its targets as prices move — and so does `backtest(turnover_model="drift")`.

    OBSERVED on these 24 books at 10 bp (printed by the test below): the two cost series agree to within 2.2e-6 of
    equity on any print and to within 0.04 % in total. WHY THEY DIFFER AT ALL: the engine measures where a position
    stands against the book's PRICE return alone; the account's equity has also been moved by the fee it paid at
    the previous print and by carry, so its weights before trading are a factor (1+R)/(1+R+carry-fee) away. That
    is a turnover difference of about gross * (fee + |carry|) per print — largest on the print after a big trade
    (after the entry: fee = 10 bp * gross, so the cost gap is about (10 bp)^2 * gross^2 = 1.7e-6) — and it grows
    with the SQUARE of the fee rate. Price and carry legs are identical to 1e-11.
    The "target" model is not close: it misses every re-balancing trade.
    """
    panel, w, kw = slow_book(seed)
    venue = VenueSpec.ideal().with_overrides(fee_bp=10.0)
    sim = simulate_account(panel, w, equity0=1e6, venue=venue, **kw)
    drift = backtest(panel, w, cost_bp_side=10.0, **kw)
    target = backtest(panel, w, cost_bp_side=10.0, turnover_model="target", **kw)
    sim_cost = account_cost_booked_like_the_engine(sim)
    np.testing.assert_allclose(sim.gross.to_numpy(), drift.gross.to_numpy(), rtol=0, atol=1e-11)
    np.testing.assert_allclose(sim.held.to_numpy(), drift.held.to_numpy(), rtol=0, atol=1e-11)
    # --- the drift model: close, print by print and in total
    np.testing.assert_allclose(sim_cost, drift.cost.to_numpy(), rtol=0, atol=5e-6)
    assert abs(sim_cost.sum() / drift.cost.sum() - 1.0) < 1e-3
    np.testing.assert_allclose(sim.net.to_numpy(), drift.net.to_numpy(), rtol=0, atol=5e-6)
    assert sim.turnover.sum() == pytest.approx(drift.turnover.sum(), rel=0.01)
    # --- the target model: not close
    assert sim_cost.sum() > 1.8 * target.cost.sum()
    assert np.abs(sim.net.to_numpy() - target.net.to_numpy()).max() > 10 * np.abs(sim.net.to_numpy() - drift.net.to_numpy()).max()


def test_engine_vs_account_gap_measured_and_explained():
    worst_print = worst_total = 0.0
    ratio_target = []
    for seed in range(24):
        panel, w, kw = slow_book(seed)
        sim = simulate_account(panel, w, equity0=1e6, venue=VenueSpec.ideal().with_overrides(fee_bp=10.0), **kw)
        drift = backtest(panel, w, cost_bp_side=10.0, **kw)
        target = backtest(panel, w, cost_bp_side=10.0, turnover_model="target", **kw)
        sim_cost = account_cost_booked_like_the_engine(sim)
        worst_print = max(worst_print, float(np.abs(sim_cost - drift.cost.to_numpy()).max()))
        worst_total = max(worst_total, abs(float(sim_cost.sum() / drift.cost.sum()) - 1.0))
        ratio_target.append(float(sim_cost.sum() / target.cost.sum()))
    print(f"\n[measured] engine drift model vs account trading every print (24 slow books, 10 bp): max per-print cost gap "
          f"{worst_print:.2e} of equity, max total-cost gap {worst_total:.3%}; the account pays "
          f"{min(ratio_target):.2f}x-{max(ratio_target):.2f}x what the target model charges")
    assert worst_print < 5e-6 and worst_total < 1e-3 and min(ratio_target) > 1.8
    # the reason, checked: with no carry the gap comes from the fee the account has just paid, so it scales with the
    # SQUARE of the fee rate (x2 fee -> x4 gap), and with no fee at all the two engines charge exactly nothing
    panel, w, kw = slow_book(0)                                         # seed 0 has no carry panel
    assert panel.carry is None

    def gap(fee_bp):
        sim = simulate_account(panel, w, equity0=1e6, venue=VenueSpec.ideal().with_overrides(fee_bp=fee_bp), **kw)
        eng = backtest(panel, w, cost_bp_side=fee_bp, **kw)
        return float(np.abs(account_cost_booked_like_the_engine(sim) - eng.cost.to_numpy()).max())

    assert gap(0.0) == 0.0
    assert gap(20.0) / gap(10.0) == pytest.approx(4.0, rel=0.05)
    # and turnover itself: with no fee and no carry the account's sides ARE the engine's drift turnover
    free = simulate_account(panel, w, equity0=1e6, venue=VenueSpec.ideal(), **kw)
    eng = backtest(panel, w, cost_bp_side=0.0, **kw)
    shifted = np.zeros(len(eng.turnover))
    shifted[1:] = free.turnover.to_numpy()[:-1]
    np.testing.assert_allclose(shifted, eng.turnover.to_numpy(), rtol=0, atol=1e-10)
