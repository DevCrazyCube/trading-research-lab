#!/usr/bin/env python3
"""T31 — daily Deribit BTC/ETH option-chain forward snapshot collector.

The convexity-wall finding: bought convexity cannot be tested because historical
option quotes are not free. The one identified escape is to forward-collect the
quotes NOW so the test becomes possible in months. This script is that collector.

Public, keyless Deribit REST only (no account, no keys, no orders):
  public/get_instruments               strike / expiry / type metadata
  public/get_book_summary_by_currency  full chain: bid/ask/mark/mark_iv/OI/underlying
  public/get_order_book (depth=1)      near-expiry enrichment (DTE <= 14): bid/ask
                                       SIZE, bid_iv/ask_iv, exchange GREEKS
  public/get_delivery_prices           daily 08:00 UTC settlement prints (outcomes)

Archive layout under research/data/deribit_forward/:
  snapshots/snapshot_YYYY-MM-DD.csv.gz   one clean chain snapshot per UTC day, in
                                          the Tardis options_chain column layout
                                          (+ trailing extra columns), so the existing
                                          deribit_wing_estimator.py reads it unchanged
  partial/                                failed/incomplete captures kept for forensics
  delivery_prices.json                    cumulative {index: {date: settlement}}
  manifest.json                           per-day sha256 + counts + provenance
  ledger.json                             completeness ledger (attempted/clean/failed)
  collect.log

Clean-day criteria: both currencies return >= MIN_INSTRUMENTS summary rows AND
>= MIN_ENRICH_FRAC of their DTE<=14 instruments were enriched from the order book.

Usage:
  t31_deribit_collect.py            capture today's (UTC) snapshot
  t31_deribit_collect.py --status   print ledger summary and exit

Research/paper programme infrastructure. Never touches the t4 path.
"""
import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "..", "research", "data", "deribit_forward"))
API = "https://www.deribit.com/api/v2/public/"
CURRENCIES = ["BTC", "ETH"]
ENRICH_DTE_MAX = 14.0
MIN_INSTRUMENTS = 300          # BTC 932 / ETH 820 listed on 2026-08-24
MIN_ENRICH_FRAC = 0.95
MIN_INTERVAL = 0.12            # ~8 req/s; Deribit public non-matching limit is 20/s
DELIVERY_COUNT = 40

# Tardis options_chain layout first (consumer compatibility), extras after.
TARDIS_COLS = ["exchange", "symbol", "timestamp", "local_timestamp", "type",
               "strike_price", "expiration", "open_interest", "last_price",
               "bid_price", "bid_amount", "bid_iv", "ask_price", "ask_amount",
               "ask_iv", "mark_price", "mark_iv", "underlying_index",
               "underlying_price", "delta", "gamma", "vega", "theta", "rho"]
EXTRA_COLS = ["source", "volume", "volume_usd", "interest_rate", "index_price"]
COLS = TARDIS_COLS + EXTRA_COLS

_next_slot = [0.0]


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


def _throttle():
    now = time.monotonic()
    slot = max(now, _next_slot[0])
    _next_slot[0] = slot + MIN_INTERVAL
    if slot > now:
        time.sleep(slot - now)


def get(method, params, tries=6):
    url = API + method + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(tries):
        _throttle()
        try:
            with urllib.request.urlopen(url, timeout=30) as fh:
                body = json.load(fh)
            if "result" in body:
                return body["result"]
            last = body.get("error")
            if last and last.get("code") in (-32602, 13008, 13009):  # bad instrument etc.
                return None
        except urllib.error.HTTPError as exc:
            last = "HTTP %d" % exc.code
            if exc.code == 429:
                time.sleep(2.0 * (attempt + 1))
        except Exception as exc:  # noqa: BLE001 - transport-shaped, retry
            last = repr(exc)
        time.sleep(0.8 * (attempt + 1))
    raise RuntimeError("%s failed after %d tries: %s" % (method, tries, last))


