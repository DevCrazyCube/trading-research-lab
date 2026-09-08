#!/usr/bin/env python3
"""NEWSDESK1 starvation counter -- the cheap measurement that decides whether the DESIGN is dead.

Pre-registered 2026-09-04 (abstention note, item 4) and built 2026-09-05.

THE QUESTION
============
NEWSDESK1's bar is 30 resolved setups. It stands at 2/30 after 12 days. The 2026-09-04 read argued
the ledger will never reach N=30 -- not because the agent keeps failing to find the setup, but
because the intersection

    {first-print HARD catalyst}  x  {frozen 18-name mega-cap universe}  x  {younger than a tick}

is ~0 per tick by construction. That is a measurable claim, so measure it instead of arguing it.

THE MEASUREMENT (frozen definition -- do not tune it after seeing counts)
========================================================================
For each tick's already-pulled event stream -- which MUST be the FULL stream
(`newsdesk read --limit 400`), not the default 15-per-source display slice, or the count is
biased downward by construction -- count events that are ALL of:
  * FRESH   : ts_utc is <= FRESH_MINUTES (15) old at pull time. A 3-hourly tick that cannot see a
              catalyst inside 15 minutes of the print is, by this programme's own standard, late.
  * IN-UNIV : names a symbol in the frozen equity watchlist or crypto universe -- via the event's
              parsed `tickers`/`assets`, or a whole-word ticker match in the headline. `feed_ticker`
              does NOT count: it records which feed the item came from, not what the item is about.
  * HARD    : carries a first-print quantitative/legal issuer fact, not commentary. SEC_8K always
              qualifies; other sources qualify only on an explicit catalyst keyword.

EXCLUSION, stated up front: COINGECKO_TRENDING is stamped at pull time, so every such item is
trivially "fresh" and would inflate the count to 15/tick with zero information. It is dropped.
This exclusion is part of the frozen definition, not a result-driven filter.

KILL RULE (pre-registered, from the 2026-09-04 note)
===================================================
If over 20 consecutive ticks the TOTAL count of qualifying events is <= 1, NEWSDESK1 is declared
STRUCTURALLY STARVED and killed -- no further discretionary reads. The fix would not be a better
read; it would be widening the universe (which collides with the liquid/free-priceable rule) or
accepting that a 3-hour cadence cannot front-run a wire.

This module never looks at any outcome and never proposes anything.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import sys

FRESH_MINUTES = 15
KILL_WINDOW_TICKS = 20
KILL_MAX_TOTAL = 1

LEDGER = pathlib.Path(__file__).resolve().parents[3] / "research" / "trading_bot" / "newsdesk" / "NEWSDESK_STARVATION.jsonl"

EXCLUDED_SOURCES = {"COINGECKO_TRENDING"}

# First-print hard-fact markers. Deliberately generous: a false POSITIVE only makes the design look
# healthier than it is, so a starvation verdict reached under this list is conservative.
HARD_PATTERNS = re.compile(
    r"\b(8-K|guidance|guides|forecast|outlook cut|outlook raised|preliminary results|"
    r"reports? (?:first|second|third|fourth|Q[1-4])|earnings (?:beat|miss|results)|"
    r"revenue (?:rose|fell|up|down)|comparable sales|monthly sales|"
    r"to acquire|acquisition of|merger agreement|tender offer|takeover bid|"
    r"secondary offering|convertible notes|share buyback|dividend (?:cut|raised|increase)|"
    r"halted|trading halt|recall|FDA (?:approval|rejection|clearance)|"
    r"SEC (?:charges|investigation)|DOJ|subpoena|antitrust suit|"
    r"CEO (?:resigns|steps down|fired)|CFO (?:resigns|steps down)|bankruptcy|Chapter 11|"
    r"files? for|8‑K)\b",
    re.IGNORECASE,
)


def _universe(spec: dict) -> tuple[set[str], set[str]]:
    equities = {s.upper() for s in spec.get("equity_watchlist", [])}
    crypto_ids = {k for k in spec.get("crypto_universe", {})}
    crypto_syms = {v.upper() for v in spec.get("crypto_universe", {}).values()}
    return equities, crypto_ids | crypto_syms


def _matches_universe(ev: dict, equities: set[str], cryptos: set[str]) -> list[str]:
    """Symbols the event is ABOUT. `feed_ticker` is intentionally ignored (it is provenance)."""
    hits = set()
    for t in ev.get("tickers") or []:
        if str(t).upper() in equities:
            hits.add(str(t).upper())
    for a in ev.get("assets") or []:
        if str(a).upper() in cryptos or str(a) in cryptos:
            hits.add(str(a).upper())
    text = f"{ev.get('headline','')} {ev.get('snippet','')}"
    for sym in equities:
        if re.search(rf"\b{re.escape(sym)}\b", text):
            hits.add(sym)
    return sorted(hits)


def _age_minutes(ev: dict, now: dt.datetime) -> float | None:
    raw = ev.get("ts_utc")
    if not raw:
        return None
    try:
        ts = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return (now - ts).total_seconds() / 60.0


def measure(read_blob: dict, spec: dict) -> dict:
    """One tick's measurement. Pure: same stream in, same numbers out."""
    equities, cryptos = _universe(spec)
    pulled = read_blob.get("pulled_utc")
    now = dt.datetime.fromisoformat(str(pulled).replace("Z", "+00:00")) if pulled else dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)

    events = read_blob.get("events") or []
    qualifying, n_fresh, n_in_univ = [], 0, 0
    for ev in events:
        if ev.get("source") in EXCLUDED_SOURCES:
            continue
        age = _age_minutes(ev, now)
        fresh = age is not None and age <= FRESH_MINUTES
        syms = _matches_universe(ev, equities, cryptos)
        hard = ev.get("source") == "SEC_8K" or bool(HARD_PATTERNS.search(f"{ev.get('headline','')} {ev.get('snippet','')}"))
        if fresh:
            n_fresh += 1
        if syms:
            n_in_univ += 1
        if fresh and syms and hard:
            qualifying.append({"id": ev.get("id"), "source": ev.get("source"), "age_min": round(age, 2),
                               "symbols": syms, "headline": (ev.get("headline") or "")[:160]})

    return {
        "tick_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "pulled_utc": pulled,
        "n_events_shown": len(events),
        "n_events_total": read_blob.get("n_events"),
        "n_fresh_le_15min": n_fresh,
        "n_in_universe": n_in_univ,
        "n_qualifying": len(qualifying),
        "qualifying": qualifying,
        "fresh_minutes": FRESH_MINUTES,
        "definition_version": 1,
    }


