"""Known-answer tests of the rules of DESIGN_v2 §4 (builder B2).

Expected values are hand-computed (arithmetic in the comments) or come from an independent oracle
written inside the test — an explicit loop, `statistics`, `scipy.stats` — never from the library.
The ML rules are in test_strategies_ml.py; generic contract / no-lookahead checks in
test_strategies_core.py.
"""
from __future__ import annotations

import math
import statistics

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sps

from scripts.factory.strategies import common as C
from scripts.factory.strategies import registry as R
from scripts.factory.strategies import (rules_carry, rules_misc, rules_reversal, rules_trend, rules_value,
                                        rules_xs)
from scripts.factory.tests.test_strategies_common import _weekday_calendar, alternating
from scripts.factory.tests.test_strategies_synth import lane_panel, mini_panel, prices_from_returns

NAN = float("nan")
H60 = 0.01 * math.sqrt(60 / 59)            # per-print std of an alternating +-1 % series over 60 prints


def col(frame, name="A"):
    return frame[name].to_numpy(dtype=float)


def explicit_index(panel, name):
    """Excess-return index by an explicit loop (independent of common.excess_index)."""
    p = panel.prices[name].to_numpy(dtype=float)
    c = None if panel.carry is None else panel.carry[name].to_numpy(dtype=float)
    out, level, started = [NAN] * len(p), 1.0, False
    for t in range(len(p)):
        if math.isnan(p[t]):
            continue
        if not started:
            started, out[t] = True, 1.0
            continue
        e = p[t] / p[t - 1] - 1.0 + (0.0 if c is None else c[t])
        if math.isnan(e):
            continue
        level *= 1.0 + e
        out[t] = level
    return out


# ==================================================================================================
# TREND
# ==================================================================================================
def test_ewmac_three_rows_by_hand():
    x = pd.DataFrame({"A": [100.0, 102.0, 101.0, 105.0]})
    # fast span 2 (weights 1, 1/3, 1/9, ..): 100, 101.5, 1315/13, 103.75
    # slow span 4 (weights 1, .6, .36, ..):  100, 101.25, 4955/49, 13995/136
    # sigma = EW std (span 3) of the changes [., 2, -1, 4]: t2 sqrt(4.5), t3 sqrt(117/14)
    # raw t2 = (1315/13 - 4955/49) / sqrt(4.5)   = 0.014800769883548875
    # raw t3 = (103.75 - 13995/136) / sqrt(117/14) = 0.29250279407460117
    out = col(rules_trend.ewmac_forecast(x, 2, 4, 10.6, vol_span=3, min_periods=1))
    np.testing.assert_allclose(out, [NAN, NAN, 10.6 * 0.014800769883548875 / 20, 10.6 * 0.29250279407460117 / 20],
                               rtol=1e-12)
    assert out[3] == pytest.approx(0.1550264808595386, rel=1e-12)
    capped = col(rules_trend.ewmac_forecast(x, 2, 4, 100.0, vol_span=3, min_periods=1))
    assert capped[3] == 1.0 and capped[2] == pytest.approx(0.07400384941774438, rel=1e-12)   # 29.25 -> cap 20
    assert col(rules_trend.ewmac_forecast(-x, 2, 4, 100.0, vol_span=3, min_periods=1))[3] == -1.0


def test_ewmac_is_scale_free_and_reads_the_excess_index():
    x = pd.DataFrame({"A": 100.0 * np.exp(np.cumsum(np.random.default_rng(0).normal(0, 0.01, 400)))})
    a = rules_trend.ewmac_forecast(x, 8, 32, 5.3)
    np.testing.assert_allclose(a.to_numpy(), rules_trend.ewmac_forecast(7.0 * x, 8, 32, 5.3).to_numpy(), rtol=1e-9)
    # a flat spot price with a positive carry is an UPTREND for a holder: the forecast is long
    flat = mini_panel({"A": [50.0] * 300}, carry={"A": [NAN] + [0.0004] * 299})
    f = col(rules_trend.ewmac(flat, 16, 64))
    assert np.isnan(f[:63]).all() and (f[63:] > 0).all()
    # ... and it is exactly the forecast of the index series itself
    idx_panel = mini_panel({"A": list(C.excess_index(flat)["A"])})
    np.testing.assert_allclose(col(rules_trend.ewmac(idx_panel, 16, 64)), f, rtol=1e-9)


def _brute_ewma(values, span, t):
    q = 1.0 - 2.0 / (span + 1)
    num = den = 0.0
    for i in range(t + 1):
        if not math.isnan(values[t - i]):
            num += q ** i * values[t - i]
            den += q ** i
    return num / den


def _brute_ewstd(values, span, t):
    q = 1.0 - 2.0 / (span + 1)
    w = [q ** (t - s) for s in range(t + 1) if not math.isnan(values[s])]
    v = [values[s] for s in range(t + 1) if not math.isnan(values[s])]
    big_w = sum(w)
    mean = sum(wi * vi for wi, vi in zip(w, v)) / big_w
    biased = sum(wi * (vi - mean) ** 2 for wi, vi in zip(w, v)) / big_w
    return math.sqrt(biased * big_w ** 2 / (big_w ** 2 - sum(wi * wi for wi in w)))


@pytest.mark.parametrize("fast,slow", list(rules_trend.EWMAC_SCALARS))
def test_ewmac_rule_matches_a_brute_force_weighted_sum(fast, slow):
    panel = lane_panel("FX")
    scalar = {(2, 8): 10.6, (4, 16): 7.5, (8, 32): 5.3, (16, 64): 3.75, (32, 128): 2.65, (64, 256): 1.87}[(fast, slow)]
    got = col(rules_trend.ewmac(panel, fast, slow), "CAD")
    x = explicit_index(panel, "CAD")
    dx = [NAN] + [x[t] - x[t - 1] for t in range(1, len(x))]
    first = max(36, slow - 1)                       # 36 changes for sigma, `slow` levels for the slow average
    assert np.isnan(got[:first]).all() and np.isfinite(got[first:]).all()
    for t in (first, first + 17, 700, 1999):
        raw = (_brute_ewma(x, fast, t) - _brute_ewma(x, slow, t)) / _brute_ewstd(dx, 36, t)
        assert got[t] == pytest.approx(max(-20.0, min(20.0, scalar * raw)) / 20.0, rel=1e-8, abs=1e-12)
    assert R.get(f"TREND.EWMAC.{fast}_{slow}").params == {"fast": fast, "slow": slow, "scalar": scalar}


def test_tsmom_sign_hand_computed_on_the_excess_index():
    p = mini_panel({"A": [100, 110, 99, 121], "B": [100, 100, 100, 100], "C": [100, 100, 100, 100]},
                   carry={"A": [NAN, 0.001, 0.001, 0.001], "B": [NAN, 0.002, 0.002, 0.002], "C": [NAN, 0.0, 0.0, 0.0]})
    s = rules_trend.tsmom_sign(p, 2)
    # A: X = 1, 1.101, 0.992001, 1.21343...: X2/X0-1 = -0.007999 -> -1 ; X3/X1-1 = +0.10212 -> +1
    np.testing.assert_array_equal(col(s, "A"), [NAN, NAN, -1.0, 1.0])
    # B: the spot never moves but the holder earns carry -> +1 ; C: nothing earned -> 0
    np.testing.assert_array_equal(col(s, "B"), [NAN, NAN, 1.0, 1.0])
    np.testing.assert_array_equal(col(s, "C"), [NAN, NAN, 0.0, 0.0])


