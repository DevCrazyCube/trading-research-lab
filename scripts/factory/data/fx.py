"""FX lanes: `FX` (ECB fix), `FX-EXEC` (ECB fix decision + FRED noon-NY execution), `FX-FRED` (H.10 noon).

Offline: reads research/factory/data/raw/{ecb,fred,bis}/ only (download them with
`python -m scripts.factory.data.sources fred ecb bis`).

    python -m scripts.factory.data.fx            # builds the three lanes

PRICES            USD per 1 unit of foreign currency.
                  ECB: EUR = USD per EUR; X = (USD per EUR) / (X per EUR)   [cross through the euro]
                  FRED H.10: DEXUSxx series are already USD per FX, DEXxxUS series are inverted.
CARRY             (i_fx - i_usd) * days / 360, `days` = calendar days since the previous print, rates in
                  decimal per year, each rate LAGGED: the last observation dated strictly before the
                  print's date (>= 1 business day old). First row NaN (no previous print).
RATES             USD  effective federal funds rate, FRED DFF
                  EUR  EONIA (ECB EON/D.EONIA_TO.RATE) through 2019-09-30, EUR short-term rate
                       (ECB EST/B.EU000A2X2A25.WT) from 2019-10-01
                  GBP  SONIA (FRED IUDSOIA) from 1997-01-02, BIS policy rate (WS_CBPOL D.GB) before
                  CHF CAD AUD NZD SEK NOK MXN ZAR PLN HUF CZK ILS TRY   BIS WS_CBPOL daily policy rate
                  JPY  BIS WS_CBPOL D.JP; BIS carries NO Japanese policy rate for 1999-02-12..2000-08-10,
                       2001-03-19..2006-03-08 and 2013-04-04..2016-09-20 ("no policy rate": ZIRP / QE / QQE).
                       Those three windows are filled with the monthly average uncollateralised call money
                       rate (FRED IRSTCI01JPM156N, OECD), month M usable from the 1st day of month M+1.
                       This is a DEVIATION from "BIS daily policy rates" and is flagged in the manifest;
                       set JPY_GAP_FILL = False to leave those prints NaN.
                  SGD  none (MAS targets the exchange rate; BIS publishes no SG policy rate) -> carry NaN
STALENESS         A policy rate is a step function: a rate observation is carried for at most
                  RATE_MAX_STALE_PRINTS (10) prints when the source has no newer observation (holiday weeks,
                  the ~1 week publication lag of the BIS file); beyond that the rate and the carry are NaN.
                  Prices (and oil) are never carried for more than 3 prints.
"""
from __future__ import annotations

import sys
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from . import sources as S
from .common import fetch_log, utc_now
from .panelio import (MAX_FFILL, asof_strictly_before, cpi_available, limited_ffill, to_utc_index, write_lane)

G10 = ["EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK"]
EM = ["MXN", "ZAR", "SGD", "PLN", "HUF", "CZK", "ILS"]
SENS = ["TRY"]
FX_COLS = G10 + EM + SENS

RATE_MAX_STALE_PRINTS = 10                     # see STALENESS in the module docstring
JPY_GAP_FILL = True                            # fill BIS "no policy rate" windows with the OECD call money rate
JPY_GAP_SERIES = "IRSTCI01JPM156N"
EUR_SWITCH = pd.Timestamp("2019-10-01")        # first EUR short-term rate observation
SONIA_START = pd.Timestamp("1997-01-02")       # first FRED IUDSOIA observation

# FRED H.10 series -> (currency, invert?)
H10 = {"EUR": ("DEXUSEU", False), "GBP": ("DEXUSUK", False), "JPY": ("DEXJPUS", True), "CHF": ("DEXSZUS", True),
       "CAD": ("DEXCAUS", True), "AUD": ("DEXUSAL", False), "NZD": ("DEXUSNZ", False), "SEK": ("DEXSDUS", True),
       "NOK": ("DEXNOUS", True), "MXN": ("DEXMXUS", True), "ZAR": ("DEXSFUS", True), "SGD": ("DEXSIUS", True)}
