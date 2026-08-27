#!/usr/bin/env python3
"""Orphan Flush (Pick #1) — Gate-0-scoped data fetcher for the DESIGN window.

FROZEN SPEC: research/trading_bot/ORIGINAL_STRATEGY_SHORTLIST.md, §3.1 / §5.1–5.6, gate 0.

WHAT THIS PULLS (and, deliberately, what it does NOT)
-----------------------------------------------------
Gate 0 is the zero-friction gross-at-zero-cost census on the DESIGN window only
(2023-01-01 -> 2024-12-31). Per §5.2 / §7 it needs NO bookDepth (that is the ~60 GB build,
deferred until after gate 0 can kill the candidate). So this fetcher pulls only:

  1. daily/metrics/{SYM}/{SYM}-metrics-{YYYY-MM-DD}.zip   5-min grid, sum_open_interest_value (dOI)
  2. monthly/klines/{SYM}/5m/{SYM}-5m-{YYYY-MM}.zip       5-min OHLCV for returns
  3. monthly/klines/{SYM}/1d/{SYM}-1d-{YYYY-MM}.zip       1-day quote_volume for the universe screen
  BTCUSDT 5m klines across the whole window (+warmup) for the beta neutralisation.

Universe is POINT-IN-TIME, SURVIVORSHIP-COMPLETE, TRAILING-ONLY (§5.1): top-80 by trailing-30-day
quote volume as of each month-start, >=60 days of listed history. The symbol list comes from the
data.binance.vision DUMP INDEX (delisted names included), NEVER from live exchangeInfo — that is
the survivorship leak T23 documents. Each in-universe symbol is fetched only for the months it is
in-universe plus a one-month warmup lead (>=30 days) so the harness's trailing-30d windows resolve.

All endpoints free, no-auth, read-only. No order, no account, no wallet.

MEMORY LESSON (non-negotiable): a rate-limited crawl must run as a DETACHED background subprocess,
never inline in an agent turn. Launch with:
    setsid nohup python3 scripts/trading_bot/orphanflush_fetch.py all > \
        research/data/orphanflush_cache/fetch.log 2>&1 &

USAGE
    python3 scripts/trading_bot/orphanflush_fetch.py enumerate
    python3 scripts/trading_bot/orphanflush_fetch.py universe
    python3 scripts/trading_bot/orphanflush_fetch.py download [--workers N]
    python3 scripts/trading_bot/orphanflush_fetch.py manifest
    python3 scripts/trading_bot/orphanflush_fetch.py all      # the four in sequence
    python3 scripts/trading_bot/orphanflush_fetch.py status   # progress summary, safe any time
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import datetime as dt
import hashlib
import io
import json
import pathlib
import re
import sys
import threading
import time
import urllib.parse
import zipfile

import requests
import requests.adapters

# --------------------------------------------------------------------------- config (FROZEN)
BUCKET_LIST = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DUMP = "https://data.binance.vision"
KLINES_PREFIX = "data/futures/um/monthly/klines/"

DESIGN_START = dt.date(2023, 1, 1)
DESIGN_END = dt.date(2024, 12, 31)
WARMUP_LEAD_MONTHS = 3          # contiguous. z(t) needs 30d of r_resid before t; each r_resid
                                 # needs a monthly beta fitted on the 30d before its month-start,
                                 # so the earliest event (2023-01-01) reaches ~60d back -> 3 months
                                 # of warmup makes all of January 2023 fully available (not dropped)
UNIVERSE_TOP_N = 80
MIN_LISTED_DAYS = 60           # §5.1 >=60 days of listed history
TRAILING_VOL_DAYS = 30        # §5.1 trailing-30-day quote volume
BASE_SYMBOL = "BTCUSDT"        # always fetched for the beta leg

CACHE = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "orphanflush_cache"
RAW = CACHE / "raw"
SYMBOLS = CACHE / "symbols.json"
VOL1D = CACHE / "vol1d"        # cached 1d klines for the universe screen
UNIVERSE = CACHE / "universe.json"
MANIFEST = CACHE / "manifest.json"

USER_AGENT = "meme-research-orphanflush/1.0 (public-dump reader; no account, no order)"
_LOCAL = threading.local()

# polite global token bucket ~20 req/s shared across workers
_rate_lock = threading.Lock()
_next_slot = [0.0]
MIN_INTERVAL = 1.0 / 20.0


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
    """Body on 200, None on a genuine 404, raise after retries on anything else."""
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


# --------------------------------------------------------------------------- helpers
def _months(a: dt.date, b: dt.date) -> list[str]:
    out, y, m = [], a.year, a.month
    while (y, m) <= (b.year, b.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def _prev_month(ym: str, k: int = 1) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    for _ in range(k):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


def _days_in_month(ym: str) -> list[str]:
    y, m = int(ym[:4]), int(ym[5:7])
    d = dt.date(y, m, 1)
    out = []
    while d.month == m:
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def _read_zip_csv(body: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        text = zf.read(zf.namelist()[0]).decode("utf-8")
    return [row for row in csv.reader(io.StringIO(text)) if row]


def _is_header(row: list[str]) -> bool:
    try:
        float(row[0])
        return False
    except (ValueError, IndexError):
        return True


# --------------------------------------------------------------------------- enumerate
def cmd_enumerate(_a) -> int:
    """Symbol list from the DUMP INDEX (delisted names included), filtered to *USDT perps."""
    CACHE.mkdir(parents=True, exist_ok=True)
    url = (f"{BUCKET_LIST}?prefix={urllib.parse.quote(KLINES_PREFIX, safe='')}"
           f"&delimiter={urllib.parse.quote('/', safe='')}")
    body = _get(url)
    if body is None:
        raise RuntimeError("bucket listing 404")
    text = body.decode("utf-8")
    if "<IsTruncated>true</IsTruncated>" in text:
        raise RuntimeError("delimiter listing truncated -- add pagination")
    folders = re.findall(re.escape(KLINES_PREFIX) + r"([^/]+)/", text)
    # USDT-margined perps only; exclude USDC-quoted and index/bull-bear leftovers.
    syms = sorted({f for f in folders if f.endswith("USDT")})
    SYMBOLS.write_text(json.dumps({"source": BUCKET_LIST, "count": len(syms),
                                   "symbols": syms}, indent=1))
    print(f"symbols={len(syms)} (USDT perps from dump index)")
    for probe in ("BTCUSDT", "LUNAUSDT", "FTTUSDT", "ARBUSDT"):
        print(f"  {probe}: {'present' if probe in syms else 'ABSENT'}")
    return 0


# --------------------------------------------------------------------------- universe (1d volume)
def _vol1d_path(sym: str, ym: str) -> pathlib.Path:
    return VOL1D / sym / f"{sym}-1d-{ym}.zip"


def _fetch_vol1d(job) -> dict:
    sym, ym = job
    p = _vol1d_path(sym, ym)
    if p.exists() and p.stat().st_size > 0:
        return {"sym": sym, "ym": ym, "status": "cached"}
    url = f"{DUMP}/{KLINES_PREFIX}{sym}/1d/{sym}-1d-{ym}.zip"
    body = _get(url)
    if body is None:
        return {"sym": sym, "ym": ym, "status": "absent"}
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".part")
    tmp.write_bytes(body)
    tmp.replace(p)
    return {"sym": sym, "ym": ym, "status": "fetched"}


def _load_daily_qvol(sym: str, months: list[str]) -> dict[str, float]:
    """date -> quote_volume for a symbol, from cached 1d klines."""
    out: dict[str, float] = {}
    for ym in months:
        p = _vol1d_path(sym, ym)
        if not (p.exists() and p.stat().st_size > 0):
            continue
        for row in _read_zip_csv(p.read_bytes()):
            if _is_header(row):
                continue
            ot = int(float(row[0]))
            if ot > 10 ** 14:
                ot //= 1000
            d = dt.datetime.fromtimestamp(ot / 1000, dt.timezone.utc).date().isoformat()
            try:
                out[d] = float(row[7])  # quote_volume
            except (ValueError, IndexError):
                pass
    return out


def cmd_universe(a) -> int:
    """Build the point-in-time top-80 universe per design month-start from trailing-30d quote vol."""
    syms = json.loads(SYMBOLS.read_text())["symbols"]
    # 1d klines span: earliest month-start needs >=60 days of prior history.
    lo = _prev_month(DESIGN_START.isoformat()[:7], 3)      # 3 months back covers 60-day history
    hi = _prev_month(DESIGN_END.isoformat()[:7], 0)
    vmonths = _months(dt.date(int(lo[:4]), int(lo[5:7]), 1),
                      dt.date(int(hi[:4]), int(hi[5:7]), 1))
    jobs = [(s, ym) for s in syms for ym in vmonths]
    print(f"universe 1d fetch: {len(jobs)} jobs ({len(syms)} syms x {len(vmonths)} months)",
          flush=True)
    counts = {"cached": 0, "fetched": 0, "absent": 0}
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, rec in enumerate(ex.map(_fetch_vol1d, jobs), 1):
            counts[rec["status"]] += 1
            if i % 4000 == 0:
                print(f"  1d {i}/{len(jobs)} {counts} {i/max(time.time()-t0,1e-9):.0f}/s",
                      flush=True)
    print(f"1d done {counts} {time.time()-t0:.0f}s", flush=True)

    # rank per design month-start on trailing-30d quote volume, >=60 listed days
    qvol = {s: _load_daily_qvol(s, vmonths) for s in syms}
    design_months = _months(DESIGN_START, DESIGN_END)
    universe: dict[str, list[str]] = {}
    for ym in design_months:
        ms = dt.date(int(ym[:4]), int(ym[5:7]), 1)          # month-start (point-in-time cut)
        win_lo = ms - dt.timedelta(days=TRAILING_VOL_DAYS)
        rank = []
        for s in syms:
            days = qvol.get(s, {})
            # trailing-30d volume: strictly BEFORE the month-start (no forward data)
            tv = sum(v for d, v in days.items() if win_lo <= dt.date.fromisoformat(d) < ms)
            listed = sum(1 for d in days if dt.date.fromisoformat(d) < ms)
            if listed >= MIN_LISTED_DAYS and tv > 0:
                rank.append((tv, s))
        rank.sort(reverse=True)
        top = [s for _, s in rank[:UNIVERSE_TOP_N]]
        if BASE_SYMBOL not in top:
            top.append(BASE_SYMBOL)
        universe[ym] = top

    # per-symbol fetch-months = in-universe months + a CONTIGUOUS warmup lead each
    sym_months: dict[str, set[str]] = {}
    for ym, members in universe.items():
        for s in members:
            sym_months.setdefault(s, set()).add(ym)
            for k in range(1, WARMUP_LEAD_MONTHS + 1):
                sym_months[s].add(_prev_month(ym, k))
    # BTC needs the full continuous window (+ the same warmup floor) for the beta leg
    floor = _prev_month(DESIGN_START.isoformat()[:7], WARMUP_LEAD_MONTHS)
    full = set(_months(dt.date(int(floor[:4]), int(floor[5:7]), 1), DESIGN_END))
    sym_months.setdefault(BASE_SYMBOL, set()).update(full)
    fetch_plan = {s: sorted(ms) for s, ms in sym_months.items()}

    union = sorted(sym_months)
    out = {
        "design_window": [DESIGN_START.isoformat(), DESIGN_END.isoformat()],
        "top_n": UNIVERSE_TOP_N, "min_listed_days": MIN_LISTED_DAYS,
        "trailing_vol_days": TRAILING_VOL_DAYS, "warmup_lead_months": WARMUP_LEAD_MONTHS,
        "base_symbol": BASE_SYMBOL,
        "n_union_symbols": len(union),
        "membership": universe,       # month -> [top-80 (+BTC) point-in-time]
        "fetch_plan": fetch_plan,     # symbol -> [months to fetch metrics+5m for]
        "union": union,
    }
    UNIVERSE.write_text(json.dumps(out, indent=1))
    total_symmonths = sum(len(v) for v in fetch_plan.values())
    print(f"universe: union={len(union)} symbols, {total_symmonths} symbol-months to fetch")
    print(f"  sample month 2023-01: {len(universe['2023-01'])} names, "
          f"first5={universe['2023-01'][:5]}")
    return 0


# --------------------------------------------------------------------------- download metrics + 5m
def _metrics_path(sym: str, day: str) -> pathlib.Path:
    return RAW / "metrics" / sym / f"{sym}-metrics-{day}.zip"


def _k5m_path(sym: str, ym: str) -> pathlib.Path:
    return RAW / "klines5m" / sym / f"{sym}-5m-{ym}.zip"


def _fetch_generic(job) -> dict:
    kind, sym, key, path = job
    if path.exists() and path.stat().st_size > 0:
        return {"kind": kind, "status": "cached"}
    if kind == "metrics":
        url = f"{DUMP}/data/futures/um/daily/metrics/{sym}/{sym}-metrics-{key}.zip"
    else:  # klines5m
        url = f"{DUMP}/{KLINES_PREFIX}{sym}/5m/{sym}-5m-{key}.zip"
    body = _get(url)
    if body is None:
        return {"kind": kind, "status": "absent"}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(body)
    tmp.replace(path)
    return {"kind": kind, "status": "fetched"}


def _clip_days(months: list[str]) -> list[str]:
    """All calendar days across the fetch-months, clipped to the fetchable floor/ceiling."""
    floor = _prev_month(DESIGN_START.isoformat()[:7], WARMUP_LEAD_MONTHS) + "-01"
    floor_d = dt.date.fromisoformat(floor)
    days = []
    for ym in months:
        for d in _days_in_month(ym):
            dd = dt.date.fromisoformat(d)
            if floor_d <= dd <= DESIGN_END:
                days.append(d)
    return days


def cmd_download(a) -> int:
    uni = json.loads(UNIVERSE.read_text())
    plan = uni["fetch_plan"]
    jobs = []
    for sym, months in sorted(plan.items()):
        for ym in months:
            jobs.append(("klines5m", sym, ym, _k5m_path(sym, ym)))
        for day in _clip_days(months):
            jobs.append(("metrics", sym, day, _metrics_path(sym, day)))
    n_metrics = sum(1 for j in jobs if j[0] == "metrics")
    n_k = len(jobs) - n_metrics
    print(f"download jobs={len(jobs)} (metrics={n_metrics} klines5m={n_k})", flush=True)
    counts = {"cached": 0, "fetched": 0, "absent": 0}
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, rec in enumerate(ex.map(_fetch_generic, jobs), 1):
            counts[rec["status"]] += 1
            if i % 4000 == 0:
                print(f"  dl {i}/{len(jobs)} {counts} {i/max(time.time()-t0,1e-9):.0f}/s",
                      flush=True)
    print(f"download done {counts} {time.time()-t0:.0f}s", flush=True)
    return 0


# --------------------------------------------------------------------------- manifest
def cmd_manifest(_a) -> int:
    files = sorted(p for p in CACHE.rglob("*.zip") if p.is_file())
    agg = hashlib.sha256()
    recs = []
    for p in files:
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        rel = p.relative_to(CACHE).as_posix()
        recs.append({"path": rel, "bytes": p.stat().st_size, "sha256": h})
        agg.update(f"{rel}:{h}\n".encode())
    total = sum(r["bytes"] for r in recs)
    out = {"n_files": len(recs), "total_bytes": total,
           "aggregate_sha256": agg.hexdigest(), "files": recs}
    MANIFEST.write_text(json.dumps(out, indent=1))
    print(f"manifest: {len(recs)} files, {total/1e9:.2f} GB, agg={agg.hexdigest()[:16]}")
    return 0


def cmd_status(_a) -> int:
    def count(kind):
        d = RAW / kind
        return sum(1 for _ in d.rglob("*.zip")) if d.exists() else 0
    print(f"symbols.json  : {'yes' if SYMBOLS.exists() else 'no'}")
    print(f"universe.json : {'yes' if UNIVERSE.exists() else 'no'}")
    print(f"vol1d files   : {sum(1 for _ in VOL1D.rglob('*.zip')) if VOL1D.exists() else 0}")
    print(f"metrics files : {count('metrics')}")
    print(f"klines5m files: {count('klines5m')}")
    if UNIVERSE.exists():
        uni = json.loads(UNIVERSE.read_text())
        plan = uni["fetch_plan"]
        want_k = sum(len(v) for v in plan.values())
        want_m = sum(len(_clip_days(v)) for v in plan.values())
        print(f"planned       : klines5m={want_k} metrics={want_m}")
    return 0


def cmd_all(a) -> int:
    print("=== enumerate ===", flush=True); cmd_enumerate(a)
    print("=== universe ===", flush=True); cmd_universe(a)
    print("=== download ===", flush=True); cmd_download(a)
    print("=== manifest ===", flush=True); cmd_manifest(a)
    print("=== ALL DONE ===", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("enumerate", "universe", "download", "manifest", "status", "all"):
        p = sub.add_parser(name)
        p.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    return {"enumerate": cmd_enumerate, "universe": cmd_universe, "download": cmd_download,
            "manifest": cmd_manifest, "status": cmd_status, "all": cmd_all}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
