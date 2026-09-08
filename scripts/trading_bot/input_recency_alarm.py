#!/usr/bin/env python3
"""T52 -- INPUT-RECENCY LIVENESS ALARM (read-only).

Why this exists
---------------
The MEME ARENA sat input-dead for 56 hours (T48 tranche 6) and every liveness signal the
programme publishes stayed GREEN through it: `chain_ok` was true because ledger CONTINUITY is
preserved by not appending; the :8795 dashboard was up because it proves a SERVER, not a FEED;
the runtime logs were fresh because the processes were alive and busy-spinning on one cached
error.  Every one of those is a PROXY.  The only signal that cannot lie is the age of the
newest INPUT row, read from the row's OWN timestamp field.

This script reports, for every live forward instrument: newest input row age, the instrument's
DECLARED expected cadence, and OK / STALE judged against that cadence.  It exits non-zero if any
instrument is STALE, so a 3-hourly tick can run it first and name the dead feeds.

Guardrails (hard): READ-ONLY.  It observes.  It never restarts a process, re-activates or
re-epochs an arm, resolves a position, or writes a ledger row.  It touches no frozen rule,
prereg, threshold or scoring path.  t4 is READ-ONLY here.  No orders, no spend, paper only.

Usage
-----
    python -m scripts.trading_bot.input_recency_alarm             # human table, exit 1 if STALE
    python -m scripts.trading_bot.input_recency_alarm --json      # machine-readable
    python -m scripts.trading_bot.input_recency_alarm --selftest  # hermetic, no filesystem deps
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------- timestamp extraction

# Timestamp fields we know about, in priority order, with their units.
TS_FIELDS: list[tuple[str, str]] = [
    ("received_unix_nanos", "nanos"),
    ("decision_unix_nanos", "nanos"),
    ("proposed_utc", "iso"),
    ("run_utc", "iso"),
    ("ts_utc", "iso"),
    ("last_scan", "iso"),
    ("ts", "seconds"),
    ("session_date", "date"),
    ("entry_day", "date"),
]


def _parse_ts(value: Any, unit: str) -> Optional[datetime]:
    try:
        if unit == "nanos":
            return datetime.fromtimestamp(float(value) / 1e9, tz=timezone.utc)
        if unit == "seconds":
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        if unit == "iso":
            s = str(value).replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        if unit == "date":
            # A date-only stamp means "some time that day"; take END of day so we never
            # report an instrument stale for a reason that is purely clock resolution.
            d = datetime.fromisoformat(str(value)[:10]).replace(tzinfo=timezone.utc)
            return d + timedelta(hours=23, minutes=59)
    except Exception:
        return None
    return None


def _ts_from_obj(obj: dict) -> tuple[Optional[datetime], Optional[str]]:
    for name, unit in TS_FIELDS:
        if name in obj:
            dt = _parse_ts(obj[name], unit)
            if dt is not None:
                return dt, name
    return None, None


def _tail_lines(path: Path, nbytes: int = 262144) -> list[str]:
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - nbytes))
        chunk = fh.read()
    return chunk.decode("utf-8", "replace").splitlines()


def read_jsonl_newest(path: Path) -> tuple[Optional[datetime], str]:
    """Newest timestamp among the last lines of a JSONL ledger, from the ROW's own field."""
    best: Optional[datetime] = None
    src = "none"
    for line in reversed(_tail_lines(path)):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        dt, name = _ts_from_obj(obj)
        if dt is not None:
            if best is None or dt > best:
                best, src = dt, f"row.{name}"
            break  # last parseable row is authoritative for append-only ledgers
    return best, src


def read_json_daykeys(path: Path, pointer: str) -> tuple[Optional[datetime], str]:
    """Newest key of a {date: {...}} map, e.g. ledger.json['days']."""
    obj = json.loads(path.read_text())
    for part in pointer.split("."):
        obj = obj[part]
    if isinstance(obj, dict) and obj:
        newest = max(k for k in obj if isinstance(k, str))
        dt = _parse_ts(newest, "date")
        if dt is not None:
            return dt, f"{pointer} key"
    if isinstance(obj, list) and obj:
        dt, name = _ts_from_obj(obj[-1]) if isinstance(obj[-1], dict) else (None, None)
        if dt is not None:
            return dt, f"{pointer}[-1].{name}"
    return None, "none"


def read_json_field(path: Path, pointer: str) -> tuple[Optional[datetime], str]:
    obj = json.loads(path.read_text())
    for part in pointer.split("."):
        obj = obj[part]
    for unit in ("iso", "nanos", "seconds", "date"):
        dt = _parse_ts(obj, unit)
        if dt is not None:
            return dt, pointer
    return None, "none"


