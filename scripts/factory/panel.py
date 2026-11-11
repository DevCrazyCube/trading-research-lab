"""PanelBundle — the one data object every factory module shares. Defined BEFORE any loader or strategy.

Conventions (see research/factory/README.md, "Interfaces"):
  * `prices`  : DataFrame, index = UTC DatetimeIndex of PRINTS (the price a position can be filled at),
                sorted, unique; columns = instruments; values = tradeable price of that print (float).
  * `carry`   : same shape as `prices` or None. Per-print accrual earned by a +1.0 exposure, already in
                return units for ONE print interval (e.g. (i_fx - i_usd)/360 per calendar day of FX
                holding, or -funding for a perp long at the funding prints, 0 elsewhere).
  * `aux`     : dict of name -> DataFrame aligned to the same index (any columns), e.g. 'rates', 'cpi',
                'glsr', 'funding_raw', 'volume'. A strategy may only read aux rows <= its decision row.
  * `tbill`   : Series aligned to the index: per-print risk-free accrual (return units), used as the
                cash benchmark and by dual-momentum rules. Zero series if unknown (and meta says so).
  * `meta`    : dict with at least {'lane', 'print_convention', 'source_manifest', 'universe',
                'periods_per_year'}. `periods_per_year` is the annualisation factor of ONE print
                interval (252 for daily FX/ETF prints, 365 for the daily crypto rebalance print).

Nothing here looks at the future; `window()` slices rows by timestamp and is the ONLY sanctioned way to
hand a strategy a design-window-only view.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import pandas as pd


def _as_utc(x, *, end_of_day: bool = False) -> pd.Timestamp:
    """Parse a window bound. A DATE-ONLY bound ('2016-12-30') means the whole UTC day: as a start it is
    00:00:00, as an end it is 23:59:59.999999999 — so the last day's print is INCLUDED. (Fixes the
    2026-11-10 v1 bug where an end date silently dropped that day's noon/close print.)"""
    ts = pd.Timestamp(x)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    date_only = isinstance(x, str) and len(x.strip()) <= 10
    if end_of_day and (date_only or ts == ts.normalize()):
        ts = ts.normalize() + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    return ts


@dataclass
class PanelBundle:
    lane: str
    prices: pd.DataFrame
    carry: Optional[pd.DataFrame] = None
    aux: Dict[str, pd.DataFrame] = field(default_factory=dict)
    tbill: Optional[pd.Series] = None
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        idx = self.prices.index
        if not isinstance(idx, pd.DatetimeIndex):
            raise TypeError("prices.index must be a DatetimeIndex")
        if idx.tz is None:
            raise ValueError("prices.index must be tz-aware UTC")
        if not idx.is_monotonic_increasing or not idx.is_unique:
            raise ValueError("prices.index must be sorted and unique")
        if self.carry is not None:
            if not self.carry.index.equals(idx) or list(self.carry.columns) != list(self.prices.columns):
                raise ValueError("carry must be aligned to prices (same index and columns)")
        for name, df in self.aux.items():
            if not df.index.equals(idx):
                raise ValueError(f"aux[{name!r}] index must equal prices.index")
        if self.tbill is None:
            self.tbill = pd.Series(0.0, index=idx, name="tbill")
            self.meta.setdefault("tbill_note", "tbill unknown; zero series used")
        elif not self.tbill.index.equals(idx):
            raise ValueError("tbill index must equal prices.index")
        self.meta.setdefault("lane", self.lane)
        self.meta.setdefault("periods_per_year", 252)
        self.meta.setdefault("universe", list(self.prices.columns))

    @property
    def periods_per_year(self) -> int:
        return int(self.meta["periods_per_year"])

    def window(self, start=None, end=None) -> "PanelBundle":
        """Rows with start <= t <= end, inclusive. Date-only bounds cover the whole UTC day (see _as_utc)."""
        mask = pd.Series(True, index=self.prices.index)
        if start is not None:
            mask &= self.prices.index >= _as_utc(start)
        if end is not None:
            mask &= self.prices.index <= _as_utc(end, end_of_day=True)
        return PanelBundle(
            lane=self.lane,
            prices=self.prices.loc[mask],
            carry=None if self.carry is None else self.carry.loc[mask],
            aux={k: v.loc[mask] for k, v in self.aux.items()},
            tbill=self.tbill.loc[mask],
            meta=dict(self.meta),
        )

    def subset(self, cols) -> "PanelBundle":
        """The same panel restricted to instruments `cols` (order kept as given, unknown names refused).
        Aux frames whose columns are exactly the instrument set are subset too; all other aux frames
        (e.g. 'rates' with a USD column, calendars) are passed through untouched."""
        cols = list(cols)
        missing = [c for c in cols if c not in self.prices.columns]
        if missing:
            raise KeyError(f"subset(): unknown instruments {missing}")
        inst = set(self.prices.columns)
        aux = {k: (v[cols] if set(v.columns) == inst else v) for k, v in self.aux.items()}
        meta = dict(self.meta)
        meta["universe"] = cols
        return PanelBundle(
            lane=self.lane,
            prices=self.prices[cols],
            carry=None if self.carry is None else self.carry[cols],
            aux=aux,
            tbill=self.tbill,
            meta=meta,
        )

    def eligible(self) -> pd.DataFrame:
        """Boolean mask (index x instruments): may the instrument be HELD at row t, known at t?
        aux['universe_mask'] if the data layer supplied a point-in-time universe, else price-is-present."""
        m = self.aux.get("universe_mask")
        if m is not None:
            return m.reindex(columns=self.prices.columns).fillna(False).astype(bool) & self.prices.notna()
        return self.prices.notna()

    def returns(self) -> pd.DataFrame:
        """r_t = P_t / P_{t-1} - 1 per instrument (first row NaN)."""
        return self.prices.pct_change(fill_method=None)
