#!/usr/bin/env python3
"""Backfill Binance USD-M daily metrics zips past the BNXUSDT alphabetical wall.

WHY: the orphanflush metrics fetch (orphanflush_fetch.py, hardwired to the
2023-01..2024-12 design window) crawled symbols alphabetically and stopped at
BNXUSDT. As a result panel1h_r3meta.npz has count_long_short_ratio (glsr) only
for A-B tickers past 2024-12-31, so the 2025-01..2026-08 XS_GLSR_Z cross-section
is a biased ~28-name A-B subset, not the real top-N-by-volume universe.

WHAT: for every symbol on the panel1h_ext_trim.npz grid (150 names, the same grid
perpmicro_r3_metapanel.py builds on), download the free no-auth daily metrics zip
  https://data.binance.vision/data/futures/um/daily/metrics/{SYM}/{SYM}-metrics-{YYYY-MM-DD}.zip
for every date in [START..END] that is not already cached. Genuine 404s (symbol
not listed that day) are recorded as 'absent' and skipped forever. Metrics only --
prices already reach 2026-08 in panel1h_ext_trim.npz; only glsr is truncated.

Then re-run scripts/trading_bot/perpmicro_r3_metapanel.py to rebuild the glsr panel.

MEMORY LESSON (non-negotiable): run DETACHED, never inline in an agent turn:
    setsid nohup python3 scripts/trading_bot/glsr_metrics_backfill.py \
        > research/data/perpmicro_cache/logs/glsr_backfill.log 2>&1 &
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import pathlib
import threading
import time

import numpy as np
import requests
import requests.adapters

ROOT = pathlib.Path(__file__).resolve().parents[2]
GRID = ROOT / "research" / "data" / "perpmicro_cache" / "panel1h_ext_trim.npz"
MET = ROOT / "research" / "data" / "orphanflush_cache" / "raw" / "metrics"
DUMP = "https://data.binance.vision"

START = dt.date(2023, 1, 1)      # re-checks pre-2025 (cheap: already cached -> skipped)
END = dt.date(2026, 8, 17)
WORKERS = 16
USER_AGENT = "meme-research-glsr-backfill/1.0 (public-dump reader; no account, no order)"

_LOCAL = threading.local()
_rate_lock = threading.Lock()
_next_slot = [0.0]
MIN_INTERVAL = 1.0 / 20.0        # polite ~20 req/s shared across workers


def _throttle() -> None:
    with _rate_lock:
        now = time.monotonic()
        slot = max(now, _next_slot[0])
        _next_slot[0] = slot + MIN_INTERVAL
    d = slot - time.monotonic()
    if d > 0:
        time.sleep(d)


def _session() -> requests.Session:
    s = getattr(_LOCAL, "s", None)
    if s is None:
        s = requests.Session()
        s.headers["User-Agent"] = USER_AGENT
        s.mount("https://", requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=4))
        _LOCAL.s = s
    return s


def _get(url: str, *, retries: int = 5, timeout: int = 60) -> bytes | None:
    last = None
    for attempt in range(retries):
        _throttle()
        try:
            r = _session().get(url, timeout=timeout)
            if r.status_code == 404:
                return None
            if r.status_code == 200:
                return r.content
            last = RuntimeError(f"HTTP {r.status_code}")
            if r.status_code == 429:
                with _rate_lock:
                    _next_slot[0] = max(_next_slot[0], time.monotonic()) + 3.0 * (attempt + 1)
        except Exception as exc:  # noqa: BLE001 -- network is the whole point
            last = exc
            _LOCAL.s = None
        time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError(f"GET failed after {retries}: {url}: {last!r}")


def _path(sym: str, day: str) -> pathlib.Path:
    return MET / sym / f"{sym}-metrics-{day}.zip"


def _fetch(job) -> str:
    sym, day = job
    p = _path(sym, day)
    if p.exists() and p.stat().st_size > 0:
        return "cached"
    url = f"{DUMP}/data/futures/um/daily/metrics/{sym}/{sym}-metrics-{day}.zip"
    body = _get(url)
    if body is None:
        return "absent"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".part")
    tmp.write_bytes(body)
    tmp.replace(p)
    return "fetched"


def main() -> int:
    syms = [str(s) for s in np.load(GRID, allow_pickle=True)["symbols"]]
    days = []
    d = START
    while d <= END:
        days.append(d.isoformat())
        d += dt.timedelta(days=1)
    # skip files already on disk before building the job list (keeps the queue small)
    jobs = []
    for s in syms:
        have = set()
        sd = MET / s
        if sd.is_dir():
            for f in sd.iterdir():
                if f.name.endswith(".zip"):
                    have.add(f.name.replace(f"{s}-metrics-", "").replace(".zip", ""))
        for day in days:
            if day not in have:
                jobs.append((s, day))
    print(f"grid symbols={len(syms)} span={START}..{END} jobs(uncached)={len(jobs)}", flush=True)
    counts = {"cached": 0, "fetched": 0, "absent": 0}
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, st in enumerate(ex.map(_fetch, jobs), 1):
            counts[st] += 1
            if i % 2000 == 0:
                rate = i / max(time.time() - t0, 1e-9)
                eta = (len(jobs) - i) / max(rate, 1e-9) / 60
                print(f"  {i}/{len(jobs)} {counts} {rate:.0f}/s eta {eta:.0f}min", flush=True)
    print(f"DONE {counts} {time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
