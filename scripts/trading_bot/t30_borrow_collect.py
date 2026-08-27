#!/usr/bin/env python3
"""T30 — daily IBKR shortstock (usa.txt) borrow fee/availability collector.

Fetches Interactive Brokers' public securities-lending availability file
(SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|AVAILABLE|FIGI) and archives one
clean snapshot per calendar day under research/data/borrow_forward/:

  raw/usa_YYYY-MM-DD.txt.gz     full file, gzipped
  extract/extract_YYYY-MM-DD.json   rows for the 602-symbol target universe
  manifest.json                 per-day sha256 + counts + provenance
  ledger.json                   completeness ledger (attempted/clean/failed)

Access-path facts (measured 2026-08-24 from this box):
  ftp2.interactivebrokers.com  port 21  -> WORKS
  ftp3.interactivebrokers.com  port 21  -> connect-timeout
  ftp.interactivebrokers.com   port 21  -> connect-timeout
  ftps (990)                   -> connect-timeout
  generic port-21 egress (ftp.gnu.org) -> works, so the wall is host-side,
  not our firewall. ftp2 is tried first; the others remain as fallbacks.

Usage:
  t30_borrow_collect.py            fetch + archive today's snapshot
  t30_borrow_collect.py --ingest F archive a usa.txt fetched elsewhere
  t30_borrow_collect.py --status   print ledger summary and exit

Research/paper programme infrastructure. Public keyless data, one file per
day, no account, no orders, no spending. Never touches the t4 path.
"""
import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
import time

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                    "research", "data", "borrow_forward")
BASE = os.path.normpath(BASE)
HOSTS = ["ftp2.interactivebrokers.com",
         "ftp3.interactivebrokers.com",
         "ftp.interactivebrokers.com"]
MIN_ROWS = 5000          # sanity floor; file carried 19,676 rows on 2026-08-23
CURL_TIMEOUT_S = 180

FIELDS = ["SYM", "CUR", "NAME", "CON", "ISIN",
          "REBATERATE", "FEERATE", "AVAILABLE", "FIGI"]


def log(msg):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    line = "[%s] %s" % (stamp, msg)
    print(line, flush=True)
    with open(os.path.join(BASE, "collect.log"), "a") as fh:
        fh.write(line + "\n")