def test_tsmom_z_hand_computed():
    p = mini_panel({"A": prices_from_returns(alternating(200, 0.01))})
    z = col(rules_trend.tsmom_z(p, 21))
    # odd rows +1 %, even rows -1 %. Rows 80..100 hold 11 even rows: ret = 1.01^10 * 0.99^11 - 1 = -0.010989...
    # sigma_daily = 0.01*sqrt(60/59) ; z = ret / (sigma * sqrt(21)) ; signal = z / 2
    assert z[100] == pytest.approx((1.01 ** 10 * 0.99 ** 11 - 1) / (H60 * math.sqrt(21)) / 2, rel=1e-9)
    assert z[101] == pytest.approx((1.01 ** 11 * 0.99 ** 10 - 1) / (H60 * math.sqrt(21)) / 2, rel=1e-9)
    assert z[100] == pytest.approx(-0.11890, abs=5e-5) and z[101] == pytest.approx(0.09728, abs=5e-5)
    assert np.isnan(z[:40]).all()
    # the clip: a 21-print run of +1 % days is 21 %/(sigma*sqrt(21)) ~ 5 sigma -> capped at +1
    run = mini_panel({"A": prices_from_returns(alternating(100, 0.01) + [0.01] * 21)})
    assert col(rules_trend.tsmom_z(run, 21))[-1] == 1.0
    fall = mini_panel({"A": prices_from_returns(alternating(100, 0.01) + [-0.01] * 21)})
    assert col(rules_trend.tsmom_z(fall, 21))[-1] == -1.0


def test_breakout_hand_computed():
    x = pd.DataFrame({"A": [10.0, 12.0, 11.0, 15.0, 13.0], "B": [5.0, 4.0, 3.0, 2.0, 1.0], "C": [7.0] * 5})
    raw = rules_trend.breakout_forecast(x, 3, smooth=1)
    # A: [10,12,11] mid 11 -> 0 ; [12,11,15] mid 13, range 4 -> 2*(15-13)/4 = +1 ; [11,15,13] -> 0
    np.testing.assert_array_equal(col(raw, "A"), [NAN, NAN, 0.0, 1.0, 0.0])
    np.testing.assert_array_equal(col(raw, "B"), [NAN, NAN, -1.0, -1.0, -1.0])     # always at the bottom of its range
    assert raw["C"].isna().all()                                                   # zero range -> no view
    # EWMA span 2 (weights 1, 1/3, 1/9) of [0, 1, 0], reported from the second value:
    #   (1 + 0/3) / (4/3) = 3/4 ;  (0 + 1/3 + 0) / (13/9) = 3/13
    np.testing.assert_allclose(col(rules_trend.breakout_forecast(x, 3, smooth=2), "A"), [NAN, NAN, NAN, 0.75, 3 / 13],
                               rtol=1e-14)


@pytest.mark.parametrize("lookback", [20, 40, 80, 160, 320])
def test_breakout_rule_matches_an_explicit_loop(lookback):
    panel = lane_panel("MACRO")
    got = col(rules_trend.breakout(panel, lookback), "GLD")
    x = explicit_index(panel, "GLD")
    span = lookback // 4
    raw = [NAN] * len(x)
    for t in range(lookback - 1, len(x)):
        w = x[t - lookback + 1:t + 1]
        raw[t] = 2.0 * (x[t] - (max(w) + min(w)) / 2.0) / (max(w) - min(w))
    first = lookback - 1 + span - 1
    assert np.isnan(got[:first]).all()
    for t in (first, first + 5, 1000, 1649):
        assert got[t] == pytest.approx(_brute_ewma(raw, span, t), rel=1e-9, abs=1e-12)
    assert np.nanmax(np.abs(got)) <= 1.0


def test_sma_rules_hand_computed():
    p = mini_panel({"A": [1, 2, 3, 4, 5, 2]})
    # the index of a carry-free panel that starts at 1 is the price itself
    # SMA3 = ., ., 2, 3, 4, 11/3 -> X - SMA3 = 1, 1, 1, -5/3
    np.testing.assert_array_equal(col(rules_trend.sma_sign(p, window=3)), [NAN, NAN, 1.0, 1.0, 1.0, -1.0])
    # SMA2 = ., 1.5, 2.5, 3.5, 4.5, 3.5 ; SMA2 - SMA3 = ., ., .5, .5, .5, -1/6
    np.testing.assert_array_equal(col(rules_trend.sma_cross(p, fast=2, slow=3)), [NAN, NAN, 1.0, 1.0, 1.0, -1.0])
    flat = mini_panel({"A": [3.0] * 6})
    np.testing.assert_array_equal(col(rules_trend.sma_sign(flat, window=3)), [NAN, NAN, 0.0, 0.0, 0.0, 0.0])
    assert R.get("TREND.SMA_SIGN.200").params == {"window": 200}
    assert R.get("TREND.SMA_CROSS.50_200").params == {"fast": 50, "slow": 200}


def test_donchian_rule_hand_computed():
    p = mini_panel({"A": [10, 11, 12, 11, 10, 9, 12, 13, 12.5, 8]})
    # same path as the state-machine test in test_strategies_common (the index is price / 10)
    np.testing.assert_array_equal(col(rules_trend.donchian(p, 3)), [NAN, NAN, NAN, 0.0, -1.0, -1.0, 1.0, 1.0, 1.0, -1.0])
    # carry alone can break a channel: flat price, the holder's index makes a new high every print
    carry = mini_panel({"A": [10.0] * 8}, carry={"A": [NAN] + [0.001] * 7})
    np.testing.assert_array_equal(col(rules_trend.donchian(carry, 3)), [NAN, NAN, NAN, 1.0, 1.0, 1.0, 1.0, 1.0])


def test_linreg_slope_t_matches_scipy_and_clips():
    panel = lane_panel("FX")
    got = col(rules_trend.linreg_slope_t(panel, 63), "GBP")
    logx = np.log(np.array(explicit_index(panel, "GBP")))
    saturated = 0
    for t in (62, 300, 1200, 1999):
        res = sps.linregress(np.arange(63), logx[t - 62:t + 1])
        tstat = res.slope / res.stderr
        assert got[t] == pytest.approx(max(-1.0, min(1.0, tstat / 3.0)), rel=1e-8, abs=1e-12)
        saturated += abs(tstat) > 3
    assert np.isnan(got[:62]).all() and np.nanmax(np.abs(got)) == 1.0
    # an exactly exponential index is a perfect line in logs: t = +inf -> +1
    line = mini_panel({"A": list(100.0 * 1.01 ** np.arange(80))})
    assert col(rules_trend.linreg_slope_t(line, 63))[-1] == pytest.approx(1.0)


# ==================================================================================================
# CARRY
# ==================================================================================================
def _carry_panel(rates, n=200, vols=None, with_carry=False):
    """Alternating-return prices (so sigma_hat is known) with constant or stepped policy rates."""
    names = [c for c in rates if c != "USD"]
    vols = vols or {c: 0.01 for c in names}
    prices = {c: prices_from_returns(alternating(n, vols[c])) for c in names}
    aux = {"rates": {c: (list(v) if isinstance(v, (list, tuple)) else [v] * n) for c, v in rates.items()}}
    idx = _weekday_calendar("2020-01-06", "2021-12-31")[:n]
    carry = None
    if with_carry:
        days = C.calendar_days_between_prints(idx).to_numpy()
        carry = {c: (np.array(aux["rates"][c]) - np.array(aux["rates"]["USD"])) * days / 360.0 for c in names}
    return mini_panel(prices, carry=carry, aux=aux, index=idx)


