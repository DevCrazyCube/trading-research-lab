# STRATEGIST DECISION — 2026-08-24 (00:00 CEST tick)

**Author:** durable supervisor, CHUNK A (strategist).
**Standing:** first strategist note under the 3-hourly durable tick. Written after orienting on
`agenda.json` (28/28 tasks closed, all owner-approved), `FINDINGS.md`, `INVENT_0823_MASTER.md`,
and the free-data-convexity-wall memory.

---

## 1. Where the programme stands

Every search track has terminated in a measured, multiply-corrected zero:

- **Directional:** 0-for-8. Carry: dead 4 independent ways (T22/T23/T24/T25).
- **Non-directional shortlist:** five candidates dead on a power census (T9, T15, T23, T24, T25);
  free data resolves 3–15 pp/yr, the surviving mechanisms offer 0.4–3 pp/yr.
- **Invention:** round 1 (4 gauntlet survivors, all dead on freeze-then-test), round 2 SIZE
  (0 survivors), INVENT_0822 (256 formulas, 0), INVENT_0823 (106 formulas, 0, 3/3 themes noise).
  The pooled-bar arithmetic now predicts **ex ante** zero survivors for any further sweep of the
  same free daily data. Running another one is buying a known zero.

What is still **alive and accruing**:

| asset | state |
|---|---|
| BASKET1 v8 forward clock | fresh clock since 2026-08-23, untouched by INVENT_0823 |
| T4 paper forward (SPY overlay) | running, 0 settled sessions, owner-gated — supervisor never touches |
| Window-2 deadness-screen OOS | collection running (b11m, b15d/e shadow loggers) |
| **Preferred-series RV** | best tether confirmation on record (gross t 7.49, OOS-replicated gradient), unpromotable **only** on the borrow wall — killed by a *flag*, never by a *rate* |
| **Bought convexity** | untestable on free historical data; Deribit snapshot tooling exists (`deribit_free_snapshot.py`, 9 historical free samples cached) |
| SPX box | T25 probe: executable −3.65 pp vs T-bills, but captured with the market closed; RTH re-measure explicitly recommended and never done |

## 2. The decision — build the forward-data spine

**Stop mining burned free data. Convert calendar time into the two datasets that each decide an
already-identified candidate.** The programme's remaining free lever is TIME, not another sweep.

Ranked, with rationale:

1. **T30 — daily borrow-fee/availability collector** (highest value). The 2026-08-22 synthesis
   ranked a borrow-availability feed as the #1 data acquisition because *it alone decides the
   already-replicated preferred-series RV*. Alpaca's `easy_to_borrow` flag is a status, not a rate
   (B22G); a daily fee/availability snapshot (IBKR shortstock mirror, free) is the measurement.
2. **T31 — daily Deribit BTC/ETH option wing-quote collector.** The one identified escape from the
   convexity dilemma. Tooling exists; what's missing is a *scheduled, detached* daily run with a
   completeness ledger. Cost is pure calendar time and it compounds while undecided.
3. **T32 — SPX box RTH re-measure** (bounded probe, ~1 h). The only remaining claim whose estimand
   is a **rate level**, not a Sharpe — it passes any power census trivially. Third and final probe.

All three create or resolve a measurement. None is a sweep.

## 3. Kill-conditions, stated before results

- **T30:** after 30 clean daily snapshots, if fewer than ~10 of the 113 preferred-RV pairs have
  both legs borrowable at a fee below the pair's measured gross edge, **preferred-series RV is
  permanently dead** and the collector downgrades to passive archive.
- **T31:** ≥95% clean-snapshot days over the first 30, or fix/kill the collector. The convexity
  test itself gets its own pre-registration **no earlier than +120 days** of collected data.
- **T32:** if the four-leg executable rate during RTH is again below T-bills, the box is dead
  permanently — no fourth probe.
- **The direction as a whole:** if both collectors mature and the pre-registered designs on them
  die at the honest bars, the free-data programme is **EXHAUSTED**, and the remaining fork —
  pay for historical options/tick data, or stop — goes to the owner as one decision.

## 4. Standing directive to future ticks (esp. CHUNK B invention)

Until the collectors mature, **invention ticks must not run new sweeps of free daily/intraday
equity, ETF, or crypto cross-section data** — that category is closed by EXECUTION_COST_WALL.md
and three consecutive honest zeros. A valid CHUNK B tick is: building/verifying a collector,
pre-registering (without running) a design that will consume the collected panels, or a genuinely
*new-data-source* idea that is neither a price-bar sweep nor a published-edge replication. An
honest "nothing clears the bar, no round run" is a better outcome than zero #4.

## 5. Owner fork (stated, not blocking)

The pay-for-data option (historical options/tick data to test bought-convexity **now** instead of
waiting ~4 months) remains open and is a money gate. Recommendation: don't spend yet — the free
collectors decide the same questions for zero dollars, and the preferred-RV question resolves in
~30 days of collection.
