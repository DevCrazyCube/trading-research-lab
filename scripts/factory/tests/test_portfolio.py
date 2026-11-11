"""Tests for scripts/factory/portfolio.py — hand-worked examples for every function, the truncation
(causality) proof for every function, and a few properties.

Run:  cd /home/anont/meme && research/factory/.venv/bin/python -m pytest scripts/factory/tests/test_portfolio.py -q
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from scripts.factory import portfolio as P
from scripts.factory.engine import Refused, backtest
from scripts.factory.panel import PanelBundle

ATOL = 1e-12
S2 = math.sqrt(2.0)


def alt_panel(T: int = 12, ppy: int = 4, carry=None) -> PanelBundle:
    """Two instruments with alternating returns, periods_per_year = 4 (sqrt = 2):
         A: +2 %, -2 %, +2 %, ...  (row 1 = +2 %)        B: +1 %, -1 %, +1 %, ..."""
    idx = pd.date_range("2024-01-01", periods=T, freq="D", tz="UTC")
    sign = np.where(np.arange(T) % 2 == 1, 1.0, -1.0)
    ra, rb = 0.02 * sign, 0.01 * sign
    ra[0] = rb[0] = 0.0
    prices = pd.DataFrame({"A": 100 * np.cumprod(1 + ra), "B": 50 * np.cumprod(1 + rb)}, index=idx)
    return PanelBundle("ALT", prices, carry=carry, meta={"periods_per_year": ppy})


def const_w(panel: PanelBundle, a: float, b: float) -> pd.DataFrame:
    return pd.DataFrame({"A": a, "B": b}, index=panel.prices.index)


def close(x, expected, atol=ATOL):
    np.testing.assert_allclose(np.asarray(x, dtype=float), np.asarray(expected, dtype=float), rtol=0, atol=atol)


# --------------------------------------------------------------------------------------------------
# book_returns / book_vol / risk_scale
# --------------------------------------------------------------------------------------------------
def test_book_returns_known_answer():
    # The engine's hand panel K1: r_A = [-, +10%, +10%, -10%, 0, +10%], r_B = [-, 0, +10%, 0, -10%, 0]
    #   w_A = [1,1,1,0,0,0], w_B = [0,0,-0.5,-0.5,0,0].  b_t = SUM w[t-1] * r[t]:
    #   b1 = 1*0.10 = 0.10 ; b2 = 1*0.10 + 0 = 0.10 ; b3 = 1*(-0.10) + (-0.5)*0 = -0.10 ;
    #   b4 = 0 + (-0.5)*(-0.10) = +0.05 ; b5 = 0
    idx = pd.date_range("2024-01-01", periods=6, freq="D", tz="UTC")
    prices = pd.DataFrame({"A": [100.0, 110.0, 121.0, 108.9, 108.9, 119.79], "B": [50.0, 50.0, 55.0, 55.0, 49.5, 49.5]},
                          index=idx)
    w = pd.DataFrame({"A": [1.0, 1, 1, 0, 0, 0], "B": [0.0, 0, -0.5, -0.5, 0, 0]}, index=idx)
    close(P.book_returns(w, PanelBundle("T", prices)), [0, 0.10, 0.10, -0.10, 0.05, 0.0])
    # with carry (+2 bp on A, -4 bp on B per print): b1 += 1*0.0002 ; b2 += 0.0002 ; b3 += 0.0002 + (-0.5)(-0.0004)
    carry = pd.DataFrame({"A": [0.0002] * 6, "B": [-0.0004] * 6}, index=idx)
    close(P.book_returns(w, PanelBundle("T", prices, carry=carry)),
          [0, 0.1002, 0.1002, -0.10 + 0.0004, 0.05 + 0.0002, 0.0])
    # NaN targets are flat; a missing price contributes 0, never NaN
    w2 = w.copy()
    w2.iloc[0, 0] = np.nan
    prices2 = prices.copy()
    prices2.iloc[2, 1] = np.nan
    out = P.book_returns(w2, PanelBundle("T", prices2))
    assert not out.isna().any() and out.iloc[1] == 0.0


def test_book_returns_is_not_the_engines_return():
    """The paper return has no fill delay and no cost: it differs from engine.backtest by construction."""
    panel = alt_panel()
    w = const_w(panel, 1.0, 0.0)
    paper = P.book_returns(w, panel)
    res = backtest(panel, w, lag=1, cost_bp_side=0.0)
    assert paper.iloc[1] == pytest.approx(0.02) and res.net.iloc[1] == 0.0      # the engine is still flat on row 1
    close(paper.iloc[2:], res.net.iloc[2:])                                     # constant weights: equal afterwards


def test_book_vol_and_risk_scale_known_answer_with_the_floor():
    # ppy = 4, vol_window = 2. w_A: rows 0-4 = 1, rows 5-8 = 0, rows 9-11 = 1 ; r_A alternates +2 % (odd t), -2 % (even t)
    #   b = [0, .02, -.02, .02, -.02, .02, 0, 0, 0, 0, -.02, .02]
    #   sigma_t = std(b[t-1], b[t], ddof=1) * 2 for t >= 2 (row 0 is not a return, so rows 0-1 are NaN):
    #     t=2..5: (.02, -.02) -> 0.04/sqrt2 * 2 = 0.0565685 ; t=6: (.02, 0) -> 0.0282843 ; t=7,8,9: (0,0) -> 0
    #     t=10: (0, -.02) -> 0.0282843 ; t=11: (-.02, .02) -> 0.0565685
    #   floor = 0.25 * median of the positive sigmas so far = 0.25 * 0.0565685 = 0.0141421 (the median stays 0.0565685)
    #   sigma_eff = [nan, nan, .0565685 x4, .0282843, .0141421 x3 (FLOORED), .0282843, .0565685]
    #   scale = 0.10 / sigma_eff = [nan, nan, 1.767767 x4, 3.535534, 7.071068 x3, 3.535534, 1.767767]
    panel = alt_panel()
    w = const_w(panel, 1.0, 0.0)
    w.iloc[5:9, 0] = 0.0
    close(P.book_returns(w, panel), [0, .02, -.02, .02, -.02, .02, 0, 0, 0, 0, -.02, .02])
    vol = P.book_vol(w, panel, vol_window=2)
    assert vol.iloc[:2].isna().all()
    s = 0.04 / S2 * 2
    close(vol.iloc[2:], [s, s, s, s, s / 2, s / 4, s / 4, s / 4, s / 2, s])
    scale = P.risk_scale(w, panel, vol_window=2, target=0.10)
    assert scale.iloc[:2].isna().all()
    close(scale.iloc[2:], [1.767767, 1.767767, 1.767767, 1.767767, 3.535534, 7.071068, 7.071068, 7.071068, 3.535534,
                           1.767767], atol=1e-6)
    # the floor caps the multiplier at 4x the typical one: 7.071068 = 4 * 1.767767
    assert scale.max() == pytest.approx(4 * 0.10 / s, rel=1e-12)


def test_a_book_that_never_trades_is_inactive():
    panel = alt_panel()
    assert P.book_vol(const_w(panel, 0.0, 0.0), panel, vol_window=2).isna().all()
    assert P.risk_scale(const_w(panel, 0.0, 0.0), panel, vol_window=2).isna().all()
    for bad in (1, 0, 2.5, True):
        with pytest.raises(Refused, match="vol_window"):
            P.book_vol(const_w(panel, 1.0, 0.0), panel, vol_window=bad)
    with pytest.raises(Refused, match="target"):
        P.risk_scale(const_w(panel, 1.0, 0.0), panel, vol_window=2, target=0.0)


# --------------------------------------------------------------------------------------------------
# equal_risk_combo / ensemble / vol_target
# --------------------------------------------------------------------------------------------------
def test_equal_risk_combo_known_answer():
    # book1: w_A = 1.0 -> sigma = 0.0565685 -> scale 1.767767 ; book2: w_A = 0.5 -> sigma = 0.0282843 -> scale 3.535534
    # combo_A = (1.767767*1.0 + 3.535534*0.5) / 2 = 1.767767 for t >= 2 ; rows 0-1 have no active book -> flat.
    # Two perfectly correlated books at target vol combine to target vol: 1.767767 * 0.0565685 = 0.10.
    panel = alt_panel()
    books = {"one": const_w(panel, 1.0, 0.0), "half": const_w(panel, 0.5, 0.0)}
    combo = P.equal_risk_combo(books, panel, vol_window=2, target=0.10)
    assert list(combo.columns) == ["A", "B"] and combo.index.equals(panel.prices.index)
    close(combo["A"], [0, 0] + [0.10 / (0.04 / S2 * 2)] * 10)
    close(combo["A"].iloc[2:], [1.767767] * 10, atol=1e-6)
    close(combo["B"], [0] * 12)
    # an inactive (always flat) book is not counted in the average
    books["dead"] = const_w(panel, 0.0, 0.0)
    close(P.equal_risk_combo(books, panel, vol_window=2, target=0.10), combo)
    # a sequence works like a mapping; positional (vol_window, target) as in the contract
    close(P.equal_risk_combo(list(books.values()), panel, 2, 0.10), combo)
    with pytest.raises(Refused):
        P.equal_risk_combo({}, panel)


def test_equal_risk_combo_averages_over_the_books_active_at_each_print():
    # book "late" only starts trading at row 6. Until its volatility exists (row 8) the combo is book "one" alone.
    #   one: scale 1.767767 from t=2.  late: w_A = 1 from row 6 -> b = 0 until t=7 (b7 = w6*r7 = +.02), b8 = -.02
    #   sigma_late: t=7: (0, .02) -> 0.0282843 -> scale 3.535534 ; t>=8: 0.0565685 -> 1.767767
    #   combo_A: t=2..6: 1.767767*1 / 1 = 1.767767 (late inactive) ; t=7: (1.767767 + 3.535534)/2 = 2.651650 ;
    #            t>=8: (1.767767 + 1.767767)/2 = 1.767767
    panel = alt_panel()
    late = const_w(panel, 1.0, 0.0)
    late.iloc[:6, 0] = np.nan
    combo = P.equal_risk_combo({"one": const_w(panel, 1.0, 0.0), "late": late}, panel, vol_window=2, target=0.10)
    close(combo["A"], [0, 0, 1.767767, 1.767767, 1.767767, 1.767767, 1.767767 / 2 * 2, 2.651650, 1.767767, 1.767767,
                       1.767767, 1.767767], atol=1e-6)


def test_ensemble_known_answer():
    # Family FA = {a: long A}, family FB = {b: long B}. ppy 4, vol_window 2, target 0.10.
    # Level 1: a -> 1.767767 on A (t>=2) ; b: sigma = 0.02/sqrt2*2 = 0.0282843 -> 3.535534 on B (t>=2).
    # Level 2: each family book earns +-0.0353553 per print from t=3 (weights exist from t=2):
    #   t=2: window (0, 0) -> sigma 0 -> inactive ; t=3: (0, .0353553) -> 0.025*2 = 0.05 -> scale 2 ;
    #   t>=4: (+-.0353553) -> 0.10 -> scale 1
    # Ensemble: t<3 flat ; t=3: (2*a + 2*b)/2 = a + b = [1.767767, 3.535534] ; t>=4: (a + b)/2 = [0.883883, 1.767767]
    panel = alt_panel()
    books = {"a": const_w(panel, 1.0, 0.0), "b": const_w(panel, 0.0, 1.0)}
    ens = P.ensemble(books, {"a": "FA", "b": "FB"}, panel, vol_window=2, target=0.10)
    close(ens.iloc[:3], np.zeros((3, 2)))
    close(ens.iloc[3], [1.767767, 3.535534], atol=1e-6)
    close(ens.iloc[4:], np.tile([0.883883, 1.767767], (8, 1)), atol=1e-6)
    # definition: equal risk inside the family, then across families
    fam = {"FA": P.equal_risk_combo({"a": books["a"]}, panel, 2, 0.10), "FB": P.equal_risk_combo({"b": books["b"]}, panel, 2, 0.10)}
    close(ens, P.equal_risk_combo(fam, panel, 2, 0.10))
    with pytest.raises(Refused, match="family_of"):
        P.ensemble(books, {"a": "FA"}, panel)
    with pytest.raises(Refused):
        P.ensemble({}, {}, panel)


def test_ensemble_gives_each_family_the_same_weight_whatever_its_size():
    rng = np.random.default_rng(3)
    panel, w = random_inputs(3, T=300, N=4)
    a = w
    b = pd.DataFrame(rng.normal(0, 0.3, w.shape), index=w.index, columns=w.columns)
    small = P.ensemble({"a1": a, "b1": b}, {"a1": "FA", "b1": "FB"}, panel, vol_window=20)
    big = P.ensemble({"a1": a, "a2": a.copy(), "a3": a.copy(), "b1": b}, {"a1": "FA", "a2": "FA", "a3": "FA", "b1": "FB"},
                     panel, vol_window=20)
    close(big, small, atol=1e-10)
    # ...whereas a flat equal-risk combo of the four rules would triple family FA's weight
    flat = P.equal_risk_combo({"a1": a, "a2": a, "a3": a, "b1": b}, panel, vol_window=20)
    assert not np.allclose(flat.to_numpy(), small.to_numpy(), atol=1e-6)


def test_vol_target_known_answer_and_gross_cap():
    # w_A = 1: scale 1.767767 from t=2 -> gross 1.767767. max_gross 2 does not bind ; max_gross 1.5 caps it at 1.5.
    panel = alt_panel()
    w = const_w(panel, 1.0, 0.0)
    free = P.vol_target(w, panel, 0.10, vol_window=2, max_gross=2.0)
    close(free["A"], [0, 0] + [1.767767] * 10, atol=1e-6)
    capped = P.vol_target(w, panel, 0.10, vol_window=2, max_gross=1.5)
    close(capped["A"], [0, 0] + [1.5] * 10)
    # the cap scales every position pro rata: w = (1, -1) -> paper returns +-0.01 -> sigma 0.0282843 -> scale 3.535534
    #   -> (3.535534, -3.535534), gross 7.071068 -> capped to gross 3: (1.5, -1.5)
    ls = P.vol_target(const_w(panel, 1.0, -1.0), panel, target=0.10, vol_window=2, max_gross=3.0)
    close(ls.iloc[2:], np.tile([1.5, -1.5], (10, 1)))
    with pytest.raises(TypeError):
        P.vol_target(w, panel, 0.10, vol_window=2)                       # max_gross is required
    with pytest.raises(Refused, match="max_gross"):
        P.vol_target(w, panel, 0.10, vol_window=2, max_gross=0.0)
    with pytest.raises(Refused, match="target"):
        P.vol_target(w, panel, -0.1, vol_window=2, max_gross=1.0)


def test_vol_target_delivers_roughly_the_target_through_the_engine():
    """Sanity, not a known answer: on iid returns the realised volatility of the scaled book is near the target."""
    panel, w = random_inputs(11, T=2500, N=6, vol=0.012)
    scaled = P.vol_target(w, panel, 0.10, vol_window=60, max_gross=50.0)
    res = backtest(panel, scaled, lag=1, cost_bp_side=0.0, missing_return="zero")   # i2 lists late
    realised = res.net.iloc[100:].std(ddof=1) * math.sqrt(252)
    assert realised == pytest.approx(0.10, rel=0.15)


# --------------------------------------------------------------------------------------------------
# apply_buffer
# --------------------------------------------------------------------------------------------------
def test_apply_buffer_hand_worked_example():
    # band = 10 % of the current target. Column X:
    #   t0 target 1.00: band [0.900, 1.100], h=0     -> 0.900  (enter at the near edge)
    #   t1 target 1.05: band [0.945, 1.155], h=0.900 -> 0.945
    #   t2 target 1.20: band [1.080, 1.320]          -> 1.080
    #   t3 target 0.50: band [0.450, 0.550], h=1.080 -> 0.550  (trade DOWN to the upper edge)
    #   t4 target 0.00: band [0, 0]                  -> 0.000  (a zero target closes in full)
    #   t5 target -1.0: band [-1.100, -0.900]        -> -0.900 (sign flip: near edge of the new band)
    #   t6 target -1.0:                              -> -0.900 (inside: no trade)
    #   t7 target -0.95: band [-1.045, -0.855]       -> -0.900 (inside: no trade)
    # Column Y:
    #   0.20 -> [0.18, 0.22] -> 0.18 ; 0.20 -> 0.18 ; 0.21 -> [0.189, 0.231] -> 0.189 ; 0.25 -> [0.225, 0.275] -> 0.225 ;
    #   0.25 -> 0.225 ; 0.10 -> [0.09, 0.11] -> 0.11 ; NaN (no target = 0) -> 0 ; 0.10 -> 0.09
    idx = pd.date_range("2024-01-01", periods=8, freq="D", tz="UTC")
    w = pd.DataFrame({"X": [1.0, 1.05, 1.2, 0.5, 0.0, -1.0, -1.0, -0.95],
                      "Y": [0.2, 0.2, 0.21, 0.25, 0.25, 0.1, np.nan, 0.1]}, index=idx)
    h = P.apply_buffer(w, band=0.10)
    close(h["X"], [0.9, 0.945, 1.08, 0.55, 0.0, -0.9, -0.9, -0.9])
    close(h["Y"], [0.18, 0.18, 0.189, 0.225, 0.225, 0.11, 0.0, 0.09])
    # turnover: target 1+0.05+0.15+0.7+0.5+1+0+0.05 = 3.45 ; buffered 0.9+0.045+0.135+0.53+0.55+0.9 = 3.06
    assert w["X"].diff().abs().sum() + 1.0 == pytest.approx(3.45)
    assert h["X"].diff().abs().sum() + 0.9 == pytest.approx(3.06)
    close(P.apply_buffer(w, band=0.0), w.fillna(0.0))                     # no band: the target itself
    close(P.apply_buffer(w), h)                                           # default band is 0.10
    for bad in (-0.1, 1.0, float("nan"), "0.1", True):
        with pytest.raises(Refused, match="band"):
            P.apply_buffer(w, band=bad)


@pytest.mark.parametrize("seed", range(6))
def test_apply_buffer_properties(seed):
    """The buffered position is always within band*|target| of the target, and it trades less on a noisy target."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=400, freq="D", tz="UTC")
    smooth = np.cumsum(rng.normal(0, 0.02, (400, 3)), axis=0)
    w = pd.DataFrame(smooth + rng.normal(0, 0.01, (400, 3)), index=idx, columns=list("xyz"))
    h = P.apply_buffer(w, band=0.10)
    assert ((h - w).abs() <= 0.10 * w.abs() + 1e-15).all().all()
    assert h.diff().abs().sum().sum() < 0.9 * w.diff().abs().sum().sum()
    wider = P.apply_buffer(w, band=0.30)
    assert wider.diff().abs().sum().sum() < h.diff().abs().sum().sum()