FRED_LANE_COLS = ["EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK"]
EXEC_LANE_COLS = ["EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK", "MXN", "ZAR", "SGD"]
QUARTERLY_CPI = {"AUD", "NZD"}

ECB_PRINT = ("14:15", "Europe/Berlin")
NY_NOON = ("12:00", "America/New_York")


# ----------------------------------------------------------------------------------------- rate sources
def rate_observations(ccy: str) -> Tuple[Optional[pd.Series], dict]:
    """Overnight / policy rate observations for one currency, PER CENT per year, naive date index."""
    if ccy == "USD":
        s = S.read_fred("DFF")
        return s, {"series": "FRED DFF (effective federal funds rate, 7-day series)", "first_obs": str(s.dropna().index[0].date()),
                   "last_obs": str(s.dropna().index[-1].date())}
    if ccy == "EUR":
        eon = S.read_ecb_rate("EONIA").dropna()
        est = S.read_ecb_rate("ESTR").dropna()
        s = pd.concat([eon[eon.index < EUR_SWITCH], est[est.index >= EUR_SWITCH]]).sort_index()
        return s, {"series": "ECB EON/D.EONIA_TO.RATE (EONIA) through 2019-09-30, then ECB EST/B.EU000A2X2A25.WT "
                             "(euro short-term rate)", "first_obs": str(s.index[0].date()), "last_obs": str(s.index[-1].date()),
                   "splice_date": str(EUR_SWITCH.date()),
                   "level_at_splice": {"EONIA_2019-09-30": float(eon[eon.index < EUR_SWITCH].iloc[-1]),
                                       "ESTR_2019-10-01": float(est[est.index >= EUR_SWITCH].iloc[0])}}
    if ccy == "GBP":
        son = S.read_fred("IUDSOIA").dropna()
        bis = S.read_bis_cbpol("GB").dropna()
        s = pd.concat([bis[bis.index < SONIA_START], son[son.index >= SONIA_START]]).sort_index()
        meta = S.read_bis_meta("WS_CBPOL_D_GB_meta.csv")
        return s, {"series": "FRED IUDSOIA (SONIA) from 1997-01-02; BIS WS_CBPOL D.GB before",
                   "first_obs": str(s.index[0].date()), "last_obs": str(s.index[-1].date()),
                   "splice_date": str(SONIA_START.date()), "bis_compilation": meta.get("COMPILATION")}
    if ccy == "SGD":
        return None, {"series": None, "note": "no defensible overnight/policy rate: MAS targets the exchange rate "
                                              "(S$NEER band), and BIS WS_CBPOL has no SG series (HTTP 404 "
                                              "'No data' recorded in raw/bis/WS_CBPOL_D_SG.NO_DATA.xml)"}
    cc = S.BIS_CBPOL_AREA[ccy]
    s = S.read_bis_cbpol(cc)
    meta = S.read_bis_meta(f"WS_CBPOL_D_{cc}_meta.csv")
    v = s.dropna()
    desc = {"series": f"BIS WS_CBPOL D.{cc} (daily central bank policy rate)", "first_obs": str(v.index[0].date()),
            "last_obs": str(v.index[-1].date()), "bis_compilation": meta.get("COMPILATION"),
            "bis_source": meta.get("SOURCE_REF")}
    gaps = source_gaps(v)
    desc["source_gaps_over_10_calendar_days"] = [{"after": str(a.date()), "before": str(b.date())} for a, b in gaps]
    if ccy == "JPY" and JPY_GAP_FILL and gaps:
        call = S.read_fred(JPY_GAP_SERIES).dropna()             # month-start index, monthly average, per cent
        parts = [v]
        for a, b in gaps:
            days = pd.date_range(a + pd.Timedelta(days=1), b - pd.Timedelta(days=1), freq="D")
            prev_month = (days.to_period("M") - 1).to_timestamp()     # month M-1 for a day in month M
            fill = pd.Series(call.reindex(prev_month).to_numpy(), index=days).dropna()
            parts.append(fill)
        v = pd.concat(parts).sort_index()
        desc["series"] += (f"; inside the BIS 'no policy rate' windows: FRED {JPY_GAP_SERIES} (OECD immediate rate, "
                           "call money/interbank, monthly average), month M used from the 1st day of month M+1")
        desc["gap_fill"] = {"deviation_from_brief": "the brief asks for BIS daily policy rates; BIS has none for JPY "
                                                    "in these windows", "series": f"FRED {JPY_GAP_SERIES}",
                            "windows": desc["source_gaps_over_10_calendar_days"],
                            "calendar_days_filled": int(sum(len(p) for p in parts[1:]))}
        return v, desc
    return s, desc


