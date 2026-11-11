"""common.py — causal building blocks of the factory strategy library (builder B2, DESIGN_v2 §3.7).

Every function here is PURE and CAUSAL: the value it returns for row t is a function of rows <= t of
its inputs (and of the index up to t). The only operations used are `rolling`, `expanding`, `ewm`,
`shift(k >= 0)`, `cumsum`/`cumprod`, `ffill`, per-row (axis = 1) reductions and elementwise arithmetic.
There is no centred window, no negative shift, no full-sample statistic and no data-dependent guard
that looks at the whole frame. `tests/test_strategies_*.py` proves it: every rule built from these
blocks returns bit-identical rows <= k on a panel truncated at k and on a panel whose rows > k were
regenerated.

CONVENTIONS OF THE LIBRARY (stated once, used everywhere)

* EXCESS RETURN  e_t = P_t / P_{t-1} - 1 + carry_t   (`excess_returns`). NaN wherever the price return
  or the carry is unknown: an unknown financing leg is NOT replaced by zero.
* EXCESS-RETURN INDEX  X_t = prod_{s <= t} (1 + e_s), started at 1.0 on each instrument's first valid
  print (`excess_index`). This is the "synthetic futures price" — what a holder actually earned — and it
  is the level series of every TREND / XSMOM / REVERSAL rule. Only VALUE rules read the raw spot price.
* WINDOWS. A trailing-L statistic needs L observations (`min_periods = L`) unless a rule says otherwise;
  `vol_estimate` (60 prints, min 40) is the one stated exception (DESIGN §3.7).
* EWMA. `ewma(x, span)` is pandas `ewm(span=span, adjust=True)`:
      y_t = sum_{i=0..t} (1-a)^i x_{t-i} / sum_{i=0..t} (1-a)^i ,   a = 2 / (span + 1).
  The weights are normalised over the history that EXISTS at t, so the estimate is causal and is not
  anchored on the first observation (which `adjust=False` would weight (span+1)/2 times too heavily).
  It is the setting Carver's forecast scalars were calibrated with. A span-L EWMA is reported once L
  observations exist. Wilder smoothing (RSI) is the one place `adjust=False` is used, by definition.
* SIGNALS are raw s in [-1, 1]; NaN means "no view" and is sized to zero by `size_positions`.
* CROSS-SECTIONS rank the ELIGIBLE (`panel.eligible()`), finite scores of one row. Fewer than three
  ranked instruments is not a cross-section: the signal is zero. Equal scores are treated equally
  (`DEFAULT_TIES = "split"`); the column-order tie-break of the brief is `ties="order"`. A cross-section
  of RETURNS ranks them in units of each instrument's own volatility (`vol_scaled_return`).
* SIZING divides by the number of ELIGIBLE instruments of the row, not by the number with a signal
  (`size_positions`; conductor ruling of 2026-11-10, replacing the N_active of DESIGN §3.7).
* NUMERICS. Per-row reductions and rolling kernels are evaluated in an order that depends only on the
  rows <= t, so truncating or changing the future cannot move a single bit of an earlier row.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from ..panel import PanelBundle

__all__ = [
    "DEFAULT_TIES",
    "NotApplicable",
    "annualised_carry",
    "calendar_days_between_prints",
    "carry_source",
    "daily_vol",
    "donchian_state",
    "ewma",
    "ewm_std",
    "excess_index",
    "excess_returns",
    "first_print_of_period",
    "lookback_return",
    "print_calendar",
    "rolling_slope_tstat",
    "rsi",
    "safe_log",
    "size_positions",
    "turn_of_month_mask",
    "utc_dates",
    "vol_estimate",
    "vol_scaled_return",
    "xs_linear_rank",
    "xs_tercile",
    "zscore",
    "zscore_clipped",
]


#: Tie handling of `xs_tercile` for every rule of the library ("split" or "order", see `xs_tercile`).
DEFAULT_TIES = "split"


class NotApplicable(Exception):
    """A rule was asked to run on a panel that lacks one of its required inputs.

    The registry filters such rules out (`registry.rules(lane, panel)`) and reports them
    (`registry.not_applicable(lane, panel)`); a rule function that is called anyway raises this instead
    of returning fabricated zeros."""


# --------------------------------------------------------------------------------------------------
# small utilities
# --------------------------------------------------------------------------------------------------
def safe_log(x):
    """Natural log where x > 0, NaN elsewhere (never a warning, never -inf)."""
    return np.log(x.where(x > 0))


def utc_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """UTC calendar date of every print (tz-naive, midnight)."""
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError("index must be a DatetimeIndex")
    if index.tz is None:
        raise ValueError("index must be tz-aware (UTC)")
    return index.tz_convert("UTC").tz_localize(None).normalize()


def print_calendar(panel: PanelBundle) -> str:
    """'daily' for a 7-day print calendar (periods_per_year >= 300, the crypto lanes), else 'weekday'
    (Monday-Friday prints: FX fixes, exchange closes). Read from `panel.meta`, never inferred from the
    data, so it cannot depend on the future."""
    return "daily" if panel.periods_per_year >= 300 else "weekday"


def calendar_days_between_prints(index: pd.DatetimeIndex, n: int = 1) -> pd.Series:
    """Calendar days between the UTC date of print t and of print t-n (NaN for the first n rows)."""
    dates = pd.Series(utc_dates(index), index=index)
    return dates.diff(n).dt.days.astype(float)


# --------------------------------------------------------------------------------------------------
# returns, index, volatility, sizing
# --------------------------------------------------------------------------------------------------
def excess_returns(panel: PanelBundle) -> pd.DataFrame:
    """Per-print EXCESS return of a +1.0 exposure: e_t = P_t / P_{t-1} - 1 + carry_t.

    `panel.returns() + panel.carry` when a carry frame exists, else the price return. This is the return
    every volatility, rank and ML computation of the library uses.
    Causality: P_t, P_{t-1} and carry_t only.
    Limits: NaN wherever the price return OR the carry is NaN — the excess return of an instrument whose
    financing leg is unknown is unknown, and the library takes no view on it (the engine draft books a
    NaN carry as zero and counts it; the two treatments differ on purpose, see the B2 report)."""
    r = panel.returns()
    if panel.carry is not None:
        r = r + panel.carry
    return r


def excess_index(panel: PanelBundle) -> pd.DataFrame:
    """Causal excess-return index ("synthetic futures price"): X_t = prod_{s <= t} (1 + e_s).

    X = 1.0 on each instrument's first valid print (its first non-NaN price); every later print
    multiplies by (1 + e_t). Rows before the first print are NaN.
    Causality: a cumulative product, i.e. rows <= t only.
    Limits: a print whose excess return is unknown (missing price, missing carry) is NaN in the index and
    contributes NO growth: the level resumes afterwards from where it stood, so a return measured across
    such a gap treats the gap as 0 %. Rolling-window rules need a full window and therefore give no
    view while a gap is inside their window; `shift`-based returns and EWMAs straddle it. FX and MACRO
    panels are gap-free by the data contract (the engine refuses a held NaN return there). The index is
    positive as long as no single excess return is <= -100 %."""
    e = excess_returns(panel)
    has_price = panel.prices.notna()
    first_print = has_price & (has_price.cumsum() == 1)
    growth = (1.0 + e).where(e.notna(), 1.0)
    return growth.cumprod().where(e.notna() | first_print)


def lookback_return(x: pd.DataFrame, lookback: int, skip: int = 0) -> pd.DataFrame:
    """Return of the level frame x from print t-lookback to print t-skip: x_{t-skip} / x_{t-lookback} - 1.
    Causal (two non-negative shifts). NaN unless both levels exist."""
    if lookback <= skip or skip < 0:
        raise ValueError("need lookback > skip >= 0")
    end = x if skip == 0 else x.shift(skip)
    return end / x.shift(lookback) - 1.0


def vol_estimate(panel: PanelBundle, window: int = 60, min_periods: int = 40,
                 floor_frac: float = 0.25) -> pd.DataFrame:
    """Annualised volatility estimate sigma_hat used for sizing and for vol-standardised signals.

        sigma_t     = std(e_{t-window+1..t}, ddof=1) * sqrt(periods_per_year)     (>= min_periods obs)
        sigma_hat_t = max(sigma_t, floor_frac * median(sigma_s : s <= t))

    The floor is 25 % of the estimate's OWN expanding median, so a quiet spell (a managed currency, a
    holiday week) cannot blow a position up by more than 4x its typical size.
    Causality: a trailing rolling std and an expanding median, both rows <= t.
    Limits: NaN until `min_periods` excess returns exist; a volatility of exactly zero is returned as
    NaN (nothing can be sized on it)."""
    e = excess_returns(panel)
    sigma = e.rolling(window, min_periods=min_periods).std() * np.sqrt(panel.periods_per_year)
    floor = floor_frac * sigma.expanding(min_periods=1).median()
    out = pd.DataFrame(np.maximum(sigma.to_numpy(dtype=float), floor.to_numpy(dtype=float)),
                       index=sigma.index, columns=sigma.columns)
    return out.where(out > 0)


def daily_vol(panel: PanelBundle) -> pd.DataFrame:
    """Per-print volatility: `vol_estimate(panel) / sqrt(periods_per_year)` (the sigma_daily of §4)."""
    return vol_estimate(panel) / np.sqrt(panel.periods_per_year)


def vol_scaled_return(panel: PanelBundle, lookback: int, skip: int = 0) -> pd.DataFrame:
    """Excess return of the window in units of its own standard deviation:

        ( X_{t-skip} / X_{t-lookback} - 1 ) / ( sigma_daily,t * sqrt(lookback - skip) )

    X = `excess_index(panel)`, sigma_daily,t = `daily_vol(panel)` at row t (the CURRENT estimate), and
    lookback - skip is the number of prints the return spans. This is the statistic TSMOM z clips, and
    — by conductor ruling of 2026-11-10 — the score every cross-sectional RETURN rule ranks, so that a
    cross-section spanning bonds, equities and commodities is not sorted by volatility.
    Causality: two non-negative shifts and a trailing volatility.
    Limits: NaN until the volatility (40 returns) and both index levels exist."""
    scale = daily_vol(panel) * np.sqrt(lookback - skip)
    return lookback_return(excess_index(panel), lookback, skip) / scale


def size_positions(signal: pd.DataFrame, panel: PanelBundle, sigma_target: float, *,
                   vol: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Turn a raw signal into target exposures:

        w_i = s_i * (sigma_target / sigma_hat_i) / N_eligible ,   |w_i| <= 1

    * sigma_hat  = `vol_estimate(panel)` (pass `vol=` to reuse one already computed on the same panel);
    * N_eligible = number of instruments that may be held at the row (`panel.eligible()`), whatever
      their signal. An eligible instrument with no view, a zero signal or no sigma_hat yet (its first
      40 prints) still counts in N_eligible and gets w = 0;
    * an ineligible instrument gets w = 0 and does not count;
    * the result has no NaN: it is a complete target, flat where there is no view.

    N_eligible REPLACES the N_active of DESIGN_v2 §3.7 (the number of instruments with a non-zero
    signal) by conductor ruling of 2026-11-10. With N_active the whole risk budget went to whichever
    instruments happened to be active: a sparse rule (RSI, Bollinger, volatility breakout) had exactly
    one active instrument on 31-38 % of the prints of a nine-instrument null panel and put about 1.0
    gross into that single name. With N_eligible every instrument owns a fixed 1/N share of the risk
    budget and uses |s_i| of it: a book is as large as the views it actually holds.
    Causality: elementwise in row t, plus sigma_hat (causal) and the row's eligibility.
    Limits: the gross exposure of a rule now scales with the fraction of the universe it has a view on
    (a tercile rule uses two thirds of the budget); book-level volatility targeting is the portfolio
    layer's job, not this function's."""
    if not (signal.index.equals(panel.prices.index) and list(signal.columns) == list(panel.prices.columns)):
        raise ValueError("signal must have exactly the panel's index and columns")
    vals = signal.to_numpy(dtype=float)
    if np.isinf(vals).any() or (np.abs(vals[np.isfinite(vals)]) > 1.0 + 1e-12).any():
        raise ValueError("signal must lie in [-1, 1] (NaN = no view)")
    if not sigma_target > 0:
        raise ValueError("sigma_target must be positive")
    sigma = vol_estimate(panel) if vol is None else vol
    if not (sigma.index.equals(signal.index) and list(sigma.columns) == list(signal.columns)):
        raise ValueError("vol must have exactly the panel's index and columns")
    eligible = panel.eligible()
    n_eligible = eligible.sum(axis=1)
    held = eligible & signal.notna() & (signal != 0) & sigma.notna()
    w = (signal * (sigma_target / sigma)).div(n_eligible.where(n_eligible > 0), axis=0)
    return w.where(held, 0.0).fillna(0.0).clip(-1.0, 1.0)


