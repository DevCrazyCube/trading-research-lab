"""Tests for scripts/factory/v2_extras.py — the realism pass and the leverage ladder (prereg §6).

Synthetic only: no real panel, no real run directory, no network (the one function that can reach the
network, `_http_get`, is replaced wherever a test could come near it).

  * the ladder's ruin logic on hand-made return streams (a single -1 % print is ruin at 200x and not at
    50x; absorption is final; a constant +0.1 % stream is never ruined and its median wealth is exact),
    against a plain loop, and the growth-optimal leverage against its closed form;
  * the liquidation scan on a tiny hand-made candle set and against a brute-force scan; the hourly
    candle reader on a fabricated raw tree;
  * the venue mapping (XBT <-> BTC, the 1000 prefixes, everything uncertain dropped) and the builders;
  * the evidence store: fetched once, saved raw with URL and fetch time, refused when it cannot be had;
  * `--synthetic` end to end: both stages on the tier-1 outputs of the conductor's own synthetic run;
    the same wiring with the ideal venue reproduces the Tier-1 stream; an unreachable endpoint refuses
    its venue while the others run.

Run:  cd /home/anont/meme && research/factory/.venv/bin/python -m pytest scripts/factory/tests/test_v2_extras.py -q
(about a minute: most of it is the conductor's synthetic tier-1 run for four books.)
"""
from __future__ import annotations

import json
import math
import zipfile

import numpy as np
import pandas as pd
import pytest

from scripts.factory import stats, v2
from scripts.factory import v2_extras as x
from scripts.factory.panel import PanelBundle

E2E_BOOKS = ["P.MACRO.LO_TREND", "P.FX.G10.ALL", "P.CRYPTO.TREND", "P.CRYPTO.LO_TREND"]      # P.CRYPTO.ALL is left out on purpose
H = x.HOUR_MS


def _no_network(*args, **kwargs):
    raise AssertionError("a test reached the network")


# --------------------------------------------------------------------------------------------------
# the ladder: ruin and absorption
# --------------------------------------------------------------------------------------------------
def test_one_minus_one_percent_print_is_ruin_at_200x_and_not_at_50x():
    r = np.zeros(40)
    r[17] = -0.01
    terminal, ruined, wiped, when = x.terminal_wealth(r[None, :], 200.0)          # 1 + 200 * (-0.01) = -1
    assert ruined[0] and wiped[0] and when[0] == 17 and terminal[0] == 0.0
    terminal, ruined, wiped, when = x.terminal_wealth(r[None, :], 50.0)           # 1 + 50 * (-0.01) = 0.5
    assert not ruined[0] and not wiped[0] and when[0] == -1 and terminal[0] == pytest.approx(0.5)
    terminal, ruined, wiped, _ = x.terminal_wealth(r[None, :], 100.0)             # exactly -100 % is a wipe-out
    assert ruined[0] and wiped[0] and terminal[0] == 0.0


def test_absorption_is_final_and_the_floor_is_ten_percent():
    r = np.array([[-0.5, -0.5, -0.5, -0.5, 1.0, 1.0],          # 0.5, 0.25, 0.125, 0.0625: ruined on the 4th print
                  [-0.5, -0.5, -0.5, 1.0, 1.0, 1.0],           # 0.125 is above the floor: survives and recovers to 1.0
                  [3.0, -1.5, 9.0, 9.0, 9.0, 9.0]])            # a single print of -150 % ends it, whatever came before
    terminal, ruined, wiped, when = x.terminal_wealth(r, 1.0)
    assert ruined.tolist() == [True, False, True] and wiped.tolist() == [False, False, True]
    assert when.tolist() == [3, -1, 1]
    assert terminal == pytest.approx([0.0625, 1.0, 0.0])


@pytest.mark.parametrize("leverage", [0.5, 3.0, 20.0, 200.0])
def test_absorbing_compounding_equals_a_plain_loop(leverage):
    rng = np.random.default_rng(int(leverage * 10))
    paths = rng.standard_t(3, size=(200, 40)) * 0.02
    terminal, ruined, wiped, when = x.terminal_wealth(paths, leverage)
    for i, path in enumerate(paths):
        wealth, hit, single, at = 1.0, False, False, -1
        for t, r in enumerate(path):
            growth = 1.0 + leverage * r
            if growth <= 0.0:
                wealth, hit, single, at = 0.0, True, True, t
                break
            wealth *= growth
            if wealth <= x.RUIN_FLOOR:
                hit, at = True, t
                break
        assert (bool(ruined[i]), bool(wiped[i]), int(when[i])) == (hit, single, at)
        assert terminal[i] == pytest.approx(wealth, rel=1e-12, abs=0.0)
    if leverage == 0.5:
        assert not ruined.any()                                  # 2 % prints at half exposure cannot reach the floor in 40 prints
    if leverage == 200.0:
        assert ruined.all() and wiped.any()                      # any print below -0.5 % is a wipe-out


def test_constant_stream_is_never_ruined_and_its_median_wealth_is_exact():
    r = np.full(700, 0.001)
    out = x.ladder_for_stream(r, 252, reps=300, seed=3)
    assert out["horizon_prints"] == 252 and out["block"] == stats.default_block_length(700) and out["reps"] == 300
    assert [row["L"] for row in out["levels"]] == list(x.LADDER_L)
    for row in out["levels"]:
        exact = (1.0 + row["L"] * 0.001) ** 252
        assert row["p_ruin"] == 0.0 and row["p_ruin_single_print_loss"] == 0.0 and row["n_survivors"] == 300
        assert row["p_final_below_half"] == 0.0 and not row["actual_history_ruined"]
        for key in ("median_wealth", "p05_wealth", "p95_wealth"):
            assert row[key] == pytest.approx(exact, rel=1e-12)
        assert row["mean_log_wealth_survivors"] == pytest.approx(252 * math.log1p(row["L"] * 0.001), rel=1e-12)
    assert out["best_L_by_median_log_wealth"] == 200.0
    assert out["growth_optimal"]["L"] == 200.0 and out["growth_optimal"]["at_grid_cap"]
    assert out["growth_optimal"]["single_print_wipe_out_leverage"] is None
    assert out["kelly_continuous_time"]["L"] is None                     # no variance: the ratio is undefined, not huge