def source_gaps(v: pd.Series, min_days: int = 10) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    """(last obs before, first obs after) for every hole of more than `min_days` calendar days."""
    idx = v.dropna().index
    d = np.diff(idx.values).astype("timedelta64[D]").astype(int)
    return [(idx[i], idx[i + 1]) for i in np.flatnonzero(d > min_days)]


def build_rates(print_dates: pd.DatetimeIndex, ccys: List[str]) -> Tuple[pd.DataFrame, dict]:
    """Lagged rate levels at each print, DECIMAL per year; columns = ccys + ['USD']."""
    cols, info = {}, {}
    for c in ccys + ["USD"]:
        obs, desc = rate_observations(c)
        if obs is None:
            cols[c] = pd.Series(np.nan, index=print_dates)
            info[c] = desc
            continue
        v, st = asof_strictly_before(obs, print_dates, max_stale_prints=RATE_MAX_STALE_PRINTS)
        cols[c] = v / 100.0
        info[c] = {**desc, "asof": st}
    return pd.DataFrame(cols, index=print_dates), info


def build_cpi(print_dates: pd.DatetimeIndex, ccys: List[str]) -> Tuple[pd.DataFrame, dict]:
    cols, info = {}, {}
    for c in ccys + ["USD"]:
        cc = S.BIS_CPI_AREA[c]
        s = S.read_bis_cpi(cc)
        if s is None:
            cols[c] = pd.Series(np.nan, index=print_dates)
            info[c] = {"series": None}
            continue
        v, st = cpi_available(s, print_dates, quarterly=c in QUARTERLY_CPI)
        cols[c] = v
        info[c] = {"series": f"BIS WS_LONG_CPI M.{cc}.628 (index, 2010 = 100)", **st}
    return pd.DataFrame(cols, index=print_dates), info


def build_oil(print_dates: pd.DatetimeIndex) -> Tuple[pd.DataFrame, dict]:
    """WTI level, lagged one day. Non-positive observations (the -36.98 settlement of 20 Apr 2020) are set
    to NaN BEFORE the <= 3-print forward-fill, so a ratio-based rule never divides by them (conductor
    ruling 2026-11-10)."""
    raw = S.read_fred("DCOILWTICO")
    o = raw.dropna()
    bad = o[o <= 0]
    obs = raw.where(raw > 0)
    v, st = asof_strictly_before(obs, print_dates)
    st.update({"series": "FRED DCOILWTICO (WTI spot, USD per barrel), price LEVEL, lagged one day",
               "non_positive_observations_set_to_nan": {str(d.date()): float(x) for d, x in bad.items()},
               "non_positive_observations_set_to_nan_count": int(len(bad)),
               "min_level_in_panel": float(v.min())})
    return v.to_frame("WTI"), st


def us_business_days(last: pd.Timestamp) -> Tuple[pd.DatetimeIndex, pd.Timestamp]:
    """Federal Reserve business days = the dates on which the H.10 release carries a rate (any DEX series
    on disk; the release is not produced on Federal Reserve holidays). Past the last H.10 date the calendar
    is continued with Monday-Friday weekdays up to `last`. Returns (calendar, last H.10 date)."""
    days = set()
    for sid, _ in H10.values():
        days |= set(S.read_fred(sid).dropna().index)
    cal = pd.DatetimeIndex(sorted(days))
    h10_last = cal[-1]
    if last > h10_last:
        cal = cal.append(pd.bdate_range(h10_last + pd.Timedelta(days=1), last))
    return cal, h10_last


