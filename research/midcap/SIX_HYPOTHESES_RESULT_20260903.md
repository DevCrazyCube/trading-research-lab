# Six new hypotheses, one survivor-shaped thing (2026-09-03)

Generated after the owner objected that the programme was killing ideas without generating them.
All six DEAD on first pass; zero reached adversarial refutation. But the round produced a benchmark
correction, one permanent closure, and the only cell this project has found with a stable positive median.

## The six
| H | idea | killed by |
|---|---|---|
| 1 | mean reversion (inverse of the falsified momentum entry) | 0 of 100 (W,X,H) cells positive; deeper drop -> WORSE forward return. Response curve is an inverted U, not monotonic: it is \|prior move\| -> damage, not direction. |
| 2 | cross-pool arbitrage (structural, same mint two prices) | 0 of 188 executable Jupiter round trips positive, ceiling -0.001%. The aggregator already closes it. |
| 3 | predict the LP-pull (B20B applied post-graduation) | non-rug 15m drift is +0.78% gross vs a 1.14% toll, so a PERFECT screen still loses. Closed permanently. |
| 4 | the second leg | only 1.7% of triggered coins ever printed a new high (1/58); median entry fill -98.6% from peak. The "retrace" IS the rug. |
| 5 | on-curve buyer microstructure | 0 of 12 feature/side cells positive; the one artifact dies on a 1-slot reaction delay. |
| 6 | graduation moment as a mechanical event | -17.99pp vs a random bar in the same coin, n=107, k=107. Graduation timing is NEGATIVE alpha. |

## Benchmark correction (this moved every goalpost)
The "+0.63% random-bar control" cited all session came from a 24-mint set. On the survivorship-free
92-137 mint universe the random-bar control is **negative**. Correct benchmark: same-mint random bar,
about **-2.1% SIMPLE / -16.8% log** net at 15m. Arms previously described as "beaten by random" were
being compared to a fiction.

## Methodological finding: report SIMPLE returns for a basket, not log
A rug is log(-99%) = -4.6 but costs a portfolio only -100% of one position. Quoting log means made
every cell look catastrophic. Same cell, real bars, 15m: **log mean -20.55% vs SIMPLE mean +2.67%**.
Log for compounding a single position; SIMPLE for an equal-weighted book. This flipped a "dead" verdict
to "marginal" and is the single most reusable thing in this document.

## The one survivor-shaped cell -- and why it is still NOT fundable
Entry: prior 5-minute return in **[+4.8%, +9.5%]** (NOT the dead +30% regime). Exit: pure 15m hold, no
stop. Real consecutive bars only, toll 1.14%, 93 survivorship-free graduates.

| dropout charge | mean | median | CI95 | resolution |
|---|---|---|---|---|
| resolved-only | +2.33% | +6.70% | [-0.67,+5.04] | 98% |
| -30% | +1.66% | +6.70% | [-1.45,+4.57] | 98% |
| -50% | +1.25% | +6.70% | [-2.11,+4.10] | 98% |
| -100% | +0.22% | +6.70% | [-3.65,+3.49] | 98% |

It is a PLATEAU (4.8-6.0% +2.30%, 6.0-7.5% +3.33%) with negative bins on both sides, survives a 3.0%
toll, and a leave-one-mint-out jackknife never crosses zero (+1.84..+2.85%).

**The mean is indistinguishable from zero at every dropout charge. Median robustly +6.70%.**

### The trap I nearly fell into, recorded
30m and 60m holds looked Bonferroni-significant (+6.36% CI[+1.61,+11.20] and +13.55% CI[+4.49,+23.85]).
**Both were dropout bias**: resolution falls 98% -> 93% -> 82% as the hold lengthens, because coins that
rug stop trading and have no exit bar. Charge dropouts and the significance vanishes; at 60m the MEDIAN
flips to -5.15%. Longer holds are not better, they just hide more corpses. Always report resolution rate
next to the horizon.

## Live confirmation, same evening
The armed paper bot took 7 real trades off the live feed: -$21.98 on $5 positions, **-62.8% average**,
with TWO coins (10M, potato) hitting -99.7% within 5-9 minutes of entry. The rug mechanism is not a
historical artifact; it fired twice in seven trades in under two hours.

## Status
Bot repurposed to forward-test the surviving cell out-of-window at $0. Prior that it is an artifact:
high -- one creation window, k=74, mean CI spans zero. The median is the only reason to keep looking.
