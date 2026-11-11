"""rules_misc.py — the VOL, SEASON, SKEW, XASSET and FLOW families of DESIGN_v2 §4 (all EXPLORATORY).

Inputs. VOL and SKEW are statistics of the per-print EXCESS return (price return + carry) and of the
excess-return index; the MAX rule ranks its statistic in units of the instrument's own volatility.
SEASON reads only the print calendar. XASSET reads `aux["oil"]`, FLOW reads `aux["glsr"]`; a rule whose
input is missing raises `NotApplicable` (the registry reports it as not applicable — nothing here
returns fabricated zeros). Lane differences enter only through `panel.meta` (`periods_per_year`,
`asset_class_of`) and the registry's `lanes` / `requires`.

Each function takes `(panel, **params)` and returns raw signals in [-1, 1], NaN = no view.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd

from ..panel import PanelBundle
from .common import (NotApplicable, daily_vol, excess_index, excess_returns, lookback_return, print_calendar,
                     safe_log, turn_of_month_mask, xs_tercile, zscore)


# --------------------------------------------------------------------------------------------------
# VOL
# --------------------------------------------------------------------------------------------------
def _rolling_std(panel: PanelBundle, window: int) -> pd.DataFrame:
    """Per-print std (ddof=1) of the excess return over the full trailing window, un-floored."""
    return excess_returns(panel).rolling(window, min_periods=window).std()


def vol_managed_basket(panel: PanelBundle, long_window: int = 252, short_window: int = 21) -> pd.DataFrame:
    """VOL.MANAGED_BASKET.<long>_<short> — long-only basket whose exposure scales with
    sigma_long / sigma_short (volatility-managed, Moreira-Muir style):

        s_i = clip( 0.5 * sigma_252,i / sigma_21,i , 0, 1 )            (never short)

    The factor 0.5 only maps the ratio into the signal range: s = 0.5 when recent and long-run
    volatility agree, 1 when recent volatility is half the long-run level or less. `size_positions`
    then applies the usual inverse-volatility sizing on top.
    Causality: two trailing stds. Limits: NaN until `long_window` returns exist. A long-only book earns
    the basket's own premium: judge it against the constant-exposure basket, not against zero."""
    short = _rolling_std(panel, short_window)
    ratio = _rolling_std(panel, long_window) / short.where(short > 0)
    return (0.5 * ratio).clip(0.0, 1.0)


def low_vol_xs(panel: PanelBundle, lookback: int = 252) -> pd.DataFrame:
    """VOL.XS_LOWVOL.L<L> — tercile on -sigma_L (std of the excess return over L prints): long the
    least volatile third, short the most volatile third.
    Causality: a trailing std, per-row ranking. Limits: NaN until L returns exist."""
    return xs_tercile(-_rolling_std(panel, lookback), panel.eligible())


def vol_breakout(panel: PanelBundle, short_window: int = 5, long_window: int = 60,
                 threshold: float = 1.5) -> pd.DataFrame:
    """VOL.BREAKOUT.<short>_<long> — when sigma_5 / sigma_60 > 1.5 (a volatility expansion) take the
    sign of the 5-print excess return X_t / X_{t-5} - 1; otherwise 0.
    Causality: trailing stds and a 5-print lookback. Limits: NaN until 60 returns exist; the two
    windows overlap (the last 5 prints are in both), so the ratio is bounded above by sqrt(59/4) ~ 3.8."""
    long = _rolling_std(panel, long_window)
    ratio = _rolling_std(panel, short_window) / long.where(long > 0)
    direction = np.sign(lookback_return(excess_index(panel), short_window))
    return direction.where(ratio > threshold, 0.0).where(ratio.notna() & direction.notna())