# --------------------------------------------------------------------------------------------------
# long_only_cap / rebalance_on / margin_utilisation
# --------------------------------------------------------------------------------------------------
def test_long_only_cap_known_answer():
    # row 0: [0.8, -0.3, 0.6] -> [0.8, 0, 0.6], sum 1.4 > 1 -> /1.4 -> [0.571429, 0, 0.428571]
    # row 1: [0.2, 0.3, -0.1] -> [0.2, 0.3, 0], sum 0.5 <= 1 -> unchanged (cash 0.5; never scaled UP)
    # row 2: [nan, -1, -2]    -> all flat
    idx = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    w = pd.DataFrame([[0.8, -0.3, 0.6], [0.2, 0.3, -0.1], [np.nan, -1.0, -2.0]], index=idx, columns=list("abc"))
    out = P.long_only_cap(w)
    close(out, [[0.8 / 1.4, 0.0, 0.6 / 1.4], [0.2, 0.3, 0.0], [0.0, 0.0, 0.0]])
    assert out.iloc[0].sum() == pytest.approx(1.0)
    close(P.long_only_cap(w, max_gross=0.5).iloc[0], [0.8 / 2.8, 0.0, 0.6 / 2.8])
    close(P.long_only_cap(w, max_gross=2.0).iloc[0], [0.8, 0.0, 0.6])
    with pytest.raises(Refused):
        P.long_only_cap(w, max_gross=0)


