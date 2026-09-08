# T67 — calendar-denominator companion gate reader (T31 + T33)

**Built and pinned:** 2026-09-08 03:00 CEST (CHUNK B integrity tick).
**Script:** `scripts/trading_bot/t67_calendar_denominator_gate.py`
**Pin:** `sha256 1bb026d7c306c6a7aaa7d50c2ca0237dcbb06647eb7f86708591256a33d3b128`
(`research/trading_bot/T67_CALENDAR_DENOMINATOR_GATE.sha256`)
**Status:** built, self-validated, live reading taken. Pinned **15 days before the T31 gate and
29 days before the T33 gate** — i.e. blind, before either gate can fire.

## 1. The defect this exists for

Both collectors compute their gate denominator from days they **observed**:

| | file:line | denominator |
|---|---|---|
| T31 | `scripts/trading_bot/t31_deribit_collect.py:219` | `days_attempted = len(ledger["days"])` |
| T33 | `scripts/trading_bot/t33_us_options_collect.py:296` | `days_attempted = len(trading)` where `trading` filters `ledger["days"]` |

`record()` is only ever called from inside a collector run. **A date on which cron never fires
gets no ledger entry at all** — it is counted as neither clean nor failed. The denominator does
not grow, the ratio stays pinned at `1.00`, and the gate returns a clean **PASS on a collector
that has been dead for a week**. It is asymmetric in the wrong direction: it can only turn a
dead collector into a PASS, never a live one into a fail.

This is the **T52 failure shape** exactly — a green proxy that cannot represent its own absence,
the same shape that let MEME ARENA render a green dashboard through a 56-hour outage.

## 2. This is not a rule change

Both frozen protocols **already** specify a calendar-derived denominator, and the frozen text is
authoritative over the code:

> **T31** (`T31_DERIBIT_FORWARD.md` L63–64): `days_clean / days_attempted ≥ 0.95` "with
> `days_attempted` = **calendar days since day 0**, so silent cron death counts as failure."

> **T33** (`T33_US_OPTIONS_FORWARD.md` L65–67): `days_clean / days_attempted ≥ 0.95`, "where
> **every scheduled trading day counts as attempted** (a silent cron death is a failed day — the
> gate tick **reconciles the ledger against the exchange calendar**)."

So the frozen rule is **not moved** and the running collectors' ledger writers are **not
patched**. Rewriting a live instrument's bookkeeping days before its gate is how this programme
reset the BASKET1 forward clock ten times. Instead this is a **strictly additive, read-only
companion** placed beside the running instrument — the same pattern as T62 and T63.

**Where this reader disagrees with a collector's own `--status`, the calendar reading is the
verdict.**

## 3. What the reader does

Read-only. It writes nothing — no ledger, no manifest, no snapshot, no report file. It reads
only day labels, per-day status strings and snapshot **filenames**; it never opens a snapshot,
so it cannot leak a strategy number before the pre-registered 2026-12-23 design read.

Per panel it enumerates every day the collector was **scheduled** to fire between day 0 and the
gate, and classifies each as `clean` / `failed` / **`MISSING`** (absent from the ledger entirely
— the defect), then reports `clean / scheduled` beside the collector's own self-reported ratio
and the **denominator gap** between them.

Three design points that are themselves load-bearing:

- **Capture clock.** A scheduled day only becomes *due* once its capture instant plus a 4-hour
  grace has passed (T31: 00:15 UTC; T33: 15:45 America/New_York). Without this the reader flags
  the current, still-in-flight day as a silent death — which is the *same* class of error the
  reader exists to catch. It did exactly that on the first run, against T33 2026-09-08, and was
  fixed before pinning.
- **Exchange calendar.** T33's trading-day set is weekdays minus an explicit, auditable US
  holiday list, with **early-close days treated as non-trading** (a 13:00 ET close cannot serve
  a 15:45 ET capture).
- **Conflict is not clean.** If the calendar says a day was scheduled and the collector says
  `market_closed`, the frozen text ("every scheduled trading day counts as attempted") makes it
  **not clean**, and it is flagged.

Exit codes: `0` pass/not-due, `1` a due gate FAILs, `2` the reader disagrees with a collector's
self-reported denominator.

## 4. Selftest — proof the reader fires

`--selftest` builds synthetic ledgers in a temp dir and asserts the absence arithmetic. All 5
cases pass. The load-bearing one:

