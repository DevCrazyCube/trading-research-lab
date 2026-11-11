"""Offline checks on the WRITTEN lanes (research/factory/data/<LANE>/*.parquet + manifest.json).

No network. A lane that has not been built yet is skipped by the generic tests; the four lanes the
data layer has delivered (FX, FX-EXEC, FX-FRED, MACRO) must exist. The crypto lanes are checked in
test_data_crypto.py.
"""
from __future__ import annotations

import functools
import json

import numpy as np
import pandas as pd
import pytest

from scripts.factory.data import LANES, load_lane, read_manifest
from scripts.factory.data import fx as FX
from scripts.factory.data import sources as S
from scripts.factory.data.common import DATA, RAW, REPO, sha256_file
from scripts.factory.data.panelio import lane_dir, to_utc_index
from scripts.factory.panel import PanelBundle

DELIVERED = ["FX", "FX-EXEC", "FX-FRED", "MACRO"]
FX_LANES = ["FX", "FX-EXEC", "FX-FRED"]

_FXW = {"design": ("2000-01-03", "2016-12-30"), "holdout": ("2017-01-02", None), "full": ("2000-01-03", None),
        "pre_pub": (None, "2012-12-31"), "post_pub": ("2013-01-01", None)}
WINDOWS = {  # DESIGN_v2 §2 (dates inclusive, UTC days)
    "FX": _FXW, "FX-EXEC": _FXW, "FX-FRED": {**_FXW, "pre_euro": ("1971-01-04", "1998-12-31")},
    "MACRO": {"design": ("2017-01-03", "2021-12-31"), "holdout": ("2022-01-03", None), "full": ("2017-01-03", None)},
    "CRYPTO-PERP": {"design": ("2020-07-01", "2023-12-31"), "holdout": ("2024-01-01", None), "post_pub": ("2021-01-01", None)},
    "CRYPTO-SPOT": {"design": ("2018-08-01", "2023-12-31"), "holdout": ("2024-01-01", None), "post_pub": ("2021-01-01", None)},
}

# plausible USD-per-1-FX ranges (lo, hi): narrow for 1999+, wide for the 1971+ H.10 history
RANGE_1999 = {"EUR": (0.8, 1.6), "GBP": (1.0, 2.2), "JPY": (0.006, 0.015), "CHF": (0.5, 1.45), "CAD": (0.6, 1.15),
              "AUD": (0.45, 1.15), "NZD": (0.38, 0.9), "SEK": (0.08, 0.18), "NOK": (0.08, 0.21), "MXN": (0.035, 0.12),
              "ZAR": (0.045, 0.19), "SGD": (0.5, 0.86), "PLN": (0.19, 0.5), "HUF": (0.002, 0.0072), "CZK": (0.022, 0.071),
              "ILS": (0.19, 0.37), "TRY": (0.015, 3.5)}
RANGE_1971 = {"EUR": (0.8, 1.65), "GBP": (1.0, 2.7), "JPY": (0.0025, 0.015), "CHF": (0.22, 1.45), "CAD": (0.6, 1.15),
              "AUD": (0.45, 1.55), "NZD": (0.38, 1.55), "SEK": (0.08, 0.27), "NOK": (0.08, 0.22)}

# FX-FRED: true crisis observations that exceed the generic bounds (documented in the manifest, not clipped)
FRED_CARRY_EPISODES = {"AUD": [("1983-03-09", "1983-03-09")], "NZD": [("1985-03-06", "1985-03-13")],
                       "SEK": [("1992-09-18", "1992-09-21")]}
FRED_RATE_EPISODES = {"NZD": [("1985-03-06", "1985-03-13")], "SEK": [("1992-09-18", "1992-09-21")]}


@functools.lru_cache(maxsize=None)
def panel(lane: str) -> PanelBundle:
    return load_lane(lane)


@functools.lru_cache(maxsize=None)
def manifest(lane: str) -> dict:
    return read_manifest(lane)


def built(lane: str) -> bool:
    return (lane_dir(lane) / "manifest.json").exists()


def need(lane: str) -> None:
    if not built(lane):
        pytest.skip(f"lane {lane} not built yet")


def local_dates(p: PanelBundle, tz: str) -> pd.DatetimeIndex:
    return p.prices.index.tz_convert(tz).tz_localize(None).normalize()


