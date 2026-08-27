#!/usr/bin/env python3
"""T33 — daily Alpaca US-options chain forward snapshot collector (goal universe).

T31 forward-collects Deribit BTC/ETH wing quotes so bought convexity becomes testable
in months. The programme's goal names US equities/ETFs; this script collects the same
kind of panel there, from the free Alpaca options snapshot endpoint that T32 proved
returns full chains with bid/ask under the paper keys (13/13 clean RTH pulls).

Quotes only: NO orders of any kind, paper or otherwise. Never touches the t4 path.

Source (data.alpaca.markets, paper keys from .env, default feed as served):
  /v1beta1/options/snapshots/{underlying}   full chain: latestQuote (bid/ask/size/ts),
                                             latestTrade, impliedVolatility, greeks,
                                             dailyBar (as served); limit=1000 + page_token
  /v2/stocks/snapshots?symbols=...           underlying spot at capture (one request)
  paper-api /v2/clock                        market-open check

Universe (FROZEN 2026-08-25 before the first snapshot; recorded in the protocol doc):
  SPY QQQ IWM TLT HYG GLD XLE XLF NVDA TSLA AAPL AMZN MSFT AMD
Expiries per underlying: every listed expiry with DTE <= 45, plus the next two standard
monthlies (3rd Friday; Thursday fallback when Friday is a holiday) beyond that window.

Snapshot clock: 15:45 America/New_York on every trading day (inside RTH, before the
closing crush). The cron line fires at 20:45 Europe/Amsterdam and this script WAITS
until 15:45 ET, so the US/EU DST-mismatch weeks never push the capture past the close.

Archive layout under research/data/us_options_forward/:
  snapshots/snapshot_YYYY-MM-DD.csv.gz   one clean chain snapshot per ET trading day
  partial/                                failed/incomplete captures kept for forensics
  manifest.json                           per-day sha256 + counts + provenance
  ledger.json                             completeness ledger (attempted/clean/failed;
                                          market-closed days recorded separately)
  collect.log

Clean-day criteria: market open at capture; ALL universe underlyings returned;
each underlying has >= MIN_CONTRACTS rows.
v2 (2026-08-26): MIN_FRESH_FRAC (share of rows with a two-sided quote timestamped on the
capture ET date) is a per-underlying ELIGIBILITY flag recorded in the ledger as
day["fresh_fail"], NOT a day-kill (v1 failed the whole day on it; HYG is structurally < 0.70).

Usage:
  t33_us_options_collect.py             wait until 15:45 ET (if before), then capture
  t33_us_options_collect.py --now       capture immediately (RTH only; used for a
                                        manual first run and for tests)
  t33_us_options_collect.py --preflight fetch two underlyings, print stats, write
                                        nothing to the ledger/manifest (format check)
  t33_us_options_collect.py --status    print ledger summary and exit
  t33_us_options_collect.py --plan      print the expiry plan and the wait, no network
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
from zoneinfo import ZoneInfo

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BASE = os.path.join(REPO, "research", "data", "us_options_forward")
DATA = "https://data.alpaca.markets"
CLOCK = "https://paper-api.alpaca.markets/v2/clock"
ET = ZoneInfo("America/New_York")

UNIVERSE = ["SPY", "QQQ", "IWM", "TLT", "HYG", "GLD", "XLE", "XLF",
            "NVDA", "TSLA", "AAPL", "AMZN", "MSFT", "AMD"]
DTE_MAX = 45                 # every listed expiry inside this window
EXTRA_MONTHLIES = 2          # plus the next N standard monthlies beyond it
CAPTURE_ET = (15, 45)        # 15:45 America/New_York
MAX_WAIT_S = 2 * 3600        # never wait more than 2 h for the capture clock
MIN_CONTRACTS = 200          # per underlying (XLF ~ smallest of the set)
MIN_FRESH_FRAC = 0.70        # share of rows with a two-sided quote stamped today (ET)
MIN_INTERVAL = 0.35          # ~170 req/min; Alpaca data limit is 200/min on the free plan
PAGE_LIMIT = 1000

COLS = ["underlying", "symbol", "root", "expiration", "dte", "type", "strike",
        "bid", "bid_size", "ask", "ask_size", "quote_ts", "quote_cond",
        "last", "last_size", "last_ts", "iv", "delta", "gamma", "theta", "vega", "rho",
        "day_open", "day_high", "day_low", "day_close", "day_volume",
        "underlying_price", "underlying_ts", "captured_utc"]

_next_slot = [0.0]


def log(msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S %Z"), msg)
    print(line, flush=True)
    os.makedirs(BASE, exist_ok=True)
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


def creds():
    env = {}
    try:
        with open(os.path.join(REPO, ".env")) as fh:
            for line in fh:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except IOError:
        pass
    k = os.environ.get("ALPACA_API_KEY_ID") or env.get("ALPACA_API_KEY_ID")
    s = os.environ.get("ALPACA_API_SECRET_KEY") or env.get("ALPACA_API_SECRET_KEY")
    if not k or not s:
        raise SystemExit("no Alpaca paper keys in env/.env")
    return {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s}


def _throttle():
    now = time.monotonic()
    slot = max(now, _next_slot[0])
    _next_slot[0] = slot + MIN_INTERVAL
    if slot > now:
        time.sleep(slot - now)


def get(url, headers, tries=6):
    last = None
    for i in range(tries):
        _throttle()
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=40) as fh:
                return json.load(fh)
        except urllib.error.HTTPError as exc:
            last = "HTTP %d %s" % (exc.code, exc.read().decode(errors="replace")[:160])
            if exc.code in (400, 401, 403, 404):
                raise RuntimeError("%s -> %s" % (url[:100], last))
            if exc.code == 429:
                time.sleep(5.0 * (i + 1))
        except Exception as exc:  # noqa: BLE001 - transport-shaped, retry
            last = repr(exc)
        time.sleep(1.5 * (i + 1))
    raise RuntimeError("%s -> %s after %d tries" % (url[:100], last, tries))


# ----------------------------------------------------------------------------- expiry plan
def third_friday(year, month):
    d = dt.date(year, month, 15)
    return d + dt.timedelta(days=(4 - d.weekday()) % 7)


def expiry_plan(today):
    """(window_gte, window_lte, [monthly candidates beyond the window])."""
    lte = today + dt.timedelta(days=DTE_MAX)
    monthlies, y, m = [], today.year, today.month
    while len(monthlies) < EXTRA_MONTHLIES:
        f = third_friday(y, m)
        if f > lte:
            monthlies.append(f)
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return today, lte, monthlies


def parse_occ(sym, underlying):
    """OCC: ROOT + yymmdd + C/P + strike*1000 (8 digits). Root length varies."""
    core = sym[-15:]
    root = sym[:-15]
    exp = dt.date(2000 + int(core[0:2]), int(core[2:4]), int(core[4:6]))
    cp = core[6]
    strike = int(core[7:]) / 1000.0
    if not root.startswith(underlying):
        raise ValueError("unexpected root %r for %s" % (root, underlying))
    return root, exp, cp, strike


def fetch_pages(underlying, params, headers):
    out, token, pages = {}, None, 0
    while True:
        q = dict(params)
        q["limit"] = PAGE_LIMIT
        if token:
            q["page_token"] = token
        url = "%s/v1beta1/options/snapshots/%s?%s" % (DATA, underlying, urllib.parse.urlencode(q))
        body = get(url, headers)
        pages += 1
        out.update(body.get("snapshots") or {})
        token = body.get("next_page_token")
        if not token:
            break
    return out, pages


def collect_underlying(underlying, today, headers):
    gte, lte, monthlies = expiry_plan(today)
    snaps, pages = fetch_pages(underlying, {"expiration_date_gte": gte.isoformat(),
                                            "expiration_date_lte": lte.isoformat()}, headers)
    monthly_used = []
    for f in monthlies:
        got = {}
        for cand in (f, f - dt.timedelta(days=1)):     # Thursday fallback on a Friday holiday
            got, p = fetch_pages(underlying, {"expiration_date": cand.isoformat()}, headers)
            pages += p
            if got:
                monthly_used.append(cand.isoformat())
                break
        snaps.update(got)
    return snaps, {"pages": pages, "window": [gte.isoformat(), lte.isoformat()],
                   "monthlies_requested": [f.isoformat() for f in monthlies],
                   "monthlies_found": monthly_used}


def rows_from(underlying, snaps, today, spot, captured_utc):
    rows, fresh, two_sided = [], 0, 0
    day = today.isoformat()
    for sym, s in snaps.items():
        try:
            root, exp, cp, strike = parse_occ(sym, underlying)
        except (ValueError, IndexError):
            continue
        q = s.get("latestQuote") or {}
        t = s.get("latestTrade") or {}
        g = s.get("greeks") or {}
        b = s.get("dailyBar") or {}
        qt = q.get("t") or ""
        # quote timestamps are UTC; the ET date of a 15:45 ET quote is today's UTC date too
        is_two_sided = (q.get("bp") or 0) > 0 and (q.get("ap") or 0) > 0
        if is_two_sided:
            two_sided += 1
            if qt.startswith(day):
                fresh += 1
        rows.append({
            "underlying": underlying, "symbol": sym, "root": root,
            "expiration": exp.isoformat(), "dte": (exp - today).days, "type": cp, "strike": strike,
            "bid": q.get("bp"), "bid_size": q.get("bs"), "ask": q.get("ap"), "ask_size": q.get("as"),
            "quote_ts": qt, "quote_cond": "".join(q.get("c") or []) if isinstance(q.get("c"), list) else q.get("c"),
            "last": t.get("p"), "last_size": t.get("s"), "last_ts": t.get("t"),
            "iv": s.get("impliedVolatility"), "delta": g.get("delta"), "gamma": g.get("gamma"),
            "theta": g.get("theta"), "vega": g.get("vega"), "rho": g.get("rho"),
            "day_open": b.get("o"), "day_high": b.get("h"), "day_low": b.get("l"),
            "day_close": b.get("c"), "day_volume": b.get("v"),
            "underlying_price": (spot or {}).get("price"), "underlying_ts": (spot or {}).get("ts"),
            "captured_utc": captured_utc,
        })
    n = len(rows)
    stats = {"contracts": n, "two_sided": two_sided, "fresh_two_sided": fresh,
             "fresh_frac": round(fresh / n, 4) if n else None,
             "expiries": len({r["expiration"] for r in rows}),
             "with_iv": sum(1 for r in rows if r["iv"] not in (None, "")),
             "with_greeks": sum(1 for r in rows if r["delta"] not in (None, ""))}
    return rows, stats


def fetch_spots(headers):
    url = "%s/v2/stocks/snapshots?%s" % (DATA, urllib.parse.urlencode({"symbols": ",".join(UNIVERSE)}))
    body = get(url, headers)
    out = {}
    for sym, s in body.items():
        tr = s.get("latestTrade") or {}
        q = s.get("latestQuote") or {}
        price = tr.get("p")
        if price is None and q.get("bp") and q.get("ap"):
            price = (q["bp"] + q["ap"]) / 2.0
        out[sym] = {"price": price, "ts": tr.get("t") or q.get("t")}
    return out


def record(ledger_path, date, status, reason=None, fresh_fail=None):
    ledger = load_json(ledger_path, {"days": {}})
    day = ledger["days"].get(date, {"attempts": 0})
    day["attempts"] = day.get("attempts", 0) + 1
    day["status"] = status
    if fresh_fail is not None:
        day["fresh_fail"] = list(fresh_fail)   # v2: per-underlying freshness flags (not a day-kill)
    if reason:
        day["last_failure_reason"] = reason
    elif "last_failure_reason" in day and status == "clean":
        day["recovered_after_failure"] = day.pop("last_failure_reason")
    ledger["days"][date] = day
    days = ledger["days"]
    trading = {k: v for k, v in days.items() if v["status"] != "market_closed"}
    ledger["summary"] = {
        "days_attempted": len(trading),
        "days_clean": sum(1 for d in trading.values() if d["status"] == "clean"),
        "days_failed": sum(1 for d in trading.values() if d["status"] != "clean"),
        "days_market_closed": len(days) - len(trading),
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


def seconds_until_capture(now_et):
    target = now_et.replace(hour=CAPTURE_ET[0], minute=CAPTURE_ET[1], second=0, microsecond=0)
    return (target - now_et).total_seconds(), target


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--now", action="store_true", help="skip the wait for 15:45 ET")
    ap.add_argument("--allow-closed", action="store_true",
                    help="preflight only: fetch even when the market is closed")
    args = ap.parse_args()
    for sub in ("snapshots", "partial"):
        os.makedirs(os.path.join(BASE, sub), exist_ok=True)
    ledger_path = os.path.join(BASE, "ledger.json")
    manifest_path = os.path.join(BASE, "manifest.json")

    if args.status:
        print(json.dumps(load_json(ledger_path, {}), indent=1, sort_keys=True))
        return 0

    now_et = dt.datetime.now(ET)
    today = now_et.date()
    if args.plan:
        gte, lte, monthlies = expiry_plan(today)
        wait, target = seconds_until_capture(now_et)
        print(json.dumps({"today_et": today.isoformat(), "window": [gte.isoformat(), lte.isoformat()],
                          "monthlies": [m.isoformat() for m in monthlies],
                          "capture_target_et": target.isoformat(), "wait_s": round(wait),
                          "universe": UNIVERSE}, indent=1))
        return 0

    headers = creds()
    date = today.isoformat()
    out_path = os.path.join(BASE, "snapshots", "snapshot_%s.csv.gz" % date)
    manifest = load_json(manifest_path, {})
    if not args.preflight and date in manifest and os.path.exists(out_path):
        log("snapshot for %s already clean; nothing to do" % date)
        return 0

    if not (args.now or args.preflight):
        wait, target = seconds_until_capture(now_et)
        if wait > MAX_WAIT_S:
            log("capture target %s is %.0f s away (> %d); refusing to wait that long"
                % (target.isoformat(), wait, MAX_WAIT_S))
            record(ledger_path, date, "failed", "launched too early: %.0f s before capture" % wait)
            return 1
        if wait > 0:
            log("waiting %.0f s until %s" % (wait, target.isoformat()))
            while dt.datetime.now(ET) < target:
                time.sleep(min(30, max(1, (target - dt.datetime.now(ET)).total_seconds())))

    try:
        clock = get(CLOCK, headers)
    except RuntimeError as exc:
        clock = {"error": str(exc)}
    is_open = bool(clock.get("is_open"))
    if not is_open and not (args.preflight and args.allow_closed):
        if args.preflight:
            print("market closed (%s); use --allow-closed for an off-hours format check" % clock)
            return 1
        summary = record(ledger_path, date, "market_closed", None)
        log("market closed at capture (%s); ledger %s" % (clock, summary))
        return 0

    capture_start = dt.datetime.now(dt.timezone.utc)
    captured_utc = capture_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    universe = ["SPY", "AMD"] if args.preflight else UNIVERSE
    t0 = time.monotonic()
    try:
        spots = fetch_spots(headers)
    except RuntimeError as exc:
        log("stock snapshots failed: %s" % exc)
        spots = {}

    all_rows, per_und, reasons = [], {}, []
    fresh_fail = []   # v2: per-underlying freshness flags, recorded, never a day-kill
    for und in universe:
        try:
            snaps, meta = collect_underlying(und, today, headers)
        except RuntimeError as exc:
            reasons.append("%s: %s" % (und, exc))
            per_und[und] = {"error": str(exc)}
            continue
        rows, stats = rows_from(und, snaps, today, spots.get(und), captured_utc)
        stats.update(meta)
        per_und[und] = stats
        all_rows.extend(rows)
        if stats["contracts"] < MIN_CONTRACTS:
            reasons.append("%s: only %d contracts" % (und, stats["contracts"]))
        # v2 (2026-08-26): freshness is a per-underlying ELIGIBILITY flag, not a day-kill.
        # Day 1 showed HYG structurally < 0.70 (0.626; 0.647 even within 15% moneyness), which
        # would have failed every day by construction. Recorded here + in the ledger; the
        # day-30 gate excludes underlyings with < 95% fresh-ok days from the December design.
        stats["fresh_ok"] = not (stats["fresh_frac"] is not None and stats["fresh_frac"] < MIN_FRESH_FRAC)
        if not stats["fresh_ok"]:
            fresh_fail.append("%s: fresh frac %.3f < %.2f" % (und, stats["fresh_frac"], MIN_FRESH_FRAC))
        log("%s: %d contracts / %d expiries / fresh %.3f / iv %d / %d pages" % (
            und, stats["contracts"], stats["expiries"], stats["fresh_frac"] or 0.0,
            stats["with_iv"], stats["pages"]))
    elapsed = round(time.monotonic() - t0, 1)

    if args.preflight:
        print(json.dumps({"clock": clock, "elapsed_s": elapsed, "rows": len(all_rows),
                          "per_underlying": per_und, "would_fail": reasons, "fresh_fail": fresh_fail,
                          "sample_row": all_rows[0] if all_rows else None}, indent=1, default=str))
        return 0

    if reasons:
        ppath = os.path.join(BASE, "partial", "partial_%s_%s.csv.gz" % (date, capture_start.strftime("%H%M%S")))
        if all_rows:
            write_csv(ppath, all_rows)
        summary = record(ledger_path, date, "failed", "; ".join(reasons))
        log("FAILED %s: %s; %d rows kept in partial/; ledger %s" % (date, "; ".join(reasons), len(all_rows), summary))
        return 1

    sha, nbytes = write_csv(out_path, all_rows)
    manifest[date] = {
        "sha256": sha, "bytes": nbytes, "rows": len(all_rows),
        "captured_utc": captured_utc, "captured_et": capture_start.astimezone(ET).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "market_open": is_open, "elapsed_s": elapsed, "per_underlying": per_und,
        "spots": spots, "universe": universe,
        "source": "Alpaca /v1beta1/options/snapshots/{underlying} (default feed as served), limit=%d + page_token; "
                  "expiries DTE<=%d plus next %d monthlies" % (PAGE_LIMIT, DTE_MAX, EXTRA_MONTHLIES),
    }
    save_json(manifest_path, manifest)
    summary = record(ledger_path, date, "clean", fresh_fail=fresh_fail)
    log("CLEAN %s: %d rows across %d underlyings in %ss; fresh_fail=%s; ledger %s" % (
        date, len(all_rows), len(universe), elapsed, fresh_fail or "none", summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