def test_rebalance_on_monthly_known_answer():
    # prints: Jan 30, Jan 31, Feb 1, Feb 2, Feb 29, Mar 4 (Mar 1 is NOT a print), Mar 5
    #   rebalance rows: 0 (first row), 2 (first February print), 5 (first March print = Mar 4)
    idx = pd.DatetimeIndex(["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02", "2024-02-29", "2024-03-04",
                            "2024-03-05"], tz="UTC") + pd.Timedelta(hours=13, minutes=15)
    w = pd.DataFrame({"a": [1.0, 2, 3, 4, 5, 6, 7], "b": [-1.0, np.nan, np.nan, 0.5, 0.5, 0.25, 9.0]}, index=idx)
    out = P.rebalance_on(w, "monthly")
    close(out["a"], [1, 1, 3, 3, 3, 6, 6])
    close(out["b"], [-1, -1, 0, 0, 0, 0.25, 0.25])       # the NaN target on the February rebalance print is held as 0
    # the schedule itself: rebalance prints, and the TRADE rows one print later (a fill delay of 1)
    rows = P.rebalance_rows(idx, "monthly")
    assert rows.tolist() == [True, False, True, False, False, True, False] and rows.index.equals(idx)
    assert rows.dtype == bool and rows.name == "rebalance_monthly"
    assert P.rebalance_rows(idx, "monthly", offset=1).tolist() == [False, True, False, True, False, False, True]
    assert P.rebalance_rows(idx, "monthly", offset=2).tolist() == [False, False, True, False, True, False, False]
    assert P.rebalance_rows(idx, "monthly", offset=9).tolist() == [False] * 7
    for bad in (-1, 1.0, True):
        with pytest.raises(Refused, match="offset"):
            P.rebalance_rows(idx, "monthly", offset=bad)


