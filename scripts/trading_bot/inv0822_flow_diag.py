#!/usr/bin/env python3
"""Validity check for the event-date convention.

If Wikipedia's date column really is the EFFECTIVE date and index trackers really execute in
the closing auction of the previous session, then relative volume must spike at R = ED-1.
If it spikes at ED instead, the convention is off by one and every offset must shift.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from trading_bot.inv0822_flow_engine import FLOW, Panel, dstr_to_int  # noqa: E402


def main():
    panel = Panel()
    ev = json.loads((FLOW / "raw" / "index_changes.json").read_text())
    ev = [e for e in ev if e["date"] >= "2016-01-05"]
    prof = {k: [] for k in range(-8, 9)}
    per_index = {}
    for e in ev:
        got = panel.get(e["ticker"])
        if got is None:
            continue
        c, dv = got
        ted = panel.day_index_on_or_after(dstr_to_int(e["date"]))
        if ted <= 0:
            continue
        R = ted - 1
        base = dv[max(0, R - 40):R - 8]
        base = base[np.isfinite(base)]
        if base.size < 15 or np.median(base) <= 0:
            continue
        med = float(np.median(base))
        for k in prof:
            i = R + k
            if 0 <= i < dv.size and np.isfinite(dv[i]):
                prof[k].append(dv[i] / med)
                per_index.setdefault((e["index"], e["side"], k), []).append(dv[i] / med)
    print("offset from R   median rel-$volume   n")
    for k in sorted(prof):
        v = prof[k]
        print(f"  R{k:+3d}          {np.median(v):8.2f}x          {len(v)}")
    print("\nby index/side, median rel-$volume at R-1 / R / R+1:")
    for idx in ("SP500", "SP400", "SP600"):
        for side in ("add", "delete"):
            row = []
            for k in (-1, 0, 1):
                v = per_index.get((idx, side, k), [])
                row.append(f"{np.median(v):6.2f}x(n={len(v)})" if v else "   -")
            print(f"  {idx} {side:6s}: " + "  ".join(row))


if __name__ == "__main__":
    main()
