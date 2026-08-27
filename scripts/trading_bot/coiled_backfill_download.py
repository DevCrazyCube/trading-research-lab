#!/usr/bin/env python3
"""Download-only relaunch of the Pick-2 early backfill (the universe was already built by
coiled_backfill_fetch.py -> universe_pick2_backfill.json; that run crashed only on a cosmetic
hardcoded print AFTER writing the universe). This just runs cmd_download against it.

    setsid nohup python3 scripts/trading_bot/coiled_backfill_download.py \
        > research/data/orphanflush_cache/coiled_backfill_dl.log 2>&1 &
"""
from __future__ import annotations
import datetime as dt
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import orphanflush_fetch as F

CACHE = F.CACHE
F.DESIGN_START = dt.date(2020, 9, 1)
F.DESIGN_END = dt.date(2022, 12, 31)
F.UNIVERSE = CACHE / "universe_pick2_backfill.json"
F.VOL1D = CACHE / "vol1d_pick2"
F.WARMUP_LEAD_MONTHS = 2

if __name__ == "__main__":
    print("=== download metrics+klines (2020-09..2022-12 backfill) ===", flush=True)
    F.cmd_download(types.SimpleNamespace(workers=16))
    print("=== backfill download DONE ===", flush=True)