def interval_days(p: PanelBundle, tz: str) -> np.ndarray:
    return pd.Series(local_dates(p, tz)).diff().dt.days.to_numpy(dtype="float64")


LANE_TZ = {"FX": "Europe/Berlin", "FX-EXEC": "Europe/Berlin", "FX-FRED": "America/New_York", "MACRO": "America/New_York",
           "CRYPTO-PERP": "UTC", "CRYPTO-SPOT": "UTC"}


# ------------------------------------------------------------------------------------------- all lanes
@pytest.mark.parametrize("lane", DELIVERED)
def test_delivered_lanes_exist(lane):
    assert built(lane), f"{lane} must be on disk"


@pytest.mark.parametrize("lane", LANES)
def test_manifest_hashes_and_shapes(lane):
    need(lane)
    m = manifest(lane)
    d = lane_dir(lane)
    for rel, rec in m["files"].items():
        assert sha256_file(d / rel) == rec["sha256"], rel
    p = panel(lane)
    assert isinstance(p, PanelBundle)
    assert p.prices.shape == (m["rows"], m["n_columns"]) and list(p.prices.columns) == m["columns"]
    assert p.carry.shape == p.prices.shape and list(p.carry.columns) == list(p.prices.columns)
    assert len(p.tbill) == len(p.prices)
    for name in ("prices.parquet", "carry.parquet", "tbill.parquet"):
        assert name in m["files"]
    assert m["first_print"] == str(p.prices.index[0]) and m["last_print"] == str(p.prices.index[-1])


@pytest.mark.parametrize("lane", LANES)
def test_index_tz_sorted_unique_no_future(lane):
    need(lane)
    p = panel(lane)
    idx = p.prices.index
    assert isinstance(idx, pd.DatetimeIndex) and str(idx.tz) == "UTC"
    assert idx.is_monotonic_increasing and idx.is_unique
    assert idx[-1] <= pd.Timestamp.now(tz="UTC"), "a print is stamped in the future"
    assert p.carry.index.equals(idx) and p.tbill.index.equals(idx)
    for name, df in p.aux.items():
        assert df.index.equals(idx), name


@pytest.mark.parametrize("lane", LANES)
def test_design_and_holdout_windows_non_empty(lane):
    need(lane)
    p = panel(lane)
    for name, (a, b) in WINDOWS[lane].items():
        w = p.window(a, b)
        assert len(w.prices) >= 100, f"{lane} window {name} has {len(w.prices)} rows"
        assert w.prices.notna().any(axis=1).all(), f"{lane} window {name}: a row without any price"
        assert w.eligible().any(axis=1).mean() > 0.99, f"{lane} window {name}: rows with nothing eligible"
        if w.carry is not None:
            assert w.carry.notna().any(axis=1).mean() > 0.99, f"{lane} window {name}: rows without any carry"
    # the holdout must start exactly where the design ends (no overlap)
    des, hold = WINDOWS[lane]["design"], WINDOWS[lane]["holdout"]
    wd, wh = p.window(*des), p.window(*hold)
    assert wd.prices.index[-1] < wh.prices.index[0]


@pytest.mark.parametrize("lane", LANES)
def test_meta_contract(lane):
    need(lane)
    p = panel(lane)
    meta = p.meta
    assert meta["lane"] == lane
    assert meta["periods_per_year"] == (365 if lane.startswith("CRYPTO") else 252)
    assert isinstance(meta["print_convention"], str) and len(meta["print_convention"]) > 80
    assert (REPO / meta["source_manifest"]).exists()
    groups = meta["universe_groups"]
    assert isinstance(groups, dict) and groups
    for g, members in groups.items():
        assert members and set(members) <= set(p.prices.columns), g
    if "exec_prices" in p.aux:
        assert meta["exec_prices_strictly_after_decision"] is True
        assert not p.aux["exec_prices"].equals(p.prices)
    else:
        assert "exec_prices_strictly_after_decision" not in meta
    if "universe_mask" in p.aux:
        um = p.aux["universe_mask"]
        assert (um.dtypes == bool).all() and list(um.columns) == list(p.prices.columns)
        assert not (um & p.prices.isna()).to_numpy().any(), "mask True where there is no price"


