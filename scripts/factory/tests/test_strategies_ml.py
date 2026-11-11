"""The ML rules of DESIGN_v2 §4 (builder B2) — on SMALL synthetic panels (15 GB laptop).

  * contract, truncation (50 / 75 / 90 % of rows, bit-identical) and future-scramble for the three ML
    rules on the panel of every lane (the registry declares them on FX only — conductor ruling of
    2026-11-10 — but the functions are lane-agnostic and are tested on every calendar and mask);
  * the walk-forward protocol itself, checked against an independent re-computation: which rows may
    train a model fitted at tau (label realised >= 21 prints before tau), what their labels are, when
    the first model exists, what happens when a fit is impossible;
  * a planted relation: the models must rank instruments the right way round out of sample.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
import pytest

from scripts.factory.strategies import common as C
from scripts.factory.strategies import registry as R
from scripts.factory.strategies import rules_ml
from scripts.factory.tests.test_strategies_core import assert_signal_contract, identical_prefix
from scripts.factory.tests.test_strategies_synth import (LANES, mini_panel, prices_from_returns, scramble_future,
                                                          small_lane_panel, truncate)

ML_IDS = ("ML.GBC.D2", "ML.GBC.D4", "ML.RIDGE.A1")
PAIRS = [(lane, rid) for lane in LANES for rid in ML_IDS]
PAIR_IDS = [f"{lane}:{rid}" for lane, rid in PAIRS]
#: first print of the first calendar year that starts >= 3 years (minus 7 days) after each small panel
FIRST_MODEL = {"FX": "2002-01-02", "FX-FRED": "1974-01-02", "MACRO": "2019-01-02",
               "CRYPTO-PERP": "2023-01-01", "CRYPTO-SPOT": "2021-01-01"}


@lru_cache(maxsize=None)
def full_signal(lane: str, rule_id: str) -> pd.DataFrame:
    rule = R.get(rule_id)
    return rule.fn(small_lane_panel(lane), **rule.params)


def test_registry_declares_the_three_ml_rules_on_fx_only():
    """Conductor ruling 2026-11-10: ML runs on FX only (thin and slow on the short lanes). The rule
    FUNCTIONS stay lane-agnostic and are exercised below on every panel shape (weekday and daily
    calendars, with and without a universe mask)."""
    assert [r.id for r in R.rules("FX") if r.family == "ML"] == list(ML_IDS)
    assert not R.not_applicable("FX", small_lane_panel("FX"))
    for lane in LANES:
        if lane != "FX":
            assert [r.id for r in R.rules(lane, include_disabled=True) if r.family == "ML"] == []
            assert all(lane in R.LANE_EXCLUSIONS[rid] for rid in ML_IDS)
    assert all(R.get(rid).lanes == ("FX",) and R.get(rid).enabled for rid in ML_IDS)
    assert R.get("ML.GBC.D2").params == {"model": "gbc", "max_depth": 2}
    assert R.get("ML.GBC.D4").params == {"model": "gbc", "max_depth": 4}
    assert R.get("ML.RIDGE.A1").params == {"model": "ridge"}
    assert all("FEATURE" in R.get(rid).description for rid in ML_IDS)      # funding is a feature, not the dead rule


@pytest.mark.parametrize("lane,rule_id", PAIRS, ids=PAIR_IDS)
def test_ml_rule_contract(lane, rule_id):
    panel = small_lane_panel(lane)
    sig = full_signal(lane, rule_id)
    values = assert_signal_contract(sig, panel)
    finite = np.isfinite(values)
    first_row = int(np.argmax(finite.any(axis=1)))
    # no model, hence no view, before the first refit date that has three years of panel behind it
    assert panel.prices.index[first_row].strftime("%Y-%m-%d") == FIRST_MODEL[lane]
    assert (values[finite] != 0).any()
    assert np.nanmax(np.abs(np.nansum(values, axis=1))) < 1e-9             # tercile: balanced
    assert not finite[~panel.eligible().to_numpy()].any()                  # ranks eligible instruments only
    w = C.size_positions(sig, panel, R.sigma_target(lane))
    assert not w.isna().any().any() and (w.abs() <= 1.0).all().all() and (w != 0).any().any()


@pytest.mark.parametrize("lane,rule_id", PAIRS, ids=PAIR_IDS)
def test_ml_rule_truncation_is_bit_identical(lane, rule_id):
    panel, rule = small_lane_panel(lane), R.get(rule_id)
    full = full_signal(lane, rule_id)
    n = len(panel.prices)
    saw_a_view = False
    for frac in (0.50, 0.75, 0.90):
        k = int(n * frac)
        part = rule.fn(truncate(panel, k), **rule.params)                  # short panels must not raise
        assert identical_prefix(full, part, k), f"{rule_id} on {lane}: rows <= {k} changed"
        saw_a_view |= bool(np.isfinite(part.to_numpy(dtype=float)).any())
    assert saw_a_view


@pytest.mark.parametrize("lane,rule_id", PAIRS, ids=PAIR_IDS)
def test_ml_rule_future_scramble_is_bit_identical(lane, rule_id):
    panel, rule = small_lane_panel(lane), R.get(rule_id)
    full = full_signal(lane, rule_id)
    k = int(len(panel.prices) * 0.85)
    other = rule.fn(scramble_future(panel, k, seed=k), **rule.params)
    assert_signal_contract(other, panel)
    assert identical_prefix(full, other, k), f"{rule_id} on {lane}: rows <= {k} changed with the future"
    assert np.isfinite(full.iloc[:k + 1].to_numpy(dtype=float)).any()


# --------------------------------------------------------------------------------------------------
# features
# --------------------------------------------------------------------------------------------------
def test_ml_features_are_the_documented_causal_blocks():
    panel = small_lane_panel("FX")
    feats = rules_ml.ml_features(panel)
    assert tuple(feats) == rules_ml.FEATURES == ("ret_5", "ret_21", "ret_63", "ret_126", "ret_252",
                                                 "carry", "value_z", "vol")
    x = C.excess_index(panel)
    for lb in (5, 21, 63, 126, 252):
        pd.testing.assert_frame_equal(feats[f"ret_{lb}"], x / x.shift(lb) - 1.0)
    rates = panel.aux["rates"]
    pd.testing.assert_frame_equal(feats["carry"], rates[list(panel.prices.columns)].sub(rates["USD"], axis=0))
    pd.testing.assert_frame_equal(feats["vol"], C.vol_estimate(panel))
    # value z: trailing 756-print window, available from the 252nd print, clipped +-2 then halved
    logp = np.log(panel.prices["EUR"].to_numpy())
    vz = feats["value_z"]["EUR"].to_numpy()
    assert np.isnan(vz[:251]).all() and np.isfinite(vz[251:]).all()
    for t in (251, 600, 755, 756, 1100):
        w = logp[max(0, t - 755):t + 1]
        z = (logp[t] - w.mean()) / w.std(ddof=1)
        assert vz[t] == pytest.approx(max(-2.0, min(2.0, z)) / 2.0, rel=1e-8, abs=1e-12)
    for name, frame in feats.items():
        part = rules_ml.ml_features(truncate(panel, 800))[name]
        assert np.array_equal(part.to_numpy(), frame.iloc[:801].to_numpy(), equal_nan=True), name


# --------------------------------------------------------------------------------------------------
# the walk-forward protocol, re-derived independently
# --------------------------------------------------------------------------------------------------
def _expected_training_sets(panel, horizon=21, purge=21, min_rows=1000, years=3.0, tol_days=7):
    """(tau, feature matrix, labels) per valid refit, by explicit loops over rows and instruments."""
    feats = rules_ml.ml_features(panel)
    arrays = [feats[name].to_numpy() for name in rules_ml.FEATURES]
    x = C.excess_index(panel).to_numpy()
    eligible = panel.eligible().to_numpy()
    index = panel.prices.index
    dates = index.tz_convert("UTC").tz_localize(None).normalize()
    out = []
    for tau in range(1, len(index)):
        if dates[tau].year == dates[tau - 1].year:
            continue                                                    # not the first print of a year
        if (dates[tau] - dates[0]).days < years * 365.25 - tol_days:
            continue
        rows, labels = [], []
        for s in range(0, tau - purge - horizon + 1):                   # label realised at s + horizon <= tau - purge
            for i in range(x.shape[1]):
                f = [a[s, i] for a in arrays]
                label = x[s + horizon, i] / x[s, i] - 1.0               # the FORWARD return of row s
                if eligible[s, i] and np.isfinite(f).all() and np.isfinite(label) and max(map(abs, f + [label])) < 1e12:
                    rows.append(f)
                    labels.append(label)
        if len(rows) >= min_rows:
            out.append((tau, np.array(rows), np.array(labels)))
    return out


@pytest.mark.parametrize("lane", ["MACRO", "CRYPTO-PERP"])
def test_training_rows_and_labels_match_an_independent_reconstruction(lane, monkeypatch):
    panel = small_lane_panel(lane)
    seen = []
    real_fit = rules_ml._fit_ridge

    def spy(x_train, y_train, *, alpha):
        seen.append((x_train.copy(), y_train.copy()))
        return real_fit(x_train, y_train, alpha=alpha)

    monkeypatch.setattr(rules_ml, "_fit_ridge", spy)
    scores = rules_ml.ml_scores(panel, "ridge")
    expected = _expected_training_sets(panel)
    assert len(seen) == len(expected) >= 1
    for (x_got, y_got), (tau, x_exp, y_exp) in zip(seen, expected):
        assert x_got.shape == x_exp.shape and x_got.shape[0] >= 1000
        np.testing.assert_array_equal(x_got, x_exp)                    # same rows, same order
        np.testing.assert_allclose(y_got, y_exp, rtol=1e-12, atol=1e-15)
    # the purge: the newest label a model may see was realised 21 prints before its refit date, and the
    # first scored row is the refit date itself
    first_tau = expected[0][0]
    finite_rows = np.flatnonzero(np.isfinite(scores.to_numpy()).any(axis=1))
    assert finite_rows[0] == first_tau
    x_index = C.excess_index(panel).to_numpy()
    newest_label = np.nanmax(x_index[first_tau - 21] / x_index[first_tau - 42] - 1.0)
    assert np.isfinite(newest_label) and np.nanmax(expected[0][2]) >= -1.0


def test_a_change_inside_the_purge_zone_cannot_reach_the_model():
    """Rows tau-41 .. tau-1 are never feature rows of the model fitted at tau, and returns realised
    after tau-21 are never labels: perturb the prices of exactly that last stretch and the fitted
    coefficients must not move (the SCORES do move, because the features of the scored rows changed)."""
    panel = small_lane_panel("MACRO")
    dates = panel.prices.index
    tau = int(np.flatnonzero((dates.year[1:] != dates.year[:-1]))[2] + 1)        # first print of 2019
    assert dates[tau].strftime("%Y-%m-%d") == "2019-01-02"
    fits = {}

    def run(p, key):
        from sklearn.linear_model import Ridge
        real = Ridge.fit

        def fit(self, x, y, *a, **kw):
            out = real(self, x, y, *a, **kw)
            fits.setdefault(key, []).append((x.shape[0], np.array(self.coef_), float(self.intercept_)))
            return out

        Ridge.fit = fit
        try:
            return rules_ml.ml_scores(p, "ridge")
        finally:
            Ridge.fit = real

    base = run(panel, "base")
    bumped_prices = panel.prices.copy()
    bumped_prices.iloc[tau - 20:tau] = bumped_prices.iloc[tau - 20:tau] * 1.5    # rows tau-20 .. tau-1
    from scripts.factory.panel import PanelBundle
    bumped = PanelBundle(lane=panel.lane, prices=bumped_prices, carry=panel.carry, aux=panel.aux,
                         tbill=panel.tbill, meta=dict(panel.meta))
    other = run(bumped, "bumped")
    n0, coef0, b0 = fits["base"][0]
    n1, coef1, b1 = fits["bumped"][0]
    assert n0 == n1 and np.array_equal(coef0, coef1) and b0 == b1                # the 2019 model is untouched
    assert not np.array_equal(base.iloc[tau:tau + 30].to_numpy(), other.iloc[tau:tau + 30].to_numpy(), equal_nan=True)
    # a change ONE print earlier (row tau-21 is the newest label row) does reach it
    bumped_prices = panel.prices.copy()
    bumped_prices.iloc[tau - 21:tau] = bumped_prices.iloc[tau - 21:tau] * 1.5
    run(PanelBundle(lane=panel.lane, prices=bumped_prices, carry=panel.carry, aux=panel.aux, tbill=panel.tbill,
                    meta=dict(panel.meta)), "edge")
    assert not np.array_equal(fits["edge"][0][1], coef0)


def test_no_model_without_three_years_and_no_exception_on_short_panels():
    panel = small_lane_panel("MACRO")
    for k in (0, 5, 60, 300, 750):
        short = truncate(panel, k)
        for rid in ML_IDS:
            rule = R.get(rid)
            out = rule.fn(short, **rule.params)
            assert out.shape == short.prices.shape and out.isna().all().all()
    # MACRO starts 2016-01-04: the first print of 2019 is 2019-01-02, two days short of three calendar
    # years — the documented 7-day tolerance admits it; a zero tolerance pushes the first model to 2020
    strict = rules_ml.ml_scores(panel, "ridge", history_tolerance_days=0)
    first = panel.prices.index[np.flatnonzero(strict.notna().any(axis=1).to_numpy())[0]]
    assert first.strftime("%Y-%m-%d") == "2020-01-02"


def test_guards_too_few_rows_and_single_class():
    panel = small_lane_panel("MACRO")
    assert rules_ml.ml_scores(panel, "ridge", min_train_rows=10 ** 9).isna().all().all()
    # every 21-print excess return positive -> the classifier has one class -> no model, no view;
    # the regression is unaffected
    n = 1100
    idx = small_lane_panel("MACRO").prices.index[:n]
    rising = {f"I{i}": list(100.0 * (1.0 + 0.0005 * (i + 1)) ** np.arange(n)) for i in range(6)}
    p = mini_panel(rising, carry={k: [0.0] * n for k in rising}, index=idx)
    assert rules_ml.ml_scores(p, "gbc", 2).isna().all().all()
    assert rules_ml.ml_xs(p, "gbc", 2).isna().all().all()
    assert rules_ml.ml_scores(p, "ridge").notna().any().any()
    with pytest.raises(ValueError):
        rules_ml.ml_scores(p, "forest")
    with pytest.raises(ValueError):
        rules_ml.ml_scores(p, "gbc")                                             # depth missing


def test_ml_needs_a_carry_input():
    panel = small_lane_panel("MACRO")
    bare = mini_panel(panel.prices, index=panel.prices.index)
    for rid in ML_IDS:
        rule = R.get(rid)
        assert R.missing_requirements(rule, bare) == ("aux:rates|carry",)
        with pytest.raises(C.NotApplicable):
            rule.signal(bare)


# --------------------------------------------------------------------------------------------------
# a planted relation
# --------------------------------------------------------------------------------------------------
@lru_cache(maxsize=None)
def planted_panel():
    """Nine instruments with constant, DIFFERENT drifts (-0.16 % .. +0.16 % a print) and small noise:
    past returns predict future returns, in the same direction."""
    rng = np.random.default_rng(77)
    n, m = 1150, 9
    idx = small_lane_panel("MACRO").prices.index[:n]
    drift = (np.arange(m) - 4) * 0.0004
    rets = drift + rng.normal(0.0, 0.004, (n, m))
    prices = {f"I{i}": prices_from_returns([0.0] + list(rets[1:, i])) for i in range(m)}
    return mini_panel(prices, carry={k: [0.0] * n for k in prices}, index=idx)


@pytest.mark.parametrize("model,depth,floor", [("ridge", None, 0.6), ("gbc", 2, 0.4), ("gbc", 4, 0.4)])
def test_models_rank_a_planted_relation_the_right_way_round(model, depth, floor):
    panel = planted_panel()
    sig = rules_ml.ml_xs(panel, model, depth)
    live = sig.dropna(how="all")
    assert len(live) > 250
    mean = live.mean()
    low, high = [f"I{i}" for i in range(3)], [f"I{i}" for i in range(6, 9)]
    assert mean[high].min() > floor and mean[low].max() < -floor                 # long the drifters, short the decliners
    assert abs(mean["I4"]) < 0.5
    # out of sample: what the long leg earned next minus what the short leg earned next is positive
    fwd = C.excess_returns(panel).shift(-1)                                      # evaluation only, not a rule
    spread = (fwd.where(sig == 1.0).mean(axis=1) - fwd.where(sig == -1.0).mean(axis=1)).dropna()
    assert spread.mean() > 0.001


def test_scores_are_deterministic_and_row_independent():
    panel = planted_panel()
    a = rules_ml.ml_scores(panel, "ridge")
    pd.testing.assert_frame_equal(a, rules_ml.ml_scores(panel, "ridge"))
    g = rules_ml.ml_scores(panel, "gbc", 2)
    pd.testing.assert_frame_equal(g, rules_ml.ml_scores(panel, "gbc", 2))
    assert g.min().min() >= 0.0 and g.max().max() <= 1.0                         # probabilities
    rng = np.random.default_rng(0)
    x, y = rng.normal(size=(500, 8)), rng.normal(size=500)
    scorer = rules_ml._fit_ridge(x, y, alpha=1.0)
    rows = rng.normal(size=(40, 8))
    np.testing.assert_array_equal(scorer(rows)[7:19], scorer(rows[7:19]))        # a row's score ignores its batch
    np.testing.assert_array_equal(scorer(rows)[::-1], scorer(rows[::-1]))
