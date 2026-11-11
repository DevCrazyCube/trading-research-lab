"""portfolio.py — the portfolio layer between rule books and the engine (DESIGN_v2 §3.5).

Every function maps target-weight frames to target-weight frames (or to a per-print series) and is
STRICTLY CAUSAL: row t of the output depends only on rows <= t of its inputs. That is proven per
function by a truncation test (tests/test_portfolio.py: cut the inputs at row k, recompute, compare
rows <= k bit for bit). Nothing here scores anything — performance comes only from
`engine.backtest` on the frame these functions return.

Conventions
  * A weight frame `w` has the panel's index and instruments; w[t, i] is the target exposure
    (signed fraction of equity) DECIDED at print t. NaN means "no target" and is treated as 0.
    Outputs are NaN-free.
  * `book_returns(w, panel)` is the PAPER return of a book: what the weights decided at t-1 earn
    over (t-1, t], gross of every cost and with no fill delay:
        b_t = SUM_i w[t-1, i] * (r[t, i] + carry[t, i]),     b_0 = 0,   missing r / carry -> 0.
    It is known at t and is a RISK input only (how volatile is this book?). It is never a
    performance figure: it ignores the engine's lag and costs on purpose.
  * Book volatility at t: sigma_t = std(b_{t-vol_window+1..t}, ddof=1) * sqrt(periods_per_year),
    available once `vol_window` paper returns exist (sigma is NaN on rows 0..vol_window-1, row 0
    being the forced 0), FLOORED at 25 % of the expanding median of its own positive past values:
        sigma_eff_t = max(sigma_t, 0.25 * median{sigma_s : s <= t, sigma_s > 0}).
    The floor mirrors the instrument-level rule of the strategy library (DESIGN_v2 §3.7) and stops
    a book that has just been flat (sigma -> 0) from being levered without bound when it re-enters.
    A book with no positive sigma yet is INACTIVE (scale NaN -> weight 0).

STATED LIMITS
  * Volatility is the book's own REALISED paper volatility over the last `vol_window` prints. It
    lags changes of composition: a book that has just levered up, or re-entered after a flat
    spell, is under-estimated for up to `vol_window` prints (bounded by the floor: at most 4x the
    typical scale). An ex-ante estimate from the current weights and a trailing covariance matrix
    would not lag; it is a possible upgrade, not what this module does.
  * Scaling changes positions, hence turnover; that cost is charged by the engine when the scaled
    frame is backtested, not here.
  * "Equal risk" equalises each book's stand-alone volatility, not its contribution to the
    combination's risk (correlations are ignored). The combination of imperfectly correlated books
    therefore runs BELOW `target`; apply `vol_target` to the result when a book-level target is
    wanted (DESIGN_v2 §6).
"""
from __future__ import annotations

import math
from typing import Dict, Mapping, Optional, Sequence, Union

import numpy as np
import pandas as pd

from .engine import Refused, returns_array, validate_prices, validate_weights
from .panel import PanelBundle

VOL_FLOOR_FRACTION = 0.25
Books = Union[Mapping[str, pd.DataFrame], Sequence[pd.DataFrame]]