@pytest.mark.parametrize("lane", LANES)
def test_no_credentials_in_logs_or_manifests(lane):
    need(lane)
    env = REPO / ".env"
    if not env.exists():
        pytest.skip("no .env")
    from scripts.factory.data.common import load_env_value
    secrets = [load_env_value("ALPACA_API_KEY_ID"), load_env_value("ALPACA_API_SECRET_KEY")]
    blobs = [(lane_dir(lane) / "manifest.json").read_text()]
    for log in list(RAW.glob("*/_fetch_log.jsonl")) + list(RAW.glob("logs/*.log")):
        blobs.append(log.read_text(errors="ignore"))
    for b in blobs:
        for s in secrets:
            assert s not in b


# ---------------------------------------------------------------------------------------------- FX lanes
@pytest.mark.parametrize("lane", FX_LANES)
def test_fx_magnitudes_plausible(lane):
    need(lane)
    p = panel(lane)
    rng = RANGE_1971 if lane == "FX-FRED" else RANGE_1999
    assert set(p.prices.columns) <= set(rng)
    for c in p.prices.columns:
        s = p.prices[c].dropna()
        lo, hi = rng[c]
        assert s.min() >= lo and s.max() <= hi, f"{lane} {c}: [{s.min()}, {s.max()}] outside [{lo}, {hi}]"
    # one-day moves: the ECB/H.10 series have no splice errors (TRY redenomination, euro changeover ...).
    # The only moves above 25 % are two real lira events: the float of 22 Feb 2001 and 21 Dec 2021.
    r = p.prices.pct_change(fill_method=None).abs()
    assert r.drop(columns=["TRY"], errors="ignore").max().max() < 0.25
    if "TRY" in r.columns:
        big = r.index[(r["TRY"] > 0.25).to_numpy()]
        assert [str(d.date()) for d in big] == ["2001-02-22", "2021-12-21"]


def test_fx_columns_and_groups():
    need("FX")
    p = panel("FX")
    assert list(p.prices.columns) == ["EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK", "MXN", "ZAR", "SGD",
                                      "PLN", "HUF", "CZK", "ILS", "TRY"]
    g = p.meta["universe_groups"]
    assert g["G10"] == ["EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK"]
    assert g["EM"] == ["MXN", "ZAR", "PLN", "HUF", "CZK", "ILS"]
    assert g["SENSITIVITY"] == ["TRY"]
    # SGD: no defensible rate -> loaded, but never in a universe group, never eligible, carry all NaN
    assert all("SGD" not in v for v in g.values())
    assert p.carry["SGD"].isna().all() and p.aux["rates"]["SGD"].isna().all()
    assert not p.eligible()["SGD"].any()
    assert "SGD" in p.meta["excluded_from_universe_groups"]
    # index = 14:15 Europe/Berlin
    loc = p.prices.index.tz_convert("Europe/Berlin")
    assert ((loc.hour == 14) & (loc.minute == 15)).all()
    assert str(p.prices.index[0]) == "1999-01-04 13:15:00+00:00"


@pytest.mark.parametrize("lane", FX_LANES)
def test_fx_rates_decimal_bounds_and_columns(lane):
    need(lane)
    p = panel(lane)
    r = p.aux["rates"]
    assert "EUR" in r.columns and "USD" in r.columns
    assert list(r.columns) == list(p.prices.columns) + ["USD"]
    bad = (r <= -0.05) | (r >= 1.0)
    if lane != "FX-FRED":
        assert not bad.to_numpy().any(), "a rate outside (-0.05, 1.0) decimal per year"
    else:
        # only the documented crisis prints (Riksbank 500 % in Sep 1992, NZ overnight cash in Mar 1985)
        cells = [(c, d) for c in r.columns for d in r.index[bad[c].to_numpy()]]
        assert cells, "expected the documented 1985/1992 observations"
        for c, d in cells:
            day = d.tz_convert("America/New_York").tz_localize(None).normalize()
            assert any(pd.Timestamp(a) <= day <= pd.Timestamp(b) for a, b in FRED_RATE_EPISODES.get(c, [])), (c, d)
        doc = manifest(lane)["rates_above_100pct_per_year"]["per_currency"]
        assert set(doc) == set(FRED_RATE_EPISODES) and sum(v["prints"] for v in doc.values()) == len(cells)
    # sanity: these are rates in decimals, not per cent
    assert r["USD"].max() < 0.25 and r["USD"].min() > 0
    assert abs(float(r["USD"].loc["2007-06-01":"2007-06-30"].mean()) - 0.0525) < 0.002