def usd_signal_rate(print_dates: pd.DatetimeIndex) -> Tuple[pd.Series, dict]:
    """USD rate that was PUBLISHED before a 14:15 Europe/Berlin print (per cent per year).

    The effective federal funds rate of business day b is released on the next Federal Reserve business
    day at about 09:00 New York time, i.e. AFTER the ECB fixing of that day. So for a print dated D the
    freshest rate already public is that of the business day before L, where L is the last Federal
    Reserve business day strictly before D ("the business day two days before the print")."""
    cal, h10_last = us_business_days(print_dates[-1])
    dff = S.read_fred("DFF")
    c = cal.values.astype("datetime64[ns]")
    d = print_dates.values.astype("datetime64[ns]")
    iL = np.searchsorted(c, d, side="left") - 1          # last business day < D
    ib = iL - 1                                          # the business day before it
    ok = ib >= 0
    b = pd.DatetimeIndex(c[np.clip(ib, 0, None)])
    val = np.where(ok, dff.reindex(b).to_numpy(dtype="float64"), np.nan)
    out = pd.Series(val, index=print_dates)
    st = {"rule": "DFF of the Federal Reserve business day before L, L = last such day strictly before the print date",
          "business_day_calendar": "dates with a rate in the Federal Reserve H.10 release (FRED DEX* series); "
                                   f"weekdays after the last H.10 date ({h10_last.date()})",
          "prints_using_the_weekday_continuation": int((d > np.datetime64(h10_last)).sum()),
          "nan": int(np.isnan(val).sum()),
          "calendar_days_between_rate_and_print": {str(int(k)): int(n) for k, n in
                                                   pd.Series((d - b.values).astype("timedelta64[D]").astype(int)[ok]).value_counts().sort_index().items()}}
    return out, st


def day_counts(print_dates: pd.DatetimeIndex) -> pd.Series:
    d = pd.Series(print_dates.values, index=print_dates).diff().dt.days.astype("float64")
    return d                                                 # first row NaN


def provenance(source: str, rels: List[str]) -> List[dict]:
    log = fetch_log(source)
    out = []
    for rel in rels:
        rec = log.get(f"raw/{source}/{rel}")
        out.append(rec if rec else {"path": f"raw/{source}/{rel}", "missing": True})
    return out


def _sources_block(ccys: List[str], *, ecb: bool, h10: List[str]) -> dict:
    blk = {}
    if ecb:
        blk["ecb_exr"] = provenance("ecb", [f"EXR_D_{c}_EUR_SP00_A.csv" for c in S.ECB_CCYS])
    blk["ecb_rates"] = provenance("ecb", ["EON_D_EONIA_TO_RATE.csv", "EST_B_EU000A2X2A25_WT.csv"])
    blk["fred"] = provenance("fred", ["DFF.csv", "IUDSOIA.csv", "DCOILWTICO.csv", f"{JPY_GAP_SERIES}.csv"]
                             + [f"{s}.csv" for s in h10])
    bis = []
    for c in ccys:
        cc = S.BIS_CBPOL_AREA.get(c)
        if cc and c != "SGD":
            bis += [f"WS_CBPOL_D_{cc}.csv", f"WS_CBPOL_D_{cc}_meta.csv"]
    bis += ["WS_CBPOL_D_SG.NO_DATA.xml"]
    for c in ccys + ["USD"]:
        bis += [f"WS_LONG_CPI_M_{S.BIS_CPI_AREA[c]}_628.csv"]
    blk["bis"] = provenance("bis", bis)
    return blk