# --------------------------------------------------------------------------------------------------
# smoothing and standardisation
# --------------------------------------------------------------------------------------------------
def ewma(x, span: int, min_periods: Optional[int] = None):
    """Exponentially weighted mean with the library convention (module docstring):
    y_t = sum_i (1-a)^i x_{t-i} / sum_i (1-a)^i, a = 2/(span+1), over the rows <= t that exist.
    `span = 1` is the identity. Reported once `min_periods` (default `span`) observations exist, and
    only on rows where x itself is known. Causal."""
    if span < 1:
        raise ValueError("span must be >= 1")
    if span == 1:
        return x.copy()
    mp = span if min_periods is None else min_periods
    return x.ewm(span=span, adjust=True, min_periods=mp).mean().where(x.notna())


def ewm_std(x, span: int, min_periods: Optional[int] = None):
    """Exponentially weighted standard deviation (same weights as `ewma`, bias-corrected):
        m = sum w_i x_i / W ,  var = [sum w_i (x_i - m)^2 / W] * W^2 / (W^2 - sum w_i^2) ,  W = sum w_i,
    w_i = (1-a)^i. For two observations this is the ordinary sample std. Causal."""
    mp = span if min_periods is None else min_periods
    return x.ewm(span=span, adjust=True, min_periods=mp).std()