def collect_currency(cur, now_us):
    ins = get("get_instruments", {"currency": cur, "kind": "option", "expired": "false"})
    meta = {i["instrument_name"]: i for i in ins}
    summ = get("get_book_summary_by_currency", {"currency": cur, "kind": "option"})
    rows = {}
    for s in summ:
        name = s["instrument_name"]
        m = meta.get(name)
        if m is None:
            continue
        rows[name] = {
            "exchange": "deribit", "symbol": name,
            "timestamp": int(s.get("creation_timestamp") or 0) * 1000,
            "local_timestamp": now_us, "type": m["option_type"],
            "strike_price": m["strike"], "expiration": int(m["expiration_timestamp"]) * 1000,
            "open_interest": s.get("open_interest"), "last_price": s.get("last"),
            "bid_price": s.get("bid_price"), "bid_amount": "", "bid_iv": "",
            "ask_price": s.get("ask_price"), "ask_amount": "", "ask_iv": "",
            "mark_price": s.get("mark_price"), "mark_iv": s.get("mark_iv"),
            "underlying_index": s.get("underlying_index"),
            "underlying_price": s.get("underlying_price"),
            "delta": "", "gamma": "", "vega": "", "theta": "", "rho": "",
            "source": "summary", "volume": s.get("volume"), "volume_usd": s.get("volume_usd"),
            "interest_rate": s.get("interest_rate"),
            "index_price": s.get("estimated_delivery_price"),
        }
    near = [n for n, r in rows.items()
            if (r["expiration"] - now_us) / 86400e6 <= ENRICH_DTE_MAX]
    enriched, failed = 0, []
    for name in sorted(near):
        try:
            ob = get("get_order_book", {"instrument_name": name, "depth": 1})
        except RuntimeError as exc:
            failed.append(name)
            log("order_book %s: %s" % (name, exc))
            continue
        if not ob:
            failed.append(name)
            continue
        r = rows[name]
        g = ob.get("greeks") or {}
        r.update({
            "timestamp": int(ob.get("timestamp") or 0) * 1000,
            "bid_price": ob.get("best_bid_price"), "bid_amount": ob.get("best_bid_amount"),
            "bid_iv": ob.get("bid_iv"), "ask_price": ob.get("best_ask_price"),
            "ask_amount": ob.get("best_ask_amount"), "ask_iv": ob.get("ask_iv"),
            "mark_price": ob.get("mark_price"), "mark_iv": ob.get("mark_iv"),
            "underlying_index": ob.get("underlying_index"),
            "underlying_price": ob.get("underlying_price"),
            "open_interest": ob.get("open_interest"), "last_price": ob.get("last_price"),
            "delta": g.get("delta"), "gamma": g.get("gamma"), "vega": g.get("vega"),
            "theta": g.get("theta"), "rho": g.get("rho"),
            "interest_rate": ob.get("interest_rate"), "index_price": ob.get("index_price"),
            "source": "order_book",
        })
        enriched += 1
    stats = {"instruments_listed": len(ins), "summary_rows": len(rows),
             "near_expiry": len(near), "enriched": enriched, "enrich_failed": len(failed),
             "enrich_frac": (enriched / len(near)) if near else None,
             "expiries": len({r["expiration"] for r in rows.values()})}
    return rows, stats


def update_delivery_prices():
    path = os.path.join(BASE, "delivery_prices.json")
    book = load_json(path, {})
    added = 0
    for idx in ("btc_usd", "eth_usd"):
        try:
            res = get("get_delivery_prices", {"index_name": idx, "count": DELIVERY_COUNT})
        except RuntimeError as exc:
            log("delivery_prices %s: %s" % (idx, exc))
            continue
        d = book.setdefault(idx, {})
        for rec in (res or {}).get("data", []):
            if rec["date"] not in d:
                d[rec["date"]] = rec["delivery_price"]
                added += 1
    save_json(path, book)
    return added


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


def write_csv(path, rows):
    with gzip.open(path, "wt", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in COLS})
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest(), os.path.getsize(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--date", default=None, help="UTC date label (default: today UTC)")
    args = ap.parse_args()
    for sub in ("snapshots", "partial"):
        os.makedirs(os.path.join(BASE, sub), exist_ok=True)
    ledger_path = os.path.join(BASE, "ledger.json")
    manifest_path = os.path.join(BASE, "manifest.json")
    if args.status:
        print(json.dumps(load_json(ledger_path, {}), indent=1, sort_keys=True))
        return 0

    now = dt.datetime.now(dt.timezone.utc)
    date = args.date or now.strftime("%Y-%m-%d")
    now_us = int(now.timestamp() * 1e6)
    out_path = os.path.join(BASE, "snapshots", "snapshot_%s.csv.gz" % date)
    manifest = load_json(manifest_path, {})
    if date in manifest and os.path.exists(out_path):
        log("snapshot for %s already clean; nothing to do" % date)
        return 0

    t0 = time.monotonic()
    all_rows, per_cur, reasons = [], {}, []
    for cur in CURRENCIES:
        try:
            rows, stats = collect_currency(cur, now_us)
        except RuntimeError as exc:
            reasons.append("%s: %s" % (cur, exc))
            per_cur[cur] = {"error": str(exc)}
            continue
        per_cur[cur] = stats
        all_rows.extend(rows.values())
        if stats["summary_rows"] < MIN_INSTRUMENTS:
            reasons.append("%s: only %d summary rows" % (cur, stats["summary_rows"]))
        if stats["enrich_frac"] is not None and stats["enrich_frac"] < MIN_ENRICH_FRAC:
            reasons.append("%s: enrich frac %.3f < %.2f" % (cur, stats["enrich_frac"], MIN_ENRICH_FRAC))
    added = update_delivery_prices()
    elapsed = round(time.monotonic() - t0, 1)

    if reasons:
        ppath = os.path.join(BASE, "partial", "partial_%s_%s.csv.gz" % (date, now.strftime("%H%M%S")))
        if all_rows:
            write_csv(ppath, all_rows)
        summary = record(ledger_path, date, "failed", "; ".join(reasons))
        log("FAILED %s: %s; %d rows kept in partial/; ledger %s" % (date, "; ".join(reasons), len(all_rows), summary))
        return 1

    sha, nbytes = write_csv(out_path, all_rows)
    manifest[date] = {
        "sha256": sha, "bytes": nbytes, "rows": len(all_rows),
        "captured_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "elapsed_s": elapsed, "per_currency": per_cur,
        "delivery_prices_added": added,
        "source": "deribit public REST v2 (book_summary + order_book depth=1 for DTE<=%g)" % ENRICH_DTE_MAX,
    }
    save_json(manifest_path, manifest)
    summary = record(ledger_path, date, "clean")
    log("CLEAN %s: %d rows (%s) in %ss; delivery prints +%d; ledger %s"
        % (date, len(all_rows),
           ", ".join("%s %d/%d enriched" % (c, s.get("enriched", 0), s.get("near_expiry", 0)) for c, s in per_cur.items()),
           elapsed, added, summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
