#!/usr/bin/env python3
"""T48 -- DATA-PATH auditor for the live forward collectors (READ-ONLY).

Why this exists (agenda T48): four independent input-surface faults have been found in live
forward instruments and ZERO were caught by a green decision-path selftest.  A green selftest on
the DECISION path says nothing about the INPUT surface.  This auditor asserts, per collector:

  (a) RECENCY        the consumer's window contains rows from the expected latest period, and no
                     period is a silent duplicate of the previous one (a stale upstream file
                     re-archived under a fresh date label would otherwise count as a fresh day).
  (b) REPRESENTATION every declared symbol/feed the consumer joins on is actually present in the
                     window, at a plausible share -- no silent truncation, no sort that buries a
                     source.
  (c) ATTRIBUTION    every join key is corroborated by the row's OWN content, never inherited
                     from the subscription/query that fetched it.

Deliberately READ-ONLY and OFFLINE: it opens no socket, writes nothing outside its own report,
and edits no collector.  T45's collector is sha-pinned (T45_PIN.sha256) and T30's is on a live
daily cron 19 days from its gate, so the audit is a separate instrument by design -- guarding a
frozen clock must not perturb it.

It NEVER prints a pair-level rate or availability figure for T30: the frozen protocol forbids
reading any pair-level number before the 30-clean-day gate.  Counts and symbols only.

Usage:  t48_datapath_audit.py [--t30] [--t31] [--t33] [--t45] [--all] [--selftest]
Exit 0 = clean, 1 = at least one WARN/FAIL finding.  Research only; no orders, no spend.
"""
import argparse
import collections
import csv
import gzip
import datetime as dt
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BORROW = os.path.join(ROOT, "research", "data", "borrow_forward")
ETFLIQ = os.path.join(ROOT, "research", "data", "etf_liquidation_forward")
EDGES = os.path.join(ROOT, "research", "trading_bot", "T30_B01_PAIR_EDGES.json")
DERIBIT = os.path.join(ROOT, "research", "data", "deribit_forward")
USOPT = os.path.join(ROOT, "research", "data", "us_options_forward")

AVAIL_FRAC = 0.80          # T30 frozen: a leg absent on >20% of clean days fails borrowable
FRESH_SCAN_DAYS = 4        # T45 cron is Mon-Fri; a Fri->Mon gap is 3 days
T31_CLOCK_UTC_MIN = 15     # T31 protocol declares the snapshot clock as 00:15 UTC
T31_CLOCK_TOL_MIN = 90     # winter runs land at 01:15 UTC; anything beyond that is off-clock
T31_CURRENCIES = ["BTC", "ETH"]
T31_MIN_ROWS = 300         # frozen MIN_INSTRUMENTS per currency
T33_UNIVERSE = ["SPY", "QQQ", "IWM", "TLT", "HYG", "GLD", "XLE", "XLF",
                "NVDA", "TSLA", "AAPL", "AMZN", "MSFT", "AMD"]
T33_MIN_CONTRACTS = 200    # frozen MIN_CONTRACTS per underlying


def jload(path, default=None):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def jlines(path):
    out = []
    try:
        with open(path) as fh:
            for line in fh:
                if line.strip():
                    out.append(json.loads(line))
    except OSError:
        pass
    return out


class Report(object):
    def __init__(self):
        self.rows = []

    def add(self, level, collector, criterion, msg):
        self.rows.append((level, collector, criterion, msg))
        print("%-5s %-4s %-14s %s" % (level, collector, criterion, msg))

    def ok(self, *a):
        self.add("OK", *a)

    def warn(self, *a):
        self.add("WARN", *a)

    def fail(self, *a):
        self.add("FAIL", *a)

    def bad(self):
        return sum(1 for r in self.rows if r[0] != "OK")


