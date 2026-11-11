"""rules_value.py — the VALUE family of DESIGN_v2 §4.

LEVEL SERIES. VALUE is the one family that reads the RAW SPOT PRICE `panel.prices` (the nominal
exchange rate in USD per unit of foreign currency; the adjusted close on MACRO), not the excess-return
index: value is a statement about the price LEVEL, and carry must not be double counted in it.

REAL EXCHANGE RATE. q = ln P + ln CPI_ccy - ln CPI_USD, with `aux["cpi"]` (columns per currency plus
"USD", already lagged for publication delay by the data layer). q rises when the foreign currency gets
more expensive in real terms. A currency without a CPI column, or a non-positive CPI, is NaN (no view).

Sign convention: every rule is long CHEAP (low level against its own history) and short DEAR.
Each function takes `(panel, **params)` and returns raw signals in [-1, 1], NaN = no view.
"""
from __future__ import annotations

import pandas as pd

from ..panel import PanelBundle
from .common import NotApplicable, safe_log, xs_tercile, zscore_clipped


def log_real_rate(panel: PanelBundle) -> pd.DataFrame:
    """q_t = ln P_t + ln CPI_ccy,t - ln CPI_USD,t (see the module docstring). Raises `NotApplicable`
    when `aux["cpi"]` or its "USD" column is missing. Causal: elementwise in row t."""
    cpi = panel.aux.get("cpi")
    if cpi is None or "USD" not in cpi.columns:
        raise NotApplicable("real value rules need aux['cpi'] with a 'USD' column")
    cols = list(panel.prices.columns)
    rel = safe_log(cpi.reindex(columns=cols).astype(float)).sub(safe_log(cpi["USD"].astype(float)), axis=0)
    return safe_log(panel.prices) + rel


def _log_level(panel: PanelBundle, real: bool) -> pd.DataFrame:
    return log_real_rate(panel) if real else safe_log(panel.prices)


def value_xs_deviation(panel: PanelBundle, lookback: int, real: bool = False) -> pd.DataFrame:
    """VALUE.XS_NOMINAL.L<L> (real=False) / VALUE.XS_REAL.L<L> (real=True) — tercile on

        score = -( q_t - mean(q_{t-L+1..t}) ) ,   q = ln P  (nominal)  or  the log real rate,

    long the third that is cheapest against its own L-print average, short the dearest third.
    Causality: a trailing mean that includes t; per-row ranking.
    Limits: NaN until L prints exist (L = 1260 is five years of prints)."""
    q = _log_level(panel, real)
    score = -(q - q.rolling(lookback, min_periods=lookback).mean())
    return xs_tercile(score, panel.eligible())


def value_ts_z(panel: PanelBundle, lookback: int) -> pd.DataFrame:
    """VALUE.TS_Z.L<L> — time-series value: `-z_L(ln P)`, the trailing-L z-score of the log spot price
    clipped at +-2 and divided by 2, negated (long when the price is low against its own history).
    Causality: trailing mean and std that include t. Limits: NaN until L prints exist."""
    return -zscore_clipped(safe_log(panel.prices), lookback)


def value_xs_long_return(panel: PanelBundle, lookback: int = 1260, real: bool = False) -> pd.DataFrame:
    """VALUE.XS_REAL_RET.L1260 (real=True, FX) / VALUE.XS_RET.L1260 (real=False, MACRO) — tercile on
    the NEGATIVE L-print log return of the level, score = -(q_t - q_{t-L}): long the biggest five-year
    losers (Asness-Moskowitz-Pedersen's long-horizon value), short the biggest winners.
    Causality: q_t and q_{t-L}. Limits: NaN until L + 1 prints exist — on a lane whose sample starts
    less than five years before its design window ends, the rule has almost no design-window history."""
    q = _log_level(panel, real)
    return xs_tercile(-(q - q.shift(lookback)), panel.eligible())
