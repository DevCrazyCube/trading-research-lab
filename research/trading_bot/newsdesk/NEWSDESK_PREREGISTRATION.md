# NEWSDESK PRE-REGISTRATION — the agent-driven "read-the-world" forward paper logger

**Written and frozen 2026-08-23, before a single forward observation exists.** That timing is the
whole point, and here it is load-bearing in a way it is not even for BASKET1. An LLM agent is the
signal source, and an LLM's backtest is **structurally poisoned by lookahead**: the model was trained
on data through 2026, so on any *historical* date it already "knows" what happened next. A backtest of
an agent's discretionary read is therefore worthless — it measures memory, not skill. The **only**
honest instrument is a **forward-only** one: the agent reads TODAY's news, **commits a falsifiable
trade (sha256 + UTC timestamp) BEFORE the move happens**, and the realised outcome is measured later
against free market prices it could not have seen. This document freezes the rules of that instrument
so the forward log it governs measures a **realised** edge, not a re-fit or a recollection.

This is a **sibling of BASKET1** (`BASKET_FORWARD_PREREGISTRATION.md`), not a new bot. It reuses the
same discipline — pre-registration freeze, append-only forward ledger, per-observation kill switch,
honest-expectancy scoring, and the loud "this is a LOGGER, no orders, no real money" framing. It adds
exactly **one** thing BASKET1 does not have: **part 5 of a discretionary trader's edge — a contextual
read of the world** — supplied by an agent reading live free news/event feeds. Parts 2/3/4
(asymmetric payoff, strict risk sizing, iron discipline) are enforced in code exactly as the programme
already enforces them.

---

## 0. WHAT THIS IS, AND — LOUDLY — WHAT IT IS NOT

This is a **LOGGER**. An agent reads the day's free news, proposes 0–N concrete falsifiable trades,
each is frozen (sha256 + timestamp) the moment it is proposed and appended to a pre-registration log
**before its outcome is known**, and a mark-to-market resolver later marks each frozen setup to
realised free prices at its stop / target / horizon and records the realised R-multiple.

- **NO orders are ever placed** — not live, not paper. There is no broker-auth, no order endpoint, no
  `submit` mode anywhere in the `newsdesk/` package. The only network it touches is a fixed allowlist
  of **free, keyless** public data hosts (SEC EDGAR, Yahoo Finance RSS + chart, Google News RSS,
  CoinGecko) — read-only. No trading host is reachable from this package by construction.
- **NO real money. NO position is ever held. NO account.** Every R-multiple in the log is
  hypothetical-but-honest: "if the frozen setup had been entered at its recorded reference price and
  managed to its frozen stop/target/horizon, this is the R it would have realised."
- **This is a HYPOTHESIS under test, and the honest prior is that it is worth zero.** The hypothesis
  is that *agent-read world context + disciplined asymmetric execution* has positive expectancy. The
  candid prior is the opposite: **public news is priced into liquid instruments within seconds**, so a
  free-feed agent reading a headline is almost always late, and the honest expectancy is **≈ 0, and
  could be negative net of the implicit spread/slippage a real fill would pay.** The forward log is the
  only arbiter. Nothing here is evidence of anything yet.

---

## 1. THE SIGNAL SOURCE — an agent reading the world (part 5), executed by parts 2/3/4

A profitable discretionary trader's edge decomposes as: **(5) a contextual read of the world +
(2) asymmetric payoff + (3) strict risk sizing + (4) iron discipline.** BASKET1 already does 2/3/4
mechanically. The Newsdesk adds 5 and re-imposes 2/3/4 in code:

- **Part 5 (the read):** at run time an agent (an LLM, acting as the "proposer brain") ingests the
  normalized event stream from the world-reader and forms a discretionary, falsifiable view. This is
  the only discretionary component and it is **frozen at proposal time** — the agent never sees the
  outcome, and the outcome is never available on the day of the read.
- **Part 2 (asymmetry), ENFORCED:** every proposal must carry a stop and a target with
  **reward:risk ≥ 2.0**. A proposal missing a stop, or with R:R < 2, is **rejected in code** — it
  never reaches the ledger.
- **Part 3 (risk sizing), ENFORCED:** each setup risks **≤ 1.0% of the (notional) account** to its
  stop; position size is `0.01 · account / |entry − stop|`. Because sizing is fixed, the outcome is
  read directly in **R-multiples** (stop = −1R, target = +≥2R), and the account currency is nominal.