# ---------------------------------------------------------------- business-day age

def weekend_hours_between(a: datetime, b: datetime) -> float:
    """Hours of Sat/Sun in [a, b).  Used so a weekday-only feed is not called stale on Sunday."""
    if b <= a:
        return 0.0
    total = 0.0
    cur = a
    while cur < b:
        nxt = min(b, (cur + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0))
        if cur.weekday() >= 5:
            total += (nxt - cur).total_seconds() / 3600.0
        cur = nxt
    return total


# ---------------------------------------------------------------- registry

@dataclass
class Instrument:
    name: str
    lane: str
    path: str
    reader: str                    # "jsonl" | "daykeys" | "field"
    pointer: str = ""
    cadence_hours: float = 24.0    # DECLARED expected cadence
    tolerance: float = 2.0         # STALE when age > cadence * tolerance
    business_days: bool = False    # subtract weekend hours before judging
    note: str = ""
    optional: bool = False         # a not-yet-started collector is not an outage
    tags: list[str] = field(default_factory=list)


REGISTRY: list[Instrument] = [
    Instrument("T30_BORROW", "equities", "research/data/borrow_forward/ledger.json",
               "daykeys", "days", 24, 2.0, True, "day-30 gate ~09-22"),
    Instrument("T31_DERIBIT", "crypto-vol", "research/data/deribit_forward/ledger.json",
               "daykeys", "days", 24, 2.0, False, "day-30 gate ~09-23"),
    Instrument("T33_US_OPTIONS", "equities", "research/data/us_options_forward/ledger.json",
               "daykeys", "days", 24, 2.0, True, "convexity panel, gate ~10-07"),
    Instrument("T45_ETF_LIQ", "equities", "research/data/etf_liquidation_forward/state.json",
               "field", "last_scan", 24, 2.0, True, "EDGAR 497 scan, K1 read ~09-23"),
    Instrument("BASKET1", "equities", "research/trading_bot/BASKET_FORWARD_LOG.jsonl",
               "jsonl", "", 24, 2.0, True, "clock LOCKED: observe only, never re-freeze"),
    Instrument("T4_REALMONEY_READONLY", "equities", "research/trading_bot/T4_FORWARD_LOG.jsonl",
               "jsonl", "", 24, 2.0, True, "READ-ONLY; never touched by this programme"),
    Instrument("NEWSDESK", "news", "research/trading_bot/newsdesk/NEWSDESK_PREREGISTRATION_LOG.jsonl",
               "jsonl", "", 24, 2.0, False, "abstentions count as rows; silence = the tick died"),
    Instrument("PREDMARKET", "predmarket", "research/trading_bot/predmarket/PREDMARKET_PREREGISTRATION_LOG.jsonl",
               "jsonl", "", 24, 2.0, False, "abstentions count as rows"),
    Instrument("ARENA_TAPE_PUMPPORTAL", "memecoin", "research/data/memebot_cache/pumpportal_trades_v2.jsonl",
               "jsonl", "", 1, 2.0, False, "the single tape ALL arena arms read (ws_data.py:45)"),
    Instrument("ARENA_MIGRATION_V1", "memecoin", "research/data/arena/MIGRATION_ACCEPTANCE_V1/ledger.jsonl",
               "jsonl", "", 24, 2.0, False, "arm decisions"),
    Instrument("ARENA_BUNDLE_V2", "memecoin", "research/data/arena/BUNDLE_MOMENTUM_V2/ledger.jsonl",
               "jsonl", "", 24, 2.0, False, "arm decisions"),
    Instrument("ARENA_VIRALITY_V2_2", "memecoin", "research/data/arena/VIRALITY_ARRIVAL_V2_2/ledger.jsonl",
               "jsonl", "", 24, 2.0, False, "arm decisions; 0-resolved defect open (T54)"),
    Instrument("MULTIVENUE_LAUNCH_TAPE", "memecoin", "research/data/memebot_cache/multivenue_launch_tape_v1.jsonl",
               "jsonl", "", 1, 2.0, False, "independent free launch/graduation tape"),
]


# ---------------------------------------------------------------- evaluation

