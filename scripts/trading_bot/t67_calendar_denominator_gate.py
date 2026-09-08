#!/usr/bin/env python3
"""T67 -- calendar-denominator companion gate reader for T31 (Deribit) and T33 (US options).

READ-ONLY. This script never writes to, patches, or repairs a collector's ledger, snapshots
or manifest. It exists because both collectors compute their gate denominator from days they
OBSERVED (`len(ledger["days"])` / `len(trading)`), which cannot represent its own absence: a
date on which cron never fires gets no ledger entry at all, so it is counted as neither clean
nor failed. The denominator does not grow, the ratio stays pinned at 1.00, and the gate can
return a clean PASS on a collector that has been dead for a week.

The frozen protocols already say the denominator is calendar-derived, and the frozen text is
authoritative over the code:

  T31 (research/trading_bot/T31_DERIBIT_FORWARD.md L63-64):
    "days_clean / days_attempted >= 0.95 (with days_attempted = CALENDAR DAYS SINCE DAY 0, so
     silent cron death counts as failure)"
  T33 (research/trading_bot/T33_US_OPTIONS_FORWARD.md L65-67):
    "days_clean / days_attempted >= 0.95, where EVERY SCHEDULED TRADING DAY counts as attempted
     (a silent cron death is a failed day -- the gate tick reconciles the ledger against the
     exchange calendar)"

So this is not a rule change and not a new gate. It is the reconciliation the frozen text
already mandates, implemented as a blind additive companion beside the running instrument
rather than as a patch to it (patching a live collector's bookkeeping days before its gate is
how this programme reset the BASKET1 clock ten times). Same pattern as T62 / T63.

WHERE THIS READER DISAGREES WITH THE COLLECTOR'S OWN `--status`, THE CALENDAR READING IS THE
VERDICT.

Reads only day labels and per-day status strings plus snapshot filenames. It never opens a
snapshot and never reads a single quote, so it cannot leak a strategy number before the
pre-registered reading dates (T31/T33 design read ~2026-12-23).

Usage:
  python -m scripts.trading_bot.t67_calendar_denominator_gate            # both panels, today
  python -m scripts.trading_bot.t67_calendar_denominator_gate --panel t31
  python -m scripts.trading_bot.t67_calendar_denominator_gate --asof 2026-09-23
  python -m scripts.trading_bot.t67_calendar_denominator_gate --json
Exit code: 0 = every due gate PASSes / not yet due; 1 = a due gate FAILs; 2 = the reader
disagrees with a collector's self-reported denominator (investigate before trusting --status).
"""

import argparse
import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

THRESHOLD = 0.95

# A scheduled day only becomes DUE once its capture instant plus this grace has passed.
# Without it the reader flags the current, still-in-flight day as a silent death -- which is
# the same class of error (a denominator that does not match what can physically be observed)
# that this reader exists to catch.
CAPTURE_GRACE_HOURS = 4

# US equity-market holidays, explicit and auditable rather than a library dependency.
# Only full closures matter (a half day still has a 15:45 ET capture? no -- 1pm close; the
# early-close dates are listed separately and treated as NON-trading for T33 because the
# 15:45 ET capture clock cannot fire on them).
US_HOLIDAYS_2026 = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
}
US_EARLY_CLOSE_2026 = {"2026-11-27", "2026-12-24"}   # 13:00 ET close -> no 15:45 ET capture
US_HOLIDAYS_2027 = {
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}
US_EARLY_CLOSE_2027 = {"2027-11-26"}

NON_TRADING = US_HOLIDAYS_2026 | US_EARLY_CLOSE_2026 | US_HOLIDAYS_2027 | US_EARLY_CLOSE_2027

PANELS = {
    "t31": {
        "name": "T31_DERIBIT",
        "ledger": os.path.join(REPO, "research", "data", "deribit_forward", "ledger.json"),
        "snapdir": os.path.join(REPO, "research", "data", "deribit_forward", "snapshots"),
        "day0": "2026-08-25",   # CONVEXITY_PREREGISTRATION: 08-24 excluded (13:06 UTC, off-clock)
        "cadence": "calendar",
        "n_days": 30,
        "documented_gate": "2026-09-23",
        "frozen_doc": "research/trading_bot/T31_DERIBIT_FORWARD.md",
        "ignore_days_before_day0": True,
        # capture clock: cron 00:15 UTC on the labelled day
        "capture_tz": "UTC",
        "capture_hm": (0, 15),
    },
    "t33": {
        "name": "T33_US_OPTIONS",
        "ledger": os.path.join(REPO, "research", "data", "us_options_forward", "ledger.json"),
        "snapdir": os.path.join(REPO, "research", "data", "us_options_forward", "snapshots"),
        "day0": "2026-08-25",   # first scheduled 15:45 ET capture (ledgered `failed` under v1)
        "cadence": "trading",
        "n_days": 30,
        "documented_gate": "2026-10-07",
        "frozen_doc": "research/trading_bot/T33_US_OPTIONS_FORWARD.md",
        "ignore_days_before_day0": True,
        # capture clock: 15:45 America/New_York on the labelled trading day
        "capture_tz": "America/New_York",
        "capture_hm": (15, 45),
    },
}


