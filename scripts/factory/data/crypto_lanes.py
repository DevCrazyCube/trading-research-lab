"""Assemble the CRYPTO-PERP and CRYPTO-SPOT lanes from the raw Binance files (offline).

See scripts/factory/data/crypto.py for the row-label convention and the phantom-candle rule.

Per row D (00:00 UTC) and symbol i
  prices        close of the daily candle that ended at D           (NaN if that candle had zero trades)
  volume_quote  quote volume of that candle                          (NaN likewise)
  universe_mask pit_universe_mask(volume_quote) AND live_at_print    (both known at D 00:00)
  live_at_print the 1h candle that ended at D 00:00 had >= 1 trade   (False where no 1h data was fetched)
  exec_prices   close of the 1h candle opened at D 00:00 = 01:00 UTC price; NaN unless that candle traded
  exec_prices_alt  close of the 1h candle opened at D 01:00 = 02:00 UTC price; NaN unless it traded
  carry (perp)  - sum of funding rates stamped in (D-1 01:00, D 01:00]; 0.0 where no funding record
  carry (spot)  - i_usd / 360 (effective fed funds of the previous calendar day)
Nothing is forward-filled in these lanes, with one exception ordered by the conductor on 2026-11-10: the
SETTLEMENT PRINT. On the last live row z of an instrument that stopped trading, exec_prices and
exec_prices_alt carry its final traded price (= prices[z]); aux['settlement_row'] flags the cell, the
universe mask is False there, and every field is NaN afterwards (carry 0.0). A position still held at the
last real execution print (row z-1) therefore earns the terminal move on row z.
"""
from __future__ import annotations

import json
from typing import Dict, List

import numpy as np
import pandas as pd

from . import crypto as C
from . import sources as S
from .common import RAW, read_jsonl, utc_now
from .crypto_build import GAP_SPLIT_DAYS, MIN_HISTORY, TOP_N, VOL_WINDOW, base_symbol, daily_universe
from .fx import provenance
from .panelio import asof_strictly_before, write_lane
from .universe import mask_summary, pit_universe_mask


def _iso(ms) -> str:
    return None if ms is None or (isinstance(ms, float) and np.isnan(ms)) else str(pd.Timestamp(int(ms), unit="ms", tz="UTC"))


def _log_summary(src: str) -> dict:
    arch = read_jsonl(RAW / src / "_archive_index.jsonl")
    rest = read_jsonl(RAW / src / "_rest_log.jsonl")
    fails = read_jsonl(RAW / src / "_rest_failures.jsonl") + read_jsonl(RAW / src / "_archive_failures.jsonl")

    def span(recs):
        t = sorted(r["fetched_utc"] for r in recs if "fetched_utc" in r)
        return {"files": len(recs), "first_fetch_utc": t[0] if t else None, "last_fetch_utc": t[-1] if t else None,
                "bytes": int(sum(r.get("bytes", 0) for r in recs))}

    kinds: Dict[str, list] = {}
    for r in arch:
        kinds.setdefault(r["path"].split("/")[2] if r["path"].count("/") >= 2 else "other", []).append(r)
    jobs = {}
    for name in ("daily", "hourly", "hourly_ONLYNEW", "fill"):
        f = RAW / src / f"_stage_{name}_DONE.json"
        if f.exists():
            j = json.loads(f.read_text())
            jobs[name] = {k: v for k, v in j.items() if k not in ("report", "funding")}
    return {"download_jobs": {"how_to_check_completion": f"every detached stage writes raw/{src}/_stage_<stage>_DONE.json when it "
                                                         "finishes and ends its log (raw/binance/logs/<market>-<stage>.log) "
                                                         "with '... DONE'; a stage that is still running has neither",
                              "markers": jobs},
            "archive": {"index_file": f"raw/{src}/_archive_index.jsonl",
                        "all_sha256_verified_against_published_CHECKSUM": bool(all(r.get("checksum_ok") for r in arch)),
                        **{k: span(v) for k, v in sorted(kinds.items())}},
            "rest": {"log_file": f"raw/{src}/_rest_log.jsonl", **span(rest)},
            "failures": fails}


def _usd_accrual(rows: pd.DatetimeIndex):
    """i_usd / 360 per daily row: DFF observation dated strictly before the row's UTC date (decimal)."""
    dates = rows.tz_convert("UTC").tz_localize(None).normalize()
    v, st = asof_strictly_before(S.read_fred("DFF"), dates, max_stale_prints=10)
    i_usd = pd.Series((v / 100.0).to_numpy(), index=rows)
    days = pd.Series(dates).diff().dt.days.to_numpy(dtype="float64")
    return i_usd, pd.Series(i_usd.to_numpy() * days / 360.0, index=rows, name="tbill"), st