def test_ladder_on_a_stream_with_one_bad_print():
    r = np.zeros(400)
    r[123] = -0.01
    out = x.ladder_for_stream(r, 100, reps=500, seed=11)
    rows = {row["L"]: row for row in out["levels"]}
    # on the actual history the print is met exactly once: ruin at 200x, a halving at 50x
    assert rows[200.0]["actual_history_ruined"] and rows[200.0]["actual_history_ruin_print"] == 123
    assert rows[200.0]["actual_history_ruin_by_single_print"] and not rows[50.0]["actual_history_ruined"]
    # a bootstrap path can miss the print or meet it several times; at 200x every meeting is a wipe-out
    assert 0.0 < rows[200.0]["p_ruin"] < 1.0 and rows[200.0]["p_ruin_single_print_loss"] == rows[200.0]["p_ruin"]
    assert rows[200.0]["median_log_wealth_is_minus_inf"] == (rows[200.0]["median_wealth"] <= 0.0)
    # 50x needs four meetings (0.5^4 < 0.1) and never loses 100 % in one print
    assert rows[50.0]["p_ruin"] < rows[200.0]["p_ruin"] and rows[50.0]["p_ruin_single_print_loss"] == 0.0
    assert rows[1.0]["p_ruin"] == 0.0 and rows[1.0]["n_survivors"] == 500
    assert out["growth_optimal"]["L"] == 0.0 and out["growth_optimal"]["single_print_wipe_out_leverage"] == pytest.approx(100.0)
    again = x.ladder_for_stream(r, 100, reps=500, seed=11)
    assert again["levels"] == out["levels"]                              # seeded: the same seed, the same ladder
    block = stats.default_block_length(len(r))
    same = [x.resample_paths(r, 100, 50, block, np.random.default_rng(11)) for _ in range(2)]
    other = x.resample_paths(r, 100, 50, block, np.random.default_rng(12))
    assert np.array_equal(same[0], same[1]) and not np.array_equal(same[0], other)


def test_growth_optimal_leverage_matches_the_closed_form():
    # half the prints +2 %, half -1 %: maximise 0.5*log(1 + 0.02 L) + 0.5*log(1 - 0.01 L)  ->  L* = (a - b) / (2ab) = 25
    r = np.tile([0.02, -0.01], 300)
    g = x.growth_optimal_leverage(r)
    assert g["L"] == pytest.approx(25.0, abs=1e-3) and not g["at_grid_cap"]
    assert g["single_print_wipe_out_leverage"] == pytest.approx(100.0)
    assert g["mean_log_growth_per_print"] == pytest.approx(0.5 * math.log(1.5) + 0.5 * math.log(0.75), rel=1e-9)
    out = x.ladder_for_stream(r, 200, reps=50, seed=0)
    mu, var = r.mean(), r.var(ddof=1)
    assert out["kelly_continuous_time"]["L"] == pytest.approx(mu / var)


def test_a_stream_shorter_than_one_year_is_refused():
    with pytest.raises(v2.Refused):
        x.ladder_for_stream(np.full(100, 0.001), 252, reps=10, seed=0)
    with pytest.raises(v2.Refused):
        x.ladder_for_stream(np.array([0.01, np.nan, 0.0]), 2, reps=10, seed=0)


def test_resampled_paths_are_stationary_bootstrap_heads():
    r = np.arange(50, dtype=float)
    paths = x.resample_paths(r, 20, 64, 5.0, np.random.default_rng(1))
    assert paths.shape == (64, 20) and set(np.unique(paths)) <= set(r)
    step = np.diff(paths, axis=1)
    assert np.isin(step, [1.0, -49.0]).mean() > 0.6                     # inside a block the index advances by one (wrapping)


