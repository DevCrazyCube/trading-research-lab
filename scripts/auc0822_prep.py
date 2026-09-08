#!/usr/bin/env python3
"""INVENT_0822B / auction-imbalance theme -- PANEL PREP.

Builds a compact numpy panel from the ALREADY-CACHED T3 collection (no network):

  research/data/t3_cache/auctions.json.gz   (sym|date) -> {'o': official OPEN print,
                                                           'c': official CLOSE print}   RAW px
  research/data/t3_cache/minutes_YYYY.json.gz  date -> sym -> {'15:29','15:49','15:59'} RAW px
  research/data/t3_cache/monthly_bars.json.gz  sym -> [[month, close, volume, vwap], ...]
  research/data/t3_cache/corporate_actions.json.gz  sym -> [dates touched by a corp action]
  research/data/t3_cache/calendar.json.gz      trading days

The minutes cache IS the point-in-time top-500-ADV universe T3 collected; that is exactly the
liquidity tier in which M0 measured the auction rail as a real, ~zero-spread fill, so the panel
is defined as "symbol-days that have a 15:59 minute bar" and no separate screen is invented.

Output: research/data/auc0822_cache/panel.npz
  dates   (D,)  'YYYY-MM-DD'
  syms    (S,)
  p29,p49,p59,po,pc  (D,S) float64, NaN where absent   -- RAW prices
  ca      (D,S) bool  -- symbol has a corporate-action date on this day (or is not covered)
  in_uni  (D,S) bool  -- symbol had a 15:59 bar that day (= point-in-time top-500 membership)
  advusd  (D,S) float64 -- prior-month dollar volume/day (point-in-time), NaN if unknown
"""
from __future__ import annotations

import gzip
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
T3 = ROOT / "research" / "data" / "t3_cache"
OUT = ROOT / "research" / "data" / "auc0822_cache"
OUT.mkdir(parents=True, exist_ok=True)


def load(name):
    with gzip.open(T3 / name, "rt") as fh:
        return json.load(fh)


def main():
    cal = load("calendar.json.gz")
    dates = [r["date"] for r in cal if r["date"] >= "2016-01-01"]
    dates = sorted(set(dates))
    didx = {d: i for i, d in enumerate(dates)}
    D = len(dates)
    print(f"[prep] {D} trading days {dates[0]}..{dates[-1]}", file=sys.stderr)

    # ---- minutes: defines the universe -------------------------------------------------
    minute_rows = {}          # (date, sym) -> (p29,p49,p59)
    symset = set()
    for yr in range(2016, 2027):
        p = T3 / f"minutes_{yr}.json.gz"
        if not p.exists():
            continue
        m = load(p.name)
        for d, per in m.items():
            if d not in didx:
                continue
            for s, mm in per.items():
                symset.add(s)
                minute_rows[(d, s)] = (mm.get("15:29"), mm.get("15:49"), mm.get("15:59"))
        del m
        print(f"[prep] minutes {yr}: cum {len(minute_rows)} rows, {len(symset)} syms",
              file=sys.stderr)

    syms = sorted(symset)
    sidx = {s: i for i, s in enumerate(syms)}
    S = len(syms)
    print(f"[prep] universe {S} symbols", file=sys.stderr)

    p29 = np.full((D, S), np.nan)
    p49 = np.full((D, S), np.nan)
    p59 = np.full((D, S), np.nan)
    in_uni = np.zeros((D, S), dtype=bool)
    for (d, s), (a, b, c) in minute_rows.items():
        i, j = didx[d], sidx[s]
        if a is not None:
            p29[i, j] = a
        if b is not None:
            p49[i, j] = b
        if c is not None:
            p59[i, j] = c
            in_uni[i, j] = True
    del minute_rows

    # ---- auction prints ----------------------------------------------------------------
    po = np.full((D, S), np.nan)
    pc = np.full((D, S), np.nan)
    auc = load("auctions.json.gz")
    hit = 0
    for k, v in auc.items():
        s, _, d = k.partition("|")
        j = sidx.get(s)
        if j is None:
            continue
        i = didx.get(d)
        if i is None:
            continue
        o, c = v.get("o"), v.get("c")
        if o:
            po[i, j] = o
        if c:
            pc[i, j] = c
        hit += 1
    del auc
    print(f"[prep] auction rows mapped: {hit}", file=sys.stderr)

    # ---- corporate actions: flag the day AND the day after (overnight legs) ------------
    ca = np.zeros((D, S), dtype=bool)
    cadat = load("corporate_actions.json.gz")
    covered = np.zeros(S, dtype=bool)
    for s, ds in cadat.items():
        j = sidx.get(s)
        if j is None:
            continue
        covered[j] = True
        for d in ds:
            i = didx.get(d)
            if i is not None:
                ca[i, j] = True
                if i + 1 < D:
                    ca[i + 1, j] = True
                if i - 1 >= 0:
                    ca[i - 1, j] = True
    del cadat
    print(f"[prep] corp-action coverage: {covered.sum()}/{S} symbols", file=sys.stderr)

    # ---- prior-month dollar volume (point in time) -------------------------------------
    mb = load("monthly_bars.json.gz")
    months = sorted({d[:7] for d in dates})
    mprev = {}
    for a, b in zip(months[:-1], months[1:]):
        mprev[b] = a
    dv = {}                      # (month, sym) -> $vol in that month
    for s, rows in mb.items():
        j = sidx.get(s)
        if j is None:
            continue
        for r in rows:
            if len(r) >= 4 and r[2] and r[3]:
                dv[(r[0], j)] = float(r[2]) * float(r[3])
    del mb
    advusd = np.full((D, S), np.nan)
    for i, d in enumerate(dates):
        pm = mprev.get(d[:7])
        if pm is None:
            continue
        for j in range(S):
            v = dv.get((pm, j))
            if v is not None:
                advusd[i, j] = v
    del dv

    np.savez_compressed(
        OUT / "panel.npz",
        dates=np.array(dates), syms=np.array(syms),
        p29=p29, p49=p49, p59=p59, po=po, pc=pc,
        ca=ca, in_uni=in_uni, advusd=advusd, ca_covered=covered,
    )
    print(f"[prep] wrote {OUT / 'panel.npz'}", file=sys.stderr)
    print(f"[prep] in_uni symbol-days={int(in_uni.sum())}, "
          f"with close print={int((in_uni & np.isfinite(pc)).sum())}, "
          f"with open print={int((in_uni & np.isfinite(po)).sum())}", file=sys.stderr)


if __name__ == "__main__":
    main()