@pytest.mark.parametrize("lane", FX_LANES)
def test_fx_carry_per_day_bound(lane):
    need(lane)
    p = panel(lane)
    days = interval_days(p, LANE_TZ[lane])
    per_day = p.carry.div(days, axis=0).abs()
    big = per_day >= 0.002
    if lane != "FX-FRED":
        assert not big.to_numpy().any()
    else:
        for c in p.carry.columns:
            for d in p.carry.index[big[c].to_numpy()]:
                day = d.tz_convert("America/New_York").tz_localize(None).normalize()
                assert any(pd.Timestamp(a) <= day <= pd.Timestamp(b) for a, b in FRED_CARRY_EPISODES.get(c, [])), (c, d)
    assert np.isnan(p.carry.iloc[0]).all() and np.isnan(p.tbill.iloc[0])      # no previous print on row 0


def _usd_accrual(dates: pd.DatetimeIndex) -> np.ndarray:
    """Effective fed funds of the last calendar day before each print date (decimal) - the accrual rate."""
    dff = S.read_fred("DFF").dropna()
    pos = np.searchsorted(dff.index.values, dates.values, side="left") - 1
    return dff.to_numpy()[pos] / 100.0


@pytest.mark.parametrize("lane", ["FX", "FX-FRED"])
def test_fx_carry_and_tbill_identity(lane):
    """carry = (i_fx - i_usd) * days / 360 and tbill = i_usd * days / 360, where i_usd is the ACCRUAL rate
    (DFF of the last calendar day before the print). On FX the USD column of aux['rates'] is a different,
    older number (signal input), so the identity is checked against the raw DFF file."""
    need(lane)
    p = panel(lane)
    r = p.aux["rates"]
    days = interval_days(p, LANE_TZ[lane])
    usd = _usd_accrual(local_dates(p, LANE_TZ[lane]))
    pd.testing.assert_series_equal(p.tbill, pd.Series(usd * days / 360.0, index=p.prices.index, name="tbill"),
                                   check_exact=False, rtol=0, atol=1e-15)
    for c in p.prices.columns:
        want = (r[c] - usd) * days / 360.0
        pd.testing.assert_series_equal(p.carry[c], want.rename(c), check_exact=False, rtol=0, atol=1e-15)
        # equivalently, without any raw file: carry = rates[c] * days / 360 - tbill
        pd.testing.assert_series_equal(p.carry[c], (r[c] * days / 360.0 - p.tbill).rename(c), check_exact=False, rtol=0, atol=1e-15)
    if lane == "FX-FRED":                                  # noon New York: the one-day-lagged rate IS the signal rate
        assert np.allclose(r["USD"].to_numpy(), usd, rtol=0, atol=1e-15)
        assert "usd_rate_asymmetry" not in p.meta
    else:
        assert "usd_rate_asymmetry" in p.meta and not np.allclose(r["USD"].to_numpy(), usd, rtol=0, atol=1e-15)
    assert set(np.unique(days[1:]).astype(int)) <= set(range(1, 20))


def _us_business_days() -> pd.DatetimeIndex:
    """Federal Reserve business days, rebuilt here from the raw H.10 files (independent of the builder)."""
    days = set()
    for sid in ("DEXUSEU", "DEXUSUK", "DEXJPUS", "DEXSZUS", "DEXCAUS", "DEXUSAL", "DEXUSNZ", "DEXSDUS", "DEXNOUS",
                "DEXMXUS", "DEXSFUS", "DEXSIUS"):
        days |= set(S.read_fred(sid).dropna().index)
    cal = pd.DatetimeIndex(sorted(days))
    return cal.append(pd.bdate_range(cal[-1] + pd.Timedelta(days=1), pd.Timestamp.now().normalize()))


