"""MACRO lane: 40 US ETFs (research proxies; the 41 of DESIGN v2 §2 minus CPER), Alpaca SIP daily bars.

Offline: reads research/factory/data/raw/{alpaca,fred,ecb}/ (download with
`python -m scripts.factory.data.sources alpaca fred ecb`).

    python -m scripts.factory.data.macro

prices            daily bar close with adjustment=all (splits, dividends, spin-offs) — the decision print
aux raw_close     the same bar with adjustment=raw (the price actually printed that day)
aux volume        shares traded that session (adjustment=raw bar)
aux usd_per_eur   ECB reference rate of the same date (fixed at 14:15 CET, i.e. BEFORE the 16:00 New York
                  close); on a date without an ECB fixing the last fixing, at most 3 sessions old
aux rates         column USD: effective fed funds (FRED DFF), decimal per year, last observation dated
                  strictly before the session date
carry             -i_usd * days / 360 for every instrument (financing of a funded long), days = calendar
                  days since the previous session; first row NaN
tbill             +i_usd * days / 360
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import sources as S
from .common import utc_now
from .fx import day_counts, provenance
from .panelio import MAX_FFILL, asof_on_or_before, asof_strictly_before, limited_ffill, to_utc_index, write_lane

ASSET_CLASS = {
    **{s: "equity_region" for s in ["SPY", "QQQ", "IWM", "EFA", "EEM", "VGK", "EWJ", "EWU", "EWG", "FXI", "INDA", "EWZ",
                                    "EWA", "EWC", "EWY", "EWT"]},
    **{s: "equity_sector" for s in ["XLE", "XLF", "XLK", "XLV", "XLU", "XLI", "XLP", "XLY", "XLB"]},
    **{s: "bond" for s in ["SHY", "IEF", "TLT", "TIP", "LQD", "HYG", "EMB", "AGG"]},
    **{s: "commodity" for s in ["GLD", "SLV", "USO", "UNG", "DBC", "DBA", "CPER"]},
    "VNQ": "real_estate",
}
assert set(ASSET_CLASS) == set(S.MACRO_ETFS)
# Conductor ruling 2026-11-10: CPER is dropped from the lane (the raw bars stay on disk).
EXCLUDED = {"CPER": "thin trading: 47 sessions with zero trades (2016-2018) and 490 sessions with fewer than 20 trades "
                    "(last 2020-01-07); under the <= 3-session forward-fill rule its 4th consecutive no-trade session "
                    "(2017-07-14, inside the design window) is a missing print"}
CLOSE = ("16:00", "America/New_York")


def build_macro() -> None:
    adj = S.read_alpaca("all")
    raw = S.read_alpaca("raw")
    cols = [c for c in S.MACRO_ETFS if c not in EXCLUDED]
    missing = [c for c in cols if c not in adj or c not in raw]
    if missing:
        raise RuntimeError(f"Alpaca returned no bars for {missing}")
    dates = pd.DatetimeIndex(sorted(set().union(*[set(adj[c].index) for c in cols])))
    prices = pd.DataFrame({c: adj[c]["c"].reindex(dates) for c in cols})
    raw_close = pd.DataFrame({c: raw[c]["c"].reindex(dates) for c in cols})
    volume = pd.DataFrame({c: raw[c]["v"].reindex(dates) for c in cols}).astype("float64")
    trades = pd.DataFrame({c: raw[c]["n"].reindex(dates) for c in cols}).astype("float64")
    # A session with ZERO trades is not a print: the vendor emits a flat bar that repeats the previous close.
    # Treat it as missing and forward-fill under the lane rule (<= 3 consecutive sessions), so it is counted.
    no_print = (trades <= 0) | (volume <= 0) | trades.isna()
    prices, ffill_stats = limited_ffill(prices.where(~no_print), MAX_FFILL)
    raw_close, _ = limited_ffill(raw_close.where(~no_print), MAX_FFILL)
    idx = to_utc_index(dates, *CLOSE)

    dff = S.read_fred("DFF")
    i_usd, st_dff = asof_strictly_before(dff, dates, max_stale_prints=10)
    i_usd = i_usd / 100.0
    days = day_counts(dates)
    acc = i_usd * days / 360.0
    carry = pd.DataFrame({c: -acc for c in cols}, index=dates)
    tbill = acc.rename("tbill")
    eur, st_eur = asof_on_or_before(S.read_ecb_exr("USD"), dates, max_stale_prints=MAX_FFILL)

    per = {}
    ret = prices.pct_change(fill_method=None)
    for c in cols:
        a = adj[c]
        r = ret[c].dropna()
        big = r[r.abs() > 0.20]
        ratio = (prices[c] / raw_close[c])
        per[c] = {"first_bar": str(a.index[0].date()), "last_bar": str(a.index[-1].date()), "bars": int(len(a)),
                  "sessions_missing_vs_union": int(len(dates.difference(a.index))),
                  "missing_dates": [str(d.date()) for d in dates.difference(a.index)][:50],
                  "adjusted_over_raw_first": float(ratio.iloc[0]), "adjusted_over_raw_last": float(ratio.iloc[-1]),
                  # adjusted closes are rounded to cents by the vendor, so tiny ratio wiggles are rounding noise
                  "adjustment_events_over_2bp": int((ratio.pct_change(fill_method=None).abs() > 2e-4).sum()),
                  "min_adjusted_close": float(prices[c].min()),
                  "max_rounding_error_bp_of_price": round(0.005 / float(prices[c].min()) * 1e4, 2),
                  "one_day_moves_over_20pct": {str(d.date()): round(float(v), 4) for d, v in big.items()},
                  "zero_trade_sessions": int(no_print[c].sum()),
                  "sessions_with_fewer_than_20_trades": int((trades[c] < 20).sum()),
                  "last_session_with_fewer_than_20_trades": (None if not (trades[c] < 20).any()
                                                             else str(dates[np.flatnonzero((trades[c] < 20).to_numpy())[-1]].date())),
                  "asset_class": ASSET_CLASS[c]}
    groups = {}
    for c in cols:
        groups.setdefault(ASSET_CLASS[c], []).append(c)
    groups["equity"] = groups["equity_region"] + groups["equity_sector"]
    groups["ALL"] = cols

    def utc(df):
        out = df.copy()
        out.index = idx
        return out

    aux = {"raw_close": utc(raw_close), "volume": utc(volume), "trade_count": utc(trades),
           "usd_per_eur": utc(eur.to_frame("usd_per_eur")), "rates": utc(i_usd.to_frame("USD"))}
    meta = {
        "periods_per_year": 252,
        "print_convention": "Row = one regular US equity session. Index = the session date at 16:00 America/New_York "
                            "(the scheduled close) converted to UTC; on early-close sessions the market actually closes "
                            "at 13:00 New York time and the label is still 16:00. Price = Alpaca daily bar close, SIP "
                            "feed, adjustment=all (split-, dividend- and spin-off-adjusted). Evaluation is lag = 1 "
                            "(fill at the next close).",
        "universe_groups": groups,
        "asset_class_of": {c: ASSET_CLASS[c] for c in cols},
        "excluded_instruments": dict(EXCLUDED),
        "rates_unit": "decimal per year (0.05 = 5 %), last DFF observation dated strictly before the session date",
        "carry_convention": "-i_usd * days / 360 for every instrument; days = calendar days since the previous session; first row NaN",
        "research_proxy_note": "US-listed ETFs are research proxies for wrappers an NL retail account can use (DESIGN v2 §0 #3)",
        "adjusted_prices_note": "adjustment=all is the vendor's CURRENT back-adjustment (as of the fetch); it is a "
                                "total-return style series, not a price that printed on the day — see aux['raw_close']. "
                                "The vendor rounds adjusted closes to whole cents: a daily return carries up to "
                                "+/- (1 cent / price) of rounding noise (see per_etf.max_rounding_error_bp_of_price).",
        "first_row_all_groups_complete": str(idx[1]),
        "last_row_all_groups_complete": str(idx[np.flatnonzero(carry.notna().all(axis=1).to_numpy())[-1]]),
    }
    manifest = {
        "sources": {"alpaca": provenance("alpaca", [p.name for p in sorted((S.RAW / "alpaca").glob("bars_1Day_*"))]),
                    "alpaca_request": {"endpoint": "https://data.alpaca.markets/v2/stocks/bars", "timeframe": "1Day",
                                       "feed": "sip", "adjustment": ["all", "raw"], "start": "2016-01-01",
                                       "symbols": list(S.MACRO_ETFS),
                                       "note": "CPER was downloaded with the other 40 and is excluded from the lane"},
                    "fred": provenance("fred", ["DFF.csv"]), "ecb": provenance("ecb", ["EXR_D_USD_EUR_SP00_A.csv"])},
        "rate_series": {"USD": {"series": "FRED DFF (effective federal funds rate)", "asof": st_dff}},
        "usd_per_eur": {"series": "ECB EXR/D.USD.EUR.SP00.A, fixing of the same date (on or before), <= 3 sessions old",
                        "asof": st_eur},
        "per_etf": per,
        "price_gaps": {"rule": f"a session with zero trades is a missing print (the vendor's flat bar is discarded); "
                               f"forward-fill at most {MAX_FFILL} consecutive sessions, longer gaps stay NaN",
                       "per_instrument": ffill_stats},
        "thin_trading_warning": {c: {"zero_trade_sessions": per[c]["zero_trade_sessions"],
                                     "sessions_with_fewer_than_20_trades": per[c]["sessions_with_fewer_than_20_trades"],
                                     "last_such_session": per[c]["last_session_with_fewer_than_20_trades"]}
                                 for c in cols if per[c]["sessions_with_fewer_than_20_trades"] > 0},
        "day_count_distribution": {str(int(k)): int(v) for k, v in days.dropna().value_counts().sort_index().items()},
        "exclusions": dict(EXCLUDED),
    }
    tb = tbill.copy()
    tb.index = idx
    write_lane("MACRO", utc(prices)[cols], utc(carry)[cols], tb, aux, meta, manifest)
    print(f"{utc_now()} built MACRO: {prices.shape} {idx[0]} .. {idx[-1]}", flush=True)


def main(argv=None) -> int:
    build_macro()
    return 0


if __name__ == "__main__":
    sys.exit(main())
