# FINDINGS — what this programme established, and how firmly

**Purpose.** Everything below is scattered across ~40 commits and a dozen documents. This is the
single index: what we know, how confident we are, where the evidence lives, and what was retracted.

**Read the confidence column first.** This project's central lesson is that a number's *distance from
zero* matters more than its sample size: a −18.9% result at 43% volatility is sixteen standard errors
out and unkillable; a +0.48% result at the same volatility is noise. Both appear below.

---

## 1. The load-bearing negatives — these are 13–16 sigma and will not move

| finding | figure | t | where |
|---|---|---|---|
| The exit-rule family loses money | −18.94% per position | **−16.2** | `B19_EVALUATION_LEDGER.json`, B19K |
| Perfect liquidity does not rescue it | −12.78% (ceiling) | **−13.2** | `B19P` §liquidity bound |
| Zero transaction cost does not rescue it | −16.89% | — | `B19P` |
| Infinite position size does not rescue it | −16.69% | — | `B19P` |

**What this means.** The failure is the *shape* of the outcome distribution — roughly 45% win small,
55% lose big — and no venue, size, cost or rebate change reaches it. **Even trading for free loses
16.89%.** That single number closes every cost-reduction idea, including rebates.

## 2. The structural explanation

> **The toll is the house edge, and the house is the creator and the protocol, not the trader.**

Every position on this venue is one of two things: be right about direction and pay the round-trip
toll, or *be the fee recipient*. The fees **are** the extraction. This is why no directional shape
dodges the toll for the same reason none beats the asymmetry — both are the house winning by
construction. `B19P`.

**Independently corroborated**: Marino et al. find all their predictive features *"remained below the
economic breakeven curve"* — separate data, separate method, same conclusion (`B21C`).

## 3. The one positive that survived every test

**The deadness screen.** At `t0 + 60` slots, if the single largest buyer holds **≥ 0.95** of all
tokens bought, do not enter.

| held-out | flagged | passed |
|---|---|---|
| share of tokens | 39% | 61% |
| **unexitable rate** | **69.7%** | **13.0%** |

Base rate 35.3%. Catches **77.7%** of all unexitable tokens at 69.7% precision. Train +52.4pp, test
+56.7pp — **no shrinkage**. Verified independently by the peer seat on a *different corpus with a
different pipeline* (n=606, +46pp, permutation p=0.000).

**Cost, which belongs beside the benefit:** it also discards ~18% of tokens that *were* exitable. One
good token in five, to cut the bad rate from 35% to 13%.

**It creates no edge.** It avoids a class of guaranteed losses. `B20B`.

**Status: FROZEN and under out-of-sample test.** Preregistration `B20B_DEADNESS_SCREEN_PREREGISTRATION.json`
(canonical `5f3a2b5e…`), runner pinned `d77f7699…`, committed while the window-2 data was *unreadable*
— blindness by construction, attested independently by both seats.

## 4. Venue structure — measured facts worth keeping

| fact | value | where |
|---|---|---|
| graduation rate, 27–28 Jul 2026 | **2.09%** (82/3,932) | B19N |
| …and it is wildly regime-dependent | 0.198% → 6.7% in ~7 weeks | `B21C` |
| graduation deposit | 84.990359056–84.990364132 SOL | B19N — *confirmed by literature at "~85 SOL"* |
| median time launch → graduation | **49 slots (~20 s)** | B19N |
| pool pricing invariant | `(quote + virtual) × base`, 765/765, zero breaks | B19N §2 |
| …virtual reserve is a **per-pool constant** | unchanged in 340/343 pools | B19N §2 |
| bonding-curve virtual quote reserve | **exactly 30.000 SOL** (protocol constant) | B19N §3b |
| median *peak lifetime* external capacity | **1.00 SOL** | B19N §3c |
| effective depth advantage, graduated vs curve | **2.9×**, not 85× | B19N §3b |
| fee: median payable tier | 95 bps/leg (25 bps tier is 25% and **not selectable**) | B19N §1b |
| migration price gap | **3 bps**, 82/82 one-directional, deterministic | B19Q §8d |
| one launch in ten doubles | 10.13% reach 2×; max 13.76× | B19Q §1 |
| peaks are **plateaus, not spikes** | 93% keep ≥80% one slot later; 0% pure spikes | peer seat, B19Q §7 |

## 5. Instrument findings that transfer beyond this market

- **For right-tail assets, a trailing stop beats fixed thresholds** — +2.7pp and 5 folds to 0, on the
  *same* positions. Survives even though the absolute level does not. `B19Q` §7.
- **The give-back optimum is a broad plateau (8–18%), not a point.** A knife-edge optimum would mean
  the effect lives in the tuning; a plateau means it belongs to the payoff shape.
- **At n≈2,000 with 43% volatility you can RANK shapes but not CERTIFY levels.** A paired comparison
  cancels asset variance; an absolute mean does not.
- **Deflated Sharpe (Bailey & López de Prado 2014) is the named correction for search-max results**,
  and applying it to our own +0.48% is brutal: observed Sharpe **0.01114** against an expected-max
  under the null of **0.01854 at only ten trials**, DSR **0.176** at our real search size. The result
  is *below the chance ceiling*. Skewness **+20.2**, kurtosis **521** — which is why every ordinary
  statistic flattered this payoff. `B19Q` §8e.
- **Sizing:** the cost curve has a minimum. B19K's 0.1 SOL was already near-optimal — fixed costs fall
  with size, slippage rises, and they cross at a few tenths of a SOL.

## 5b. The crash filter under the strongest test we have

The one candidate that might see real money, put through Deflated Sharpe. **The benchmark matters
enormously and the first version of this test got it wrong.**

**Wrong test:** DSR on the filter's own returns gives 1.000 at every trial count — but that only asks
*"is this Sharpe non-zero?"*, and holding BTC through a 74,000% run answers yes for anything invested
most of the time. It is not evidence about the filter.

**Right test — the paired difference against buy-and-hold**, which cancels the common asset move:

| | |
|---|---|
| SMA lengths with **negative** excess Sharpe | **9 of 10** |
| best (SMA 125) | +0.00241/day, **t = +0.17** |
| expected max Sharpe under the null, 10 trials | **0.00834** |
| DSR (10 → 100 trials) | **0.341 → 0.224, fails throughout** |

**The return advantage is below the chance ceiling**, and nine of ten filter lengths *lose* return
versus simply holding.

**What survives untouched:** the **drawdown reduction** — −84.9% → −69.5% full sample, protection in
5 of 7 measurable crashes, zero harmful, reproduced from two independent data sources by two
independent implementations. DSR tests return series and does not bear on it.

**So the honest statement is exactly what the playbook already says, now confirmed by the strongest
method available:** it is *insurance*, not alpha. Anyone reading it as a return enhancer is reading
it wrong.

## 5c. WHERE DEFLATED SHARPE APPLIES — and where applying it would be an error

DSR corrects **return series** for search-selection. It has two failure modes and this project has
now hit one of each, so both are recorded:

**False PASS — wrong benchmark.** Running DSR on the crash filter's *own* returns gives **1.000** at
every trial count. That only asks "is this Sharpe non-zero", which holding BTC through a 74,000% run
answers yes to regardless of the filter. **The paired difference against buy-and-hold is the correct
instrument**, and it fails (DSR 0.224).

**False FAIL — wrong object.** The **deadness screen is a classifier, not a strategy with a Sharpe.**
There is no return series to deflate. Its correct tests are the ones it passed: a **label permutation
on the flagged-versus-passed difference (p = 0.000, both tails)**, a held-out split with no shrinkage,
and independent replication on a different corpus. *Applying DSR to it would report a failure that
does not exist.*

> **Rule:** DSR for anything with a return series that came out of a sweep. Permutation for
> classifiers. Paired differences whenever a common market move would otherwise dominate.

## 5d. Consolidated ledger after the DSR pass