def test_carry_ts_hand_computed():
    p = _carry_panel({"EUR": 0.07, "JPY": 0.0, "TRY": 0.45, "USD": 0.03}, vols={"EUR": 0.01, "JPY": 0.02, "TRY": 0.01})
    s = rules_carry.carry_ts(p, span=1)
    sigma = H60 * math.sqrt(252)                                    # 0.1600847233313279 for the +-1 % series
    # EUR: (0.07-0.03)/0.16008 = 0.24987 ; JPY: (0-0.03)/0.32017 = -0.09370 ; TRY: 0.42/0.16008 = 2.62 -> 1
    assert s["EUR"].iloc[-1] == pytest.approx(0.04 / sigma, rel=1e-9) == pytest.approx(0.249868, abs=1e-6)
    assert s["JPY"].iloc[-1] == pytest.approx(-0.03 / (2 * sigma), rel=1e-9)
    assert s["TRY"].iloc[-1] == 1.0
    assert s.iloc[:40].isna().all().all() and s.iloc[60:].notna().all().all()


def test_carry_ts_smooths_the_ratio_then_clips():
    step = [0.046] * 150 + [0.062] * 50                             # differential 1.6 % -> 3.2 % at row 150
    p = _carry_panel({"EUR": step, "USD": 0.03})
    sigma = H60 * math.sqrt(252)
    ratio = [NAN] * 40 + [(r - 0.03) / C.vol_estimate(p)["EUR"].iloc[t] for t, r in enumerate(step) if t >= 40]
    raw = col(rules_carry.carry_ts(p, span=1), "EUR")
    assert raw[149] == pytest.approx(0.016 / sigma, rel=1e-9) and raw[150] == pytest.approx(0.032 / sigma, rel=1e-9)
    for span in (20, 60, 120):
        got = col(rules_carry.carry_ts(p, span=span), "EUR")
        assert np.isnan(got[:40 + span - 1]).all()                   # `span` ratio values are needed
        for t in (40 + span - 1, 170, 199):
            assert got[t] == pytest.approx(_brute_ewma(ratio, span, t), rel=1e-9)
        assert raw[149] < got[199] < raw[199]                        # still converging to the new level
    # clip AFTER smoothing: a ratio of 2.6 smoothed with zeros would not be capped early
    big = _carry_panel({"TRY": [0.03] * 120 + [0.45] * 80, "USD": 0.03})
    got = col(rules_carry.carry_ts(big, span=20), "TRY")
    assert got[119] == pytest.approx(0.0, abs=1e-15) and 0 < got[121] < 1 and got[199] == 1.0


def _nine_rates():
    # differential to USD (3 %): EUR -3, GBP +1, JPY -4, CHF -2.5, CAD 0, AUD +2, NZD +3, SEK -1, NOK +1.5 (%)
    return {"EUR": 0.0, "GBP": 0.04, "JPY": -0.01, "CHF": 0.005, "CAD": 0.03, "AUD": 0.05, "NZD": 0.06,
            "SEK": 0.02, "NOK": 0.045, "USD": 0.03}


def test_carry_xs_rules_hand_computed():
    p = _carry_panel(_nine_rates(), n=80)
    t3 = rules_carry.carry_xs_tercile(p, span=1)
    # ascending: JPY, EUR, CHF | SEK, CAD, GBP | NOK, AUD, NZD
    expect = {"EUR": -1, "GBP": 0, "JPY": -1, "CHF": -1, "CAD": 0, "AUD": 1, "NZD": 1, "SEK": 0, "NOK": 1}
    for name, value in expect.items():
        assert (t3[name] == value).all(), name
    lin = rules_carry.carry_xs_linear(p, span=1).iloc[-1]
    # ranks 1..9 -> (rank - 5) / 4
    ranks = {"JPY": 1, "EUR": 2, "CHF": 3, "SEK": 4, "CAD": 5, "GBP": 6, "NOK": 7, "AUD": 8, "NZD": 9}
    for name, r in ranks.items():
        assert lin[name] == pytest.approx((r - 5) / 4, abs=1e-15), name
    # smoothing a constant changes nothing, but needs `span` observations
    t20 = rules_carry.carry_xs_tercile(p, span=20)
    assert t20.iloc[:19].isna().all().all()
    pd.testing.assert_frame_equal(t20.iloc[19:], t3.iloc[19:])


def test_carry_rules_rank_the_differential_not_the_monday_accrual():
    """With rates the signal is the same on Mondays; from the accrual panel alone the 5-print fallback
    recovers the same ranking (the raw Monday accrual is 3x and would not)."""
    with_rates = _carry_panel(_nine_rates(), n=80, with_carry=True)
    without = mini_panel(with_rates.prices, carry=with_rates.carry, index=with_rates.prices.index)
    assert C.carry_source(with_rates) == "rates" and C.carry_source(without) == "carry"
    a = rules_carry.carry_xs_tercile(with_rates, span=1)
    b = rules_carry.carry_xs_tercile(without, span=1)
    pd.testing.assert_frame_equal(a.iloc[5:], b.iloc[5:])
    np.testing.assert_allclose(C.annualised_carry(without).iloc[5:].to_numpy(),
                               C.annualised_carry(with_rates).iloc[5:].to_numpy(), rtol=1e-12, atol=1e-15)
    lin_a = rules_carry.carry_xs_linear(with_rates, span=1)
    assert (lin_a.iloc[5:].nunique() == 1).all()                    # no weekday pattern at all


def test_carry_change_hand_computed_and_quiet_markets_give_no_position():
    rates = {c: [v] * 120 for c, v in _nine_rates().items()}
    rates["AUD"] = [0.05] * 60 + [0.0575] * 60                      # +75 bp at row 60
    rates["SEK"] = [0.02] * 70 + [0.015] * 50                       # -50 bp at row 70
    p = _carry_panel(rates, n=120)
    s = rules_carry.carry_change_xs(p, lookback=10)
    assert s.iloc[:10].isna().all().all()
    # rows 10..59: nobody moved in the last 10 prints -> nine equal scores -> ZERO signal (not a portfolio)
    assert (s.iloc[10:60] == 0.0).all().all()
    # rows 60..69: AUD +0.75, the other eight tie at 0 -> AUD is long 1; the eight share 3 short slots and 2
    # long slots: (2 - 3) / 8 = -1/8 each
    assert (s["AUD"].iloc[60:70] == 1.0).all()
    np.testing.assert_allclose(s.drop(columns="AUD").iloc[60:70].to_numpy(), -1 / 8, rtol=1e-15)
    # rows 70..79: AUD's move is now more than 10 prints old (its change is 0 again); SEK -0.50 takes one
    # short slot; the other eight tie at 0 and share 2 short slots and 3 long slots: (3 - 2) / 8 = +1/8 each
    assert (s["SEK"].iloc[70:80] == -1.0).all()
    np.testing.assert_allclose(s.drop(columns="SEK").iloc[70:80].to_numpy(), 1 / 8, rtol=1e-15)
    assert (s.iloc[80:] == 0.0).all().all()
    np.testing.assert_allclose(s.sum(axis=1).iloc[10:], 0.0, atol=1e-12)


