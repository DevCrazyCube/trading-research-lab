#!/usr/bin/env python3
"""T45 — ETF liquidation terminal-convergence $0 FORWARD paper logger.

Prereg (BINDING, pinned before any number was read):
  research/trading_bot/INVENT_2026-09-02_0300_desk.md  sha256 6821745b...
Amendment A1 (pinned 2026-09-02 15:00 CEST, before any event existed in the ledger):
  no free keyless bid/ask source exists on this host (Yahoo v7/v10 are auth-walled,
  Stooq is JS-walled), so the prereg's "buy at the ask" is implemented as
      entry = close(announcement+1) * (1 + MODELED_HALF_SPREAD)
  with MODELED_HALF_SPREAD = 0.005 (50 bp, conservative for small wind-down ETFs).
  Every event carries spread_modeled=true. This constant may never be retuned
  after the first event enters the ledger.

Design (from the prereg):
  entry  : announcement day +1, at the (modeled) ask; full half-spread toll, causal
  exit   : final cash distribution per share (no exit toll); no intermediate marking
  PASS   : N >= 30 completed events, pooled mean net > 0 AND cluster-bootstrap
           (cluster = issuer x announcement-month) CI-lo > 0
  K1     : < 4 events with complete free data in the first 21 collecting days
           -> BLOCKED_ON_DATA
  K2     : CI-lo <= 0 at N >= 30, or pooled mean < -1% at N >= 10  -> DEAD
  K3     : one event <= -15% -> FLAG; two such -> DEAD
  Capacity honesty, carried on every report: median liquidated ETF ~ $5.7M AUM ->
  small-dollar arm (~$1-5k/event) even on a PASS.

Sources (free, keyless, one-shot pulls only -- no crawls):
  EDGAR full-text search (efts.sec.gov)  497/497K liquidation supplements
  Yahoo v8 chart API                      daily closes for tracked tickers

Pipeline (candidate -> event is a judgment step done by an agent tick, not code):
  scan          pull recent 497/497K liquidation hits, append NEW ones to
                candidates.jsonl (dedupe by accession)
  confirm       promote a candidate to a tracked event (ticker, dates from the
                actual filing, read by a human/agent)
  reject        mark a candidate as not-an-ETF-liquidation (kept, never deleted)
  prices        pull daily closes for tracked events; freeze the entry as soon as
                the announcement+1 close exists
  record-cash   append the final cash per share -> event complete
  status/report ledger summary + prereg decider state
  selftest      hermetic check of entry math, dedupe, kill logic, hash chain
  --cron        prices then scan (the daily crontab entrypoint)

Append-only integrity: every mutation is appended to ledger_chain.txt as
  sha256(prev_hash_hex + canonical_json(record))
`verify-chain` recomputes the whole chain.

Research/paper programme infrastructure. No orders, no spend, no keys.
Never touches the t4 path.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request

BASE = os.environ.get("T45_BASE") or os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "..", "research", "data", "etf_liquidation_forward"))

MODELED_HALF_SPREAD = 0.005      # A1: pinned pre-data; never retune
PASS_N = 30
K1_DAYS = 21
K1_MIN_EVENTS = 4
K2_EARLY_N = 10
K2_EARLY_MEAN = -0.01
K3_EVENT_RET = -0.15
K3_DEAD_COUNT = 2
BOOT_ITERS = 4000
BOOT_SEED = 45

UA = "meme-research-t45-forward-logger (contact: officialjoy04@gmail.com)"
EDGAR_QUERIES = ['"liquidation and dissolution"', '"approved the liquidation"',
                 '"plan of liquidation"']
EDGAR_FORMS = "497,497K"
SCAN_LOOKBACK_DAYS = 10


def p(name):
    return os.path.join(BASE, name)


def log(msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S %Z"), msg)
    print(line, flush=True)
    os.makedirs(BASE, exist_ok=True)
    with open(p("collect.log"), "a") as fh:
        fh.write(line + "\n")


def load_json(path, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def chain_append(record):
    """Append a mutation record to the tamper-evident hash chain."""
    os.makedirs(BASE, exist_ok=True)
    prev = "0" * 64
    try:
        with open(p("ledger_chain.txt")) as fh:
            for line in fh:
                if line.strip():
                    prev = json.loads(line)["h"]
    except OSError:
        pass
    body = canonical(record)
    h = hashlib.sha256((prev + body).encode()).hexdigest()
    with open(p("ledger_chain.txt"), "a") as fh:
        fh.write(json.dumps({"h": h, "r": record}, sort_keys=True) + "\n")
    return h


def chain_verify():
    prev = "0" * 64
    n = 0
    try:
        with open(p("ledger_chain.txt")) as fh:
            for i, line in enumerate(fh):
                if not line.strip():
                    continue
                row = json.loads(line)
                want = hashlib.sha256((prev + canonical(row["r"])).encode()).hexdigest()
                if row["h"] != want:
                    return False, "chain break at line %d" % (i + 1)
                prev = row["h"]
                n += 1
    except OSError:
        return True, "empty chain"
    return True, "%d links ok" % n


def http_json(url, timeout=25, attempts=3):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception:  # noqa: BLE001 - EDGAR FTS 500s on bursts; back off
            if i == attempts - 1:
                raise
            time.sleep(2.0 + 3.0 * i)


# ----------------------------------------------------------------- scan
def cmd_scan():
    state = load_json(p("state.json"), {})
    if "collection_start" not in state:
        state["collection_start"] = dt.date.today().isoformat()
        chain_append({"t": "collection_start", "date": state["collection_start"]})
        log("collection clock started %s (K1 window %d days)"
            % (state["collection_start"], K1_DAYS))
    seen = set(state.get("seen_accessions", []))
    start = (dt.date.today() - dt.timedelta(days=SCAN_LOOKBACK_DAYS)).isoformat()
    end = dt.date.today().isoformat()
    new = 0
    for q in EDGAR_QUERIES:
        url = ("https://efts.sec.gov/LATEST/search-index?q=%s&forms=%s"
               "&dateRange=custom&startdt=%s&enddt=%s"
               % (urllib.parse.quote_plus(q), EDGAR_FORMS, start, end))
        try:
            data = http_json(url)
        except Exception as e:  # noqa: BLE001 - log-and-continue collector
            log("scan ERROR query=%s: %s" % (q, e))
            continue
        hits = data.get("hits", {}).get("hits", [])
        log("scan query=%s hits=%d" % (q, len(hits)))
        for hit in hits:
            src = hit.get("_source", {})
            adsh = src.get("adsh")
            if not adsh or adsh in seen:
                continue
            seen.add(adsh)
            cand = {
                "adsh": adsh,
                "form": src.get("form"),
                "file_date": src.get("file_date"),
                "display_names": src.get("display_names", []),
                "ciks": src.get("ciks", []),
                "doc_id": hit.get("_id"),
                "query": q,
                "first_seen": dt.datetime.now(dt.timezone.utc).isoformat(),
                "review": "pending",
            }
            with open(p("candidates.jsonl"), "a") as fh:
                fh.write(json.dumps(cand, sort_keys=True) + "\n")
            chain_append({"t": "candidate", "adsh": adsh,
                          "file_date": cand["file_date"]})
            new += 1
        time.sleep(1.5)
    state["seen_accessions"] = sorted(seen)
    state["last_scan"] = dt.datetime.now(dt.timezone.utc).isoformat()
    save_json(p("state.json"), state)
    log("scan done: %d new candidate(s), %d total seen" % (new, len(seen)))


def set_candidate_review(adsh, verdict, note=""):
    rows = []
    found = False
    try:
        with open(p("candidates.jsonl")) as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("adsh") == adsh:
                    row["review"] = verdict
                    if note:
                        row["review_note"] = note
                    found = True
                rows.append(row)
    except OSError:
        pass
    if found:
        with open(p("candidates.jsonl"), "w") as fh:
            for row in rows:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
    return found


# ----------------------------------------------------------------- events
def cmd_confirm(args):
    events = load_json(p("events.json"), {})
    eid = args.ticker.upper()
    if eid in events:
        log("REFUSED: event %s already exists (append-only; no edits)" % eid)
        return 1
    ev = {
        "ticker": eid,
        "issuer": args.issuer,
        "adsh": args.adsh,
        "announcement_date": args.announced,
        "last_trading_day": args.last_day,
        "confirmed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "spread_modeled": True,
        "modeled_half_spread": MODELED_HALF_SPREAD,
        "entry_date": None,
        "entry_close": None,
        "entry_price": None,
        "entry_frozen_sha": None,
        "final_cash_per_share": None,
        "pay_date": None,
        "cash_source": None,
        "status": "awaiting_entry",
        "notes": args.notes or "",
    }
    events[eid] = ev
    save_json(p("events.json"), events)
    chain_append({"t": "confirm", "ticker": eid, "adsh": args.adsh,
                  "announcement_date": args.announced,
                  "last_trading_day": args.last_day})
    if args.adsh:
        set_candidate_review(args.adsh, "confirmed", "-> event %s" % eid)
    log("event %s confirmed (announced %s, last day %s)"
        % (eid, args.announced, args.last_day))
    return 0


def cmd_reject(args):
    if set_candidate_review(args.adsh, "rejected", args.reason or ""):
        chain_append({"t": "reject", "adsh": args.adsh,
                      "reason": args.reason or ""})
        log("candidate %s rejected: %s" % (args.adsh, args.reason or ""))
        return 0
    log("candidate %s not found" % args.adsh)
    return 1


def yahoo_daily_closes(ticker, days=15):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/%s"
           "?range=%dd&interval=1d" % (urllib.parse.quote(ticker), days))
    data = http_json(url)
    res = data["chart"]["result"][0]
    stamps = res.get("timestamp") or []
    closes = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    out = {}
    for ts, c in zip(stamps, closes):
        if c is None:
            continue
        d = dt.datetime.utcfromtimestamp(ts).date().isoformat()
        out[d] = round(float(c), 6)
    return out


def freeze_entry_if_ready(ev, closes):
    """Entry = first close ON/AFTER announcement+1 (<=3 trading days late), modeled ask."""
    if ev["entry_price"] is not None:
        return False
    ann = dt.date.fromisoformat(ev["announcement_date"])
    target = ann + dt.timedelta(days=1)
    limit = ann + dt.timedelta(days=6)   # allow weekends/holidays, cap the drift
    for d in sorted(closes):
        day = dt.date.fromisoformat(d)
        if target <= day <= limit:
            ev["entry_date"] = d
            ev["entry_close"] = closes[d]
            ev["entry_price"] = round(closes[d] * (1.0 + MODELED_HALF_SPREAD), 6)
            ev["entry_frozen_sha"] = hashlib.sha256(canonical(
                {k: ev[k] for k in ("ticker", "entry_date", "entry_close",
                                    "entry_price", "modeled_half_spread")}
            ).encode()).hexdigest()
            ev["status"] = "holding"
            return True
    return False


def cmd_prices():
    events = load_json(p("events.json"), {})
    today = dt.date.today()
    pulled = 0
    for eid, ev in sorted(events.items()):
        if ev["status"] in ("complete", "error"):
            continue
        last_day = dt.date.fromisoformat(ev["last_trading_day"])
        if today > last_day + dt.timedelta(days=10) and ev["status"] == "holding":
            ev["status"] = "awaiting_cash"
        if today > last_day + dt.timedelta(days=1) and ev["entry_price"] is None:
            pass  # still try: closes remain fetchable for a while post-delisting
        try:
            closes = yahoo_daily_closes(eid)
        except Exception as e:  # noqa: BLE001
            log("prices ERROR %s: %s" % (eid, e))
            continue
        pulled += 1
        with open(p("prices.jsonl"), "a") as fh:
            fh.write(json.dumps({"ticker": eid, "pulled": today.isoformat(),
                                 "closes": closes}, sort_keys=True) + "\n")
        if freeze_entry_if_ready(ev, closes):
            chain_append({"t": "entry_frozen", "ticker": eid,
                          "entry_date": ev["entry_date"],
                          "entry_price": ev["entry_price"],
                          "sha": ev["entry_frozen_sha"]})
            log("ENTRY FROZEN %s @ %s (close %s +%d bp modeled ask)"
                % (eid, ev["entry_price"], ev["entry_close"],
                   MODELED_HALF_SPREAD * 10000))
        time.sleep(0.4)
    save_json(p("events.json"), events)
    log("prices done: %d ticker(s) pulled" % pulled)


def cmd_record_cash(args):
    events = load_json(p("events.json"), {})
    eid = args.ticker.upper()
    ev = events.get(eid)
    if not ev:
        log("no such event %s" % eid)
        return 1
    if ev.get("final_cash_per_share") is not None:
        log("REFUSED: %s already has final cash (append-only)" % eid)
        return 1
    ev["final_cash_per_share"] = float(args.cash)
    ev["pay_date"] = args.paydate
    ev["cash_source"] = args.source
    ev["status"] = "complete" if ev["entry_price"] is not None else "error"
    if ev["status"] == "error":
        ev["notes"] += " | cash recorded but entry was never frozen (no announcement+1 close)"
    save_json(p("events.json"), events)
    chain_append({"t": "final_cash", "ticker": eid, "cash": float(args.cash),
                  "pay_date": args.paydate, "source": args.source})
    log("final cash %s: %s (pay %s) -> %s" % (eid, args.cash, args.paydate,
                                              ev["status"]))
    return 0


# ----------------------------------------------------------------- decider
def net_return(ev):
    return ev["final_cash_per_share"] / ev["entry_price"] - 1.0


def cluster_bootstrap_ci_lo(events, iters=BOOT_ITERS, seed=BOOT_SEED):
    clusters = {}
    for ev in events:
        key = (ev["issuer"], ev["announcement_date"][:7])
        clusters.setdefault(key, []).append(net_return(ev))
    keys = sorted(clusters)
    rng = random.Random(seed)
    means = []
    for _ in range(iters):
        sample = []
        for _ in keys:
            sample.extend(clusters[keys[rng.randrange(len(keys))]])
        means.append(sum(sample) / len(sample))
    means.sort()
    return means[int(0.025 * len(means))]


def decider(events_dict, today=None):
    today = today or dt.date.today()
    state = load_json(p("state.json"), {})
    start = state.get("collection_start")
    complete = [e for e in events_dict.values() if e["status"] == "complete"]
    with_data = [e for e in events_dict.values() if e["entry_price"] is not None]
    rets = [net_return(e) for e in complete]
    n = len(rets)
    mean = sum(rets) / n if n else None
    tails = [r for r in rets if r <= K3_EVENT_RET]
    verdict, why = "COLLECTING", ""
    if len(tails) >= K3_DEAD_COUNT:
        verdict, why = "DEAD", "K3: %d events <= %.0f%%" % (len(tails),
                                                           K3_EVENT_RET * 100)
    elif n >= K2_EARLY_N and mean is not None and mean < K2_EARLY_MEAN:
        verdict, why = "DEAD", ("K2-early: mean %.2f%% < -1%% at N=%d"
                                % (mean * 100, n))
    elif n >= PASS_N:
        ci_lo = cluster_bootstrap_ci_lo(complete)
        if ci_lo > 0 and mean > 0:
            verdict, why = "PASS", "CI-lo %.3f%% > 0 at N=%d" % (ci_lo * 100, n)
        else:
            verdict, why = "DEAD", "K2: CI-lo %.3f%% <= 0 at N=%d" % (ci_lo * 100, n)
    elif start:
        days = (today - dt.date.fromisoformat(start)).days
        if days >= K1_DAYS and len(with_data) < K1_MIN_EVENTS:
            verdict, why = "BLOCKED_ON_DATA", ("K1: %d event(s) with data after "
                                               "%d days" % (len(with_data), days))
    return {"verdict": verdict, "why": why, "n_complete": n,
            "n_with_data": len(with_data), "mean": mean,
            "n_tail_flags": len(tails), "collection_start": start}


def cmd_status(report=False):
    state = load_json(p("state.json"), {})
    events = load_json(p("events.json"), {})
    pending = 0
    try:
        with open(p("candidates.jsonl")) as fh:
            pending = sum(1 for line in fh
                          if line.strip()
                          and json.loads(line).get("review") == "pending")
    except OSError:
        pass
    ok, msg = chain_verify()
    d = decider(events)
    print("T45 ETF-LIQUIDATION FORWARD — prereg 6821745b… (BINDING) + A1 modeled ask 50bp")
    print("collection_start=%s  last_scan=%s  chain=%s (%s)"
          % (d["collection_start"], state.get("last_scan"),
             "OK" if ok else "BROKEN", msg))
    print("candidates pending review: %d   (confirm/reject each via CLI — judgment step)"
          % pending)
    print("events: %d tracked, %d with frozen entry, %d complete"
          % (len(events), d["n_with_data"], d["n_complete"]))
    for eid, ev in sorted(events.items()):
        ret = ("%+.2f%%" % (net_return(ev) * 100)
               if ev["status"] == "complete" else "-")
        print("  %-6s %-14s ann=%s entry=%s cash=%s ret=%s"
              % (eid, ev["status"], ev["announcement_date"],
                 ev["entry_price"], ev["final_cash_per_share"], ret))
    print("DECIDER: %s %s" % (d["verdict"], ("(%s)" % d["why"]) if d["why"] else ""))
    if report and d["n_complete"]:
        print("pooled mean net: %.3f%%  tail flags (<=-15%%): %d"
              % (d["mean"] * 100, d["n_tail_flags"]))
    print("CAPACITY HONESTY: median liquidated ETF ~$5.7M AUM -> small-dollar arm "
          "(~$1-5k/event) even on a PASS. Paper only; no orders; no spend.")


# ----------------------------------------------------------------- selftest
def cmd_selftest():
    import tempfile
    global BASE
    old = BASE
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        BASE = tmp
        # entry freeze math + causality
        ev = {"ticker": "XX", "announcement_date": "2026-09-01",
              "entry_price": None, "entry_close": None, "entry_date": None,
              "entry_frozen_sha": None, "status": "awaiting_entry",
              "modeled_half_spread": MODELED_HALF_SPREAD}
        closes = {"2026-09-01": 10.0, "2026-09-02": 9.5, "2026-09-03": 9.4}
        freeze_entry_if_ready(ev, closes)
        if ev["entry_date"] != "2026-09-02":
            fails.append("entry picked %s, want announcement+1" % ev["entry_date"])
        if abs(ev["entry_price"] - 9.5 * 1.005) > 1e-9:
            fails.append("entry price %s missing modeled half-spread" % ev["entry_price"])
        # announcement-day close must never be used (lookahead guard)
        ev2 = dict(ev, entry_price=None, entry_date=None,
                   announcement_date="2026-09-03")
        freeze_entry_if_ready(ev2, {"2026-09-03": 5.0})
        if ev2["entry_price"] is not None:
            fails.append("used announcement-day close (lookahead)")
        # decider: K3 two-tail death
        evs = {}
        for i, r in enumerate([0.02, -0.16, 0.01, -0.20]):
            evs["T%d" % i] = {"issuer": "I%d" % i, "announcement_date": "2026-09-01",
                              "status": "complete", "entry_price": 1.0,
                              "final_cash_per_share": 1.0 + r}
        save_json(p("state.json"), {"collection_start": "2026-09-02"})
        d = decider(evs, today=dt.date(2026, 9, 10))
        if d["verdict"] != "DEAD" or not d["why"].startswith("K3"):
            fails.append("K3 not firing: %s" % d)
        # decider: K2 early mean death at N>=10
        evs = {"T%d" % i: {"issuer": "I%d" % (i % 3),
                           "announcement_date": "2026-09-01",
                           "status": "complete", "entry_price": 1.0,
                           "final_cash_per_share": 0.98}
               for i in range(10)}
        d = decider(evs, today=dt.date(2026, 9, 10))
        if d["verdict"] != "DEAD" or not d["why"].startswith("K2-early"):
            fails.append("K2-early not firing: %s" % d)
        # decider: K1 blocked
        d = decider({}, today=dt.date(2026, 10, 1))
        if d["verdict"] != "BLOCKED_ON_DATA":
            fails.append("K1 not firing: %s" % d)
        # decider: PASS path with 30 clustered winners
        evs = {"T%d" % i: {"issuer": "I%d" % (i % 6),
                           "announcement_date": "2026-0%d-01" % (1 + i % 4),
                           "status": "complete", "entry_price": 1.0,
                           "final_cash_per_share": 1.02 + 0.001 * (i % 5)}
               for i in range(30)}
        d = decider(evs, today=dt.date(2026, 12, 1))
        if d["verdict"] != "PASS":
            fails.append("PASS path broken: %s" % d)
        # hash chain: append 3, verify, tamper, verify breaks
        for i in range(3):
            chain_append({"t": "test", "i": i})
        ok, _ = chain_verify()
        if not ok:
            fails.append("clean chain failed verify")
        with open(p("ledger_chain.txt")) as fh:
            lines = fh.readlines()
        row = json.loads(lines[1])
        row["r"]["i"] = 99
        lines[1] = json.dumps(row, sort_keys=True) + "\n"
        with open(p("ledger_chain.txt"), "w") as fh:
            fh.writelines(lines)
        ok, _ = chain_verify()
        if ok:
            fails.append("tampered chain passed verify")
    BASE = old
    if fails:
        print("SELFTEST FAILED:")
        for f in fails:
            print("  - " + f)
        return 1
    print("SELFTEST ALL_PASSED (entry math, lookahead guard, K1/K2/K3, PASS path, chain)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("scan")
    sub.add_parser("prices")
    c = sub.add_parser("confirm")
    c.add_argument("--ticker", required=True)
    c.add_argument("--issuer", required=True)
    c.add_argument("--announced", required=True, help="YYYY-MM-DD announcement date")
    c.add_argument("--last-day", dest="last_day", required=True,
                   help="YYYY-MM-DD last trading day from the filing")
    c.add_argument("--adsh", default="")
    c.add_argument("--notes", default="")
    r = sub.add_parser("reject")
    r.add_argument("--adsh", required=True)
    r.add_argument("--reason", default="")
    rc = sub.add_parser("record-cash")
    rc.add_argument("--ticker", required=True)
    rc.add_argument("--cash", required=True, type=float)
    rc.add_argument("--paydate", required=True)
    rc.add_argument("--source", required=True)
    sub.add_parser("status")
    sub.add_parser("report")
    sub.add_parser("selftest")
    sub.add_parser("verify-chain")
    ap.add_argument("--cron", action="store_true",
                    help="daily entrypoint: prices then scan")
    args = ap.parse_args()
    if args.cron:
        cmd_prices()
        cmd_scan()
        return 0
    if args.cmd == "scan":
        cmd_scan()
    elif args.cmd == "prices":
        cmd_prices()
    elif args.cmd == "confirm":
        return cmd_confirm(args)
    elif args.cmd == "reject":
        return cmd_reject(args)
    elif args.cmd == "record-cash":
        return cmd_record_cash(args)
    elif args.cmd == "status":
        cmd_status()
    elif args.cmd == "report":
        cmd_status(report=True)
    elif args.cmd == "selftest":
        return cmd_selftest()
    elif args.cmd == "verify-chain":
        ok, msg = chain_verify()
        print(("OK " if ok else "BROKEN ") + msg)
        return 0 if ok else 1
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
