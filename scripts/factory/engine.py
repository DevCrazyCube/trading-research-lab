"""engine.py — the vectorised backtest core of the factory (float64, numpy). DESIGN_v2 §3.1.

WHAT THIS MODULE IS
  `backtest` turns target exposures into per-print P&L series under ONE frozen timing convention;
  `fast_net_returns` is its lean numpy twin for the nulls (proven equal in tests). An independent
  loop engine (`xcheck.py`, written from the contract's text, sharing no code with this file) is
  pinned to this one to 1e-10 on random panels.

  There are NO statistics here (DESIGN_v2 §3.1). The runner calls
  `stats.summarize(result.net, window=(start, end), ...)` on an explicit date window, so warm-up
  rows — where `held` is identically zero — are never scored.

TIMING — the only two legal conventions
  `w` is the target exposure (signed fraction of equity) DECIDED at row s from rows <= s.

  (A) no `exec_prices`: decide on P_s, fill at a LATER panel print.
          r_t    = P_t / P_{t-1} - 1
          held_t = w_{t-1-lag}            held = w.shift(1 + lag),  lag >= 1  (lag = 0 raises Refused)
      w_s is filled at print s+lag and first earns r_{s+lag+1}.

  (B) with `exec_prices` F: an execution print STRICTLY LATER in clock time than the decision
      print that shares its row (crypto: decide on the 00:00 UTC close, execute at the 01:00 UTC
      close stored on the same row).
          r_t    = F_t / F_{t-1} - 1
          held_t = w_{t-1-extra_lag}      held = w.shift(1 + extra_lag),  extra_lag >= 0
      w_s is executed at F_{s+extra_lag} and first earns F_{s+extra_lag+1} / F_{s+extra_lag} - 1.
      Every return is taken on F, so the price transacted at and the price marked at are the same
      print. `lag` has no meaning here and must be left at its default.
      The engine CANNOT see clocks. It therefore refuses `exec_prices` unless the data layer has
      asserted `panel.meta["exec_prices_strictly_after_decision"] is True` (identity, not
      truthiness), and it refuses an `exec_prices` frame identical to `panel.prices` (that would be
      lag = 0 under another name). The share of cells where F == P exactly is reported in
      `meta["exec_equals_decision_frac"]` for the reader.
      (The v1 draft used held = w.shift(1 + lag) with lag >= 1 on the F series: a 00:00 decision
      executed at 01:00 the NEXT day, 25 hours late. That is what v2 fixes.)

THE P&L FORMULA (per print t, per instrument i; exactly what the code computes)
      price_pnl_t = SUM_i held_{t,i} * r_{t,i}
      carry_t     = SUM_i held_{t,i} * carry_{t,i}
      before_{t,i} = held_{t-1,i} * (1 + r_{t-1,i}) / (1 + R_{t-1}),   R_{t-1} = SUM_j held_{t-1,j} * r_{t-1,j}
                                                                          [turnover_model="drift", the default]
                   = held_{t-1,i}                                         [turnover_model="target"]
                     (before_0 = 0 under both)
      turnover_t  = SUM_i |held_{t,i} - before_{t,i}|
      cost_t      = SUM_i |held_{t,i} - before_{t,i}| * cost_bp_side_i / 1e4
      hold_cost_t = [ SUM_i max(held_{t,i}, 0)  * hold_cost_long_bp_year_i  / 1e4
                    + SUM_i max(-held_{t,i}, 0) * hold_cost_short_bp_year_i / 1e4 ] * days_t / 365
      gross_t     = price_pnl_t + carry_t
      net_t       = gross_t - cost_t - hold_cost_t
      turnover_target_t = SUM_i |held_{t,i} - held_{t-1,i}|    gross_leverage_t = SUM_i |held_{t,i}|
  where days_t is the number of CALENDAR days between print t-1 and print t, taken from the panel
  index as the difference of the two UTC calendar dates (days_0 = 0; Friday -> Monday = 3;
  `calendar_days`).

  * TURNOVER MODEL. `held` is a fraction of equity that the engine restores at every print. Between
    prints the position does not stay at that fraction: over (t-2, t-1] instrument i grows by
    (1 + r_{t-1,i}) while the book grows by (1 + R_{t-1}), so at print t-1 — just before the trade
    that sets held_t — the position stands at `before_{t,i}`. Under "drift" (default) the trade
    booked on row t is the move from THERE to held_t: re-balancing is no longer free, and a
    constant target pays for being kept constant. Under "target" the trade is the change of the
    target alone (the pre-drift behaviour; kept for comparison and for the nulls' fast path).
    `turnover` / `cost` hold the model actually charged; `turnover_target` is always the
    target-only figure, so a report can show both.
    Only PRICE returns drift a position: carry (and costs) accrue to cash, not to position size.
    The denominator is likewise the book's price return alone; the carry, cost and hold cost of
    that print, which also move equity by a few 1e-4, are left out. That is the difference —
    measured, not assumed — between this engine and `realism.simulate_account`, which keeps the
    actual equity (tests/test_realism.py). A book that loses 100 % or more in one print
    (1 + R_{t-1} <= 1e-9) has no drifted weights: "drift" refuses it.

  * `held_t` is the position in force over (t-1, t]. `|held_t - before_t|` is the trade executed
    at print t-1; its cost is booked in row t, the FIRST row whose P&L the new position earns.
    Costs are per side in bp of traded notional: a reversal +1 -> -1 is 2.0 units and pays twice.
  * `carry_{t,i}` is the panel's per-print accrual of a +1.0 exposure over (t-1, t] (the financing
    leg: -r_f for funded instruments, the rate differential for FX, -funding for perps). It is paid
    to `held_t`. Every lane is therefore scored in EXCESS return. With `exec_prices` the data layer
    must align carry to the F intervals; the engine cannot verify that.
  * Hold costs are a venue markup on top of the carry panel, on the long and on the short notional
    separately. They accrue in CALENDAR time (ACT/365 on days_t), like the carry panel itself: a
    position held over a weekend pays three days. `periods_per_year` plays no part in the P&L
    (a per-print rate of bp_year / periods_per_year drifts whenever a panel's real prints-per-year
    differ from the declared figure); it is only recorded in `meta`. days_t counts calendar DATES,
    so two prints on the same UTC date accrue nothing between them and the overnight interval
    accrues one day — the way financing is actually charged.
  * All series are fractions of equity per print (the linear simplification). Compounding happens
    only in `stats`.

COSTS — never defaulted to something unsourced
  `cost_bp_side` is a required keyword. `hold_cost_*_bp_year` default to 0.0 because the contract's
  signature says so (FX and perps carry their financing in the carry panel); whether each was left
  at its default is recorded in `meta["hold_cost_long_defaulted"]` / `["hold_cost_short_defaulted"]`
  so a zero is never silent. Each accepts a scalar, a dict or a per-instrument Series; a missing
  instrument, None, a bool, NaN, inf or a negative value raises `Refused`.

MISSING DATA
  * NaN in `w` means "no target" -> 0 (flat); the count is `meta["n_nan_w"]`. +/-inf refuses.
  * `missing_return="refuse"` (FX, MACRO): a held position (held != 0) on a print whose return OR
    whose carry is NaN raises `Refused`, naming the first cell. A missing carry is refused too
    because scoring a position without its financing leg is the v1 defect (#1) in miniature.
  * `missing_return="zero"` (crypto): those cells earn 0 — the position is marked at its last
    price, and drifts by 0 in the turnover model — and are counted in
    `meta["n_missing_return_held"]` / `["n_missing_carry_held"]`.
    `held` itself is NOT altered: it stays `w.shift(...)`. So a position on a dead instrument still
    counts in `gross_leverage`, still pays hold costs, and pays its exit side on the row its
    target goes to zero (one or two prints late when the strategy sizes with `panel.eligible()`).
    An interior GAP in a price series loses the gap's true return on both NaN-return rows: 'zero'
    on a gappy panel is an approximation, and the counts are how the reader finds out.
  * The engine never forward-fills a price.

STATED LIMITS
  * THE COST OF A FILL IS BOOKED ONE ROW AFTER THE FILL. A trade executed at print t-1 changes
    `held_t`; its cost appears in row t, the first row whose P&L the new position earns — not in
    row t-1, the print at which cash actually leaves. Totals are unaffected; a per-print comparison
    with an engine that books costs at the fill print is offset by one row.
  * A TARGET DECIDED ON THE LAST `1 + lag` PRINTS (`1 + extra_lag` on exec prices) IS NEVER BOOKED:
    held_t = w_{t - shift}, so the decisions of rows T-shift .. T-1 would first be held after the
    sample ends. Neither their cost nor their P&L exists in the result.
  * A position still open on the last print is never closed, so it is never charged an exit
    (`meta["n_open_at_end"]`). Buy-and-hold pays one entry and no exit.
  * RE-BALANCING TO TARGET ON EVERY PRINT. `held` is restored to the target fraction at each print.
    Under "drift" the trades that takes are charged; under "target" they are free. Either way the
    RETURN PATH is that of a book re-balanced every print. A book that really trades on a schedule
    (monthly, weekly) and drifts in between follows a different path — and the drift model then
    over-charges it, restoring daily what the schedule restores once a period. For those books the
    official engine is `realism.simulate_account` (units, a re-balance mask, a no-trade band).
  * Float64 throughout; summation order differs between this file, `fast_net_returns` and
    `xcheck.py`, so equality is asserted to 1e-10, not bit for bit.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Literal, Optional, Union

import numpy as np
import pandas as pd

from .panel import PanelBundle

log = logging.getLogger(__name__)

MIN_LAG = 1
DEFAULT_LAG = 1
EXEC_FLAG = "exec_prices_strictly_after_decision"
MissingReturnPolicy = Literal["refuse", "zero"]
TurnoverModel = Literal["drift", "target"]
CostSpec = Union[float, int, pd.Series, Dict[str, float]]

DAYS_PER_YEAR = 365.0          # ACT/365 for hold costs
WIPED_OUT = 1e-9               # drift model: a book worth <= this fraction of itself after one print is refused
CONVENTION = (
    "held = w.shift(1+lag) on panel.prices [lag>=1], or w.shift(1+extra_lag) on exec_prices [extra_lag>=0]; "
    "net = SUM held*r + SUM held*carry - SUM |held - before|*cost_side "
    "- SUM (max(held,0)*hc_long + max(-held,0)*hc_short) * calendar_days/365; "
    "before = held[t-1]*(1+r[t-1])/(1+SUM held[t-1]*r[t-1]) under turnover_model='drift', held[t-1] under 'target'"
)


class Refused(Exception):
    """An input violates the frozen convention; the run does not happen. Never caught silently."""


class _DefaultZero(float):
    """The float 0.0, but recognisable by identity: lets `backtest` record in `meta` whether a hold
    cost was LEFT at the contract's default (0.0) or passed explicitly — a zero is never silent."""

    __slots__ = ()


