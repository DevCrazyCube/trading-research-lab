#!/usr/bin/env python3
"""T26 -- dense numpy panel for the WIDE overnight-equity formula sweep.

Reads ONLY cached files under research/data/t3_cache (no network). Writes one .npz of
(days x symbols) float32 matrices so the sweep harness never re-parses 27 MB of JSON.

Matrices (all aligned to `days` x `syms`):
    O    official opening auction print
    C    official closing auction print
    P29  last trade at 15:29 local
    P49  last trade at 15:49 local
    P59  last trade at 15:59 local
    ADV  dollar ADV of the PRIOR month (point-in-time, forward-filled into the month)
    U500 1.0 where the symbol is in that month's top-500-ADV screen (else 0)
    U300 same for top-300
    CA   1.0 where a corporate action lands on that DATE (exit-date exclusion uses day+1)

Peak RSS is dominated by the auctions dict (~3.6 M records). It is parsed, poured into the
matrices, and dropped before the minute files are touched.
"""

from __future__ import annotations

import gzip
import json
import pathlib
import sys
from collections import defaultdict

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / "research" / "data" / "t3_cache"
OUT = ROOT / "research" / "data" / "t26_cache"
OUT.mkdir(parents=True, exist_ok=True)

START = "2016-01-04"
END = "2026-08-14"


def _load(name):
    with gzip.open(CACHE / f"{name}.json.gz", "rt") as fh:
        return json.load(fh)


def _next_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    m += 1
    if m == 13:
        y, m = y + 1, 1
    return f"{y:04d}-{m:02d}"


