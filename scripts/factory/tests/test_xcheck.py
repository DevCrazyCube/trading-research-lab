"""engine.py == xcheck.py (the independent naive loop engine) to 1e-10 on random panels (DESIGN_v2 §7).

Each seed draws its own panel shape, calendar (daily, business days, irregular gaps), timing convention
(lag on panel prints, or exec prices with an extra lag), cost form (scalar / dict / Series, per
instrument), hold costs, carry, NaN warm-up in the targets and — under the 'zero' policy — late
listings, delistings, interior price gaps and carry holes. Every seed is compared under BOTH turnover
models ("drift", the default, and "target").

Run:  cd /home/anont/meme && research/factory/.venv/bin/python -m pytest scripts/factory/tests/test_xcheck.py -q
"""
from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from scripts.factory import xcheck
from scripts.factory.engine import Refused, backtest
from scripts.factory.panel import PanelBundle
from scripts.factory.xcheck import NaiveRefused, naive_backtest

ATOL = 1e-10
SERIES = ("net", "gross", "price_pnl", "carry", "cost", "hold_cost", "turnover", "turnover_target", "gross_leverage")
N_RANDOM_PANELS = 160


def _cost_form(rng, cols, hi):
    """A scalar, a dict or a Series of per-instrument bp values in [0, hi]."""
    kind = int(rng.integers(0, 3))
    vals = rng.uniform(0.0, hi, len(cols))
    if rng.random() < 0.15:
        vals[int(rng.integers(0, len(cols)))] = 0.0
    if kind == 0:
        return float(vals[0])
    if kind == 1:
        return {c: float(v) for c, v in zip(cols, vals)}
    order = rng.permutation(len(cols))
    return pd.Series(vals[order], index=[cols[i] for i in order])