def d(s):
    return dt.date(*(int(x) for x in s.split("-")))


def is_trading(day):
    return day.weekday() < 5 and day.isoformat() not in NON_TRADING


def expected_days(day0, cadence, upto):
    """Every day the collector was SCHEDULED to fire, day0..upto inclusive."""
    out, cur = [], day0
    while cur <= upto:
        if cadence == "calendar" or is_trading(cur):
            out.append(cur.isoformat())
        cur += dt.timedelta(days=1)
    return out


def gate_date(day0, cadence, n_days):
    """The date on which the n_days-th scheduled day lands."""
    seen, cur = 0, day0
    while True:
        if cadence == "calendar" or is_trading(cur):
            seen += 1
            if seen >= n_days:
                return cur
        cur += dt.timedelta(days=1)


def last_due_day(cfg, now_utc):
    """The most recent scheduled day whose capture instant + grace has already passed."""
    tz = ZoneInfo(cfg["capture_tz"])
    hh, mm = cfg["capture_hm"]
    cur = now_utc.astimezone(tz).date()
    for _ in range(40):
        if cfg["cadence"] == "calendar" or is_trading(cur):
            deadline = dt.datetime.combine(cur, dt.time(hh, mm), tzinfo=tz) + \
                dt.timedelta(hours=CAPTURE_GRACE_HOURS)
            if deadline <= now_utc:
                return cur
        cur -= dt.timedelta(days=1)
    return cur