def build():
    cal = _load("calendar")
    all_days = [r["date"] for r in cal]
    close_by_day = {r["date"]: r["close"] for r in cal}
    full_days = [d for d in all_days if close_by_day[d] == "16:00" and START <= d <= END]
    day_idx = {d: i for i, d in enumerate(full_days)}
    # next TRADING day (any close time) -- used to locate the exit open auction
    nxt_all = {all_days[i]: all_days[i + 1] for i in range(len(all_days) - 1)}

    print(f"full trading days: {len(full_days)}", flush=True)

    # ---- universe screen (identical arithmetic to t3_pressure_reversal.build_universe) ----
    pool = _load("asset_pool")
    monthly = _load("monthly_bars")
    days_in_month = defaultdict(int)
    for row in cal:
        days_in_month[row["date"][:7]] += 1

    by_month = defaultdict(list)
    adv_by_month = {}
    for sym, rows in monthly.items():
        if sym not in pool:
            continue
        for month, close, vol, vw in rows:
            nd = days_in_month.get(month, 0)
            if nd == 0 or close is None or close <= 5.0 or vol is None or vw is None:
                continue
            adv = (vw * vol) / nd
            adv_by_month[(_next_month(month), sym)] = adv
            if adv <= 20e6:
                continue
            by_month[month].append((adv, sym))

    uni500, uni300 = {}, {}
    for month, rows in by_month.items():
        ranked = sorted(rows, reverse=True)
        nm = _next_month(month)
        uni500[nm] = [s for _, s in ranked[:500]]
        uni300[nm] = [s for _, s in ranked[:300]]

    union = sorted({s for v in uni500.values() for s in v})
    sym_idx = {s: i for i, s in enumerate(union)}
    nD, nS = len(full_days), len(union)
    print(f"universe union: {nS} symbols; matrix {nD} x {nS}", flush=True)

    def blank():
        return np.full((nD, nS), np.nan, dtype=np.float32)

    O, C = blank(), blank()
    auct = _load("auctions")
    print(f"auction records: {len(auct)}", flush=True)
    for key, rec in auct.items():
        sym, day = key.split("|", 1)
        i = day_idx.get(day)
        j = sym_idx.get(sym)
        if i is None or j is None:
            continue
        if "o" in rec:
            O[i, j] = rec["o"]
        if "c" in rec:
            C[i, j] = rec["c"]
    del auct

    # ---- the exit leg needs the NEXT trading day's open even when that day is a half day ----
    # Build an "open auction of the next trading day" matrix directly, so a half-day exit is
    # still reachable; the sweep decides whether to keep those nights.
    O_next = blank()
    halfday_exit = np.zeros(nD, dtype=bool)
    # index open auctions for ALL days, not just full ones
    O_all = {}
    auct = _load("auctions")
    for key, rec in auct.items():
        if "o" not in rec:
            continue
        sym, day = key.split("|", 1)
        j = sym_idx.get(sym)
        if j is None:
            continue
        O_all.setdefault(day, {})[j] = rec["o"]
    del auct
    for i, d in enumerate(full_days):
        nd = nxt_all.get(d)
        if nd is None:
            continue
        halfday_exit[i] = close_by_day.get(nd) != "16:00"
        row = O_all.get(nd)
        if not row:
            continue
        js = np.fromiter(row.keys(), dtype=np.int64, count=len(row))
        vs = np.fromiter(row.values(), dtype=np.float32, count=len(row))
        O_next[i, js] = vs
    del O_all

    # ---- minutes ----
    P29, P49, P59 = blank(), blank(), blank()
    for year in range(2016, 2027):
        try:
            mins = _load(f"minutes_{year}")
        except FileNotFoundError:
            continue
        for day, rows in mins.items():
            i = day_idx.get(day)
            if i is None:
                continue
            for sym, m in rows.items():
                j = sym_idx.get(sym)
                if j is None:
                    continue
                if "15:29" in m:
                    P29[i, j] = m["15:29"]
                if "15:49" in m:
                    P49[i, j] = m["15:49"]
                if "15:59" in m:
                    P59[i, j] = m["15:59"]
        del mins
        print(f"  minutes {year} in", flush=True)

    # ---- ADV (prior month, forward filled) ----
    ADV = blank()
    U500 = np.zeros((nD, nS), dtype=np.float32)
    U300 = np.zeros((nD, nS), dtype=np.float32)
    for i, d in enumerate(full_days):
        month = d[:7]
        for s in uni500.get(month, ()):
            U500[i, sym_idx[s]] = 1.0
        for s in uni300.get(month, ()):
            U300[i, sym_idx[s]] = 1.0
    month_of = np.array([d[:7] for d in full_days])
    for month in np.unique(month_of):
        rows = np.where(month_of == month)[0]
        vals = np.full(nS, np.nan, dtype=np.float32)
        for sym, j in sym_idx.items():
            a = adv_by_month.get((month, sym))
            if a is not None:
                vals[j] = a
        ADV[rows, :] = vals

    # ---- corporate actions ----
    CA = np.zeros((nD, nS), dtype=np.float32)
    ca = _load("corporate_actions")
    ca_days = {d: i for i, d in enumerate(full_days)}
    for sym, dates in ca.items():
        j = sym_idx.get(sym)
        if j is None:
            continue
        for d in dates:
            i = ca_days.get(d)
            if i is not None:
                CA[i, j] = 1.0
    # a corporate action on the EXIT date (next trading day) is what T3 excludes
    CA_next = np.zeros((nD, nS), dtype=np.float32)
    ca_sets = {s: set(v) for s, v in ca.items()}
    for i, d in enumerate(full_days):
        nd = nxt_all.get(d)
        if nd is None:
            continue
        for sym, j in sym_idx.items():
            if nd in ca_sets.get(sym, ()):
                CA_next[i, j] = 1.0
    del ca, ca_sets

    np.savez_compressed(
        OUT / "panel.npz",
        days=np.array(full_days),
        syms=np.array(union),
        O=O, C=C, O_next=O_next, P29=P29, P49=P49, P59=P59,
        ADV=ADV, U500=U500, U300=U300, CA=CA, CA_next=CA_next,
        halfday_exit=halfday_exit,
    )
    print("wrote", OUT / "panel.npz", flush=True)


if __name__ == "__main__":
    build()
