# B22A — the equity day-trading pivot: what transfers, and the one unexamined hole

**Why this exists.** The owner directed a switch from Solana memecoins to US equities, day trading
specifically. This records what the external evidence actually says, what carries over from this
programme's findings, and the single measurement that decides whether the best published candidate
is real.

**Status.** External-literature review. **No claim here is our own result.** Nothing has been
measured by us. The arithmetic in §4 is an *estimate that motivates a test*, not a finding.

---

## 1. The base rates, which are worse than the memecoin venue in one specific way

| finding | source | n |
|---|---|---|
| ~80% of day traders lose money net of fees | Barber, Lee, Liu & Odean, Taiwan 1992–2006 | all day traders in a national market |
| **<1%** predictably earn positive abnormal returns net of fees | same, cross-section of speculator skill | — |
| heaviest traders earned 11.4% vs market 17.9% — 6.5pp/yr drag from trading alone | Barber & Odean, *Trading is Hazardous to Your Wealth* | 66,465 households |
| 74–97% retail day-trader loss rates | Brazil (Chague & De-Losso), Taiwan, ESMA | multiple jurisdictions |
| 92% of US funds underperformed benchmark over 20 years | SPIVA | — |
| **0 of 22** US equity categories had a majority of active managers beat benchmark over 15 years | SPIVA | — |

**The one genuinely encouraging number in this table:** the top-500 day traders in Taiwan earned
**+37.9 bps/day net of fees**, against the bottom's −28.9 bps — a spread exceeding 70 bps/day, and it
**persisted year to year**. Skill is real, measurable, and rare. That is a different world from the
memecoin venue, where we established the game is negative-sum by construction and no skill tier was
identifiable.

## 2. What structurally changed in 2026 — the PDT rule is gone

The SEC approved elimination of the $25,000 pattern-day-trader minimum on **14 April 2026**; FINRA
Regulatory Notice 26-10 set the effective date at **4 June 2026**. The PDT designation and the
$25,000 floor no longer exist, replaced by a risk-based intraday margin standard tied to real-time
margin excess. **Brokers have until 20 October 2027 to implement**, so per-broker behaviour during
the transition must be checked rather than assumed.

*Relevance: the capital floor that made this strategy class inaccessible below $25k is gone. This is
a real change in what is buildable, and it is why the question is live now and was not in 2024.*

## 3. The best published candidate: Zarattini, Barbon & Aziz (2024)

*A Profitable Day Trading Strategy For The U.S. Equity Market*, SFI Research Paper 24-98 / SSRN
4729284. ~7,000 US stocks, 2016–2023, CRSP + IQFeed intraday, survivorship-bias free.

**The rule.**
1. Universe filters: open > $5; 14-day avg volume > 1,000,000 shares; 14-day ATR > $0.50.
2. Direction is set by the first 5-minute candle — bullish candle ⇒ long only, bearish ⇒ short only,
   doji ⇒ no trade. **The direction is not a free parameter.**
3. Entry: stop order at the 5-minute high (long) or low (short).
4. Stop loss: 10% of 14-day ATR from entry. Profit target: end of day (16:00 ET).
5. **Stocks in Play filter:** relative volume in the first 5 minutes ≥ 100% of its own 14-day
   average, then trade **only the top 20** by relative volume.
6. Sizing: 1% of capital risked per position, max **4× leverage**.

**Reported results (net of a $0.0035/share commission):**

| | total return | IRR | vol | Sharpe | hit rate | MDD | alpha | beta |
|---|---|---|---|---|---|---|---|---|
| ORB base (all stocks) | 29% | 3.2% | 6.6% | 0.48 | 41.4% | 13% | 3.3% | 0.01 |
| **ORB + RelVol top-20** | **1,637%** | **41.6%** | 14.8% | **2.81** | 48.4% | 12% | 35.8% | 0.00 |
| S&P 500 buy & hold | 198% | 14.2% | 18.3% | 0.78 | 54.9% | 34% | 0.00% | 1.00 |

### What is genuinely strong about it

- **The base case loses to buy-and-hold and they report it.** 3.2% vs 14.2%. A paper willing to
  publish its own null is behaving differently from a marketing document.
- **Survivorship-bias-free**, 8 years, ~7,000 names. Twitter is in the database.
- **The mechanism is economically motivated**: news → institutional repositioning → a demand/supply
  imbalance that persists through the session. Relative volume is a *measurement of the mechanism*,
  not a mined parameter.
