"""rules_ml.py — the ML family of DESIGN_v2 §4 (EXPLORATORY, all lanes): three pooled panel models,
walk-forward by construction.

FEATURES (one row per print x instrument, every one a function of rows <= t)
    ret_5, ret_21, ret_63, ret_126, ret_252   L-print return of the excess-return index X
    carry                                     annualised carry (`common.annualised_carry`)
    value_z                                   z-score of ln(spot price) against its trailing
                                              `value_window` (756) prints, available once
                                              `value_min_periods` (252) prints exist, clipped +-2, /2
    vol                                       `common.vol_estimate` (annualised, floored)
On CRYPTO-PERP the carry feature is the perp's funding. Using funding as one FEATURE of a model is not
a re-run of the funding-carry STRATEGY that is on the dead ledger and stays excluded from the grid.

TARGET  the forward `horizon` (21)-print excess return of the instrument: its SIGN for the classifier
(1 if > 0 else 0), its VALUE for the ridge regression.

WALK-FORWARD PROTOCOL
  * refit date tau = the first print of each calendar year;
  * a model is fitted only when the panel holds >= `min_history_years` (3) years before tau (with a
    `history_tolerance_days` (7) allowance, so a panel that starts on the first business day of a year
    refits on the first business day three years later);
  * training rows are the (print s, instrument) pairs with s + horizon <= tau - purge, i.e. the label
    was fully realised at least `purge` (21) prints BEFORE the refit date; the instrument must be
    eligible at s and every feature and the label must be finite (and smaller than 1e12 in absolute
    value: a number beyond that is not a return, a rate or a volatility, and the float32 tree code
    cannot hold it — such a row is treated as missing, on its own values only); expanding window;
  * a fit needs >= `min_train_rows` (1000) rows (and both classes for the classifier), else that year
    has no model and no view;
  * the model fitted at tau scores every print of that calendar year; the signal is the tercile of the
    score among the eligible instruments whose features are complete.

CAUSALITY BY CONSTRUCTION. No forward shift exists in this module: the label of feature row s is read
as the BACKWARD-looking realised return stored at row s + horizon (`X_{s+h} / X_s - 1`), and only rows
s + horizon <= tau - purge are ever paired. A prediction at t >= tau uses features at t and a model
that saw nothing after tau - purge. The truncation test in `tests/test_strategies_ml.py` checks it.

MODELS (scikit-learn, fixed seeds)
  ML.GBC.D2 / ML.GBC.D4  GradientBoostingClassifier(max_depth 2 / 4, n_estimators 100,
                         learning_rate 0.05, subsample 0.8, random_state 0); score = P(up).
  ML.RIDGE.A1            Ridge(alpha 1.0) on features standardised with the TRAINING rows' mean and
                         std; score = predicted return. With 10^4-10^5 pooled rows alpha = 1 is
                         numerically ordinary least squares.

LIMITS, stated plainly. Rows are pooled across instruments with raw (not cross-sectionally ranked)
features and 21-print labels that overlap 20/21 with their neighbours: the effective sample is about
1/21 of the row count, and neither model knows it. The first model needs three years of panel, so on a
short lane the design window contains only one to three years of predictions.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from ..panel import PanelBundle
from .common import (annualised_carry, excess_index, first_print_of_period, lookback_return, safe_log,
                     vol_estimate, xs_tercile, zscore_clipped, utc_dates)

FEATURES: Tuple[str, ...] = ("ret_5", "ret_21", "ret_63", "ret_126", "ret_252", "carry", "value_z", "vol")
RETURN_LOOKBACKS: Tuple[int, ...] = (5, 21, 63, 126, 252)
#: a feature or label at or beyond this magnitude is treated as missing (see the module docstring)
MAX_ABS_VALUE = 1e12


def _usable(a: np.ndarray) -> np.ndarray:
    """Finite and of a magnitude a model can hold; decided cell by cell (no whole-frame statistic)."""
    return np.isfinite(a) & (np.abs(a) < MAX_ABS_VALUE)


def ml_features(panel: PanelBundle, *, value_window: int = 756,
                value_min_periods: int = 252) -> Dict[str, pd.DataFrame]:
    """The eight feature frames of the ML rules, keyed by `FEATURES` (see the module docstring).
    Causal: each is built from `common` blocks that use rows <= t only."""
    x = excess_index(panel)
    feats = {f"ret_{lb}": lookback_return(x, lb) for lb in RETURN_LOOKBACKS}
    feats["carry"] = annualised_carry(panel)
    feats["value_z"] = zscore_clipped(safe_log(panel.prices), value_window, value_min_periods)
    feats["vol"] = vol_estimate(panel)
    return feats


def _fit_gbc(x_train: np.ndarray, y_train: np.ndarray, *, max_depth: int, n_estimators: int,
             learning_rate: float, subsample: float, random_state: int):
    """Fit the classifier on sign(y); returns a scorer rows -> P(up), or None if one class is absent."""
    from sklearn.ensemble import GradientBoostingClassifier

    up = (y_train > 0).astype(int)
    if up.min() == up.max():
        return None
    model = GradientBoostingClassifier(max_depth=max_depth, n_estimators=n_estimators,
                                       learning_rate=learning_rate, subsample=subsample,
                                       random_state=random_state)
    model.fit(x_train, up)
    return lambda rows: model.predict_proba(rows)[:, 1]


def _fit_ridge(x_train: np.ndarray, y_train: np.ndarray, *, alpha: float):
    """Fit Ridge(alpha) on features standardised with the training mean / std; returns a scorer.
    The prediction is evaluated row by row (elementwise product, then a row sum), so the score of a row
    does not depend on which other rows are scored with it."""
    from sklearn.linear_model import Ridge

    mu = x_train.mean(axis=0)
    sd = x_train.std(axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    model = Ridge(alpha=alpha)
    model.fit((x_train - mu) / sd, y_train)
    coef, intercept = np.asarray(model.coef_, dtype=float), float(model.intercept_)
    return lambda rows: intercept + (((rows - mu) / sd) * coef).sum(axis=1)


def ml_scores(panel: PanelBundle, model: str, max_depth: Optional[int] = None, *, horizon: int = 21,
              purge: int = 21, min_history_years: float = 3.0, history_tolerance_days: int = 7,
              min_train_rows: int = 1000, value_window: int = 756, value_min_periods: int = 252,
              n_estimators: int = 100, learning_rate: float = 0.05, subsample: float = 0.8,
              alpha: float = 1.0, random_state: int = 0) -> pd.DataFrame:
    """Walk-forward model scores (module docstring): P(up) for `model="gbc"`, the predicted
    `horizon`-print excess return for `model="ridge"`. NaN where there is no model yet, where a feature
    is missing or where the instrument is not eligible. Never raises on a short panel: too little
    history simply means no view."""
    if model not in ("gbc", "ridge"):
        raise ValueError("model must be 'gbc' or 'ridge'")
    if model == "gbc" and max_depth is None:
        raise ValueError("the gradient-boosting classifier needs max_depth")
    if horizon < 1 or purge < 0:
        raise ValueError("need horizon >= 1 and purge >= 0")
    index, cols = panel.prices.index, panel.prices.columns
    n_rows = len(index)
    feats = ml_features(panel, value_window=value_window, value_min_periods=value_min_periods)
    f = np.stack([feats[name].to_numpy(dtype=float) for name in FEATURES], axis=2)
    realised = lookback_return(excess_index(panel), horizon).to_numpy(dtype=float)
    complete = _usable(f).all(axis=2) & panel.eligible().to_numpy(dtype=bool)
    out = np.full((n_rows, len(cols)), np.nan)
    if n_rows == 0:
        return pd.DataFrame(out, index=index, columns=cols)

    dates = utc_dates(index)
    refits = np.flatnonzero(first_print_of_period(index, "Y").to_numpy())
    need_days = min_history_years * 365.25 - history_tolerance_days
    for j, tau in enumerate(refits):
        if (dates[tau] - dates[0]).days < need_days:
            continue
        last = tau - purge - horizon                    # last feature row whose label is old enough
        if last < 0:
            continue
        labels = realised[horizon:last + 1 + horizon]   # label of feature row s sits at row s + horizon
        use = complete[:last + 1] & _usable(labels)
        if int(use.sum()) < min_train_rows:
            continue
        x_train, y_train = f[:last + 1][use], labels[use]
        if model == "gbc":
            scorer = _fit_gbc(x_train, y_train, max_depth=int(max_depth), n_estimators=n_estimators,
                              learning_rate=learning_rate, subsample=subsample, random_state=random_state)
        else:
            scorer = _fit_ridge(x_train, y_train, alpha=alpha)
        if scorer is None:
            continue
        end = refits[j + 1] if j + 1 < len(refits) else n_rows
        block = complete[tau:end]
        if block.any():
            scores = np.full(block.shape, np.nan)
            scores[block] = scorer(f[tau:end][block])
            out[tau:end] = scores
    return pd.DataFrame(out, index=index, columns=cols)


def ml_xs(panel: PanelBundle, model: str, max_depth: Optional[int] = None, **kwargs) -> pd.DataFrame:
    """ML.GBC.D2 / ML.GBC.D4 / ML.RIDGE.A1 — tercile on the walk-forward model score: long the third
    with the highest predicted forward 21-print excess return (ridge) or probability of a positive one
    (classifier), short the lowest third. Protocol, causality argument and limits: module docstring;
    keyword arguments are those of `ml_scores`."""
    return xs_tercile(ml_scores(panel, model, max_depth, **kwargs), panel.eligible())
