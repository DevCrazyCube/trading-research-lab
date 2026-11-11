"""FASTMOM v1 — minute-scale momentum on the three most liquid crypto perps, at real fees.

Implements the FROZEN pre-registration `research/factory/FASTMOM_PREREGISTRATION.md`
(sha256 340b178b79d23fabd4c12939c68cfaebf91c3740a95e875623906e549e284f24). That file is the spec;
this module never edits it and refuses to run if its hash differs.

    cd /home/anont/meme
    research/factory/.venv/bin/python -m scripts.factory.fastmom <stage>

Stages (run in this order; the holdout is sealed in code until DESIGN_PASSERS.json exists)
  download     monthly 1-minute kline zips + .CHECKSUM from data.binance.vision, sha256-verified
  verify       re-hash every zip on disk against its saved .CHECKSUM (no network)
  design       all 129 formula-symbol pairs on the DESIGN window -> design_ledger.csv / .json,
               control_design.csv, data_report_design.json
  passers      apply the design pass rule mechanically -> DESIGN_PASSERS.json (+ .sha256)
  holdout      holdout window, design passers ONLY -> holdout_passers.csv
  descriptive  holdout statistics of ALL pairs (descriptive, not evidence) -> holdout_descriptive.csv
  sensitivity  design window under the alternative reading of each ambiguous sentence (not decisional)
  reproduce    recompute the frozen tables with the current code and compare byte for byte
  report       reports/fastmom_v1/FASTMOM_RESULTS.md

Nothing here places an order, holds a key or talks to a trading endpoint. Research only.

HOW EVERY OPEN POINT OF THE PRE-REGISTRATION IS READ (R1..R16; each is repeated in the report)
  R1  sigma_k(t) = sample standard deviation (ddof = 1, about the window mean) of the 1,440 overlapping
      k-minute simple returns close_i / close_(i-k) - 1 for i = t-1439 .. t, i.e. the window ENDS at and
      INCLUDES the signal bar. It needs all 1,440 returns (1,440 + k consecutive present bars); otherwise
      there is no signal at t (no trade on incomplete data).
  R2  A signal at the close of bar t is filled at the OPEN of bar t+1. A fixed hold of h minutes exits at
      the OPEN of bar t+1+h.
  R3  "Signals during an open position are ignored": a position that exits at the open of bar x (or inside
      bar x) is still open at the close of bar x-1, so the first signal that can be acted on is the one at
      the close of bar x (entry at the open of x+1). No back-to-back re-entry at the exit print.
  R4  Tradeable bar = present in the archive AND volume > 0. Entries need a tradeable entry bar (else the
      signal is dropped and counted). A time exit due on a missing or zero-volume bar is filled at the next
      tradeable open (counted). Stops and targets are evaluated on tradeable bars only.
  R5  Cost is additive on entry notional: net = side * (exit / entry - 1) - 2 * cost_per_side.
  R6  M2 breakout: close_t > max(high_(t-N) .. high_(t-1)) (long), close_t < min(low_(t-N) .. low_(t-1))
      (short); all N previous bars must be present.
  R7  M2 trailing stop: distance = y * sigma_5 (as a RETURN, sigma_5 frozen at the signal bar) from the best
      price since entry; long stop = best * (1 - y*sigma_5), short stop = best * (1 + y*sigma_5). The best
      price starts at the entry price and the stop is live from the entry bar on.
  R8  M2 order of events inside a bar is unknown. Bar by bar the WORSE of the two orders of the bar's high
      and low is taken (the pre-registration's own "pessimistic ordering" of M3, applied to the trail):
        a) bar opens beyond the stop                      -> filled at the open (gap-through is paid);
        b) the adverse extreme reaches the stop that was in force at the open (best so far, incl. this
           open)                                          -> filled at that stop;
        c) else, if the adverse extreme reaches the stop RATCHETED by this bar's own favourable extreme
           (favourable extreme first, then the retrace)   -> filled at the ratcheted stop;
        d) else the position survives the bar and the best price is updated.
  R9  M3 levels: take-profit = entry * (1 + a*sigma_5), stop = entry * (1 - b*sigma_5) for a long (mirrored
      for a short), sigma_5 at the signal bar. Stop first whenever a bar's range touches both. A stop on a
      bar that opens beyond it is filled at the open; a take-profit is ALWAYS filled at its level (no price
      improvement on a favourable gap).
  R10 Time exits (M2 60 min, M3 30 min) are at the open of the bar that many minutes after the entry bar.
  R11 A trade belongs to the window that contains its entry bar and must be able to finish inside it: no
      entry whose time-limit exit would fall after the window's last bar. The design run loads no bar
      after 2023-12-31; the holdout run uses December 2023 only as warm-up for sigma and the N-bar extremes.
  R12 Win rate is on NET returns (the gross win rate is also in the ledger).
  R13 Total net return = sum of per-trade net returns (fixed notional, not compounded); the compounded
      figure is also in the ledger.
  R14 A trade is booked to the UTC day of its ENTRY (daily P&L, clusters). Daily Sharpe uses every calendar
      day of the window (no trade = 0) and is annualised by sqrt(365).
  R15 Day-clustered t = mean / sqrt( G/(G-1) * sum_g (sum_{i in g} (r_i - mean))^2 / N^2 ), G = days with
      at least one trade (cluster-robust variance of an intercept, CR1).
  R16 Benjamini-Hochberg over all 129 pairs at q = 10 %: the p-value definition is not in the spec, so a
      pair must be rejected under BOTH the one-sided p (H1: mean > 0) and the two-sided p, each from
      Student-t with G-1 degrees of freedom. A pair with fewer than 2 trading days has p = 1.
"""
from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import io
import json
import math
import os
import sys
import threading
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[2]
FACTORY = REPO / "research" / "factory"
PREREG_PATH = FACTORY / "FASTMOM_PREREGISTRATION.md"
PREREG_SHA256 = "340b178b79d23fabd4c12939c68cfaebf91c3740a95e875623906e549e284f24"
RAW_1M = FACTORY / "data" / "raw" / "binance" / "futures_um" / "archive_klines_1m"
RUN_DIR = FACTORY / "runs" / "fastmom_v1"
REPORT_DIR = FACTORY / "reports" / "fastmom_v1"
VISION = "https://data.binance.vision/"
ARCHIVE_KEY = "data/futures/um/monthly/klines/{sym}/1m/{sym}-1m-{ym}.zip"

# ---- pre-registration §1: data and windows ---------------------------------------------------------
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
DATA_FIRST_MONTH = "2021-01"
DATA_LAST_MONTH = "2026-10"
DESIGN_FIRST_MONTH, DESIGN_LAST_MONTH = "2021-01", "2023-12"       # 2021-01-01 -> 2023-12-31
HOLDOUT_FIRST_MONTH, HOLDOUT_LAST_MONTH = "2024-01", "2026-10"     # 2024-01-01 -> 2026-10-31
HOLDOUT_WARMUP_MONTH = "2023-12"                                   # history for sigma / N-bar extremes only
MIN_MS = 60_000
DAY_MIN = 1440

# ---- pre-registration §2: costs, in bp of notional per side -----------------------------------------
TAKER_FEE_BP = 5.0
HALF_SPREAD_BP = {"BTCUSDT": 0.07, "ETHUSDT": 0.24, "SOLUSDT": 0.60}
MAKER_BOUND_BP = 2.0                                               # optimistic bound, no spread

# ---- pre-registration §3 / §4 -------------------------------------------------------------------------
SIGMA_WINDOW = 1440
M2_MAX_HOLD = 60
M3_MAX_HOLD = 30
DESIGN_T_MIN = 3.0
HOLDOUT_T_MIN = 2.0
BH_Q = 0.10
CONTROL_SEED = 20261110

KIND_TIME, KIND_STOP, KIND_TP, KIND_GAP, KIND_RATCHET = 0, 1, 2, 3, 4
KIND_NAMES = {KIND_TIME: "time", KIND_STOP: "stop", KIND_TP: "take_profit", KIND_GAP: "gap_stop",
              KIND_RATCHET: "ratchet_stop"}


def base_cost_side_bp(sym: str) -> float:
    return TAKER_FEE_BP + HALF_SPREAD_BP[sym]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(f"{utc_now()} {msg}", flush=True)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}_{threading.get_ident()}")
    with open(tmp, "wb") as f:
        f.write(content)
    os.replace(tmp, path)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def check_prereg() -> str:
    """The frozen spec must be byte-identical to the hash recorded in DECISIONS.md (2026-11-10 18:09 UTC)."""
    got = sha256_file(PREREG_PATH)
    if got != PREREG_SHA256:
        raise SystemExit(f"REFUSED: {PREREG_PATH} sha256 {got} != frozen {PREREG_SHA256}")
    return got


# ---- months -----------------------------------------------------------------------------------------
def month_range(first: str, last: str) -> List[str]:
    y, m = int(first[:4]), int(first[5:7])
    y1, m1 = int(last[:4]), int(last[5:7])
    out = []
    while (y, m) <= (y1, m1):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def month_bounds_ms(ym: str) -> Tuple[int, int]:
    """[start_ms, end_ms) of a calendar month in UTC."""
    y, m = int(ym[:4]), int(ym[5:7])
    a = datetime(y, m, 1, tzinfo=timezone.utc)
    b = datetime(y + (m == 12), (m % 12) + 1, 1, tzinfo=timezone.utc)
    return int(a.timestamp()) * 1000, int(b.timestamp()) * 1000


