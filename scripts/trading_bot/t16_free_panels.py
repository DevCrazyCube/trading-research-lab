#!/usr/bin/env python3
"""T16 -- the FREE forward-data panels: FINRA short interest + a free borrow mirror.

WHAT THIS IS, AND WHAT IT IS NOT
================================
This script CREATES A DATA ASSET.  It does not find an edge, it does not test one, and no
number it writes is evidence for or against any strategy.  Its whole argument is the one
`research/trading_bot/DATA_PURCHASE_SCOPE.md` §8a makes: **history that does not exist can
only be created by starting now.**  Every day this does not run is a day of point-in-time
observation that no vendor will sell back to us at a retail price.

The candidate it most directly feeds -- shortlist #9, short interest -- is very probably
UNDERPOWERED.  FINRA publishes 24 settlement dates a year and the panel starts 2017-12-29,
so a strategy keyed on the SI cycle has roughly 110 bi-monthly observations in the window we
would hold out.  `DATA_PURCHASE_SCOPE.md` §0(b) puts P(pass) at ~0.05.  Collect anyway,
because the collection is free and the option is not; but do not confuse a panel with a
finding.

THE THREE PANELS
================
  1. FINRA Consolidated Short Interest      free, no key, no account, 2017-12-29 -> today
     POST https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest
     GET  https://api.finra.org/partitions/group/... enumerates every settlement date.
     Bi-monthly, ~19.5k-22.3k symbol-date rows per date, ~3.9 M rows total.
     Fields: current + previous short position, average daily volume, days to cover,
     split flag, revision flag, market class.

  2. Alpaca asset borrow flags              free with the key this repo already holds
     GET https://paper-api.alpaca.markets/v2/assets  (read-only; no order path is touched)
     14.2k US equities x {shortable, easy_to_borrow, borrow_status, margin requirements}.
     A LIVE SNAPSHOT WITH NO HISTORY ANYWHERE -- which is precisely why snapshotting it
     daily is worth something.  It is also our OWN broker's constraint, so unlike a
     third-party fee it is directly actionable.

  3. iborrowdesk.com                        free public mirror of IBKR's stock-loan file
     GET https://iborrowdesk.com/api/ticker/<SYM>   (daily fee %, shares available)
     Rate-limited hard: nginx closes the connection (HTTP 444) after a few hundred hits, and
     as of 2026-08-17 this host was returning 444 on every /api/ path from this address --
     see COLLECTION_LOG.jsonl.  This leg is therefore BEST-EFFORT by construction: it fails
     loudly into the log and never blocks the other two.  RE-PROBED 2026-08-17 15:xx UTC:
     still a bare connection close on /api/ticker and /api/home_stats.  IBKR's own file was
     re-probed too: ftp3.interactivebrokers.com times out, and ViewShortableStocks.php
     renders 169 kB of markup with NO data URL in it.  There is, as of today, no reachable
     free borrow-FEE source.  Panel 4 is what was added instead.

  4. FINRA Reg SHO daily short-sale volume  free, no key, no account, DAILY
     GET https://cdn.finra.org/equity/regsho/daily/CNMSshvol<YYYYMMDD>.txt
     Pipe-delimited: Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market, ~12.2k
     symbol rows per session, with a bare record-count line at the foot that this collector
     checks against the rows it parsed.  Added on 2026-08-17 BECAUSE panel 3 is unreachable:
     it is the only free, working, DAILY short-side panel we could find, and it is on exactly
     the topic panel 1 is underpowered for -- 252 observations a year against panel 1's 24.
     The CDN keeps a rolling retention window (probed: 2018-07-02 denied, 2018-08-01 served),
     so unlike panel 1 its history is NOT fully recoverable later.  That is the case for
     starting it today rather than when a candidate wants it.

POINT-IN-TIME DISCIPLINE (guardrail 1), STATED PRECISELY
========================================================
Two dates, never confused, and the distinction is the entire value of this panel:

  * `settlement_date` -- the date the short position was as-of.  FINRA's key.
  * `observed_utc`    -- the moment WE pulled the bytes.  Ours, and unrecoverable later.

FINRA disseminates a settlement date roughly eight business days after it, and the API
serves only the LATEST state of every date: a revision (revisionFlag='R') silently replaces
what was published.  So:

  * A snapshot file is NEVER overwritten.  The path carries `observed=<timestamp>`, an
    existing path is a hard refusal, and MANIFEST.jsonl is opened in append mode only.
  * Refetching a settlement date (`--refresh-revisions`) writes a SECOND observation of that
    date alongside the first.  The pair is the revision record.  Nothing is ever replaced.
  * `verify` re-hashes every file in the manifest.  A mismatch means something overwrote a
    prior snapshot, which is the one failure this design exists to make visible.

  * THE BACKFILL IS NOT POINT-IN-TIME AND IS LABELLED `backfill: true`.  Rows for settlement
    dates before the first run carry whatever revisions FINRA applied before we arrived, and
    their true dissemination date is unknown to us.  Only dates first seen by a forward poll
    carry `first_seen_utc`, which bounds real dissemination within the poll interval.  A
    backtest that treats a backfilled date as knowable on its settlement date is looking
    ~8 business days into the future.  The panel records which rows are which so that the
    mistake has to be made deliberately.

WHAT THIS SCRIPT WILL NOT DO
============================
No orders, no order path, no live host.  Every endpoint is read-only.  It installs no
crontab: `crontab-line` PRINTS the line for the owner to install, and that is the only
scheduling this file performs.  Nothing here is paid, and no account or payment detail is
created or required beyond the Alpaca market key already in `.env`.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import pathlib
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import date as date_cls, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.trading_bot.data import load_env_credentials  # noqa: E402

# --------------------------------------------------------------------------------------
# layout
# --------------------------------------------------------------------------------------

PANELS = ROOT / "research" / "data" / "t16_panels"
FINRA_DIR = PANELS / "finra_short_interest"
FINRA_RAW = FINRA_DIR / "raw"
FINRA_MANIFEST = FINRA_DIR / "MANIFEST.jsonl"
BORROW_DIR = PANELS / "borrow"
ALPACA_RAW = BORROW_DIR / "alpaca_assets" / "raw"
IBD_RAW = BORROW_DIR / "iborrowdesk" / "raw"
BORROW_MANIFEST = BORROW_DIR / "MANIFEST.jsonl"
REGSHO_DIR = PANELS / "finra_regsho_daily"
REGSHO_RAW = REGSHO_DIR / "raw"
REGSHO_MANIFEST = REGSHO_DIR / "MANIFEST.jsonl"
WATCHLIST = PANELS / "borrow_watchlist.txt"
COLLECTION_LOG = PANELS / "COLLECTION_LOG.jsonl"
COVERAGE = PANELS / "COVERAGE.json"
FIRST_SEEN = PANELS / "FINRA_FIRST_SEEN.jsonl"

# --------------------------------------------------------------------------------------
# endpoints -- all free, all read-only
# --------------------------------------------------------------------------------------

FINRA_DATA = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
FINRA_PARTITIONS = "https://api.finra.org/partitions/group/otcMarket/name/consolidatedShortInterest"
FINRA_PAGE = 5000                      # record-max-limit, reported by the API itself
ALPACA_ASSETS = "https://paper-api.alpaca.markets/v2/assets"
IBD_TICKER = "https://iborrowdesk.com/api/ticker/{sym}"
REGSHO_DAILY = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{ymd}.txt"
# Probed 2026-08-17: 2018-07-02 -> 403, 2018-08-01 -> 200. The CDN's retention window moves,
# so this floor is a documented probe, not a promise, and the collector treats a 403 as
# "not available" rather than as an error.
REGSHO_EARLIEST = "2018-08-01"
# A 403 on a date within the last few days means "not published yet" (the file for session D
# appears the following business day); a 403 on an older date means retention or a holiday.
# Only the latter is retired, so a not-yet-published day is retried tomorrow instead of lost.
REGSHO_RETIRE_AFTER_DAYS = 6

UA = "meme-research (contact officialjoy04@gmail.com)"

FINRA_FIELDS = [
    "settlementDate", "symbolCode", "issueName", "marketClassCode",
    "issuerServicesGroupExchangeCode", "currentShortPositionQuantity",
    "previousShortPositionQuantity", "changePreviousNumber", "changePercent",
    "averageDailyVolumeQuantity", "daysToCoverQuantity", "stockSplitFlag",
    "revisionFlag", "accountingYearMonthNumber",
]

ALPACA_FIELDS = [
    "symbol", "name", "exchange", "status", "tradable", "marginable", "shortable",
    "easy_to_borrow", "borrow_status", "fractionable",
    "maintenance_margin_requirement", "margin_requirement_long", "margin_requirement_short",
]

IBD_FIELDS = ["symbol", "time", "fee", "available", "rebate_rate"]

REGSHO_FIELDS = ["date", "symbol", "short_volume", "short_exempt_volume",
                 "total_volume", "market"]

WATCHLIST_SIZE = 120                   # politeness cap; iborrowdesk 444s well before this


class Refused(Exception):
    """Raised instead of guessing.  Never caught to produce a default."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stamp(dt: datetime | None = None) -> str:
    return (dt or utcnow()).strftime("%Y%m%dT%H%M%SZ")


