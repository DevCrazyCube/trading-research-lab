"""Tests for scripts/factory/engine.py — known answers (hand-computed in the comments), refusals,
the exec-price convention, the missing-data policies, the numpy fast path and causality properties.

Run:  cd /home/anont/meme && research/factory/.venv/bin/python -m pytest scripts/factory/tests/test_engine.py -q
"""
from __future__ import annotations

import dataclasses
import inspect
import json

import numpy as np
import pandas as pd
import pytest

from scripts.factory import engine
from scripts.factory.engine import BacktestResult, Refused, backtest, fast_net_returns
from scripts.factory.panel import PanelBundle

ATOL = 1e-12


# --------------------------------------------------------------------------------------------------
# The hand-worked panel K1 (6 daily prints, periods_per_year = 365)
#   A: 100, 110, 121, 108.9, 108.9, 119.79   -> r_A = [nan, +10%, +10%, -10%,   0%, +10%]
#   B:  50,  50,  55,  55,   49.5,  49.5     -> r_B = [nan,   0%, +10%,   0%, -10%,   0%]
#   w_A = [1, 1, 1, 0, 0, 0]      w_B = [0, 0, -0.5, -0.5, 0, 0]
# --------------------------------------------------------------------------------------------------
IDX = pd.date_range("2024-01-01", periods=6, freq="D", tz="UTC")


def k1_panel(carry=None, meta=None, prices=None) -> PanelBundle:
    p = pd.DataFrame(
        {"A": [100.0, 110.0, 121.0, 108.9, 108.9, 119.79], "B": [50.0, 50.0, 55.0, 55.0, 49.5, 49.5]}, index=IDX
    )
    if prices is not None:
        p = prices
    m = {"periods_per_year": 365}
    m.update(meta or {})
    return PanelBundle("TEST", p, carry=carry, meta=m)


def k1_w() -> pd.DataFrame:
    return pd.DataFrame({"A": [1.0, 1.0, 1.0, 0.0, 0.0, 0.0], "B": [0.0, 0.0, -0.5, -0.5, 0.0, 0.0]}, index=IDX)


TARGET = {"turnover_model": "target"}      # the pre-drift convention: only CHANGES of the target are charged


def close(series, expected):
    np.testing.assert_allclose(np.asarray(series, dtype=float), np.asarray(expected, dtype=float), rtol=0, atol=ATOL)


# --------------------------------------------------------------------------------------------------
# Known answers
# --------------------------------------------------------------------------------------------------
def test_known_answer_lag1():
    # held = w.shift(2):  held_A = [0,0,1,1,1,0]   held_B = [0,0,0,0,-0.5,-0.5]
    # price_pnl: t2 = 1*(+10%) = 0.10 ; t3 = 1*(-10%) = -0.10 ; t4 = 1*0 + (-0.5)*(-10%) = +0.05 ; t5 = 0
    # turnover : t2 = |1-0| = 1 ; t3 = 0 ; t4 = |-0.5-0| = 0.5 ; t5 = |0-1| + 0 = 1
    # cost @10bp/side: 0.0010, 0, 0.0005, 0.0010
    # net = [0, 0, 0.0990, -0.1000, 0.0495, -0.0010]          (turnover_model="target": target changes only)
    res = backtest(k1_panel(), k1_w(), lag=1, cost_bp_side=10.0, **TARGET)
    assert res.held["A"].tolist() == [0, 0, 1, 1, 1, 0]
    assert res.held["B"].tolist() == [0, 0, 0, 0, -0.5, -0.5]
    close(res.price_pnl, [0, 0, 0.10, -0.10, 0.05, 0.0])
    close(res.turnover, [0, 0, 1.0, 0.0, 0.5, 1.0])
    close(res.cost, [0, 0, 0.0010, 0.0, 0.0005, 0.0010])
    close(res.carry, [0] * 6)
    close(res.hold_cost, [0] * 6)
    close(res.gross, [0, 0, 0.10, -0.10, 0.05, 0.0])
    close(res.net, [0, 0, 0.0990, -0.1000, 0.0495, -0.0010])
    close(res.gross_leverage, [0, 0, 1.0, 1.0, 1.5, 0.5])
    assert res.meta["shift"] == 2 and res.meta["lag"] == 1 and res.meta["priced_on"] == "prices"
    assert res.meta["n_open_at_end"] == 1            # B is still short on the last print: no exit charged
    assert res.meta["turnover_model"] == "target"
    close(res.turnover_target, res.turnover)         # under "target" the two are the same series


def test_known_answer_lag1_drift_model():
    # The DEFAULT. Same panel, same held; the trade charged on row t is measured from where the previous position
    # STANDS after its own interval:  before_t = held_{t-1} * (1 + r_{t-1}) / (1 + R_{t-1}).
    #   row 2: nothing was held before               -> turnover 1.0            (entry into A)
    #   row 3: held_2 = (1, 0), r_2 = (+10 %, +10 %), R_2 = +0.10 -> A stands at 1*1.10/1.10 = 1 -> turnover 0
    #          (an unlevered single position IS the book: it never drifts)
    #   row 4: held_3 = (1, 0), r_3 = (-10 %, 0), R_3 = -0.10 -> A stands at 0.9/0.9 = 1 -> turnover |-0.5 - 0| = 0.5
    #   row 5: held_4 = (1, -0.5), r_4 = (0, -10 %), R_4 = (-0.5)(-0.10) = +0.05
    #          A stands at 1*1.00/1.05 = 0.952381 ; B stands at -0.5*0.90/1.05 = -0.428571
    #          held_5 = (0, -0.5): turnover = |0 - 0.952381| + |-0.5 + 0.428571| = 0.952381 + 0.071429 = 1.023810
    #          (the short gained, so equity grew and BOTH weights shrank: closing A is a smaller trade, and
    #           the short must be topped back up to -50 %)
    # cost @10bp = [0, 0, 0.001, 0, 0.0005, 0.00102381] ; net = [0, 0, 0.099, -0.10, 0.0495, -0.00102381]
    res = backtest(k1_panel(), k1_w(), lag=1, cost_bp_side=10.0)
    assert res.meta["turnover_model"] == "drift"
    row5 = 1 / 1.05 + (0.5 - 0.45 / 1.05)                                # 0.952381 + 0.071429
    assert row5 == pytest.approx(1.0238095, abs=1e-7)
    close(res.turnover, [0, 0, 1.0, 0.0, 0.5, row5])
    close(res.turnover_target, [0, 0, 1.0, 0.0, 0.5, 1.0])               # the target-only figure is still reported
    close(res.cost, [0, 0, 0.001, 0.0, 0.0005, row5 * 0.001])
    close(res.net, [0, 0, 0.0990, -0.1000, 0.0495, -row5 * 0.001])
    assert res.net.iloc[5] == pytest.approx(-0.0010238095, abs=1e-10)
    close(res.price_pnl, [0, 0, 0.10, -0.10, 0.05, 0.0])                 # the P&L legs do not depend on the model
    # per instrument on row 5: A pays 0.952381 * 10 bp, B pays 0.071429 * 10 bp
    close(res.net_by_instrument["A"], [0, 0, 0.099, -0.10, 0.0, -(1 / 1.05) * 0.001])
    close(res.net_by_instrument["B"], [0, 0, 0.0, 0.0, 0.0495, -(0.5 - 0.45 / 1.05) * 0.001])