def _finish(lane: str, dates: pd.DatetimeIndex, clock: Tuple[str, str], prices: pd.DataFrame, ffill_stats: dict,
            cols: List[str], groups: dict, extra_aux: dict, extra_meta: dict, extra_manifest: dict,
            carry_override: Optional[pd.DataFrame] = None, tbill_override: Optional[pd.Series] = None,
            usd_signal_extra_lag: bool = False) -> None:
    rates, rate_info = build_rates(dates, cols)
    cpi, cpi_info = build_cpi(dates, cols)
    oil, oil_info = build_oil(dates)
    days = day_counts(dates)
    if carry_override is None:
        carry = pd.DataFrame({c: (rates[c] - rates["USD"]) * days / 360.0 for c in cols}, index=dates)
        tbill = (rates["USD"] * days / 360.0).rename("tbill")
    else:
        carry, tbill = carry_override, tbill_override
    usd_note = None
    if usd_signal_extra_lag:
        # SIGNAL input only: the USD column of aux['rates'] is the rate already published before the 14:15
        # print. carry and tbill above keep the accrual rate (the rate that applied to the interval).
        sig, sig_st = usd_signal_rate(dates)
        rates = rates.copy()
        rates["USD"] = sig / 100.0
        rate_info["USD"] = {**rate_info["USD"], "signal_column": sig_st,
                            "asymmetry": "aux['rates']['USD'] is lagged one extra business day (published before the "
                                         "print); carry and tbill use the one-day-lagged accrual rate described in 'asof'"}
        usd_note = ("aux['rates']['USD'] = effective fed funds of the Federal Reserve business day two before the "
                    "print date (already published at 14:15 Europe/Berlin). carry and tbill are NOT built from it: "
                    "they accrue the rate of the last calendar day before the print. Hence "
                    "carry[c] = aux['rates'][c] * days/360 - tbill, and carry[c] != (rates[c] - rates['USD']) * days/360.")
    # instruments whose price exists but whose financing leg is unknown may not be held
    mask = prices.notna() & carry.notna()
    usable = [c for g in ("G10", "EM") for c in groups.get(g, [])]
    complete = carry[usable].notna().all(axis=1) & prices[usable].notna().all(axis=1)
    idx = to_utc_index(dates, *clock)
    last_complete = None if not complete.any() else str(idx[np.flatnonzero(complete.to_numpy())[-1]])
    first_complete = None if not complete.any() else str(idx[np.flatnonzero(complete.to_numpy())[0]])

    def utc(df):
        out = df.copy()
        out.index = idx
        return out

    aux = {"rates": utc(rates), "cpi": utc(cpi), "oil": utc(oil), "universe_mask": utc(mask)}
    aux.update({k: utc(v) for k, v in extra_aux.items()})
    meta = {
        "periods_per_year": 252,
        "universe_groups": groups,
        "rates_unit": "decimal per year (0.05 = 5 %), lagged: last observation dated strictly before the print date",
        "carry_convention": "(i_fx - i_usd) * days / 360; days = calendar days since the previous print; first row NaN",
        "cpi_convention": "index level; a monthly observation is usable from the 1st day of the 2nd month after its "
                          "reference month starts, a quarterly one (AUD, NZD) from the 1st day of the 4th month after "
                          "its reference quarter starts; step function until the next release; current-vintage data "
                          "(NOT real-time vintages)",
        "oil_convention": "WTI spot price level (USD/bbl), FRED DCOILWTICO, last observation dated strictly before the "
                          "print; non-positive observations (one: -36.98 on 2020-04-20) are set to NaN before the "
                          "<= 3-print forward-fill, so every value in aux['oil'] is > 0",
        "universe_mask_note": "True where the price AND the carry of the instrument are known at the row (an "
                              "instrument without a financing leg may not be held: the engine refuses it)",
        "first_row_all_groups_complete": first_complete,
        "last_row_all_groups_complete": last_complete,
    }
    if usd_note:
        meta["usd_rate_asymmetry"] = usd_note
        meta["rates_unit"] = ("decimal per year (0.05 = 5 %); every currency: last observation dated strictly before the "
                              "print date; USD: one EXTRA business day (see usd_rate_asymmetry)")
        meta["carry_convention"] = ("(i_fx - i_usd) * days / 360 with i_usd = effective fed funds of the last calendar day "
                                    "before the print (accrual, NOT the USD column of aux['rates']); days = calendar days "
                                    "since the previous print; first row NaN")
    meta.update(extra_meta)
    tail_nan = {c: int(carry[c].iloc[::-1].isna().cummin().sum()) for c in cols}
    manifest = {
        "sources": _sources_block(cols, ecb=lane != "FX-FRED", h10=[H10[c][0] for c in cols if c in H10] if lane != "FX" else []),
        "rate_series": rate_info,
        "cpi_series": cpi_info,
        "oil_series": oil_info,
        "price_gaps": {"rule": f"forward-fill at most {MAX_FFILL} consecutive missing prints inside an instrument's life; "
                               "longer gaps stay NaN", "per_instrument": ffill_stats},
        "carry_trailing_nan_prints": tail_nan,
        "carry_nan_inside_price_life": {c: int((carry[c].isna() & prices[c].notna()).sum()) for c in cols},
        "day_count_distribution": {str(int(k)): int(v) for k, v in days.dropna().value_counts().sort_index().items()},
    }
    manifest.update(extra_manifest)
    carry_u, tbill_u, prices_u = utc(carry), tbill.copy(), utc(prices)
    tbill_u.index = idx
    write_lane(lane, prices_u[cols], carry_u[cols], tbill_u, aux, meta, manifest)
    print(f"{utc_now()} built {lane}: {prices_u.shape} {idx[0]} .. {idx[-1]} last complete row {last_complete}", flush=True)


