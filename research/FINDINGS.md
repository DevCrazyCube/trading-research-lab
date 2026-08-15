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

**Two things survive the whole programme, and neither makes money:** a drawdown reduction on a
position you were holding anyway, and a screen that avoids a class of losses.

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

## 10. Open

- **Window 2 collection** — running; the frozen screen's out-of-sample test.
- **Common-funding-source clustering** — the one wallet-linking heuristic we could not test.
- **Whether window 1's regime generalises** — graduation rate moved 25× in eight months.