def iso(dt: datetime | None = None) -> str:
    return (dt or utcnow()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------------------
# transport -- one global token bucket, shared by every leg
# --------------------------------------------------------------------------------------

class Throttle:
    """Serialises outbound requests to `per_second`.

    A public free endpoint with no key is a courtesy, not an entitlement.  Every leg goes
    through one bucket so that adding a leg cannot silently double the rate.
    """

    def __init__(self, per_second: float):
        self._gap = 1.0 / per_second
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next:
                time.sleep(self._next - now)
                now = time.monotonic()
            self._next = now + self._gap


THROTTLE = Throttle(2.0)


def _open(req: urllib.request.Request, timeout: int, retries: int = 4):
    last = None
    for attempt in range(retries):
        THROTTLE.wait()
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2.0 * (2 ** attempt))
                continue
            raise
        except Exception as exc:                      # noqa: BLE001 -- transport, re-raised below
            last = exc
            if attempt < retries - 1:
                time.sleep(2.0 * (2 ** attempt))
                continue
            raise
    raise last                                        # pragma: no cover


def get_json(url: str, headers: dict, timeout: int = 120):
    with _open(urllib.request.Request(url, headers={"User-Agent": UA, **headers}), timeout) as r:
        return json.loads(r.read()), dict(r.headers)


def post_json(url: str, body: dict, timeout: int = 180):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"User-Agent": UA, "Content-Type": "application/json",
                 "Accept": "application/json"},
        method="POST",
    )
    with _open(req, timeout) as r:
        return json.loads(r.read()), dict(r.headers)


def get_text(url: str, headers: dict | None = None, timeout: int = 120) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with _open(req, timeout) as r:
        return r.read().decode("utf-8", errors="replace")


# --------------------------------------------------------------------------------------
# append-only storage
# --------------------------------------------------------------------------------------

def append_jsonl(path: pathlib.Path, record: dict) -> None:
    """The ONLY write mode used for manifests and logs.  Mode 'a', flushed and fsynced.

    An interrupted run must leave a readable prefix, not a truncated file, which is why the
    record is serialised whole before the handle is opened.
    """
    line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


def write_snapshot(path: pathlib.Path, rows: list[dict], fields: list[str]) -> dict:
    """Write ONE immutable gzip-CSV snapshot.  Refuses if the path already exists.

    Written to `<path>.partial` and renamed, so a killed process never leaves a short file
    that a later run would mistake for a sealed snapshot.  `mtime=0` keeps the gzip header
    deterministic, so the sha256 below is a hash of the DATA and can be recomputed from a
    copy made anywhere.
    """
    if path.exists():
        raise Refused(
            f"{path} already exists. Snapshots are append-only and are never overwritten "
            "(guardrail 1). If you meant to record a revision, take a NEW observation."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        writer = csv.DictWriter(text, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fields})
        text.flush()
        text.detach()
    blob = buf.getvalue()
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_bytes(blob)
    os.replace(tmp, path)
    return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest(), "rows": len(rows)}