def iso_minute(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def zip_path(sym: str, ym: str) -> Path:
    return RAW_1M / sym / f"{sym}-1m-{ym}.zip"


def checksum_path(sym: str, ym: str) -> Path:
    return RAW_1M / sym / f"{sym}-1m-{ym}.zip.CHECKSUM"


def published_sha(sym: str, ym: str) -> Optional[str]:
    """sha256 from the saved .CHECKSUM file (format '<sha256>  <file name>'), None if absent or malformed."""
    p = checksum_path(sym, ym)
    if not p.exists():
        return None
    parts = p.read_text().split()
    if len(parts) != 2 or parts[1] != zip_path(sym, ym).name or len(parts[0]) != 64:
        return None
    return parts[0].lower()


def verified_on_disk(sym: str, ym: str) -> bool:
    z = zip_path(sym, ym)
    pub = published_sha(sym, ym)
    return bool(pub) and z.exists() and sha256_file(z) == pub


# ---- download ---------------------------------------------------------------------------------------
class _RateLimiter:
    """At most one request START every `gap` seconds across all threads (0.26 s -> < 4 requests / second)."""

    def __init__(self, gap: float):
        self.gap = gap
        self.lock = threading.Lock()
        self.next = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            t = max(now, self.next)
            self.next = t + self.gap
        if t > now:
            time.sleep(t - now)


def stage_download(workers: int = 4, gap: float = 0.26) -> int:
    """Resumable and idempotent: a file whose zip hashes to its saved .CHECKSUM is skipped without a request.

    Plain scripted GETs through the factory data layer's `http_get` (the requests library's default
    User-Agent, exponential backoff on 418/429/5xx, no retry on 404), rate-limited here to < 4 requests/s.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from scripts.factory.data.common import HttpError, http_get      # reused, not re-implemented

    check_prereg()
    limiter = _RateLimiter(gap)
    jobs = [(s, ym) for s in SYMBOLS for ym in month_range(DATA_FIRST_MONTH, DATA_LAST_MONTH)]
    log(f"download: {len(jobs)} files, {workers} workers, >= {gap}s between request starts")
    prev: Dict[Tuple[str, str], dict] = {}
    mpath = RUN_DIR / "download_manifest.json"
    if mpath.exists():                                          # keep the original fetch record of a file
        for r in json.loads(mpath.read_text()).get("files", []):
            prev[(r["symbol"], r["month"])] = r
    records: Dict[Tuple[str, str], dict] = {}
    lock = threading.Lock()

    def one(sym: str, ym: str) -> dict:
        key = ARCHIVE_KEY.format(sym=sym, ym=ym)
        rec = {"symbol": sym, "month": ym, "url": VISION + key, "path": str(zip_path(sym, ym).relative_to(REPO))}
        if verified_on_disk(sym, ym):
            z = zip_path(sym, ym)
            rec.update(status="skip_verified", bytes=z.stat().st_size, sha256=published_sha(sym, ym),
                       checksum_published=published_sha(sym, ym), checksum_ok=True, checked_utc=utc_now())
            old = prev.get((sym, ym), {})
            if old.get("fetched_utc") and old.get("sha256") == rec["sha256"]:
                rec["fetched_utc"] = old["fetched_utc"]
            return rec
        last = "?"
        for attempt in range(3):
            try:
                limiter.wait()
                chk = http_get(VISION + key + ".CHECKSUM").text
                limiter.wait()
                body = http_get(VISION + key).content
            except HttpError as e:                              # 404 etc.: recorded, never silent
                rec.update(status=f"http_{e.status}", checksum_ok=False, checked_utc=utc_now())
                return rec
            parts = chk.split()
            pub = parts[0].lower() if parts else ""
            actual = sha256_bytes(body)
            if len(parts) == 2 and parts[1] == zip_path(sym, ym).name and pub == actual:
                atomic_write_bytes(zip_path(sym, ym), body)
                atomic_write_text(checksum_path(sym, ym), chk)
                rec.update(status="ok", bytes=len(body), sha256=actual, checksum_published=pub, checksum_ok=True,
                           fetched_utc=utc_now())
                return rec
            last = f"sha256 {actual} != published {pub!r}"
            time.sleep(2 + 3 * attempt)
        rec.update(status="checksum_mismatch", detail=last, checksum_ok=False, checked_utc=utc_now())
        return rec

    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(one, s, ym): (s, ym) for s, ym in jobs}
        for fut in as_completed(futs):
            k = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:                              # network failure after retries
                rec = {"symbol": k[0], "month": k[1], "status": "error", "detail": repr(e)[:300],
                       "checksum_ok": False, "checked_utc": utc_now()}
            with lock:
                records[k] = rec
                done += 1
                if done % 20 == 0 or done == len(jobs):
                    log(f"  {done}/{len(jobs)} files ({time.time() - t0:.0f}s)")
    recs = [records[k] for k in jobs]
    counts: Dict[str, int] = {}
    for r in recs:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    manifest = {"written_utc": utc_now(), "source": VISION + ARCHIVE_KEY, "user_agent": "python-requests default",
                "files_expected": len(jobs), "status_counts": counts,
                "bytes_total": int(sum(r.get("bytes", 0) for r in recs)), "files": recs}
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(mpath, json.dumps(manifest, indent=1))
    bad = [r for r in recs if not r.get("checksum_ok")]
    log(f"download done: {counts}; {manifest['bytes_total'] / 1e6:.1f} MB; failures {len(bad)}")
    for r in bad:
        log(f"  FAILED {r['symbol']} {r['month']}: {r['status']} {r.get('detail', '')}")
    return 1 if bad else 0


def stage_verify() -> int:
    """Offline re-verification of every expected zip against its saved published checksum."""
    bad = []
    n = 0
    for s in SYMBOLS:
        for ym in month_range(DATA_FIRST_MONTH, DATA_LAST_MONTH):
            n += 1
            if not verified_on_disk(s, ym):
                bad.append(f"{s} {ym}")
    log(f"verify: {n - len(bad)}/{n} zips match their published sha256")
    for b in bad:
        log(f"  NOT VERIFIED {b}")
    return 1 if bad else 0


# ---- the seal ---------------------------------------------------------------------------------------
def require_design_frozen() -> dict:
    """No holdout bar is parsed before the design passers are frozen, and the frozen list must still describe
    the ledger on disk."""
    p = RUN_DIR / "DESIGN_PASSERS.json"
    side = RUN_DIR / "DESIGN_PASSERS.sha256"
    if not p.exists() or not side.exists():
        raise SystemExit("REFUSED: the holdout is sealed until DESIGN_PASSERS.json (+ .sha256) exists")
    if sha256_file(p) != side.read_text().split()[0]:
        raise SystemExit("REFUSED: DESIGN_PASSERS.json does not match its recorded sha256")
    d = json.loads(p.read_text())
    if sha256_file(RUN_DIR / "design_ledger.csv") != d["design_ledger_csv_sha256"]:
        raise SystemExit("REFUSED: design_ledger.csv changed after the passers were frozen")
    return d


# ---- bars -------------------------------------------------------------------------------------------
KLINE_COLS = ("open_time", "open", "high", "low", "close", "volume", "count")
_USECOLS = (0, 1, 2, 3, 4, 5, 8)


def parse_kline_csv(b: bytes, ym: str, label: str = "") -> Tuple[np.ndarray, dict]:
    """One monthly archive CSV -> float64 rows (open_ms, open, high, low, close, volume, count).

    Header row optional (newer files have one). USD-M futures archives are in milliseconds; a file in
    microseconds (the spot archive since 2025) is converted and flagged; a file mixing units is refused.
    Every open time must sit on the minute grid, inside the month of the file name, strictly increasing.
    """
    has_header = b[:1].isalpha()
    txt = io.BytesIO(b)
    a = np.loadtxt(txt, delimiter=",", skiprows=1 if has_header else 0, usecols=_USECOLS, dtype=np.float64, ndmin=2)
    info = {"rows": int(len(a)), "header": bool(has_header), "unit": "ms"}
    if len(a) == 0:
        return a, info
    t = a[:, 0]
    micro = t > 1e14
    if micro.any():
        if not micro.all():
            raise ValueError(f"{label}: file mixes millisecond and microsecond open times")
        if np.any(np.mod(t, 1000.0) != 0):
            raise ValueError(f"{label}: microsecond open times are not whole milliseconds")
        a[:, 0] = t / 1000.0
        t = a[:, 0]
        info["unit"] = "us"
    lo, hi = month_bounds_ms(ym)
    if t.min() < lo or t.max() >= hi:
        raise ValueError(f"{label}: a bar opens outside the month named by the file "
                         f"([{t.min():.0f}, {t.max():.0f}] vs [{lo}, {hi}))")
    if np.any(np.mod(t, float(MIN_MS)) != 0):
        raise ValueError(f"{label}: an open time is not on the minute grid")
    if np.any(np.diff(t) <= 0):
        raise ValueError(f"{label}: open times are not strictly increasing (duplicate or unsorted rows)")
    return a, info


def read_month(sym: str, ym: str) -> Tuple[np.ndarray, dict]:
    z = zip_path(sym, ym)
    if not verified_on_disk(sym, ym):
        raise SystemExit(f"REFUSED: {z} is missing or does not match its published sha256")
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        if len(names) != 1:
            raise ValueError(f"{z.name}: expected one member, found {names}")
        b = zf.read(names[0])
    return parse_kline_csv(b, ym, label=z.name)


class Bars:
    """One symbol on a COMPLETE minute grid: index i <-> open time t0_ms + i minutes. A bar absent from the
    archive is NaN in every column. `tradeable` = present and volume > 0 (pre-registration: zero-volume bars
    are no-trade bars)."""

    def __init__(self, symbol: str, t0_ms: int, o, h, l, c, vol, count=None):
        self.symbol = symbol
        self.t0_ms = int(t0_ms)
        self.o = np.ascontiguousarray(o, dtype=np.float64)
        self.h = np.ascontiguousarray(h, dtype=np.float64)
        self.l = np.ascontiguousarray(l, dtype=np.float64)
        self.c = np.ascontiguousarray(c, dtype=np.float64)
        self.vol = np.ascontiguousarray(vol, dtype=np.float64)
        self.count = None if count is None else np.ascontiguousarray(count, dtype=np.float64)
        self.n = int(len(self.o))
        for a in (self.h, self.l, self.c, self.vol):
            if len(a) != self.n:
                raise ValueError("bar columns differ in length")
        self.present = np.isfinite(self.o) & np.isfinite(self.h) & np.isfinite(self.l) & np.isfinite(self.c)
        self.tradeable = self.present & (self.vol > 0)
        idx = np.where(self.tradeable, np.arange(self.n, dtype=np.int64), self.n)
        nt = np.minimum.accumulate(idx[::-1])[::-1] if self.n else idx
        self.next_tradeable = np.append(nt, self.n).astype(np.int64)      # length n + 1, sentinel n
        self._lists: Optional[dict] = None

    def lists(self) -> dict:
        """Python lists for the scalar exit loops (list indexing is ~3x faster than numpy scalar indexing)."""
        if self._lists is None:
            self._lists = {"o": self.o.tolist(), "h": self.h.tolist(), "l": self.l.tolist(),
                           "tr": self.tradeable.tolist(), "nt": self.next_tradeable.tolist()}
        return self._lists

    def free(self) -> None:
        self._lists = None


def _runs(mask: np.ndarray) -> List[Tuple[int, int]]:
    """(start index, length) of every run of True."""
    if not mask.any():
        return []
    d = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return [(int(s), int(e - s)) for s, e in zip(starts, ends)]


def load_bars(sym: str, first_month: str, last_month: str) -> Tuple[Bars, dict]:
    """Parse the verified monthly zips of [first_month, last_month] onto a complete minute grid.

    Refuses to parse any month after the design window unless the design passers are frozen."""
    months = month_range(first_month, last_month)
    if months[-1] > DESIGN_LAST_MONTH:
        require_design_frozen()
    t0, _ = month_bounds_ms(months[0])
    _, t1 = month_bounds_ms(months[-1])
    n = (t1 - t0) // MIN_MS
    cols = [np.full(n, np.nan) for _ in range(6)]             # o h l c vol count
    per_month = []
    n_header = n_micro = 0
    for ym in months:
        a, info = read_month(sym, ym)
        lo, hi = month_bounds_ms(ym)
        per_month.append({"month": ym, "expected": int((hi - lo) // MIN_MS), "present": info["rows"]})
        n_header += info["header"]
        n_micro += info["unit"] == "us"
        if len(a):
            i = ((a[:, 0] - t0) / MIN_MS).astype(np.int64)
            for j in range(6):
                cols[j][i] = a[:, j + 1]
        del a
    bars = Bars(sym, t0, cols[0], cols[1], cols[2], cols[3], cols[4], cols[5])
    present = bars.present
    zero_vol = present & (bars.vol <= 0)
    zero_cnt = present & (bars.count <= 0)
    with np.errstate(invalid="ignore"):
        bad_ohlc = present & ((bars.h < np.maximum(bars.o, bars.c)) | (bars.l > np.minimum(bars.o, bars.c))
                              | (bars.l <= 0))
    miss_runs = _runs(~present)
    zv_runs = _runs(zero_vol)
    report = {
        "symbol": sym, "first_month": first_month, "last_month": last_month,
        "first_bar_utc": iso_minute(t0), "last_bar_utc": iso_minute(t1 - MIN_MS),
        "files": len(months), "files_with_header_row": int(n_header), "files_in_microseconds": int(n_micro),
        "bars_expected": int(n), "bars_present": int(present.sum()), "bars_missing": int((~present).sum()),
        "missing_runs": len(miss_runs), "longest_missing_run_min": max([r[1] for r in miss_runs], default=0),
        "missing_run_list": [{"start_utc": iso_minute(t0 + s * MIN_MS), "minutes": ln} for s, ln in miss_runs[:200]],
        "zero_volume_bars": int(zero_vol.sum()), "zero_trade_count_bars": int(zero_cnt.sum()),
        "zero_volume_runs": len(zv_runs), "longest_zero_volume_run_min": max([r[1] for r in zv_runs], default=0),
        "zero_volume_run_list": [{"start_utc": iso_minute(t0 + s * MIN_MS), "minutes": ln} for s, ln in zv_runs[:200]],
        "ohlc_inconsistent_bars": int(bad_ohlc.sum()),
        "tradeable_bars": int(bars.tradeable.sum()),
        "months_with_missing_bars": [m for m in per_month if m["present"] != m["expected"]],
    }
    return bars, report


# ---- pre-registration §3: the 43 formulas -----------------------------------------------------------
@dataclass(frozen=True)
class Formula:
    family: str
    fid: str
    k: int = 0          # M1 / M3: look-back of the return, minutes
    x: float = 0.0      # M1 / M3: threshold in sigma_k
    h: int = 0          # M1: fixed hold, minutes
    N: int = 0          # M2: breakout look-back, bars
    y: float = 0.0      # M2: trailing distance in sigma_5
    a: float = 0.0      # M3: take-profit in sigma_5
    b: float = 0.0      # M3: stop-loss in sigma_5

    @property
    def maxhold(self) -> int:
        return {"M1": self.h, "M2": M2_MAX_HOLD, "M3": M3_MAX_HOLD}[self.family]


def formulas() -> List[Formula]:
    out: List[Formula] = []
    for k in (1, 5, 15):
        for x in (1, 2, 3):
            for h in (1, 5, 15, 60):
                out.append(Formula("M1", f"M1.k{k}.x{x}.h{h}", k=k, x=float(x), h=h))
    for N in (30, 120):
        for y in (1, 2):
            out.append(Formula("M2", f"M2.N{N}.y{y}", N=N, y=float(y)))
    for a, b in ((1, 1), (2, 1), (1, 2)):
        out.append(Formula("M3", f"M3.a{a}.b{b}", k=5, x=2.0, a=float(a), b=float(b)))
    if len(out) != 43 or len({f.fid for f in out}) != 43:
        raise AssertionError("the pre-registration declares exactly 43 formulas")
    return out


# ---- sigma and signals ------------------------------------------------------------------------------
def k_returns(c: np.ndarray, k: int) -> np.ndarray:
    """r[i] = c[i] / c[i-k] - 1 (NaN where either close is missing or i < k)."""
    r = np.full(len(c), np.nan)
    if len(c) > k:
        r[k:] = c[k:] / c[:-k] - 1.0
    return r


def trailing_std(r: np.ndarray, window: int = SIGMA_WINDOW) -> np.ndarray:
    """out[i] = sample std (ddof = 1) of r[i-window+1 .. i]; NaN unless all `window` values are finite.

    Prefix sums only, so out[i] is a function of r[0..i] alone (bit-identical when later values change)."""
    n = len(r)
    out = np.full(n, np.nan)
    if n < window:
        return out
    valid = np.isfinite(r)
    x = np.where(valid, r, 0.0)
    cs1 = np.concatenate(([0.0], np.cumsum(x)))
    cs2 = np.concatenate(([0.0], np.cumsum(x * x)))
    cn = np.concatenate(([0], np.cumsum(valid, dtype=np.int64)))
    s1 = cs1[window:] - cs1[:-window]
    s2 = cs2[window:] - cs2[:-window]
    full = (cn[window:] - cn[:-window]) == window
    var = np.maximum((s2 - s1 * s1 / window) / (window - 1), 0.0)
    out[window - 1:] = np.where(full, np.sqrt(var), np.nan)
    return out


def burst_side(r: np.ndarray, sigma: np.ndarray, x: float) -> np.ndarray:
    """+1 where r > x*sigma, -1 where r < -x*sigma, else 0 (NaN anywhere -> 0; sigma must be > 0)."""
    with np.errstate(invalid="ignore"):
        ok = np.isfinite(r) & np.isfinite(sigma) & (sigma > 0)
        long = ok & (r > x * sigma)
        short = ok & (r < -x * sigma)
    return long.astype(np.int8) - short.astype(np.int8)


def breakout_side(h: np.ndarray, l: np.ndarray, c: np.ndarray, N: int) -> np.ndarray:
    """+1 where close[t] > max(high[t-N..t-1]), -1 where close[t] < min(low[t-N..t-1]); 0 if any of the N
    previous bars (or bar t) is missing."""
    from numpy.lib.stride_tricks import sliding_window_view

    n = len(c)
    side = np.zeros(n, dtype=np.int8)
    if n <= N:
        return side
    hh = sliding_window_view(h, N)[:-1].max(axis=1)           # row j = h[j .. j+N-1] -> bar t = j + N
    ll = sliding_window_view(l, N)[:-1].min(axis=1)
    with np.errstate(invalid="ignore"):
        side[N:] = (c[N:] > hh).astype(np.int8) - (c[N:] < ll).astype(np.int8)
    return side


class SignalCache:
    """Per-symbol cache of k-minute returns and sigma_k (k = 1, 5, 15)."""

    def __init__(self, bars: Bars, sigma_lag: int = 0):
        self.bars = bars
        self.sigma_lag = int(sigma_lag)       # 0 = registered reading R1; 1 = sensitivity S1 (window ends at t-1)
        self._r: Dict[int, np.ndarray] = {}
        self._s: Dict[int, np.ndarray] = {}

    def r(self, k: int) -> np.ndarray:
        if k not in self._r:
            self._r[k] = k_returns(self.bars.c, k)
        return self._r[k]

    def sigma(self, k: int) -> np.ndarray:
        if k not in self._s:
            sg = trailing_std(self.r(k), SIGMA_WINDOW)
            if self.sigma_lag:
                sg = np.concatenate((np.full(self.sigma_lag, np.nan), sg[:-self.sigma_lag]))
            self._s[k] = sg
        return self._s[k]

    def signal(self, f: Formula) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """(side per bar, sigma used by the exit rule or None)."""
        if f.family == "M1":
            return burst_side(self.r(f.k), self.sigma(f.k), f.x), None
        if f.family == "M2":
            return breakout_side(self.bars.h, self.bars.l, self.bars.c, f.N), self.sigma(5)
        if f.family == "M3":
            return burst_side(self.r(5), self.sigma(5), 2.0), self.sigma(5)
        raise ValueError(f.family)


# ---- exits (scalar loops over Python lists; one position at a time bounds the work by the bar count) ----
def _exit_tp_sl(O, H, L, TR, NT, e: int, side: int, up: float, dn: float, maxhold: int) -> Tuple[int, float, int]:
    """M3. `up` = a*sigma_5 (take-profit distance as a return), `dn` = b*sigma_5 (stop distance).
    Returns (exit bar, exit price, kind). Stop first when both are touched; a stop on a bar that opens beyond
    it pays the open; a take-profit always fills at its level."""
    entry = O[e]
    due = e + maxhold
    j = e
    if side > 0:
        sl = entry * (1.0 - dn)
        tp = entry * (1.0 + up)
        while j < due:
            if TR[j]:
                if L[j] <= sl:
                    o = O[j]
                    return (j, o, KIND_GAP) if o <= sl else (j, sl, KIND_STOP)
                if H[j] >= tp:
                    return j, tp, KIND_TP
            j += 1
    else:
        sl = entry * (1.0 + dn)
        tp = entry * (1.0 - up)
        while j < due:
            if TR[j]:
                if H[j] >= sl:
                    o = O[j]
                    return (j, o, KIND_GAP) if o >= sl else (j, sl, KIND_STOP)
                if L[j] <= tp:
                    return j, tp, KIND_TP
            j += 1
    x = NT[due]
    return x, (O[x] if x < len(O) else float("nan")), KIND_TIME


def _exit_trail(O, H, L, TR, NT, e: int, side: int, dist: float, maxhold: int,
                ratchet: bool = True) -> Tuple[int, float, int]:
    """M2. `dist` = y*sigma_5 (trailing distance as a return from the best price since entry). See R8.
    `ratchet=False` is the alternative reading S3 of the sensitivity stage only (adverse extreme always first:
    a bar's own favourable extreme never raises the stop that the same bar then hits)."""
    best = O[e]
    due = e + maxhold
    j = e
    if side > 0:
        k = 1.0 - dist
        while j < due:
            if TR[j]:
                o = O[j]
                if o <= best * k:                               # a) opens through the stop
                    return j, o, KIND_GAP
                if o > best:
                    best = o
                lo = L[j]
                s0 = best * k
                if lo <= s0:                                    # b) low first: the stop in force at the open
                    return j, s0, KIND_STOP
                hi = H[j]
                if hi > best:
                    s1 = hi * k
                    if ratchet and lo <= s1:                    # c) high first, then the retrace
                        return j, s1, KIND_RATCHET
                    best = hi
            j += 1
    else:
        k = 1.0 + dist
        while j < due:
            if TR[j]:
                o = O[j]
                if o >= best * k:
                    return j, o, KIND_GAP
                if o < best:
                    best = o
                hi = H[j]
                s0 = best * k
                if hi >= s0:
                    return j, s0, KIND_STOP
                lo = L[j]
                if lo < best:
                    s1 = lo * k
                    if ratchet and hi >= s1:
                        return j, s1, KIND_RATCHET
                    best = lo
            j += 1
    x = NT[due]
    return x, (O[x] if x < len(O) else float("nan")), KIND_TIME


class Trades:
    __slots__ = ("sig", "entry", "exit", "side", "exit_px", "kind", "gross", "deferred_exits",
                 "skipped_untradeable_entry", "dropped_window_end")

    def __init__(self, sig, entry, exit_, side, exit_px, kind, gross, deferred=0, skipped=0, dropped=0):
        self.sig = np.asarray(sig, dtype=np.int64)
        self.entry = np.asarray(entry, dtype=np.int64)
        self.exit = np.asarray(exit_, dtype=np.int64)
        self.side = np.asarray(side, dtype=np.int8)
        self.exit_px = np.asarray(exit_px, dtype=np.float64)
        self.kind = np.asarray(kind, dtype=np.int8)
        self.gross = np.asarray(gross, dtype=np.float64)
        self.deferred_exits = int(deferred)
        self.skipped_untradeable_entry = int(skipped)
        self.dropped_window_end = int(dropped)

    def __len__(self) -> int:
        return len(self.sig)

    @property
    def hold_bars(self) -> np.ndarray:
        """Bars from the entry open to the exit: exits at an open (time, gap) = exit - entry; exits inside a
        bar are counted to the end of that bar (exit - entry + 1). Always >= 1."""
        intrabar = (self.kind == KIND_STOP) | (self.kind == KIND_TP) | (self.kind == KIND_RATCHET)
        return (self.exit - self.entry + intrabar).astype(np.int64)


def valid_signal_mask(bars: Bars, side: np.ndarray, maxhold: int, w0: int, w1: int,
                      extra: Optional[np.ndarray] = None) -> Tuple[np.ndarray, int]:
    """Signals that may open a trade: entry bar s+1 inside [w0, w1 - maxhold] (R11) and tradeable (R4).
    Returns (mask, number of otherwise-valid signals lost because the entry bar is not tradeable)."""
    n = bars.n
    cand = side != 0
    if extra is not None:
        cand &= extra
    in_range = np.zeros(n, dtype=bool)
    lo, hi = max(w0 - 1, 0), w1 - maxhold - 1
    if hi >= lo:
        in_range[lo:hi + 1] = True
    cand &= in_range
    tr_next = np.zeros(n, dtype=bool)
    tr_next[:-1] = bars.tradeable[1:]
    skipped = int((cand & ~tr_next).sum())
    return cand & tr_next, skipped


def simulate(bars: Bars, f: Formula, side: np.ndarray, sigma_exit: Optional[np.ndarray] = None,
             w0: int = 0, w1: Optional[int] = None, *, reentry_at_exit: bool = False,
             trail_ratchet: bool = True) -> Trades:
    """One position at a time. `side[s]` in {-1, 0, +1} is the signal at the CLOSE of bar s; the fill is the
    OPEN of bar s+1. `sigma_exit[s]` (M2, M3) is sigma_5 at the signal bar. Entries only in [w0, w1].

    The two keyword switches are the alternative readings S2 / S3 of the sensitivity stage; the registered
    run never sets them."""
    n = bars.n
    if w1 is None:
        w1 = n - 1
    maxhold = f.maxhold
    extra = None
    if f.family in ("M2", "M3"):
        if sigma_exit is None:
            raise ValueError("M2 / M3 need sigma_5 at the signal bar")
        with np.errstate(invalid="ignore"):
            extra = np.isfinite(sigma_exit) & (sigma_exit > 0)
    valid, skipped = valid_signal_mask(bars, side, maxhold, w0, w1, extra)
    idx = np.where(valid, np.arange(n, dtype=np.int64), n)
    nxt = np.minimum.accumulate(idx[::-1])[::-1].tolist() if n else []
    nxt.append(n)
    LL = bars.lists()
    O, NT = LL["o"], LL["nt"]
    S: List[int] = []
    X: List[int] = []
    PX: List[float] = []
    KD: List[int] = []
    deferred = dropped = 0
    free = 0                                                    # first signal bar that may be acted on (R3)
    if f.family == "M1":
        h = f.h
        while True:
            s = nxt[free]
            if s >= n:
                break
            due = s + 1 + h
            x = NT[due]
            if x > w1:                                          # exit pushed past the window by missing bars:
                dropped += 1                                    # the position never closes inside it -> dropped,
                break                                           # and nothing can be entered behind it
            if x != due:
                deferred += 1
            S.append(s)
            X.append(x)
            free = x - 1 if reentry_at_exit else x
        sig = np.asarray(S, dtype=np.int64)
        ex = np.asarray(X, dtype=np.int64)
        px = bars.o[ex] if len(ex) else np.empty(0)
        kind = np.zeros(len(sig), dtype=np.int8)
    else:
        H, L, TR = LL["h"], LL["l"], LL["tr"]
        trail = f.family == "M2"
        while True:
            s = nxt[free]
            if s >= n:
                break
            e = s + 1
            sd = int(side[s])
            sg = float(sigma_exit[s])
            if trail:
                j, p, kd = _exit_trail(O, H, L, TR, NT, e, sd, f.y * sg, maxhold, trail_ratchet)
            else:
                j, p, kd = _exit_tp_sl(O, H, L, TR, NT, e, sd, f.a * sg, f.b * sg, maxhold)
            if j > w1:
                dropped += 1
                break
            if kd == KIND_TIME and j != e + maxhold:
                deferred += 1
            S.append(s)
            X.append(j)
            PX.append(p)
            KD.append(kd)
            free = j - 1 if (reentry_at_exit and kd in (KIND_TIME, KIND_GAP)) else j
        sig = np.asarray(S, dtype=np.int64)
        ex = np.asarray(X, dtype=np.int64)
        px = np.asarray(PX, dtype=np.float64)
        kind = np.asarray(KD, dtype=np.int8)
    entry = sig + 1
    sd_arr = side[sig].astype(np.int8) if len(sig) else np.empty(0, dtype=np.int8)
    gross = sd_arr * (px / bars.o[entry] - 1.0) if len(sig) else np.empty(0)
    return Trades(sig, entry, ex, sd_arr, px, kind, gross, deferred, skipped, dropped)


def fade_gross(bars: Bars, f: Formula, tr: Trades, sigma_exit: np.ndarray) -> np.ndarray:
    """M2 / M3 only: gross return of taking the OPPOSITE side at each actual entry, with the same exit rule,
    each simulated on its own (no sequencing). With a pessimistic exit rule a coin-flip direction loses on
    average; (follow + fade)/2 measures that drag and (follow - fade)/2 the directional content."""
    LL = bars.lists()
    O, H, L, TR, NT = LL["o"], LL["h"], LL["l"], LL["tr"], LL["nt"]
    out = np.full(len(tr), np.nan)
    trail = f.family == "M2"
    for i in range(len(tr)):
        s = int(tr.sig[i])
        e = s + 1
        sd = -int(tr.side[i])
        sg = float(sigma_exit[s])
        if trail:
            j, p, _ = _exit_trail(O, H, L, TR, NT, e, sd, f.y * sg, f.maxhold)
        else:
            j, p, _ = _exit_tp_sl(O, H, L, TR, NT, e, sd, f.a * sg, f.b * sg, f.maxhold)
        if j < bars.n:
            out[i] = sd * (p / O[e] - 1.0)
    return out


def random_entry_gross(bars: Bars, tr: Trades, w0: int, w1: int, rng: np.random.Generator) -> np.ndarray:
    """Sanity control: for every actual trade, a trade of the SAME side and the SAME holding time (in bars)
    entered at the open of a uniformly random tradeable bar of the window and closed at the open `hold` bars
    later (next tradeable open if that bar is missing). Its gross mean must be ~ 0 and its net mean ~ minus
    the round-trip cost; anything else is a bug in the price / cost accounting."""
    n_tr = len(tr)
    if n_tr == 0:
        return np.empty(0)
    hold = tr.hold_bars
    cand = np.flatnonzero(bars.tradeable[w0:w1 + 1]) + w0
    e = rng.choice(cand, size=n_tr)
    nt = bars.next_tradeable
    for _ in range(200):
        x = nt[np.minimum(e + hold, bars.n)]
        bad = x > w1
        if not bad.any():
            break
        e[bad] = rng.choice(cand, size=int(bad.sum()))
    else:
        raise RuntimeError("random-entry control could not place every trade inside the window")
    return tr.side * (bars.o[x] / bars.o[e] - 1.0)


# ---- pre-registration §4: statistics ----------------------------------------------------------------
def cluster_t(values: np.ndarray, cluster: np.ndarray) -> Tuple[float, int]:
    """t-statistic of mean(values) with cluster-robust (CR1) variance, clusters = `cluster` ids (R15).
    Returns (t, number of clusters). NaN with fewer than 2 clusters or zero variance."""
    v = np.asarray(values, dtype=np.float64)
    n = len(v)
    if n == 0:
        return float("nan"), 0
    _, inv = np.unique(np.asarray(cluster), return_inverse=True)
    g = int(inv.max()) + 1
    if g < 2:
        return float("nan"), g
    m = v.mean()
    sums = np.bincount(inv, weights=v - m, minlength=g)
    var = g / (g - 1.0) * float(np.sum(sums * sums)) / (n * n)
    if not var > 0:
        return float("nan"), g
    return float(m / math.sqrt(var)), g


def benjamini_hochberg(p: Sequence[float], q: float) -> np.ndarray:
    """Step-up BH: reject the k smallest p, k = max{i : p_(i) <= q*i/m}. NaN counts as p = 1 and stays in m."""
    pv = np.asarray(p, dtype=np.float64).copy()
    pv[~np.isfinite(pv)] = 1.0
    m = len(pv)
    rej = np.zeros(m, dtype=bool)
    if m == 0:
        return rej
    order = np.argsort(pv, kind="stable")
    below = pv[order] <= q * np.arange(1, m + 1) / m
    if below.any():
        rej[order[: int(np.flatnonzero(below).max()) + 1]] = True
    return rej


def t_pvalues(t: float, clusters: int) -> Tuple[float, float]:
    """(one-sided p for H1 mean > 0, two-sided p), Student-t with clusters - 1 degrees of freedom (R16)."""
    if not math.isfinite(t) or clusters < 2:
        return 1.0, 1.0
    from scipy import stats as _st

    dof = clusters - 1
    return float(_st.t.sf(t, dof)), float(2.0 * _st.t.sf(abs(t), dof))


def series_stats(ret: np.ndarray, day: np.ndarray, n_days: int) -> dict:
    """Statistics of one per-trade return series (fractions, not bp). `day` = UTC day index of the entry."""
    n = len(ret)
    if n == 0:
        return {"mean_bp": float("nan"), "median_bp": float("nan"), "win_rate": float("nan"), "total": 0.0,
                "total_compounded": 0.0, "sharpe_daily": float("nan"), "sharpe_ann": float("nan"),
                "t": float("nan"), "std_bp": float("nan")}
    daily = np.bincount(day, weights=ret, minlength=n_days)
    sd = float(daily.std(ddof=1)) if n_days > 1 else 0.0
    sh = float(daily.mean() / sd) if sd > 0 else float("nan")
    t, _ = cluster_t(ret, day)
    with np.errstate(invalid="ignore", over="ignore"):
        logs = np.log1p(np.maximum(ret, -0.999999))
    return {"mean_bp": float(ret.mean() * 1e4), "median_bp": float(np.median(ret) * 1e4),
            "win_rate": float((ret > 0).mean()), "total": float(ret.sum()),
            "total_compounded": float(math.expm1(float(logs.sum()))),
            "sharpe_daily": sh, "sharpe_ann": sh * math.sqrt(365.0) if math.isfinite(sh) else float("nan"),
            "t": t, "std_bp": float(ret.std(ddof=1) * 1e4) if n > 1 else float("nan")}


def pair_row(sym: str, f: Formula, tr: Trades, w0: int, n_days: int, window: str) -> dict:
    """One ledger row: every §4 statistic at the base cost, at zero cost and at the maker bound."""
    c_base = base_cost_side_bp(sym)
    n = len(tr)
    day = ((tr.entry - w0) // DAY_MIN).astype(np.int64) if n else np.empty(0, dtype=np.int64)
    g = tr.gross
    row = {"pair_id": f"{sym}|{f.fid}", "window": window, "symbol": sym, "family": f.family, "formula": f.fid,
           "k": f.k, "x": f.x, "h": f.h, "N": f.N, "y": f.y, "a": f.a, "b": f.b, "max_hold_min": f.maxhold,
           "cost_side_bp": c_base, "round_trip_cost_bp": 2 * c_base,
           "n_trades": n, "n_long": int((tr.side > 0).sum()), "n_short": int((tr.side < 0).sum()),
           "n_days_window": n_days, "n_days_with_trades": int(len(np.unique(day))) if n else 0,
           "trades_per_day": n / n_days if n_days else float("nan"),
           "mean_hold_bars": float(tr.hold_bars.mean()) if n else float("nan"),
           "exits_time": int((tr.kind == KIND_TIME).sum()), "exits_stop": int((tr.kind == KIND_STOP).sum()),
           "exits_ratchet_stop": int((tr.kind == KIND_RATCHET).sum()),
           "exits_gap_stop": int((tr.kind == KIND_GAP).sum()), "exits_take_profit": int((tr.kind == KIND_TP).sum()),
           "exits_deferred_missing_bar": tr.deferred_exits,
           "signals_lost_untradeable_entry": tr.skipped_untradeable_entry,
           "trades_dropped_window_end": tr.dropped_window_end}
    for tag, cost in (("gross", 0.0), ("net", c_base), ("maker", MAKER_BOUND_BP)):
        st = series_stats(g - 2.0 * cost * 1e-4, day, n_days)
        for k, v in st.items():
            row[f"{k}_{tag}"] = v
    row["breakeven_cost_side_bp"] = row["mean_bp_gross"] / 2.0 if n else float("nan")
    p1, p2 = t_pvalues(row["t_net"], row["n_days_with_trades"])
    row["p_one_sided_net"], row["p_two_sided_net"] = p1, p2
    return row


def apply_pass_rule(rows: List[dict], t_min: float, with_bh: bool) -> None:
    """Design: mean net > 0 AND t >= 3.0 AND BH(q = 10 %, all pairs) rejects under both p definitions.
    Holdout: mean net > 0 AND t >= 2.0. Adds the flags to every row in place."""
    if with_bh:
        r1 = benjamini_hochberg([r["p_one_sided_net"] for r in rows], BH_Q)
        r2 = benjamini_hochberg([r["p_two_sided_net"] for r in rows], BH_Q)
    for i, r in enumerate(rows):
        pos = bool(r["n_trades"] > 0 and r["mean_bp_net"] > 0)
        tt = bool(math.isfinite(r["t_net"]) and r["t_net"] >= t_min)
        r["mean_net_positive"] = pos
        r[f"t_net_ge_{t_min:g}"] = tt
        if with_bh:
            r["bh_reject_one_sided"] = bool(r1[i])
            r["bh_reject_two_sided"] = bool(r2[i])
            r["design_pass"] = bool(pos and tt and r1[i] and r2[i])
        else:
            r["holdout_pass"] = bool(pos and tt)


# ---- running a window -------------------------------------------------------------------------------
def window_spec(window: str) -> Tuple[str, str, str]:
    """(first month to load, first month scored, last month)."""
    if window == "design":
        return DESIGN_FIRST_MONTH, DESIGN_FIRST_MONTH, DESIGN_LAST_MONTH
    if window == "holdout":
        return HOLDOUT_WARMUP_MONTH, HOLDOUT_FIRST_MONTH, HOLDOUT_LAST_MONTH
    raise ValueError(window)


def run_window(window: str, pair_filter: Optional[set] = None, with_controls: bool = True
               ) -> Tuple[List[dict], List[dict], List[dict]]:
    """Simulate every (or the selected) formula-symbol pair on one window, one symbol at a time.
    Returns (ledger rows, control rows, data reports)."""
    load_first, score_first, last = window_spec(window)
    fl = formulas()
    rows: List[dict] = []
    ctrl: List[dict] = []
    reports: List[dict] = []
    for si, sym in enumerate(SYMBOLS):
        todo = [f for f in fl if pair_filter is None or f"{sym}|{f.fid}" in pair_filter]
        if not todo:
            continue
        t_load = time.time()
        bars, rep = load_bars(sym, load_first, last)
        w0 = int((month_bounds_ms(score_first)[0] - bars.t0_ms) // MIN_MS)
        w1 = bars.n - 1
        n_days = (w1 - w0 + 1) // DAY_MIN
        rep.update(window=window, scored_from_utc=iso_minute(bars.t0_ms + w0 * MIN_MS), scored_days=n_days,
                   scored_bars=int(w1 - w0 + 1), scored_bars_tradeable=int(bars.tradeable[w0:].sum()),
                   scored_bars_missing=int((~bars.present[w0:]).sum()),
                   scored_bars_zero_volume=int((bars.present[w0:] & ~bars.tradeable[w0:]).sum()))
        cache = SignalCache(bars)
        for k in (1, 5, 15):
            sg = cache.sigma(k)
            rep[f"scored_bars_sigma{k}_defined"] = int(np.isfinite(sg[w0:]).sum())
        reports.append(rep)
        log(f"[{window}] {sym}: {bars.n} bars loaded in {time.time() - t_load:.1f}s; present {rep['bars_present']}, "
            f"missing {rep['bars_missing']}, zero-volume {rep['zero_volume_bars']}")
        for f in todo:
            t1 = time.time()
            side, sg_exit = cache.signal(f)
            tr = simulate(bars, f, side, sg_exit, w0, w1)
            row = pair_row(sym, f, tr, w0, n_days, window)
            rows.append(row)
            if with_controls:
                fi = [g.fid for g in fl].index(f.fid)
                rng = np.random.default_rng([CONTROL_SEED, 0 if window == "design" else 1, si, fi])
                cg = random_entry_gross(bars, tr, w0, w1, rng)
                c = {"pair_id": row["pair_id"], "window": window, "symbol": sym, "family": f.family,
                     "formula": f.fid, "n_trades": len(tr), "round_trip_cost_bp": row["round_trip_cost_bp"],
                     "random_entry_mean_gross_bp": float(cg.mean() * 1e4) if len(cg) else float("nan"),
                     "random_entry_se_bp": float(cg.std(ddof=1) / math.sqrt(len(cg)) * 1e4) if len(cg) > 1 else float("nan"),
                     "random_entry_mean_net_bp": float(cg.mean() * 1e4 - row["round_trip_cost_bp"]) if len(cg) else float("nan"),
                     "actual_mean_gross_bp": row["mean_bp_gross"]}
                c["random_entry_z"] = (c["random_entry_mean_gross_bp"] / c["random_entry_se_bp"]
                                       if len(cg) > 1 and c["random_entry_se_bp"] > 0 else float("nan"))
                if f.family in ("M2", "M3") and len(tr):
                    fg = fade_gross(bars, f, tr, sg_exit)
                    fm = float(np.nanmean(fg) * 1e4)
                    c["fade_mean_gross_bp"] = fm
                    c["exit_rule_drag_bp"] = (row["mean_bp_gross"] + fm) / 2.0
                    c["directional_edge_bp"] = (row["mean_bp_gross"] - fm) / 2.0
                else:
                    c["fade_mean_gross_bp"] = -row["mean_bp_gross"] if len(tr) else float("nan")
                    c["exit_rule_drag_bp"] = 0.0 if len(tr) else float("nan")
                    c["directional_edge_bp"] = row["mean_bp_gross"]
                ctrl.append(c)
            log(f"  {row['pair_id']:<24} trades {len(tr):>7}  gross {row['mean_bp_gross']:+8.3f} bp  "
                f"net {row['mean_bp_net']:+8.3f} bp  t_net {row['t_net']:+7.2f}  ({time.time() - t1:.1f}s)")
            del tr, side
        bars.free()
        del cache, bars
        gc.collect()
    return rows, ctrl, reports


# ---- output helpers ---------------------------------------------------------------------------------
def _fmt(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        return f"{v:.10g}"
    return str(v)


def render_csv(rows: List[dict], columns: Optional[List[str]] = None) -> str:
    cols = columns or (list(rows[0].keys()) if rows else [])
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow([_fmt(r.get(c, "")) for c in cols])
    return buf.getvalue()


def write_csv(path: Path, rows: List[dict], columns: Optional[List[str]] = None) -> None:
    atomic_write_text(path, render_csv(rows, columns))


def _json_safe(o):
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, (np.floating,)):
        return _json_safe(float(o))
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def write_json(path: Path, obj) -> None:
    atomic_write_text(path, json.dumps(_json_safe(obj), indent=1, allow_nan=False))


def run_meta() -> dict:
    import platform

    import scipy

    return {"written_utc": utc_now(), "prereg_sha256": check_prereg(),
            "code_sha256": sha256_file(Path(__file__).resolve()), "python": platform.python_version(),
            "numpy": np.__version__, "scipy": scipy.__version__,
            "symbols": list(SYMBOLS), "formulas_per_symbol": len(formulas()),
            "cost_side_bp": {s: base_cost_side_bp(s) for s in SYMBOLS}, "maker_bound_side_bp": MAKER_BOUND_BP,
            "sigma_window": SIGMA_WINDOW, "bh_q": BH_Q, "design_t_min": DESIGN_T_MIN, "holdout_t_min": HOLDOUT_T_MIN,
            "control_seed": CONTROL_SEED}


# ---- stages -----------------------------------------------------------------------------------------
def stage_design(force: bool = False) -> int:
    check_prereg()
    if (RUN_DIR / "DESIGN_PASSERS.json").exists() and not force:
        raise SystemExit("REFUSED: DESIGN_PASSERS.json exists - the design ledger is frozen. Re-running the "
                         "design after the freeze needs --force-redesign and is recorded in the ledger meta.")
    rows, ctrl, reports = run_window("design")
    if len(rows) != 129:
        raise SystemExit(f"expected 129 pairs, got {len(rows)}")
    apply_pass_rule(rows, DESIGN_T_MIN, with_bh=True)
    meta = run_meta()
    meta.update(window="design", window_days="2021-01-01..2023-12-31", redesign_after_freeze=bool(force),
                holdout_months_parsed=0)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(RUN_DIR / "design_ledger.csv", rows)
    write_json(RUN_DIR / "design_ledger.json", {"meta": meta, "rows": rows})
    write_csv(RUN_DIR / "control_design.csv", ctrl)
    write_json(RUN_DIR / "data_report_design.json", {"meta": meta, "symbols": reports})
    log(f"design ledger written: {len(rows)} pairs; mean gross > 0: {sum(r['mean_bp_gross'] > 0 for r in rows)}; "
        f"mean net > 0: {sum(r['mean_net_positive'] for r in rows)}; design pass: {sum(r['design_pass'] for r in rows)}")
    return 0


def stage_passers() -> int:
    """Mechanical: re-derive the pass flags from the ledger's own numbers, then freeze the list."""
    check_prereg()
    ledger = json.loads((RUN_DIR / "design_ledger.json").read_text())
    rows = ledger["rows"]
    if len(rows) != 129:
        raise SystemExit(f"design ledger has {len(rows)} rows, expected 129")
    chk = [dict(r) for r in rows]
    for r in chk:
        for k in ("t_net", "mean_bp_net"):
            if r[k] is None:
                r[k] = float("nan")
    apply_pass_rule(chk, DESIGN_T_MIN, with_bh=True)
    for a, b in zip(rows, chk):
        if bool(a["design_pass"]) != bool(b["design_pass"]):
            raise SystemExit(f"pass flag mismatch for {a['pair_id']}: ledger {a['design_pass']} vs recomputed {b['design_pass']}")
    passers = [{"pair_id": r["pair_id"], "symbol": r["symbol"], "formula": r["formula"], "n_trades": r["n_trades"],
                "mean_bp_net": r["mean_bp_net"], "mean_bp_gross": r["mean_bp_gross"], "t_net": r["t_net"],
                "p_one_sided_net": r["p_one_sided_net"], "p_two_sided_net": r["p_two_sided_net"]}
               for r in chk if r["design_pass"]]
    csv_sha = sha256_file(RUN_DIR / "design_ledger.csv")
    payload = {"pair_ids": sorted(p["pair_id"] for p in passers), "design_ledger_csv_sha256": csv_sha}
    out = {"written_utc": utc_now(), "prereg_sha256": PREREG_SHA256,
           "code_sha256": sha256_file(Path(__file__).resolve()),
           "design_ledger_csv_sha256": csv_sha,
           "design_ledger_json_sha256": sha256_file(RUN_DIR / "design_ledger.json"),
           "rule": ("mean net per trade > 0 AND day-clustered t >= 3.0 AND Benjamini-Hochberg (q = 0.10, m = 129) "
                    "rejects under both the one-sided and the two-sided p-value"),
           "n_pairs": len(chk),
           "n_mean_gross_positive": sum(1 for r in chk if r["mean_bp_gross"] is not None and r["mean_bp_gross"] > 0),
           "n_mean_net_positive": sum(1 for r in chk if r["mean_net_positive"]),
           "n_t_ge_3": sum(1 for r in chk if r["t_net_ge_3"]),
           "n_bh_reject_one_sided": sum(1 for r in chk if r["bh_reject_one_sided"]),
           "n_bh_reject_two_sided": sum(1 for r in chk if r["bh_reject_two_sided"]),
           "n_passers": len(passers), "passers": passers,
           "payload_sha256": sha256_bytes(json.dumps(payload, sort_keys=True).encode())}
    p = RUN_DIR / "DESIGN_PASSERS.json"
    write_json(p, out)
    h = sha256_file(p)
    atomic_write_text(RUN_DIR / "DESIGN_PASSERS.sha256", f"{h}  DESIGN_PASSERS.json\n")
    log(f"DESIGN_PASSERS.json written: {len(passers)} passer(s); sha256 {h}")
    return 0


def stage_holdout() -> int:
    """One shot, design passers only."""
    check_prereg()
    frozen = require_design_frozen()
    ids = {p["pair_id"] for p in frozen["passers"]}
    meta = run_meta()
    meta.update(window="holdout", window_days="2024-01-01..2026-10-31", passers=sorted(ids),
                design_passers_sha256=sha256_file(RUN_DIR / "DESIGN_PASSERS.json"))
    rows: List[dict] = []
    if ids:
        rows, _, _ = run_window("holdout", pair_filter=ids, with_controls=False)
        apply_pass_rule(rows, HOLDOUT_T_MIN, with_bh=False)
    cols = list(rows[0].keys()) if rows else ["pair_id", "window", "symbol", "family", "formula", "n_trades",
                                              "mean_bp_gross", "mean_bp_net", "t_net", "holdout_pass"]
    write_csv(RUN_DIR / "holdout_passers.csv", rows, cols)
    write_json(RUN_DIR / "holdout_passers.json", {"meta": meta, "rows": rows,
                                                  "note": "empty: no pair passed the design rule" if not ids else ""})
    log(f"holdout (passers only): {len(rows)} pair(s); PASS {sum(r['holdout_pass'] for r in rows)}")
    return 0


def _descriptive_rows() -> Tuple[List[dict], List[dict], List[dict]]:
    rows, ctrl, reports = run_window("holdout")
    apply_pass_rule(rows, HOLDOUT_T_MIN, with_bh=False)
    for r in rows:
        r["descriptive_only_meets_holdout_numbers"] = r.pop("holdout_pass")
    return rows, ctrl, reports


def stage_descriptive() -> int:
    """Holdout statistics of ALL pairs. Descriptive only: nothing here can promote a formula."""
    check_prereg()
    require_design_frozen()
    rows, ctrl, reports = _descriptive_rows()
    meta = run_meta()
    meta.update(window="holdout", window_days="2024-01-01..2026-10-31",
                status="DESCRIPTIVE - not evidence; the pre-registered holdout read is holdout_passers.csv")
    write_csv(RUN_DIR / "holdout_descriptive.csv", rows)
    write_json(RUN_DIR / "holdout_descriptive.json", {"meta": meta, "rows": rows})
    write_csv(RUN_DIR / "control_holdout_descriptive.csv", ctrl)
    write_json(RUN_DIR / "data_report_holdout.json", {"meta": meta, "symbols": reports})
    log(f"holdout descriptive written: {len(rows)} pairs")
    return 0


SENSITIVITY_READINGS = (
    ("R0_registered", "the registered readings R1-R16 (must equal design_ledger.csv)"),
    ("S1_sigma_excludes_signal_bar", "sigma_k from the 1,440 returns ending at t-1, so a burst does not inflate its own threshold"),
    ("S2_reentry_at_exit_print", "a signal at the close just before an exit open may be filled at that same open"),
    ("S3_m2_adverse_extreme_first", "M2 only: inside a bar the adverse extreme always comes first (no same-bar ratchet stop)"),
)


def stage_sensitivity() -> int:
    """DESIGN window only, and only after the freeze: the same pairs under the alternative reading of each
    ambiguous sentence. It shows whether the verdict depends on the reading chosen. It is NOT part of the
    decision rule and cannot promote a formula."""
    check_prereg()
    require_design_frozen()
    ledger = {r["pair_id"]: r for r in json.loads((RUN_DIR / "design_ledger.json").read_text())["rows"]}
    fl = formulas()
    rows: List[dict] = []
    carried: List[dict] = []
    for sym in SYMBOLS:
        bars, _ = load_bars(sym, DESIGN_FIRST_MONTH, DESIGN_LAST_MONTH)
        w0, w1 = 0, bars.n - 1
        n_days = bars.n // DAY_MIN
        c0, c1 = SignalCache(bars), SignalCache(bars, sigma_lag=1)
        for f in fl:
            variants = [("R0_registered", c0, {}), ("S1_sigma_excludes_signal_bar", c1, {}),
                        ("S2_reentry_at_exit_print", c0, {"reentry_at_exit": True})]
            if f.family == "M2":
                variants.append(("S3_m2_adverse_extreme_first", c0, {"trail_ratchet": False}))
            for name, cache, kw in variants:
                side, sg = cache.signal(f)
                tr = simulate(bars, f, side, sg, w0, w1, **kw)
                r = pair_row(sym, f, tr, w0, n_days, "design")
                if name == "R0_registered":
                    led = ledger[r["pair_id"]]
                    if r["n_trades"] != led["n_trades"] or abs(r["mean_bp_gross"] - led["mean_bp_gross"]) > 1e-9:
                        raise SystemExit(f"sensitivity baseline differs from the frozen ledger for {r['pair_id']}")
                    far = tr.hold_bars > f.maxhold + DAY_MIN          # exit pushed across an archive hole >= 1 day
                    if far.any():
                        carried.append({"pair_id": r["pair_id"], "n_carried": int(far.sum()),
                                        "mean_bp_gross_all": r["mean_bp_gross"],
                                        "mean_bp_gross_without_them": float(tr.gross[~far].mean() * 1e4),
                                        "largest_abs_carried_trade_bp": float(np.abs(tr.gross[far]).max() * 1e4)})
                rows.append({"reading": name, "pair_id": r["pair_id"], "symbol": sym, "family": f.family,
                             "formula": f.fid, "n_trades": r["n_trades"], "mean_bp_gross": r["mean_bp_gross"],
                             "t_gross": r["t_gross"], "mean_bp_net": r["mean_bp_net"], "t_net": r["t_net"],
                             "mean_bp_maker": r["mean_bp_maker"], "win_rate_net": r["win_rate_net"]})
            del side
        bars.free()
        del c0, c1, bars
        gc.collect()
        log(f"[sensitivity] {sym} done")
    base = {r["pair_id"]: r for r in rows if r["reading"] == "R0_registered"}
    summary = []
    for name, text in SENSITIVITY_READINGS:
        rr = [r for r in rows if r["reading"] == name]
        best = max(rr, key=lambda r: r["mean_bp_net"])
        bestg = max(rr, key=lambda r: r["mean_bp_gross"])
        d = [r["mean_bp_gross"] - base[r["pair_id"]]["mean_bp_gross"] for r in rr]
        summary.append({"reading": name, "what": text, "pairs": len(rr), "trades": int(sum(r["n_trades"] for r in rr)),
                        "trades_registered_same_pairs": int(sum(base[r["pair_id"]]["n_trades"] for r in rr)),
                        "mean_gross_positive": sum(1 for r in rr if r["mean_bp_gross"] > 0),
                        "mean_net_positive": sum(1 for r in rr if r["mean_bp_net"] > 0),
                        "mean_maker_positive": sum(1 for r in rr if r["mean_bp_maker"] > 0),
                        "t_net_ge_3": sum(1 for r in rr if r["t_net"] >= DESIGN_T_MIN),
                        "median_gross_bp": float(np.median([r["mean_bp_gross"] for r in rr])),
                        "best_net_pair": best["pair_id"], "best_net_bp": best["mean_bp_net"],
                        "best_gross_pair": bestg["pair_id"], "best_gross_bp": bestg["mean_bp_gross"],
                        "largest_gross_change_vs_registered_bp": float(max(d, key=abs)),
                        "mean_gross_change_vs_registered_bp": float(np.mean(d))})
    meta = run_meta()
    meta.update(window="design", status="SENSITIVITY - alternative readings, not part of the decision rule")
    write_csv(RUN_DIR / "sensitivity_design.csv", rows)
    write_json(RUN_DIR / "sensitivity_design.json", {"meta": meta, "summary": summary, "trades_carried_across_archive_holes": carried})
    for s in summary:
        log(f"  {s['reading']:<32} pairs {s['pairs']:>3}  gross>0 {s['mean_gross_positive']:>3}  net>0 {s['mean_net_positive']}  "
            f"best net {s['best_net_bp']:+.3f} bp ({s['best_net_pair']})")
    return 0


def stage_reproduce() -> int:
    """Recompute the frozen tables with the code as it is now and compare them byte for byte."""
    check_prereg()
    require_design_frozen()
    rows, ctrl, _ = run_window("design")
    apply_pass_rule(rows, DESIGN_T_MIN, with_bh=True)
    checks = [("design_ledger.csv", render_csv(rows)), ("control_design.csv", render_csv(ctrl))]
    if (RUN_DIR / "holdout_descriptive.csv").exists():
        hrows, hctrl, _ = _descriptive_rows()
        checks += [("holdout_descriptive.csv", render_csv(hrows)), ("control_holdout_descriptive.csv", render_csv(hctrl))]
    out = {"written_utc": utc_now(), "code_sha256": sha256_file(Path(__file__).resolve()), "files": {}}
    ok = True
    for name, text in checks:
        a, b = sha256_bytes(text.encode("utf-8")), sha256_file(RUN_DIR / name)
        out["files"][name] = {"sha256_on_disk": b, "sha256_recomputed": a, "identical": a == b}
        ok = ok and a == b
        log(f"reproduce {name}: {'IDENTICAL' if a == b else 'DIFFERENT'}")
    out["all_identical"] = ok
    write_json(RUN_DIR / "REPRODUCTION.json", out)
    return 0 if ok else 1


# ---- report -----------------------------------------------------------------------------------------
def _read_csv(path: Path) -> List[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _f(v) -> float:
    if v is None or v == "":
        return float("nan")
    return float(v)


def _md_table(header: List[str], rows: List[List[str]], left: int = 1) -> List[str]:
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join(" :--- " if i < left else " ---: " for i in range(len(header))) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def _agg(rows: List[dict]) -> dict:
    g = np.array([_f(r["mean_bp_gross"]) for r in rows])
    n = np.array([_f(r["mean_bp_net"]) for r in rows])
    mk = np.array([_f(r["mean_bp_maker"]) for r in rows])
    tg = np.array([_f(r["t_gross"]) for r in rows])
    be = np.array([_f(r["breakeven_cost_side_bp"]) for r in rows])
    return {"pairs": len(rows), "trades": int(sum(r["n_trades"] for r in rows)),
            "gross_pos": int((g > 0).sum()), "net_pos": int((n > 0).sum()), "maker_pos": int((mk > 0).sum()),
            "med_gross": float(np.median(g)), "min_gross": float(g.min()), "max_gross": float(g.max()),
            "med_abs_gross": float(np.median(np.abs(g))),
            "med_net": float(np.median(n)), "max_net": float(n.max()), "min_net": float(n.min()),
            "med_maker": float(np.median(mk)), "max_maker": float(mk.max()),
            "med_be": float(np.median(be)), "max_be": float(be.max()),
            "tg_ge3": int((tg >= 3).sum()), "tg_ge2": int((tg >= 2).sum()), "tg_le_m3": int((tg <= -3).sum()),
            "tg_le_m2": int((tg <= -2).sum())}


def _pair_table(rows: List[dict], with_hold: bool) -> List[str]:
    head = ["Pair", "Trades", "Win %", "Gross bp", "Net bp", "Break-even bp/side", "t (net)", "Sharpe (daily, ann.)",
            "t (gross)"] + (["Hold min"] if with_hold else [])
    body = []
    for r in rows:
        line = [f"{r['symbol'][:3]} {r['formula']}", f"{r['n_trades']:,}", f"{100 * _f(r['win_rate_net']):.1f}",
                f"{_f(r['mean_bp_gross']):+.2f}", f"{_f(r['mean_bp_net']):+.2f}", f"{_f(r['breakeven_cost_side_bp']):+.2f}",
                f"{_f(r['t_net']):+.1f}", f"{_f(r['sharpe_ann_net']):+.1f}", f"{_f(r['t_gross']):+.1f}"]
        if with_hold:
            line.append(f"{_f(r['mean_hold_bars']):.1f}")
        body.append(line)
    return _md_table(head, body)


def _agg_table(groups: List[Tuple[str, List[dict], str]]) -> List[str]:
    head = ["Group", "Pairs", "Trades", "Gross > 0", "Net > 0", "Median gross bp", "Median break-even bp/side",
            "Charged bp/side", "Best net bp", "Gross t >= 3", "Gross t <= -3"]
    body = []
    for name, rr, charged in groups:
        a = _agg(rr)
        body.append([name, str(a["pairs"]), f"{a['trades']:,}", f"{a['gross_pos']} ({100 * a['gross_pos'] / a['pairs']:.0f} %)",
                     f"{a['net_pos']} ({100 * a['net_pos'] / a['pairs']:.0f} %)", f"{a['med_gross']:+.2f}",
                     f"{a['med_be']:+.2f}", charged, f"{a['max_net']:+.2f}", str(a["tg_ge3"]), str(a["tg_le_m3"])])
    return _md_table(head, body)


def _groups(rows: List[dict]) -> List[Tuple[str, List[dict], str]]:
    cs = sorted({base_cost_side_bp(s) for s in SYMBOLS})
    allc = f"{cs[0]:.2f}-{cs[-1]:.2f}"
    out = [("All pairs", rows, allc)]
    for fam, label in (("M1", "M1 burst, fixed hold"), ("M2", "M2 breakout, trailing stop"), ("M3", "M3 scalp, target / stop")):
        out.append((label, [r for r in rows if r["family"] == fam], allc))
    for s in SYMBOLS:
        out.append((s, [r for r in rows if r["symbol"] == s], f"{base_cost_side_bp(s):.2f}"))
    return out


def _ctrl_summary(ctrl: List[dict]) -> dict:
    n = np.array([int(r["n_trades"]) for r in ctrl], dtype=float)
    g = np.array([_f(r["random_entry_mean_gross_bp"]) for r in ctrl])
    net = np.array([_f(r["random_entry_mean_net_bp"]) for r in ctrl])
    rt = np.array([_f(r["round_trip_cost_bp"]) for r in ctrl])
    z = np.array([_f(r["random_entry_z"]) for r in ctrl])
    i = int(np.nanargmax(np.abs(z)))
    return {"w_gross": float((n * g).sum() / n.sum()), "w_net": float((n * net).sum() / n.sum()),
            "w_rt": float((n * rt).sum() / n.sum()), "z_mean": float(np.nanmean(z)), "z_sd": float(np.nanstd(z)),
            "z_gt2": int((np.abs(z) > 2).sum()), "z_gt3": int((np.abs(z) > 3).sum()),
            "z_max_pair": ctrl[i]["pair_id"], "z_max": float(z[i]), "pairs": len(ctrl),
            "unw_gross": float(np.mean(g)), "med_gross": float(np.median(g))}


def _data_rows(reports: List[dict]) -> List[List[str]]:
    out = []
    for d in reports:
        out.append([d["symbol"], d["window"], f"{d['scored_bars']:,}", f"{d['scored_bars'] - d['scored_bars_missing']:,}",
                    f"{d['scored_bars_missing']:,}", f"{d['scored_bars_zero_volume']:,}",
                    f"{d['scored_bars_tradeable']:,}", f"{d['scored_bars_sigma1_defined']:,}",
                    f"{d['scored_bars_sigma15_defined']:,}"])
    return out


def _run_list(d: dict, key: str, lo_utc: str) -> str:
    items = [f"{x['start_utc']} ({x['minutes']:,} min)" for x in d[key] if x["start_utc"] >= lo_utc]
    return "; ".join(items) if items else "none"


def stage_report() -> int:
    from scipy import stats as _st

    check_prereg()
    frozen = require_design_frozen()
    if frozen["n_passers"] != 0:
        raise SystemExit("the report text below was written for the outcome 'no design passer'; a passer needs "
                         "its own holdout section before anything is published")
    D = json.loads((RUN_DIR / "design_ledger.json").read_text())
    rows = D["rows"]
    H = json.loads((RUN_DIR / "holdout_descriptive.json").read_text())
    hrows = H["rows"]
    hbyid = {r["pair_id"]: r for r in hrows}
    ctrl = _read_csv(RUN_DIR / "control_design.csv")
    hctrl = _read_csv(RUN_DIR / "control_holdout_descriptive.csv")
    dr = json.loads((RUN_DIR / "data_report_design.json").read_text())["symbols"]
    hr = json.loads((RUN_DIR / "data_report_holdout.json").read_text())["symbols"]
    man = json.loads((RUN_DIR / "download_manifest.json").read_text())
    sens_p, repro_p, pyt_p = RUN_DIR / "sensitivity_design.json", RUN_DIR / "REPRODUCTION.json", RUN_DIR / "logs" / "pytest.log"
    sens = json.loads(sens_p.read_text()) if sens_p.exists() else None
    repro = json.loads(repro_p.read_text()) if repro_p.exists() else None
    pytest_line = ""
    if pyt_p.exists():
        tail = [ln.strip() for ln in pyt_p.read_text().splitlines() if " passed" in ln or " failed" in ln or " error" in ln]
        pytest_line = tail[-1] if tail else ""

    A, HA = _agg(rows), _agg(hrows)
    best_g = max(rows, key=lambda r: r["mean_bp_gross"])
    best_n = max(rows, key=lambda r: r["mean_bp_net"])
    best_mk = max(rows, key=lambda r: r["mean_bp_maker"])
    worst_n = min(rows, key=lambda r: r["mean_bp_net"])
    sig_pos = sorted([r for r in rows if r["t_gross"] >= 3], key=lambda r: -r["t_gross"])
    hbest_g = max(hrows, key=lambda r: r["mean_bp_gross"])
    hbest_n = max(hrows, key=lambda r: r["mean_bp_net"])
    hbest_mk = max(hrows, key=lambda r: r["mean_bp_maker"])
    costs = {s: base_cost_side_bp(s) for s in SYMBOLS}
    c_lo, c_hi = min(costs.values()), max(costs.values())
    m1 = [r for r in rows if r["family"] == "M1"]
    a_m1 = _agg(m1)
    stop_rows = [r for r in rows if r["family"] != "M1"]
    n_stop_neg = sum(1 for r in stop_rows if r["mean_bp_gross"] < 0)
    fb = [r for r in ctrl if r["family"] != "M1"]                 # follow / fade decomposition of the stop-based pairs
    e2 = [_f(r["directional_edge_bp"]) for r in fb if r["family"] == "M2"]
    e3 = [_f(r["directional_edge_bp"]) for r in fb if r["family"] == "M3"]
    d2 = [_f(r["exit_rule_drag_bp"]) for r in fb if r["family"] == "M2"]
    d3 = [_f(r["exit_rule_drag_bp"]) for r in fb if r["family"] == "M3"]
    gd = np.array([r["mean_bp_gross"] for r in rows])
    gh = np.array([hbyid[r["pair_id"]]["mean_bp_gross"] for r in rows])
    rho_all = float(_st.spearmanr(gd, gh)[0])
    im1 = [i for i, r in enumerate(rows) if r["family"] == "M1"]
    rho_m1 = float(_st.spearmanr(gd[im1], gh[im1])[0])
    stay = int(((gd > 0) & (gh > 0)).sum())
    top5 = [rows[i] for i in np.argsort(-gd)[:5]]
    CS, HCS = _ctrl_summary(ctrl), _ctrl_summary(hctrl)
    dfiles = {f["status"] for f in man["files"]}
    fetched = sorted(f.get("fetched_utc", "") for f in man["files"] if f.get("fetched_utc"))
    deferred = sum(r["exits_deferred_missing_bar"] for r in rows)
    lost = sum(r["signals_lost_untradeable_entry"] for r in rows)
    dropped = sum(r["trades_dropped_window_end"] for r in rows)
    hdeferred = sum(r["exits_deferred_missing_bar"] for r in hrows)
    hlost = sum(r["signals_lost_untradeable_entry"] for r in hrows)
    code_sha = sha256_file(Path(__file__).resolve())
    passers_sha = sha256_file(RUN_DIR / "DESIGN_PASSERS.json")

    L: List[str] = []
    L += ["# FASTMOM v1 — results: minute-scale momentum on BTC / ETH / SOL perps at real fees", "",
          f"**Generated** {utc_now()} by `scripts/factory/fastmom.py report` (module sha256 `{code_sha}`). "
          "Engineer and analyst: Claude, model ID `claude-fable-5-2`.  ",
          f"**Spec:** `research/factory/FASTMOM_PREREGISTRATION.md`, sha256 `{PREREG_SHA256}`, frozen 2026-11-10 18:09 UTC "
          "(DECISIONS.md) and not edited; every stage re-hashes it and refuses on a mismatch.  ",
          f"**Design passers frozen** {frozen['written_utc']}: `runs/fastmom_v1/DESIGN_PASSERS.json`, sha256 `{passers_sha}` "
          f"({frozen['n_passers']} passers). The code parses no bar after 2023-12-31 until that file exists.  ",
          "Research / paper only. No orders, keys, accounts or spend.", "",
          "Labels used below: **[fact]** a number this code produced from the checksum-verified archive files; "
          "**[reading]** how an open point of the pre-registration was resolved (section 10); "
          "**[interpretation]** my judgement, not a measurement.", ""]

    # ---- 1. verdict
    sp = sig_pos[0] if sig_pos else None
    sig_txt = ""
    if sp is not None:
        ratio = sp["round_trip_cost_bp"] / sp["mean_bp_gross"]
        hsp = hbyid[sp["pair_id"]]
        sig_txt = (f"but only {len(sig_pos)} of them {'is' if len(sig_pos) == 1 else 'are'} statistically distinguishable "
                   f"from zero on the right side ({sp['pair_id'].replace('|', ' ')}: {sp['mean_bp_gross']:+.2f} bp per trade, "
                   f"t = {sp['t_gross']:.1f}, {sp['n_trades']:,} trades) — {ratio:.0f} times smaller than its own "
                   f"round-trip cost, and in the descriptive 2024–2026 table the same pair is "
                   f"{hsp['mean_bp_gross']:+.2f} bp (t = {hsp['t_gross']:.1f}) — ")
    else:
        sig_txt = "but none of them is statistically distinguishable from zero — "
    L += ["## 1. Verdict", "",
          f"**DEAD at this cost. No formula passes the design rule, none has a positive average return after costs, "
          f"and none comes close.** [fact] On the design window (2021-01-01 → 2023-12-31) the 129 formula-symbol pairs "
          f"made {A['trades']:,} simulated trades. After the round-trip cost all 129 lose on average: the best pair loses "
          f"{-best_n['mean_bp_net']:.2f} bp per trade ({best_n['pair_id'].replace('|', ' ')}), the median pair loses "
          f"{-A['med_net']:.2f} bp — the typical formula hands over the whole round trip ({2 * c_lo:.2f}–{2 * c_hi:.2f} bp) "
          f"and a little more. Before any cost the average trade makes between {A['min_gross']:+.2f} and "
          f"{A['max_gross']:+.2f} bp depending on the formula (median {A['med_gross']:+.2f} bp; for the 108 fixed-hold "
          f"pairs the median size of the gross mean is {a_m1['med_abs_gross']:.2f} bp). The median break-even cost is "
          f"{A['med_be']:+.2f} bp per side against the {c_lo:.2f}–{c_hi:.2f} bp charged. {A['gross_pos']} of 129 pairs "
          f"are positive before costs, {sig_txt}while {a_m1['tg_le_m3']} of the 108 fixed-hold pairs are significantly "
          f"NEGATIVE before costs (t ≤ −3) — at these horizons a burst is more often partly given back than continued — "
          f"and {n_stop_neg} of the {len(stop_rows)} stop-based pairs are negative before costs: the trailing-stop pairs "
          f"mostly because of the pessimistic intrabar ordering (median drag {float(np.median(d2)):+.2f} bp, median "
          f"directional edge {float(np.median(e2)):+.2f} bp), the target/stop pairs because following the burst did no "
          f"better than fading it (median drag {float(np.median(d3)):+.2f} bp, median edge {float(np.median(e3)):+.2f} bp; "
          f"section 8.2). "
          f"Under the optimistic maker bound (2 bp per side, every passive order assumed filled, no adverse selection) "
          f"{A['maker_pos']} of 129 are positive. Because no pair passed, no formula earned the one-shot holdout read. "
          f"The descriptive 2024-01 → 2026-10 table (not evidence; computed only after the passers file was frozen) says "
          f"the same, a little worse: {HA['gross_pos']} of 129 positive before costs, {HA['net_pos']} after, best "
          f"{hbest_n['mean_bp_net']:+.2f} bp per trade. The pre-registration expected a gross edge of 0–3 bp against a "
          f"10–11 bp round trip; the measured gross is lower than that expectation and the net conclusion is the one it "
          f"predicted. [interpretation] In plain words: buying what is moving and selling within minutes does not fail "
          f"here because of a badly chosen stop or parameter. It fails because, once the bar that shows the move has "
          f"closed, what is left to catch is a fraction of a basis point — more often against you than for you — and "
          f"the fee to try is ten.", ""]

    # ---- 2. what was run
    L += ["## 2. What was run", ""]
    L += _md_table(["Item", "Value"], [
        ["Data", f"Binance USD-M perpetual 1-minute klines, public archive `data.binance.vision`, {man['files_expected']} monthly "
                 f"zips (3 symbols × 70 months, 2021-01 → 2026-10), {man['bytes_total'] / 1e6:.1f} MB, every zip sha256-verified "
                 f"against its published `.CHECKSUM` (fetched {fetched[0] if fetched else '?'} → {fetched[-1] if fetched else '?'})"],
        ["Design window", f"2021-01-01 → 2023-12-31: {dr[0]['scored_days']:,} days, {dr[0]['scored_bars']:,} minutes per symbol"],
        ["Holdout window", f"2024-01-01 → 2026-10-31: {hr[0]['scored_days']:,} days, {hr[0]['scored_bars']:,} minutes per symbol "
                           "(December 2023 is loaded as warm-up only)"],
        ["Cost per side", "taker 5.0 bp + half-spread: " + ", ".join(f"{s[:3]} {costs[s]:.2f} bp" for s in SYMBOLS)
                          + " → round trip " + " / ".join(f"{2 * costs[s]:.2f}" for s in SYMBOLS) + " bp"],
        ["Formulas", "43 per symbol = 129 pairs: M1 burst + fixed hold (36), M2 breakout + trailing stop (4), "
                     "M3 scalp with target and stop (3). Nothing else enters the decision."],
        ["Timing", "signal from the bar that closes at minute t → filled at the OPEN of bar t+1; one position at a time "
                   "per pair; entry and exit each pay the per-side cost; returns are simple returns on notional"],
        ["Trades simulated", f"design {A['trades']:,}; holdout (descriptive) {HA['trades']:,}"],
    ], left=2)
    L += [""]

    # ---- 3. per-family tables
    L += ["## 3. Design window — every formula-symbol pair", "",
          "Columns: **Trades**; **Win %** = share of trades that make money AFTER costs; **Gross** = mean bp per trade "
          "before costs; **Net** = mean bp per trade after the round trip; **Break-even** = gross / 2 = the per-side cost "
          "at which the pair would just break even (charged: "
          + ", ".join(f"{s[:3]} {costs[s]:.2f}" for s in SYMBOLS) + "); **t (net)** = t-statistic of the mean net per "
          "trade, clustered by UTC day; **Sharpe** = annualised (√365) Sharpe of the daily net P&L, a day with no trade "
          "= 0; **t (gross)** = the same clustered t for the gross mean, i.e. whether there is any signal at zero cost. "
          "Formula names: `M1.k5.x2.h15` = 5-minute return beyond 2 σ₅, hold 15 minutes; `M2.N30.y1` = 30-bar breakout, "
          "trail 1 σ₅; `M3.a2.b1` = target 2 σ₅, stop 1 σ₅.", ""]
    L += ["### 3.1 M1 — momentum burst, fixed hold (108 pairs)", ""]
    L += _pair_table(m1, with_hold=False)
    L += ["", "### 3.2 M2 — minute breakout with a trailing stop, 60-minute limit (12 pairs)", ""]
    L += _pair_table([r for r in rows if r["family"] == "M2"], with_hold=True)
    L += ["", "The gross of M2 is negative mostly because of the pessimistic intrabar ordering (reading R8), not because of "
              "the signal: see section 8.2 (follow vs fade) and section 11 (the alternative reading).", ""]
    L += ["### 3.3 M3 — scalp with take-profit and stop-loss, 30-minute limit (9 pairs)", ""]
    L += _pair_table([r for r in rows if r["family"] == "M3"], with_hold=True)
    L += [""]

    # ---- 4. best pairs
    def one(r: dict) -> str:
        return (f"**{r['pair_id'].replace('|', ' ')}** — {r['n_trades']:,} trades, win rate {100 * r['win_rate_net']:.1f} % net "
                f"({100 * r['win_rate_gross']:.1f} % gross), gross {r['mean_bp_gross']:+.2f} bp per trade (t {r['t_gross']:+.2f}), "
                f"net {r['mean_bp_net']:+.2f} bp per trade (median {r['median_bp_net']:+.2f}, t {r['t_net']:+.2f}), "
                f"break-even {r['breakeven_cost_side_bp']:+.2f} bp per side against {r['cost_side_bp']:.2f} charged, "
                f"sum of net returns {100 * r['total_net']:+,.0f} % of one trade's notional, daily Sharpe {r['sharpe_ann_net']:+.1f}")

    L += ["## 4. The single best pairs (design window)", "",
          f"- [fact] Best by GROSS: {one(best_g)}.",
          (f"- [fact] Best by NET: the same pair, {best_n['mean_bp_net']:+.2f} bp per trade — it loses "
           f"{-best_n['mean_bp_net'] / best_n['round_trip_cost_bp'] * 100:.0f} % of its round-trip cost instead of all of it."
           if best_n["pair_id"] == best_g["pair_id"] else f"- [fact] Best by NET: {one(best_n)}."),
          f"- [fact] In the descriptive holdout the best-gross design pair has gross "
          f"{hbyid[best_g['pair_id']]['mean_bp_gross']:+.2f} bp (t {hbyid[best_g['pair_id']]['t_gross']:+.2f}), net "
          f"{hbyid[best_g['pair_id']]['mean_bp_net']:+.2f} bp."]
    if sp is not None:
        hs = hbyid[sp["pair_id"]]
        L += [f"- [fact] The only pair whose gross mean is significantly positive (t ≥ 3): **{sp['pair_id'].replace('|', ' ')}**, "
              f"{sp['mean_bp_gross']:+.3f} bp per trade on {sp['n_trades']:,} trades (t {sp['t_gross']:+.2f}); net "
              f"{sp['mean_bp_net']:+.2f} bp. Descriptive holdout: gross {hs['mean_bp_gross']:+.3f} bp (t {hs['t_gross']:+.2f})."]
    L += [f"- [fact] Worst by net: {worst_n['pair_id'].replace('|', ' ')}, {worst_n['mean_bp_net']:+.2f} bp per trade.",
          f"- [interpretation] The best gross figure belongs to one of the smallest samples in the grid "
          f"({best_g['n_trades']:,} trades, t {best_g['t_gross']:+.2f}): the largest of 129 noisy means, not a discovery.", ""]

    # ---- 5. aggregates
    L += ["## 5. Aggregates (design window)", ""]
    L += _agg_table(_groups(rows))
    L += ["",
          f"[fact] Share of pairs with a positive mean before costs: {A['gross_pos']} / 129 = {100 * A['gross_pos'] / 129:.0f} %. "
          f"After costs: {A['net_pos']} / 129. Median break-even cost per side {A['med_be']:+.2f} bp (best pair "
          f"{A['max_be']:+.2f} bp) versus {c_lo:.2f}–{c_hi:.2f} bp actually charged: the median formula would lose money "
          f"even if trading were free, and the best one would need the all-in cost per side to fall by "
          f"{100 * (1 - A['max_be'] / best_g['cost_side_bp']):.0f} %. Gross means significantly above zero (t ≥ 3): {A['tg_ge3']}; "
          f"significantly below zero (t ≤ −3): {A['tg_le_m3']}. Design rule: mean net > 0: {frozen['n_mean_net_positive']}; "
          f"t ≥ 3.0: {frozen['n_t_ge_3']}; Benjamini–Hochberg at q = 10 % over 129 rejects (one-sided, mean > 0): "
          f"{frozen['n_bh_reject_one_sided']}; (two-sided): {frozen['n_bh_reject_two_sided']} — every two-sided rejection "
          f"is on the LOSING side. Passers: {frozen['n_passers']}.", "",
          f"[fact] Sum of net returns per pair over the three years, on a fixed stake per trade: between "
          f"{100 * max(r['total_net'] for r in rows):+,.0f} % and {100 * min(r['total_net'] for r in rows):+,.0f} % of that stake "
          f"(median {100 * float(np.median([r['total_net'] for r in rows])):+,.0f} %). The more often a formula trades, the more "
          f"it loses: the pair with the most trades ({max(rows, key=lambda r: r['n_trades'])['pair_id'].replace('|', ' ')}, "
          f"{max(rows, key=lambda r: r['n_trades'])['n_trades'] / dr[0]['scored_days']:.0f} trades a day) loses "
          f"{-100 * max(rows, key=lambda r: r['n_trades'])['total_net']:,.0f} % of its stake.", ""]

    # ---- 6. maker bound
    L += ["## 6. Maker optimistic bound (2.0 bp per side, no spread)", "",
          f"[fact] Same trades, charged 2.0 bp per side instead of the taker cost: {A['maker_pos']} of 129 pairs have a "
          f"positive mean. The best is {best_mk['pair_id'].replace('|', ' ')} at {best_mk['mean_bp_maker']:+.2f} bp per trade "
          f"(t {best_mk['t_maker']:+.2f}); the median pair makes {A['med_maker']:+.2f} bp. Descriptive holdout: "
          f"{HA['maker_pos']} of 129 positive, best {hbest_mk['mean_bp_maker']:+.2f} bp "
          f"({hbest_mk['pair_id'].replace('|', ' ')}).", "",
          "[interpretation] Why this row is only a ceiling and not a strategy:", "",
          "1. It keeps the taker run's fills — the open of the next bar, a stop level, a target level — and assumes a "
          "resting order would have been filled at each of them every time. A passive buy is filled when the market "
          "comes DOWN to it. For a momentum entry that means: filled mostly when the move has already failed, left "
          "unfilled when the move runs away. That adverse selection is the whole cost of trading passively and a "
          "one-minute bar cannot show it.",
          "2. Stop exits are market orders by nature; they are charged here as if they were passive.",
          "3. No queue position, no partial fill and no missed trade is modelled; the half-spread a maker would EARN is "
          "not credited either, because the same fills cannot both be passive and happen on every signal.",
          "", "So the true maker result lies below this row by an amount bars cannot measure. "
              + ("Even this ceiling is negative for every pair." if A["maker_pos"] == 0 else
                 "The pairs that are positive here are positive only under those assumptions."), ""]

    # ---- 7. holdout
    L += ["## 7. Holdout (2024-01-01 → 2026-10-31)", "",
          "### 7.1 The pre-registered read: design passers only", "",
          f"[fact] There is no design passer, so the one-shot holdout was not used for any formula. "
          f"`runs/fastmom_v1/holdout_passers.csv` holds a header and no rows. Outcome under the pre-registration: "
          f"every formula is DEAD at this cost.", "",
          "### 7.2 Descriptive table for all 129 pairs — NOT evidence", "",
          "Computed after `DESIGN_PASSERS.json` was written, at the conductor's instruction, so the owner can see whether "
          "2024–2026 looks different. Nothing in it can promote a formula (see section 13).", ""]
    L += _agg_table(_groups(hrows))
    L += ["",
          f"[fact] Positive before costs: {HA['gross_pos']} / 129; after costs: {HA['net_pos']} / 129; under the maker bound: "
          f"{HA['maker_pos']} / 129. Pairs that would meet the holdout numbers (mean net > 0 and t ≥ 2): "
          f"{sum(1 for r in hrows if r['descriptive_only_meets_holdout_numbers'])}. Best gross: "
          f"{hbest_g['pair_id'].replace('|', ' ')} {hbest_g['mean_bp_gross']:+.2f} bp (t {hbest_g['t_gross']:+.2f}, "
          f"{hbest_g['n_trades']:,} trades). Best net: {hbest_n['pair_id'].replace('|', ' ')} {hbest_n['mean_bp_net']:+.2f} bp. "
          f"Median gross {HA['med_gross']:+.2f} bp, median break-even {HA['med_be']:+.2f} bp per side. Gross means with "
          f"t ≥ 3: {HA['tg_ge3']}; with t ≥ 2: {HA['tg_ge2']}; with t ≤ −3: {HA['tg_le_m3']}.", "",
          f"[fact] Did anything change? The rank correlation (Spearman) of the gross means between the two windows is "
          f"{rho_all:+.2f} over all 129 pairs — most of that is the mechanical ordering of the families (M2 below M3 "
          f"below M1) — and {rho_m1:+.2f} inside the 108 M1 pairs. Of the {A['gross_pos']} pairs that were positive before "
          f"costs in the design window, {stay} are still positive in 2024–2026. The five best design pairs by gross:", ""]
    L += _md_table(["Pair", "Design gross bp (t)", "Holdout gross bp (t)", "Holdout net bp"],
                   [[r["pair_id"].replace("|", " "), f"{r['mean_bp_gross']:+.2f} ({r['t_gross']:+.2f})",
                     f"{hbyid[r['pair_id']]['mean_bp_gross']:+.2f} ({hbyid[r['pair_id']]['t_gross']:+.2f})",
                     f"{hbyid[r['pair_id']]['mean_bp_net']:+.2f}"] for r in top5])
    L += ["", "[interpretation] The small positive gross means of the design window were noise around zero: they do not "
              "carry over" + (" (no gross mean reaches t ≥ 2 in 2024–2026)" if HA["tg_ge2"] == 0 else "")
              + ". What does carry over is the sign of the bulk — slightly negative before costs — and the size of the fee.", ""]

    # ---- 8. sanity
    L += ["## 8. Sanity checks", "", "### 8.1 Random-entry control", "",
          f"For every pair, the same number of trades with the same sides and the same holding times (in bars) was "
          f"entered at uniformly random tradeable minutes of the same window and closed at the open that many bars later "
          f"(seed {CONTROL_SEED}; `control_design.csv`, `control_holdout_descriptive.csv`). Expected: zero before costs, "
          f"minus the round trip after.", ""]
    L += _md_table(["Window", "Trade-weighted control gross bp", "Control net bp", "Round trip bp (trade-weighted)",
                    "z of the 129 control means: mean / sd", "abs(z) > 2 (≈ 6 expected)", "abs(z) > 3", "Largest z"],
                   [["Design", f"{CS['w_gross']:+.4f}", f"{CS['w_net']:+.4f}", f"{CS['w_rt']:.4f}",
                     f"{CS['z_mean']:+.2f} / {CS['z_sd']:.2f}", str(CS["z_gt2"]), str(CS["z_gt3"]),
                     f"{CS['z_max']:+.2f} ({CS['z_max_pair'].replace('|', ' ')})"],
                    ["Holdout (descriptive)", f"{HCS['w_gross']:+.4f}", f"{HCS['w_net']:+.4f}", f"{HCS['w_rt']:.4f}",
                     f"{HCS['z_mean']:+.2f} / {HCS['z_sd']:.2f}", str(HCS["z_gt2"]), str(HCS["z_gt3"]),
                     f"{HCS['z_max']:+.2f} ({HCS['z_max_pair'].replace('|', ' ')})"]])
    L += ["",
          f"[fact] The control behaves: its gross mean is {CS['w_gross']:+.3f} bp (design) and {HCS['w_gross']:+.3f} bp "
          f"(holdout) per trade, its net mean {CS['w_net']:.2f} and {HCS['w_net']:.2f} bp against round trips of "
          f"{CS['w_rt']:.2f} and {HCS['w_rt']:.2f} bp, and the per-pair z-scores are distributed as chance says they should "
          f"be. The price and cost accounting has no drift of its own. (The control says nothing about look-ahead in the "
          f"signals; that is what the entry-timing and truncation tests are for.)", "",
          "### 8.2 Follow versus fade — how much of M2 / M3 is the exit rule, how much the signal", "",
          "M2 and M3 exit on intrabar rules that are pessimistic by construction (readings R8 and R9), so even a coin-flip "
          "direction loses before costs. To separate that from the signal, every actual M2 / M3 entry was also simulated "
          "in the OPPOSITE direction with the same exit rule. **Drag** = (follow + fade) / 2 is what the exit rule costs "
          "whatever the direction; **edge** = (follow − fade) / 2 is what the direction of the signal adds. Design window, "
          "bp per trade before costs:", ""]
    L += _md_table(["Pair", "Trades", "Follow (the formula)", "Fade (opposite side)", "Drag of the exit rule", "Edge of the direction"],
                   [[r["pair_id"].replace("|", " "), f"{int(r['n_trades']):,}", f"{_f(r['actual_mean_gross_bp']):+.2f}",
                     f"{_f(r['fade_mean_gross_bp']):+.2f}", f"{_f(r['exit_rule_drag_bp']):+.2f}",
                     f"{_f(r['directional_edge_bp']):+.2f}"] for r in fb])
    L += ["",
          f"[fact] M2: drag {min(d2):+.2f} to {max(d2):+.2f} bp, directional edge {min(e2):+.2f} to {max(e2):+.2f} bp "
          f"({sum(1 for v in e2 if v > 0)} of {len(e2)} positive). M3: drag {min(d3):+.2f} to {max(d3):+.2f} bp, edge "
          f"{min(e3):+.2f} to {max(e3):+.2f} bp ({sum(1 for v in e3 if v > 0)} of {len(e3)} positive). "
          f"[interpretation] Take the pessimistic exit rule away entirely and the direction of the breakout or of the "
          f"5-minute burst is still worth only between {min(e2 + e3):+.2f} and {max(e2 + e3):+.2f} bp per trade"
          + (" — in M3 it is negative for every pair, i.e. fading the burst did better than following it" if max(e3) < 0 else "")
          + f". Against a {2 * c_lo:.0f}–{2 * c_hi:.0f} bp round trip neither is tradeable.", "",
          "### 8.3 Independent cross-checks and tests", "",
          "- `scripts/factory/tests/test_fastmom.py` — synthetic bars with hand-computed answers: entry timing (a signal at "
          "t cannot use bar t+1), fixed-hold P&L with costs, stop-before-target inside one bar, gap-through fills at the "
          "open, one position at a time, σ_k from past bars only (truncation: everything up to bar t is bit-identical when "
          "later bars are altered), the day-clustered t against a hand-computed example and against statsmodels, "
          "Benjamini–Hochberg on toy vectors, missing / zero-volume bars, the holdout seal, an end-to-end pipeline on "
          "synthetic archives."
          + (f" Last run: `{pytest_line}`." if pytest_line else ""),
          "- An independent minute-by-minute state machine (in the test file) reproduces the simulator trade for trade "
          "on random bars and on three slices of the real archive that contain zero-volume runs and the SOL archive holes.",
          "- A separate pandas path (rolling standard deviation, plain sequencing loop) reproduces the frozen ledger's "
          "trade count and gross mean of three M1 pairs on the full design window; statsmodels' cluster-robust OLS "
          "reproduces the ledger's t-statistics on the real trades of three ETHUSDT pairs (both are tests in the suite).",
          "- Before the design run, 25 deliberately broken versions of the module (look-ahead fill, peeking signal, target "
          "before stop, gap filled at the level, cost charged once, unclustered t, seal removed, …) each made at least "
          "one test fail (an ad-hoc mutation run during development, not part of the suite)."]
    if repro is not None:
        same = repro["code_sha256"] == code_sha
        L += [f"- `fastmom reproduce` ({repro['written_utc']}, module sha256 `{repro['code_sha256']}`"
              + (", the module that wrote this report" if same else ", an EARLIER version of the module than the one that "
                 "wrote this report") + "): the frozen tables recomputed from the raw zips are byte-identical: "
              + ", ".join(f"`{k}` {'identical' if v['identical'] else 'DIFFERENT'}" for k, v in repro["files"].items()) + "."]
    L += [""]

    # ---- 9. data notes
    L += ["## 9. Data notes", "",
          f"[fact] {man['files_expected']} files requested, "
          + ", ".join(f"{v} {k}" for k, v in man["status_counts"].items())
          + f"; all {sum(1 for f in man['files'] if f.get('checksum_ok'))} zips match "
          f"their published sha256 (`download_manifest.json`; `fastmom verify` re-hashes them offline). Plain scripted GETs, "
          f"default `python-requests` User-Agent, under 4 requests per second. Timestamps are milliseconds in every file "
          f"(no microsecond file); every bar's open time lies inside the month named by its file, on the minute grid, "
          f"strictly increasing (asserted while parsing). Header rows: "
          + ", ".join(f"{d['symbol'][:3]} {d['files_with_header_row']} of {d['files']} design files" for d in dr)
          + "; " + ", ".join(f"{d['symbol'][:3]} {d['files_with_header_row']} of {d['files']}" for d in hr)
          + " files of the holdout load. OHLC-inconsistent bars: "
          + str(sum(d["ohlc_inconsistent_bars"] for d in dr) + sum(d["ohlc_inconsistent_bars"] for d in hr)) + ".", ""]
    L += _md_table(["Symbol", "Window", "Minutes expected", "Bars present", "Missing", "Zero-volume", "Tradeable",
                    "σ₁ defined", "σ₁₅ defined"], _data_rows(dr) + _data_rows(hr), left=2)
    L += ["", "Missing runs (bars absent from the archive) and zero-volume runs inside each scored window:", ""]
    for d in dr:
        L += [f"- {d['symbol']} design — missing: {_run_list(d, 'missing_run_list', '2021-01-01')}; zero-volume: "
              f"{_run_list(d, 'zero_volume_run_list', '2021-01-01')}"]
    for d in hr:
        L += [f"- {d['symbol']} holdout — missing: {_run_list(d, 'missing_run_list', '2024-01-01')}; zero-volume: "
              f"{_run_list(d, 'zero_volume_run_list', '2024-01-01')}"]
    L += ["",
          f"[fact] Consequences in the simulation. Design: {lost:,} otherwise-valid signals were not taken because the entry "
          f"bar had no volume or was missing; {deferred:,} time exits fell on a missing or zero-volume bar and were filled "
          f"at the next available open; {dropped} trades were dropped at the window end. Holdout (descriptive): {hlost:,} "
          f"and {hdeferred:,}. After a hole σ_k is undefined for the next 1,440 + k minutes (R1), so no signal is taken "
          f"for a day after each hole."]
    if sens is not None and sens.get("trades_carried_across_archive_holes"):
        cc = sens["trades_carried_across_archive_holes"]
        worst = max(cc, key=lambda c: abs(c["mean_bp_gross_all"] - c["mean_bp_gross_without_them"]))
        L += [f"[fact] SOLUSDT has two archive holes in the design window (three days from 2022-02-26, two days from "
              f"2022-04-01). A position open when a hole starts is closed at the first bar after it, as the brief "
              f"requires: {sum(c['n_carried'] for c in cc)} trades in {len(cc)} pairs were carried across a hole for days. "
              f"Removing them changes a pair's gross mean by at most "
              f"{abs(worst['mean_bp_gross_all'] - worst['mean_bp_gross_without_them']):.2f} bp "
              f"({worst['pair_id'].replace('|', ' ')}: {worst['mean_bp_gross_all']:+.2f} → "
              f"{worst['mean_bp_gross_without_them']:+.2f} bp) and turns no pair positive after costs."]
    L += [""]

    # ---- 10. readings
    q = "> "
    L += ["## 10. Every open point of the pre-registration and how it was read", "",
          "Rule followed: where the frozen text leaves a choice, take the reading that is WORSE for the strategy; where "
          "neither reading is clearly worse, take the literal one and say so. The sentences are quoted verbatim. Section "
          "11 shows what the main alternatives would have given.", "",
          "**A1 — σ_k.**", q + "σ_k = the trailing 1,440-bar (24 h) standard deviation of k-minute returns, known at the signal bar.",
          "", "Open: overlapping or non-overlapping k-minute returns; whether the window contains the signal bar's own "
              "return; the divisor; what happens when bars are missing. [reading R1] The 1,440 OVERLAPPING k-minute simple "
              "returns close_i / close_(i−k) − 1 ending at and including the signal bar (the brief said \"using bars up to "
              "and including the signal bar\"), sample standard deviation (n − 1) about the window mean; all 1,440 must "
              "exist, otherwise no signal. Including the signal bar's own return makes a burst inflate its own threshold "
              "(fewer signals); the alternative is sensitivity S1.", "",
          "**A2 — one position at a time.**",
          q + "One position at a time per formula-symbol; signals during an open position are ignored.", "",
          "Open: a signal at the close of the bar just before an exit open coincides with the exit print. [reading R3] "
          "The position is still open at that close, so the signal is ignored; the first usable signal is the one at the "
          "close of the exit bar. Literal reading; direction of the effect unknown a priori; the alternative is "
          "sensitivity S2.", "",
          "**A3 — M2 stop.**",
          q + "exit when price retraces y·σ_5 from the best price since entry, y ∈ {1, 2}, or after 60 minutes. Stops are "
              "evaluated on each bar's high/low and filled AT THE STOP LEVEL if the bar opens beyond it, at the open "
              "(gap-through is paid).", "",
          "Open: (i) the second sentence, read word for word, says the stop is filled at its level WHEN the bar opens "
          "beyond it. It is read as \"filled at the stop level; if the bar opens beyond it, at the open\", which is what "
          "\"gap-through is paid\" and the brief (\"gap-through fills at the open\") say. (ii) y·σ_5 is a return measured "
          "from the best price, with σ_5 frozen at the signal bar [R7]. (iii) The text does not say whether a bar's own "
          "high may raise the stop that the same bar's low then hits. [reading R8] Bar by bar the worse of the two orders "
          "of the bar's high and low is taken, with fills at the stop level in force — the pre-registration's own "
          "\"pessimistic ordering\" of M3 applied to the trail. This is harsher than the usual back-test convention "
          "(adverse extreme first, sensitivity S3) but it is not the worst conceivable path (a fill at the bar's low).", "",
          "**A4 — M3 levels.**",
          q + "exit at +a·σ_5 (take-profit) or −b·σ_5 (stop-loss) or after 30 minutes, (a, b) ∈ {(1, 1), (2, 1), (1, 2)}. If a "
              "bar's range touches both levels, the STOP is assumed to fill first (pessimistic ordering).", "",
          "Open: what the levels are measured from; gap-through is written for M2 only; a favourable gap through the "
          "target. [reading R9] Levels are returns from the entry price with σ_5 at the signal bar. A stop on a bar that "
          "opens beyond it pays the open (worse). A take-profit is always filled at its level, never at a better open "
          "(worse). A bar that opens beyond the target and also trades through the stop is booked as a stop (literal, "
          "worse).", "",
          "**A5 — zero-volume and missing bars.**", q + "Zero-volume bars are no-trade bars.", "",
          "[reading R4] No entry on a zero-volume or missing bar (the signal is dropped, counted); a time exit due on one "
          "is filled at the next bar with volume (counted); stops and targets are evaluated on bars with volume only. A "
          "signal may still be COMPUTED at a zero-volume bar that exists in the archive (its close is the last traded "
          "price). Signals need complete history (R1, R6), so nothing is traded for a day after a hole.", "",
          "**A6 — costs.**", q + "Per side: taker fee 5.0 bp + half-spread BTC 0.07 / ETH 0.24 / SOL 0.60 bp.", "",
          "[reading R5] Additive on entry notional: net = side × (exit / entry − 1) − 2 × cost. Charging the exit on exit "
          "notional would change a trade by less than 0.01 bp.", "",
          "**A7 — statistics.**",
          q + "number of trades, win rate, mean and median net return per trade (bp), mean gross per trade (bp), breakeven "
              "cost per side (bp), total net return, Sharpe of the daily P&L (a day with no trade = 0), and a t-statistic of "
              "the mean net per trade clustered by UTC day.", "",
          "[readings R12–R15] Win rate on NET returns (worse; the gross win rate is in the ledger). Total net return = the "
          "sum of per-trade net returns on a fixed notional (the compounded figure is also in the ledger). A trade belongs "
          "to the UTC day of its entry. Daily Sharpe over every calendar day of the window, annualised by √365. Clustered "
          "t = cluster-robust (CR1) t of an intercept, clusters = entry days.", "",
          "**A8 — the multiple-testing step.**",
          q + "mean net per trade > 0 with day-clustered t ≥ 3.0 AND the Benjamini–Hochberg test at q = 10 % over all 129 "
              "pairs rejects it.", "",
          "Open: which p-value. [reading R16] A pair must be rejected under BOTH the one-sided p (alternative: mean > 0) and "
          "the two-sided p, each from Student-t with (trading days − 1) degrees of freedom. The one-sided reading is the "
          f"binding one here: the two-sided test rejects all {frozen['n_bh_reject_two_sided']} pairs for being significantly "
          "NEGATIVE, which would have made the step vacuous for a positive candidate.", "",
          "**A9 — window edges.**", q + "Design window 2021-01-01 → 2023-12-31. Holdout 2024-01-01 → 2026-10-31, read once, "
                                     "only for formulas that pass the design rule.", "",
          "[reading R11] A trade belongs to the window of its entry bar and must be able to finish inside it (no entry "
          "whose time limit falls after the window's last bar), so the design run never needs a 2024 bar. The holdout run "
          "loads December 2023 only to warm up σ and the N-bar extremes. \"Read once, only for formulas that pass\": see "
          "section 13 for the descriptive table.", "",
          "**Not open, stated for completeness.** M1 exits at the open h minutes after the entry open (R2). M2 breakout = "
          "close above the highest HIGH (below the lowest LOW) of the previous N bars, the current bar excluded, all N "
          "present (R6). Time exits of M2 / M3 are at the open 60 / 30 minutes after the entry open (R10).", "",
          "**No formula was impossible to run as written.** All 43 ran on all three symbols; the only textual defect is "
          "the garbled stop sentence of A3 (i).", ""]

    # ---- 11. sensitivity
    if sens is not None:
        L += ["## 11. Does the verdict depend on those readings? (design window; not part of the decision rule)", "",
              "The same pairs re-run under the reading that was NOT chosen, one at a time, after the passers were frozen. "
              "These rows cannot promote anything; they only show whether section 1 hangs on a choice of mine.", ""]
        L += _md_table(["Reading", "What changes", "Pairs", "Trades", "Gross > 0", "Net > 0", "Maker bound > 0",
                        "Median gross bp", "Best net bp (pair)", "Largest change of a gross mean bp"],
                       [[s["reading"].split("_")[0], s["what"], str(s["pairs"]), f"{s['trades']:,}", str(s["mean_gross_positive"]),
                         str(s["mean_net_positive"]), str(s["mean_maker_positive"]), f"{s['median_gross_bp']:+.2f}",
                         f"{s['best_net_bp']:+.2f} ({s['best_net_pair'].replace('|', ' ')})",
                         f"{s['largest_gross_change_vs_registered_bp']:+.2f}"] for s in sens["summary"]], left=2)
        worst_alt = max((s for s in sens["summary"]), key=lambda s: s["best_net_bp"])
        any_pos = any(s["mean_net_positive"] > 0 for s in sens["summary"])
        s3 = [s for s in sens["summary"] if s["reading"].startswith("S3")]
        L += ["",
              "[fact] " + ("Under at least one alternative reading a pair has a positive net mean — see the table; it is not a "
                           "pass (the decision uses the registered readings only)." if any_pos else
                           f"Under every alternative reading the number of pairs with a positive net mean is 0; the best net "
                           f"mean over all readings is {worst_alt['best_net_bp']:+.2f} bp ({worst_alt['best_net_pair'].replace('|', ' ')}, "
                           f"reading {worst_alt['reading'].split('_')[0]}).")
              + (f" With the usual \"adverse extreme first\" convention (S3) the 12 M2 pairs have a median gross of "
                 f"{s3[0]['median_gross_bp']:+.2f} bp and {s3[0]['mean_gross_positive']} of 12 are positive before costs; their "
                 f"best net mean is {s3[0]['best_net_bp']:+.2f} bp." if s3 else "")
              + " [interpretation] The verdict does not depend on how the open points were read.", ""]

    # ---- 12. limits
    tnet = np.array([r["t_net"] for r in rows])
    L += ["## 12. Limits", "",
          "- **Funding is ignored** (pre-registration §1). Holding periods are 1–60 minutes; a position pays or receives "
          "funding only if it is open across an 8-hourly stamp. Second-order here, and it cannot rescue pairs that are "
          f"{-A['max_net']:.0f}–{-A['min_net']:.0f} bp per trade under water.",
          "- **No market impact, no latency.** The entry is the first print of the next minute. A real order sent when the "
          "bar closes arrives later; after a burst it chases the move, so the true entry is probably worse than the open "
          "used here (not measured).",
          "- **Bars, not ticks.** The order of the high and the low inside a minute is unknown; M2 and M3 are "
          "pessimistic-ordering simulations, not tick replays (section 8.2 measures how much that costs). And a stop "
          "\"filled at the level\" is itself optimistic on a fast move: a stop-market order fills at the next available "
          "price, which can be well through the level; only opens beyond the stop are charged for that here.",
          "- **The costs are today's, on another venue.** Taker 5.0 bp is the Kraken Derivatives EEA entry tier and the "
          "half-spreads are one top-of-book snapshot of 2026-11-10 (`landscape/venues.json`), applied to Binance prices of "
          "2021–2026. No historical spread was measured and Kraken's book is not Binance's. If spreads were wider in "
          "2021–2023 — likely, above all for SOL, but unverified here — the real cost was higher than the one charged.",
          "- **The maker row is a ceiling**, not a result (section 6).",
          "- **The 129 pairs are not independent tests**: formulas share signals and trades (the three M3 pairs enter on the "
          "same bars as M1.k5.x2.*), and the three symbols move together. The clustered t handles dependence inside a day, "
          "not across pairs; this matters only for how surprising a positive result would have been, and there is none.",
          "- **Day clustering assumes days are independent.** Volatility regimes last longer than a day. The t-statistics "
          f"of the net means run from {tnet.min():.1f} to {tnet.max():.1f} (median {float(np.median(tnet)):.0f}), all negative; "
          "a longer dependence horizon would shrink them towards zero but cannot change a sign, and the pass rule needs "
          "a positive mean first.",
          "- **The random-entry control checks the accounting, not the signals**; look-ahead in the signals is excluded by "
          "the entry-timing and truncation tests and by the reference simulator.",
          "- **Archive holes** (SOLUSDT 2022-02-26 → 28 and 2022-04-01 → 02; all three symbols 2026-10-28) are holes in the "
          "public archive, not in trading. Nothing is traded for a day after a hole and a few positions are carried across "
          "one (section 9).",
          "- **Fixed notional, no account effects**: no minimum order size, no margin, no liquidation, no compounding.", ""]

    # ---- 13. deviations and disclosures
    L += ["## 13. Deviations and disclosures", "",
          "1. **Descriptive holdout for all pairs.** The pre-registration says the holdout is \"read once, only for formulas "
          "that pass the design rule\". The conductor's brief additionally asked for the holdout statistics of ALL pairs in "
          "a clearly separate file, after the passers were frozen. That was done (`holdout_descriptive.csv`), in that order, "
          "enforced in code. It is outside the letter of the pre-registration; it is labelled descriptive everywhere and no "
          "formula can be promoted from it. With zero passers the pre-registered read itself was never used.",
          "2. **Four raw holdout rows were displayed before the freeze.** While probing the archive format (header row, "
          "timestamp unit) before any code existed, the first two and last two CSV rows of `SOLUSDT-1m-2026-10.zip` were "
          "printed. No statistic was computed from them, the design rule is mechanical, and the design run parses no file "
          "after 2023-12; it is recorded here because \"never look at a holdout number before the passers exist\" was the "
          "rule, and four raw prices are four numbers.",
          "3. **Sensitivity rows and the follow/fade and random-entry controls are additions** to what the pre-registration "
          "lists. They are diagnostics on the same 129 pairs, run on the design window (the controls also on the "
          "descriptive holdout), and none of them enters the pass rule. \"Nothing else is run\" is respected in the sense "
          "that matters: no further formula was tried and nothing was tuned.",
          "4. **Order of work as executed:** download and checksum verification → tests → design ledger "
          f"({D['meta']['written_utc']}) → `DESIGN_PASSERS.json` ({frozen['written_utc']}) → `holdout_passers.csv` (empty) → "
          f"`holdout_descriptive.csv` ({H['meta']['written_utc']}) → sensitivity, reproduction check, this report. The design "
          "ledger was written once and never re-run with `--force-redesign`"
          + (" (flag recorded false in its meta)." if not D["meta"].get("redesign_after_freeze") else " — NO: the flag is TRUE, see the ledger meta."),
          "5. The module was extended after the freeze (sensitivity switches that default to the registered behaviour, the "
          "reproduce stage, this report). `fastmom reproduce` shows the frozen tables are regenerated byte for byte by the "
          "final code (section 8.3).", ""]

    # ---- 14. files
    files = ["design_ledger.csv", "design_ledger.json", "DESIGN_PASSERS.json", "DESIGN_PASSERS.sha256", "holdout_passers.csv",
             "holdout_passers.json", "holdout_descriptive.csv", "holdout_descriptive.json", "control_design.csv",
             "control_holdout_descriptive.csv", "sensitivity_design.csv", "sensitivity_design.json",
             "data_report_design.json", "data_report_holdout.json", "download_manifest.json", "REPRODUCTION.json"]
    L += ["## 14. Files", "",
          "- Spec (frozen): `research/factory/FASTMOM_PREREGISTRATION.md`",
          "- Code: `scripts/factory/fastmom.py`; tests: `scripts/factory/tests/test_fastmom.py`",
          "- Raw data: `research/factory/data/raw/binance/futures_um/archive_klines_1m/<SYMBOL>/<SYMBOL>-1m-YYYY-MM.zip` "
          "(+ `.zip.CHECKSUM`)",
          "- Run directory `research/factory/runs/fastmom_v1/`:", ""]
    L += _md_table(["File", "sha256"], [[f"`{n}`", f"`{sha256_file(RUN_DIR / n)}`"] for n in files if (RUN_DIR / n).exists()])
    L += ["", "Reproduce: `cd /home/anont/meme && research/factory/.venv/bin/python -m scripts.factory.fastmom "
              "<download | verify | design | passers | holdout | descriptive | sensitivity | reproduce | report>` and "
              "`research/factory/.venv/bin/python -m pytest scripts/factory/tests/test_fastmom.py -q`.", ""]
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(REPORT_DIR / "FASTMOM_RESULTS.md", "\n".join(L))
    log(f"report written: {REPORT_DIR / 'FASTMOM_RESULTS.md'} ({len(L)} lines)")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    stages = {"download": stage_download, "verify": stage_verify, "passers": stage_passers,
              "holdout": stage_holdout, "descriptive": stage_descriptive, "sensitivity": stage_sensitivity,
              "reproduce": stage_reproduce, "report": stage_report}
    ap = argparse.ArgumentParser(prog="fastmom", description=__doc__.split("\n")[0])
    ap.add_argument("stage", choices=["download", "verify", "design", "passers", "holdout", "descriptive",
                                      "sensitivity", "reproduce", "report"])
    ap.add_argument("--force-redesign", action="store_true")
    a = ap.parse_args(argv)
    if a.stage == "design":
        return stage_design(force=a.force_redesign)
    return stages[a.stage]()


if __name__ == "__main__":
    sys.exit(main())
