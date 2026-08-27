#!/usr/bin/env python3
"""T17 UNIVERSE SCREEN. Point-in-time, integer micro-dollars, no fitting, no strategy.

Applies Zarattini/Barbon/Aziz's three universe filters to every symbol on every session:

    open(d)      >= $5.00        -- the day's OPEN, known at 09:30, before the 09:35 decision
    avgvol14     >= 1,000,000    -- mean share volume over the 14 sessions BEFORE d
    ATR(14)      >= $0.50        -- over the 14 true ranges ending on d-1

THE ONE PLACE THIS DELIBERATELY DIFFERS FROM THE B22B RUNNER, AND WHY
---------------------------------------------------------------------
The B22B collection runner called the frozen `atr_micros(bars, 14)` with a bar list that
INCLUDED day d itself. `atr_micros` takes the last 15 bars, so its 14 true ranges ran
d-13..d and used **day d's own high, low and close** -- none of which is known at 09:35
when the stop distance is set. That is same-day lookahead in the R unit.

For a slippage *distribution* it is a second-order error and B22B's verdict does not turn
on it. For a PnL backtest it is not second-order: R is the stop distance, the position size
and the denominator of every reported number. So this module computes ATR(14) from bars
strictly BEFORE d -- window `bars[i-15:i]`, true ranges d-14..d-1 -- and calls the same
frozen function to do it, so the arithmetic is still the pinned definition.

Prices are RAW (`t17_collect.py` explains why level filters must not be adjusted).
"""

from __future__ import annotations

import glob
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from trading_bot import frozen as PINNED  # noqa: E402  (the pinned B22B definitions)

CACHE = ROOT / "research" / "data" / "t17_cache"

MIN_OPEN_MICROS = 5_000_000
MIN_AVG_VOLUME = 1_000_000
MIN_ATR_MICROS = 500_000
ATR_LOOKBACK = 14


def build_screen() -> dict:
    """day -> [[symbol, atr_micros, avgvol, open_micros], ...], sorted by avgvol desc."""
    per_day: dict = {}
    files = sorted(glob.glob(str(CACHE / "daily" / "chunk_*.json")))
    for fi, f in enumerate(files):
        chunk = json.loads(pathlib.Path(f).read_text())
        for sym, rows in chunk.items():
            n = len(rows)
            if n < ATR_LOOKBACK + 2:
                continue
            micros = [(r[0], PINNED.to_micros(r[1]), PINNED.to_micros(r[2]),
                       PINNED.to_micros(r[3]), PINNED.to_micros(r[4]), int(r[5]))
                      for r in rows]
            vols = [m[5] for m in micros]
            for i in range(ATR_LOOKBACK + 1, n):
                open_d = micros[i][1]
                if open_d < MIN_OPEN_MICROS:
                    continue
                avgvol = sum(vols[i - ATR_LOOKBACK:i]) // ATR_LOOKBACK
                if avgvol < MIN_AVG_VOLUME:
                    continue
                window = [{"h": m[2] / 1_000_000, "l": m[3] / 1_000_000, "c": m[4] / 1_000_000}
                          for m in micros[i - ATR_LOOKBACK - 1:i]]
                try:
                    atr = PINNED.atr_micros(window, ATR_LOOKBACK)
                except PINNED.Refused:
                    continue
                if atr < MIN_ATR_MICROS:
                    continue
                per_day.setdefault(micros[i][0], []).append([sym, atr, avgvol, open_d])
        print(f"screened chunk {fi + 1}/{len(files)}", flush=True)
    for d in per_day:
        per_day[d].sort(key=lambda r: -r[2])
    return per_day


if __name__ == "__main__":
    screen = build_screen()
    out = CACHE / "screen.json"
    out.write_text(json.dumps(screen))
    days = sorted(screen)
    sizes = sorted(len(v) for v in screen.values())
    print(f"days={len(days)} first={days[0]} last={days[-1]}")
    print("passers/day: min=%d p10=%d p50=%d p90=%d max=%d"
          % (sizes[0], sizes[len(sizes) // 10], sizes[len(sizes) // 2],
             sizes[9 * len(sizes) // 10], sizes[-1]))
