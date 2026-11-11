"""Alignment primitives of the data layer: lags, staleness, CPI availability, clocks, funding labels.
Synthetic inputs only — no files, no network."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.factory.data import crypto as C
from scripts.factory.data.fx import day_counts, exec_after_decision, source_gaps
from scripts.factory.data.panelio import (asof_on_or_before, asof_strictly_before, cpi_available, limited_ffill,
                                          to_utc_index)

D = pd.Timestamp


def test_asof_is_strictly_lagged_and_known_before_the_print():
    obs = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03",
                                                                     "2024-01-04", "2024-01-05"]))
    prints = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"])
    v, st = asof_strictly_before(obs, prints)
    assert v.tolist() == [1.0, 2.0, 3.0, 4.0, 5.0]          # never the same-day observation
    assert st["ffilled"] == 0 and st["nan_stale"] == 0
    # changing the observation dated ON a print date (or later) cannot change that print's value
    obs2 = obs.copy()
    obs2.loc["2024-01-04":] = 99.0
    v2, _ = asof_strictly_before(obs2, prints)
    assert v2.iloc[:3].tolist() == [1.0, 2.0, 3.0]


def test_asof_weekend_uses_fridays_value_and_counts_days():
    obs = pd.Series([5.0, 5.5], index=pd.to_datetime(["2024-03-07", "2024-03-08"]))        # Thu, Fri
    prints = pd.to_datetime(["2024-03-08", "2024-03-11"])                                  # Fri, Mon
    v, _ = asof_strictly_before(obs, prints)
    assert v.tolist() == [5.0, 5.5]
    assert day_counts(prints).tolist()[1] == 3.0 and np.isnan(day_counts(prints).iloc[0])


def test_asof_staleness_limit():
    obs = pd.Series([1.0], index=pd.to_datetime(["2024-01-01"]))
    prints = pd.bdate_range("2024-01-02", periods=8)
    v, st = asof_strictly_before(obs, prints, max_stale_prints=3)
    # print 1 fresh, prints 2-4 forward-filled, from the 5th on NaN
    assert v.notna().tolist() == [True, True, True, True, False, False, False, False]
    assert st["fresh"] == 1 and st["ffilled"] == 3 and st["nan_stale"] == 4
    v10, st10 = asof_strictly_before(obs, prints, max_stale_prints=10)
    assert v10.notna().all() and st10["ffilled_beyond_3_prints"] == 4
    # a new observation resets the run
    obs2 = pd.concat([obs, pd.Series([2.0], index=pd.to_datetime(["2024-01-09"]))])
    v2, _ = asof_strictly_before(obs2, prints, max_stale_prints=3)
    assert v2.tolist()[-2:] == [2.0, 2.0] and np.isnan(v2.iloc[4])


def test_asof_before_start_is_nan_and_nan_obs_ignored():
    obs = pd.Series([np.nan, 7.0], index=pd.to_datetime(["2024-01-02", "2024-01-04"]))
    prints = pd.to_datetime(["2024-01-03", "2024-01-04", "2024-01-05"])
    v, st = asof_strictly_before(obs, prints)
    assert np.isnan(v.iloc[0]) and np.isnan(v.iloc[1]) and v.iloc[2] == 7.0
    assert st["nan_before_start"] == 2


def test_asof_on_or_before_uses_same_day():
    obs = pd.Series([1.0, 2.0], index=pd.to_datetime(["2024-01-02", "2024-01-03"]))
    prints = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    v, st = asof_on_or_before(obs, prints)
    assert v.tolist() == [1.0, 2.0, 2.0, 2.0] and st["ffilled"] == 2


def test_cpi_monthly_available_two_months_after_period_start():
    cpi = pd.Series([100.0, 101.0, 102.0], index=pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]))
    prints = pd.to_datetime(["2024-02-15", "2024-02-29", "2024-03-01", "2024-03-29", "2024-04-01", "2024-05-01"])
    v, st = cpi_available(cpi, prints, quarterly=False)
    assert np.isnan(v.iloc[0]) and np.isnan(v.iloc[1])      # January CPI is not usable in February
    assert v.iloc[2] == 100.0 and v.iloc[3] == 100.0        # ... it is from 1 March
    assert v.iloc[4] == 101.0 and v.iloc[5] == 102.0
    assert st["last_available_from"] == "2024-05-01"


def test_cpi_quarterly_available_four_months_after_quarter_start():
    # BIS repeats the quarterly value in each month of the quarter
    idx = pd.date_range("2024-01-01", periods=6, freq="MS")
    cpi = pd.Series([100.0, 100.0, 100.0, 103.0, 103.0, 103.0], index=idx)
    prints = pd.to_datetime(["2024-04-30", "2024-05-01", "2024-07-31", "2024-08-01"])
    v, st = cpi_available(cpi, prints, quarterly=True)
    assert np.isnan(v.iloc[0]) and v.iloc[1] == 100.0 and v.iloc[2] == 100.0 and v.iloc[3] == 103.0
    assert st["quarter_consistency_violations"] == 0 and st["observations_used"] == 2
    bad = cpi.copy()
    bad.iloc[1] = 100.5
    _, st2 = cpi_available(bad, prints, quarterly=True)
    assert st2["quarter_consistency_violations"] == 1


def test_cpi_goes_stale_after_three_missed_releases():
    cpi = pd.Series([100.0], index=pd.to_datetime(["2024-01-01"]))          # usable from 2024-03-01
    prints = pd.to_datetime(["2024-03-01", "2024-06-28", "2024-07-01"])
    v, _ = cpi_available(cpi, prints, quarterly=False)
    assert v.iloc[0] == 100.0 and v.iloc[1] == 100.0 and np.isnan(v.iloc[2])


def test_limited_ffill_three_prints_only_and_never_past_the_end():
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    df = pd.DataFrame({"A": [1, np.nan, np.nan, np.nan, np.nan, 6, 7, np.nan, np.nan, np.nan],
                       "B": [np.nan, np.nan, 3, 4, np.nan, 6, 7, 8, 9, 10]}, index=idx, dtype="float64")
    f, st = limited_ffill(df, 3)
    assert f["A"].iloc[:4].tolist() == [1, 1, 1, 1]         # three fills after the real value, no more
    assert np.isnan(f["A"].iloc[4]) and f["A"].iloc[5] == 6 and f["A"].iloc[6] == 7
    assert f["A"].iloc[7:].isna().all()                     # nothing is invented after the last real value
    assert st["A"] == {"missing_prints": 4, "ffilled": 3, "left_nan": 1}
    assert f["B"].iloc[:2].isna().all() and f["B"].iloc[4] == 4
    assert st["B"] == {"missing_prints": 1, "ffilled": 1, "left_nan": 0}


def test_utc_index_follows_local_dst():
    d = pd.to_datetime(["2024-01-15", "2024-07-15"])
    ecb = to_utc_index(d, "14:15", "Europe/Berlin")
    assert [str(x) for x in ecb] == ["2024-01-15 13:15:00+00:00", "2024-07-15 12:15:00+00:00"]
    ny = to_utc_index(d, "16:00", "America/New_York")
    assert [str(x) for x in ny] == ["2024-01-15 21:00:00+00:00", "2024-07-15 20:00:00+00:00"]
    assert str(ecb.tz) == "UTC" and ecb.name == "ts"


def test_noon_new_york_is_after_the_ecb_fix_in_every_dst_regime():
    # every calendar day 1999-2030: all four combinations of (US DST, EU DST) incl. the mismatch weeks
    days = pd.date_range("1999-01-01", "2030-12-31", freq="D")
    dec, exe = exec_after_decision(days)
    gap_h = (exe - dec).total_seconds() / 3600.0
    assert gap_h.min() == 2.75 and gap_h.max() == 4.75
    # mismatch weeks: US already on summer time, Europe not yet -> smallest gap
    assert ((exe - dec)[days == pd.Timestamp("2021-03-20")].total_seconds() / 3600.0)[0] == 2.75
    assert ((exe - dec)[days == pd.Timestamp("2021-11-03")].total_seconds() / 3600.0)[0] == 2.75
    assert ((exe - dec)[days == pd.Timestamp("2021-07-01")].total_seconds() / 3600.0)[0] == 3.75
    assert ((exe - dec)[days == pd.Timestamp("2021-12-01")].total_seconds() / 3600.0)[0] == 3.75
    # before 2007 the US changed clocks on different dates (first Sunday of April): still positive
    assert ((exe - dec)[days == pd.Timestamp("2003-03-31")].total_seconds() / 3600.0)[0] == 4.75


def test_source_gaps():
    v = pd.Series(1.0, index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-03-01", "2024-03-02"]))
    g = source_gaps(v)
    assert g == [(D("2024-01-02"), D("2024-03-01"))]


# ---------------------------------------------------------------------------------------- crypto helpers
def test_funding_labels_follow_the_exec_interval():
    day = C.DAY_MS
    h = C.HOUR_MS
    d0 = int(pd.Timestamp("2024-05-10", tz="UTC").value // 10**6)
    ev = pd.DataFrame({"rate": [0.0001, 0.0002, 0.0004, 0.0008, 0.0016, 0.0032]},
                      index=pd.Index([d0 + 4,            # 05-10 00:00:00.004 -> row 05-10 (<= 01:00 of 05-10)
                                      d0 + h,            # 05-10 01:00:00.000 exactly -> row 05-10 (interval is closed on the right)
                                      d0 + h + 1,        # 05-10 01:00:00.001 -> row 05-11
                                      d0 + 8 * h,        # 05-10 08:00 -> row 05-11
                                      d0 + 16 * h + 7,   # 05-10 16:00 -> row 05-11
                                      d0 + day + 2],     # 05-11 00:00 -> row 05-11
                                     dtype="int64"))
    rows = pd.date_range("2024-05-09", periods=4, freq="D", tz="UTC")
    tot, cnt = C.funding_to_rows(ev, rows, cut_after_ms=None)
    assert cnt.tolist() == [0, 2, 4, 0]
    assert tot.iloc[1] == pytest.approx(0.0003) and tot.iloc[2] == pytest.approx(0.0004 + 0.0008 + 0.0016 + 0.0032)
    # phantom funding after the last traded hour is dropped
    tot2, cnt2 = C.funding_to_rows(ev, rows, cut_after_ms=d0 + 9 * h)
    assert cnt2.tolist() == [0, 2, 2, 0] and tot2.iloc[2] == pytest.approx(0.0012)


def test_kline_csv_parser_header_optional_and_microseconds():
    no_header = b"1601510400000,1,2,0.5,10773.5,8,1601513999999,871.5,28,4,47,0\n1601514000000,1,2,0.5,10833.13,5,1601517599999,579.25,0,3,36,0\n"
    a = C._kline_rows_from_csv(no_header)
    assert a.shape == (2, 4) and a[0].tolist() == [1601510400000.0, 10773.5, 871.5, 28.0] and a[1, 3] == 0.0
    with_header = b"open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n" + no_header
    b = C._kline_rows_from_csv(with_header)
    assert np.array_equal(a, b)
    micro = b"1735689600000000,1,2,0.5,93576.0,8,1735693199999999,871.5,28,4,47,0\n"
    c = C._kline_rows_from_csv(micro)
    assert c[0, 0] == 1735689600000.0


def test_spot_leveraged_tokens_are_sibling_pairs():
    bases = {"BTC", "BTCUP", "BTCDOWN", "ETHBULL", "ETHBEAR", "BULL", "BEAR", "1INCHUP", "1INCHDOWN", "JUP", "SYRUP",
             "SUPER", "XRPDOWN", "XRPUP"}
    for base in ("BTCUP", "BTCDOWN", "ETHBULL", "ETHBEAR", "BULL", "BEAR", "1INCHUP", "1INCHDOWN", "XRPDOWN"):
        assert C.spot_leveraged(base, bases), base
    for base in ("BTC", "JUP", "SYRUP", "SUPER"):          # real coins: no DOWN / BEAR sibling
        assert not C.spot_leveraged(base, bases), base


def test_s3_listing_parser_handles_checksum_elements(monkeypatch):
    from scripts.factory.data import binance_dl as B

    xml = ('<?xml version="1.0" encoding="UTF-8"?><ListBucketResult><Prefix>p/</Prefix><IsTruncated>false</IsTruncated>'
           '<Contents><Key>p/A-1d-2020-01.zip</Key><LastModified>2021-06-14T06:12:38.000Z</LastModified>'
           '<ETag>&quot;eac9&quot;</ETag><Size>1978</Size><StorageClass>STANDARD</StorageClass></Contents>'
           '<Contents><Key>p/A-1d-2025-04.zip</Key><LastModified>2025-05-17T13:45:26.000Z</LastModified>'
           '<ETag>&quot;bf84&quot;</ETag><ChecksumAlgorithm>CRC64NVME</ChecksumAlgorithm>'
           '<ChecksumType>FULL_OBJECT</ChecksumType><Size>318</Size><StorageClass>STANDARD</StorageClass></Contents>'
           '<CommonPrefixes><Prefix>p/sub/</Prefix></CommonPrefixes></ListBucketResult>')

    class R:
        text = xml

    monkeypatch.setattr(B, "http_get", lambda *a, **k: R())
    keys, pre = B.s3_list("p/")
    assert [k["key"] for k in keys] == ["p/A-1d-2020-01.zip", "p/A-1d-2025-04.zip"]
    assert [k["size"] for k in keys] == [1978, 318] and keys[1]["etag"] == "bf84" and pre == ["p/sub/"]


# ------------------------------------------------------------- archive files: units and the period in the name
def _zip(path, name, text):
    import zipfile
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(name, text)
    return path


def test_archive_file_bounds():
    ms = lambda s: int(pd.Timestamp(s, tz="UTC").value // 10**6)
    assert C.archive_file_bounds("BTCUSDT-1h-2025-01.zip") == (ms("2025-01-01"), ms("2025-02-01"))
    assert C.archive_file_bounds("BTCUSDT-1d-2024-12.zip") == (ms("2024-12-01"), ms("2025-01-01"))
    assert C.archive_file_bounds("BTCUSDT-1h-2026-11-07.zip") == (ms("2026-11-07"), ms("2026-11-08"))
    assert C.archive_file_bounds("BTCUSDT-fundingRate-2021-02.zip") == (ms("2021-02-01"), ms("2021-03-01"))
    with pytest.raises(ValueError):
        C.archive_file_bounds("BTCUSDT-1h.zip")


def test_archive_klines_milliseconds_and_microseconds_inside_the_named_month(tmp_path):
    ms0 = int(pd.Timestamp("2025-01-01", tz="UTC").value // 10**6)
    row = lambda t: f"{t},1,2,0.5,100.5,8,{t + 3599999},871.5,28,4,47,0\n"
    # milliseconds (futures files; spot files before 2025)
    p1 = _zip(tmp_path / "AAAUSDT-1h-2025-01.zip", "AAAUSDT-1h-2025-01.csv", row(ms0) + row(ms0 + 3_600_000))
    a = C.archive_kline_rows(p1)
    assert a[:, 0].tolist() == [ms0, ms0 + 3_600_000]
    # microseconds (spot files from 2025-01): same instants after conversion
    us = lambda t: f"{t * 1000},1,2,0.5,100.5,8,{(t + 3599999) * 1000 + 999},871.5,28,4,47,0\n"
    d2 = tmp_path / "us"
    d2.mkdir()
    p2 = _zip(d2 / "AAAUSDT-1h-2025-01.zip", "AAAUSDT-1h-2025-01.csv", us(ms0) + us(ms0 + 3_600_000))
    b = C.archive_kline_rows(p2)
    assert np.array_equal(a, b)
    # a candle outside the month named by the file is refused (this is what a wrong unit would look like)
    d3 = tmp_path / "bad"
    d3.mkdir()
    p3 = _zip(d3 / "AAAUSDT-1h-2025-01.zip", "AAAUSDT-1h-2025-01.csv", row(ms0) + row(ms0 + 32 * 86_400_000))
    with pytest.raises(ValueError, match="outside the period"):
        C.archive_kline_rows(p3)
    # a file that mixes units is refused
    d4 = tmp_path / "mixed"
    d4.mkdir()
    p4 = _zip(d4 / "AAAUSDT-1h-2025-01.zip", "AAAUSDT-1h-2025-01.csv", row(ms0) + us(ms0 + 3_600_000))
    with pytest.raises(ValueError, match="mixes"):
        C.archive_kline_rows(p4)


def test_funding_cut_before_first_trade():
    h = C.HOUR_MS
    d0 = int(pd.Timestamp("2024-05-10", tz="UTC").value // 10**6)
    ev = pd.DataFrame({"rate": [0.01, 0.02, 0.04]}, index=pd.Index([d0 + 8 * h, d0 + 16 * h, d0 + 24 * h], dtype="int64"))
    rows = pd.date_range("2024-05-10", periods=3, freq="D", tz="UTC")
    tot, cnt = C.funding_to_rows(ev, rows, cut_after_ms=None, cut_before_ms=d0 + 12 * h)
    assert cnt.tolist() == [0, 2, 0] and tot.iloc[1] == pytest.approx(0.06)


def test_off_grid_candles_are_dropped_and_counted(tmp_path, monkeypatch):
    """After the Feb 2018 outage the spot archive holds hourly candles anchored at the restart second."""
    ms0 = int(pd.Timestamp("2018-02-09 09:00", tz="UTC").value // 10**6)
    row = lambda t, c: f"{t},1,2,0.5,{c},8,{t + 3599999},871.5,28,4,47,0\n"
    d = tmp_path / "binance" / "spot" / "archive_klines_1h" / "AAAUSDT"
    d.mkdir(parents=True)
    _zip(d / "AAAUSDT-1h-2018-02.zip", "AAAUSDT-1h-2018-02.csv",
         row(ms0, 100.0) + row(ms0 + 28 * 60_000 + 14_789, 101.0) + row(ms0 + 3_600_000, 102.0))
    monkeypatch.setattr(C, "RAW", tmp_path)
    df = C.read_klines("spot", "AAAUSDT", "1h")
    assert df.index.tolist() == [ms0, ms0 + 3_600_000] and df["close"].tolist() == [100.0, 102.0]
    assert df.attrs["off_grid_dropped"] == 1


def test_hole_filler_pages_of_different_ranges_do_not_overwrite_each_other(tmp_path, monkeypatch):
    """Regression (2026-11-10, spot, 2018-02-07..12): two hole ranges with the same start but different ends
    used to write the same file name, so the shorter request destroyed the longer one's candles."""
    import json as _json
    from scripts.factory.data import binance_dl as B

    monkeypatch.setattr(B, "RAW", tmp_path)
    h = 3_600_000
    t0 = int(pd.Timestamp("2018-02-07", tz="UTC").value // 10**6)

    class R:
        def __init__(self, rows, url):
            self._rows, self.url = rows, url
            self.content = _json.dumps(rows).encode()
            self.headers = {}

        def json(self):
            return self._rows

    def fake_get(url, params=None, **kw):
        n = (params["endTime"] + 1 - params["startTime"]) // h
        rows = [[params["startTime"] + i * h, "1", "1", "1", str(100 + i), "1", 0, "5", 3, "1", "1", "0"] for i in range(n)]
        return R(rows, url)

    monkeypatch.setattr(B, "http_get", fake_get)
    rest = B.Rest("spot")
    d = tmp_path / "binance" / "spot" / "rest_klines_1h" / "AAAUSDT"
    long_ = rest.klines("AAAUSDT", "1h", t0, t0 + 120 * h - 1, d, tag=f"fill_{t0}_{t0 + 120 * h}_")
    short = rest.klines("AAAUSDT", "1h", t0, t0 + 72 * h - 1, d, tag=f"fill_{t0}_{t0 + 72 * h}_")
    assert long_["rows"] == 120 and short["rows"] == 72
    assert len(list(d.glob("1h_*.json"))) == 2                      # two files, nothing overwritten
    monkeypatch.setattr(C, "RAW", tmp_path)
    df = C.read_klines("spot", "AAAUSDT", "1h")
    assert len(df) == 120 and df.index[-1] == t0 + 119 * h          # the long range's candles are all still there