- **Part 4 (discipline), ENFORCED:** at most **N = 5 concurrent open setups**; the proposer is
  explicitly allowed — and expected — to return **"no trade today"** (not trading is the skill), and
  that abstention is itself logged. Once frozen, a setup's stop/target/horizon are immutable; there is
  no code path that moves a live setup's rule (an improvement is a NEW frozen instrument, per §7).

---

## 2. THE LOOKAHEAD-PROOF FORWARD-ONLY DESIGN (the assertion that makes this honest)

The one failure this instrument exists to defeat is an LLM "predicting" a past it was trained on.
Enforced, not promised:

1. **Freeze precedes outcome.** The moment the agent proposes a setup, the full spec — instrument,
   direction, entry reference price captured *now*, stop, target, horizon, thesis, confidence, and the
   ids of the events that triggered it — is canonically serialised and **sha256-hashed with a UTC
   `proposed_utc` timestamp**, then appended to `NEWSDESK_PREREGISTRATION_LOG.jsonl` **before** any
   resolution. The hash is what makes the commitment tamper-evident.
2. **Resolution reads only the strictly-later path.** The mark-to-market resolver uses **only price
   bars whose timestamp is strictly greater than `proposed_utc`.** A bar at or before the freeze is
   discarded and asserted against (`_assert_forward`): a setup that could be scored on a bar it saw at
   freeze is the exact failure this instrument exists to prevent, and it refuses.
3. **No backtesting the agent, ever.** There is **no** code path that runs the proposer on a
   historical date. The agent is only ever pointed at *live* feeds. A "proof" mode exists for wiring
   only (synthetic events, synthetic prices) and never writes the ledger.
4. **Entry at the reference captured at freeze.** v1 enters at the reference price recorded at freeze
   (the live price at read time). It is a real, contemporaneous price; the realised path that scores it
   is strictly later; there is no window in which the future is visible.

---

## 3. THE FREE SOURCES (all verified 200 OK, keyless, from this environment)

The world-reader pulls only these hosts, on a fixed allowlist; any other host refuses:

| source | endpoint | what it gives |
|---|---|---|
| SEC EDGAR latest filings | `www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&output=atom` | 8-K material-event filings, near-real-time |
| SEC EDGAR full-text search | `efts.sec.gov/LATEST/search-index?q=…` | filing full-text search (optional deepen) |
| Yahoo Finance headline RSS | `feeds.finance.yahoo.com/rss/2.0/headline?s=TICKER` | per-ticker headline stream |
| Google News RSS | `news.google.com/rss/search?q=…` | keyword news search |
| CoinGecko trending | `api.coingecko.com/api/v3/search/trending` | trending crypto assets |
| Yahoo Finance chart | `query1.finance.yahoo.com/v8/finance/chart/TICKER` | free OHLC for equity/ETF resolution |
| CoinGecko market chart | `api.coingecko.com/api/v3/coins/{id}/market_chart/range` | free crypto price path for resolution |

Instruments are restricted to **liquid, free-priceable symbols**: US equities/ETFs (priced on Yahoo
chart) and major crypto (priced on CoinGecko). Nothing else may be proposed.

---

## 4. HONEST SCORING (mirror of `basket_eval`)

After each **resolved** setup (stop, target, or horizon reached), the evaluator computes, over the
stream of realised R-multiples `{R_i}`:

- **win-rate** = fraction with `R_i > 0`; **loss-rate** = 1 − win-rate;
- **avg-win R** = mean of the positive `R_i`; **avg-loss R** = mean of `|R_i|` over the non-positive;
- **EXPECTANCY** = `winrate · avgWinR − lossrate · avgLossR` — the real metric, in R per setup. A
  high win-rate with a negative expectancy is a losing system; expectancy is the number that counts.

Two pre-registered benchmarks:

1. **Zero.** Expectancy must clear 0 (a coin-flip on a 2:1 asymmetric bet has expectancy
   `0.5·2 − 0.5·1 = +0.5R` *only if entries are random-good*; a real edge must beat the null below).
2. **Random-direction null.** For each setup, a deterministic coin (seeded from the setup's own
   sha256) picks a direction and the **same instrument, same risk distance, same R:R, same horizon**
   are re-resolved over the **same** realised price path. The agent's expectancy must beat this
   same-instrument random-entry null — otherwise the "read" added nothing over the asymmetry mechanics.

