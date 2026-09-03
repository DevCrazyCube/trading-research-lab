# Why every strategy in this repo died: the median asset falls, the mean is carried by a tail

Measured today, on three completely independent datasets, using three different event definitions.

## The same signature, three times

| study | population | MEDIAN outcome | MEAN outcome |
|---|---|---|---|
| memecoin bonding-curve trades (live arm) | pump.fun launches | **−16.1%** | tail-carried |
| token unlock cliffs, −30d→+14d | 545 insider/privateSale events | **−9.99%** | **+4.85%** |
| volume-spike events, market-relative | 12,563 UP-spikes, 2,002 days | **−1.68%** | −0.26% |

In every case **the typical asset underperforms badly while the average does not**, because a thin minority
of names produce enormous positive returns. The cross-section is violently right-skewed at every horizon and
in every venue we have measured.

## What that does to a strategy — and it is symmetric, so there is no clever side to take

- **Short the typical name** → you win most trades and lose money. The median is negative (you are usually
  right) but the mean is not (a few names rip and take back everything). This is short gamma, and it is
  exactly what killed the unlock-cliff short: median −9.99% but a short still loses 4.85% outright.
- **Long individual names hoping to beat the basket** → you lose most trades. The median name loses to the
  basket; only the tail wins, and nothing we measured predicts which names are in the tail *before the price
  already reflects it*.
- **Hold the basket** → you capture the tail by construction. On this panel the equal-weighted liquid basket
  returns roughly **+65%** over the sample while the **median name compounds to about −100%**.

The gap between those two numbers is the whole story: **the entire return of this asset class lives in a thin
tail, and the tail is what a basket owns and a stock-picker misses.**

## Why this explains every death in the repo, not just today's

Every strategy here has been an attempt to extract alpha from an individual-name cross-section whose return
is concentrated in a tail nobody can select ex ante:

- Sniper, PAC, memebot_evo, the arena arms — pick names, hold briefly, die.
- The 598-formula perp sweep — its sole survivor was **three coins, two since delisted**, i.e. the tail
  itself, not a rule that finds the tail.
- Creator provenance — a real 4.75× effect on *who* graduates, fully impounded in price before it is
  actionable.
- Unlock shorts, volume-spike exhaustion, funding-extreme fades — all name-level, all dead.

The 1-of-598 "survivor" and the 158%-of-book single trade in the bundle arm are not anomalies to be corrected
for. **They are the asset class showing you where its returns actually are.**

## The honest implication

**Stop trying to pick names in a crypto cross-section.** The measurements say the achievable positions are:

1. **Own the basket** — that is beta, not alpha. It is available for near-zero cost, it captures the tail by
   construction, and no work in this repo has beaten it.
2. **Be the venue, not the trader** — earn fees/spread rather than direction, so the tail's skew is someone
   else's problem. Untested here; it is the one structurally different posture remaining.
3. **Find a market whose cross-section is NOT tail-dominated.** Every measurement above is crypto. The skew
   is a property of this asset class, and it is the reason name-selection keeps failing.

A caveat stated plainly: the top-3-symbol concentration statistic is **undefined** for the volume-spike arms
(residuals sum to ≈0, so the share ratio explodes to −95% and −15,575%). It is reported here only to note it
must not be quoted; the CI and net-of-cost columns carry the verdict on their own.
