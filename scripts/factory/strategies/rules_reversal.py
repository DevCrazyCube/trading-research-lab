"""rules_reversal.py — the REVERSAL family of DESIGN_v2 §4 (EXPLORATORY, all lanes).

LEVEL SERIES. Returns, RSI and Bollinger bands are computed on the causal EXCESS-RETURN INDEX X
(`common.excess_index`), not on the spot price. Every rule is CONTRARIAN: long what fell, short what
rose. Returns are measured in units of the instrument's own volatility (`common.vol_scaled_return`),
in the time-series rule and — by conductor ruling of 2026-11-10 — in the cross-sectional rule too.
Each function takes `(panel, **params)` and returns raw signals in [-1, 1], NaN = no view.
"""
from __future__ import annotations

import pandas as pd

from ..panel import PanelBundle
from .common import excess_index, rsi, vol_scaled_return, xs_tercile


def reversal_xs(panel: PanelBundle, lookback: int) -> pd.DataFrame:
    """REVERSAL.XS_TERCILE.L<L> — tercile on the NEGATIVE vol-scaled L-print excess return,

        score = -( X_t / X_{t-L} - 1 ) / ( sigma_daily * sqrt(L) )      (`common.vol_scaled_return`)

    long the third that fell most IN UNITS OF ITS OWN VOLATILITY, short the third that rose most.
    The scaling (conductor ruling of 2026-11-10) keeps a mixed cross-section from being a volatility
    sort: a 2 % fall of a bond fund outranks a 3 % fall of a commodity fund.
    Causality: X_t, X_{t-L}, a trailing volatility, per-row ranking.
    Limits: NaN until L prints and the volatility estimate (40 returns) exist."""
    return xs_tercile(-vol_scaled_return(panel, lookback), panel.eligible())


def reversal_ts_z(panel: PanelBundle, lookback: int) -> pd.DataFrame:
    """REVERSAL.TS_Z.L<L> — `-clip(ret_L / (sigma_daily * sqrt(L)), +-2) / 2`: the negative of the
    vol-standardised L-print excess return (the exact mirror of TREND.TSMOM_Z at a short horizon).
    "z" is the return in units of its own L-print standard deviation, NOT the trailing-window z_L of §4
    (a z-score of a 5-print return over 5 overlapping observations would be meaningless).
    Causality: X_t, X_{t-L} and a trailing volatility. Limits: NaN until both exist."""
    return -(vol_scaled_return(panel, lookback).clip(-2.0, 2.0) / 2.0)


def _band_signal(level: pd.DataFrame, low: pd.DataFrame | float, high: pd.DataFrame | float,
                 defined: pd.DataFrame) -> pd.DataFrame:
    """+1 where level < low, -1 where level > high, 0 between; NaN where `defined` is False."""
    out = pd.DataFrame(0.0, index=level.index, columns=level.columns)
    out = out.mask(level < low, 1.0).mask(level > high, -1.0)
    return out.where(defined)


def rsi_contrarian(panel: PanelBundle, n: int, low: float, high: float) -> pd.DataFrame:
    """REVERSAL.RSI.<n>_<low>_<high> — Wilder RSI(n) of the excess-return index (`common.rsi`):
    +1 when RSI < low (oversold), -1 when RSI > high (overbought), 0 between.
    STATELESS: the position exists only on prints whose own RSI is outside the band; there is no
    "hold until the opposite band" memory (§4 names thresholds, not an exit).
    Causality: RSI is a forward recursion. Limits: NaN for the first n prints and on a flat window."""
    r = rsi(excess_index(panel), n)
    return _band_signal(r, low, high, r.notna())


def bollinger_reversion(panel: PanelBundle, window: int = 20, width: float = 2.0) -> pd.DataFrame:
    """REVERSAL.BOLLINGER.<n>_<k> — Bollinger band reversion on the excess-return index:

        mid = SMA_n(X) ,  sd = population std (ddof = 0) of X over the same n prints   (Bollinger's own)
        +1 when X < mid - k * sd ,  -1 when X > mid + k * sd ,  0 inside the band.

    STATELESS (no "exit at the middle band" memory).
    Causality: trailing mean/std that include t. Limits: NaN until n prints exist."""
    x = excess_index(panel)
    roll = x.rolling(window, min_periods=window)
    mid, sd = roll.mean(), roll.std(ddof=0)
    return _band_signal(x, mid - width * sd, mid + width * sd, mid.notna() & sd.notna() & x.notna())
