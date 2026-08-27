#!/usr/bin/env python3
"""Parallel pre-warm of the bookDepth per-bar band cache for the DESIGN universe.

Parsing a symbol's bookDepth to its reduced per-bar band series is deterministic and independent per
symbol, so warming the cache in a process pool changes NO result -- the subsequent
`orphanflush_depthq.py --window design` run reads the identical byte-for-byte series from disk. This
exists only to collapse the one-time 33 GB parse wall-time across cores. Idempotent: a symbol whose
cache tag already matches is skipped near-instantly.

Writes progress to research/trading_bot/depthq_bandcache_status.json.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import orphanflush_depthq as M  # noqa: E402

STATUS = M.RESULT_DIR / "depthq_bandcache_status.json"


def _days_for_months(months):
    out = []
    for ym in months:
        y, m = int(ym[:4]), int(ym[5:7])
        d = dt.date(y, m, 1)
        while d.month == m:
            out.append(d.isoformat())
            d += dt.timedelta(days=1)
    return out


def warm(sym_days):
    sym, days = sym_days
    t0 = time.perf_counter()
    n = len(M.load_bookdepth_band1_perbar(sym, days))
    return sym, n, time.perf_counter() - t0


def main():
    uni = json.loads(M.UNIVERSE_DESIGN.read_text())
    plan = uni["fetch_plan"]
    union = uni["union"]
    tasks = [(sym, _days_for_months(plan[sym])) for sym in union]
    n_total = len(tasks)
    workers = min(8, max(1, (__import__("os").cpu_count() or 4)))
    t_start = time.time()
    done = 0
    STATUS.write_text(json.dumps({"phase": "warming", "n_total": n_total, "done": 0,
                                  "workers": workers, "started": t_start}, indent=1))
    with cf.ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(warm, t): t[0] for t in tasks}
        for fut in cf.as_completed(futs):
            sym = futs[fut]
            try:
                s, n, secs = fut.result()
                msg = f"{s} bars={n} {secs:.1f}s"
            except Exception as exc:  # noqa: BLE401
                msg = f"{sym} ERROR {exc!r}"
            done += 1
            elapsed = time.time() - t_start
            rate = done / elapsed if elapsed else 0
            eta = (n_total - done) / rate if rate else None
            STATUS.write_text(json.dumps({
                "phase": "warming", "n_total": n_total, "done": done,
                "workers": workers, "elapsed_s": round(elapsed, 1),
                "eta_s": round(eta, 1) if eta else None, "last": msg,
            }, indent=1))
    STATUS.write_text(json.dumps({"phase": "done", "n_total": n_total, "done": done,
                                  "elapsed_s": round(time.time() - t_start, 1)}, indent=1))
    print(f"warmed {done}/{n_total} in {time.time()-t_start:.1f}s")


if __name__ == "__main__":
    sys.exit(main())