_HOLD_COST_DEFAULT = _DefaultZero(0.0)


@dataclass(frozen=True)
class BacktestResult:
    """Per-print series of one backtest. Every Series/DataFrame shares the panel index.

    net               gross - cost - hold_cost                      (fraction of equity per print)
    gross             price_pnl + carry                             (no trading cost, no hold cost)
    price_pnl         SUM_i held * r
    carry             SUM_i held * carry_panel
    cost              SUM_i |held_t - before_t| * cost_side          (booked on the first row earned;
                      `before` per the turnover model, module docstring)
    hold_cost         SUM_i (max(held,0)*hc_long + max(-held,0)*hc_short) * days_t / 365
    held              positions in force over (t-1, t]  (= w.shift(1 + lag | extra_lag), NaN -> 0)
    turnover          SUM_i |held_t - before_t|: the turnover actually CHARGED (sides: a reversal
                      counts twice); under "drift" it includes the trades that restore the target
    gross_leverage    SUM_i |held_t|
    meta              resolved inputs and counts (JSON-serialisable; see `backtest`)
    net_by_instrument (T x N) price + carry - cost - hold_cost per instrument; rows sum to `net`
                      up to float summation order. An ADDITION to the contract's field list, needed
                      by `stats.contribution_by_instrument(result)`.
    turnover_target   SUM_i |held_t - held_{t-1}|: the change of the TARGET alone, whatever model was
                      charged (equal to `turnover` under "target"), so reports can show both.
    """

    net: pd.Series
    gross: pd.Series
    price_pnl: pd.Series
    carry: pd.Series
    cost: pd.Series
    hold_cost: pd.Series
    held: pd.DataFrame
    turnover: pd.Series
    gross_leverage: pd.Series
    meta: dict = field(default_factory=dict)
    net_by_instrument: Optional[pd.DataFrame] = None
    turnover_target: Optional[pd.Series] = None