def test_rebalance_on_weekly_known_answer_including_the_iso_year_boundary():
    # prints: Fri 2024-12-20 (ISO 2024-W51), Mon 12-23 (W52), Fri 12-27 (W52), Mon 12-30 (ISO 2025-W01),
    #         Thu 2025-01-02 (2025-W01), Mon 01-06 (2025-W02), Tue 01-07 (W02)
    #   rebalance rows: 0, 1, 3, 5 — and NOT row 4: the calendar year changed but the ISO week did not.
    idx = pd.DatetimeIndex(["2024-12-20", "2024-12-23", "2024-12-27", "2024-12-30", "2025-01-02", "2025-01-06",
                            "2025-01-07"], tz="UTC")
    w = pd.DataFrame({"a": [1.0, 2, 3, 4, 5, 6, 7]}, index=idx)
    close(P.rebalance_on(w, "weekly")["a"], [1, 2, 2, 4, 4, 6, 6])
    assert P.rebalance_rows(idx, "weekly").tolist() == [True, True, False, True, False, True, False]
    # crypto prints every day: the weekly rebalance is the Monday 00:00 UTC print
    daily = pd.date_range("2024-01-01", periods=15, freq="D", tz="UTC")      # 2024-01-01 is a Monday
    out = P.rebalance_on(pd.DataFrame({"a": np.arange(15.0)}, index=daily), "weekly")
    close(out["a"], [0] * 7 + [7] * 7 + [14])
    with pytest.raises(Refused, match="freq"):
        P.rebalance_on(w, "daily")
    with pytest.raises(Refused, match="tz-aware"):
        P.rebalance_on(pd.DataFrame({"a": [1.0]}, index=pd.DatetimeIndex(["2024-01-01"])), "monthly")


