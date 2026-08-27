#!/usr/bin/env python3
"""Orphan Flush (Pick #1) — FULL-WINDOW fetcher: bookDepth (q denominator) + held-out panel.

FROZEN SPEC: research/trading_bot/ORIGINAL_STRATEGY_SHORTLIST.md §5.1-5.7, §7.

WHY THIS EXISTS
---------------
Gate 0 (design-window, depth-FREE q) already passed. The REAL test needs the depth-denominated
q --- |dOI| / (trailing-24h median +-1% book notional) --- which requires `daily/bookDepth`. This
script fetches that panel for the SAME point-in-time top-80 universe over BOTH windows
(design 2023-01-01 -> 2024-12-31, held-out 2025-01-01 -> 2026-08-17), and --- so the one-shot
held-out backtest is actually runnable when the owner triggers it --- also fetches the held-out
`metrics` + 5m `klines` panel that the design cache stops short of (design cache ends 2024-12-31).

Deliverable #1 of the frozen-test staging. Nothing here runs a backtest or touches a held-out
number; it only DOWNLOADS public, no-auth archive files.

WHAT IT PULLS
-------------
  1. daily/bookDepth/{SYM}/{SYM}-bookDepth-{YYYY-MM-DD}.zip   ~2,867 snaps/day, +-1..+-5% bands,
     cols: timestamp, percentage, depth, notional. FROM 2023-01-01 (verified: 2022-12-31 -> 404).
     Fetched design-window-FIRST (jobs sorted ascending by date) so the depth-q DESIGN
     re-validation can run against a partial cache before the held-out tail lands.
  2. HELD-OUT daily/metrics/{SYM}/...            (design cache stops at 2024-12-31)
  3. HELD-OUT 5m klines: monthly for complete months, DAILY for the partial final month
     (2026-08 monthly archive is 404 until the month closes --- verified).

UNIVERSE (frozen, identical construction to orphanflush_fetch.py cmd_universe, EXTENDED to the
full window): point-in-time top-80 by trailing-30d quote volume as of each month-start, >=60
listed days, survivorship-complete (symbol list from the dump index, delisted names included).
Design-month membership recomputed here is identical by construction to universe.json (same code,
same vol1d inputs); an assertion enforces it.

MEMORY LESSON (non-negotiable): a rate-limited crawl runs as a DETACHED background subprocess,
never inline in an agent turn. Launch with:
    setsid nohup python3 scripts/trading_bot/orphanflush_bookdepth_fetch.py all \
        > research/data/orphanflush_cache/bookdepth_fetch.log 2>&1 < /dev/null &

USAGE
    python3 scripts/trading_bot/orphanflush_bookdepth_fetch.py universe-full   # build plan (+vol1d)
    python3 scripts/trading_bot/orphanflush_bookdepth_fetch.py bookdepth       # the ~60 GB pull
    python3 scripts/trading_bot/orphanflush_bookdepth_fetch.py heldout-panel   # metrics+klines 2025+
    python3 scripts/trading_bot/orphanflush_bookdepth_fetch.py status          # progress, any time
    python3 scripts/trading_bot/orphanflush_bookdepth_fetch.py all             # the three, in order
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import orphanflush_fetch as F  # noqa: E402  reuse the validated fetch helpers (throttle, session, IO)

# --------------------------------------------------------------------------- config (FROZEN)
DESIGN_START = dt.date(2023, 1, 1)
DESIGN_END = dt.date(2024, 12, 31)
HELDOUT_START = dt.date(2025, 1, 1)
FULL_END = dt.date(2026, 8, 17)            # held-out end (frozen)
BOOKDEPTH_FLOOR = dt.date(2023, 1, 1)      # earliest bookDepth on the archive (verified)
# bookDepth feeds ONLY q; q needs ~31 days of history (trailing-30d p90 of a trailing-24h-median
# quantity), so 2 months of warmup is correct and complete. (The 3-month metrics/klines warmup is
# for the beta + residual-sd chain, which bookDepth does not touch.) Using the leaner value here
# keeps the depth panel within disk.
BOOKDEPTH_WARMUP_MONTHS = 2

DAILY_KLINES_PREFIX = "data/futures/um/daily/klines/"

CACHE = F.CACHE
RAW = F.RAW
BOOKDEPTH = CACHE / "bookdepth"            # task-specified location
VOL1D = F.VOL1D
UNIVERSE_FULL = CACHE / "universe_full.json"
UNIVERSE_DESIGN = F.UNIVERSE


# --------------------------------------------------------------------------- universe (full window)
def _clip_day(d: dt.date, lo: dt.date, hi: dt.date) -> bool:
    return lo <= d <= hi


def _need_vol1d_months() -> list[str]:
    """vol1d months required to screen every month-start in [DESIGN_START .. FULL_END]."""
    lo = F._prev_month(DESIGN_START.isoformat()[:7], 3)     # 3 months back covers 60-day history
    hi = FULL_END.isoformat()[:7]
    return F._months(dt.date(int(lo[:4]), int(lo[5:7]), 1),
                     dt.date(int(hi[:4]), int(hi[5:7]), 1))


def cmd_universe_full(a) -> int:
    syms = json.loads(F.SYMBOLS.read_text())["symbols"]
    vmonths = _need_vol1d_months()
    # fetch only the vol1d months not already cached (design build already has 2022-10..2024-12).
    # --skip-fetch rebuilds the plan from cached vol1d only (use when a prior run already probed all
    # months to completion; re-probing the 404-absent months yields nothing and wastes ~18 min).
    if not getattr(a, "skip_fetch", False):
        jobs = [(s, ym) for s in syms for ym in vmonths
                if not (F._vol1d_path(s, ym).exists() and F._vol1d_path(s, ym).stat().st_size > 0)]
        print(f"universe-full: vol1d to fetch = {len(jobs)} "
              f"({len(syms)} syms x {len(vmonths)} months, cached skipped)", flush=True)
        counts = {"cached": 0, "fetched": 0, "absent": 0}
        t0 = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
            for i, rec in enumerate(ex.map(F._fetch_vol1d, jobs), 1):
                counts[rec["status"]] += 1
                if i % 4000 == 0:
                    print(f"  vol1d {i}/{len(jobs)} {counts} "
                          f"{i/max(time.time()-t0,1e-9):.0f}/s", flush=True)
        print(f"vol1d done {counts} {time.time()-t0:.0f}s", flush=True)
    else:
        print("universe-full: --skip-fetch, rebuilding plan from cached vol1d", flush=True)

    qvol = {s: F._load_daily_qvol(s, vmonths) for s in syms}
    full_months = F._months(DESIGN_START, FULL_END)
    membership: dict[str, list[str]] = {}
    for ym in full_months:
        ms = dt.date(int(ym[:4]), int(ym[5:7]), 1)          # point-in-time cut
        win_lo = ms - dt.timedelta(days=F.TRAILING_VOL_DAYS)
        rank = []
        for s in syms:
            days = qvol.get(s, {})
            tv = sum(v for d, v in days.items()
                     if win_lo <= dt.date.fromisoformat(d) < ms)
            listed = sum(1 for d in days if dt.date.fromisoformat(d) < ms)
            if listed >= F.MIN_LISTED_DAYS and tv > 0:
                rank.append((tv, s))
        rank.sort(reverse=True)
        top = [s for _, s in rank[:F.UNIVERSE_TOP_N]]
        if F.BASE_SYMBOL not in top:
            top.append(F.BASE_SYMBOL)
        membership[ym] = top

    # SURVIVORSHIP / REPRODUCIBILITY GUARD: design months must match universe.json exactly.
    if UNIVERSE_DESIGN.exists():
        du = json.loads(UNIVERSE_DESIGN.read_text())["membership"]
        for ym, members in du.items():
            if sorted(members) != sorted(membership.get(ym, [])):
                raise SystemExit(f"universe drift at {ym}: full-window rebuild disagrees with "
                                 f"universe.json -- refusing to proceed (frozen universe changed)")
        print("universe guard: design-month membership identical to universe.json OK", flush=True)

    # bookDepth fetch plan: in-universe months + 3-month warmup, expanded to days,
    # clipped to [BOOKDEPTH_FLOOR .. FULL_END].
    bd_days: dict[str, set[str]] = {}
    for ym, members in membership.items():
        wl_months = [ym] + [F._prev_month(ym, k) for k in range(1, BOOKDEPTH_WARMUP_MONTHS + 1)]
        for s in members:
            for wm in wl_months:
                for d in F._days_in_month(wm):
                    dd = dt.date.fromisoformat(d)
                    if _clip_day(dd, BOOKDEPTH_FLOOR, FULL_END):
                        bd_days.setdefault(s, set()).add(d)
    bookdepth_plan = {s: sorted(ds) for s, ds in bd_days.items()}

    # held-out panel plan: metrics (daily) + klines (monthly + partial-month daily),
    # for held-out months 2025-01..2026-08 + 3-month warmup; clipped so nothing pre-dates
    # what the trailing-30d windows need. Cached design days are skipped at download time.
    ho_months = F._months(HELDOUT_START, FULL_END)
    warm_floor = dt.date.fromisoformat(F._prev_month(HELDOUT_START.isoformat()[:7], 3) + "-01")
    ho_sym_months: dict[str, set[str]] = {}
    for ym in ho_months:
        for s in membership[ym]:
            for wm in [ym] + [F._prev_month(ym, k) for k in range(1, F.WARMUP_LEAD_MONTHS + 1)]:
                ho_sym_months.setdefault(s, set()).add(wm)
    heldout_plan = {s: sorted(m for m in ms
                              if dt.date.fromisoformat(m + "-01") >= warm_floor)
                    for s, ms in ho_sym_months.items()}

    out = {
        "windows": {
            "design": [DESIGN_START.isoformat(), DESIGN_END.isoformat()],
            "heldout": [HELDOUT_START.isoformat(), FULL_END.isoformat()],
        },
        "bookdepth_floor": BOOKDEPTH_FLOOR.isoformat(),
        "top_n": F.UNIVERSE_TOP_N, "min_listed_days": F.MIN_LISTED_DAYS,
        "trailing_vol_days": F.TRAILING_VOL_DAYS, "warmup_lead_months": F.WARMUP_LEAD_MONTHS,
        "base_symbol": F.BASE_SYMBOL,
        "full_months": full_months,
        "membership": membership,               # month -> [top-80 (+BTC) point-in-time], full window
        "bookdepth_plan": bookdepth_plan,       # symbol -> [days] of bookDepth to fetch
        "heldout_plan": heldout_plan,           # symbol -> [months] of metrics+klines to fetch
        "union": sorted(set().union(*[set(m) for m in membership.values()])),
    }
    UNIVERSE_FULL.write_text(json.dumps(out, indent=1))
    n_bd = sum(len(v) for v in bookdepth_plan.values())
    n_ho_m = sum(len(v) for v in heldout_plan.values())
    print(f"universe-full: union={len(out['union'])} symbols", flush=True)
    print(f"  bookDepth symbol-days to fetch = {n_bd} (~{n_bd*0.55/1024:.1f} GB @ ~560 KB/day)",
          flush=True)
    print(f"  held-out symbol-months (metrics+klines) = {n_ho_m}", flush=True)
    return 0


# --------------------------------------------------------------------------- downloads
def _bookdepth_path(sym: str, day: str) -> pathlib.Path:
    return BOOKDEPTH / sym / f"{sym}-bookDepth-{day}.zip"


def _fetch_bookdepth(job) -> dict:
    sym, day = job
    p = _bookdepth_path(sym, day)
    if p.exists() and p.stat().st_size > 0:
        return {"status": "cached"}
    url = f"{F.DUMP}/data/futures/um/daily/bookDepth/{sym}/{sym}-bookDepth-{day}.zip"
    body = F._get(url)
    if body is None:
        return {"status": "absent"}
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".part")
    tmp.write_bytes(body)
    tmp.replace(p)
    return {"status": "fetched", "bytes": len(body)}


def cmd_bookdepth(a) -> int:
    uni = json.loads(UNIVERSE_FULL.read_text())
    plan = uni["bookdepth_plan"]
    win = getattr(a, "window", "design")
    de = DESIGN_END

    def _in_win(day: str) -> bool:
        dd = dt.date.fromisoformat(day)
        if win == "design":
            return dd <= de
        if win == "heldout":
            return dd > de
        return True

    # design-window-FIRST: sort jobs ascending by DAY so the depth-q design re-validation can run
    # against a partial cache before the held-out tail is fetched.
    jobs = sorted(((s, d) for s, days in plan.items() for d in days if _in_win(d)),
                  key=lambda j: (j[1], j[0]))
    print(f"bookdepth[{win}]: {len(jobs)} symbol-days (~{len(jobs)*0.56/1024:.1f} GB) "
          f"design-first order", flush=True)
    counts = {"cached": 0, "fetched": 0, "absent": 0}
    nbytes = 0
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, rec in enumerate(ex.map(_fetch_bookdepth, jobs), 1):
            counts[rec["status"]] += 1
            nbytes += rec.get("bytes", 0)
            if i % 2000 == 0:
                el = time.time() - t0
                gb = nbytes / 1e9
                eta = (len(jobs) - i) / max(i / max(el, 1e-9), 1e-9) / 3600
                print(f"  bd {i}/{len(jobs)} {counts} {i/max(el,1e-9):.0f}/s "
                      f"{gb:.1f}GB eta~{eta:.1f}h", flush=True)
    print(f"bookdepth done {counts} {nbytes/1e9:.1f}GB {time.time()-t0:.0f}s", flush=True)
    return 0


def _fetch_heldout_metrics(job) -> dict:
    sym, day = job
    p = RAW / "metrics" / sym / f"{sym}-metrics-{day}.zip"
    if p.exists() and p.stat().st_size > 0:
        return {"status": "cached"}
    url = f"{F.DUMP}/data/futures/um/daily/metrics/{sym}/{sym}-metrics-{day}.zip"
    body = F._get(url)
    if body is None:
        return {"status": "absent"}
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".part"); tmp.write_bytes(body); tmp.replace(p)
    return {"status": "fetched"}


def _fetch_kline(job) -> dict:
    """kind in {'m','d'}: monthly klines (key=YYYY-MM) or daily klines (key=YYYY-MM-DD)."""
    kind, sym, key = job
    if kind == "m":
        p = RAW / "klines5m" / sym / f"{sym}-5m-{key}.zip"
        url = f"{F.DUMP}/{F.KLINES_PREFIX}{sym}/5m/{sym}-5m-{key}.zip"
    else:
        p = RAW / "klines5m" / sym / f"{sym}-5m-{key}.zip"   # daily files share the dir; distinct names
        url = f"{F.DUMP}/{DAILY_KLINES_PREFIX}{sym}/5m/{sym}-5m-{key}.zip"
    if p.exists() and p.stat().st_size > 0:
        return {"status": "cached"}
    body = F._get(url)
    if body is None:
        return {"status": "absent"}
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".part"); tmp.write_bytes(body); tmp.replace(p)
    return {"status": "fetched"}


def cmd_heldout_panel(a) -> int:
    uni = json.loads(UNIVERSE_FULL.read_text())
    plan = uni["heldout_plan"]
    partial_month = FULL_END.isoformat()[:7]     # e.g. 2026-08 -> daily klines (monthly not archived)

    metrics_jobs, kline_jobs = [], []
    for sym, months in sorted(plan.items()):
        for ym in months:
            for day in F._days_in_month(ym):
                dd = dt.date.fromisoformat(day)
                if dd <= FULL_END:
                    metrics_jobs.append((sym, day))
            if ym == partial_month:
                for day in F._days_in_month(ym):
                    if dt.date.fromisoformat(day) <= FULL_END:
                        kline_jobs.append(("d", sym, day))
            else:
                kline_jobs.append(("m", sym, ym))
    print(f"heldout-panel: metrics={len(metrics_jobs)} klines={len(kline_jobs)} "
          f"(cached design days skipped)", flush=True)
    counts = {"cached": 0, "fetched": 0, "absent": 0}
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, rec in enumerate(ex.map(_fetch_kline, kline_jobs), 1):
            counts[rec["status"]] += 1
    print(f"  klines done {counts} {time.time()-t0:.0f}s", flush=True)
    counts = {"cached": 0, "fetched": 0, "absent": 0}
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, rec in enumerate(ex.map(_fetch_heldout_metrics, metrics_jobs), 1):
            counts[rec["status"]] += 1
            if i % 4000 == 0:
                print(f"  metrics {i}/{len(metrics_jobs)} {counts} "
                      f"{i/max(time.time()-t0,1e-9):.0f}/s", flush=True)
    print(f"heldout-panel metrics done {counts} {time.time()-t0:.0f}s", flush=True)
    return 0


def cmd_status(_a) -> int:
    def count(base):
        return sum(1 for _ in base.rglob("*.zip")) if base.exists() else 0
    print(f"universe_full.json : {'yes' if UNIVERSE_FULL.exists() else 'no'}")
    print(f"bookdepth files    : {count(BOOKDEPTH)}")
    print(f"metrics files      : {count(RAW / 'metrics')}")
    print(f"klines5m files     : {count(RAW / 'klines5m')}")
    if UNIVERSE_FULL.exists():
        uni = json.loads(UNIVERSE_FULL.read_text())
        want_bd = sum(len(v) for v in uni["bookdepth_plan"].values())
        have_bd = count(BOOKDEPTH)
        print(f"bookdepth planned  : {want_bd}  ({100*have_bd/max(want_bd,1):.1f}% present)")
        try:
            import shutil
            free = shutil.disk_usage(str(CACHE)).free / 1e9
            print(f"disk free          : {free:.1f} GB")
        except Exception:
            pass
    return 0


def cmd_all(a) -> int:
    print("=== universe-full ===", flush=True); cmd_universe_full(a)
    a.window = "design"
    print("=== bookdepth DESIGN (design-first) ===", flush=True); cmd_bookdepth(a)
    print("=== heldout-panel (metrics+klines) ===", flush=True); cmd_heldout_panel(a)
    print("NOTE: held-out bookDepth (~45 GB) is DEFERRED to protect disk headroom and because the "
          "held-out is only spent if design re-validation passes. Fetch it when triggering the "
          "held-out:  python3 scripts/trading_bot/orphanflush_bookdepth_fetch.py bookdepth "
          "--window heldout", flush=True)
    print("=== ALL DONE ===", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("universe-full", "bookdepth", "heldout-panel", "status", "all"):
        p = sub.add_parser(name)
        p.add_argument("--workers", type=int, default=16)
        if name in ("universe-full", "all"):
            p.add_argument("--skip-fetch", action="store_true",
                           help="rebuild plan from cached vol1d without re-probing absent months")
        if name in ("bookdepth", "all"):
            p.add_argument("--window", choices=["design", "heldout", "all"], default="design",
                           help="which window's bookDepth to fetch (default design)")
    a = ap.parse_args()
    return {
        "universe-full": cmd_universe_full, "bookdepth": cmd_bookdepth,
        "heldout-panel": cmd_heldout_panel, "status": cmd_status, "all": cmd_all,
    }[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