def manifest_records(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


# --------------------------------------------------------------------------------------
# leg 1 -- FINRA consolidated short interest
# --------------------------------------------------------------------------------------

def finra_settlement_dates() -> list[str]:
    payload, _ = get_json(FINRA_PARTITIONS, {"Accept": "application/json"})
    dates = sorted({p["partitions"][0] for p in payload["availablePartitions"]})
    if not dates:
        raise Refused("FINRA partitions endpoint returned no settlement dates.")
    return dates


def finra_fetch_date(settlement_date: str) -> tuple[list[dict], int]:
    """Page one settlement date to exhaustion.  Returns (rows, record-total header)."""
    rows: list[dict] = []
    offset = 0
    total = None
    while True:
        page, headers = post_json(FINRA_DATA, {
            "limit": FINRA_PAGE,
            "offset": offset,
            "compareFilters": [{"fieldName": "settlementDate",
                                "fieldValue": settlement_date,
                                "compareType": "EQUAL"}],
        })
        if total is None:
            total = int(headers.get("record-total", "0"))
        rows.extend(page)
        offset += len(page)
        if len(page) < FINRA_PAGE or offset >= total:
            break
    if total and len(rows) != total:
        raise Refused(
            f"{settlement_date}: paged {len(rows)} rows but the API's record-total header "
            f"said {total}. A short read must fail rather than seal a partial snapshot."
        )
    return rows, total or len(rows)


def collect_finra(*, refresh_revisions: bool, limit_dates: int | None,
                  run_id: str, refresh_recent: int = 0,
                  refresh_age_days: int = 7) -> dict:
    """Fetch every listed settlement date we do not already hold.

    `backfill` and `daily` run the SAME rule deliberately: a daily poll that only ever looks
    at the newest date cannot heal a gap left by a night the machine was down, and a panel
    with an unexplained hole is worth less than one that self-heals and says so.
    """
    held = manifest_records(FINRA_MANIFEST)
    seen = {r["settlement_date"] for r in held}
    first_seen_records = manifest_records(FIRST_SEEN)
    first_seen = {r["settlement_date"] for r in first_seen_records}
    # A date we WATCHED appear is forward-observed forever, including on later
    # re-observations of it.  Deriving this from the discovery log rather than from "is this
    # the run that fetched it" is what keeps a revision snapshot of a forward-observed date
    # from being mislabelled as backfill.
    discovered = {r["settlement_date"] for r in first_seen_records if r.get("is_discovery")}
    available = finra_settlement_dates()

    # Record discovery BEFORE fetching: a settlement date's first appearance in the
    # partitions listing is our best free proxy for its dissemination timestamp, and it is
    # the one field no vendor sells us.  Backfilled dates are flagged as not-a-discovery.
    now = utcnow()
    newly_listed = [d for d in available if d not in first_seen]
    inception = not first_seen
    for date in newly_listed:
        append_jsonl(FIRST_SEEN, {
            "settlement_date": date,
            "first_seen_utc": iso(now),
            "run_id": run_id,
            # True dissemination is unknown for anything we did not watch appear.
            "is_discovery": not inception,
            "note": ("observed appearing in the partitions listing" if not inception else
                     "present at panel inception; dissemination date unknown"),
        })
        if not inception:
            discovered.add(date)

    todo = list(available) if refresh_revisions else [d for d in available if d not in seen]
    if limit_dates is not None:
        todo = todo[-limit_dates:]

    # Bounded revision capture.  FINRA silently REPLACES a settlement date's rows when it
    # revises them (revisionFlag='R'), and a collector that only ever fetches dates it has
    # never seen will never observe a single revision -- which would quietly discard the one
    # thing this panel claims to record.  Re-observing writes a SECOND snapshot beside the
    # first; the pair IS the revision record and nothing is overwritten.  It is bounded
    # (N most recent dates, at most once every `refresh_age_days`) because the unbounded
    # version would seal ~600 kB twice a day forever for no extra information.
    refreshed: list[str] = []
    if refresh_recent and not refresh_revisions:
        last_obs: dict[str, str] = {}
        for record in held:
            key = record["settlement_date"]
            if record["observed_utc"] > last_obs.get(key, ""):
                last_obs[key] = record["observed_utc"]
        cutoff = now - timedelta(days=refresh_age_days)
        for date in available[-refresh_recent:]:
            if date not in seen or date in todo:
                continue
            stamped = last_obs.get(date)
            if stamped and datetime.fromisoformat(stamped.replace("Z", "+00:00")) < cutoff:
                todo.append(date)
                refreshed.append(date)

    fetched, failed = [], []
    for date in todo:
        try:
            rows, total = finra_fetch_date(date)
        except Exception as exc:                      # noqa: BLE001 -- recorded, not hidden
            failed.append({"settlement_date": date, "error": f"{type(exc).__name__}: {exc}"})
            print(f"  FINRA {date}  FAILED  {type(exc).__name__}: {exc}", flush=True)
            continue
        observed = utcnow()
        path = FINRA_RAW / f"settlement={date}" / f"observed={stamp(observed)}.csv.gz"
        meta = write_snapshot(path, rows, FINRA_FIELDS)
        record = {
            "panel": "finra_consolidated_short_interest",
            "settlement_date": date,
            "observed_utc": iso(observed),
            "run_id": run_id,
            # A snapshot of a date that already existed when we arrived carries revisions we
            # never saw.  It is history, not observation, and it says so here.
            "backfill": date not in discovered,
            "is_revision_observation": date in seen,
            "path": str(path.relative_to(ROOT)),
            "rows": meta["rows"],
            "record_total_header": total,
            "bytes": meta["bytes"],
            "sha256": meta["sha256"],
            "source": FINRA_DATA,
        }
        append_jsonl(FINRA_MANIFEST, record)
        fetched.append(record)
        print(f"  FINRA {date}  {meta['rows']:>6} rows  {meta['bytes']/1e6:5.2f} MB  "
              f"{meta['sha256'][:12]}", flush=True)

    return {
        "available_dates": len(available),
        "range": [available[0], available[-1]],
        "already_held": len(seen),
        "newly_listed": newly_listed,
        "re_observed_for_revisions": refreshed,
        "fetched": len(fetched),
        "failed": failed,
    }


# --------------------------------------------------------------------------------------
# leg 4 -- FINRA Reg SHO DAILY short-sale volume (free, no key, 252 obs/yr not 24)
# --------------------------------------------------------------------------------------

def parse_regsho(text: str, ymd: str) -> list[dict]:
    """Parse one pipe-delimited Reg SHO daily file, checking its own footer count.

    The file is `Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market` with a header
    line and a BARE RECORD COUNT as the last line.  That count is the file's own integrity
    statement, so it is checked rather than discarded: a truncated download that silently
    seals 4,000 of 12,195 rows is exactly the failure a point-in-time panel cannot survive,
    because nothing later can tell a short file from a quiet day.
    """
    lines = [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
    if not lines or not lines[0].lower().startswith("date|"):
        raise Refused(f"Reg SHO {ymd}: unexpected header {lines[:1]!r}")
    footer = None
    if "|" not in lines[-1]:
        try:
            footer = int(lines[-1].strip())
        except ValueError:
            raise Refused(f"Reg SHO {ymd}: unparseable footer {lines[-1]!r}") from None
        lines = lines[:-1]
    rows = []
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) < 6:
            raise Refused(f"Reg SHO {ymd}: short record {line!r}")
        raw_date = parts[0].strip()
        if raw_date != ymd:
            raise Refused(f"Reg SHO {ymd}: row carries date {raw_date!r}")
        rows.append({
            "date": f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}",
            "symbol": parts[1].strip(),
            "short_volume": parts[2].strip(),
            "short_exempt_volume": parts[3].strip(),
            "total_volume": parts[4].strip(),
            "market": parts[5].strip(),
        })
    if footer is not None and footer != len(rows):
        raise Refused(
            f"Reg SHO {ymd}: parsed {len(rows)} rows but the file's own footer says {footer}. "
            "A short read must fail rather than seal a partial snapshot."
        )
    if not rows:
        raise Refused(f"Reg SHO {ymd}: zero rows")
    return rows


