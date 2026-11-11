"""Shared helpers of the factory data layer (builder B3).

Nothing here imports the engine or the strategy library. Everything that touches the network goes
through `http_get`, which sends one honest generic User-Agent, rate-limits per host and never prints
request headers (credentials, when a source needs them, travel in headers only).

All clock times written by this package are UTC, produced by `utc_now()` (never local time).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import requests

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "research" / "factory" / "data"
RAW = DATA / "raw"

# The requests library's own default User-Agent ("python-requests/<version>") — an honest, generic
# script identifier. (A custom product string was reset by FRED's front end on 2026-11-10; the library
# default is accepted everywhere we fetch. No browser impersonation anywhere in this package.)
USER_AGENT = requests.utils.default_user_agent()

_session_local = threading.local()
_host_lock = threading.Lock()
_host_next: Dict[str, float] = {}
_log_lock = threading.Lock()

# minimum seconds between two requests to the same host (polite defaults; <= 3 req/s for the
# statistical agencies and Alpaca, as the task brief requires)
HOST_MIN_INTERVAL = {
    "fred.stlouisfed.org": 0.40,
    "data-api.ecb.europa.eu": 0.40,
    "stats.bis.org": 0.40,
    "data.bis.org": 0.40,
    "data.alpaca.markets": 0.40,
    "fapi.binance.com": 0.05,       # the weight budget is enforced separately from the response header
    "api.binance.com": 0.05,
    "data.binance.vision": 0.0,     # archive CDN: concurrency-limited by the worker pool
    "s3-ap-northeast-1.amazonaws.com": 0.05,
}


def utc_now() -> str:
    """ISO-8601 UTC timestamp with a trailing Z (seconds resolution)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_ms() -> int:
    return int(time.time() * 1000)


def session() -> requests.Session:
    s = getattr(_session_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
        _session_local.s = s
    return s


def _throttle(host: str) -> None:
    gap = HOST_MIN_INTERVAL.get(host, 0.34)
    if gap <= 0:
        return
    with _host_lock:
        now = time.monotonic()
        t = max(now, _host_next.get(host, 0.0))
        _host_next[host] = t + gap
    wait = t - now
    if wait > 0:
        time.sleep(wait)


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, body: str = ""):
        super().__init__(f"HTTP {status} for {url} :: {body[:300]}")
        self.status = status
        self.url = url
        self.body = body


def http_get(url: str, *, params: Optional[dict] = None, headers: Optional[dict] = None,
             timeout: float = 60.0, tries: int = 6, ok_status: Iterable[int] = (200,),
             fatal_status: Iterable[int] = (400, 401, 403, 404)) -> requests.Response:
    """GET with per-host throttling and exponential backoff on 418/429/5xx/network errors.

    A status in `fatal_status` raises HttpError at once (no point retrying a missing file).
    """
    host = url.split("/")[2]
    delay = 1.5
    last: Optional[BaseException] = None
    for attempt in range(tries):
        _throttle(host)
        try:
            r = session().get(url, params=params, headers=headers, timeout=timeout)
        except requests.RequestException as e:      # network hiccup: back off and retry
            last = e
            time.sleep(delay)
            delay = min(delay * 2, 60)
            continue
        if r.status_code in ok_status:
            return r
        if r.status_code in fatal_status:
            raise HttpError(r.status_code, r.url, r.text)
        last = HttpError(r.status_code, r.url, r.text)
        ra = r.headers.get("Retry-After")
        wait = float(ra) if (ra and ra.replace(".", "", 1).isdigit()) else delay
        time.sleep(min(max(wait, delay), 300))
        delay = min(delay * 2, 60)
    raise RuntimeError(f"GET failed after {tries} tries: {url} :: {last!r}")


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


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_bytes(path, json.dumps(obj, indent=1, sort_keys=False, default=str).encode())


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, sort_keys=False, default=str) + "\n"
    with _log_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)


def read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue            # a torn last line after a crash is ignored, never fatal
    return out


def save_raw(source: str, relname: str, content: bytes, url: str, *, extra: Optional[dict] = None) -> Path:
    """Write a raw download under raw/<source>/<relname> and append to raw/<source>/_fetch_log.jsonl
    {path, url, fetched_utc, bytes, sha256}. The URL must never contain a credential."""
    path = RAW / source / relname
    atomic_write_bytes(path, content)
    rec = {"path": str(path.relative_to(DATA)), "url": url, "fetched_utc": utc_now(),
           "bytes": len(content), "sha256": sha256_bytes(content)}
    if extra:
        rec.update(extra)
    append_jsonl(RAW / source / "_fetch_log.jsonl", rec)
    return path


def fetch_log(source: str) -> Dict[str, dict]:
    """Last fetch-log record per raw path (relative to the data dir)."""
    out: Dict[str, dict] = {}
    for rec in read_jsonl(RAW / source / "_fetch_log.jsonl"):
        out[rec["path"]] = rec
    return out


def load_env_value(key: str) -> str:
    """Read one KEY=VALUE from <repo>/.env, stripping surrounding quotes. Never log the value."""
    env = REPO / ".env"
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            return v
    raise KeyError(f"{key} not found in .env")