def test_rebalance_on_cuts_turnover_through_the_engine():
    panel, w = random_inputs(5, T=400, N=4)
    daily = backtest(panel, w, cost_bp_side=5.0, missing_return="zero")             # i2 lists late
    monthly = backtest(panel, P.rebalance_on(w, "monthly"), cost_bp_side=5.0, missing_return="zero")
    assert monthly.turnover_target.sum() < 0.2 * daily.turnover_target.sum()        # the schedule cuts TARGET changes
    # ...but the engine's default drift model restores the held target on every print and charges for it, so the
    # turnover it books for the monthly frame is larger than the target-only figure (a truly scheduled book is
    # realism.simulate_account's job)
    assert monthly.turnover.sum() > monthly.turnover_target.sum()
    held_changes = int((monthly.held.diff().abs().sum(axis=1) > 0).sum())
    n_months = len(set(zip(panel.prices.index.year, panel.prices.index.month)))    # 19 calendar months of prints
    assert n_months == 19 and 15 <= held_changes <= n_months             # one trade date per month, at most


def test_margin_utilisation_known_answer():
    # row: [0.5, -1.0, 2.0] ; classes a,b = etf (20 % margin), c = fx (5 %): 0.5*0.2 + 1.0*0.2 + 2.0*0.05 = 0.4
    idx = pd.date_range("2024-01-01", periods=2, freq="D", tz="UTC")
    w = pd.DataFrame([[0.5, -1.0, 2.0], [np.nan, 0.0, 30.0]], index=idx, columns=list("abc"))
    cls = {"a": "etf", "b": "etf", "c": "fx", "unused": "crypto"}
    out = P.margin_utilisation(w, {"etf": 0.2, "fx": 0.05}, cls)
    close(out, [0.4, 1.5])                                               # row 1: 30 * 0.05 = 1.5 > 1: cannot be carried
    assert out.name == "margin_utilisation"
    with pytest.raises(Refused, match="asset_class_of"):
        P.margin_utilisation(w, {"etf": 0.2, "fx": 0.05}, {"a": "etf", "b": "etf"})
    with pytest.raises(Refused, match="margin_rate_by_class"):
        P.margin_utilisation(w, {"etf": 0.2}, cls)
    for bad in (None, float("nan"), -0.1, "0.2", True):
        with pytest.raises(Refused, match="margin rate"):
            P.margin_utilisation(w, {"etf": 0.2, "fx": bad}, cls)