| candidate | verdict | by what test |
|---|---|---|
| trailing stop, return | **dead** — below the chance ceiling | DSR 0.176 |
| crash filter, return | **dead** — below the chance ceiling, 9/10 lengths lose | DSR 0.224–0.341 |
| **crash filter, drawdown** | **stands**, ~14–15pp reduction | two sources, two implementations, 5/7 crashes |
| **deadness screen** | **stands**, frozen, under out-of-sample test | permutation p = 0.000, held-out, replicated |
| funding carry | **dead** — below risk-free forward | −0.46pp vs T-bills, needs +1.47pp for tail risk |
| PUMP "own the house" yield | **dead** — the experiment already ran and failed | 9 months, 100% of >$1B revenue, price below launch |
| PUMP structure ("the house is the protocol") | **stands** | B19P, quantified externally |
| **T3 end-of-day pressure reversal** (equities, shortlist #1) | **dead** — held-out DSR **0.9379** against a threshold of 0.95 frozen first | `research/trading_bot/T3_RESULT.md` |
| **T7 ex-dividend drop-off, close-to-close in the auctions** (equities, shortlist #2) | **dead** — permutation **p = 0.213** and DSR **0.076**, both frozen first; all eight design trials negative | `research/trading_bot/T7_RESULT.md` |
| **T9 spin-off forced-selling drift** (equities, shortlist #4) | **dead by INSUFFICIENT POWER** — MDE **5.51%** against a 2.40% literature effect on **62** held-out events, gate frozen first; also p = 0.627 and DSR 0.063 | `research/trading_bot/T9_RESULT.md` |
| **T10 overnight-vs-intraday premium** (equities, shortlist #6) | **dead TWICE OVER, independently** — held-out **DSR 0.3772** (observed per-obs Sharpe 0.01405 *below* the 0.02342 chance ceiling at 8 declared trials), **and** dead at **0.26 × one measured half-spread** on a book that turns 4.00 of notional per session | `research/trading_bot/T10_RESULT.md` |
| **T11 cash-merger arbitrage spread** (equities, shortlist #7) | **dead on all five frozen gates**, and the first candidate killed by a **TAIL** rather than by friction: MDE 1.324% vs 1.179% benchmark, mean **−0.83%**/event (t −0.985), permutation **p = 0.876**, **DSR 0.0391**, and the break gate. On the *cleanest* 317 deals the spread is real — **+6.66 %/yr over T-bills** — but its **break-even deal-failure rate is 6.68 %** at a −25% break loss, inside the 5–10% quoted band. It loses at **zero cost** (−0.776%), so friction is not the mechanism | `research/trading_bot/T11_RESULT.md` |

| **T15 PEAD, post-earnings-announcement drift** (equities, shortlist #12) | **DEAD BY INSUFFICIENT POWER, before it was tested and without burning the held-out window.** Gate frozen first (sha256 `76f712f7…`): MDE ≤ 0.90 %, Martineau's own pooled large-cap random-walk decile spread. Measured **MDE = 4.44 %** on **5,991** held-out events in 18 seasons — **fails by 4.93×**, and fails in all four declared framings. The window cannot detect *any* large-cap PEAD figure in the literature, including the 1973–1990 one. **The scoping arithmetic that promoted this candidate was wrong by 9.8×** | `research/trading_bot/T15_RESULT.md` |

| **T23 cross-sectional perp funding carry** (crypto; T21's rank-1 candidate, the +2.20 pp/yr claim) | **DEAD BY INSUFFICIENT POWER, held-out window NOT spent.** Gate frozen first (sha256 `a9ce4fc0…`) with the windows, the 36.8 bp round trip, the −2.00 % delisting tail, the by-year T-bill benchmark and a **+1.00 pp/yr venue-tail bar**, all before any number. Survivorship-complete panel built from `data.binance.vision`: **920 symbol folders, 833 USDT perps of which 158 are dead today, 2,721,204 funding prints, 63,801 archives cached and hashed**; the BTC leg reconciles **exactly** (max abs diff 0.0) against this repo's independent REST pull. Measured **MDE = 15.25 pp/yr** against the 2.20 pp claim — **6.93×**; and **4.56 pp, still 2.07×**, at T21's own optimistic 3.08 pp dispersion. **T21's "Sharpe 3.14" is the GROSS Sharpe; the excess-over-T-bills Sharpe it implies is 0.714, which by T10's `(2.80/S)²` wants 15.4 years and Binance publishes 6.6.** This panel can only certify an edge ≥ **11.4 pp/yr**. Two design-window findings survive the block: **31.2 % of the names the rule selects no longer trade** (22.7 % of name-months — `LUNAUSDT` is a top-3 holding in Oct/Nov 2021), so T21's `exchangeInfo` universe was missing a quarter of the strategy; and **the liquidity screen T21 credits the entire edge to HURT at every `topN` on the 34 unburned early months** while reversing a −70.67 %/yr loss on T21's own 22 — an unstable sign, which is what a search-max looks like. BTC-only beat the cross-sectional book on Sharpe (2.47 vs 1.67) in the same window | `research/trading_bot/FUNDING_CARRY_VALIDATION.md` |

| **T25 cross-venue perp funding differential** (crypto; T21's rank-3 candidate — Hyperliquid vs Binance, same coin, no spot leg) | **DEAD BY INSUFFICIENT POWER, held-out window NOT spent.** Gate frozen first (sha256 `3cc5759d…`) with the windows, the 24.1 bp round trip, the ÷2 capital multiplier, the by-year T-bill benchmark and a **+1.00 pp/yr venue-tail bar**, all before any number. Survivorship-complete two-venue panel: **106 coins, 2,340,613 Hyperliquid hourly funding prints**, and **41 of 41 HL-delisted coins still return full history**. **Both blocking gates fail:** MDE **6.30 pp/yr** on the held-out window (5.89× the 1.07 pp claim) and **2.85 pp/yr on the ENTIRE joint history of both venues** (2.66×) — so **no split of this data can ever work**. Certifying the claim needs **22.5 years of a venue that is 3.3 years old.** Three findings survive the block: (a) in the burned window **none of the four declared `topN` clears the +1.00 pp bar** — best +0.738 pp/yr (t 0.53, 40.9 % of months positive), `topN=20` **−1.47 pp/yr (t −2.43)** — while the trailing differential calls next month's **sign 79–84 %** of the time, i.e. **the signal works and loses to T-bills** once the differential is halved for double collateral and compared to 3.84 %; (b) cross-venue differentials **are** persistent (Spearman **+0.391**), the opposite of T23's finding for funding *levels*; (c) **a single-interval cross-section is not a month's carry** — T21 §6.3's snapshot overstates the realised monthly p90 by **2.0×** and understates the median by **2.4×** | `research/trading_bot/T25_RESULT.md` |

| **T13 risk-shaping** (equities, the pivot away from direction) | **dead on the frozen gate, both families.** SMA crash filter: **−9.65 pp** of drawdown *worse* than de-risked buy-and-hold at matched volatility (46.66 % vs 37.01 %), −1.66 %/yr, p = 0.527. Vol-targeting overlay: **+7.25 pp and +0.66 %/yr but p = 0.233** — the effect clears the size threshold and not the significance one. Neither licenses a return claim (DSR 0.016 / 0.355) | `research/trading_bot/T13_RESULT.md` |

**Two things survive the whole programme, and neither makes money:** a drawdown reduction on a
position you were holding anyway, and a screen that avoids a class of losses.

> **⚠ T13 puts a qualifier on the first of those.** §5b's crash-filter drawdown claim is stated
> **crash-by-crash**, and the equity replication passes that metric (3 of 3, mean 16.9 pp) while
> **failing full-path drawdown against a de-risked buy-and-hold**. Read §5b as *"protects inside
> crashes"*, never as *"reduces the drawdown you will live through"*. Whether the BTC result
> survives the vol-matched null has not been tested; `scripts/t13_risk_shaping.py` now does it in
> one call. §5i.

**And one negative that is a different shape from all the others.** Every prior death was the
friction floor or the chance ceiling. T11's spread is *real and correctly priced*: the payoff is
the compensation for the payoff's own tail. `FINDINGS` had no category for that until now.

## 5e. T3 — the first equity candidate through the full bar, and the shape of its failure

Frozen rule `T3_PREREGISTRATION.md` (sha256 `401fd377…`), design 2016–2021, held out 2022-01-03 →
2026-08-14, 1,139 nights, 1.24 M symbol-nights, universe screened point-in-time from 14,724 active
**and inactive** symbols.

| gate, all three frozen in advance | held-out | outcome |
|---|---|---|
| net mean per night > 0 | +5.35 bp, t **+2.73**, Sharpe 1.29 | passes |
| cross-sectional label permutation p < 0.05 | **p = 0.0001** | passes |
| **DSR ≥ 0.95 at the declared 8 trials** | **0.9379** | **fails → DEAD** |

**Three things worth carrying forward, independent of the verdict:**

- **The signal is real and it is not the bid-ask bounce.** Replacing the 15:59 last-trade entry with
  the bounce-free official closing auction print leaves +6.07 bp/night, t +3.10 out of sample.
- **The free auction rail cannot reach it.** MOC orders stop being accepted at **15:50**, and the
  variant that uses only pre-cutoff information (15:29→15:49, both legs in the auctions, zero modelled
  spread) is t = **1.38** held out. The structural cost advantage is only available to a signal that
  is too old to be worth trading.
- **First-party equity friction, measured:** median quoted half-spread in the final second before the
  close, top-500-ADV universe, is **1.13 bp (2016–2021)** and **1.43 bp (2022–2026)**, n ≈ 20,000
  symbol-days per period. 4× that spread erases the whole edge. It agrees with the peer seat's
  independent B22B run on a different universe and a different order type — `B22B_SLIPPAGE_RESULT.json`
  reports a **median quoted spread of 3 bp** on the ORB most-actives pool against **2.9 bp** implied
  here (2 × 1.43). Two different instruments, two different populations, the same number.

**And one method item, found by checking rather than by intending:** the first version of the
auction-to-auction diagnostic ranked on a 30-minute return that *ended at 15:59* while placing an
order due at 15:50 — nine minutes of lookahead, worth more than half the result (+6.47 bp, t 3.07 →
+2.98 bp, t 1.38 once corrected). A hand-written diagnostic sits outside the T2 harness's three
anti-lookahead layers, and that is exactly where the lookahead appeared.

## 5f. T7 — the second equity candidate through the full bar, and the tax arithmetic behind it

Frozen rule `T7_PREREGISTRATION.md` (sha256 `7bd072a7…`), design 2016–2021, held out 2022-01-03 →
2026-08-14, **2,321 event-days / 14,187 cash dividends** in the point-in-time top-500-ADV universe,
both legs official closing-auction prints so the modelled quoted spread is genuinely zero.

| gate, all three frozen in advance | held-out | outcome |
|---|---|---|
| net mean per event-day > 0 | +0.84 bp, t **+0.46** | passes, meaninglessly |
| cross-sectional label permutation p < 0.05 | **p = 0.213** | **fails** |
| DSR ≥ 0.95 at the declared 8 trials | **0.076** | **fails → DEAD** |

**All eight design-window trials were negative** — the mirror image of T3, where all eight were
positive and it missed by 0.012. Pre-registration was load-bearing in both directions.

**The drop-off ratio, measured on our own instrument.** 0.9748 (design) and 0.9524 (held-out) —
**below 1 in both periods and distinguishable from 1 in neither** (95 % CI [0.84, 1.08] held out).
The residual is ~2.9 bp per event against ±2.4 bp of one-day portfolio noise. Elton & Gruber's
0.78 is outside both intervals. *The mechanism is visible and the trade is not there.*

**Three things worth carrying forward:**

- **Half a measured half-spread per leg kills it.** +0.84 bp at the auction rung, **−0.59 bp** at
  0.5 h. **M0 — do MOC/MOO orders fill at the official print — is now load-bearing for two dead
  candidates in a row** and is still unperformed. It is the cheapest outstanding item in the
  programme.
- **The tax framing in `EDGE_SHORTLIST.md` was wrong, and the truth is worse.** There is **no rate
  differential** for a one-day capture: the dividend is ordinary income *and* the offsetting price
  fall is a **short-term** capital loss, taxed at the same rates. The real problem is **usability**
  (IRC §1211(b)): the strategy books **67.7 % of equity per year in ordinary dividend income**
  against **65.9 % in short-term capital losses it generates no gains to absorb**, to earn 1.86 %
  pre-tax. In a standalone taxable account that is **−21.8 %/yr at a 35 % rate**. Break-even needs
  a drop-off ratio below **1 − t ≈ 0.65**; it is 0.95. A **tax-deferred account removes the
  objection entirely** — which is an owner-disposable account-type question, and should not be
  allowed to sink a *future* candidate that passes on the statistics.
- **The residual is overnight and is given back intraday.** Exiting at the ex-date *opening*
  auction instead of its close is +3.72 bp/day held out (t 3.29), +3.63 bp against the same-day
  non-ex-dividend control (t 3.18, permutation p 0.042). **This is exploratory and 2022–2026 is now
  burned for it** — it was excluded from the declared grid in advance, and any pre-registration of
  it needs a *prospective forward* test, not a re-run on this cache.

## 5g. T9 — the third equity candidate, and the first that does NOT die at the friction floor

Frozen rule `T9_PREREGISTRATION.md` (sha256 `cd36949c…`), and the gate that decided it is a
**power gate computed before the held-out number existed**, on design-window and structural
quantities only.

| gate, all four frozen in advance | held-out | outcome |
|---|---|---|
| **MDE at 80% power ≤ 2.40%** (Cusatis's own ≈+10%/yr over 60 sessions) | **MDE = 5.51%** on **62** events | **FAILS by 2.3×** |
| net mean per event > 0 | −0.82%, t −0.39, CI [−4.9%, +3.3%] | fails |
| event-label permutation p < 0.05 | **p = 0.627** (37th percentile of the null) | fails |
| DSR ≥ 0.95 at the declared 3 trials | **0.063** | fails |

**"243 spin-off records already on disk" was this programme's own count and it was wrong about the
world.** 243 raw → 225 unique → 177 with a ticker `new_symbol` (48 are CVRs, escrow/contingent
entitlements and bare CUSIPs) → **82 tradeable events, 62 held out, 14 in the design window**.
And the corporate-actions feed's spin-off history is **truncated, not thin**: zero records in
2016, zero in 2018, one in 2019 — Corteva, Dow, Adient, Lamb Weston, Valvoline, Resideo, Garrett,
Arlo and Brighthouse are all absent while five of them return cash dividends over the identical
query window. **The T3/T7 design/test split is not executable for this candidate**, so T9 declared
its configuration a priori instead and had no fitted parameter at all.

**The inversion worth carrying.** Per event: friction **11.78 bp**, per-event standard deviation
**1,635 bp** — a ratio of **139×**. T3 died at 6.8 bp of gross against 1.4 bp of friction; T7 at
0.84 bp against 0.37 bp. T9 loses at **zero** cost (−0.70%, t −0.34) and the whole stress ladder
from free to 4× the measured spread moves the answer by 35 bp. **The binding constraint here is
sample size, not friction, and it is the first time in this programme that has been true.**

**Reusable measurement:** the median quoted half-spread of a **freshly distributed spin-off stub**
is **7.47 bp** (p25 3.40, p75 18.42, p95 59.57, mean 20.86, n = 134 symbol-days), same instrument
and window as T3 — against SPY's **0.116 bp** and the top-500-ADV universe's 1.13–1.43 bp.

> **Method rule earned here: count the events before building the harness.** A candidate whose
> minimum detectable effect exceeds the literature's own effect size is dead before it is tested,
> and establishing that is a counting exercise, not a backtest. It took minutes; the harness took
> hours. **327 events are needed and 13.4 arrive per year — 24 years of prospective collection.**

## 5h. T10 — the fourth equity candidate, and the one that names the programme's real constraint

Frozen rule `T10_PREREGISTRATION.md` (sha256 `7f661951…`), design 2016-02 → 2021-12, held out
2022-01-03 → 2026-08-14, **1,140 sessions / 1.24 M symbol-days**, both legs official auction
prints, eight declared trials, one frozen configuration (the Lou-Polk-Skouras cross-sectional
tug of war, 63-session lookback, deciles, top-500-ADV).

| gate, all frozen in advance | held-out | outcome |
|---|---|---|
| net mean per session > 0 | +1.482 bp, t **+0.47** | passes, meaninglessly |
| label permutation p < 0.05 | **p = 0.0020** | passes — **and the instrument is wrong, see below** |
| **DSR ≥ 0.95 at the declared 8 trials** | **0.3772** | **fails → DEAD** |
| power label, declared first | MDE **1.304** Sharpe vs benchmarks 0.903 / 0.382 | **UNDERPOWERED** |

Design → held-out annualised Sharpe **+0.903 → +0.221**. All eight design trials were positive —
the T3 shape, which is exactly why the deflation exists.

**Four things worth carrying forward.**

- **The programme's binding constraint is the resolution of its own test, and T10 makes it
  arithmetic.** At 80 % power on daily data, certifying a true annualised Sharpe needs
  `(2.80/S)²` years of held-out data: **S = 1.3 → 4.6 yr, S = 1.0 → 7.8, S = 0.8 → 12.2,
  S = 0.5 → 31.4, S = 0.3 → 87.1.** We hold **4.6 years** held out and 10.6 in total. **Every
  remaining directional candidate on the shortlist sits below Sharpe 0.5.** That is why the
  recommendation after T10 is the risk/sizing pivot rather than a fifth directional candidate:
  the surviving results of this whole programme (crash-filter drawdown, deadness screen) are
  **distribution-shape claims, not mean claims**, and that is precisely why they survived.
- **Friction, and it is a separate death from the power one.** The paired trade flips the book at
  both auctions: **4.00 of gross notional traded and 2.00 sold per session**, measured and
  asserted, not assumed. SEC §31 alone is **0.556 bp/session = 138 bp/yr**; total charged
  friction 193 bp/yr against a gross edge of **4.29 %/yr**. **Break-even is 0.370 bp per auction
  leg — 26 % of the measured quoted half-spread of its own universe.** At 0.5 h it is −4.68 %/yr.
  **M0's unmeasured live half is now worth 1,414 bp/yr to this candidate**, which makes M0-C4 the
  most expensive outstanding measurement in the programme rather than merely the cheapest.
- **The Lou-Polk-Skouras asymmetry is REAL and reproduces out of sample on a second instrument —
  and harvesting it still does not work.** Held out on auction prints: SPY overnight **+7.29 %/yr,
  Sharpe 0.724** against intraday **+3.15 %/yr, Sharpe 0.284**; EW top-500 +7.15 %/0.670 against
  +2.38 %/0.228. B22F measured 0.87 vs 0.43 on 2016–2026 adjusted bars. Different data, different
  window, same 2.5× asymmetry. **It is a risk-shaping fact, not an edge** — which is what B22F and
  the shortlist both already said, now with an out-of-sample number behind it.
- **A declared deviation, found by auditing the code against the pre-registration's own timing
  sentence — and it ran the *other* way.** The frozen signal's most recent term ends at
  `C(i,t−1)`, the print the overnight leg is entered at, which an MOC due at **15:50** cannot
  see: 1 of 63 terms. Corrected (signal ends at `C(t−2)`), the held-out net **rises** +1.48 →
  **+2.97 bp/session** and DSR 0.3772 → **0.5713** — still failing the 0.95 gate, on a variant
  that is a ninth trial run after the freeze. **T3 found a nine-minute lookahead worth more than
  half its result; T10 found a ten-minute one worth *minus* half of its.** *Audit the
  implementation against the pre-registration's timing sentence, and do not assume lookahead
  flatters.*
- **A method rule, extending §5c.** Gate 2 returned **p = 0.0020** on a series whose own t is
  **+0.47**. The signal-sorted decile book carries **3.88×** the per-session dispersion of a
  random partition of the same names (**105.5 bp vs 27.2 bp**), and it is **not** market beta
  (β = −0.036, residual Sharpe unchanged). A cross-sectional label permutation tests the *sharp*
  null and so answers **"is this partition special?"** — for a sorted **return series** that is
  not the same question as "is the mean positive?", and the two diverge by exactly the factor
  loading the sort picks up.
  > **Report the ratio of the real book's dispersion to the permutation null's beside any
  > permutation p-value on a sorted portfolio. Far from 1 means the p-value is not about the
  > mean.** (This does not overturn T3, whose permutation and t-statistic agreed — p = 0.0001 at
  > t = +2.73 — and which died on DSR anyway. But the ratio should be reported for it too.)

## 5i. T13 — the risk/sizing pivot, and the power wall that is worse than T10's

Frozen rule `T13_PREREGISTRATION.md` (sha256 `0eda5f7a…`), design **^GSPC 1929-01-03 → 1989-12-29**
(15,298 bars), held out **1990-01-02 → 2026-08-14** (9,222 bars, **36.6 years, 8 crashes**), primary
instrument ^SP500TR and confirmatory SPY, 14 declared trials, lookahead audit bit-identical on four
truncation probes with its negative control caught.

**The null that decides everything is `N1`: a constant weight in the same index plus T-bills, sized
so its realised volatility equals the strategy's, fitted with hindsight the strategy never gets.**

| | crash filter SMA-100 | vol overlay L60/10 % |
|---|---|---|
| **G1** ΔmaxDD vs N1, ≥3 pp and p<0.05 | **−9.65 pp** (46.66 vs 37.01), p 0.527 | **+7.25 pp**, **p 0.233** |
| **G2** ΔCAGR ≥ −0.5 %/yr | −1.66 %/yr | +0.66 %/yr ✔ |
| **G3** below 5th pct of its own 9,221 circular rotations | 32.8th pct | **2.2nd pct** ✔ |
| **G4** at 4× cost | fails | ✔ (+7.07 pp) |
| **G5** DSR ≥ 0.95 at 14 trials | 0.0159 | 0.3545 |
| round trips / yr | 5.84 | **0.86** |

**Both DEAD on the frozen logic.** N2 (ex-ante matched) and N3 (exposure-matched) agree with N1 to
within 1.5 pp — the conclusion does not depend on which form of "hold less" is chosen.

**Five things worth carrying forward.**

- **The filter protects in crashes AND has a deeper drawdown than holding less. Both are true.**
  Per crash vs N1: 2000-02 **+10.4 pp**, 2008 **+26.5 pp**, 2020 **+13.9 pp**, 3 for 3, none harmful.
  Its *own* worst drawdown is **1999-07-16 → 2003-04-16, −46.66 %, not recovered until 2010-01-07** —
  a **whipsaw**, not a crash, and ten and a half years underwater against the null's three and a
  half. Ulcer **16.35 against 13.80 for undiluted buy-and-hold**. **Measuring only inside crashes
  counts the benefit and not the cost; the cost arrives between them.**
- **The drawdown power wall, which is the T10 arithmetic's harsher sibling.** A mean claim gets one
  observation per **day**; a drawdown claim gets one per **crash**. 36.6 years = 9,222 daily
  observations and **three usable crash comparisons**. The overlay's per-crash advantage is
  **−6.00 pp, sd 6.84, n = 3** — and the +7.25 pp headline is **essentially 2008 alone** (13.82 pp
  there, 1.11 and 3.08 in the other two). The paired block bootstrap agrees: 5–95 range **−3.68 to
  +13.01 pp** around +7.25. **Crashes arrive one per nine years; twenty of them is 180 years.**
- **A plateau in a RATIO is not a plateau in the statistic you care about.** §5's plateau rule
  picked SMA-100 because it sat within 5 % of SMA-150 on design MAR. Held out, those two neighbours
  differ by **15.5 pp of maximum drawdown**. Worse: **four of the five declared lengths beat the
  null (+8.8, +6.6, +16.7, +16.3 pp) and the freeze picked the only one that did not.** Design MAR
  ranked `150>100>250>200>50`; held-out drawdown ranks `200>250>50>150>100` — **close to inverted**.
  *Check the plateau in the metric the claim will be made in, and out of sample.*
- **G3 is the weaker null and must never be reported without G1.** A circular rotation of a
  *time-varying* exposure path has median maxDD 45.7 %, far worse than a *constant* weight's 34.9 %,
  because randomly-placed variable exposure is a bad thing to hold. The overlay sits in the 2.2nd
  percentile of its own rotations **and still loses to a flat line**. Both statements are true.
- **The de-risked buy-and-hold null belongs in the standard battery.** No parameters, one function,
  and it has now killed two strategy families here after killing funding carry in the crypto phase.
  **Any future "this reduces risk" claim gets it automatically.** Family B (volatility targeting) is
  the one direction left standing on behaviour rather than statistics — cheap, positive-signed in
  **all four decades and all eight declared configurations** — and **1990–2026 is now burned for
  it**, so the only honest next instrument is a pre-registered *prospective* test.

## 5j. T15 — PEAD, and the largest scoping error in this programme's history

Frozen gate `T15_POWER_GATE.md` (sha256 `76f712f7…`), hashed **before the census ran**, with
`T15_POWER_CENSUS.json` verified absent in the same command. Held out 2022-01-03 → 2026-08-14,
**5,991 events, 18 earnings seasons, 591 decile pairs**, point-in-time top-500-ADV universe,
per-event 60-session market-adjusted dispersion **18.76 %**.

| framing, all four declared in advance | held-out MDE | vs the 0.90 % gate |
|---|---|---|
| naive — every event independent (`DATA_PURCHASE_SCOPE.md`'s framing) | 3.06 % | fails 3.4× |
| **season block bootstrap, persistent placebo — the primary** | **4.44 %** | **fails 4.93×** |
| season block bootstrap, IID placebo | 4.35 % | fails 4.8× |
| within-season rank regression on all events (the most powerful that exists) | 3.33 % | fails 3.7× |

**STEP 2 was not run, no rule was frozen, and 2022–2026 was not spent.** Total cost: an afternoon.

**Five things worth carrying forward.**

- **THE DECILE-BOOK POWER RULE, and it is now the largest single scoping error here.** A quantile
  long-short book does not estimate its mean from `n` observations — it uses `n/5` of them and
  their difference carries **twice** the variance: `SE = σ√2 / √(n/10)`, not `σ/√n`. Applying an
  all-events MDE to a decile spread overstates power by `√(2n/n_pairs)` — here **5.58×**.
  `DATA_PURCHASE_SCOPE.md` §5b flagged the *season-clustering* risk (worth **1.45×**) and missed
  this one, which was **four times larger**. **Count the observations the ESTIMATOR uses, not the
  observations the dataset has.** Full decomposition of the 9.8×: estimator/count **5.58×**,
  σ borrowed from the wrong instrument **1.21×**, season clustering **1.45×**.
- **Run the block bootstrap even when theory says the cluster cancels.** A within-season long-short
  book cancels the season's market move by construction — and still carries a **2.11×** variance
  inflation (**280 effective decile pairs out of 591**) from volatility heterogeneity *across*
  seasons, 2022 above all. Block lengths of 1, 2 and 4 seasons agree to 3 %.
- **The friction inversion, now three times more extreme than T9's.** Per event: friction
  **4.23 bp** on M0's auction rail against a per-event dispersion of **1,876 bp** — a ratio of
  **444×** (T9's was 139×; T3 died at 1.4 bp of friction against 6.8 bp of gross). **Sample size,
  not friction, is the binding constraint for the second time — and this is the first candidate
  for which M0's unmeasured C4 provably does not matter.**
- **The free SEC route WORKS, and one asset survives the verdict.** 8-K item **2.02** with
  `acceptanceDateTime` gives a universe-wide, second-resolution, point-in-time US earnings
  calendar — **72,649 filings, 0 fetch failures** — and it places **95 %** of large-cap releases
  outside the session (52.3 % pre-open, 43.0 % post-close, 4.7 % intraday) with **no timing
  assumption**. XBRL `EarningsPerShareDiluted` is filed at a **median lag of 1 day** behind the
  8-K, not the 30–40 days feared; 34.7 % arrive on or before it. **The hole is fiscal Q4** — the
  10-K tags the annual period, so **24.9 %** of events have no quarterly EPS fact at all, and a
  strictly point-in-time seasonal-random-walk SUE exists for **33.9 %** of events. Cached at
  `research/data/t15_cache/`; **any future candidate that needs to AVOID earnings dates now gets
  the calendar for nothing.**
- **The prior was right and it was not what decided this.** Martineau (2021, *Critical Finance
  Review*) regresses `BHAR[2,60]` on the decile rank of **the same seasonal-random-walk surprise**
  for **all-but-microcap** stocks and gets **0.001\*\* pooled 1973–2019** but **−0.002, −0.000,
  −0.003, −0.000, −0.003\*** in every subperiod from 1996 on — *"For large stocks, PEAD have been
  non-existent since 2006."* The gate used the **pooled** figure precisely because erring toward
  the candidate is the honest direction.

> **The process rule this earns, and it outranks any next candidate.** T9 and T15 have now both
> died on a power census costing under two hours, and **neither candidate's scoring document had
> run one.** Make the power census a mandatory pre-registered gate on every future candidate,
> **computed on the estimator that will actually be used**, before a line of harness is written.
> Two candidates killed for one afternoon — and, decisively, **without burning the held-out
> window**, which is the only genuinely scarce resource this programme has.

## 6. Retractions — recorded because the pattern matters more than the items

| claim | why it was wrong |
|---|---|
| graduated market 4.5× cheaper on fees | truncated an ascending distribution; median leg is 95 bps not 25 |
| 12× lower round-trip toll | compared an instrument that **cancels** slippage against one that charges it |
| 85× depth advantage | compared against the curve's **real** reserve, which never prices anything (virtual is 30 SOL) |
| graduation deposit "exactly 85.0 SOL" | float formatting; it is 53 distinct values across 5,076 lamports |
| cheap-tier config misses by 7 bps | ignored that 28% of cheap pools flip; real gap 0.31pp, and the populations never met |
| cashback "1,159.99 SOL" concentration, 97% | wrong **field** — lifetime accrual, not window activity. In-window: top claimer 12%, no concentration |
| "the literature doesn't measure early-buyer concentration" | **MemeTrans measures it directly** (17pp separation). One paper's silence is not the field's |
| curves hold no real SOL | endpoint artifact — curves are empty *at death*; median **peak** is 1.00 SOL |

**Every one of these was flattering.** That is the tell to watch for.

## 7. Where this sits in the literature (`B21C`)

**The published Solana rug-pull work excludes our population by construction:** *"we exclude
Pump.fun-only tokens that never establish liquidity pools."* Only 2.09% of our tokens ever
established a pool. The EVM frameworks (RPHunter, LROO) define a rug around **liquidity withdrawal**,
and a bonding curve has no pool to withdraw.

**Prior art we replicate, not discover:** early-buyer concentration (MemeTrans, 17pp) and
leakage-resistant evaluation (LROO). **And the label too** — see `B21D`: Liu (2006) named it
**"lock-in risk"** and measures it by counting zero-trading days; Lesmond, Ogden & Trzcinka (1999)
use the flat price that broke our first label design *as their measure*. Amihud (2002), the field
default, is undefined at zero volume — which is exactly why it does not fit here.

**What is genuinely ours, at the right size:** the *venue*, the *mechanism*, and the *population*.
In equities concentration causes illiquidity through **adverse selection** — the market exists but
is expensive. On a bonding curve it causes unexitability through **mechanical counterparty absence**
— the market does not exist at all. The relationship survives a change of mechanism, on a population
every published rug-pull dataset excludes.

**Tested and dismissed:** wallet clustering does not improve the screen. Same-slot co-occurrence on
this venue is **competition, not collusion** — racing snipers, whose presence means the token attracted
attention. Clustering flags 11pp more of the population and catches 0% more of the outcome.

## 8. Method rules earned the hard way

- **A layered guard hides its inner branches** from every fixture the outer layer catches. "No test
  reaches this branch" is never evidence the branch is dead.
- **Undefined is not zero.** An unreadable SMA, an unbought token, an absent state file — each must
  refuse, not default.
- **A key made of field values is not an identity.** It produced three different counts for one
  quantity.
- **Two indirect signals agreeing is not a measurement.** Three separate checks of the cashback unit
  failed because each used the wrong instrument.
- **Label before feature.** Two rug labels were broken — one by observation density, one because a
  bonding curve's price only moves when someone trades, so an untouched token reads as *holding its
  value*.
- **Verify the diagnostic, not just the system.** Twice a checking tool was wrong rather than the
  thing checked.

## 9. Data and tooling that survives this session

| artifact | path |
|---|---|
| BTC daily, Bitstamp 2013–2026, gap-free | `research/data/btc_usd_daily_bitstamp_2013_2026.csv` |
| BTC perp funding, Binance 2019–2026 | `research/data/btc_perp_funding_binance_2019_2026.csv` |
| crash-filter replication (runnable, self-auditing) | `scripts/btc_crash_filter_replicate.py` |
| deadness-screen runner (**pinned, do not edit**) | `scripts/b20b_deadness_screen_runner.py` |
| holder extraction | inside the runner — regenerable, not cached |
| extracted paper text | `research/literature/` |
| **S&P 500 daily 1927-12-30 → 2026-08-14** (^GSPC price, ^SP500TR total return, SPY adjusted) and a spliced 1928→today 3-month cash yield, all sha256-manifested | `research/data/t13_cache/`, built by `scripts/t13_data.py` |
| **risk-shaping harness** — de-risked buy-and-hold nulls (ex-post / ex-ante / exposure-matched), exact circular-shift timing null, paired block bootstrap on maxDD, expanding walk-forward, truncation lookahead audit | `scripts/t13_risk_shaping.py` |
| **survivorship-COMPLETE Binance USD-M perp panel 2020-01 → 2026-07** — 920 symbol folders incl. delisted (`LUNAUSDT`, `FTTUSDT`, `SRMUSDT`), **2,721,204 funding prints**, 634,608 daily perp bars, 620,625 daily premium-index bars, from the public dumps; 63,801 raw archives preserved, three flat panels sha256-manifested, BTC leg reconciled **exactly** against the independent REST pull. Built by `t23_collect.py enumerate\|download\|panel`; gitignored, regenerable in ~11 min | `research/data/t23_cache/`, `scripts/trading_bot/t23_collect.py` |
| **point-in-time cross-sectional carry harness** — survivorship-complete universe, trailing-only liquidity screen, basis mark-to-market, delisting funding-cap tail, by-year T-bill benchmark, declared-trial DSR, two permutation nulls, and a held-out runner that **refuses to run on a failed census** | `scripts/trading_bot/t23_carry.py`, `t23_census.py`, `t23_run.py` |

## 10. Open

- **After T25 — the non-directional shortlist is down to mechanisms that are too small to be a
  trading bot, and the wall is now the same one five times.** T9, T15, T23, T24 and T25 all died on
  a power census costing under a day. Stated as one sentence: **the free data this programme can
  reach resolves effects of 3–15 pp/yr, and every surviving non-directional mechanism offers
  0.4–3 pp/yr.** T25 §7 declines to call the space EXHAUSTED — because it also found **two of
  `NONDIRECTIONAL_INCOME_SHORTLIST.md` §2's data scores are stale**, and a survey with stale scores
  cannot support a claim of exhaustion:
  - **Alpaca DOES serve European, cash-settled SPX index options** (`style: "european"`,
    `tradable: true`, 55 expirations to 2031-12-19, level-3 approved). T21's "✗ 404" is wrong, and
    it was the sole basis for scoring the box spread down on **American early-assignment risk**.
  - **`SOLANA_RPC_URL` returns 200 `ok`**, not the 403 that scored every on-chain mechanism `D = 1`.
  - **And the box was then probed rather than promoted:** at mid the 1-year SPX box lends **+0.37 pp
    over T-bills**; at the four-leg executable price **+0.06 %/yr, 3.65 pp BELOW T-bills**, with a
    cross-strike dispersion at mid (1.57 %→7.02 %) fifteen times the pickup. *Scoping probe, market
    closed at capture.* `research/trading_bot/T25_BOX_PROBE.json`.
  **Recommendation: concentrate on the real-economy track; spend one hour (not a slice) re-measuring
  the SPX box during RTH, because the box is the only remaining claim whose estimand is a RATE LEVEL
  rather than a Sharpe and would therefore pass a power census trivially; do not spend a slice on
  hedged staking or DEX LP.** `T25_RESULT.md` §7.

- **After T15 — the last free, "not power-blocked" candidate is dead on power, and the ranked
  remainder is thin.** §5j. What this seat would do, in order: **(1) M0's C4**, still unperformed
  and now load-bearing for five dead candidates; **(2) start the free forward panels — FINRA short
  interest and the IBKR borrow-fee mirror — as a daily cron today**, because it is the only item on
  the list that *creates* an asset rather than testing one; **(3) #9 short interest (the free
  half), power-censused first** — a bi-monthly cross-sectional sort over 4.6 held-out years is
  ~110 portfolio observations, a T10-shaped Sharpe problem rather than a T15-shaped event-count
  one. **Whether the shortlist is worth continuing at all is an owner scope call**, and after
  seven negatives the question *"is there a different KIND of candidate"* now outranks *"which
  candidate is next"*. `T15_RESULT.md` §10.

- **After T13 — the risk/sizing pivot has been run and it is dead on the frozen gate, so the next
  move is an OWNER SCOPE CALL and there is no technically-obvious successor.** §5i. The pivot's
  premise held (shape claims are the right family) and its hoped-for conclusion did not (shape
  claims have a *worse* power wall than mean claims — one observation per crash, not per day).
  What is left, in the order this seat would rank it:
  **(1) M0's C4**, still unperformed, still the cheapest measurement in the programme and now
  load-bearing for five dead candidates;
  **(2) re-test the crypto crash filter (§5b) against the T13 vol-matched null** — one call to
  `scripts/t13_risk_shaping.py`, and §5b's surviving claim has never faced it;
  **(3) a pre-registered PROSPECTIVE test of the volatility-targeting overlay** — the one direction
  T13 leaves standing on behaviour, but 1990–2026 is burned for it and crashes arrive one per nine
  years, so this is a decade-scale commitment and squarely the owner's call, not a technical one.
  **Recommendation: (1), then put (2) and (3) to the owner together.**

  > **(3) is now BUILT and running in dry-run — T4.** `scripts/trading_bot/t4_forward.py`,
  > pre-registered at `research/trading_bot/T4_FORWARD_PREREGISTRATION.md`, ledger at
  > `research/trading_bot/T4_FORWARD_LOG.jsonl` (opened 2026-08-17). It runs the frozen T13 rule
  > forward on SPY, market-on-close, on the Alpaca **PAPER** account, priced with the T6 per-side
  > model on M0's measured auction rail plus SEC 31 / FINRA TAF by name. **No evidence yet: zero
  > settled sessions, and `certifiable` is a hard `false` in every record.** Two things the
  > pre-registration fixes *before* the accrual, both of which change how it should be read:
  > **(a) the decade-scale estimate was optimistic.** At T13's own per-crash effect (6.00 pp,
  > sd 6.84), 80 % power needs **~10 crashes ≈ 92 years**; three crashes (~27 years) is only the
  > minimum before a *verdict is attempted at all*. **This test is not expected to certify.** Its
  > realistic yield is a live measurement of the auction rail (one observation per fill, daily)
  > and a behavioural check outside the burned window. **(b)** paper order *submission* is gated
  > on `research/trading_bot/T4_OWNER_AUTHORISATION.json`, which does not exist — `paper.py` says
  > owner sign-off precedes any order leaving the process, *paper or otherwise*, and the agent
  > graph's task brief is not that sign-off. Creating that file is the owner's remaining decision.

- **After T10 — the recommendation is the RISK/SIZING PIVOT, and it is an owner scope call.**
  #6 is dead too, and §5h's resolution arithmetic says a fifth directional candidate buys another
  honest negative and no new information: our held-out window cannot certify anything below
  annualised Sharpe **1.3**, and every remaining shortlist candidate sits below **0.5**.
  Recommended order: **(1) M0's C4** — the live paper-order batch, bounded, days not years, and
  now worth 1,414 bp/yr to any rail-dependent candidate; **(2) the risk/sizing work proper**,
  framed as pre-registered *distribution-shape* questions (drawdown control, sizing against the
  measured cost curve, and the overnight-session exposure of §5h evaluated as risk shaping rather
  than as alpha — noting it is not free: ~70 bp/yr even at two legs a day, and levering back to
  full-day volatility pays margin interest that consumes the difference).
  **Alternatives, so the owner chooses rather than ratifies:** #5 CEF discount reversion (last
  large-n directional candidate, but no auction rail and 4–36 bp spreads — run a one-hour power
  census first); or pre-register T7's close-to-open variant as a **prospective forward** test.
  `T10_RESULT.md` §8.
- **Next candidate after T9 — an owner scope call.** #4 is now dead too, so the ranked remainder is
  #3 turn-of-month (15), then #5 CEF discount mean reversion (14), then #7 merger arb (12).
  `T9_RESULT.md` §8 nominates **#3 as ranked but recommends against running it**: ~60 held-out
  month-ends is exactly the failure T9 just made quantitative. Recommendation: **M0 first, then #5**
  (the one remaining candidate with a large n — its problem is friction, which this programme knows
  how to price, not power) — and **run a one-hour power census on both before spending a slice on
  either.** Third option: pre-register T7's close-to-open variant as a **prospective forward** test.
- **M0 still unperformed** — whether an MOC/MOO order actually fills at the official print. T3
  assumed it once; **T7 assumes it twice**; T9 rests on it in the thinnest auctions in the
  programme. **Four dead candidates now rest on it**, and at 0.5 h per leg T7 goes from +0.84 to
  −0.59 bp. **T10 raises the stakes by three orders of magnitude:** at 4.00 of notional traded per
  session, being wrong about the rail by one half-spread costs it **1,414 bp/yr**, and its
  break-even is **0.370 bp per leg**. M0's tape half is done (`M0_AUCTION_FILLS.md`); **C4, the
  live half, is still the cheapest measurement in the programme and no longer the least
  consequential.**
- **Window 2 collection** — **RESTARTED, running detached since 2026-08-25 00:23 CEST** (verified alive at the 15:00 tick; unledgered until then). Supervisor still shows the 08-16 `Q07_stage_failed` at `transaction_bodies` (Chainstack reset); the stage was restarted from stage start in a fresh `b11a_bodies.sqlite` on the free public RPC (4 req/s per-method cap; the Chainstack partial set aside, not resumed). Population 5,484,133 signatures / 173,855 slots; blocks 63.6 % at 15:10, then the `getTransaction` phase needs **≥ 15.9 days at cap → earliest ≈ 2026-09-11, realistic ≈ 09-26**. Liveness ≥ 100k rows/day, kill/relaunch and supervisor hand-back rules pre-declared in `research/b11m_window2/T34_RESTART_2026-08-25.md`. Nothing read from the bodies; `results_unlocked` false.
- **Common-funding-source clustering** — the one wallet-linking heuristic we could not test.
- **Whether window 1's regime generalises** — graduation rate moved 25× in eight months.

## 11. STRATEGIST decisions (durable tick)

- **2026-08-24 — CONVERGENCE: build the forward-data spine.** All 28 agenda tasks are closed and
  owner-approved; three invention programmes ended in honest zeros (256 + 106 formulas; pooled bar
  now predicts zero survivors *ex ante* for any further free-data sweep). Decision: the free-data
  sweep category is **closed**; the programme's remaining free lever is calendar time. Three tasks
  queued with frozen kill-conditions: **T30** daily borrow-fee/availability collector (alone decides
  the replicated preferred-series RV, killed so far only by a *flag*, never a *rate*), **T31**
  scheduled Deribit wing-quote forward collection (the named convexity-dilemma escape), **T32**
  SPX box RTH re-measure (final probe of the last rate-level claim). Standing directive: invention
  ticks stop sweeping burned data; live forward clocks (BASKET1 v8, T4, window-2) continue
  untouched. Owner fork stated, not blocking: pay-for-data remains available if ~4 months of
  collection is unacceptable. Full note: `research/trading_bot/STRATEGIST_2026-08-24.md`.

- **2026-08-24 (03:00 tick, CHUNK B) — T30 borrow collector LIVE; no formula sweep run (directive
  honoured).** The invention tick's valid move under the standing directive was collector-building:
  `t30_borrow_collect.py` now archives IBKR's public `usa.txt` loan-desk feed daily (16:30 CET cron,
  non-t4 line), sha256-manifested under `research/data/borrow_forward/`, with a completeness ledger.
  **First clean snapshot on disk**: 19,676 rows, 377 preferred-SYM rows, **592/602 target-universe
  symbols matched** (join residual 10, as BORROW_FEED_SCOPE §3 predicted). New measured fact:
  the FTP wall is **host-side, not our sandbox** — generic port-21 egress works, `ftp3`/`ftp`
  time out (21 and 990), **`ftp2.interactivebrokers.com` serves the file**; HTTPS republications
  remain blocked. The 30-clean-day kill-condition clock is running; the evaluation protocol is
  frozen in `T30_BORROW_FORWARD.md` (sha256 `df2c31a9…`) and **no pair-level rate will be read
  before day 30**. Honest expectation restated before any data: this is infrastructure and the
  standing both-legs-shortable pre-condition for future RV work, **not a B01 rescue** — B01 is
  insignificant (t 1.48) independent of borrow. T30 marked done in the agenda; T31 (Deribit
  collector) is the next build.

- **2026-08-24 (12:00 tick, STRATEGIST) — Direction confirmed: forward-data spine; finish the
  spine TODAY, then hold the line.** Review of state: all three invention programmes closed at
  honest zeros (the 08-23 master's final synthesis is **106 formulas, 3/3 themes noise, 0
  survivors** — the interim "queued survivor" in the commit message died in the final synthesis);
  T30 is LIVE and clean (1/1 days, cron installed, day-30 borrow gate lands ~**2026-09-22**);
  T31 and T32 are the only open tasks. Decision — no new direction, no new tasks; the single most
  promising direction remains the one already frozen: **make the two forward panels exist and let
  calendar time run**, because it is the only lever left that costs zero dollars and zero
  multiple-testing budget. Execution order set in the agenda: **(1) T31** Deribit wing-quote
  collector, built at today's 15:00 CHUNK B tick on the T30 pattern (snapshot + cron + manifested
  ledger in one bounded tick); **(2) T32** SPX box RTH probe, launched by the same tick as a
  **detached** background capture starting 15:30 CEST (today is a normal US trading Monday) that
  captures ~1h, then computes and writes its own verdict artifacts. Kill-conditions unchanged and
  restated: T30 day-30 borrow gate; T31 ≥95% clean days over 30, convexity pre-registration no
  earlier than +120 days; T32 executable-below-T-bills = box permanently dead, no fourth probe.
  **What would prove the direction dead:** both collectors mature and every pre-registered design
  on them dies at the honest bars — then the pay-for-data-or-stop fork goes to the owner as one
  decision. Ops flag for the owner (observed, not touched): three non-programme crontab lines run
  `/tmp/battery-check`, `/tmp/updates-check`, `/tmp/posture-check`, and **none of those files
  exist** — they fail silently every run; either dead leftovers to remove or something that should
  live outside `/tmp`.

- **2026-08-24 (15:00 tick, CHUNK B invention) — No sweep run (directive honoured). The
  forward-data spine is built: T31 DONE, T32 LAUNCHED.** Valid invention work under the 00:00
  directive is collectors and new data sources, so this tick built the second collector and fired
  the last probe instead of buying zero #4. **T31** (`t31_deribit_collect.py`): Deribit public REST
  only — full BTC/ETH chain via `book_summary`, order-book enrichment (size, bid/ask IV, exchange
  greeks) for every DTE ≤ 14 instrument, plus a cumulative settlement-print ledger
  (`delivery_prices.json`, 40 days back-filled) so expiry outcomes are reconstructable. First clean
  snapshot on disk: **1,752 rows, 332/332 near-expiry enriched per coin, sha256 `c8cee19f…`**, 112 s.
  Written in the Tardis column layout; `deribit_wing_estimator.py` reads it unchanged (that run is
  a **format check, not a result** — the convexity pre-registration is frozen at ≥ +120 days,
  ≈ 2026-12-22). Cron installed at 02:15 local = 00:15 UTC to match the 9 historical samples'
  clock; collector gate (≥ 95 % clean) lands ≈ 2026-09-23. Protocol + honest expectation in
  `T31_DERIBIT_FORWARD.md` (sha256 in `.sha256`). **T32** (`t32_box_rth.py`) launched as a detached
  process: waits for 13:30 UTC, 13 quote snapshots over 60 min, then computes and writes
  `T32_BOX_RTH.json/.md` itself. Protocol frozen before any RTH quote was read (primary expiry
  2027-08-20; session-median of per-snapshot median executable four-leg rate vs live DTB3; p90 is
  context only; kill = executable below T-bills, no fourth probe). Preflight validated the math
  against T25 on Friday-close quotes: 1y **mid 4.37 % / executable 2.76 %** (T25 overnight
  4.08 / 0.06), 5,521 pairs vs T25's 5,442 — same estimand, and already **−0.95 pp vs T-bills at
  the tightest quotes the closed market offers**, so the honest prior for the RTH read is death.
  The 18:00 tick reads the verdict. After that the spine is complete and ticks hold the line:
  keep the T30/T31 ledgers honest, run no free-data sweeps, read no gated number early.

**2026-08-24 21:00 CEST — PREDMARKET tick (chunk D, durable supervisor).** Pulled 4,398 open
politics markets (4,053 selectable; 3,797 Polymarket / 256 Kalshi). Froze **4 estimates**, all on
20–70-day horizons so they can actually feed the N_min = 50 gate (the 6 prior estimates all resolve
≥ 2026-12-31): Trump Nobel 2026 (`637002`, 2.15c → **0.6 %**, side no), Zelenskyy Nobel
(`637011`, 4.65c → **1.5 %**, no), AfD plurality in Berlin 20 Sep (`789953`, 9.45c → **3.5 %**, no),
Becerra CA governor (`628941`, 95.15c → **97.5 %**, yes). Each thesis names a structural reason
and its falsifier; ledger `PREDMARKET_PREREGISTRATION_LOG.jsonl` (sha `9699…`, `26da…`, `f0f1…`,
`f5a2…`). **4 abstentions**, one of them instructive: the Duma "United Russia *gains* the most
seats" market at 72c vs "*wins* the most seats" at 98.8c looked like a cross-market mispricing;
reading the criteria showed it resolves on **net seat gain vs pre-election** — a different question,
no edge. Also abstained: CA billionaire wealth tax (cannot verify qualification/polling in-tick),
the Iran/Hormuz live-news cluster + SC runoff, and the Sweden/Nobel sub-1.5c tails (< 1 pt
disagreement, same rule as the 2028 cluster). Tracker: **0/50 resolved, 10 open, kill ALIVE**.
Honest expectation unchanged: the four new reads are mostly tail-shading against longshot premium;
the Brier gain per market is tiny and a verdict needs many mid-priced resolutions, not these.
First resolutions land 13–20 Sep (Sweden/Berlin), then 9 Oct (Nobel), 3 Nov (CA).

- **2026-08-25 (00:00 tick, STRATEGIST) — Spine complete; T32 DEAD; direction CONVERGED into its
  waiting regime and extended into the goal universe (T33).** Verified on disk, not from memory: T30
  1/1 clean (cron fired 08-24 and correctly skipped; day-1 snapshot is the pre-market 03:08 CEST manual
  fetch, days 2+ are 16:30 CEST intraday stamps — recorded before any rate is read); T31 1/1 clean, first
  *cron* run 02:15 today still unverified; **T32 SPX box: DEAD PERMANENTLY** — 13/13 clean RTH snapshots,
  primary 2027-08-20 session-median executable **2.958 % vs DTB3 3.71 % = −0.75 pp** (mid +0.61 pp
  unreachable at four legs; T25 closed-market −3.65 pp, preflight −0.95 pp, same sign three times; no
  fourth probe) — **the last rate-level claim in the programme is closed and goes to the dead ledger**;
  BASKET1 clock is **advancing by design, not stuck** (runner logs only sessions past Alpaca's free-tier
  recent-SIP embargo; 08-24's row lands 08-25/26; untouched per the 08-24 hard rule); T4 untouched (7 rows).
  **Discipline failure recorded:** window-2 collection has been quarantined (`Q07_stage_failed`,
  `transaction_bodies`, RPC reset) since 08-16 while §10 said "running" — corrected above. **Decision:**
  no pivot. The free lever is still calendar time, so make the waiting time collect *more decisive* data
  in the *goal* universe: **T33** daily Alpaca US-options wing-quote forward collector (14 liquid
  ETF/single-name underlyings, 15:45 ET snapshot, full chains with bid/ask — the endpoint T32 just proved
  chain-wide under the paper keys; kill ≥ 95 % clean/30 days; no strategy number before +120 days ≈
  2026-12-23; convexity design pre-registered jointly with T31 so both universes share one bar). Honest
  expectation stated first: the variance premium is real (T21 §4b, +4σ), so bought convexity has negative
  carry by default and survives only via a trigger that pays its multiple-testing cost — the collector
  makes the claim testable, not likely. Rejected alternative: a design on free expired-OPRA *daily bars*
  (no bid/ask → prices a statistic, not the claim). Also queued: **T34** window-2 stage restart (detached,
  never in-tick) and **T35** hash-pinned T30 day-30 evaluator + joint convexity pre-registration written
  now, opened in December. Kill-dates: T30 ≈ 09-22, T31 ≈ 09-23, T33 ≈ 10-07, basket per-leg N_min=40
  ≈ mid-Oct, convexity ≈ 12-22; T30 kills preferred-RV **and** both convexity designs die → EXHAUSTED →
  pay-for-data-or-stop fork to the owner. Full note: `research/trading_bot/STRATEGIST_2026-08-25.md`.

- **2026-08-25 (03:00 tick, CHUNK B — INVENTION) — No sweep run (category closed); the tick's valid
  invention work was the queued collector: T33 BUILT.** `scripts/trading_bot/t33_us_options_collect.py`
  forward-collects full US option chains (bid/ask/size/quote-ts, last, IV + greeks as served, day bar,
  underlying spot) for 14 liquid ETF/single-name underlyings (`SPY QQQ IWM TLT HYG GLD XLE XLF NVDA TSLA
  AAPL AMZN MSFT AMD`, **frozen before the first snapshot, none trimmed**), every expiry ≤ 45 DTE plus the
  next two monthlies, one capture per trading day at **15:45 ET** from the free Alpaca snapshots endpoint
  T32 proved. Off-hours format check (2026-08-24 21:03 ET, not ledgered): SPY 6,934 contracts / 17 expiries /
  9 pages, AMD 3,730 / 12 / 6, both monthlies resolved, IV+greeks served on 74 % / 43 % of rows — bid/ask
  (what a bought-wing claim is priced on) is complete on the two-sided core. Cron installed on a non-t4 line
  at **20:45 local** with the script waiting to 15:45 ET — a deliberate change from the draft 21:45, because
  during the US/EU DST-mismatch weeks (10-25 → 11-01, 03-14 → 03-28) that clock lands at 16:45 ET, after the
  close. Clean-day rule in code (market open; all 14 returned; ≥ 200 contracts each; ≥ 70 % rows two-sided
  and stamped on the capture ET date); market-closed days ledgered separately; sha256 manifest; protocol
  `research/trading_bot/T33_US_OPTIONS_FORWARD.md` pinned with its `.sha256` (doc + script). **Frozen
  rules restated:** collector gate ≥ 95 % clean over the first 30 trading days (≈ 2026-10-07) counting
  silent cron deaths as failures; **no strategy number read before ≈ 2026-12-23**; the test is the joint
  T31/T33 convexity pre-registration (T35), one bar and one multiple-testing cost for both universes.
  Honest expectation written first: the variance premium is real (T21 §4b), so bought convexity is dead
  by default here too; this panel makes the claim priceable, not likely. First snapshot lands by cron
  **today 15:45 ET**; T33 is `running` until the 08-26 00:00 tick verifies 1/1 clean. Also verified this
  tick: **T31's first cron run (02:15 local) was clean — ledger 2/2**; T30 unchanged 1/1 (next run 16:30).
  Nothing killed, nothing promoted; basket untouched; no gated number read.

**2026-08-25 09:00 CEST — PREDMARKET tick (chunk D, durable supervisor).** Pulled 4,574 open
politics markets (4,219 selectable). Froze **4 estimates**, all on one deliberately *structural*
thesis (base rates / institutional arithmetic, not a news read, since the supervisor's world-knowledge
is stale): Trump out before 2027 (`666861`, 6.5c → **3 %**, actuarial 128-day mortality + no removal
path; criteria exclude temporary 25th-Amendment transfers), Putin out by 31 Dec (`560317`, 7.5c →
**2.5 %**), Trump impeached by end-2026 (`568116`, 2.4c → **0.5 %**: the House stays Republican until
3 Jan 2027 whatever the midterm says), Pope Leo XIV Nobel (`637003`, 3.05c → **1 %**: no sitting pope
in 125 years). Ledger shas `560c…`, `45fd…`, `98f0…`, `c0a7…`. **3 abstentions**, two of them
data-killed rather than skipped: (i) CDU most seats in Sachsen-Anhalt at 0.65c looked cheap on the
2021 polling-miss precedent, but the live Insa 10-Aug poll is AfD 42 / CDU 22 — a 20-pt gap — so the
disagreement fell under the 1-pt rule; (ii) the Le Pen 32c / Bardella 2.6c pair is coherent with the
7-Jul appeal ruling (ban shortened, eligible ~31 Mar 2027, cassation pending), no cross-market
mispricing. **Process note:** on 2026-08-24 21:12 the tick re-froze `567621`/`703257`/`997488` as
duplicates of the 07:10 estimates; duplicate freezes are correlated observations and must not count
toward N_min = 50 — future ticks must skip markets already OPEN in the ledger. Tracker: **0/50
resolved, 17 open (14 distinct markets), kill ALIVE**. Earliest resolutions: Sachsen-Anhalt 6 Sep
(none frozen), Berlin 20 Sep, Nobel 10 Oct, then the year-end block.

- **2026-08-25 (12:00 tick, STRATEGIST) — Direction unchanged and in its waiting regime; ledgers
  verified, no faults, two process facts recorded.** Verified on disk: **T31 2/2 clean** (first cron run
  02:15 CEST clean: 1,772 rows, BTC 342/342 + ETH 340/340 enriched); **T30 1/1** (today's 16:30 run not
  yet due); **T33** no ledger yet — correct, the first scheduled capture is today 15:45 ET and the
  offline `--plan` is sane (window 08-25→10-09, monthlies 10-16/11-20, 14 underlyings unchanged, in-script
  wait 3,600 s < the 7,200 s refuse bound); **BASKET1 clock is advancing** — at 09:00 today the runner
  logged session **2026-08-24, the first true post-freeze10 session** (log 2 → 3 rows; the 08-25 00:00
  embargo prediction held), 12:00 correctly `no_session`; frozen file untouched (sha `d53b4fe4…`);
  row-level leg numbers exist and were **not read** (per-leg N_min = 40). T4: 7 rows, last session 08-24,
  untouched. Window-2 still quarantined (T34 at 15:00). **Facts recorded so no tick re-derives them:**
  (1) the collector gates count days differently — T30/T31 count *calendar* days (weekend IBKR files are
  stale desk data, ledgered clean by design), T33 counts *trading* days reconciled against the exchange
  calendar; gate dates therefore T30 ≈ 09-22/23, T31 ≈ 09-23, T33 ≈ 10-07; (2) BASKET1's inception
  session 2026-08-24 is now a logged fact — settlement rows land 1–2 sessions late by design. Decision:
  no pivot, no new task, order confirmed **T34 (today 15:00, bounded: detached restart or `blocked`,
  no spend) → T35 (08-26 03:00) → pure waiting**; the 08-26 00:00 tick must verify T33 1/1 and flip it
  `running → done`. Kill-condition for the direction unchanged and dated (T30 ≈ 09-22 and both convexity
  designs ≈ 12-22 must *both* die before the pay-for-data-or-stop fork goes to the owner). Nothing
  killed, nothing promoted. Full note: `research/trading_bot/STRATEGIST_2026-08-25_1200.md`.

- **2026-08-25 (15:00 tick, CHUNK B — INVENTION) — T34 verified: window-2 stage restart is ALIVE (found
  already running, ledgered now); invention round = three angles killed at the desk, 0 formulas run.**
  Verified on disk: a detached restart of `transaction_bodies` was launched **2026-08-24T22:23:34Z** (00:23 CEST)
  from an interactive session — not by a tick and absent from every ledger until this note. It runs
  `research/b11m_window2/run_free_decode.sh` (bash restart loop, checkpoint-resumable) on the **free public
  Solana RPC** at the endpoint's per-method cap of 4 req/s, into a **fresh** `b11a_bodies.sqlite`; the 387 MB
  Chainstack partial was set aside as `.chainstack-partial.sqlite`, *not* resumed — the watcher's "a partial
  artifact is not a checkpoint" rule holds. Liveness: attempt 1 still running after 14.8 h, zero transport
  failures, `blocks 110,600 / 173,855` (63.6 %) at 15:10, DB mtime advancing. **Honest ETA:** blocks done ≈
  23:40 tonight; then **5,484,133 `getTransaction` calls ≥ 15.9 days at cap → earliest 2026-09-11, realistic
  ≈ 09-26** (Chainstack at 14 req/s would be ≈ 4.5 days but is the endpoint that reset — owner call, not taken).
  Pre-declared rules: ≥ 100k `raw_transaction` rows/day from 08-26; no advance over one tick with the child
  alive → kill the child only (loop relaunches on checkpoints); loop dead → relaunch verbatim; > 20 failed
  attempts/day → BLOCKED, no spend; at rc=0 → supervisor hand-back (re-attest with reason, `SOLANA_RPC_URL`
  = free endpoint, `b9d` no-op verification pass writes the receipt, then `decode_and_reserves` → gates).
  Disclosed: an **uncommitted** `b9d_transaction_bodies.py` patch (OSError added to the retryable tuple — the
  exact escape that killed the Chainstack run); `b9d` is not hash-pinned; owner to commit. T34 `pending →
  running`. Invention (per the no-new-free-sweeps order): three original angles were pre-registered on the
  desk and checked against the ledger *before* any data read — CEF tender/rights convergence (dead:
  `INVENT_0822C_cefdeep` §8e), term-CEF d/T pull-to-NAV (dead: `DEEPMINE_CEFNAV` X01 0.02/0.05), SPAC trust
  tether (not free + below-T-bill by construction: `INVENT_0823_exotic`). **0 formulas, 0 numbers, 0
  survivors, no new dead-ledger entries.** One durable output → **T35**: cost the ≤ 3 convexity trigger
  designs on the free DoltHub options panel (347 weekly chains with bid/ask, 2020–26) as the *design*
  window so T31/T33 become a pure held-out; caveats carried (no OI, front-month only, EOD-stamp Clause 2).
  Record: `research/trading_bot/INVENT_0825B_desk.md`. Basket untouched; T4 untouched; nothing killed,
  nothing promoted. Next: 08-26 00:00 STRATEGIST verifies T33 1/1 **and** window-2 row advance; 03:00 = T35.

- **2026-08-25 18:00 CEST (NEWSDESK tick, durable supervisor).** First NEWSDESK1 resolution is on the
  ledger: the 23 Aug XOM long (oil bid on Iran headlines) stopped at 161.80 → **−1R** (null short would
  have paid; "edge vs null −1.985R", n=1, **not evidence**, kill-switch needs n≥30). ETH long still open
  (2476 vs 2439.65 entry; stop 2340 / target 2690; expires 26 Aug 17:00 UTC), untouched by rule. This tick:
  390 pulled / 60 ranked, no 8-K ranked; one discrete catalyst checked and rejected — Boeing "$131B F-15"
  award, free 60m bars show Mon close 210.44 → 211.82 (+0.7%) after a −6.5% week, i.e. the tape already
  read it as a multi-year IDIQ ceiling; no information advantage, no plainly-stateable asymmetry →
  **abstention logged** (4th consecutive; ledger `research/trading_bot/newsdesk/`). Status: resolved 1/30,
  NO VERDICT, kill ALIVE, open 1. Running tally for the instrument's honest prior ("free headlines are
  priced within seconds"): 2 proposals, 1 resolved at −1R, 4 abstentions. Basket untouched; T4 untouched;
  agenda untouched (not a STRATEGIST tick). Next: 08-25 21:00 = PREDMARKET; 08-26 00:00 STRATEGIST reads
  the ETH resolution (due 17:00 UTC 26 Aug) and T33/window-2 progress.

- **2026-08-25 21:00 CEST (PREDMARKET tick, chunk D, durable supervisor).** Pulled 2,588 open
  politics markets (2,432 selectable; Kalshi returned 0 this pull, Polymarket only). Applied the 09:00
  process rule (skip markets already OPEN in the ledger) and, new this tick, filtered to **≤120-day
  closes** — the 17 prior estimates almost all resolve 31 Dec 2026 or later, so the N_min = 50 clock
  was not actually running. Froze **10 estimates on 10 distinct markets**, every one a *structural*
  read (seat arithmetic / partisan lean / FPTP geography / fixed candidate fields), not a news read:
  Duma seat buckets `1125100` <280 (4.2c → **1.5 %**), `1125106` ≥355 (8.5c → **14 %**), `1125105`
  340-354 (24.5c → **29 %**) — the crowd anchors on 2021's 324 while ~200 SMDs + a mid-50s list share
  centres on ~335-345; Alaska Senate Peltola `634976` (61c → **50 %**, R+8 state, unscandalled
  incumbent, midterm lift gets her to even not to favourite); Quebec PQ `789407` (70.5c → **77 %**) and
  CAQ `789406` (16.5c → **10 %**, FPTP seat efficiency vs Montreal-concentrated PLQ, post-Legault CAQ);
  Renan Santos 2nd in Brazil R1 `1365860` (4.3c → **2 %**, registration closed 15 Aug, Flávio priced
  87.5c for 2nd); AfD most seats MV `1364103` (87.5c → **85 %**, Schwesig 2021 +9 polling undershoot);
  Andersson next Swedish PM `1193094` (88.5c → **86 %**, 2022 late-closing precedent + resolves on
  *assuming office*); Hilton CA governor `628940` (4.75c → **2 %**, consistent with the 24 Aug Becerra
  97.5 freeze). Ledger shas `a8a6… ed52… a950… 2567… 8316… 0c9d… 208c… f5a9… 0909… bf29…`; all 10
  clear the cost floor (edges 2.3-11 pt vs 0.05-1 pt), 3 hypothetical-yes / 7 hypothetical-no.
  **2 abstention records** covering the Iran ceasefire/blockade ladder (live timeline unverifiable
  in-tick, as on 24 Aug), Berlin CDU/Linke (implies mid-2026 polling I lack), NATO×Russia clash
  (drone-shootdown criteria ambiguity), Brazil top-line, Nobel tails, Canadian mayoral, Latvia,
  Bulgaria, the Duma net-gain family and the Fed-funds buckets. Tracker: **0/50 resolved, 27 open
  (24 distinct markets), kill ALIVE**. Resolution calendar now front-loaded: Sweden 13 Sep (+formation),
  Duma/MV 20 Sep, Berlin 20 Sep, Quebec 5 Oct, Brazil 4 Oct, Nobel 9 Oct, US 3 Nov — the first ~12
  paired Brier observations arrive inside 10 weeks. Honest note: the supervisor's world-knowledge is
  stale to early 2026, so every number above is a base-rate/arithmetic prior and should be *expected*
  to lose to the crowd on markets where 2026 polling moved; that is exactly what the Brier comparison
  is for. Basket untouched; T4 untouched; agenda untouched (not a STRATEGIST tick). Next: 08-26 00:00
  STRATEGIST reads the ETH newsdesk resolution (due 17:00 UTC 26 Aug) and T33/window-2 progress.

- **2026-08-26 (00:00 tick, STRATEGIST) — Direction unchanged; one fault found and fixed on day 1:
  T33's first capture FAILED on its own freshness rule.** The 08-25 15:45 ET capture was mechanically
  complete (14/14 underlyings, 37,883 rows, 0 transport errors, 71 s) and ledgered `failed` because
  `HYG fresh 0.626` and `XLE fresh 0.700` (795/1136 = 0.69982) sat under the 70 % floor. Inspecting
  the partial (integrity counts only, no price/IV read): HYG's staleness is **structural** — 0.647
  even within 15 % moneyness, strikes 45–105 on spot 79.9; XLE carries 124 dead-series rows stamped
  2025-12-04. The v1 rule would therefore have failed **every** trading day and killed the collector at
  the day-30 gate by construction — the BASKET1-re-freeze bug in a new coat. **Fix taken** under the
  protocol's own "fix/kill" branch, dated and re-pinned (`T33_US_OPTIONS_FORWARD.md` § Amendment v2;
  doc `053c4d18…`, script `2cbe5ebd…`, v1 hashes kept as audit trail): freshness is now a
  per-underlying **eligibility flag** (ledger `fresh_fail`, manifest `fresh_ok`), clean-day = open +
  14/14 + ≥ 200 contracts; eligibility rule for the December design written now (fresh_ok on ≥ 95 % of
  clean days, evaluated at the ≈ 10-07 gate; **HYG expected excluded**, XLE/XLF at risk). 08-25 stays
  `failed`, its partial excluded from the panel by default (T35 may admit it explicitly, before
  opening); the 30-day gate now has **zero slack**. Capture/universe/clock/columns unchanged. T33
  **stays `running`** → `done` only on the first clean v2 day (08-26, verified 08-27 00:00). Other
  clocks verified: T30 **2/2**, T31 **2/2**, BASKET1 log 3 rows + frozen sha `d53b4fe4…` untouched,
  T4 8 rows untouched, window-2 **at the transactions stage** (`raw_transaction` 43,032 at 00:01,
  attempt 4 live; the ≥ 100k/day rule reads first 08-27 00:00), newsdesk ETH open (resolves 17:00 UTC
  today), predmarket 0/50. Order: **T35 at 03:00** (must restate the eligibility rule and rule on the
  08-25 partial) → waiting. Kill-condition unchanged (T30 ≈ 09-22 and both convexity designs ≈ 12-22
  must all die before the owner's pay-or-stop fork). Method rule earned: a data-quality threshold is
  never a day-kill on a forward collector unless proven attainable on the *weakest* name before
  freezing. Full note: `research/trading_bot/STRATEGIST_2026-08-26_0000.md`.

- **2026-08-26 (03:00 tick, CHUNK B / INVENTION) — T35 DONE: both evaluators pinned before their
  panels mature; no sweep run, zero forward-panel numbers read.** (a) `t30_borrow_evaluate.py`
  (sha `28e525c3…`) is the T30 day-30 rule as code: `--evaluate` refuses below 30 clean days (no
  override) and on any pin drift; the B01 record turned out to hold no per-pair edge, so the 113
  same-issuer preferred pairs were rebuilt deterministically from the frozen 0822 cache (count
  reproduced exactly) into `T30_B01_PAIR_EDGES.json` (`acacbfa5…`, rule uses full-sample gross
  bp/active-week; aggregate only: median 37.2). Day-1 format check, counts only: **107/113 pairs
  have both legs in the IBKR file**, the other 6 count NOT borrowable by protocol. T30 doc amended
  and re-pinned (`7366f5d5…`, prior `df2c31a9…` kept). (b) `CONVEXITY_PREREGISTRATION.md`
  (`5bded3ea…`), the joint T31/T33 test: ~15-delta strangle, 3–10 DTE, bought at ask, **held to
  expiry** (contractual convexity, no stop), cluster = (underlying, expiry); three designs stated
  once — D1 IV-under-realised (ATM IV / 20-snapshot RV ≤ 0.90), D2 aftershock (|1-day return| ≥
  2.5 sd), D3 IV-compression (ATM IV ≤ p20 of trailing 40) — plus C0 unconditional as a
  non-promotable control; bar = cluster-robust t ≥ 2.5 AND > 99th pct of a size-matched
  random-entry placebo AND top cluster ≤ 40 % of gains AND N_min 40 clusters; first reading
  **2026-12-23**, one extension 2027-04-22, all-dead ⇒ escape CLOSED ⇒ owner pay-or-stop fork.
  T33 eligibility restated (fresh_ok ≥ 95 % of clean days, written on the full 14-name universe);
  **08-25 T33 partial EXCLUDED, T31 day 0 EXCLUDED.** Design-window prior on the free DoltHub
  panel (`CONVEXITY_DESIGN_COSTING.json`, 5,707 marked strangles, 335 weekly clusters, US large
  caps 2020–26): unconditional 15-delta ~28-DTE strangle **−31.8 % of premium per 2-week hold,
  t −19.2**; D1/D2/D3 −26.2/−28.6/−26.4 % — the triggers claw back 3–6 pp, none flips the sign;
  entry half-spread ≈ 9 % of mid (p75 17–19 %), ≈ 18 pp of the loss is the round-trip spread.
  **Stated expectation, written before the panels open: all three designs die in December.** One
  method note earned: the Dolt cache lists only ~3 expiries per name, so a ~14-DTE contract is
  unmarkable a week later — costing had to use the ~28-DTE tenor marked at ~14 DTE. Basket
  untouched; T4 untouched. Remaining build item: pin `convexity_evaluate.py` before 2026-12-01.
  Next: STRATEGIST 12:00 verifies T33's first v2 day (08-26) and the ledgers; then pure waiting.

- **2026-08-26 (12:00 tick, STRATEGIST) — Direction unchanged and converged; waiting regime; no
  faults; one process move.** Clocks verified read-only: T30 **2/2**, T31 **3/3** (08-26: 1,782 rows,
  BTC 356/356 + ETH 328/328 enriched), T33 0/1 pre-v2 (08-25 stays `failed`; pins `053c4d18…` /
  `2cbe5ebd…` intact; first v2 capture today 15:45 ET, verified 08-27 00:00), BASKET1 log **4 rows**
  (session 08-25 — clock advancing) + frozen sha `d53b4fe4…` untouched, T4 8 rows untouched,
  convexity prereg `5bded3ea…` intact, window-2 `raw_transaction` **117,039** at 12:00 vs 43,032 at
  00:01 ≈ **148k/day** (pre-read; official ≥ 100k/day read 08-27 00:00). Window-2 fault recorded, not a
  fault: attempts 4–7 each died rc=1 on `FreezeViolation: finalized getTransaction returned null` —
  a different signature each time, the runner raises rather than skips, the loop relaunches and the
  signature is re-fetched → transient nulls from the public pool, no population loss; 4/day vs the
  20/day BLOCKED rule; raw-phase ETA revised to **≈ 10-01** (min 09-11). Process move: **T36 added**
  — pin `convexity_evaluate.py` at the *next* CHUNK B tick, while the panel is empty (T33 0 clean
  days), so the evaluator is blind by construction; "before 12-01" would let it be written after
  three months of quotes had been integrity-checked — the basket-re-freeze / T33-v1 class of bug
  again. PREDMARKET carry-over: scorer must dedupe by `market_id` keep-first (703257 / 997488 /
  567621 double-frozen 08-24). Kill-conditions unchanged (T30 ≈ 09-22 AND both convexity designs
  ≈ 12-22 must all die before the owner pay-or-stop fork; a second failed T33 day = one fix tick, a
  third kills the US-options escape). Full note: `research/trading_bot/STRATEGIST_2026-08-26_1200.md`.
- **2026-08-27 (00:00 tick, STRATEGIST) — Direction unchanged and converged; waiting regime; no
  faults; no pivot; no new sweep.** Clocks verified read-only: **T33 first v2 day 08-26 = CLEAN**
  (38,585 rows, 14/14 underlyings, `fresh_ok` 12/14 — HYG 0.631 / XLE 0.680 recorded in `fresh_fail`;
  08-25 stays `failed`; pins `053c4d18…` / `2cbe5ebd…` intact) → **T33 build marked done**; day-30
  gate ≈ 10-07 keeps zero slack. T30 **3/3**, T31 **3/3**, BASKET1 log 4 rows + frozen sha `d53b4fe4…`
  untouched, convexity pins `505072ce…` / `ba6bb268…` intact, NEWSDESK 2/30, PREDMARKET 0/50 (34 open).
  **Window-2 official ≥ 100k/day read: PASS** — `raw_transaction` 188,807 at 08-26 23:59 vs 43,032 at
  00:01 ≈ **146k/day**; remaining 5,295,326 signatures → raw phase ≈ **10-02**. Margin thinning,
  recorded not acted on: **12 failed restarts on 08-26** (attempts 4–15; mode shifted from null
  returns to `HTTPError` transport failures) vs the 20/day BLOCKED rule; rule NOT loosened. Expectation
  update from the collector ledger only: HYG **and XLE** now expected excluded at the 10-07
  eligibility gate, XLF marginal (rule unchanged, evaluated by the pinned evaluator). Ranked direction
  restated with dated kills: (1) preferred-series RV gated only on borrow — T30 day-30 read ≈ 09-22,
  dead if < 10 of 113 pairs have both legs borrowable at fee < measured gross edge; (2) B20B window-2
  OOS (memecoin, not goal universe) ≈ 10-02 raw → pinned gates; (3) bought convexity, prior all-dead,
  12-23. Owner pay-or-stop fork only after (1) AND (3) both die. No new tasks; every candidate "chunk"
  was a sweep against a closed family or a basket leg. CHUNK B guidance: one round only on a family
  absent from the dead ledger with a published synchronous tether or forward panel, else a one-paragraph
  abstention. Full note: `research/trading_bot/STRATEGIST_2026-08-27_0000.md`.

## 2026-08-26 09:00 CEST — PREDMARKET tick (supervisor, CHUNK D)
- Froze 6 estimates (file: `research/trading_bot/predmarket/proposals/2026-08-26T09_supervisor_estimates.json`; hashes in `PREDMARKET_PREREGISTRATION_LOG.jsonl`): midterms-as-scheduled (q .99 vs .9605), Xi-out (q .012 vs .0495), Modi-out (q .025 vs .0705), Erdoğan-out (q .02 vs .055), UNRWA Nobel (q .015 vs .043), and one relative-value NO on the "Nothing Ever Happens: 2026" parlay (q .75 vs .815 — the parlay trades ABOVE what the crowd's own 13 component markets imply, ~0.60). Logged one explicit abstention covering all US–Iran/Hormuz deadline ladders (post-cutoff news), the Senate-control coin-flip, Sachsen-Anhalt, Tyler Robinson, Venezuela, and every 2028 longshot. Tracker: 33 open / 0 resolved → NO VERDICT, kill ALIVE.
- Criteria trap worth remembering: the Russian Duma "most seats" trio (1130012/1130016/1130015) resolves on seats **gained vs 2021**, not seats held — United Russia at 0.715 is not a mispricing. Abstained.
- Ledger hygiene flag for the next STRATEGIST tick: market_ids 703257 / 997488 / 567621 were each frozen twice on 2026-08-24 (open list double-counts them). Append-only ledger, so not corrected here; the scorer should dedupe by market_id (keep first freeze) before any Brier verdict.
- Honesty note: 5 of 6 estimates are actuarial/statutory longshot fades — the same family prior ticks logged. The tracker's verdict rests on whether that family beats the crowd after fees; it cannot be known before markets resolve (first resolutions: Sachsen-Anhalt 09-06, Duma 09-20, Brazil 10-04, Nobel 10-10).

## 2026-08-26 15:00 CEST — CHUNK B tick (supervisor): T36 evaluator pinned + one invention round (honest zero)

**T36 — DONE. The December convexity reading is now fully mechanical and provably blind.**
`scripts/trading_bot/convexity_evaluate.py` (sha256 `ba6bb268…b12504`) implements
`CONVEXITY_PREREGISTRATION.md` §2–§7 exactly: D1/D2/D3 + C0 control, ~15-delta strangle on the
nearest 3–10 DTE expiry bought at the ask with fees, held to settlement, `r=(payoff−P)/P`, cluster
`(underlying, expiry)`, ALIVE only on cluster-robust t ≥ 2.5 **and** > p99 of 1,000 size-matched
C0-cluster placebo draws **and** top cluster ≤ 40 % **and** ≥ 40 clusters **and** ≤ 10 % dropped
**and** no universe at t ≤ −2; T33 eligibility = `fresh_ok` ≥ 95 % of the first 30 clean days; T31
day 0 and the T33 08-25 partial are excluded by window + ledger. Pinned on T31 day 3 / T33 day 1
with **zero forward-panel rows read**; developed only against synthetic panels (`--selftest`, 25/25:
null → C0 ≈ −0.70/premium, t −13, nothing ALIVE; planted aftershock → D2 ALIVE t 4.9; one-cluster
windfall → never ALIVE). `--evaluate` refuses before 2026-12-23 (rc 3, verified today), on pin drift
(rc 4), on an existing verdict (rc 5). Amendment A1 (11 mechanical resolutions, no rule change)
appended to the prereg; doc re-pinned `505072ce…`, v1 hash kept as audit trail. `--plan` (counts
only): T31 2 clean in-window, T33 0 clean (first v2 capture 15:45 ET today).
**The programme has nothing left to build before its frozen reads** (T30 ≈ 09-22, T33 gate ≈ 10-07,
convexity 12-23). The standing instruction to future ticks is: hold the line, no new free-data sweeps
against the CEF/RV/intraday families already closed, no basket legs.

**Invention round INVENT_2026-08-26B — CEF NAV-innovation underreaction: DEAD (honest zero).**
Object: decompose the daily CEF discount change into a NAV-driven and a price-driven part and ask
whether only the NAV-driven part (a synchronous *published* tether) predicts the next 1–10 sessions /
1 week. Disjoint from DEEPMINE_CEFNAV (total-Δdiscount fades, raw NAV momentum) and 0822C
(category-relative NAV momentum). 12 formulas, bar √(2 ln 12) = t 2.23 gross at gap-1, tercile L/S
dollar-neutral, ETB short leg, 316 daily-NAV funds (245 sessions) + 248-week panel, permutation
placebo, 11.5 bp half-spread. **The decomposition clause fails with the wrong sign everywhere**
(t_NAV − t_PRC = −0.52 / −1.08 / −0.16 / −3.06): the NAV-driven part is the *weakest* of the three
terms at every horizon; whatever NAV information exists is consumed inside the stamp session
(same-close t 3.69 → gap-1 t 0.97). Frozen shortlist (sha `095e7b61…`) held nothing NAV-shaped;
held-out read once: `D_TOT_k5` gross t 0.05, `W_PRC_1w` t 1.93 but net −30 bp/wk, `W_TOT_1w`
t 1.63 / net −44 bp/wk (M01 in tercile form). ρ1(P&L) > −0.17 throughout (no bounce in the books).
Dead-ledger: NAV-innovation/NAV-momentum at 1 session–13 weeks; total-Δdiscount fade at 1–10
sessions / 1–4 weeks; intra-CEF daily/weekly price reversal. **Do not re-propose.** Caveat recorded:
daily held-out (94 sessions) only powers Sharpe ≈ 3.65, but the NAV terms are centred on zero in
both panels and negative net at any plausible Sharpe — dead on distance-from-zero and cost at once.
Files: `research/trading_bot/INVENT_2026-08-26B_cefnav{_PREREG.md,_DESIGN.json,_SHORTLIST.json,_REVEAL.json,.md,.json}`,
`scripts/trading_bot/invent_0826b_cefnav.py`. Basket untouched; no proposal.

**Next step (single most important):** verify tonight's first T33 v2 capture at the 00:00 tick
(clean or the one bounded fix), then wait. Nothing else is due until 09-22.

## 2026-08-26 21:00 CEST — PREDMARKET tick (supervisor, CHUNK D)
- Pulled 2,538 open / 2,384 selectable; hand-screened the 90 near-dated (close ≤ 2026-11-30), liquid (≥ $20k), non-extreme (0.03–0.97) markets. Froze **1** estimate (file `research/trading_bot/predmarket/proposals/2026-08-26T21_supervisor_estimates.json`, sha `55ab8b9f…`): *Republicans hold < 22 governorships after the midterms* — q .09 vs p .16 on a $49k / 4c-spread book (needs a net −5 for R from a stated baseline of 26; thin-book tail overpricing). Edge .07 vs cost .02.
- **Resolution-text trap logged (worth remembering):** "United Russia GAINS the most seats" (1130012) printed 0.735 on $7.9M and looked like a 20-pt structural mispricing; the text scores the seat **delta** vs 2021, not the winner (the "win most seats" market is at 0.987). Honest number ~0.72–0.78 → no edge → abstained. Lesson: read `resolution_criteria` before forming q; the CLI pull carries it.
- Explicit abstention logged for everything else: Berlin/Latvia/Brazil/Canadian mayoral/Bulgaria (crowd holds post-cutoff polling), all US–Iran ladders + Lyman + NATO–Russia (post-cutoff news), Senate coin-flip, CA billionaire tax, complements of already-frozen positions (would double-count), 2028 sub-1% longshots, Navalnaya Nobel (ledger already long-shot-fade heavy).
- Tracker: **34 open / 0 resolved → NO VERDICT, kill ALIVE.** First resolutions: 09-13 (Sweden PM), 09-20 (Berlin, Mecklenburg-Vorpommern, Duma buckets), 10-04/05 (Brazil R1, Quebec), 10-10 (Nobel), 11-03 (midterm cluster). The 50-resolved verdict cannot arrive before the 11-03 cluster settles; nothing to do but let the clock run. Agenda untouched (not a STRATEGIST tick). Next tick 08-27 00:00 = STRATEGIST.

## 2026-08-27 03:00 CEST — CHUNK B tick (supervisor): invention round INVENT_2026-08-27 parity-implied carry — DEAD, two durable facts

**One fresh angle, pre-registered (sha `abb3c3f5…`), run, dead.** Object never tried before (`grep` put-call
parity / implied borrow = 0 files): the parity-implied forward `F=(C−P)e^{rT}+K` on the free DoltHub weekly EOD
chains (51 mega-caps, 2020-03 → 2026-08) as a *law-published* tether for `S`; implied dividend-plus-borrow
`c = r − ln(F/S)/T`, symbol-demeaned backward. Pre-registered sign long LOW / short HIGH carry, executable fill at
close t+1 → t+6, gross bar weekly t ≥ 2.5 AND > p99 of 1,000 size-matched placebo draws, design 2020–23H1 /
held-out 2023H2–26 gated. **Design F1 t = −2.43 (wrong sign), −25 bp/wk, fails both bars → DEAD; held-out
returns never read.** The near-bar wrong-sign magnitude is the PUT_SLOPE sign-flip trap again; a flipped object
is explicitly not admitted (no ex-ante mechanism, would still fail 2.5, and via the asynchrony channel it is a
late-day-continuation microstructure object — a family `INVENT_0825` closed). F2 (same-print) ≈ F1, so not a
Clause-3 artifact — just noise.
**Durable fact 1 (source property):** the DoltHub option snapshot is stamped BEFORE the 16:00 print — `c_res`
loads on the same-day open→close move with t **5.2** (2020–23) → **14.8** (2023–26), slope 0.08 → 0.32; the lag
has GROWN. T35's "entry marks only" clause is now measured, not assumed. T35/T36 unaffected (forward T31/T33
panels, not Dolt).
**Durable fact 2 (data-acquisition):** the free panel CANNOT measure borrow — cross-sectional IQR of implied
carry 2.1 %/yr vs a quote-noise floor of 1.5 %/yr (ratio 1.4 < 2); median implied carry ≈ dividend yield (0.3 →
0.7 %/yr), borrow ≈ 0 on GC names. The #1 paid-data ask (borrow-availability feed) stands; no free substitute.
Dead-ledger: parity-implied-carry XS (both signs); options-implied borrow proxy; any Dolt object comparing the
snapshot to the same-day close. Files: `research/trading_bot/INVENT_2026-08-27_parity{_PREREG.md,_PREREG.sha256,.md,.json}`,
`scripts/trading_bot/invent_0827_parity.py`. **Basket untouched. No proposal. Agenda unchanged** (no task
promoted/killed — nothing is due before the 09-22 T30 read).
**Next step (single most important):** hold the line — the 06:00 NEWSDESK tick runs as scheduled; the next
STRATEGIST tick should keep the "no new free sweeps against closed families" order and only verify the T31/T33
collectors are still capturing cleanly.

- **2026-08-27 06:00 CEST (NEWSDESK tick, durable supervisor).** Stream 393 pulled / 60 ranked; two discrete
  catalysts, both already realised after the 26 Aug 20:00 UTC close (NVDA FQ2 beat-and-raise + AWS 2M-GPU deal;
  META $18B teen-safety settlement). **Abstention logged** (7th consecutive; ledger
  `research/trading_bot/newsdesk/NEWSDESK_PREREGISTRATION_LOG.jsonl`). Primary reason is PROCESS, not view:
  `entry_model = reference_price_at_freeze`, and at 04:00 UTC the only free reference is the pre-catalyst close
  (NVDA 209.66, META 576.14) — freezing a long there is lookahead in our own favour. Secondary: post-print drift
  on the quarter's most-anticipated earnings is not a 2:1 asymmetry statable in either direction. Status:
  resolved 2/30, NO VERDICT, kill ALIVE, open 0. **Structural note for the next STRATEGIST tick:** the 06:00
  CEST newsdesk tick is systematically unable to act on after-hours catalysts (the only kind the overnight
  stream contains) because the reference price is stale; every 06:00 tick to date has abstained on this or the
  no-catalyst ground. Either the pre-open tick should be re-timed to post-open (≥ 13:35 UTC) so the reference is
  a live quote, or its abstentions should be discounted as uninformative about the agent's read. Do NOT
  re-freeze NEWSDESK_FROZEN.json for this; it is a scheduling question for the owner. Basket untouched.

## 2026-08-27 09:00 CEST — PREDMARKET tick (supervisor, CHUNK D)
- Pulled 2,522 open / 2,384 selectable (2,140 Polymarket / 244 Kalshi). **Tooling note:** `predmarket pull` prints only `--limit` (default 40) markets to stdout and persists nothing; a screen needs `pull --limit 5000 > file`. Hand-screened the 75 near-dated (close ≤ 2026-11-30), liquid (≥ $20k), non-extreme (0.03–0.97), not-yet-frozen markets.
- Froze **1** estimate (file `research/trading_bot/predmarket/proposals/2026-08-27T09_supervisor_estimates.json`, sha `00a224e3…`): *Bernadette Wilson wins the 2026 Alaska governorship* — q .48 vs p .355 on a $167k / 1c-spread book. Mechanism is fundamentals-vs-crowd, not news: the event's price mass says the Aug-18 top-4 is 2 R (Wilson, Bronson) / 2 D (Kreiss-Tomkins, Begich) and the crowd implies P(Democrat) ≈ .50 in an R+8 / Trump +13 state; RCV consolidates into a Wilson-vs-K-T final with Wilson ≈ 85% of the R mass → P(R) .58 × .85 ≈ .49. Confidence .40; stated risk = post-primary polling the agent cannot see. This diversifies a ledger that is otherwise longshot-fade heavy (a "back the fundamentals in a wave year" bet, opposite sign of risk).
- Explicit abstention logged for the other 74, in three classes: (1) crowd holds post-cutoff polling/news — Sachsen-Anhalt AfD majority, Berlin CDU/Linke/Grüne, MV SPD + MV CDU vote-share buckets (that event is internally coherent around an 8–11% mode; the <8% bucket at .275 sits on a 9c spread), Latvia (AS at .53 vs a ~5% cutoff poll = missing coalition/poll info, not a mispricing), Brazil Lula/F. Bolsonaro/PL seats (União-PP federation counting trap), Bulgaria, Vancouver/Toronto/Ottawa mayors, CA billionaire tax, Navalnaya Nobel; (2) every US–Iran blockade/ceasefire/meeting ladder, Hormuz, Bab el-Mandeb, Lyman, NATO×Russia, Russia–Ukraine ceasefire — post-cutoff, and every ladder is monotone and sums correctly (meeting .215 + no-meeting .788; balance-of-power combos ≈ 1.00 with the House/Senate singles), so no structural mispricing; (3) complements/correlates of frozen positions — Dem House, Sullivan AK Senate, Kristersson, Duma 325–339 (agent distribution ~.33–.38 = crowd .33; event already frozen 3×), governorships 24–25 (our frozen <22 distribution implies ~.31 vs .28), ACA-credits×House combo (credits leg already determined; price = P(D House)).
- Tracker: **35 open / 0 resolved → NO VERDICT, kill ALIVE.** First resolutions unchanged: 09-13 Sweden, 09-20 Berlin/MV/Duma, 10-04/05 Brazil R1/Quebec, 10-10 Nobel, 11-03 midterm cluster (now incl. AK governor). Scorer still must dedupe by `market_id` keep-first. Agenda untouched (not a STRATEGIST tick). Next tick 08-27 12:00 = STRATEGIST.

## 2026-08-27 12:00 CEST — STRATEGIST tick (supervisor, CHUNK A)
- **Direction unchanged and converged; waiting regime; all ledgers verified, no faults.** T30 3/3 clean (day 4 due 16:30); T31 **4/4** clean (08-27: 1,774 rows, BTC 350/350, ETH 326/326, delivery +2); T33 1/2 (day 2 due 20:45; pins `053c4d18`/`2cbe5ebd` intact); BASKET1 **5 rows, session 08-26 logged 09:00** as predicted, frozen `d53b4fe4` untouched, curve not read; T4 9 rows untouched; window-2 `raw_transaction` **266,257** (+77,450 in ~12 h ≈ **155k/day**, PASS), **1/20** failed exits so far today (attempt 17, 00:45Z, connection reset), attempt 18 running ~11 h, raw phase ≈ 09-30/10-01; convexity pins `505072ce`/`ba6bb268`/`1d3e53c4` intact; NEWSDESK 2/30 open 0; PREDMARKET 0/50 open 35. Owner channels unmoved since 08-16/18.
- **Agenda: no task promoted/killed/re-ordered** (T34 stays running; nothing due before 09-06 PREDMARKET first resolution / 09-22 T30 read). Paid-data menu for the post-12-23 pay-or-stop fork frozen at three items — borrow-availability feed, bond/credit-ETF NAV, non-US investment-trust NAV — so that fork is one decision, not a re-survey.
- **Process fault recorded (once):** `research/trading_bot/INVENT_2026-08-27_MASTER.md` (07:07, outside the cron ticks) ran 27 free cross-section formulas — perp-OI session rotation, overnight-vs-intraday persistence, intraday RV signature — against families CLOSED by the 08-24 directive. Verdict **honest zero, 0 survivors, no basket action** (pooled bar 2.82; best design t≈2.3 flipped sign held-out); linked here so it stays on the dead ledger. **Method rule banked from it:** choosing sign by negating the NET PnL adds costs back as profit (−(gp−c) = −gp+c) and manufactured phantom held-out t 2.5–4.0; re-book the negated *signal* with cost still subtracted.
- **Owner scheduling recommendation (not actioned):** the 06:00 CEST newsdesk slot is structurally unable to act (after-hours catalysts, stale pre-catalyst reference = lookahead); recommend swapping 06:00→PREDMARKET and moving NEWSDESK to a live-quote slot. Method rule meanwhile: a 06:00 stale-reference abstention is a PROCESS abstention, not evidence about the agent's read. Full note: `research/trading_bot/STRATEGIST_2026-08-27_1200.md` (sha `ef303bfe…`).
- Next tick 08-27 15:00 = INVENTION (abstain unless a published-synchronous-tether or forward-panel family outside the dead ledger exists); 00:00 STRATEGIST verifies T30 day 4, T33 day 2, window-2 08-27 failure total.
