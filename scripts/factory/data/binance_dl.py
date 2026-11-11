"""Binance raw-data downloader — resumable, idempotent, meant to run DETACHED.

    cd /home/anont/meme
    setsid nohup research/factory/.venv/bin/python -m scripts.factory.data.binance_dl <stage> \
        > research/factory/data/raw/binance/logs/<stage>.log 2>&1 < /dev/null &

Stages
  perp-daily     1d klines of every USDT-quoted USD-M perpetual: REST (fapi) for every symbol the
                 exchange still knows (TRADING + SETTLING), the public archive for names that exist only
                 there (old delisted contracts, "...SETTLED" re-used names).
  spot-daily     same for spot USDT pairs (api.binance.com + archive).
  perp-hourly    1h klines (archive monthly zips, sha256-verified against the published .CHECKSUM;
                 REST for months the archive does not hold) + funding (archive monthly + REST) for the
                 symbols in <src>/_ever_in_mask.json (written by scripts.factory.data.crypto).
  spot-hourly    1h klines for the symbols in the spot _ever_in_mask.json.
  perp-fill / spot-fill   REST 1h klines (daily archive zips where REST has nothing) for the holes that the
                 monthly archive zips leave (listed in <src>/_hourly_holes.json).
  (The daily "metrics" / long-short-ratio download of the original brief was DROPPED on the conductor's
   instruction of 2026-11-10: the rule that used aux["glsr"] is on the dead ledger. Nothing was fetched.)

Sources (public market data, no key):
  REST     https://fapi.binance.com/fapi/v1/{exchangeInfo,klines,fundingRate}
           https://api.binance.com/api/v3/{exchangeInfo,klines}
  archive  https://data.binance.vision/<key>  (+ <key>.CHECKSUM), listed through
           https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=<path>/

Idempotency: an archive file is skipped when it is on disk with the size recorded in
`_archive_index.jsonl` and its sha256 matched the published checksum; a REST symbol is skipped when
its `_done.json` carries the same (or a later) cutoff. Only COMPLETE candles are requested
(endTime = cutoff - 1 ms, cutoff = 00:00 UTC of the run day for 1d, the last full hour for 1h).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .common import (RAW, HttpError, append_jsonl, atomic_write_bytes, atomic_write_json, http_get,
                     read_jsonl, sha256_bytes, utc_now, utc_now_ms)

S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
VISION = "https://data.binance.vision/"
DAY_MS = 86_400_000
HOUR_MS = 3_600_000

MARKETS = {
    "perp": dict(src="binance/futures_um", rest="https://fapi.binance.com", klines="/fapi/v1/klines",
                 klimit=1500, exinfo="/fapi/v1/exchangeInfo", arch="data/futures/um", budget=1500),
    "spot": dict(src="binance/spot", rest="https://api.binance.com", klines="/api/v3/klines",
                 klimit=1000, exinfo="/api/v3/exchangeInfo", arch="data/spot", budget=3000),
}
USDT_NAME = re.compile(r"^[A-Z0-9]+USDT(_?SETTLED)*$")


def log(msg: str) -> None:
    print(f"{utc_now()} {msg}", flush=True)


# ------------------------------------------------------------------------------------------ S3 listing
def s3_list(prefix: str, *, marker: Optional[str] = None) -> Tuple[List[dict], List[str]]:
    """All keys (non-recursive) and common prefixes under `prefix` (must end with '/' or be a partial
    file name)."""
    keys: List[dict] = []
    prefixes: List[str] = []
    block = re.compile(r"<Contents>(.*?)</Contents>", re.S)

    def field(b: str, tag: str) -> Optional[str]:
        m = re.search(rf"<{tag}>([^<]*)</{tag}>", b)
        return m.group(1) if m else None

    while True:
        params = {"delimiter": "/", "prefix": prefix}
        if marker:
            params["marker"] = marker
        x = http_get(S3, params=params).text
        # S3 added <ChecksumAlgorithm>/<ChecksumType> elements for objects uploaded since 2025, so every
        # <Contents> block is parsed field by field (a fixed-order pattern silently skipped those keys).
        page = []
        for b in block.findall(x):
            page.append(dict(key=field(b, "Key"), last_modified=field(b, "LastModified"),
                             etag=(field(b, "ETag") or "").replace("&quot;", ""), size=int(field(b, "Size") or -1)))
        if len(page) != x.count("<Contents>") or any(k["key"] is None or k["size"] < 0 for k in page):
            raise RuntimeError(f"S3 listing parse mismatch for prefix {prefix!r}")
        keys += page
        pre = re.findall(r"<CommonPrefixes><Prefix>([^<]+)</Prefix>", x)
        prefixes += pre
        if "<IsTruncated>true</IsTruncated>" in x:
            nm = re.search(r"<NextMarker>([^<]+)</NextMarker>", x)
            if nm:
                marker = nm.group(1)
            elif page:
                marker = page[-1]["key"]
            elif pre:
                marker = pre[-1]
            else:
                break
        else:
            break
    return keys, prefixes


# ------------------------------------------------------------------------------------- archive download
class Archive:
    def __init__(self, src: str):
        self.src = src
        self.index_path = RAW / src / "_archive_index.jsonl"
        self.index: Dict[str, dict] = {}
        for rec in read_jsonl(self.index_path):
            if rec.get("checksum_ok"):
                self.index[rec["key"]] = rec
        self.lock = threading.Lock()

    def have(self, key: str, dest: Path) -> bool:
        rec = self.index.get(key)
        return bool(rec) and dest.exists() and dest.stat().st_size == rec["bytes"]

    def fetch(self, key: str, dest: Path) -> str:
        """Download one archive zip + its published sha256; returns 'skip' | 'ok'. Raises on mismatch."""
        if self.have(key, dest):
            return "skip"
        for attempt in range(3):
            body = http_get(VISION + key).content
            published = http_get(VISION + key + ".CHECKSUM").text.split()[0].strip().lower()
            actual = sha256_bytes(body)
            if published == actual:
                atomic_write_bytes(dest, body)
                rec = {"key": key, "path": str(dest.relative_to(RAW)), "bytes": len(body), "sha256": actual,
                       "checksum_published": published, "checksum_ok": True,
                       "url": VISION + key, "fetched_utc": utc_now()}
                append_jsonl(self.index_path, rec)
                with self.lock:
                    self.index[key] = rec
                return "ok"
            time.sleep(2 + 3 * attempt)
        raise RuntimeError(f"sha256 mismatch after 3 tries: {key}")

    def fetch_many(self, jobs: List[Tuple[str, Path]], *, workers: int = 8, label: str = "") -> dict:
        stats = {"ok": 0, "skip": 0, "fail": 0}
        fails = []
        todo = [(k, d) for k, d in jobs if not self.have(k, d)]
        stats["skip"] = len(jobs) - len(todo)
        if not todo:
            return stats
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(self.fetch, k, d): k for k, d in todo}
            for i, fut in enumerate(as_completed(futs), 1):
                k = futs[fut]
                try:
                    stats[fut.result()] += 1
                except Exception as e:                       # recorded, reported, never silent
                    stats["fail"] += 1
                    fails.append({"key": k, "error": repr(e)[:300], "utc": utc_now()})
                if i % 500 == 0:
                    log(f"  [{label}] {i}/{len(todo)} files, {i / max(time.time() - t0, 1e-9):.1f}/s")
        for f in fails:
            append_jsonl(RAW / self.src / "_archive_failures.jsonl", f)
        return stats


# ----------------------------------------------------------------------------------------------- REST
class Rest:
    def __init__(self, market: str):
        self.m = MARKETS[market]
        self.src = self.m["src"]
        self.used = 0

    def get(self, path: str, params: dict):
        r = http_get(self.m["rest"] + path, params=params, fatal_status=(400, 401, 403, 404))
        try:
            self.used = int(r.headers.get("x-mbx-used-weight-1m", "0"))
        except ValueError:
            self.used = 0
        if self.used >= self.m["budget"]:               # stay well inside the documented weight limit
            time.sleep(61 - (time.time() % 60))
        return r

    def klines(self, symbol: str, interval: str, start_ms: int, end_ms: int, outdir: Path, *, tag: str = "") -> dict:
        """Page complete candles with open time in [start_ms, end_ms]; one raw JSON file per page, named
        <interval>_<tag><page start>.json. Callers that request DIFFERENT ranges with the same start (the
        hole filler) pass a `tag` that names the range, so that a shorter range can never overwrite the
        file of a longer one."""
        step = DAY_MS if interval == "1d" else HOUR_MS
        cur, pages, rows, first, last = start_ms, 0, 0, None, None
        limit = self.m["klimit"]
        while cur <= end_ms:
            params = {"symbol": symbol, "interval": interval, "startTime": cur, "endTime": end_ms, "limit": limit}
            r = self.get(self.m["klines"], params)
            data = r.json()
            if not data:
                break
            atomic_write_bytes(outdir / f"{interval}_{tag}{cur}.json", r.content)
            append_jsonl(RAW / self.src / "_rest_log.jsonl",
                         {"path": str((outdir / f"{interval}_{tag}{cur}.json").relative_to(RAW)), "url": r.url,
                          "fetched_utc": utc_now(), "bytes": len(r.content), "sha256": sha256_bytes(r.content),
                          "rows": len(data)})
            pages += 1
            rows += len(data)
            first = data[0][0] if first is None else first
            last = data[-1][0]
            cur = last + step
            if len(data) < limit:
                break
        return {"pages": pages, "rows": rows, "first_open_ms": first, "last_open_ms": last}


def exchange_info(market: str) -> dict:
    m = MARKETS[market]
    r = http_get(m["rest"] + m["exinfo"])
    stamp = utc_now().replace(":", "").replace("-", "")
    path = RAW / m["src"] / "exchangeInfo" / f"exchangeInfo_{stamp}.json"
    atomic_write_bytes(path, r.content)
    append_jsonl(RAW / m["src"] / "_rest_log.jsonl",
                 {"path": str(path.relative_to(RAW)), "url": r.url, "fetched_utc": utc_now(),
                  "bytes": len(r.content), "sha256": sha256_bytes(r.content)})
    atomic_write_bytes(RAW / m["src"] / "exchangeInfo" / "latest.json", r.content)
    return r.json()


def archive_names(market: str) -> Dict[str, List[str]]:
    """Symbol names present in the archive (monthly and daily kline roots), saved as a raw listing."""
    m = MARKETS[market]
    out = {}
    for freq in ("monthly", "daily"):
        _, pre = s3_list(f"{m['arch']}/{freq}/klines/")
        out[freq] = sorted(p.rstrip("/").split("/")[-1] for p in pre)
    atomic_write_json(RAW / m["src"] / "listings" / "archive_symbol_names.json",
                      {"fetched_utc": utc_now(), "source": S3 + f"?delimiter=/&prefix={m['arch']}/<freq>/klines/",
                       "names": out})
    return out


# ------------------------------------------------------------------------------------------ stage: daily
def stage_daily(market: str) -> None:
    m = MARKETS[market]
    src = m["src"]
    cutoff = (utc_now_ms() // DAY_MS) * DAY_MS          # 00:00 UTC today: candles opened before it are complete
    log(f"[{market}-daily] start, cutoff_ms={cutoff} ({datetime.fromtimestamp(cutoff / 1000, timezone.utc)})")
    info = exchange_info(market)
    if market == "perp":
        rest_syms = sorted(s["symbol"] for s in info["symbols"]
                           if s.get("quoteAsset") == "USDT"
                           and s.get("contractType") in ("PERPETUAL", "TRADIFI_PERPETUAL"))
    else:
        rest_syms = sorted(s["symbol"] for s in info["symbols"] if s.get("quoteAsset") == "USDT")
    names = archive_names(market)
    arch_all = sorted(set(names["monthly"]) | set(names["daily"]))
    arch_usdt = [n for n in arch_all if USDT_NAME.match(n)]
    arch_only = sorted(set(arch_usdt) - set(rest_syms))
    log(f"[{market}-daily] REST symbols={len(rest_syms)} archive USDT names={len(arch_usdt)} archive-only={len(arch_only)}")
    atomic_write_json(RAW / src / "listings" / "daily_plan.json",
                      {"fetched_utc": utc_now(), "cutoff_ms": cutoff, "rest_symbols": rest_syms,
                       "archive_only_symbols": arch_only})

    rest = Rest(market)
    base = RAW / src / "rest_klines_1d"
    n_done = n_skip = n_err = 0
    for i, sym in enumerate(rest_syms, 1):
        d = base / sym
        donef = d / "_done.json"
        if donef.exists():
            try:
                if json.loads(donef.read_text()).get("cutoff_ms", 0) >= cutoff:
                    n_skip += 1
                    continue
            except Exception:
                pass
        try:
            res = rest.klines(sym, "1d", 0, cutoff - 1, d)
            res.update({"symbol": sym, "cutoff_ms": cutoff, "fetched_utc": utc_now()})
            atomic_write_json(donef, res)
            n_done += 1
        except HttpError as e:
            n_err += 1
            append_jsonl(RAW / src / "_rest_failures.jsonl",
                         {"symbol": sym, "stage": "daily", "status": e.status, "body": e.body[:200], "utc": utc_now()})
        if i % 50 == 0:
            log(f"[{market}-daily] REST {i}/{len(rest_syms)} done={n_done} skip={n_skip} err={n_err} weight={rest.used}")
    log(f"[{market}-daily] REST finished done={n_done} skip={n_skip} err={n_err}")

    # ---- names the exchange no longer lists.  REST still serves many of them completely (e.g. LUNAUSDT),
    # and the monthly archive files have holes (LUNAUSDT-1d-2022-02.zip lacks 26-28 Feb), so: REST first;
    # the archive (monthly zips + daily zips for the days the monthly zips miss) only when REST has nothing
    # (the "...SETTLED" re-used names).
    arch = Archive(src)
    listing = {}
    st = {"ok": 0, "skip": 0, "fail": 0}
    rest_served = []
    for sym in arch_only:
        d = base / sym
        donef = d / "_done.json"
        have_rest = False
        if donef.exists():
            try:
                j = json.loads(donef.read_text())
                have_rest = j.get("cutoff_ms", 0) >= cutoff and j.get("rows", 0) > 0
                if j.get("cutoff_ms", 0) >= cutoff and j.get("rows", 0) == 0:
                    have_rest = None                    # asked today, REST had nothing
            except Exception:
                pass
        if have_rest is False:
            try:
                res = rest.klines(sym, "1d", 0, cutoff - 1, d)
            except HttpError as e:
                res = {"pages": 0, "rows": 0, "first_open_ms": None, "last_open_ms": None, "http_status": e.status}
            res.update({"symbol": sym, "cutoff_ms": cutoff, "fetched_utc": utc_now(), "archive_only_name": True})
            atomic_write_json(donef, res)
            have_rest = res["rows"] > 0
        if have_rest:
            rest_served.append(sym)
            continue
        keys, _ = s3_list(f"{m['arch']}/monthly/klines/{sym}/1d/")
        zips = [k for k in keys if k["key"].endswith(".zip")]
        jobs = [(k["key"], RAW / src / "archive_klines_1d" / sym / k["key"].split("/")[-1]) for k in zips]
        r1 = arch.fetch_many(jobs, label=f"{sym}-1d-monthly")
        # which days do the monthly zips actually contain?
        have_days = set()
        for _, dest in jobs:
            if dest.exists():
                try:
                    import zipfile
                    with zipfile.ZipFile(dest) as z:
                        for n in z.namelist():
                            for line in z.read(n).decode().splitlines():
                                tok = line.split(",")[0]
                                if tok.isdigit():
                                    t = int(tok)
                                    t = t // 1000 if t > 10**14 else t
                                    have_days.add(datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d"))
                except Exception as e:
                    append_jsonl(RAW / src / "_archive_failures.jsonl", {"key": str(dest), "error": repr(e)[:200], "utc": utc_now()})
        keys, _ = s3_list(f"{m['arch']}/daily/klines/{sym}/1d/")
        dz = [k for k in keys if k["key"].endswith(".zip") and k["key"].split("/")[-1][-14:-4] not in have_days]
        jobs2 = [(k["key"], RAW / src / "archive_klines_1d" / sym / k["key"].split("/")[-1]) for k in dz]
        r2 = arch.fetch_many(jobs2, label=f"{sym}-1d-daily")
        listing[sym] = {"monthly": [k["key"].split("/")[-1] for k in zips],
                        "daily_for_days_missing_in_monthly": [k["key"].split("/")[-1] for k in dz]}
        for k in st:
            st[k] += r1[k] + r2[k]
    atomic_write_json(RAW / src / "listings" / "archive_only_1d_listing.json",
                      {"fetched_utc": utc_now(), "rest_served": rest_served, "listing": listing})
    log(f"[{market}-daily] archive-only names: REST served {len(rest_served)}, archive used for {len(listing)}; archive {st}")
    atomic_write_json(RAW / src / "_stage_daily_DONE.json",
                      {"finished_utc": utc_now(), "cutoff_ms": cutoff, "rest_done": n_done, "rest_skipped": n_skip,
                       "rest_errors": n_err, "archive": st})
    log(f"[{market}-daily] DONE")


# ----------------------------------------------------------------------------------------- stage: hourly
def _month_range(first_ms: int, last_ms: int) -> List[str]:
    a = datetime.fromtimestamp(first_ms / 1000, timezone.utc)
    b = datetime.fromtimestamp(last_ms / 1000, timezone.utc)
    out, y, mo = [], a.year, a.month
    while (y, mo) <= (b.year, b.month):
        out.append(f"{y:04d}-{mo:02d}")
        mo += 1
        if mo == 13:
            y, mo = y + 1, 1
    return out


def _month_bounds(ym: str) -> Tuple[int, int]:
    y, mo = int(ym[:4]), int(ym[5:7])
    a = datetime(y, mo, 1, tzinfo=timezone.utc)
    b = datetime(y + (mo == 12), (mo % 12) + 1, 1, tzinfo=timezone.utc)
    return int(a.timestamp() * 1000), int(b.timestamp() * 1000)


def _rest_fill_klines(rest: "Rest", src: str, sym: str, months: List[str], cutoff_h: int) -> int:
    d = RAW / src / "rest_klines_1h" / sym
    got = 0
    for ym in months:
        a, b = _month_bounds(ym)
        b = min(b, cutoff_h)
        donef = d / f"_done_{ym}.json"
        if donef.exists() and json.loads(donef.read_text()).get("end_ms", 0) >= b:
            continue
        try:
            res = rest.klines(sym, "1h", a, b - 1, d)
            res.update({"symbol": sym, "month": ym, "end_ms": b, "fetched_utc": utc_now()})
            atomic_write_json(donef, res)
            got += res["rows"]
        except HttpError as e:
            append_jsonl(RAW / src / "_rest_failures.jsonl",
                         {"symbol": sym, "stage": "hourly", "month": ym, "status": e.status,
                          "body": e.body[:200], "utc": utc_now()})
    return got


def _rest_fill_funding(rest: "Rest", src: str, sym: str, months: List[str], cutoff_h: int) -> int:
    d = RAW / src / "rest_funding" / sym
    got = 0
    for ym in months:
        a, b = _month_bounds(ym)
        b = min(b, cutoff_h)
        donef = d / f"_done_{ym}.json"
        if donef.exists() and json.loads(donef.read_text()).get("end_ms", 0) >= b:
            continue
        try:
            cur, page, rows = a, 0, 0
            while cur < b:
                time.sleep(0.65)                           # fundingRate: 500 requests / 5 min / IP
                r = rest.get("/fapi/v1/fundingRate", {"symbol": sym, "startTime": cur, "endTime": b - 1, "limit": 1000})
                data = r.json()
                if not data:
                    break
                p = d / f"funding_{ym}_{page}.json"
                atomic_write_bytes(p, r.content)
                append_jsonl(RAW / src / "_rest_log.jsonl",
                             {"path": str(p.relative_to(RAW)), "url": r.url, "fetched_utc": utc_now(),
                              "bytes": len(r.content), "sha256": sha256_bytes(r.content), "rows": len(data)})
                rows += len(data)
                page += 1
                cur = data[-1]["fundingTime"] + 1
                if len(data) < 1000:
                    break
            atomic_write_json(donef, {"symbol": sym, "month": ym, "end_ms": b, "rows": rows, "fetched_utc": utc_now()})
            got += rows
        except HttpError as e:
            append_jsonl(RAW / src / "_rest_failures.jsonl",
                         {"symbol": sym, "stage": "funding", "month": ym, "status": e.status,
                          "body": e.body[:200], "utc": utc_now()})
    return got


def stage_hourly(market: str, *, with_funding: bool, chunk: int = 12, workers: int = 16, only_new: bool = False) -> None:
    """1h klines (+ funding) for the symbols of <src>/_ever_in_mask.json, over each symbol's traded life.
    Archive monthly zips first (sha256-verified); months the archive does not hold come from REST.
    `only_new`: skip every symbol that already has hourly files on disk (used after the plan gained a few
    symbols; a full pass re-lists every symbol and refreshes the current month)."""
    m = MARKETS[market]
    src = m["src"]
    plan = json.loads((RAW / src / "_ever_in_mask.json").read_text())
    syms = sorted(plan["symbols"].items())        # [(sym, {"first_ms":..., "last_ms":..., "rest": bool}), ...]
    if only_new:
        syms = [(s, v) for s, v in syms
                if not any((RAW / src / d / s).exists() for d in ("archive_klines_1h", "rest_klines_1h"))]
    cutoff_h = (utc_now_ms() // HOUR_MS) * HOUR_MS
    log(f"[{market}-hourly] start symbols={len(syms)} funding={with_funding} cutoff_hour_ms={cutoff_h}")
    arch = Archive(src)
    rest = Rest(market)
    repf = RAW / src / "_stage_hourly_report.json"
    report = json.loads(repf.read_text()) if repf.exists() else {}
    for c0 in range(0, len(syms), chunk):
        part = syms[c0:c0 + chunk]
        jobs: List[Tuple[str, Path]] = []
        todo_rest = []
        for sym, meta in part:
            last_ms = min(meta["last_ms"] + 3 * DAY_MS, cutoff_h)   # + the settlement print after the last trade day
            months = _month_range(meta["first_ms"], last_ms)
            rep = {"months": len(months), "first_month": months[0], "last_month": months[-1]}
            keys, _ = s3_list(f"{m['arch']}/monthly/klines/{sym}/1h/")
            have = {k["key"].split("/")[-1][-11:-4]: k["key"] for k in keys if k["key"].endswith(".zip")}
            jobs += [(have[ym], RAW / src / "archive_klines_1h" / sym / have[ym].split("/")[-1]) for ym in months if ym in have]
            rep["klines_1h_archive_months"] = sum(1 for ym in months if ym in have)
            kmiss = [ym for ym in months if ym not in have]
            rep["klines_1h_missing_in_archive"] = kmiss
            fmiss: List[str] = []
            if with_funding:
                keys, _ = s3_list(f"{m['arch']}/monthly/fundingRate/{sym}/")
                fhave = {k["key"].split("/")[-1][-11:-4]: k["key"] for k in keys if k["key"].endswith(".zip")}
                jobs += [(fhave[ym], RAW / src / "archive_funding" / sym / fhave[ym].split("/")[-1]) for ym in months if ym in fhave]
                rep["funding_archive_months"] = sum(1 for ym in months if ym in fhave)
                fmiss = [ym for ym in months if ym not in fhave]
                rep["funding_missing_in_archive"] = fmiss
            report[sym] = rep
            todo_rest.append((sym, meta, kmiss, fmiss))
        st = arch.fetch_many(jobs, workers=workers, label=f"{market}-hourly chunk {c0 // chunk}")
        for sym, meta, kmiss, fmiss in todo_rest:
            if meta.get("rest", True):
                if kmiss:
                    report[sym]["klines_1h_rest_rows"] = _rest_fill_klines(rest, src, sym, kmiss, cutoff_h)
                if fmiss:
                    report[sym]["funding_rest_rows"] = _rest_fill_funding(rest, src, sym, fmiss, cutoff_h)
        atomic_write_json(repf, report)
        atomic_write_json(RAW / src / "_stage_hourly_progress.json",
                          {"updated_utc": utc_now(), "done": min(c0 + chunk, len(syms)), "total": len(syms)})
        log(f"[{market}-hourly] {min(c0 + chunk, len(syms))}/{len(syms)} symbols; chunk archive {st}; weight={rest.used}")
    # an --only-new pass has its own marker: it must not overwrite the record of the last FULL pass
    marker = "_stage_hourly_ONLYNEW_DONE.json" if only_new else "_stage_hourly_DONE.json"
    atomic_write_json(RAW / src / marker,
                      {"finished_utc": utc_now(), "cutoff_hour_ms": cutoff_h, "symbols": len(syms),
                       "only_new": only_new, "plan_written_utc": plan.get("written_utc")})
    log(f"[{market}-hourly] DONE")


def stage_fill(market: str) -> None:
    """Fill holes in the hourly data listed in <src>/_hourly_holes.json ({sym: [[start_ms, end_ms], ...]},
    written by scripts.factory.data.crypto_build holes-<market>): REST 1h klines for each range; where REST
    has nothing (re-used "...SETTLED" names) the DAILY archive zips of those days."""
    m = MARKETS[market]
    src = m["src"]
    holes = json.loads((RAW / src / "_hourly_holes.json").read_text())["holes"]
    rest = Rest(market)
    arch = Archive(src)
    report = {}
    log(f"[{market}-fill] start: {len(holes)} symbols, {sum(len(v) for v in holes.values())} ranges")
    for i, (sym, ranges) in enumerate(sorted(holes.items()), 1):
        got, daily = 0, {"ok": 0, "skip": 0, "fail": 0}
        d = RAW / src / "rest_klines_1h" / sym
        day_listing = None
        for a_ms, b_ms in ranges:
            n = 0
            # one marker per requested range: a range is fetched once, and its pages carry the range in their
            # name (a genuinely empty hour is re-listed by every later hole scan with a SHORTER range around it;
            # with pages named by start alone that shorter request overwrote the longer file - seen on spot,
            # 2018-02-07..12, 2026-11-10)
            marker = d / f"_fill_{a_ms}_{b_ms}.json"
            if marker.exists():
                n = json.loads(marker.read_text()).get("rows", 0)
            else:
                try:
                    n = rest.klines(sym, "1h", a_ms, b_ms - 1, d, tag=f"fill_{a_ms}_{b_ms}_")["rows"]
                    atomic_write_json(marker, {"symbol": sym, "range_ms": [a_ms, b_ms], "rows": n, "fetched_utc": utc_now()})
                except HttpError as e:
                    append_jsonl(RAW / src / "_rest_failures.jsonl",
                                 {"symbol": sym, "stage": "fill", "range": [a_ms, b_ms], "status": e.status,
                                  "body": e.body[:200], "utc": utc_now()})
            got += n
            if n == 0:                                   # REST has nothing: daily archive zips for those days
                if day_listing is None:
                    keys, _ = s3_list(f"{m['arch']}/daily/klines/{sym}/1h/")
                    day_listing = {k["key"].split("/")[-1][-14:-4]: k["key"] for k in keys if k["key"].endswith(".zip")}
                jobs, t = [], a_ms - (a_ms % DAY_MS)
                while t < b_ms:
                    day = datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d")
                    if day in day_listing:
                        jobs.append((day_listing[day], RAW / src / "archive_klines_1h" / sym / day_listing[day].split("/")[-1]))
                    t += DAY_MS
                r = arch.fetch_many(jobs, label=f"{sym}-1h-daily")
                for k in daily:
                    daily[k] += r[k]
        report[sym] = {"ranges": len(ranges), "rest_rows": got, "daily_archive": daily}
        if i % 20 == 0 or i == len(holes):
            log(f"[{market}-fill] {i}/{len(holes)} symbols; weight={rest.used}")
    freport = {}
    fpath = RAW / src / "_funding_holes.json"
    if market == "perp" and fpath.exists():
        fholes = json.loads(fpath.read_text())["holes"]
        log(f"[{market}-fill] funding: {len(fholes)} symbols, {sum(len(v) for v in fholes.values())} ranges")
        for i, (sym, ranges) in enumerate(sorted(fholes.items()), 1):
            # an old contract renamed "...SETTLED" keeps its funding history under the PLAIN ticker
            q = re.sub(r"(_?SETTLED)+$", "", sym)
            d = RAW / src / "rest_funding" / q
            got = 0
            arch_stats = None
            if q != sym:
                keys, _ = s3_list(f"{m['arch']}/monthly/fundingRate/{q}/")
                fhave = {k["key"].split("/")[-1][-11:-4]: k["key"] for k in keys if k["key"].endswith(".zip")}
                jobs = []
                for a_ms, b_ms in ranges:
                    for ym in _month_range(a_ms, b_ms):
                        if ym in fhave:
                            jobs.append((fhave[ym], RAW / src / "archive_funding" / q / fhave[ym].split("/")[-1]))
                arch_stats = arch.fetch_many(sorted(set(jobs)), label=f"{q}-funding-for-{sym}")
            for a_ms, b_ms in ranges:
                cur, page = a_ms, 0
                try:
                    while cur < b_ms:
                        time.sleep(0.65)                       # fundingRate: 500 requests / 5 min / IP
                        r = rest.get("/fapi/v1/fundingRate", {"symbol": q, "startTime": cur, "endTime": b_ms - 1, "limit": 1000})
                        data = r.json()
                        if not data:
                            break
                        p = d / f"funding_fill_{a_ms}_{b_ms}_{page}.json"      # range in the name: never overwritten by another range
                        atomic_write_bytes(p, r.content)
                        append_jsonl(RAW / src / "_rest_log.jsonl",
                                     {"path": str(p.relative_to(RAW)), "url": r.url, "fetched_utc": utc_now(),
                                      "bytes": len(r.content), "sha256": sha256_bytes(r.content), "rows": len(data)})
                        got += len(data)
                        page += 1
                        cur = data[-1]["fundingTime"] + 1
                        if len(data) < 1000:
                            break
                except HttpError as e:
                    append_jsonl(RAW / src / "_rest_failures.jsonl",
                                 {"symbol": sym, "stage": "fill-funding", "range": [a_ms, b_ms], "status": e.status,
                                  "body": e.body[:200], "utc": utc_now()})
            freport[sym] = {"ranges": len(ranges), "queried_as": q, "rest_rows": got, "archive": arch_stats}
            if i % 20 == 0 or i == len(fholes):
                log(f"[{market}-fill] funding {i}/{len(fholes)} symbols; weight={rest.used}")
    atomic_write_json(RAW / src / "_stage_fill_DONE.json", {"finished_utc": utc_now(), "report": report, "funding": freport})
    log(f"[{market}-fill] DONE")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["perp-daily", "spot-daily", "perp-hourly", "spot-hourly", "perp-fill", "spot-fill"])
    ap.add_argument("--workers", type=int, default=16, help="concurrent archive downloads (hourly stages)")
    ap.add_argument("--only-new", action="store_true", help="hourly stages: only symbols without hourly files on disk")
    a = ap.parse_args(argv)
    if a.stage == "perp-daily":
        stage_daily("perp")
    elif a.stage == "spot-daily":
        stage_daily("spot")
    elif a.stage == "perp-hourly":
        stage_hourly("perp", with_funding=True, workers=a.workers, only_new=a.only_new)
    elif a.stage == "spot-hourly":
        stage_hourly("spot", with_funding=False, workers=a.workers, only_new=a.only_new)
    elif a.stage == "perp-fill":
        stage_fill("perp")
    elif a.stage == "spot-fill":
        stage_fill("spot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
