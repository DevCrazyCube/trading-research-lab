"""CRYPTO-PERP / CRYPTO-SPOT lane builders (offline; read raw Binance files, write parquet + manifest).

    python -m scripts.factory.data.crypto_build plan-perp     # daily frames -> mask -> _ever_in_mask.json
    python -m scripts.factory.data.crypto_build holes-perp    # after perp-hourly: hourly holes -> _hourly_holes.json
    python -m scripts.factory.data.crypto_build build-perp    # after perp-hourly (+ perp-fill)
    python -m scripts.factory.data.crypto_build plan-spot / build-spot
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from . import crypto as C
from .common import RAW, atomic_write_json, read_jsonl, utc_now
from .universe import mask_summary, pit_universe_mask

TOP_N = {"perp": 30, "spot": 20}
MIN_HISTORY = 60
VOL_WINDOW = 30
GAP_SPLIT_DAYS = 3          # a symbol that does not trade for >= 3 consecutive days comes back as a NEW instrument
SEG = "@"                   # earlier segments are named <SYMBOL>@<YYYYMMDD of their last row>


def base_symbol(col: str) -> str:
    return col.split(SEG)[0]


def split_segments(px: pd.DataFrame, qv: pd.DataFrame, gap_days: int = GAP_SPLIT_DAYS):
    """A trading suspension of >= `gap_days` days (token swap / redenomination / relisting: COCOS 1000:1,
    BNX, old LUNA -> new LUNA under one ticker, FTT 2022-11 -> 2023-09) breaks a symbol into separate
    instruments, so that no lookback, volatility estimate or 60-candle history ever spans the break.
    The LAST segment keeps the plain symbol name; earlier ones become <SYMBOL>@<YYYYMMDD of last row>.
    Causal: whether row t starts a new segment depends only on rows <= t.
    Returns (px2, qv2, info) with info[col] = {base, first_row, last_row, segment, of}."""
    out_px, out_qv, info = {}, {}, {}
    n = len(px)
    for c in px.columns:
        valid = px[c].notna().to_numpy()
        pos = np.flatnonzero(valid)
        if len(pos) == 0:
            continue
        cuts = np.flatnonzero(np.diff(pos) > gap_days)          # > gap_days apart  <=>  >= gap_days missing days
        starts = np.r_[pos[0], pos[cuts + 1]]
        ends = np.r_[pos[cuts], pos[-1]]
        k = len(starts)
        for j, (a, z) in enumerate(zip(starts, ends)):
            name = c if j == k - 1 else f"{c}{SEG}{px.index[z].strftime('%Y%m%d')}"
            keep = np.zeros(n, dtype=bool)
            keep[a:z + 1] = True
            out_px[name] = px[c].where(keep)
            out_qv[name] = qv[c].where(keep)
            info[name] = {"base": c, "first_row": str(px.index[a]), "last_row": str(px.index[z]), "segment": j + 1, "of": k}
    cols = sorted(out_px)
    return pd.DataFrame(out_px)[cols], pd.DataFrame(out_qv)[cols], info


def _names(market: str) -> List[str]:
    plan = json.loads((RAW / C.SRC[market] / "listings" / "daily_plan.json").read_text())
    return sorted(set(plan["rest_symbols"]) | set(plan["archive_only_symbols"]))


def drop_aliases(cls: pd.DataFrame, px: pd.DataFrame) -> pd.DataFrame:
    """A "...SETTLED" name whose candles are IDENTICAL to its plain ticker's on every common day is the
    same contract served twice (the ticker has not been re-listed yet): keep the plain name, exclude the
    alias. Common days with different prices would mean two contracts traded under one ticker at once —
    refused."""
    cls = cls.copy()
    for x in [c for c in cls.index[cls["include"]] if C.is_settled_name(c) and c in px.columns]:
        p = C.plain_name(x)
        if p not in px.columns or not bool(cls.at[p, "include"]):
            continue
        both = (px[x].notna() & px[p].notna()).to_numpy()
        if not both.any():
            continue                                         # old contract and re-listed contract: two instruments
        if np.allclose(px[x].to_numpy()[both], px[p].to_numpy()[both], rtol=1e-9, atol=0):
            cls.at[x, "include"] = False
            cls.at[x, "reason"] = "alias: the same contract is served under the plain ticker (kept there)"
        else:
            raise RuntimeError(f"{x} and {p} overlap on {int(both.sum())} days with different prices")
    return cls


def assert_no_duplicate_instruments(px: pd.DataFrame) -> None:
    """No two instruments may carry the same price history (it would double a position). Signature = the
    dates and closes of five quantile rows of each column's life."""
    seen: Dict[tuple, str] = {}
    for c in px.columns:
        s = px[c].dropna()
        if len(s) < 10:
            continue
        k = [0, len(s) // 4, len(s) // 2, (3 * len(s)) // 4, len(s) - 1]
        sig = tuple((s.index[i].value, float(s.iloc[i])) for i in k)
        if sig in seen:
            raise RuntimeError(f"instruments {seen[sig]} and {c} have identical price histories")
        seen[sig] = c


def daily_universe(market: str):
    """One market, all symbols: dict with
       cls    classification table (every name)
       px/qv  live close / quote volume of EVERY name (phantom candles removed), unsplit
       count  trade counts (unsplit)
       spx/sqv  the included names, split into segments (the lane's instruments)
       seg    segment info per instrument
       mask   volume-rank mask on the instruments (before the last-hour liveness condition)
       notes  names without any candle on disk"""
    names = _names(market)
    cls = C.classify_perp(names) if market == "perp" else C.classify_spot(names)
    close, qvol, count, notes = C.daily_frames(market, names)
    if market == "spot":
        first = close.where(count > 0).apply(lambda s: s.first_valid_index())
        cls = C.flag_tokenized_equities(cls, first)
    px, qv = C.live_frames(close, qvol, count)
    cls = drop_aliases(cls, px)
    inc = [c for c in cls.index[cls["include"]] if c in px.columns]
    inc = [c for c in inc if px[c].notna().any()]
    assert_no_duplicate_instruments(px[inc])
    spx, sqv, seg = split_segments(px[inc], qv[inc])
    mask = pit_universe_mask(sqv, top_n=TOP_N[market], min_history=MIN_HISTORY, vol_window=VOL_WINDOW)
    return {"cls": cls, "px": px, "qv": qv, "count": count, "spx": spx, "sqv": sqv, "seg": seg, "mask": mask,
            "notes": notes, "included_names": inc}


def plan(market: str) -> dict:
    U = daily_universe(market)
    mask, px = U["mask"], U["px"]
    ever = [c for c in mask.columns if mask[c].any()]
    syms = {}
    for b in sorted({base_symbol(c) for c in ever}):
        s = px[b].dropna()
        # candle OPEN times of the first / last traded daily candle of the SYMBOL (row label - 1 day); the
        # download covers the whole life, every segment
        syms[b] = {"first_ms": int((s.index[0] - pd.Timedelta(days=1)).value // 10**6),
                   "last_ms": int((s.index[-1] - pd.Timedelta(days=1)).value // 10**6),
                   "rest": True}
    out = {"market": market, "top_n": TOP_N[market], "min_history": MIN_HISTORY, "vol_window": VOL_WINDOW,
           "gap_split_days": GAP_SPLIT_DAYS, "mask_summary": mask_summary(mask),
           "instruments_ever_in_mask": ever, "symbols": syms}
    p = C.write_plan(market, out)
    print(f"{utc_now()} plan-{market}: {len(syms)} ever-in-mask symbols -> {p}", flush=True)
    print(json.dumps(out["mask_summary"]), flush=True)
    return out


def holes(market: str) -> dict:
    """Hourly candles that the lane needs but that are absent on disk (the monthly archive zips have holes).
    For every instrument ever in the mask and every live row D of it: the 1h candles opened D-1 23:00,
    D 00:00 and D 01:00. Missing days are merged into [start_ms, end_ms) ranges per symbol and written to
    <src>/_hourly_holes.json for `binance_dl <market>-fill`."""
    U = daily_universe(market)
    mask, spx = U["mask"], U["spx"]
    rows = spx.index
    out: Dict[str, List[List[int]]] = {}
    n_days = 0
    cache = {}
    for c in [c for c in mask.columns if mask[c].any()]:
        b = base_symbol(c)
        if b not in cache:
            cache = {b: C.exec_prints(market, b)}
        ex = cache[b]
        live = spx[c].notna().to_numpy()
        pos = np.flatnonzero(live)
        z = pos[-1]
        need_exec = live.copy()
        need_exec[z] = False                                  # the last live row has no next candle by construction
        miss = (live & ex["pre"].reindex(rows).isna().to_numpy()) | (need_exec & (ex["exec"].reindex(rows).isna().to_numpy()
                                                                                | ex["alt"].reindex(rows).isna().to_numpy()))
        days = rows[miss]
        if len(days) == 0:
            continue
        n_days += len(days)
        rng: List[List[int]] = []
        for d in days:
            a = int((d - pd.Timedelta(days=1)).value // 10**6)
            e = int((d + pd.Timedelta(days=1)).value // 10**6)
            if rng and a <= rng[-1][1]:
                rng[-1][1] = max(rng[-1][1], e)
            else:
                rng.append([a, e])
        out.setdefault(b, [])
        out[b] += rng
    atomic_write_json(RAW / C.SRC[market] / "_hourly_holes.json",
                      {"written_utc": utc_now(), "instrument_days_with_a_missing_hourly_candle": n_days, "holes": out})
    print(f"{utc_now()} holes-{market}: {n_days} instrument-days, {len(out)} symbols, "
          f"{sum(len(v) for v in out.values())} ranges", flush=True)
    if market == "perp":
        # funding: a live row (traded on D and on D-1) whose execution interval (D-1 01:00, D 01:00] holds no
        # funding record at all — the monthly fundingRate zips have the same holes as the kline zips
        fout: Dict[str, List[List[int]]] = {}
        n_rows = 0
        fcache = {}
        for c in [c for c in mask.columns if mask[c].any()]:
            b = base_symbol(c)
            if b not in fcache:
                fcache = {b: C.funding_events(b)}
            _, cnt = C.funding_to_rows(fcache[b], rows, cut_after_ms=None)
            live = spx[c].notna()
            miss = (live & live.shift(1, fill_value=False) & (cnt == 0)).to_numpy()
            days = rows[miss]
            if len(days) == 0:
                continue
            n_rows += len(days)
            rng = []
            for d in days:
                a = int((d - pd.Timedelta(days=1) + pd.Timedelta(hours=1)).value // 10**6)
                e = int((d + pd.Timedelta(hours=1)).value // 10**6) + 1
                if rng and a <= rng[-1][1]:
                    rng[-1][1] = max(rng[-1][1], e)
                else:
                    rng.append([a, e])
            fout.setdefault(b, [])
            fout[b] += rng
        atomic_write_json(RAW / C.SRC[market] / "_funding_holes.json",
                          {"written_utc": utc_now(), "instrument_rows_without_any_funding_record": n_rows, "holes": fout})
        print(f"{utc_now()} holes-{market}: funding: {n_rows} instrument-rows, {len(fout)} symbols", flush=True)
    return out


def main(argv=None) -> int:
    cmd = (argv or sys.argv[1:])[0]
    if cmd == "plan-perp":
        plan("perp")
    elif cmd == "plan-spot":
        plan("spot")
    elif cmd == "holes-perp":
        holes("perp")
    elif cmd == "holes-spot":
        holes("spot")
    elif cmd == "build-perp":
        from .crypto_lanes import build_perp
        build_perp()
    elif cmd == "build-spot":
        from .crypto_lanes import build_spot
        build_spot()
    else:
        raise SystemExit(f"unknown command {cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