def test_drift_known_answer_constant_weights_one_print_plus10_minus5():
    # Two instruments, CONSTANT targets 60 % / 40 %, lag 1 -> held = (0.6, 0.4) from row 2 on.
    #   A: 100, 100, 100, 110, 110  -> r_A = [-, 0, 0, +10 %, 0]
    #   B:  50,  50,  50, 47.5, 47.5 -> r_B = [-, 0, 0,  -5 %, 0]
    # row 2: entry, turnover 1.0 under both models.
    # row 3: the book earns 0.6*0.10 + 0.4*(-0.05) = +0.04. Nothing drifted before it (r_2 = 0): turnover 0.
    # row 4: the positions put on at print 2 have just lived through row 3:
    #        A stands at 0.6*1.10/1.04 = 0.634615 ; B stands at 0.4*0.95/1.04 = 0.365385
    #        "drift":  turnover = |0.6 - 0.634615| + |0.4 - 0.365385| = 0.034615 + 0.034615 = 0.069231 (= 0.072/1.04)
    #                  cost @10bp = 6.9231e-5 -> net[4] = -6.9231e-5
    #        "target": the target did not change -> turnover 0, cost 0, net[4] = 0
    idx5 = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    panel = PanelBundle("DRIFT", pd.DataFrame({"A": [100.0, 100.0, 100.0, 110.0, 110.0],
                                               "B": [50.0, 50.0, 50.0, 47.5, 47.5]}, index=idx5),
                        meta={"periods_per_year": 365})
    w = pd.DataFrame({"A": [0.6] * 5, "B": [0.4] * 5}, index=idx5)
    drift = backtest(panel, w, lag=1, cost_bp_side=10.0)
    target = backtest(panel, w, lag=1, cost_bp_side=10.0, turnover_model="target")
    close(drift.turnover, [0, 0, 1.0, 0.0, 0.072 / 1.04])
    assert drift.turnover.iloc[4] == pytest.approx(0.0692308, abs=1e-7)
    close(drift.cost, [0, 0, 0.001, 0.0, 0.072 / 1.04 * 0.001])
    close(drift.net, [0, 0, -0.001, 0.04, -0.072 / 1.04 * 0.001])
    assert drift.net.iloc[4] == pytest.approx(-6.92308e-5, abs=1e-10)
    close(target.turnover, [0, 0, 1.0, 0.0, 0.0])
    close(target.net, [0, 0, -0.001, 0.04, 0.0])
    close(drift.turnover_target, target.turnover)                        # both figures in one result
    close(drift.gross, target.gross)
    assert drift.meta["turnover_model"] == "drift" and target.meta["turnover_model"] == "target"
    # per-instrument costs: A 10 bp, B 30 bp -> 0.0346154*0.001 + 0.0346154*0.003 = 1.384615e-4
    mixed = backtest(panel, w, lag=1, cost_bp_side={"A": 10.0, "B": 30.0})
    assert mixed.cost.iloc[4] == pytest.approx(0.036 / 1.04 * 0.004, rel=1e-12)
    # the helper itself
    r0 = np.nan_to_num(engine.returns_array(panel.prices.to_numpy()))
    before = engine.positions_before_trade(drift.held.to_numpy(), r0, "drift")
    np.testing.assert_allclose(before[4], [0.66 / 1.04, 0.38 / 1.04], rtol=1e-14)
    np.testing.assert_allclose(before[3], [0.6, 0.4], rtol=1e-14)        # r_2 = 0: nothing moved
    assert before[0].tolist() == [0.0, 0.0] and before[2].tolist() == [0.0, 0.0]
    np.testing.assert_array_equal(engine.positions_before_trade(drift.held.to_numpy(), r0, "target")[1:],
                                  drift.held.to_numpy()[:-1])


def test_drift_model_properties_on_hand_cases():
    idx4 = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    px = pd.DataFrame({"A": [100.0, 100.0, 100.0, 120.0, 120.0]}, index=idx4)       # +20 % on row 3
    panel = PanelBundle("DRIFT", px, meta={"periods_per_year": 365})

    def run(weight):
        return backtest(panel, pd.DataFrame({"A": [weight] * 5}, index=idx4), lag=1, cost_bp_side=10.0)

    # unlevered long 100 %: the position IS the book -> stands at 1.2/1.2 = 1 -> no drift trade
    assert run(1.0).turnover.iloc[4] == 0.0
    # half invested: stands at 0.5*1.2/1.1 = 0.545455 -> sell 0.045455 to get back to 50 %
    assert run(0.5).turnover.iloc[4] == pytest.approx(0.6 / 1.1 - 0.5, rel=1e-12)
    # 2x levered: stands at 2*1.2/1.4 = 1.714286 -> BUY 0.285714 to get back to 200 % (leverage decays on a gain)
    assert run(2.0).turnover.iloc[4] == pytest.approx(2.0 - 2.4 / 1.4, rel=1e-12)
    # short 100 %: loses 20 %, book 0.8, stands at -1*1.2/0.8 = -1.5 -> buy back 0.5 (a losing short grows)
    assert run(-1.0).turnover.iloc[4] == pytest.approx(0.5, rel=1e-12)
    # a book wiped out in one print has no drifted weights: refused under "drift", untouched under "target".
    # -5 x (+20 %) is exactly -100 % on paper and -0.9999999999999998 in floating point: refused all the same.
    wipe = pd.DataFrame({"A": [-5.0] * 5}, index=idx4)
    assert 1.0 + (-5.0) * (120.0 / 100.0 - 1.0) > 0.0                    # the float is a hair above zero
    for weight in (-5.0, -6.0):
        with pytest.raises(Refused, match="<= -100 %"):
            backtest(panel, pd.DataFrame({"A": [weight] * 5}, index=idx4), lag=1, cost_bp_side=10.0)
    assert backtest(panel, wipe, lag=1, cost_bp_side=10.0, turnover_model="target").net.iloc[3] == pytest.approx(-1.0)
    assert run(-4.9).turnover.iloc[4] == pytest.approx(4.9 * 1.2 / 0.02 - 4.9, rel=1e-9)   # 98 % lost: still defined
    # ...but only if a later trade is measured from it: a wipe-out on the LAST row is not refused
    last = PanelBundle("DRIFT", px.iloc[:4], meta={"periods_per_year": 365})
    assert backtest(last, wipe.iloc[:4], lag=1, cost_bp_side=10.0).net.iloc[3] == pytest.approx(-1.0)
    for bad in ("Drift", "", None, 1):
        with pytest.raises(Refused, match="turnover_model"):
            backtest(panel, wipe, lag=1, cost_bp_side=10.0, turnover_model=bad)


def test_a_missing_return_drifts_by_zero_under_the_zero_policy():
    # held = (0.6, 0.4). B's price is missing on row 3, so r_B is NaN on rows 3 and 4; A gains 10 % on row 3.
    #   R_3 = 0.6*0.10 + 0.4*0 (missing -> 0) = +0.06
    #   A stands at 0.6*1.10/1.06 = 0.622642 ; B stands at 0.4*1.00/1.06 = 0.377358   (B "drifts by 0")
    #   turnover[4] = |0.6 - 0.622642| + |0.4 - 0.377358| = 0.045283
    idx5 = pd.date_range("2024-01-01", periods=6, freq="D", tz="UTC")
    px = pd.DataFrame({"A": [100.0, 100.0, 100.0, 110.0, 110.0, 110.0], "B": [50.0, 50.0, 50.0, np.nan, 50.0, 50.0]}, index=idx5)
    panel = PanelBundle("DRIFT", px, meta={"periods_per_year": 365})
    w = pd.DataFrame({"A": [0.6] * 6, "B": [0.4] * 6}, index=idx5)
    with pytest.raises(Refused, match="no return"):
        backtest(panel, w, lag=1, cost_bp_side=10.0)
    res = backtest(panel, w, lag=1, cost_bp_side=10.0, missing_return="zero")
    assert res.meta["n_missing_return_held"] == 2
    assert res.turnover.iloc[4] == pytest.approx(2 * (0.66 / 1.06 - 0.6), rel=1e-12)
    assert res.turnover.iloc[4] == pytest.approx(0.0452830189, abs=1e-9)
    assert res.turnover.iloc[5] == 0.0                                   # row 4's returns: A 0, B missing -> no drift


def test_known_answer_lag2():
    # held = w.shift(3):  held_A = [0,0,0,1,1,1]   held_B = [0,0,0,0,0,-0.5]
    # price_pnl: t3 = -0.10 ; t4 = 0 ; t5 = 1*(+10%) + (-0.5)*0 = +0.10
    # cost @10bp: t3 = 0.0010 (entry A) ; t5 = 0.5*0.0010 = 0.0005 (entry B)
    # net = [0, 0, 0, -0.1010, 0, 0.0995]
    res = backtest(k1_panel(), k1_w(), lag=2, cost_bp_side=10.0)
    close(res.net, [0, 0, 0, -0.1010, 0.0, 0.0995])
    assert res.meta["shift"] == 3


