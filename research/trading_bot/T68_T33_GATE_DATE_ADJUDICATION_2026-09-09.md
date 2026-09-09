# T68 — T33 collector-gate DATE adjudication (2026-09-09 15:00 CEST, CHUNK B / T61 duty)

Read-only adjudication. The frozen rule in `T33_US_OPTIONS_FORWARD.md` is NOT edited; this doc
records the arithmetic and files the estimate correction for the owner. Nothing pinned moved.

## The disagreement (filed by T67 on 2026-09-08)

* Frozen rule (doc §"Protocol", item 1): collector gate **at the 30th trading day**,
  `days_clean / days_attempted >= 0.95`, day 0 = 2026-08-25.
* Doc's estimate of that day: **"≈ 2026-10-07"** (stated twice, lines 65 and 127).
* T67 companion reader (pinned): gate **2026-10-06**, and it prints
  `!! DOES NOT MATCH DOC 2026-10-07` on every run.

## Arithmetic (NYSE calendar, Labor Day 2026-09-07 the only closure in range)

| trading day # | date | note |
|---|---|---|
| 1 | Tue 2026-08-25 | day 0; ledgered `failed` (v1 rule), counted in `days_attempted` |
| 10 | Tue 2026-09-08 | newest ledger row; `days_attempted` = 10 today |
| 29 | Mon 2026-10-05 | |
| **30** | **Tue 2026-10-06** | `days_attempted` first reaches 30 (if no further gaps) |
| 31 | Wed 2026-10-07 | the doc's "≈" date = day 0 + 43 calendar days = 30 trading days AFTER day 0, exclusive |

The collector's own `record()` (`t33_us_options_collect.py:294-296`) counts 2026-08-25 in
`days_attempted` (it is `failed`, not `market_closed`). So under the denominator the gate
actually reads, **trading day 30 is Tue 2026-10-06**. The doc's 10-07 is the 30th trading day
*after* day 0 counted exclusively — an off-by-one in the estimate, not in the rule.

## When the gate is READABLE (the number that matters)

Capture instant for 2026-10-06 is 15:45 America/New_York = 21:45 CEST (crontab fires 20:45 CEST
and the collector sleeps to the target). T72's declared grace is +4h → **23:45 CEST 2026-10-06**.
Supervisor ticks land at 00/03/…/21 CEST, so:

* the **2026-10-06 21:00 CEST tick is TOO EARLY** (day-30 row may not be committed / inside grace);
* the **first admissible read is the 2026-10-07 00:00 CEST (CHUNK A) tick**.

So both dates are "right" on different clocks: **10-06 is the gate's trading day; 10-07 is the
CEST calendar date of the first honest read.** The early-read hazard the strategist named is real
only for a reader who takes 10-06 literally and reads it at the 10-06 12:00 or 15:00 tick, before
the day-30 capture exists. The late-read reading (waiting for 31 trading days) is harmless.

## Does the one-day ambiguity change the VERDICT? No.

Let k = further failed/missing trading days between now and the read. Ledger today: 9 clean / 10.

| read at | k=0 | k=1 | k=2 |
|---|---|---|---|
| day 30 (10-06) | 29/30 = 0.967 PASS | 28/30 = 0.933 FAIL | 27/30 = 0.900 FAIL |
| day 31 (10-07) | 30/31 = 0.968 PASS | 29/31 = 0.935 FAIL | 28/31 = 0.903 FAIL |

The pass/fail boundary is k ≤ 1 on both denominators. The gate has **zero slack**: exactly one
more failed OR silently-missed day kills it (already acknowledged in the frozen doc, line 133).
Cumulative silent-miss exposure is covered by T67 (calendar denominator) and T72 (gap reader);
T67's calendar count must be the denominator of record at the read, per its own rule.

## Filed correction (owner call; no frozen text edited)

1. Amend the doc's two "≈ 2026-10-07" estimates to: **"trading day 30 = Tue 2026-10-06 (capture
   15:45 ET); first admissible read = the 2026-10-07 00:00 CEST tick; NOT the 10-06 12:00/15:00/
   21:00 ticks."** Rule text unchanged.
2. The T67 flag `DOES NOT MATCH DOC` is adjudicated: it is a labelling mismatch, not a defect
   in either number. Leave T67 pinned as-is (it is correct on the trading-day clock).
3. Agenda T68 → done (adjudicated); the read instruction is carried on T62-style gate tasks
   for the 2026-10-07 00:00 tick.

## Not verified this tick

The NYSE 2026 holiday calendar beyond Labor Day was taken from memory (next closure
Thanksgiving 11-26, outside the window); T33 per-underlying coverage, the T33 pin sha256, and the
collector's sleep-to-target behaviour on the 10-06 run itself.