@pytest.mark.parametrize("lane", ["FX", "FX-EXEC"])
def test_fx_usd_signal_rate_was_published_before_the_print(lane):
    """aux['rates']['USD'] on a row = DFF of the business day TWO before the print date: the effective fed
    funds rate of business day b comes out on the next business day at ~09:00 New York, after that day's
    14:15 Berlin fixing, so the freshest public value at a print is the one from two business days back."""
    need(lane)
    p = panel(lane)
    usd = p.aux["rates"]["USD"]
    assert usd.notna().all()
    dates = local_dates(p, "Europe/Berlin")
    dff = S.read_fred("DFF")
    cal = _us_business_days()
    c = cal.values
    iL = np.searchsorted(c, dates.values, side="left") - 1
    L, b = cal[iL], cal[iL - 1]
    assert (L < dates).all() and (b < L).all()
    # the rate used is that of b, and b's rate was released on L (the next business day), a day BEFORE the print
    assert np.allclose(usd.to_numpy(), dff.reindex(b).to_numpy() / 100.0, rtol=0, atol=1e-15)
    lag = (dates - b).days
    assert lag.min() == 2 and lag.max() <= 7
    # ordinary weeks, in plain words: Wednesday's print carries Monday's rate, Monday's carries last Thursday's
    wd = dates.day_of_week
    for k in np.flatnonzero((wd == 2) & (lag == 2))[::150]:
        assert usd.iloc[k] == pytest.approx(dff.loc[dates[k] - pd.Timedelta(days=2)] / 100.0) and (dates[k] - pd.Timedelta(days=2)).day_of_week == 0
    for k in np.flatnonzero((wd == 0) & (lag == 4))[::150]:
        assert usd.iloc[k] == pytest.approx(dff.loc[dates[k] - pd.Timedelta(days=4)] / 100.0) and (dates[k] - pd.Timedelta(days=4)).day_of_week == 3
    # a US holiday the day before the print pushes the usable rate further back (Thanksgiving 2024: Friday's
    # print uses Tuesday's rate, because Wednesday's rate was only released on Friday morning in New York)
    k = dates.searchsorted(pd.Timestamp("2024-11-29"))
    assert dates[k] == pd.Timestamp("2024-11-29") and b[k] == pd.Timestamp("2024-11-26")
    # it is one business day OLDER than the accrual rate that carry and tbill use
    acc = _usd_accrual(dates)
    differs = np.abs(usd.to_numpy() - acc) > 1e-12
    assert 0.2 < differs.mean() < 0.8                      # the rate moves most days; equal only when it did not
    assert "one extra business day" in manifest(lane)["rate_series"]["USD"]["asymmetry"]


@pytest.mark.parametrize("lane", FX_LANES)
def test_fx_rates_are_lagged_one_day(lane):
    """aux['rates'] at a print must equal the source observation dated strictly BEFORE the print's date."""
    need(lane)
    p = panel(lane)
    dates = local_dates(p, LANE_TZ[lane])
    dff = S.read_fred("DFF").dropna()
    est = S.read_ecb_rate("ESTR").dropna()
    rng = np.random.default_rng(7)
    for k in rng.choice(np.arange(5, len(dates)), size=300, replace=False):
        d = dates[k]
        src = dff[dff.index < d]
        assert src.index[-1] < d
        if lane == "FX-FRED":                               # FX / FX-EXEC: see the published-before-the-print test
            assert p.aux["rates"]["USD"].iloc[k] == pytest.approx(src.iloc[-1] / 100.0, abs=1e-12)
        if d > pd.Timestamp("2019-10-10"):
            e = est[est.index < d]
            assert p.aux["rates"]["EUR"].iloc[k] == pytest.approx(e.iloc[-1] / 100.0, abs=1e-12)