def test_cost_is_booked_on_the_first_row_the_new_position_earns():
    # The trade into A is executed at print 1 (decision at print 0, lag 1). Its cost appears in row 2,
    # the first row with held_A != 0 — not in row 1 and not in row 0.
    res = backtest(k1_panel(), k1_w(), lag=1, cost_bp_side=10.0)
    assert res.cost.iloc[0] == 0.0 and res.cost.iloc[1] == 0.0 and res.cost.iloc[2] == pytest.approx(0.001)


def test_per_instrument_costs_series_and_dict_agree():
    # A 10 bp, B 30 bp. lag 1: cost t2 = 1*0.0010 ; t4 = 0.5*0.0030 = 0.0015 ; t5 = 1*0.0010 (exit A)
    expected = [0, 0, 0.0010, 0.0, 0.0015, 0.0010]
    as_dict = backtest(k1_panel(), k1_w(), lag=1, cost_bp_side={"A": 10.0, "B": 30.0}, **TARGET)
    as_series = backtest(k1_panel(), k1_w(), lag=1, cost_bp_side=pd.Series({"B": 30.0, "A": 10.0, "ZZZ": 99.0}), **TARGET)
    close(as_dict.cost, expected)
    close(as_series.cost, expected)
    assert as_dict.meta["cost_bp_side"] == {"A": 10.0, "B": 30.0}
    # drift model, row 5 (see test_known_answer_lag1_drift_model): A trades 0.952381 at 10 bp, B 0.071429 at 30 bp
    #   = 0.000952381 + 0.000214286 = 0.001166667
    drift = backtest(k1_panel(), k1_w(), lag=1, cost_bp_side={"A": 10.0, "B": 30.0})
    close(drift.cost, [0, 0, 0.0010, 0.0, 0.0015, (1 / 1.05) * 0.001 + (0.5 - 0.45 / 1.05) * 0.003])
    assert drift.cost.iloc[5] == pytest.approx(0.0011666667, abs=1e-9)


def test_reversal_pays_two_sides():
    # w_A = [1, -1, -1, -1, -1, -1] -> held (shift 2) = [0, 0, 1, -1, -1, -1]
    # turnover t2 = 1 ; t3 = |-1 - 1| = 2 ; cost @10bp: 0.001, 0.002
    w = pd.DataFrame({"A": [1.0, -1, -1, -1, -1, -1], "B": [0.0] * 6}, index=IDX)
    res = backtest(k1_panel(), w, lag=1, cost_bp_side=10.0, **TARGET)
    close(res.turnover, [0, 0, 1.0, 2.0, 0, 0])
    close(res.cost, [0, 0, 0.001, 0.002, 0, 0])
    # drift model: the reversal is the same 2.0 (the long stood at 1.0); then on row 4 the short has just gained
    # 10 % (r_3 = -10 %): book 1.10, the short stands at -1*0.90/1.10 = -0.818182 -> 0.181818 is sold to restore -100 %
    drift = backtest(k1_panel(), w, lag=1, cost_bp_side=10.0)
    close(drift.turnover, [0, 0, 1.0, 2.0, 2 / 11, 0.0])
    close(drift.turnover_target, [0, 0, 1.0, 2.0, 0, 0])
    # price: t2 = +0.10 ; t3 = (-1)*(-0.10) = +0.10 ; t4 = 0 ; t5 = (-1)*(+0.10) = -0.10
    close(res.price_pnl, [0, 0, 0.10, 0.10, 0.0, -0.10])


def test_hold_costs_long_and_short_known_answer():
    # daily prints (1 calendar day apart). long 365 bp/yr -> 1 bp per day ; short 730 bp/yr -> 2 bp per day.
    # held_A = [0,0,1,1,1,0] (long)  held_B = [0,0,0,0,-0.5,-0.5] (short)
    # hold_cost: t2 = 1*0.0001 ; t3 = 0.0001 ; t4 = 1*0.0001 + 0.5*0.0002 = 0.0002 ; t5 = 0.5*0.0002 = 0.0001
    res = backtest(k1_panel(), k1_w(), lag=1, cost_bp_side=0.0,
                   hold_cost_long_bp_year=365.0, hold_cost_short_bp_year=730.0)
    close(res.hold_cost, [0, 0, 0.0001, 0.0001, 0.0002, 0.0001])
    close(res.net, np.array([0, 0, 0.10, -0.10, 0.05, 0.0]) - np.array([0, 0, 0.0001, 0.0001, 0.0002, 0.0001]))
    assert res.meta["cost_is_zero"] is True
    assert res.meta["hold_cost_long_defaulted"] is False and res.meta["hold_cost_short_defaulted"] is False


def test_hold_costs_accrue_in_calendar_time_friday_to_monday():
    # Wed 3 Jan, Thu 4, Fri 5, Mon 8, Tue 9 Jan 2024 -> calendar days between prints = [0, 1, 1, 3, 1].
    # Flat prices; long A = 1.0 and short B = 0.5 from the first decision; lag 1 -> held on rows 2, 3, 4.
    # long 365 bp/yr = 1 bp per DAY, short 730 bp/yr = 2 bp per DAY:
    #   row 2 (Fri, 1 day)  : 1*1bp*1 + 0.5*2bp*1 = 0.0002
    #   row 3 (Mon, 3 days) : 1*1bp*3 + 0.5*2bp*3 = 0.0006      <- the weekend is three days of financing
    #   row 4 (Tue, 1 day)  : 0.0002
    idx = pd.DatetimeIndex(["2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09"], tz="UTC") \
        + pd.Timedelta(hours=13, minutes=15)
    assert [d.day_name() for d in idx] == ["Wednesday", "Thursday", "Friday", "Monday", "Tuesday"]
    assert engine.calendar_days(idx).tolist() == [0.0, 1.0, 1.0, 3.0, 1.0]
    prices = pd.DataFrame({"A": [100.0] * 5, "B": [50.0] * 5}, index=idx)
    w = pd.DataFrame({"A": [1.0] * 5, "B": [-0.5] * 5}, index=idx)
    for ppy in (252, 365, 12):                                  # periods_per_year plays no part in the accrual
        res = backtest(PanelBundle("CAL", prices, meta={"periods_per_year": ppy}), w, lag=1, cost_bp_side=0.0,
                       hold_cost_long_bp_year=365.0, hold_cost_short_bp_year=730.0)
        close(res.hold_cost, [0, 0, 0.0002, 0.0006, 0.0002])
        close(res.net, [0, 0, -0.0002, -0.0006, -0.0002])
        assert res.meta["calendar_days_total"] == 6.0 and "ACT/365" in res.meta["hold_cost_day_count"]
    # per instrument too: A's row is 1bp*days, B's row is 0.5*2bp*days
    close(res.net_by_instrument["A"], [0, 0, -0.0001, -0.0003, -0.0001])
    close(res.net_by_instrument["B"], [0, 0, -0.0001, -0.0003, -0.0001])