| case | collector `--status` | T67 reading | |
|---|---|---|---|
| all clean, 30 days | 30/30 = 1.00 PASS | 1.0000 **PASS** | agree |
| **cron silently dies for the last 7 days** | **23/23 = 1.00 → fake PASS** | **0.7667 → FAIL** | **the defect, caught** |
| one *explicit* failure | 29/30 = 0.9667 PASS | 0.9667 **PASS** | agree — not over-strict |
| two silent gaps | 28/28 = 1.00 → fake PASS | 0.9333 **FAIL** | caught |
| trading cadence, weekends absent | 30/30 PASS | 1.0000 **PASS** | weekends correctly not "missing" |

**Scope limit, stated explicitly (T-selftest rule):** this validates the *arithmetic of absence*
on synthetic input. It says nothing about the live data path. The §5 live reading is the
separate — and more important — evidence.

## 5. Live reading, 2026-09-08 (blind: no strategy number read)

```
T31_DERIBIT   [calendar, day0 2026-08-25, gate 2026-09-23]
  window 2026-08-25 .. 2026-09-07 (last due day; capture 00:15 UTC +4h)
  14 scheduled -> clean 14 / failed 0 / MISSING 0     calendar ratio 1.0000
  collector --status 16/16 = 1.0     denominator gap -2
  VERDICT: GATE_NOT_DUE

T33_US_OPTIONS [trading, day0 2026-08-25, gate 2026-10-06 (doc says ~10-07)]
  window 2026-08-25 .. 2026-09-04 (last due day; capture 15:45 ET +4h)
  9 scheduled -> clean 8 / failed 1 / MISSING 0       calendar ratio 0.8889
  collector --status 8/9 = 0.8889   denominator gap 0
  VERDICT: GATE_NOT_DUE
```

**Both panels have ZERO missing days today.** The exposure is live but has **not yet bitten** —
consistent with the 2026-09-08 00:00 STRATEGIST calendar enumeration. The reader is in place for
the remaining 15 / 29 days, which is the entire point of pinning it now.

Two reconciliations, both benign and both recorded rather than papered over:

- **T31 gap −2.** The collector's denominator is *larger* than the calendar's: it counts
  2026-08-24 (day 0, excluded by `CONVEXITY_PREREGISTRATION.md` as off-clock at 13:06 UTC) and
  the in-flight 2026-09-08. 08-24 is clean, so it inflates numerator and denominator equally and
  cannot move the ratio materially. Noted, not scored.
- **T33 8/9 = 0.8889 is currently BELOW the 0.95 threshold** — this is the known, already-logged
  v1 failure on 2026-08-25 under the superseded clean-day rule, and the panel has **zero slack**
  by design (one further failed day → 28/30 < 0.95 → the gate's one bounded fix tick). The gate
  is not due; nothing here is new and nothing is moved.

## 6. Open flag for the gate tick — T33's gate date is off by one

The frozen doc estimates the T33 gate at "**≈ 2026-10-07**". Counting the rule it actually
states — the **30th trading day** from day 0 = 2026-08-25, with 2026-09-07 Labor Day excluded
(and the collector itself ledgered 09-07 `market_closed`, agreeing) — the 30th trading day is
**Tuesday 2026-10-06**. The "≈" estimate appears to predate the Labor Day exclusion.

**Not resolved autonomously.** No frozen text is edited. The reader reports **both** dates and
flags the mismatch loudly on every run. The operative rule is the 30th trading day; a one-day
disagreement must be settled by a human **before** 2026-10-06, not discovered on the day.

## 7. How to use it at the gates

At the **~2026-09-23 T31 gate** and the **2026-10-06/07 T33 gate**, run

```
python -m scripts.trading_bot.t67_calendar_denominator_gate --panel t31   # then t33
```

**before** trusting the collector's own `--status`. If the two disagree, the calendar reading is
the verdict and the gate does not pass on the collector's word.

## 8. Not covered

T30 is **not exposed** — `t30_borrow_evaluate.py:309` gates on an absolute count of 30 *clean*
days (`MIN_CLEAN_DAYS = 30`), so an outage can only **delay** its gate, never fake it. That is
the safer gate design and should be the default for any future collector. T45, BASKET1,
NEWSDESK, PREDMARKET denominators are **not audited here** and are not asserted clean.
