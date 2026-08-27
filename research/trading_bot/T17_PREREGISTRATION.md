# T17 — PRE-REGISTRATION: the ORB multi-position day-trading strategy, run through the honest harness

**Status: FROZEN 2026-08-17. Hashed before any T17 profit-and-loss number existed.**

At the moment the hashes below were taken, `research/trading_bot/T17_DESIGN_RESULT.json`,
`research/trading_bot/T17_HELDOUT_RESULT.json` and `research/trading_bot/T17_POSTPAPER_RESULT.json`
**did not exist**, and the command that recorded the hashes asserted their absence in the same
invocation.

---

## 1. The question, in one sentence

Zarattini, Barbon & Aziz (2024, SSRN 4729284) report an annualised **Sharpe of 2.81** for an
opening-range breakout traded on the top 20 US stocks by opening relative volume, modelling
**only** a $0.0035/share commission — the strings `slippage`, `bid-ask`, `market impact`,
`capacity` and `fill` occur **zero** times in their paper. T5/B22B measured the quantity they
omitted. **This document runs the whole strategy with that measurement in it.**

This is not another slippage measurement. It is the strategy.

---

## 2. What is frozen, and at what hash

| artifact | role | sha256 |
|---|---|---|
| `scripts/trading_bot/t17_orb.py` | **the rule.** Selection, entry, stop, exit, sizing, gross cap, empirical slippage draw | `c54b0349a847fa05a68bb1050fe8855a74afd549516c910026181458975907c6` |
| `scripts/trading_bot/t17_run.py` | the driver: cost application, the six declared configurations, permutation, DSR, gates | `62f0818c4481c73bcb8555c4b911c11c35cb5ec553ccc442599366b2dbf2c7ae` |
| `scripts/trading_bot/t17_screen.py` | the point-in-time universe screen | `ce1c935f54da9e7922adddd0280af30d4659a273bfd542b404d29f16af08ad2c` |
| `scripts/trading_bot/t17_select.py` | relative volume and the top-20 selection | `5e8ac16cbde51c912ebce30a1ad61e4af4b2bd8c388e407a6d6441377c3a8ac7` |

**Amendment, 2026-08-17, made BEFORE any T17 PnL existed and recorded rather than hidden.**
Two defects were found while the data was still being collected and both were fixed and
re-hashed with no result in existence: (i) `t17_run.py`'s trial-count assertion was written
`a != b != c`, which Python reads as `(a != b) and (b != c)` and which with two equal
constants is always False — an assertion that could never fire; (ii) `t17_select.py` held
every session's opening bars in memory at once (~3 GB) and now keeps only a rolling
15-session window. Superseded hashes: `t17_run.py`
`6a877aaeace801060f649035c3ba43c97001c78d9d167bb3c5529bc4b20b8ef9`, `t17_select.py`
`c0a673c46876324610006cd8813610bb459dd5736be56dc5232c8f76e5ea8cd9`. Neither edit touches the
rule, the windows, the gates or the cost model.
| `scripts/trading_bot/t17_collect.py` | data collection only; contains no decision | `a71e6a288a7f56c1b27df247c4a6e5ea9aba96fb0f0c0b7fcab8573348eeb7c3` |
| `research/trading_bot/T17_POWER_GATE.md` | the power thresholds, hashed before the census | `03d257ce8ff6c92c09b0be4c896dacc6a424c8925d96a805e2fc25a80fec6465` |
| `research/trading_bot/T17_SLIPPAGE_EMPIRICAL.json` | the 429 per-observation B22B slippage measurements, extracted from the run's own checkpoints | `0bec0d806e60b89c62262b2a2cea5bbe3946d72a2c5f34218dc9770e0f32fa92` |
| `scripts/b22b_slippage_harness.py` | the pinned B22B arithmetic, **consumed not copied** | `a0f1b4c434d89fe54edb4f835f7c5401a5dbc2ca023d155fd9aefad1d8b57baf` (unchanged) |

---

## 3. The rule under test

1. **Universe (point in time).** open(d) ≥ $5 · mean share volume over the 14 sessions before
   d ≥ 1,000,000 · ATR(14) over the 14 true ranges ending at d−1 ≥ $0.50. Raw (unadjusted)
   prices, because an adjusted price level is retroactive.
2. **Opening range** [09:30, 09:35) ET, per-day DST via the pinned `et_offset_hours`.
   Direction: bullish candle ⇒ long only, bearish ⇒ short only, **doji ⇒ no trade**.
3. **Stocks in Play.** Opening-5-minute volume ≥ 100 % of the same stock's own average
   opening-5-minute volume over the previous 14 sessions (≥ 10 observations required, fewer
   is a refusal not a 100 %), then the **top 20** by that ratio.
4. **Entry** on a stop at the opening-range high (long) / low (short), from 09:35.
5. **Stop loss** R = 10 % of ATR(14) from the entry FILL. **Exit** at the close otherwise.
6. **Sizing** 1 % of equity risked per position, gross exposure capped at **4×** equity,
   pro-rata across the basket (see §5b).

### 3a. One deliberate correction to the B22B runner
`atr_micros` was called there with a bar list **including day d**, so its 14 true ranges used
day d's own high, low and close — none of which is known at 09:35. T17 computes ATR(14)
strictly from bars before d. The frozen function is unchanged; only what is handed to it is.

