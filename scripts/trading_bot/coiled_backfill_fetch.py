#!/usr/bin/env python3
"""Detached backfill of the EARLY design-window data for Pick 2 (Coiled Leverage Expansion).

Pick 2's frozen design window (SHORTLIST 6.6) is 2020-09-01 -> 2023-12-31. The existing
orphanflush cache holds metrics+klines only from 2022-10 (it was built for Pick 1's 2023-24
window). This backfills 2020-09-01 -> 2022-12-31 into the SAME raw cache (additive; the files
are keyed by symbol/date, so nothing is overwritten) so a FULL-design-window Gate-0 rerun and
the power census (gate 3) become possible.

It reuses orphanflush_fetch's machinery with the date constants monkeypatched, and writes its
point-in-time universe to a SEPARATE file (universe_pick2_backfill.json) and its 1d-vol probes
to a SEPARATE dir (vol1d_pick2) so it can NEVER clobber the live universe.json that the running
Gate-0 harness reads.

MEMORY rule obeyed: launch DETACHED, never inline.
    setsid nohup python3 scripts/trading_bot/coiled_backfill_fetch.py \
        > research/data/orphanflush_cache/coiled_backfill.log 2>&1 &
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import orphanflush_fetch as F  # same dir

CACHE = F.CACHE

# --- monkeypatch the frozen window to the EARLY slice, and redirect universe/vol1d outputs ---
F.DESIGN_START = dt.date(2020, 9, 1)
F.DESIGN_END = dt.date(2022, 12, 31)
F.UNIVERSE = CACHE / "universe_pick2_backfill.json"
F.VOL1D = CACHE / "vol1d_pick2"
F.WARMUP_LEAD_MONTHS = 2


def main() -> int:
    args = types.SimpleNamespace(workers=16)
    print("=== enumerate ===", flush=True)
    F.cmd_enumerate(args)
    print("=== universe (2020-09..2022-12) ===", flush=True)
    F.cmd_universe(args)
    print("=== download metrics+klines ===", flush=True)
    F.cmd_download(args)
    print("=== backfill DONE ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