@pytest.mark.parametrize("lane", FX_LANES)
def test_fx_cpi_and_oil_availability(lane):
    need(lane)
    p = panel(lane)
    cpi = p.aux["cpi"]
    assert list(cpi.columns) == list(p.prices.columns) + ["USD"]
    assert (cpi.min() > 0).all()
    dates = local_dates(p, LANE_TZ[lane])

    def at(day: str, col: str) -> float:
        k = dates.searchsorted(pd.Timestamp(day))
        assert dates[k] == pd.Timestamp(day), day
        return float(cpi[col].iloc[k])

    us = S.read_bis_cpi("US")
    au = S.read_bis_cpi("AU")
    # monthly: the January 2010 index is usable from 1 March 2010, the February one from 1 April
    assert at("2010-03-01", "USD") == pytest.approx(us.loc["2010-01-01"])
    assert at("2010-02-26", "USD") == pytest.approx(us.loc["2009-12-01"])
    assert at("2010-03-31", "USD") == pytest.approx(us.loc["2010-01-01"])
    assert at("2010-04-01", "USD") == pytest.approx(us.loc["2010-02-01"])
    # quarterly (AUD): Q1 2010 is usable from 1 May 2010; until then Q4 2009
    assert at("2010-04-30", "AUD") == pytest.approx(au.loc["2009-10-01"])
    assert at("2010-05-03", "AUD") == pytest.approx(au.loc["2010-01-01"])
    # oil: level, lagged one day; the non-positive settlement of 2020-04-20 (-36.98) is NaN before the
    # <= 3-print forward-fill, so the 2020-04-21 print repeats the last positive level (17 April)
    oil = p.aux["oil"]["WTI"]
    wti = S.read_fred("DCOILWTICO").dropna()
    assert wti.loc["2020-04-20"] == pytest.approx(-36.98) and int((wti <= 0).sum()) == 1
    wti = wti[wti > 0]
    k = dates.searchsorted(pd.Timestamp("2020-04-21"))
    assert dates[k] == pd.Timestamp("2020-04-21")
    assert oil.iloc[k] == pytest.approx(wti.loc["2020-04-17"]) and oil.iloc[k + 1] == pytest.approx(wti.loc["2020-04-21"])
    assert (oil.dropna() > 0).all()
    o = manifest(lane)["oil_series"]
    assert o["non_positive_observations_set_to_nan"] == {"2020-04-20": -36.98} and o["non_positive_observations_set_to_nan_count"] == 1
    rng = np.random.default_rng(11)
    start = dates.searchsorted(pd.Timestamp("1987-01-01"))
    for j in rng.choice(np.arange(max(start, 5), len(dates)), size=200, replace=False):
        if np.isnan(oil.iloc[j]):
            continue
        src = wti[wti.index < dates[j]]
        assert oil.iloc[j] == pytest.approx(src.iloc[-1])


def test_fx_prices_match_raw_ecb():
    need("FX")
    p = panel("FX")
    dates = local_dates(p, "Europe/Berlin")
    usd = S.read_ecb_exr("USD")
    jpy = S.read_ecb_exr("JPY")
    pln = S.read_ecb_exr("PLN")
    for day in ("1999-01-04", "2008-10-10", "2015-01-15", "2020-03-18", "2026-11-09"):
        k = dates.searchsorted(pd.Timestamp(day))
        assert dates[k] == pd.Timestamp(day)
        assert p.prices["EUR"].iloc[k] == pytest.approx(usd.loc[day])
        assert p.prices["JPY"].iloc[k] == pytest.approx(usd.loc[day] / jpy.loc[day])
        assert p.prices["PLN"].iloc[k] == pytest.approx(usd.loc[day] / pln.loc[day])
    assert p.prices["EUR"].iloc[0] == pytest.approx(1.1789)          # the first euro fixing, 4 Jan 1999


def test_fx_exec_prints_are_after_the_decision():
    need("FX-EXEC")
    p = panel("FX-EXEC")
    assert p.meta["exec_prices_strictly_after_decision"] is True
    dates = local_dates(p, "Europe/Berlin")
    dec, exe = FX.exec_after_decision(dates)             # raises unless noon NY > 14:15 Berlin on every row
    assert dec.equals(p.prices.index)
    gap = (exe - dec).total_seconds() / 3600.0
    assert gap.min() >= 2.75 and gap.max() <= 4.75
    assert exe.equals(to_utc_index(dates, "12:00", "America/New_York"))
    # every row date is a date of BOTH sources, and the exec price is the raw H.10 value of that same date
    ecb = S.read_ecb_exr("USD").dropna()
    eu = S.read_fred("DEXUSEU").dropna()
    jp = S.read_fred("DEXJPUS").dropna()
    assert dates.isin(ecb.index).all() and dates.isin(eu.index).all()
    e = p.aux["exec_prices"]
    assert list(e.columns) == list(p.prices.columns) == FX.EXEC_LANE_COLS
    assert np.allclose(e["EUR"].to_numpy(), eu.reindex(dates).to_numpy())
    assert np.allclose(e["JPY"].to_numpy(), (1.0 / jp.reindex(dates)).to_numpy())
    assert e.notna().all().all()
    # same instrument, same day, a few hours apart: the two prints are close but not identical
    rel = (e / p.prices - 1.0).abs()
    assert rel.median().max() < 0.005 and (rel.to_numpy() > 0).mean() > 0.9