def evaluate(inst: Instrument, now: datetime, root: Path) -> dict:
    p = root / inst.path
    out = {
        "name": inst.name, "lane": inst.lane, "path": inst.path,
        "cadence_hours": inst.cadence_hours, "tolerance": inst.tolerance,
        "business_days": inst.business_days, "note": inst.note,
        "ts_source": None, "newest_utc": None, "age_hours": None,
        "effective_age_hours": None, "allowed_hours": inst.cadence_hours * inst.tolerance,
        "status": None, "detail": "",
    }
    if not p.exists():
        out["status"] = "OPTIONAL_ABSENT" if inst.optional else "MISSING"
        out["detail"] = "file does not exist"
        return out
    if p.stat().st_size == 0:
        out["status"] = "OPTIONAL_ABSENT" if inst.optional else "MISSING"
        out["detail"] = "file is empty"
        return out

    try:
        if inst.reader == "jsonl":
            dt, src = read_jsonl_newest(p)
        elif inst.reader == "daykeys":
            dt, src = read_json_daykeys(p, inst.pointer)
        elif inst.reader == "field":
            dt, src = read_json_field(p, inst.pointer)
        else:
            dt, src = None, "none"
    except Exception as exc:  # a reader that cannot read is itself a fault, not an OK
        out["status"] = "UNREADABLE"
        out["detail"] = f"{type(exc).__name__}: {exc}"
        return out

    if dt is None:
        # FALLBACK, and it is LABELLED: mtime is a proxy and this script exists because
        # proxies lie.  It is reported, never silently treated as a row timestamp.
        dt = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        src = "MTIME_FALLBACK(proxy, not a row timestamp)"

    age = (now - dt).total_seconds() / 3600.0
    eff = age - (weekend_hours_between(dt, now) if inst.business_days else 0.0)
    out["ts_source"] = src
    out["newest_utc"] = dt.isoformat()
    out["age_hours"] = round(age, 2)
    out["effective_age_hours"] = round(eff, 2)
    out["status"] = "STALE" if eff > out["allowed_hours"] else "OK"
    if out["status"] == "STALE":
        out["detail"] = (f"newest input row is {eff:.1f}h old "
                         f"({'business-hours adj' if inst.business_days else 'calendar'}), "
                         f"allowed {out['allowed_hours']:.1f}h")
    return out


BAD = {"STALE", "MISSING", "UNREADABLE"}