# --------------------------------------------------------------------------------------------------
# 200x on hourly candles
# --------------------------------------------------------------------------------------------------
def _candles(o, h, lo, skip=()):
    ms0 = int(pd.Timestamp("2024-01-01", tz="UTC").value // 10**6)
    hours = [k for k in range(len(o) + len(skip)) if k not in skip]
    return pd.DataFrame({"open": np.asarray(o, float), "high": np.asarray(h, float), "low": np.asarray(lo, float)},
                        index=np.array([ms0 + H * k for k in hours], dtype=np.int64))


def test_liquidation_scan_on_hand_made_candles():
    c = _candles(o=[100, 100, 100, 100, 100, 100], h=[100.1, 100.6, 100.0, 100.2, 100.0, 100.0],
                 lo=[99.8, 99.6, 100.0, 99.4, 100.0, 100.0])
    ms, o, h, lo = c.index.to_numpy(), c["open"].to_numpy(), c["high"].to_numpy(), c["low"].to_numpy()
    nan = float("nan")
    # 0.5 %: a long dies at <= 99.5 (only the 4th candle), a short at >= 100.5 (only the 2nd candle)
    np.testing.assert_array_equal(x.liquidation_hours(ms, o, h, lo, 0.005, "long"), [4, 3, 2, 1, nan, nan])
    np.testing.assert_array_equal(x.liquidation_hours(ms, o, h, lo, 0.005, "short"), [2, 1, nan, nan, nan, nan])
    # 0.25 %: a long dies at <= 99.75 (2nd and 4th candle), a short at >= 100.25 (2nd candle)
    np.testing.assert_array_equal(x.liquidation_hours(ms, o, h, lo, 0.0025, "long"), [2, 1, 2, 1, nan, nan])
    np.testing.assert_array_equal(x.liquidation_hours(ms, o, h, lo, 0.0025, "short"), [2, 1, nan, nan, nan, nan])
    with pytest.raises(v2.Refused):
        x.liquidation_hours(ms, o, h, lo, 0.005, "flat")

    tab = x.liquidation_table(c, distances=(0.005,), horizons=(1, 2))
    assert tab["n_candles"] == 6 and tab["missing_hourly_candles"] == 0
    long, short = tab["rows"]
    assert (long["side"], short["side"]) == ("long", "short") and long["n_entries"] == 5       # the last entry has no 2 h of data
    assert long["share_within_1h"] == pytest.approx(1 / 5) and long["share_within_2h"] == pytest.approx(2 / 5)
    assert long["median_hours_to_liquidation"] == 3.0 and long["share_never_liquidated_in_data"] == pytest.approx(1 / 5)
    assert short["share_within_1h"] == pytest.approx(1 / 5) and short["share_within_2h"] == pytest.approx(2 / 5)
    assert short["median_hours_to_liquidation"] is None                # more than half are never liquidated in the data
    assert short["share_never_liquidated_in_data"] == pytest.approx(3 / 5)


def test_liquidation_time_is_clock_time_across_a_missing_candle():
    c = _candles(o=[100, 100, 100], h=[100, 100, 100], lo=[100, 100, 99.0], skip=(2,))     # hours 0, 1, 3
    hrs = x.liquidation_hours(c.index.to_numpy(), c["open"].to_numpy(), c["high"].to_numpy(), c["low"].to_numpy(), 0.005, "long")
    np.testing.assert_array_equal(hrs, [4, 3, 1])
    assert x.liquidation_table(c, distances=(0.005,), horizons=(1,))["missing_hourly_candles"] == 1


@pytest.mark.parametrize("n", [1, 2, 3, 17, 64, 100])
def test_first_passage_equals_brute_force(n):
    rng = np.random.default_rng(n)
    v = rng.normal(size=n)
    t = v + rng.normal(scale=1.5, size=n)
    for below in (True, False):
        want = []
        for i in range(n):
            hit = np.flatnonzero(v[i:] <= t[i]) if below else np.flatnonzero(v[i:] >= t[i])
            want.append(i + hit[0] if len(hit) else n)
        np.testing.assert_array_equal(x.first_passage(v, t, below), want)


def test_fee_arithmetic_at_200x():
    five, two = x.fee_arithmetic()
    assert five["round_trip_fee_pct_of_margin"] == pytest.approx(20.0) and five["price_move_to_break_even_pct"] == pytest.approx(0.10)
    assert two["round_trip_fee_pct_of_margin"] == pytest.approx(8.0) and two["price_move_to_break_even_pct"] == pytest.approx(0.04)


def test_hourly_reader_follows_the_data_layer_conventions(tmp_path, monkeypatch):
    from scripts.factory.data import common

    monkeypatch.setattr(common, "RAW", tmp_path)
    jan = int(pd.Timestamp("2020-01-01", tz="UTC").value // 10**6)
    rest = tmp_path / "binance" / "futures_um" / "rest_klines_1h" / "TESTUSDT"
    arch = tmp_path / "binance" / "futures_um" / "archive_klines_1h" / "TESTUSDT"
    rest.mkdir(parents=True)
    arch.mkdir(parents=True)

    def k(ms, o, h, lo, c, n=5):
        return [ms, str(o), str(h), str(lo), str(c), "1.0", ms + H - 1, "10.0", n, "0.5", "5.0", "0"]

    (rest / "1h_0.json").write_text(json.dumps([k(jan, 10, 12, 9, 11), k(jan + H, 11, 11.5, 10.5, 11.2)]))
    csv = "open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n" + "\n".join(
        ",".join(map(str, row)) for row in [k(jan + H, 99, 99, 99, 99),              # duplicate of a REST candle: REST wins
                                            k(jan + 2 * H, 11.2, 13, 11, 12.5),
                                            k(jan + 2 * H + 1234, 1, 1, 1, 1),        # off the hourly grid: dropped
                                            k(jan + 3 * H, 12.5, 12.5, 12.5, 12.5, 0)])
    with zipfile.ZipFile(arch / "TESTUSDT-1h-2020-01.zip", "w") as z:
        z.writestr("TESTUSDT-1h-2020-01.csv", csv)
    df = x.read_ohlc_1h("TESTUSDT", "perp")
    assert df.index.tolist() == [jan, jan + H, jan + 2 * H, jan + 3 * H]
    assert df["open"].tolist() == [10, 11, 11.2, 12.5] and df["high"].tolist() == [12, 11.5, 13, 12.5]
    assert df["low"].tolist() == [9, 10.5, 11, 12.5] and df["src"].tolist() == [0, 0, 1, 1] and df["count"].tolist() == [5, 5, 5, 0]

    (rest / "1h_1.json").write_text(json.dumps([k(jan + 4 * H, 10, 9, 9, 10)]))          # high below the open
    with pytest.raises(v2.Refused, match="not valid OHLC"):
        x.read_ohlc_1h("TESTUSDT", "perp")
    with pytest.raises(v2.Refused, match="no hourly candles"):
        x.read_ohlc_1h("NOPEUSDT", "perp")


# --------------------------------------------------------------------------------------------------
# instrument mapping
# --------------------------------------------------------------------------------------------------
def test_binance_names_and_kraken_bases():
    assert x.parse_binance_symbol("BTCUSDT")[:2] == ("BTC", 1.0)
    assert x.parse_binance_symbol("1000PEPEUSDT")[:2] == ("PEPE", 1000.0)
    assert x.parse_binance_symbol("1000000MOGUSDT")[:2] == ("MOG", 1e6)
    assert x.parse_binance_symbol("1MBABYDOGEUSDT")[:2] == ("BABYDOGE", 1e6)
    assert x.parse_binance_symbol("1INCHUSDT")[:2] == ("1INCH", 1.0)            # a leading digit is not a multiplier
    assert x.parse_binance_symbol("0GUSDT")[:2] == ("0G", 1.0)
    for bad in ("FTTUSDT@20221116", "BNXUSDTSETTLED", "ICPUSDT_SETTLED", "币安人生USDT", "BTCUSD", "btcusdt", "USDT"):
        base, _, why = x.parse_binance_symbol(bad)
        assert base is None and why
    assert x.kraken_base("PF_XBTUSD") == "BTC" == x.kraken_base("PF_XBTUSD", "BTC")       # XBT <-> BTC
    assert x.kraken_base("PF_ETHUSD", "ETH") == "ETH"
    assert x.kraken_base("PF_SPYXUSD", "SPYx") is None                          # tokenised equity: the payload's base disagrees
    assert x.kraken_base("FF_XBTUSD_261225", "BTC") is None                     # a dated future is not the perpetual
    assert x.kraken_base("PF_XBTUSD", "ETH") is None


def _kr(symbol, base, precision, **over):
    it = {"symbol": symbol, "type": "flexible_futures", "base": base, "quote": "USD", "contractSize": 1,
          "contractValueTradePrecision": precision, "tradeable": True, "suspended": False, "postOnly": False,
          "isExpired": False, "tradfi": False, "platformsPermitted": ["europa", "mtf"], "countriesBanned": [],
          "category": "Layer 1"}
    it.update(over)
    return it


def test_mapping_drops_what_it_cannot_map_with_certainty():
    instruments = {"result": "success", "instruments": [
        _kr("PF_XBTUSD", "BTC", 4), _kr("PF_PEPEUSD", "PEPE", -3), _kr("PF_LUNAUSD", "LUNA", 0), _kr("PF_DOGEUSD", "DOGE", 0),
        _kr("PF_ADAUSD", "ADA", 0), _kr("FF_XBTUSD_261225", "BTC", 4),
        _kr("PF_ETHUSD", "ETH", 3, tradeable=False), _kr("PF_MUUSD", "MU", 2, category="Equities"),
        _kr("PF_SOLUSD", "SOL", 2, platformsPermitted=["payward_digital_solutions"]), _kr("PF_XRPUSD", "XRP", 0, countriesBanned=["NL"]),
        _kr("PF_EURUSD", "EUR", 0, tradfi=True), _kr("PF_LTCUSD", "LTC", 2, postOnly=True),
        _kr("PF_SPYXUSD", "SPYx", 2, category="xStocks")]}
    tickers = {"tickers": [{"symbol": "PF_XBTUSD", "markPrice": 74000.0}, {"symbol": "PF_PEPEUSD", "markPrice": 5.3e-6},
                           {"symbol": "PF_LUNAUSD", "markPrice": 4e-5}, {"symbol": "PF_ADAUSD", "markPrice": 0.4}]}
    listing, ineligible = x.kraken_listing(instruments, tickers)
    assert set(listing) == {"BTC", "PEPE", "LUNA", "DOGE", "ADA"}
    assert set(ineligible) == {"ETH", "MU", "SOL", "XRP", "EUR", "LTC"}
    assert listing["BTC"]["symbol"] == "PF_XBTUSD" and listing["BTC"]["lot_base"] == pytest.approx(1e-4)
    assert listing["PEPE"]["lot_base"] == pytest.approx(1000.0) and listing["DOGE"]["price"] is None

    last = {"BTCUSDT": 73000.0, "1000PEPEUSDT": 0.0052, "PEPEUSDT": 0.0052, "LUNAUSDT": 0.037, "DOGEUSDT": 0.07,
            "ADAUSDT": float("nan"), "ETHUSDT": 2100.0, "MUUSDT": 0.5, "SOLUSDT": 87.0, "XRPUSDT": 2.0, "FOOUSDT": 1.0,
            "BNXUSDTSETTLED": 1.0, "FTTUSDT@20221116": 1.0}
    mapped, dropped = x.map_instruments(list(last), last, listing, ineligible)
    assert set(mapped) == {"BTCUSDT", "1000PEPEUSDT"}
    assert mapped["BTCUSDT"]["venue_symbol"] == "PF_XBTUSD" and mapped["BTCUSDT"]["multiplier"] == 1.0
    assert mapped["1000PEPEUSDT"]["multiplier"] == 1000.0 and mapped["1000PEPEUSDT"]["price_ratio"] == pytest.approx(5.3e-3 / 5.2e-3)
    kinds = {d["instrument"]: d["kind"] for d in dropped}
    assert kinds == {"PEPEUSDT": "price_mismatch",              # the same ticker, a unit that is off by 1,000
                     "LUNAUSDT": "price_mismatch",              # the same ticker, another asset
                     "DOGEUSDT": "no_venue_price", "ADAUSDT": "no_binance_price",
                     "ETHUSDT": "not_eligible", "MUUSDT": "not_eligible", "SOLUSDT": "not_eligible", "XRPUSDT": "not_eligible",
                     "FOOUSDT": "not_listed", "BNXUSDTSETTLED": "name", "FTTUSDT@20221116": "name"}
    assert set(kinds.values()) <= set(x.DROP_KINDS) and all(d["reason"] for d in dropped)
    assert len(mapped) + len(dropped) == len(last)             # nothing disappears silently


def test_bitvavo_listing_reads_precision_minimum_and_implied_price():
    markets = [
        {"market": "BTC-EUR", "status": "trading", "base": "BTC", "quote": "EUR", "quantityDecimals": 8,
         "minOrderInQuoteAsset": "5.00", "minOrderInBaseAsset": "0.00007294"},
        {"market": "BTC-USDC", "status": "trading", "base": "BTC", "quote": "USDC", "quantityDecimals": 8,
         "minOrderInQuoteAsset": "5.000000", "minOrderInBaseAsset": "0.00007"},
        {"market": "PEPE-EUR", "status": "trading", "base": "PEPE", "quote": "EUR", "quantityDecimals": 0,
         "minOrderInQuoteAsset": "5.00", "minOrderInBaseAsset": "1047524"},
        {"market": "ETH-EUR", "status": "halted", "base": "ETH", "quote": "EUR", "quantityDecimals": 8,
         "minOrderInQuoteAsset": "5.00", "minOrderInBaseAsset": "0.0026"},
        {"market": "SOL-EUR", "status": "trading", "base": "SOL", "quote": "EUR", "quantityDecimals": None,
         "minOrderInQuoteAsset": "5.00", "minOrderInBaseAsset": "0.06"}]
    listing, ineligible = x.bitvavo_listing(markets, 1.1193)
    assert set(listing) == {"BTC", "PEPE"} and set(ineligible) == {"ETH", "SOL"}
    assert listing["BTC"]["lot_base"] == pytest.approx(1e-8) and listing["PEPE"]["lot_base"] == 1.0
    assert listing["BTC"]["min_order_quote_eur"] == 5.0
    assert listing["BTC"]["price"] == pytest.approx(5.0 / 0.00007294 * 1.1193)
    mapped, dropped = x.map_instruments(["BTCUSDT", "PEPEUSDT", "ETHUSDT"], {"BTCUSDT": 75000.0, "PEPEUSDT": 5.2e-6, "ETHUSDT": 2100.0},
                                        listing, ineligible)
    assert set(mapped) == {"BTCUSDT", "PEPEUSDT"} and dropped[0]["kind"] == "not_eligible"


# --------------------------------------------------------------------------------------------------
# VenueSpec builders (the pinned venues.json, no payload needed for these two venues)
# --------------------------------------------------------------------------------------------------
def _labels_are_complete(build: x.VenueBuild) -> None:
    assert build.provenance
    for row in build.provenance:
        assert row["basis"] in (x.FROM_FILE, x.VERIFIED, x.ASSUMED, x.UNKNOWN) and row["source"]
        assert (row["value"] is None) == (row["basis"] == x.UNKNOWN)
    for spec in build.specs.values():
        for name, note in spec.notes.items():
            if note.get("status") == "override":                # every override carries a VERIFIED / ASSUMED row
                assert any(r["field"] == name and r["basis"] in (x.VERIFIED, x.ASSUMED) for r in build.provenance)


def test_pepperstone_spec_lots_spreads_financing_and_leverage():
    idx = pd.date_range("2024-01-01", periods=4, freq="B", tz="UTC")
    last = {"EUR": 1.10, "GBP": 1.30, "JPY": 0.0064, "CHF": 1.25, "CAD": 0.70, "AUD": 0.69, "NZD": 0.56, "SEK": 0.10, "NOK": 0.11}
    panel = PanelBundle("FX", pd.DataFrame({k: [v * 0.99, v * 1.01, v, v] for k, v in last.items()}, index=idx))
    b = x.build_pepperstone(list(last) + ["MXN"], panel)
    assert b.refused is None and [d["instrument"] for d in b.dropped] == ["MXN"] and set(b.specs) == set(last)
    for ccy in ("EUR", "GBP", "AUD", "NZD"):                    # <CCY>USD: a 0.01 lot is 1,000 units of the instrument
        assert b.specs[ccy].lot_step == 1000.0
    for ccy in ("JPY", "CHF", "CAD", "SEK", "NOK"):             # USD<CCY>: a 0.01 lot is 1,000 dollars at the latest price
        assert b.specs[ccy].lot_step == pytest.approx(1000.0 / last[ccy])
    assert {c: b.specs[c].leverage_cap for c in last} == {"EUR": 30, "GBP": 30, "JPY": 30, "CHF": 30, "CAD": 30,
                                                          "AUD": 20, "NZD": 20, "SEK": 20, "NOK": 20}
    for ccy, spec in b.specs.items():
        base_bp, hold_bp = x._base_cost(("FX", "t1"), v2._fx_group(ccy))
        assert spec.financing_long_bp_year == spec.financing_short_bp_year == hold_bp == 100.0
        assert spec.min_notional == 0.0 and spec.contract_notional == 1.0 and spec.min_fee is not None and spec.currency == "USD"
        if ccy in ("CHF", "CAD", "AUD", "NZD"):                 # no published spread: the prereg's base cost is what is paid
            assert spec.fee_bp + spec.half_spread_bp == pytest.approx(base_bp)
        if ccy in ("SEK", "NOK"):
            assert spec.half_spread_bp == base_bp == 2.5
    rows = {(r["field"], r["basis"]) for r in b.provenance}
    assert ("lot_step", x.VERIFIED) in rows and ("lot_step", x.ASSUMED) in rows and ("financing_long_bp_year", x.ASSUMED) in rows
    _labels_are_complete(b)


def test_trading212_spec_is_explicit_about_what_it_assumes():
    eurusd, ref = x.reference_eurusd()
    assert ref["EURUSD"] == eurusd > 0
    b = x.build_trading212(["SPY", "TLT"], eurusd)
    assert b.refused is None and not b.dropped and set(b.specs) == {"SPY", "TLT"}
    spec = b.specs["SPY"]
    assert spec.fee_bp + spec.half_spread_bp == pytest.approx(x._base_cost(("MACRO", "t1_lo"))[0])       # prereg base: 5 bp
    assert spec.lot_step == 0.0 and spec.leverage_cap == 1.0 and spec.min_notional == pytest.approx(x.T212_MIN_ORDER_EUR * eurusd)
    assert spec.financing_short_bp_year is None and spec.cash_interest_bp_year is None                    # unknown stays unknown
    basis = {r["field"]: r["basis"] for r in b.provenance}
    assert basis["half_spread_bp"] == basis["min_notional"] == basis["lot_step"] == x.ASSUMED
    assert basis["financing_short_bp_year"] == basis["cash_interest_bp_year"] == x.UNKNOWN
    _labels_are_complete(b)


def test_a_venue_without_instrument_metadata_is_refused_not_guessed():
    idx = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    panel = PanelBundle("CRYPTO-PERP", pd.DataFrame({"BTCUSDT": [70000.0, 71000.0, 72000.0], "ETHUSDT": [2000.0, 2100.0, 2050.0]},
                                                    index=idx))
    gone = {"payload": None, "meta": {}, "error": "HTTP 503"}
    b = x.build_kraken(["BTCUSDT"], panel, {"kraken_instruments": gone, "kraken_tickers": gone}, 1.1)
    assert b.refused.startswith("instrument metadata unavailable") and "HTTP 503" in b.refused and not b.specs
    b = x.build_bitvavo(["BTCUSDT"], panel, {"bitvavo_markets": gone}, 1.1)
    assert b.refused.startswith("instrument metadata unavailable") and not b.specs
    # instruments but no price evidence: the mapping cannot be corroborated, so Kraken is refused as well
    ins = {"payload": {"result": "success", "instruments": [_kr("PF_XBTUSD", "BTC", 4)]}, "meta": {}, "error": None}
    b = x.build_kraken(["BTCUSDT"], panel, {"kraken_instruments": ins, "kraken_tickers": gone}, 1.1)
    assert b.refused.startswith("instrument metadata unavailable") and not b.specs
    # with both, BTC maps and its lot is the payload's
    tick = {"payload": {"tickers": [{"symbol": "PF_XBTUSD", "markPrice": 72500.0}]}, "meta": {"fetched_utc": "t"}, "error": None}
    b = x.build_kraken(["BTCUSDT", "ETHUSDT"], panel, {"kraken_instruments": ins, "kraken_tickers": tick}, 1.1)
    assert b.refused is None and set(b.specs) == {"BTCUSDT"} and b.specs["BTCUSDT"].lot_step == pytest.approx(1e-4)
    assert b.specs["BTCUSDT"].leverage_cap == v2.LANES["CRYPTO-PERP"].max_gross == 2.0
    assert [d["instrument"] for d in b.dropped] == ["ETHUSDT"]
    _labels_are_complete(b)


# --------------------------------------------------------------------------------------------------
# the evidence store
# --------------------------------------------------------------------------------------------------
def test_evidence_is_fetched_once_saved_raw_and_refused_when_it_cannot_be_had(tmp_path, monkeypatch):
    calls = []
    body = json.dumps({"result": "success", "instruments": [_kr("PF_XBTUSD", "BTC", 4)]}).encode()

    def fake_get(url, timeout=30.0):
        calls.append(url)
        return 200, body, {"user_agent": "test-agent", "content_type": "application/json"}

    monkeypatch.setattr(x, "_http_get", _no_network)
    ev = x.load_evidence("kraken_instruments", allow_network=False, directory=tmp_path)
    assert ev["payload"] is None and ev["error"] and not list(tmp_path.iterdir())

    monkeypatch.setattr(x, "_http_get", lambda url, timeout=30.0: (503, b"busy", {}))
    ev = x.load_evidence("kraken_instruments", allow_network=True, directory=tmp_path)
    assert ev["payload"] is None and ev["error"] == "HTTP 503" and not list(tmp_path.iterdir())           # nothing is saved

    monkeypatch.setattr(x, "_http_get", lambda url, timeout=30.0: (200, b"[]", {}))                       # wrong shape
    ev = x.load_evidence("kraken_instruments", allow_network=True, directory=tmp_path)
    assert ev["payload"] is None and "not a Kraken instruments payload" in ev["error"] and not list(tmp_path.iterdir())

    monkeypatch.setattr(x, "_http_get", fake_get)
    ev = x.load_evidence("kraken_instruments", allow_network=True, directory=tmp_path)
    assert ev["error"] is None and ev["payload"]["instruments"][0]["symbol"] == "PF_XBTUSD"
    saved = tmp_path / x.ENDPOINTS["kraken_instruments"]["file"]
    meta = json.loads((tmp_path / "kraken_futures_instruments.meta.json").read_text())
    assert saved.read_bytes() == body                                                                     # raw, byte for byte
    assert meta["url"] == x.ENDPOINTS["kraken_instruments"]["url"] == calls[0] and meta["http_status"] == 200
    assert meta["sha256"] == x.sha256_bytes(body) and meta["bytes"] == len(body) and meta["user_agent"] == "test-agent"
    assert pd.Timestamp(meta["fetched_utc"]).tz is not None                                               # a UTC timestamp

    monkeypatch.setattr(x, "_http_get", _no_network)                                                      # on disk: never fetched again
    again = x.load_evidence("kraken_instruments", allow_network=True, directory=tmp_path)
    assert again["error"] is None and again["payload"] == ev["payload"] and len(calls) == 1
    assert again["meta"]["fetched_utc"] == meta["fetched_utc"]

    saved.write_bytes(body + b" ")                                                                        # altered after the fact
    assert "sha256" in x.load_evidence("kraken_instruments", allow_network=True, directory=tmp_path)["error"]


def test_cli_refuses_a_synthetic_run_without_a_scratch_directory():
    with pytest.raises(SystemExit):
        x.main(["realism", "--synthetic"])


# --------------------------------------------------------------------------------------------------
# --synthetic end to end, on the conductor's own synthetic tier-1 outputs
# --------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def smoke(tmp_path_factory):
    """A scratch run directory holding what `python -m scripts.factory.v2 tier1 --synthetic --out DIR` writes.
    Tier 1 refuses to run before the survivor freeze exists, so a stub freeze is written first."""
    out = tmp_path_factory.mktemp("v2_extras_smoke")
    (out / "SURVIVORS_FROZEN.json").write_text(json.dumps({"frozen_utc": "synthetic stub", "survivors": [], "candidates": [],
                                                           "n_formulas": 0}))
    v2.tier1(v2.Ctx(True, str(out)), only=E2E_BOOKS)
    for pid in E2E_BOOKS:
        assert (out / "tier1_w" / f"{pid}.parquet").exists() and (out / "tier1_net" / f"{pid}.parquet").exists()
    return out


def test_synthetic_realism_end_to_end(smoke, monkeypatch, tmp_path):
    monkeypatch.setattr(x, "_http_get", _no_network)
    monkeypatch.setattr(x, "EVIDENCE_DIR", tmp_path / "evidence_must_stay_empty")
    (smoke / "reports" / "REALISM.md").write_text("EARLIER SECTION\n")
    x.main(["realism", "--synthetic", "--out", str(smoke)])
    assert not (tmp_path / "evidence_must_stay_empty").exists()

    res = json.loads((smoke / "realism_results.json").read_text())
    assert res["synthetic"] is True and res["prereg_sha256"] == "SYNTHETIC"
    assert all(ev["meta"]["synthetic"] for ev in res["evidence"].values())
    recs = res["records"]
    assert len(recs) == len(x.BOOKS) * len(x.EUR_SIZES) * len(x.CONTRIBUTIONS_EUR) == 30
    assert {(r["book"], r["venue"]) for r in recs} == set(x.BOOKS)
    missing = [r for r in recs if r["book"] == "P.CRYPTO.ALL"]                 # no tier-1 output: refused visibly, never skipped
    assert len(missing) == 6 and all(r["status"].startswith("REFUSED: no Tier-1 target frame") for r in missing)
    ok = [r for r in recs if r["status"] == "OK"]
    assert len(ok) == 24 and all(r["synthetic"] for r in recs)

    eurusd = res["reference"]["EURUSD"]
    for r in ok:
        assert r["equity0_ccy"] == pytest.approx(r["equity0_eur"] * eurusd) and r["final_equity_ccy"] > 0
        assert r["final_equity_multiple_of_start"] == pytest.approx(r["final_equity_ccy"] / r["equity0_ccy"])
        c = r["costs"]
        assert min(c["fees_ccy"], c["spread_ccy"], c["financing_ccy"]) >= 0 and c["frictions_bp_year"] >= 0
        assert r["tracking_error_ann"] >= 0 and -1 <= r["max_drawdown"] <= 0 and r["turnover_sides_per_year"] >= 0
        o = r["orders"]
        assert o["n_skipped_lot_or_minimum"] == o["n_skipped_min_notional"] + o["n_targets_rounded_to_zero"]
        years = r["equity_path_year_end_multiple_of_start"]
        assert list(years.values())[-1] == pytest.approx(r["final_equity_multiple_of_start"])
        if r["monthly_contribution_eur"] == 0:
            assert r["contributions_ccy"] == 0 and r["final_equity_over_paid_in"] == pytest.approx(r["final_equity_multiple_of_start"])
        else:
            assert r["contributions_ccy"] > 0 and r["contributions_ccy"] / (100.0 * eurusd) == pytest.approx(
                round(r["contributions_ccy"] / (100.0 * eurusd)))              # a whole number of EUR 100 months
        assert (r["share_of_ideal_ann_return"] is None) == (r["ideal_ann_return"] <= 0)

    blocks = {b["book"]: b for b in res["venues"]}
    assert blocks["P.CRYPTO.ALL"]["status"].startswith("REFUSED")
    for pid in E2E_BOOKS:
        b = blocks[pid]
        assert b["status"] == "OK" and b["n_simulated_instruments"] + b["n_dropped_instruments"] == b["n_book_instruments"]
        assert all(r["basis"] in (x.FROM_FILE, x.VERIFIED, x.ASSUMED, x.UNKNOWN) and r["source"] for r in b["provenance"])
        paths = pd.read_parquet(smoke / b["paths_file"])
        assert len(paths) == b["n_prints"] and {"ideal_net", "ideal_growth", "net_eur1000_plus0", "equity_eur10000_plus100"} <= set(paths.columns)
        assert paths["equity_eur1000_plus0"].iloc[0] == pytest.approx(1.0, abs=0.02)             # opens at 1.0, less the opening costs
    # the fabricated venues list some instruments and not others: the book is restricted, and the drops are named
    for pid in ("P.CRYPTO.TREND", "P.CRYPTO.LO_TREND"):
        b = blocks[pid]
        assert 0 < b["n_simulated_instruments"] < b["n_book_instruments"] and 0 < b["listed_share_of_target_gross"] < 1
        assert {d["kind"] for d in b["dropped"]} >= {"not_listed", "price_mismatch", "no_binance_price", "not_eligible"}
        assert any(r["field"] == "lot_step" and r["basis"] == x.VERIFIED for r in b["provenance"])
    assert blocks["P.MACRO.LO_TREND"]["listed_share_of_target_gross"] == pytest.approx(1.0)
    assert blocks["P.MACRO.LO_TREND"]["long_only"] and blocks["P.MACRO.LO_TREND"]["rebalance"] == "monthly"
    assert not blocks["P.FX.G10.ALL"]["long_only"] and blocks["P.FX.G10.ALL"]["no_trade_band"] == v2.BUFFER

    # a fractional zero-commission venue at the lane's base cost tracks the ideal account closely at every size
    t212 = [r for r in ok if r["venue"] == "trading212_invest"]
    assert all(r["tracking_error_ann"] < 0.01 and abs(r["ann_return_gap_vs_ideal"]) < 0.005 for r in t212)
    assert all(r["costs"]["fees_ccy"] == 0 and r["costs"]["financing_ccy"] == 0 and r["costs"]["spread_ccy"] > 0 for r in t212)
    # 0.01-lot steps bite hardest on the smallest account
    fx = {(r["equity0_eur"], r["monthly_contribution_eur"]): r for r in ok if r["venue"] == "pepperstone_eu_ctrader"}
    assert fx[(1000.0, 0.0)]["orders"]["n_targets_rounded_to_zero"] > fx[(10000.0, 0.0)]["orders"]["n_targets_rounded_to_zero"] > 0
    assert fx[(1000.0, 0.0)]["tracking_error_ann"] > fx[(10000.0, 0.0)]["tracking_error_ann"]
    assert all(r["costs"]["financing_ccy"] > 0 for r in fx.values())
    # a EUR 5 minimum order skips more rebalancing orders on a small account
    bv = {(r["equity0_eur"], r["monthly_contribution_eur"]): r for r in ok if r["venue"] == "bitvavo"}
    assert bv[(1000.0, 0.0)]["orders"]["n_skipped_min_notional"] > bv[(10000.0, 0.0)]["orders"]["n_skipped_min_notional"]

    md = (smoke / "reports" / "REALISM.md").read_text()
    assert md.startswith("EARLIER SECTION\n") and md.count("## Realism pass") == 1                # appended, not overwritten
    assert "SYNTHETIC SMOKE TEST" in md and "REFUSED: no Tier-1 target frame" in md and "ASSUMED" in md and "VERIFIED" in md


def test_an_unreachable_endpoint_refuses_that_venue_and_the_others_still_run(smoke, tmp_path, monkeypatch):
    """The stage's REAL-mode branch (evidence from `real_evidence`, pins checked) with Kraken's instruments
    endpoint down: both Kraken books are REFUSED with the reason, the other three venues are simulated."""
    import shutil

    for sub in ("tier1_w", "tier1_net"):
        shutil.copytree(smoke / sub, tmp_path / sub)
    ctx = v2.Ctx(True, str(tmp_path))
    fabricated = x.synthetic_evidence(ctx, x.reference_eurusd()[0])
    for lane in ("MACRO", "FX", "CRYPTO-PERP", "CRYPTO-SPOT"):          # cache the synthetic panels and windows ...
        ctx.panel(lane)
        ctx.cfg(lane)
    ctx.synthetic = False                                               # ... then take the real-mode branch of the stage
    seen = {}

    def evidence(allow_network=True):
        seen["allow_network"] = allow_network
        down = {"payload": None, "meta": {"url": x.ENDPOINTS["kraken_instruments"]["url"]},
                "error": "GET failed: ConnectionError: unreachable"}
        return {"kraken_instruments": down, "kraken_tickers": fabricated["kraken_tickers"],
                "bitvavo_markets": fabricated["bitvavo_markets"]}

    monkeypatch.setattr(x, "real_evidence", evidence)
    monkeypatch.setattr(x, "_http_get", _no_network)
    monkeypatch.setattr(v2, "check_pins", lambda c: "f" * 64)
    out = x.stage_realism(ctx, allow_network=False)                     # what `realism --offline` calls
    assert seen == {"allow_network": False} and out["synthetic"] is False and out["prereg_sha256"] == "f" * 64

    by_book = {}
    for r in out["records"]:
        by_book.setdefault(r["book"], []).append(r["status"])
    assert all(len(v) == 6 for v in by_book.values()) and set(by_book) == {b for b, _ in x.BOOKS}
    kraken = by_book["P.CRYPTO.TREND"]
    assert all(st.startswith("REFUSED: instrument metadata unavailable") and "ConnectionError" in st
               and x.ENDPOINTS["kraken_instruments"]["url"] in st for st in kraken)
    assert all(st.startswith("REFUSED: no Tier-1 target frame") for st in by_book["P.CRYPTO.ALL"])
    for pid in ("P.MACRO.LO_TREND", "P.FX.G10.ALL", "P.CRYPTO.LO_TREND"):
        assert by_book[pid] == ["OK"] * 6
    saved = json.loads((tmp_path / "realism_results.json").read_text())
    assert saved["evidence"]["kraken_instruments"]["error"].startswith("GET failed") and len(saved["records"]) == 30
    md = (tmp_path / "reports" / "REALISM.md").read_text()
    assert "(real data)" in md and "**UNAVAILABLE**" in md and "REFUSED: instrument metadata unavailable" in md


@pytest.mark.parametrize("pid, venue", [("P.MACRO.LO_TREND", "trading212_invest"), ("P.CRYPTO.TREND", "kraken_derivatives_eea")])
def test_an_ideal_venue_through_the_same_wiring_reproduces_the_tier1_stream(smoke, tmp_path, monkeypatch, pid, venue):
    """The realism wiring (window, schedule, band, timing) with the IDEAL venue at the lane's base cost and a
    large account is the Tier-1 account itself — exactly, once every instrument has traded once after the
    opening. Whatever a real venue adds on top is therefore friction, not wiring."""
    import shutil

    for sub in ("tier1_w", "tier1_net"):
        shutil.copytree(smoke / sub, tmp_path / sub)
    ctx = v2.Ctx(True, str(tmp_path))
    spec = {s.id: s for s in x.registry.primaries()}[pid]

    def ideal_build(venue_id, cols, panel, evidence, eurusd):
        c, h = v2.cost_series(v2.COSTS[v2._t1_cost_key(spec)]["base"], cols)
        specs = {k: x.VenueSpec.ideal().with_overrides(fee_bp=float(c[k]), financing_long_bp_year=float(h[k]),
                                                       financing_short_bp_year=float(h[k])) for k in cols}
        return x.VenueBuild(venue_id, specs=specs)

    monkeypatch.setattr(x, "build_venue", ideal_build)
    monkeypatch.setattr(x, "EUR_SIZES", (1e7,))
    monkeypatch.setattr(x, "CONTRIBUTIONS_EUR", (0.0,))
    block, recs = x.realism_book(ctx, pid, venue, {}, 1.0)
    assert block["status"] == "OK" and len(recs) == 1 and recs[0]["status"] == "OK"
    assert block["listed_share_of_target_gross"] == pytest.approx(1.0)
    paths = pd.read_parquet(tmp_path / block["paths_file"])
    gap = (paths["net_eur10000000_plus0"] - paths["ideal_net"]).to_numpy()
    assert np.abs(gap[60:]).max() < 1e-12                                      # the same account, print for print
    assert np.abs(gap[:60]).max() > 0                                          # the opening itself is not the ideal's
    assert recs[0]["tracking_error_ann"] < 0.005 and abs(recs[0]["ann_return_gap_vs_ideal"]) < 0.002
    assert recs[0]["orders"]["n_skipped_lot_or_minimum"] == 0


def test_the_recomputed_ideal_account_is_the_saved_tier1_stream(smoke, tmp_path):
    ctx = v2.Ctx(True, str(smoke))
    spec = {s.id: s for s in x.registry.primaries()}["P.MACRO.LO_TREND"]
    cfg, panel = ctx.cfg(spec.lane), ctx.panel(spec.lane)
    w = pd.read_parquet(smoke / "tier1_w" / f"{spec.id}.parquet")
    idx = panel.window(cfg.full[0], cfg.full[1]).prices.index
    saved, src_saved = x.ideal_reference(ctx, spec, cfg, panel, w, idx)
    assert "column 'base'" in src_saved
    elsewhere = v2.Ctx(True, str(tmp_path))                                    # no tier1_net there: the reference is recomputed
    again, src_again = x.ideal_reference(elsewhere, spec, cfg, panel, w, idx)
    assert "recomputed" in src_again
    np.testing.assert_allclose(again.to_numpy(), saved.to_numpy(), rtol=0, atol=1e-12)


def test_synthetic_ladder_end_to_end(smoke, monkeypatch):
    monkeypatch.setattr(x, "_http_get", _no_network)
    x.main(["ladder", "--synthetic", "--out", str(smoke), "--reps", "400"])
    res = json.loads((smoke / "ladder_results.json").read_text())
    assert res["synthetic"] is True and res["reps"] == 400 and res["levels"] == list(x.LADDER_L)
    books = {b["book"]: b for b in res["books"]}
    assert list(books) == [b for b, _ in x.BOOKS] and books["P.CRYPTO.ALL"]["status"].startswith("REFUSED: no Tier-1 net stream")
    for pid in E2E_BOOKS:
        b = books[pid]
        ppy = v2.LANES[b["lane"]].ppy
        assert b["status"] == "OK" and b["horizon_prints"] == ppy and b["block"] == stats.default_block_length(b["n_obs"])
        assert [row["L"] for row in b["levels"]] == list(x.LADDER_L)
        for row in b["levels"]:
            assert 0 <= row["p05_wealth"] <= row["median_wealth"] <= row["p95_wealth"]
            assert 0 <= row["p_ruin_single_print_loss"] <= row["p_ruin"] <= row["p_final_below_half"] <= 1
            assert row["n_survivors"] == round((1 - row["p_ruin"]) * 400)
            assert (row["mean_log_wealth_survivors"] is None) == (row["n_survivors"] == 0)
            assert (row["actual_history_ruin_date"] is None) == (not row["actual_history_ruined"])
        top = b["levels"][-1]
        assert top["L"] == 200.0 and top["p_ruin"] > 0.99 and top["actual_history_ruined"]    # 200x on a 10-20 % vol book
        assert 0 <= b["growth_optimal"]["L"] <= x.GRID_MAX_L and "IN-SAMPLE" in b["growth_optimal"]["caveat"]
        assert b["kelly_continuous_time"]["L"] == pytest.approx(
            b["kelly_continuous_time"]["mean_per_print"] / b["kelly_continuous_time"]["variance_per_print"])

    btc = res["btc_200x"]
    assert btc["source"]["synthetic"] is True and len(btc["rows"]) == 4 and btc["missing_hourly_candles"] == 0
    rows = {(r["side"], r["adverse_move"]): r for r in btc["rows"]}
    for side in ("long", "short"):
        tight, wide = rows[(side, 0.0025)], rows[(side, 0.005)]
        for r in (tight, wide):
            assert 0 < r["share_within_1h"] <= r["share_within_4h"] <= r["share_within_24h"] <= 1
        assert tight["share_within_24h"] >= wide["share_within_24h"] and tight["share_within_1h"] >= wide["share_within_1h"]
    assert [f["round_trip_fee_pct_of_margin"] for f in btc["fees"]] == pytest.approx([20.0, 8.0])
    eu = res["eu_leverage"]
    assert eu["x200_available"] is False and eu["kraken_eea_retail_cap"] == 10 and eu["esma_retail_cfd_caps"]["crypto"] == 2

    md = (smoke / "reports" / "LEVERAGE_LADDER.md").read_text()
    assert "SYNTHETIC SMOKE TEST" in md and "LOWER BOUND" in md and "200× is not available" in md and "IN-SAMPLE" in md