def test_carry_change_is_not_ranked_by_floating_point_dust():
    """From the accrual panel alone the annualised carry is a ratio of sums: for a currency whose rate
    differential never moved, carry_t - carry_{t-L} is +-1e-17 instead of 0. Unrounded, that dust would
    rank such currencies against each other; the rule must see them as tied."""
    names = ["EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK"]
    fx = lane_panel("FX").subset(names)
    from_accrual = mini_panel(fx.prices, carry=fx.carry, index=fx.prices.index, meta=dict(fx.meta))
    assert C.carry_source(from_accrual) == "carry" and C.carry_source(fx) == "rates"
    lb = 63
    rates = fx.aux["rates"]
    span = lb + 6                                                   # the lookback plus a 5-print span each side
    changed = ((rates.diff() != 0) & rates.diff().notna()).astype(int).rolling(span, min_periods=span).sum()
    # "unmoved": neither the currency's rate nor the dollar's changed anywhere in the window -> true change 0
    unmoved = ((changed[names] == 0).to_numpy() & (changed["USD"] == 0).to_numpy()[:, None])
    rows = np.flatnonzero(unmoved.sum(axis=1) >= 2)
    assert len(rows) > 100
    ca = C.annualised_carry(from_accrual)
    raw = (ca - ca.shift(lb)).to_numpy()
    dust = raw[unmoved]
    assert (np.abs(dust) < 1e-12).all() and (dust != 0).mean() > 0.2          # the dust exists ...
    unrounded_ties_broken = sum(np.unique(raw[t][unmoved[t]]).size > 1 for t in rows)
    assert unrounded_ties_broken > 50                                         # ... and would break real ties
    for panel in (from_accrual, fx):
        sig = rules_carry.carry_change_xs(panel, lb).to_numpy()
        for t in rows:
            assert np.unique(sig[t][unmoved[t]]).size == 1, t                 # tied currencies, one signal
        assert np.nanmax(np.abs(np.nansum(sig, axis=1))) < 1e-12
    assert rules_carry.CHANGE_DECIMALS == 9


# ==================================================================================================
# VALUE
# ==================================================================================================
def test_value_xs_nominal_hand_computed():
    p = mini_panel({"A": [1, 2, 4, 4], "B": [4, 2, 1, 1], "C": [3, 3, 3, 3]})
    s = rules_value.value_xs_deviation(p, lookback=3)
    # row 2: ln A = 0, ln2, 2ln2 -> deviation +ln2 (dear) ; B: -ln2 (cheap) ; C: 0  -> long B, short A
    np.testing.assert_array_equal(s.iloc[2].to_numpy(), [-1.0, 1.0, 0.0])
    # row 3: A window ln 2, ln 4, ln 4 -> ln4 - (5/3) ln2 = +ln2/3 ; B: -ln2/3 ; C: 0 -> unchanged
    np.testing.assert_array_equal(s.iloc[3].to_numpy(), [-1.0, 1.0, 0.0])
    assert s.iloc[:2].isna().all().all()
    # it reads the SPOT price, not the excess index: a large carry on A must not change anything
    q = mini_panel({"A": [1, 2, 4, 4], "B": [4, 2, 1, 1], "C": [3, 3, 3, 3]},
                   carry={"A": [NAN, 0.5, 0.5, 0.5], "B": [NAN, 0.0, 0.0, 0.0], "C": [NAN, 0.0, 0.0, 0.0]})
    pd.testing.assert_frame_equal(rules_value.value_xs_deviation(q, lookback=3), s)


def test_value_real_rate_and_real_rules_hand_computed():
    prices = {"A": [2.0] * 4, "B": [2.0] * 4, "C": [2.0] * 4}
    cpi = {"A": [100, 110, 121, 133.1], "B": [100, 100, 100, 100], "C": [100, 95, 90.25, 85.7375],
           "USD": [100, 100, 100, 100]}
    p = mini_panel(prices, aux={"cpi": cpi})
    q = rules_value.log_real_rate(p)
    # q = ln 2 + ln(CPI_ccy / CPI_USD): A inflates 10 % a print, C deflates 5 %
    np.testing.assert_allclose(q["A"].to_numpy(), math.log(2) + np.arange(4) * math.log(1.1), rtol=1e-13)
    np.testing.assert_allclose(q["C"].to_numpy(), math.log(2) + np.arange(4) * math.log(0.95), rtol=1e-13)
    np.testing.assert_allclose(q["B"].to_numpy(), math.log(2), rtol=1e-15)
    # nominal value sees nothing (all prices flat -> no dispersion -> zero); real value shorts the inflater
    assert (rules_value.value_xs_deviation(p, lookback=3, real=False).iloc[2:] == 0.0).all().all()
    real = rules_value.value_xs_deviation(p, lookback=3, real=True)
    np.testing.assert_array_equal(real.iloc[2].to_numpy(), [-1.0, 0.0, 1.0])
    ret = rules_value.value_xs_long_return(p, lookback=2, real=True)
    # -(q_t - q_{t-2}): A = -2 ln 1.1 (dear), B = 0, C = -2 ln 0.95 > 0 (cheap)
    np.testing.assert_array_equal(ret.iloc[3].to_numpy(), [-1.0, 0.0, 1.0])
    assert ret.iloc[:2].isna().all().all()
    # a US inflation of the same size cancels A's
    cpi["USD"] = [100, 110, 121, 133.1]
    q2 = rules_value.log_real_rate(mini_panel(prices, aux={"cpi": cpi}))
    np.testing.assert_allclose(q2["A"].to_numpy(), math.log(2), rtol=1e-13)


def test_value_ts_z_hand_computed():
    p = mini_panel({"A": list(np.exp([1.0, 2.0, 3.0, 4.0, 10.0]))})
    # ln P = 1, 2, 3, 4, 10 ; z_3 = ., ., 1, 1, 1.1445861782233109 -> signal = -z/2
    np.testing.assert_allclose(col(rules_value.value_ts_z(p, lookback=3)), [NAN, NAN, -0.5, -0.5, -1.1445861782233109 / 2],
                               rtol=1e-9)
    spike = mini_panel({"A": [1.0] * 9 + [0.2]})                    # a collapse of the price -> z < -2 -> +1
    assert col(rules_value.value_ts_z(spike, lookback=10))[-1] == 1.0


def test_value_long_return_on_prices_hand_computed():
    p = mini_panel({"A": [1, 1, 3, 9], "B": [8, 8, 8, 2], "C": [5, 5, 5, 5]},
                   carry={"A": [NAN, 0.9, 0.9, 0.9], "B": [NAN, 0.0, 0.0, 0.0], "C": [NAN, 0.0, 0.0, 0.0]})
    s = rules_value.value_xs_long_return(p, lookback=2)
    # row 2: -(ln 3 - ln 1) (A), 0 (B), 0 (C): A short; B and C tie for one long slot -> +1/2 each
    np.testing.assert_allclose(s.iloc[2].to_numpy(), [-1.0, 0.5, 0.5])
    # row 3: A = -(ln 9 - ln 1) short ; B = -(ln 2 - ln 8) = +ln 4 long ; C = 0
    np.testing.assert_array_equal(s.iloc[3].to_numpy(), [-1.0, 1.0, 0.0])
    assert R.get("VALUE.XS_RET.L1260").params == {"lookback": 1260, "real": False}