def _assemble(market: str) -> dict:
    src = C.SRC[market]
    U = daily_universe(market)
    cls, vmask, seg = U["cls"], U["mask"], U["seg"]
    prices, volq = U["spx"], U["sqv"]
    inc = list(prices.columns)
    rows = prices.index
    ever = [c for c in inc if vmask[c].any()]
    plan = json.loads((RAW / src / "_ever_in_mask.json").read_text())
    not_fetched = sorted({base_symbol(c) for c in ever} - set(plan["symbols"]))
    if not_fetched:
        raise RuntimeError(f"{market}: {len(not_fetched)} ever-in-mask symbols have no hourly download plan "
                           f"(re-run plan-{market} and the {market}-hourly stage): {not_fetched[:10]}")

    exec_p = pd.DataFrame(np.nan, index=rows, columns=inc)
    exec_a = pd.DataFrame(np.nan, index=rows, columns=inc)
    live = pd.DataFrame(False, index=rows, columns=inc)
    carry = pd.DataFrame(0.0, index=rows, columns=inc)
    fund_n = pd.DataFrame(0, index=rows, columns=inc, dtype="int64")
    per: Dict[str, dict] = {}
    xcheck = {"rows_compared": 0, "mismatches": 0, "max_rel_diff": 0.0, "symbols_with_mismatch": {}, "mismatch_cells": []}
    count = U["count"]

    for c in inc:
        b = base_symbol(c)
        s = prices[c].dropna()
        span = (s.index[-1] - s.index[0]).days + 1
        row = cls.loc[b]
        rest_files = list((RAW / src / "rest_klines_1d" / b).glob("1d_*.json"))
        arch_files = list((RAW / src / "archive_klines_1d" / b).glob("*.zip"))
        per[c] = {"symbol": b, "segment": f"{seg[c]['segment']}/{seg[c]['of']}",
                  "first_candle_open": str(s.index[0] - pd.Timedelta(days=1)), "last_candle_open": str(s.index[-1] - pd.Timedelta(days=1)),
                  "first_row": str(s.index[0]), "last_row": str(s.index[-1]), "traded_daily_candles": int(len(s)),
                  "zero_trade_candles_dropped_symbol": int((count[b] == 0).sum()),
                  "missing_days_inside_segment": int(span - len(s)),
                  "status": row["status"],
                  "daily_source": "+".join(x for x, f in (("REST", rest_files), ("archive", arch_files)) if f),
                  "ever_in_mask": c in ever}
        if market == "perp":
            ob = row.get("onboard_ms")
            per[c]["exchange_onboard"] = None if ob is None or pd.isna(ob) else _iso(ob)
            if row["status"] == "SETTLING":
                per[c]["exchange_delivery"] = _iso(row.get("delivery_ms"))

    cache: Dict[str, object] = {}
    for k, c in enumerate(ever, 1):
        b = base_symbol(c)
        if b not in cache:
            cache = {b: (C.exec_prints(market, b), C.funding_events(b) if market == "perp" else None)}
        ex, ev = cache[b]
        s = prices[c].dropna()
        a_row, z_row = s.index[0], s.index[-1]
        inseg = np.asarray((rows >= a_row) & (rows <= z_row))
        e = ex["exec"].where(ex["exec_n"] > 0).reindex(rows).where(inseg)
        a = ex["alt"].where(ex["alt_n"] > 0).reindex(rows).where(inseg)
        exec_p[c] = e.to_numpy()
        exec_a[c] = a.to_numpy()
        live[c] = (ex["pre_n"].reindex(rows).fillna(0) > 0).to_numpy() & inseg
        # decision print (daily candle) against the close of the 1h candle opened D-1 23:00 (independent files)
        pre = ex["pre"].reindex(rows)
        both = prices[c].notna() & pre.notna()
        rel = ((prices[c] - pre).abs() / prices[c])[both]
        bad = int((rel > 1e-9).sum())
        xcheck["rows_compared"] += int(both.sum())
        xcheck["mismatches"] += bad
        if bad:
            xcheck["symbols_with_mismatch"][c] = bad
            xcheck["max_rel_diff"] = max(xcheck["max_rel_diff"], float(rel.max()))
            for t, v in rel[rel > 1e-9].items():          # the daily candle stays the decision print; the cell is listed
                if len(xcheck["mismatch_cells"]) < 500:
                    xcheck["mismatch_cells"].append({"row": str(t), "instrument": c, "daily_close": float(prices[c][t]),
                                                     "hourly_close_23h": float(pre[t]), "rel_diff": round(float(v), 6)})
        # traded hours of THIS segment: 1h candles opened in [first candle open, last row)
        t_open = ex.attrs["traded_open_ms"]
        lo = int((a_row - pd.Timedelta(days=1)).value // 10**6)
        hi = int(z_row.value // 10**6)
        t_seg = t_open[(t_open >= lo) & (t_open < hi)]
        first_ms = int(t_seg.min()) if len(t_seg) else None
        last_ms = int(t_seg.max() + C.HOUR_MS) if len(t_seg) else None
        d = per[c]
        need_exec = prices[c].notna().to_numpy().copy()
        need_exec[rows.get_loc(z_row)] = False               # the last live row cannot have a next-hour print
        d.update({"hourly_candles_symbol": ex.attrs.get("n_hourly", 0), "hourly_candles_from_rest_symbol": ex.attrs.get("n_hourly_rest", 0),
                  "off_grid_hourly_candles_dropped_symbol": ex.attrs.get("off_grid_dropped", 0),
                  "first_traded_hour_open": _iso(first_ms), "last_traded_hour_close": _iso(last_ms),
                  "first_exec_print": None if e.notna().sum() == 0 else str(e.first_valid_index()),
                  "last_exec_print": None if e.notna().sum() == 0 else str(e.last_valid_index()),
                  "exec_candles_with_zero_trades": int(((ex["exec_n"].reindex(rows) == 0).to_numpy() & inseg).sum()),
                  "live_rows_without_exec_print": int((need_exec & e.isna().to_numpy()).sum()),
                  "live_rows_without_exec_alt_print": int((need_exec & a.isna().to_numpy()).sum()),
                  "live_rows_without_hourly_decision_candle": int((prices[c].notna() & pre.isna()).sum()),
                  "decision_vs_hourly_mismatches": bad})
        if market == "perp":
            tot, cnt = C.funding_to_rows(ev, rows, cut_after_ms=last_ms, cut_before_ms=first_ms)
            tot, cnt = tot.where(inseg, 0.0), cnt.where(inseg, 0)
            carry[c] = -tot.to_numpy()
            fund_n[c] = cnt.to_numpy()
            held_possible = e.notna() & e.shift(1).notna()
            in_seg_ev = ev.index[(ev.index >= (first_ms or 0)) & (ev.index <= (last_ms or 0))]
            d.update({"funding_events_used": int(cnt.sum()), "funding_events_symbol_archive": ev.attrs["n_archive"],
                      "funding_events_symbol_rest": ev.attrs["n_rest"],
                      "phantom_funding_events_after_last_trade_symbol": 0 if ex.attrs["last_traded_close_ms"] is None
                      else int((ev.index > ex.attrs["last_traded_close_ms"]).sum()),
                      "first_funding": None if len(in_seg_ev) == 0 else _iso(in_seg_ev[0]),
                      "rows_with_exec_interval_but_no_funding_record": int((held_possible.to_numpy() & (cnt.to_numpy() == 0)).sum()),
                      "funding_downloaded": True})
        if k % 50 == 0:
            print(f"{utc_now()} {market}: hourly/funding {k}/{len(ever)}", flush=True)
    if market == "perp":
        for c in inc:
            if c not in ever:
                per[c]["funding_downloaded"] = False

    removed = (vmask & ~live)
    # trailing rows without a single execution print carry no tradeable information -> dropped (recorded)
    has_exec = exec_p.notna().any(axis=1).to_numpy()
    last = int(np.flatnonzero(has_exec)[-1])
    dropped_tail = [str(t) for t in rows[last + 1:]]
    sl = slice(0, last + 1)
    final_row = rows[last]

    # ---- SETTLEMENT PRINTS (conductor ruling 2026-11-10) ------------------------------------------------
    # Execution prints end before trading does: the row after an instrument's last real 01:00 print is its
    # last live row z (the close of its last traded daily candle = its final traded price), and that row
    # has no next-hour candle. So that a position still held at the last real execution print earns the
    # final move, the final traded price is written into exec_prices / exec_prices_alt on row z:
    #     exec_prices[z] = prices[z] = exec_prices[z - 1] * (1 + terminal_return[z])
    # The universe mask is False on z and everything is NaN afterwards. A target of zero decided on row
    # z - 1 is executed at that row's real 01:00 print and therefore does not earn the move.
    one = pd.Timedelta(days=1)
    exec_real, alt_real = exec_p.copy(), exec_a.copy()
    term = pd.DataFrame(0.0, index=rows, columns=inc)
    settle = pd.DataFrame(False, index=rows, columns=inc)
    sp = {"instruments": 0, "nonzero_terminal_return": 0, "zero_terminal_return": [],
          "mask_cells_cleared_on_the_settlement_row": [], "exec_terminal_move_not_bookable": [],
          "alt_terminal_move_not_bookable": [], "last_live_row_is_the_panel_final_row": [],
          "ended_within_3_days_of_the_panel_end": [], "terminal_return_alt": {}}
    for c in ever:
        s = prices[c].dropna()
        z = s.index[-1]
        e, al = exec_real[c].dropna(), alt_real[c].dropna()
        if e.empty:
            continue
        if z >= final_row:
            # alive at the panel's end. An instrument that stopped trading during the panel's last day cannot
            # be told apart from one whose 01:00 print is merely absent: nothing is done, the case is counted.
            if pd.isna(exec_real.loc[final_row, c]):
                sp["last_live_row_is_the_panel_final_row"].append(c)
            continue
        if z >= final_row - 3 * one:                      # cannot yet be told from a short trading halt
            sp["ended_within_3_days_of_the_panel_end"].append({"instrument": c, "settlement_row": str(z)})
        p_final = float(s.iloc[-1])
        term.loc[z, c] = p_final / float(e.iloc[-1]) - 1.0
        exec_p.loc[z, c] = p_final
        exec_a.loc[z, c] = p_final
        settle.loc[z, c] = True
        sp["instruments"] += 1
        if term.loc[z, c] != 0.0:
            sp["nonzero_terminal_return"] += 1
        else:
            sp["zero_terminal_return"].append(c)
        if bool(vmask.loc[z, c]) and bool(live.loc[z, c]):
            sp["mask_cells_cleared_on_the_settlement_row"].append({"row": str(z), "instrument": c})
        if e.index[-1] != z - one:
            sp["exec_terminal_move_not_bookable"].append({"instrument": c, "last_real_exec_print": str(e.index[-1]), "settlement_row": str(z)})
        if al.empty or al.index[-1] != z - one:
            sp["alt_terminal_move_not_bookable"].append({"instrument": c, "last_real_alt_print": None if al.empty else str(al.index[-1]),
                                                         "settlement_row": str(z)})
        if not al.empty:
            sp["terminal_return_alt"][c] = round(p_final / float(al.iloc[-1]) - 1.0, 6)
    mask = vmask & live & ~settle
    return {"cls": cls, "inc": inc, "ever": ever, "rows": rows[sl], "prices": prices.iloc[sl], "volq": volq.iloc[sl],
            "terminal": term.iloc[sl], "settle": settle.iloc[sl], "settlement": sp,
            "exec_real": exec_real.iloc[sl], "alt_real": alt_real.iloc[sl],
            "mask": mask.iloc[sl], "vmask": vmask.iloc[sl], "live": live.iloc[sl], "exec": exec_p.iloc[sl],
            "alt": exec_a.iloc[sl], "carry": carry.iloc[sl], "fund_n": fund_n.iloc[sl], "per": per, "xcheck": xcheck,
            "removed": removed.iloc[sl], "dropped_tail": dropped_tail, "notes": U["notes"], "px_all": U["px"].iloc[sl],
            "qv_all": U["qv"].iloc[sl], "count": count.iloc[sl], "seg": seg, "included_names": U["included_names"]}


def _delisting_report(A: dict) -> dict:
    """For every symbol that stopped trading: where its prints end (nothing is filled afterwards)."""
    rep = {}
    rows = A["rows"]
    for c in A["ever"]:
        s = A["prices"][c].dropna()
        if s.index[-1] >= rows[-1]:
            continue
        e = A["exec_real"][c].dropna()
        rep[c] = {"settlement_row": str(s.index[-1]), "final_traded_price": float(s.iloc[-1]),
                  "last_real_exec_print": None if e.empty else str(e.index[-1]),
                  "last_real_exec_price": None if e.empty else float(e.iloc[-1]),
                  "terminal_return": None if e.empty else round(float(s.iloc[-1] / e.iloc[-1] - 1.0), 6),
                  "terminal_return_alt": A["settlement"]["terminal_return_alt"].get(c),
                  "mask_rows_after_last_real_exec_print": int(A["mask"][c].loc[e.index[-1]:].iloc[1:].sum()) if not e.empty else None,
                  "in_mask_on_last_real_exec_row": None if e.empty else bool(A["mask"][c].loc[e.index[-1]])}
    return rep


def build_perp() -> None:
    A = _assemble("perp")
    rows, inc, ever, cls = A["rows"], A["inc"], A["ever"], A["cls"]
    i_usd, tbill, st_dff = _usd_accrual(rows)
    # what the top-30 would look like if the non-crypto (TradFi) perpetuals were ranked too
    trad = [c for c in cls.index[cls["reason"].str.startswith("TRADIFI")] if c in A["qv_all"].columns]
    both = pit_universe_mask(A["qv_all"][sorted(set(A["included_names"]) | set(trad))], top_n=TOP_N["perp"],
                             min_history=MIN_HISTORY, vol_window=VOL_WINDOW)
    tslots = both[trad].sum()
    trow = both[trad].any(axis=1)
    excl = {}
    for reason, g in cls[~cls["include"]].groupby("reason"):
        excl[reason] = sorted(g.index)
    no_data = sorted(c for c in cls.index[cls["include"]] if c not in A["included_names"])
    segments = {c: v for c, v in A["seg"].items() if v["of"] > 1}
    aux = {"universe_mask": A["mask"], "exec_prices": A["exec"], "exec_prices_alt": A["alt"], "volume_quote": A["volq"],
           "live_at_print": A["live"], "funding_obs": A["fund_n"], "terminal_return": A["terminal"],
           "settlement_row": A["settle"]}
    cm = A["carry"]
    held = A["exec_real"].notna() & A["exec_real"].shift(1).notna()     # real execution intervals (no settlement rows)
    meta = {
        "periods_per_year": 365,
        "print_convention": "Row stamped D 00:00 UTC = the close of the Binance USD-M daily candle that ENDED at D 00:00 "
                            "(opened D-1 00:00): the decision print. aux['exec_prices'] = close of the 1h candle opened at "
                            "D 00:00 (the 01:00 UTC price, one hour after the decision); aux['exec_prices_alt'] = close of "
                            "the 1h candle opened at D 01:00 (the 02:00 UTC price). A candle with zero trades is not a "
                            "print (NaN); nothing is forward-filled - with ONE exception: on the last live row of an "
                            "instrument that stopped trading, both execution series carry its final traded price (the "
                            "settlement print, see settlement_prints). carry on row D = minus the sum of the funding rates "
                            "stamped in (D-1 01:00, D 01:00], i.e. aligned to the execution interval.",
        "exec_prices_strictly_after_decision": True,
        "exec_print_clock": "row timestamp + 1 hour (01:00 UTC); alt: row timestamp + 2 hours (02:00 UTC)",
        "universe_groups": {"EVER_IN_MASK": [c for c in inc if A["mask"][c].any()], "ALL": inc},
        "universe_rule": f"aux['universe_mask'][t,i] = (i has >= {MIN_HISTORY} traded daily candles ended strictly before t) "
                         f"AND (i's mean quote volume over the {VOL_WINDOW} consecutive candles ending at t ranks in the top "
                         f"{TOP_N['perp']} of all crypto perps with a complete window) AND (i traded in the hour that ended "
                         "at t). Ranked among crypto-coin USDT perpetuals only (see manifest exclusions). An instrument is "
                         f"one uninterrupted trading segment of a symbol (a break of >= {GAP_SPLIT_DAYS} days starts a new one).",
        "carry_convention": "- sum(funding rate) over funding stamps in (01:00 of D-1, 01:00 of D]; 0.0 where there is no "
                            "funding record (see aux['funding_obs'] = number of funding events in the interval; funding "
                            "was downloaded only for EVER_IN_MASK symbols — all other columns carry 0.0)",
        "tbill_convention": "effective fed funds (FRED DFF) of the last calendar day before the row, / 360",
        "settlement_prints": "When an instrument stops trading (delisting, suspension >= 3 days) its real execution "
                             "prints end one row before its last live row z (z holds the close of its last traded daily "
                             "candle = its final traded price; the 01:00 candle of z never trades). The final traded "
                             "price is BOOKED on row z: exec_prices[z] = exec_prices_alt[z] = prices[z] = "
                             "exec_prices[z-1] * (1 + terminal_return[z]). aux['settlement_row'] flags those cells; "
                             "aux['universe_mask'] is False on them and every field is NaN afterwards. Effect in the "
                             "engine (held = w.shift(1), r = F/F.shift(1) - 1): a target still held on row z-1 earns the "
                             "terminal move on row z; a target of zero decided on row z-1 was executed at that row's real "
                             "01:00 print and does not. These are the ONLY cells of exec_prices that are not a print "
                             "later than the row's decision print (trading had stopped before the row timestamp); they "
                             "can only close a position. In the conductor's notation t_last = z-1 (the last row with a "
                             "real execution print) and the settlement print sits on t_last + 1.",
        "terminal_return_note": "aux['terminal_return'][z, i] = prices[z, i] / (last REAL execution print of i) - 1 on the "
                                "settlement row z of an instrument that stopped trading, 0 elsewhere - kept for audit; it "
                                "equals exec_prices[z] / exec_prices[z-1] - 1. A realised return, never a signal input.",
        "glsr": "not shipped: step 5 of the brief (long/short account ratio) was dropped on the conductor's instruction "
                "of 2026-11-10; nothing was downloaded",
        "first_row_all_groups_complete": str(rows[np.flatnonzero(A["mask"].any(axis=1).to_numpy())[0]]),
        "last_row_all_groups_complete": str(rows[-1]),
    }
    manifest = {
        "sources": {
            "rest": {"exchangeInfo": "https://fapi.binance.com/fapi/v1/exchangeInfo",
                     "klines": "https://fapi.binance.com/fapi/v1/klines (interval=1d for every symbol the exchange knows; "
                               "interval=1h only for months the archive does not hold)",
                     "fundingRate": "https://fapi.binance.com/fapi/v1/fundingRate (months the archive does not hold)"},
            "archive": {"base": "https://data.binance.vision/data/futures/um/",
                        "listing": "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/futures/um/...",
                        "used_for": "1d klines of names the exchange no longer knows; 1h klines and fundingRate (monthly zips)"},
            "choice": "Daily candles: REST for every symbol REST still serves — all symbols in exchangeInfo (TRADING and "
                      "SETTLING, full history incl. 2019-09-08..2019-12-31 which the archive lacks) and the delisted "
                      "names it still answers for (e.g. LUNAUSDT); the archive (monthly zips + daily zips for the days "
                      "the monthly zips miss) only for the re-used '...SETTLED' names REST does not serve. "
                      "per_symbol.daily_source says which. Hourly candles and funding: archive monthly zips "
                      "(sha256-checked against the published .CHECKSUM); REST for months without a monthly zip (before "
                      "2020-01 and the current month) and for the holes inside monthly zips (e.g. 26-28 Feb 2022); daily "
                      "archive zips where REST has nothing.",
            "logs": _log_summary(C.SRC["perp"]),
            "fred": provenance("fred", ["DFF.csv"]),
            "exchangeInfo_snapshot": "raw/binance/futures_um/exchangeInfo/latest.json",
        },
        "archive_start_note": "USD-M monthly archive kline files start 2020-01; BTCUSDT trades since 2019-09-08 and those "
                              "candles come from REST. Each symbol's true first candle is in per_symbol.first_candle_open.",
        "universe": {"top_n": TOP_N["perp"], "min_history": MIN_HISTORY, "vol_window": VOL_WINDOW,
                     "summary": mask_summary(A["mask"]),
                     "volume_rank_mask_cells_removed_because_not_trading_in_the_last_hour": int(A["removed"].to_numpy().sum()),
                     "removed_cells": [{"row": str(t), "symbol": c} for c in ever for t in rows[A["removed"][c].to_numpy()]][:200]},
        "exclusions": {"by_reason": excl,
                       "included_but_no_traded_daily_candle": no_data,
                       "note": "TRADIFI_PERPETUAL contracts (equity, commodity, FX, pre-IPO underlyings) are a separate "
                               "Binance contract type and are NOT crypto; the brief listed only stablecoin/fiat/index "
                               "exclusions, so this exclusion is the data layer's call and is reported.",
                       "tradfi_if_ranked_too": {"first_row_a_tradfi_perp_would_enter_the_top30": None if not trow.any() else str(trow[trow].index[0]),
                                                "row_slots_they_would_take": int(tslots.sum()),
                                                "top": {k: int(v) for k, v in tslots.sort_values(ascending=False).head(15).items() if v > 0}}},
        "phantom_candles": {"rule": "a daily candle with zero trades is not a print",
                            "zero_trade_daily_candles_dropped": int((A["count"][A["included_names"]] == 0).sum().sum()),
                            "symbols_affected": int(((A["count"][A["included_names"]] == 0).any()).sum())},
        "segments": {"rule": f"a symbol that does not trade for >= {GAP_SPLIT_DAYS} consecutive days is split: the last "
                             "segment keeps the symbol name, earlier ones are <SYMBOL>@<YYYYMMDD of their last row>; "
                             "no history is shared across the break",
                     "split_instruments": segments},
        "delisted_symbols_ever_in_mask": _delisting_report(A),
        "decision_print_crosscheck": {"what": "daily close on row D vs close of the 1h candle opened D-1 23:00 (independent files)",
                                      **A["xcheck"]},
        "exec_prints": {"mask_cells": int(A["mask"].to_numpy().sum()),
                        "mask_cells_without_exec_price": int((A["mask"] & A["exec"].isna()).to_numpy().sum()),
                        "mask_cells_without_exec_alt_price": int((A["mask"] & A["alt"].isna()).to_numpy().sum())},
        "settlement_prints": {"rule": "exec_prices[z] = exec_prices_alt[z] = prices[z] (the final traded price) on the last "
                                      "live row z of every instrument that stopped trading before the panel's final row; "
                                      "universe_mask False on z; NaN afterwards; see meta.settlement_prints",
                              **A["settlement"]},
        "funding": {"missing_funding_rule": "carry = 0.0 where no funding record falls in the interval",
                    "cells_with_exec_interval_and_no_funding_record": int((held & (A["fund_n"] == 0))[ever].to_numpy().sum()),
                    "mask_cells_with_no_funding_record": int((A["mask"] & (A["fund_n"] == 0)).to_numpy().sum()),
                    "per_symbol": {c: A["per"][c].get("rows_with_exec_interval_but_no_funding_record") for c in ever
                                   if A["per"][c].get("rows_with_exec_interval_but_no_funding_record")}},
        "rate_series": {"USD": {"series": "FRED DFF", "asof": st_dff}},
        "tail_rows_dropped_no_exec_print_yet": A["dropped_tail"],
        "price_gaps": {"rule": "no forward fill in this lane; gaps of 1-2 days stay NaN inside an instrument, longer "
                               "ones split it (see segments)",
                       "instruments_with_missing_days_inside_segment": {c: v["missing_days_inside_segment"] for c, v in A["per"].items()
                                                                        if v["missing_days_inside_segment"]}},
        "hourly_coverage": {"instruments_ever_in_mask": len(ever),
                            "off_grid_hourly_candles_dropped": {c: A["per"][c]["off_grid_hourly_candles_dropped_symbol"] for c in ever
                                                                if A["per"][c].get("off_grid_hourly_candles_dropped_symbol")},
                            "live_rows_without_exec_print": {c: A["per"][c]["live_rows_without_exec_print"] for c in ever
                                                             if A["per"][c]["live_rows_without_exec_print"]},
                            "live_rows_without_hourly_decision_candle": {c: A["per"][c]["live_rows_without_hourly_decision_candle"]
                                                                         for c in ever if A["per"][c]["live_rows_without_hourly_decision_candle"]}},
        "per_symbol": A["per"],
        "notes": A["notes"],
    }
    write_lane("CRYPTO-PERP", A["prices"], cm, tbill, aux, meta, manifest)
    print(f"{utc_now()} built CRYPTO-PERP: {A['prices'].shape} {rows[0]} .. {rows[-1]} ever-in-mask {len(ever)}", flush=True)


def build_spot() -> None:
    A = _assemble("spot")
    rows, inc, ever, cls = A["rows"], A["inc"], A["ever"], A["cls"]
    i_usd, tbill, st_dff = _usd_accrual(rows)
    carry = pd.DataFrame({c: -tbill.to_numpy() for c in inc}, index=rows)
    excl = {}
    for reason, g in cls[~cls["include"]].groupby("reason"):
        excl[reason] = sorted(g.index)
    no_data = sorted(c for c in cls.index[cls["include"]] if c not in A["included_names"])
    segments = {c: v for c, v in A["seg"].items() if v["of"] > 1}
    aux = {"universe_mask": A["mask"], "exec_prices": A["exec"], "exec_prices_alt": A["alt"], "volume_quote": A["volq"],
           "live_at_print": A["live"], "terminal_return": A["terminal"], "settlement_row": A["settle"]}
    meta = {
        "periods_per_year": 365,
        "print_convention": "Row stamped D 00:00 UTC = the close of the Binance spot daily candle that ENDED at D 00:00 "
                            "(opened D-1 00:00): the decision print. aux['exec_prices'] = close of the 1h candle opened at "
                            "D 00:00 (the 01:00 UTC price); aux['exec_prices_alt'] = the 02:00 UTC price. A candle with "
                            "zero trades is not a print (NaN); nothing is forward-filled - with ONE exception: on the last "
                            "live row of an instrument that stopped trading, both execution series carry its final traded "
                            "price (the settlement print, see settlement_prints). Long-only use.",
        "exec_prices_strictly_after_decision": True,
        "exec_print_clock": "row timestamp + 1 hour (01:00 UTC); alt: row timestamp + 2 hours (02:00 UTC)",
        "universe_groups": {"EVER_IN_MASK": [c for c in inc if A["mask"][c].any()], "ALL": inc},
        "universe_rule": f"aux['universe_mask'][t,i] = (>= {MIN_HISTORY} traded daily candles ended strictly before t) AND "
                         f"(mean quote volume of the {VOL_WINDOW} consecutive candles ending at t in the top {TOP_N['spot']} "
                         "of all included USDT pairs with a complete window) AND (traded in the hour that ended at t). "
                         f"An instrument is one uninterrupted trading segment of a symbol (a break of >= {GAP_SPLIT_DAYS} "
                         "days starts a new one).",
        "carry_convention": "-i_usd * days / 360 for every instrument (days = 1); effective fed funds (FRED DFF) of the last "
                            "calendar day before the row; first row NaN",
        "settlement_prints": "When an instrument stops trading (delisting, suspension >= 3 days) its real execution "
                             "prints end one row before its last live row z (z holds the close of its last traded daily "
                             "candle = its final traded price; the 01:00 candle of z never trades). The final traded "
                             "price is BOOKED on row z: exec_prices[z] = exec_prices_alt[z] = prices[z] = "
                             "exec_prices[z-1] * (1 + terminal_return[z]). aux['settlement_row'] flags those cells; "
                             "aux['universe_mask'] is False on them and every field is NaN afterwards. Effect in the "
                             "engine (held = w.shift(1), r = F/F.shift(1) - 1): a target still held on row z-1 earns the "
                             "terminal move on row z; a target of zero decided on row z-1 was executed at that row's real "
                             "01:00 print and does not. These are the ONLY cells of exec_prices that are not a print "
                             "later than the row's decision print (trading had stopped before the row timestamp); they "
                             "can only close a position. In the conductor's notation t_last = z-1 (the last row with a "
                             "real execution print) and the settlement print sits on t_last + 1.",
        "terminal_return_note": "aux['terminal_return'][z, i] = prices[z, i] / (last REAL execution print of i) - 1 on the "
                                "settlement row z of an instrument that stopped trading, 0 elsewhere - kept for audit; it "
                                "equals exec_prices[z] / exec_prices[z-1] - 1. A realised return, never a signal input.",
        "first_row_all_groups_complete": str(rows[np.flatnonzero(A["mask"].any(axis=1).to_numpy())[0]]),
        "last_row_all_groups_complete": str(rows[-1]),
    }
    manifest = {
        "sources": {
            "rest": {"exchangeInfo": "https://api.binance.com/api/v3/exchangeInfo",
                     "klines": "https://api.binance.com/api/v3/klines (interval=1d for every USDT pair the exchange knows, "
                               "TRADING and BREAK; interval=1h for months the archive does not hold and for holes "
                               "inside its monthly zips)"},
            "archive": {"base": "https://data.binance.vision/data/spot/",
                        "used_for": "1d klines of names the exchange no longer knows; 1h klines (monthly zips, sha256-checked)",
                        "timestamp_unit_note": "spot archive kline files are in MICROSECONDS from 2025-01 on (milliseconds "
                                               "before); detected per file and every candle is asserted to lie inside the "
                                               "month named by its file"},
            "logs": _log_summary(C.SRC["spot"]),
            "fred": provenance("fred", ["DFF.csv"]),
            "exchangeInfo_snapshot": "raw/binance/spot/exchangeInfo/latest.json",
        },
        "universe": {"top_n": TOP_N["spot"], "min_history": MIN_HISTORY, "vol_window": VOL_WINDOW,
                     "summary": mask_summary(A["mask"]),
                     "volume_rank_mask_cells_removed_because_not_trading_in_the_last_hour": int(A["removed"].to_numpy().sum()),
                     "removed_cells": [{"row": str(t), "symbol": c} for c in ever for t in rows[A["removed"][c].to_numpy()]][:200]},
        "exclusions": {"by_reason": excl, "included_but_no_traded_daily_candle": no_data},
        "phantom_candles": {"rule": "a daily candle with zero trades is not a print",
                            "zero_trade_daily_candles_dropped": int((A["count"][A["included_names"]] == 0).sum().sum()),
                            "symbols_affected": int(((A["count"][A["included_names"]] == 0).any()).sum())},
        "segments": {"rule": f"a symbol that does not trade for >= {GAP_SPLIT_DAYS} consecutive days is split: the last "
                             "segment keeps the symbol name, earlier ones are <SYMBOL>@<YYYYMMDD of their last row>; "
                             "no history is shared across the break",
                     "split_instruments": segments},
        "delisted_symbols_ever_in_mask": _delisting_report(A),
        "decision_print_crosscheck": {"what": "daily close on row D vs close of the 1h candle opened D-1 23:00 (independent files)",
                                      **A["xcheck"]},
        "exec_prints": {"mask_cells": int(A["mask"].to_numpy().sum()),
                        "mask_cells_without_exec_price": int((A["mask"] & A["exec"].isna()).to_numpy().sum()),
                        "mask_cells_without_exec_alt_price": int((A["mask"] & A["alt"].isna()).to_numpy().sum())},
        "settlement_prints": {"rule": "exec_prices[z] = exec_prices_alt[z] = prices[z] (the final traded price) on the last "
                                      "live row z of every instrument that stopped trading before the panel's final row; "
                                      "universe_mask False on z; NaN afterwards; see meta.settlement_prints",
                              **A["settlement"]},
        "rate_series": {"USD": {"series": "FRED DFF", "asof": st_dff}},
        "tail_rows_dropped_no_exec_print_yet": A["dropped_tail"],
        "price_gaps": {"rule": "no forward fill in this lane; gaps of 1-2 days stay NaN inside an instrument, longer "
                               "ones split it (see segments)",
                       "instruments_with_missing_days_inside_segment": {c: v["missing_days_inside_segment"] for c, v in A["per"].items()
                                                                        if v["missing_days_inside_segment"]}},
        "hourly_coverage": {"instruments_ever_in_mask": len(ever),
                            "off_grid_hourly_candles_dropped": {c: A["per"][c]["off_grid_hourly_candles_dropped_symbol"] for c in ever
                                                                if A["per"][c].get("off_grid_hourly_candles_dropped_symbol")},
                            "live_rows_without_exec_print": {c: A["per"][c]["live_rows_without_exec_print"] for c in ever
                                                             if A["per"][c]["live_rows_without_exec_print"]},
                            "live_rows_without_hourly_decision_candle": {c: A["per"][c]["live_rows_without_hourly_decision_candle"]
                                                                         for c in ever if A["per"][c]["live_rows_without_hourly_decision_candle"]}},
        "per_symbol": A["per"],
        "notes": A["notes"],
    }
    write_lane("CRYPTO-SPOT", A["prices"], carry, tbill, aux, meta, manifest)
    print(f"{utc_now()} built CRYPTO-SPOT: {A['prices'].shape} {rows[0]} .. {rows[-1]} ever-in-mask {len(ever)}", flush=True)