def _regsho_calendar(since: str, until: date_cls) -> list[str]:
    """Every weekday from `since` to `until` inclusive, as YYYY-MM-DD.

    Deliberately NOT a holiday calendar.  A holiday is indistinguishable from a retention
    gap at the CDN (both answer 403), and hard-coding a market calendar here would be one
    more thing to be silently wrong about; the collector simply asks and records the answer.
    """
    day = date_cls.fromisoformat(since)
    out = []
    while day <= until:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def collect_regsho(run_id: str, since: str = REGSHO_EARLIEST,
                   limit_dates: int | None = None) -> dict:
    """Fetch every Reg SHO session file not already held.

    Same self-healing rule as leg 1: ask for everything missing, not just the newest day, so
    a night the machine was down leaves no permanent hole.  A 403/404 is recorded as
    UNAVAILABLE rather than raised -- the CDN answers 403 both for a market holiday and for a
    date that has aged out of retention -- and an UNAVAILABLE date older than
    REGSHO_RETIRE_AFTER_DAYS is never asked for again, so a decade of holidays is not
    re-probed nightly.  A recent one IS retried, because session D's file appears on D+1.
    """
    records = manifest_records(REGSHO_MANIFEST)
    sealed = {r["session_date"] for r in records if r.get("status") == "OK"}
    retired = {r["session_date"] for r in records if r.get("status") == "UNAVAILABLE"
               and r.get("retired")}
    today = utcnow().date()
    # An hourly cron probing a not-yet-published session would otherwise append 24 identical
    # "UNAVAILABLE" rows a day forever.  The PROBE still happens hourly -- that is what makes
    # a new session's first observation prompt -- but the manifest records at most one
    # unavailability per session per UTC day, so the log stays a record rather than a churn.
    logged_today = {r["session_date"] for r in records
                    if r.get("status") == "UNAVAILABLE"
                    and r.get("observed_utc", "")[:10] == today.isoformat()}
    todo = [d for d in _regsho_calendar(since, today)
            if d not in sealed and d not in retired]
    if limit_dates is not None:
        todo = todo[-limit_dates:]

    fetched, unavailable, failed = 0, 0, []
    rows_total = 0
    for day in todo:
        ymd = day.replace("-", "")
        try:
            text = get_text(REGSHO_DAILY.format(ymd=ymd), timeout=90)
        except urllib.error.HTTPError as exc:
            if exc.code not in (403, 404):
                failed.append({"session_date": day, "error": f"HTTP {exc.code}"})
                continue
            age = (today - date_cls.fromisoformat(day)).days
            if day in logged_today:
                unavailable += 1
                continue
            append_jsonl(REGSHO_MANIFEST, {
                "panel": "finra_regsho_daily_short_volume",
                "session_date": day,
                "observed_utc": iso(),
                "run_id": run_id,
                "status": "UNAVAILABLE",
                "http_code": exc.code,
                "retired": age > REGSHO_RETIRE_AFTER_DAYS,
                "note": ("holiday or aged out of the CDN retention window; not retried"
                         if age > REGSHO_RETIRE_AFTER_DAYS else
                         "not published yet (session files appear on D+1); will retry"),
            })
            unavailable += 1
            continue
        except Exception as exc:                      # noqa: BLE001 -- recorded, not hidden
            failed.append({"session_date": day, "error": f"{type(exc).__name__}: {exc}"})
            continue

        try:
            rows = parse_regsho(text, ymd)
        except Refused as exc:
            failed.append({"session_date": day, "error": f"Refused: {exc}"})
            print(f"  REGSHO {day}  REFUSED  {exc}", flush=True)
            continue

        observed = utcnow()
        path = REGSHO_RAW / f"session={day}" / f"observed={stamp(observed)}.csv.gz"
        meta = write_snapshot(path, rows, REGSHO_FIELDS)
        append_jsonl(REGSHO_MANIFEST, {
            "panel": "finra_regsho_daily_short_volume",
            "session_date": day,
            "observed_utc": iso(observed),
            "run_id": run_id,
            "status": "OK",
            # Same discipline as leg 1: a session fetched long after it happened is history,
            # not observation.  The threshold is 3 days rather than 1 because a session file
            # appears on D+1 and D+1 for a FRIDAY session is a Monday -- a three-day gap that
            # is the schedule working, not a late catch-up.  Anything older is backfill.
            "backfill": (today - date_cls.fromisoformat(day)).days > 3,
            "path": str(path.relative_to(ROOT)),
            "rows": meta["rows"],
            "bytes": meta["bytes"],
            "sha256": meta["sha256"],
            "source": REGSHO_DAILY.format(ymd=ymd),
        })
        fetched += 1
        rows_total += meta["rows"]
        if fetched % 25 == 0 or fetched == 1:
            print(f"  REGSHO {day}  {meta['rows']:>6} rows  {meta['bytes']/1e3:6.1f} kB",
                  flush=True)

    return {"considered": len(todo), "fetched": fetched, "rows": rows_total,
            "unavailable": unavailable, "failed": failed[:10],
            "failed_count": len(failed), "since": since}


