"""Offline checks on the written CRYPTO-PERP / CRYPTO-SPOT lanes, against the raw Binance files on disk.
A lane that has not been built yet is skipped (the generic tests in test_data_lanes.py cover whatever
exists). No network."""
from __future__ import annotations

import functools
import io
import json
import zipfile

import numpy as np
import pandas as pd
import pytest

from scripts.factory.data import load_lane, read_manifest
from scripts.factory.data import crypto as C
from scripts.factory.data import sources as S
from scripts.factory.data.common import RAW
from scripts.factory.data.crypto_build import GAP_SPLIT_DAYS, MIN_HISTORY, TOP_N, VOL_WINDOW, base_symbol
from scripts.factory.data.panelio import lane_dir
from scripts.factory.data.universe import pit_universe_mask

CRYPTO = ["CRYPTO-PERP", "CRYPTO-SPOT"]
MARKET = {"CRYPTO-PERP": "perp", "CRYPTO-SPOT": "spot"}
DAY = pd.Timedelta(days=1)
HOUR = pd.Timedelta(hours=1)


@functools.lru_cache(maxsize=None)
def panel(lane):
    return load_lane(lane)


@functools.lru_cache(maxsize=None)
def manifest(lane):
    return read_manifest(lane)


def need(lane):
    if not (lane_dir(lane) / "manifest.json").exists():
        pytest.skip(f"lane {lane} not built yet")


def raw_hourly(market: str, sym: str, month: str) -> pd.DataFrame:
    """One raw monthly 1h archive zip, parsed here independently of the data layer's reader."""
    p = RAW / C.SRC[market] / "archive_klines_1h" / sym / f"{sym}-1h-{month}.zip"
    if not p.exists():
        pytest.skip(f"raw file {p.name} not on disk")
    with zipfile.ZipFile(p) as z:
        txt = z.read(z.namelist()[0]).decode()
    lines = [l.split(",") for l in txt.splitlines() if l and l[0].isdigit()]
    t = np.array([int(l[0]) for l in lines], dtype="int64")
    raw_unit_micro = bool(t.max() > 10**14)
    if raw_unit_micro:
        t = t // 1000
    df = pd.DataFrame({"close": [float(l[4]) for l in lines], "count": [int(l[8]) for l in lines]},
                      index=pd.to_datetime(t, unit="ms", utc=True))
    df.attrs["micro"] = raw_unit_micro
    return df


@pytest.mark.parametrize("lane", CRYPTO)
def test_daily_rows_and_meta(lane):
    need(lane)
    p = panel(lane)
    idx = p.prices.index
    assert (idx.hour == 0).all() and (idx.minute == 0).all()
    assert (np.diff(idx.asi8) == DAY.value).all(), "a calendar day is missing from the row index"
    assert p.meta["periods_per_year"] == 365 and p.meta["exec_prices_strictly_after_decision"] is True
    assert "glsr" not in p.aux                                       # step 5 dropped on the conductor's instruction
    for name in ("universe_mask", "exec_prices", "exec_prices_alt", "volume_quote", "live_at_print", "terminal_return",
                 "settlement_row"):
        assert name in p.aux and list(p.aux[name].columns) == list(p.prices.columns), name
    g = p.meta["universe_groups"]
    assert g["ALL"] == list(p.prices.columns)
    assert g["EVER_IN_MASK"] == [c for c in p.prices.columns if p.aux["universe_mask"][c].any()]
    first = {"CRYPTO-PERP": "2019-09-09", "CRYPTO-SPOT": "2017-08-18"}[lane]
    assert str(idx[0].date()) == first                              # BTCUSDT's first daily candle + 1 day


