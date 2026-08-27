#!/usr/bin/env python3
"""T23 DATA COLLECTION -- the survivorship-complete Binance USD-M perp panel, cached on disk.

WHY THIS FILE EXISTS AT ALL
---------------------------
T21 (`research/trading_bot/NONDIRECTIONAL_INCOME_SHORTLIST.md`) pulled 1,074,296 funding prints
from the live REST API and DISCARDED them. That is an AGENTS.md violation ("Preserve raw data and
point-in-time observations. Derived tables must be reproducible."). This module pulls from the
PUBLIC HISTORICAL DUMPS at data.binance.vision, writes every raw archive to disk unmodified, and
records a sha256 manifest so the panel below it is reproducible byte for byte.

WHY data.binance.vision AND NOT THE REST API
--------------------------------------------
The live REST API is reachable only through `exchangeInfo`, whose symbol list contains ONLY the
perps that exist TODAY. Building a universe from it is the exact survivorship leakage that makes
T21's +2.20pp untrustworthy: every perp that was liquid in 2021 and is delisted in 2026 is
invisible, and T21 measured that the condemned pool's trailing funding is median -23.6%/yr. The
bucket listing at s3-ap-northeast-1.amazonaws.com/data.binance.vision enumerates 920 fundingRate
symbol folders INCLUDING delisted names (LUNAUSDT, FTTUSDT, SRMUSDT), so the universe is
constructed from the DUMP INDEX and never from a live endpoint.

WHAT IS COLLECTED, PER SYMBOL-MONTH
-----------------------------------
  fundingRate/{SYM}/{SYM}-fundingRate-YYYY-MM.zip      the 8h (or 4h) funding prints
  klines/{SYM}/1d/{SYM}-1d-YYYY-MM.zip                 perp OHLCV -- close AND quote volume
  premiumIndexKlines/{SYM}/1d/{SYM}-1d-YYYY-MM.zip     the perp premium over the spot index

The quote volume is what the POINT-IN-TIME liquidity screen consumes: the screen for month m may
read only bars dated strictly before month m begins. The premium index is what carries the basis
mark-to-market -- the leg T21 omitted entirely by measuring realised funding alone.

USAGE
    python3 scripts/trading_bot/t23_collect.py enumerate
    python3 scripts/trading_bot/t23_collect.py download [--workers N] [--limit N]
    python3 scripts/trading_bot/t23_collect.py panel
    python3 scripts/trading_bot/t23_collect.py verify
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
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

BUCKET_LIST = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DUMP = "https://data.binance.vision"
FUNDING_PREFIX = "data/futures/um/monthly/fundingRate/"

CACHE = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "t23_cache"
RAW = CACHE / "raw"
UNIVERSE = CACHE / "universe.json"
MANIFEST = CACHE / "manifest.jsonl"
PANEL = CACHE / "panel"

USER_AGENT = "meme-research-t23/1.0 (public-dump reader; no account, no order)"


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

_LOCAL = threading.local()


def _session():
    """One keep-alive session per worker thread. Without connection reuse every one of the 64,341
    fetches pays a fresh TLS handshake, which measured 13 files/s; with it, ~10x that."""
    s = getattr(_LOCAL, "s", None)
    if s is None:
        s = requests.Session()
        s.headers["User-Agent"] = USER_AGENT
        s.mount("https://", requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=4))
        _LOCAL.s = s
    return s


def _get(url: str, *, retries: int = 4, timeout: int = 60) -> bytes | None:
    """Return the body, or None on a genuine 404. Any other failure raises after retries."""
    last = None
    for attempt in range(retries):
        try:
            resp = _session().get(url, timeout=timeout)
            if resp.status_code == 404:
                return None
            if resp.status_code == 200:
                return resp.content
            last = RuntimeError(f"HTTP {resp.status_code}")
        except Exception as exc:  # noqa: BLE001 -- network is the whole point
            last = exc
            _LOCAL.s = None
        time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError(f"GET failed after {retries} attempts: {url}: {last!r}")


# ---------------------------------------------------------------------------
# enumerate
# ---------------------------------------------------------------------------

def cmd_enumerate(_args) -> int:
    """List every fundingRate key in the bucket. The universe IS this listing."""
    CACHE.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    marker = ""
    pages = 0
    while True:
        url = f"{BUCKET_LIST}?prefix={urllib.parse.quote(FUNDING_PREFIX, safe='')}"
        if marker:
            url += f"&marker={urllib.parse.quote(marker, safe='')}"
        body = _get(url)
        if body is None:
            raise RuntimeError("bucket listing 404")
        text = body.decode("utf-8")
        page_keys = re.findall(r"<Key>([^<]+)</Key>", text)
        keys.extend(page_keys)
        pages += 1
        if "<IsTruncated>true</IsTruncated>" in text and page_keys:
            marker = page_keys[-1]
        else:
            break
    zips = [k for k in keys if k.endswith(".zip")]
    universe: dict[str, list[str]] = {}
    pat = re.compile(re.escape(FUNDING_PREFIX) + r"([^/]+)/\1-fundingRate-(\d{4}-\d{2})\.zip$")
    unmatched = []
    for k in zips:
        m = pat.match(k)
        if not m:
            unmatched.append(k)
            continue
        universe.setdefault(m.group(1), []).append(m.group(2))
    for sym in universe:
        universe[sym] = sorted(universe[sym])
    out = {
        "source": BUCKET_LIST,
        "prefix": FUNDING_PREFIX,
        "listing_pages": pages,
        "keys_total": len(keys),
        "zip_keys": len(zips),
        "unmatched_keys": unmatched,
        "symbols": len(universe),
        "symbol_months": sum(len(v) for v in universe.values()),
        "universe": universe,
    }
    UNIVERSE.write_text(json.dumps(out, indent=1, sort_keys=True))
    print(f"symbols={len(universe)} symbol_months={out['symbol_months']} pages={pages}")
    for probe in ("LUNAUSDT", "FTTUSDT", "SRMUSDT", "BTCUSDT"):
        print(f"  {probe}: {len(universe.get(probe, []))} months "
              f"{universe.get(probe, ['-'])[0]}..{universe.get(probe, ['-'])[-1]}")
    return 0


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------

KINDS = (
    ("fundingRate", "data/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{ym}.zip"),
    ("klines1d", "data/futures/um/monthly/klines/{sym}/1d/{sym}-1d-{ym}.zip"),
    ("premium1d", "data/futures/um/monthly/premiumIndexKlines/{sym}/1d/{sym}-1d-{ym}.zip"),
)


def _target(kind: str, sym: str, ym: str) -> pathlib.Path:
    return RAW / kind / sym / f"{sym}-{kind}-{ym}.zip"


def _fetch_one(job) -> dict:
    kind, sym, ym, path = job
    if path.exists() and path.stat().st_size > 0:
        body = path.read_bytes()
        return {"kind": kind, "symbol": sym, "month": ym, "status": "cached",
                "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    tmpl = dict(KINDS)[kind]
    url = f"{DUMP}/{tmpl.format(sym=sym, ym=ym)}"
    body = _get(url)
    if body is None:
        return {"kind": kind, "symbol": sym, "month": ym, "status": "absent"}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(body)
    tmp.replace(path)
    return {"kind": kind, "symbol": sym, "month": ym, "status": "fetched",
            "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def cmd_download(args) -> int:
    uni = json.loads(UNIVERSE.read_text())["universe"]
    syms = sorted(uni)
    if args.limit:
        syms = syms[: args.limit]
    jobs = []
    for sym in syms:
        for ym in uni[sym]:
            for kind, _ in KINDS:
                jobs.append((kind, sym, ym, _target(kind, sym, ym)))
    print(f"jobs={len(jobs)} symbols={len(syms)}", flush=True)
    done = 0
    counts = {"cached": 0, "fetched": 0, "absent": 0}
    t0 = time.time()
    with MANIFEST.open("a") as mf:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
            for rec in ex.map(_fetch_one, jobs):
                counts[rec["status"]] += 1
                if rec["status"] != "absent":
                    mf.write(json.dumps(rec, sort_keys=True) + "\n")
                done += 1
                if done % 2000 == 0:
                    el = time.time() - t0
                    print(f"  {done}/{len(jobs)} {counts} {done/max(el,1e-9):.0f}/s", flush=True)
    print(f"done={done} {counts} elapsed={time.time()-t0:.0f}s")
    return 0


# ---------------------------------------------------------------------------
# panel
# ---------------------------------------------------------------------------

def _rows(path: pathlib.Path) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as zf:
        name = zf.namelist()[0]
        text = zf.read(name).decode("utf-8")
    out = []
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        out.append(row)
    return out


def _is_header(row: list[str]) -> bool:
    try:
        float(row[0])
    except (ValueError, IndexError):
        return True
    return False


def _ms(v: str) -> int:
    """Binance switched some dumps to microseconds in 2025. Normalise to milliseconds."""
    n = int(float(v))
    if n > 10 ** 14:  # microseconds
        n //= 1000
    return n


def cmd_panel(_args) -> int:
    """Collapse the raw archives into three flat, sorted, reproducible CSVs."""
    PANEL.mkdir(parents=True, exist_ok=True)
    uni = json.loads(UNIVERSE.read_text())["universe"]

    # --- funding prints -----------------------------------------------------
    # fundingRate columns: calc_time, funding_interval_hours, last_funding_rate
    # Some early dumps carry only two columns (calc_time, rate); both shapes are handled and the
    # interval is recorded as 0 when absent rather than guessed.
    n = 0
    with (PANEL / "funding.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "funding_time_ms", "interval_hours", "funding_rate"])
        for sym in sorted(uni):
            recs = []
            for ym in uni[sym]:
                p = _target("fundingRate", sym, ym)
                if not p.exists():
                    continue
                for row in _rows(p):
                    if _is_header(row):
                        continue
                    if len(row) >= 3:
                        recs.append((_ms(row[0]), int(float(row[1] or 0)), row[2]))
                    elif len(row) == 2:
                        recs.append((_ms(row[0]), 0, row[1]))
            recs.sort()
            seen = set()
            for ts, iv, rate in recs:
                if ts in seen:
                    continue
                seen.add(ts)
                w.writerow([sym, ts, iv, rate])
                n += 1
    print(f"funding rows={n}")

    # --- daily perp bars ----------------------------------------------------
    # kline columns: open_time, open, high, low, close, volume, close_time,
    #                quote_volume, count, taker_buy_volume, taker_buy_quote_volume, ignore
    m = 0
    with (PANEL / "perp_daily.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "day_ms", "close", "quote_volume", "trades"])
        for sym in sorted(uni):
            recs = {}
            for ym in uni[sym]:
                p = _target("klines1d", sym, ym)
                if not p.exists():
                    continue
                for row in _rows(p):
                    if _is_header(row):
                        continue
                    recs[_ms(row[0])] = (row[4], row[7], row[8])
            for ts in sorted(recs):
                close, qv, cnt = recs[ts]
                w.writerow([sym, ts, close, qv, cnt])
                m += 1
    print(f"perp_daily rows={m}")

    # --- daily premium index ------------------------------------------------
    k = 0
    with (PANEL / "premium_daily.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "day_ms", "premium_close"])
        for sym in sorted(uni):
            recs = {}
            for ym in uni[sym]:
                p = _target("premium1d", sym, ym)
                if not p.exists():
                    continue
                for row in _rows(p):
                    if _is_header(row):
                        continue
                    recs[_ms(row[0])] = row[4]
            for ts in sorted(recs):
                w.writerow([sym, ts, recs[ts]])
                k += 1
    print(f"premium_daily rows={k}")

    digests = {}
    for name in ("funding.csv", "perp_daily.csv", "premium_daily.csv"):
        digests[name] = hashlib.sha256((PANEL / name).read_bytes()).hexdigest()
    (PANEL / "PANEL_SHA256.json").write_text(json.dumps(digests, indent=1, sort_keys=True))
    print(json.dumps(digests, indent=1))
    return 0


def cmd_verify(_args) -> int:
    uni = json.loads(UNIVERSE.read_text())["universe"]
    have = {kind: 0 for kind, _ in KINDS}
    want = sum(len(v) for v in uni.values())
    for sym in uni:
        for ym in uni[sym]:
            for kind, _ in KINDS:
                if _target(kind, sym, ym).exists():
                    have[kind] += 1
    print(json.dumps({"symbol_months_expected": want, "present": have,
                      "coverage": {k: round(v / want, 4) for k, v in have.items()}}, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("enumerate")
    d = sub.add_parser("download")
    d.add_argument("--workers", type=int, default=24)
    d.add_argument("--limit", type=int, default=0)
    sub.add_parser("panel")
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    return {"enumerate": cmd_enumerate, "download": cmd_download,
            "panel": cmd_panel, "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