# --------------------------------------------------------------------------------------
# leg 2 -- Alpaca borrow flags (our own broker's constraint, free, no history anywhere)
# --------------------------------------------------------------------------------------

def collect_alpaca_assets(run_id: str, force: bool = False) -> dict:
    today = utcnow().date().isoformat()
    held = {r.get("asof_date") for r in manifest_records(BORROW_MANIFEST)
            if r.get("panel") == "alpaca_asset_borrow_flags"}
    if today in held and not force:
        return {"skipped": "already snapshotted this UTC day", "asof_date": today}

    key, secret = load_env_credentials()
    url = f"{ALPACA_ASSETS}?status=active&asset_class=us_equity"
    assets, _ = get_json(url, {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
                               "Accept": "application/json"}, timeout=300)
    observed = utcnow()
    path = ALPACA_RAW / f"asof={today}" / f"observed={stamp(observed)}.csv.gz"
    meta = write_snapshot(path, assets, ALPACA_FIELDS)

    shortable = sum(1 for a in assets if a.get("shortable"))
    etb = sum(1 for a in assets if a.get("easy_to_borrow"))
    record = {
        "panel": "alpaca_asset_borrow_flags",
        "asof_date": today,
        "observed_utc": iso(observed),
        "run_id": run_id,
        "path": str(path.relative_to(ROOT)),
        "rows": meta["rows"],
        "bytes": meta["bytes"],
        "sha256": meta["sha256"],
        "shortable": shortable,
        "easy_to_borrow": etb,
        "hard_to_borrow": meta["rows"] - etb,
        "source": ALPACA_ASSETS,
        "note": "read-only GET; no order path touched",
    }
    append_jsonl(BORROW_MANIFEST, record)
    print(f"  ALPACA {today}  {meta['rows']} assets  shortable={shortable}  "
          f"easy_to_borrow={etb}", flush=True)
    return record


# --------------------------------------------------------------------------------------
# leg 3 -- iborrowdesk borrow FEE (best-effort; rate-limited by design at the source)
# --------------------------------------------------------------------------------------

def read_watchlist() -> list[str]:
    if not WATCHLIST.exists():
        return []
    out = []
    for line in WATCHLIST.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip().upper()
        if line:
            out.append(line)
    return out