def test_calendar_days_counts_utc_dates_not_elapsed_hours():
    # ECB fix at 14:15 Frankfurt: 13:15 UTC in winter, 12:15 UTC in summer. Across the clock change
    # (Fri 2024-03-29 13:15 UTC -> Mon 2024-04-01 12:15 UTC) 2.958 days elapse; the day COUNT is 3.
    idx = pd.DatetimeIndex(["2024-03-28 13:15", "2024-03-29 13:15", "2024-04-01 12:15", "2024-04-02 12:15"], tz="UTC")
    assert engine.calendar_days(idx).tolist() == [0.0, 1.0, 3.0, 1.0]
    # two prints on the same UTC date accrue nothing between them; the overnight interval accrues one day
    intraday = pd.DatetimeIndex(["2024-01-02 09:00", "2024-01-02 17:00", "2024-01-03 09:00"], tz="UTC")
    assert engine.calendar_days(intraday).tolist() == [0.0, 0.0, 1.0]
    # a timezone other than UTC is converted first: 23:30 New York on 2 Jan is 04:30 UTC on 3 Jan
    ny = pd.DatetimeIndex(["2024-01-02 12:00", "2024-01-02 23:30"], tz="America/New_York")
    assert engine.calendar_days(ny).tolist() == [0.0, 1.0]
    with pytest.raises(Refused):
        engine.calendar_days(pd.DatetimeIndex(["2024-01-02", "2024-01-03"]))
    # a whole year of business days costs exactly the annual rate, whatever periods_per_year says
    year = pd.bdate_range("2023-01-02", "2024-01-02", tz="UTC")           # spans 365 calendar days, 262 prints
    px = pd.DataFrame({"A": 100.0}, index=year)
    res = backtest(PanelBundle("CAL", px, meta={"periods_per_year": 252}), pd.DataFrame({"A": 1.0}, index=year),
                   lag=1, cost_bp_side=0.0, hold_cost_long_bp_year=200.0)
    held_days = engine.calendar_days(year)[2:].sum()                     # the position exists from row 2
    assert res.hold_cost.sum() == pytest.approx(0.02 * held_days / 365, rel=1e-12)
    assert len(year) == 262 and held_days == 364.0
    assert res.hold_cost.sum() == pytest.approx(0.0199452, abs=1e-7)       # 2 % * 364/365
    # the old per-print rule (bp_year / periods_per_year) would have charged 260 * 2 %/252 = 2.0635 %: 3.5 % too much
    assert (len(year) - 2) * 0.02 / 252 == pytest.approx(res.hold_cost.sum() * 1.0346, rel=1e-3)


def test_hold_costs_per_instrument():
    # long: A 365 bp/yr (1 bp/day), B 0 ; short: A 0, B 3650 bp/yr (10 bp/day)
    # t2,t3: 0.0001 ; t4: 0.0001 + 0.5*0.0010 = 0.0006 ; t5: 0.5*0.0010 = 0.0005
    res = backtest(k1_panel(), k1_w(), lag=1, cost_bp_side=0.0,
                   hold_cost_long_bp_year={"A": 365.0, "B": 0.0},
                   hold_cost_short_bp_year=pd.Series({"A": 0.0, "B": 3650.0}))
    close(res.hold_cost, [0, 0, 0.0001, 0.0001, 0.0006, 0.0005])


def test_hold_cost_default_is_flagged_not_silent():
    res = backtest(k1_panel(), k1_w(), cost_bp_side=1.0)
    assert res.meta["hold_cost_long_defaulted"] is True and res.meta["hold_cost_short_defaulted"] is True
    explicit = backtest(k1_panel(), k1_w(), cost_bp_side=1.0, hold_cost_long_bp_year=0.0, hold_cost_short_bp_year=0.0)
    assert explicit.meta["hold_cost_long_defaulted"] is False and explicit.meta["hold_cost_short_defaulted"] is False
    close(res.net, explicit.net)


def test_carry_is_paid_to_held():
    # carry_A = +2 bp per print, carry_B = -4 bp per print (a short B EARNS 4 bp).
    # carry pnl: t2 = 1*0.0002 ; t3 = 0.0002 ; t4 = 0.0002 + (-0.5)*(-0.0004) = 0.0004 ; t5 = 0.0002
    carry = pd.DataFrame({"A": [0.0002] * 6, "B": [-0.0004] * 6}, index=IDX)
    res = backtest(k1_panel(carry=carry), k1_w(), lag=1, cost_bp_side=10.0)
    close(res.carry, [0, 0, 0.0002, 0.0002, 0.0004, 0.0002])
    close(res.gross, np.array([0, 0, 0.10, -0.10, 0.05, 0.0]) + np.array([0, 0, 0.0002, 0.0002, 0.0004, 0.0002]))
    close(res.net, res.gross - res.cost)
    assert res.meta["has_carry"] is True


# --------------------------------------------------------------------------------------------------
# exec_prices: an execution print strictly later than the decision print, on the same row
#   F_A = [100, 120, 120, 132, 132, 132]  -> rF_A = [nan, +20%,   0%, +10%, 0%,   0%]
#   F_B = [ 50,  50,  50,  45,  45,  54]  -> rF_B = [nan,   0%,   0%, -10%, 0%, +20%]
# --------------------------------------------------------------------------------------------------
def k1_exec() -> pd.DataFrame:
    return pd.DataFrame({"A": [100.0, 120.0, 120.0, 132.0, 132.0, 132.0], "B": [50.0, 50.0, 50.0, 45.0, 45.0, 54.0]},
                        index=IDX)


EXEC_OK = {"exec_prices_strictly_after_decision": True}


def test_exec_prices_extra_lag_0_known_answer():
    # held = w.shift(1): held_A = [0,1,1,1,0,0]  held_B = [0,0,0,-0.5,-0.5,0]   (NOT shift(2): no 25 h delay)
    # price (on F): t1 = 1*0.20 = 0.20 ; t2 = 0 ; t3 = 1*0.10 + (-0.5)*(-0.10) = 0.15 ; t4 = 0 ; t5 = 0
    # turnover: t1 = 1 ; t3 = 0.5 ; t4 = 1 (A out) ; t5 = 0.5 (B out)   cost @10bp: 0.001, 0.0005, 0.001, 0.0005
    # net = [0, 0.199, 0, 0.1495, -0.001, -0.0005]
    res = backtest(k1_panel(meta=EXEC_OK), k1_w(), cost_bp_side=10.0, exec_prices=k1_exec(), extra_lag=0, **TARGET)
    assert res.held["A"].tolist() == [0, 1, 1, 1, 0, 0]
    assert res.held["B"].tolist() == [0, 0, 0, -0.5, -0.5, 0]
    close(res.price_pnl, [0, 0.20, 0.0, 0.15, 0.0, 0.0])
    close(res.net, [0, 0.199, 0.0, 0.1495, -0.001, -0.0005])
    # drift model (default), measured on the EXEC returns: row 4: held_3 = (1, -0.5), rF_3 = (+10 %, -10 %),
    #   R_3 = 0.10 + 0.05 = 0.15 ; A stands at 1.10/1.15 = 0.956522 ; B at -0.5*0.90/1.15 = -0.391304
    #   held_4 = (0, -0.5): turnover = 0.956522 + |-0.5 + 0.391304| = 1.065217 -> cost 0.001065217
    drift = backtest(k1_panel(meta=EXEC_OK), k1_w(), cost_bp_side=10.0, exec_prices=k1_exec(), extra_lag=0)
    row4 = 1.1 / 1.15 + (0.5 - 0.45 / 1.15)
    assert row4 == pytest.approx(1.0652174, abs=1e-7)
    close(drift.turnover, [0, 1.0, 0.0, 0.5, row4, 0.5])
    close(drift.net, [0, 0.199, 0.0, 0.1495, -row4 * 0.001, -0.0005])
    assert res.meta["priced_on"] == "exec_prices" and res.meta["shift"] == 1
    assert res.meta["lag"] is None and res.meta["extra_lag"] == 0
    assert res.meta["n_open_at_end"] == 0


def test_exec_prices_extra_lag_1_known_answer():
    # held = w.shift(2) on F: held_A = [0,0,1,1,1,0]  held_B = [0,0,0,0,-0.5,-0.5]
    # price: t2 = 1*0 ; t3 = 1*0.10 ; t4 = 0 + (-0.5)*0 ; t5 = (-0.5)*(+0.20) = -0.10
    # cost @10bp: t2 = 0.001 ; t4 = 0.0005 ; t5 = 0.001
    # net = [0, 0, -0.001, 0.10, -0.0005, -0.101]
    res = backtest(k1_panel(meta=EXEC_OK), k1_w(), cost_bp_side=10.0, exec_prices=k1_exec(), extra_lag=1)
    close(res.net, [0, 0, -0.001, 0.10, -0.0005, -0.101])
    assert res.meta["shift"] == 2