def zscore(x, window: int, min_periods: Optional[int] = None):
    """Trailing z-score: (x_t - mean(x_{t-window+1..t})) / std(x_{t-window+1..t}, ddof=1); the window
    INCLUDES row t. NaN until `min_periods` (default the full window) observations exist and when the
    window is constant (std = 0). Causal."""
    mp = window if min_periods is None else min_periods
    roll = x.rolling(window, min_periods=mp)
    sd = roll.std()
    return (x - roll.mean()) / sd.where(sd > 0)


def zscore_clipped(x, window: int, min_periods: Optional[int] = None):
    """z_L(x) of DESIGN §4: the trailing-L z-score clipped at +-2, then divided by 2 -> [-1, 1]."""
    return zscore(x, window, min_periods).clip(-2.0, 2.0) / 2.0


# --------------------------------------------------------------------------------------------------
# cross-sectional constructions
# --------------------------------------------------------------------------------------------------
def _ranked_scores(score: pd.DataFrame, eligible: pd.DataFrame) -> pd.DataFrame:
    if not (score.index.equals(eligible.index) and list(score.columns) == list(eligible.columns)):
        raise ValueError("score and eligible must share index and columns")
    v = score.where(eligible.astype(bool))
    return v.where(np.isfinite(v))


def xs_tercile(score: pd.DataFrame, eligible: pd.DataFrame, *, min_n: int = 3,
               ties: Optional[str] = None) -> pd.DataFrame:
    """+1 for the top third, -1 for the bottom third of the row's eligible, finite scores; 0 between.

    With n ranked instruments in a row the leg size is k = floor(n / 3) (so k >= 1 whenever n >= 3);
    n < `min_n` (3) gives a zero signal for the whole row. Ineligible instruments and NaN scores are NaN
    (no view). Sort ascending: positions 1..k are the short leg, positions n-k+1..n the long leg.

    TIES (`ties`, default `DEFAULT_TIES`):
    * "split" — a group of equal scores occupying positions a..b gets, for every member,
          (#positions of a..b in the long leg - #positions of a..b in the short leg) / (b - a + 1).
      Untied instruments get exactly -1 / 0 / +1; a tie that straddles a leg boundary shares that leg's
      remaining slots equally — the value is the EXPECTATION of the "order" rule over every tie-break
      order. Each leg still hands out exactly k slots and the row sums to zero; a group that reaches
      into both legs nets its two shares, so a row with no dispersion at all is exactly zero.
      Deterministic and independent of column order.
    * "order" — the brief's literal rule: ranks ascending with `method="first"`, i.e. among equal
      scores the EARLIER column gets the LOWER rank, so a tie straddling the bottom boundary puts the
      earlier columns in the short leg and a tie straddling the top boundary puts the later columns in
      the long leg. Values are always -1 / 0 / +1. With step-valued scores (policy rates, "at the
      high") this turns "no information" into a persistent position chosen by the column order.
    The two modes are identical on every row without a straddling tie.
    Causality: each row is ranked on its own."""
    mode = DEFAULT_TIES if ties is None else ties
    v = _ranked_scores(score, eligible)
    n = v.notna().sum(axis=1)
    k = (n // 3).where(n >= min_n, 0)
    if mode == "order":
        rank = v.rank(axis=1, method="first")
        out = pd.DataFrame(0.0, index=v.index, columns=v.columns)
        out = out.mask(rank.gt(n - k, axis=0), 1.0).mask(rank.le(k, axis=0), -1.0)
    elif mode == "split":
        a = v.rank(axis=1, method="min")
        b = v.rank(axis=1, method="max")
        in_short = (b.clip(upper=k, axis=0) - a + 1.0).clip(lower=0.0)
        in_long = (b - a.clip(lower=n - k + 1, axis=0) + 1.0).clip(lower=0.0)
        out = (in_long - in_short) / (b - a + 1.0)
    else:
        raise ValueError("ties must be 'split' or 'order'")
    return out.where(v.notna())


def xs_linear_rank(score: pd.DataFrame, eligible: pd.DataFrame, *, min_n: int = 3) -> pd.DataFrame:
    """Weights linear in the cross-sectional rank, mean zero, extremes at +-1:

        w_i = (rank_i - (n + 1) / 2) / ((n - 1) / 2) ,   rank in 1..n ascending.

    TIES share their AVERAGE rank (tied scores get equal weights, the row still sums to zero; max |w|
    is exactly 1 unless the extreme itself is tied). n < `min_n` (3) gives a zero signal; ineligible
    instruments and NaN scores are NaN. Causality: each row is ranked on its own."""
    v = _ranked_scores(score, eligible)
    n = v.notna().sum(axis=1)
    rank = v.rank(axis=1, method="average")
    centre = (n + 1) / 2.0
    half = ((n - 1) / 2.0).where(n >= min_n)
    w = rank.sub(centre, axis=0).div(half, axis=0)
    w = w.where(half.notna(), 0.0, axis=0)
    return w.where(v.notna())


# --------------------------------------------------------------------------------------------------
# technical state
# --------------------------------------------------------------------------------------------------
def donchian_state(x: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Donchian channel stop-and-reverse state machine on the level frame x.

        up_t   : x_t > max(x_{t-lookback} .. x_{t-1})      -> state = +1
        down_t : x_t < min(x_{t-lookback} .. x_{t-1})      -> state = -1
        else   : state_t = state_{t-1}                     (0 until the first breakout)

    The channel EXCLUDES the current print. There is no exit channel: once in, the position is held
    until the opposite breakout (DESIGN §4 names one parameter, L).
    Causality: `shift(1)` + trailing rolling extremes + forward fill.
    Limits: NaN while the channel is undefined (first `lookback` prints, or a gap inside the window) and
    where x is NaN; the state itself is carried across such rows."""
    prev = x.shift(1)
    hi = prev.rolling(lookback, min_periods=lookback).max()
    lo = prev.rolling(lookback, min_periods=lookback).min()
    event = pd.DataFrame(np.nan, index=x.index, columns=x.columns)
    event = event.mask(x > hi, 1.0).mask(x < lo, -1.0)
    state = event.ffill().fillna(0.0)
    return state.where(hi.notna() & x.notna())


def rsi(x: pd.DataFrame, n: int) -> pd.DataFrame:
    """Wilder's Relative Strength Index of the level frame x, in [0, 100].

        gain_t = max(dx_t, 0),  loss_t = max(-dx_t, 0),  dx_t = x_t - x_{t-1}
        first averages (at the n-th change) = simple means of the first n gains / losses
        avg_t = (avg_{t-1} * (n - 1) + new_t) / n                       (Wilder smoothing, a = 1/n)
        RSI_t = 100 * avg_gain_t / (avg_gain_t + avg_loss_t)

    Causality: an expanding mean for the seed and a recursion forward from it.
    Limits: NaN for the first n prints, where x is NaN, and when both averages are zero (a flat window
    has no relative strength). A missing change is skipped (the recursion continues on the next one)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    d = x.diff()
    gain = d.clip(lower=0.0)
    loss = (-d).clip(lower=0.0)
    count = d.notna().cumsum()
    seed_row = d.notna() & (count == n)
    after = d.notna() & (count > n)

    def wilder(v: pd.DataFrame) -> pd.DataFrame:
        seeded = v.expanding(min_periods=1).mean().where(seed_row)
        seq = seeded.where(seed_row, v.where(after))
        return seq.ewm(alpha=1.0 / n, adjust=False, ignore_na=True).mean().where(seq.notna())

    ag, al = wilder(gain), wilder(loss)
    total = ag + al
    return (100.0 * ag / total.where(total > 0)).where(x.notna())


def rolling_slope_tstat(y: pd.DataFrame, window: int) -> pd.DataFrame:
    """OLS t-statistic of the slope of y on time (0, 1, .., window-1) over each trailing window.

        b = S_xy / S_xx ,  SSE = S_yy - b * S_xy ,  se(b) = sqrt(SSE / (window - 2) / S_xx) ,  t = b / se(b)

    The classical (i.i.d.-residual) standard error; no HAC correction.
    Causality: each row uses its own trailing window; the arithmetic of a row does not depend on how
    many rows the frame has.
    Limits: NaN unless the window is complete and NaN-free; +-inf for an exact line; NaN for a constant."""
    if window < 3:
        raise ValueError("window must be >= 3")
    t = np.arange(window, dtype=float)
    tc = t - t.mean()
    sxx = float((tc * tc).sum())
    vals = y.to_numpy(dtype=float)
    out = np.full(vals.shape, np.nan)
    if len(vals) >= window:
        with np.errstate(divide="ignore", invalid="ignore"):
            for j in range(vals.shape[1]):
                w = np.ascontiguousarray(sliding_window_view(vals[:, j], window))
                dev = w - w.mean(axis=1)[:, None]
                sxy = (dev * tc).sum(axis=1)
                syy = (dev * dev).sum(axis=1)
                slope = sxy / sxx
                sse = np.maximum(syy - slope * sxy, 0.0)
                out[window - 1:, j] = slope / np.sqrt(sse / (window - 2) / sxx)
    return pd.DataFrame(out, index=y.index, columns=y.columns)


# --------------------------------------------------------------------------------------------------
# calendar
# --------------------------------------------------------------------------------------------------
def first_print_of_period(index: pd.DatetimeIndex, period: str) -> pd.Series:
    """True on the first print the index contains of each calendar month ("M"), ISO week ("W", Monday
    start) or calendar year ("Y"), by UTC date.

    Causality: row t is compared with row t-1 only.
    Limits: the FIRST row of the index is flagged True — it is the first print of its period that the
    panel contains, which is not necessarily the first print of that period in the real calendar."""
    dates = utc_dates(index)
    if period == "M":
        key = dates.year.to_numpy() * 12 + dates.month.to_numpy()
    elif period == "W":
        iso = dates.isocalendar()
        key = iso["year"].to_numpy(dtype=np.int64) * 100 + iso["week"].to_numpy(dtype=np.int64)
    elif period == "Y":
        key = dates.year.to_numpy()
    else:
        raise ValueError("period must be 'M', 'W' or 'Y'")
    flag = np.ones(len(index), dtype=bool)
    flag[1:] = key[1:] != key[:-1]
    return pd.Series(flag, index=index)


def turn_of_month_mask(index: pd.DatetimeIndex, last_n: int = 3, first_n: int = 2, *,
                       calendar: str = "weekday") -> pd.Series:
    """True on the DECISION prints that belong to the turn of the month: the last `last_n` prints of a
    calendar month and the first `first_n` prints of the next (UTC dates).

    Whether a print is one of the LAST prints of its month cannot be read off the index at print time
    (the remaining prints have not happened), so that side is CALENDAR ARITHMETIC on the print's own
    date:
        calendar="weekday": the number of Monday-Friday days after the date within its month < last_n
        calendar="daily"  : the number of calendar days after the date within its month < last_n
    The FIRST side is exact and causal: the print is one of the first `first_n` prints of its month in
    the index (a running count of rows <= t). In the first month the index contains — where prints
    before the panel start are unknown — the same arithmetic is used instead (weekday / calendar-day
    number within the month <= first_n).

    Error of the arithmetic (weekday calendars only; the daily calendar is exact): a market holiday
    among the last `last_n` weekdays of a month removes one print from the window, which then holds
    `last_n - 1` prints instead of sliding back to the true third-last print (e.g. Good Friday
    2024-03-29: the window is 27-28 March, the true last three prints were 26-28 March). Measured on
    rule-based holiday calendars for 2000-2025 (312 month-ends, last_n = 3): 29 month-ends (9.3 %) on a
    NYSE calendar — Memorial Day, Thanksgiving, Good Friday — and 4 (1.3 %) on the TARGET calendar; never
    more than one print is lost. No future row is ever used; the window is only ever SHORTER than
    intended, never shifted onto a print that the calendar could not name in advance.

    The mask marks decision prints. With the engine's lag = 1 a position decided on these five prints
    earns the returns of the last print of the month and the first four of the next (days -1 .. +4)."""
    if calendar not in ("weekday", "daily"):
        raise ValueError("calendar must be 'weekday' or 'daily'")
    if last_n < 0 or first_n < 0:
        raise ValueError("last_n and first_n must be >= 0")
    dates = utc_dates(index)
    n = len(dates)
    if n == 0:
        return pd.Series(np.zeros(0, dtype=bool), index=index)
    day = dates.day.to_numpy()
    if calendar == "daily":
        remaining = dates.days_in_month.to_numpy() - day
        ordinal = day
    else:
        d = dates.to_numpy().astype("datetime64[D]")
        month_start = d.astype("datetime64[M]").astype("datetime64[D]")
        next_month = (d.astype("datetime64[M]") + np.timedelta64(1, "M")).astype("datetime64[D]")
        nxt = d + np.timedelta64(1, "D")
        remaining = np.busday_count(nxt, next_month)
        ordinal = np.busday_count(month_start, nxt)
    last_side = remaining < last_n
    ym = dates.year.to_numpy() * 12 + dates.month.to_numpy()
    new_month = np.ones(n, dtype=bool)
    new_month[1:] = ym[1:] != ym[:-1]
    start_of_run = np.maximum.accumulate(np.where(new_month, np.arange(n), 0))
    count_in_month = np.arange(n) - start_of_run + 1
    first_side = np.where(ym == ym[0], ordinal <= first_n, count_in_month <= first_n)
    return pd.Series(last_side | first_side, index=index)


# --------------------------------------------------------------------------------------------------
# carry
# --------------------------------------------------------------------------------------------------
def carry_source(panel: PanelBundle) -> str:
    """Which input `annualised_carry` reads on this panel: 'rates', 'carry' or 'none'. Decided from the
    panel's STRUCTURE (which frames and columns exist), never from its values."""
    rates = panel.aux.get("rates")
    if rates is not None and "USD" in rates.columns and any(c in rates.columns for c in panel.prices.columns):
        return "rates"
    return "carry" if panel.carry is not None else "none"


def annualised_carry(panel: PanelBundle, *, span_prints: int = 5) -> pd.DataFrame:
    """Annualised carry of a +1.0 exposure, per instrument (a decimal rate per year).

    1. `aux["rates"]` present with a "USD" column and a column for at least one instrument (the FX
       lanes): the rate differential  rates[ccy] - rates["USD"]  — the frame is already lagged by the
       data layer. An instrument without a rates column is NaN (no view); sources are never mixed
       inside one cross-section.
    2. otherwise, from the accrual panel:  sum(carry_{t-4..t}) / (calendar days from print t-5 to
       print t) * 360.  FX accrual is by calendar days, so a Monday print carries about three days; the
       five-print sum over its own day count removes that artefact exactly when the rate is constant
       over the span (one week on a weekday calendar).
    3. neither input: `NotApplicable`.
    Causality: aux/carry rows <= t and index dates <= t.
    Limits: the two sources differ by day-count convention and timing around a rate change; NO unit
    check is made here (a rule must not look at the whole frame) — `aux["rates"]` must be decimal
    fractions per year, like the rates behind `panel.carry`."""
    source = carry_source(panel)
    cols = list(panel.prices.columns)
    if source == "rates":
        rates = panel.aux["rates"]
        return rates.reindex(columns=cols).astype(float).sub(rates["USD"].astype(float), axis=0)
    if source == "carry":
        days = calendar_days_between_prints(panel.prices.index, span_prints)
        total = panel.carry.rolling(span_prints, min_periods=span_prints).sum()
        return total.div(days.where(days > 0), axis=0) * 360.0
    raise NotApplicable("annualised carry needs aux['rates'] (with a 'USD' column) or panel.carry")