# --------------------------------------------------------------------------------------------------
# Causality: the truncation proof, function by function
# --------------------------------------------------------------------------------------------------
def random_inputs(seed: int, T: int = 260, N: int = 5, vol: float = 0.015):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-11-04 13:15", periods=T, freq="B", tz="UTC")
    cols = [f"i{j}" for j in range(N)]
    px = 100 * np.exp(np.cumsum(rng.normal(0, vol, (T, N)), axis=0))
    if N >= 3:
        px[:30, 2] = np.nan                                              # a late listing
    panel = PanelBundle("RND", pd.DataFrame(px, index=idx, columns=cols),
                        carry=pd.DataFrame(rng.normal(0, 1e-4, (T, N)), index=idx, columns=cols),
                        meta={"periods_per_year": 252})
    raw = np.cumsum(rng.normal(0, 0.05, (T, N)), axis=0)
    raw[:10] = np.nan                                                    # NaN warm-up
    raw[rng.random((T, N)) < 0.03] = np.nan
    return panel, pd.DataFrame(raw, index=idx, columns=cols)


def _functions(panel, w, w2):
    cls = {c: ("etf" if i % 2 else "fx") for i, c in enumerate(w.columns)}
    return {
        "book_returns": lambda p, a, b: P.book_returns(a, p),
        "book_vol": lambda p, a, b: P.book_vol(a, p, vol_window=20),
        "risk_scale": lambda p, a, b: P.risk_scale(a, p, vol_window=20, target=0.1),
        "equal_risk_combo": lambda p, a, b: P.equal_risk_combo({"a": a, "b": b}, p, 20, 0.1),
        "ensemble": lambda p, a, b: P.ensemble({"a": a, "b": b, "c": -a}, {"a": "F1", "b": "F2", "c": "F1"}, p, 20, 0.1),
        "vol_target": lambda p, a, b: P.vol_target(a, p, 0.1, vol_window=20, max_gross=3.0),
        "apply_buffer": lambda p, a, b: P.apply_buffer(a, 0.10),
        "long_only_cap": lambda p, a, b: P.long_only_cap(a, 1.0),
        "rebalance_monthly": lambda p, a, b: P.rebalance_on(a, "monthly"),
        "rebalance_weekly": lambda p, a, b: P.rebalance_on(a, "weekly"),
        "rebalance_rows": lambda p, a, b: P.rebalance_rows(a.index, "monthly", offset=1).astype(float)
        + 2.0 * P.rebalance_rows(a.index, "weekly").astype(float),
        "margin_utilisation": lambda p, a, b: P.margin_utilisation(a, {"etf": 0.2, "fx": 0.05}, cls),
        "primary_pipeline": lambda p, a, b: P.apply_buffer(P.vol_target(
            P.ensemble({"a": a, "b": b}, {"a": "F1", "b": "F2"}, p, 20, 0.1), p, 0.1, vol_window=20, max_gross=4.0), 0.10),
    }