def test_fx_exec_carry_is_the_fx_lane_carry_summed_over_the_same_dates():
    need("FX")
    need("FX-EXEC")
    full, ex = panel("FX"), panel("FX-EXEC")
    fd, ed = local_dates(full, "Europe/Berlin"), local_dates(ex, "Europe/Berlin")
    grp = np.searchsorted(ed.values, fd.values, side="left")
    keep = grp < len(ed)
    for c in ("EUR", "JPY", "AUD", "MXN", "ZAR"):
        s = pd.Series(full.carry[c].to_numpy()[keep])
        tot = s.groupby(grp[keep]).sum(min_count=1)
        anynan = s.isna().groupby(grp[keep]).any()
        want = tot.where(~anynan).reindex(range(len(ed))).to_numpy()
        got = ex.carry[c].to_numpy()
        assert np.isnan(got[0])
        assert np.allclose(got[1:], want[1:], rtol=0, atol=1e-15, equal_nan=True)
    days = interval_days(ex, "Europe/Berlin")
    tb = pd.Series(full.tbill.to_numpy()[keep]).groupby(grp[keep]).sum(min_count=1).reindex(range(len(ed))).to_numpy()
    assert np.allclose(ex.tbill.to_numpy()[1:], tb[1:], rtol=0, atol=1e-15, equal_nan=True)
    assert days[1:].min() >= 1


def test_fx_fred_coverage_and_index():
    need("FX-FRED")
    p = panel("FX-FRED")
    m = manifest("FX-FRED")
    loc = p.prices.index.tz_convert("America/New_York")
    assert ((loc.hour == 12) & (loc.minute == 0)).all()
    assert list(p.prices.columns) == ["EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK"]
    assert p.prices["EUR"].first_valid_index() == pd.Timestamp("1999-01-04 17:00", tz="UTC")
    assert str(p.prices.index[0]) == "1971-01-04 17:00:00+00:00"
    cov = m["carry_coverage_by_decade"]
    assert set(cov) == set(p.prices.columns)
    for c in ("GBP", "CHF", "CAD", "SEK"):
        assert all(v["share"] is None or v["share"] > 0.99 for v in cov[c].values())
    assert cov["NOK"]["1970s"]["share"] == 0.0 and cov["NZD"]["1970s"]["share"] == 0.0
    # inversion check against the raw files
    dates = local_dates(p, "America/New_York")
    uk, sz = S.read_fred("DEXUSUK"), S.read_fred("DEXSZUS")
    k = dates.searchsorted(pd.Timestamp("1985-02-26"))
    assert p.prices["GBP"].iloc[k] == pytest.approx(uk.loc["1985-02-26"])
    assert p.prices["CHF"].iloc[k] == pytest.approx(1.0 / sz.loc["1985-02-26"])


def test_jpy_gap_fill_is_flagged():
    need("FX")
    m = manifest("FX")
    j = m["rate_series"]["JPY"]
    assert "IRSTCI01JPM156N" in j["series"] and len(j["gap_fill"]["windows"]) == 3
    assert [w["after"] for w in j["gap_fill"]["windows"]] == ["1999-02-11", "2001-03-18", "2013-04-03"]
    p = panel("FX")
    r = p.aux["rates"]["JPY"]
    assert r.loc["2003-01-01":"2005-12-31"].abs().max() < 0.001            # ~0 % during QE
    assert r.notna().iloc[1:].all()


# ------------------------------------------------------------------------------------------------- MACRO
def test_macro_shape_and_classes():
    need("MACRO")
    p = panel("MACRO")
    # 40 ETFs: the 41 of DESIGN v2 §2 minus CPER (thin trading; conductor ruling 2026-11-10)
    assert list(p.prices.columns) == [s for s in S.MACRO_ETFS if s != "CPER"] and p.prices.shape[1] == 40
    assert "CPER" not in p.prices.columns and "CPER" not in p.meta["asset_class_of"]
    assert "CPER" in manifest("MACRO")["exclusions"] and "CPER" in p.meta["excluded_instruments"]
    assert p.prices.notna().all().all() and (p.prices > 0).all().all()
    assert str(p.prices.index[0]) == "2016-01-04 21:00:00+00:00"
    loc = p.prices.index.tz_convert("America/New_York")
    assert ((loc.hour == 16) & (loc.minute == 0)).all() and (loc.day_of_week < 5).all()
    ac = p.meta["asset_class_of"]
    assert set(ac) == set(p.prices.columns)
    assert set(ac.values()) == {"equity_region", "equity_sector", "bond", "commodity", "real_estate"}
    equities = {"SPY", "QQQ", "IWM", "EFA", "EEM", "VGK", "EWJ", "EWU", "EWG", "FXI", "INDA", "EWZ", "EWA", "EWC", "EWY",
                "EWT", "XLE", "XLF", "XLK", "XLV", "XLU", "XLI", "XLP", "XLY", "XLB"}
    for sym, label in ac.items():
        assert ("equity" in label) == (sym in equities), sym
    g = p.meta["universe_groups"]
    for label in set(ac.values()):
        assert g[label] == [s for s in p.prices.columns if ac[s] == label]
    assert [len(g[k]) for k in ("equity_region", "equity_sector", "bond", "commodity", "real_estate")] == [16, 9, 8, 6, 1]
    assert g["commodity"] == ["GLD", "SLV", "USO", "UNG", "DBC", "DBA"] and len(g["ALL"]) == 40


