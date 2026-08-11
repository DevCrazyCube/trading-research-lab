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

## 6. What this actually establishes

Not "it doesn't work" — something much more specific:

- **the tradeable edge is ~0.86% gross**, and it is real;
- **the cost of trading is ~3.0%**;
- therefore the venue's fee would have to fall from 125 bps to roughly **35 bps per leg**, or the
  edge would have to be **3.5× larger**, for any of this to clear.

Neither is available. The graduated market's 95 bps (B19N) narrows the gap and does not close it.

**Two of the four things attacked here were real defects in the prior work** — the +6% target
inverting the payoff, and rent being charged as unrecoverable. Both were worth finding, and both
were worth roughly 2 points. Together they were not worth 3.
