# T18 — the ORB exit leg, measured at tick level. The knife-edge collapses, and not upward.

**VERDICT: ORB is DEAD, and the −8.36-to-+1.09 spread that T17 left open is now a measured
number.** On the T17 held-out selection, re-priced with a tick-measured exit leg and a
tick-measured entry-bar stop rule, the commission-free (Alpaca-realistic) held-out Sharpe is
**−1.078**, annualised return **−19.9 %**, max drawdown **75.3 %**, deflated Sharpe **0.0000**
against a 0.95 gate. The one number that settles it without any simulation at all: on the 712
decontaminated stock-days measured tick by tick, entry fill to exit fill, **the average ORB
trade loses 0.479 R** (t = **−4.71**, clustered by session). T17's simulation said +0.073 R.

**And the reason is not the exit.** The exit leg, measured, is *cheaper* than the adverse proxy
T17 charged — correcting it alone lifts the held-out Sharpe from 1.088 to **+2.857**. What kills
the strategy is the quantity T17 flagged as unresolvable from one-minute bars: **on the entry
bar, when the bar spans the stop but closes clear of it, the stop really did trade through
48.7 % of the time** (154 of 316, tick by tick). T17's frozen rule assumed 0 %. Putting the
measured 48.7 % in takes +2.857 to −1.078.

**The most uncomfortable number in this document is not about the exit at all.** The B22B entry
slippage T17 charged was measured on a 2025 **most-actives** pool. Re-measured on the stock-days
this strategy actually selects, the entry costs **2,402 bp of R against B22B's 273** — 8.8× —
because the top-20-by-relative-volume screen selects names whose **quoted spread is 16.4 bp of
price against an R of 34.2 bp**. *The bid-ask spread of the names ORB trades is roughly half of
its entire risk unit.* Charging that as well takes the held-out Sharpe to **−3.921**.

---

## 0. Provenance

| | |
|---|---|
| pre-registration, frozen before any held-out T18 number | `T18_PREREGISTRATION.md` / `.json` |
| the measurement | `scripts/trading_bot/t18_exit_ticks.py` `4973e7619ccf438d56cec2772896e54f7085f949849eae438862741b5946ebdf` |
| the re-cost | `scripts/trading_bot/t18_recost.py` `8ef0cae495ebc6d6e0436e46af02cf9c9240bd17061c5933bfc1faca9edc8202` |
| the pinned B22B harness — **imported, hash-asserted, never edited** | `a0f1b4c434d89fe54edb4f835f7c5401a5dbc2ca023d155fd9aefad1d8b57baf` |
| the T17 rule and driver — **unchanged**, hashes as published | `c54b0349…`, `62f0818c…` |
| raw records, 50 session files | `research/data/t18_cache/heldout_*.json` |
| measurement result | `T18_EXIT_MEASUREMENT.json` |
| re-cost result | `T18_RECOST_RESULT.json` |
| post-hoc sensitivity curve | `T18_SENSITIVITY_POSTHOC.json` |
| data | Alpaca **SIP** trades, quotes (NBBO) and auctions; T17's own cached 1-minute raw bars |

**The reproduction control passed before anything was corrected.** The T18 simulator, run with
T17's own settings, reproduces T17's published held-out primary Sharpe to ten decimal places:
`1.0882197304` against `1.0882197303767718`. Every number below is a change from that baseline
and nothing else.

**Sample.** 50 sessions drawn with seed `20260818`, stratified by calendar year (2022–2025 × 11,
2026 × 6), **every** one of T17's top-20 selections on each: **1,000 stock-days**, 4.32 % of the
held-out window's 23,160. Outcomes: 760 stopped, 70 held to the close, 169 never triggered, 1
refused. Against B22B's 429 entry observations this is the larger measurement, and it is on the
right universe.

---

## 1. The exit stop leg — the number nobody had

A stop-loss market order, priced from the first SIP print at or through the stop level after the
entry filled, to the prevailing NBBO bid (long) / ask (short) at that instant + 100 ms.

| exit slippage, 100 ms rung | n | p50 | p90 | p95 | mean | adverse / favourable |
|---|---|---|---|---|---|---|
| **bp of R, decontaminated** — *charged* | 645 | **1,484** | 8,009 | 13,275 | **1,243** | 517 / 127 |
| bp of R, unfiltered | 760 | 1,265 | 9,058 | 14,731 | 354 | 557 / 202 |
| centi-bp of notional, decontaminated | 645 | 509 | 3,145 | 5,030 | **332** | — |

**In the strategy's own unit the measured stop exit costs a mean of 0.124 R and a median of
0.148 R.** The paper's reported per-trade edge at its own filter is 0.08 R. **One leg of the
round trip, measured, is larger than the entire advertised edge.**