def test_exec_prices_returns_are_taken_on_the_exec_series_only():
    # Changing panel.prices (the decision print) must not change any P&L when exec_prices is given.
    w = k1_w()
    a = backtest(k1_panel(meta=EXEC_OK), w, cost_bp_side=3.0, exec_prices=k1_exec())
    other = pd.DataFrame({"A": [7.0, 8, 9, 10, 11, 12], "B": [3.0, 2, 5, 4, 6, 1]}, index=IDX)
    b = backtest(k1_panel(meta=EXEC_OK, prices=other), w, cost_bp_side=3.0, exec_prices=k1_exec())
    close(a.net, b.net)


@pytest.mark.parametrize("flag", ["absent", False, 1, "True", None])
def test_exec_prices_refused_without_the_data_layers_assertion(flag):
    meta = {} if flag == "absent" else {"exec_prices_strictly_after_decision": flag}
    with pytest.raises(Refused, match="exec_prices refused"):
        backtest(k1_panel(meta=meta), k1_w(), cost_bp_side=10.0, exec_prices=k1_exec())


def test_exec_prices_timing_refusals():
    panel = k1_panel(meta=EXEC_OK)
    with pytest.raises(Refused, match="must\\s+be left at its default"):
        backtest(panel, k1_w(), lag=2, cost_bp_side=10.0, exec_prices=k1_exec())
    with pytest.raises(Refused, match="extra_lag must be an integer >= 0"):
        backtest(panel, k1_w(), cost_bp_side=10.0, exec_prices=k1_exec(), extra_lag=-1)
    with pytest.raises(Refused, match="extra_lag must be an integer >= 0"):
        backtest(panel, k1_w(), cost_bp_side=10.0, exec_prices=k1_exec(), extra_lag=0.0)
    with pytest.raises(Refused, match="no meaning without exec_prices"):
        backtest(panel, k1_w(), cost_bp_side=10.0, extra_lag=1)
    with pytest.raises(Refused, match="identical to panel.prices"):
        backtest(panel, k1_w(), cost_bp_side=10.0, exec_prices=panel.prices.copy())


def test_exec_prices_alignment_refusals():
    panel = k1_panel(meta=EXEC_OK)
    with pytest.raises(Refused, match="index"):
        backtest(panel, k1_w(), cost_bp_side=1.0, exec_prices=k1_exec().iloc[:-1])
    with pytest.raises(Refused, match="columns"):
        backtest(panel, k1_w(), cost_bp_side=1.0, exec_prices=k1_exec().rename(columns={"B": "C"}))
    bad = k1_exec()
    bad.loc[IDX[2], "A"] = -1.0
    with pytest.raises(Refused, match="exec_prices must be > 0"):
        backtest(panel, k1_w(), cost_bp_side=1.0, exec_prices=bad)
    with pytest.raises(Refused, match="DataFrame"):
        backtest(panel, k1_w(), cost_bp_side=1.0, exec_prices=k1_exec().to_numpy())


def test_exec_equals_decision_fraction_is_reported():
    f = k1_exec()
    f.loc[IDX[0], "A"] = 100.0      # equals P_A[0] = 100 ; B[0] = 50 and B[1] = 50 also equal P_B -> 3 of 12 cells
    res = backtest(k1_panel(meta=EXEC_OK), k1_w(), cost_bp_side=1.0, exec_prices=f)
    assert res.meta["exec_equals_decision_frac"] == pytest.approx(3 / 12)


# --------------------------------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lag", [0, -1, 1.0, True, "1", None])
def test_lag_below_one_or_not_an_integer_is_refused(lag):
    with pytest.raises(Refused, match="lag"):
        backtest(k1_panel(), k1_w(), lag=lag, cost_bp_side=10.0)


def test_cost_is_required():
    with pytest.raises(TypeError):
        backtest(k1_panel(), k1_w(), lag=1)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "cost",
    [None, True, -1.0, float("nan"), float("inf"), {"A": 1.0}, {"A": 1.0, "B": float("nan")}, {"A": 1.0, "B": -2.0},
     {"A": 1.0, "B": None}, pd.Series({"A": 1.0}), "5", [1.0, 2.0], pd.Series([1.0, 2.0], index=["A", "A"])],
)
def test_missing_negative_or_nan_cost_refuses(cost):
    with pytest.raises(Refused, match="cost_bp_side"):
        backtest(k1_panel(), k1_w(), lag=1, cost_bp_side=cost)


@pytest.mark.parametrize("bad", [None, -5.0, float("nan"), {"A": 10.0}, True])
def test_bad_hold_cost_refuses(bad):
    with pytest.raises(Refused, match="hold_cost_long_bp_year"):
        backtest(k1_panel(), k1_w(), cost_bp_side=1.0, hold_cost_long_bp_year=bad)
    with pytest.raises(Refused, match="hold_cost_short_bp_year"):
        backtest(k1_panel(), k1_w(), cost_bp_side=1.0, hold_cost_short_bp_year=bad)


def test_weight_alignment_refusals_and_column_reordering():
    panel = k1_panel()
    with pytest.raises(Refused, match="index"):
        backtest(panel, k1_w().iloc[1:], cost_bp_side=1.0)
    with pytest.raises(Refused, match="columns"):
        backtest(panel, k1_w().rename(columns={"B": "C"}), cost_bp_side=1.0)
    with pytest.raises(Refused, match="columns"):
        backtest(panel, k1_w()[["A"]], cost_bp_side=1.0)
    with pytest.raises(Refused, match="DataFrame"):
        backtest(panel, k1_w().to_numpy(), cost_bp_side=1.0)
    w_inf = k1_w()
    w_inf.loc[IDX[0], "A"] = np.inf
    with pytest.raises(Refused, match="inf"):
        backtest(panel, w_inf, cost_bp_side=1.0)
    # columns in another order are re-ordered by NAME, never by position
    swapped = backtest(panel, k1_w()[["B", "A"]], cost_bp_side=10.0, **TARGET)
    close(swapped.net, [0, 0, 0.0990, -0.1000, 0.0495, -0.0010])
    assert list(swapped.held.columns) == ["A", "B"]


def test_non_positive_prices_and_bad_inputs_refuse():
    p = k1_panel().prices.copy()
    p.loc[IDX[3], "A"] = 0.0
    with pytest.raises(Refused, match="panel.prices must be > 0"):
        backtest(k1_panel(prices=p), k1_w(), cost_bp_side=1.0)
    with pytest.raises(Refused, match="missing_return"):
        backtest(k1_panel(), k1_w(), cost_bp_side=1.0, missing_return="ffill")
    with pytest.raises(Refused, match="PanelBundle"):
        backtest(k1_panel().prices, k1_w(), cost_bp_side=1.0)
    with pytest.raises(Refused, match="periods_per_year"):
        backtest(k1_panel(meta={"periods_per_year": 0}), k1_w(), cost_bp_side=1.0)


# --------------------------------------------------------------------------------------------------
# Missing data
# --------------------------------------------------------------------------------------------------
def test_nan_target_is_flat_and_counted():
    w = k1_w()
    w.loc[IDX[0], "A"] = np.nan       # A's first target is "no view" -> held_A = [0,0,0,1,1,0]
    res = backtest(k1_panel(), w, lag=1, cost_bp_side=10.0, **TARGET)
    assert res.held["A"].tolist() == [0, 0, 0, 1, 1, 0]
    assert res.meta["n_nan_w"] == 1
    # net: t2 = 0 ; t3 = 1*(-0.10) - 0.001 = -0.101 ; t4 = 0 + 0.05 - 0.0005 ; t5 = -0.001
    close(res.net, [0, 0, 0.0, -0.101, 0.0495, -0.001])


def test_missing_return_refuse_names_the_cell_and_zero_counts_it():
    # A's price at row 3 is missing -> r_A is NaN on rows 3 and 4, where held_A = 1.
    p = k1_panel().prices.copy()
    p.loc[IDX[3], "A"] = np.nan
    panel = k1_panel(prices=p)
    with pytest.raises(Refused) as exc:
        backtest(panel, k1_w(), lag=1, cost_bp_side=10.0)
    assert "'A'" in str(exc.value) and str(IDX[3]) in str(exc.value) and "2 held position(s) have no return" in str(exc.value)
    res = backtest(panel, k1_w(), lag=1, cost_bp_side=10.0, missing_return="zero", **TARGET)
    assert res.meta["n_missing_return_held"] == 2 and res.meta["missing_return_policy"] == "zero"
    # row 3: A earns 0 instead of -0.10 ; row 4: A earns 0, B earns +0.05 ; costs unchanged (held is not altered)
    close(res.net, [0, 0, 0.0990, 0.0, 0.0495, -0.0010])
    assert res.held["A"].tolist() == [0, 0, 1, 1, 1, 0]      # still the pure shift
    close(res.gross_leverage, [0, 0, 1.0, 1.0, 1.5, 0.5])    # the dead position still counts