def test_real_value_rules_refuse_a_panel_without_cpi():
    p = mini_panel({"A": [1, 2, 3], "B": [1, 2, 3], "C": [3, 2, 1]})
    with pytest.raises(C.NotApplicable):
        rules_value.value_xs_deviation(p, lookback=2, real=True)
    with pytest.raises(C.NotApplicable):
        rules_value.value_xs_long_return(mini_panel({"A": [1, 2, 3]}, aux={"cpi": {"A": [1, 1, 1]}}), 2, real=True)
    partial = mini_panel({"A": [1, 2, 3], "B": [1, 2, 3]}, aux={"cpi": {"A": [1, 1, 1], "USD": [1, 1, 1]}})
    assert rules_value.log_real_rate(partial)["B"].isna().all()     # no CPI column -> no view, not a zero


# ==================================================================================================
# XSMOM
# ==================================================================================================
def _burst_panel():
    """Sixty prints of alternating returns pin each instrument's volatility (A +-1 %, B +-2 %, C +-0.5 %),
    then five prints of steady gains (A +1.0 %, B +1.5 %, C +0.6 % a print). D lists 30 prints before the
    end: it has an index but not yet a volatility estimate. Returns the panel and the return lists."""
    rets = {"A": alternating(61, 0.01)[1:] + [0.010] * 5, "B": alternating(61, 0.02)[1:] + [0.015] * 5,
            "C": alternating(61, 0.005)[1:] + [0.006] * 5}
    prices = {k: prices_from_returns([0.0] + v) for k, v in rets.items()}            # 66 prints
    prices["D"] = [NAN] * 36 + prices_from_returns([0.0] + [0.02] * 29, p0=50.0)
    return mini_panel(prices), rets


def _scaled(rets, lookback, skip=0):
    """Independent oracle: window return / (stdev of the last 60 returns * sqrt(window length))."""
    window = rets[len(rets) - lookback:len(rets) - skip]
    return (math.prod(1.0 + r for r in window) - 1.0) / (statistics.stdev(rets[-60:]) * math.sqrt(lookback - skip))


def test_xsmom_ranks_vol_scaled_returns_hand_computed():
    p, rets = _burst_panel()
    score = {k: _scaled(v, 5) for k, v in rets.items()}
    # by hand: 5-print returns A 5.101 %, B 7.728 %, C 3.036 % ; per-print sigma A 1.0062 %, B 1.9776 %,
    # C 0.5117 % ; score = ret / (sigma * sqrt(5)) = A 2.2672, B 1.7477, C 2.6538
    assert score["A"] == pytest.approx(2.267192407037116, rel=1e-12)
    assert score["B"] == pytest.approx(1.7476871116897146, rel=1e-12)
    assert score["C"] == pytest.approx(2.6537993833592433, rel=1e-12)
    got = C.vol_scaled_return(p, 5).iloc[-1]
    for k in "ABC":
        assert got[k] == pytest.approx(score[k], rel=1e-9), k
    assert np.isnan(got["D"])                                        # 29 returns: no volatility estimate yet
    # RAW returns would say B > A > C; in units of its own volatility the order is C > A > B
    t3 = rules_xs.xsmom_tercile(p, lookback=5).iloc[-1]
    np.testing.assert_array_equal(t3.to_numpy(), [0.0, -1.0, 1.0, NAN])
    abc = p.subset(["A", "B", "C"])
    raw_order = C.xs_tercile(C.lookback_return(C.excess_index(abc), 5), abc.eligible()).iloc[-1]
    np.testing.assert_array_equal(raw_order.to_numpy(), [0.0, 1.0, -1.0])            # the volatility sort it replaces
    lin = rules_xs.xsmom_linear(p, lookback=5).iloc[-1]
    np.testing.assert_array_equal(lin.to_numpy(), [0.0, -1.0, 1.0, NAN])              # ranks 2, 1, 3 -> (r - 2) / 1
    assert rules_xs.xsmom_tercile(p, lookback=5).iloc[:40].isna().all().all()        # no sigma, no score


def test_xsmom_skip_month_window_and_scaling():
    p, rets = _burst_panel()
    # 10 skipping 5 at the last row: X_{60} / X_{55} - 1 (five alternating prints), scaled by sqrt(10 - 5)
    score = {k: _scaled(v, 10, skip=5) for k, v in rets.items()}
    assert score["A"] == pytest.approx(-0.4532598120651416, rel=1e-12)
    assert score["B"] == pytest.approx(-0.47000223935556357, rel=1e-12)
    assert score["C"] == pytest.approx(-0.44137238333051687, rel=1e-12)
    got = C.vol_scaled_return(p, 10, skip=5).iloc[-1]
    for k in "ABC":
        assert got[k] == pytest.approx(score[k], rel=1e-9), k
    np.testing.assert_array_equal(rules_xs.xsmom_tercile(p, lookback=10, skip=5).iloc[-1].to_numpy(), [0.0, -1.0, 1.0, NAN])
    assert R.get("XSMOM.TERCILE.L252_SKIP21").params == {"lookback": 252, "skip": 21}   # window = 231 prints
    panel = lane_panel("MACRO")
    x = C.excess_index(panel)
    expect = (x.shift(21) / x.shift(252) - 1.0) / (C.daily_vol(panel) * math.sqrt(231))
    pd.testing.assert_frame_equal(C.vol_scaled_return(panel, 252, skip=21), expect)


def test_xsmom_ranks_the_excess_return_not_the_spot_return():
    # identical +-1 % noise (so identical volatility); over the last 20 prints A drifts +0.3 % a print and
    # C drifts -0.3 %; B does nothing.
    noise = alternating(86, 0.01)[1:]
    rets = {"A": noise[:65] + [r + 0.003 for r in noise[65:]], "B": list(noise),
            "C": noise[:65] + [r - 0.003 for r in noise[65:]]}
    prices = {k: prices_from_returns([0.0] + v) for k, v in rets.items()}
    spot = mini_panel(prices)
    np.testing.assert_array_equal(rules_xs.xsmom_tercile(spot, lookback=20).iloc[-1].to_numpy(), [1.0, 0.0, -1.0])
    # B earns 0.8 % carry a print (a constant: it adds nothing to B's volatility): its HOLDER made the most
    n = len(noise) + 1
    carried = mini_panel(prices, carry={"A": [NAN] + [0.0] * (n - 1), "B": [NAN] + [0.008] * (n - 1),
                                        "C": [NAN] + [0.0] * (n - 1)})
    np.testing.assert_array_equal(rules_xs.xsmom_tercile(carried, lookback=20).iloc[-1].to_numpy(), [0.0, 1.0, -1.0])


def test_residual_momentum_matches_an_explicit_regression():
    panel = lane_panel("MACRO")
    lb = 252
    got = rules_xs.residual_momentum(panel, lookback=lb)
    e = C.excess_returns(panel)
    basket = e.mean(axis=1)                                         # every instrument is eligible on MACRO
    t = 1400
    scores = {}
    for name in panel.prices.columns:
        y = e[name].iloc[t - lb + 1:t + 1].to_numpy()
        b = basket.iloc[t - lb + 1:t + 1].to_numpy()
        beta, alpha = np.polyfit(b, y, 1)                           # OLS with intercept
        assert float(np.sum(y - beta * b)) == pytest.approx(lb * alpha, rel=1e-6, abs=1e-10)
        scores[name] = lb * alpha
    order = sorted(scores, key=scores.get)
    k = len(order) // 3
    for name in order[:k]:
        assert got[name].iloc[t] == -1.0
    for name in order[-k:]:
        assert got[name].iloc[t] == 1.0
    for name in order[k:-k]:
        assert got[name].iloc[t] == 0.0
    assert got.iloc[:lb].isna().all().all() and got.iloc[lb].notna().all()


