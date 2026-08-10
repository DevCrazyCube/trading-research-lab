# The liquidity wall replicates across two windows

**Status.** DEVELOPMENT OBSERVATION, not an evaluation result and never to be reported as one.
`B19G_CAPACITY_WALL_HISTORICAL_V3` permits runs against the burned corpus as development only. No
pass was spent to produce this and no ledger entry was created.

**Why it exists.** The owner asked whether the evaluation might simply have caught an unlucky
22.6-hour window. That is the one objection a single window genuinely cannot answer, and it
deserved a test rather than a shrug.

## The comparison

The same measurement, the same admission rules, the same code, on two non-overlapping periods
with entirely disjoint curves.

**The geometry, stated precisely, because the first version of this note got it wrong.** The two
LAUNCH COHORTS are about 1.47 million slots apart — roughly a week. But the two OBSERVED EXTENTS
are nearly adjacent: 433,894,233–435,536,000 and 435,569,222–437,210,794, a gap of 33,222 slots,
**about 3.7 hours edge to edge**. The first version of this note said "about 1.6 million slots
apart — roughly a week of chain time" while printing the two extents directly beneath it, which is
the kind of claim a reader checks in ten seconds. As regime samples these are one contiguous
fortnight of the same market, and that bounds what the replication buys.

| group | burned window (1,136 curves) | fresh window (3,932 curves) |
|---|---|---|
| h_1000 · delay 1 | 34 | 20 |
| h_1000 · delay 2 | 34 | 21 |
| h_1000 · delay 4 | 38 | 26 |
| h_10000 · delay 1 | 22 | 16 |
| h_10000 · delay 2 | 22 | 17 |
| h_10000 · delay 4 | 23 | 20 |

Median external capacity, lamports, cap-hit cells excluded.

Full distribution, `h_1000_slots|delay_1`:

| | burned | fresh |
|---|---|---|
| min | 3 | 3 |
| p25 | 6 | 4 |
| median | 34 | 20 |
| p75 | 89,834,099 | 45,964,566 |
| p90 | 663,000,792 | 632,386,317 |

Burned corpus: slots 433,894,233–435,536,000. Fresh window: slots 435,569,222–437,210,794.

## What it supports

The objection **as posed** — that the evaluation caught an unlucky 22.6 hours — is answered. Two
non-overlapping periods with disjoint curves give medians in the same order of magnitude in every
group: tens of lamports. The earlier window is somewhat more liquid at the median (34 vs 20), a
real difference that is not explained away, but it is a difference between "essentially no
liquidity" and "essentially no liquidity".

**The p90 claim in the first version was wrong.** It said "p90 values within 5% of each other". That
holds for the h_1000 groups (4.6%, 1.3%, 3.5%) and fails for h_10000 delay 1 and delay 2, which
diverge by **21.2%** and **16.8%**. Same order of magnitude everywhere is true, and is all the
argument requires; "within 5%" was a claim scoped to one group and generalised to six.

**Split the conclusion, because the two halves have different standing.**

- The **SHAPE** of the wall — a cliff near zero with a thin liquid tail orders of magnitude above —
  has now been seen twice and is plausibly structural to how launches work.
- The **QUANTILES** — a median of 20 lamports, 17% of curves executable at 0.1 SOL — are magnitudes,
  and magnitudes are regime-exposed. A mania could move them by orders. Two adjacent weeks of one
  market do not establish them across regimes.

"Mostly survives" is right for the shape. It is **unestablished** for the magnitudes.

## What it does NOT support

- It is **not** a preregistered replication. It has no frozen document, no pass, no ledger entry,
  and it may not be cited as an evaluation result.
- Two windows are not many windows. Both sit within a few weeks; a genuinely different market
  regime — a bull phase, a change in venue parameters — remains untested.
- The burned corpus reached this measurement through a different collection pipeline. The
  admission rules applied here are identical, but the underlying population was assembled
  differently, so this is a robustness observation rather than a controlled replication.
- It says nothing about whether the SIGNAL results (B19D, B19F) replicate. Only capacity was
  compared. Signal results plausibly are more regime-sensitive than a liquidity distribution.

## The distinction worth keeping

Some of this programme's findings are arithmetic and some are observations.

- The **fee schedule** (125 bps per leg) and the **slippage arithmetic** are properties of the
  deployed program and of constant-product mechanics. They do not vary with sampling luck at all.
  Scope that correctly: they are invariant **until the venue changes its parameters**, which is an
  observable event rather than sampling noise — 43 curves in this very window carried disagreeing
  schedules, and the B0 inventories document past program upgrades. Against the unlucky-window
  objection the cost floor takes zero force; against "the venue could change" it takes some, and
  that is a monitorable risk rather than a statistical one.
- The **capacity distribution** is an observation, and it is the one just shown to replicate.
- The **signal results** are observations on one window and are the most exposed to regime change.

An "unlucky window" objection therefore has real force against B19D and B19F, and much less against
B19G and none at all against the cost floor.
