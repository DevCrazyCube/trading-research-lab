"""rules_trend.py — the TREND family of DESIGN_v2 §4 (time-series rules, all lanes).

LEVEL SERIES. Every rule here reads the causal EXCESS-RETURN INDEX X_t = prod_{s<=t}(1 + e_s),
e = price return + carry, X = 1.0 on the instrument's first valid print (`common.excess_index`) — the
"synthetic futures price". It is NOT the raw spot price: trend on a high-carry currency, on a funded ETF
or on a perp with funding therefore sees what a holder actually earned. Where §4 writes "P" for a trend
rule, read "X"; where it writes "ret_L", read X_t / X_{t-L} - 1. All rules are scale-free in X.

Each function takes `(panel, **params)` and returns a DataFrame (panel index x instruments) of raw
signals in [-1, 1], NaN = no view. Sizing is the caller's job (`common.size_positions`).
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from ..panel import PanelBundle
from .common import (donchian_state, ewma, excess_index, lookback_return, rolling_slope_tstat, safe_log,
                     vol_scaled_return)

#: Carver's forecast scalars for EWMAC(fast, slow) (Systematic Trading, appendix B), as given in §4.
EWMAC_SCALARS = {(2, 8): 10.6, (4, 16): 7.5, (8, 32): 5.3, (16, 64): 3.75, (32, 128): 2.65, (64, 256): 1.87}
EWMAC_CAP = 20.0
EWMAC_VOL_SPAN = 36


def ewmac_forecast(x: pd.DataFrame, fast: int, slow: int, scalar: float, *, vol_span: int = EWMAC_VOL_SPAN,
                   cap: float = EWMAC_CAP, min_periods: Optional[int] = None) -> pd.DataFrame:
    """Normalised EWMAC forecast of a level frame x:

        raw_t      = (EWMA_fast(x)_t - EWMA_slow(x)_t) / sigma_t
        sigma_t    = exponentially weighted std (span `vol_span`) of the print-to-print CHANGES of x
        forecast_t = clip(scalar * raw_t, -cap, +cap) / cap                         in [-1, 1]

    EWMA / EW-std conventions: `common.ewma`, `common.ewm_std` (pandas `adjust=True`). By default each
    average is reported once it has as many observations as its span (so the signal starts after `slow`
    prints); `min_periods` overrides all three warm-ups (used by the hand-computed test).
    Causality: three exponentially weighted statistics of rows <= t.
    Limits: scale-free in x; NaN where x is NaN, where sigma is zero and during the warm-up."""
    if not 0 < fast < slow:
        raise ValueError("need 0 < fast < slow")
    mp_f, mp_s, mp_v = (fast, slow, vol_span) if min_periods is None else (min_periods,) * 3
    f = x.ewm(span=fast, adjust=True, min_periods=mp_f).mean()
    s = x.ewm(span=slow, adjust=True, min_periods=mp_s).mean()
    sigma = x.diff().ewm(span=vol_span, adjust=True, min_periods=mp_v).std()
    raw = (f - s) / sigma.where(sigma > 0)
    return ((scalar * raw).clip(-cap, cap) / cap).where(x.notna())


def ewmac(panel: PanelBundle, fast: int, slow: int, scalar: Optional[float] = None) -> pd.DataFrame:
    """TREND.EWMAC.<fast>_<slow> — Carver's EWMA crossover on the excess-return index:
    `clip(scalar * (EWMA_fast(X) - EWMA_slow(X)) / sigma_X, +-20) / 20`, sigma_X = EW std (span 36) of the
    daily changes of the same index X. `scalar` defaults to the §4 table (2/8 10.6 ... 64/256 1.87).
    Causality and limits: see `ewmac_forecast`. The index, not the spot price, is the level series."""
    if scalar is None:
        scalar = EWMAC_SCALARS[(fast, slow)]
    return ewmac_forecast(excess_index(panel), fast, slow, scalar)


def tsmom_sign(panel: PanelBundle, lookback: int) -> pd.DataFrame:
    """TREND.TSMOM_SIGN.L<L> — sign of the L-print EXCESS return: sign(X_t / X_{t-L} - 1), in {-1, 0, +1}.
    Causality: X_t and X_{t-L}. Limits: NaN until L prints of index history exist."""
    return np.sign(lookback_return(excess_index(panel), lookback))


def tsmom_z(panel: PanelBundle, lookback: int) -> pd.DataFrame:
    """TREND.TSMOM_Z.L<L> — vol-standardised L-print EXCESS return:
    `clip(ret_L / (sigma_daily * sqrt(L)), +-2) / 2`, ret_L = X_t / X_{t-L} - 1,
    sigma_daily = `common.vol_estimate` de-annualised (60-print std of excess returns, floored).
    Causality: X_t, X_{t-L} and a trailing volatility. Limits: NaN until both exist."""
    return vol_scaled_return(panel, lookback).clip(-2.0, 2.0) / 2.0


def breakout_forecast(x: pd.DataFrame, lookback: int, smooth: Optional[int] = None) -> pd.DataFrame:
    """Continuous (Carver) breakout of a level frame x:

        raw_t = 2 * (x_t - mid_t) / (max_t - min_t) ,  max/min over the L prints t-L+1..t,  mid = (max+min)/2
        signal = EWMA_span(raw) ,  span = `smooth` or max(L // 4, 1)

    raw is +1 at the top of the trailing range and -1 at the bottom, so the signal stays in [-1, 1].
    Causality: trailing extremes that include print t, then a causal EWMA.
    Limits: NaN until L prints exist (plus the EWMA warm-up of `span` values), where the range is zero,
    and on any row whose own raw value is undefined."""
    span = max(lookback // 4, 1) if smooth is None else smooth
    hi = x.rolling(lookback, min_periods=lookback).max()
    lo = x.rolling(lookback, min_periods=lookback).min()
    width = hi - lo
    raw = 2.0 * (x - (hi + lo) / 2.0) / width.where(width > 0)
    return ewma(raw, span).clip(-1.0, 1.0)


def breakout(panel: PanelBundle, lookback: int) -> pd.DataFrame:
    """TREND.BREAKOUT.L<L> — `2 * (X - mid_L) / (max_L - min_L)` smoothed by EWMA(L/4), on the
    excess-return index X. See `breakout_forecast` for the formula, causality and limits."""
    return breakout_forecast(excess_index(panel), lookback)


def sma_sign(panel: PanelBundle, window: int = 200) -> pd.DataFrame:
    """TREND.SMA_SIGN.<n> — sign(X_t - SMA_n(X)_t) on the excess-return index, in {-1, 0, +1}.
    SMA_n = mean of the n prints t-n+1..t. Causality: a trailing mean that includes t.
    Limits: NaN until n prints exist."""
    x = excess_index(panel)
    return np.sign(x - x.rolling(window, min_periods=window).mean())


def sma_cross(panel: PanelBundle, fast: int = 50, slow: int = 200) -> pd.DataFrame:
    """TREND.SMA_CROSS.<fast>_<slow> — sign(SMA_fast(X) - SMA_slow(X)) on the excess-return index.
    Causality: two trailing means. Limits: NaN until `slow` prints exist."""
    if not 0 < fast < slow:
        raise ValueError("need 0 < fast < slow")
    x = excess_index(panel)
    return np.sign(x.rolling(fast, min_periods=fast).mean() - x.rolling(slow, min_periods=slow).mean())


def donchian(panel: PanelBundle, lookback: int) -> pd.DataFrame:
    """TREND.DONCHIAN.L<L> — Donchian channel stop-and-reverse on the excess-return index: +1 after a
    close above the highest X of the previous L prints, -1 after a close below the lowest, held until
    the opposite breakout, 0 before the first one (`common.donchian_state`; no separate exit channel).
    Causality: channel of prints t-L..t-1, forward-filled state. Limits: NaN for the first L prints."""
    return donchian_state(excess_index(panel), lookback)


def linreg_slope_t(panel: PanelBundle, lookback: int) -> pd.DataFrame:
    """TREND.LINREG_T.L<L> — `clip(t / 3, +-1)`, t = OLS t-statistic of the slope of ln X on time over
    the trailing L prints (classical standard error, `common.rolling_slope_tstat`).
    Causality: one trailing window per row. Limits: NaN until L index prints exist. On a random walk the
    classical t of a level-on-time regression grows like sqrt(L) (spurious regression), so the clip
    binds on most rows and the rule is close to sign(slope) — see the B2 report."""
    t = rolling_slope_tstat(safe_log(excess_index(panel)), lookback)
    return (t / 3.0).clip(-1.0, 1.0)