@pytest.mark.parametrize("name", ["book_returns", "book_vol", "risk_scale", "equal_risk_combo", "ensemble", "vol_target",
                                  "apply_buffer", "long_only_cap", "rebalance_monthly", "rebalance_weekly",
                                  "rebalance_rows", "margin_utilisation", "primary_pipeline"])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_every_function_is_strictly_causal_by_truncation(name, seed):
    """Cut every input at row k and recompute: rows <= k must be bit-identical to the full run (NaN-aware).
    Then change every input AFTER row k (weights, prices, carry) and check the same rows again."""
    panel, w = random_inputs(seed)
    _, w2 = random_inputs(100 + seed)
    fn = _functions(panel, w, w2)[name]
    full = np.asarray(fn(panel, w, w2), dtype=float)
    idx = panel.prices.index
    for k in (25, 61, 130, 200, len(idx) - 2):
        cut = panel.window(end=idx[k])
        part = np.asarray(fn(cut, w.iloc[: k + 1], w2.iloc[: k + 1]), dtype=float)
        assert part.shape[0] == k + 1
        assert np.array_equal(part, full[: k + 1], equal_nan=True), f"{name}: truncation at row {k} changed the past"
        # a different future: same past
        rng = np.random.default_rng(1000 + k)
        px = panel.prices.copy()
        px.iloc[k + 1:] = px.iloc[k + 1:] * np.exp(rng.normal(0, 0.2, px.iloc[k + 1:].shape))
        carry = panel.carry.copy()
        carry.iloc[k + 1:] = rng.normal(0, 0.01, carry.iloc[k + 1:].shape)
        wa, wb = w.copy(), w2.copy()
        wa.iloc[k + 1:] = rng.normal(0, 2, wa.iloc[k + 1:].shape)
        wb.iloc[k + 1:] = rng.normal(0, 2, wb.iloc[k + 1:].shape)
        other = np.asarray(fn(PanelBundle("RND", px, carry=carry, meta=dict(panel.meta)), wa, wb), dtype=float)
        assert np.array_equal(other[: k + 1], full[: k + 1], equal_nan=True), f"{name}: the future at {k} leaked"
        if k == 130 and name != "rebalance_rows":                        # ...and the perturbation was not a no-op
            assert not np.array_equal(other, full, equal_nan=True), name     # (a schedule depends on the index only)