# ------------------------------------------------------------------------------------------------- lanes
def ecb_prices() -> Tuple[pd.DataFrame, dict]:
    """USD per 1 FX from the ECB reference rates, on the dates the USD fixing exists."""
    usd = S.read_ecb_exr("USD").dropna()
    dates = usd.index
    px = {"EUR": usd}
    for c in FX_COLS:
        if c == "EUR":
            continue
        x = S.read_ecb_exr(c).reindex(dates)
        px[c] = usd / x
    raw = pd.DataFrame(px, index=dates)[FX_COLS]
    filled, st = limited_ffill(raw, MAX_FFILL)
    for c in FX_COLS:
        st[c]["first_print"] = str(raw[c].first_valid_index().date())
        st[c]["prints_before_first"] = int(raw[c].loc[:raw[c].first_valid_index()].isna().sum())
    return filled, st


def build_fx() -> None:
    prices, st = ecb_prices()
    dates = prices.index
    groups = {"G10": G10, "EM": [c for c in EM if c != "SGD"], "SENSITIVITY": SENS}
    meta = {
        "print_convention": "Row = one ECB euro foreign exchange reference rate. The rate is fixed in the daily "
                            "concertation around 14:10 CET and PUBLISHED around 16:00 CET the same day (conductor note "
                            "2026-11-10, from the data-sources researcher; not re-verified by this build). The row "
                            "timestamp is the fixing date at 14:15 Europe/Berlin converted to UTC — the conservative "
                            "DECISION instant (the information content of the price is no later than 14:15). "
                            "Price = USD per 1 unit of foreign currency, crossed through the euro: EUR = USD per EUR; "
                            "X = (USD per EUR) / (X per EUR). Primary evaluation is lag = 1 (fill at the next fixing). "
                            "The reference rate is a published mid, not a dealable quote.",
        "excluded_from_universe_groups": {"SGD": "no defensible rate series (MAS targets the exchange rate; BIS has no SG "
                                                 "policy rate) -> price column is loaded, carry is NaN, not in G10/EM"},
        "usd_leg_publication_note": "The effective federal funds rate of day t-1 (FRED DFF) is released by the New York "
                                    "Fed on day t at about 09:00 New York time (its stated schedule; not re-verified by "
                                    "this build) = 15:00 Berlin time, i.e. about 45 minutes AFTER the 14:15 row timestamp "
                                    "(14:00 Berlin time during the US/EU daylight-saving mismatch weeks). The carry "
                                    "accrual for (t-1, t] correctly uses the t-1 rate. For SIGNALS the USD column of "
                                    "aux['rates'] is therefore lagged one extra business day (conductor ruling "
                                    "2026-11-10) - see usd_rate_asymmetry.",
    }
    _finish("FX", dates, ECB_PRINT, prices, st, FX_COLS, groups, {}, meta,
            {"exclusions": meta["excluded_from_universe_groups"]}, usd_signal_extra_lag=True)