def test_residual_momentum_removes_the_basket():
    """Two instruments that are 2x and 0.5x the basket plus one with a genuine alpha: only alpha ranks."""
    rng = np.random.default_rng(4)
    n = 400
    market = rng.normal(0.0, 0.01, n)
    noise = rng.normal(0.0, 0.002, (n, 4))
    rets = {"HI": 2.0 * market + noise[:, 0], "LO": 0.5 * market + noise[:, 1],
            "UP": market + 0.002 + noise[:, 2], "DN": market - 0.002 + noise[:, 3]}
    p = mini_panel({k: prices_from_returns([0.0] + list(v[1:])) for k, v in rets.items()})
    last = rules_xs.residual_momentum(p, lookback=252).iloc[-1]
    assert last["UP"] == 1.0 and last["DN"] == -1.0 and last["HI"] == 0.0 and last["LO"] == 0.0


def test_high_proximity_hand_computed():
    p = mini_panel({"A": [1, 2, 3, 4], "B": [4, 3, 2, 1], "C": [2, 4, 2, 3], "D": [1, 1, 5, 4.9]})
    s = rules_xs.high_proximity(p, lookback=3)
    # row 2: X/max3 = A 3/3 = 1, B 2/4 = .5, C 2/4 = .5, D 5/5 = 1 (index = price / first price; ratios equal)
    #        n = 4, k = 1: A and D tie for the long slot (+1/2 each), B and C tie for the short slot (-1/2 each)
    np.testing.assert_allclose(s.iloc[2].to_numpy(), [0.5, -0.5, -0.5, 0.5])
    # row 3: A 4/4 = 1, B 1/3, C 3/4, D 4.9/5 = .98 -> long A, short B
    np.testing.assert_array_equal(s.iloc[3].to_numpy(), [1.0, -1.0, 0.0, 0.0])
    assert s.iloc[:2].isna().all().all()


# ==================================================================================================
# REVERSAL
# ==================================================================================================
def test_reversal_xs_ranks_vol_scaled_returns_hand_computed():
    p, rets = _burst_panel()
    # L = 5: scaled returns C 2.654 > A 2.267 > B 1.748 -> the biggest riser IN ITS OWN UNITS (C) is sold,
    # the smallest (B) is bought — although B has the largest raw return
    np.testing.assert_array_equal(rules_reversal.reversal_xs(p, lookback=5).iloc[-1].to_numpy(), [0.0, 1.0, -1.0, NAN])
    # L = 1: last print / sigma = A 0.01/0.010062 = 0.9938, B 0.015/0.019776 = 0.7585, C 0.006/0.0051166 = 1.1727
    score1 = {k: _scaled(v, 1) for k, v in rets.items()}
    assert score1["A"] == pytest.approx(0.9938426506674557, rel=1e-12)
    assert score1["B"] == pytest.approx(0.7584908238550643, rel=1e-12)
    assert score1["C"] == pytest.approx(1.1726585760395036, rel=1e-12)
    np.testing.assert_array_equal(rules_reversal.reversal_xs(p, lookback=1).iloc[-1].to_numpy(), [0.0, 1.0, -1.0, NAN])
    for lb in (1, 5, 10):
        pd.testing.assert_frame_equal(rules_reversal.reversal_xs(p, lb), -rules_xs.xsmom_tercile(p, lb))
    panel = lane_panel("CRYPTO-PERP")
    pd.testing.assert_frame_equal(rules_reversal.reversal_xs(panel, 5), -rules_xs.xsmom_tercile(panel, 5))


def test_reversal_ts_z_hand_computed():
    p = mini_panel({"A": prices_from_returns(alternating(200, 0.01))})
    z = col(rules_reversal.reversal_ts_z(p, 5))
    # rows 96..100: evens 96, 98, 100 (-), odds 97, 99 (+): ret = 1.01^2 * 0.99^3 - 1 = -0.0102...
    assert z[100] == pytest.approx(-(1.01 ** 2 * 0.99 ** 3 - 1) / (H60 * math.sqrt(5)) / 2, rel=1e-9)
    assert z[100] > 0 > z[101]


def test_rsi_contrarian_thresholds():
    up, down = list(np.arange(1.0, 31.0)), list(np.arange(30.0, 0.0, -1.0))
    mixed = [10, 11, 10.5, 11.5, 11.0, 12.0] + [12.0 + 0.1 * (-1) ** i for i in range(24)]
    p = mini_panel({"U": up, "D": down, "M": mixed})
    s = rules_reversal.rsi_contrarian(p, n=2, low=10.0, high=90.0)
    assert (s["U"].iloc[2:] == -1.0).all() and (s["D"].iloc[2:] == 1.0).all()   # RSI 100 / 0
    # M: RSI(2) = 66.7, 85.7, 54.5, 81.5 on rows 2..5 (hand-computed in test_strategies_common) -> inside 10/90
    np.testing.assert_array_equal(s["M"].iloc[:6].to_numpy(), [NAN, NAN, 0.0, 0.0, 0.0, 0.0])
    s14 = rules_reversal.rsi_contrarian(p, n=14, low=30.0, high=70.0)
    assert s14.iloc[:14].isna().all().all() and (s14["U"].iloc[14:] == -1.0).all() and (s14["D"].iloc[14:] == 1.0).all()
    assert R.get("REVERSAL.RSI.2_10_90").params == {"n": 2, "low": 10.0, "high": 90.0}
    assert R.get("REVERSAL.RSI.14_30_70").params == {"n": 14, "low": 30.0, "high": 70.0}


def test_bollinger_hand_computed():
    p = mini_panel({"A": [10, 10, 10, 10, 10, 16], "B": [10, 10, 10, 10, 10, 4], "C": [10, 11, 10, 11, 10, 11],
                    "D": [10, 10, 10, 10, 10, 10]})
    s = rules_reversal.bollinger_reversion(p, window=6, width=2.0).iloc[-1]
    # A (index = price/10; work in price units): mean 11, population var (5*1 + 25)/6 = 5, upper band
    #   11 + 2*sqrt(5) = 15.47 < 16 -> short. B mirrored: lower band 9 - 2*sqrt(5) = 4.53 > 4 -> long.
    # C: mean 10.5, std 0.5, band [9.5, 11.5] -> inside. D: flat, band collapses onto the price -> inside.
    assert s["A"] == -1.0 and s["B"] == 1.0 and s["C"] == 0.0 and s["D"] == 0.0
    assert rules_reversal.bollinger_reversion(p, window=6).iloc[:5].isna().all().all()
    # Bollinger's POPULATION std is used, and it matters at the edge. Window 9, 11, 9, 11, 10, 15:
    #   mean 65/6 = 10.833 ; sum of squared deviations = 4 + 25 - 25/6 = 24.833
    #   population std = sqrt(24.833/6) = 2.0344 -> upper band 14.902 < 15  -> short
    #   sample std     = sqrt(24.833/5) = 2.2286 -> upper band 15.291 > 15  -> would be flat
    window = [9, 11, 9, 11, 10, 15]
    mean = statistics.mean(window)
    assert mean + 2 * statistics.pstdev(window) < 15 < mean + 2 * statistics.stdev(window)
    assert mean + 2 * statistics.pstdev(window) == pytest.approx(14.902, abs=1e-3)
    q = mini_panel({"A": window})
    assert rules_reversal.bollinger_reversion(q, window=6).iloc[-1]["A"] == -1.0
    assert R.get("REVERSAL.BOLLINGER.20_2").params == {"window": 20, "width": 2.0}