def test_unheld_missing_prices_are_not_a_problem():
    # B's price is missing on rows 0-1, where held_B = 0: nothing to refuse.
    p = k1_panel().prices.copy()
    p.loc[IDX[0], "B"] = np.nan
    p.loc[IDX[1], "B"] = np.nan
    res = backtest(k1_panel(prices=p), k1_w(), lag=1, cost_bp_side=10.0, **TARGET)
    assert res.meta["n_missing_return_held"] == 0
    # r_B on row 2 is NaN too (no previous price) but held_B[2] = 0 ; everything else as in the base case
    close(res.net, [0, 0, 0.0990, -0.1000, 0.0495, -0.0010])


def test_delisting_under_zero_policy():
    # B's price ends after row 3. held_B = -0.5 on rows 4 and 5: two cells with no return, marked at the last price.
    p = k1_panel().prices.copy()
    p.loc[IDX[4]:, "B"] = np.nan
    res = backtest(k1_panel(prices=p), k1_w(), lag=1, cost_bp_side=10.0, missing_return="zero")
    assert res.meta["n_missing_return_held"] == 2
    # t4: A 0 + B 0 - 0.0005 (the entry into B is still charged) ; t5: -0.001 (exit A)
    close(res.net, [0, 0, 0.0990, -0.1000, -0.0005, -0.0010])


def test_missing_carry_refuses_and_zero_counts():
    carry = pd.DataFrame({"A": [0.0002] * 6, "B": [-0.0004] * 6}, index=IDX)
    carry.loc[IDX[3], "A"] = np.nan     # held_A[3] = 1 -> the financing leg of a held position is unknown
    panel = k1_panel(carry=carry)
    with pytest.raises(Refused, match="first missing carry: 'A'"):
        backtest(panel, k1_w(), lag=1, cost_bp_side=10.0)
    res = backtest(panel, k1_w(), lag=1, cost_bp_side=10.0, missing_return="zero")
    assert res.meta["n_missing_carry_held"] == 1 and res.meta["n_missing_return_held"] == 0
    close(res.carry, [0, 0, 0.0002, 0.0, 0.0004, 0.0002])
    carry_inf = carry.fillna(np.inf)
    with pytest.raises(Refused, match="inf"):
        backtest(k1_panel(carry=carry_inf), k1_w(), lag=1, cost_bp_side=10.0, missing_return="zero")


# --------------------------------------------------------------------------------------------------
# Result contract
# --------------------------------------------------------------------------------------------------
def test_result_has_the_contract_fields_and_no_statistics():
    res = backtest(k1_panel(), k1_w(), cost_bp_side=10.0)
    names = [f.name for f in dataclasses.fields(BacktestResult)]
    assert names == ["net", "gross", "price_pnl", "carry", "cost", "hold_cost", "held", "turnover",
                     "gross_leverage", "meta", "net_by_instrument", "turnover_target"]
    assert not hasattr(res, "stats")
    src = inspect.getsource(engine)
    assert "summarize" not in src.replace("stats.summarize(result.net", "")   # mentioned once, in the docstring
    assert "from .stats" not in src and "import stats" not in src
    json.dumps(res.meta)                                                      # meta must be JSON-serialisable
    for s in (res.net, res.gross, res.price_pnl, res.carry, res.cost, res.hold_cost, res.turnover, res.gross_leverage,
              res.turnover_target):
        assert s.index.equals(IDX) and s.dtype == np.float64 and not s.isna().any()


def test_signature_matches_the_contract():
    sig = inspect.signature(backtest)
    assert list(sig.parameters) == ["panel", "w", "lag", "cost_bp_side", "hold_cost_long_bp_year",
                                    "hold_cost_short_bp_year", "exec_prices", "extra_lag", "missing_return",
                                    "turnover_model"]
    assert sig.parameters["turnover_model"].default == "drift"
    assert sig.parameters["lag"].default == 1
    assert sig.parameters["cost_bp_side"].default is inspect.Parameter.empty
    assert sig.parameters["hold_cost_long_bp_year"].default == 0.0
    assert sig.parameters["hold_cost_short_bp_year"].default == 0.0
    assert sig.parameters["exec_prices"].default is None and sig.parameters["extra_lag"].default == 0
    assert sig.parameters["missing_return"].default == "refuse"
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for n, p in sig.parameters.items() if n not in ("panel", "w"))
    fast_sig = inspect.signature(fast_net_returns)
    assert list(fast_sig.parameters) == ["held", "r", "carry", "cost_frac", "hc_long", "hc_short", "days"]
    assert all(p.default is inspect.Parameter.empty for p in fast_sig.parameters.values())   # no defaults at all


def test_net_by_instrument_known_answer_and_sums_to_net():
    # A: t2 = +0.10 - 0.001 = 0.099 ; t3 = -0.10 ; t4 = 0 ; t5 = -0.001 (exit)
    # B: t4 = +0.05 - 0.0005 = 0.0495 ; t5 = 0
    res = backtest(k1_panel(), k1_w(), lag=1, cost_bp_side=10.0, **TARGET)
    close(res.net_by_instrument["A"], [0, 0, 0.099, -0.10, 0.0, -0.001])
    close(res.net_by_instrument["B"], [0, 0, 0.0, 0.0, 0.0495, 0.0])
    close(res.net_by_instrument.sum(axis=1), res.net)
    drift = backtest(k1_panel(), k1_w(), lag=1, cost_bp_side=10.0)       # the drift model's costs are attributed too
    close(drift.net_by_instrument.sum(axis=1), drift.net)


# --------------------------------------------------------------------------------------------------
# Random panels: identities, the fast path, linearity, causality
# --------------------------------------------------------------------------------------------------
def random_case(seed: int, with_exec: bool = False):
    rng = np.random.default_rng(seed)
    T, N = int(rng.integers(25, 70)), int(rng.integers(1, 6))
    idx = pd.date_range("2022-06-01", periods=T, freq="B" if seed % 3 else "D", tz="UTC")   # weekends in 2 of 3
    cols = [f"I{j}" for j in range(N)]
    prices = pd.DataFrame(100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, (T, N)), axis=0)), index=idx, columns=cols)
    carry = pd.DataFrame(rng.normal(0, 2e-4, (T, N)), index=idx, columns=cols)
    w_arr = rng.normal(0, 0.5, (T, N))
    w_arr[rng.random((T, N)) < 0.2] = 0.0
    w_arr[: int(rng.integers(0, 6))] = np.nan
    w = pd.DataFrame(w_arr, index=idx, columns=cols)
    meta = {"periods_per_year": 252}
    kwargs = dict(
        cost_bp_side=pd.Series(rng.uniform(0, 30, N), index=cols),
        hold_cost_long_bp_year=pd.Series(rng.uniform(0, 400, N), index=cols),
        hold_cost_short_bp_year=pd.Series(rng.uniform(0, 400, N), index=cols),
    )
    if with_exec:
        meta["exec_prices_strictly_after_decision"] = True
        kwargs["exec_prices"] = prices * np.exp(rng.normal(0, 0.004, (T, N)))
        kwargs["extra_lag"] = int(rng.integers(0, 3))
    else:
        kwargs["lag"] = int(rng.integers(1, 4))
    return PanelBundle("RND", prices, carry=carry, meta=meta), w, kwargs


