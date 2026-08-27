# T18 PRE-REGISTRATION — the ORB exit leg, measured at tick level

**Status: FROZEN.** Hashed before any held-out T18 number exists. The two scripts named below
are hashed in the same command that asserts the absence of `T18_EXIT_MEASUREMENT.json` and
`T18_RECOST_RESULT.json`.

---

## 0. The question, in one sentence

T17 established that the Zarattini/Barbon/Aziz opening-range breakout is a **real** signal
(permutation p = 0.0005, held-out zero-cost Sharpe 2.74 against the paper's 2.81) whose honest
net Sharpe sits somewhere between **+1.09 and −8.36**, and that the entire spread is carried by
**two never-measured quantities**: what the EXIT leg actually fills at, and where inside the
one-minute entry bar the stop realistically fires. This measures both, from SIP ticks, and
re-prices the held-out run with the answers.

## 1. What is being measured, exactly

On a pinned sample of the stock-days T17's **held-out** run actually traded
(`research/data/t17_cache/selection.json`, window 2022-01-03 → 2026-08-14):

| | quantity | definition |
|---|---|---|
| **X** | **stop-loss exit slippage** | the first SIP trade at or through the stop level after the entry fills is the trigger; the fill is the prevailing **NBBO bid** (long) / **ask** (short) at trigger + latency; the slippage is `stop level − fill` (long) / `fill − stop level` (short), **positive is adverse**. Reported in bp of R and centi-bp of notional, on the 0/100/500/1000 ms ladder. |
| **C** | **MOC exit slippage** | for positions that reach the close: the realised fill is the **official closing print** (SIP condition `6`, largest size where several venues print — M0's convention). The backtest credits the **last 1-minute bar's close**. The signed adverse gap between them is the cost. If there is **no** official print the MOC does not fill, and the exit is priced at the last NBBO bid/ask before 16:00:00 ET. |
| **T** | **entry-bar tie-break** | for the SAME stop level, three readings of "was the stop hit during the entry minute": `close` (T17's frozen rule — the bar closes through), `full_bar` (T17's adverse sensitivity — the bar's low/high is through), and **TICK** (a trade printed at or through the stop **after the entry fill instant**, inside that same minute). The disputed set is `full_bar` = hit and `close` = not hit; the reported statistic is `P(tick says hit | disputed)` with its exact numerator and denominator. |

The entry leg is **not** re-measured for a verdict — B22B owns it — but it is recomputed on this
sample and reported as a **consistency check** against B22B's 429 observations, because a T18
entry number that disagreed with B22B would mean the two measurements are not measuring the same
thing and the exit number could not be combined with T6.

## 2. Sample, pinned before it is drawn

| | |
|---|---|
| population | the 1,158 held-out sessions carrying a T17 selection |
| draw | `sample_sessions(..., n=50, seed=20260818)`, **stratified by calendar year** in proportion to each year's share of sessions, remainder largest-fraction-first, ties on the year label |
| per session | **every** name in T17's top-20 selection, at its own opening-range level and direction |
| expected size | ~1,000 stock-days, against B22B's 429 entry observations |
| data | Alpaca **SIP** `/v2/stocks/trades`, `/v2/stocks/quotes`, `/v2/stocks/auctions`; 1-minute paths from the T17 cache (`adjustment=raw`, SIP), i.e. the same bars the backtest ran on |
| verdict latency rung | **100 ms**, B22B's own verdict rung, carried across unchanged |

Sessions drawn (printed by `t18_exit_ticks.py sample` before collection): 2022 × 11, 2023 × 11,
2024 × 11, 2025 × 11, 2026 × 6.

## 3. Discipline

1. **`scripts/b22b_slippage_harness.py` is NOT edited.** It is imported, its sha256 asserted
   against the pin in `research/B22B_SLIPPAGE_PREREGISTRATION.json` at import time, and its
   arithmetic re-used: the single float boundary `to_micros`, the nanosecond RFC3339 parser, the
   prevailing-quote lookup `quote_at`, the integer-index percentiles, the ATR/R units and the
   DST-derived session bounds. A modified harness makes T18 refuse.
2. **Absence is refusal, never zero.** No prevailing quote → refusal (after widening the
   lookback, because a 5-second window containing no quote is a property of the window, not of
   the market). No opening-range trigger → its own bucket, never a zero-slippage observation.
   No closing print → priced as a hand unwind across the closing spread, never as a free exit.
3. **Sign convention asserted, not assumed.** `adverse()` writes both legs out separately;
   positive is always worse for the trader.
4. **Decontamination.** B22B/T6's 0.1-ATR rung (one whole R through the level) is applied, and
   the unfiltered distribution is reported beside it. **The exit's filter direction is not the
   entry's**, so the pool actually charged is chosen by a rule frozen here:
   > **the pool charged is whichever of {unfiltered, decontaminated} has the MORE ADVERSE mean.**
   Both are recorded, with the chosen one named.
5. **The re-cost changes exactly two inputs.** Universe, selection, paths, sizing, 4× gross cap,
   compounding, **entry** slippage draws (same pool, same keys, same LCG), statistics and
   permutation machinery are T17's, imported from `t17_run.py`, unedited.
6. **Control.** The T18 simulator, run with T17's own settings, must reproduce the published
   held-out primary Sharpe (1.0882197303767718) to 1e-9 or the run refuses. A corrected number
   from a rig that cannot reproduce the number it corrects is not evidence.
7. **The exit half-spread is not charged twice.** The measured exit slippage runs from a traded
   level to the far side of the book and therefore already contains the half-spread, exactly as
   B22B's entry number does. The `plus_exit_half_spread` rung charges it anyway, on top of T17's
   own adverse bar-gap exit base, as the conservative bound.

## 4. The declared configurations — EIGHT, declared before any T18 PnL exists

Commission-free (Alpaca-realistic) unless stated. All on T17's held-out window and selection.

| # | name | entry-bar rule | exit base | exit half-spread | commission | charge mode | entry slippage |
|---|---|---|---|---|---|---|---|
| 1 | `t18/measured_exit/R` — **PRIMARY** | measured rate | stop level | not charged | 0 | price, bp of R | B22B |
| 2 | `t18/measured_exit/R/entry_bar_close` | T17's `close` | stop level | not charged | 0 | price, bp of R | B22B |
| 3 | `t18/measured_exit/R/entry_bar_full_bar` | T17's `full_bar` | stop level | not charged | 0 | price, bp of R | B22B |
| 4 | `t18/measured_exit/R/plus_exit_half_spread` | measured rate | T17 bar gap | **charged** | 0 | price, bp of R | B22B |
| 5 | `t18/measured_exit/R/paper_commission` | measured rate | stop level | not charged | $0.0035/sh | price, bp of R | B22B |
| 6 | `t18/measured_exit/R/tie_break_upper_ci` | measured rate at the **Wilson 95 % upper bound** | stop level | not charged | 0 | price, bp of R | B22B |
| 7 | `t18/measured_exit/notional` | measured rate | stop level | not charged | 0 | **notional** | B22B |
| 8 | `t18/measured_entry_and_exit/R` — **declared diagnostic** | measured rate | stop level | not charged | 0 | price, bp of R | **T18, on T17's own selected names** |

**Why #7 exists.** T17's verdict differed between the two legitimate transfers of one
measurement — bp of R gave Sharpe 1.088 and PSR 0.9931, bp of notional gave 0.674 and 0.9323.
The same fork has to be reported for the corrected exit or the comparison is not like-for-like.

**Why #8 exists, and why it is declared rather than footnoted.** B22B measured the entry on a
**2025 most-actives** pool. T17 trades the **top 20 by relative volume**, which is a different
and generally less liquid set of names, and transfers B22B's distribution onto it. This
configuration re-measures the ENTRY on the stock-days the strategy actually selected. If the two
disagree materially then the larger error in T17's cost model is the *transfer*, not the exit,
and that must be visible in the result rather than buried. It is a **diagnostic**: the verdict
is taken on #1.

## 4b. The additive change to `costs.py`

`SlippageProvenance.MEASURED_T18_EXIT` and `measured_exit_leg_t18(kind, latency_ms)` are added.
**No existing cost number changes** — `b22b_measured_costs()` still returns the T6 model with
its `ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG` exit, so every published result stays reproducible,
and a caller who wants the measured exit asks for it. The provenance is gated on
`T18_EXIT_MEASUREMENT.json` existing **and** carrying at least 300 measured stop exits;
truncate the file and the rig returns to refusing. `tests/test_t2_backtest_harness.py`:
113/113 pass after the change.

## 5. Certification, and the multiple-testing count that is NOT reset

The T17 gates are re-applied unchanged: net mean daily return > 0, permutation p < 0.05,
deflated Sharpe ≥ 0.95. Three certification numbers are reported for **every** configuration and
the primary one is named here in advance:

| basis | trials | what it is |
|---|---|---|
| `dsr_trials_12_cumulative` — **the verdict** | **12** | T17's 6 declared trials **plus** T18's 6, with the cross-trial Sharpe variance recomputed over all twelve. The search does not get to forget T17. |
| `dsr_trials_6_t17_basis` | 6 | the same statistic on T17's own basis, so the two runs are directly comparable |
| `psr_trials_1` | 1 | the probabilistic Sharpe against zero, i.e. the most generous specification available — reported because T17 reported it (0.9931 / 0.9323), never as the verdict |

**Verdict rule, frozen:** SURVIVES only if net mean > 0 **and** permutation p < 0.05 **and**
`dsr_trials_12_cumulative` ≥ 0.95. Anything else is DEAD, and a DEAD verdict with a higher
Sharpe than T17's is still DEAD.

## 6. What this cannot establish, stated in advance

- **Capacity.** The measurement records the size resting at the touched side; it does not ask
  whether a real order size fills there. A price is not a fill.
- **The transfer.** Measured exit slippage is drawn onto simulated stop events by a keyed draw,
  so the *correlation* between an expensive fill and a bad day is not preserved — the same
  limitation T17's entry draws carry, in the same direction.
- **Our order joining the closing cross.** M0's C4. A tape cannot answer it; only live orders
  can, and none were placed.
- **50 sessions are not 1,158.** The measurement is a sample; the re-cost transfers it to the
  whole held-out window and says so.
- **Point-in-time shortability** is still unobtainable (B22G), so the short leg's availability
  is a bound, not a fact.

## 7. Artifacts hashed by this document

| artifact | sha256 |
|---|---|
| `scripts/trading_bot/t18_exit_ticks.py` | `4973e7619ccf438d56cec2772896e54f7085f949849eae438862741b5946ebdf` |
| `scripts/trading_bot/t18_recost.py` | `8ef0cae495ebc6d6e0436e46af02cf9c9240bd17061c5933bfc1faca9edc8202` |
| `scripts/b22b_slippage_harness.py` (pinned, unchanged) | `a0f1b4c434d89fe54edb4f835f7c5401a5dbc2ca023d155fd9aefad1d8b57baf` |
| `scripts/trading_bot/costs.py` (additive change, §4b) | `a8c1c0562b0a1c7136b685a0aa346a404d7872092e4d1f8daa867085be8dbf13` |
| `scripts/trading_bot/t17_orb.py` (unchanged, T17's pin) | `c54b0349a847fa05a68bb1050fe8855a74afd549516c910026181458975907c6` |
| `scripts/trading_bot/t17_run.py` (unchanged, T17's pin) | `62f0818c4481c73bcb8555c4b911c11c35cb5ec553ccc442599366b2dbf2c7ae` |
| `research/trading_bot/T18_EXIT_MEASUREMENT.json` | ABSENT at pin time, asserted in the pinning command |
| `research/trading_bot/T18_RECOST_RESULT.json` | ABSENT at pin time, asserted in the pinning command |

Pinned 2026-08-17T17:57:07+00:00. The reproduction control (§3.6) was run BEFORE this pin and passed: the T18 simulator reproduces T17's published held-out primary Sharpe 1.0882197304.