def h10_prices(cols: List[str]) -> pd.DataFrame:
    """USD per 1 FX from FRED H.10 noon buying rates (NaN where H.10 has no value)."""
    out = {}
    for c in cols:
        sid, inv = H10[c]
        s = S.read_fred(sid)
        out[c] = (1.0 / s) if inv else s
    return pd.DataFrame(out)


def exec_after_decision(dates: pd.DatetimeIndex) -> Tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """(decision timestamps, execution timestamps) in UTC for the FX-EXEC lane; raises unless the noon
    New York print is strictly later than the 14:15 Berlin print on EVERY row (all DST regimes)."""
    dec = to_utc_index(dates, *ECB_PRINT)
    exe = to_utc_index(dates, *NY_NOON)
    later = np.asarray(exe > dec)
    if not later.all():
        bad = dates[~later]
        raise RuntimeError(f"FX-EXEC: execution print not after decision print on {list(bad[:5])}")
    return dec, exe


def build_fx_exec() -> None:
    ecb, _ = ecb_prices()
    h10 = h10_prices(EXEC_LANE_COLS)
    fred_dates = S.read_fred("DEXUSEU").dropna().index            # H.10 calendar (EUR is published on every H.10 day)
    dates = ecb.index.intersection(fred_dates)
    prices = ecb.loc[dates, EXEC_LANE_COLS]
    execp = h10.reindex(dates)[EXEC_LANE_COLS]
    dec, exe = exec_after_decision(dates)
    gap_h = (exe - dec).total_seconds() / 3600.0
    # carry / tbill of the FULL ECB calendar, summed over the ECB prints inside each (previous row, row]
    full_dates = ecb.index
    rates_full, _ = build_rates(full_dates, EXEC_LANE_COLS)
    days_full = day_counts(full_dates)
    carry_full = pd.DataFrame({c: (rates_full[c] - rates_full["USD"]) * days_full / 360.0 for c in EXEC_LANE_COLS},
                              index=full_dates)
    tbill_full = rates_full["USD"] * days_full / 360.0
    grp = np.searchsorted(dates.values, full_dates.values, side="left")     # row that closes each ECB print's interval
    keep = grp < len(dates)

    def agg(df: pd.DataFrame) -> pd.DataFrame:
        g = df[keep].groupby(grp[keep])
        tot = g.sum(min_count=1)
        anynan = df[keep].isna().groupby(grp[keep]).any()
        tot = tot.where(~anynan)
        tot.index = dates[tot.index]
        return tot.reindex(dates)

    carry = agg(carry_full)
    tbill = agg(tbill_full.to_frame("tbill"))["tbill"]
    carry.iloc[0] = np.nan                                    # no previous row: the first interval is undefined
    tbill.iloc[0] = np.nan
    skipped = int(len(full_dates[(full_dates >= dates[0]) & (full_dates <= dates[-1])]) - len(dates))
    groups = {"G10": G10, "EM": ["MXN", "ZAR"]}            # SGD is loaded (price + exec price) but has no carry
    meta = {
        "print_convention": "Decision print = ECB reference rate of the row's date (fixed around 14:10 CET, published "
                            "around 16:00 CET the same day per the conductor note of 2026-11-10); row timestamp = 14:15 "
                            "Europe/Berlin -> UTC, the conservative decision instant (USD per 1 FX, crossed through the "
                            "euro). Rows = dates present in BOTH the ECB series and the FRED H.10 series. "
                            "aux['exec_prices'] = the FRED H.10 noon buying rate in New York of the SAME date (12:00 "
                            "America/New_York = 17:00 or 18:00 Berlin time, i.e. after the 14:15 fixing and after the "
                            "~16:00 CET publication), converted to USD per 1 FX; never forward-filled.",
        "exec_prices_strictly_after_decision": True,
        "exec_print_clock": "12:00 America/New_York on the row's date",
        "exec_minus_decision_hours": {"min": float(gap_h.min()), "max": float(gap_h.max())},
        "carry_alignment": "sum of the ECB-calendar accruals (i_fx - i_usd) * days / 360 over the ECB prints in "
                           "(previous row, row]; decision and execution intervals span the same dates",
        "excluded_from_universe_groups": {"SGD": "no defensible rate series -> carry NaN (price and exec price are loaded)"},
        "currencies_not_in_H10": ["PLN", "HUF", "CZK", "ILS", "TRY"],
    }
    manifest = {
        "exec_prices_missing_on_rows": {c: int(execp[c].isna().sum()) for c in EXEC_LANE_COLS},
        "ecb_prints_not_in_lane": skipped,
        "exclusions": {**meta["excluded_from_universe_groups"],
                       "PLN/HUF/CZK/ILS/TRY": "not published in the Federal Reserve H.10 release -> no execution print"},
        "exec_assertion": "exec_after_decision(): 12:00 America/New_York > 14:15 Europe/Berlin in UTC on every row "
                          f"(min gap {gap_h.min():.2f} h, max {gap_h.max():.2f} h)",
    }
    ff = {c: {"missing_prints": 0, "ffilled": 0, "left_nan": int(prices[c].isna().sum())} for c in EXEC_LANE_COLS}
    _finish("FX-EXEC", dates, ECB_PRINT, prices, ff, EXEC_LANE_COLS, groups, {"exec_prices": execp}, meta, manifest,
            carry_override=carry, tbill_override=tbill, usd_signal_extra_lag=True)


