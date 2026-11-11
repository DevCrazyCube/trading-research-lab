#!/usr/bin/env python3
"""FORWARD-CRYPTO v1 — the forward PAPER LOGGER of research/factory/FORWARD_CRYPTO_v1_PREREGISTRATION.md.

    cd /home/anont/meme
    research/factory/.venv/bin/python -m scripts.factory.forward_crypto run        # the daily job (after 01:10 UTC)
    research/factory/.venv/bin/python -m scripts.factory.forward_crypto status [--verify] [--verify-store] [--pseudo-forward K]
    research/factory/.venv/bin/python -m scripts.factory.forward_crypto replay --start YYYY-MM-DD --out DIR [--asof YYYY-MM-DD] [--daily]

A LOGGER: no orders, no keys, no accounts. It reads four public Binance market-data endpoints and two public
Kraken ones, and it writes only under research/factory/forward/crypto_v1/ (`replay`: only under --out). The
frozen v2 lane (research/factory/data/CRYPTO-PERP) is read, hash-checked and never written.

WHAT ONE RUN DOES
  1. PINS. The forward pre-registration, the v2 pre-registration, the rule grid, the CRYPTO-PERP manifest,
     venues.json and the library files this job executes must still hash to their pins; else it refuses.
  2. EXTEND THE PANEL. Daily candles of every included USDT perpetual, and hourly candles + funding of every
     instrument that has ever been in the volume-rank mask, are fetched from fapi.binance.com (plain GETs,
     the requests library's own User-Agent, <= 4 requests a second, half the documented weight budget,
     <= 462 funding requests per five minutes). Every response body is stored verbatim in one zip per run
     next to an index with its URL, UTC fetch time and sha256; the first observation of a candle wins for
     ever, and a later response that disagrees with it is an incident, not an update.
     The extended lane is rebuilt in memory with the data layer's own code — `crypto.classify_perp`,
     `crypto.daily_frames`, `crypto.live_frames`, `crypto_build.split_segments`, `universe.pit_universe_mask`,
     `crypto.exec_prints`, `crypto.funding_to_rows` — reading the forward store instead of the v2 raw tree.
     Rows up to the frozen lane's last row ARE the frozen lane.
  3. CONTINUITY. The last 90 frozen rows are rebuilt from the REST responses alone, with the data layer's
     as-of-the-freeze logic, and must equal the frozen lane cell for cell (prices, quote volume, mask,
     01:00 and 02:00 prints, live flag, carry, funding counts, settlement flags). A difference is a data
     incident: the run stops and appends nothing.
  4. THE FIVE ARMS (prereg §1), on the instruments ever eligible: A60 = `v2.build_primary` itself; A30 /
     A120 = the same member books through `portfolio.ensemble` and `portfolio.vol_target` with
     vol_window 30 / 120; A0 = the plain mean of the 20 member books x 4.0; C252 = XSMOM.HIGH_PROXIMITY.L252
     sized as in v2 x 8.0; the last two capped at 2x gross, row by row, pro rata.
  5. THE TEN ACCOUNTS, `realism.simulate_account` on the rows from the forward start only (no target exists
     before it: every account opens flat and trades into its book at that row's 01:00 print), 10 % no-trade
     band, `exec_prices` timing with extra_lag 0, missing_return "zero", USD 5,597 each:
     IDEAL = `VenueSpec.ideal()` + 7 bp; KRAKEN-5K = the spec `v2_extras.build_kraken` builds from today's
     Kraken instruments payload (5 bp fee, lot precision, 2x cap) with a flat 2 bp half-spread, holding only
     the instruments Kraken lists on the day the row is appended.
  6. LEDGER. Re-simulation must reproduce every ledgered row (equity and 1 + net return within 1e-12
     relative); then the new rows are appended to ledger.jsonl, each carrying prev_hash / row_hash.
  7. STATUS.md and runs/<utc>.json are rewritten / written.
An incident writes INCIDENT_<utc>.json and exits 2; an unreadable endpoint exits 3; nothing is appended in
either case and the next run backfills the missed rows with the same prints (`backfilled: true`).

THE FORWARD ROWS ARE CAUSAL — where that differs from the v2 data layer
  The v2 lane is built once, after the fact; three of its conventions use data later than the row and
  cannot be applied to a row on the day it is logged. On extension rows only:
  * a row holds an execution print, a live flag and carry only if the daily candle that ended on it traded
    (v2: inside the instrument's whole first-to-last span, which is only known afterwards);
  * a funding stamp counts if the instrument had traded in an hour that closed at or after the stamp, as
    known at the row's own 01:00 print (v2: before the last traded hour of the whole segment);
  * THE SETTLEMENT PRINT of an instrument that stops trading is booked on the THIRD non-traded row after
    its last traded row z (v2 books it on z itself). Three rows is the data layer's own rule for "this
    instrument is over": a later return is a new instrument. Until then a held position is carried at its
    last print; nothing is booked that a later row could take back.
  An instrument that enters the volume-rank mask for the first time gets its whole-life hourly candles and
  funding fetched and filled, as the data layer does for every EVER_IN_MASK instrument (before that its
  carry is 0.0 and it cannot be held, exactly as in the frozen lane).

FILES (all under research/factory/forward/crypto_v1/)
  PIN.json                      read-only: the freeze time that defines the forward start
  ledger.jsonl                  append-only, one row per account per forward day, hash-chained
  kraken_terms.jsonl            append-only, content-addressed: every distinct Kraken listing a row was
                                simulated with (venue symbol, lot step, multiplier per instrument)
  STATUS.md, runs/<utc>.json, INCIDENT_<utc>.json, CODE_FINGERPRINT.json
  data/binance/<utc>.zip        every response body of the run (r/<seq>.json) + index.jsonl
  data/binance/<utc>.index.jsonl, <utc>.parquet   the same index, and the parsed candles / funding stamps
  data/kraken/<utc>_{instruments,tickers}.json.gz + .meta.json
"""
from __future__ import annotations

import argparse
import contextlib
import email.utils
import fcntl
import gzip
import hashlib
import json
import math
import os
import pathlib
import sys
import time
import traceback
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.factory import portfolio, realism, stats, v2, v2_extras  # noqa: E402
from scripts.factory.data import crypto as C  # noqa: E402
from scripts.factory.data import crypto_build as CB  # noqa: E402
from scripts.factory.data.universe import pit_universe_mask  # noqa: E402
from scripts.factory.engine import Refused as EngineRefused  # noqa: E402
from scripts.factory.panel import PanelBundle  # noqa: E402
from scripts.factory.realism import VenueSpec  # noqa: E402
from scripts.factory.strategies import registry  # noqa: E402
from scripts.factory.strategies.common import size_positions  # noqa: E402

# ==================================================================================================
# Configuration — a transcription of FORWARD_CRYPTO_v1_PREREGISTRATION §1-§3. Nothing here is tuned.
# ==================================================================================================
LANE = "CRYPTO-PERP"
FWD = v2.FACT / "forward" / "crypto_v1"
PIN_PATH = FWD / "PIN.json"
PRIMARY_ID = "P.CRYPTO.TREND"
C252_RULE = "XSMOM.HIGH_PROXIMITY.L252"
ARMS = ("A60", "A30", "A120", "A0", "C252")
ACCOUNTS = ("IDEAL", "KRAKEN-5K")
SHADOW_WINDOWS = {"A30": 30, "A120": 120}
N_MEMBERS = 20                      # "the 20 CORE trend rules": v2's speed limit kept all of them
A0_FACTOR = 4.0
C252_FACTOR = 8.0
GROSS_CAP = 2.0
EQUITY0 = 5597.0                    # USD = EUR 5,000 at the ECB reference rate of 2026-11-09
IDEAL_FEE_BP = 7.0
KRAKEN_FEE_BP = 5.0
KRAKEN_HALF_SPREAD_BP = 2.0         # flat, for every instrument (prereg §1) — not the per-coin snapshots of venues.json
KRAKEN_LEVERAGE_CAP = 2.0
STOP_LOSS = 0.30                    # an arm whose IDEAL account is down 30 % from its start is frozen
TOL = 1e-12
FIRST_READ, READ_STEP, VERDICT_ROWS = 60, 30, 180
CONTINUITY_ROWS = 90
PPY = 365

DAY, HOUR = 86_400_000, 3_600_000
ONE_DAY = pd.Timedelta(days=1)
FINALITY_MARGIN = pd.Timedelta(minutes=10)          # a candle is used 10 minutes after it closed: "after 01:10 UTC"
BINANCE = "https://fapi.binance.com"
MIN_GAP_S = 0.25                    # <= 4 requests a second (the limit asked for is 5)
FUNDING_GAP_S = 0.65                # fundingRate: 500 requests / 5 minutes / IP
WEIGHT_BUDGET = 1200                # half of the documented 2,400 a minute; lowered if exchangeInfo says less
OVERLAP_DAYS = 2                    # every fetch re-reads the last two days it already holds: the revision check
NO_DATA_CODES = (-1121, -1122)      # Binance: invalid symbol / invalid symbol status -> the symbol has no candles
KRAKEN_INSTRUMENTS_URL = v2_extras.ENDPOINTS["kraken_instruments"]["url"]
KRAKEN_TICKERS_URL = v2_extras.KRAKEN_TICKERS_URL
PINNED_LIBRARY = ("panel.py", "engine.py", "stats.py", "portfolio.py", "realism.py")
FINGERPRINT_FILES = ("forward_crypto.py", "v2.py", "v2_extras.py", "panel.py", "engine.py", "stats.py", "portfolio.py",
                     "realism.py", "data/crypto.py", "data/crypto_build.py", "data/universe.py", "data/panelio.py",
                     "strategies/common.py", "strategies/registry.py", "strategies/rules_trend.py", "strategies/rules_xs.py")
EXIT_OK, EXIT_CRASH, EXIT_INCIDENT, EXIT_FETCH, EXIT_BUSY = 0, 1, 2, 3, 4


class Incident(RuntimeError):
    """A pre-registered invariant is broken (a pin, the hash chain, the re-simulation, the continuity of
    the data). The run writes INCIDENT_<utc>.json, appends nothing and exits non-zero."""

    def __init__(self, kind: str, message: str, detail: Optional[dict] = None):
        super().__init__(message)
        self.kind = kind
        self.detail = detail or {}


class FetchFailed(RuntimeError):
    """A public endpoint could not be read completely. Nothing is appended; the next run backfills."""


@dataclass(frozen=True)
class Paths:
    root: pathlib.Path

    @property
    def ledger(self) -> pathlib.Path:
        return self.root / "ledger.jsonl"

    @property
    def status(self) -> pathlib.Path:
        return self.root / "STATUS.md"

    @property
    def runs(self) -> pathlib.Path:
        return self.root / "runs"

    @property
    def binance(self) -> pathlib.Path:
        return self.root / "data" / "binance"

    @property
    def kraken(self) -> pathlib.Path:
        return self.root / "data" / "kraken"

    @property
    def classify_root(self) -> pathlib.Path:
        return self.root / "data" / "classify_root"

    @property
    def terms(self) -> pathlib.Path:
        return self.root / "kraken_terms.jsonl"

    @property
    def fingerprint(self) -> pathlib.Path:
        return self.root / "CODE_FINGERPRINT.json"


# ==================================================================================================
# Small helpers
# ==================================================================================================
def _say(*args) -> None:
    print(*args, flush=True)


def utc_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def iso(ts) -> str:
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp(ts) -> str:
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y%m%dT%H%M%SZ")


