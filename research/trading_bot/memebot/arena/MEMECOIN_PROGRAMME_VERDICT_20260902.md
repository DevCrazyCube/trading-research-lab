# Memecoin programme — measured verdict (2026-09-02)

Not an opinion. Every number below was recomputed from raw ledgers this session.

## The live arm, clean IDL-pinned epoch

BUNDLE_MOMENTUM_V2: n=34 resolved, mean net **−24.50%**, median −16.07%, **t = −5.27**, 4 wins / 34,
27 HARD_STOP. Mean **GROSS −22.40%** — the signal is negative *before a cent of cost*.

"Six buys inside 1.0s" is a spike-**TOP** detector, not a momentum detector: entry lands 0.9s after a
coordinated burst, which is exactly when the burst reverses. Median hold time: **1 second**. The arm is
past every futility rule it carries.

The earlier +3.96% book was invalidated in writing (`FEED_INVALIDATION_20260902T134837Z.md`) as a decoder
artifact — 10,487 out-of-regime TradeEvents. It was never an edge estimate, and it should not have been
reported as one.

## Why no memecoin bot can work on this venue

- **A perfect deadness screen was already tested.** Exact B20B sealed, 1,307 concentration vetoes, every
  rug deleted for free, ATA rent reclaimed → the exitable survivors **still lose −4.66% / ticket,
  t = −5.98** (n=382, PAC_LWS scenario ledger).
- **B19P:** the exit-rule family loses **−16.89% at literally ZERO transaction cost.**
- **B19Q:** best held-out gross edge measured anywhere = **0.86%** against a **2.48–2.98%** venue
  round-trip fee (2.9–3.5×). The fee is multiplicative and invariant to clip size, reserve depth, rule
  shape and holding period — there is no clip and no coin state where it clears.
- **Pooled across every recomputable paper ledger: n = 19,024 resolved, sum = −12,079 R**, win ~17%.
  Not one book net-positive. Sniper alone: n=16,458, mean −0.709 R, **t = −90.33**.

**Conclusion: memecoin trading on this venue is structurally negative on the outcome distribution, not on
cost. This is a measurement, not a mood. Recommended budget: $0.**

## The last surviving candidate is a handful of coins

X2_FLOWSTREAK, frozen held-out window 2025-01-01 → 2026-07-31, verified independently this session:

| rank | name | share of gross P&L | last bar |
|---|---|---|---|
| 1 | BEATUSDT | 18.6% | 2026-08-16 |
| 2 | MYXUSDT | 13.8% | **2026-03-31 (delisted)** |
| 3 | RIVERUSDT | 12.5% | **2026-06-30 (delisted)** |

Top-3 = **44.9%** of all gross P&L. Top-10 = 85.5%.

| drop | gross SR | t | breakeven | net @8bp | net @10bp |
|---|---|---|---|---|---|
| none | 3.336 | 4.19 | 17.89 bp | +1.84 | +1.47 |
| top-1 | 2.820 | 3.55 | 14.65 bp | +1.28 | +0.89 |
| **top-3** | 2.154 | 2.71 | 10.02 bp | **+0.43** | **0.00** |
| top-5 | 1.748 | 2.20 | 7.71 bp | **−0.07** | −0.52 |

Remove the three biggest names — two of which no longer trade — and a realistic 10 bp/side takes it to
**exactly zero**. This is not a strategy; it is a bet on a few thin, new, mostly-delisted coins.

## The recurring cause of death across ~60 retirements

Every headline that ever looked alive here was alive only because **one quantity in it was ASSUMED rather
than MEASURED**, and it died the moment that quantity was measured. Twelve documented before/after pairs
(Orphan Flush +41.92 bp → −10.99 bp; ORB Sharpe +2.857 → −0.034; sniper −0.05 R → −1.34 R under honest
repricing; and so on).

The programme did not fail to find an edge. It built an unusually good machine for proving there wasn't
one — which is worth something, but it is not a bot.
