#!/usr/bin/env python3
"""T72 -- CALENDAR-GAP READER for the live forward instruments (READ-ONLY companion).

Why this exists
---------------
On 2026-09-08 the host was down ~8 hours and the T30 borrow collector lost the 09-08 day.
Three separate signals stayed green through it (STRATEGIST_2026-09-09_0000.md):

  * the T30 ledger summary read `days_attempted 15 / days_clean 15 = 1.00`, because
    `days_attempted` is `len(ledger["days"])` -- a denominator built only from days the
    collector OBSERVED, which cannot represent its own absence (the T67 lens);
  * the T52 input-recency alarm printed `OK  T30_BORROW  22.03h / 48.0h` for a feed whose
    last actual collection was ~46h earlier;
  * the supervisor's own 3-hourly attendance left no artifact in the hole at all (T73).

This reader answers the one question none of those can express: **which calendar (or trading)
dates between day 0 and today have NO ledger entry at all?** A missing date is neither `clean`
nor `failed` anywhere in the programme's bookkeeping; it is simply absent, and absence is
invisible to every ratio whose denominator is a count of observed units.

Relationship to T67. T67 recomputes T31's and T33's *gate ratio* on a calendar denominator.
T72 is one level below that: it enumerates the missing dates themselves, for every instrument
that keeps a per-date record, and it says plainly which instruments keep no such record and are
therefore UNMEASURABLE.

The three T52 errors this companion corrects (in the companion, NOT in the live alarm --
patching a running monitor's semantics days before a gate is how this programme reset the
BASKET1 clock ten times):

  E1  A bare date key was credited to the END of its day, reporting every `daykeys` instrument
      ~24h younger than it is. Here each date is credited to that instrument's DECLARED CAPTURE
      INSTANT (its crontab line), so `age_since_capture_h` is true elapsed time.
  E2  `allowed = cadence * tolerance = 48h` let a daily feed miss two consecutive collections
      before alarming. Here ONE missed due capture is already a gap.
  E3  T30 was registered `business_days=True`, but its collector is calendar-daily (its ledger
      holds clean weekend entries for 08-29, 08-30, 09-05, 09-06). The weekend grace was a
      suppression, not a grace. Here T30 is CALENDAR.

Guardrails (hard). READ-ONLY. Never writes, patches, backfills or repairs any ledger, state
file, snapshot or manifest; never restarts a process or re-epochs an arm; moves no frozen rule,
threshold, prereg or gate date; reads only date labels and per-date status strings, never a
quote or a price, so it cannot leak a strategy number before a pre-registered reading. t4 is
read-only here. No orders, no spend, paper only.

Usage
-----
    python -m scripts.trading_bot.t72_calendar_gap_reader             # table; exit 1 if any gap
    python -m scripts.trading_bot.t72_calendar_gap_reader --json
    python -m scripts.trading_bot.t72_calendar_gap_reader --asof 2026-09-23
    python -m scripts.trading_bot.t72_calendar_gap_reader --selftest  # hermetic, no filesystem
Exit: 0 = no gaps on any measurable instrument; 1 = at least one missing due date;
      2 = an instrument could not be read at all (path/schema problem).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
LOCAL = ZoneInfo("Europe/Amsterdam")   # the host's crontab timezone
UTC = dt.timezone.utc

# US full closures + early closes. An early close has no 15:45 ET capture, so for capture-clock
# purposes it is NOT a trading day (same convention as t67_calendar_denominator_gate.py).
US_HOLIDAYS = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}
US_EARLY_CLOSE = {"2026-11-27", "2026-12-24", "2027-11-26"}
NON_TRADING = US_HOLIDAYS | US_EARLY_CLOSE


@dataclass
class Inst:
    name: str
    path: str
    reader: str              # "daykeys" | "jsonl_field"
    day0: str                # first date the instrument was supposed to record
    calendar: str            # "calendar" | "us_trading"
    capture_local: str       # HH:MM in Europe/Amsterdam, from the crontab line
    grace_hours: float       # how long after the capture instant a date stays in flight
    pointer: str = ""        # daykeys: the dict key; jsonl_field: the row's date field
    note: str = ""
    unmeasurable: str = ""   # non-empty => keeps no per-date record; report and skip
    tags: list[str] = field(default_factory=list)


REGISTRY: list[Inst] = [
    # crontab: 30 16 * * *   (calendar-daily -- E3: NOT business days)
    Inst("T30_BORROW", "research/data/borrow_forward/ledger.json", "daykeys",
         "2026-08-24", "calendar", "16:30", 4.0, "days",
         "30-clean-day gate ~2026-09-23; absolute clean count, so a gap DELAYS, never fake-passes"),
    # crontab: 15 2 * * *
    Inst("T31_DERIBIT", "research/data/deribit_forward/ledger.json", "daykeys",
         "2026-08-24", "calendar", "02:15", 4.0, "days",
         "collector gate ~2026-09-23; ratio denominator is len(days) -> T67 companion required"),
    # crontab: 45 20 * * 1-5  (waits for 15:45 ET)
    Inst("T33_US_OPTIONS", "research/data/us_options_forward/ledger.json", "daykeys",
         "2026-08-25", "us_trading", "20:45", 4.0, "days",
         "convexity panel; collector gate ~2026-10-06/07 (T68 off-by-one open)"),
    # crontab: 15 23 * * 1-5 -- but state.json records only last_scan, no per-date history
    Inst("T45_ETF_LIQ", "research/data/etf_liquidation_forward/state.json", "daykeys",
         "2026-09-02", "us_trading", "23:15", 4.0, "days",
         "K1 read ~09-23",
         unmeasurable="state.json carries only `last_scan` (one scalar) + `seen_accessions`; "
                      "there is NO per-date scan record, so scan attendance cannot be "
                      "reconstructed for any past date. Consistent with T62_t45_d1."),
    # no crontab line of its own: appended by scripts/agent_graph/durable_tick.sh:172 every 3h,
    # one row per NEW settled session, so its date axis is US trading sessions.
    Inst("BASKET1", "research/trading_bot/BASKET_FORWARD_LOG.jsonl", "jsonl_field",
         "2026-08-20", "us_trading", "00:00", 48.0, "session_date",
         "clock LOCKED (hard rule 2026-08-24): observe only. Free-tier SIP embargo means a "
         "session lands 1-2 days late, hence the 48h grace."),
    # the supervisor's own two proposal ledgers: a tick that runs must leave a row (an
    # abstention is a row), so a date with no row is a tick that did not run or did not log.
    Inst("NEWSDESK1", "research/trading_bot/newsdesk/NEWSDESK_PREREGISTRATION_LOG.jsonl",
         "jsonl_field", "2026-09-02", "calendar", "18:00", 8.0, "proposed_utc",
         "CHUNK C runs at h06/h18; abstentions count as rows"),
    Inst("PREDMARKET1", "research/trading_bot/predmarket/PREDMARKET_PREREGISTRATION_LOG.jsonl",
         "jsonl_field", "2026-09-02", "calendar", "21:00", 8.0, "proposed_utc",
         "CHUNK D runs at h09/h21; abstentions count as rows"),
]


# ------------------------------------------------------------------ calendar

def is_due_date(d: dt.date, calendar: str) -> bool:
    if calendar == "calendar":
        return True
    if calendar == "us_trading":
        return d.weekday() < 5 and d.isoformat() not in NON_TRADING
    raise ValueError(f"unknown calendar {calendar!r}")


def expected_dates(inst: Inst, asof: dt.datetime) -> list[dt.date]:
    """Every date from day0 whose capture instant + grace has already passed (E1/E2)."""
    out: list[dt.date] = []
    d = dt.date.fromisoformat(inst.day0)
    last = asof.astimezone(LOCAL).date()
    while d <= last:
        if is_due_date(d, inst.calendar) and capture_instant(inst, d) + dt.timedelta(
                hours=inst.grace_hours) <= asof:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def capture_instant(inst: Inst, d: dt.date) -> dt.datetime:
    """E1: a date is credited to its DECLARED capture instant, not to the end of its day."""
    hh, mm = (int(x) for x in inst.capture_local.split(":"))
    return dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=LOCAL).astimezone(UTC)


# ------------------------------------------------------------------ readers

def observed_dates(inst: Inst, root: Path) -> tuple[set[dt.date], dict[str, str], str | None]:
    """-> (dates present, per-date status label, error)."""
    p = root / inst.path
    if not p.exists():
        return set(), {}, f"path missing: {inst.path}"
    try:
        if inst.reader == "daykeys":
            days = json.loads(p.read_text()).get(inst.pointer)
            if not isinstance(days, dict):
                return set(), {}, f"{inst.pointer!r} is not a dict of date keys"
            got, status = set(), {}
            for k, v in days.items():
                try:
                    got.add(dt.date.fromisoformat(str(k)[:10]))
                except ValueError:
                    continue
                status[str(k)[:10]] = (v or {}).get("status", "?") if isinstance(v, dict) else "?"
            return got, status, None
        if inst.reader == "jsonl_field":
            got, status = set(), {}
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                raw = row.get(inst.pointer)
                if not raw:
                    continue
                try:
                    d = dt.date.fromisoformat(str(raw)[:10])
                except ValueError:
                    continue
                got.add(d)
                status[d.isoformat()] = str(row.get("kind") or row.get("status") or "row")
            return got, status, None
    except Exception as exc:                                   # noqa: BLE001 - report, never raise
        return set(), {}, f"{type(exc).__name__}: {exc}"
    return set(), {}, f"unknown reader {inst.reader!r}"


# ------------------------------------------------------------------ evaluation

def evaluate(inst: Inst, asof: dt.datetime, root: Path) -> dict:
    out = {"name": inst.name, "path": inst.path, "day0": inst.day0,
           "calendar": inst.calendar, "capture_local": inst.capture_local,
           "note": inst.note, "status": None, "error": None,
           "n_expected": 0, "n_present": 0, "missing": [], "extra": [],
           "newest_present": None, "age_since_capture_h": None,
           "one_capture_overdue": None}
    if inst.unmeasurable:
        out["status"] = "UNMEASURABLE"
        out["error"] = inst.unmeasurable
        return out
    got, statuses, err = observed_dates(inst, root)
    if err:
        out["status"], out["error"] = "UNREADABLE", err
        return out
    exp = expected_dates(inst, asof)
    missing = sorted(d for d in exp if d not in got)
    # Dates the ledger holds that the declared calendar does not expect. Not a gap, but it means
    # the declared calendar is wrong -- exactly the E3 mistake, caught mechanically this time.
    # A collector that explicitly ledgers a closure (T33 writes `market_closed`) is being
    # honest, not mislabelled -- those are excluded from the mismatch flag.
    extra = sorted(d for d in got if d >= dt.date.fromisoformat(inst.day0)
                   and not is_due_date(d, inst.calendar)
                   and statuses.get(d.isoformat()) not in ("market_closed", "closed", "holiday"))
    out["n_expected"], out["n_present"] = len(exp), len([d for d in exp if d in got])
    out["missing"] = [d.isoformat() for d in missing]
    out["extra"] = [d.isoformat() for d in extra]
    if got:
        newest = max(got)
        out["newest_present"] = newest.isoformat()
        age = (asof - capture_instant(inst, newest)).total_seconds() / 3600.0
        out["age_since_capture_h"] = round(age, 2)
        # E2: one missed due capture is already a gap.
        nxt = [d for d in exp if d > newest]
        out["one_capture_overdue"] = bool(nxt)
    out["status"] = "GAP" if missing else "COMPLETE"
    return out


def render(rows: list[dict], asof: dt.datetime) -> str:
    L = [f"CALENDAR-GAP READER (T72)  asof {asof.isoformat()}  ({len(rows)} instruments)",
         "-" * 104,
         f"{'STATUS':<14}{'INSTRUMENT':<16}{'CAL':<11}{'DAY0':<12}{'PRESENT/DUE':>12}"
         f"{'GAPS':>6}{'AGE(h)':>9}  NEWEST",
         "-" * 104]
    for r in rows:
        age = "-" if r["age_since_capture_h"] is None else f"{r['age_since_capture_h']:.2f}"
        L.append(f"{r['status']:<14}{r['name']:<16}{r['calendar']:<11}{r['day0']:<12}"
                 f"{str(r['n_present'])+'/'+str(r['n_expected']):>12}{len(r['missing']):>6}"
                 f"{age:>9}  {r['newest_present'] or '-'}")
    L.append("-" * 104)
    L.append("AGE(h) = true elapsed hours since the DECLARED CAPTURE INSTANT of the newest "
             "recorded date (T52 error E1 corrected here).")
    gaps = [r for r in rows if r["status"] == "GAP"]
    if gaps:
        L.append("")
        L.append(f"LOST DAYS -- {len(gaps)} instrument(s) with at least one due date carrying "
                 f"NO ledger entry at all:")
        for r in gaps:
            L.append(f"  - {r['name']}: {len(r['missing'])} missing of {r['n_expected']} due "
                     f"-> {', '.join(r['missing'])}")
    for r in rows:
        if r["status"] in ("UNMEASURABLE", "UNREADABLE"):
            L.append("")
            L.append(f"{r['status']} -- {r['name']}: {r['error']}")
        if r["extra"]:
            L.append("")
            L.append(f"DECLARED-CALENDAR MISMATCH -- {r['name']} holds {len(r['extra'])} entries "
                     f"on dates its declared '{r['calendar']}' calendar does not expect "
                     f"({', '.join(r['extra'][:8])}{'...' if len(r['extra']) > 8 else ''}). "
                     f"The calendar label is wrong, not the ledger.")
    if not gaps:
        L.append("")
        L.append("No missing due dates on any measurable instrument.")
    return "\n".join(L)


# ------------------------------------------------------------------ selftest

def selftest() -> int:
    import tempfile
    ok = True

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and bool(cond)
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  ({detail})" if detail else ""))

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "d").mkdir()
        # A calendar-daily daykeys ledger with 09-03 missing entirely.
        (root / "d" / "led.json").write_text(json.dumps({"days": {
            "2026-09-01": {"status": "clean"}, "2026-09-02": {"status": "clean"},
            "2026-09-04": {"status": "clean"}}}))
        inst = Inst("FAKE", "d/led.json", "daykeys", "2026-09-01", "calendar", "16:30", 4.0, "days")
        asof = dt.datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
        r = evaluate(inst, asof, root)
        check("1 a wholly absent date is reported as a GAP",
              r["status"] == "GAP" and r["missing"] == ["2026-09-03"], str(r["missing"]))
        check("2 present/due counts exclude the gap", (r["n_present"], r["n_expected"]) == (3, 4),
              f"{r['n_present']}/{r['n_expected']}")
        # E1: newest 09-04, capture 16:30 local = 14:30Z; asof 09-05 12:00Z -> 21.5h,
        # NOT the ~12h an end-of-day credit would give.
        check("3 E1 age is measured from the capture instant, not end of day",
              abs(r["age_since_capture_h"] - 21.5) < 0.01, str(r["age_since_capture_h"]))
        # E2: 09-05's capture (14:30Z) + 4h grace is not yet due at 12:00Z, so not overdue yet.
        check("4 E2 an in-flight date is not counted due", r["one_capture_overdue"] is False,
              str(r["one_capture_overdue"]))
        r2 = evaluate(inst, dt.datetime(2026, 9, 6, 12, 0, tzinfo=UTC), root)
        check("5 E2 one missed capture already alarms",
              r2["status"] == "GAP" and r2["one_capture_overdue"] is True
              and "2026-09-05" in r2["missing"], str(r2["missing"]))
        # E3: weekend entries under a us_trading label must surface as a calendar mismatch.
        inst3 = Inst("FAKE_T", "d/led.json", "daykeys", "2026-09-01", "us_trading", "16:30", 4.0,
                     "days")
        r3 = evaluate(inst3, dt.datetime(2026, 9, 7, 12, 0, tzinfo=UTC), root)
        check("6 E3 a wrong calendar label is caught (weekend/holiday entries flagged)",
              r3["extra"] == [] and r3["status"] in ("GAP", "COMPLETE"), str(r3["extra"]))
        # ... and with an actual weekend entry present:
        (root / "d" / "led2.json").write_text(json.dumps({"days": {
            "2026-09-04": {"status": "clean"}, "2026-09-05": {"status": "clean"}}}))
        inst4 = Inst("FAKE_W", "d/led2.json", "daykeys", "2026-09-04", "us_trading", "16:30", 4.0,
                     "days")
        r4 = evaluate(inst4, dt.datetime(2026, 9, 7, 12, 0, tzinfo=UTC), root)
        check("7 E3 weekend entry under a us_trading label is reported as a mismatch",
              r4["extra"] == ["2026-09-05"], str(r4["extra"]))
        # jsonl reader
        (root / "d" / "log.jsonl").write_text(
            '{"session_date": "2026-09-01", "kind": "x"}\n'
            'not json\n'
            '{"session_date": "2026-09-02"}\n')
        inst5 = Inst("FAKE_J", "d/log.jsonl", "jsonl_field", "2026-09-01", "calendar", "00:00",
                     4.0, "session_date")
        r5 = evaluate(inst5, dt.datetime(2026, 9, 2, 12, 0, tzinfo=UTC), root)
        check("8 jsonl reader survives a malformed line and reads both dates",
              r5["status"] == "COMPLETE" and r5["n_present"] == 2, json.dumps(r5["missing"]))
        # unmeasurable + unreadable
        r6 = evaluate(Inst("FAKE_U", "d/led.json", "daykeys", "2026-09-01", "calendar", "16:30",
                           4.0, "days", unmeasurable="no per-date record"), asof, root)
        check("9 an instrument with no per-date record is UNMEASURABLE, not COMPLETE",
              r6["status"] == "UNMEASURABLE")
        r7 = evaluate(Inst("FAKE_X", "d/nope.json", "daykeys", "2026-09-01", "calendar", "16:30",
                           4.0, "days"), asof, root)
        check("10 a missing path is UNREADABLE, never silently complete",
              r7["status"] == "UNREADABLE")
        # read-only: nothing was created beside the fixtures we wrote
        check("11 reader created no files", sorted(x.name for x in (root / "d").iterdir())
              == ["led.json", "led2.json", "log.jsonl"])

    print(f"\nT72 SELFTEST {'ALL_PASSED' if ok else 'FAILED'}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="T72 read-only calendar-gap reader")
    ap.add_argument("--asof", default=None, help="ISO datetime (default: now UTC)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--instrument", default=None)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    asof = dt.datetime.now(UTC) if not a.asof else dt.datetime.fromisoformat(a.asof).replace(
        tzinfo=UTC) if len(a.asof) > 10 else dt.datetime.fromisoformat(a.asof + "T23:59:59+00:00")
    regs = [i for i in REGISTRY if not a.instrument or i.name == a.instrument]
    rows = [evaluate(i, asof, REPO) for i in regs]
    print(json.dumps({"asof": asof.isoformat(), "instruments": rows}, indent=2) if a.json
          else render(rows, asof))
    if any(r["status"] == "UNREADABLE" for r in rows):
        return 2
    return 1 if any(r["status"] == "GAP" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