def load_json(path, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (IOError, ValueError):
        return default


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


def fetch(host):
    """Fetch usa.txt from one host; returns bytes or None."""
    url = "ftp://shortstock:@%s/usa.txt" % host
    try:
        out = subprocess.run(
            ["curl", "-sS", "--connect-timeout", "25",
             "--max-time", str(CURL_TIMEOUT_S), url, "-o", "-"],
            capture_output=True, timeout=CURL_TIMEOUT_S + 30)
    except (subprocess.TimeoutExpired, OSError) as exc:
        log("fetch %s: %s" % (host, exc))
        return None
    if out.returncode != 0:
        log("fetch %s: curl exit %d %s"
            % (host, out.returncode, out.stderr.decode(errors="replace")[:200]))
        return None
    return out.stdout


def validate(raw):
    """Return (rows, bof_stamp, reason). rows is None when invalid."""
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception as exc:  # pragma: no cover
        return None, None, "decode: %s" % exc
    lines = text.splitlines()
    if len(lines) < MIN_ROWS:
        return None, None, "only %d lines" % len(lines)
    if not lines[0].startswith("#BOF|"):
        return None, None, "missing #BOF header"
    if not lines[1].startswith("#SYM|"):
        return None, None, "missing field header"
    bof = lines[0].split("|", 1)[1]
    data = [ln for ln in lines[2:] if ln and not ln.startswith("#")]
    eof = [ln for ln in lines if ln.startswith("#EOF|")]
    if eof:
        try:
            declared = int(eof[-1].split("|")[1])
        except (IndexError, ValueError):
            declared = None
        if declared is not None and declared != len(data):
            return None, None, ("row-count mismatch: #EOF says %s, parsed %d"
                                % (declared, len(data)))
    if len(data) < MIN_ROWS:
        return None, None, "only %d data rows" % len(data)
    rows = []
    for ln in data:
        parts = ln.split("|")
        if len(parts) < 9:
            continue
        rows.append(dict(zip(FIELDS, parts[:9])))
    return rows, bof, None


def extract_universe(rows):
    uni = load_json(os.path.join(BASE, "universe.json"), None)
    if uni is None:
        return None, 0
    targets = set(uni["symbols_ibkr"])
    hit = [r for r in rows if r["SYM"] in targets]
    return hit, len(targets)


def record(ledger_path, date, status, reason=None):
    ledger = load_json(ledger_path, {"days": {}})
    day = ledger["days"].get(date, {"attempts": 0})
    day["attempts"] = day.get("attempts", 0) + 1
    day["status"] = status
    if reason:
        day["last_failure_reason"] = reason
    elif "last_failure_reason" in day and status == "clean":
        day["recovered_after_failure"] = day.pop("last_failure_reason")
    ledger["days"][date] = day
    days = ledger["days"]
    ledger["summary"] = {
        "days_attempted": len(days),
        "days_clean": sum(1 for d in days.values() if d["status"] == "clean"),
        "days_failed": sum(1 for d in days.values() if d["status"] != "clean"),
        "updated": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
    }
    save_json(ledger_path, ledger)
    return ledger["summary"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ingest", metavar="FILE",
                    help="archive a usa.txt fetched on another machine")
    ap.add_argument("--date", default=time.strftime("%Y-%m-%d"),
                    help="snapshot date label (default: today, local)")
    ap.add_argument("--status", action="store_true",
                    help="print ledger summary and exit")
    args = ap.parse_args()

    for sub in ("raw", "extract"):
        os.makedirs(os.path.join(BASE, sub), exist_ok=True)
    ledger_path = os.path.join(BASE, "ledger.json")
    manifest_path = os.path.join(BASE, "manifest.json")

    if args.status:
        print(json.dumps(load_json(ledger_path, {}), indent=1, sort_keys=True))
        return 0

    date = args.date
    raw_path = os.path.join(BASE, "raw", "usa_%s.txt.gz" % date)
    manifest = load_json(manifest_path, {})
    if date in manifest and os.path.exists(raw_path):
        log("snapshot for %s already clean; nothing to do" % date)
        return 0

    raw, host = None, None
    if args.ingest:
        with open(args.ingest, "rb") as fh:
            raw = fh.read()
        host = "ingest:%s" % args.ingest
    else:
        for h in HOSTS:
            raw = fetch(h)
            if raw:
                host = h
                break

    if not raw:
        summary = record(ledger_path, date, "failed", "all hosts unreachable")
        log("FAILED %s: all hosts unreachable; ledger %s" % (date, summary))
        return 1

    rows, bof, reason = validate(raw)
    if rows is None:
        summary = record(ledger_path, date, "failed", reason)
        log("FAILED %s: invalid file (%s); ledger %s" % (date, reason, summary))
        return 1

    with gzip.open(raw_path, "wb") as fh:
        fh.write(raw)
    hit, n_targets = extract_universe(rows)
    if hit is not None:
        save_json(os.path.join(BASE, "extract", "extract_%s.json" % date),
                  {"date": date, "bof": bof, "n_universe": n_targets,
                   "n_matched": len(hit), "rows": hit})
    n_pref = sum(1 for r in rows if " PR" in r["SYM"])
    manifest[date] = {
        "sha256_raw": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "rows": len(rows),
        "pref_rows": n_pref,
        "universe_matched": len(hit) if hit is not None else None,
        "bof_stamp": bof,
        "host": host,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
    }
    save_json(manifest_path, manifest)
    summary = record(ledger_path, date, "clean")
    log("CLEAN %s: %d rows (%d pref, %d/%d universe) from %s; ledger %s"
        % (date, len(rows), n_pref,
           len(hit) if hit is not None else -1, n_targets, host, summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