# --------------------------------------------------------------------------------------------------
# Validation helpers (shared with mtest.py / portfolio.py / realism.py)
# --------------------------------------------------------------------------------------------------
def _is_int(x) -> bool:
    return isinstance(x, (int, np.integer)) and not isinstance(x, (bool, np.bool_))


def validate_lag(lag) -> int:
    """`lag` must be an integer >= 1: a target decided at print s cannot be filled at print s."""
    if not _is_int(lag):
        raise Refused(f"lag must be an integer >= {MIN_LAG}; got {lag!r}")
    if lag < MIN_LAG:
        raise Refused(
            f"lag = {lag} refused: a target decided at print s cannot be filled at print s "
            f"(DESIGN_v2 §3.1: lag >= {MIN_LAG} is enforced)."
        )
    return int(lag)


def validate_extra_lag(extra_lag) -> int:
    """`extra_lag` must be an integer >= 0 (0 = execute at the exec print of the decision row)."""
    if not _is_int(extra_lag) or extra_lag < 0:
        raise Refused(f"extra_lag must be an integer >= 0; got {extra_lag!r}")
    return int(extra_lag)


def resolve_shift(panel: PanelBundle, lag, extra_lag, exec_prices) -> int:
    """The number of rows `w` is shifted to become `held`, after every timing refusal.

    No `exec_prices`: 1 + lag (lag >= 1), and `extra_lag` must be 0.
    With `exec_prices`: 1 + extra_lag (extra_lag >= 0); `lag` must be left at its default and
    `panel.meta["exec_prices_strictly_after_decision"]` must be the object True.
    """
    if exec_prices is None:
        lag = validate_lag(lag)
        if not _is_int(extra_lag) or extra_lag != 0:
            raise Refused(
                f"extra_lag = {extra_lag!r} has no meaning without exec_prices; leave it at 0 "
                f"(the fill delay on panel prints is `lag`)."
            )
        return 1 + lag
    if panel.meta.get(EXEC_FLAG) is not True:
        raise Refused(
            f"exec_prices refused: panel.meta[{EXEC_FLAG!r}] is {panel.meta.get(EXEC_FLAG)!r}, not True. "
            f"The engine cannot see clocks; the data layer must assert that every exec print is strictly "
            f"later than the decision print of its row."
        )
    if not _is_int(lag) or lag != DEFAULT_LAG:
        raise Refused(
            f"lag = {lag!r} given together with exec_prices: `lag` is ignored on the exec series and must "
            f"be left at its default ({DEFAULT_LAG}); use extra_lag to delay the execution."
        )
    return 1 + validate_extra_lag(extra_lag)