@pytest.mark.parametrize("lane", CRYPTO)
def test_universe_mask_is_reproducible_and_point_in_time(lane):
    need(lane)
    p = panel(lane)
    top = TOP_N[MARKET[lane]]
    vq, live, um = p.aux["volume_quote"], p.aux["live_at_print"], p.aux["universe_mask"]
    settle = p.aux["settlement_row"]
    vol_mask = pit_universe_mask(vq, top_n=top, min_history=MIN_HISTORY, vol_window=VOL_WINDOW)
    # top-N by trailing volume, AND traded in the hour before the print, AND not the settlement row of a dead instrument
    pd.testing.assert_frame_equal(um, vol_mask & live & ~settle)
    assert um.sum(axis=1).max() <= top
    assert not (um & p.prices.isna()).to_numpy().any()
    # every member has >= 60 traded candles strictly before the row and a complete 30-candle window
    n_before = p.prices.notna().cumsum() - p.prices.notna().astype(int)
    assert (n_before.to_numpy()[um.to_numpy()] >= MIN_HISTORY).all()
    full_window = p.prices.notna().rolling(VOL_WINDOW).sum() == VOL_WINDOW
    assert full_window.to_numpy()[um.to_numpy()].all()
    # truncation on the REAL frame: cut the volume panel at t, the mask up to t is unchanged
    n = len(vq)
    for t in (n // 5, n // 2, n - 400, n - 2):
        cut = pit_universe_mask(vq.iloc[: t + 1], top_n=top, min_history=MIN_HISTORY, vol_window=VOL_WINDOW)
        pd.testing.assert_frame_equal(cut, vol_mask.iloc[: t + 1])
    # ... and scrambling everything after t does not move row t either
    rng = np.random.default_rng(5)
    t = n // 2
    alt = vq.copy()
    tail = alt.iloc[t + 1:].to_numpy(copy=True)
    tail = tail[rng.permutation(len(tail))] * rng.uniform(0.1, 10.0, size=tail.shape)
    alt.iloc[t + 1:] = tail
    m2 = pit_universe_mask(alt, top_n=top, min_history=MIN_HISTORY, vol_window=VOL_WINDOW)
    pd.testing.assert_frame_equal(m2.iloc[: t + 1], vol_mask.iloc[: t + 1])


@pytest.mark.parametrize("lane", CRYPTO)
def test_exec_prints_are_later_and_match_the_raw_hourly_files(lane):
    need(lane)
    p = panel(lane)
    mk = MARKET[lane]
    e, a = p.aux["exec_prices"], p.aux["exec_prices_alt"]
    assert not e.equals(p.prices)
    for month, day in (("2021-06", "2021-06-15"), ("2023-03", "2023-03-02"), ("2025-06", "2025-06-20")):
        h = raw_hourly(mk, "BTCUSDT", month)
        d = pd.Timestamp(day, tz="UTC")
        # decision print = close of the candle that ENDED at D 00:00; exec = one hour later; alt = two hours later
        assert p.prices.loc[d, "BTCUSDT"] == pytest.approx(h.loc[d - HOUR, "close"])
        assert e.loc[d, "BTCUSDT"] == pytest.approx(h.loc[d, "close"])
        assert a.loc[d, "BTCUSDT"] == pytest.approx(h.loc[d + HOUR, "close"])
    # the daily candle file agrees: the candle OPENED at D-1 closes at the row's price
    rest = RAW / C.SRC[mk] / "rest_klines_1d" / "BTCUSDT"
    rows = [r for f in sorted(rest.glob("1d_*.json")) for r in json.loads(f.read_bytes())]
    by_open = {int(r[0]): float(r[4]) for r in rows}
    for day in ("2020-03-13", "2022-11-10", "2026-01-05"):
        d = pd.Timestamp(day, tz="UTC")
        assert p.prices.loc[d, "BTCUSDT"] == pytest.approx(by_open[int((d - DAY).value // 10**6)])
    # relation between the three prints across the whole history (same asset, 1 h / 2 h apart)
    rel = (e["BTCUSDT"] / p.prices["BTCUSDT"] - 1).abs().dropna()
    assert 0 < rel.median() < 0.01 and rel.max() < 0.25
    # independent files agree on the decision print: every disagreement is listed, and they are a handful
    # (Binance's own 2019 daily candles: BTCUSDT 2019-09-24, ETHUSDT 2019-12-11 on the perp venue)
    x = manifest(lane)["decision_print_crosscheck"]
    assert x["rows_compared"] > 100_000
    assert x["mismatches"] == len(x["mismatch_cells"]) <= 1e-4 * x["rows_compared"]
    for cell in x["mismatch_cells"]:
        d = pd.Timestamp(cell["row"])
        assert p.prices.loc[d, cell["instrument"]] == pytest.approx(cell["daily_close"])   # the daily candle is kept


@pytest.mark.parametrize("lane", CRYPTO)
def test_mask_members_have_execution_prints(lane):
    need(lane)
    p = panel(lane)
    um, e, a = p.aux["universe_mask"], p.aux["exec_prices"], p.aux["exec_prices_alt"]
    n = int(um.to_numpy().sum())
    miss = int((um & e.isna()).to_numpy().sum())
    miss_alt = int((um & a.isna()).to_numpy().sum())
    man = manifest(lane)["exec_prints"]
    assert man["mask_cells"] == n and man["mask_cells_without_exec_price"] == miss
    assert man["mask_cells_without_exec_alt_price"] == miss_alt
    assert miss <= 0.0005 * n and miss_alt <= 0.0005 * n, (miss, miss_alt, n)
    # exec prints exist only inside an instrument's traded life
    outside = p.prices.isna() & (e.notna() | a.notna())
    first_row = p.prices.apply(lambda s: s.first_valid_index())
    for c in p.prices.columns[outside.any().to_numpy()]:
        bad = outside.index[outside[c].to_numpy()]
        # allowed only on the day BEFORE the first daily candle closes (listing day: the hourly candle already trades)
        assert (bad < first_row[c]).all(), c


@pytest.mark.parametrize("lane", CRYPTO)
def test_dead_instruments_end_cleanly_never_forward_filled(lane):
    need(lane)
    p = panel(lane)
    e, a, um = p.aux["exec_prices"], p.aux["exec_prices_alt"], p.aux["universe_mask"]
    last_row = p.prices.index[-1]
    dead = [c for c in p.prices.columns if p.prices[c].last_valid_index() < last_row - 2 * DAY]
    assert len(dead) > 20
    settle = p.aux["settlement_row"]
    for c in dead:
        z = p.prices[c].last_valid_index()
        after = p.prices.index > z
        assert p.prices[c][after].isna().all()
        assert e[c][after].isna().all() and a[c][after].isna().all()
        assert not um[c][after].any() and not um.loc[z, c]
        # an instrument that ever had execution prints gets exactly one settlement print, on its last live row
        if e[c].notna().any():
            assert bool(settle.loc[z, c]) and int(settle[c].sum()) == 1
            assert e.loc[z, c] == p.prices.loc[z, c] == a.loc[z, c]
        else:
            assert not settle[c].any()
        assert (p.aux["volume_quote"][c][after].isna()).all()
        if lane == "CRYPTO-PERP":
            assert (p.carry[c][after] == 0.0).all()
        # the last traded daily candle is a real print (volume > 0), not a flat phantom
        assert p.aux["volume_quote"][c].loc[z] > 0
    # no instrument hides a trading break of >= GAP_SPLIT_DAYS days
    valid = p.prices.notna().to_numpy()
    for j, c in enumerate(p.prices.columns):
        pos = np.flatnonzero(valid[:, j])
        assert (np.diff(pos) <= GAP_SPLIT_DAYS).all(), c


def _pnl(w: pd.Series, F: pd.Series) -> pd.Series:
    """The engine's execution-print arithmetic for one instrument (extra_lag = 0, missing_return = 'zero'):
    held_t = w_{t-1}, r_t = F_t / F_{t-1} - 1, a NaN return counts as 0. Written out here so the test does
    not depend on the engine module."""
    r = (F / F.shift(1) - 1.0).fillna(0.0)
    return w.shift(1).fillna(0.0) * r


@pytest.mark.parametrize("lane", CRYPTO)
def test_settlement_prints_book_the_terminal_move(lane):
    need(lane)
    p = panel(lane)
    tr, e, a, um, settle = (p.aux[k] for k in ("terminal_return", "exec_prices", "exec_prices_alt", "universe_mask", "settlement_row"))
    sp = manifest(lane)["settlement_prints"]
    idx, cols = p.prices.index, list(p.prices.columns)
    cells = np.argwhere(settle.to_numpy())
    assert len(cells) == sp["instruments"] > 40 and settle.sum(axis=0).max() == 1
    assert np.isfinite(tr.to_numpy()).all()
    assert not (tr.to_numpy() != 0)[~settle.to_numpy()].any()                 # terminal_return lives on settlement rows only
    assert int((tr != 0).to_numpy().sum()) == sp["nonzero_terminal_return"]
    assert sp["exec_terminal_move_not_bookable"] == []                         # every one has a real print on the previous row
    assert sp["last_live_row_is_the_panel_final_row"] == []                    # no instrument ended on the panel's last row
    no_alt = {x["instrument"] for x in sp["alt_terminal_move_not_bookable"]}
    assert len(no_alt) <= 2
    for i, j in cells:
        c, z = cols[j], idx[i]
        assert z == p.prices[c].last_valid_index() and z < idx[-1]              # the last live row, never the panel's last row
        final = p.prices.iat[i, j]
        assert e.iat[i, j] == final and a.iat[i, j] == final                    # both series go to the same final traded price
        assert not um.iat[i, j]                                                # nothing may be opened on the settlement row
        assert e.iloc[i + 1:, j].isna().all() and a.iloc[i + 1:, j].isna().all()   # NaN afterwards
        prev = e.iat[i - 1, j]                                                  # the last REAL execution print
        assert np.isfinite(prev) and not settle.iat[i - 1, j]
        assert tr.iat[i, j] == pytest.approx(final / prev - 1.0, abs=1e-12)
        assert e.iat[i, j] == pytest.approx(prev * (1.0 + tr.iat[i, j]), rel=1e-12)
        if c in no_alt:
            assert np.isnan(a.iat[i - 1, j])
        else:
            assert final / a.iat[i - 1, j] - 1.0 == pytest.approx(sp["terminal_return_alt"][c], abs=1e-6)
    if lane != "CRYPTO-PERP":
        return
    # LUNAUSDT (Terra, May 2022): the last real 01:00 print is on 12 May (t_last); the settlement print on 13 May.
    c = "LUNAUSDT"
    z = p.prices[c].last_valid_index()
    t_last = z - DAY
    assert str(z.date()) == "2022-05-13" and bool(settle.loc[z, c]) and np.isfinite(e.loc[t_last, c])
    F = e[c]
    held_to_the_end = pd.Series(0.0, index=idx)
    held_to_the_end.loc[pd.Timestamp("2022-04-01", tz="UTC"):t_last] = 1.0      # still long at t_last
    flat_at_t_last = held_to_the_end.copy()
    flat_at_t_last.loc[t_last] = 0.0                                            # target 0 decided at t_last, filled at its 01:00 print
    pnl_held, pnl_flat = _pnl(held_to_the_end, F), _pnl(flat_at_t_last, F)
    assert pnl_held.loc[z] == pytest.approx(tr.loc[z, c]) and pnl_held.loc[z] < -0.99   # loses ~99 % on the settlement row
    assert pnl_flat.loc[z] == 0.0                                               # went flat in time: loses nothing
    assert (pnl_held.loc[z + DAY:] == 0.0).all() and (pnl_flat.loc[z:] == 0.0).all()
    # up to and including t_last the two paths are identical: the only difference is the terminal move
    pd.testing.assert_series_equal(pnl_held.loc[:t_last], pnl_flat.loc[:t_last])
    d0 = pd.Timestamp("2022-05-10", tz="UTC")
    assert (1.0 + pnl_held.loc[d0:z]).prod() < 0.001 < (1.0 + pnl_flat.loc[d0:z]).prod()
    # the same holds on the 02:00 series
    pa = _pnl(held_to_the_end, a[c])
    assert pa.loc[z] == pytest.approx(sp["terminal_return_alt"][c], abs=1e-6) and pa.loc[z] < -0.9
    # the other big ones are booked too
    assert tr["ALPACAUSDT"].max() > 4.0 and abs(tr["FTTUSDT"]).max() > 0.05


def test_perp_phantom_candles_after_delisting_are_not_prints():
    need("CRYPTO-PERP")
    p = panel("CRYPTO-PERP")
    # FTTUSDT: the raw REST file keeps emitting flat zero-trade candles after the delisting
    rest = RAW / C.SRC["perp"] / "rest_klines_1d" / "FTTUSDT"
    rows = [r for f in sorted(rest.glob("1d_*.json")) for r in json.loads(f.read_bytes())]
    zero = [r for r in rows if int(r[8]) == 0]
    assert len(zero) > 1000 and float(zero[0][4]) == pytest.approx(float(zero[-1][4]))   # flat forever
    s = p.prices["FTTUSDT"].dropna()
    last_traded_open = max(int(r[0]) for r in rows if int(r[8]) > 0)
    assert s.index[-1] == pd.Timestamp(last_traded_open, unit="ms", tz="UTC") + DAY
    assert str(s.index[-1].date()) == "2022-11-15" and s.iloc[-1] == pytest.approx(1.59)
    # the last REAL 01:00 print is on 14 Nov; 15 Nov carries the settlement print (the final traded price), then NaN
    ex, settle = p.aux["exec_prices"]["FTTUSDT"], p.aux["settlement_row"]["FTTUSDT"]
    assert ex.where(~settle).last_valid_index() == s.index[-1] - DAY
    assert bool(settle.loc[s.index[-1]]) and ex.loc[s.index[-1]] == pytest.approx(1.59) and ex.last_valid_index() == s.index[-1]
    assert not p.aux["universe_mask"]["FTTUSDT"].loc[s.index[-1]:].any()
    # LUNAUSDT (old Terra contract): one uninterrupted instrument 2021-01 .. 2022-05, nothing afterwards
    l = p.prices["LUNAUSDT"].dropna()
    assert str(l.index[0].date()) == "2021-01-29" and str(l.index[-1].date()) == "2022-05-13"
    assert len(l) == (l.index[-1] - l.index[0]).days + 1
    man = manifest("CRYPTO-PERP")
    assert "FTTUSDT" in man["delisted_symbols_ever_in_mask"] and "LUNAUSDT" in man["delisted_symbols_ever_in_mask"]


def test_perp_carry_is_minus_funding_over_the_exec_interval():
    need("CRYPTO-PERP")
    p = panel("CRYPTO-PERP")
    f = RAW / C.SRC["perp"] / "archive_funding" / "BTCUSDT" / "BTCUSDT-fundingRate-2023-05.zip"
    if not f.exists():
        pytest.skip("raw funding file not on disk")
    with zipfile.ZipFile(f) as z:
        b = z.read(z.namelist()[0])
    cols = ["calc_time", "funding_interval_hours", "last_funding_rate"]
    df = pd.read_csv(io.BytesIO(b), header=0 if b[:1].isalpha() else None, names=None if b[:1].isalpha() else cols)
    t = pd.to_datetime(df["calc_time"], unit="ms", utc=True)
    for day in ("2023-05-10", "2023-05-20", "2023-05-31"):
        d = pd.Timestamp(day, tz="UTC")
        sel = (t > d - DAY + HOUR) & (t <= d + HOUR)             # (01:00 of D-1, 01:00 of D]
        assert int(sel.sum()) == 3
        assert p.carry.loc[d, "BTCUSDT"] == pytest.approx(-float(df["last_funding_rate"][sel.to_numpy()].sum()), abs=1e-12)
        assert p.aux["funding_obs"].loc[d, "BTCUSDT"] == 3
    c = p.carry["BTCUSDT"]
    assert c.abs().max() < 0.02 and -0.001 < c.loc["2020-07-01":].mean() < 0      # longs paid on average
    um = p.aux["universe_mask"]
    held = p.aux["exec_prices"].notna() & p.aux["exec_prices"].shift(1).notna()
    nofund = int((um & held & (p.aux["funding_obs"] == 0)).to_numpy().sum())
    assert nofund <= 0.002 * int(um.to_numpy().sum()), nofund
    assert np.isfinite(p.carry.to_numpy()).all()                  # missing funding is 0.0, never NaN
    # never-in-mask instruments carry no funding at all (not downloaded) and say so
    never = [c for c in p.prices.columns if not um[c].any()]
    assert (p.carry[never] == 0.0).all().all()
    per = manifest("CRYPTO-PERP")["per_symbol"]
    assert all(per[c]["funding_downloaded"] is False for c in never[:50])
    # T-bill leg: effective fed funds of the previous calendar day / 360
    dff = S.read_fred("DFF").dropna()
    for day in ("2021-03-08", "2023-08-15", "2026-06-01"):
        d = pd.Timestamp(day, tz="UTC")
        want = dff[dff.index < pd.Timestamp(day)].iloc[-1] / 100.0 / 360.0
        assert p.tbill.loc[d] == pytest.approx(want, abs=1e-15)


def test_perp_exclusions_and_first_candles():
    need("CRYPTO-PERP")
    p = panel("CRYPTO-PERP")
    man = manifest("CRYPTO-PERP")
    cols = set(p.prices.columns)
    for bad in ("USDCUSDT", "BTCDOMUSDT", "DEFIUSDT", "XAUUSDT", "XAGUSDT", "BTCUSDT_260925", "BTCBUSD", "ETHUSDC",
                "PAXGUSDT", "XAUTUSDT"):
        assert bad not in cols
    assert {"BTCUSDT", "ETHUSDT", "LUNAUSDT", "FTTUSDT", "SRMUSDT"} <= cols      # delisted contracts are kept
    reasons = man["exclusions"]["by_reason"]
    assert any(r.startswith("TRADIFI_PERPETUAL") for r in reasons) and "synthetic index (BTCDOM-type)" in reasons
    assert "USDCUSDT" in reasons["stablecoin/fiat underlying"]
    assert reasons["commodity-backed token (gold) - not a crypto asset"] == ["PAXGUSDT", "XAUTUSDT"]
    # the archive starts 2020-01; the true first candle (2019-09-08) comes from REST and is recorded
    per = man["per_symbol"]["BTCUSDT"]
    assert per["first_candle_open"].startswith("2019-09-08") and "REST" in per["daily_source"]
    assert p.prices["BTCUSDT"].first_valid_index() == pd.Timestamp("2019-09-09", tz="UTC")
    assert per["hourly_candles_from_rest_symbol"] > 2000          # 2019-09..12 and the current month
    assert man["tail_rows_dropped_no_exec_print_yet"] == [] or len(man["tail_rows_dropped_no_exec_print_yet"]) <= 2


def test_spot_carry_and_exclusions():
    need("CRYPTO-SPOT")
    p = panel("CRYPTO-SPOT")
    man = manifest("CRYPTO-SPOT")
    assert np.allclose((p.carry["BTCUSDT"] + p.tbill).to_numpy()[1:], 0.0, atol=1e-18)
    assert (p.carry.iloc[1:].to_numpy() <= 0).all() and np.isnan(p.carry.iloc[0]).all()
    for c in ("ETHUSDT", "SOLUSDT"):
        pd.testing.assert_series_equal(p.carry[c], p.carry["BTCUSDT"].rename(c))
    cols = set(p.prices.columns)
    for bad in ("USDCUSDT", "BUSDUSDT", "FDUSDUSDT", "EURUSDT", "BTCUPUSDT", "BTCDOWNUSDT", "ETHBULLUSDT", "BEARUSDT",
                "WBTCUSDT", "WBETHUSDT", "AAPLBUSDT", "SPYBUSDT", "STXBUSDT", "PAXGUSDT", "XAUTUSDT"):
        assert bad not in cols, bad
    assert man["exclusions"]["by_reason"]["commodity-backed token (gold) - not a crypto asset"] == ["PAXGUSDT", "XAUTUSDT"]
    assert {"BTCUSDT", "ETHUSDT", "JUPUSDT", "SYRUPUSDT", "USTCUSDT", "FRAXUSDT"} <= cols   # coins, not levered / stable
    assert set(man["exclusions"]["by_reason"]) >= {"stablecoin base (stablecoin-vs-stablecoin pair)", "fiat base",
                                                   "wrapped / staked wrapper token", "leveraged token (UP/DOWN/BULL/BEAR)",
                                                   "tokenised equity / ETF (<TICKER>B) - not a crypto asset"}
    # one ticker, two assets: old LUNA and LUNA 2.0 are separate instruments
    assert "LUNAUSDT@20220514" in cols and p.prices["LUNAUSDT"].first_valid_index() >= pd.Timestamp("2022-05-30", tz="UTC")


def test_spot_microsecond_archive_files_are_read_correctly():
    need("CRYPTO-SPOT")
    p = panel("CRYPTO-SPOT")
    old = raw_hourly("spot", "BTCUSDT", "2024-06")
    new = raw_hourly("spot", "BTCUSDT", "2025-06")
    assert old.attrs["micro"] is False and new.attrs["micro"] is True       # the unit really changes in the raw files
    for h, day in ((old, "2024-06-15"), (new, "2025-06-15")):
        d = pd.Timestamp(day, tz="UTC")
        assert h.index.min() >= d.replace(day=1) and h.index.max() < d.replace(day=1) + pd.DateOffset(months=1)
        assert p.aux["exec_prices"].loc[d, "BTCUSDT"] == pytest.approx(h.loc[d, "close"])
        assert p.prices.loc[d, "BTCUSDT"] == pytest.approx(h.loc[d - HOUR, "close"])