All early numbers travel inside an `inputs_that_are_not_results` block with the reason they are not
evidence, exactly as BASKET1 does.

---

## 5. THE KILL SWITCH — frozen before any datum

A setup accrues one realised R-multiple. Let `n` be the resolved count, `mean` the sample mean R,
`se = sd/√n`.

> **The Newsdesk is HALTED when, after `n ≥ N_min = 30` resolved setups, the one-sided upper 95%
> confidence bound on the mean R is below zero: `mean + 1.645·se < 0`.**

That fires only when the instrument is **significantly negative** (per-setup t < −1.645) — it will not
prematurely halt a true-but-noisy positive, and it will catch an instrument that is genuinely losing.
On a HALT the instrument is closed (the ledger is never deleted); resuming is a NEW frozen instrument,
never an edit to this one. No pass verdict is licensed before `n ≥ N_min`.

---

## 6. THE RISK / ASYMMETRY RULES — enforced in code, immutable once frozen

| rule | value | enforced by |
|---|---|---|
| minimum reward : risk | **2.0** | proposer rejects R:R < 2.0 |
| stop required | **mandatory** | proposer rejects a missing/degenerate stop |
| account risk per setup | **≤ 1.0%** | proposer rejects > 1.0%; size = 0.01·acct/|entry−stop| |
| max concurrent open setups | **5** | proposer refuses to freeze a 6th while 5 are open |
| direction consistency | long: stop<entry<target; short: target<entry<stop | proposer rejects violations |
| horizon | **1 h – 240 h** (hours to days) | proposer rejects out-of-range horizons |
| adverse tie-break | if one bar spans both stop & target → **assume STOP first** | resolver (pessimistic) |
| instruments | liquid US equity/ETF or major crypto only | proposer rejects unknown/illiquid symbols |

---

## 7. WHAT MAY AND MAY NOT CHANGE (ITERATION_PROTOCOL, restated)

- **Immutable:** the R:R floor, the 1% risk cap, the concurrency cap, the horizon bounds, the source
  allowlist, the kill thresholds, the minimum sample, the scoring definition, the forward-only
  assertion. Changing any is a **NEW** frozen instrument with a new pre-registration.
- **Maintenance (allowed, logged):** fixing a crash/retry/timeout, a feed URL the vendor itself moved,
  adding a read-only metric to the evaluator, extending the equity watchlist the world-reader *scans*
  (this widens the eyes, not the rules; a proposal is still bound by every §6 rule).
- **Forbidden:** editing a frozen setup's stop/target/horizon, backtesting the proposer on a historical
  date, resolving a setup on a bar at or before its freeze, restarting/truncating the ledger, reading
  the expectancy verdict before `N_min`, promoting anything to real money (owner-gated; this logger
  places no orders and cannot promote itself).

---

## 8. CLAIMS THIS LOG MAY NEVER SUPPORT

- that the Newsdesk, or any setup, makes money;
- that agent-read context has positive expectancy, before §5's minimum is met;
- any expectancy, win-rate or R statistic computed before the minimum, outside an explicit
  `inputs_that_are_not_results` block;
- that a good early streak is evidence about the edge;
- that this paper log is a reason to fund a live account. **Live execution is owner-gated, and this
  instrument is a logger that places no orders — it cannot promote itself.**

---

## 9. THE HONEST EXPECTATION, IN ONE PARAGRAPH

The efficient-market prior is brutal and correct: by the time a free feed surfaces a headline, a
liquid instrument has already moved, so the naive expectancy of "trade the news" is **≈ 0 before
costs and negative after the spread a real fill would cross.** The bet is that an agent's *contextual*
read — recognising which of the day's events is mispriced *relative to* the disciplined 2:1
asymmetric structure it must be expressed through, and abstaining on the rest — carries a small,
survivable positive. That is a hypothesis, not a belief. This log exists to find out, at the cost of
zero dollars and zero orders, and the honest base case is that it halts on the kill switch.

---

*Frozen instrument. No orders, no real money, no accounts, no purchases, no git commit by the logger;
free/keyless data only, on a fixed host allowlist. The agent is never backtested. Every proposal is a
falsifiable forward commitment; the realised R-multiple is the only evidence, and it is not yet
evidence of anything.*