# ==================================================================================================
# VOL
# ==================================================================================================
def test_vol_managed_basket_hand_computed():
    calm = alternating(274, 0.01)[1:]                                # 273 returns, +, -, +, ...
    for tail, label in (([0.01, -0.01] * 10 + [0.01], "same"), ([0.005, -0.005] * 10 + [0.005], "calmer"),
                        ([0.04, -0.04] * 10 + [0.04], "stormy")):
        rets = calm[:252] + tail                                     # 273 returns: the last 21 are `tail`
        p = mini_panel({"A": prices_from_returns([0.0] + rets)})
        got = col(rules_misc.vol_managed_basket(p))[-1]
        s252, s21 = statistics.stdev(rets[-252:]), statistics.stdev(rets[-21:])
        assert got == pytest.approx(min(1.0, 0.5 * s252 / s21), rel=1e-8), label
    # same vol: 0.5 * sqrt(252/251) / sqrt(22/21) = 0.4895 ; stormy (4x): ~0.19 ; calmer (half): ~0.94
    p = mini_panel({"A": prices_from_returns([0.0] + calm[:252] + [0.01, -0.01] * 10 + [0.01])})
    same = 0.5 * math.sqrt(252 / 251) / math.sqrt(22 / 21)
    assert col(rules_misc.vol_managed_basket(p))[-1] == pytest.approx(same, rel=1e-8)
    quiet = mini_panel({"A": prices_from_returns([0.0] + calm[:252] + [0.001, -0.001] * 10 + [0.001])})
    assert col(rules_misc.vol_managed_basket(quiet))[-1] == 1.0     # ratio ~ 9.6 -> capped: never above 1
    out = rules_misc.vol_managed_basket(lane_panel("MACRO"))
    assert out.iloc[:252].isna().all().all() and out.iloc[252:].notna().all().all()
    assert out.min().min() >= 0.0 and out.max().max() <= 1.0                 # long-only, bounded


def test_low_vol_and_vol_breakout_hand_computed():
    n = 80
    p = mini_panel({"A": prices_from_returns(alternating(n, 0.01)), "B": prices_from_returns(alternating(n, 0.02)),
                    "C": prices_from_returns(alternating(n, 0.03))})
    np.testing.assert_array_equal(rules_misc.low_vol_xs(p, lookback=60).iloc[-1].to_numpy(), [1.0, 0.0, -1.0])
    quiet = alternating(61, 0.001)[1:]                               # 60 returns of +-0.1 %
    for burst, expect in (([0.03, -0.01, 0.03, -0.01, 0.03], 1.0), ([-0.03, 0.01, -0.03, 0.01, -0.03], -1.0),
                          ([0.001, -0.001, 0.001, -0.001, 0.001], 0.0)):
        rets = quiet + burst
        q = mini_panel({"A": prices_from_returns([0.0] + rets)})
        ratio = statistics.stdev(rets[-5:]) / statistics.stdev(rets[-60:])
        assert (ratio > 1.5) == (expect != 0.0)
        assert col(rules_misc.vol_breakout(q))[-1] == expect
    assert R.get("VOL.BREAKOUT.5_60").params == {"short_window": 5, "long_window": 60, "threshold": 1.5}


# ==================================================================================================
# SEASON
# ==================================================================================================
def _season_panel(index, ppy, classes=None):
    names = list(classes) if classes else ["X", "Y"]
    meta = {"asset_class_of": classes} if classes else {}
    return mini_panel({c: [1.0 + 0.01 * i for i in range(len(index))] for c in names}, index=index, ppy=ppy, meta=meta)


def test_turn_of_month_rules_hand_checked_calendar():
    idx = _weekday_calendar("2024-01-22", "2024-04-05", holidays=("2024-03-29", "2024-04-01"))
    on = {"2024-01-29", "2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02", "2024-02-27", "2024-02-28",
          "2024-02-29", "2024-03-01", "2024-03-04", "2024-03-27", "2024-03-28", "2024-04-02", "2024-04-03"}
    expect = np.array([1.0 if d.strftime("%Y-%m-%d") in on else 0.0 for d in idx])
    macro = _season_panel(idx, 252, {"SPY": "equity", "XLE": "Equity_Sector", "TLT": "bond", "GLD": "commodity"})
    s = R.get("SEASON.TOM.EQUITY").signal(macro)
    np.testing.assert_array_equal(s["SPY"].to_numpy(), expect)
    np.testing.assert_array_equal(s["XLE"].to_numpy(), expect)      # label CONTAINS "equity", any case
    assert s["TLT"].isna().all() and s["GLD"].isna().all()          # no view on non-equities
    fx = _season_panel(idx, 252)
    np.testing.assert_array_equal(R.get("SEASON.TOM.LONG_USD").signal(fx)["X"].to_numpy(), -expect)
    np.testing.assert_array_equal(R.get("SEASON.TOM.SHORT_USD").signal(fx)["Y"].to_numpy(), expect)


def test_turn_of_month_on_a_daily_calendar():
    idx = pd.date_range("2024-01-25", "2024-03-05", freq="D", tz="UTC")
    s = R.get("SEASON.TOM.LONG").signal(_season_panel(idx, 365))
    on = ["2024-01-29", "2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02",
          "2024-02-27", "2024-02-28", "2024-02-29", "2024-03-01", "2024-03-02"]
    assert [d.strftime("%Y-%m-%d") for d in idx[(s["X"] == 1.0).to_numpy()]] == on
    assert ((s == 0.0) | (s == 1.0)).all().all()
    # the same dates on a weekday-calendar panel would be judged by weekdays: the panel's convention decides
    assert C.print_calendar(_season_panel(idx, 365)) == "daily"


def test_sell_in_may_hand_checked():
    idx = _weekday_calendar("2023-10-25", "2024-05-06")
    p = _season_panel(idx, 252, {"SPY": "equity", "TLT": "bond"})
    s = R.get("SEASON.SELL_IN_MAY.EQUITY").signal(p)
    month = idx.month
    np.testing.assert_array_equal(s["SPY"].to_numpy(), np.where((month >= 11) | (month <= 4), 1.0, 0.0))
    assert s["SPY"].loc["2023-10-31"].item() == 0.0 and s["SPY"].loc["2023-11-01"].item() == 1.0
    assert s["SPY"].loc["2024-04-30"].item() == 1.0 and s["SPY"].loc["2024-05-01"].item() == 0.0
    assert s["TLT"].isna().all()


def test_equity_rules_need_an_equity_label():
    idx = _weekday_calendar("2024-01-22", "2024-02-09")
    none = _season_panel(idx, 252)
    bonds = _season_panel(idx, 252, {"TLT": "bond", "IEF": "bond"})
    for panel in (none, bonds):
        for rid in ("SEASON.TOM.EQUITY", "SEASON.SELL_IN_MAY.EQUITY"):
            rule = R.get(rid)
            assert R.missing_requirements(rule, panel) == ("asset_class:equity",)
            with pytest.raises(C.NotApplicable):
                rule.signal(panel)