def run(now: Optional[datetime] = None, root: Optional[Path] = None,
        registry: Optional[list[Instrument]] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    root = root or REPO
    rows = [evaluate(i, now, root) for i in (registry or REGISTRY)]
    return {
        "generated_utc": now.isoformat(),
        "root": str(root),
        "n": len(rows),
        "stale": [r["name"] for r in rows if r["status"] in BAD],
        "rows": rows,
    }


def render(rep: dict) -> str:
    lines = [f"INPUT-RECENCY ALARM  {rep['generated_utc']}  ({rep['n']} instruments)",
             "-" * 108,
             f"{'STATUS':<16}{'INSTRUMENT':<26}{'LANE':<11}{'AGE(h)':>9}{'ALLOW(h)':>10}  SOURCE"]
    order = {"STALE": 0, "MISSING": 1, "UNREADABLE": 2, "OK": 3, "OPTIONAL_ABSENT": 4}
    for r in sorted(rep["rows"], key=lambda x: (order.get(x["status"], 9), x["name"])):
        age = "-" if r["effective_age_hours"] is None else f"{r['effective_age_hours']:.2f}"
        lines.append(f"{r['status']:<16}{r['name']:<26}{r['lane']:<11}{age:>9}"
                     f"{r['allowed_hours']:>10.1f}  {r['ts_source'] or r['detail']}")
    bad = [r for r in rep["rows"] if r["status"] in BAD]
    lines.append("-" * 108)
    if bad:
        lines.append(f"ALARM: {len(bad)} instrument(s) not live:")
        for r in bad:
            lines.append(f"  - {r['name']}: {r['detail'] or r['status']}  [{r['path']}]")
    else:
        lines.append("All instruments live against their declared cadence.")
    return "\n".join(lines)


# ---------------------------------------------------------------- hermetic selftest

def _selftest() -> int:
    now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)   # a Saturday
    passed, failed = [], []

    def check(name: str, cond: bool, extra: str = "") -> None:
        (passed if cond else failed).append(f"{name} {extra}".strip())

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "d").mkdir()

        def write_jsonl(fn: str, ts: datetime, extra: dict | None = None) -> None:
            row = {"kind": "x", "received_unix_nanos": int(ts.timestamp() * 1e9)}
            row.update(extra or {})
            (root / "d" / fn).write_text(json.dumps(row) + "\n")

        # 1. a synthetic STALE feed MUST be caught
        write_jsonl("stale.jsonl", now - timedelta(hours=56))
        r = evaluate(Instrument("STALE_FEED", "t", "d/stale.jsonl", "jsonl", cadence_hours=1), now, root)
        check("1 stale feed caught", r["status"] == "STALE" and 55 < r["age_hours"] < 57, str(r["status"]))

        # 2. THE 09-02 ARENA SHAPE: live busy process (fresh sibling log + fresh mtime on the
        #    ledger file itself) while the newest ROW is 56h old -> must still be STALE.
        write_jsonl("arena.jsonl", now - timedelta(hours=56))
        (root / "d" / "runtime.log").write_text("busy-spinning on a cached 429\n")
        os.utime(root / "d" / "arena.jsonl", None)          # fresh mtime, stale content
        r = evaluate(Instrument("ARENA_SHAPE", "t", "d/arena.jsonl", "jsonl", cadence_hours=1), now, root)
        check("2 live-process/dead-feed caught", r["status"] == "STALE" and r["ts_source"].startswith("row."),
              f"{r['status']} src={r['ts_source']}")

        # 3. a genuinely fresh feed is OK
        write_jsonl("fresh.jsonl", now - timedelta(minutes=3))
        r = evaluate(Instrument("FRESH", "t", "d/fresh.jsonl", "jsonl", cadence_hours=1), now, root)
        check("3 fresh feed OK", r["status"] == "OK", str(r["status"]))

        # 4. missing and empty files are faults, not silence
        r = evaluate(Instrument("GONE", "t", "d/nope.jsonl", "jsonl"), now, root)
        (root / "d" / "empty.jsonl").write_text("")
        r2 = evaluate(Instrument("EMPTY", "t", "d/empty.jsonl", "jsonl"), now, root)
        check("4 missing/empty are faults", r["status"] == "MISSING" and r2["status"] == "MISSING",
              f"{r['status']}/{r2['status']}")

        # 5. weekend grace: a business-daily feed last written Friday 23:00 is OK on Saturday noon,
        #    and the SAME age on a calendar-cadence feed is STALE.
        fri = now - timedelta(hours=37)
        write_jsonl("biz.jsonl", fri)
        rb = evaluate(Instrument("BIZ", "t", "d/biz.jsonl", "jsonl", cadence_hours=24, business_days=True), now, root)
        rc = evaluate(Instrument("CAL", "t", "d/biz.jsonl", "jsonl", cadence_hours=24, business_days=False), now, root)
        check("5 weekend grace applies only to business feeds",
              rb["status"] == "OK" and rc["effective_age_hours"] > rb["effective_age_hours"],
              f"{rb['status']} eff={rb['effective_age_hours']} vs cal={rc['effective_age_hours']}")

        # 6. mtime fallback is used only when no row timestamp exists, and is LABELLED
        (root / "d" / "nots.jsonl").write_text(json.dumps({"kind": "x", "mint": "abc"}) + "\n")
        r = evaluate(Instrument("NOTS", "t", "d/nots.jsonl", "jsonl", cadence_hours=1), now, root)
        check("6 mtime fallback labelled", "MTIME_FALLBACK" in (r["ts_source"] or ""), str(r["ts_source"]))

        # 7. day-key ledgers read their newest DATE key
        (root / "d" / "ledger.json").write_text(json.dumps(
            {"days": {"2026-09-01": {"status": "clean"}, "2026-09-04": {"status": "clean"}}}))
        r = evaluate(Instrument("DAYS", "t", "d/ledger.json", "daykeys", "days",
                                cadence_hours=24, business_days=True), now, root)
        check("7 daykeys reads newest date", r["newest_utc"].startswith("2026-09-04") and r["status"] == "OK",
              f"{r['newest_utc']} {r['status']}")

        # 8. a corrupt ledger is UNREADABLE, never OK
        (root / "d" / "bad.json").write_text("{not json")
        r = evaluate(Instrument("BAD", "t", "d/bad.json", "daykeys", "days"), now, root)
        check("8 corrupt ledger is UNREADABLE", r["status"] == "UNREADABLE", str(r["status"]))

        # 9. exit code: any STALE makes the run fail
        reg = [Instrument("A", "t", "d/fresh.jsonl", "jsonl", cadence_hours=1),
               Instrument("B", "t", "d/stale.jsonl", "jsonl", cadence_hours=1)]
        rep = run(now=now, root=root, registry=reg)
        check("9 report flags stale set", rep["stale"] == ["B"], str(rep["stale"]))

    print("SELFTEST")
    for p in passed:
        print(f"  PASS  {p}")
    for f in failed:
        print(f"  FAIL  {f}")
    ok = not failed
    print(f"  => {'ALL_PASSED' if ok else 'FAILED'} ({len(passed)}/{len(passed) + len(failed)})")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="T52 input-recency liveness alarm (read-only)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--selftest", action="store_true", help="hermetic selftest, no repo deps")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    rep = run()
    print(json.dumps(rep, indent=2) if args.json else render(rep))
    return 1 if rep["stale"] else 0


if __name__ == "__main__":
    sys.exit(main())
