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

## 8b. The mean was the wrong statistic — and the right one is worse

The peer seat's question: a right-tail strategy is not run for its mean per trade, it is run for
compounded survival across many trades. Is there a formulation in which 2,000 samples decides
something useful? There is, and it does — against.

**Kelly sizing.** `f* = mean / variance = 0.0257` — **2.57% of bankroll per position.** At a 0.1 SOL
position that implies a **3.9 SOL bankroll**, which is itself the first hard fact: the strategy
cannot be run larger without exceeding the Kelly fraction, and the capacity work (B19N §3c) says the
market cannot absorb larger positions anyway.

**Median log-wealth**, the statistic a repeated bettor actually maximises:

| fraction | log-growth per trade | over 1,000 trades |
|---|---|---|
| 0.010 | +0.000039 | ×1.040 |
| **0.026 (Kelly)** | **+0.000070** | **×1.072** |
| 0.050 | +0.000056 | ×1.057 |
| 0.100 | −0.000147 | ×0.864 |
| 1.000 | −0.018936 | ×0.000 |

**Simulated campaigns** — 1,000 trades, Kelly-sized, resampled from the observed outcomes, 2,000
campaigns:

| | |
|---|---|
| median final wealth | **×1.042** |
| p10 | ×0.736 |
| p90 | ×1.662 |
| **campaigns ending below the starting bankroll** | **44%** |

### What that means in plain terms

Taking the +0.48% entirely at face value — ignoring that its confidence interval contains zero —
**one thousand trades returns a median 4.2% on a 3.9 SOL bankroll, with a 44% chance of ending
down.** That is roughly 0.16 SOL of median profit for a thousand round trips, and 1,000 launches is
about four days of the *entire* pump.fun market.

**The peer's framing was right and the answer is worse than the mean suggested.** The mean flatters
the strategy because it ignores variance drag; median log-wealth accounts for it, and once it does,
the Kelly-optimal growth rate is 0.007% per trade. The variance does not merely make the edge hard
to measure — it consumes almost all of it.

## 8c. The shape tournament — settled, by the one statistic this sample can decide

The peer seat established the decidable question: at n≈2,000 you can **rank** instrument shapes
robustly, because a *paired* comparison on the same positions cancels the asset-move variance that
makes absolute levels unmeasurable. You cannot **certify** levels. So the tournament below reports
paired differences.

They also measured the thing that makes trailing viable at all, and it reversed their own prior:
**peaks are plateaus, not spikes.** On 130 selected curves reaching a >+6% peak — median 98% of the
peak still available one slot later, 93% keep ≥80%, median plateau width 27 observations, **0% pure
spikes**. Their gap-risk objection was retracted on that data. The top rolls over slowly; the violent
move comes later.

### Every elaboration loses to plain trailing

| shape | own mean | vs base (paired) | t | folds + |
|---|---|---|---|---|
| plain trailing, 15% | +0.22% | +0.20% | 0.98 | 6/10 |
| **plain trailing, 20% [base]** | +0.02% | — | — | — |
| plain trailing, 25% | −0.60% | −0.62% | **−3.53** | 2/10 |
| two-regime: hard 15% → trail 20% @1.2× | +0.01% | −0.01% | −0.06 | 6/10 |
| two-regime: hard 10% → trail 25% @1.2× | +0.03% | +0.01% | 0.05 | 5/10 |
| ratchet 25%→15% at 1.5× | −0.12% | −0.14% | −1.01 | 5/10 |
| ratchet 30%→20% at 2.0× | −1.10% | −1.12% | **−6.60** | 0/10 |
| floored trail 20%, floor at 1.2× | +0.01% | −0.01% | −0.41 | 5/10 |

**Nothing beats plain trailing.** The two-regime idea — tight stop until a peak establishes, then
trail — is the peer's own proposal and comes out at −0.01%, t = −0.06: **no difference at all.**
Ratchets and floors are worse. What *is* robust is the direction: **looser give-back is reliably
worse** (t = −3.53, −6.60), so the plateau's wobble is narrower than 20% and handing back 25%+ costs
real money.

### The give-back optimum is broad and flat

| give-back | mean | t | folds + |
|---|---|---|---|
| 6% | +0.04% | 0.05 | 3/10 |
| 8% | +0.28% | 0.29 | 4/10 |
| **10%** | **+0.48%** | 0.50 | **5/10** |
| 12% | +0.32% | 0.33 | 5/10 |
| 15% | +0.22% | 0.22 | 5/10 |
| 20% | +0.02% | 0.02 | 4/10 |
| 25% | −0.60% | −0.62 | 3/10 |

Paired against the best: 10% vs 25% is t = **+3.16**, but 10% vs 6%, 15% and 20% are t = 1.35–1.65 —
**not distinguishable.** The optimum is a plateau from roughly 8% to 18%, which is the good kind of
result: the rule is not finely tuned and does not depend on hitting a parameter exactly. (The peer
predicted 15–25% from the wobble measurement; the data says slightly tighter.)

**So the instrument question is closed and the answer is simple:** a plain trailing stop with a
give-back somewhere in 8–18%, entered after a delay, beating every fixed rule and every elaboration
tested. That is a real, transferable finding about rule shape — and it is worth exactly as much as
§8b says, which is a median 4.2% over 1,000 trades at a size the market cannot absorb.

## 8d. The migration event — the one shape outside Q3's dichotomy, and it is 3 bps

The peer seat's Q3 answer divides every position into *be right about direction and pay the toll*, or
*be the fee recipient*. There is arguably a third: **be present at a mechanical repricing.** At
graduation the bonding curve stops and a pool is created with fixed reserves, which sets an opening
price. The curve had a final price. Nobody had ever asked whether they match.

If they differed systematically, capturing that would not be a directional bet on a memecoin — it
would be an event arb at a *known moment*, clearing a mechanical gap rather than a random walk. And
unlike a mean test on a 43%-volatility payoff, a **sign test** on a mechanical gap is decidable at
n=82.

**The sign test passes perfectly and the magnitude kills it.**

| pool price ÷ curve price | value |
|---|---|
| p0 | 9,997 bps |
| p50 | 9,997 bps |
| p100 | 9,997 bps |
| pool opens LOWER | **82 / 82 (100%)** |

**Every percentile is identical.** The migration applies a deterministic transformation: the pool
opens exactly **0.03% below** the curve's final price, on all 82 graduations, with zero dispersion.
That is a fixed mechanical constant — a rounding or migration convention — not a market gap.

Perfectly predictable in sign, and **roughly 90× too small to clear the toll.** The third shape dies
in one measurement, which is what it should do when it is wrong.

### And the post-listing drift cannot be measured here at all

| after trade | n | p25 | median | p75 | up |
|---|---|---|---|---|---|
| 1 | 33 | 0.897× | 1.000× | 1.588× | 36% |
| 2 | 15 | 0.425× | 1.014× | 2.142× | 53% |
| 3 | **11** | 1.005× | 1.114× | 2.368× | 81% |

The sample collapses from 33 to 11 as the horizon extends, because window 1's PumpSwap coverage is
incidental (B19N §4). The "81% up" at trade 3 rests on **eleven observations** with a p25–p75 range
spanning 0.4× to 2.4×. **No conclusion is available**, in either direction, and quoting the 81% would
be exactly the error this document spent §8 dismantling.

This is the one question the graduated collector was built to answer and it remains unanswered by
choice, not by oversight.

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