def day(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def to_ms(ts) -> int:
    return int(pd.Timestamp(ts).value // 10 ** 6)


def from_ms(x) -> pd.Timestamp:
    return pd.Timestamp(int(x), unit="ms", tz="UTC")


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: pathlib.Path) -> str:
    return v2.sha256_file(p)


def canonical(obj) -> str:
    """The one JSON form that is hashed: sorted keys, no whitespace, ASCII, NaN / inf refused."""
    return json.dumps(v2.jsonable(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _atomic_write(path: pathlib.Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _same(a: np.ndarray, b: np.ndarray) -> bool:
    return a.shape == b.shape and bool(np.array_equal(a, b, equal_nan=True))


def _on(s: pd.Series, index: pd.DatetimeIndex, dtype=np.float64) -> np.ndarray:
    """`s` on `index` as a WRITABLE array (pandas hands out read-only views)."""
    return np.array(s.reindex(index).to_numpy(dtype=dtype), dtype=dtype, copy=True)


def last_appendable_row(now: pd.Timestamp) -> pd.Timestamp:
    """The latest row D whose 01:00 UTC execution print is final: D + 1 h + 10 min <= now."""
    return (now - pd.Timedelta(hours=1) - FINALITY_MARGIN).floor("D")


def last_final_hour(now: pd.Timestamp) -> pd.Timestamp:
    """Open time of the latest 1h candle that closed at least 10 minutes ago."""
    return (now - FINALITY_MARGIN).floor("h") - pd.Timedelta(hours=1)


def forward_start_row(index: pd.DatetimeIndex, frozen_utc) -> Optional[pd.Timestamp]:
    """Prereg §2: the first daily 00:00 UTC row that closes AFTER the freeze. None while it does not exist."""
    frozen = pd.Timestamp(frozen_utc)
    frozen = frozen.tz_localize("UTC") if frozen.tzinfo is None else frozen.tz_convert("UTC")
    k = int(index.searchsorted(frozen, side="right"))
    return None if k >= len(index) else index[k]


def forward_start_label(frozen_utc) -> pd.Timestamp:
    """The same row by the calendar: the first UTC midnight strictly after the freeze."""
    frozen = pd.Timestamp(frozen_utc)
    frozen = frozen.tz_localize("UTC") if frozen.tzinfo is None else frozen.tz_convert("UTC")
    return frozen.floor("D") + ONE_DAY


# ==================================================================================================
# The ledger: canonical rows, a hash chain, append only
# ==================================================================================================
def row_hash(row: Mapping) -> str:
    return sha256_hex(canonical({k: v for k, v in row.items() if k != "row_hash"}).encode())


def genesis_hash(pin: Mapping, label: str = "forward") -> str:
    """prev_hash of the first row: the chain is anchored on the frozen pre-registration."""
    return sha256_hex(f"FORWARD-CRYPTO v1|{pin['sha256']}|{pin['frozen_utc']}|{label}".encode())


def chain(rows: Sequence[Mapping], prev: str) -> List[dict]:
    out = []
    for r in rows:
        row = {k: v for k, v in v2.jsonable(dict(r)).items() if k not in ("prev_hash", "row_hash")}
        row["prev_hash"] = prev
        row["row_hash"] = row_hash(row)
        prev = row["row_hash"]
        out.append(row)
    return out


def read_ledger(path: pathlib.Path) -> List[dict]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise Incident("LEDGER_TORN", f"{path.name} does not end with a newline: its last row was not written completely")
    rows = []
    for k, line in enumerate(raw.decode("utf-8").split("\n")[:-1]):
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise Incident("LEDGER_CHAIN", f"{path.name} line {k + 1} is not JSON: {exc}") from exc
        if not isinstance(row, dict) or canonical(row) != line:
            raise Incident("LEDGER_CHAIN", f"{path.name} line {k + 1} is not in canonical form (edited by hand?)",
                           {"line": k + 1})
        rows.append(row)
    return rows


def verify_chain(rows: Sequence[Mapping], genesis: str) -> str:
    """Every row must name its predecessor's hash and carry its own. Returns the last hash."""
    prev = genesis
    for k, r in enumerate(rows):
        if r.get("prev_hash") != prev:
            raise Incident("LEDGER_CHAIN", f"ledger row {k + 1} ({r.get('date')} {r.get('arm')} {r.get('account')}): prev_hash "
                           f"does not continue the chain", {"row": k + 1, "expected_prev": prev, "found_prev": r.get("prev_hash")})
        if r.get("row_hash") != row_hash(r):
            raise Incident("LEDGER_CHAIN", f"ledger row {k + 1} ({r.get('date')} {r.get('arm')} {r.get('account')}): row_hash "
                           f"does not match its content", {"row": k + 1, "expected": row_hash(r), "found": r.get("row_hash")})
        prev = r["row_hash"]
    return prev


def append_ledger(path: pathlib.Path, rows: Sequence[Mapping]) -> None:
    blob = "".join(canonical(r) + "\n" for r in rows).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "ab") as f:
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())


# ==================================================================================================
# Pins
# ==================================================================================================
def load_pin() -> dict:
    return json.loads(PIN_PATH.read_text())


def check_pins() -> dict:
    """Refuse on any pinned object that changed: the two pre-registrations, the rule grid, the frozen lane's
    manifest, venues.json and the library files this job executes."""
    pin = load_pin()
    v2pin = json.loads(v2.PIN.read_text())
    lib = ROOT / "scripts" / "factory"
    manifest = v2.FACT / "data" / LANE / "manifest.json"
    found = {
        "forward_prereg": sha256_file(ROOT / pin["preregistration"]),
        "v2_prereg": sha256_file(v2.PREREG),
        "grid": registry.grid_sha256(),
        "manifest": sha256_file(manifest),
        "venues": sha256_file(v2.VENUES),
        **{f"library/{f}": sha256_file(lib / f) for f in PINNED_LIBRARY},
    }
    want = {
        "forward_prereg": pin["sha256"],
        "v2_prereg": pin["v2_prereg_sha256"],
        "grid": pin["grid_sha256_with_sources"],
        "manifest": v2pin["data_manifest_sha256"][LANE],
        "venues": v2pin["venues_sha256"],
        **{f"library/{f}": v2pin["library_sha256"][f] for f in PINNED_LIBRARY},
    }
    if v2pin["preregistration_sha256"] != pin["v2_prereg_sha256"]:
        raise Incident("PINS", "PIN.json and PREREG_PIN_v2.json name different v2 pre-registrations")
    bad = sorted(k for k in want if found[k] != want[k])
    if bad:
        raise Incident("PINS", f"pinned objects changed since the freeze: {bad}. A frozen logger does not continue on "
                       f"edited rules, data or code.", {k: {"pinned": want[k], "found": found[k]} for k in bad})
    return {"pin": pin, "hashes": found}


def code_fingerprint() -> Dict[str, str]:
    lib = ROOT / "scripts" / "factory"
    return {f: sha256_file(lib / f) for f in FINGERPRINT_FILES}


# ==================================================================================================
# HTTP: plain GETs, rate-limited, every response recorded
# ==================================================================================================
@dataclass
class Resp:
    status: int
    content: bytes
    headers: Dict[str, str]
    url: str
    fetched_utc: str


def _requests_transport() -> Callable:
    import requests

    session = requests.Session()                       # the library's own User-Agent; no key, no cookie, no extra header

    def call(url: str, params: Mapping) -> Tuple[int, bytes, Dict[str, str], str]:
        r = session.get(url, params=params or None, timeout=30)
        return r.status_code, r.content, {k.lower(): v for k, v in r.headers.items()}, r.url

    return call


class Http:
    def __init__(self, transport: Optional[Callable] = None, *, min_gap: float = MIN_GAP_S, slow_gap: float = FUNDING_GAP_S,
                 weight_budget: int = WEIGHT_BUDGET, sleep: Callable = time.sleep, wall: Callable = utc_now):
        self.transport = transport or _requests_transport()
        self.min_gap, self.slow_gap, self.weight_budget = float(min_gap), float(slow_gap), int(weight_budget)
        self.sleep, self.wall = sleep, wall
        self._last = 0.0
        self.n_requests = self.n_bytes = self.max_weight = self.n_weight_pauses = self.n_retries = 0
        self.max_skew_s = 0.0

    def get(self, url: str, params: Optional[Mapping] = None, *, slow: bool = False) -> Resp:
        wait = (self.slow_gap if slow else self.min_gap) - (time.monotonic() - self._last)
        if wait > 0:
            self.sleep(wait)
        last_exc: Optional[BaseException] = None
        for attempt in range(3):
            try:
                status, content, headers, final_url = self.transport(url, dict(params or {}))
            except Exception as exc:                   # network error: two more tries, then the run fails visibly
                last_exc = exc
                self._last = time.monotonic()
                self.n_retries += 1
                self.sleep(2.0 * (attempt + 1))
                continue
            self._last = time.monotonic()
            now = self.wall()
            self.n_requests += 1
            self.n_bytes += len(content)
            try:
                server = pd.Timestamp(email.utils.parsedate_to_datetime(headers["date"])).tz_convert("UTC")
                self.max_skew_s = max(self.max_skew_s, abs((now - server).total_seconds()))
            except Exception:
                pass
            used = headers.get("x-mbx-used-weight-1m")
            if used is not None and str(used).isdigit():
                self.max_weight = max(self.max_weight, int(used))
                if int(used) >= self.weight_budget:    # stay well inside the documented request-weight limit
                    self.n_weight_pauses += 1
                    self.sleep(61.0 - (time.time() % 60.0))
            if status in (418, 429):
                raise FetchFailed(f"HTTP {status} from {url} (rate limited; Retry-After {headers.get('retry-after')}): the run "
                                  f"stops instead of retrying")
            if status >= 500 and attempt < 2:
                self.n_retries += 1
                self.sleep(2.0 * (attempt + 1))
                continue
            return Resp(int(status), content, headers, final_url, iso(now))
        raise FetchFailed(f"GET {url} failed three times: {last_exc!r}")


# ==================================================================================================
# The forward store: raw responses (zip + index) and the parsed observations, first observation wins
# ==================================================================================================
TABLE_KINDS = ("1d", "1h", "fund")


class Tables:
    """Every Binance observation in the store. data[kind][symbol] is a float64 array sorted by time:
    klines (open_ms, close, quote_volume, count), funding (stamp_ms, rate)."""

    def __init__(self) -> None:
        self.data: Dict[str, Dict[str, np.ndarray]] = {k: {} for k in TABLE_KINDS}
        self.cov: Dict[Tuple[str, str], Tuple[int, int]] = {}
        self.complete_through: Optional[pd.Timestamp] = None
        self.runs: List[str] = []

    # ---- loading
    @classmethod
    def load(cls, paths: Paths) -> "Tables":
        t = cls()
        for idx_path in sorted(paths.binance.glob("*.index.jsonl")):
            run_id = idx_path.name[: -len(".index.jsonl")]
            t.runs.append(run_id)
            pq = paths.binance / f"{run_id}.parquet"
            if pq.exists():
                df = pd.read_parquet(pq)
                for (kind, sym), g in df.groupby(["kind", "symbol"], sort=False):
                    width = 2 if kind == "fund" else 4
                    arr = g[["t", "a", "b", "c"]].to_numpy(dtype=np.float64)[:, :width]
                    t.add(str(kind), str(sym), arr)
            for line in idx_path.read_text().splitlines():
                rec = json.loads(line)
                if rec.get("type") == "coverage":
                    t.cover(rec["kind"], rec["symbol"], rec["start_ms"], rec["end_ms"])
                elif rec.get("type") == "complete":
                    through = pd.Timestamp(rec["through_row"])
                    if t.complete_through is None or through > t.complete_through:
                        t.complete_through = through
        return t

    # ---- merging
    def add(self, kind: str, sym: str, arr: np.ndarray) -> Tuple[np.ndarray, List[dict]]:
        """Merge observations; the FIRST observation of a timestamp is kept. Returns (the rows that were
        new, the conflicts: timestamps already held with different values)."""
        arr = np.asarray(arr, dtype=np.float64)
        if arr.ndim != 2 or not len(arr):
            return arr.reshape(0, 2 if kind == "fund" else 4), []
        arr = arr[np.argsort(arr[:, 0], kind="stable")]
        arr = arr[np.r_[True, arr[1:, 0] != arr[:-1, 0]]]
        old = self.data[kind].get(sym)
        if old is None or not len(old):
            self.data[kind][sym] = arr
            return arr, []
        pos = np.clip(np.searchsorted(old[:, 0], arr[:, 0]), 0, len(old) - 1)
        dup = old[pos, 0] == arr[:, 0]
        conflicts = []
        for k in np.flatnonzero(dup):
            if not _same(old[pos[k]], arr[k]):
                conflicts.append({"kind": kind, "symbol": sym, "t_ms": int(arr[k, 0]), "first_seen": old[pos[k]].tolist(),
                                  "now": arr[k].tolist()})
        new = arr[~dup]
        if len(new):
            merged = np.vstack([old, new])
            self.data[kind][sym] = merged[np.argsort(merged[:, 0], kind="stable")]
        return new, conflicts

    def cover(self, kind: str, sym: str, start_ms: int, end_ms: int) -> None:
        a, b = self.cov.get((kind, sym), (int(start_ms), int(end_ms)))
        self.cov[(kind, sym)] = (min(a, int(start_ms)), max(b, int(end_ms)))

    # ---- reading, in the data layer's own shapes
    def symbols(self, kind: str) -> List[str]:
        return sorted(self.data[kind])

    def klines(self, sym: str, interval: str) -> pd.DataFrame:
        """What `crypto.read_klines` returns: index = open time (ms), columns close, quote_volume, count, src."""
        arr = self.data["1d" if interval == "1d" else "1h"].get(sym)
        if arr is None or not len(arr):
            df = pd.DataFrame(columns=["close", "quote_volume", "count", "src"], index=pd.Index([], dtype="int64"))
            df.attrs["off_grid_dropped"] = 0
            return df
        df = pd.DataFrame({"close": arr[:, 1], "quote_volume": arr[:, 2], "count": arr[:, 3], "src": 0.0},
                          index=pd.Index(arr[:, 0].astype("int64")))
        off = (df.index.to_numpy() % (DAY if interval == "1d" else HOUR)) != 0
        if off.any():
            df = df[~off]
        df.attrs["off_grid_dropped"] = int(off.sum())
        return df

    def funding(self, sym: str) -> pd.DataFrame:
        """What `crypto.funding_events` returns for a REST-only symbol: index = stamp (ms), column rate; one
        event per minute (the data layer's de-duplication)."""
        arr = self.data["fund"].get(sym)
        if arr is None or not len(arr):
            out = pd.DataFrame({"rate": np.empty(0)}, index=pd.Index(np.empty(0, dtype="int64"), name="ms"))
        else:
            out = pd.DataFrame({"rate": arr[:, 1]}, index=pd.Index(arr[:, 0].astype("int64"), name="ms"))
            minute = (out.index.to_numpy() + 30_000) // 60_000
            out = out[~pd.Index(minute).duplicated(keep="first")]
        out.attrs["n_archive"], out.attrs["n_rest"] = 0, int(len(out))
        return out

    def last_traded_day_open(self, sym: str) -> Optional[int]:
        arr = self.data["1d"].get(sym)
        if arr is None:
            return None
        traded = arr[arr[:, 3] > 0, 0]
        return int(traded.max()) if len(traded) else None


class RunWriter:
    """One run's additions to the store. Bodies go into <run>.zip verbatim; the index records URL, UTC
    fetch time and sha256 per request; the parsed rows that were NEW go into <run>.parquet."""

    def __init__(self, paths: Paths, run_id: str, tabs: Tables):
        self.dir, self.run_id, self.tabs = paths.binance, run_id, tabs
        self.index: List[dict] = []
        self.rows: List[Tuple[str, str, np.ndarray]] = []
        self.conflicts: List[dict] = []
        self._zip: Optional[zipfile.ZipFile] = None
        self._tmp: Optional[pathlib.Path] = None
        self.seq = 0

    def _open(self) -> zipfile.ZipFile:
        if self._zip is None:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._tmp = self.dir / f"{self.run_id}.zip.partial"
            self._zip = zipfile.ZipFile(self._tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6)
        return self._zip

    def record(self, kind: str, symbol: str, start_ms: Optional[int], end_ms: Optional[int], resp: Resp) -> None:
        self.seq += 1
        entry = f"r/{self.seq:06d}.json"
        self._open().writestr(entry, resp.content)
        self.index.append({"type": "request", "seq": self.seq, "kind": kind, "symbol": symbol, "start_ms": start_ms,
                           "end_ms": end_ms, "url": resp.url, "fetched_utc": resp.fetched_utc, "http_status": resp.status,
                           "bytes": len(resp.content), "sha256": sha256_hex(resp.content), "entry": entry})

    def add_rows(self, kind: str, symbol: str, arr: np.ndarray) -> None:
        new, conflicts = self.tabs.add(kind, symbol, arr)
        if len(new):
            self.rows.append((kind, symbol, new))
        for c in conflicts:
            self.index.append({"type": "conflict", **c})
        self.conflicts += conflicts

    def coverage(self, kind: str, symbol: str, start_ms: int, end_ms: int) -> None:
        self.index.append({"type": "coverage", "kind": kind, "symbol": symbol, "start_ms": int(start_ms), "end_ms": int(end_ms)})
        self.tabs.cover(kind, symbol, start_ms, end_ms)

    def complete(self, through: pd.Timestamp) -> None:
        self.index.append({"type": "complete", "through_row": iso(through)})
        self.tabs.complete_through = through

    def close(self) -> dict:
        if self._zip is None:
            return {"requests": 0}
        blob = "".join(json.dumps(r, sort_keys=True) + "\n" for r in self.index).encode()
        self._zip.writestr("index.jsonl", blob)
        self._zip.close()
        self._zip = None
        final = self.dir / f"{self.run_id}.zip"
        os.replace(self._tmp, final)
        out = {"requests": sum(r["type"] == "request" for r in self.index), "zip": final.name, "zip_bytes": final.stat().st_size,
               "zip_sha256": sha256_file(final), "response_bytes": int(sum(r.get("bytes", 0) for r in self.index)),
               "rows_added": {k: int(sum(len(a) for kk, _, a in self.rows if kk == k)) for k in TABLE_KINDS},
               "conflicts": len(self.conflicts)}
        if self.rows:
            parts = []
            for kind, sym, a in self.rows:
                pad = np.full((len(a), 4 - a.shape[1]), np.nan)
                b = np.hstack([a, pad])
                parts.append(pd.DataFrame({"kind": kind, "symbol": sym, "t": b[:, 0].astype("int64"), "a": b[:, 1], "b": b[:, 2],
                                           "c": b[:, 3]}))
            pq = self.dir / f"{self.run_id}.parquet"
            tmp = pq.with_name(pq.name + ".partial")
            pd.concat(parts, ignore_index=True).to_parquet(tmp, engine="pyarrow", compression="zstd")
            os.replace(tmp, pq)
            out["parsed"], out["parsed_sha256"] = pq.name, sha256_file(pq)
        _atomic_write(self.dir / f"{self.run_id}.index.jsonl", blob)     # written last: a run without it does not exist
        out["index"], out["index_sha256"] = f"{self.run_id}.index.jsonl", sha256_hex(blob)
        return out


def parse_klines(body: bytes) -> np.ndarray:
    """(open_ms, close, quote_volume, count) — the data layer's own REST parser."""
    return C._kline_rows_from_rest(body)


def parse_funding(body: bytes) -> np.ndarray:
    data = json.loads(body)
    if not data:
        return np.empty((0, 2))
    return np.array([(float(r["fundingTime"]), float(r["fundingRate"])) for r in data], dtype=np.float64)


def verify_store(paths: Paths) -> dict:
    """Re-read every zip: each body must hash to its index entry, and re-parsing all of them in order must
    give exactly the tables the parquet files give."""
    fresh, n_req, bad = Tables(), 0, []
    for idx_path in sorted(paths.binance.glob("*.index.jsonl")):
        run_id = idx_path.name[: -len(".index.jsonl")]
        with zipfile.ZipFile(paths.binance / f"{run_id}.zip") as z:
            for line in idx_path.read_text().splitlines():
                rec = json.loads(line)
                if rec.get("type") != "request":
                    continue
                n_req += 1
                body = z.read(rec["entry"])
                if sha256_hex(body) != rec["sha256"]:
                    bad.append({"run": run_id, "entry": rec["entry"], "why": "sha256 differs from the index"})
                    continue
                if rec["http_status"] != 200 or rec["kind"] not in TABLE_KINDS:
                    continue
                arr = parse_funding(body) if rec["kind"] == "fund" else parse_klines(body)
                fresh.add(rec["kind"], rec["symbol"], arr)
    stored = Tables.load(paths)
    for kind in TABLE_KINDS:
        if set(fresh.data[kind]) != set(stored.data[kind]):
            bad.append({"kind": kind, "why": "symbol sets differ between the raw responses and the parsed files"})
            continue
        for sym, arr in fresh.data[kind].items():
            if not _same(arr, stored.data[kind][sym]):
                bad.append({"kind": kind, "symbol": sym, "why": "parsed rows differ from the raw responses"})
    return {"runs": len(stored.runs), "requests": n_req, "problems": bad, "ok": not bad}


@contextlib.contextmanager
def _data_layer_reads(tabs: Optional[Tables] = None, raw_root: Optional[pathlib.Path] = None):
    """Point the data layer's readers at the forward store for the duration of the block, so that
    `crypto.daily_frames`, `crypto.exec_prints` and `crypto.classify_perp` run unchanged on it. Nothing
    in the data layer is edited; the two module attributes are restored on exit."""
    saved = (C.RAW, C.read_klines)
    try:
        if raw_root is not None:
            C.RAW = raw_root
        if tabs is not None:
            C.read_klines = lambda market, sym, interval: tabs.klines(sym, interval)
        yield
    finally:
        C.RAW, C.read_klines = saved


# ==================================================================================================
# The frozen lane
# ==================================================================================================
@dataclass
class Frozen:
    panel: PanelBundle
    manifest_sha256: str
    tracked: List[str]                       # instruments whose hourly candles and funding the data layer holds
    excluded: Dict[str, str]                 # name -> why the frozen build excluded it (sticky)

    @property
    def last_row(self) -> pd.Timestamp:
        return self.panel.prices.index[-1]

    def bases(self) -> Dict[str, pd.Timestamp]:
        """symbol -> its last traded row in the frozen lane."""
        out: Dict[str, pd.Timestamp] = {}
        last = self.panel.prices.apply(lambda s: s.last_valid_index())
        for c, t in last.items():
            b = CB.base_symbol(str(c))
            if t is not None and (b not in out or t > out[b]):
                out[b] = t
        return out


def load_frozen() -> Frozen:
    from scripts.factory.data import load_lane, read_manifest

    panel = load_lane(LANE)                  # refuses a parquet whose sha256 differs from the manifest
    man = read_manifest(LANE)
    for name in ("universe_mask", "exec_prices", "exec_prices_alt", "volume_quote", "live_at_print", "funding_obs",
                 "terminal_return", "settlement_row"):
        if list(panel.aux[name].columns) != list(panel.prices.columns):
            raise Incident("FROZEN_HISTORY", f"the frozen lane's aux[{name!r}] is not aligned to its prices")
    tracked = [c for c in panel.prices.columns if man["per_symbol"][c].get("ever_in_mask")]
    excluded = {n: reason for reason, names in man["exclusions"]["by_reason"].items() for n in names}
    return Frozen(panel, sha256_file(v2.FACT / "data" / LANE / "manifest.json"), tracked, excluded)


# ==================================================================================================
# Fetch: what the extension needs, and nothing else
# ==================================================================================================
def _no_data(resp: Resp) -> bool:
    if resp.status != 400:
        return False
    try:
        return json.loads(resp.content).get("code") in NO_DATA_CODES
    except Exception:
        return False


def fetch_klines(http: Http, w: RunWriter, sym: str, interval: str, start_ms: int, end_ms: int) -> int:
    """Every candle of `sym` with open time in [start_ms, end_ms] (all closed: the caller chooses end_ms)."""
    step = DAY if interval == "1d" else HOUR
    cur, parts = int(start_ms), []
    while cur <= end_ms:
        expected = (end_ms - cur) // step + 1
        limit = 99 if expected <= 99 else 499 if expected <= 499 else 1000 if expected <= 1000 else 1500   # weight 1 / 2 / 5 / 10
        resp = http.get(BINANCE + "/fapi/v1/klines", {"symbol": sym, "interval": interval, "startTime": cur, "endTime": int(end_ms),
                                                     "limit": limit})
        w.record(interval, sym, cur, int(end_ms), resp)
        if _no_data(resp):
            break
        if resp.status != 200:
            raise FetchFailed(f"klines {sym} {interval}: HTTP {resp.status} {resp.content[:200]!r}")
        arr = parse_klines(resp.content)
        if not len(arr):
            break
        if arr[:, 0].max() > end_ms or arr[:, 0].min() < cur:
            raise FetchFailed(f"klines {sym} {interval}: a candle outside the requested range came back")
        parts.append(arr)
        cur = int(arr[-1, 0]) + step
        if len(arr) < limit:
            break
    n = 0
    if parts:
        rows = np.vstack(parts)
        n = len(rows)
        w.add_rows(interval, sym, rows)
    w.coverage(interval, sym, start_ms, end_ms)
    return n


def fetch_funding(http: Http, w: RunWriter, sym: str, start_ms: int, end_ms: int) -> int:
    cur, parts = int(start_ms), []
    while cur <= end_ms:
        resp = http.get(BINANCE + "/fapi/v1/fundingRate", {"symbol": sym, "startTime": cur, "endTime": int(end_ms), "limit": 1000},
                        slow=True)
        w.record("fund", sym, cur, int(end_ms), resp)
        if _no_data(resp):
            break
        if resp.status != 200:
            raise FetchFailed(f"fundingRate {sym}: HTTP {resp.status} {resp.content[:200]!r}")
        arr = parse_funding(resp.content)
        if not len(arr):
            break
        parts.append(arr)
        cur = int(arr[-1, 0]) + 1
        if len(arr) < 1000:
            break
    n = 0
    if parts:
        rows = np.vstack(parts)
        n = len(rows)
        w.add_rows("fund", sym, rows)
    w.coverage("fund", sym, start_ms, end_ms)
    return n


def _ranges(cov: Optional[Tuple[int, int]], need: int, end: int, overlap: int, alive: bool) -> List[Tuple[int, int]]:
    if cov is None:
        return [(need, end)] if need <= end else []
    out = []
    if need < cov[0]:
        out.append((need, cov[0]))
    if alive and end > cov[1]:
        out.append((max(cov[1] - overlap, cov[0]), end))
    return out


def fetch_binance(paths: Paths, fz: Frozen, tabs: Tables, http: Http, now: pd.Timestamp, run_id: str,
                  say: Callable = _say) -> dict:
    """Bring the store up to the latest row whose 01:00 print is final. Raises FetchFailed (whatever was
    fetched is kept) or Incident (a stored observation came back different)."""
    L, F = last_appendable_row(now), fz.last_row
    win0 = F - (CONTINUITY_ROWS - 1) * ONE_DAY           # the first row the continuity check rebuilds
    w = RunWriter(paths, run_id, tabs)
    rep: dict = {"through_row": iso(L), "notices": []}
    t0 = time.time()
    try:
        resp = http.get(BINANCE + "/fapi/v1/exchangeInfo")
        w.record("exchangeInfo", "", None, None, resp)
        if resp.status != 200:
            raise FetchFailed(f"exchangeInfo: HTTP {resp.status}")
        if http.max_skew_s > 120:                                # known from the first response: stop before deciding what is closed
            raise Incident("CLOCK", f"this machine's clock differs from Binance's by {http.max_skew_s:.0f} s: which candles are "
                           f"closed cannot be decided safely")
        info = json.loads(resp.content)
        _atomic_write(paths.classify_root / C.SRC["perp"] / "exchangeInfo" / "latest.json", resp.content)
        limit = next((x.get("limit") for x in info.get("rateLimits", [])
                      if x.get("rateLimitType") == "REQUEST_WEIGHT" and x.get("interval") == "MINUTE"), None)
        if limit:
            http.weight_budget = min(http.weight_budget, int(limit) // 2)
        rep["exchange_info"] = {"symbols": len(info["symbols"]), "request_weight_limit_per_minute": limit,
                                "payload_server_time": None if not info.get("serverTime") else iso(from_ms(info["serverTime"])),
                                "payload_age_hours": None if not info.get("serverTime")
                                else round((now - from_ms(info["serverTime"])).total_seconds() / 3600.0, 2)}
        age = rep["exchange_info"]["payload_age_hours"]
        if age is not None and age > 72:
            rep["notices"].append(f"Binance's exchangeInfo payload is {age:.0f} hours old (the venue serves it from a cache): a new "
                                  f"listing can enter the lane late — at most as late as the payload is old")
        S = {s["symbol"]: s for s in info["symbols"]}
        rest_names = sorted(n for n, s in S.items() if s.get("quoteAsset") == "USDT"
                            and s.get("contractType") in ("PERPETUAL", "TRADIFI_PERPETUAL"))
        frozen_last = fz.bases()
        names = sorted(set(rest_names) | set(frozen_last) | set(tabs.symbols("1d")))
        with _data_layer_reads(raw_root=paths.classify_root):
            cls = C.classify_perp(names)
        included = []
        for n in names:
            inc = bool(cls.at[n, "include"])
            if n in frozen_last:
                if not inc:
                    rep["notices"].append(f"classification drift: {n} is in the frozen lane but exchangeInfo now says "
                                          f"{cls.at[n, 'reason']!r}; it stays in the lane")
                included.append(n)
            elif n in fz.excluded:
                if inc:
                    rep["notices"].append(f"classification drift: {n} was excluded by the frozen build ({fz.excluded[n]}) and "
                                          f"would now be included; it stays excluded")
            elif inc and (n in S or n in tabs.data["1d"]):
                included.append(n)
        rep["names"] = {"usdt_perpetuals_in_exchange_info": len(rest_names), "included": len(included),
                        "excluded_by_reason": {str(k): int(v) for k, v in cls.loc[~cls["include"], "reason"].value_counts().items()},
                        "new_since_freeze": sorted(n for n in included if n not in frozen_last)}
        status = {n: (S[n].get("status") if n in S else None) for n in included}

        def alive(n: str) -> bool:
            if status[n] == "TRADING":
                return True
            last = tabs.last_traded_day_open(n)
            last = from_ms(last + DAY) if last is not None else frozen_last.get(n)
            return last is not None and last >= L - 3 * ONE_DAY

        # ---- daily candles of every included name
        d_end = to_ms(L) - DAY                                   # open time of the candle that ended at L
        n_d = 0
        for n in included:
            cov = tabs.cov.get(("1d", n))
            if n in frozen_last:
                if cov is None and not (status[n] == "TRADING" or frozen_last[n] >= win0):
                    continue                                     # stopped trading before the continuity window
                need = to_ms(win0) - DAY
            else:
                need = 0                                         # a new listing: its whole history
            for a, b in _ranges(cov, need, d_end, OVERLAP_DAYS * DAY, alive(n)):
                n_d += fetch_klines(http, w, n, "1d", a, b)
        say(f"  daily candles: {n_d} rows fetched; {len(included)} names in the lane (weight used {http.max_weight})")

        # ---- hourly candles and funding of every instrument ever in the volume-rank mask
        uni = build_universe(fz, tabs, L)
        frozen_tracked = set(uni.tracked_frozen)
        need_h: Dict[str, int] = {}
        for c in uni.tracked:
            valid = uni.spx[c].notna().to_numpy()
            pos = np.flatnonzero(valid)
            a_row, z_row = uni.rows[pos[0]], uni.rows[pos[-1]]
            if c in frozen_tracked:
                if z_row < win0:
                    continue                                     # nothing after the freeze, nothing in the continuity window
                need = to_ms(win0) - 2 * DAY
            else:
                need = to_ms(a_row) - DAY - HOUR                 # first time in the mask: the whole life, as the data layer does
            b = CB.base_symbol(c)
            need_h[b] = min(need, need_h.get(b, need))
        h_end, f_end = to_ms(last_final_hour(now)), to_ms(now)
        n_h = n_f = 0
        for b in sorted(need_h):
            is_alive = alive(b) if b in status else False
            for a, e in _ranges(tabs.cov.get(("1h", b)), need_h[b], h_end, OVERLAP_DAYS * DAY, is_alive):
                n_h += fetch_klines(http, w, b, "1h", a, e)
            q = C.plain_name(b)                                  # an old "...SETTLED" contract keeps its funding under the plain ticker
            for a, e in _ranges(tabs.cov.get(("fund", q)), need_h[b], f_end, OVERLAP_DAYS * DAY, is_alive):
                n_f += fetch_funding(http, w, q, a, e)
        say(f"  hourly candles: {n_h} rows, funding stamps: {n_f} for {len(need_h)} tracked symbols "
            f"({len(uni.newly)} new in the mask since the freeze)")
        if not w.conflicts:                                      # a store that disagrees with the venue is not "complete":
            w.complete(L)                                        # the next run reads the overlap again
    finally:
        rep.update(w.close())
        rep.update({"seconds": round(time.time() - t0, 1), "max_used_weight_1m": http.max_weight,
                    "weight_budget": http.weight_budget, "weight_pauses": http.n_weight_pauses, "retries": http.n_retries,
                    "max_clock_skew_s": round(http.max_skew_s, 1)})
    if w.conflicts:
        raise Incident("UPSTREAM_REVISION", f"{len(w.conflicts)} observation(s) already in the store came back different from "
                       f"Binance; the first observation is kept and nothing is appended", {"conflicts": w.conflicts[:50]})
    if http.max_skew_s > 120:
        raise Incident("CLOCK", f"this machine's clock differs from the servers' by {http.max_skew_s:.0f} s: which candles are "
                       f"closed cannot be decided safely")
    return rep


# ==================================================================================================
# The extended lane
# ==================================================================================================
@dataclass
class Universe:
    rows: pd.DatetimeIndex
    n0: int                                   # number of frozen rows
    spx: pd.DataFrame                         # prices, instruments (segments), all rows
    sqv: pd.DataFrame                         # quote volume
    seg: dict
    vmask: pd.DataFrame                       # the volume-rank mask (before the last-hour liveness condition)
    rename: Dict[str, str]                    # frozen column -> extended column (identity unless a ticker was re-listed)
    tracked_frozen: List[str]
    tracked: List[str]
    newly: List[str]
    notices: List[str] = field(default_factory=list)


def _norm_index(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    out = idx.tz_convert("UTC").as_unit("ns")
    out.name = "ts"
    return out


def build_universe(fz: Frozen, tabs: Tables, L: pd.Timestamp) -> Universe:
    """Prices, quote volumes, segments and the volume-rank mask on frozen rows + extension rows. Rows up to
    the frozen lane's last row come from the frozen lane; later rows from the store's daily candles."""
    P0 = fz.panel
    R0 = P0.prices.index
    F = R0[-1]
    new_rows = _norm_index(pd.date_range(F + ONE_DAY, L, freq="D")) if L > F else R0[:0]
    rows = _norm_index(R0.append(new_rows))
    cols0 = [str(c) for c in P0.prices.columns]
    base0 = [CB.base_symbol(c) for c in cols0]
    px0, qv0 = P0.prices, P0.aux["volume_quote"]
    multi = {b for b, k in Counter(base0).items() if k > 1}
    single = [c for c, b in zip(cols0, base0) if b not in multi]
    sym_px, sym_qv = px0[single].copy(), qv0[single].copy()      # one segment: the column name IS the symbol
    for b in sorted(multi):                                      # several segments of one symbol never overlap in time
        cs = [c for c, bb in zip(cols0, base0) if bb == b]
        sym_px[b], sym_qv[b] = px0[cs].max(axis=1), qv0[cs].max(axis=1)
    notices: List[str] = []
    if len(new_rows):
        names = tabs.symbols("1d")
        if names:
            with _data_layer_reads(tabs=tabs):
                close, qvol, count, _ = C.daily_frames("perp", names)
            px_r, qv_r = C.live_frames(close, qvol, count)
            ext_px, ext_qv = px_r.reindex(index=new_rows), qv_r.reindex(index=new_rows)
            fresh = [n for n in ext_px.columns if n not in sym_px.columns and bool(ext_px[n].notna().any())]
            for n in fresh:
                if bool(px_r[n].loc[:F].notna().any()):
                    notices.append(f"{n} is not in the frozen lane but Binance returns traded candles before {day(F)}; "
                                   f"only its rows after the freeze are used")
            all_names = sorted(set(sym_px.columns) | set(fresh))
            sym_px = pd.concat([sym_px.reindex(columns=all_names), ext_px.reindex(columns=all_names)])
            sym_qv = pd.concat([sym_qv.reindex(columns=all_names), ext_qv.reindex(columns=all_names)])
        else:
            sym_px, sym_qv = sym_px.reindex(index=rows), sym_qv.reindex(index=rows)
    sym_px.index, sym_qv.index = rows, rows
    spx, sqv, seg = CB.split_segments(sym_px.astype("float64"), sym_qv.astype("float64"))
    n0 = len(R0)
    rename: Dict[str, str] = {}
    for c in cols0:
        ref = px0[c].to_numpy()
        if c in spx.columns and _same(spx[c].to_numpy()[:n0], ref):
            rename[c] = c
            continue
        first = px0[c].first_valid_index()
        cand = [k for k, v in seg.items() if v["base"] == CB.base_symbol(c) and pd.Timestamp(v["first_row"]) == first]
        if len(cand) != 1 or not _same(spx[cand[0]].to_numpy()[:n0], ref):
            raise Incident("FROZEN_HISTORY", f"the extended lane does not contain the frozen history of {c}")
        rename[c] = cand[0]
        notices.append(f"{c} stopped trading for three days or more and its ticker trades again: the frozen instrument is "
                       f"now named {cand[0]} (the data layer's segment rule)")
    vmask = pit_universe_mask(sqv, top_n=CB.TOP_N["perp"], min_history=CB.MIN_HISTORY, vol_window=CB.VOL_WINDOW)
    tracked_frozen = [rename[c] for c in fz.tracked]
    tracked = [c for c in spx.columns if bool(vmask[c].to_numpy().any())]
    lost = sorted(set(tracked_frozen) - set(tracked))
    if lost:
        raise Incident("FROZEN_HISTORY", f"instruments the frozen build tracked are not in the recomputed volume-rank mask: {lost[:10]}")
    known = set(tracked_frozen)
    return Universe(rows, n0, spx, sqv, seg, vmask, rename, tracked_frozen, tracked, [c for c in tracked if c not in known], notices)


def _causal_funding(ev: pd.DataFrame, traded_open_ms: np.ndarray) -> pd.DataFrame:
    """Keep a funding stamp only if, as known at the 01:00 print of the row that collects it, the instrument
    had traded in an hour that closed at or after the stamp (compared to the minute, as the data layer
    de-duplicates stamps: they carry a few milliseconds of jitter)."""
    if not len(ev) or not len(traded_open_ms):
        return ev.iloc[:0]
    t = ev.index.to_numpy(dtype="int64")
    row = -((-(t - HOUR)) // DAY) * DAY                 # the row D with D-1 01:00 < stamp <= D 01:00 (crypto.funding_to_rows)
    k = np.searchsorted(traded_open_ms, row + HOUR, side="left") - 1      # last traded candle opened before D 01:00
    last_close = np.where(k >= 0, traded_open_ms[np.clip(k, 0, None)] + HOUR, -1)
    minute = ((t + 30_000) // 60_000) * 60_000
    return ev[minute <= last_close]


@dataclass
class Extended:
    panel: PanelBundle
    uni: Universe
    info: dict


def build_extended(fz: Frozen, tabs: Tables, L: pd.Timestamp, uni: Optional[Universe] = None) -> Extended:
    """The frozen lane plus every row after it up to L, by the causal rules of the module docstring."""
    uni = uni or build_universe(fz, tabs, L)
    P0 = fz.panel
    rows, n0, T = uni.rows, uni.n0, len(uni.rows)
    cols = [str(c) for c in uni.spx.columns]
    pos_of = {c: j for j, c in enumerate(cols)}
    j0 = np.array([pos_of[uni.rename[str(c)]] for c in P0.prices.columns])

    def lift(df0: pd.DataFrame, fill, dtype) -> np.ndarray:
        out = np.full((T, len(cols)), fill, dtype=dtype)
        out[:n0, j0] = df0.to_numpy(dtype=dtype)
        return out

    exec_p = lift(P0.aux["exec_prices"], np.nan, np.float64)
    alt = lift(P0.aux["exec_prices_alt"], np.nan, np.float64)
    live = lift(P0.aux["live_at_print"], False, bool)
    carry = lift(P0.carry, 0.0, np.float64)
    fund_n = lift(P0.aux["funding_obs"], 0, np.int64)
    settle = lift(P0.aux["settlement_row"], False, bool)
    term = lift(P0.aux["terminal_return"], 0.0, np.float64)
    mask0 = lift(P0.aux["universe_mask"], False, bool)
    vmask = uni.vmask.to_numpy(dtype=bool)
    if not _same((vmask & live & ~settle)[:n0], mask0[:n0]):
        bad = np.argwhere((vmask & live & ~settle)[:n0] != mask0[:n0])
        raise Incident("FROZEN_HISTORY", f"the recomputed universe mask differs from the frozen one on {len(bad)} cells",
                       {"first": [{"row": iso(rows[i]), "instrument": cols[j]} for i, j in bad[:10]]})
    px = uni.spx.to_numpy(dtype=np.float64)
    valid = ~np.isnan(px)
    frozen_tracked = set(uni.tracked_frozen)
    cache: Dict[str, pd.DataFrame] = {}
    info: dict = {"frozen_last_row": iso(rows[n0 - 1]), "last_row": iso(rows[-1]), "extension_rows": T - n0,
                  "instruments": len(cols), "new_instruments": sorted(set(cols) - set(uni.rename.values())),
                  "newly_tracked": list(uni.newly), "settlements_booked": [], "notices": list(uni.notices),
                  "decision_vs_hourly": {"rows_compared": 0, "mismatches": []}, "mask_without_exec_print": []}
    with _data_layer_reads(tabs=tabs):
        for c in uni.tracked:
            j = pos_of[c]
            pos = np.flatnonzero(valid[:, j])
            a, z = int(pos[0]), int(pos[-1])
            start = n0 if c in frozen_tracked else a             # a first-time mask member is filled for its whole life
            if start >= T or (c in frozen_tracked and z < n0 - 1):
                continue                                         # no extension row, or it stopped trading before the freeze
            b = CB.base_symbol(c)
            if b not in cache:
                cache[b] = C.exec_prints("perp", b)
            ex = cache[b]
            h_cov = tabs.cov.get(("1h", b))
            if h_cov is None or (z >= n0 and h_cov[1] < to_ms(rows[z])):
                raise Incident("STORE_INCOMPLETE", f"{c}: the store holds no hourly candles up to its last traded row "
                               f"{day(rows[z])}; the row cannot be built")
            sel = rows[start:]
            lv_row = valid[start:, j]
            e = _on(ex["exec"].where(ex["exec_n"] > 0), sel)
            al = _on(ex["alt"].where(ex["alt_n"] > 0), sel)
            pre = _on(ex["pre"], sel)
            pre_n = _on(ex["pre_n"], sel)                        # NaN where the store has no such candle
            e[~lv_row], al[~lv_row] = np.nan, np.nan
            traded = np.asarray(ex.attrs["traded_open_ms"], dtype="int64")
            t_seg = traded[traded >= to_ms(rows[a]) - DAY]
            first_ms = int(t_seg.min()) if len(t_seg) else None
            ev = _causal_funding(tabs.funding(C.plain_name(b)), traded)
            tot, cnt = C.funding_to_rows(ev, sel, cut_after_ms=None, cut_before_ms=first_ms)
            cr, cn = -np.array(tot.to_numpy(dtype=np.float64)), np.array(cnt.to_numpy(dtype=np.int64))
            cr[~lv_row], cn[~lv_row] = 0.0, 0
            exec_p[start:, j], alt[start:, j], carry[start:, j], fund_n[start:, j] = e, al, cr, cn
            live[start:, j] = (pre_n > 0) & lv_row
            both = lv_row & ~np.isnan(pre)
            new = both & (np.arange(start, T) >= n0)
            info["decision_vs_hourly"]["rows_compared"] += int(new.sum())
            rel = np.abs(px[start:, j] - pre) / px[start:, j]
            for k in np.flatnonzero(new & (rel > 1e-9)):
                info["decision_vs_hourly"]["mismatches"].append({"row": iso(sel[k]), "instrument": c, "daily_close": float(px[start + k, j]),
                                                                  "hourly_close_23h": float(pre[k])})
    # ---- settlement prints, booked when the instrument's end is certain (three non-traded rows)
    for c in uni.tracked:
        j = pos_of[c]
        z = int(np.flatnonzero(valid[:, j])[-1])
        t = z + CB.GAP_SPLIT_DAYS
        if t < n0 or t >= T or settle[z, j]:
            continue                                             # frozen rows are never touched; not certain yet; or booked on z by the frozen lane
        real = exec_p[: z + 1, j][~settle[: z + 1, j]]
        real = real[~np.isnan(real)]
        if not len(real):
            continue
        exec_p[t, j] = alt[t, j] = px[z, j]
        settle[t, j] = True
        term[t, j] = px[z, j] / real[-1] - 1.0
        info["settlements_booked"].append({"instrument": c, "last_traded_row": day(rows[z]), "booked_on": day(rows[t]),
                                           "final_traded_price": float(px[z, j]), "terminal_return": float(term[t, j])})
    mask = vmask & live & ~settle
    for i, j in np.argwhere(mask[n0:] & np.isnan(exec_p[n0:])):
        info["mask_without_exec_print"].append({"row": iso(rows[n0 + i]), "instrument": cols[j]})
    if info["mask_without_exec_print"]:
        info["notices"].append(f"{len(info['mask_without_exec_print'])} eligible instrument-rows after the freeze have no 01:00 print "
                               f"(no trade in that hour): an order there is not sent and is reconsidered on the next row")
    if info["decision_vs_hourly"]["mismatches"]:
        info["notices"].append(f"{len(info['decision_vs_hourly']['mismatches'])} daily closes after the freeze differ from the close of "
                               f"the 23:00 hourly candle (the daily candle stays the decision print, as in the data layer)")

    def frame(a: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame(a, index=rows, columns=cols)

    aux = {"universe_mask": frame(mask), "exec_prices": frame(exec_p), "exec_prices_alt": frame(alt),
           "volume_quote": pd.DataFrame(uni.sqv.to_numpy(dtype=np.float64), index=rows, columns=cols),
           "live_at_print": frame(live), "funding_obs": frame(fund_n), "terminal_return": frame(term), "settlement_row": frame(settle)}
    meta = dict(P0.meta)
    meta["universe_groups"] = {"EVER_IN_MASK": [c for j, c in enumerate(cols) if mask[:, j].any()], "ALL": cols}
    meta["forward_extension"] = {"frozen_last_row": info["frozen_last_row"], "rows": T - n0,
                                 "rule": "causal rows; see scripts/factory/forward_crypto.py"}
    meta["tbill_note"] = "extension rows carry NaN: the fed funds rate is not fetched and no arm reads it"
    panel = PanelBundle(lane=LANE, prices=frame(px), carry=frame(carry), aux=aux, tbill=P0.tbill.reindex(rows), meta=meta)
    return Extended(panel, uni, info)


def _bad(mine: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Cells that differ (two NaN are equal)."""
    if mine.dtype.kind == "f" or ref.dtype.kind == "f":
        a, b = mine.astype(np.float64), ref.astype(np.float64)
        return ~((a == b) | (np.isnan(a) & np.isnan(b)))
    return mine != ref


def _diff(mine: np.ndarray, ref: np.ndarray, rows, cols, limit: int = 12) -> dict:
    bad = _bad(mine, ref)
    cells = [{"row": day(rows[i]), "instrument": str(cols[j]), "rebuilt": v2.jsonable(mine[i, j].item()),
              "frozen": v2.jsonable(ref[i, j].item())} for i, j in np.argwhere(bad)[:limit]]
    return {"cells": int(mine.size), "mismatches": int(bad.sum()), "first": cells}


def continuity_check(fz: Frozen, tabs: Tables, uni: Universe, n_rows: int = CONTINUITY_ROWS) -> dict:
    """Rebuild the last `n_rows` frozen rows from the stored REST responses alone, with the data layer's
    logic as of the freeze (`crypto_lanes._assemble`: segment span, phantom-funding cut, settlement print on
    the last traded row), and compare every cell with the frozen lane."""
    P0 = fz.panel
    R0 = P0.prices.index
    W = R0[-n_rows:]
    F = R0[-1]
    cols0 = [str(c) for c in P0.prices.columns]
    out: dict = {"rows": [day(W[0]), day(W[-1])], "n_rows": len(W), "frames": {}}
    # ---- decision prints and quote volumes, per symbol
    base0 = [CB.base_symbol(c) for c in cols0]
    bases = sorted(set(base0))
    f_px = pd.DataFrame({b: P0.prices.loc[W, [c for c, bb in zip(cols0, base0) if bb == b]].max(axis=1) for b in bases})
    f_qv = pd.DataFrame({b: P0.aux["volume_quote"].loc[W, [c for c, bb in zip(cols0, base0) if bb == b]].max(axis=1) for b in bases})
    names = tabs.symbols("1d")
    if names:
        with _data_layer_reads(tabs=tabs):
            close, qvol, count, _ = C.daily_frames("perp", names)
        px_r, qv_r = C.live_frames(close, qvol, count)
        r_px, r_qv = px_r.reindex(index=W, columns=bases), qv_r.reindex(index=W, columns=bases)
    else:
        r_px = r_qv = pd.DataFrame(np.nan, index=W, columns=bases)
    out["frames"]["prices"] = _diff(r_px.to_numpy(dtype=np.float64), f_px.to_numpy(dtype=np.float64), W, bases)
    out["frames"]["volume_quote"] = _diff(r_qv.to_numpy(dtype=np.float64), f_qv.to_numpy(dtype=np.float64), W, bases)
    # ---- execution prints, live flag, carry, settlement: per tracked instrument, as of the freeze
    n = len(W)
    shape = (n, len(cols0))
    e_all, a_all = np.full(shape, np.nan), np.full(shape, np.nan)
    lv_all, st_all = np.zeros(shape, dtype=bool), np.zeros(shape, dtype=bool)
    cr_all, cn_all = np.zeros(shape), np.zeros(shape, dtype=np.int64)
    cache: Dict[str, pd.DataFrame] = {}
    rebuilt = 0
    tracked0 = set(fz.tracked)
    with _data_layer_reads(tabs=tabs):
        for j, c in enumerate(cols0):
            if c not in tracked0:
                continue
            s0 = P0.prices[c]
            pos = np.flatnonzero(s0.notna().to_numpy())
            a_row, z_row = R0[pos[0]], R0[pos[-1]]
            if z_row < W[0]:
                continue                                         # stopped trading before the window: nothing to rebuild
            rebuilt += 1
            b = CB.base_symbol(c)
            if b not in cache:
                cache[b] = C.exec_prints("perp", b)
            ex = cache[b]
            inseg = np.asarray((W >= a_row) & (W <= z_row))
            e = _on(ex["exec"].where(ex["exec_n"] > 0), W)
            al = _on(ex["alt"].where(ex["alt_n"] > 0), W)
            e[~inseg], al[~inseg] = np.nan, np.nan
            lv = (_on(ex["pre_n"], W) > 0) & inseg
            t_open = np.asarray(ex.attrs["traded_open_ms"], dtype="int64")
            lo, hi = to_ms(a_row) - DAY, to_ms(z_row)
            t_seg = t_open[(t_open >= lo) & (t_open < hi)]
            last_ms = int(t_seg.max()) + HOUR if len(t_seg) else None
            h_cov = tabs.cov.get(("1h", b))
            # the first traded hour is known only if the store's hourly candles reach back to the listing
            first_ms = int(t_seg.min()) if len(t_seg) and h_cov is not None and lo >= h_cov[0] else None
            tot, cnt = C.funding_to_rows(tabs.funding(C.plain_name(b)), W, cut_after_ms=last_ms, cut_before_ms=first_ms)
            tot, cnt = tot.where(inseg, 0.0), cnt.where(inseg, 0)
            if z_row < F and bool(np.isfinite(P0.aux["exec_prices"][c].to_numpy()[: pos[-1]]).any()):
                zi = int(W.get_loc(z_row))                       # the settlement print: the final traded price on the last traded row
                e[zi] = al[zi] = float(s0[z_row])
                st_all[zi, j] = True
            e_all[:, j], a_all[:, j], lv_all[:, j] = e, al, lv
            cr_all[:, j], cn_all[:, j] = -tot.to_numpy(dtype=np.float64), cnt.to_numpy(dtype=np.int64)
    vm = uni.vmask.loc[W, [uni.rename[c] for c in cols0]].to_numpy(dtype=bool)
    aux = P0.aux
    for name, mine, ref in (
            ("exec_prices", e_all, aux["exec_prices"].loc[W].to_numpy(dtype=np.float64)),
            ("exec_prices_alt", a_all, aux["exec_prices_alt"].loc[W].to_numpy(dtype=np.float64)),
            ("live_at_print", lv_all, aux["live_at_print"].loc[W].to_numpy(dtype=bool)),
            ("carry", cr_all, P0.carry.loc[W].to_numpy(dtype=np.float64)),
            ("funding_obs", cn_all, aux["funding_obs"].loc[W].to_numpy(dtype=np.int64)),
            ("settlement_row", st_all, aux["settlement_row"].loc[W].to_numpy(dtype=bool)),
            ("universe_mask", vm & lv_all & ~st_all, aux["universe_mask"].loc[W].to_numpy(dtype=bool))):
        out["frames"][name] = _diff(mine, ref, W, cols0)
    out["instruments_rebuilt_from_hourly_and_funding"] = rebuilt
    out["symbols_with_daily_candles_in_store"] = len(names)
    out["mismatches"] = int(sum(v["mismatches"] for v in out["frames"].values()))
    out["ok"] = out["mismatches"] == 0
    return out


def pseudo_forward(fz: Frozen, tabs: Tables, k: int) -> dict:
    """A check of the FORWARD rules on rows whose answer is known: cut the frozen lane k rows early, extend it
    from the store exactly as a forward run does, and compare the k rows with the frozen lane's own. The only
    cells that may differ are the settlement prints of instruments that stopped trading in those rows (the
    logger books them three rows later — module docstring); everything else is listed as unexplained."""
    idx = fz.panel.prices.index
    if not 1 <= k < CONTINUITY_ROWS:
        raise ValueError(f"k must be between 1 and {CONTINUITY_ROWS - 1}: the store holds the last {CONTINUITY_ROWS} frozen rows")
    last, cut_at = idx[-1], idx[-1 - k]
    vmask = build_universe(fz, Tables(), last).vmask
    cut = fz.panel.window(None, cut_at)
    early = Frozen(cut, fz.manifest_sha256, [str(c) for c in cut.prices.columns if bool(vmask.loc[:cut_at, c].to_numpy().any())],
                   fz.excluded)
    ext = build_extended(early, tabs, last)
    rows, cols = idx[-k:], [str(c) for c in fz.panel.prices.columns]
    P, P0 = ext.panel, fz.panel
    settled = {b["instrument"] for b in ext.info["settlements_booked"]} | \
        {c for c in cols if bool(P0.aux["settlement_row"].loc[rows, c].to_numpy().any())}
    out: dict = {"cut_at": day(cut_at), "rows": [day(rows[0]), day(rows[-1])], "n_rows": k, "frames": {}, "unexplained": [],
                 "settlements_booked": ext.info["settlements_booked"], "first_in_mask_after_the_cut": ext.info["newly_tracked"]}
    for name in ("prices", "carry", "universe_mask", "exec_prices", "exec_prices_alt", "volume_quote", "live_at_print", "funding_obs",
                 "settlement_row"):
        mine = (P.prices if name == "prices" else P.carry if name == "carry" else P.aux[name]).loc[rows, cols].to_numpy()
        ref = (P0.prices if name == "prices" else P0.carry if name == "carry" else P0.aux[name]).loc[rows, cols].to_numpy()
        bad = _bad(mine, ref)
        odd = [(i, j) for i, j in np.argwhere(bad) if not (cols[j] in settled and name in ("exec_prices", "exec_prices_alt", "settlement_row"))]
        out["frames"][name] = {"cells": int(mine.size), "differ": int(bad.sum()), "unexplained": len(odd)}
        out["unexplained"] += [{"frame": name, "row": day(rows[i]), "instrument": cols[j]} for i, j in odd[:25]]
    out["n_unexplained"] = int(sum(v["unexplained"] for v in out["frames"].values()))
    out["ok"] = out["n_unexplained"] == 0
    return out


# ==================================================================================================
# The five arms
# ==================================================================================================
class _Ctx:
    """The small part of `v2.Ctx` that `v2.build_primary` uses, serving the panel it is given."""

    def __init__(self, panel: PanelBundle, cfg: "v2.LaneCfg"):
        self._panel, self._cfg = panel, cfg

    def cfg(self, lane: str) -> "v2.LaneCfg":
        return self._cfg

    def panel(self, lane: str) -> PanelBundle:
        return self._panel

    def universes(self, lane: str, panel: PanelBundle) -> Dict[str, List[str]]:
        return {"ALL": list(panel.prices.columns)}


def cap_gross(w: pd.DataFrame, max_gross: float) -> pd.DataFrame:
    """Row by row: if SUM_i |w_i| > max_gross, scale the row pro rata to exactly max_gross (the cap of
    `portfolio.vol_target`, without its volatility scaling)."""
    arr = w.to_numpy(dtype=np.float64)
    gross = np.abs(arr).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        scale = np.where(gross > max_gross, max_gross / gross, 1.0)
    return pd.DataFrame(arr * scale[:, None], index=w.index, columns=w.columns)


def static_mean(books: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """The plain mean of the member books: no volatility scaling of any kind."""
    acc, first = None, None
    for w in books.values():
        a = w.to_numpy(dtype=np.float64)
        acc, first = (a.copy(), w) if acc is None else (acc + a, first)
    return pd.DataFrame(acc / len(books), index=first.index, columns=first.columns)


def build_arms(sub: PanelBundle, cfg: "v2.LaneCfg", *, enforce_members: bool = True) -> Tuple[Dict[str, pd.DataFrame], dict]:
    """Target frames of the five arms on `sub` (the instruments ever eligible)."""
    spec = next(s for s in registry.primaries() if s.id == PRIMARY_ID)
    target_vol = float(spec.transforms["vol_target"])
    b = v2.build_primary(_Ctx(sub, cfg), spec)                   # members -> speed limit -> ensemble -> vol target, as scored in v2
    declared = [r.id for r in registry.primary_members(spec)]
    kept = [m["rule_id"] for m in b["members"] if m["kept"]]
    info = {"primary": PRIMARY_ID, "declared_members": len(declared), "kept_members": len(kept),
            "dropped_by_speed_limit": [m["rule_id"] for m in b["members"] if not m["kept"]],
            "max_cost_sr": max(float(m["cost_sr"]) for m in b["members"]), "speed_limit_sr": v2.SPEED_LIMIT_SR}
    if enforce_members and (len(declared) != N_MEMBERS or kept != declared):
        raise Incident("SPEED_LIMIT", f"the speed limit kept {len(kept)} of {len(declared)} declared members; the registered book "
                       f"has all {N_MEMBERS} CORE trend rules", info)
    if b["w"] is None:
        raise Incident("SPEED_LIMIT", "every member exceeds the speed limit: there is no book", info)
    books = {rid: size_positions(registry.get(rid).signal(sub), sub, cfg.sigma) for rid in kept}
    fam = {rid: registry.get(rid).family for rid in kept}
    a60 = portfolio.vol_target(portfolio.ensemble(books, fam, sub, target=cfg.sigma), sub, target_vol, max_gross=cfg.max_gross)
    if not _same(a60.to_numpy(), b["w"].to_numpy()):
        raise Incident("ARMS", "the member books rebuilt for the shadows do not reproduce v2.build_primary's frame")
    arms = {"A60": b["w"]}
    for name, win in SHADOW_WINDOWS.items():
        arms[name] = portfolio.vol_target(portfolio.ensemble(books, fam, sub, vol_window=win, target=cfg.sigma), sub, target_vol,
                                          vol_window=win, max_gross=cfg.max_gross)
    arms["A0"] = cap_gross(static_mean(books) * A0_FACTOR, cfg.max_gross)
    rule = registry.get(C252_RULE)
    arms["C252"] = cap_gross(size_positions(rule.signal(sub), sub, cfg.sigma) * C252_FACTOR, cfg.max_gross)
    return {a: arms[a] for a in ARMS}, info


# ==================================================================================================
# Kraken: the listing a row is simulated with, and the price gap
# ==================================================================================================
def _gz_save(path: pathlib.Path, raw: bytes, meta: dict) -> None:
    _atomic_write(path, gzip.compress(raw, compresslevel=6, mtime=0))
    _atomic_write(path.with_name(path.name[: -len(".json.gz")] + ".meta.json"), (json.dumps(meta, indent=1) + "\n").encode())


def fetch_kraken(paths: Paths, http: Http, run_id: str) -> Dict[str, dict]:
    """ONE GET of the instruments endpoint and ONE of the tickers endpoint, saved with URL, UTC fetch time and
    sha256, in the evidence shape `v2_extras.build_kraken` takes."""
    out: Dict[str, dict] = {}
    for key, url, name in (("kraken_instruments", KRAKEN_INSTRUMENTS_URL, "instruments"), ("kraken_tickers", KRAKEN_TICKERS_URL, "tickers")):
        resp = http.get(url)
        if resp.status != 200:
            raise FetchFailed(f"Kraken {name}: HTTP {resp.status}")
        try:
            payload = json.loads(resp.content)
        except ValueError as exc:
            raise FetchFailed(f"Kraken {name}: the response is not JSON ({exc})") from exc
        problem = v2_extras._payload_problem(key, payload)
        if problem:
            raise FetchFailed(f"Kraken {name}: {problem}")
        saved = f"{run_id}_{name}.json.gz"
        meta = {"url": url, "method": "GET", "fetched_utc": resp.fetched_utc, "http_status": resp.status, "bytes": len(resp.content),
                "sha256": sha256_hex(resp.content), "saved_as": saved, "encoding": "gzip of the raw response body, byte for byte",
                "fetched_by": "scripts/factory/forward_crypto.py", "payload_server_time": payload.get("serverTime")}
        _gz_save(paths.kraken / saved, resp.content, meta)
        out[key] = {"payload": payload, "meta": meta, "error": None}
    return out


def kraken_spec(lot_step: float) -> VenueSpec:
    """Prereg §1: 5 bp fee + 2 bp half-spread on every instrument, Kraken's lot precision, 2x cap."""
    return VenueSpec(fee_bp=KRAKEN_FEE_BP, min_fee=0.0, half_spread_bp=KRAKEN_HALF_SPREAD_BP, lot_step=float(lot_step),
                     min_notional=0.0, contract_notional=1.0, financing_long_bp_year=0.0, financing_short_bp_year=0.0,
                     leverage_cap=KRAKEN_LEVERAGE_CAP, venue_id="kraken_derivatives_eea", instrument_class="crypto_perps",
                     currency="USD")


_SPEC_FIELDS = ("fee_bp", "min_fee", "half_spread_bp", "lot_step", "min_notional", "contract_notional",
                "financing_long_bp_year", "financing_short_bp_year", "leverage_cap")


def kraken_terms(cols: Sequence[str], price_panel: PanelBundle, evidence: Mapping[str, dict]) -> Tuple[Dict[str, dict], dict]:
    """Map the book's instruments to Kraken perpetuals with `v2_extras.build_kraken` (its name / listing /
    price-corroboration rule, lot = 10^-contractValueTradePrecision / multiplier) and return, per mapped
    instrument, the terms a simulation needs. The spec used here is v2_extras' own with ONE override: the
    flat 2 bp half-spread of the forward pre-registration."""
    eurusd, _ = v2_extras.reference_eurusd()
    build = v2_extras.build_kraken(list(cols), price_panel.subset(list(cols)), evidence, eurusd)
    summary = {"book_instruments": len(cols), "mapped": len(build.specs), "dropped_by_kind": dict(Counter(d["kind"] for d in build.dropped)),
               "refused": build.refused}
    if build.refused and not build.specs and "no instrument of the book could be mapped" not in str(build.refused):
        raise FetchFailed(f"Kraken venue terms: {build.refused}")
    by_inst = {r["instrument"]: r for r in build.instruments}
    terms: Dict[str, dict] = {}
    for col, spec in build.specs.items():
        mine, theirs = kraken_spec(spec.lot_step), spec.with_overrides(half_spread_bp=KRAKEN_HALF_SPREAD_BP)
        diff = [f for f in _SPEC_FIELDS if getattr(mine, f) != getattr(theirs, f)]
        if diff:
            raise Incident("KRAKEN_TERMS", f"{col}: v2_extras' Kraken spec differs from the pre-registered terms in {diff}",
                           {f: [getattr(mine, f), getattr(theirs, f)] for f in diff})
        terms[str(col)] = {"venue_symbol": by_inst[col]["venue_symbol"], "lot_step": float(spec.lot_step),
                           "multiplier": float(by_inst[col]["multiplier"])}
    return terms, summary


class TermsBook:
    """kraken_terms.jsonl: every distinct listing a ledger row was simulated with, addressed by its sha256."""

    def __init__(self, path: pathlib.Path):
        self.path = path
        self.by_sha: Dict[str, dict] = {}
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    rec = json.loads(line)
                    if sha256_hex(canonical(rec["terms"]).encode()) != rec["sha256"]:
                        raise Incident("KRAKEN_TERMS", f"{path.name}: a record does not hash to its own sha256")
                    self.by_sha[rec["sha256"]] = rec

    @staticmethod
    def sha(terms: Mapping) -> str:
        return sha256_hex(canonical(terms).encode())

    def add(self, terms: Mapping, meta: Mapping) -> str:
        s = self.sha(terms)
        if s not in self.by_sha:
            rec = {"sha256": s, "n_mapped": len(terms), **dict(meta), "terms": dict(terms)}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a") as f:
                f.write(canonical(rec) + "\n")
                f.flush()
                os.fsync(f.fileno())
            self.by_sha[s] = rec
        return s

    def get(self, sha: str) -> dict:
        if sha not in self.by_sha:
            raise Incident("KRAKEN_TERMS", f"the ledger names Kraken terms {sha[:16]}… that are not in {self.path.name}")
        return self.by_sha[sha]["terms"]


def price_gap(tickers: Mapping, terms: Mapping[str, dict], instruments: Iterable[str], binance_px: Mapping[str, Tuple[float, pd.Timestamp]]) -> List[dict]:
    """Kraken mark / last against the latest Binance print in hand. Informational; never used in P&L."""
    by_sym = {t.get("symbol"): t for t in (tickers.get("tickers") or []) if isinstance(t, dict)}
    server = tickers.get("serverTime")
    out = []
    for col in sorted(instruments):
        t = by_sym.get(terms[col]["venue_symbol"]) if col in terms else None
        if t is None or col not in binance_px:
            continue
        px, at = binance_px[col]
        mult = terms[col]["multiplier"]
        mark, last = t.get("markPrice"), t.get("last")
        rec = {"instrument": col, "kraken_symbol": terms[col]["venue_symbol"], "binance_price": px, "binance_print_utc": iso(at),
               "kraken_mark_per_panel_unit": None if mark is None else float(mark) * mult,
               "kraken_last_per_panel_unit": None if last is None else float(last) * mult,
               "kraken_last_time": t.get("lastTime"), "kraken_server_time": server}
        if mark is not None and px and px > 0:
            rec["mark_gap_bp"] = (float(mark) * mult / px - 1.0) * 1e4
        if server:
            rec["seconds_kraken_after_binance"] = (pd.Timestamp(server) - at).total_seconds()
        out.append(rec)
    return out


# ==================================================================================================
# Accounts
# ==================================================================================================
def ideal_venue(cols: Sequence[str]) -> Dict[str, VenueSpec]:
    """`VenueSpec.ideal()` + the lane's base cost, exactly as `v2.account_run` builds it."""
    c, h = v2.cost_series(v2.COSTS[(LANE, "t1")]["base"], cols)
    if not (c == IDEAL_FEE_BP).all() or not (h == 0.0).all():
        raise Incident("PINS", "v2's CRYPTO-PERP base cost is no longer 7 bp per side with no holding cost")
    return {k: VenueSpec.ideal().with_overrides(fee_bp=float(c[k]), financing_long_bp_year=float(h[k]),
                                                financing_short_bp_year=float(h[k])) for k in cols}


@dataclass
class AccountPath:
    """One account over the forward rows: what `simulate_account` returned, reduced to what is ledgered."""
    equity: np.ndarray
    net: np.ndarray
    gross: np.ndarray
    turnover: np.ndarray
    price_pnl: np.ndarray
    carry: np.ndarray
    fees: np.ndarray
    spread: np.ndarray
    cols: List[str]
    notional: np.ndarray                      # (rows, cols): position value after the trade of the row
    counts: dict


def simulate(panel_f: PanelBundle, w_f: pd.DataFrame, venue: Mapping[str, VenueSpec], cfg: "v2.LaneCfg") -> AccountPath:
    """`realism.simulate_account` on the forward rows: the account is flat on the first row and trades into
    the targets of that row at its execution print. 10 % no-trade band, exec timing, missing return 'zero'."""
    T = len(w_f)
    cols = [str(c) for c in w_f.columns if bool((w_f[c].to_numpy() != 0.0).any())]
    if not cols:
        z = np.zeros(T)
        return AccountPath(np.full(T, EQUITY0), z.copy(), z.copy(), z.copy(), z.copy(), z.copy(), z.copy(), z.copy(), [], np.zeros((T, 0)), {})
    sub = panel_f.subset(cols)
    res = realism.simulate_account(sub, w_f[cols], equity0=EQUITY0, venue={c: venue[c] for c in cols}, no_trade_band=v2.BUFFER,
                                   ideal_net=pd.Series(0.0, index=sub.prices.index), **v2.eng_kwargs(sub, cfg))
    mark = sub.aux["exec_prices"].ffill().to_numpy(dtype=np.float64)
    units = res.units.to_numpy(dtype=np.float64)
    notional = np.where(units != 0.0, units * mark, 0.0)
    keep = ("n_orders", "n_trades_skipped_in_band", "n_targets_rounded_to_zero", "n_orders_skipped_min_notional",
            "n_orders_skipped_no_price", "n_prints_leverage_capped", "n_prints_over_cap", "n_missing_price_held",
            "n_missing_carry_held", "ruined_at", "max_margin_utilisation")
    f = res.flows
    return AccountPath(res.equity.to_numpy(), res.net.to_numpy(), res.gross.to_numpy(), res.turnover.to_numpy(), f["price_pnl"].to_numpy(),
                f["carry"].to_numpy(), f["fees"].to_numpy(), f["spread"].to_numpy(), cols, notional,
                {k: res.meta.get(k) for k in keep})


def _fnum(x) -> Optional[float]:
    x = float(x)
    return x if math.isfinite(x) else None


def _row_gross(arr: np.ndarray) -> np.ndarray:
    """SUM |x| of each row over its NON-ZERO cells only, in column order: an instrument that is not in the
    row cannot move a bit of the sum (numpy sums in blocks, so a zero column in between would)."""
    return np.array([float(np.abs(r[r != 0.0]).sum()) for r in arr], dtype=np.float64)


def account_rows(arm: str, account: str, dates: pd.DatetimeIndex, p: AccountPath, target_gross: np.ndarray, held_gross: np.ndarray,
                 frozen_from: Optional[int], extra: Sequence[Mapping]) -> List[dict]:
    out = []
    for j, d in enumerate(dates):
        eq = float(p.equity[j])
        n = p.notional[j] if len(p.cols) else np.zeros(0)
        held = n[n != 0.0]                                       # the positions only (see _row_gross)
        order = [k for k in np.argsort(-np.abs(n), kind="stable")[:10] if n[k] != 0.0]
        tg, hg = float(target_gross[j]), float(held_gross[j])
        row = {"date": day(d), "exec_utc": iso(d + pd.Timedelta(hours=1)), "n": j + 1, "arm": arm, "account": account,
               "state": "FROZEN" if frozen_from is not None and j >= frozen_from else "LIVE",
               "equity": eq, "net_return": _fnum(p.net[j]), "gross_return": _fnum(p.gross[j]),
               "price_pnl": _fnum(p.price_pnl[j]), "funding": _fnum(p.carry[j]), "fees": _fnum(p.fees[j]), "spread": _fnum(p.spread[j]),
               "turnover": _fnum(p.turnover[j]),
               "gross_exposure": _fnum(np.abs(held).sum() / eq) if eq > 0 else None,
               "net_exposure": _fnum(held.sum() / eq) if eq > 0 else None,
               "n_positions": int(len(held)),
               "top_positions": [[p.cols[k], _fnum(n[k] / eq) if eq > 0 else None] for k in order],
               "target_gross": tg, "target_gross_holdable": hg, "unheld_share": _fnum(1.0 - hg / tg) if tg > 0 else None}
        row.update(extra[j])
        out.append(row)
    return out


def _canon_bytes(a: np.ndarray) -> bytes:
    if a.dtype.kind != "f":
        return np.ascontiguousarray(a).tobytes()
    b = np.array(a, dtype="<f8", copy=True)
    b[np.isnan(b)] = np.nan                   # one NaN bit pattern
    b += 0.0                                  # -0.0 -> 0.0
    return np.ascontiguousarray(b).tobytes()


def data_fingerprints(sub: PanelBundle, base_id: str, base_last: pd.Timestamp, base_cols: Set[str],
                      dates: pd.DatetimeIndex) -> Dict[str, str]:
    """sha256 of the data a row can depend on: the frozen lane (named by its manifest hash) plus prices,
    carry, mask and 01:00 prints of every row after it up to the row, for the instruments that had been
    eligible by then — and, for an instrument first eligible after the freeze, its whole history."""
    idx = sub.prices.index
    cols = [str(c) for c in sub.prices.columns]
    mask = sub.aux["universe_mask"].to_numpy(dtype=bool)
    first = np.where(mask.any(axis=0), mask.argmax(axis=0), len(idx))
    n0 = int(idx.searchsorted(base_last, side="right"))
    frames = [sub.prices.to_numpy(dtype=np.float64), sub.carry.to_numpy(dtype=np.float64), mask.astype(np.uint8),
              sub.aux["exec_prices"].to_numpy(dtype=np.float64)]
    out = {}
    for d in dates:
        t = int(idx.get_loc(d))
        sel = np.flatnonzero(first <= t)
        h = hashlib.sha256()
        h.update(canonical({"base": base_id, "base_last_row": iso(base_last), "through": iso(d),
                            "instruments": [cols[j] for j in sel]}).encode())
        if t >= n0:
            for a in frames:
                h.update(_canon_bytes(a[n0: t + 1][:, sel]))
        for j in sel:
            if cols[j] not in base_cols:
                for a in frames:
                    h.update(_canon_bytes(a[:n0, j]))
        out[day(d)] = h.hexdigest()
    return out


# ==================================================================================================
# Performance readings (prereg §3) — nothing before 60 rows
# ==================================================================================================
def read_point(n: int) -> Optional[int]:
    """The reading in force with n rows: 60, 90, 120, ... (None before 60)."""
    return None if n < FIRST_READ else FIRST_READ + READ_STEP * ((n - FIRST_READ) // READ_STEP)


def backtest_net(sub: PanelBundle, w: pd.DataFrame, cfg: "v2.LaneCfg", end: pd.Timestamp) -> pd.Series:
    """The arm's IDEAL account on the history that existed before the forward start, scored on v2's Tier-1
    FULL window: the stream whose n-day outcomes a forward reading is set beside."""
    hist = sub.window(None, end)
    wf = w.loc[hist.prices.index]
    cols = [c for c in wf.columns if bool((wf[c].to_numpy() != 0.0).any())] or list(wf.columns[:1])
    hist = hist.subset(cols)
    res = realism.simulate_account(hist, wf[cols], equity0=EQUITY0, venue=ideal_venue(cols), no_trade_band=v2.BUFFER,
                                   ideal_net=pd.Series(0.0, index=hist.prices.index), **v2.eng_kwargs(hist, cfg))
    return res.net[stats.window_mask(res.net.index, cfg.full)]


def n_day_outcomes(net: np.ndarray, n: int) -> np.ndarray:
    """Compounded return of every window of n consecutive prints."""
    lg = np.log1p(np.asarray(net, dtype=np.float64))
    if len(lg) < n:
        return np.empty(0)
    c = np.r_[0.0, np.cumsum(lg)]
    return np.expm1(c[n:] - c[:-n])


def performance(ideal_net: Mapping[str, np.ndarray], backtests: Mapping[str, pd.Series]) -> dict:
    """Per arm, at the reading in force: realised return, volatility and Sharpe with a stationary-bootstrap
    90 % interval, next to the backtest's distribution of same-length outcomes; at 180 rows the pre-declared
    readings."""
    out: dict = {"arms": {}, "verdicts": None}
    totals180: Dict[str, float] = {}
    sharpe180: Dict[str, float] = {}
    for arm in ARMS:
        x = np.asarray(ideal_net[arm], dtype=np.float64)
        cp = read_point(len(x))
        if cp is None:
            out["arms"][arm] = {"rows": len(x), "reading": None, "statement": f"n < {FIRST_READ}: no performance statement"}
            continue
        y = x[:cp]
        boot = stats.sharpe_ci_bootstrap(y, periods_per_year=PPY, reps=2000, ci=0.90, seed=v2.SEED)
        dist = n_day_outcomes(backtests[arm].to_numpy(), cp)
        total = float(np.prod(1.0 + y) - 1.0)
        q = {f"p{p:02d}": float(np.percentile(dist, p)) for p in (5, 25, 50, 75, 95)} if len(dist) else {}
        out["arms"][arm] = {"rows": len(x), "reading": cp, "total_return": total, "ann_vol": float(y.std(ddof=1) * math.sqrt(PPY)),
                            "sharpe": v2.jsonable(boot["sharpe"]), "sharpe_ci90": [v2.jsonable(boot["lo"]), v2.jsonable(boot["hi"])],
                            "bootstrap": {"reps": boot["reps"], "block": boot["block"], "seed": boot["seed"]},
                            "backtest_outcomes": {"n_windows": int(len(dist)), **q,
                                                  "share_below_realised": float((dist < total).mean()) if len(dist) else None}}
        if len(x) >= VERDICT_ROWS:
            y180 = x[:VERDICT_ROWS]
            d180 = n_day_outcomes(backtests[arm].to_numpy(), VERDICT_ROWS)
            totals180[arm] = float(np.prod(1.0 + y180) - 1.0)
            sharpe180[arm] = float(stats.sharpe_ratio(y180, PPY))
            if arm in ("A60", "C252") and len(d180):
                p05, p25 = float(np.percentile(d180, 5)), float(np.percentile(d180, 25))
                verdict = ("consistent with a positive edge" if sharpe180[arm] > 0 and totals180[arm] > p25
                           else "contradicted" if totals180[arm] < p05 else "undecided")
                out["arms"][arm]["reading_180"] = {"total_return": totals180[arm], "sharpe": sharpe180[arm], "backtest_p05": p05,
                                                   "backtest_p25": p25, "verdict": verdict}
    if all(a in totals180 for a in ("A60", "A30", "A120", "A0")):
        trio = [totals180[a] for a in ("A30", "A60", "A120")]
        spread, edge = max(trio) - min(trio), totals180["A60"] - totals180["A0"]
        out["verdicts"] = {"metric": "total return of the IDEAL account over the first 180 rows", "a60_minus_a0": edge,
                           "spread_a30_a60_a120": spread,
                           "volatility_scaling": "declared noise" if edge < spread else "not declared noise",
                           "sharpe_180": sharpe180}
    return out


# ==================================================================================================
# One step of the logger: arms -> accounts -> immutability -> append
# ==================================================================================================
@dataclass
class KrakenInput:
    evidence: Mapping[str, dict]                 # {"kraken_instruments": {...}, "kraken_tickers": {...}} as v2_extras takes it
    source: dict                                 # where it came from (file names, hashes, fetch times)
    price_panel: Optional[PanelBundle] = None    # the panel whose latest prints corroborate the mapping (default: the run's)


def advance(paths: Paths, panel: PanelBundle, *, cfg: "v2.LaneCfg", start: Optional[pd.Timestamp], now: pd.Timestamp,
            genesis: str, base_id: str, base_last: pd.Timestamp, base_cols: Set[str], kraken: Optional[KrakenInput],
            bt_end: pd.Timestamp, enforce_members: bool = True, dry_run: bool = False, say: Callable = _say) -> dict:
    """Everything after the panel exists. Returns a result dict; raises Incident."""
    run_utc = iso(now)
    led = read_ledger(paths.ledger)
    last_hash = verify_chain(led, genesis)
    mask = panel.aux["universe_mask"]
    ever = [str(c) for c in panel.prices.columns if bool(mask[c].to_numpy().any())]
    sub = panel.subset(ever)
    arms, arm_info = build_arms(sub, cfg, enforce_members=enforce_members)
    idx = sub.prices.index
    fwd = idx[idx >= start] if start is not None else idx[:0]
    fwd_days = [day(d) for d in fwd]
    led_days = sorted({r["date"] for r in led})
    if led_days != fwd_days[: len(led_days)]:
        raise Incident("LEDGER_DATES", f"the ledger holds {len(led_days)} dates ({led_days[:1]}…{led_days[-1:]}) that are not the first "
                       f"forward rows of the panel ({fwd_days[:1]}…{fwd_days[-1:]})")
    expected = {(d, a, acc) for d in led_days for a in ARMS for acc in ACCOUNTS}
    if {(r["date"], r["arm"], r["account"]) for r in led} != expected or len(led) != len(expected):
        raise Incident("LEDGER_DATES", "the ledger does not hold exactly one row per account for each of its dates")
    new_days = fwd_days[len(led_days):]
    result: dict = {"run_utc": run_utc, "panel_last_row": iso(idx[-1]), "forward_start": None if start is None else iso(start),
                    "forward_rows": len(fwd), "ledger_rows_before": len(led), "new_days": new_days, "rows_appended": 0,
                    "arms": arm_info, "instruments_ever_eligible": len(ever)}

    # ---- the Kraken listing: today's for the rows appended today, the recorded one for the rows already there
    book = TermsBook(paths.terms)
    terms_today, sha_today = None, None
    if kraken is not None:
        terms_today, k_summary = kraken_terms(ever, kraken.price_panel or sub, kraken.evidence)
        sha_today = TermsBook.sha(terms_today)
        result["kraken"] = {**k_summary, "terms_sha256": sha_today, "source": kraken.source}
    sha_by_day: Dict[str, str] = {}
    for r in led:
        if r["account"] == "KRAKEN-5K":
            if sha_by_day.setdefault(r["date"], r["venue_sha256"]) != r["venue_sha256"]:
                raise Incident("KRAKEN_TERMS", f"the KRAKEN-5K rows of {r['date']} name different venue terms")
    if new_days and terms_today is None:
        raise Incident("KRAKEN_TERMS", "rows are due but no Kraken listing was supplied")
    for d in new_days:
        sha_by_day[d] = sha_today
    lot: Dict[str, float] = {}
    changes: List[str] = []
    col_pos = {c: j for j, c in enumerate(ever)}
    hold = np.zeros((len(fwd), len(ever)), dtype=bool)
    for i, d in enumerate(fwd_days):
        terms = terms_today if sha_by_day[d] == sha_today and terms_today is not None else book.get(sha_by_day[d])
        for col, t in terms.items():
            if col not in col_pos:
                continue
            hold[i, col_pos[col]] = True
            if col not in lot:
                lot[col] = float(t["lot_step"])
            elif lot[col] != float(t["lot_step"]) and not any(c.startswith(col + ":") for c in changes):
                changes.append(f"{col}: Kraken's lot step is {t['lot_step']} from {d} (first seen {lot[col]}); the account keeps "
                               f"the first-seen step")
    k_cols = [c for c in ever if c in lot]                       # panel order, whatever order the listing came in
    result["kraken_lot_changes"] = changes

    # ---- nothing to simulate yet: say what the books hold now, and stop
    def preview() -> dict:
        out = {}
        for arm in ARMS:
            w = arms[arm].iloc[-1]
            g = float(w.abs().sum())
            held = float(w[[c for c in w.index if terms_today and c in terms_today]].abs().sum()) if terms_today else None
            out[arm] = {"row": day(idx[-1]), "target_gross": g, "target_net": float(w.sum()), "n_targets": int((w != 0).sum()),
                        "kraken_unheld_share": None if held is None or g <= 0 else 1.0 - held / g}
        return out

    result["targets_now"] = preview()
    result["_terms_today"] = terms_today
    result["_targeted_now"] = [c for c in ever if any(float(arms[a][c].iloc[-1]) != 0.0 for a in ARMS)]
    if not len(fwd):
        result["status"] = "NO_FORWARD_ROW_YET"
        return result

    # ---- the ten accounts
    panel_f = sub.window(fwd[0], None)
    data_sha = data_fingerprints(sub, base_id, base_last, base_cols, fwd)
    venue_i = ideal_venue(ever)
    venue_k = {c: kraken_spec(lot[c]) for c in k_cols}
    rows_by_key: Dict[Tuple[str, str, str], dict] = {}
    paths_by: Dict[Tuple[str, str], AccountPath] = {}
    stops: Dict[str, Optional[str]] = {}
    for arm in ARMS:
        w_f = arms[arm].loc[fwd]
        ideal = simulate(panel_f, w_f, venue_i, cfg)
        hit = np.flatnonzero(ideal.equity <= (1.0 - STOP_LOSS) * EQUITY0)
        frozen_from = None
        if len(hit):                                             # prereg §3 stop rule: flat from the row after the breach
            frozen_from = int(hit[0]) + 1
            if frozen_from < len(w_f):
                w_f = w_f.copy()
                w_f.iloc[frozen_from:] = 0.0
                ideal = simulate(panel_f, w_f, venue_i, cfg)
        stops[arm] = None if frozen_from is None else fwd_days[frozen_from - 1]
        w_k = w_f.where(hold, 0.0)
        kr = simulate(panel_f, w_k[k_cols], venue_k, cfg)
        tg, hg = _row_gross(w_f.to_numpy(dtype=np.float64)), _row_gross(w_k.to_numpy(dtype=np.float64))
        for account, p, held_g in (("IDEAL", ideal, tg), ("KRAKEN-5K", kr, hg)):
            extra = [{"venue_sha256": sha_by_day[d] if account == "KRAKEN-5K" else None, "data_sha256": data_sha[d],
                      "backfilled": bool(now >= ts + ONE_DAY), "run_utc": run_utc} for d, ts in zip(fwd_days, fwd)]
            for row in account_rows(arm, account, fwd, p, tg, held_g, frozen_from, extra):
                rows_by_key[(row["date"], arm, account)] = row
            paths_by[(arm, account)] = p
    result["stops"] = stops
    result["account_counts"] = {f"{a}/{acc}": paths_by[(a, acc)].counts for a in ARMS for acc in ACCOUNTS}

    # ---- immutability: every ledgered row must come out of the re-simulation again
    bad, drift = [], 0
    for r in led:
        s = rows_by_key[(r["date"], r["arm"], r["account"])]
        e_ok = abs(s["equity"] - r["equity"]) <= TOL * max(abs(s["equity"]), abs(r["equity"]))
        a, b = 1.0 + (s["net_return"] or 0.0), 1.0 + (r["net_return"] or 0.0)
        n_ok = abs(a - b) <= TOL * max(abs(a), abs(b))
        drift += int(s["data_sha256"] != r["data_sha256"])
        if not (e_ok and n_ok):
            bad.append({"date": r["date"], "arm": r["arm"], "account": r["account"], "ledger_equity": r["equity"],
                        "resimulated_equity": s["equity"], "ledger_net_return": r["net_return"],
                        "resimulated_net_return": s["net_return"], "data_sha256_reproduced": s["data_sha256"] == r["data_sha256"]})
    result["ledger_rows_checked"] = len(led)
    result["data_sha256_not_reproduced"] = drift
    if bad:
        raise Incident("IMMUTABILITY", f"re-simulation does not reproduce {len(bad)} of {len(led)} ledgered rows; first: "
                       f"{bad[0]['date']} {bad[0]['arm']} {bad[0]['account']}. Nothing is appended; the ledger is not rewritten.",
                       {"n_rows_differ": len(bad), "first": bad[0], "examples": bad[:20],
                        "cause_hint": "data_sha256_reproduced false = the data changed; true = the code or the Kraken terms did"})

    # ---- append
    new_rows = [rows_by_key[(d, a, acc)] for d in new_days for a in ARMS for acc in ACCOUNTS]
    chained = chain(new_rows, last_hash)
    if chained and not dry_run:
        book.add(terms_today, {"first_run_utc": run_utc, **(kraken.source if kraken else {})})
        append_ledger(paths.ledger, chained)
        if not paths.fingerprint.exists():
            _atomic_write(paths.fingerprint, (json.dumps({"written_utc": run_utc, "note": "sha256 of the code the first forward row "
                                                          "was computed with", "files": code_fingerprint()}, indent=1) + "\n").encode())
    result["rows_appended"] = 0 if dry_run else len(chained)
    result["would_append"] = len(chained)
    result["last_hash"] = chained[-1]["row_hash"] if chained else last_hash
    result["status"] = "APPENDED" if chained and not dry_run else "DRY_RUN" if dry_run else "NOTHING_TO_APPEND"
    result["held_by_kraken_accounts"] = sorted({c for a in ARMS for c, n in zip(paths_by[(a, "KRAKEN-5K")].cols,
                                                                                   paths_by[(a, "KRAKEN-5K")].notional[-1]) if n != 0.0})
    # ---- performance readings, only when an arm has reached one
    n_rows = len(fwd_days) if not dry_run else len(led_days)
    if read_point(n_rows) is not None:
        ideal_net = {a: np.array([rows_by_key[(d, a, "IDEAL")]["net_return"] or 0.0 for d in fwd_days[:n_rows]]) for a in ARMS}
        result["performance"] = performance(ideal_net, {a: backtest_net(sub, arms[a], cfg, bt_end) for a in ARMS})
    else:
        result["performance"] = {"arms": {a: {"rows": n_rows, "reading": None, "statement": f"n < {FIRST_READ}: no performance statement"}
                                          for a in ARMS}, "verdicts": None}
    return result


# ==================================================================================================
# STATUS.md
# ==================================================================================================
def _pct(x, nd: int = 2) -> str:
    return "–" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{100.0 * x:+.{nd}f} %"


def _num(x, nd: int = 2) -> str:
    return "–" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:,.{nd}f}"


def summarise_ledger(rows: Sequence[Mapping]) -> Dict[Tuple[str, str], dict]:
    out: Dict[Tuple[str, str], dict] = {}
    for arm in ARMS:
        for acc in ACCOUNTS:
            rs = [r for r in rows if r["arm"] == arm and r["account"] == acc]
            if not rs:
                out[(arm, acc)] = {"rows": 0}
                continue
            last = rs[-1]
            costs = sum((r["fees"] or 0.0) + (r["spread"] or 0.0) for r in rs)
            avg_eq = float(np.mean([r["equity"] for r in rs]))
            unheld = [r["unheld_share"] for r in rs if r["unheld_share"] is not None]
            out[(arm, acc)] = {
                "rows": len(rs), "first": rs[0]["date"], "last": last["date"], "equity": last["equity"],
                "return_since_start": last["equity"] / EQUITY0 - 1.0, "gross_exposure": last["gross_exposure"],
                "net_exposure": last["net_exposure"], "n_positions": last["n_positions"],
                "turnover": float(sum(r["turnover"] or 0.0 for r in rs)), "costs_usd": costs,
                "costs_bp_per_year": 1e4 * costs / avg_eq / (len(rs) / PPY) if avg_eq > 0 else None,
                "funding_usd": float(sum(r["funding"] or 0.0 for r in rs)),
                "unheld_share_last": last["unheld_share"], "unheld_share_mean": float(np.mean(unheld)) if unheld else None,
                "state": last["state"], "backfilled_rows": int(sum(bool(r["backfilled"]) for r in rs))}
    return out


def render_status(paths: Paths, pin: Mapping, run: Mapping, rows: Sequence[Mapping], title: str = "FORWARD-CRYPTO v1") -> str:
    s = summarise_ledger(rows)
    adv = run.get("advance") or {}
    L: List[str] = [f"# {title} — status", "",
                    f"Generated {run.get('run_utc')} by `scripts/factory/forward_crypto.py` ({run.get('mode', 'run')}). "
                    f"A paper LOGGER: no orders, no keys, no account; every P&L figure below is hypothetical.", "",
                    f"- Pre-registration sha256 `{pin['sha256'][:16]}…`, frozen {pin['frozen_utc']}; forward-start row "
                    f"**{run.get('forward_start_label')}** 00:00 UTC (first fill at its 01:00 UTC print).",
                    f"- Last run: **{run.get('status')}** — {run.get('message', '')}",
                    (f"- Panel: the frozen lane ({run.get('frozen_last_row')}) with its history cut at **{run.get('panel_last_row')}**; "
                     if str(run.get("mode", "")).startswith("replay") else
                     f"- Panel: frozen through {run.get('frozen_last_row')}, extended through **{run.get('panel_last_row')}**; ")
                    + f"forward rows in the ledger: **{len({r['date'] for r in rows})}** ({len(rows)} ledger rows"
                    + (f", last hash `{rows[-1]['row_hash'][:16]}…`)." if rows else ").")]
    cont = run.get("continuity")
    if cont:
        L.append(f"- Continuity with the frozen lane ({cont['rows'][0]} → {cont['rows'][1]}, {cont['n_rows']} rows rebuilt from "
                 f"Binance REST): **{'EXACT' if cont['ok'] else 'BROKEN'}** — "
                 + ", ".join(f"{k} {v['mismatches']}/{v['cells']}" for k, v in cont["frames"].items()) + " cells differ.")
    inc = sorted(p.name for p in paths.root.glob("INCIDENT_*.json"))
    runs = sorted(paths.runs.glob("*.json")) if paths.runs.exists() else []
    failed = []
    for p in runs:
        try:
            st = json.loads(p.read_text()).get("status")
        except Exception:
            st = "UNREADABLE"
        if st not in ("APPENDED", "NOTHING_TO_APPEND", "NO_FORWARD_ROW_YET"):
            failed.append(f"{p.stem} {st}")
    L += [f"- Runs on file: {len(runs)}; failed or refused: {len(failed)}" + (f" ({'; '.join(failed[-5:])})" if failed else "") + ".",
          f"- Incidents: {len(inc)}" + (f" — {', '.join(inc[-5:])}" if inc else "") + ".", ""]
    L += ["## Accounts", "",
          "Equity in USD (every account starts at 5,597). Exposure is after the last row's trade. Costs = fees + half-spread paid so "
          "far, the one-off entry of the whole book included; bp / year annualises them over the rows so far, so it is far too "
          "high in the first weeks. Operational figures, not performance.", "",
          "| arm | account | rows | equity | since start | gross | net | positions | turnover | costs USD | costs bp/yr | funding USD | "
          "Kraken cannot hold (last / mean) | state |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    for arm in ARMS:
        for acc in ACCOUNTS:
            v = s[(arm, acc)]
            if not v["rows"]:
                L.append(f"| {arm} | {acc} | 0 | {_num(EQUITY0)} | – | – | – | – | – | – | – | – | – | not started |")
                continue
            un = "–" if acc == "IDEAL" else f"{_pct(v['unheld_share_last'], 1)} / {_pct(v['unheld_share_mean'], 1)}".replace("+", "")
            L.append(f"| {arm} | {acc} | {v['rows']} | {_num(v['equity'])} | {_pct(v['return_since_start'])} | {_num(v['gross_exposure'])} | "
                     f"{_num(v['net_exposure'])} | {v['n_positions']} | {_num(v['turnover'])} | {_num(v['costs_usd'])} | "
                     f"{_num(v['costs_bp_per_year'], 0)} | {_num(v['funding_usd'])} | {un} | "
                     f"{'FROZEN (stop rule)' if v['state'] == 'FROZEN' else 'live'} |")
    if any(s[(a, "IDEAL")]["rows"] for a in ARMS):
        L += ["", "Operational parity (KRAKEN-5K minus its IDEAL twin, return since start): "
              + "; ".join(f"{a} {_pct(s[(a, 'KRAKEN-5K')]['return_since_start'] - s[(a, 'IDEAL')]['return_since_start'])}" for a in ARMS
                          if s[(a, "IDEAL")]["rows"]) + "."]
    counts = adv.get("account_counts")
    if counts:
        L += ["", "Orders since the forward start (from this run's re-simulation): "
              + "; ".join(f"{k} {v.get('n_orders', 0)} sent, {v.get('n_trades_skipped_in_band', 0)} inside the band"
                          + (f", {v.get('n_targets_rounded_to_zero', 0)} rounded to zero by the lot size, "
                             f"{v.get('n_prints_leverage_capped', 0)} prints cut by the 2x cap" if k.endswith("KRAKEN-5K") else "")
                          + (f", {v['n_missing_price_held']} held prints without a price" if v.get("n_missing_price_held") else "")
                          for k, v in counts.items()) + "."]
    now_t = adv.get("targets_now")
    if now_t:
        L += ["", "## What the books target on the panel's last row", "",
              "| arm | row | target gross | target net | instruments | share Kraken cannot hold today |", "|---|---|---:|---:|---:|---:|"]
        for arm in ARMS:
            t = now_t[arm]
            L.append(f"| {arm} | {t['row']} | {_num(t['target_gross'], 3)} | {_num(t['target_net'], 3)} | {t['n_targets']} | "
                     f"{_pct(t['kraken_unheld_share'], 1).replace('+', '')} |")
    L += ["", "## Performance (prereg §3: nothing before 60 rows; a reading at 60 and every further 30)", ""]
    perf = adv.get("performance")
    if not perf:                                                 # the run did not get as far as the readings
        perf = {"arms": {a: {"statement": f"n < {FIRST_READ}: no performance statement" if s[(a, "IDEAL")]["rows"] < FIRST_READ
                             else "not recomputed — this run did not complete; the reading in force is in the last complete "
                                  "run's file under runs/"} for a in ARMS}}
    for arm in ARMS:
        p = perf["arms"].get(arm, {})
        if p.get("reading") is None:
            L.append(f"- **{arm}**: {p.get('statement', f'n < {FIRST_READ}: no performance statement')}")
            continue
        b = p["backtest_outcomes"]
        L.append(f"- **{arm}** (IDEAL account, first {p['reading']} rows): return {_pct(p['total_return'])}, volatility "
                 f"{_pct(p['ann_vol'], 1).replace('+', '')} a year, Sharpe {_num(p['sharpe'])} (90 % stationary-bootstrap interval "
                 f"{_num(p['sharpe_ci90'][0])} … {_num(p['sharpe_ci90'][1])}). Backtest, all {b['n_windows']} windows of "
                 f"{p['reading']} rows: 5 % {_pct(b.get('p05'))}, 25 % {_pct(b.get('p25'))}, median {_pct(b.get('p50'))}, 75 % "
                 f"{_pct(b.get('p75'))}, 95 % {_pct(b.get('p95'))}; {_pct(b.get('share_below_realised'), 0).replace('+', '')} of them "
                 f"are below the realised return.")
        r180 = p.get("reading_180")
        if r180:
            L.append(f"  - **Reading at {VERDICT_ROWS} rows: {r180['verdict'].upper()}** (Sharpe {_num(r180['sharpe'])}, return "
                     f"{_pct(r180['total_return'])}; backtest 5 % {_pct(r180['backtest_p05'])}, 25 % {_pct(r180['backtest_p25'])}).")
    v = perf.get("verdicts")
    if v:
        L.append(f"- **Shadows at {VERDICT_ROWS} rows:** A60 − A0 = {_pct(v['a60_minus_a0'])}; spread among A30 / A60 / A120 = "
                 f"{_pct(v['spread_a30_a60_a120'])} → the volatility scaling is **{v['volatility_scaling']}** ({v['metric']}).")
    stops = {a: d for a, d in (adv.get("stops") or {}).items() if d}
    if stops:
        L += ["", "Stop rule (−30 % on the IDEAL account): " + "; ".join(f"**{a} FAILED on {d}**, flat since" for a, d in stops.items()) + "."]
    gap = run.get("price_gap") or []
    if gap:
        L += ["", "## Kraken against Binance (informational, never in P&L)", "",
              f"{run.get('price_gap_basis', '')} Kraken mark from the tickers snapshot against the latest Binance 1h close in the store; "
              f"the two prints are not simultaneous (seconds apart in the last column).", "",
              "| instrument | Kraken | Binance print | Kraken mark | gap bp | Kraken later by (s) |", "|---|---|---:|---:|---:|---:|"]
        for g in gap[:40]:
            L.append(f"| {g['instrument']} | {g['kraken_symbol']} | {g['binance_price']:.6g} | "
                     f"{(g.get('kraken_mark_per_panel_unit') or float('nan')):.6g} | {_num(g.get('mark_gap_bp'), 1)} | "
                     f"{_num(g.get('seconds_kraken_after_binance'), 0)} |")
        if len(gap) > 40:
            L.append(f"| … {len(gap) - 40} more in runs/{run.get('run_id')}.json | | | | | |")
    notes = list((run.get("panel") or {}).get("notices") or []) + list((run.get("binance") or {}).get("notices") or []) \
        + list(adv.get("kraken_lot_changes") or []) + list(run.get("notices") or [])
    if notes:
        L += ["", "## Notices", ""] + [f"- {n}" for n in notes]
    return "\n".join(L) + "\n"


# ==================================================================================================
# Commands
# ==================================================================================================
@contextlib.contextmanager
def _lock(paths: Paths):
    paths.root.mkdir(parents=True, exist_ok=True)
    f = open(paths.root / ".lock", "w")
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            print(f"another forward_crypto process holds {paths.root / '.lock'}: nothing done", file=sys.stderr, flush=True)
            raise SystemExit(EXIT_BUSY) from exc
        yield
    finally:
        f.close()


def _write_run(paths: Paths, run: dict) -> pathlib.Path:
    p = paths.runs / f"{run['run_id']}.json"
    _atomic_write(p, (json.dumps(v2.jsonable(run), indent=1, default=str) + "\n").encode())
    return p


def _finish(paths: Paths, pin: Mapping, run: dict, title: str = "FORWARD-CRYPTO v1") -> None:
    _write_run(paths, run)
    rows = []
    try:
        rows = read_ledger(paths.ledger)
    except Incident:
        pass
    _atomic_write(paths.status, render_status(paths, pin, run, rows, title).encode())


def _incident(paths: Paths, run: dict, exc: Incident) -> None:
    rec = {"utc": run["run_utc"], "run_id": run["run_id"], "kind": exc.kind, "message": str(exc), "detail": exc.detail,
           "action": "nothing was appended; the ledger was not rewritten"}
    _atomic_write(paths.root / f"INCIDENT_{run['run_id']}.json", (json.dumps(v2.jsonable(rec), indent=1, default=str) + "\n").encode())
    run.update({"status": f"INCIDENT:{exc.kind}", "message": str(exc), "exit_code": EXIT_INCIDENT})


def latest_binance_prints(tabs: Tables, cols: Iterable[str]) -> Dict[str, Tuple[float, pd.Timestamp]]:
    out = {}
    for c in cols:
        arr = tabs.data["1h"].get(CB.base_symbol(c))
        if arr is None:
            continue
        arr = arr[arr[:, 3] > 0]
        if len(arr):
            out[c] = (float(arr[-1, 1]), from_ms(arr[-1, 0] + HOUR))
    return out


def cmd_run(now: Optional[pd.Timestamp] = None, transport: Optional[Callable] = None, paths: Optional[Paths] = None,
            fz: Optional[Frozen] = None, cfg: Optional["v2.LaneCfg"] = None, enforce_members: bool = True,
            http: Optional[Http] = None, say: Callable = _say) -> int:
    """The daily job. Every argument exists for the tests; the command line passes none."""
    paths = paths or Paths(FWD)
    now = now or utc_now()
    with _lock(paths):
        run: dict = {"run_id": stamp(now), "run_utc": iso(now), "mode": "run", "status": "STARTED", "exit_code": EXIT_OK,
                     "forward_start_label": None}
        pin = load_pin()
        t0 = time.time()
        try:
            pins = check_pins() if fz is None else {"pin": pin, "hashes": {}}
            run["pins"], run["code_sha256"] = pins["hashes"], code_fingerprint()
            run["forward_start_label"] = day(forward_start_label(pin["frozen_utc"]))
            genesis = genesis_hash(pin)
            verify_chain(read_ledger(paths.ledger), genesis)
            if paths.fingerprint.exists():
                first = json.loads(paths.fingerprint.read_text())["files"]
                changed = sorted(f for f, h in run["code_sha256"].items() if first.get(f) != h)
                if changed:
                    run.setdefault("notices", []).append(f"code changed since the first forward row was written: {changed} "
                                                         f"(the immutability check decides whether that matters)")
            fz = fz or load_frozen()
            run["frozen_last_row"] = day(fz.last_row)
            tabs = Tables.load(paths)
            L = last_appendable_row(now)
            http = http or Http(transport)
            if tabs.complete_through is None or L > tabs.complete_through:
                say(f"[run] fetching Binance through row {day(L)} …")
                run["binance"] = fetch_binance(paths, fz, tabs, http, now, run["run_id"], say)
            else:
                run["binance"] = {"requests": 0, "note": f"the store is complete through {day(tabs.complete_through)}: nothing to fetch"}
            L = max(min(L, tabs.complete_through), fz.last_row)
            ext = build_extended(fz, tabs, L)
            run["panel"] = ext.info
            run["panel_last_row"] = day(ext.panel.prices.index[-1])
            cont = continuity_check(fz, tabs, ext.uni)
            run["continuity"] = cont
            if not cont["ok"]:
                raise Incident("CONTINUITY", f"rebuilding the last {cont['n_rows']} frozen rows from Binance REST gives "
                               f"{cont['mismatches']} cells that differ from the frozen lane", cont)
            say(f"[run] panel {day(ext.panel.prices.index[0])} → {run['panel_last_row']} ({ext.info['extension_rows']} extension rows); "
                f"continuity over {cont['n_rows']} rows exact")
            start = forward_start_row(ext.panel.prices.index, pin["frozen_utc"])
            if start is not None and start != forward_start_label(pin["frozen_utc"]):
                raise Incident("FORWARD_START", f"the first row after the freeze is {start}, not the next UTC midnight")
            led_days = {r["date"] for r in read_ledger(paths.ledger)}
            fwd_days = [day(d) for d in ext.panel.prices.index if start is not None and d >= start]
            kraken = None
            if not fwd_days or any(d not in led_days for d in fwd_days):
                ev = fetch_kraken(paths, http, run["run_id"])
                kraken = KrakenInput(ev, {k: {x: v["meta"][x] for x in ("url", "fetched_utc", "sha256", "saved_as")} for k, v in ev.items()})
            man_cols = set(fz.panel.meta["universe_groups"]["EVER_IN_MASK"])
            adv = advance(paths, ext.panel, cfg=cfg or v2.LANES[LANE], start=start, now=now, genesis=genesis,
                          base_id=f"{LANE}:manifest:{fz.manifest_sha256}", base_last=fz.last_row,
                          base_cols={ext.uni.rename[c] for c in man_cols}, kraken=kraken, bt_end=fz.last_row,
                          enforce_members=enforce_members, say=say)
            run["advance"] = adv
            run["status"] = adv["status"]
            if adv.get("data_sha256_not_reproduced"):
                run.setdefault("notices", []).append(f"{adv['data_sha256_not_reproduced']} ledgered rows carry a data fingerprint that "
                                                     f"the rebuilt panel no longer gives, although their equity and return are "
                                                     f"reproduced: a cell that no account depended on has changed")
            terms_now, targeted = adv.pop("_terms_today", None), adv.pop("_targeted_now", [])
            if kraken is not None and terms_now is not None:
                held = adv.get("held_by_kraken_accounts") or []
                basis = "Instruments held by a KRAKEN-5K account after the last row's trade."
                if not held:
                    held = [c for c in targeted if c in terms_now]
                    basis = ("No KRAKEN-5K position exists yet: the Kraken-listed instruments the five books target on the "
                             "panel's last row.")
                run["price_gap"] = price_gap(kraken.evidence["kraken_tickers"]["payload"], terms_now, held,
                                             latest_binance_prints(tabs, held))
                run["price_gap_basis"] = basis
            if adv["status"] == "NO_FORWARD_ROW_YET":
                run["message"] = (f"0 forward rows: the panel is current through {run['panel_last_row']} and the forward-start row "
                                  f"{run['forward_start_label']} has no 01:00 print yet; nothing appended")
            elif adv["status"] == "APPENDED":
                run["message"] = (f"appended {adv['rows_appended']} rows for {', '.join(adv['new_days'])}; "
                                  f"{adv['ledger_rows_checked']} earlier rows reproduced")
            else:
                run["message"] = (f"the ledger already holds every row through {run['panel_last_row']}; "
                                  f"{adv['ledger_rows_checked']} rows reproduced; nothing appended")
        except Incident as exc:
            _incident(paths, run, exc)
        except (FetchFailed, EngineRefused, v2.Refused) as exc:
            run.update({"status": f"FAILED:{type(exc).__name__}", "message": f"{exc} — nothing appended; the next run backfills",
                        "exit_code": EXIT_FETCH})
        except Exception as exc:                                 # a bug is a failed run on file, never a silent one
            run.update({"status": f"CRASHED:{type(exc).__name__}", "message": f"{exc} — nothing appended",
                        "traceback": traceback.format_exc()[-4000:], "exit_code": EXIT_CRASH})
        for k in ("_terms_today", "_targeted_now"):
            (run.get("advance") or {}).pop(k, None)
        run["seconds"] = round(time.time() - t0, 1)
        _finish(paths, pin, run)
        say(f"[run] {run['status']}: {run.get('message', '')} ({run['seconds']} s)")
        return int(run["exit_code"])


def frozen_kraken_evidence() -> KrakenInput:
    """The Kraken payloads the v2 realism pass saved on 2026-11-10 (no network): what `replay` simulates with."""
    ev = v2_extras.real_evidence(allow_network=False)
    for k in ("kraken_instruments", "kraken_tickers"):
        if ev[k].get("payload") is None:
            raise FetchFailed(f"replay needs the saved Kraken evidence under {v2_extras.EVIDENCE_DIR}: {ev[k].get('error')}")
    src = {k: {"path": ev[k]["meta"].get("path"), "fetched_utc": ev[k]["meta"].get("fetched_utc"), "sha256": ev[k]["meta"].get("sha256")}
           for k in ("kraken_instruments", "kraken_tickers")}
    return KrakenInput(ev, {**src, "note": "replay: the listing of 2026-11-10 is applied to every replayed day"})


def replay_step(paths: Paths, panel: PanelBundle, *, cfg: "v2.LaneCfg", start: pd.Timestamp, asof: pd.Timestamp, pin: Mapping,
                kraken: KrakenInput, base_id: str, enforce_members: bool = True, say: Callable = _say) -> dict:
    """ONE simulated daily run: the history ends at `asof`, the clock reads asof 01:10 UTC."""
    now = asof + pd.Timedelta(hours=1) + FINALITY_MARGIN
    run: dict = {"run_id": stamp(now), "run_utc": iso(now), "mode": f"replay (pretend forward start {day(start)}, history cut at "
                 f"{day(asof)})", "status": "STARTED", "exit_code": EXIT_OK, "forward_start_label": day(start),
                 "frozen_last_row": day(panel.prices.index[-1])}
    cut = panel.window(None, asof)
    run["panel_last_row"] = day(cut.prices.index[-1])
    if kraken.price_panel is None:
        kraken = KrakenInput(kraken.evidence, kraken.source, panel)        # the listing snapshot is corroborated by the panel's latest prints
    t0 = time.time()
    try:
        idx = cut.prices.index
        st = idx[int(idx.searchsorted(start, side="left"))] if start <= idx[-1] else None
        before = panel.prices.index[max(int(panel.prices.index.searchsorted(start, side="left")) - 1, 0)]
        adv = advance(paths, cut, cfg=cfg, start=st, now=now, genesis=genesis_hash(pin, f"replay:{day(start)}"), base_id=base_id,
                      base_last=panel.prices.index[-1], base_cols={str(c) for c in panel.prices.columns},
                      kraken=kraken, bt_end=before, enforce_members=enforce_members, say=say)
        adv.pop("_terms_today", None), adv.pop("_targeted_now", None)
        run["advance"], run["status"] = adv, adv["status"]
        run["message"] = f"{adv['rows_appended']} rows appended for {len(adv['new_days'])} day(s); {adv.get('ledger_rows_checked', 0)} " \
                         f"earlier rows reproduced"
    except Incident as exc:
        _incident(paths, run, exc)
    run["seconds"] = round(time.time() - t0, 1)
    _finish(paths, pin, run, title="FORWARD-CRYPTO v1 — REPLAY (not the forward ledger)")
    say(f"[replay] history to {day(asof)}: {run['status']} — {run.get('message', '')} ({run['seconds']} s)")
    return run


def replay_sanity(paths: Paths, start: pd.Timestamp) -> Optional[dict]:
    """The replayed A60 IDEAL account against v2's own Tier-1 base stream of P.CRYPTO.TREND on the same dates."""
    ref_p = v2.FACT / "runs" / "v2" / "tier1_net" / f"{PRIMARY_ID}.parquet"
    rows = [r for r in read_ledger(paths.ledger) if r["arm"] == "A60" and r["account"] == "IDEAL"]
    if not ref_p.exists() or len(rows) < 3:
        return None
    ref = pd.read_parquet(ref_p)["base"]
    mine = pd.Series([r["net_return"] or 0.0 for r in rows], index=pd.DatetimeIndex([pd.Timestamp(r["date"], tz="UTC") for r in rows]))
    ref = ref.reindex(mine.index)
    if ref.isna().any():
        return None
    gap = (mine - ref).to_numpy()
    k = min(60, len(gap) - 1)
    out = {"dates": [day(mine.index[0]), day(mine.index[-1])], "rows": len(mine), "replay_total_return": float((1 + mine).prod() - 1),
           "v2_base_total_return": float((1 + ref).prod() - 1), "replay_total_from_row_2": float((1 + mine.iloc[1:]).prod() - 1),
           "v2_base_total_from_row_2": float((1 + ref.iloc[1:]).prod() - 1),
           "corr": float(np.corrcoef(mine.to_numpy()[1:], ref.to_numpy()[1:])[0, 1]) if len(gap) > 3 else None,
           "max_abs_daily_gap": float(np.abs(gap).max()), "max_abs_daily_gap_after_row_1": float(np.abs(gap[1:]).max()),
           f"max_abs_daily_gap_after_row_{k}": float(np.abs(gap[k:]).max()), "first_row_v2_net": float(ref.iloc[0]),
           "reading": "row 1: the replayed account is flat until its first 01:00 fill while v2's long-running account is invested; "
                      "row 2 carries the cost of entering the whole book at once; after that the two differ only while an "
                      "instrument has not traded since the opening (the 10 % band leaves v2's account anywhere inside the band)"}
    _atomic_write(paths.root / "REPLAY_SANITY.json", (json.dumps(out, indent=1) + "\n").encode())
    return out


def cmd_replay(start: str, out: str, asof: Optional[str] = None, daily: bool = False, say: Callable = _say) -> int:
    paths = Paths(pathlib.Path(out).resolve())
    if paths.root == FWD.resolve() or FWD.resolve() in paths.root.parents:
        raise SystemExit("replay never writes into the forward directory: choose a scratch --out")
    pins = check_pins()
    fz = load_frozen()
    panel = fz.panel
    idx = panel.prices.index
    s = pd.Timestamp(start, tz="UTC")
    a = pd.Timestamp(asof, tz="UTC") if asof else idx[-1]
    if s not in idx or a not in idx:
        raise SystemExit(f"--start and --asof must be rows of the frozen lane ({day(idx[0])} … {day(idx[-1])}): replay needs no network")
    kraken = frozen_kraken_evidence()
    base_id = f"{LANE}:manifest:{fz.manifest_sha256}"
    code = EXIT_OK
    with _lock(paths):
        led = read_ledger(paths.ledger)
        done = max((pd.Timestamp(r["date"], tz="UTC") for r in led), default=None)
        days = [a]
        if daily:
            first = s if done is None else done + ONE_DAY
            days = list(idx[(idx >= first) & (idx <= a)]) or [a]
        for d in days:
            run = replay_step(paths, panel, cfg=v2.LANES[LANE], start=s, asof=d, pin=pins["pin"], kraken=kraken, base_id=base_id, say=say)
            code = max(code, int(run["exit_code"]))
            if code:
                break
        san = replay_sanity(paths, s)
        if san:
            say(f"[replay] A60 IDEAL vs v2 tier1 base, {san['dates'][0]} → {san['dates'][1]} ({san['rows']} rows): total "
                f"{san['replay_total_return']:+.4%} vs {san['v2_base_total_return']:+.4%}; from row 2 {san['replay_total_from_row_2']:+.4%} "
                f"vs {san['v2_base_total_from_row_2']:+.4%}; corr {san['corr']:.6f}; max |daily gap| after row 1 "
                f"{san['max_abs_daily_gap_after_row_1']:.2e}")
    return code


def cmd_status(verify: bool = False, verify_store_flag: bool = False, pseudo: int = 0, say: Callable = _say) -> int:
    paths = Paths(FWD)
    pin = load_pin()
    code = EXIT_OK
    try:
        rows = read_ledger(paths.ledger)
        last = verify_chain(rows, genesis_hash(pin))
        say(f"ledger: {len(rows)} rows, {len({r['date'] for r in rows})} forward days; hash chain OK (last {last[:16]}…)")
    except Incident as exc:
        say(f"LEDGER INCIDENT [{exc.kind}]: {exc}")
        return EXIT_INCIDENT
    runs = sorted(paths.runs.glob("*.json")) if paths.runs.exists() else []
    if runs:
        last_run = json.loads(runs[-1].read_text())
        say(f"last run {last_run.get('run_utc')}: {last_run.get('status')} — {last_run.get('message', '')}")
    if paths.status.exists():
        say("")
        say(paths.status.read_text())
    else:
        say("no STATUS.md yet: `run` has not been executed")
    if verify_store_flag:
        v = verify_store(paths)
        say(f"store: {v['runs']} runs, {v['requests']} raw responses re-hashed and re-parsed: {'OK' if v['ok'] else v['problems'][:5]}")
        code = code if v["ok"] else EXIT_INCIDENT
    if pseudo:
        res = pseudo_forward(load_frozen(), Tables.load(paths), pseudo)
        say(f"pseudo-forward: the frozen lane cut at {res['cut_at']} and extended by the forward rules over {res['rows'][0]} → "
            f"{res['rows'][1]} ({res['n_rows']} rows): " + ", ".join(f"{k} {v['differ']}" for k, v in res["frames"].items())
            + f" cells differ from the frozen lane; settlement prints booked three rows later: "
            f"{[(b['instrument'], b['last_traded_row'], b['booked_on']) for b in res['settlements_booked']]}; unexplained: "
            f"{res['n_unexplained']} {res['unexplained'][:5] if res['unexplained'] else ''}")
        code = code if res["ok"] else EXIT_INCIDENT
    if verify:
        try:
            check_pins()
            fz = load_frozen()
            tabs = Tables.load(paths)
            last_day = max((pd.Timestamp(r["date"], tz="UTC") for r in rows), default=fz.last_row)
            L = max(min(last_day, tabs.complete_through or fz.last_row), fz.last_row)
            ext = build_extended(fz, tabs, L)
            cont = continuity_check(fz, tabs, ext.uni)
            say(f"continuity ({cont['rows'][0]} → {cont['rows'][1]}): {'EXACT' if cont['ok'] else str(cont['mismatches']) + ' cells differ'}")
            adv = advance(paths, ext.panel, cfg=v2.LANES[LANE], start=forward_start_row(ext.panel.prices.index, pin["frozen_utc"]),
                          now=utc_now(), genesis=genesis_hash(pin), base_id=f"{LANE}:manifest:{fz.manifest_sha256}",
                          base_last=fz.last_row, base_cols={ext.uni.rename[c] for c in fz.panel.meta["universe_groups"]["EVER_IN_MASK"]},
                          kraken=None, bt_end=fz.last_row, dry_run=True, say=say)
            say(f"re-simulation: {adv.get('ledger_rows_checked', 0)} ledgered rows reproduced within {TOL:g}; "
                f"{adv.get('data_sha256_not_reproduced', 0)} data fingerprints differ")
            code = code if cont["ok"] else EXIT_INCIDENT
        except Incident as exc:
            say(f"VERIFY FAILED [{exc.kind}]: {exc}")
            code = EXIT_INCIDENT
    return code


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="FORWARD-CRYPTO v1 — forward paper logger (no orders, public market data only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="the daily job: extend the panel, simulate, append the new ledger rows")
    st = sub.add_parser("status", help="print the ledger's state (no network, no write)")
    st.add_argument("--verify", action="store_true", help="rebuild the panel from the store and re-simulate every ledgered row")
    st.add_argument("--verify-store", action="store_true", help="re-hash and re-parse every stored raw response")
    st.add_argument("--pseudo-forward", type=int, default=0, metavar="K",
                    help="cut the frozen lane K rows early, extend it from the store by the forward rules, compare with the frozen rows")
    rp = sub.add_parser("replay", help="the whole pipeline with a pretend forward start in the past, into a scratch directory")
    rp.add_argument("--start", required=True, help="pretend forward-start row, YYYY-MM-DD")
    rp.add_argument("--out", required=True, help="scratch directory (never the forward directory)")
    rp.add_argument("--asof", help="cut the history at this row (default: the frozen lane's last row)")
    rp.add_argument("--daily", action="store_true", help="one simulated run per day from the last replayed day to --asof")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return cmd_run()
    if a.cmd == "status":
        return cmd_status(a.verify, a.verify_store, a.pseudo_forward)
    return cmd_replay(a.start, a.out, a.asof, a.daily)


if __name__ == "__main__":
    sys.exit(main())
