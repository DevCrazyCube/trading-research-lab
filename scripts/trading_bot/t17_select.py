#!/usr/bin/env python3
"""T17 SELECTION. Applies the frozen rule's universe/direction/relative-volume filters.

Reads the screen (`screen.json`) and the cached opening-range bars (`opening/`), and writes
`selection.json`: for every session, the TOP 20 names by relative volume, with the direction
the opening candle assigned and the R unit the screen computed.

No PnL is computed here and no intraday path is read, so the selection cannot see the
outcome it is selecting for. `t17_collect.py paths` then fetches minute bars for exactly
these names -- which is also why the expensive fetch is small: 20 names a day, not 1,000.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from trading_bot import frozen as PINNED  # noqa: E402
from trading_bot import t17_orb as ORB  # noqa: E402

CACHE = ROOT / "research" / "data" / "t17_cache"


def build_selection() -> tuple:
    """Rolling 15-session window over the opening bars.

    Holding every session's opening bars at once is ~3 GB on this universe, and a run that
    dies on memory two hours in produces nothing. Only the current session and the previous
    RELVOL_LOOKBACK are ever resident.
    """
    screen = json.loads((CACHE / "screen.json").read_text())
    days = sorted(screen)

    def read(day):
        p = CACHE / "opening" / f"{day}.json"
        return json.loads(p.read_text()) if p.exists() else None

    opening = {}
    selection, census = {}, []
    for i, day in enumerate(days):
        keep = set(days[max(0, i - ORB.RELVOL_LOOKBACK):i + 1])
        for stale in [d for d in opening if d not in keep]:
            del opening[stale]
        for d in days[max(0, i - ORB.RELVOL_LOOKBACK):i + 1]:
            if d not in opening:
                opening[d] = read(d)
        if opening.get(day) is None:
            census.append({"day": day, "status": "OPENING_BARS_MISSING"})
            continue
        hist_days = [d for d in days[max(0, i - ORB.RELVOL_LOOKBACK):i] if opening.get(d)]
        today = opening[day]
        candidates, n_screen, n_no_open, n_short_hist, n_doji = [], 0, 0, 0, 0
        for sym, atr, avgvol, open_px in screen[day]:
            n_screen += 1
            row = today.get(sym)
            if row is None:
                n_no_open += 1
                continue
            o, h, low, c, v = (PINNED.to_micros(row[0]), PINNED.to_micros(row[1]),
                               PINNED.to_micros(row[2]), PINNED.to_micros(row[3]),
                               PINNED.to_shares(row[4]))
            history = [PINNED.to_shares(opening[d][sym][4]) for d in hist_days if sym in opening[d]]
            try:
                relvol = ORB.relative_volume(v, history)
            except PINNED.Refused:
                n_short_hist += 1
                continue
            direction = "long" if c > o else ("short" if c < o else None)
            if direction is None:
                n_doji += 1
                continue
            candidates.append((relvol, sym, direction, {"o": o, "h": h, "l": low, "c": c,
                                                        "v": v}, atr))
        top = ORB.select(candidates)
        selection[day] = [[c[0], c[1], c[2], c[3]["h"], c[3]["l"], c[4]] for c in top]
        census.append({"day": day, "status": "OK", "screened": n_screen,
                       "no_opening_bar": n_no_open, "short_relvol_history": n_short_hist,
                       "doji": n_doji, "eligible": len(candidates), "selected": len(top)})
    return selection, census


if __name__ == "__main__":
    sel, census = build_selection()
    (CACHE / "selection.json").write_text(json.dumps(sel))
    (CACHE / "selection_census.json").write_text(json.dumps(census))
    ok = [c for c in census if c["status"] == "OK"]
    full = [c for c in ok if c["selected"] == ORB.TOP_N]
    print(f"sessions with a selection: {len(ok)} / {len(census)}; "
          f"{len(full)} have a full top-{ORB.TOP_N}")
    if ok:
        n = sorted(c["selected"] for c in ok)
        print("selected/day: min=%d p10=%d p50=%d mean=%.1f"
              % (n[0], n[len(n) // 10], n[len(n) // 2], sum(n) / len(n)))