- **Beta 0.00.** Genuinely uncorrelated with the index, which is rare and valuable.
- **The Sharpe has headroom.** 2.81 is far enough above 1.0 that it can absorb a large cost haircut
  and still beat the S&P's 0.78. This is categorically unlike our memecoin results, where a 0.6pp
  gross edge faced a 95 bps toll and had no headroom at all.
- **Deflated Sharpe would not kill it.** ~2,000 trading days, ~4 declared timeframe trials. Under
  Bailey & López de Prado the haircut on SR=2.81 at N=4, T=2000 is small. Contrast every return
  result in this programme, which died at DSR (0.176 and 0.224).

### The hole — and it is precisely the one that killed everything else we tested

Machine-checked against the extracted text of the paper:

| term | occurrences in the paper |
|---|---|
| `slippage` | **0** |
| `bid-ask` / `bid ask` | **0** |
| `market impact` | **0** |
| `capacity` | **0** |
| `fill` | **0** |
| `commission` | 12 |

**The only modelled cost is $0.0035/share commission.** No spread, no slippage, no impact.

**And the entry mechanism makes this the worst case, not an edge case.** Entry is a *stop order* —
which becomes a **market order** the moment it triggers. It fires as price breaks the opening range,
i.e. at the instant of maximum momentum, in the **top 20 stocks by relative volume** — the fastest,
most news-driven names of the day. The backtest credits a fill at exactly the stop price. That is
the fill you are least likely to get, in the names where you are least likely to get it.

Mesfin (2026) names this failure mode first in his list of why retail backtests look better than
reality: *"unrealistic fill prices (using mid-market instead of actual bid-ask)."*

## 4. The arithmetic that decides it — AN ESTIMATE, NOT A RESULT

The paper's own per-trade edge, in R units, where **R = 10% of 14-day ATR**:

| relative volume | avg PnL per trade |
|---|---|
| < 100% | **−0.02R** |
| > 100% (the filter actually used) | **+0.08R** |
| > 30× | +0.38R |

Per-share edge = `PnL_in_R × 0.10 × ATR`.

For a $50 stock with $2.00 ATR: **R = $0.20/share**, so the edge is **$0.016/share at 0.08R**,
rising to $0.076/share at 0.38R.

Against that, Schwarz, Barber, Huang, Jorion & Odean (*Journal of Finance*, 2025) measured actual
retail execution by placing **85,000 simultaneous market orders across six accounts at five
brokers**: mean account-level **round-trip cost of 7 to 46 bps, excluding commissions**. On a $50
stock that is **$0.035 to $0.23 per share**.

> **The measured retail execution cost is the same size as — or several times larger than — the
> entire per-trade edge.**

And Schwarz measured *ordinary market orders in ordinary conditions*. Not stop orders in the most
volatile stock of the session.

**Two caveats that keep this honest.** (a) The top-20 filter selects far above the 100% threshold, so
the realistic per-trade edge sits above 0.08R — somewhere toward 0.2–0.4R. (b) The 7–46 bps figure is
a round-trip on marketable orders and its applicability to a stop-order fill in a high-RelVol name is
exactly what is unmeasured. **This arithmetic does not refute the strategy. It identifies the
quantity on which the entire result depends, and shows that quantity is the same order of magnitude
as the edge.**

### The structural insight this exposes

**The edge scales with dollar ATR. The cost scales with spread.** So viability is governed by the
**ATR-to-spread ratio**, a quantity the paper never examines. This has a sharp consequence:

- $50 stock, ATR $2.00, spread $0.02 → R = $0.20, edge/spread ratio is workable.
- $8 stock, ATR $0.55, spread $0.01 → **R = $0.055**, and at 0.08R the edge is **$0.0044/share** —
  *less than half the spread*. Dead before commission.

Both stocks pass every filter in the paper. **The universe filters admit names where the edge cannot
survive the spread, and the backtest cannot see it because it does not model the spread.** Screening
on ATR/spread rather than on ATR alone is a concrete, testable refinement — and it is the kind of
change that would show up as a large effect if the diagnosis is right.

## 5. The adversarial counterweight: Mesfin (2026)

*Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures: A Systematic Falsification Study.*
14 signal families, 947 trading days of 5-minute bars, 2021–2025. Pre-committed 5-criterion bar
(OOS T ≥ 2.0, N ≥ 30, positive net after 2-point friction, year-stability, permutation p < 0.05).

**Nothing passed.** ORB specifically:

