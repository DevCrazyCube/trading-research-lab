"""Tests for scripts/factory/stats.py — every key of `summarize` against hand-computed numbers,
the HAC t-statistic against statsmodels, windowed scoring (warm-up never scored), the Sharpe
toolkit (PSR / DSR / MinTRL), the stationary bootstrap and the contribution table.

Run:  cd /home/anont/meme && research/factory/.venv/bin/python -m pytest scripts/factory/tests/test_stats.py -q
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
from scipy import stats as sps

from scripts.factory import stats as S
from scripts.factory.engine import backtest
from scripts.factory.panel import PanelBundle

# The hand-worked series X5 (5 prints, periods_per_year = 252):
#   x = [0.01, -0.02, 0.03, 0.00, 0.02]     mean = 0.008
#   d = x - mean = [0.002, -0.028, 0.022, -0.008, 0.012]      SUM d^2 = 1.48e-3
X5 = np.array([0.01, -0.02, 0.03, 0.00, 0.02])


# --------------------------------------------------------------------------------------------------
# summarize: every key, by hand
# --------------------------------------------------------------------------------------------------
def test_summarize_returns_exactly_the_contract_keys():
    contract = ["n_obs", "start", "end", "ann_return", "cagr", "ann_vol", "sharpe", "hac_t", "p_one_sided",
                "sortino", "max_drawdown", "calmar", "skew", "excess_kurt", "hit_rate", "worst_print", "worst_21",
                "avg_gross_leverage", "turnover_sides_per_year", "breakeven_cost_bp_side", "beta", "alpha_ann",
                "alpha_t", "psr0"]
    out = S.summarize(X5, periods_per_year=252)
    assert list(out) == contract and list(S.STAT_KEYS) == contract


def test_summarize_known_answers_on_x5():
    out = S.summarize(X5, periods_per_year=252, hac_lags=1)
    assert out["n_obs"] == 5 and out["start"] is None and out["end"] is None
    # ann_return = 0.008 * 252 = 2.016 (arithmetic)
    assert out["ann_return"] == pytest.approx(2.016, abs=1e-12)
    # curve = 1.01, 0.9898, 1.019494, 1.019494, 1.03988388 ; cagr = 1.03988388^(252/5) - 1
    assert out["cagr"] == pytest.approx(1.03988388 ** (252 / 5) - 1, rel=1e-12)
    # var(ddof=1) = 1.48e-3 / 4 = 3.7e-4 ; sd = 0.0192353841 ; ann_vol = sd * sqrt(252) = 0.3053522556
    assert out["ann_vol"] == pytest.approx(math.sqrt(3.7e-4) * math.sqrt(252), rel=1e-12)
    assert out["ann_vol"] == pytest.approx(0.3053522556, abs=1e-9)
    # sharpe = 0.008 / 0.0192353841 * sqrt(252) = 6.6022109319
    assert out["sharpe"] == pytest.approx(6.6022109319, abs=1e-9)
    # HAC, L = 1: g0 = 1.48e-3/5 = 2.96e-4 ; g1 = (d1d0 + d2d1 + d3d2 + d4d3)/5
    #   = (-5.6e-5 - 6.16e-4 - 1.76e-4 - 9.6e-5)/5 = -1.888e-4 ; S = g0 + 2*(1 - 1/2)*g1 = 1.072e-4
    #   se = sqrt(S/5) = sqrt(2.144e-5) = 0.00463033 ; t = 0.008 / 0.00463033 = 1.7277369
    assert out["hac_t"] == pytest.approx(0.008 / math.sqrt(1.072e-4 / 5), rel=1e-10)
    assert out["hac_t"] == pytest.approx(1.7277369, abs=1e-6)
    assert out["p_one_sided"] == pytest.approx(sps.norm.sf(1.7277368511627), rel=1e-9)   # 0.0420177
    assert out["p_one_sided"] == pytest.approx(0.0420177, abs=1e-6)
    # sortino: min(x,0)^2 = [0, 4e-4, 0, 0, 0] -> mean 8e-5 -> 0.00894427 ; 0.008/0.00894427*sqrt(252) = 14.1985915
    assert out["sortino"] == pytest.approx(0.008 / math.sqrt(8e-5) * math.sqrt(252), rel=1e-12)
    # max drawdown: peak 1.01 after print 0, trough 0.9898 -> 0.9898/1.01 - 1 = -0.02
    assert out["max_drawdown"] == pytest.approx(-0.02, abs=1e-12)
    assert out["calmar"] == pytest.approx(out["cagr"] / 0.02, rel=1e-9)
    # m2 = 2.96e-4 ; m3 = SUM d^3 / 5 = -1.008e-5/5 = -2.016e-6 ; skew = m3 / m2^1.5 = -0.3958703
    assert out["skew"] == pytest.approx(-2.016e-6 / 2.96e-4 ** 1.5, rel=1e-9)
    assert out["skew"] == pytest.approx(-0.3958703, abs=1e-6)
    # m4 = 8.7376e-7 / 5 = 1.74752e-7 ; m2^2 = 8.7616e-8 ; excess = 1.9945215 - 3 = -1.0054785
    assert out["excess_kurt"] == pytest.approx(1.74752e-7 / 8.7616e-8 - 3.0, rel=1e-9)
    # hit rate: 3 positive prints of 4 non-flat ones (the 0.00 print is excluded)
    assert out["hit_rate"] == 0.75
    assert out["worst_print"] == -0.02
    assert math.isnan(out["worst_21"])                                  # fewer than 21 prints
    # psr0: sr = 0.008/0.0192353841 = 0.4159002 ; denom = 1 + 0.3958703*0.4159002 + (1.9945215-1)/4*0.4159002^2
    #       = 1.2076490 ; z = 0.4159002*sqrt(4)/sqrt(1.2076490) = 0.7569180 ; Phi = 0.7754505
    assert out["psr0"] == pytest.approx(0.7754505, abs=1e-6)
    for k in ("avg_gross_leverage", "turnover_sides_per_year", "breakeven_cost_bp_side", "beta", "alpha_ann", "alpha_t"):
        assert math.isnan(out[k])
    # cross-check the moment definitions against scipy's population estimators
    assert out["skew"] == pytest.approx(sps.skew(X5, bias=True), rel=1e-12)
    assert out["excess_kurt"] == pytest.approx(sps.kurtosis(X5, fisher=True, bias=True), rel=1e-12)


def test_engine_companions_turnover_leverage_breakeven():
    # 4 prints, ppy = 250. gross = [0.001, 0.0, 0.0006, 0.0] -> mean 0.0004 ; turnover = [0.5, 0, 0.3, 0] -> mean 0.2
    #   breakeven = 1e4 * 0.0004 / 0.2 = 20 bp per side ; turnover sides per year = 0.2 * 250 = 50
    #   leverage = [1, 1, 2, 2] -> mean 1.5
    net = np.array([0.0009, 0.0, 0.0005, 0.0])
    out = S.summarize(net, periods_per_year=250, gross=[0.001, 0.0, 0.0006, 0.0], turnover=[0.5, 0.0, 0.3, 0.0],
                      gross_leverage=[1.0, 1.0, 2.0, 2.0])
    assert out["breakeven_cost_bp_side"] == pytest.approx(20.0, rel=1e-12)
    assert out["turnover_sides_per_year"] == pytest.approx(50.0, rel=1e-12)
    assert out["avg_gross_leverage"] == pytest.approx(1.5, rel=1e-12)
    # no trades -> no breakeven; turnover without gross -> turnover/yr only
    flat = S.summarize(net, periods_per_year=250, gross=[0.001, 0.0, 0.0006, 0.0], turnover=[0.0] * 4)
    assert math.isnan(flat["breakeven_cost_bp_side"]) and flat["turnover_sides_per_year"] == 0.0
    only_to = S.summarize(net, periods_per_year=250, turnover=[0.5, 0.0, 0.3, 0.0])
    assert math.isnan(only_to["breakeven_cost_bp_side"]) and only_to["turnover_sides_per_year"] == pytest.approx(50.0)


def test_breakeven_is_the_cost_that_zeroes_net_when_there_are_no_hold_costs():
    """Engine round trip: re-running at the reported breakeven cost gives mean(net) = 0."""
    rng = np.random.default_rng(5)
    T, N = 300, 4
    idx = pd.date_range("2020-01-01", periods=T, freq="D", tz="UTC")
    cols = list("abcd")
    prices = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0.0008, 0.01, (T, N)), axis=0)), index=idx, columns=cols)
    panel = PanelBundle("T", prices, meta={"periods_per_year": 365})
    w = pd.DataFrame(np.abs(rng.normal(0.2, 0.1, (T, N))), index=idx, columns=cols)
    base = backtest(panel, w, cost_bp_side=3.0)
    st = S.summarize(base.net, periods_per_year=365, gross=base.gross, turnover=base.turnover)
    at_be = backtest(panel, w, cost_bp_side=st["breakeven_cost_bp_side"])
    assert abs(at_be.net.mean()) < 1e-15


def test_worst_21_known_answer():
    # 30 prints: zero, except 21 consecutive prints of -1% (rows 4..24) -> 0.99^21 - 1 = -0.19027213
    x = np.zeros(30)
    x[4:25] = -0.01
    out = S.summarize(x, periods_per_year=252)
    assert out["worst_21"] == pytest.approx(0.99 ** 21 - 1, rel=1e-12)
    assert out["worst_21"] == pytest.approx(-0.19027213, abs=1e-8)
    assert S.worst_window([0.1, -0.5, 0.2], k=2) == pytest.approx(min(1.1 * 0.5, 0.5 * 1.2) - 1)   # -0.45


def test_max_drawdown_counts_the_starting_equity_as_a_peak():
    # A book that loses from its first print: curve 1 -> 0.5 -> 0.5 -> 0.55. Drawdown is -50 %, not 0.
    # (the v1 draft returned 0.0 here: it took the running peak from E_0, not from the starting 1.0)
    assert S.max_drawdown([-0.5, 0.0, 0.1]) == pytest.approx(-0.5, abs=1e-15)
    assert S.max_drawdown([0.1, 0.1]) == 0.0
    # 1 -> 1.1 -> 0.88 -> 0.968 : trough 0.88/1.1 - 1 = -0.2
    assert S.max_drawdown([0.1, -0.2, 0.1]) == pytest.approx(-0.2, abs=1e-15)
    assert S.max_drawdown([0.5, -1.0, 0.3]) == -1.0 and S.cagr([0.5, -1.0, 0.3], 252) == -1.0     # ruin
    assert math.isnan(S.max_drawdown([]))


def test_degenerate_inputs_give_nan_not_exceptions():
    one = S.summarize([0.01], periods_per_year=252)
    assert one["n_obs"] == 1 and math.isnan(one["sharpe"]) and math.isnan(one["hac_t"]) and math.isnan(one["ann_vol"])
    assert one["ann_return"] == pytest.approx(2.52)
    const = S.summarize([0.0] * 30, periods_per_year=252)
    assert math.isnan(const["sharpe"]) and math.isnan(const["hac_t"]) and math.isnan(const["hit_rate"])
    assert math.isnan(const["sortino"]) and math.isnan(const["calmar"]) and math.isnan(const["psr0"])
    assert const["max_drawdown"] == 0.0 and const["worst_21"] == 0.0
    empty = S.summarize(pd.Series([], dtype=float, index=pd.DatetimeIndex([], tz="UTC")), periods_per_year=252)
    assert empty["n_obs"] == 0 and empty["start"] is None and math.isnan(empty["ann_return"])


def test_structural_errors_raise():
    idx = pd.date_range("2020-01-01", periods=5, freq="D", tz="UTC")
    net = pd.Series(X5, index=idx)
    with pytest.raises(ValueError, match="NaN/inf inside the scored window"):
        S.summarize(pd.Series([0.01, np.nan, 0.02], index=idx[:3]), periods_per_year=252)
    with pytest.raises(ValueError, match="turnover has 4 rows"):
        S.summarize(net, periods_per_year=252, turnover=[0.1] * 4)
    with pytest.raises(ValueError, match="does not cover the scored window"):
        S.summarize(net, periods_per_year=252, gross=net.iloc[1:])
    with pytest.raises(ValueError, match="benchmark has NaN"):
        S.summarize(net, periods_per_year=252, benchmark=pd.Series([np.nan, 0, 0, 0, 0.0], index=idx))
    with pytest.raises(ValueError, match="tz-aware DatetimeIndex"):
        S.summarize(X5, periods_per_year=252, window=("2020-01-01", "2020-01-03"))
    with pytest.raises(ValueError, match="tz-aware DatetimeIndex"):
        S.summarize(pd.Series(X5, index=idx.tz_localize(None)), periods_per_year=252, window=("2020-01-01", None))
    with pytest.raises(ValueError, match="after its end"):
        S.summarize(net, periods_per_year=252, window=("2020-01-04", "2020-01-02"))
    with pytest.raises(ValueError, match="periods_per_year"):
        S.summarize(net, periods_per_year=0)
    with pytest.raises(ValueError, match=r"window must be \(start, end\)"):
        S.summarize(net, periods_per_year=252, window="2020-01-01")


# --------------------------------------------------------------------------------------------------
# Windows: warm-up is never scored; semantics identical to PanelBundle.window
# --------------------------------------------------------------------------------------------------
def test_window_scores_only_the_window_and_warm_up_is_excluded():
    rng = np.random.default_rng(11)
    idx = pd.date_range("2019-01-01 13:15", periods=400, freq="D", tz="UTC")
    x = rng.normal(0.001, 0.01, 400)
    x[:100] = 0.0                                                       # 100 flat warm-up prints
    net = pd.Series(x, index=idx)
    gross = net + 0.0001
    to = pd.Series(rng.uniform(0, 0.2, 400), index=idx)
    win = (idx[100], None)
    scored = S.summarize(net, periods_per_year=365, window=win, gross=gross, turnover=to)
    direct = S.summarize(x[100:], periods_per_year=365, gross=gross.to_numpy()[100:], turnover=to.to_numpy()[100:])
    for k in S.STAT_KEYS:
        if k in ("start", "end"):
            continue
        assert scored[k] == pytest.approx(direct[k], rel=1e-12, nan_ok=True), k
    assert scored["n_obs"] == 300 and scored["start"] == idx[100].isoformat() and scored["end"] == idx[-1].isoformat()
    diluted = S.summarize(net, periods_per_year=365)                     # scoring the warm-up dilutes everything
    assert diluted["n_obs"] == 400 and diluted["hac_t"] < scored["hac_t"] and diluted["ann_return"] < scored["ann_return"]


def test_a_date_only_end_bound_includes_that_days_print():
    # Prints at 13:15 UTC. The end bound '2020-01-05' must include the 2020-01-05 13:15 print (the v1 bug dropped it).
    idx = pd.date_range("2020-01-01 13:15", periods=10, freq="D", tz="UTC")
    net = pd.Series(np.arange(10) / 100.0, index=idx)
    out = S.summarize(net, periods_per_year=252, window=("2020-01-03", "2020-01-05"))
    assert out["n_obs"] == 3 and out["start"] == "2020-01-03T13:15:00+00:00" and out["end"] == "2020-01-05T13:15:00+00:00"
    assert out["ann_return"] == pytest.approx((0.02 + 0.03 + 0.04) / 3 * 252)


@pytest.mark.parametrize("seed", range(25))
def test_window_mask_is_identical_to_panelbundle_window(seed):
    rng = np.random.default_rng(seed)
    hour = int(rng.choice([0, 0, 12, 13, 17]))
    idx = pd.date_range(f"2021-03-01 {hour:02d}:15" if hour else "2021-03-01", periods=60, freq="D", tz="UTC")
    panel = PanelBundle("W", pd.DataFrame({"A": np.arange(60) + 1.0}, index=idx))

    def bound():
        d = pd.Timestamp("2021-03-01") + pd.Timedelta(days=int(rng.integers(-3, 64)))
        kind = int(rng.integers(0, 6))
        if kind == 0:
            return None
        if kind == 1:
            return d.strftime("%Y-%m-%d")                               # date-only string
        if kind == 2:
            return d                                                    # naive midnight Timestamp
        if kind == 3:
            return d.tz_localize("UTC") + pd.Timedelta(hours=int(rng.integers(0, 24)))
        if kind == 4:
            return (d + pd.Timedelta(hours=13)).strftime("%Y-%m-%d %H:%M")
        return d.tz_localize("Europe/Amsterdam")

    a, b = bound(), bound()
    expected = panel.window(a, b).prices.index
    try:
        mask = S.window_mask(idx, (a, b))
    except ValueError as exc:                                           # start after end: the panel returns no rows
        assert "after its end" in str(exc) and len(expected) == 0
        return
    assert idx[mask].equals(expected)


def test_evidence_table():
    idx = pd.date_range("2010-01-01", periods=1000, freq="D", tz="UTC")
    rng = np.random.default_rng(2)
    net = pd.Series(rng.normal(0.0005, 0.01, 1000), index=idx)
    windows = {"FULL": ("2010-01-01", None), "PRE": (None, "2010-12-31"), "POST": ("2011-01-01", None),
               "EMPTY": ("2030-01-01", None)}
    table = S.evidence_table(net, windows, 365)
    assert list(table.index) == ["FULL", "PRE", "POST", "EMPTY"] and list(table.columns) == list(S.STAT_KEYS)
    assert table.loc["FULL", "n_obs"] == 1000 and table.loc["PRE", "n_obs"] == 365 and table.loc["POST", "n_obs"] == 635
    assert table.loc["EMPTY", "n_obs"] == 0 and pd.isna(table.loc["EMPTY", "sharpe"])
    assert table.loc["PRE", "sharpe"] == pytest.approx(S.sharpe_ratio(net.iloc[:365], 365), rel=1e-12)
    assert table.loc["POST", "end"] == idx[-1].isoformat()
    with pytest.raises(ValueError):
        S.evidence_table(net, {}, 365)


# --------------------------------------------------------------------------------------------------
# HAC: hand example and statsmodels
# --------------------------------------------------------------------------------------------------
def test_newey_west_hand_example():
    # x = [1, 2, 4, 3], L = 1: mean 2.5, d = [-1.5, -0.5, 1.5, 0.5]
    #   g0 = (2.25 + 0.25 + 2.25 + 0.25)/4 = 1.25 ; g1 = (0.75 - 0.75 + 0.75)/4 = 0.1875
    #   S = 1.25 + 2*(1/2)*0.1875 = 1.4375 ; se = sqrt(1.4375/4) = 0.599479 ; t = 2.5/0.599479 = 4.170288
    assert S.newey_west_t([1.0, 2.0, 4.0, 3.0], lags=1) == pytest.approx(2.5 / math.sqrt(1.4375 / 4), rel=1e-12)
    assert S.newey_west_t([1.0, 2.0, 4.0, 3.0], lags=1) == pytest.approx(4.170288, abs=1e-6)
    # L = 0 is the plain t with the population variance: 2.5 / sqrt(1.25/4) = 4.472136
    assert S.newey_west_t([1.0, 2.0, 4.0, 3.0], lags=0) == pytest.approx(4.472136, abs=1e-6)
    assert math.isnan(S.newey_west_t([1.0, 2.0, 4.0, 3.0], lags=3))     # needs T > L + 1
    assert math.isnan(S.newey_west_t([2.0] * 20, lags=5))               # zero variance


@pytest.mark.parametrize("seed,lags", [(0, 5), (1, 5), (2, 1), (3, 10), (4, 0), (5, 21)])
def test_hac_t_equals_statsmodels_without_small_sample_correction(seed, lags):
    """WHICH statsmodels setting matches: OLS on a constant, cov_type='HAC', maxlags=L,
    use_correction=False (statsmodels' default). use_correction=True is a DIFFERENT number."""
    rng = np.random.default_rng(seed)
    e = rng.normal(0, 0.01, 600)
    x = 0.0004 + e + 0.3 * np.concatenate([[0.0], e[:-1]])              # MA(1): autocorrelated on purpose
    ols = sm.OLS(x, np.ones((len(x), 1)))
    plain = ols.fit(cov_type="HAC", cov_kwds={"maxlags": lags, "use_correction": False})
    default = ols.fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    corrected = ols.fit(cov_type="HAC", cov_kwds={"maxlags": lags, "use_correction": True})
    mine = S.newey_west_t(x, lags)
    assert mine == pytest.approx(float(plain.tvalues[0]), rel=1e-10)
    assert float(default.tvalues[0]) == pytest.approx(float(plain.tvalues[0]), rel=1e-14)
    # the small-sample correction scales the variance by n/(n-1): t shrinks by sqrt((n-1)/n)
    assert float(corrected.tvalues[0]) == pytest.approx(mine * math.sqrt(599 / 600), rel=1e-10)
    assert S.summarize(x, periods_per_year=252, hac_lags=lags)["hac_t"] == pytest.approx(mine, rel=1e-14)
    assert S.summarize(x, periods_per_year=252, hac_lags=lags)["p_one_sided"] == pytest.approx(
        float(sps.norm.sf(plain.tvalues[0])), rel=1e-9)


def test_newey_west_is_vectorised_over_columns():
    rng = np.random.default_rng(9)
    X = rng.normal(0.001, 0.02, (300, 7))
    X[:, 3] = 0.5                                                       # a constant column -> NaN, the rest unaffected
    t = S.newey_west_t(X, 5)
    assert t.shape == (7,) and math.isnan(t[3])
    for j in (0, 1, 2, 4, 5, 6):
        assert t[j] == pytest.approx(S.newey_west_t(X[:, j], 5), rel=1e-13)


def test_beta_alpha_exact_and_against_statsmodels():
    rng = np.random.default_rng(3)
    bench = rng.normal(0.0003, 0.01, 500)
    # exact line: net = 0.001 + 0.5 * bench -> beta 0.5, alpha_ann = 0.001 * 252 = 0.252, alpha_t undefined (zero residual)
    exact = S.summarize(0.001 + 0.5 * bench, periods_per_year=252, benchmark=bench)
    assert exact["beta"] == pytest.approx(0.5, rel=1e-10) and exact["alpha_ann"] == pytest.approx(0.252, rel=1e-9)
    assert math.isnan(exact["alpha_t"])
    noise = rng.normal(0, 0.004, 500)
    noise[1:] += 0.4 * noise[:-1]
    net = 0.0002 + 0.7 * bench + noise
    out = S.summarize(net, periods_per_year=252, benchmark=bench, hac_lags=5)
    ref = sm.OLS(net, sm.add_constant(bench)).fit(cov_type="HAC", cov_kwds={"maxlags": 5, "use_correction": False})
    assert out["beta"] == pytest.approx(float(ref.params[1]), rel=1e-10)
    assert out["alpha_ann"] == pytest.approx(float(ref.params[0]) * 252, rel=1e-10)
    assert out["alpha_t"] == pytest.approx(float(ref.tvalues[0]), rel=1e-9)
    coef, cov = S.hac_ols(net, sm.add_constant(bench), 5)
    np.testing.assert_allclose(cov, ref.cov_params(), rtol=1e-9)
    const_bench = S.summarize(net, periods_per_year=252, benchmark=np.full(500, 0.001))
    assert math.isnan(const_bench["beta"]) and math.isnan(const_bench["alpha_t"])


# --------------------------------------------------------------------------------------------------
# PSR / expected max Sharpe / DSR / MinTRL
# --------------------------------------------------------------------------------------------------
def test_psr_known_answers():
    # sr = 0.1 per print, n = 101, normal: z = 0.1*sqrt(100)/sqrt(1 + 0.5*0.01) = 1/sqrt(1.005) = 0.99750934 -> 0.84074133
    assert S.psr(0.1, 0.0, 101, 0.0, 3.0) == pytest.approx(0.84074133, abs=1e-8)
    # skew -1, kurt 6: denom = 1 + 0.1 + (5/4)*0.01 = 1.1125 ; z = 1/sqrt(1.1125) = 0.94809093 -> 0.82845842
    assert S.psr(0.1, 0.0, 101, -1.0, 6.0) == pytest.approx(0.82845842, abs=1e-8)
    assert S.psr(0.1, 0.1, 101, 0.0, 3.0) == pytest.approx(0.5)          # estimate equal to the hurdle
    assert math.isnan(S.psr(0.1, 0.0, 1, 0.0, 3.0)) and math.isnan(S.psr(float("nan"), 0.0, 50, 0.0, 3.0))
    assert math.isnan(S.psr(2.0, 0.0, 50, 3.0, 1.0))                     # 1 - 6 + 0 < 0: variance term not positive


def test_expected_max_sharpe_known_answer():
    # N = 10, V = 1: (1-g)*Phi^-1(0.9) + g*Phi^-1(1 - 1/(10e))
    #   = 0.42278434*1.28155157 + 0.57721566*1.78924176 = 0.54181 + 1.03278 = 1.57459830
    assert S.expected_max_sharpe(10, 1.0) == pytest.approx(1.57459830, abs=1e-8)
    assert S.expected_max_sharpe(10, 0.04) == pytest.approx(0.2 * 1.57459830, abs=1e-8)   # scales with sqrt(V)
    assert S.expected_max_sharpe(1, 1.0) == 0.0 and S.expected_max_sharpe(50, 0.0) == 0.0
    assert S.expected_max_sharpe(1000, 1.0) > S.expected_max_sharpe(100, 1.0) > S.expected_max_sharpe(10, 1.0)
    # sanity against simulation: the mean of the max of 10 standard normals is 1.5388 (the formula is an
    # approximation that slightly overstates it at small N)
    sim = np.random.default_rng(0).standard_normal((200_000, 10)).max(axis=1).mean()
    assert abs(sim - 1.5388) < 0.01 and abs(S.expected_max_sharpe(10, 1.0) - sim) < 0.05


def test_deflated_sharpe():
    rng = np.random.default_rng(4)
    x = rng.normal(0.001, 0.01, 1000)
    one = S.deflated_sharpe(x, n_trials=1)
    assert one["sr0_per_print"] == 0.0 and one["dsr"] == pytest.approx(S.summarize(x, periods_per_year=252)["psr0"], rel=1e-12)
    many = S.deflated_sharpe(x, n_trials=100)
    assert many["var_source"] == "assumed_1_over_n_minus_1" and many["var_sharpe_used"] == pytest.approx(1 / 999)
    assert many["sr0_per_print"] == pytest.approx(S.expected_max_sharpe(100, 1 / 999), rel=1e-12)
    assert many["dsr"] < one["dsr"]
    sr = x.mean() / x.std(ddof=1)
    skew, kurt = sps.skew(x, bias=True), sps.kurtosis(x, fisher=False, bias=True)
    assert many["dsr"] == pytest.approx(S.psr(sr, many["sr0_per_print"], 1000, skew, kurt), rel=1e-12)
    supplied = S.deflated_sharpe(x, n_trials=100, var_sharpe_trials=0.01)
    assert supplied["var_source"] == "supplied" and supplied["sr0_per_print"] == pytest.approx(0.1 * S.expected_max_sharpe(100, 1.0))
    assert math.isnan(S.deflated_sharpe([0.0, 0.0, 0.0, 0.0], n_trials=5)["dsr"])


def test_min_track_record_length_known_answer():
    # sr = 0.1/print, normal, alpha 5 %: 1 + (1 + 0.5*0.01) * (1.6448536/0.1)^2 = 1 + 1.005*270.554345 = 272.907117
    assert S.min_track_record_length(0.1) == pytest.approx(272.907117, abs=1e-6)
    # consistency with PSR: at n = MinTRL the PSR is exactly 1 - alpha
    n = S.min_track_record_length(0.05, 0.01, skew=-0.8, kurt=5.0, alpha=0.05)
    z = (0.05 - 0.01) * math.sqrt(n - 1) / math.sqrt(1 + 0.8 * 0.05 + (5 - 1) / 4 * 0.05 ** 2)
    assert sps.norm.cdf(z) == pytest.approx(0.95, abs=1e-12)
    assert S.min_track_record_length(0.01, 0.02) == float("inf")
    assert math.isnan(S.min_track_record_length(0.1, alpha=1.5))
    # negative skew and fat tails lengthen the record needed
    assert S.min_track_record_length(0.1, skew=-1.0, kurt=8.0) > S.min_track_record_length(0.1)


# --------------------------------------------------------------------------------------------------
# Stationary bootstrap
# --------------------------------------------------------------------------------------------------
def test_indices_from_draws_hand_example():
    # n = 5. Blocks start at positions 0 and 3, with drawn starts 3 and 0:
    #   pos 0: 3 ; pos 1: 3+1 = 4 ; pos 2: 3+2 = 5 -> wraps to 0 ; pos 3: new block at 0 ; pos 4: 0+1 = 1
    new_block = np.array([[True, False, False, True, False]])
    starts = np.array([[3, 9, 9, 0, 9]])                                # the 9s are never read
    assert S.indices_from_draws(new_block, starts, 5).tolist() == [[3, 4, 0, 0, 1]]
    # column 0 always starts a block, whatever the draw says
    assert S.indices_from_draws(np.array([[False, False, False]]), np.array([[2, 7, 7]]), 3).tolist() == [[2, 0, 1]]


def test_stationary_bootstrap_block_lengths_have_the_requested_mean():
    rng = np.random.default_rng(0)
    idx = S.stationary_bootstrap_indices(2000, 10.0, 200, rng)
    assert idx.shape == (200, 2000) and idx.min() >= 0 and idx.max() <= 1999
    continues = (idx[:, 1:] == (idx[:, :-1] + 1) % 2000).mean()
    # P(position continues the previous block) = 1 - 1/10, plus a 1/2000 chance that a new block lands there anyway
    assert continues == pytest.approx(0.9 + 0.1 / 2000, abs=0.004)
    iid = S.stationary_bootstrap_indices(500, 1.0, 50, rng)
    assert (iid[:, 1:] == (iid[:, :-1] + 1) % 500).mean() < 0.01
    with pytest.raises(ValueError):
        S.stationary_bootstrap_indices(10, 0.5, 5, rng)


def test_default_block_length_known_answers():
    # ceil(2 * T^(1/3)): 2*500^(1/3) = 15.87 -> 16 ; 2*1250^(1/3) = 21.54 -> 22 ; 2*4400^(1/3) = 32.77 -> 33
    assert S.default_block_length(500) == 16 and S.default_block_length(1250) == 22 and S.default_block_length(4400) == 33
    assert S.BLOCK_FACTOR == 2.0
    # exact cubes are not pushed up or down by the float cube root: 27 -> 2*3, 64 -> 2*4, 1000 -> 2*10
    assert S.default_block_length(27) == 6 and S.default_block_length(64) == 8 and S.default_block_length(1000) == 20
    assert S.default_block_length(27, factor=1.0) == 3 and S.default_block_length(1000, factor=1.0) == 10
    assert S.default_block_length(1) == 2 and S.default_block_length(1, factor=0.1) == 1          # never below 1
    assert S.default_block_length(500, factor=1.0) == 8
    # far below arch's sqrt(T) fallback: 33 against 66 at T = 4,400
    assert S.default_block_length(4400) < int(math.sqrt(4400)) == 66
    # the rule behind the factor: the MSE-optimal block for an AR(1) is (2 rho / (1 - rho^2))^(2/3) * T^(1/3):
    #   rho = 0.1 -> 0.344 ; rho = 0.3 -> 0.757 ; rho = sqrt(2) - 1 -> 1 ; rho = 1/sqrt(2) -> 2
    coef = lambda rho: (2 * rho / (1 - rho ** 2)) ** (2 / 3)                               # noqa: E731
    assert coef(0.1) == pytest.approx(0.344, abs=1e-3) and coef(0.3) == pytest.approx(0.757, abs=1e-3)
    assert coef(math.sqrt(2) - 1) == pytest.approx(1.0, abs=1e-12) and coef(1 / math.sqrt(2)) == pytest.approx(2.0, abs=1e-12)
    for bad in (0, -5, 2.5, True):
        with pytest.raises(ValueError):
            S.default_block_length(bad)
    with pytest.raises(ValueError):
        S.default_block_length(100, factor=0.0)


def test_sharpe_ci_bootstrap_known_answers():
    rng = np.random.default_rng(1)
    x = rng.normal(0.0008, 0.01, 750)
    point = S.sharpe_ratio(x, 252)
    # One block as long as the sample = a circular shift: every replicate has the sample's own mean and std,
    # so the interval collapses onto the point estimate.
    one_block = S.sharpe_ci_bootstrap(x, periods_per_year=252, block=1e12, reps=200, seed=3)
    assert one_block["lo"] == pytest.approx(point, rel=1e-9) and one_block["hi"] == pytest.approx(point, rel=1e-9)
    assert one_block["sharpe"] == pytest.approx(point, rel=1e-14)
    a = S.sharpe_ci_bootstrap(x, periods_per_year=252, block=5, reps=1500, seed=7)
    b = S.sharpe_ci_bootstrap(x, periods_per_year=252, block=5, reps=1500, seed=7)
    c = S.sharpe_ci_bootstrap(x, periods_per_year=252, block=5, reps=1500, seed=8)
    assert a == b and (a["lo"], a["hi"]) != (c["lo"], c["hi"])           # seedable and deterministic
    assert a["lo"] < point < a["hi"] and a["n_degenerate"] == 0 and a["n_obs"] == 750
    # iid data: the bootstrap standard error matches the textbook sqrt((1 + SR^2/2)/n) * sqrt(ppy) within 15 %
    sr_pp = x.mean() / x.std(ddof=1)
    analytic = math.sqrt((1 + sr_pp ** 2 / 2) / 750) * math.sqrt(252)
    iid = S.sharpe_ci_bootstrap(x, periods_per_year=252, block=1, reps=4000, seed=1)
    assert iid["se"] == pytest.approx(analytic, rel=0.15)
    assert 0.0 <= iid["frac_le_zero"] <= 1.0
    wider = S.sharpe_ci_bootstrap(x, periods_per_year=252, block=5, reps=1500, seed=7, ci=0.99)
    assert wider["lo"] < a["lo"] and wider["hi"] > a["hi"]
    short = S.sharpe_ci_bootstrap([0.01, 0.02], periods_per_year=252)
    assert math.isnan(short["lo"]) and short["n_obs"] == 2
    # no block given: the default ceil(2 n^(1/3)) = ceil(2 * 9.086) = 19 at n = 750 is used and reported
    auto = S.sharpe_ci_bootstrap(x, periods_per_year=252, reps=500, seed=7)
    assert auto["block"] == 19.0 == S.default_block_length(750)
    assert auto == S.sharpe_ci_bootstrap(x, periods_per_year=252, block=19, reps=500, seed=7)


def test_sharpe_ci_bootstrap_coverage_on_iid_data():
    """90 % intervals should cover the true Sharpe about 90 % of the time (measured, loose bounds)."""
    true_sharpe = 0.05 * math.sqrt(252)                                 # mean 0.0005, sd 0.01 per print
    hits = 0
    trials = 120
    for seed in range(trials):
        x = np.random.default_rng(1000 + seed).normal(0.0005, 0.01, 400)
        out = S.sharpe_ci_bootstrap(x, periods_per_year=252, block=1, reps=400, seed=seed)
        hits += out["lo"] <= true_sharpe <= out["hi"]
    coverage = hits / trials
    print(f"\n[measured] sharpe_ci_bootstrap 90% CI coverage on iid data: {coverage:.3f} ({hits}/{trials})")
    assert 0.80 <= coverage <= 0.97


def test_sharpe_ci_bootstrap_window():
    idx = pd.date_range("2020-01-01", periods=300, freq="D", tz="UTC")
    x = np.random.default_rng(6).normal(0.001, 0.01, 300)
    net = pd.Series(x, index=idx)
    win = S.sharpe_ci_bootstrap(net, periods_per_year=365, block=5, reps=300, seed=2, window=(idx[100], None))
    direct = S.sharpe_ci_bootstrap(x[100:], periods_per_year=365, block=5, reps=300, seed=2)
    assert win == direct and win["n_obs"] == 200


# --------------------------------------------------------------------------------------------------
# contribution_by_instrument
# --------------------------------------------------------------------------------------------------
def test_contribution_by_instrument_known_answer():
    # The engine's hand-worked panel K1 (see test_engine.py): per-instrument net
    #   A = [0, 0, +0.099, -0.10, 0, -0.001] -> SUM = -0.002 ; B = [0, 0, 0, 0, +0.0495, 0] -> SUM = +0.0495
    #   total = 0.0475 ; share_A = -0.002/0.0475 = -0.0421053 ; share_B = 1.0421053
    #   abs_share_A = 0.002/0.0515 = 0.0388350 ; abs_share_B = 0.9611650
    idx = pd.date_range("2024-01-01", periods=6, freq="D", tz="UTC")
    panel = PanelBundle("T", pd.DataFrame({"A": [100.0, 110.0, 121.0, 108.9, 108.9, 119.79],
                                           "B": [50.0, 50.0, 55.0, 55.0, 49.5, 49.5]}, index=idx),
                        meta={"periods_per_year": 365})
    w = pd.DataFrame({"A": [1.0, 1, 1, 0, 0, 0], "B": [0.0, 0, -0.5, -0.5, 0, 0]}, index=idx)
    res = backtest(panel, w, lag=1, cost_bp_side=10.0, turnover_model="target")     # the hand numbers above
    table = S.contribution_by_instrument(res)
    assert list(table.index) == ["B", "A"] and list(table.columns) == ["net", "share", "abs_share"]
    assert table.loc["A", "net"] == pytest.approx(-0.002, abs=1e-12)
    assert table.loc["B", "net"] == pytest.approx(0.0495, abs=1e-12)
    assert table.loc["A", "share"] == pytest.approx(-0.002 / 0.0475, rel=1e-9)
    assert table.loc["B", "share"] == pytest.approx(0.0495 / 0.0475, rel=1e-9)
    assert table.loc["A", "abs_share"] == pytest.approx(0.002 / 0.0515, rel=1e-9)
    assert table["abs_share"].sum() == pytest.approx(1.0) and table["net"].sum() == pytest.approx(res.net.sum())
    # windowed: rows 2..3 only -> A = 0.099 - 0.10 = -0.001, B = 0
    win = S.contribution_by_instrument(res, window=(idx[2], idx[3]))
    assert win.loc["A", "net"] == pytest.approx(-0.001, abs=1e-12) and win.loc["B", "net"] == 0.0
    with pytest.raises(ValueError):
        S.contribution_by_instrument(object())
    # under the default drift model the costs of row 5 are A 0.952381 * 10 bp and B 0.071429 * 10 bp
    #   A = -0.001 - 0.000952381 = -0.001952381 ; B = 0.0495 - 0.0000714286 = 0.0494285714
    drift = S.contribution_by_instrument(backtest(panel, w, lag=1, cost_bp_side=10.0))
    assert drift.loc["A", "net"] == pytest.approx(0.099 - 0.10 - (1 / 1.05) * 0.001, abs=1e-12)
    assert drift.loc["B", "net"] == pytest.approx(0.0495 - (0.5 - 0.45 / 1.05) * 0.001, abs=1e-12)