def append(record: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def verdict() -> dict:
    """Where the pre-registered kill rule stands. No tuning: the rule was frozen before tick 1."""
    if not LEDGER.exists():
        return {"n_ticks": 0, "status": "NO_DATA"}
    rows = [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]
    window = rows[-KILL_WINDOW_TICKS:]
    total = sum(r.get("n_qualifying", 0) for r in window)
    status = "COLLECTING"
    if len(window) >= KILL_WINDOW_TICKS:
        status = "STARVED_KILL" if total <= KILL_MAX_TOTAL else "NOT_STARVED"
    return {"n_ticks": len(rows), "window_ticks": len(window), "window_qualifying_total": total,
            "kill_rule": f"<= {KILL_MAX_TOTAL} qualifying over {KILL_WINDOW_TICKS} consecutive ticks",
            "status": status}


def main(argv: list[str]) -> int:
    spec = json.loads((LEDGER.parent / "NEWSDESK_FROZEN.json").read_text())
    if argv and argv[0] == "verdict":
        print(json.dumps(verdict(), indent=2))
        return 0
    if not argv:
        print("usage: starvation.py <read_output.json> | verdict", file=sys.stderr)
        return 2
    rec = measure(json.loads(pathlib.Path(argv[0]).read_text()), spec)
    append(rec)
    print(json.dumps({**rec, "verdict": verdict()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