The decontamination rule was frozen in advance and it bit in the direction the pre-registration
anticipated: the unfiltered mean (354 bp) is *lower* than the decontaminated one (1,243 bp),
because dislocated prints through the stop produce enormous spurious *favourable* readings. The
frozen rule — charge whichever pool has the more adverse mean — selects the decontaminated pool,
and the result file records both.

Two context numbers from the same measurement, both new:

| | |
|---|---|
| quoted spread at the stop trigger | median **18.9 bp** of notional, mean 34.7 bp |
| size resting at the touched side | median **3 shares**, p90 200 |

T6 priced this leg at a 2.5 bp half-spread from the retail-taker literature. **The market this
rule actually stops out into quotes 18.9 bp wide at the median.**

**Latency does not rescue it and speed barely matters** — 0 ms 803, 100 ms 1,243, 500 ms 1,167,
1,000 ms 1,310 bp of R. The cost is the spread and the move, not the wire.

---

## 2. The MOC leg — very nearly free, and T17 overcharged it

For every triggered stock-day (not merely the ones that survived to the close — conditioning the
exit cost on the trade having been a winner would be a selection this programme does not make):
the official closing print against the last-1-minute-bar mark the backtest credits.

| | |
|---|---|
| official closing print exists | **828 of 830 = 99.76 %** |
| deviation, print vs the backtest's mark | **median 0 bp of R**; decontaminated mean **+3.7 bp of R** (0.0004 R) |
| the same in notional | mean **−0.87 bp**, i.e. slightly *favourable* |
| median print size | **$9.4 M** |
| the 2 stock-days with no print, unwound at the closing NBBO | mean **3,926 bp of R** (0.39 R) |

**The end-of-day exit is essentially costless and T17 charged it 4.05 bp of notional.** The
reason is mundane and worth recording: Alpaca's 16:00 minute bar *contains the closing cross*,
so the mark the backtest used already is the auction print. M0 predicted exactly this — a
backtest that marks at the print and executes at the print has no friction to pay — and this is
the first time the programme has measured it on a rule that actually exits MOC.

---

## 3. The entry-bar tie-break — resolved, and it is the thing that kills ORB

The disputed set is the stock-days where the entry bar's low/high spans the stop but its close
does not: `full_bar` calls them stop-outs, T17's frozen `close` rule calls them survivors.

