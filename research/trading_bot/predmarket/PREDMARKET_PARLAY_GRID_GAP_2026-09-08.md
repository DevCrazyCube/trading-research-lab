# Parlay grid vs standalone legs: a ~2.5pp disagreement (2026-09-08, tick h21)

Status: **OBSERVED, NOT TRADED.** Logged as a structural note, not a position.

## The measurement

Polymarket prices the 2026 US Balance of Power as a 2x2 parlay grid *and* prices the
Senate and House control markets standalone. On the 2026-09-08T19:02Z pull:

| market | question | p_mid | volume |
|---|---|---|---|
| 562793 | D Senate | 0.525 | 2.48M |
| 562794 | R Senate | 0.485 | 1.73M |
| 562802 | D House | **0.885** | (open in our book) |
| 562803 | R House | **0.120** | (open in our book) |
| 562828 | D Senate + D House | 0.515 | 2.90M |
| 562830 | R Senate + D House | 0.345 | 2.09M |

Grid-implied P(D House) = 0.515 + 0.345 = **0.860** vs standalone **0.885**.
Grid-implied P(R House) = 0.140 vs standalone **0.120**.
The Senate legs reconcile exactly (grid-implied R Senate = 0.485 = standalone).

So the disagreement is entirely in the House dimension, ~2.0-2.5pp, on markets carrying
1.7M-2.9M in volume and 0.005 round-trip cost each.

## Why we did not take it

- Gross 2.5pp against ~1.0pp of two-leg round-trip cost is thin, before any slippage.
- Our open book already holds **both** standalone House legs (q=0.830 / 0.170). Our own
  R-House view (0.170) sits *above* the grid-implied 0.140, so a grid leg would be a
  third correlated position on one event pointing the opposite way from the two we hold.
- A calibration tracker scores probability estimates, not spreads. This is a relative-value
  observation; it has no clean single-leg q to freeze.

## What would make it real

Repeat the same grid-vs-standalone reconciliation across *many* Polymarket parlay families
(Balance of Power, the governorship-count ladders, the Russia seat ladders, the Brazil
place families) on a schedule, and record the signed gap. If the parlay grid is
**systematically cheap relative to standalone legs** — plausible mechanism: parlay legs
attract retail lottery flow on the long-shot combos and the resulting book never gets
arbed back against the two far more liquid standalones — that is a repeatable structural
edge of exactly the kind this programme is looking for, and it needs no forecasting skill.

**Kill-condition:** collect >= 30 family-days of signed gaps. If the mean signed gap is not
distinguishable from zero, or its magnitude is below the two-leg round-trip cost (~1.0pp),
this is spread noise and it dies. A gap that is real but sub-cost is still DEAD — distance
from zero is what matters, not sample size.

## Second observation, same tick: stale-prior inversion recurred

See [PREDMARKET_STALE_PRIOR_INVERSION_2026-09-06.md](PREDMARKET_STALE_PRIOR_INVERSION_2026-09-06.md).
Our open book logged Sweden next-PM Andersson (1193094) at p=0.885. The fresh pull has it
at **0.785** — a 10-point reprice. Pricing the paired Kristersson leg (1193093, p=0.205)
off the *book's* stale Andersson value would have manufactured a fake 0.09 arbitrage
(0.885+0.205 = 1.090 > 1) and produced a confident q~0.12 against a fair 0.205. Against the
fresh pull the pair sums to 0.990 and is perfectly coherent.

This is the **second** occurrence. Any cross-market coherence argument MUST be built from a
single fresh pull; never mix a logged book price with a live one. The 75 open estimates in
the ledger are frozen *entry* prices and are not valid inputs to a coherence screen.
