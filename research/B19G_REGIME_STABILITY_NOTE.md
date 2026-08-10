# The liquidity wall replicates across two windows

**Status.** DEVELOPMENT OBSERVATION, not an evaluation result and never to be reported as one.
`B19G_CAPACITY_WALL_HISTORICAL_V3` permits runs against the burned corpus as development only. No
pass was spent to produce this and no ledger entry was created.

**Why it exists.** The owner asked whether the evaluation might simply have caught an unlucky
22.6-hour window. That is the one objection a single window genuinely cannot answer, and it
deserved a test rather than a shrug.

## The comparison

The same measurement, the same admission rules, the same code, on two non-overlapping periods
about 1.6 million slots apart — roughly a week of chain time — with entirely disjoint curves.

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

The liquidity wall is **structural, not a timestamp artefact**. Two independent periods give
medians in the same order of magnitude — tens of lamports — and p90 values within 5% of each other.
The earlier window is somewhat more liquid at the median (34 vs 20), which is a real difference and
is not being explained away, but it is a difference between "essentially no liquidity" and
"essentially no liquidity".

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
  protocol and of constant-product mechanics. They do not vary by window at all.
- The **capacity distribution** is an observation, and it is the one just shown to replicate.
- The **signal results** are observations on one window and are the most exposed to regime change.

An "unlucky window" objection therefore has real force against B19D and B19F, and much less against
B19G and none at all against the cost floor.
