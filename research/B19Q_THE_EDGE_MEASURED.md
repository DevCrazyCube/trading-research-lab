# B19Q — the edge, measured against the cost of trading

**Status.** Burned data, no preregistration, no ledger pass. This is the search the owner asked for
after the exit-rule family closed: *stop concluding and find a way.* It found two real errors in the
prior work and then measured, quantitatively, exactly how far short the remaining edge falls.

**The one-line answer.** A real edge exists. It is **0.86% gross**, held out. The cost of trading is
**~3.0%**. The edge is roughly a quarter of the toll, and that gap is the whole story.

---

## 1. The prior work capped its own winners — a real design error

Every rule this programme tested took profit at **+6%**. Nobody had measured how high these tokens
actually go. Maximum favourable excursion, across 2,903 launches with an observable post-entry path:

| | reached at some point |
|---|---|
| +10% | 34.17% |
| +50% | 16.98% |
| **2×** | **10.13%** |
| 5× | 2.51% |
| 10× | 0.38% |
| max observed | 13.76× |

**One launch in ten doubles.** Taking profit at +6% sells that for six percent while still eating the
full downside — the exact inversion of what a fat right tail requires.

**Fixing it matters, and is measurable.** With all costs stripped, entering at t0+50:

| rule | gross |
|---|---|
| buy and hold to the end | **−6.19%** |
| best take-profit / stop-loss cell | **+0.76%** |

A tight stop with a distant target converts a −6.19% process into a +0.76% one. **The rule shape was
genuinely wrong**, and this is the first thing in the programme that moved the sign.

## 2. The cost model overstated the toll by 2 percentage points

`b10a` charges ATA rent as unrecoverable, with the reasoning recorded in the code: *"ATA rent is
charged on entry and NOT refunded on exit, by contract. The reclaim is real but conditional on
closing the account."*

**The reclaim is real, and closing can be bundled into the sell transaction.** At a 0.1 SOL position
the rent is 2,039,280 lamports — **2.04% of position**, and about 40% of the entire round-trip toll.

| | best cell, real venue fees |
|---|---|
| rent burned (project convention) | −4.90% |
| **rent reclaimed on exit** | **−2.75%** |

This is a conservative convention doing real damage to every cost figure in the programme. It should
be revisited wherever a cost is quoted — not to make results look better, but because 2 points is
larger than most of the effects being measured.

## 3. The cost stack, decomposed

Entering at t0+50, 0.1 SOL, stripping one layer at a time:

| | result | implies |
|---|---|---|
| real costs | −4.31% | |
| no transaction costs | −1.81% | transaction costs = **2.50%** (rent is 2.04% of it) |
| no costs at all | **+0.76%** | venue fees = **2.57%** (125 bps × 2 legs) |

**The bar any strategy must clear is ~3.0% gross** — 2.57% venue fee plus ~0.46% irreducible
transaction cost once rent is reclaimed.

## 4. Entry timing is the strongest single effect found

The edge grows monotonically the longer you wait before entering. This is a *causal* filter, not
lookahead: you observe whether a token is still trading and only then enter.

| entry | n | gross edge | buy & hold |
|---|---|---|---|
| t0 | 2,821 | 0.22% | −10.48% |
| t0+50 | 2,314 | 0.79% | −6.19% |
| t0+200 | 1,978 | 1.67% | −2.79% |
| t0+1000 | 1,132 | 1.70% | −1.44% |
| **t0+5000** | 820 | **2.70%** | **+1.27%** |

Waiting ~33 minutes turns buy-and-hold from −10.48% to **+1.27%**. The survivors are a genuinely
better population — and survivorship is exactly what a patient entrant is allowed to select on.

**But 2.70% is still below the 3.0% bar.**

## 5. Signal search: nothing beats the baseline

Trade-level features from the observation window `(t0, t0+50]` — distinct users, trade count, buy
volume, net flow, largest buy, creator re-entry, sell pressure, creator deposit — with thresholds
fitted on half the curves and reported on the other half, and all costs stripped so any signal would
be visible:

| best cell on A | held out on B |
|---|---|
| `n_trades ≥ 50`, TP 5×, SL 0.98× → 2.48% | **0.86%** |
| no selection at all | 0.19% |

**Maximum gross edge available anywhere: 0.86%, against a 3.0% bar.** The in-sample 2.48% shrinking
to 0.86% out of sample is the ordinary signature of threshold-fitting, so even 0.86% is generous.

### The one apparent positive, and why it is not one

At `t0+20000` with TP 10× and SL 0.95×, the held-out half returned **+0.53%** net. It does not
survive inspection:

| ten-fold check | |
|---|---|
| folds positive | **3 of 10** |
| mean | +0.22% |
| **median** | **−2.71%** |
| winners | **20 of 638 (3%)** |
| share of total from the top 3 outcomes | **1563%** |

**Three positions out of 638 carry the entire result.** Remove them and it is deeply negative. Two
folds return +13.52% and +14.31%; the other eight lose. That is a lottery ticket wearing the costume
of a strategy, and it is precisely the shape that looks like an edge to anyone who stops at the
mean.

## 6. The one configuration that comes close — and it reverses a recommendation

