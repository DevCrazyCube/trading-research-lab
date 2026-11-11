"""Synthetic PanelBundles for the strategy-library tests (builder B2) — and the tests of the builders.

No network, no real data: seeded random walks with different drifts / volatilities per instrument, a
common factor, step-function policy rates (so ties occur, as in reality), monthly CPI steps, an oil
series, late listings, a price gap, a delisting, point-in-time universe masks. One builder per lane of
DESIGN_v2 §2, each carrying the `meta` keys the rules read (`periods_per_year`, `universe_groups`,
`asset_class_of`). Sizes stay far below 3,000 x 30.

The helpers `truncate` and `scramble_future` are the two probes of the no-lookahead tests:
`truncate(panel, k)` keeps rows <= k (the future does not exist); `scramble_future(panel, k, seed)`
keeps rows <= k and REGENERATES everything after k (prices re-anchored at the last honest price, every
other frame replaced by fresh noise, no NaN left) — the same idea as `audit.future_scramble_audit`.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
import pytest

from scripts.factory.panel import PanelBundle

G10 = ["EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK"]
EM = ["MXN", "ZAR", "SGD", "PLN", "HUF", "CZK", "ILS"]
MACRO_CLASSES = {
    "SPY": "equity", "QQQ": "equity", "EFA": "equity", "EEM": "equity", "XLE": "equity", "XLF": "equity",
    "IEF": "bond", "TLT": "bond", "LQD": "bond", "HYG": "bond",
    "GLD": "commodity", "USO": "commodity", "DBC": "commodity",
    "VNQ": "real_estate",
}
LANES = ("FX", "FX-FRED", "MACRO", "CRYPTO-PERP", "CRYPTO-SPOT")


# --------------------------------------------------------------------------------------------------
# calendars
# --------------------------------------------------------------------------------------------------
def weekday_index(start: str, n: int, hour: int, minute: int = 0, seed: int = 0,
                  holidays_per_year: int = 6) -> pd.DatetimeIndex:
    """n Monday-Friday prints from `start` (UTC), with 1 January, 25 December and a few seeded random
    weekdays per year removed, stamped at hour:minute UTC."""
    days = pd.bdate_range(start, periods=int(n * 1.08) + 40)
    rng = np.random.default_rng(seed + 991)
    keep = np.ones(len(days), dtype=bool)
    keep &= ~((days.month == 1) & (days.day == 1))
    keep &= ~((days.month == 12) & (days.day == 25))
    n_random = int(holidays_per_year * len(days) / 252)
    keep[rng.choice(len(days), size=n_random, replace=False)] = False
    keep[0] = True
    days = days[keep][:n]
    assert len(days) == n
    return (days + pd.Timedelta(hours=hour, minutes=minute)).tz_localize("UTC")


def daily_index(start: str, n: int) -> pd.DatetimeIndex:
    """n consecutive calendar days at 00:00 UTC (the crypto print)."""
    return pd.date_range(start, periods=n, freq="D", tz="UTC")


def _calendar_days(index: pd.DatetimeIndex) -> np.ndarray:
    d = index.tz_localize(None).normalize()
    out = np.zeros(len(d))
    out[1:] = (d[1:] - d[:-1]).days
    return out


# --------------------------------------------------------------------------------------------------
# generators
# --------------------------------------------------------------------------------------------------
def _random_walk(rng, index, cols, daily_vol, drift_ann, ppy, factor_load=0.5, p0=None) -> pd.DataFrame:
    n, m = len(index), len(cols)
    common = rng.standard_normal(n)
    own = rng.standard_normal((n, m))
    load = np.full(m, factor_load)
    shocks = load * common[:, None] + np.sqrt(1.0 - load ** 2) * own
    rets = shocks * np.asarray(daily_vol) + np.asarray(drift_ann) / ppy
    rets[0] = 0.0
    start = rng.uniform(0.5, 150.0, size=m) if p0 is None else np.asarray(p0, dtype=float)
    return pd.DataFrame(start * np.exp(np.cumsum(rets, axis=0)), index=index, columns=cols)


def _step_rates(rng, index, cols, lo=0.0, hi=0.08, step=0.0025, change_prob=0.012) -> pd.DataFrame:
    """Policy-rate-like step functions on a 25 bp grid (exact ties happen, as in reality)."""
    n, m = len(index), len(cols)
    level = np.round(rng.uniform(lo, hi, size=m) / step) * step
    out = np.empty((n, m))
    for t in range(n):
        move = rng.random(m) < change_prob
        level = np.where(move, level + step * rng.choice([-1.0, 1.0], size=m), level)
        level = np.clip(level, -0.0075, 0.20)
        out[t] = level
    return pd.DataFrame(np.round(out / step) * step, index=index, columns=cols)


def _monthly_cpi(rng, index, cols) -> pd.DataFrame:
    """CPI levels that step once a month (first print of the month), different inflation per column."""
    month = index.year * 12 + index.month
    new_month = np.r_[True, month[1:] != month[:-1]]
    infl = rng.uniform(0.0, 0.07, size=len(cols)) / 12.0
    steps = np.where(new_month[:, None], infl + rng.normal(0.0, 0.002, size=(len(index), len(cols))), 0.0)
    return pd.DataFrame(100.0 * np.exp(np.cumsum(steps, axis=0)), index=index, columns=cols)


def _universe_mask(volume: pd.DataFrame, prices: pd.DataFrame, top: int, min_listed: int = 60,
                   window: int = 30) -> pd.DataFrame:
    """Point-in-time top-`top` by trailing-`window` mean volume among instruments listed >= `min_listed`
    prints — every ingredient is known at t."""
    listed = prices.notna().cumsum() >= min_listed
    trailing = volume.rolling(window, min_periods=window).mean().where(listed & prices.notna())
    rank = trailing.rank(axis=1, ascending=False, method="first")
    return (rank <= top).fillna(False)


def make_fx_panel(n_rows: int = 2000, seed: int = 0, lane: str = "FX") -> PanelBundle:
    rng = np.random.default_rng(seed)
    if lane == "FX":
        cols, start, hour, minute = G10 + EM, "1999-01-04", 13, 15
    else:
        cols, start, hour, minute = ["GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK", "EUR"], "1971-01-04", 17, 0
    index = weekday_index(start, n_rows, hour, minute, seed)
    m = len(cols)
    prices = _random_walk(rng, index, cols, rng.uniform(0.004, 0.011, m), rng.uniform(-0.04, 0.04, m), 252,
                          p0=rng.uniform(0.01, 2.0, m))
    rates = _step_rates(rng, index, cols + ["USD"])
    days = _calendar_days(index)
    carry = rates[cols].sub(rates["USD"], axis=0).mul(days / 360.0, axis=0)
    carry.iloc[0] = np.nan                                       # no accrual period before the first print
    aux = {"rates": rates}
    groups = {"G10": [c for c in cols if c in G10]}
    if lane == "FX":
        prices.loc[index[:250], "ILS"] = np.nan                  # late start
        prices.loc[index[900:903], "HUF"] = np.nan               # a three-print gap
        aux["cpi"] = _monthly_cpi(rng, index, cols + ["USD"])
        aux["oil"] = _random_walk(rng, index, ["WTI"], [0.022], [0.03], 252, factor_load=0.0, p0=[60.0])
        groups["EM"] = list(EM)
    else:
        prices.loc[index[:300], "EUR"] = np.nan                  # EUR exists from 1999 in H.10
    tbill = (rates["USD"] * days / 360.0).rename("tbill")
    meta = {"periods_per_year": 252, "universe_groups": groups, "print_convention": f"synthetic {lane} fix",
            "source_manifest": "synthetic"}
    return PanelBundle(lane=lane, prices=prices, carry=carry, aux=aux, tbill=tbill, meta=meta)


def make_macro_panel(n_rows: int = 1650, seed: int = 0) -> PanelBundle:
    rng = np.random.default_rng(seed + 7)
    cols = list(MACRO_CLASSES)
    index = weekday_index("2016-01-04", n_rows, 21, 0, seed + 7)
    vol_of = {"equity": 0.011, "bond": 0.004, "commodity": 0.016, "real_estate": 0.012}
    drift_of = {"equity": 0.08, "bond": 0.02, "commodity": 0.0, "real_estate": 0.05}
    vols = [vol_of[MACRO_CLASSES[c]] * rng.uniform(0.7, 1.4) for c in cols]
    drifts = [drift_of[MACRO_CLASSES[c]] + rng.uniform(-0.03, 0.03) for c in cols]
    prices = _random_walk(rng, index, cols, vols, drifts, 252, factor_load=0.4, p0=rng.uniform(20, 400, len(cols)))
    rates = _step_rates(rng, index, ["USD"], lo=0.0, hi=0.05)
    days = _calendar_days(index)
    accrual = -(rates["USD"] * days / 360.0)
    carry = pd.DataFrame(np.repeat(accrual.to_numpy()[:, None], len(cols), axis=1), index=index, columns=cols)
    groups: dict = {}
    for c, k in MACRO_CLASSES.items():
        groups.setdefault(k, []).append(c)
    meta = {"periods_per_year": 252, "universe_groups": groups, "asset_class_of": dict(MACRO_CLASSES),
            "print_convention": "synthetic close", "source_manifest": "synthetic"}
    return PanelBundle(lane="MACRO", prices=prices, carry=carry, aux={"rates": rates},
                       tbill=(-accrual).rename("tbill"), meta=meta)


def make_crypto_panel(n_rows: int = 1500, seed: int = 0, lane: str = "CRYPTO-PERP") -> PanelBundle:
    rng = np.random.default_rng(seed + (21 if lane == "CRYPTO-PERP" else 33))
    perp = lane == "CRYPTO-PERP"
    m = 20 if perp else 16
    cols = [f"C{i:02d}USDT" for i in range(m)]
    index = daily_index("2019-09-08" if perp else "2017-08-17", n_rows)
    prices = _random_walk(rng, index, cols, rng.uniform(0.03, 0.06, m), rng.uniform(-0.3, 0.6, m), 365,
                          factor_load=0.7, p0=rng.uniform(0.05, 9000.0, m))
    listing = np.r_[0, 0, 0, np.sort(rng.integers(20, int(n_rows * 0.6), size=m - 3))]
    for j, c in enumerate(cols):
        if listing[j] > 0:
            prices.loc[index[:listing[j]], c] = np.nan
    prices.loc[index[int(n_rows * 0.8):], cols[5]] = np.nan      # a delisting
    size = rng.uniform(0.2, 5.0, m)
    volume = pd.DataFrame(np.exp(rng.normal(0.0, 0.6, (n_rows, m))) * size * 1e7, index=index, columns=cols)
    volume = volume.where(prices.notna())
    aux = {"volume_quote": volume, "universe_mask": _universe_mask(volume, prices, top=12 if perp else 10)}
    if perp:
        funding = pd.DataFrame(rng.normal(0.0003, 0.0006, (n_rows, m)), index=index, columns=cols)
        carry = (-funding).where(prices.notna())
        log_ratio = np.zeros((n_rows, m))
        shocks = rng.normal(0.0, 0.08, (n_rows, m))
        for t in range(1, n_rows):
            log_ratio[t] = 0.97 * log_ratio[t - 1] + shocks[t]
        aux["glsr"] = pd.DataFrame(np.exp(0.3 + log_ratio), index=index, columns=cols).where(prices.notna())
        tbill = pd.Series(0.03 / 360.0, index=index, name="tbill")
    else:
        usd = _step_rates(rng, index, ["USD"], lo=0.0, hi=0.05)["USD"]
        carry = pd.DataFrame(np.repeat((-usd / 360.0).to_numpy()[:, None], m, axis=1), index=index, columns=cols)
        aux["rates"] = usd.to_frame()
        tbill = (usd / 360.0).rename("tbill")
    meta = {"periods_per_year": 365, "universe_groups": {"ALL": cols}, "print_convention": "synthetic 00:00 UTC",
            "source_manifest": "synthetic"}
    return PanelBundle(lane=lane, prices=prices, carry=carry, aux=aux, tbill=tbill, meta=meta)


def mini_panel(prices, carry=None, aux=None, ppy: int = 252, start: str = "2024-01-01", freq: str = "B",
               index: pd.DatetimeIndex = None, meta: dict = None, lane: str = "TEST") -> PanelBundle:
    """A tiny hand-made panel: `prices` (and `carry`, each aux value) is a dict column -> list, or a
    DataFrame. The index is `index` if given, else `len` prints from `start` at frequency `freq` (UTC)."""
    def frame(obj, idx):
        if isinstance(obj, pd.DataFrame):
            return obj
        return pd.DataFrame({k: np.asarray(v, dtype=float) if not isinstance(v[0], (bool, np.bool_))
                             else np.asarray(v, dtype=bool) for k, v in obj.items()}, index=idx)

    n = len(prices) if isinstance(prices, pd.DataFrame) else len(next(iter(prices.values())))
    idx = index if index is not None else pd.date_range(start, periods=n, freq=freq, tz="UTC")
    px = frame(prices, idx)
    m = {"periods_per_year": ppy, "source_manifest": "hand-made"}
    m.update(meta or {})
    return PanelBundle(lane=lane, prices=px, carry=None if carry is None else frame(carry, idx),
                       aux={k: frame(v, idx) for k, v in (aux or {}).items()}, meta=m)


def prices_from_returns(returns, p0: float = 100.0) -> list:
    """Price path whose print-to-print returns are `returns[1:]` (returns[0] is ignored: first print)."""
    out = [p0]
    for r in list(returns)[1:]:
        out.append(out[-1] * (1.0 + r))
    return out


@lru_cache(maxsize=None)
def lane_panel(lane: str, seed: int = 0) -> PanelBundle:
    """The standard synthetic panel of a lane (cached; treat it as read-only)."""
    if lane in ("FX", "FX-FRED"):
        return make_fx_panel(2000, seed, lane)
    if lane == "MACRO":
        return make_macro_panel(1650, seed)
    if lane in ("CRYPTO-PERP", "CRYPTO-SPOT"):
        return make_crypto_panel(1500, seed, lane)
    raise ValueError(lane)


@lru_cache(maxsize=None)
def small_lane_panel(lane: str, seed: int = 0) -> PanelBundle:
    """A small panel per lane for the ML tests: long enough for two yearly refits, few instruments."""
    if lane == "FX":
        return make_fx_panel(1180, seed + 100, "FX").subset(G10[:6] + ["MXN", "ZAR"])
    if lane == "FX-FRED":
        return make_fx_panel(1180, seed + 100, "FX-FRED").subset(["GBP", "JPY", "CHF", "CAD", "AUD", "NZD"])
    if lane == "MACRO":
        return make_macro_panel(1180, seed + 100).subset(["SPY", "EFA", "XLE", "IEF", "TLT", "GLD", "USO", "VNQ"])
    if lane in ("CRYPTO-PERP", "CRYPTO-SPOT"):
        return make_crypto_panel(1560, seed + 100, lane)
    raise ValueError(lane)


# --------------------------------------------------------------------------------------------------
# no-lookahead probes
# --------------------------------------------------------------------------------------------------
def truncate(panel: PanelBundle, k: int) -> PanelBundle:
    """Rows 0..k of the panel (through the conductor's own `window()`)."""
    out = panel.window(end=panel.prices.index[k])
    assert len(out.prices) == k + 1
    return out


def scramble_future(panel: PanelBundle, k: int, seed: int = 0) -> PanelBundle:
    """Same rows <= k; rows > k regenerated: prices are a fresh geometric walk anchored at each
    instrument's last honest price (1.0 if it never had one), no NaN; carry, tbill and every numeric aux
    frame are fresh normals with a random scale (so CPI / oil / ratios can turn NEGATIVE — a rule must not
    raise on that); boolean aux frames are fresh coin flips."""
    rng = np.random.default_rng(seed + 4242)
    n = len(panel.prices) - (k + 1)
    idx = panel.prices.index

    def tail_normal(frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        if n > 0:
            out.iloc[k + 1:] = rng.normal(0.0, rng.uniform(0.001, 5.0), size=(n, frame.shape[1]))
        return out

    prices = panel.prices.copy()
    if n > 0:
        anchor = panel.prices.iloc[:k + 1].ffill().iloc[-1].fillna(1.0).to_numpy()
        vol = rng.uniform(0.005, 0.05, size=prices.shape[1])
        steps = rng.standard_normal((n, prices.shape[1])) * vol
        prices.iloc[k + 1:] = anchor * np.exp(np.cumsum(steps, axis=0))
    carry = None if panel.carry is None else tail_normal(panel.carry)
    aux = {}
    for name, frame in panel.aux.items():
        if all(pd.api.types.is_bool_dtype(t) for t in frame.dtypes):
            out = frame.copy()
            if n > 0:
                out.iloc[k + 1:] = rng.random((n, frame.shape[1])) < 0.5
            aux[name] = out
        else:
            aux[name] = tail_normal(frame.astype(float))
    tbill = panel.tbill.copy()
    if n > 0:
        tbill.iloc[k + 1:] = rng.normal(0.0, 1e-4, size=n)
    return PanelBundle(lane=panel.lane, prices=prices, carry=carry, aux=aux, tbill=tbill, meta=dict(panel.meta))


# --------------------------------------------------------------------------------------------------
# the builders are tested too
# --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lane", LANES)
def test_synthetic_panel_is_a_valid_bundle(lane):
    p = lane_panel(lane)
    assert p.lane == lane and p.meta["periods_per_year"] in (252, 365)
    assert p.prices.shape[0] <= 3000 and p.prices.shape[1] <= 30
    assert str(p.prices.index.tz) == "UTC" and p.prices.index.is_monotonic_increasing
    assert p.carry is not None and p.carry.shape == p.prices.shape
    live = p.prices.notna()
    assert (p.prices.where(live, 1.0) > 0).all().all()
    assert live.iloc[-1].sum() >= 6                              # a real cross-section at the end
    vols = p.returns().std()
    assert vols.max() / vols.min() > 1.5                         # instruments genuinely differ
    assert p.eligible().iloc[-1].sum() >= 6


def test_fx_panel_has_the_declared_aux_and_groups():
    p = lane_panel("FX")
    assert set(p.aux) == {"rates", "cpi", "oil"}
    assert list(p.aux["rates"].columns) == G10 + EM + ["USD"] and "USD" in p.aux["cpi"].columns
    assert p.meta["universe_groups"] == {"G10": G10, "EM": EM}
    assert p.prices["ILS"].iloc[:250].isna().all() and p.prices["HUF"].iloc[900:903].isna().all()
    days = _calendar_days(p.prices.index)
    assert days[1:].min() >= 1 and days.max() >= 3               # weekends and holidays are in the calendar
    weekday = p.prices.index.day_of_week
    assert weekday.max() <= 4


def test_crypto_universe_mask_is_point_in_time():
    p = lane_panel("CRYPTO-PERP")
    mask = p.aux["universe_mask"]
    assert mask.dtypes.eq(bool).all() and mask.sum(axis=1).max() == 12
    assert not mask.iloc[:29].any().any()                        # needs 30 prints of volume
    k = 900
    cut = truncate(p, k)
    again = _universe_mask(cut.aux["volume_quote"], cut.prices, top=12)
    pd.testing.assert_frame_equal(again, mask.iloc[:k + 1])


def test_truncate_and_scramble_keep_the_past_bit_identical():
    p = lane_panel("FX")
    k = 1234
    t, s = truncate(p, k), scramble_future(p, k, seed=1)
    for a, b in ((t.prices, p.prices), (t.carry, p.carry), (t.aux["cpi"], p.aux["cpi"])):
        pd.testing.assert_frame_equal(a, b.iloc[:k + 1])
    for a, b in ((s.prices, p.prices), (s.carry, p.carry), (s.aux["rates"], p.aux["rates"])):
        pd.testing.assert_frame_equal(a.iloc[:k + 1], b.iloc[:k + 1])
    assert s.prices.iloc[k + 1:].notna().all().all()
    assert not np.allclose(s.prices.iloc[k + 1:].to_numpy(), p.prices.iloc[k + 1:].fillna(0.0).to_numpy())
    assert (s.aux["cpi"].iloc[k + 1:] < 0).any().any()           # the scramble does produce hostile values