# --------------------------------------------------------------------------------------------------
# SEASON
# --------------------------------------------------------------------------------------------------
def asset_class_columns(panel: PanelBundle, asset_class: str) -> list:
    """Instruments whose `meta["asset_class_of"]` label CONTAINS `asset_class` (case-insensitive), in
    panel column order. Raises `NotApplicable` when the mapping is missing or matches nothing."""
    mapping = panel.meta.get("asset_class_of")
    if not mapping:
        raise NotApplicable("meta['asset_class_of'] is required to select an asset class")
    key = asset_class.lower()
    cols = [c for c in panel.prices.columns if key in str(mapping.get(c, "")).lower()]
    if not cols:
        raise NotApplicable(f"no instrument of this panel is labelled {asset_class!r} in meta['asset_class_of']")
    return cols


def _calendar_signal(panel: PanelBundle, on: pd.Series, direction: float,
                     asset_class: Optional[str]) -> pd.DataFrame:
    """`direction` on the prints where `on` is True, 0 on the others, for the selected instruments;
    NaN for unselected instruments and where the instrument has no price."""
    cols = list(panel.prices.columns) if asset_class is None else asset_class_columns(panel, asset_class)
    out = pd.DataFrame(np.nan, index=panel.prices.index, columns=panel.prices.columns)
    values = np.where(on.to_numpy(dtype=bool), float(direction), 0.0)
    for c in cols:
        out[c] = values
    return out.where(panel.prices.notna())


def turn_of_month(panel: PanelBundle, direction: float = 1.0, asset_class: Optional[str] = None,
                  last_n: int = 3, first_n: int = 2) -> pd.DataFrame:
    """SEASON.TOM.* — `direction` (+1 long, -1 short) on the decision prints that are among the last
    `last_n` prints of a month or the first `first_n` of the next, 0 on every other print.

    * MACRO  : asset_class="equity", direction=+1   (long equities)
    * CRYPTO : all instruments, direction=+1
    * FX     : all instruments, direction=-1 (long USD: prices are USD per unit of foreign currency)
               and direction=+1 (its negation)
    The window is `common.turn_of_month_mask` on the panel's own print calendar ('weekday' or 'daily'
    from `meta["periods_per_year"]`): the first side is exact, the last side is business-day arithmetic
    with a documented holiday error; nothing looks ahead.
    Causality: the print's own date and a running count of earlier prints.
    Limits: these are DECISION prints; with lag = 1 the engine earns the returns of days -1 .. +4. A
    long-only calendar rule on a rising asset class has a positive mean simply from being long — judge
    it against the same average exposure held every day."""
    on = turn_of_month_mask(panel.prices.index, last_n, first_n, calendar=print_calendar(panel))
    return _calendar_signal(panel, on, direction, asset_class)


def sell_in_may(panel: PanelBundle, asset_class: Optional[str] = "equity",
                months: Sequence[int] = (11, 12, 1, 2, 3, 4)) -> pd.DataFrame:
    """SEASON.SELL_IN_MAY.EQUITY — +1 on prints whose UTC month is November-April, 0 in May-October,
    for the instruments of `asset_class` (others NaN).
    Causality: the print's own date. Limits: decision prints (the engine's lag shifts the held window
    by one or two prints); one independent bet per year, so a five-year design window holds five
    winters — the rule cannot be distinguished from a constant equity exposure there."""
    month = panel.prices.index.tz_convert("UTC").month
    on = pd.Series(np.isin(month, list(months)), index=panel.prices.index)
    return _calendar_signal(panel, on, 1.0, asset_class)


# --------------------------------------------------------------------------------------------------
# SKEW
# --------------------------------------------------------------------------------------------------
def skew_xs(panel: PanelBundle, lookback: int = 126) -> pd.DataFrame:
    """SKEW.XS_LOW_MINUS_HIGH.L<L> — tercile on MINUS the sample skewness of the excess return over L
    prints: long the third with the lowest (most negative) skew, short the third with the highest.
    Causality: a trailing skewness, per-row ranking. Limits: NaN until L returns exist; skewness over
    126 prints is dominated by one or two extreme days."""
    sk = excess_returns(panel).rolling(lookback, min_periods=lookback).skew()
    return xs_tercile(-sk, panel.eligible())