@pytest.mark.parametrize("seed", range(30))
def test_identities_and_fast_path_equal_backtest(seed):
    panel, w, kw = random_case(seed, with_exec=bool(seed % 2))
    drift = backtest(panel, w, **kw)                                     # the default model
    res = backtest(panel, w, turnover_model="target", **kw)              # the model the fast path implements
    for out in (drift, res):
        np.testing.assert_allclose(out.gross, out.price_pnl + out.carry, rtol=0, atol=1e-15)
        np.testing.assert_allclose(out.net, out.gross - out.cost - out.hold_cost, rtol=0, atol=1e-15)
        np.testing.assert_allclose(out.net_by_instrument.sum(axis=1), out.net, rtol=0, atol=1e-12)
        np.testing.assert_allclose(out.turnover_target, (out.held - out.held.shift(1).fillna(0.0)).abs().sum(axis=1),
                                   atol=1e-15)
        np.testing.assert_allclose(out.gross_leverage, out.held.abs().sum(axis=1), rtol=0, atol=1e-15)
        assert (out.cost >= 0).all() and (out.hold_cost >= 0).all()
    np.testing.assert_array_equal(res.turnover.to_numpy(), res.turnover_target.to_numpy())
    for name in ("gross", "price_pnl", "carry", "hold_cost", "gross_leverage", "turnover_target"):
        np.testing.assert_array_equal(getattr(drift, name).to_numpy(), getattr(res, name).to_numpy())
    # the drift formula, re-derived with pandas: before_t = held_{t-1} (1 + r_{t-1}) / (1 + R_{t-1})
    px_frame = kw.get("exec_prices") if "exec_prices" in kw else panel.prices
    ret = px_frame.pct_change(fill_method=None).fillna(0.0)
    grown = (drift.held * (1.0 + ret)).div(1.0 + (drift.held * ret).sum(axis=1), axis=0)
    expected_turnover = (drift.held - grown.shift(1).fillna(0.0)).abs().sum(axis=1)
    np.testing.assert_allclose(drift.turnover, expected_turnover, rtol=0, atol=1e-12)
    cost_series = pd.Series(kw["cost_bp_side"]).reindex(panel.prices.columns) / 1e4
    np.testing.assert_allclose(drift.cost, (drift.held - grown.shift(1).fillna(0.0)).abs().mul(cost_series, axis=1).sum(axis=1),
                               rtol=0, atol=1e-13)

    # the lean numpy path, fed the same resolved inputs
    px = (kw.get("exec_prices") if "exec_prices" in kw else panel.prices).to_numpy()
    r = engine.returns_array(px)
    r0 = np.where(np.isnan(r), 0.0, r)
    days = engine.calendar_days(panel.prices.index)
    cost_frac = kw["cost_bp_side"].to_numpy() / 1e4
    hcl = kw["hold_cost_long_bp_year"].to_numpy() / 1e4                   # ANNUAL fractions
    hcs = kw["hold_cost_short_bp_year"].to_numpy() / 1e4
    fast = fast_net_returns(res.held.to_numpy(), r0, panel.carry.to_numpy(), cost_frac, hcl, hcs, days)
    np.testing.assert_allclose(fast, res.net.to_numpy(), rtol=0, atol=1e-12)
    # leading (batch) dimensions broadcast: two formulas stacked
    stacked = np.stack([res.held.to_numpy(), -0.5 * res.held.to_numpy()])
    fast2 = fast_net_returns(stacked, r0, panel.carry.to_numpy(), cost_frac, hcl, hcs, days)
    assert fast2.shape == (2, len(res.net))
    np.testing.assert_allclose(fast2[0], res.net.to_numpy(), rtol=0, atol=1e-12)
    flipped = backtest(panel, -0.5 * w, turnover_model="target", **kw)
    np.testing.assert_allclose(fast2[1], flipped.net.to_numpy(), rtol=0, atol=1e-12)
    # the fast path is NOT the default model: with a non-zero cost and moving prices the two differ
    if float(res.cost.sum()) > 0:
        assert not np.allclose(fast, drift.net.to_numpy(), rtol=0, atol=1e-12)


def test_fast_net_returns_known_answer_and_refusals():
    # one instrument, held = [0, 1, 1, -1], r = [0, +1%, -2%, +3%], carry = 1 bp per print, cost 10 bp/side,
    # hold long 365 bp/yr (1 bp/day), hold short 730 bp/yr (2 bp/day), calendar days = [0, 1, 3, 1] (a weekend on row 2)
    # t1: 0.01 + 0.0001 - 1*0.001 - 1bp*1           = 0.0090
    # t2: -0.02 + 0.0001 - 0      - 1bp*3           = -0.0202
    # t3: -0.03 - 0.0001 - 2*0.001 - 2bp*1          = -0.0323
    held = np.array([[0.0], [1.0], [1.0], [-1.0]])
    r = np.array([[0.0], [0.01], [-0.02], [0.03]])
    carry = np.full((4, 1), 0.0001)
    days = np.array([0.0, 1.0, 3.0, 1.0])
    out = fast_net_returns(held, r, carry, 0.001, 0.0365, 0.0730, days)
    close(out, [0.0, 0.0090, -0.0202, -0.0323])
    close(fast_net_returns(held, r, None, 0.001, 0.0, 0.0, days), [0.0, 0.009, -0.02, -0.032])
    with pytest.raises(Refused, match="NaN-free"):
        fast_net_returns(np.array([[np.nan]]), np.array([[0.0]]), None, 0.0, 0.0, 0.0, np.array([0.0]))
    with pytest.raises(Refused, match="disagree"):
        fast_net_returns(held, r[:3], None, 0.0, 0.0, 0.0, days)
    with pytest.raises(Refused, match="carry"):
        fast_net_returns(held, r, np.full((4, 1), np.nan), 0.0, 0.0, 0.0, days)
    with pytest.raises(Refused, match="cost_frac"):
        fast_net_returns(held, r, None, np.array([0.1, 0.2]), 0.0, 0.0, days)
    with pytest.raises(Refused, match="hc_short"):
        fast_net_returns(held, r, None, 0.0, 0.0, -1.0, days)
    for bad_days in (days[:3], np.array([0.0, 1.0, np.nan, 1.0]), np.array([0.0, -1.0, 1.0, 1.0])):
        with pytest.raises(Refused, match="days"):
            fast_net_returns(held, r, None, 0.0, 0.0, 0.0, bad_days)
    with pytest.raises(TypeError):
        fast_net_returns(held, r, None, 0.0, 0.0, 0.0)                    # days is required: no silent calendar


@pytest.mark.parametrize("seed", range(8))
def test_linearity_in_w(seed):
    panel, w, kw = random_case(100 + seed, with_exec=bool(seed % 2))
    k = 0.37
    # under "target" every leg is linear in w
    base = backtest(panel, w, turnover_model="target", **kw)
    scaled = backtest(panel, k * w, turnover_model="target", **kw)
    for name in ("price_pnl", "carry", "cost", "hold_cost", "net", "turnover", "gross_leverage"):
        np.testing.assert_allclose(getattr(scaled, name), k * getattr(base, name), rtol=0, atol=1e-13)
    # under "drift" the P&L legs, hold cost and the target turnover still are; the charged turnover is NOT
    # (how far a position drifts from its target depends on leverage: an unlevered single long never drifts)
    base_d = backtest(panel, w, **kw)
    scaled_d = backtest(panel, k * w, **kw)
    for name in ("price_pnl", "carry", "hold_cost", "gross_leverage", "turnover_target"):
        np.testing.assert_allclose(getattr(scaled_d, name), k * getattr(base_d, name), rtol=0, atol=1e-13)
    assert not np.allclose(scaled_d.turnover, k * base_d.turnover, rtol=0, atol=1e-9)


