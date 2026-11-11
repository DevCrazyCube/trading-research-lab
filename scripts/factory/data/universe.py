"""Point-in-time universe mask (the ONLY place the crypto universe is decided).

`pit_universe_mask(qvol, top_n=..., min_history=60, vol_window=30)`

Input  `qvol`: DataFrame, index = print rows t (sorted, unique), columns = instruments;
        `qvol.loc[t, i]` = quote volume of the candle of i that ENDED at t, NaN when i has no traded
        candle ending at t (not listed yet, delisted, or a zero-trade phantom candle).
Output boolean DataFrame of the same shape. `mask.loc[t, i]` is True iff ALL of
  (1) i has a traded candle ending at t                                  (it is tradeable at the print);
  (2) i has >= `min_history` traded candles that ended STRICTLY BEFORE t (listed long enough);
  (3) the `vol_window` consecutive candles ending at t all exist, and their mean quote volume ranks
      in the top `top_n` among ALL instruments that satisfy (1) and have a complete window at t.
The rank in (3) is taken across every instrument with a complete window — an instrument that is too
young for (2) still occupies its rank, so the mask can hold fewer than `top_n` names (this is the
literal reading of "has >= 60 candles AND ranks in the top N").

Causality: row t of the output is a function of rows <= t of the input only (trailing rolling mean,
cumulative count shifted by one row, cross-sectional rank at t). `tests/test_data_universe.py` proves
it by altering every row after t and comparing.
Ties are broken by column order (rank method "first"), so the result is deterministic.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def trailing_mean_volume(qvol: pd.DataFrame, vol_window: int = 30) -> pd.DataFrame:
    """Mean quote volume of the `vol_window` candles ending at t; NaN unless all of them exist."""
    return qvol.rolling(vol_window, min_periods=vol_window).mean()


def pit_universe_mask(qvol: pd.DataFrame, *, top_n: int, min_history: int = 60, vol_window: int = 30) -> pd.DataFrame:
    if not qvol.index.is_monotonic_increasing or not qvol.index.is_unique:
        raise ValueError("qvol index must be sorted and unique")
    if top_n < 1 or min_history < 0 or vol_window < 1:
        raise ValueError("bad parameters")
    present = qvol.notna()
    # candles that ended strictly before t  =  cumulative count up to t, minus the one at t
    n_before = present.cumsum() - present.astype("int64")
    tmv = trailing_mean_volume(qvol, vol_window)
    tmv = tmv.where(present)                                  # (1) must trade at t to be ranked at all
    rank = tmv.rank(axis=1, ascending=False, method="first", na_option="keep")
    mask = (rank <= top_n) & (n_before >= min_history) & present
    return mask.fillna(False).astype(bool)


def mask_summary(mask: pd.DataFrame) -> dict:
    n = mask.sum(axis=1)
    live = n[n > 0]
    return {
        "rows": int(len(mask)),
        "rows_with_any_member": int((n > 0).sum()),
        "first_row_with_member": None if live.empty else str(live.index[0]),
        "members_per_row_min_after_first": None if live.empty else int(n.loc[live.index[0]:].min()),
        "members_per_row_median_after_first": None if live.empty else float(n.loc[live.index[0]:].median()),
        "members_per_row_max": int(n.max()) if len(n) else 0,
        "ever_in_mask": int(mask.any(axis=0).sum()),
    }
