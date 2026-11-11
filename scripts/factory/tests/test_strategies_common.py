"""Known-answer tests of `strategies/common.py` (builder B2).

Every expected number below was computed BY HAND (the arithmetic is written out next to it) or by an
independent explicit loop inside the test — never by calling the function under test twice.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sps

from scripts.factory.strategies import common as C
from scripts.factory.tests.test_strategies_synth import mini_panel, prices_from_returns

NAN = float("nan")


def col(frame, name="A"):
    return frame[name].to_numpy(dtype=float)


def alternating(n, a, first=+1.0):
    """[ignored, +a, -a, +a, ...] — n values; the first is the (unused) return of the first print."""
    return [0.0] + [a * first * (1.0 if i % 2 == 0 else -1.0) for i in range(n - 1)]


# --------------------------------------------------------------------------------------------------
# excess returns and the excess-return index
# --------------------------------------------------------------------------------------------------
def test_excess_returns_is_price_return_plus_carry():
    p = mini_panel({"A": [100, 110, 99, 121]}, carry={"A": [NAN, 0.001, 0.001, 0.001]})
    # 110/100-1 = 0.10 ; 99/110-1 = -0.10 ; 121/99-1 = 0.2222...  (+ 0.001 each)
    np.testing.assert_allclose(col(C.excess_returns(p)), [NAN, 0.101, -0.099, 2 / 9 + 0.001], rtol=0, atol=1e-15)
    no_carry = mini_panel({"A": [100, 110, 99, 121]})
    np.testing.assert_allclose(col(C.excess_returns(no_carry)), [NAN, 0.10, -0.10, 2 / 9], rtol=0, atol=1e-15)


def test_excess_returns_unknown_carry_is_unknown_not_zero():
    p = mini_panel({"A": [100, 110, 99, 121]}, carry={"A": [NAN, 0.001, NAN, 0.001]})
    e = col(C.excess_returns(p))
    assert np.isnan(e[2]) and e[1] == pytest.approx(0.101) and e[3] == pytest.approx(2 / 9 + 0.001)


def test_excess_index_hand_computed():
    p = mini_panel({"A": [100, 110, 99, 121]}, carry={"A": [NAN, 0.001, 0.001, 0.001]})
    # X = 1 ; 1.101 ; 1.101*0.901 = 0.992001 ; 0.992001*(1+2/9+0.001) = 3640313003/3000000000
    np.testing.assert_allclose(col(C.excess_index(p)), [1.0, 1.101, 0.992001, 3640313003 / 3000000000],
                               rtol=1e-15, atol=0)


def test_excess_index_starts_at_one_on_each_first_valid_print():
    p = mini_panel({"A": [10, 11, 12.1, 13.31], "B": [NAN, NAN, 50, 55]})
    x = C.excess_index(p)
    np.testing.assert_allclose(col(x, "A"), [1.0, 1.1, 1.21, 1.331], rtol=1e-14)
    np.testing.assert_allclose(col(x, "B"), [NAN, NAN, 1.0, 1.1], rtol=1e-14)


def test_excess_index_gap_is_nan_and_contributes_no_growth():
    # print 2 is missing: returns of rows 2 and 3 are unknown; the level resumes at row 4.
    p = mini_panel({"A": [100, 110, NAN, 120, 132]})
    np.testing.assert_allclose(col(C.excess_index(p)), [1.0, 1.1, NAN, NAN, 1.1 * 1.1], rtol=1e-14)


def test_carry_changes_a_flat_price_into_a_rising_index():
    p = mini_panel({"A": [100, 100, 100]}, carry={"A": [NAN, 0.002, 0.002]})
    np.testing.assert_allclose(col(C.excess_index(p)), [1.0, 1.002, 1.002 ** 2], rtol=1e-15)


def test_lookback_return_and_skip():
    x = pd.DataFrame({"A": [1.0, 2.0, 4.0, 8.0, 16.0]})
    np.testing.assert_allclose(col(C.lookback_return(x, 2)), [NAN, NAN, 3.0, 3.0, 3.0])
    np.testing.assert_allclose(col(C.lookback_return(x, 3, skip=1)), [NAN, NAN, NAN, 3.0, 3.0])   # 4/1-1, 8/2-1
    with pytest.raises(ValueError):
        C.lookback_return(x, 2, skip=2)


# --------------------------------------------------------------------------------------------------
# volatility
# --------------------------------------------------------------------------------------------------
def test_vol_estimate_alternating_returns_known_answer():
    # returns +1 %, -1 %, ...: a 60-print window holds 30 of each, mean 0, sum of squares 60 * 1e-4
    # std(ddof=1) = 0.01 * sqrt(60/59) = 0.010084389681792214 ; * sqrt(252) = 0.1600847233313279
    p = mini_panel({"A": prices_from_returns(alternating(200, 0.01))})
    v = col(C.vol_estimate(p))
    assert np.isnan(v[:40]).all() and np.isfinite(v[40:]).all()        # needs 40 returns: rows 1..40
    np.testing.assert_allclose(v[60:], 0.1600847233313279, rtol=1e-10)
    # row 40 has exactly 40 returns (20 up, 20 down): 0.01 * sqrt(40/39) * sqrt(252)
    assert v[40] == pytest.approx(0.01 * math.sqrt(40 / 39) * math.sqrt(252), rel=1e-10)
    assert col(C.daily_vol(p))[100] == pytest.approx(0.010084389681792214, rel=1e-10)


def test_vol_estimate_uses_periods_per_year():
    p = mini_panel({"A": prices_from_returns(alternating(100, 0.01))}, ppy=365, freq="D")
    assert col(C.vol_estimate(p))[-1] == pytest.approx(0.19266199435227643, rel=1e-10)     # * sqrt(365)


def test_vol_estimate_floor_is_a_quarter_of_its_own_expanding_median():
    # rows 1..300: +-2 % ; rows 301..399: +-0.1 %. At the last row the raw 60-print estimate is
    # 0.001*sqrt(60/59*252) = 0.016008..., but the history of the estimate (rows 40..399, 360 values) is
    # 40 low + 59 transition values < H, 241 values = H, 20 warm-up values > H, so its median is
    # H = 0.02*sqrt(60/59*252) and the floor is 0.25 * H = 0.08004236166566395.
    rets = alternating(301, 0.02) + [0.001 * (1.0 if i % 2 == 0 else -1.0) for i in range(99)]
    p = mini_panel({"A": prices_from_returns(rets)})
    v = col(C.vol_estimate(p))
    assert v[-1] == pytest.approx(0.08004236166566395, rel=1e-9)
    assert v[300] == pytest.approx(0.02 * math.sqrt(60 / 59 * 252), rel=1e-9)             # un-floored before
    raw = col(C.excess_returns(p).rolling(60, min_periods=40).std()) * math.sqrt(252)
    assert raw[-1] == pytest.approx(0.01600847233313279, rel=1e-9)
    assert (v[40:] >= raw[40:] - 1e-15).all()                                             # a floor, never a cap


def test_vol_estimate_floor_is_causal():
    rets = alternating(301, 0.02) + [0.001 * (1.0 if i % 2 == 0 else -1.0) for i in range(99)]
    full = mini_panel({"A": prices_from_returns(rets)})
    cut = mini_panel({"A": prices_from_returns(rets[:350])})
    np.testing.assert_array_equal(col(C.vol_estimate(cut)), col(C.vol_estimate(full))[:350])


def test_vol_estimate_zero_volatility_is_nan():
    p = mini_panel({"A": [100.0] * 80})
    assert np.isnan(col(C.vol_estimate(p))).all()


def test_vol_scaled_return_hand_computed():
    p = mini_panel({"A": prices_from_returns(alternating(200, 0.01))})
    sigma = 0.01 * math.sqrt(60 / 59)                                # per-print std of the +-1 % series
    z = col(C.vol_scaled_return(p, 21))
    # rows 80..100 hold 11 even (down) and 10 odd (up) rows: ret = 1.01^10 * 0.99^11 - 1, spanning 21 prints
    assert z[100] == pytest.approx((1.01 ** 10 * 0.99 ** 11 - 1) / (sigma * math.sqrt(21)), rel=1e-9)
    assert z[100] == pytest.approx(-0.23780, abs=1e-5)                 # -0.010989557 / 0.046212481
    # skip: X_{96} / X_{90} - 1 at row 100 spans SIX prints (rows 91..96: three up, three down)
    zs = col(C.vol_scaled_return(p, 10, skip=4))
    assert zs[100] == pytest.approx((1.01 ** 3 * 0.99 ** 3 - 1) / (sigma * math.sqrt(6)), rel=1e-9)
    assert np.isnan(z[:40]).all() and np.isfinite(z[40:]).all()      # needs the 40-return volatility
    # twice the volatility with the same path shape: the raw return more than doubles (1.02^10 * 0.98^11 - 1
    # = -0.0239 against -0.0110), the scaled return moves by under 10 % (-0.2587 against -0.2378)
    q = mini_panel({"A": prices_from_returns(alternating(200, 0.02))})
    raw_ratio = (1.02 ** 10 * 0.98 ** 11 - 1) / (1.01 ** 10 * 0.99 ** 11 - 1)
    scaled_ratio = col(C.vol_scaled_return(q, 21))[100] / z[100]
    assert raw_ratio > 2.0 and 1.0 < scaled_ratio < 1.1
    assert scaled_ratio == pytest.approx(raw_ratio / 2.0, rel=1e-9)


# --------------------------------------------------------------------------------------------------
# sizing
# --------------------------------------------------------------------------------------------------
def _frame(panel, rows):
    return pd.DataFrame(rows, index=panel.prices.index, columns=panel.prices.columns, dtype=float)


def test_size_positions_two_instruments_by_hand_and_an_ineligible_one():
    mask = {"A": [True, True], "B": [True, True], "C": [False, False]}
    p = mini_panel({"A": [1, 1], "B": [1, 1], "C": [1, 1]}, aux={"universe_mask": mask})
    sig = _frame(p, [[1.0, -0.5, 1.0], [1.0, -0.5, 1.0]])
    vol = _frame(p, [[0.20, 0.10, 0.25], [0.20, 0.10, 0.25]])
    w = C.size_positions(sig, p, 0.10, vol=vol)
    # N_eligible = 2 (C may not be held):  A = 1 * (0.10/0.20) / 2 = 0.25 ;  B = -0.5 * (0.10/0.10) / 2 = -0.25
    np.testing.assert_allclose(w.to_numpy(), [[0.25, -0.25, 0.0], [0.25, -0.25, 0.0]], rtol=0, atol=1e-15)


def test_size_positions_divides_by_the_eligible_count_not_the_active_count():
    """Conductor ruling 2026-11-10: N_eligible replaces the N_active of DESIGN §3.7."""
    mask = {"A": [True] * 4, "B": [True] * 4, "C": [False] * 4, "D": [True] * 4}
    p = mini_panel({k: [1.0] * 4 for k in "ABCD"}, aux={"universe_mask": mask})
    sig = _frame(p, [[1.0, -0.5, 1.0, 0.0],        # D is eligible but has a ZERO signal: it still counts
                     [1.0, -0.5, 1.0, NAN],        # ... and so does an eligible instrument with NO view
                     [1.0, 0.0, 1.0, 0.0],         # one active instrument out of three eligible
                     [0.0, 0.0, 1.0, NAN]])        # the only signal sits on the ineligible instrument
    vol = _frame(p, [[0.20, 0.10, 0.25, 0.20]] * 4)
    w = C.size_positions(sig, p, 0.10, vol=vol).to_numpy()
    # N_eligible = 3 on every row (A, B, D):  A = (0.10/0.20)/3 = 1/6 ;  B = -0.5*(0.10/0.10)/3 = -1/6
    np.testing.assert_allclose(w[0], [1 / 6, -1 / 6, 0.0, 0.0], atol=1e-15)
    np.testing.assert_allclose(w[1], [1 / 6, -1 / 6, 0.0, 0.0], atol=1e-15)
    # with N_active the lone active instrument would have taken the whole budget (0.5); it takes its third
    np.testing.assert_allclose(w[2], [1 / 6, 0.0, 0.0, 0.0], atol=1e-15)
    np.testing.assert_array_equal(w[3], [0.0, 0.0, 0.0, 0.0])


def test_size_positions_uses_the_eligibility_of_each_row():
    mask = {"A": [True, True, True], "B": [True, False, False], "C": [True, True, False], "D": [True, True, False]}
    p = mini_panel({k: [1.0] * 3 for k in "ABCD"}, aux={"universe_mask": mask})
    sig = _frame(p, [[1.0, 1.0, 1.0, 1.0]] * 3)
    vol = _frame(p, [[0.20, 0.20, 0.20, 0.20]] * 3)
    w = C.size_positions(sig, p, 0.10, vol=vol).to_numpy()
    # 0.10/0.20 = 0.5 per instrument, shared among 4, then 3, then 1 eligible instruments
    np.testing.assert_allclose(w, [[0.125, 0.125, 0.125, 0.125], [1 / 6, 0.0, 1 / 6, 1 / 6], [0.5, 0.0, 0.0, 0.0]],
                               atol=1e-15)


def test_size_positions_cap_zero_and_nan_signals():
    p = mini_panel({"A": [1, 1, 1, 1], "B": [1, 1, 1, 1], "C": [1, 1, 1, 1]})
    sig = _frame(p, [[1.0, 0.0, NAN],          # three eligible: (0.10/0.05)/3 = 2/3 for A, nothing else
                     [1.0, 1.0, NAN],          # A 2/3 ; B (0.10/0.40)/3 = 1/12
                     [-1.0, -1.0, -1.0],       # -2/3 ; -1/12 ; -(0.10/0.20)/3 = -1/6
                     [1.0, -1.0, 0.0]])        # sigma_A = 1 %: (0.10/0.01)/3 = 3.33 -> capped at 1
    vol = _frame(p, [[0.05, 0.40, 0.20]] * 3 + [[0.01, 0.40, 0.20]])
    w = C.size_positions(sig, p, 0.10, vol=vol).to_numpy()
    np.testing.assert_allclose(w, [[2 / 3, 0.0, 0.0], [2 / 3, 1 / 12, 0.0], [-2 / 3, -1 / 12, -1 / 6],
                                   [1.0, -1 / 12, 0.0]], atol=1e-15)
    assert not np.isnan(w).any()


def test_size_positions_signal_without_a_vol_estimate_counts_but_is_flat():
    p = mini_panel({"A": [1, 1], "B": [1, 1]})
    sig = _frame(p, [[1.0, 1.0], [1.0, 1.0]])
    vol = _frame(p, [[0.20, NAN], [0.20, NAN]])
    # N_eligible = 2 (B is eligible; it just cannot be sized yet): A = 0.10/0.20/2 = 0.25, B = 0
    np.testing.assert_allclose(C.size_positions(sig, p, 0.10, vol=vol).to_numpy(), [[0.25, 0.0]] * 2, atol=1e-15)


def test_size_positions_end_to_end_with_the_vol_floor():
    a = prices_from_returns(alternating(400, 0.01))
    b = prices_from_returns(alternating(301, 0.02) + [0.001 * (1.0 if i % 2 == 0 else -1.0) for i in range(99)])
    c = prices_from_returns(alternating(400, 0.03))
    d = prices_from_returns(alternating(400, 0.02))
    mask = {"A": [True] * 400, "B": [True] * 400, "C": [False] * 400, "D": [True] * 400}
    p = mini_panel({"A": a, "B": b, "C": c, "D": d}, aux={"universe_mask": mask})
    sig = pd.DataFrame({"A": 1.0, "B": -1.0, "C": 1.0, "D": 0.0}, index=p.prices.index)
    w = C.size_positions(sig, p, 0.10).iloc[-1]
    # sigma_A = 0.1600847233313279 ; sigma_B = floor = 0.08004236166566395 ; N_eligible = 3 (A, B, D)
    assert w["A"] == pytest.approx(0.10 / 0.1600847233313279 / 3, rel=1e-9)                # 0.20822...
    assert w["B"] == pytest.approx(-0.10 / 0.08004236166566395 / 3, rel=1e-9)             # -0.41645...
    assert w["C"] == 0.0 and w["D"] == 0.0
    assert (C.size_positions(sig, p, 0.10).iloc[:40] == 0.0).all().all()                   # no vol yet -> flat


def test_a_sparse_signal_is_no_longer_a_single_name_bet():
    """One active instrument out of nine: 1/9 of the budget, not all of it."""
    names = list("ABCDEFGHI")
    p = mini_panel({k: prices_from_returns(alternating(100, 0.006)) for k in names})
    sig = pd.DataFrame(0.0, index=p.prices.index, columns=names)
    sig["E"] = 1.0
    w = C.size_positions(sig, p, 0.10).iloc[-1]
    sigma = 0.006 * math.sqrt(60 / 59) * math.sqrt(252)                                    # 9.6 % a year
    assert w["E"] == pytest.approx(0.10 / sigma / 9, rel=1e-9) == pytest.approx(0.1157, abs=1e-4)
    assert w.abs().sum() == pytest.approx(w["E"])                                          # gross 0.116, not 1.0


def test_size_positions_refuses_bad_input():
    p = mini_panel({"A": [1, 1], "B": [1, 1]})
    with pytest.raises(ValueError):
        C.size_positions(_frame(p, [[1.5, 0.0], [0.0, 0.0]]), p, 0.10)
    with pytest.raises(ValueError):
        C.size_positions(_frame(p, [[np.inf, 0.0], [0.0, 0.0]]), p, 0.10)
    with pytest.raises(ValueError):
        C.size_positions(_frame(p, [[1.0, 0.0], [0.0, 0.0]])[["B", "A"]], p, 0.10)
    with pytest.raises(ValueError):
        C.size_positions(_frame(p, [[1.0, 0.0], [0.0, 0.0]]), p, 0.0)


# --------------------------------------------------------------------------------------------------
# smoothing, z-scores
# --------------------------------------------------------------------------------------------------
def test_ewma_hand_computed():
    x = pd.DataFrame({"A": [100.0, 102.0, 101.0, 105.0]})
    # span 2: a = 2/3, weights 1, 1/3, 1/9, 1/27
    #   t1 = (102 + 100/3) / (4/3) = 101.5 ; t2 = (101 + 34 + 100/9) / (13/9) = 1315/13 ; t3 = 4150/40 = 103.75
    np.testing.assert_allclose(col(C.ewma(x, 2)), [NAN, 101.5, 1315 / 13, 103.75], rtol=1e-15)
    # span 4: a = 0.4, weights 1, .6, .36, .216: 162/1.6 = 101.25 ; 198.2/1.96 = 4955/49 ; 223.92/2.176 = 13995/136
    np.testing.assert_allclose(col(C.ewma(x, 4, min_periods=1)), [100.0, 101.25, 4955 / 49, 13995 / 136], rtol=1e-15)


def test_ewma_span_one_is_identity_and_nan_rows_stay_nan():
    x = pd.DataFrame({"A": [1.0, NAN, 3.0, 4.0]})
    np.testing.assert_array_equal(col(C.ewma(x, 1)), [1.0, NAN, 3.0, 4.0])
    out = col(C.ewma(x, 2, min_periods=1))
    assert np.isnan(out[1]) and out[0] == 1.0
    # the missing row still ages the first observation: weights (1/3)^2 and 1 -> (3 + 1/9) / (10/9) = 2.8
    assert out[2] == pytest.approx(2.8, rel=1e-15)


def test_ewm_std_hand_computed():
    d = pd.DataFrame({"A": [NAN, 2.0, -1.0, 4.0]})
    # span 3 (a = 0.5). t2: obs 2 (w .5), -1 (w 1): two points -> sample variance (2-(-1))^2/2 = 4.5
    # t3: obs 2, -1, 4 with w .25, .5, 1: mean 16/7, sum w*(x-m)^2 = 409.5/49, W = 1.75, sum w^2 = 1.3125
    #     var = (409.5/49)/1.75 * 1.75^2/(1.75^2 - 1.3125) = 117/14
    np.testing.assert_allclose(col(C.ewm_std(d, 3, min_periods=1)), [NAN, NAN, math.sqrt(4.5), math.sqrt(117 / 14)],
                               rtol=1e-14)


def test_zscore_clipped_hand_computed():
    x = pd.DataFrame({"A": [1.0, 2.0, 3.0, 4.0, 10.0]})
    # [1,2,3] and [2,3,4]: mean = middle, std = 1 -> z = 1 -> 0.5
    # [3,4,10]: mean 17/3, var = (64/9 + 25/9 + 169/9)/2 = 43/3, z = (13/3)/sqrt(43/3) = 1.1445861782233109
    np.testing.assert_allclose(col(C.zscore_clipped(x, 3)), [NAN, NAN, 0.5, 0.5, 1.1445861782233109 / 2], rtol=1e-12)
    np.testing.assert_allclose(col(C.zscore(x, 3)), [NAN, NAN, 1.0, 1.0, 1.1445861782233109], rtol=1e-12)


def test_zscore_clip_binds_and_constant_window_is_nan():
    spike = pd.DataFrame({"A": [0.0] * 9 + [1.0], "B": [5.0] * 10})
    z = C.zscore(spike, 10)
    assert z["A"].iloc[-1] == pytest.approx(0.9 / math.sqrt(0.1), rel=1e-12)              # 2.846 > 2
    assert C.zscore_clipped(spike, 10)["A"].iloc[-1] == 1.0
    assert C.zscore_clipped(spike, 10)["B"].isna().all()                                  # std = 0 -> no view
    assert C.zscore_clipped(-spike, 10)["A"].iloc[-1] == -1.0


# --------------------------------------------------------------------------------------------------
# cross-sections
# --------------------------------------------------------------------------------------------------
def _xs(rows, eligible=None, cols="abcdefghij"):
    score = pd.DataFrame(rows, columns=list(cols[:len(rows[0])]), dtype=float)
    el = pd.DataFrame(True, index=score.index, columns=score.columns) if eligible is None else \
        pd.DataFrame(eligible, columns=score.columns, dtype=bool)
    return score, el


@pytest.mark.parametrize("ties", ["split", "order"])
def test_xs_tercile_without_ties(ties):
    score, el = _xs([[3, 1, 2, NAN, 5, 4, 0]])
    # six ranked scores -> k = 2: bottom {0, 1} = columns g, b ; top {5, 4} = columns e, f ; d has no score
    out = C.xs_tercile(score, el, ties=ties).iloc[0].to_numpy()
    np.testing.assert_array_equal(out, [0.0, -1.0, 0.0, NAN, 1.0, 1.0, -1.0])


@pytest.mark.parametrize("n,k", [(3, 1), (4, 1), (5, 1), (6, 2), (7, 2), (8, 2), (9, 3), (10, 3)])
def test_xs_tercile_leg_size_is_floor_n_over_3(n, k):
    score, el = _xs([list(range(n))])
    for ties in ("split", "order"):
        out = C.xs_tercile(score, el, ties=ties).iloc[0].to_numpy()
        assert (out == 1.0).sum() == k and (out == -1.0).sum() == k and (out == 0.0).sum() == n - 2 * k
        assert (out[:k] == -1.0).all() and (out[-k:] == 1.0).all()


def test_xs_tercile_fewer_than_three_is_zero_and_ineligible_is_nan():
    score, el = _xs([[1.0, 2.0, NAN, NAN], [1.0, 2.0, 3.0, 4.0]],
                    eligible=[[True, True, True, True], [True, False, True, False]])
    out = C.xs_tercile(score, el).to_numpy()
    np.testing.assert_array_equal(out[0], [0.0, 0.0, NAN, NAN])         # n = 2 -> zero signal, NaN stays NaN
    np.testing.assert_array_equal(out[1], [0.0, NAN, 0.0, NAN])         # only a and c are eligible -> n = 2
    score, el = _xs([[1.0, 2.0, 3.0, 4.0]], eligible=[[True, True, True, False]])
    np.testing.assert_array_equal(C.xs_tercile(score, el).to_numpy()[0], [-1.0, 0.0, 1.0, NAN])   # n = 3, k = 1


def test_xs_tercile_ties_split_shares_the_boundary_slots():
    score, el = _xs([[1, 1, 1, 2, 2, 2]])
    # k = 2. The three 1s occupy positions 1..3, two of which are short slots -> -2/3 each; same on top.
    np.testing.assert_allclose(C.xs_tercile(score, el).to_numpy()[0], [-2 / 3] * 3 + [2 / 3] * 3, rtol=1e-15)
    score, el = _xs([[5, 1, 1, 9, 1, 7]])
    # ascending: 1,1,1 (positions 1..3: b, c, e), 5 (a), 7 (f), 9 (d); k = 2 -> b, c, e share 2 short slots
    np.testing.assert_allclose(C.xs_tercile(score, el).to_numpy()[0], [0.0, -2 / 3, -2 / 3, 1.0, -2 / 3, 1.0], rtol=1e-15)


def test_xs_tercile_ties_order_is_the_column_order_rule():
    score, el = _xs([[1, 1, 1, 2, 2, 2]])
    # ranks "first": a=1, b=2, c=3 | d=4, e=5, f=6 ; k = 2 -> short a, b ; long e, f ; c and d flat
    np.testing.assert_array_equal(C.xs_tercile(score, el, ties="order").to_numpy()[0], [-1.0, -1.0, 0.0, 0.0, 1.0, 1.0])
    score, el = _xs([[5, 1, 1, 9, 1, 7]])
    np.testing.assert_array_equal(C.xs_tercile(score, el, ties="order").to_numpy()[0], [0.0, -1.0, -1.0, 1.0, 0.0, 1.0])


def test_xs_tercile_no_dispersion_is_zero_under_split_and_a_portfolio_under_order():
    score, el = _xs([[0.0] * 9])
    np.testing.assert_array_equal(C.xs_tercile(score, el).to_numpy()[0], [0.0] * 9)
    # the literal column-order rule turns "no information" into short-first-three / long-last-three
    np.testing.assert_array_equal(C.xs_tercile(score, el, ties="order").to_numpy()[0], [-1.0] * 3 + [0.0] * 3 + [1.0] * 3)


def _tercile_expectation_over_tie_breaks(values):
    """Brute force: average the column-order rule over EVERY ordering of the instruments (exact)."""
    from fractions import Fraction
    from itertools import permutations

    n = len(values)
    k = n // 3 if n >= 3 else 0
    total = [Fraction(0)] * n
    count = 0
    for order in permutations(range(n)):                 # `order` = the column order of this world
        ranked = sorted(order, key=lambda i: values[i])  # stable: ties keep the column order
        for i in ranked[:k]:
            total[i] -= 1
        for i in ranked[n - k:] if k else []:
            total[i] += 1
        count += 1
    return [float(t / count) for t in total]


@pytest.mark.parametrize("values", [[1, 1, 1, 2, 2, 2], [5, 1, 1, 9, 1, 7], [0, 0, 0, 0, 0, 0], [3, 3, 1, 3, 3, 2],
                                    [1, 2, 2, 2, 2, 3, 3], [4, 4, 4, 4, 9], [1, 2, 3, 4, 5, 6, 7]])
def test_xs_tercile_split_is_the_expectation_over_all_tie_break_orders(values):
    score, el = _xs([values])
    np.testing.assert_allclose(C.xs_tercile(score, el, ties="split").to_numpy()[0],
                               _tercile_expectation_over_tie_breaks(values), rtol=0, atol=1e-15)


def test_xs_tercile_split_properties_on_heavily_tied_rows():
    rng = np.random.default_rng(3)
    score = pd.DataFrame(rng.integers(0, 4, size=(400, 11)).astype(float))            # many ties
    score = score.mask(rng.random(score.shape) < 0.15)
    el = pd.DataFrame(rng.random(score.shape) < 0.9, columns=score.columns)
    out = C.xs_tercile(score, el)
    pd.testing.assert_frame_equal(out, C.xs_tercile(score, el, ties="split"))
    assert C.DEFAULT_TIES == "split"
    np.testing.assert_allclose(out.sum(axis=1), 0.0, atol=1e-12)                      # long slots = short slots
    assert out.abs().max().max() <= 1.0
    n = (score.where(el).notna()).sum(axis=1)
    k = (n // 3).where(n >= 3, 0)
    assert (out.clip(lower=0).sum(axis=1) <= k + 1e-12).all()                         # never more than k per leg
    order = C.xs_tercile(score, el, ties="order")
    assert set(np.unique(order.to_numpy()[np.isfinite(order.to_numpy())])) <= {-1.0, 0.0, 1.0}
    np.testing.assert_array_equal((order == 1.0).sum(axis=1), k)
    np.testing.assert_array_equal((order == -1.0).sum(axis=1), k)
    # equal scores get equal signals under split; permuting the columns permutes the signal and nothing else
    for t in range(0, 400, 37):
        row, sig = score.where(el).iloc[t], out.iloc[t]
        for value in row.dropna().unique():
            assert sig[row == value].nunique() == 1
    perm = list(rng.permutation(score.columns))
    pd.testing.assert_frame_equal(C.xs_tercile(score[perm], el[perm])[list(score.columns)], out)
    with pytest.raises(ValueError):
        C.xs_tercile(score, el, ties="random")


def test_xs_linear_rank_hand_computed():
    score, el = _xs([[10, 30, 20, NAN], [1, 2, 3, 4], [1, 1, 3, NAN], [7, 7, 7, 7], [1, 2, NAN, NAN]])
    out = C.xs_linear_rank(score, el).to_numpy()
    np.testing.assert_allclose(out[0], [-1.0, 1.0, 0.0, NAN])            # ranks 1,3,2 ; (r - 2) / 1
    np.testing.assert_allclose(out[1], [-1.0, -1 / 3, 1 / 3, 1.0])       # (r - 2.5) / 1.5
    np.testing.assert_allclose(out[2], [-0.5, -0.5, 1.0, NAN])           # tied ranks 1.5, 1.5, 3
    np.testing.assert_allclose(out[3], [0.0, 0.0, 0.0, 0.0])             # no dispersion -> all at the centre
    np.testing.assert_allclose(out[4], [0.0, 0.0, NAN, NAN])             # n = 2 < 3 -> zero


def test_xs_linear_rank_is_mean_zero_bounded_and_respects_eligibility():
    rng = np.random.default_rng(5)
    score = pd.DataFrame(rng.standard_normal((300, 9)))
    el = pd.DataFrame(rng.random(score.shape) < 0.8, columns=score.columns)
    out = C.xs_linear_rank(score, el)
    assert not out.where(~el).notna().any().any()                    # ineligible -> NaN, never a weight
    np.testing.assert_allclose(out.sum(axis=1), 0.0, atol=1e-12)
    n = el.sum(axis=1)
    assert (out.max(axis=1)[n >= 3] == 1.0).all() and (out.min(axis=1)[n >= 3] == -1.0).all()
    assert (out[n < 3].fillna(0.0) == 0.0).all().all()


# --------------------------------------------------------------------------------------------------
# Donchian, RSI, regression slope
# --------------------------------------------------------------------------------------------------
def test_donchian_state_machine_hand_computed():
    x = pd.DataFrame({"A": [10, 11, 12, 11, 10, 9, 12, 13, 12.5, 8]}, dtype=float)
    # channel = previous 3 prints.
    # t3: [10,11,12] -> 11 inside -> 0 (no breakout yet)     t4: [11,12,11] min 11 > 10 -> -1
    # t5: [12,11,10] min 10 > 9 -> -1                         t6: [11,10,9] max 11 < 12 -> +1
    # t7: [10,9,12] max 12 < 13 -> +1                         t8: [9,12,13] 12.5 inside -> hold +1
    # t9: [12,13,12.5] min 12 > 8 -> -1
    np.testing.assert_array_equal(col(C.donchian_state(x, 3)), [NAN, NAN, NAN, 0.0, -1.0, -1.0, 1.0, 1.0, 1.0, -1.0])


def test_donchian_equal_to_the_channel_edge_is_not_a_breakout():
    x = pd.DataFrame({"A": [10, 11, 12, 12, 12, 10, 10]}, dtype=float)
    # 12 == prior max (not >) -> no event ; 10 == prior min at t5? channel [12,12,12] -> 10 < 12 -> -1
    np.testing.assert_array_equal(col(C.donchian_state(x, 3)), [NAN, NAN, NAN, 0.0, 0.0, -1.0, -1.0])


def test_rsi_wilder_hand_computed():
    x = pd.DataFrame({"A": [10, 11, 10.5, 11.5, 11.0, 12.0]})
    # changes +1, -.5, +1, -.5, +1 ; n = 2
    # seed (2nd change): gain (1+0)/2 = .5, loss (0+.5)/2 = .25 -> 100*.5/.75 = 66.667
    # then avg = (avg + new)/2: (.75, .125) -> 85.714 ; (.375, .3125) -> 54.545 ; (.6875, .15625) -> 81.481
    np.testing.assert_allclose(col(C.rsi(x, 2)), [NAN, NAN, 200 / 3, 600 / 7, 600 / 11, 2200 / 27], rtol=1e-14)


def _wilder_rsi_loop(values, n):
    out = [NAN] * len(values)
    gains, losses = [], []
    ag = al = None
    for t in range(1, len(values)):
        d = values[t] - values[t - 1]
        g, l = max(d, 0.0), max(-d, 0.0)
        if ag is None:
            gains.append(g)
            losses.append(l)
            if len(gains) == n:
                ag, al = sum(gains) / n, sum(losses) / n
        else:
            ag, al = (ag * (n - 1) + g) / n, (al * (n - 1) + l) / n
        if ag is not None:
            out[t] = 100.0 * ag / (ag + al) if (ag + al) > 0 else NAN
    return out


@pytest.mark.parametrize("n", [2, 14])
def test_rsi_matches_an_independent_wilder_loop(n):
    rng = np.random.default_rng(11)
    values = list(100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, 300))))
    got = col(C.rsi(pd.DataFrame({"A": values}), n))
    np.testing.assert_allclose(got, _wilder_rsi_loop(values, n), rtol=1e-11)
    assert np.isnan(got[:n]).all() and np.nanmin(got) >= 0.0 and np.nanmax(got) <= 100.0


def test_rsi_extremes_and_flat():
    up = pd.DataFrame({"A": np.arange(1.0, 21.0), "B": np.arange(20.0, 0.0, -1.0), "C": [5.0] * 20})
    r = C.rsi(up, 5)
    assert (r["A"].iloc[5:] == 100.0).all() and (r["B"].iloc[5:] == 0.0).all() and r["C"].isna().all()


def test_rolling_slope_tstat_matches_scipy_linregress():
    rng = np.random.default_rng(2)
    y = pd.DataFrame({"A": np.cumsum(rng.normal(0.01, 1.0, 120)), "B": np.cumsum(rng.normal(0, 0.2, 120))})
    y.loc[50, "B"] = NAN
    out = C.rolling_slope_tstat(y, 30)
    assert out.iloc[:29].isna().all().all()
    for t in (29, 60, 119):
        res = sps.linregress(np.arange(30), y["A"].iloc[t - 29:t + 1].to_numpy())
        assert out["A"].iloc[t] == pytest.approx(res.slope / res.stderr, rel=1e-9)
    assert out["B"].iloc[50:80].isna().all() and np.isfinite(out["B"].iloc[80])           # NaN poisons its windows
    res = sps.linregress(np.arange(30), y["B"].iloc[90:120].to_numpy())
    assert out["B"].iloc[119] == pytest.approx(res.slope / res.stderr, rel=1e-9)


def test_rolling_slope_tstat_degenerate_windows():
    y = pd.DataFrame({"line": np.arange(10.0) * 2.0, "down": -np.arange(10.0), "flat": [3.0] * 10})
    out = C.rolling_slope_tstat(y, 5).iloc[-1]
    assert out["line"] == np.inf and out["down"] == -np.inf and np.isnan(out["flat"])


# --------------------------------------------------------------------------------------------------
# calendar
# --------------------------------------------------------------------------------------------------
def _weekday_calendar(start, end, holidays=(), hour=13, minute=15):
    days = pd.bdate_range(start, end)
    days = days[~days.isin(pd.to_datetime(list(holidays)))]
    return (days + pd.Timedelta(hours=hour, minutes=minute)).tz_localize("UTC")


def _flagged(index, mask):
    return [d.strftime("%Y-%m-%d") for d in index[mask.to_numpy()]]


def test_turn_of_month_weekday_calendar_with_easter_2024():
    # Good Friday 2024-03-29 and Easter Monday 2024-04-01 are not prints (TARGET calendar).
    idx = _weekday_calendar("2024-01-22", "2024-04-05", holidays=("2024-03-29", "2024-04-01"))
    got = _flagged(idx, C.turn_of_month_mask(idx))
    assert got == [
        "2024-01-29", "2024-01-30", "2024-01-31",       # last three weekdays of January
        "2024-02-01", "2024-02-02",                     # first two prints of February
        "2024-02-27", "2024-02-28", "2024-02-29",
        "2024-03-01", "2024-03-04",
        "2024-03-27", "2024-03-28",                     # the third weekday (29th) is a holiday: window of 2
        "2024-04-02", "2024-04-03",                     # first side counts PRINTS, so Easter Monday is skipped
    ]


def test_turn_of_month_daily_calendar_is_exact():
    idx = pd.date_range("2024-01-25", "2024-03-05", freq="D", tz="UTC")
    got = _flagged(idx, C.turn_of_month_mask(idx, calendar="daily"))
    assert got == ["2024-01-29", "2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02",
                   "2024-02-27", "2024-02-28", "2024-02-29", "2024-03-01", "2024-03-02"]


def test_turn_of_month_window_sizes_and_first_month_fallback():
    idx = _weekday_calendar("2024-02-05", "2024-03-06")
    # the panel starts on the third weekday of February: nothing in early February may be flagged
    assert _flagged(idx, C.turn_of_month_mask(idx)) == ["2024-02-27", "2024-02-28", "2024-02-29",
                                                         "2024-03-01", "2024-03-04"]
    idx = _weekday_calendar("2024-02-01", "2024-02-09")
    assert _flagged(idx, C.turn_of_month_mask(idx)) == ["2024-02-01", "2024-02-02"]
    idx = _weekday_calendar("2024-01-22", "2024-03-06")
    assert _flagged(idx, C.turn_of_month_mask(idx, last_n=1, first_n=0)) == ["2024-01-31", "2024-02-29"]
    assert _flagged(idx, C.turn_of_month_mask(idx, last_n=0, first_n=1)) == ["2024-02-01", "2024-03-01"]
    with pytest.raises(ValueError):
        C.turn_of_month_mask(idx, calendar="lunar")


@pytest.mark.parametrize("calendar", ["weekday", "daily"])
def test_turn_of_month_mask_does_not_look_ahead(calendar):
    idx = (_weekday_calendar("2019-11-01", "2021-03-10", holidays=("2020-01-01", "2020-04-10", "2020-12-25"))
           if calendar == "weekday" else pd.date_range("2019-11-01", "2021-03-10", freq="D", tz="UTC"))
    full = C.turn_of_month_mask(idx, calendar=calendar).to_numpy()
    for k in range(1, len(idx) + 1, 7):
        np.testing.assert_array_equal(C.turn_of_month_mask(idx[:k], calendar=calendar).to_numpy(), full[:k])
    per_month = pd.Series(full, index=idx).groupby([idx.year, idx.month]).sum()
    assert per_month.iloc[1:-1].between(3, 5).all()            # 5 prints, minus holidays at a month end


def test_first_print_of_period():
    idx = _weekday_calendar("2023-12-27", "2024-02-06", holidays=("2024-01-01",))
    month = _flagged(idx, C.first_print_of_period(idx, "M"))
    assert month == ["2023-12-27", "2024-01-02", "2024-02-01"]              # the first row is always flagged
    year = _flagged(idx, C.first_print_of_period(idx, "Y"))
    assert year == ["2023-12-27", "2024-01-02"]
    week = _flagged(idx, C.first_print_of_period(idx, "W"))
    # Mondays, except the week of 1 January whose first print is Tuesday the 2nd
    assert week == ["2023-12-27", "2024-01-02", "2024-01-08", "2024-01-15", "2024-01-22", "2024-01-29", "2024-02-05"]
    with pytest.raises(ValueError):
        C.first_print_of_period(idx, "Q")
    daily = pd.date_range("2024-01-01", "2024-01-21", freq="D", tz="UTC")       # 1 January 2024 is a Monday
    assert _flagged(daily, C.first_print_of_period(daily, "W")) == ["2024-01-01", "2024-01-08", "2024-01-15"]


def test_calendar_days_between_prints_and_print_calendar():
    idx = _weekday_calendar("2024-03-25", "2024-04-05", holidays=("2024-03-29", "2024-04-01"))
    # Mon 25, Tue 26, Wed 27, Thu 28, [Fri 29, Mon 1 closed], Tue 2, Wed 3, Thu 4, Fri 5
    np.testing.assert_array_equal(C.calendar_days_between_prints(idx).to_numpy(), [NAN, 1, 1, 1, 5, 1, 1, 1])
    np.testing.assert_array_equal(C.calendar_days_between_prints(idx, 5).to_numpy()[5:], [9, 9, 9])
    assert C.print_calendar(mini_panel({"A": [1, 2]}, ppy=252)) == "weekday"
    assert C.print_calendar(mini_panel({"A": [1, 2]}, ppy=365, freq="D")) == "daily"
    with pytest.raises(ValueError):
        C.calendar_days_between_prints(pd.date_range("2024-01-01", periods=3, freq="D"))     # tz-naive


# --------------------------------------------------------------------------------------------------
# annualised carry
# --------------------------------------------------------------------------------------------------
def _fx_carry_panel(with_rates, with_carry=True):
    idx = _weekday_calendar("2024-01-08", "2024-02-09", holidays=("2024-01-24",))
    days = np.r_[np.nan, np.diff(idx.tz_localize(None).normalize().to_numpy()).astype("timedelta64[D]").astype(float)]
    usd, eur, jpy = 0.05, 0.03, 0.014
    carry = {"EUR": (eur - usd) * days / 360.0, "JPY": (jpy - usd) * days / 360.0}
    aux = {"rates": {"EUR": [eur] * len(idx), "JPY": [jpy] * len(idx), "USD": [usd] * len(idx)}} if with_rates else {}
    return mini_panel({"EUR": [1.1] * len(idx), "JPY": [0.007] * len(idx)}, carry=carry if with_carry else None,
                      aux=aux, index=idx), days


def test_annualised_carry_is_the_rate_differential_when_rates_exist():
    p, _ = _fx_carry_panel(with_rates=True)
    ca = C.annualised_carry(p)
    assert C.carry_source(p) == "rates"
    np.testing.assert_allclose(ca["EUR"].to_numpy(), 0.03 - 0.05, rtol=0, atol=1e-17)     # every row, incl. row 0
    np.testing.assert_allclose(ca["JPY"].to_numpy(), 0.014 - 0.05, rtol=0, atol=1e-17)


def test_annualised_carry_fallback_removes_the_monday_artefact():
    p, days = _fx_carry_panel(with_rates=False)
    assert C.carry_source(p) == "carry"
    raw = p.carry["EUR"].to_numpy()
    assert np.nanmax(raw) / np.nanmin(raw) == pytest.approx(1 / 3)       # Monday accrual (negative) is 3x Tuesday's
    assert sorted(set(days[1:])) == [1.0, 2.0, 3.0]                      # 2 = the Wednesday holiday
    ca = C.annualised_carry(p)
    # five-print sum / calendar days of the same span * 360 = the differential, on every row from the sixth
    assert ca.iloc[:5].isna().all().all()
    np.testing.assert_allclose(ca["EUR"].iloc[5:].to_numpy(), -0.02, rtol=1e-12)
    np.testing.assert_allclose(ca["JPY"].iloc[5:].to_numpy(), -0.036, rtol=1e-12)


def test_annualised_carry_sources_and_missing_inputs():
    p, _ = _fx_carry_panel(with_rates=True)
    p.aux["rates"] = p.aux["rates"][["EUR", "USD"]]                      # JPY has no rate column
    ca = C.annualised_carry(p)
    assert ca["JPY"].isna().all() and (ca["EUR"] == 0.03 - 0.05).all()   # no mixing of sources
    p.aux["rates"] = p.aux["rates"][["USD"]]                             # a rates frame without instruments
    assert C.carry_source(p) == "carry"
    np.testing.assert_allclose(C.annualised_carry(p)["EUR"].iloc[5:].to_numpy(), -0.02, rtol=1e-12)
    bare, _ = _fx_carry_panel(with_rates=False, with_carry=False)
    assert C.carry_source(bare) == "none"
    with pytest.raises(C.NotApplicable):
        C.annualised_carry(bare)


def test_safe_log_never_warns():
    import warnings
    x = pd.DataFrame({"A": [1.0, 0.0, -2.0, NAN, math.e]})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = col(C.safe_log(x))
    np.testing.assert_allclose(out, [0.0, NAN, NAN, NAN, 1.0])
