# T59 — T45_ETF_LIQ authoritative-clock adjudication

**Date:** 2026-09-07T01:00Z (CHUNK B tick, hour 03 rotation)
**Duty:** T61 instrument-integrity queue, item (2).
**Scope:** read-only diagnosis. Nothing restarted, re-epoched or resolved. The T45
collector is hash-pinned (`a290805a…`, verified intact this tick) and was NOT edited.

## 1. The reported disagreement was NOT a disagreement

Logged twice as a footnote (2026-09-05 15:00, 2026-09-06 03:00): the CLI prints
`last_scan=2026-09-04T21:15:11Z` (~52h stale by now) while the T52 alarm reads
T45_ETF_LIQ at 2.75–3.76h and calls it OK.

Adjudicated: **both readers read the same field** — `research/data/etf_liquidation_forward/state.json`
key `last_scan`. There is no second field and no second file.

- `input_recency_alarm.py:185-186` registers T45 as `reader="field", pointer="last_scan"`,
  `cadence_hours=24, tolerance=2.0, business_days=True`.
- The alarm's table column prints `effective_age_hours` = calendar age **minus weekend hours**
  (`evaluate()`, `weekend_hours_between()`), because T45 is a weekday-only feed.
- T45's cron is weekday-only by construction: `15 23 * * 1-5`.

Arithmetic, this tick: last scan Fri 2026-09-04 21:15:11Z; now Mon 2026-09-07 01:00:30Z.
Calendar age 51.76h; weekend hours (Sat 00:00 → Mon 00:00) = 48.0h; effective = **3.76h**. OK.

The constant `2.75` printed across every tick from 09-05 15:00 through 09-07 00:00 is
**correct by construction**, not a frozen value: through the weekend, each additional hour of
calendar age is an additional weekend hour, so the effective age is stationary. It ticked up
to 3.76 the moment Monday started, exactly as it should.

**Verdict on the alarm: no defect.** The weekend adjustment is right and matches the feed's
declared cadence. The 25h "gap" was a human comparison of a *calendar* age against a
*business-hours-adjusted* age — two clocks over one field, not two fields.

## 2. Was T45 actually collecting? YES

`cron.log` shows clean, on-schedule runs with no errors:

```
[2026-09-02 23:15] scan done: 0 new candidate(s), 11 total seen
[2026-09-03 23:15] scan done: 0 new candidate(s), 11 total seen
[2026-09-04 23:15] scan done: 0 new candidate(s), 11 total seen
```

Fri 09-04 was the last weekday; the next scheduled run is Mon 2026-09-07 23:15 CEST.
**T45 has not missed a run.** The 0-new-candidate streak is a world fact (no new US ETF cash
liquidations hit the three EDGAR full-text queries), not a process fault.

**AUTHORITATIVE CLOCK (declared):** `state.json:last_scan`, judged **business-hours-adjusted**
against a 24h cadence / 48h allowance. The CLI's raw calendar print stays as-is; it is
bookkeeping, and reading it as an outage was the error.

## 3. NEW DEFECT FOUND (filed, not fixed) — T45-D1: `last_scan` is an attempt proxy

`t45_etf_liquidation_collect.py:210` writes `state["last_scan"] = now()` **unconditionally**
after the query loop. The loop is log-and-continue on exception (`except Exception … continue`,
~line 191). Therefore:

> If all three EDGAR full-text queries throw every night — network down, SEC blocks the UA,
> endpoint moved, rate limit — the collector logs three `scan ERROR` lines, writes a fresh
> `last_scan`, and **the T52 alarm stays green forever over an input surface that is receiving
> nothing.**

This is precisely the failure shape T52 was built to catch, on a currently-live lane:
a green proxy over a dead input. Today it is masked because a genuine "0 new candidates"
and a total EDGAR failure produce **the same observable state** at the alarm.
Severity: the K1 read is ~09-23; a silent EDGAR failure between now and then would present
as "no liquidations occurred" and the pinned evaluator would read it as a world fact.

**Proposed correction (owner decision — collector is hash-pinned, do NOT apply autonomously):**
one line, collector-side: track whether at least one query returned without exception and
write `state["last_scan_ok"]` only in that case; repoint the alarm's `pointer` to
`last_scan_ok`. Cost: a re-pin of `a290805a…`. Because it changes a pinned instrument
mid-flight it must not be done in a tick.

**Zero-cost interim mitigation, also owner's call:** nothing in the collector needs to change
to detect this — `cron.log` already emits `scan query=… hits=N` on success and `scan ERROR` on
failure. A reader that asserts "≥1 `hits=` line in the last weekday run" closes the hole
without touching the pin.

## 4. Standing duty T46 (same tick)

`t45_etf_liquidation_collect.py status`: prereg `6821745b…` BINDING, chain OK (23 links),
**0 candidates pending review**, 0 tracked events, 0 complete, DECIDER=COLLECTING.
Nothing to confirm or reject; no event past a pay date needs record-cash. Duty discharged.