def test_macro_carry_is_minus_the_funding_rate():
    need("MACRO")
    p = panel("MACRO")
    r = p.aux["rates"]["USD"]
    days = interval_days(p, "America/New_York")
    want = -(r * days / 360.0)
    for c in p.prices.columns:
        pd.testing.assert_series_equal(p.carry[c], want.rename(c), check_exact=False, rtol=0, atol=1e-15)
    pos = (r > 0).to_numpy() & ~np.isnan(days)
    assert pos.sum() == len(r) - 1                                 # fed funds was positive on every session
    assert (p.carry.to_numpy()[pos] < 0).all()                     # financing a funded long costs money
    assert (p.tbill.to_numpy()[pos] > 0).all()
    assert np.allclose((p.carry["SPY"] + p.tbill).to_numpy()[1:], 0.0, atol=1e-15)
    assert r.max() < 0.07 and r.min() > 0
    # lag: Monday's rate is the last DFF observation before Monday (FRED carries Friday's rate over the weekend)
    dff = S.read_fred("DFF").dropna()
    dates = local_dates(p, "America/New_York")
    for k in (1, 500, 1500, 2700):
        assert r.iloc[k] == pytest.approx(dff[dff.index < dates[k]].iloc[-1] / 100.0)


def test_macro_aux_and_raw_match():
    need("MACRO")
    p = panel("MACRO")
    assert set(p.aux) >= {"raw_close", "volume", "trade_count", "usd_per_eur", "rates"}
    assert (p.aux["raw_close"] > 0).all().all() and (p.aux["volume"] > 0).all().all()
    # a zero-trade session would be a missing print (forward-filled <= 3 and counted): none of the 40 has one
    zero = (p.aux["volume"] <= 0) | (p.aux["trade_count"] <= 0)
    gaps = manifest("MACRO")["price_gaps"]["per_instrument"]
    assert not zero.to_numpy().any()
    assert all(gaps[c] == {"missing_prints": 0, "ffilled": 0, "left_nan": 0} for c in p.prices.columns)
    assert manifest("MACRO")["thin_trading_warning"] == {}
    eur = p.aux["usd_per_eur"]["usd_per_eur"]
    assert eur.notna().all() and 0.9 < eur.min() and eur.max() < 1.35
    # the ECB fixing of the same date is used when one exists
    ecb = S.read_ecb_exr("USD").dropna()
    dates = local_dates(p, "America/New_York")
    both = dates.isin(ecb.index)
    assert both.mean() > 0.98
    assert np.allclose(eur.to_numpy()[both], ecb.reindex(dates[both]).to_numpy())
    # prices are the vendor bars: first page, first SPY bars
    page = json.loads((RAW / "alpaca" / "bars_1Day_all_page000.json").read_text())
    rawp = json.loads((RAW / "alpaca" / "bars_1Day_raw_page000.json").read_text())
    sym = next(iter(page["bars"]))
    for bar, rbar in list(zip(page["bars"][sym], rawp["bars"][sym]))[:25]:
        ts = pd.Timestamp(bar["t"]).tz_convert("America/New_York").tz_localize(None).normalize()
        k = dates.searchsorted(ts)
        assert dates[k] == ts
        assert p.prices[sym].iloc[k] == pytest.approx(bar["c"])
        assert p.aux["raw_close"][sym].iloc[k] == pytest.approx(rbar["c"])
        assert p.aux["volume"][sym].iloc[k] == pytest.approx(rbar["v"])
    per = manifest("MACRO")["per_etf"]
    assert all(v["first_bar"] == "2016-01-04" and v["sessions_missing_vs_union"] == 0 for v in per.values())