def max_return_xs(panel: PanelBundle, lookback: int = 21) -> pd.DataFrame:
    """SKEW.XS_MAX.L<L> — the MAX effect (Bali-Cakici-Whitelaw): tercile on MINUS the largest single
    excess return of the last L prints IN UNITS OF THE INSTRUMENT'S OWN VOLATILITY,

        score = - max(e_{t-L+1..t}) / sigma_daily,t ,   sigma_daily = `common.daily_vol` at the row,

    short the third with the highest scaled maximum, long the third with the lowest. The scaling
    (conductor ruling of 2026-11-10) makes the score "how extreme was its best day for THIS
    instrument", so a mixed cross-section is not sorted by volatility.
    Causality: a trailing maximum and a trailing volatility, per-row ranking.
    Limits: NaN until L returns and the volatility estimate (40 returns) exist."""
    mx = excess_returns(panel).rolling(lookback, min_periods=lookback).max()
    return xs_tercile(-(mx / daily_vol(panel)), panel.eligible())


# --------------------------------------------------------------------------------------------------
# XASSET
# --------------------------------------------------------------------------------------------------
def _single_series(frame: pd.DataFrame, preferred: Sequence[str], what: str) -> pd.Series:
    for name in preferred:
        if name in frame.columns:
            return frame[name].astype(float)
    if frame.shape[1] == 1:
        return frame.iloc[:, 0].astype(float)
    raise NotApplicable(f"{what} must have one column or one named {list(preferred)}")


def oil_currencies(panel: PanelBundle, lookback: int = 63,
                   instruments: Sequence[str] = ("CAD", "NOK", "MXN")) -> pd.DataFrame:
    """XASSET.OIL_FX.L<L> — for the oil currencies present in the panel (CAD, NOK, MXN): the sign of the
    trailing L-print WTI return, sign(oil_t / oil_{t-L} - 1) (long the currency against USD when oil
    rose). Every other instrument is NaN. `aux["oil"]` is WTI spot, already lagged one day by the data
    layer (one column, or a column named "WTI" / "oil").
    Causality: oil_t and oil_{t-L} from an already-lagged frame.
    Limits: two instruments in G10 (CAD, NOK), three in G10EM — ONE oil-momentum bet expressed through two
    or three currencies, not a cross-section."""
    oil = panel.aux.get("oil")
    if oil is None:
        raise NotApplicable("XASSET oil rule needs aux['oil']")
    cols = [c for c in instruments if c in panel.prices.columns]
    if not cols:
        raise NotApplicable(f"none of {list(instruments)} is in this panel")
    series = _single_series(oil, ("WTI", "oil"), "aux['oil']")
    level = series.where(series > 0)
    direction = np.sign(level / level.shift(lookback) - 1.0)
    out = pd.DataFrame(np.nan, index=panel.prices.index, columns=panel.prices.columns)
    for c in cols:
        out[c] = direction
    return out.where(panel.prices.notna())


# --------------------------------------------------------------------------------------------------
# FLOW
# --------------------------------------------------------------------------------------------------
def glsr_fade(panel: PanelBundle, lookback: int = 7) -> pd.DataFrame:
    """FLOW.XS_GLSR_Z.L<L> — crowding fade on the global long/short ACCOUNT ratio of each perp:

        z_i = ( ln glsr_i,t - mean_L ) / std_L        (own trailing L prints, unclipped)
        tercile on -z : short the third whose accounts became unusually long, long the opposite third.

    `aux["glsr"]` has one column per instrument (ratio > 0).
    Causality: a trailing z-score, per-row ranking.
    Limits: the reference leg of the earlier programme (XS_GLSR_Z) measured z over 168 HOURLY bars and
    sorted quintiles; on a daily panel L = 7 prints is seven observations of the same seven days — a
    coarser, noisier statistic, not a replication."""
    glsr = panel.aux.get("glsr")
    if glsr is None:
        raise NotApplicable("FLOW rule needs aux['glsr']")
    z = zscore(safe_log(glsr.reindex(columns=panel.prices.columns).astype(float)), lookback)
    return xs_tercile(-z, panel.eligible())