# --------------------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------------------
def _weights(w: pd.DataFrame, panel: Optional[PanelBundle] = None) -> np.ndarray:
    """`w` as a float64 array with NaN -> 0 (panel column order when a panel is given)."""
    if panel is not None:
        arr = validate_weights(w, panel)
    else:
        if not isinstance(w, pd.DataFrame):
            raise Refused(f"w must be a DataFrame of target exposures; got {type(w).__name__}")
        try:
            arr = w.to_numpy(dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise Refused(f"w must be numeric: {exc}") from exc
        if np.isinf(arr).any():
            raise Refused("w contains +/-inf; an infinite exposure is not a target")
    return np.where(np.isnan(arr), 0.0, arr)


def _frame(arr: np.ndarray, w: pd.DataFrame, panel: Optional[PanelBundle] = None) -> pd.DataFrame:
    cols = list(panel.prices.columns) if panel is not None else list(w.columns)
    return pd.DataFrame(arr, index=w.index, columns=cols)


def _positive_int(x, name: str) -> int:
    if isinstance(x, (bool, np.bool_)) or not isinstance(x, (int, np.integer)) or x < 2:
        raise Refused(f"{name} must be an integer >= 2; got {x!r}")
    return int(x)


def _positive_float(x, name: str) -> float:
    if isinstance(x, (bool, np.bool_)) or not isinstance(x, (int, float, np.integer, np.floating)):
        raise Refused(f"{name} must be a number > 0; got {x!r}")
    if not np.isfinite(x) or x <= 0:
        raise Refused(f"{name} must be finite and > 0; got {x!r}")
    return float(x)


def _excess_returns(panel: PanelBundle) -> np.ndarray:
    """r + carry per instrument and print, NaN -> 0 (row 0 has no return)."""
    r = returns_array(validate_prices(panel.prices, "panel.prices"))
    x = np.where(np.isnan(r), 0.0, r)
    if panel.carry is not None:
        c = panel.carry[list(panel.prices.columns)].to_numpy(dtype=np.float64)
        x = x + np.where(np.isnan(c), 0.0, c)
    return x


# --------------------------------------------------------------------------------------------------
# risk inputs
# --------------------------------------------------------------------------------------------------
def book_returns(w: pd.DataFrame, panel: PanelBundle) -> pd.Series:
    """Paper return of the book per print: b_t = SUM_i w[t-1, i] * (r[t, i] + carry[t, i]), b_0 = 0.

    Gross of all costs, no fill delay, missing returns / carry count as 0. A RISK input (module
    docstring), not a performance series.
    """
    arr = _weights(w, panel)
    x = _excess_returns(panel)
    out = np.zeros(len(arr))
    if len(arr) > 1:
        out[1:] = (arr[:-1] * x[1:]).sum(axis=1)
    return pd.Series(out, index=w.index, name="book_return")


def book_vol(w: pd.DataFrame, panel: PanelBundle, *, vol_window: int = 60) -> pd.Series:
    """Floored, annualised realised volatility of the book's paper returns (`sigma_eff`, module
    docstring). NaN until `vol_window` paper returns exist (rows 0..vol_window-1) and while the
    book has never had a positive volatility."""
    vol_window = _positive_int(vol_window, "vol_window")
    ppy = float(panel.periods_per_year)
    b = book_returns(w, panel).to_numpy()
    sigma = np.full(len(b), np.nan)
    if len(b) > vol_window:
        # each window is computed from its own values only (no running sums): the result at t cannot
        # depend on anything after t, and a flat window gives exactly 0. Row 0 is not a return.
        windows = np.lib.stride_tricks.sliding_window_view(b[1:], vol_window)
        sigma[vol_window:] = windows.std(axis=1, ddof=1) * math.sqrt(ppy)
    sig = pd.Series(sigma, index=w.index)
    floor = VOL_FLOOR_FRACTION * sig.where(sig > 0).expanding(min_periods=1).median()
    eff = np.maximum(sig.to_numpy(), floor.to_numpy())                  # NaN wherever either is NaN
    return pd.Series(eff, index=w.index, name="book_vol")


def risk_scale(w: pd.DataFrame, panel: PanelBundle, *, vol_window: int = 60, target: float = 0.10) -> pd.Series:
    """The causal multiplier that brings the book to `target` annualised volatility:
    scale_t = target / sigma_eff_t (NaN while the book is inactive). Building block of
    `equal_risk_combo` / `vol_target`; exposed so cross-lane combinations (P.GLOBAL) can scale
    each lane's frame before backtesting it on its own panel."""
    target = _positive_float(target, "target")
    vol = book_vol(w, panel, vol_window=vol_window)
    return (target / vol).rename("risk_scale")


# --------------------------------------------------------------------------------------------------
# combinations
# --------------------------------------------------------------------------------------------------
def equal_risk_combo(books: Books, panel: PanelBundle, vol_window: int = 60, target: float = 0.10) -> pd.DataFrame:
    """Equal-risk combination of weight frames on ONE panel:

        w_combo[t] = (1 / n_active_t) * SUM_{b active at t} (target / sigma_eff_b[t]) * w_b[t]

    Each book is scaled to the same stand-alone annualised volatility `target`, and the scaled books
    are averaged over the books ACTIVE at t (those with a defined scale; a book still in warm-up is
    not counted, a book that is active but currently flat is counted and contributes 0). Rows with
    no active book are flat. `books` is a mapping id -> frame (or a sequence of frames).
    """
    frames = list(books.values()) if isinstance(books, Mapping) else list(books)
    if not frames:
        raise Refused("equal_risk_combo needs at least one book")
    total = np.zeros(panel.prices.shape)
    n_active = np.zeros(len(panel.prices))
    for frame in frames:
        arr = _weights(frame, panel)
        scale = risk_scale(frame, panel, vol_window=vol_window, target=target).to_numpy()
        active = np.isfinite(scale)
        total += np.where(active, scale, 0.0)[:, None] * arr
        n_active += active
    with np.errstate(divide="ignore", invalid="ignore"):
        combo = np.where(n_active[:, None] > 0, total / n_active[:, None], 0.0)
    return _frame(combo, frames[0], panel)


def ensemble(rule_books: Mapping[str, pd.DataFrame], family_of: Mapping[str, str], panel: PanelBundle,
             vol_window: int = 60, target: float = 0.10) -> pd.DataFrame:
    """Two-level equal-risk ensemble: `equal_risk_combo` of the rules inside each family, then
    `equal_risk_combo` of the family books. Every rule id must have a family (else `Refused`).
    A family with many rules therefore weighs the same as a family with one."""
    if not rule_books:
        raise Refused("ensemble needs at least one rule book")
    missing = [rid for rid in rule_books if rid not in family_of]
    if missing:
        raise Refused(f"family_of has no entry for rule ids {missing}")
    families: Dict[str, Dict[str, pd.DataFrame]] = {}
    for rid, frame in rule_books.items():
        families.setdefault(family_of[rid], {})[rid] = frame
    family_books = {fam: equal_risk_combo(members, panel, vol_window, target) for fam, members in families.items()}
    return equal_risk_combo(family_books, panel, vol_window, target)


def vol_target(w: pd.DataFrame, panel: PanelBundle, target: float, *, vol_window: int = 60,
               max_gross: float) -> pd.DataFrame:
    """Scale the book to `target` annualised volatility, then cap its gross exposure:

        w'[t] = w[t] * target / sigma_eff[t]            (0 while the book is inactive)
        if SUM_i |w'[t, i]| > max_gross:  w'[t] *= max_gross / SUM_i |w'[t, i]|

    `max_gross` is REQUIRED (keyword): the leverage a venue allows is a fact to be supplied, not a
    default. The cap binds row by row and scales every position pro rata.
    """
    max_gross = _positive_float(max_gross, "max_gross")
    arr = _weights(w, panel)
    scale = risk_scale(w, panel, vol_window=vol_window, target=target).to_numpy()
    scaled = np.where(np.isfinite(scale), scale, 0.0)[:, None] * arr
    gross = np.abs(scaled).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        cap = np.where(gross > max_gross, max_gross / gross, 1.0)
    return _frame(scaled * cap[:, None], w, panel)


# --------------------------------------------------------------------------------------------------
# trading rules on a weight frame
# --------------------------------------------------------------------------------------------------
def apply_buffer(w: pd.DataFrame, band: float = 0.10) -> pd.DataFrame:
    """Stateful no-trade band around the target; trade only to the nearest band edge.

    BAND WIDTH, precisely: for instrument i at print t the band is
        [ w[t,i] - band * |w[t,i]| ,  w[t,i] + band * |w[t,i]| ]
    i.e. +/- `band` (10 %) of the CURRENT target position, in the target's own units (this is the
    "position" buffer of Carver's pysystemtrade with trade-to-edge). With h[-1] = 0:
        h[t,i] = clip( h[t-1,i], lower[t,i], upper[t,i] )
    so a position inside the band is left alone, and one outside it moves to the NEAREST edge, not
    to the target. Consequences worth knowing: a zero target has a zero-width band (the position
    is closed in full); a sign flip trades to the near edge of the new band (target -1 -> -0.9);
    after an entry the position sits `band` short of the target until the target moves further.
    The output is a weight frame to hand to the engine in place of `w`.
    """
    if isinstance(band, (bool, np.bool_)) or not isinstance(band, (int, float, np.integer, np.floating)) \
            or not np.isfinite(band) or not (0.0 <= band < 1.0):
        raise Refused(f"band must be a number in [0, 1); got {band!r}")
    arr = _weights(w)
    out = np.empty_like(arr)
    held = np.zeros(arr.shape[1])
    half = float(band) * np.abs(arr)
    lower, upper = arr - half, arr + half
    for t in range(arr.shape[0]):
        held = np.minimum(np.maximum(held, lower[t]), upper[t])
        out[t] = held
    return _frame(out, w)


def long_only_cap(w: pd.DataFrame, max_gross: float = 1.0) -> pd.DataFrame:
    """Long-only, capped: negative targets become 0; if the remaining weights of a row sum to more
    than `max_gross`, the row is scaled down pro rata to exactly `max_gross`. Rows below the cap
    are NOT scaled up (the remainder is cash)."""
    max_gross = _positive_float(max_gross, "max_gross")
    arr = np.maximum(_weights(w), 0.0)
    gross = arr.sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        scale = np.where(gross > max_gross, max_gross / gross, 1.0)
    return _frame(arr * scale[:, None], w)


def _period_starts(index: pd.Index, freq: str) -> np.ndarray:
    """True on row 0 and on every row whose calendar period differs from the previous row's."""
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise Refused("a rebalance schedule needs a tz-aware DatetimeIndex (the panel's own index)")
    utc = index.tz_convert("UTC")
    if freq == "monthly":
        key = utc.year.to_numpy() * 12 + utc.month.to_numpy()
    elif freq == "weekly":
        iso = utc.isocalendar()
        key = iso["year"].to_numpy(dtype=np.int64) * 100 + iso["week"].to_numpy(dtype=np.int64)
    else:
        raise Refused(f"freq must be 'monthly' or 'weekly'; got {freq!r}")
    starts = np.ones(len(index), dtype=bool)
    starts[1:] = key[1:] != key[:-1]
    return starts


def rebalance_rows(index: pd.DatetimeIndex, freq: str, offset: int = 0) -> pd.Series:
    """Boolean Series on `index`: True on the rebalance prints of the schedule, shifted by `offset` rows.

    A rebalance print is the first row of the index, or the first print of a new period of the index
    itself: `freq="monthly"` — the UTC calendar (year, month) differs from the previous row's;
    `freq="weekly"` — the ISO (year, week) differs (ISO weeks start on Monday; 2024-12-30 belongs
    to ISO week 1 of 2025). A month whose first calendar day is not a print rebalances on its first
    print. `offset = k` marks the row k prints AFTER each rebalance print instead: with decisions
    taken on the rebalance prints and a fill delay of `delay` prints,
    `rebalance_rows(index, freq, offset=delay)` is the mask of TRADE rows that
    `realism.simulate_account(rebalance_mask=...)` expects. Only timestamps at or before row t
    decide row t: the schedule is causal.
    """
    if isinstance(offset, (bool, np.bool_)) or not isinstance(offset, (int, np.integer)) or offset < 0:
        raise Refused(f"offset must be an integer >= 0; got {offset!r}")
    starts = _period_starts(index, freq)
    out = np.zeros(len(index), dtype=bool)
    if offset == 0:
        out = starts
    elif len(index) > offset:
        out[offset:] = starts[:-offset]
    return pd.Series(out, index=index, name=f"rebalance_{freq}")


def rebalance_on(w: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Hold the target of the last REBALANCE print: out[t] = w[last rebalance row <= t] (NaN -> 0).

    The rebalance prints are those of `rebalance_rows(w.index, freq)`: the first row of `w`, and the
    first print of each new calendar month (`"monthly"`) or ISO week (`"weekly"`) of the index
    itself. Only timestamps at or before t are consulted, so the schedule is causal.
    NOTE: the result is a target frame for `engine.backtest`, which re-balances back to it on EVERY
    print (and, under its default drift turnover model, charges for doing so — more than a real
    monthly schedule would trade). A book that is really traded once a period and DRIFTS in between
    is `realism.simulate_account(..., rebalance_mask=rebalance_rows(index, freq, offset=delay))`.
    """
    if not isinstance(w, pd.DataFrame):
        raise Refused(f"w must be a DataFrame of target exposures; got {type(w).__name__}")
    is_reb = _period_starts(w.index, freq)
    arr = _weights(w)
    if len(arr) == 0:
        return _frame(arr, w)
    last = np.maximum.accumulate(np.where(is_reb, np.arange(len(arr)), 0))
    return _frame(arr[last], w)


def margin_utilisation(w: pd.DataFrame, margin_rate_by_class: Mapping[str, float],
                       asset_class_of: Mapping[str, str]) -> pd.Series:
    """Initial margin the book ties up, per print, as a fraction of equity:

        m[t] = SUM_i |w[t, i]| * margin_rate_by_class[ asset_class_of[i] ]

    A margin rate is the fraction of notional a venue requires (0.05 = 20:1, 1.0 = fully funded).
    m[t] > 1 means the book cannot be carried at that venue on that print. An instrument without a
    class, or a class without a finite rate >= 0, raises `Refused` — an unknown margin is not zero.
    """
    arr = np.abs(_weights(w))
    rates = np.empty(arr.shape[1])
    for j, col in enumerate(w.columns):
        if col not in asset_class_of:
            raise Refused(f"asset_class_of has no entry for instrument {col!r}")
        cls = asset_class_of[col]
        if cls not in margin_rate_by_class:
            raise Refused(f"margin_rate_by_class has no entry for class {cls!r} (instrument {col!r})")
        rate = margin_rate_by_class[cls]
        if rate is None or isinstance(rate, (bool, np.bool_)) or not isinstance(rate, (int, float, np.integer, np.floating)) \
                or not np.isfinite(rate) or rate < 0:
            raise Refused(f"margin rate for class {cls!r} must be a finite number >= 0; got {rate!r}")
        rates[j] = float(rate)
    # row-wise sum, not `arr @ rates`: BLAS picks its code path by array shape, so a matrix product is not
    # bit-identical between a full and a truncated frame (found by the truncation test).
    return pd.Series((arr * rates).sum(axis=1), index=w.index, name="margin_utilisation")


__all__ = [
    "book_returns", "book_vol", "risk_scale", "equal_risk_combo", "ensemble", "vol_target", "apply_buffer",
    "long_only_cap", "rebalance_on", "rebalance_rows", "margin_utilisation", "VOL_FLOOR_FRACTION",
]