def test_outputs_are_nan_free_frames_on_the_panel_axes():
    panel, w = random_inputs(7)
    _, w2 = random_inputs(8)
    shuffled = w[list(w.columns[::-1])]                                   # columns handed over in another order
    for name, fn in _functions(panel, w, w2).items():
        out = fn(panel, w, w2)
        assert out.index.equals(panel.prices.index), name
        if isinstance(out, pd.DataFrame):
            assert list(out.columns) == list(panel.prices.columns) and not out.isna().any().any(), name
    a = P.equal_risk_combo({"x": shuffled}, panel, 20, 0.1)
    b = P.equal_risk_combo({"x": w}, panel, 20, 0.1)
    assert list(a.columns) == list(panel.prices.columns)
    close(a, b)
    bad = w.copy()
    bad.iloc[50, 0] = np.inf
    for call in (lambda: P.book_returns(bad, panel), lambda: P.apply_buffer(bad), lambda: P.long_only_cap(bad),
                 lambda: P.vol_target(bad, panel, 0.1, max_gross=2.0)):
        with pytest.raises(Refused, match="inf"):
            call()
    with pytest.raises(Refused, match="index"):
        P.book_returns(w.iloc[:-1], panel)
    with pytest.raises(Refused, match="DataFrame"):
        P.apply_buffer(w.to_numpy())