| reading of the entry minute | count, of 830 triggered |
|---|---|
| `full_bar` says the stop was hit | 442 |
| `close` says the stop was hit (T17's frozen rule) | 126 |
| **ticks say the stop was hit** | **345** |
| **the disputed set** | **316** |
| **…of which the ticks say really traded through, after the entry filled** | **154 → P = 0.4873** |
| Wilson 95 % upper bound | 0.5423 |
| the same, additionally requiring the NBBO to confirm the print | 95 → P = 0.3006 |
| both rules say hit → ticks agree | 122 of 126 (96.8 %) |
| neither rule says hit → ticks say hit anyway | 69 of 388 (17.8 %) |
| median time from entry fill to stop trigger | **38.9 s** |

**The truth is not at either end. It is at 0.487, almost exactly halfway**, and T17's frozen
choice sat at the favourable end of a range it knew it could not resolve. The last row is worth
its own sentence: on 69 stock-days a trade printed through the stop inside a bar whose own
low/high never reached it — odd-lot and out-of-sequence prints that a minute bar does not carry.
That is why the quote-confirmed variant (0.3006) is reported beside the headline; the sensitivity
curve in §6 spans both.

---

## 4. The entry leg, re-measured on the names this rule actually trades

This was pre-registered as a **consistency check**: if T18's entry number disagreed with B22B,
the two measurements are not measuring the same thing. They disagree, badly.

| entry slippage, 100 ms, decontaminated | n | p50 | p90 | mean |
|---|---|---|---|---|
| **B22B — 2025 most-actives pool, what T17 charged** | 425 | **1** | 1,181 | **273** bp of R |
| **T18 — T17's own selected stock-days** | 810 | **1,230** | 6,556 | **2,402** bp of R |

**8.8× on the mean, and three orders of magnitude on the median.** The mechanism is not subtle:

| | median, on T17's selected stock-days |
|---|---|
| quoted spread at the entry trigger | **16.4 bp of price** |
| R — the whole risk unit, 10 % of ATR(14) | **34.2 bp of price** |

**The round-trip quoted spread of the names this screen selects is ~48 % of its risk unit.** The
top-20-by-*relative*-volume filter is, by construction, a filter for names trading far above
their own normal volume — which is not the same thing as names that are liquid, and B22B's
most-actives pool was the second thing. T17 said its verdict rode on the exit; it also rode on
this transfer, and this is the larger of the two errors.

---

## 5. The corrected held-out result

1,158 sessions, 2022-01-03 → 2026-08-14, commission-free (Alpaca-realistic) unless stated.
Eight configurations, all declared in the pre-registration before any of these numbers existed.

| configuration | Sharpe | ann. return | max DD | t | DSR (12 trials) | PSR (1 trial) |
|---|---|---|---|---|---|---|
| **`t18/measured_exit/R` — PRIMARY** | **−1.078** | **−19.9 %** | **75.3 %** | **−2.31** | **0.0000** | 0.0153 |
| `…/entry_bar_close` — *the exit correction alone* | **+2.857** | +83.3 % | 11.3 % | +6.12 | 0.0000 | 1.0000 |
| `…/entry_bar_full_bar` | −6.193 | −61.9 % | 98.8 % | −13.28 | 0.0000 | 0.0000 |
| `…/plus_exit_half_spread` — conservative bound | −4.145 | −55.5 % | 97.9 % | −8.88 | 0.0000 | 0.0000 |
| `…/paper_commission` ($0.0035/share) | −1.903 | −31.5 % | 86.6 % | −4.08 | 0.0000 | 0.0001 |
| `…/tie_break_upper_ci` (P = 0.542) | −1.654 | −27.9 % | 84.4 % | −3.55 | 0.0000 | 0.0007 |
| `t18/measured_exit/notional` — the other transfer | −1.074 | −19.5 % | 74.7 % | −2.30 | 0.0000 | 0.0159 |
| `t18/measured_entry_and_exit/R` — declared diagnostic | **−3.921** | −49.4 % | 96.2 % | −8.41 | 0.0000 | 0.0000 |
| *for reference: T17's published primary* | *+1.088* | *+24.1 %* | *27.9 %* | *+2.33* | *0.2945* | *0.9931* |

**The gates, as frozen by T17 and re-applied unchanged:**

| gate | result | |
|---|---|---|
| net mean daily return > 0 | **−0.0812 %/day** | **FAIL** |
| permutation p < 0.05 | p = 0.0125 (24 of 2,000) | PASS |
| deflated Sharpe ≥ 0.95, 12 cumulative trials | 0.0000 | **FAIL** |

**Verdict: DEAD.**

**The permutation still passes, and that is the honest epitaph for this candidate.** Only 24 of
2,000 direction-randomised runs beat the real direction — the opening candle's colour *does*
predict which side breaks, exactly as T17 found. The strategy is not noise. It is a real signal
whose realised friction is larger than itself.

**Two corrections, opposite signs, and the report of one without the other would have been a
lie in either direction.** The exit is cheaper than T17 assumed (+1.77 Sharpe on its own); the
entry-bar timing is far worse (−3.94 from there). Anyone reading only §1–2 would have concluded
ORB was rescued.

### Where the money goes now, per trade, in R

| | T17 (published) | T18 (primary) |
|---|---|---|
| mean net R per trade | **+0.073** | **−0.081** |
| price slippage charged | 0.054 R | 0.136 R |
| notional charge (exit half-spread) | 0.079 R | 0 (inside the measured fill) |
| share of trades stopped out | 85.6 % | 87.9 % |
| net win rate | 13.9 % | 15.8 % |
| median trade | −1.10 R | −1.11 R |

---

## 6. POST HOC — the sensitivity curve on the one number that decides it

Not pre-registered. Reported because the tie-break rate is the load-bearing input and a reader
is entitled to the whole curve rather than the one point.

SWEEP_TABLE

The whole verdict turns on a rate between 0.15 and 0.30. **The measured rate is 0.487, its
quote-confirmed variant is 0.301, and its 95 % lower bound is above 0.43.** There is no
defensible reading of the tick data that puts it below 0.30, and at 0.30 the strategy is already
under water on the primary configuration.

---

## 7. The check that makes the transfer honest: simulation versus tick truth

The re-cost transfers a measured distribution onto 18,847 simulated trades. On the 704 stock-days
that were *also* measured directly, the two can be compared per trade, in R.

| | mean net R per trade | stopped share |
|---|---|---|
| **TICK TRUTH — entry fill to exit fill, both measured** | **−0.479** | **90.6 %** |
| `t18/measured_entry_and_exit/R` | −0.292 | 88.5 % |
| `…/entry_bar_full_bar` | −0.324 | 88.5 % |
| `…/plus_exit_half_spread` | −0.221 | 85.8 % |
| **PRIMARY `t18/measured_exit/R`** | **−0.109** | 85.8 % |
| `…/entry_bar_close` | +0.115 | 83.9 % |

**Every simulated configuration — including the ones this document calls conservative — is
kinder than the ticks.** The corrected held-out Sharpe of −1.078 is therefore an *optimistic*
transfer, and the direct measurement is the more adverse and the more direct evidence:

> **712 decontaminated stock-days, measured end to end, mean −0.479 R per trade, session-clustered
> t = −4.71, win rate 13.6 %.** Stopped trades average −1.124 R; the 67 that reach the close
> average +5.73 R and do not pay for the rest.

The gap between the simulation and the truth has a known cause and it is worth stating because it
constrains every future rig here: the measured slippage is drawn onto simulated stop events by a
keyed draw, so an expensive fill and a violent day are decoupled. In reality they are the same
event. A per-trade cost distribution sampled independently of the path will always be too kind.

---

## 8. What this establishes, and what it does not

**Established.**

1. **The exit leg is measured.** A stop-loss market exit costs a mean **0.124 R** (median
   0.148 R, p90 0.80 R) into a market quoting 18.9 bp wide with 3 shares at the touch. The MOC
   exit is **free to four decimal places** and the `ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG` label
   can come off `costs.py` for this rule — replaced, not merely relabelled.
2. **The entry-bar tie-break is resolved: 0.4873 (154/316), not 0 and not 1.** The
   −8.36-to-+1.09 spread was real and its resolution lands at **−1.078**.
3. **ORB is dead at the friction floor, not at the signal.** Permutation p = 0.0125 with a
   negative mean: the direction call is genuinely informative and is worth less than the spread.
4. **The cost transfer, not the exit, was T17's largest error.** Entry slippage measured on the
   traded names is 8.8× the pool T17 borrowed. Any future candidate in this programme that
   borrows a friction distribution from a different universe inherits this failure.
5. **A one-minute bar cannot price a rule whose stop is 0.32 % of price.** The same rule read
   three ways off the same bars spans 9 Sharpe points. This is a constraint on the *harness*, not
   only on ORB.

**Not established.**

- **Capacity.** The measurement prices a fill; it never asks whether size fills. A median of
  **3 shares** at the touched side, in a rule that puts ~20 % of equity into a name at 4× gross,
  says the true capacity question was never even reached — and that it points the same way.
- **50 sessions are not 1,158.** The measurement is 4.32 % of the held-out stock-days; the
  re-cost transfers it. §7 is the check on that transfer and it says the transfer flatters.
- **Our order joining the closing cross** (M0's C4) still needs live orders. Nothing here
  changes that, and nothing here needed it: the MOC leg is not what killed this.
- **Point-in-time shortability** (B22G) remains unobtainable, so the short leg is a bound.
- **The 2 no-print stock-days** are 0.24 % of the sample and cost 0.39 R each. On a universe
  reaching further down the liquidity ladder that rate is M0's tier E/F problem, not this one's.

---

## 9. Recommendation to the owner

**Bury it.** Not "it failed a gate" — the reasons are structural and each one is measured:

1. The realised per-trade edge is **negative** end-to-end on tick data, at t = −4.7.
2. The mechanism is the universe, not the execution: this screen selects names whose quoted
   spread is **half its risk unit**. No smarter order type recovers that; a limit order that does
   not cross forfeits the breakout it is trying to catch.
3. Both remaining unknowns (capacity, shortability) point the same way.

**Do not paper-trade it.** T17's option 3 was already premature; with a measured negative
per-trade edge it would spend weeks confirming a number that took 50 sessions of tape to
establish.

**What to carry forward instead** — three transferable findings, each cheap and each aimed at
the failure mode that actually bit here:

- **Measure friction on the universe you will trade, never on a proxy universe.** The 8.8× is
  the single most valuable number in this document.
- **A candidate whose risk unit is close to the spread of its own universe is dead on arrival.**
  `R / quoted spread` is a one-line screen and would have killed ORB before the harness ran.
  On this rule it is 34.2 bp / 16.4 bp ≈ **2.1**; a rule needs that ratio to be *large*.
- **Bar-granularity ambiguity is a stop condition, not a caveat.** Where a rule's stop is
  smaller than a bar's typical range, the backtest cannot answer the question and the tick
  measurement must come first — before the held-out window is spent, not after.

**Guardrails.** `scripts/b22b_slippage_harness.py` was imported and hash-asserted, never edited.
The measurement method was frozen and hashed — with both result files asserted absent in the same
command — before any held-out PnL existed, and the reproduction control was run and passed before
that pin. The T6 per-side model is used unchanged for everything except the newly-measured exit,
and the change to `costs.py` is additive (new provenance + reader; `b22b_measured_costs()`
untouched; 113/113 harness tests still pass). Market data only, no orders of any kind, nothing
committed.