def validate_weights(w: pd.DataFrame, panel: PanelBundle) -> np.ndarray:
    """Check `w` against the panel and return it as a float64 (T, N) array in the panel's column order.

    `w.index` must equal the panel's index; the column SET must equal the panel's instruments (any
    order). NaN is kept (the caller counts it and treats it as flat); +/-inf refuses.
    """
    if not isinstance(w, pd.DataFrame):
        raise Refused(f"w must be a DataFrame of target exposures; got {type(w).__name__}")
    if not w.index.equals(panel.prices.index):
        raise Refused(
            "w.index must equal panel.prices.index (same prints, same order); "
            f"got {len(w.index)} rows vs {len(panel.prices.index)}"
        )
    cols = list(panel.prices.columns)
    if not w.columns.is_unique or set(w.columns) != set(cols):
        missing = sorted(map(str, set(cols) - set(w.columns)))
        extra = sorted(map(str, set(w.columns) - set(cols)))
        raise Refused(f"w.columns must be exactly the panel instruments; missing={missing} extra={extra}")
    try:
        arr = w[cols].to_numpy(dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise Refused(f"w must be numeric: {exc}") from exc
    if np.isinf(arr).any():
        raise Refused("w contains +/-inf; an infinite exposure is not a target")
    return arr


def validate_prices(prices: pd.DataFrame, what: str = "prices") -> np.ndarray:
    """Prices must be > 0 and finite wherever they are not NaN. Returns the float64 array."""
    try:
        arr = prices.to_numpy(dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise Refused(f"{what} must be numeric: {exc}") from exc
    bad = ~np.isnan(arr) & ~(np.isfinite(arr) & (arr > 0))
    if bad.any():
        i, j = np.argwhere(bad)[0]
        raise Refused(
            f"{what} must be > 0 and finite where present; first offender "
            f"{prices.columns[j]!r} at {prices.index[i]}: {arr[i, j]!r}"
        )
    return arr


def resolve_per_instrument(spec: CostSpec, columns, name: str) -> np.ndarray:
    """A per-instrument cost input in its own unit (bp), aligned to `columns`.

    A scalar applies to every instrument. A dict / Series must have an entry for every instrument
    (extra entries are ignored: one cost table may serve several universes). None, a bool, a
    missing instrument, NaN, inf or a negative number raises `Refused` — an unsourced cost is not
    zero. Zero itself is allowed, and is flagged by the caller.
    """
    cols = list(columns)
    if spec is None or isinstance(spec, (bool, np.bool_)):
        raise Refused(f"{name} must be a number, a dict or a per-instrument Series; got {spec!r}")
    if isinstance(spec, (int, float, np.integer, np.floating)):
        c = float(spec)
        if not np.isfinite(c) or c < 0:
            raise Refused(f"{name} must be finite and >= 0; got {spec!r}")
        return np.full(len(cols), c, dtype=np.float64)
    if isinstance(spec, dict):
        spec = pd.Series(spec, dtype=object)
    if not isinstance(spec, pd.Series):
        raise Refused(f"{name} must be a number, a dict or a per-instrument Series; got {type(spec).__name__}")
    if not spec.index.is_unique:
        raise Refused(f"{name} has duplicate instrument labels")
    missing = [c for c in cols if c not in spec.index]
    if missing:
        raise Refused(f"{name} has no entry for {missing}; an unsourced cost refuses")
    picked = spec.reindex(cols)
    if any(isinstance(v, (bool, np.bool_)) or v is None for v in picked.tolist()):
        raise Refused(f"{name} has None/bool entries: {dict(zip(cols, picked.tolist()))}")
    try:
        vals = picked.to_numpy(dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise Refused(f"{name} must be numeric per instrument: {exc}") from exc
    if not np.isfinite(vals).all() or (vals < 0).any():
        raise Refused(f"{name} has NaN/inf/negative entries: {dict(zip(cols, vals.tolist()))}")
    return vals


def aligned_exec_prices(panel: PanelBundle, exec_prices: pd.DataFrame) -> np.ndarray:
    """`exec_prices` as a validated float64 (T, N) array in the panel's column order.

    Must be a DataFrame on the panel's index with exactly the panel's instruments, > 0 where
    present, and NOT identical to `panel.prices` (executing at the decision print is lag = 0).
    """
    if not isinstance(exec_prices, pd.DataFrame):
        raise Refused(f"exec_prices must be a DataFrame aligned to panel.prices; got {type(exec_prices).__name__}")
    if not exec_prices.index.equals(panel.prices.index):
        raise Refused("exec_prices.index must equal panel.prices.index")
    cols = list(panel.prices.columns)
    if not exec_prices.columns.is_unique or set(exec_prices.columns) != set(cols):
        raise Refused("exec_prices.columns must be exactly the panel instruments")
    arr = validate_prices(exec_prices[cols], "exec_prices")
    dec = panel.prices.to_numpy(dtype=np.float64)
    if arr.size and np.array_equal(arr, dec, equal_nan=True):
        raise Refused(
            "exec_prices is identical to panel.prices: executing at the decision print is lag = 0. "
            "An execution print must be strictly later than the decision print."
        )
    return arr


def calendar_days(index: pd.DatetimeIndex) -> np.ndarray:
    """days_t: calendar days between print t-1 and print t, as the difference of their UTC calendar
    DATES (float array, days_0 = 0). Friday -> Monday is 3; two prints on one UTC date are 0 apart."""
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise Refused("calendar_days needs a tz-aware DatetimeIndex")
    dates = index.tz_convert("UTC").normalize()
    out = np.zeros(len(dates), dtype=np.float64)
    if len(dates) > 1:
        out[1:] = np.asarray((dates[1:] - dates[:-1]).days, dtype=np.float64)
    if (out < 0).any():
        raise Refused("the index is not sorted in time")
    return out


def positions_before_trade(held: np.ndarray, r: np.ndarray, turnover_model: str = "drift") -> np.ndarray:
    """before[t, i]: where the position stands, as a fraction of equity, at print t-1 just before the
    trade that sets held[t]. (T, N) arrays; `r` NaN-free (a missing return drifts by 0). before[0] = 0.

    "target": before[t] = held[t-1] — the previous target, as if it had not moved.
    "drift":  before[t, i] = held[t-1, i] * (1 + r[t-1, i]) / (1 + R[t-1]),  R[t-1] = SUM_j held[t-1, j] * r[t-1, j]
              — the previous position after its own interval, relative to the book after the same
              interval (price returns only). Refuses if the book lost 100 % or more on a row whose
              drift is needed (1 + R <= 1e-9: "to within rounding"; the last row is never needed).
    """
    if turnover_model not in ("drift", "target"):
        raise Refused(f"turnover_model must be 'drift' or 'target'; got {turnover_model!r}")
    held = np.asarray(held, dtype=np.float64)
    before = np.zeros_like(held)
    if held.shape[0] < 2:
        return before
    if turnover_model == "target":
        before[1:] = held[:-1]
        return before
    r = np.asarray(r, dtype=np.float64)
    if r.shape != held.shape or np.isnan(r).any():
        raise Refused("positions_before_trade needs NaN-free returns aligned to held")
    book = 1.0 + (held * r).sum(axis=1)
    if (book[:-1] <= WIPED_OUT).any():             # -100 % to within rounding: -5 x 20 % is -0.9999999999999998
        t = int(np.argmax(book[:-1] <= WIPED_OUT))
        raise Refused(
            f"turnover_model='drift': the book's price return on row {t} is {book[t] - 1.0:+.4f} (<= -100 %); "
            f"a book that is wiped out in one print has no drifted weights. Cap the leverage, or score it with "
            f"turnover_model='target' and say so."
        )
    before[1:] = held[:-1] * (1.0 + r[:-1]) / book[:-1, None]
    return before


def returns_array(px: np.ndarray) -> np.ndarray:
    """r_t = X_t / X_{t-1} - 1 on a (T, N) price array; row 0 is NaN; NaN wherever either price is NaN."""
    r = np.full(px.shape, np.nan, dtype=np.float64)
    if px.shape[0] > 1:
        r[1:] = px[1:] / px[:-1] - 1.0
    return r


def shift_positions_array(w: np.ndarray, shift: int) -> np.ndarray:
    """held[..., t, :] = w[..., t - shift, :] for t >= shift, else 0. `shift` >= 1; arrays (..., T, N).

    `shift` is the TOTAL row shift (1 + lag, or 1 + extra_lag), not the lag. NaN in `w` is carried
    through unchanged — resolve it first.
    """
    if not _is_int(shift) or shift < 1:
        raise Refused(f"shift must be an integer >= 1 (it is 1 + lag or 1 + extra_lag); got {shift!r}")
    w = np.asarray(w, dtype=np.float64)
    held = np.zeros_like(w)
    if w.shape[-2] > shift:
        held[..., shift:, :] = w[..., :-shift, :]
    return held


# --------------------------------------------------------------------------------------------------
# Lean numpy path — for the nulls; proven equal to `backtest` in tests/test_engine.py
# --------------------------------------------------------------------------------------------------
def fast_net_returns(
    held: np.ndarray,
    r: np.ndarray,
    carry: Optional[np.ndarray],
    cost_frac: Union[float, np.ndarray],
    hc_long: Union[float, np.ndarray],
    hc_short: Union[float, np.ndarray],
    days: np.ndarray,
) -> np.ndarray:
    """Net return per print from POST-SHIFT positions, as matrix products. Returns shape (..., T).

    held       (..., T, N) positions in force over (t-1, t], NaN-free. Leading dimensions broadcast
               (e.g. one slab per formula).
    r          (T, N) returns, NaN already resolved by the caller's stated policy.
    carry      (T, N) NaN-free, or None for "no carry panel".
    cost_frac  scalar or (N,): cost per side as a FRACTION (bp / 1e4).
    hc_long    scalar or (N,): hold cost on long notional as an ANNUAL fraction (bp_year / 1e4).
    hc_short   same for short notional.
    days       (T,) calendar days between print t-1 and print t (`calendar_days(index)`); the hold
               cost of row t is the annual rate times days[t] / 365.

    net_t = SUM held*r + SUM held*carry - SUM |held_t - held_{t-1}|*cost_frac
            - (SUM max(held,0)*hc_long + SUM max(-held,0)*hc_short) * days_t / 365,     held_{-1} = 0.
    There are no defaults and no NaN policy here: NaN in any input refuses.

    TURNOVER MODEL: this path implements "target" ONLY — the cost is charged on the change of the
    target, |held_t - held_{t-1}|. It equals `backtest(..., turnover_model="target")`, NOT the
    default "drift" model of `backtest`, which also charges the trades that restore the target as
    prices move. It is kept on "target" on purpose: it is the fast path of the nulls, where
    positions are re-aligned against returns and a drift term would have to be recomputed per
    replicate.
    """
    held = np.asarray(held, dtype=np.float64)
    r = np.asarray(r, dtype=np.float64)
    if held.ndim < 2 or held.shape[-2:] != r.shape:
        raise Refused(f"held {held.shape} and r {r.shape} disagree on (T, N)")
    if np.isnan(held).any() or np.isnan(r).any():
        raise Refused("fast_net_returns takes NaN-free held and r; resolve NaN by an explicit policy first")
    n = r.shape[1]
    params = []
    for name, x in (("cost_frac", cost_frac), ("hc_long", hc_long), ("hc_short", hc_short)):
        arr = np.asarray(x, dtype=np.float64)
        if arr.ndim > 1 or (arr.ndim == 1 and arr.shape[0] != n):
            raise Refused(f"{name} must be a scalar or an (N,) array; got shape {arr.shape}")
        if not np.isfinite(arr).all() or (arr < 0).any():
            raise Refused(f"{name} must be finite and >= 0")
        params.append(arr)
    cost_arr, hcl, hcs = params
    year_frac = np.asarray(days, dtype=np.float64)
    if year_frac.shape != (r.shape[0],) or not np.isfinite(year_frac).all() or (year_frac < 0).any():
        raise Refused(f"days must be a finite, non-negative (T,) array; got shape {year_frac.shape}")
    year_frac = year_frac / DAYS_PER_YEAR
    pnl = np.einsum("...tn,tn->...t", held, r)
    if carry is not None:
        carry = np.asarray(carry, dtype=np.float64)
        if carry.shape != r.shape or np.isnan(carry).any():
            raise Refused("carry must be a NaN-free (T, N) array aligned to r, or None")
        pnl = pnl + np.einsum("...tn,tn->...t", held, carry)
    prev = np.concatenate([np.zeros_like(held[..., :1, :]), held[..., :-1, :]], axis=-2)
    cost = (np.abs(held - prev) * cost_arr).sum(axis=-1)
    hold = ((np.maximum(held, 0.0) * hcl).sum(axis=-1) + (np.maximum(-held, 0.0) * hcs).sum(axis=-1)) * year_frac
    return pnl - cost - hold


# --------------------------------------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------------------------------------
def backtest(
    panel: PanelBundle,
    w: pd.DataFrame,
    *,
    lag: int = DEFAULT_LAG,
    cost_bp_side: CostSpec,
    hold_cost_long_bp_year: CostSpec = _HOLD_COST_DEFAULT,
    hold_cost_short_bp_year: CostSpec = _HOLD_COST_DEFAULT,
    exec_prices: Optional[pd.DataFrame] = None,
    extra_lag: int = 0,
    missing_return: MissingReturnPolicy = "refuse",
    turnover_model: TurnoverModel = "drift",
) -> BacktestResult:
    """Score target exposures `w` on `panel` under the frozen convention (module docstring).

    panel       PanelBundle; `panel.carry` (or None) is the financing leg; the panel INDEX supplies
                the calendar-day count used for hold costs.
    w           DataFrame on the panel's index with the panel's instruments: the target decided at
                row t from rows <= t. NaN = flat.
    lag         fill delay in panel prints, >= 1. Only without `exec_prices`.
    cost_bp_side            REQUIRED. bp of traded notional per side; scalar | dict | Series.
    hold_cost_long_bp_year  bp per year on long notional (venue markup), accrued on calendar days
                            (ACT/365); scalar | dict | Series.
    hold_cost_short_bp_year bp per year on short notional, same accrual; scalar | dict | Series.
    exec_prices execution-print prices on the panel's index (see TIMING (B)); requires
                `panel.meta["exec_prices_strictly_after_decision"] is True`.
    extra_lag   extra rows of delay on the exec series, >= 0. Only with `exec_prices`.
    missing_return  "refuse" | "zero" (module docstring, MISSING DATA).
    turnover_model  "drift" (default): the trade charged on row t is the move from the DRIFTED
                position (the previous position after its own price returns) to the new one, so
                re-balancing back to target is paid for. "target": only changes of the target are
                charged (the earlier behaviour, exactly). Module docstring, TURNOVER MODEL.

    Returns a `BacktestResult`. Raises `Refused` on any convention violation.

    `meta` keys: lane, periods_per_year, priced_on, lag (None with exec_prices), extra_lag, shift,
    n_prints, n_instruments, n_nan_w, missing_return_policy, n_missing_return_held,
    n_missing_carry_held, has_carry, cost_bp_side{}, hold_cost_long_bp_year{},
    hold_cost_short_bp_year{}, cost_is_zero, hold_cost_long_defaulted, hold_cost_short_defaulted,
    n_open_at_end, hold_cost_day_count, calendar_days_total, turnover_model,
    exec_equals_decision_frac (None without exec_prices), convention.
    """
    if not isinstance(panel, PanelBundle):
        raise Refused(f"panel must be a PanelBundle; got {type(panel).__name__}")
    if missing_return not in ("refuse", "zero"):
        raise Refused(f"missing_return must be 'refuse' or 'zero'; got {missing_return!r}")
    if turnover_model not in ("drift", "target"):
        raise Refused(f"turnover_model must be 'drift' or 'target'; got {turnover_model!r}")
    cols = list(panel.prices.columns)
    idx = panel.prices.index
    if not cols:
        raise Refused("the panel has no instruments")
    if not panel.prices.columns.is_unique:
        raise Refused("panel.prices has duplicate instrument labels")
    try:
        ppy = float(panel.periods_per_year)        # the bundle's own (integer) annualisation factor
    except (KeyError, TypeError, ValueError) as exc:
        raise Refused(f"panel.meta['periods_per_year'] is unusable: {exc}") from exc
    if not np.isfinite(ppy) or ppy <= 0:
        raise Refused(f"panel.meta['periods_per_year'] must be > 0; got {panel.meta.get('periods_per_year')!r}")

    shift = resolve_shift(panel, lag, extra_lag, exec_prices)
    w_arr = validate_weights(w, panel)
    nan_w = np.isnan(w_arr)
    n_nan_w = int(nan_w.sum())
    if n_nan_w:
        log.debug("backtest: %d NaN targets in w treated as 0 (flat)", n_nan_w)
        w_arr = np.where(nan_w, 0.0, w_arr)

    cost_bp = resolve_per_instrument(cost_bp_side, cols, "cost_bp_side")
    hcl_bp = resolve_per_instrument(hold_cost_long_bp_year, cols, "hold_cost_long_bp_year")
    hcs_bp = resolve_per_instrument(hold_cost_short_bp_year, cols, "hold_cost_short_bp_year")
    cost_frac = cost_bp / 1e4
    hc_long = hcl_bp / 1e4                         # annual fractions; accrued on calendar days below
    hc_short = hcs_bp / 1e4
    days = calendar_days(idx)
    year_frac = days / DAYS_PER_YEAR

    dec_px = validate_prices(panel.prices, "panel.prices")
    if exec_prices is None:
        px = dec_px
        exec_equal_frac = None
    else:
        px = aligned_exec_prices(panel, exec_prices)
        both = ~np.isnan(px) & ~np.isnan(dec_px)
        exec_equal_frac = float((px[both] == dec_px[both]).mean()) if both.any() else None
    r = returns_array(px)
    held = shift_positions_array(w_arr, shift)
    active = held != 0.0

    # ---- missing-data policy: a held position needs a return AND (when the panel has one) a carry.
    miss_r = np.isnan(r) & active
    if panel.carry is None:
        carry_arr = None
        miss_c = np.zeros_like(active)
    else:
        try:
            carry_arr = panel.carry[cols].to_numpy(dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise Refused(f"panel.carry must be numeric: {exc}") from exc
        if np.isinf(carry_arr).any():
            raise Refused("panel.carry contains +/-inf")
        miss_c = np.isnan(carry_arr) & active
    n_miss_r, n_miss_c = int(miss_r.sum()), int(miss_c.sum())
    if missing_return == "refuse" and (n_miss_r or n_miss_c):
        which, mask = ("return", miss_r) if n_miss_r else ("carry", miss_c)
        i, j = np.argwhere(mask)[0]
        raise Refused(
            f"{n_miss_r} held position(s) have no return and {n_miss_c} have no carry "
            f"(first missing {which}: {cols[j]!r} at {idx[i]}, held={held[i, j]:+.6f}). The panel is "
            f"incomplete there; deliver a complete panel or pass missing_return='zero' and report the count."
        )
    r0 = np.where(np.isnan(r), 0.0, r)

    # ---- the formula, per instrument first (so contributions are auditable), then summed.
    price_i = held * r0
    if carry_arr is None:
        carry_i = np.zeros_like(held)
    else:
        carry_i = held * np.where(np.isnan(carry_arr), 0.0, carry_arr)
    traded = np.abs(held - positions_before_trade(held, r0, turnover_model))   # the trade actually charged
    prev = np.zeros_like(held)
    prev[1:] = held[:-1]
    target_change = np.abs(held - prev)                                         # the change of the target alone
    cost_i = traded * cost_frac
    hold_i = (np.maximum(held, 0.0) * hc_long + np.maximum(-held, 0.0) * hc_short) * year_frac[:, None]

    price_pnl = price_i.sum(axis=1)
    carry_pnl = carry_i.sum(axis=1)
    cost = cost_i.sum(axis=1)
    hold_cost = hold_i.sum(axis=1)
    gross = price_pnl + carry_pnl
    net = gross - cost - hold_cost
    turnover = traded.sum(axis=1)
    turnover_target = target_change.sum(axis=1)
    gross_leverage = np.abs(held).sum(axis=1)

    def series(a: np.ndarray, name: str) -> pd.Series:
        return pd.Series(a, index=idx, name=name)

    meta = {
        "lane": panel.lane,
        "periods_per_year": ppy,
        "priced_on": "prices" if exec_prices is None else "exec_prices",
        "lag": int(lag) if exec_prices is None else None,
        "extra_lag": int(extra_lag),
        "shift": int(shift),
        "n_prints": int(len(idx)),
        "n_instruments": len(cols),
        "n_nan_w": n_nan_w,
        "missing_return_policy": missing_return,
        "n_missing_return_held": n_miss_r,
        "n_missing_carry_held": n_miss_c,
        "has_carry": panel.carry is not None,
        "cost_bp_side": {str(c): float(v) for c, v in zip(cols, cost_bp)},
        "hold_cost_long_bp_year": {str(c): float(v) for c, v in zip(cols, hcl_bp)},
        "hold_cost_short_bp_year": {str(c): float(v) for c, v in zip(cols, hcs_bp)},
        "cost_is_zero": bool(np.all(cost_bp == 0.0)),
        "hold_cost_long_defaulted": hold_cost_long_bp_year is _HOLD_COST_DEFAULT,
        "hold_cost_short_defaulted": hold_cost_short_bp_year is _HOLD_COST_DEFAULT,
        "n_open_at_end": int(active[-1].sum()) if len(idx) else 0,
        "hold_cost_day_count": "ACT/365 on the UTC calendar dates of the panel index",
        "calendar_days_total": float(days.sum()),
        "turnover_model": turnover_model,
        "exec_equals_decision_frac": exec_equal_frac,
        "convention": CONVENTION,
    }
    return BacktestResult(
        net=series(net, "net"),
        gross=series(gross, "gross"),
        price_pnl=series(price_pnl, "price_pnl"),
        carry=series(carry_pnl, "carry"),
        cost=series(cost, "cost"),
        hold_cost=series(hold_cost, "hold_cost"),
        held=pd.DataFrame(held, index=idx, columns=cols),
        turnover=series(turnover, "turnover"),
        gross_leverage=series(gross_leverage, "gross_leverage"),
        meta=meta,
        net_by_instrument=pd.DataFrame(price_i + carry_i - cost_i - hold_i, index=idx, columns=cols),
        turnover_target=series(turnover_target, "turnover_target"),
    )


__all__ = [
    "Refused", "BacktestResult", "backtest", "fast_net_returns", "MIN_LAG", "DEFAULT_LAG", "EXEC_FLAG",
    "CONVENTION", "DAYS_PER_YEAR", "CostSpec", "MissingReturnPolicy", "TurnoverModel", "calendar_days",
    "positions_before_trade", "WIPED_OUT", "validate_lag",
    "validate_extra_lag", "resolve_shift",
    "validate_weights", "validate_prices", "resolve_per_instrument", "aligned_exec_prices", "returns_array",
    "shift_positions_array",
]
