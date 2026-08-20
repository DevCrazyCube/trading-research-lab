#!/usr/bin/env python3
"""Build the compact panel for the PRECISE CALENDAR / FORCED-FLOW sweep.

Two blocks, both cached to one .npz so the sweep itself is cheap to re-run:

  xs  : US single stocks on the 2018-08-01 .. 2026-08-14 session grid
        open / close / dollar-volume  (t17 daily cache, delisted names INCLUDED)
        + Reg SHO daily short volume  (T16 panel)
        + FINRA bi-monthly short interest (T16 panel), keyed to its DISSEMINATION
          date (settlement + 8 business days), never to its settlement date.
  etf : the calendar_cache daily ETF/index history back to 1993.

Point-in-time discipline
------------------------
* Universe inclusion is *equivalent* to the point-in-time eligibility rule, not a
  survivorship screen: a symbol is stored iff its trailing-60-session mean dollar
  volume ever reached the eligibility threshold while its close was over $5. A name
  that never crosses the bar could never be eligible on any day, so dropping it
  removes nothing a live strategy could have traded.
* Eligibility itself is recomputed per day from trailing data only.
* Short interest is aligned to settlement + 8 business days (FINRA's own
  dissemination lag). The T16 COVERAGE file warns the backfilled panel is not
  point-in-time; the 8-business-day shift is the minimum honest correction.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
T17 = ROOT / "research" / "data" / "t17_cache" / "daily"
CAL = ROOT / "research" / "data" / "calendar_cache"
T16 = ROOT / "research" / "data" / "t16_panels"
OUT = ROOT / "research" / "data" / "newterr_flowcal"
OUT.mkdir(parents=True, exist_ok=True)

XS_START = "2018-08-01"
XS_END = "2026-08-14"
ADV_MIN = 30e6          # trailing-60-session mean dollar volume
PX_MIN = 5.0


def session_grid():
    d = json.loads((CAL / "SPY.json").read_text())
    dates = [r[0] for r in d["rows"] if XS_START <= r[0] <= XS_END]
    return sorted(dates)


def build_xs(dates):
    idx = {d: i for i, d in enumerate(dates)}
    n = len(dates)
    keep_sym, keep_arr = [], []
    chunks = sorted(T17.glob("chunk_*.json"))
    for ci, p in enumerate(chunks):
        dd = json.load(p.open())
        for s, rows in dd.items():
            o = np.full(n, np.nan, np.float32)
            c = np.full(n, np.nan, np.float32)
            v = np.full(n, np.nan, np.float32)
            hit = 0
            for r in rows:
                i = idx.get(r[0])
                if i is None:
                    continue
                o[i], c[i], v[i] = r[1], r[4], r[5]
                hit += 1
            if hit < 250:
                continue
            dv = np.nan_to_num(c * v, nan=0.0).astype(np.float64)
            cs = np.concatenate([[0.0], np.cumsum(dv)])
            adv = (cs[60:] - cs[:-60]) / 60.0
            adv = np.concatenate([np.full(60, 0.0), adv[:-1]])  # adv[t] uses t-60..t-1
            px = np.nan_to_num(c, nan=0.0)
            if not ((adv >= ADV_MIN) & (px >= PX_MIN)).any():
                continue
            keep_sym.append(s)
            keep_arr.append((o, c, v))
        if ci % 25 == 0:
            print(f"  chunk {ci}/{len(chunks)} kept={len(keep_sym)}", flush=True)
        del dd
    k = len(keep_sym)
    print(f"xs universe: {k} symbols x {n} sessions", flush=True)
    O = np.stack([a[0] for a in keep_arr], axis=1)
    C = np.stack([a[1] for a in keep_arr], axis=1)
    V = np.stack([a[2] for a in keep_arr], axis=1)
    del keep_arr
    return keep_sym, O, C, V


def build_regsho(dates, syms):
    col = {s: j for j, s in enumerate(syms)}
    idx = {d: i for i, d in enumerate(dates)}
    n, k = len(dates), len(syms)
    SV = np.full((n, k), np.nan, np.float32)
    TV = np.full((n, k), np.nan, np.float32)
    root = T16 / "finra_regsho_daily" / "raw"
    sess = sorted(root.glob("session=*"))
    got = 0
    for sd in sess:
        day = sd.name.split("=", 1)[1]
        i = idx.get(day)
        if i is None:
            continue
        files = sorted(sd.glob("observed=*.csv.gz"))
        if not files:
            continue
        with gzip.open(files[-1], "rt", newline="") as f:
            rd = csv.reader(f)
            head = next(rd)
            try:
                si, sv, tv = head.index("symbol"), head.index("short_volume"), head.index("total_volume")
            except ValueError:
                continue
            for row in rd:
                j = col.get(row[si])
                if j is None:
                    continue
                try:
                    SV[i, j] = float(row[sv])
                    TV[i, j] = float(row[tv])
                except (ValueError, IndexError):
                    pass
        got += 1
        if got % 250 == 0:
            print(f"  regsho {got}/{len(sess)}", flush=True)
    print(f"regsho sessions filled: {got}", flush=True)
    return SV, TV


def build_short_interest(dates, syms):
    """Short interest keyed to DISSEMINATION date = settlement + 8 business days."""
    col = {s: j for j, s in enumerate(syms)}
    n, k = len(dates), len(syms)
    darr = np.array(dates)
    SI = np.full((n, k), np.nan, np.float32)      # current short position, shares
    SIP = np.full((n, k), np.nan, np.float32)     # previous short position, shares
    SETTLE = np.zeros(n, bool)                    # settlement date itself (for the
    root = T16 / "finra_short_interest" / "raw"   # "cover into the report" mechanism)
    dset = {d: i for i, d in enumerate(dates)}
    got = 0
    for sd in sorted(root.glob("settlement=*")):
        settle = sd.name.split("=", 1)[1]
        files = sorted(sd.glob("observed=*.csv.gz"))
        if not files:
            continue
        # dissemination: 8 business days after settlement -> first grid session with
        # index >= (index of settlement) + 8; if settlement is not a grid session use
        # the next one.
        pos = int(np.searchsorted(darr, settle, side="left"))
        if pos >= n:
            continue
        if settle in dset:
            SETTLE[dset[settle]] = True
        pub = pos + 8
        if pub >= n:
            continue
        with gzip.open(files[-1], "rt", newline="") as f:
            rd = csv.reader(f)
            head = next(rd)
            try:
                si_c = head.index("symbolCode")
                cur = head.index("currentShortPositionQuantity")
                prv = head.index("previousShortPositionQuantity")
            except ValueError:
                continue
            for row in rd:
                j = col.get(row[si_c])
                if j is None:
                    continue
                try:
                    SI[pub, j] = float(row[cur])
                    SIP[pub, j] = float(row[prv])
                except (ValueError, IndexError):
                    pass
        got += 1
    print(f"short-interest settlement dates mapped: {got}", flush=True)
    return SI, SIP, SETTLE


def build_etf():
    syms, rows_by = [], {}
    for p in sorted(CAL.glob("*.json")):
        d = json.loads(p.read_text())
        rows_by[d["symbol"]] = d["rows"]
        syms.append(d["symbol"])
    spy = {r[0] for r in rows_by["SPY"]}
    dates = sorted(spy)
    idx = {d: i for i, d in enumerate(dates)}
    n = len(dates)
    O = np.full((n, len(syms)), np.nan, np.float32)
    C = np.full((n, len(syms)), np.nan, np.float32)
    A = np.full((n, len(syms)), np.nan, np.float32)
    for j, s in enumerate(syms):
        for r in rows_by[s]:
            i = idx.get(r[0])
            if i is None:
                continue
            O[i, j], C[i, j], A[i, j] = r[1], r[4], r[6]
    return dates, syms, O, C, A


def main():
    dates = session_grid()
    print(f"xs grid {dates[0]}..{dates[-1]} n={len(dates)}", flush=True)
    syms, O, C, V = build_xs(dates)
    SV, TV = build_regsho(dates, syms)
    SI, SIP, SETTLE = build_short_interest(dates, syms)
    edates, esyms, EO, EC, EA = build_etf()
    out = OUT / "panel.npz"
    np.savez_compressed(
        out,
        dates=np.array(dates), syms=np.array(syms),
        O=O, C=C, V=V, SV=SV, TV=TV, SI=SI, SIP=SIP, SETTLE=SETTLE,
        edates=np.array(edates), esyms=np.array(esyms), EO=EO, EC=EC, EA=EA,
    )
    print(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB)", flush=True)


if __name__ == "__main__":
    sys.exit(main())