---

## 4. Friction: what is charged and on whose authority

**The paper's zero is not used anywhere.** Three modes:

| mode | entry | exit | provenance |
|---|---|---|---|
| **MEAN** | 1.5452 bp of notional | 2.5 bp half-spread + 1.5452 bp | `MEASURED_B22B` / `ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG` |
| **EMPIRICAL** | a draw from the 425 decontaminated B22B observations, in **bp of R**, applied to the FILL PRICE | an independent draw from the same distribution, plus the 2.5 bp exit half-spread | same |
| **ZERO** | 0 | 0 | `STRESS_LADDER` — **diagnostic only**, per B19P. Never a trading assumption. |

T6 round trip = **5.59 bp of notional**. The empirical mode exists because a mean cannot
carry a fat tail into a drawdown, and B22B's tail is the whole point: p90 **1,181 bp of R**,
p95 **1,654 bp of R**, max **3,616 bp of R**, against the **800 bp of R** the paper reports as
its entire per-trade edge.

**Borrow is not charged** — every position closes the same session and US equity borrow
accrues overnight. The short leg's real constraint is *availability*, handled in §6.

---

## 5. Modelling choices where the paper is silent. Each is stated with its direction of bias.

**a. Entry-bar stop granularity — the one place "assume the worst" is wrong.** R is ≈ 0.5 %
of price here, and a one-minute bar in a top-relative-volume name routinely spans that. Using
the entry bar's whole low would stop out a large share of trades at −1R using price action
that occurred *before the position existed*. Frozen rule: on the entry bar only, the stop is
hit iff the bar **closes** beyond it; from the next bar the low/high is used. The maximally
adverse `full_bar` reading is reported as a labelled sensitivity, never as the headline.

**b. The 4× gross cap binds every day, and pro-rata is the strategy-FAVOURABLE reading.**
Risking 1 % of equity over a stop 0.5 % away is ≈ 2× equity of notional **per position**;
twenty of them is ≈ 40×. Frozen rule: scale the whole basket to 4× (all twenty names held,
≈ 0.1 % risk each). Rank-order truncation — which leaves about *two* names a day — is
declared configuration #6. Sharpe is invariant to a uniform leverage scale, so this choice
moves the answer only through diversification, and the default gives the strategy the most.

**c. Gap-through fills.** A stop order cannot fill better than the market: if the triggering
bar opens beyond the level, the fill is the open. Adverse.

**d. Survivorship.** The symbol master is Alpaca's `/v2/assets` with **status=inactive
included** (14,794 tickers on NASDAQ/NYSE/ARCA/BATS/AMEX). Mitigated, not cured: a symbol
Alpaca has dropped entirely is invisible.

**e. Splits in the raw daily series.** Raw prices are required for the level filters, so a
split leaves a jump in the ATR window for up to 14 sessions. That *widens* R, which shrinks
the position and widens the stop. It does not manufacture profit.

---

## 6. The design / held-out split, declared before either was run

| window | dates | role |
|---|---|---|
| **design** | 2016-01-26 → 2021-12-31 | implementation, and the six trial Sharpes that feed DSR's cross-trial variance |
| **held out** | 2022-01-03 → 2026-08-14 | **run ONCE.** The driver writes a sentinel and refuses a second run. |
| **post-paper** | 2024-01-02 → 2026-08-14 | secondary, entirely after the paper's own 2016–2023 study period |

**The six declared trials** (fixed here; the driver asserts the count at run time):
`mean/zero_diagnostic`, `mean/T6_measured`, `mean/T6_plus_paper_commission`,
`empirical/T6_measured`, `empirical/T6_plus_paper_commission`,
`empirical/T6_measured/truncate`.

**Primary configuration: `empirical/T6_measured`** — the measured slippage distribution with
its tail, the T6 per-side cost model, zero commission (the current retail schedule), pro-rata
sizing. All three gates are read off this one.

---

## 7. The gates. Frozen. A verdict of SURVIVES requires all three.

| gate | threshold |
|---|---|
| **G-net** | mean daily net return of the primary configuration **> 0** |
| **G-perm** | permutation **p < 0.05** |
| **G-DSR** | deflated Sharpe **≥ 0.95** at 6 declared trials |

**The permutation null, stated precisely.** *The colour of the first five-minute candle does
not say which side breaks profitably.* Each of 2,000 permutations keeps the same stock-days,
the same opening-range levels, the same R, the same sizing, the same intraday paths and the
same slippage draws, and redraws only each position's direction from a fair coin. Because
both directions of every stock-day are simulated and cached up front, the permutation is
exact rather than a re-simulation carrying its own new randomness.

**Post-hoc sensitivities, labelled as such and never gates:** `full_bar` entry-bar stop rule;
long-only and short-only legs (the short leg's availability bound — B22G found 8 of the 52
names B22B screened are hard-to-borrow and not shortable at Alpaca, and point-in-time
shortability is not obtainable, so the truth lies between long-only and the primary); and the
p90 / p95 adverse slippage rungs charged to *every* trade.

---

## 8. Single use

This document authorises **one** evaluation pass over the held-out window. Re-running with a
different top-N, a different filter, a different latency rung, a different entry-bar rule or a
different split is a new document with a new hash. If the held-out result is negative it is
reported as negative.