def build_fx_fred() -> None:
    raw = h10_prices(FRED_LANE_COLS)
    raw = raw[raw.notna().any(axis=1)].sort_index()
    raw = raw.loc["1971-01-01":]
    prices, st = limited_ffill(raw, MAX_FFILL)
    for c in FRED_LANE_COLS:
        st[c]["first_print"] = str(raw[c].first_valid_index().date())
    dates = prices.index
    groups = {"G10": FRED_LANE_COLS, "G10_EX_EUR": [c for c in FRED_LANE_COLS if c != "EUR"]}
    meta = {
        "print_convention": "Row = one Federal Reserve H.10 noon buying rate in New York. Index = the date at 12:00 "
                            "America/New_York converted to UTC. Price = USD per 1 unit of foreign currency (DEXJPUS, "
                            "DEXSZUS, DEXCAUS, DEXSDUS, DEXNOUS are inverted). EUR exists from 1999-01-04. "
                            "Evaluation is lag = 1 (next noon print).",
        "universe_groups_note": "the G10 group includes EUR, which has prices only from 1999-01-04; before that the "
                                "group has 8 members",
    }
    # carry coverage per currency per decade (share of price prints that have a carry)
    rates, _ = build_rates(dates, FRED_LANE_COLS)
    days = day_counts(dates)
    cov = {}
    for c in FRED_LANE_COLS:
        car = (rates[c] - rates["USD"]) * days / 360.0
        have = prices[c].notna()
        dec = (dates.year // 10) * 10
        cov[c] = {f"{int(d)}s": {"price_prints": int(have[dec == d].sum()),
                                 "carry_prints": int((have & car.notna())[dec == d].sum()),
                                 "share": None if have[dec == d].sum() == 0 else round(float((have & car.notna())[dec == d].sum() / have[dec == d].sum()), 4)}
                  for d in sorted(set(dec))}
    big = {}
    for c in FRED_LANE_COLS:
        r = rates[c].dropna()
        hi = r[r > 1.0]
        if len(hi):
            big[c] = {"prints": int(len(hi)), "first": str(hi.index[0].date()), "last": str(hi.index[-1].date()),
                      "max_decimal": float(hi.max())}
    manifest = {"carry_coverage_by_decade": cov,
                "rates_above_100pct_per_year": {"note": "true crisis observations, NOT clipped", "per_currency": big}}
    _finish("FX-FRED", dates, NY_NOON, prices, st, FRED_LANE_COLS, groups, {}, meta, manifest)


def main(argv=None) -> int:
    what = (argv or sys.argv[1:]) or ["FX", "FX-EXEC", "FX-FRED"]
    for w in what:
        {"FX": build_fx, "FX-EXEC": build_fx_exec, "FX-FRED": build_fx_fred}[w]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