def draw_case(seed: int):
    rng = np.random.default_rng(10_000 + seed)
    T = int(rng.integers(20, 90))
    N = int(rng.integers(1, 7))
    start = pd.Timestamp("2019-01-01", tz="UTC") + pd.Timedelta(hours=int(rng.integers(0, 24)))
    calendar = int(rng.integers(0, 3))
    if calendar == 0:
        idx = pd.date_range(start, periods=T, freq="D")                 # every calendar day (crypto)
    elif calendar == 1:
        idx = pd.date_range(start, periods=T, freq="B")                 # business days: weekends are 3-day gaps
    else:                                                               # irregular gaps (holidays, missing prints)
        idx = pd.date_range(start, periods=3 * T, freq="D")[np.sort(rng.choice(3 * T, size=T, replace=False))]
    cols = [f"X{j}" for j in range(N)]
    policy = "zero" if rng.random() < 0.5 else "refuse"

    prices = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.03, (T, N)), axis=0))
    use_exec = rng.random() < 0.5
    exec_px = prices * np.exp(rng.normal(0, 0.006, (T, N))) if use_exec else None
    carry = None if rng.random() < 0.3 else rng.normal(0, 3e-4, (T, N))

    if policy == "zero":
        for j in range(N):
            if rng.random() < 0.35:                                   # late listing
                k = int(rng.integers(1, T // 2))
                prices[:k, j] = np.nan
                if exec_px is not None:
                    exec_px[: k + int(rng.integers(0, 2)), j] = np.nan
            if rng.random() < 0.35:                                   # delisting
                k = int(rng.integers(T // 2, T))
                prices[k:, j] = np.nan
                if exec_px is not None:
                    exec_px[max(k - int(rng.integers(0, 2)), 0):, j] = np.nan
        holes = rng.random((T, N)) < 0.03                              # interior gaps
        prices[holes] = np.nan
        if exec_px is not None:
            exec_px[rng.random((T, N)) < 0.03] = np.nan
        if carry is not None:
            carry[rng.random((T, N)) < 0.05] = np.nan

    w = rng.normal(0, 0.6, (T, N))
    w[rng.random((T, N)) < 0.25] = 0.0                                 # exact flats
    w[rng.random((T, N)) < 0.05] = np.nan                              # scattered "no view"
    w[: int(rng.integers(0, 8))] = np.nan                              # NaN warm-up
    if rng.random() < 0.3:                                             # a persistent book: few trades
        w = np.repeat(w[:: 5], 5, axis=0)[:T]

    meta = {"periods_per_year": int(rng.choice([252, 365]))}
    kwargs = {"cost_bp_side": _cost_form(rng, cols, 30.0), "missing_return": policy}
    if rng.random() < 0.7:
        kwargs["hold_cost_long_bp_year"] = _cost_form(rng, cols, 500.0)
    if rng.random() < 0.7:
        kwargs["hold_cost_short_bp_year"] = _cost_form(rng, cols, 500.0)
    if use_exec:
        meta["exec_prices_strictly_after_decision"] = True
        kwargs["exec_prices"] = pd.DataFrame(exec_px, index=idx, columns=cols)
        kwargs["extra_lag"] = int(rng.integers(0, 3))
    else:
        kwargs["lag"] = int(rng.integers(1, 4))

    panel = PanelBundle(
        "XCHK",
        pd.DataFrame(prices, index=idx, columns=cols),
        carry=None if carry is None else pd.DataFrame(carry, index=idx, columns=cols),
        meta=meta,
    )
    w_df = pd.DataFrame(w, index=idx, columns=cols)
    if rng.random() < 0.3:                                             # columns handed over in another order
        w_df = w_df[list(rng.permutation(cols))]
    return panel, w_df, kwargs


@pytest.mark.parametrize("model", ["drift", "target"])
@pytest.mark.parametrize("seed", range(N_RANDOM_PANELS))
def test_engine_equals_naive_loop_engine(seed, model):
    panel, w, kwargs = draw_case(seed)
    fast = backtest(panel, w, turnover_model=model, **kwargs)
    slow = naive_backtest(panel, w, turnover_model=model, **kwargs)
    for name in SERIES:
        a, b = getattr(fast, name), getattr(slow, name)
        assert a.index.equals(b.index)
        np.testing.assert_allclose(a.to_numpy(), b.to_numpy(), rtol=0, atol=ATOL, err_msg=f"{name} (seed {seed}, {model})")
    assert list(fast.held.columns) == list(slow.held.columns)
    assert np.array_equal(fast.held.to_numpy(), slow.held.to_numpy())
    for key in ("n_nan_w", "n_missing_return_held", "n_missing_carry_held"):
        assert fast.meta[key] == slow.meta[key], key
    assert fast.meta["shift"] == slow.meta["delay"] + 1 and fast.meta["turnover_model"] == model


def test_the_two_turnover_models_really_differ_on_the_random_panels():
    """Guard against a vacuous second half of the cross-check: on almost every panel the drift model charges a
    different turnover than the target model, and the default of both engines is "drift"."""
    differ = more = 0
    for seed in range(N_RANDOM_PANELS):
        panel, w, kwargs = draw_case(seed)
        default = backtest(panel, w, **kwargs)
        target = backtest(panel, w, turnover_model="target", **kwargs)
        assert default.meta["turnover_model"] == "drift"
        np.testing.assert_array_equal(default.turnover_target.to_numpy(), target.turnover.to_numpy())
        np.testing.assert_array_equal(default.gross.to_numpy(), target.gross.to_numpy())
        differ += not np.allclose(default.turnover.to_numpy(), target.turnover.to_numpy(), rtol=0, atol=1e-9)
        more += float(default.turnover.sum()) > float(target.turnover.sum())
        slow_default = naive_backtest(panel, w, **kwargs)
        np.testing.assert_allclose(slow_default.turnover.to_numpy(), default.turnover.to_numpy(), rtol=0, atol=ATOL)
    assert differ >= 0.95 * N_RANDOM_PANELS and more >= 0.5 * N_RANDOM_PANELS, (differ, more)


def test_the_random_panels_actually_exercise_every_feature():
    """Guard against a vacuous cross-check: count what the seeds cover."""
    seen = {"exec": 0, "lag>1": 0, "extra_lag>0": 0, "carry": 0, "no_carry": 0, "zero_policy": 0, "calendar_gaps": 0,
            "missing_return_cells": 0, "missing_carry_cells": 0, "hold_long": 0, "hold_short": 0,
            "dict_cost": 0, "series_cost": 0, "scalar_cost": 0, "nan_w": 0, "trades": 0}
    for seed in range(N_RANDOM_PANELS):
        panel, w, kw = draw_case(seed)
        res = backtest(panel, w, **kw)
        seen["exec"] += "exec_prices" in kw
        seen["calendar_gaps"] += bool((np.diff(panel.prices.index.normalize().asi8) != np.diff(panel.prices.index.normalize().asi8)[0]).any())
        seen["lag>1"] += kw.get("lag", 1) > 1
        seen["extra_lag>0"] += kw.get("extra_lag", 0) > 0
        seen["carry"] += panel.carry is not None
        seen["no_carry"] += panel.carry is None
        seen["zero_policy"] += kw["missing_return"] == "zero"
        seen["missing_return_cells"] += res.meta["n_missing_return_held"] > 0
        seen["missing_carry_cells"] += res.meta["n_missing_carry_held"] > 0
        seen["hold_long"] += float(res.hold_cost.sum()) > 0 and "hold_cost_long_bp_year" in kw
        seen["hold_short"] += "hold_cost_short_bp_year" in kw
        seen["dict_cost"] += isinstance(kw["cost_bp_side"], dict)
        seen["series_cost"] += isinstance(kw["cost_bp_side"], pd.Series)
        seen["scalar_cost"] += isinstance(kw["cost_bp_side"], float)
        seen["nan_w"] += res.meta["n_nan_w"] > 0
        seen["trades"] += float(res.turnover.sum()) > 0
    assert N_RANDOM_PANELS >= 100
    for key, count in seen.items():
        assert count >= 15, f"feature {key!r} is exercised by only {count} of {N_RANDOM_PANELS} panels"


@pytest.mark.parametrize("seed", range(12))
def test_both_engines_refuse_a_held_position_without_a_return(seed):
    rng = np.random.default_rng(50_000 + seed)
    T, N = 40, 3
    idx = pd.date_range("2020-01-01", periods=T, freq="D", tz="UTC")
    cols = ["a", "b", "c"]
    prices = 50.0 * np.exp(np.cumsum(rng.normal(0, 0.02, (T, N)), axis=0))
    prices[int(rng.integers(10, 30)), int(rng.integers(0, N))] = np.nan
    panel = PanelBundle("XCHK", pd.DataFrame(prices, index=idx, columns=cols), meta={"periods_per_year": 365})
    w = pd.DataFrame(rng.choice([-1.0, 1.0], size=(T, N)), index=idx, columns=cols)   # always invested
    with pytest.raises(Refused):
        backtest(panel, w, lag=1, cost_bp_side=5.0)
    with pytest.raises(NaiveRefused):
        naive_backtest(panel, w, lag=1, cost_bp_side=5.0)


def test_both_engines_refuse_the_same_timing_and_cost_violations():
    panel, w, kwargs = draw_case(3)
    base = {k: v for k, v in kwargs.items() if k not in ("lag", "extra_lag", "exec_prices")}
    plain = PanelBundle("XCHK", panel.prices.ffill().bfill(), meta={"periods_per_year": 252})
    w = w.fillna(0.0)[list(plain.prices.columns)]
    base["missing_return"] = "zero"
    bad_calls = [
        dict(base, lag=0),
        dict(base, lag=1, extra_lag=1),
        dict(base, exec_prices=plain.prices * 1.01),                    # no data-layer assertion in meta
        dict(base, lag=1, cost_bp_side=-1.0),
        dict(base, lag=1, cost_bp_side={"X0": 1.0} if len(plain.prices.columns) > 1 else None),
        dict(base, lag=1, hold_cost_short_bp_year=float("nan")),
        dict(base, lag=1, turnover_model="units"),
    ]
    for call in bad_calls:
        with pytest.raises(Refused):
            backtest(plain, w, **call)
        with pytest.raises(NaiveRefused):
            naive_backtest(plain, w, **call)


def test_both_engines_refuse_a_book_wiped_out_in_one_print_under_the_drift_model():
    # 6x short, the price rises 20 %: the book's price return is -120 %. "drift" has no weights to measure the next
    # trade from; "target" does not need any. On the LAST print nothing is measured from it: neither engine refuses.
    idx = pd.date_range("2024-01-01", periods=6, freq="D", tz="UTC")
    panel = PanelBundle("XCHK", pd.DataFrame({"A": [100.0, 100.0, 100.0, 120.0, 120.0, 120.0]}, index=idx),
                        meta={"periods_per_year": 365})
    w = pd.DataFrame({"A": [-6.0] * 6}, index=idx)
    with pytest.raises(Refused, match="-100 %"):
        backtest(panel, w, lag=1, cost_bp_side=5.0)
    with pytest.raises(NaiveRefused, match="100 %"):
        naive_backtest(panel, w, lag=1, cost_bp_side=5.0)
    a = backtest(panel, w, lag=1, cost_bp_side=5.0, turnover_model="target")
    b = naive_backtest(panel, w, lag=1, cost_bp_side=5.0, turnover_model="target")
    np.testing.assert_allclose(a.net.to_numpy(), b.net.to_numpy(), rtol=0, atol=1e-12)
    short = PanelBundle("XCHK", panel.prices.iloc[:4], meta={"periods_per_year": 365})      # the wipe-out is the last row
    a = backtest(short, w.iloc[:4], lag=1, cost_bp_side=5.0)
    b = naive_backtest(short, w.iloc[:4], lag=1, cost_bp_side=5.0)
    np.testing.assert_allclose(a.net.to_numpy(), b.net.to_numpy(), rtol=0, atol=1e-12)
    assert a.net.iloc[3] == pytest.approx(-1.2) and a.cost.iloc[2] == pytest.approx(6 * 0.0005)   # entry booked on row 2


def test_naive_engine_drift_known_answer():
    # The same hand-worked case as tests/test_engine.py: constant targets 60 % / 40 %, lag 1, one print with
    # A +10 % and B -5 %. After that print A stands at 0.66/1.04 and B at 0.38/1.04, so restoring 60/40 trades
    # 0.072/1.04 = 0.069231 ("drift"); the target did not change, so "target" trades nothing.
    idx = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    panel = PanelBundle("XCHK", pd.DataFrame({"A": [100.0, 100.0, 100.0, 110.0, 110.0],
                                              "B": [50.0, 50.0, 50.0, 47.5, 47.5]}, index=idx),
                        meta={"periods_per_year": 365})
    w = pd.DataFrame({"A": [0.6] * 5, "B": [0.4] * 5}, index=idx)
    drift = naive_backtest(panel, w, lag=1, cost_bp_side=10.0)
    target = naive_backtest(panel, w, lag=1, cost_bp_side=10.0, turnover_model="target")
    np.testing.assert_allclose(drift.turnover.to_numpy(), [0, 0, 1.0, 0.0, 0.072 / 1.04], rtol=0, atol=1e-12)
    np.testing.assert_allclose(drift.net.to_numpy(), [0, 0, -0.001, 0.04, -0.072 / 1.04 * 0.001], rtol=0, atol=1e-12)
    np.testing.assert_allclose(target.turnover.to_numpy(), [0, 0, 1.0, 0.0, 0.0], rtol=0, atol=1e-12)
    np.testing.assert_allclose(drift.turnover_target.to_numpy(), target.turnover.to_numpy(), rtol=0, atol=0)
    assert target.net.iloc[4] == 0.0


def test_xcheck_shares_no_code_with_the_engine():
    """Independence is the point: the naive engine must not import the fast one, nor numpy."""
    src = inspect.getsource(xcheck)
    code = src.split('"""', 2)[2]                                       # everything after the module docstring
    assert "import numpy" not in code and "from numpy" not in code
    assert "from .engine" not in code and "import engine" not in code and "from . import" not in code
    assert not hasattr(xcheck, "np") and not hasattr(xcheck, "engine")
    for needle in (".shift(", "fast_net_returns", "shift_positions"):
        assert needle not in code


def test_naive_engine_hand_worked_example():
    # Two prints of delay (lag = 2), one instrument, cost 20 bp/side, hold long 365 bp/yr at 365 prints/yr.
    #   P = [10, 11, 12.1, 12.1, 13.31]   w = [1, 1, 0, 0, 0]
    #   decision 0 is filled at print 2 and earns row 3 (0%) ; decision 1 keeps it for row 4 (+10%);
    #   decision 2 (flat) is filled at print 4 — its exit cost would be booked on row 5, outside the sample.
    #   row 3: 0 - 0.002 (entry) - 0.0001 (hold) = -0.0021 ; row 4: +0.10 - 0.0001 = 0.0999
    idx = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    panel = PanelBundle("XCHK", pd.DataFrame({"A": [10.0, 11.0, 12.1, 12.1, 13.31]}, index=idx),
                        meta={"periods_per_year": 365})
    w = pd.DataFrame({"A": [1.0, 1.0, 0.0, 0.0, 0.0]}, index=idx)
    out = naive_backtest(panel, w, lag=2, cost_bp_side=20.0, hold_cost_long_bp_year=365.0)
    np.testing.assert_allclose(out.net.to_numpy(), [0, 0, 0, -0.0021, 0.0999], rtol=0, atol=1e-12)
    assert out.held["A"].tolist() == [0, 0, 0, 1, 1]
    fast = backtest(panel, w, lag=2, cost_bp_side=20.0, hold_cost_long_bp_year=365.0)
    np.testing.assert_allclose(fast.net.to_numpy(), out.net.to_numpy(), rtol=0, atol=1e-12)