The bar is 3.0% because of the 125 bps fee. But B19N established that a 25 bps tier exists on the
graduated market, and that a pool's fee is **92% predictable from its first trade**. That was
recorded as a dead end because pools opening on a cheap *base* still paid ~100 bps total once the
creator fee stacked. Selecting on the **total** rather than the base is a different test:

| | |
|---|---|
| pools with ≥3 observed trades | 60 |
| whose FIRST trade totals ≤25 bps | 18 |
| **of those, every later trade also ≤25 bps** | **13 (72%)** |
| median later-trade fee on cheap-start pools | **25 bps** |

### The accounting

| the bar, 25 bps tier, 0.1 SOL | |
|---|---|
| venue fee, 2 legs at 25 bps | 0.50% |
| slippage, 2 legs (measured) | 0.22% |
| transaction cost, rent reclaimed | 0.21% |
| **total** | **0.93%** |

| the edge | |
|---|---|
| best held-out gross edge | **0.86%** |

**Gap: 0.07 percentage points short.**

### Why this is still not a result

- **The edge is measured on bonding curves; the fee on graduated pools.** Combining them assumes the
  edge transfers between populations, and nothing here shows that it does. This is the single
  largest weakness and it is not a small one.
- **72% persistence, on a sample of 18 pools.**
- **28% of cheap-start pools stop being cheap.** A pool that turns expensive *after* entry charges
  the exit leg at 95–125 bps — alone larger than the entire edge.
- **0.86% is the maximum of a search** over features and thresholds. Its honest expectation is
  lower, and the in-sample figure was 2.48%.

### What it changes

It reverses the collection recommendation I gave, and the reversal should be stated plainly rather
than buried. That recommendation rested on the liquidity and size levers, which **are** properly
closed. This is a different question: *does the corrected rule shape, run on cheap-tier graduated
pools, clear a 0.93% bar?* It is 7 basis points from doing so on numbers assembled from two
populations — which is precisely the kind of question a real panel settles and burned data cannot.

**Owner's call, and the honest framing is: not an edge, a near-miss whose error bars are wider than
the gap.**

## 7. The right instrument — the owner's idea, and it flips the sign

The owner's objection to everything above: *every rule either seat has ever tested uses FIXED
thresholds.* Take profit at a constant multiple, stop at a constant fraction, applied identically to
every curve. The peer seat's framing of the same point: **B19F's drawdown rules and B19K's +6% were
left-tail instruments pointed at a right-tail asset.**

The right-tail instrument is a **trailing stop**: exit a fixed fraction below the running peak, with
**no take-profit cap at all**. It cannot truncate the tail, because it has no ceiling.

| rule, entry t0+200, real 125 bps fees, rent reclaimed | mean | winners | folds positive |
|---|---|---|---|
| fixed TP 2.00×, SL 0.95× | −2.20% | 6% | **0 / 10** |
| **trailing stop, 10% give-back** | **+0.48%** | 10% | **5 / 10** |

**The sign flips.** A 2.7-point improvement from changing the instrument alone, with no new
information, no selection and no venue change. Partial exits (sell half at 2×, ride the rest) were
tested alongside and are worse everywhere — best −1.29%.

## 8. Why +0.48% still cannot be called an edge

The mean is positive. It is also indistinguishable from zero, and the reason is the same property
that makes the instrument correct:

| | |
|---|---|
| n | 1,978 |
| mean | **+0.482%** of position |
| standard deviation | **43.3%** per position |
| standard error | 0.974% |
| t-statistic | **0.50** |
| 95% interval | **[−1.43%, +2.39%]** — contains zero |
| bootstrap 95% (2,000 resamples) | [−1.21%, +2.65%], 67% above zero |
| **largest single position** | **138% of the total profit** |
| **sample needed to distinguish from zero** | **≈ 30,965 positions** |

**One position is more than the entire profit.** The top ten are 483% of it. A right-tail payoff
concentrates its return in a handful of outcomes by construction — which is exactly why it needs an
enormous sample before its mean means anything.

Window 1 holds 3,932 launches. **Roughly eight such windows would be needed** to establish whether
+0.48% is real.

### What that implies practically

- **This is not a small-bankroll strategy.** A 43% per-position standard deviation with 10% winners
  means long losing runs are the norm, and the return arrives in single positions that cannot be
  predicted or waited for.
- **It cannot be validated cheaply.** Any backtest on one window — including this one — is inside
  the noise. The honest statement about any result derived from 2,000 samples of a 43%-volatility
  payoff is that it is consistent with zero.
- **The instrument finding stands regardless.** Trailing beats fixed by 2.7 points and 5 folds to 0.
  That comparison is between two rules on the *same* positions, so it does not depend on the
  absolute level being measurable — which is precisely why it survives when the level does not.

## 9. What this actually establishes

Not "it doesn't work" — something much more specific:

- **the tradeable edge is ~0.86% gross**, and it is real;
- **the cost of trading is ~3.0%**;
- therefore the venue's fee would have to fall from 125 bps to roughly **35 bps per leg**, or the
  edge would have to be **3.5× larger**, for any of this to clear.

Neither is available. The graduated market's 95 bps (B19N) narrows the gap and does not close it.

**Two of the four things attacked here were real defects in the prior work** — the +6% target
inverting the payoff, and rent being charged as unrecoverable. Both were worth finding, and both
were worth roughly 2 points. Together they were not worth 3.