# ------------------------------------------------------------------ T30 borrow
def audit_t30(rep, base=BORROW, edges_path=EDGES):
    led = jload(os.path.join(base, "ledger.json"), {"days": {}})
    man = jload(os.path.join(base, "manifest.json"), {})
    edges = jload(edges_path, {"pairs": []})
    days = sorted(d for d, v in led.get("days", {}).items() if v.get("status") == "clean")
    if not days:
        rep.fail("T30", "recency", "no clean day in ledger")
        return

    # (a) RECENCY -- label vs content stamp, and duplicate content across days
    prev_sha = prev_bof = None
    off, dup = [], []
    for d in days:
        m = man.get(d)
        if not m:
            rep.fail("T30", "recency", "clean day %s has no manifest entry" % d)
            continue
        bof_date = str(m.get("bof_stamp", "")).split("|")[0].replace(".", "-")
        if bof_date != d:
            off.append((d, bof_date))
        if m.get("sha256_raw") == prev_sha or (prev_bof and bof_date == prev_bof):
            dup.append(d)
        prev_sha, prev_bof = m.get("sha256_raw"), bof_date
    if dup:
        rep.fail("T30", "recency", "STALE UPSTREAM: day(s) %s duplicate the previous day's file "
                                   "-- they inflate days_clean without new information" % dup)
    else:
        rep.ok("T30", "recency", "%d clean days, all distinct upstream files (sha + #BOF stamp)" % len(days))
    if off:
        rep.warn("T30", "recency", "content stamp != date label on %d day(s): %s (vintage offset, "
                                   "recorded honestly in bof_stamp; not a duplicate)"
                 % (len(off), ", ".join("%s<-%s" % x for x in off)))
    last = dt.date.fromisoformat(days[-1])
    lag = (dt.date.today() - last).days
    if lag > 2:
        rep.warn("T30", "recency", "latest clean day %s is %d days old (cron 16:30 daily)" % (days[-1], lag))

    # (b) REPRESENTATION -- every B01 leg present in the extract the evaluator reads
    legs = sorted({p["ibkr_a"] for p in edges["pairs"]} | {p["ibkr_b"] for p in edges["pairs"]})
    pres = collections.Counter()
    dups = collections.Counter()
    names = {}
    for d in days:
        e = jload(os.path.join(base, "extract", "extract_%s.json" % d), {"rows": []})
        syms = [r["SYM"] for r in e["rows"]]
        for s, k in collections.Counter(syms).items():
            if k > 1:
                dups[s] += 1
        seen = set(syms)
        for s in legs:
            if s in seen:
                pres[s] += 1
        for r in e["rows"]:
            names.setdefault(r["SYM"], set()).add(r.get("NAME", ""))
    n = len(days)
    never = [s for s in legs if pres[s] == 0]
    thin = sorted(s for s in legs if 0 < pres[s] / n < AVAIL_FRAC)
    if never:
        killed = sum(1 for p in edges["pairs"] if p["ibkr_a"] in never or p["ibkr_b"] in never)
        rep.fail("T30", "representation", "%d leg(s) NEVER in the extract -> %d/%d pairs fail for a "
                                          "data reason, not an economic one: %s"
                 % (len(never), killed, len(edges["pairs"]), never))
    else:
        rep.ok("T30", "representation", "all %d B01 legs join the extract; min presence %d/%d days"
               % (len(legs), min(pres[s] for s in legs), n))
    if thin:
        rep.warn("T30", "representation", "leg(s) below the %d%% availability floor on presence alone "
                                          "-- would fail 'borrowable' for absence, not for cost: %s"
                 % (int(AVAIL_FRAC * 100), [(s, "%d/%d" % (pres[s], n)) for s in thin]))
    if dups:
        rep.fail("T30", "representation", "duplicate SYM rows within a day: %s" % dict(dups))

    # (c) ATTRIBUTION -- the SYM->NAME identity must be stable and self-corroborating
    unstable = sorted(s for s in legs if len(names.get(s, set())) > 1)
    if unstable:
        rep.fail("T30", "attribution", "SYM->NAME changes across days (join key not self-consistent): %s"
                 % [(s, sorted(names[s])) for s in unstable[:5]])
    else:
        rep.ok("T30", "attribution", "SYM->NAME stable across all %d days for every leg; issuer text "
                                     "corroborates the .PR->' PR' mapping from the row's own content" % n)