@pytest.mark.parametrize("seed", range(10))
def test_engine_is_causal(seed):
    """Row t of every output depends on w rows <= t - shift and on prices/carry rows <= t only."""
    panel, w, kw = random_case(200 + seed, with_exec=bool(seed % 2))
    base = backtest(panel, w, **kw)
    shift = base.meta["shift"]
    rng = np.random.default_rng(seed)
    T = len(w)
    s = int(rng.integers(3, T - 3))
    # (1) change every target from row s on: outputs before row s + shift are bit-identical
    w2 = w.copy()
    w2.iloc[s:] = rng.normal(0, 1, w2.iloc[s:].shape)
    alt = backtest(panel, w2, **kw)
    cut = s + shift
    for name in ("net", "gross", "cost", "hold_cost", "turnover", "gross_leverage"):
        assert np.array_equal(getattr(alt, name).to_numpy()[:cut], getattr(base, name).to_numpy()[:cut])
    assert not np.array_equal(alt.net.to_numpy(), base.net.to_numpy())
    # (2) change prices, exec prices and carry after row s: outputs up to row s are bit-identical
    prices2 = panel.prices.copy()
    prices2.iloc[s + 1:] = prices2.iloc[s + 1:] * 1.5
    carry2 = panel.carry.copy()
    carry2.iloc[s + 1:] = 0.123
    kw2 = dict(kw)
    if "exec_prices" in kw:
        f2 = kw["exec_prices"].copy()
        f2.iloc[s + 1:] = f2.iloc[s + 1:] * 0.7
        kw2["exec_prices"] = f2
    panel2 = PanelBundle("RND", prices2, carry=carry2, meta=dict(panel.meta))
    alt2 = backtest(panel2, w, **kw2)
    assert np.array_equal(alt2.net.to_numpy()[: s + 1], base.net.to_numpy()[: s + 1])
    assert not np.array_equal(alt2.net.to_numpy(), base.net.to_numpy())


def test_exec_lag_convention_is_one_row_earlier_than_the_v1_draft():
    """Regression for DESIGN_v2 §0 row 6: on exec prices the shift is 1 + extra_lag, not 1 + lag."""
    panel, w, kw = random_case(999, with_exec=True)
    kw["extra_lag"] = 0
    res = backtest(panel, w, **kw)
    expected_held = w.shift(1).fillna(0.0)
    assert np.array_equal(res.held.to_numpy(), expected_held.to_numpy())
    assert not np.array_equal(res.held.to_numpy(), w.shift(2).fillna(0.0).to_numpy())


def test_short_panels_do_not_crash():
    one = PanelBundle("S", pd.DataFrame({"A": [1.0]}, index=IDX[:1]), meta={"periods_per_year": 252})
    res = backtest(one, pd.DataFrame({"A": [1.0]}, index=IDX[:1]), cost_bp_side=1.0)
    assert res.net.tolist() == [0.0] and res.meta["n_open_at_end"] == 0
    two = PanelBundle("S", pd.DataFrame({"A": [1.0, 2.0]}, index=IDX[:2]), meta={"periods_per_year": 252})
    res = backtest(two, pd.DataFrame({"A": [1.0, 1.0]}, index=IDX[:2]), cost_bp_side=1.0)
    assert res.net.tolist() == [0.0, 0.0]            # shift 2: nothing is held inside two prints


# --------------------------------------------------------------------------------------------------
# Public helpers (shared with mtest / portfolio / realism): one known answer each
# --------------------------------------------------------------------------------------------------
def test_helper_known_answers():
    # returns_array: X = [[10, 4], [11, nan], [12.1, 5]] -> row 1: [10 %, nan] ; row 2: [10 %, nan (previous missing)]
    r = engine.returns_array(np.array([[10.0, 4.0], [11.0, np.nan], [12.1, 5.0]]))
    assert np.isnan(r[0]).all() and r[1, 0] == pytest.approx(0.10) and np.isnan(r[1, 1])
    assert r[2, 0] == pytest.approx(0.10) and np.isnan(r[2, 1])
    # shift_positions_array: shift 2 moves row t to row t+2 and zero-fills the first two rows
    w = np.array([[1.0], [2.0], [3.0], [4.0]])
    assert engine.shift_positions_array(w, 2)[:, 0].tolist() == [0.0, 0.0, 1.0, 2.0]
    assert engine.shift_positions_array(np.stack([w, -w]), 1)[1, :, 0].tolist() == [0.0, -1.0, -2.0, -3.0]   # batch dims
    assert engine.shift_positions_array(w, 9)[:, 0].tolist() == [0.0] * 4
    for bad in (0, -1, 1.5, True):
        with pytest.raises(Refused, match="shift"):
            engine.shift_positions_array(w, bad)
    # resolve_per_instrument: scalar / dict / Series, aligned to the requested order, in the input's own unit
    cols = ["A", "B"]
    assert engine.resolve_per_instrument(3, cols, "x").tolist() == [3.0, 3.0]
    assert engine.resolve_per_instrument({"B": 2.0, "A": 1.0, "C": 9.0}, cols, "x").tolist() == [1.0, 2.0]
    assert engine.resolve_per_instrument(pd.Series({"B": 0.0, "A": 7.5}), cols, "x").tolist() == [7.5, 0.0]
    # resolve_shift: 1 + lag on panel prints ; 1 + extra_lag on exec prints
    plain, certified = k1_panel(), k1_panel(meta=EXEC_OK)
    assert engine.resolve_shift(plain, 1, 0, None) == 2 and engine.resolve_shift(plain, 3, 0, None) == 4
    assert engine.resolve_shift(certified, 1, 0, k1_exec()) == 1 and engine.resolve_shift(certified, 1, 2, k1_exec()) == 3
    assert engine.validate_lag(2) == 2 and engine.validate_extra_lag(0) == 0
    # validate_weights returns the panel's column order and keeps NaN ; validate_prices returns the array
    arr = engine.validate_weights(k1_w()[["B", "A"]], plain)
    assert arr[2].tolist() == [1.0, -0.5]
    assert engine.validate_prices(plain.prices)[0].tolist() == [100.0, 50.0]
    assert engine.aligned_exec_prices(certified, k1_exec()[["B", "A"]])[1].tolist() == [120.0, 50.0]
    assert engine.MIN_LAG == 1 and engine.DEFAULT_LAG == 1 and engine.EXEC_FLAG == "exec_prices_strictly_after_decision"


# --------------------------------------------------------------------------------------------------
# The two booking conventions listed under STATED LIMITS
# --------------------------------------------------------------------------------------------------
def test_cost_of_a_fill_is_booked_one_row_after_the_fill():
    # A is bought at print 1 (decision at row 0, lag 1). Cash leaves at print 1; the engine books the 10 bp in
    # row 2, the first row the position earns. Totals are the same; the row is one later than a fill-print booking.
    res = backtest(k1_panel(), k1_w(), lag=1, cost_bp_side=10.0)
    assert res.cost.iloc[1] == 0.0 and res.cost.iloc[2] == pytest.approx(0.001)
    assert res.turnover.iloc[1] == 0.0 and res.turnover.iloc[2] == 1.0
    # on exec prices with extra_lag 0 the fill is on the decision row itself and is booked on the next row
    ex = backtest(k1_panel(meta=EXEC_OK), k1_w(), cost_bp_side=10.0, exec_prices=k1_exec())
    assert ex.cost.iloc[0] == 0.0 and ex.cost.iloc[1] == pytest.approx(0.001)


@pytest.mark.parametrize("lag", [1, 2, 3])
def test_a_target_decided_on_the_last_shift_prints_is_never_booked(lag):
    """held_t = w_{t - (1 + lag)}: the decisions of the last 1 + lag rows would first be held after the sample."""
    w = k1_w()
    base = backtest(k1_panel(), w, lag=lag, cost_bp_side=10.0)
    wild = w.copy()
    wild.iloc[-(1 + lag):] = [[9.0, -9.0]] * (1 + lag)                  # absurd targets on the last 1 + lag rows
    same = backtest(k1_panel(), wild, lag=lag, cost_bp_side=10.0)
    for name in ("net", "gross", "cost", "hold_cost", "turnover", "gross_leverage"):
        assert np.array_equal(getattr(same, name).to_numpy(), getattr(base, name).to_numpy()), name
    assert np.array_equal(same.held.to_numpy(), base.held.to_numpy())
    # one row earlier and the result does change (when that row exists)
    if len(w) > 2 + lag:
        moved = w.copy()
        moved.iloc[-(2 + lag)] = [9.0, -9.0]
        assert not np.array_equal(backtest(k1_panel(), moved, lag=lag, cost_bp_side=10.0).net.to_numpy(), base.net.to_numpy())