# ==================================================================================================
# SKEW
# ==================================================================================================
def test_skew_and_max_rules_match_independent_statistics():
    panel = lane_panel("FX-FRED")
    e = C.excess_returns(panel)
    t = 1500
    sk = {c: float(sps.skew(e[c].iloc[t - 125:t + 1].to_numpy(), bias=False)) for c in e.columns}
    # MAX in units of the instrument's own per-print volatility (the 60-print std; the floor is not binding here)
    sigma = {c: statistics.stdev(e[c].iloc[t - 59:t + 1].tolist()) for c in e.columns}
    for c in e.columns:
        assert C.daily_vol(panel)[c].iloc[t] == pytest.approx(sigma[c], rel=1e-9)
    mx = {c: float(e[c].iloc[t - 20:t + 1].max()) / sigma[c] for c in e.columns}
    for scores, got in ((sk, rules_misc.skew_xs(panel, 126)), (mx, rules_misc.max_return_xs(panel, 21))):
        order = sorted(scores, key=scores.get)                      # ascending
        k = len(order) // 3
        row = got.iloc[t]
        assert all(row[c] == 1.0 for c in order[:k])                # LOW skew / LOW scaled max -> long
        assert all(row[c] == -1.0 for c in order[-k:])              # HIGH skew / HIGH scaled max -> short
        assert all(row[c] == 0.0 for c in order[k:-k])


def test_skew_hand_made():
    base = alternating(127, 0.01)[1:]                               # 126 returns
    lottery = list(base)
    lottery[60] = 0.20                                              # one huge up day -> positive skew
    crash = list(base)
    crash[61] = -0.20                                               # one huge down day -> negative skew
    p = mini_panel({"L": prices_from_returns([0.0] + lottery), "N": prices_from_returns([0.0] + base),
                    "C": prices_from_returns([0.0] + crash)})
    np.testing.assert_array_equal(rules_misc.skew_xs(p, 126).iloc[-1].to_numpy(), [-1.0, 0.0, 1.0])


def test_max_rule_ranks_the_vol_scaled_maximum_hand_computed():
    def with_spike(a, spike):
        r = alternating(81, a)[1:]                                  # 80 returns
        if spike is not None:
            r[-10] = spike                                          # inside the last 21 prints
        return r

    rets = {"A": with_spike(0.03, None), "B": with_spike(0.01, 0.026), "C": with_spike(0.02, 0.024)}
    p = mini_panel({k: prices_from_returns([0.0] + v) for k, v in rets.items()})
    # raw best day: A 3.0 % > B 2.6 % > C 2.4 %. In units of its own volatility (std of the last 60 returns):
    #   A 0.030 / 0.030253 = 0.9916 ;  B 0.026 / 0.010554 = 2.4635 ;  C 0.024 / 0.020242 = 1.1856
    scaled = {k: max(v[-21:]) / statistics.stdev(v[-60:]) for k, v in rets.items()}
    assert scaled["A"] == pytest.approx(0.9916316520429012, rel=1e-12)
    assert scaled["B"] == pytest.approx(2.4635386917796005, rel=1e-12)
    assert scaled["C"] == pytest.approx(1.1856251938250721, rel=1e-12)
    got = (C.excess_returns(p).rolling(21, min_periods=21).max() / C.daily_vol(p)).iloc[-1]
    for k in "ABC":
        assert got[k] == pytest.approx(scaled[k], rel=1e-9), k
    # B's best day was the most extreme FOR B: it is the one sold; the calm-for-its-size A is bought
    np.testing.assert_array_equal(rules_misc.max_return_xs(p, 21).iloc[-1].to_numpy(), [1.0, -1.0, 0.0])
    raw = C.xs_tercile(-C.excess_returns(p).rolling(21, min_periods=21).max(), p.eligible()).iloc[-1]
    np.testing.assert_array_equal(raw.to_numpy(), [-1.0, 0.0, 1.0])                  # the volatility sort it replaces
    assert rules_misc.max_return_xs(p, 21).iloc[:40].isna().all().all()
    assert R.get("SKEW.XS_MAX.L21").params == {"lookback": 21}


# ==================================================================================================
# XASSET, FLOW
# ==================================================================================================
def test_oil_currencies_hand_computed():
    oil = [50, 55, 60, 54, 40, 40]
    p = mini_panel({"EUR": [1.0] * 6, "CAD": [0.7] * 6, "NOK": [0.1] * 6, "MXN": [0.05] * 6}, aux={"oil": {"WTI": oil}})
    s = rules_misc.oil_currencies(p, lookback=2)
    # oil_t / oil_{t-2} - 1: ., ., +20 %, -1.8 %, -33 %, -26 %
    for name in ("CAD", "NOK", "MXN"):
        np.testing.assert_array_equal(s[name].to_numpy(), [NAN, NAN, 1.0, -1.0, -1.0, -1.0])
    assert s["EUR"].isna().all()
    g10 = p.subset(["EUR", "CAD", "NOK"])                            # MXN is not in G10: two instruments remain
    assert rules_misc.oil_currencies(g10, lookback=2)[["CAD", "NOK"]].iloc[2].tolist() == [1.0, 1.0]
    flat = mini_panel({"CAD": [1.0] * 4}, aux={"oil": {"WTI": [50, 50, 50, 50]}})
    np.testing.assert_array_equal(rules_misc.oil_currencies(flat, lookback=2)["CAD"].to_numpy(), [NAN, NAN, 0.0, 0.0])


def test_oil_rule_is_not_applicable_without_its_inputs():
    rule = R.get("XASSET.OIL_FX.L63")
    no_oil = mini_panel({"CAD": [1.0] * 3, "EUR": [1.0] * 3})
    assert R.missing_requirements(rule, no_oil) == ("aux:oil",)
    with pytest.raises(C.NotApplicable):
        rule.signal(no_oil)
    no_ccy = mini_panel({"EUR": [1.0] * 3, "JPY": [1.0] * 3}, aux={"oil": {"WTI": [1, 2, 3]}})
    assert R.missing_requirements(rule, no_ccy) == ("instrument:CAD|instrument:NOK|instrument:MXN",)
    with pytest.raises(C.NotApplicable):
        rule.signal(no_ccy)
    two = mini_panel({"CAD": [1.0] * 3}, aux={"oil": {"brent": [1, 2, 3], "wti_alt": [1, 2, 3]}})
    with pytest.raises(C.NotApplicable):
        rule.signal(two)                                             # ambiguous oil frame


def test_glsr_fade_hand_computed():
    e = math.e
    glsr = {"A": [1, 1, 1, 1, 1, 1, e], "B": [e, e, e, e, e, e, 1], "C": [1, e, 1, e, 1, e, e ** 0.5],
            "D": [1, 1, 1, 1, 1, 1, 1]}
    p = mini_panel({c: [10.0] * 7 for c in glsr}, aux={"glsr": glsr}, ppy=365, freq="D")
    s = rules_misc.glsr_fade(p, lookback=7)
    # ln glsr: A six 0s then 1 -> z = +6/sqrt(7) = 2.268 ; B mirrored -> -2.268 ; C 0,1,0,1,0,1,.5 -> z = 0
    # D is constant -> no z -> no view. Three ranked: fade the crowded long A, buy B.
    np.testing.assert_array_equal(s.iloc[-1].to_numpy(), [-1.0, 1.0, 0.0, NAN])
    assert s.iloc[:6].isna().all().all()
    z = C.zscore(C.safe_log(p.aux["glsr"]), 7).iloc[-1]
    assert z["A"] == pytest.approx(6 / math.sqrt(7), rel=1e-12) and z["C"] == pytest.approx(0.0, abs=1e-12)
    with pytest.raises(C.NotApplicable):
        rules_misc.glsr_fade(mini_panel({"A": [1.0] * 3}))