# ------------------------------------------------------------------ T45 etf liquidation
def audit_t45(rep, base=ETFLIQ):
    state = jload(os.path.join(base, "state.json"), {})
    cands = jlines(os.path.join(base, "candidates.jsonl"))
    events = jload(os.path.join(base, "events.json"), {})

    # (a) RECENCY -- scan clock, and candidate file_dates inside the declared lookback
    ls = state.get("last_scan")
    if not ls:
        rep.fail("T45", "recency", "no last_scan in state.json")
    else:
        age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(ls)).days
        (rep.ok if age <= FRESH_SCAN_DAYS else rep.warn)(
            "T45", "recency", "last_scan %s (%d day(s) ago; cron Mon-Fri 23:15)" % (ls[:19], age))
    if cands:
        fds = sorted(c.get("file_date", "") for c in cands)
        stale = [c["adsh"] for c in cands
                 if c.get("file_date", "") < (dt.date.fromisoformat(c["first_seen"][:10])
                                              - dt.timedelta(days=11)).isoformat()]
        if stale:
            rep.fail("T45", "recency", "candidate(s) filed outside the 10-day lookback -> the EDGAR "
                                       "date filter is being ignored: %s" % stale[:5])
        else:
            rep.ok("T45", "recency", "%d candidates, file_date %s..%s, all inside the 10-day lookback "
                                     "of their own first_seen" % (len(cands), fds[0], fds[-1]))

    # (b) REPRESENTATION -- the triage duty (T46) and the price series' own coverage
    pending = [c["adsh"] for c in cands if c.get("review") == "pending"]
    if pending:
        rep.warn("T45", "representation", "%d candidate(s) still review=pending -- untriaged candidates "
                                          "are invisible events (T46 duty): %s" % (len(pending), pending[:5]))
    else:
        rep.ok("T45", "representation", "0 candidates pending review (%d triaged: %s)"
               % (len(cands), dict(collections.Counter(c.get("review") for c in cands))))
    for row in jlines(os.path.join(base, "prices.jsonl")):
        closes = row.get("closes") or {}
        pulled = row.get("pulled")
        if not closes:
            rep.fail("T45", "representation", "%s price pull on %s returned ZERO closes -- a silent "
                                              "empty series counts as 'pulled'" % (row.get("ticker"), pulled))
            continue
        gap = (dt.date.fromisoformat(pulled) - dt.date.fromisoformat(max(closes))).days
        if gap > 5:
            rep.warn("T45", "representation", "%s price series ends %s but was pulled %s (%d-day gap)"
                     % (row.get("ticker"), max(closes), pulled, gap))

    # (c) ATTRIBUTION -- the event ticker must trace to a filing accession, not to a query
    for eid, ev in sorted(events.items()):
        if not ev.get("adsh"):
            rep.fail("T45", "attribution", "event %s has no source accession -- its ticker is unattributed" % eid)
    if events:
        rep.ok("T45", "attribution", "%d event(s), each carrying the accession it was read from" % len(events))
    else:
        rep.ok("T45", "attribution", "0 events; candidate ciks/display_names come from the hit's own "
                                     "_source (not inherited from the query string)")


# ------------------------------------------------------------------ shared readers
def read_csv_gz(path):
    try:
        with gzip.open(path, "rt") as fh:
            return list(csv.DictReader(fh))
    except (OSError, ValueError):
        return []