def seed_watchlist(size: int = WATCHLIST_SIZE) -> dict:
    """Seed the borrow-fee watchlist from the most-recent FINRA date, exchange-listed only.

    The rule is fixed and stated so the composition is reproducible rather than curated:
    highest days-to-cover among non-OTC symbols with a non-zero average daily volume, on the
    latest settlement date we hold.  It is a POLITENESS budget, not a universe: iborrowdesk
    closes the connection long before a real universe could be walked.
    """
    records = [r for r in manifest_records(FINRA_MANIFEST)]
    if not records:
        raise Refused("No FINRA snapshot held yet; run `backfill` or `daily` first.")
    latest = max(records, key=lambda r: (r["settlement_date"], r["observed_utc"]))
    rows = []
    with gzip.open(ROOT / latest["path"], "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["marketClassCode"] == "OTC":
                continue
            try:
                dtc = float(row["daysToCoverQuantity"] or 0)
                adv = float(row["averageDailyVolumeQuantity"] or 0)
            except ValueError:
                continue
            # 999.99 is FINRA's sentinel for "no meaningful volume", not a real days-to-cover
            if adv <= 0 or dtc >= 999:
                continue
            rows.append((dtc, row["symbolCode"]))
    rows.sort(reverse=True)
    syms = [s for _, s in rows[:size]]
    WATCHLIST.parent.mkdir(parents=True, exist_ok=True)
    WATCHLIST.write_text(
        "# T16 borrow-fee watchlist -- POLITENESS BUDGET, not a universe.\n"
        f"# Seeded {iso()} from FINRA settlement {latest['settlement_date']}:\n"
        "# top days-to-cover, non-OTC, average daily volume > 0, sentinel 999.99 excluded.\n"
        "# Edit freely; one symbol per line. The panel records which symbols each run used.\n"
        + "\n".join(syms) + "\n", encoding="utf-8")
    return {"settlement_date": latest["settlement_date"], "symbols": len(syms),
            "path": str(WATCHLIST.relative_to(ROOT))}


def _ibd_latest(payload):
    """Pull the most recent {time, fee, available} point out of whatever shape came back.

    The response shape could not be re-probed while writing this: as of 2026-08-17 the host
    closes every /api/* connection from this address without a response. Rather than pin a
    shape from memory -- which is how a collector silently stores nulls for a year -- this
    accepts a bare list, a wrapped series under any of the plausible keys, or a flat object,
    and returns None if none of them carry a `fee`. A None is logged as zero rows, which is
    visible; a row of nulls would not be.
    """
    def _pick(seq):
        pts = [p for p in seq if isinstance(p, dict) and p.get("fee") is not None]
        return pts[-1] if pts else None

    if isinstance(payload, list):
        return _pick(payload)
    if isinstance(payload, dict):
        for key in ("real_time_rates", "rates", "data", "history", "series", "daily_rates"):
            value = payload.get(key)
            if isinstance(value, list) and value:
                point = _pick(value)
                if point:
                    return point
        if payload.get("fee") is not None:
            return payload
    return None


def collect_iborrowdesk(run_id: str, force: bool = False, max_symbols: int = WATCHLIST_SIZE) -> dict:
    today = utcnow().date().isoformat()
    held = {r.get("asof_date") for r in manifest_records(BORROW_MANIFEST)
            if r.get("panel") == "iborrowdesk_borrow_fee"}
    if today in held and not force:
        return {"skipped": "already snapshotted this UTC day", "asof_date": today}

    symbols = read_watchlist()[:max_symbols]
    if not symbols:
        return {"skipped": "watchlist empty; run `seed-watchlist`", "asof_date": today}

    rows, errors = [], []
    consecutive = 0
    for sym in symbols:
        try:
            payload, _ = get_json(IBD_TICKER.format(sym=sym),
                                  {"Accept": "application/json"}, timeout=45)
        except Exception as exc:                      # noqa: BLE001 -- recorded, not hidden
            errors.append({"symbol": sym, "error": f"{type(exc).__name__}: {exc}"})
            consecutive += 1
            # A remote that has stopped answering is not a remote to keep hitting.  nginx 444
            # presents as a bare connection close, so five in a row is treated as a ban and
            # the leg gives up for the day rather than hammering.
            if consecutive >= 5:
                break
            continue
        consecutive = 0
        latest = _ibd_latest(payload)
        if latest:
            rows.append({"symbol": sym, "time": latest.get("time"),
                         "fee": latest.get("fee"), "available": latest.get("available"),
                         "rebate_rate": latest.get("rebate_rate")})

    if not rows:
        record = {
            "panel": "iborrowdesk_borrow_fee",
            "asof_date": today,
            "observed_utc": iso(),
            "run_id": run_id,
            "status": "FAILED",
            "rows": 0,
            "symbols_attempted": len(symbols),
            "errors": errors[:10],
            "error_count": len(errors),
            "source": IBD_TICKER,
            "note": ("no rows obtained -- the host closes /api/* connections without a "
                     "response (nginx 444) once rate-limited. Recorded as a failure so the "
                     "gap in the panel is visible rather than silent."),
        }
        append_jsonl(BORROW_MANIFEST, record)
        print(f"  IBORROWDESK {today}  FAILED  {len(errors)} errors, 0 rows", flush=True)
        return record

    observed = utcnow()
    path = IBD_RAW / f"asof={today}" / f"observed={stamp(observed)}.csv.gz"
    meta = write_snapshot(path, rows, IBD_FIELDS)
    record = {
        "panel": "iborrowdesk_borrow_fee",
        "asof_date": today,
        "observed_utc": iso(observed),
        "run_id": run_id,
        "status": "OK",
        "path": str(path.relative_to(ROOT)),
        "rows": meta["rows"],
        "bytes": meta["bytes"],
        "sha256": meta["sha256"],
        "symbols_attempted": len(symbols),
        "error_count": len(errors),
        "source": IBD_TICKER,
    }
    append_jsonl(BORROW_MANIFEST, record)
    print(f"  IBORROWDESK {today}  {meta['rows']} symbols  {len(errors)} errors", flush=True)
    return record


# --------------------------------------------------------------------------------------
# coverage + verification
# --------------------------------------------------------------------------------------

def build_coverage() -> dict:
    finra = manifest_records(FINRA_MANIFEST)
    borrow = manifest_records(BORROW_MANIFEST)
    first_seen = manifest_records(FIRST_SEEN)
    regsho = manifest_records(REGSHO_MANIFEST)
    rs_ok = sorted({r["session_date"] for r in regsho if r.get("status") == "OK"})

    dates = sorted({r["settlement_date"] for r in finra})
    forward = [r["settlement_date"] for r in first_seen if r.get("is_discovery")]
    # Rows are counted over the LATEST snapshot of each settlement date, not over every
    # snapshot.  Summing every snapshot would inflate the panel by exactly the number of
    # revision re-observations -- i.e. the count would grow fastest when the LEAST new
    # information arrived, which is the wrong direction for a coverage number to move.
    latest_by_date: dict[str, dict] = {}
    for record in finra:
        key = record["settlement_date"]
        if record["observed_utc"] >= latest_by_date.get(key, {}).get("observed_utc", ""):
            latest_by_date[key] = record
    alpaca = sorted({r["asof_date"] for r in borrow
                     if r.get("panel") == "alpaca_asset_borrow_flags"})
    ibd_ok = sorted({r["asof_date"] for r in borrow
                     if r.get("panel") == "iborrowdesk_borrow_fee" and r.get("status") == "OK"})
    ibd_fail = sorted({r["asof_date"] for r in borrow
                       if r.get("panel") == "iborrowdesk_borrow_fee"
                       and r.get("status") == "FAILED"})

    cov = {
        "generated_utc": iso(),
        "what_this_is": (
            "A collection asset, not a result. No number here is evidence for or against "
            "any strategy."
        ),
        "finra_short_interest": {
            "settlement_dates_held": len(dates),
            "range": [dates[0], dates[-1]] if dates else None,
            "rows_held": sum(r["rows"] for r in latest_by_date.values()),
            "rows_across_all_snapshots": sum(r["rows"] for r in finra),
            "snapshots": len(finra),
            "revision_observations": sum(1 for r in finra if r.get("is_revision_observation")),
            "backfilled_dates": len({r["settlement_date"] for r in finra if r.get("backfill")}),
            "forward_observed_dates": sorted(set(forward)),
            "bytes": sum(r["bytes"] for r in finra),
        },
        "finra_regsho_daily_short_volume": {
            "sessions_held": len(rs_ok),
            "range": [rs_ok[0], rs_ok[-1]] if rs_ok else None,
            "rows_held": sum(r.get("rows", 0) for r in regsho if r.get("status") == "OK"),
            "snapshots": sum(1 for r in regsho if r.get("status") == "OK"),
            "unavailable_dates": sum(1 for r in regsho if r.get("status") == "UNAVAILABLE"),
            "backfilled_sessions": len({r["session_date"] for r in regsho
                                        if r.get("status") == "OK" and r.get("backfill")}),
            "forward_observed_sessions": len({r["session_date"] for r in regsho
                                              if r.get("status") == "OK"
                                              and not r.get("backfill")}),
            "bytes": sum(r.get("bytes", 0) for r in regsho if r.get("status") == "OK"),
            "note": ("Daily, 252 obs/yr against panel 1's 24. The CDN keeps only a rolling "
                     "retention window (2018-07-02 denied, 2018-08-01 served when probed on "
                     "2026-08-17), so this history is NOT fully recoverable later -- unlike "
                     "the short-interest panel, a day not collected is a day lost."),
        },
        "alpaca_asset_borrow_flags": {
            "days_held": len(alpaca),
            "range": [alpaca[0], alpaca[-1]] if alpaca else None,
            "rows_held": sum(r["rows"] for r in borrow
                             if r.get("panel") == "alpaca_asset_borrow_flags"),
        },
        "iborrowdesk_borrow_fee": {
            "days_ok": len(ibd_ok),
            "days_failed": len(ibd_fail),
            "range": [ibd_ok[0], ibd_ok[-1]] if ibd_ok else None,
            "rows_held": sum(r.get("rows", 0) for r in borrow
                             if r.get("panel") == "iborrowdesk_borrow_fee"),
            "note": ("DEAD at the source, not broken here: the host answers every /api/ path "
                     "with a bare connection close (nginx 444), re-probed 2026-08-17. IBKR's "
                     "own file is unreachable too. There is no free borrow-FEE source we can "
                     "reach; the panel records the failure daily rather than hiding it, and "
                     "will start accruing by itself if the host ever answers again."),
        },
        "point_in_time_warning": (
            "Backfilled FINRA settlement dates are NOT point-in-time: they carry revisions "
            "applied before this panel existed, and FINRA disseminates a date ~8 business "
            "days after it settles. Only dates in forward_observed_dates carry a first_seen "
            "timestamp that bounds real availability. A backtest keying a backfilled date to "
            "its settlement date is looking into the future."
        ),
        "power_warning": (
            "24 settlement dates a year. Any strategy keyed on the SI cycle has ~110 "
            "bi-monthly observations in a 2022+ held-out window. DATA_PURCHASE_SCOPE.md "
            "puts P(pass) for shortlist candidate #9 at ~0.05. This panel is an option, "
            "not an edge."
        ),
    }
    COVERAGE.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE.write_text(json.dumps(cov, indent=2) + "\n", encoding="utf-8")
    return cov


def selftest() -> int:
    """Offline checks of the two properties the panel's value rests on.

    No network, no credentials, and nothing written outside a temp directory. The properties
    are (a) a sealed snapshot cannot be overwritten and (b) its sha256 is a hash of the DATA,
    not of the moment it was written -- without (b), `verify` could not tell a restored copy
    from a tampered one and the append-only claim would be unfalsifiable.
    """
    import shutil
    import tempfile

    failures: list[str] = []
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="t16_selftest_"))
    try:
        rows = [{"settlementDate": "2020-01-15", "symbolCode": "AAPL"},
                {"settlementDate": "2020-01-15", "symbolCode": "MSFT"}]
        fields = ["settlementDate", "symbolCode"]
        first = write_snapshot(tmp / "a" / "observed=20200116T000000Z.csv.gz", rows, fields)

        # (a) an existing path must refuse, not clobber
        try:
            write_snapshot(tmp / "a" / "observed=20200116T000000Z.csv.gz",
                           [{"settlementDate": "x", "symbolCode": "y"}], fields)
            failures.append("write_snapshot OVERWROTE an existing snapshot")
        except Refused:
            pass

        # (b) same rows, different path and different moment -> same digest
        second = write_snapshot(tmp / "b" / "observed=20990101T000000Z.csv.gz", rows, fields)
        if first["sha256"] != second["sha256"]:
            failures.append("sha256 is not a function of the data alone")
        if first["rows"] != 2:
            failures.append(f"row count wrong: {first['rows']}")

        # (c) a truncated file must be caught by re-hashing, which is what `verify` does
        path = tmp / "a" / "observed=20200116T000000Z.csv.gz"
        path.write_bytes(path.read_bytes()[:-5])
        if hashlib.sha256(path.read_bytes()).hexdigest() == first["sha256"]:
            failures.append("a truncated snapshot still matched its manifest hash")

        # (d) the borrow-fee parser must return None rather than a row of nulls
        if _ibd_latest({"rates": [{"time": "t", "fee": None}]}) is not None:
            failures.append("_ibd_latest returned a fee-less point")
        if (_ibd_latest([{"fee": 1.0}, {"fee": 2.0}]) or {}).get("fee") != 2.0:
            failures.append("_ibd_latest did not take the LAST priced point")

        # (e) the Reg SHO parser must honour the file's own footer count.  A truncated
        # download is the failure mode that a daily panel cannot recover from later, because
        # nothing afterwards distinguishes a short file from a quiet session.
        good = ("Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
                "20260814|AAPL|100.5|7|300.25|B,Q,N\n"
                "20260814|MSFT|50|0|200|Q\n2\n")
        parsed = parse_regsho(good, "20260814")
        if len(parsed) != 2 or parsed[0]["date"] != "2026-08-14":
            failures.append(f"parse_regsho mis-parsed a good file: {parsed}")
        if parsed[1]["symbol"] != "MSFT" or parsed[1]["total_volume"] != "200":
            failures.append("parse_regsho lost a field")
        try:
            parse_regsho(good.replace("\n2\n", "\n7\n"), "20260814")
            failures.append("parse_regsho SEALED a file whose footer count disagreed")
        except Refused:
            pass
        try:
            parse_regsho("Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
                         "20260813|AAPL|1|0|2|Q\n1\n", "20260814")
            failures.append("parse_regsho accepted rows carrying the WRONG session date")
        except Refused:
            pass
        try:
            parse_regsho("<?xml version=\"1.0\"?><Error>AccessDenied</Error>", "20260814")
            failures.append("parse_regsho accepted an error page as data")
        except Refused:
            pass

        # (f) the Reg SHO calendar must be weekday-only and inclusive at both ends
        cal = _regsho_calendar("2026-08-07", date_cls(2026, 8, 11))
        if cal != ["2026-08-07", "2026-08-10", "2026-08-11"]:
            failures.append(f"_regsho_calendar wrong: {cal}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for line in failures:
        print(f"FAIL  {line}")
    if not failures:
        print("t16 selftest OK -- append-only refusal, data-only hashing, truncation "
              "detection, fee-parser null discipline, Reg SHO footer/date/error-page "
              "refusal, weekday calendar")
    return 1 if failures else 0


def verify() -> dict:
    """Re-hash every sealed snapshot.  This is the append-only guarantee's only proof."""
    ok, bad, missing = 0, [], []
    for record in (manifest_records(FINRA_MANIFEST) + manifest_records(BORROW_MANIFEST)
                   + manifest_records(REGSHO_MANIFEST)):
        rel = record.get("path")
        if not rel:
            continue
        path = ROOT / rel
        if not path.exists():
            missing.append(rel)
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest == record["sha256"]:
            ok += 1
        else:
            bad.append({"path": rel, "manifest_sha256": record["sha256"], "on_disk": digest})
    return {"verified": ok, "mismatched": bad, "missing": missing,
            "append_only_intact": not bad and not missing}


# --------------------------------------------------------------------------------------
# entrypoints
# --------------------------------------------------------------------------------------

CRONTAB_LINE = ("17 * * * * /home/anont/meme/scripts/trading_bot/t16_entrypoint.sh"
                "  # T16 free forward panels (idempotent; no-op once the day is collected)")

# Optional second line. Hourly collection never re-reads a date it already holds, so on its
# own it would never observe a FINRA revision. This one does, once a week, for the four most
# recent settlement dates -- ~2.5 MB a year, and it writes NEW snapshots beside the originals.
CRONTAB_LINE_REVISIONS = (
    "41 6 * * 0 /home/anont/meme/scripts/trading_bot/t16_entrypoint.sh --revisions"
    "  # T16 weekly FINRA revision re-observation (append-only; never overwrites)")


def run(mode: str, args) -> dict:
    run_id = stamp()
    started = utcnow()
    print(f"T16 {mode}  run_id={run_id}", flush=True)

    result: dict = {"run_id": run_id, "mode": mode, "started_utc": iso(started)}
    try:
        if mode in ("backfill", "daily"):
            result["finra"] = collect_finra(
                refresh_revisions=getattr(args, "refresh_revisions", False),
                limit_dates=getattr(args, "limit_dates", None),
                run_id=run_id,
                refresh_recent=getattr(args, "refresh_recent", 0),
                refresh_age_days=getattr(args, "refresh_age_days", 7),
            )
            # Leg 4 is its own try/except: it is a different host on a different cadence and
            # a CDN outage must not cost us the short-interest leg's first-seen timestamps.
            try:
                result["regsho"] = collect_regsho(
                    run_id,
                    since=getattr(args, "regsho_since", None) or REGSHO_EARLIEST,
                    limit_dates=getattr(args, "regsho_limit", None),
                )
            except Exception as exc:                  # noqa: BLE001 -- recorded, not hidden
                result["regsho"] = {"status": "FAILED",
                                    "error": f"{type(exc).__name__}: {exc}"}
                print(f"  REGSHO FAILED {type(exc).__name__}: {exc}", flush=True)
        if mode == "daily":
            if not read_watchlist():
                try:
                    result["watchlist"] = seed_watchlist()
                except Refused as exc:
                    result["watchlist"] = {"skipped": str(exc)}
            try:
                result["alpaca"] = collect_alpaca_assets(run_id, force=getattr(args, "force", False))
            except Exception as exc:                  # noqa: BLE001 -- recorded, not hidden
                result["alpaca"] = {"status": "FAILED",
                                    "error": f"{type(exc).__name__}: {exc}"}
                print(f"  ALPACA FAILED {type(exc).__name__}: {exc}", flush=True)
            result["iborrowdesk"] = collect_iborrowdesk(run_id, force=getattr(args, "force", False))
        result["status"] = "OK"
    except Exception as exc:                          # noqa: BLE001 -- recorded, then re-raised
        result["status"] = "FAILED"
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["finished_utc"] = iso()
        append_jsonl(COLLECTION_LOG, result)
        raise

    result["finished_utc"] = iso()
    result["elapsed_seconds"] = round((utcnow() - started).total_seconds(), 1)
    result["coverage"] = build_coverage()
    append_jsonl(COLLECTION_LOG, result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="T16 -- free forward-data panels (FINRA short interest + borrow mirrors). "
                    "Collection only: no orders, no purchases, no crontab installation.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_back = sub.add_parser("backfill", help="fetch every FINRA settlement date not yet held")
    p_back.add_argument("--limit-dates", type=int, default=None,
                        help="fetch at most N of the most recent missing dates")
    p_back.add_argument("--refresh-revisions", action="store_true",
                        help="re-observe dates already held; writes NEW snapshots, "
                             "never overwrites the originals")
    p_back.add_argument("--regsho-since", default=None,
                        help=f"earliest Reg SHO session to attempt (default {REGSHO_EARLIEST})")
    p_back.add_argument("--regsho-limit", type=int, default=None,
                        help="fetch at most N of the most recent missing Reg SHO sessions")

    p_daily = sub.add_parser("daily", help="the cron entrypoint: poll all four panels once")
    p_daily.add_argument("--force", action="store_true",
                         help="re-snapshot the borrow legs even if today is already held")
    p_daily.add_argument("--limit-dates", type=int, default=None)
    p_daily.add_argument("--refresh-revisions", action="store_true")
    p_daily.add_argument("--regsho-since", default=None)
    p_daily.add_argument("--regsho-limit", type=int, default=None)
    p_daily.add_argument("--refresh-recent", type=int, default=0,
                         help="re-observe the N most recent settlement dates when their last "
                              "observation is older than --refresh-age-days, capturing FINRA "
                              "revisions as a SECOND snapshot (never an overwrite). 0 = off; "
                              "the weekly crontab line uses 4.")
    p_daily.add_argument("--refresh-age-days", type=int, default=7,
                         help="minimum age of the last observation before --refresh-recent "
                              "re-observes a date (default 7)")

    sub.add_parser("selftest", help="offline checks; no network, no credentials")
    sub.add_parser("coverage", help="rebuild and print COVERAGE.json")
    sub.add_parser("verify", help="re-hash every sealed snapshot against the manifest")
    sub.add_parser("crontab-line", help="print the crontab line for the OWNER to install")
    p_seed = sub.add_parser("seed-watchlist", help="seed the borrow-fee watchlist from FINRA")
    p_seed.add_argument("--size", type=int, default=WATCHLIST_SIZE)

    args = parser.parse_args(argv)

    if args.cmd == "crontab-line":
        print("# Install with `crontab -e`. This script does NOT install it for you.")
        print(CRONTAB_LINE)
        print("#")
        print("# Optional, recommended -- without it no FINRA revision is ever observed:")
        print(CRONTAB_LINE_REVISIONS)
        return 0
    if args.cmd == "selftest":
        return selftest()
    if args.cmd == "coverage":
        print(json.dumps(build_coverage(), indent=2))
        return 0
    if args.cmd == "verify":
        out = verify()
        print(json.dumps(out, indent=2))
        return 0 if out["append_only_intact"] else 1
    if args.cmd == "seed-watchlist":
        print(json.dumps(seed_watchlist(args.size), indent=2))
        return 0

    out = run(args.cmd, args)
    print(json.dumps({k: v for k, v in out.items() if k != "coverage"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