def load_json(path, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return default


def evaluate(key, asof, now_utc=None):
    cfg = PANELS[key]
    day0 = d(cfg["day0"])
    gate = gate_date(day0, cfg["cadence"], cfg["n_days"])
    gate_matches_doc = gate.isoformat() == cfg["documented_gate"]

    # Score day0..min(asof, gate, last DUE day). Capping at the last due day keeps the
    # still-in-flight current day out of the denominator; capping at the gate keeps
    # post-gate days from diluting the gate reading.
    due_through = last_due_day(cfg, now_utc or dt.datetime.now(dt.timezone.utc))
    window_end = min(asof, gate, due_through)
    exp = expected_days(day0, cfg["cadence"], window_end)

    ledger = load_json(cfg["ledger"], {"days": {}})
    days = ledger.get("days", {})
    snaps = set()
    if os.path.isdir(cfg["snapdir"]):
        for fn in os.listdir(cfg["snapdir"]):
            if fn.startswith("snapshot_") and len(fn) >= 19:
                snaps.add(fn[9:19])

    clean, failed, missing, conflict, clean_no_artifact = [], [], [], [], []
    for day in exp:
        rec = days.get(day)
        if rec is None:
            missing.append(day)          # THE DEFECT: invisible to the collector's own denominator
            continue
        st = rec.get("status")
        if st == "clean":
            clean.append(day)
            if day not in snaps:
                clean_no_artifact.append(day)
        elif st == "market_closed":
            # our exchange calendar says this day was scheduled; the collector says closed.
            # Frozen text: every scheduled trading day counts as attempted. Not clean.
            conflict.append(day)
            failed.append(day)
        else:
            failed.append(day)

    # Days the collector ledgered that our calendar did NOT expect (e.g. T31 day 0, or a
    # market_closed weekend/holiday row). Reported, never scored.
    unexpected = sorted(k for k in days
                        if k not in set(exp)
                        and (not cfg["ignore_days_before_day0"] or d(k) >= day0)
                        and d(k) <= window_end)

    denom = len(exp)
    ratio = (len(clean) / denom) if denom else None

    self_sum = ledger.get("summary", {}) or {}
    self_att, self_clean = self_sum.get("days_attempted"), self_sum.get("days_clean")
    self_ratio = (self_clean / self_att) if (self_att) else None

    due = window_end >= gate
    if not due:
        verdict = "GATE_NOT_DUE"
    elif ratio is not None and ratio >= THRESHOLD:
        verdict = "PASS"
    else:
        verdict = "FAIL"

    # The whole point of the reader: does the collector's own denominator understate reality?
    denom_gap = (denom - self_att) if isinstance(self_att, int) else None
    disagrees = bool(missing) or bool(conflict) or bool(clean_no_artifact) or (
        denom_gap is not None and denom_gap > 0 and not cfg["ignore_days_before_day0"])

    return {
        "panel": cfg["name"],
        "frozen_doc": cfg["frozen_doc"],
        "cadence": cfg["cadence"],
        "day0": cfg["day0"],
        "gate_date_computed": gate.isoformat(),
        "gate_date_documented": cfg["documented_gate"],
        "gate_date_matches_doc": gate_matches_doc,
        "asof": asof.isoformat(),
        "capture_clock": "%02d:%02d %s + %dh grace" % (
            cfg["capture_hm"][0], cfg["capture_hm"][1], cfg["capture_tz"], CAPTURE_GRACE_HOURS),
        "last_due_day": due_through.isoformat(),
        "window_end": window_end.isoformat(),
        "calendar_days_attempted": denom,
        "days_clean": len(clean),
        "days_failed": len(failed),
        "days_MISSING_from_ledger": len(missing),
        "missing_dates": missing,
        "calendar_conflict_dates": conflict,
        "clean_but_no_snapshot_on_disk": clean_no_artifact,
        "ledgered_but_not_expected": unexpected,
        "calendar_ratio": None if ratio is None else round(ratio, 4),
        "collector_self_days_attempted": self_att,
        "collector_self_days_clean": self_clean,
        "collector_self_ratio": None if self_ratio is None else round(self_ratio, 4),
        "denominator_gap_calendar_minus_self": denom_gap,
        "threshold": THRESHOLD,
        "gate_due": due,
        "verdict": verdict,
        "reader_disagrees_with_collector": disagrees,
    }


def selftest():
    """Prove the reader fires on the exact defect it exists to catch.

    This validates the ARITHMETIC of absence-detection against synthetic ledgers. It says
    nothing about the live data path -- the live reading printed by a normal run is the
    separate, and more important, evidence.
    """
    import tempfile
    ok = True

    def run(name, ledger_days, cadence, asof, expect_missing, expect_ratio, expect_verdict):
        nonlocal ok
        tmp = tempfile.mkdtemp(prefix="t67_selftest_")
        lp = os.path.join(tmp, "ledger.json")
        summary_days = {k: v for k, v in ledger_days.items()}
        trading = {k: v for k, v in summary_days.items() if v["status"] != "market_closed"}
        with open(lp, "w") as fh:
            json.dump({"days": summary_days,
                       "summary": {"days_attempted": len(trading),
                                   "days_clean": sum(1 for v in trading.values()
                                                     if v["status"] == "clean")}}, fh)
        key = "__selftest__"
        PANELS[key] = {"name": name, "ledger": lp, "snapdir": tmp, "day0": "2026-08-25",
                       "cadence": cadence, "n_days": 30, "documented_gate": "2026-09-23",
                       "frozen_doc": "(selftest)", "ignore_days_before_day0": True,
                       "capture_tz": "UTC", "capture_hm": (0, 15)}
        # freeze "now" far past the window so every scored day is due
        r = evaluate(key, d(asof), dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc))
        del PANELS[key]
        good = (r["days_MISSING_from_ledger"] == expect_missing
                and r["calendar_ratio"] == round(expect_ratio, 4)
                and r["verdict"] == expect_verdict)
        ok = ok and good
        print("  [%s] %-38s missing=%s ratio=%s verdict=%s (self-reported %s/%s)"
              % ("ok " if good else "FAIL", name, r["days_MISSING_from_ledger"],
                 r["calendar_ratio"], r["verdict"],
                 r["collector_self_days_clean"], r["collector_self_days_attempted"]))
        return r

    clean30 = {(d("2026-08-25") + dt.timedelta(days=i)).isoformat(): {"status": "clean"}
               for i in range(30)}
    print("T67 SELFTEST -- absence arithmetic")

    # 1. fully clean 30 calendar days -> PASS
    run("all-clean", clean30, "calendar", "2026-09-23", 0, 1.0, "PASS")

    # 2. THE DEFECT: cron silently dies for the last 7 days. The collector's own denominator
    #    shrinks with it and still reports 23/23 = 1.00 -> a fake PASS. The reader must FAIL.
    dead = {k: v for k, v in clean30.items() if k < "2026-09-17"}
    r = run("silent-cron-death-7d", dead, "calendar", "2026-09-23", 7, 23 / 30.0, "FAIL")
    assert r["collector_self_ratio"] == 1.0, "fixture must reproduce the fake 1.00"

    # 3. one explicitly failed day out of 30 -> 29/30 = 0.9667 >= 0.95 -> PASS (not over-strict)
    one_fail = dict(clean30); one_fail["2026-09-01"] = {"status": "failed"}
    run("one-explicit-failure", one_fail, "calendar", "2026-09-23", 0, 29 / 30.0, "PASS")

    # 4. two missing days out of 30 -> 28/30 = 0.9333 < 0.95 -> FAIL
    two_gaps = {k: v for k, v in clean30.items() if k not in ("2026-09-01", "2026-09-02")}
    run("two-silent-gaps", two_gaps, "calendar", "2026-09-23", 2, 28 / 30.0, "FAIL")

    # 5. trading cadence: weekends absent from the ledger must NOT count as missing
    td, cur = {}, d("2026-08-25")
    while len([x for x in td if td[x]]) < 30:
        if is_trading(cur):
            td[cur.isoformat()] = {"status": "clean"}
        cur += dt.timedelta(days=1)
    run("trading-cadence-weekends-ok", td, "trading", cur.isoformat(), 0, 1.0, "PASS")

    print("SELFTEST %s" % ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--panel", choices=sorted(PANELS) + ["all"], default="all")
    ap.add_argument("--asof", default=None, help="UTC date to score as-of (default: today UTC)")
    ap.add_argument("--json", action="store_true", help="machine-readable only")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the absence arithmetic on synthetic ledgers; touches nothing real")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    asof = d(args.asof) if args.asof else dt.datetime.now(dt.timezone.utc).date()
    keys = sorted(PANELS) if args.panel == "all" else [args.panel]
    now_utc = dt.datetime.now(dt.timezone.utc)
    results = [evaluate(k, asof, now_utc) for k in keys]

    if args.json:
        print(json.dumps(results, indent=1))
    else:
        print("T67 CALENDAR-DENOMINATOR COMPANION GATE READER  (read-only)  asof=%s" % asof)
        print("=" * 92)
        for r in results:
            print("\n%s  [%s days, day0 %s, gate %s%s]" % (
                r["panel"], r["cadence"], r["day0"], r["gate_date_computed"],
                "" if r["gate_date_matches_doc"] else "  !! DOES NOT MATCH DOC %s" % r["gate_date_documented"]))
            print("  scored window        : %s .. %s  (last due day %s, capture %s)"
                  % (r["day0"], r["window_end"], r["last_due_day"], r["capture_clock"]))
            print("  calendar denominator : %s scheduled days  ->  clean %s / failed %s / MISSING %s"
                  % (r["calendar_days_attempted"], r["days_clean"], r["days_failed"],
                     r["days_MISSING_from_ledger"]))
            print("  calendar ratio       : %s   (threshold %s)" % (r["calendar_ratio"], r["threshold"]))
            print("  collector --status   : %s / %s = %s" % (
                r["collector_self_days_clean"], r["collector_self_days_attempted"], r["collector_self_ratio"]))
            print("  denominator gap      : %s  (calendar minus collector-observed)"
                  % r["denominator_gap_calendar_minus_self"])
            for label, k in (("MISSING (never ledgered)", "missing_dates"),
                             ("calendar conflict", "calendar_conflict_dates"),
                             ("clean w/o snapshot file", "clean_but_no_snapshot_on_disk"),
                             ("ledgered, not expected", "ledgered_but_not_expected")):
                if r[k]:
                    print("  %-24s: %s" % (label, ", ".join(r[k])))
            print("  VERDICT              : %s%s" % (
                r["verdict"], "   [READER DISAGREES WITH COLLECTOR]" if r["reader_disagrees_with_collector"] else ""))
        print("\n" + "=" * 92)
        print("Where this reader disagrees with the collector's own --status, the CALENDAR reading")
        print("is the verdict. This reader writes nothing; it never opens a snapshot.")

    if any(r["verdict"] == "FAIL" for r in results):
        return 1
    if any(r["reader_disagrees_with_collector"] for r in results):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