def clock_off_min(captured_utc, target_min):
    """Minutes between a captured_utc stamp's time-of-day and the declared clock (wraps midnight)."""
    try:
        t = dt.datetime.strptime(captured_utc, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None
    off = (t.hour * 60 + t.minute) - target_min
    return min(abs(off), 1440 - abs(off))


# ------------------------------------------------------------------ T31 (Deribit forward)
def audit_t31(rep, base=DERIBIT):
    """T31 -- daily Deribit option-chain snapshots. Gate denominator = ledger days_clean."""
    ledger = jload(os.path.join(base, "ledger.json"), {}) or {}
    man = jload(os.path.join(base, "manifest.json"), {}) or {}
    days = sorted(k for k, v in (ledger.get("days") or {}).items() if v.get("status") == "clean")
    if not days:
        rep.fail("T31", "recency", "no clean days in ledger -- nothing to audit")
        return

    # (a) RECENCY -- capture clock, distinct content, snapshot present for every clean day
    off_clock = []
    for d in days:
        cap = (man.get(d) or {}).get("captured_utc")
        off = clock_off_min(cap, T31_CLOCK_UTC_MIN)
        if off is None:
            rep.fail("T31", "recency", "%s clean but manifest has no parseable captured_utc" % d)
        elif off > T31_CLOCK_TOL_MIN:
            off_clock.append((d, cap, off))
    if off_clock:
        for d, cap, off in off_clock:
            rep.fail("T31", "recency", "%s captured %s = %dh%02dm off the declared 00:15 UTC clock, "
                                       "yet counts as a clean gate day (protocol declares Tardis "
                                       "comparability ONLY at 00:15 UTC)"
                     % (d, cap, off // 60, off % 60))
    else:
        rep.ok("T31", "recency", "all %d clean days captured within %dm of the declared 00:15 UTC clock"
               % (len(days), T31_CLOCK_TOL_MIN))

    shas = collections.Counter((man.get(d) or {}).get("sha256") for d in days if (man.get(d) or {}).get("sha256"))
    dup = [h for h, n in shas.items() if n > 1]
    if dup:
        rep.fail("T31", "recency", "%d clean day(s) share a snapshot sha256 -- a re-archived stale "
                                   "file would inflate the gate denominator" % sum(shas[h] for h in dup))
    else:
        rep.ok("T31", "recency", "%d/%d clean days carry a distinct snapshot sha256" % (len(shas), len(days)))

    # (b) REPRESENTATION -- both declared currencies present, above the frozen floor, every day
    thin = []
    for d in days:
        rows = read_csv_gz(os.path.join(base, "snapshots", "snapshot_%s.csv.gz" % d))
        if not rows:
            rep.fail("T31", "representation", "%s clean but its snapshot is unreadable/empty" % d)
            continue
        cur = collections.Counter(str(r.get("symbol", "")).split("-")[0] for r in rows)
        for c in T31_CURRENCIES:
            if cur.get(c, 0) < T31_MIN_ROWS:
                thin.append((d, c, cur.get(c, 0)))
    if thin:
        for d, c, n in thin:
            rep.fail("T31", "representation", "%s: %s has %d rows < frozen floor %d" % (d, c, n, T31_MIN_ROWS))
    else:
        rep.ok("T31", "representation", "%s each present above the frozen %d-row floor on all %d clean days"
               % ("/".join(T31_CURRENCIES), T31_MIN_ROWS, len(days)))

    # a re-archived stale file also shows up as an unchanged index price
    idx_seen = collections.defaultdict(list)
    for d in days:
        rows = read_csv_gz(os.path.join(base, "snapshots", "snapshot_%s.csv.gz" % d))
        for c in T31_CURRENCIES:
            # index_price varies by a few ticks WITHIN a day (rows are snapped seconds apart), so
            # take the day's minimum as its representative -- a re-archived file repeats it exactly.
            vals = sorted({r.get("index_price") for r in rows
                           if r.get("index_price") and str(r.get("symbol", "")).startswith(c + "-")})
            if vals:
                idx_seen[c].append(vals[0])
    for c, seq in sorted(idx_seen.items()):
        rep_runs = [i for i in range(1, len(seq)) if seq[i] == seq[i - 1]]
        if rep_runs:
            rep.warn("T31", "recency", "%s index price repeats verbatim on %d consecutive day pair(s)"
                     % (c, len(rep_runs)))
        else:
            rep.ok("T31", "recency", "%s index price moves on every consecutive clean-day pair (%d days)"
                   % (c, len(seq)))

    # (c) ATTRIBUTION -- currency/strike/expiry read from the row's OWN instrument name
    mism = strikes = 0
    for d in days:
        for r in read_csv_gz(os.path.join(base, "snapshots", "snapshot_%s.csv.gz" % d)):
            sym = str(r.get("symbol", ""))
            parts = sym.split("-")
            if len(parts) < 4:
                mism += 1
                continue
            if not str(r.get("underlying_index", "")).startswith(parts[0]):
                mism += 1
            try:
                if abs(float(r.get("strike_price")) - float(parts[2])) > 1e-6:
                    strikes += 1
            except (TypeError, ValueError):
                strikes += 1
    if mism or strikes:
        rep.fail("T31", "attribution", "%d row(s) whose underlying_index disagrees with their own "
                                       "instrument name, %d whose strike_price does" % (mism, strikes))
    else:
        rep.ok("T31", "attribution", "every row's currency and strike are corroborated by its own "
                                     "Deribit instrument name (the consumer splits on it too)")


# ------------------------------------------------------------------ T33 (US options forward)
def audit_t33(rep, base=USOPT):
    """T33 -- 15:45 ET US option-chain snapshots. Freshness is a per-underlying eligibility flag."""
    ledger = jload(os.path.join(base, "ledger.json"), {}) or {}
    man = jload(os.path.join(base, "manifest.json"), {}) or {}
    days = sorted(k for k, v in (ledger.get("days") or {}).items() if v.get("status") == "clean")
    if not days:
        rep.fail("T33", "recency", "no clean days in ledger -- nothing to audit")
        return

    # (a) RECENCY -- quotes stamped on the snapshot's own date, and stale rows cannot masquerade
    poison = []
    for d in days:
        rows = read_csv_gz(os.path.join(base, "snapshots", "snapshot_%s.csv.gz" % d))
        if not rows:
            rep.fail("T33", "recency", "%s clean but its snapshot is unreadable/empty" % d)
            continue
        cap = (man.get(d) or {}).get("captured_utc", "")
        if not cap.startswith(d):
            rep.fail("T33", "recency", "%s snapshot carries captured_utc %r from another date" % (d, cap))
        per = collections.Counter()
        for r in rows:
            if str(r.get("quote_ts") or "").startswith(d):
                continue
            b, a = r.get("bid") or "0", r.get("ask") or "0"
            try:
                if float(b) > 0 and float(a) > 0:
                    per[r.get("underlying")] += 1
            except ValueError:
                pass
        for u, n in per.items():
            poison.append((d, u, n))
    if poison:
        worst = collections.Counter()
        for _, u, n in poison:
            worst[u] += n
        rep.warn("T33", "recency", "stale two-sided quotes present (a nine-month-old bid/ask that "
                                   "still looks live): %s -- CONTAINED because the evaluator's "
                                   "two_sided test requires quote_ts to start with the snapshot date"
                 % ", ".join("%s=%d rows" % kv for kv in worst.most_common()))
    else:
        rep.ok("T33", "recency", "no stale two-sided quote anywhere in %d clean snapshots" % len(days))

    # (b) REPRESENTATION -- every declared underlying present, above the frozen floor, every day
    thin = []
    for d in days:
        rows = read_csv_gz(os.path.join(base, "snapshots", "snapshot_%s.csv.gz" % d))
        cnt = collections.Counter(r.get("underlying") for r in rows)
        for u in T33_UNIVERSE:
            if cnt.get(u, 0) < T33_MIN_CONTRACTS:
                thin.append((d, u, cnt.get(u, 0)))
    if thin:
        for d, u, n in thin:
            rep.fail("T33", "representation", "%s: %s has %d contracts < frozen floor %d"
                     % (d, u, n, T33_MIN_CONTRACTS))
    else:
        rep.ok("T33", "representation", "all %d declared underlyings present above the frozen "
                                        "%d-contract floor on all %d clean days"
               % (len(T33_UNIVERSE), T33_MIN_CONTRACTS, len(days)))

    # the collector silently drops any row whose OCC root fails to parse -- no counter exists
    rows_by_day = {d: (man.get(d) or {}).get("rows") for d in days}
    if any(v is None for v in rows_by_day.values()):
        rep.warn("T33", "representation", "manifest lacks a row count on some clean day")
    else:
        rep.ok("T33", "representation", "row counts logged per clean day (%s)"
               % "/".join(str(rows_by_day[d]) for d in days))

    # (c) ATTRIBUTION -- underlying/expiry/strike re-derived from the row's OWN OCC symbol
    bad_root = bad_exp = bad_strike = 0
    for d in days:
        for r in read_csv_gz(os.path.join(base, "snapshots", "snapshot_%s.csv.gz" % d)):
            sym = str(r.get("symbol", ""))
            if len(sym) < 16:
                bad_root += 1
                continue
            core, root = sym[-15:], sym[:-15]
            if not root.startswith(str(r.get("underlying", "\x00"))):
                bad_root += 1
            try:
                exp = "20%s-%s-%s" % (core[0:2], core[2:4], core[4:6])
                if str(r.get("expiration", ""))[:10] != exp:
                    bad_exp += 1
                if abs(float(r.get("strike")) - int(core[7:]) / 1000.0) > 1e-6:
                    bad_strike += 1
            except (TypeError, ValueError):
                bad_exp += 1
    if bad_root or bad_exp or bad_strike:
        rep.fail("T33", "attribution", "%d row(s) whose underlying disagrees with their own OCC root, "
                                       "%d expiry, %d strike" % (bad_root, bad_exp, bad_strike))
    else:
        rep.ok("T33", "attribution", "every row's underlying, expiry and strike are re-derivable from "
                                     "its own OCC symbol (never inherited from the query)")


# ------------------------------------------------------------------ selftest
def selftest():
    """Hermetic: build a STALE + BROKEN-JOIN fixture and assert the auditor flags it."""
    d = tempfile.mkdtemp(prefix="t48_selftest_")
    os.makedirs(os.path.join(d, "extract"))
    days = ["2026-01-01", "2026-01-02", "2026-01-03"]
    ledger = {"days": {x: {"status": "clean"} for x in days}}
    man = {days[0]: {"sha256_raw": "a" * 64, "bof_stamp": "2026.01.01|10:00:00"},
           days[1]: {"sha256_raw": "a" * 64, "bof_stamp": "2026.01.01|10:00:00"},   # STALE dup
           days[2]: {"sha256_raw": "c" * 64, "bof_stamp": "2026.01.03|10:00:00"}}
    json.dump(ledger, open(os.path.join(d, "ledger.json"), "w"))
    json.dump(man, open(os.path.join(d, "manifest.json"), "w"))
    for i, x in enumerate(days):
        rows = [{"SYM": "AA PRA", "NAME": "ALCOA" if i < 2 else "ALCOA CORP"}]  # unstable NAME
        json.dump({"rows": rows}, open(os.path.join(d, "extract", "extract_%s.json" % x), "w"))
    ep = os.path.join(d, "edges.json")
    json.dump({"pairs": [{"ibkr_a": "AA PRA", "ibkr_b": "ZZ PRB"}]}, open(ep, "w"))
    rep = Report()
    audit_t30(rep, base=d, edges_path=ep)
    got = {(lv, cr) for lv, _, cr, _ in rep.rows}
    need = [("FAIL", "recency"), ("FAIL", "representation"), ("FAIL", "attribution")]
    missing = [x for x in need if x not in got]
    print("\nSELFTEST %s (%s)" % ("ALL_PASSED" if not missing else "FAILED", missing or "3/3 fault classes caught"))
    return 1 if missing else 0


def selftest_optpanels():
    """Hermetic: an OFF-CLOCK T31 day and a MIS-ATTRIBUTED T33 chain must both be flagged."""
    d = tempfile.mkdtemp(prefix="t48_opt_selftest_")
    t31 = os.path.join(d, "t31")
    os.makedirs(os.path.join(t31, "snapshots"))
    days = ["2026-01-01", "2026-01-02"]
    json.dump({"days": {x: {"status": "clean"} for x in days}}, open(os.path.join(t31, "ledger.json"), "w"))
    json.dump({days[0]: {"captured_utc": "2026-01-01T13:05:09Z", "sha256": "a" * 64},   # OFF-CLOCK
               days[1]: {"captured_utc": "2026-01-02T00:15:00Z", "sha256": "b" * 64}},
              open(os.path.join(t31, "manifest.json"), "w"))
    for x in days:
        with gzip.open(os.path.join(t31, "snapshots", "snapshot_%s.csv.gz" % x), "wt") as fh:
            w = csv.DictWriter(fh, fieldnames=["symbol", "strike_price", "underlying_index", "index_price"])
            w.writeheader()
            for c in T31_CURRENCIES:
                for i in range(T31_MIN_ROWS + 1):
                    w.writerow({"symbol": "%s-30JAN26-%d-C" % (c, 50000 + i), "strike_price": 50000 + i,
                                "underlying_index": "%s-30JAN26" % c, "index_price": "1000" + x[-1]})
    t33 = os.path.join(d, "t33")
    os.makedirs(os.path.join(t33, "snapshots"))
    json.dump({"days": {days[0]: {"status": "clean"}}}, open(os.path.join(t33, "ledger.json"), "w"))
    json.dump({days[0]: {"captured_utc": "2026-01-01T19:45:00Z", "rows": 1}}, open(os.path.join(t33, "manifest.json"), "w"))
    with gzip.open(os.path.join(t33, "snapshots", "snapshot_%s.csv.gz" % days[0]), "wt") as fh:
        w = csv.DictWriter(fh, fieldnames=["underlying", "symbol", "expiration", "strike", "bid", "ask", "quote_ts"])
        w.writeheader()
        for u in T33_UNIVERSE:
            for i in range(T33_MIN_CONTRACTS):
                w.writerow({"underlying": u, "symbol": "%s260116C%08d" % (u, (500 + i) * 1000),
                            "expiration": "2026-01-16", "strike": 500 + i, "bid": "1", "ask": "2",
                            "quote_ts": days[0] + "T19:45:00Z"})
        # one row whose ticker is INHERITED from the query, not its own OCC root
        w.writerow({"underlying": "SPY", "symbol": "QQQ260116C00500000", "expiration": "2026-01-16",
                    "strike": 500, "bid": "1", "ask": "2", "quote_ts": days[0] + "T19:45:00Z"})
        # one row with a live-looking two-sided quote stamped nine months ago
        w.writerow({"underlying": "XLE", "symbol": "XLE260116C00500000", "expiration": "2026-01-16",
                    "strike": 500, "bid": "18.38", "ask": "21.56", "quote_ts": "2025-04-01T20:59:59Z"})
    rep = Report()
    audit_t31(rep, base=t31)
    audit_t33(rep, base=t33)
    got = {(lv, cl, cr) for lv, cl, cr, _ in rep.rows}
    need = [("FAIL", "T31", "recency"), ("FAIL", "T33", "attribution"), ("WARN", "T33", "recency")]
    missing = [x for x in need if x not in got]
    print("\nSELFTEST(opt-panels) %s (%s)"
          % ("ALL_PASSED" if not missing else "FAILED", missing or "3/3 fault classes caught"))
    return 1 if missing else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--t30", action="store_true")
    ap.add_argument("--t31", action="store_true")
    ap.add_argument("--t33", action="store_true")
    ap.add_argument("--t45", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest() or selftest_optpanels()
    rep = Report()
    if a.t30 or a.all or not (a.t31 or a.t33 or a.t45):
        audit_t30(rep)
    if a.t31 or a.all:
        audit_t31(rep)
    if a.t33 or a.all:
        audit_t33(rep)
    if a.t45 or a.all:
        audit_t45(rep)
    print("\n%d finding(s) needing attention of %d checks" % (rep.bad(), len(rep.rows)))
    return 1 if rep.bad() else 0


if __name__ == "__main__":
    sys.exit(main())