| variant | N | mean net | T | verdict |
|---|---|---|---|---|
| ORB Long bar+1 | 447 | −0.82 | 1.17 | FAIL |
| ORB Long bar+15 | 447 | +2.82 | 1.50 | FAIL |
| ORB Short bar+1 | 428 | −3.45 | −1.33 | FAIL |
| ORB Pullback | 83 | −4.44 | −1.27 | FAIL |

Central finding — **the gross edge ceiling**: across all 14 families the maximum gross return before
friction is ~0.07 to 1.50 points; friction alone is 2.0 points. *"Every signal family fails, not
because the signals are measuring nothing, but because what they measure is too small to survive
realistic execution costs."*

**This is our own finding, in a third independent domain.** Memecoins: gross edge real, 95 bps toll
kills it. Binance practitioners: 12 of 20 profitable at zero fees, 1 of 20 with fees. MNQ futures:
gross edge 0.07–1.50 points, friction 2.0 points. **Costs, not signal, are the binding constraint —
now observed in three unrelated markets.**

### But it is not a refutation of Zarattini, and saying so would be sloppy

Different instrument (one index future vs ~7,000 individual stocks), and critically **the ORB paper's
entire claim is that the base signal does not work** — which Mesfin independently confirms — and that
performance comes only from conditioning on abnormal single-name volume. MNQ has no analogue of a
single-stock news catalyst. **Mesfin refutes the thing Zarattini also reports as failing.** The
Stocks-in-Play conditioning is untested by Mesfin.

### Mesfin's transferable positive result

His two positive controls (T = 5.83 and 5.15, permutation p < 0.001) both cleared the bar, and he
identifies what they share: *"they hold positions for 12–15 bars rather than 1–6. That longer hold
allows the signal's regime-level information to build up enough net return to clear friction."*

**Hold longer to clear a fixed friction cost.** ORB's end-of-day exit is on the right side of this —
its hold is the full session, not one bar. That is a point in its favour that neither paper connects.

## 6. What carries over from this programme

**Applies unchanged:**
- Cost realism is the binding constraint. Three domains now agree. Any backtest that does not model
  the spread is measuring a quantity that does not exist.
- Deflated Sharpe against declared trial count, before believing any Sharpe.
- Walk-forward with the compounding audit (`audit_compounding()` in
  `scripts/btc_crash_filter_replicate.py`) — chaining per-fold equity silently skips the return
  across each join. Caught only by asserting B&H-chained == B&H-direct.
- Paired comparison to cancel asset variance.
- Preregistration and single-use evaluation for anything we intend to act on.

**Newly relevant, and not something we needed before:**
- **Broker choice is worth more than most strategies.** Schwarz et al. found a **6.5× spread** in
  round-trip cost (7 vs 46 bps) across brokers on *identical simultaneous orders*, and PFOF does not
  explain the variation. At the edge sizes involved, selecting the right broker is plausibly a larger
  effect than any signal refinement available to us. **This is the cheapest available improvement and
  should be settled first.**

**Does not carry over:** the deadness screen, the concentration work, everything venue-specific to
bonding curves. Window 2 collection is unaffected and continues on its own track.

## 7. The decisive experiment

Do not replicate the 8-year backtest first. **Measure the one unmeasured quantity.**

> Over a sample of stock-days that would have been top-20 by opening relative volume, reconstruct
> from **quote** data (not trades) the fill a stop order at the 5-minute high/low would actually have
> received, and compare it to the stop price. That distribution — median and tail — subtracted from
> the paper's 0.08–0.38R, decides the strategy.

Properties that make this the right first move: it is bounded (weeks of data, not 8 years), it needs
no strategy implementation, it is a *measurement* rather than a search so there is no multiple-testing
exposure, and **either outcome is worth having.** If median slippage exceeds ~0.2R the strategy is
dead and we stop. If it is under ~0.05R the edge is real and everything else is engineering.

**Secondary, from the same data at no extra cost:** the ATR/spread ratio distribution across the
universe filters, which tests §4's structural claim directly.

Data requires quotes, not just OHLCV bars. Candidates: Polygon.io, Databento, Alpaca, IQFeed
(the paper's own source). **Not yet chosen — pending the owner's call on cost.**

---

*External literature only. Every number above is someone else's measurement, cited so it can be
checked. This programme has measured nothing in equities yet, and this document must not be read as
though it has. See [FINDINGS.md](FINDINGS.md) for what we have actually established.*
