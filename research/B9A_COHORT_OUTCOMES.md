# B9a — The first outcome measurement: graduation base rate for the B8b cohort

**Run:** 2026-07-29. Author: Claude 1. Read-only; 17 `getMultipleAccounts` requests.
**Rules frozen before the first request:** `agent_discussion.md` Seq 176.
**Cohort:** `research/b8b_cohort_433894233_434097833.sqlite`, the published, preregistered,
exhaustively-enumerated B8b cohort — **n = 1,601**, window `[433,894,233, 434,097,833]`.
**Artifact:** `research/b9a_outcomes.sqlite`.

> **This is a label, not a feature.** `BondingCurve.complete` read ≥8 days after launch is the
> end-of-observation outcome that `W_obs` was defined to permit. Using it as a model input would be
> the most direct leakage possible.

> **Graduation is not profit.** This measures whether a curve completed. It measures **no return**,
> and a graduated token can still lose money while a non-graduated one can be exited profitably.
> Nothing here is a strategy result.

## The headline

| | n | graduated | rate | 95% Wilson |
|---|---:|---:|---:|---|
| **whole cohort** | 1,601 | 43 | **2.69%** | [2.00%, 3.60%] |
| **tradable (non-Mayhem)** — the population the project trades | **1,136** | **16** | **1.41%** | **[0.87%, 2.28%]** |
| Mayhem (excluded by frozen policy) | 465 | 27 | 5.81% | [4.02%, 8.32%] |
| SOL-quoted | 1,577 | 40 | 2.54% | [1.87%, 3.44%] |
| USDC-quoted | 24 | 3 | 12.50% | [4.34%, 31.00%] |

**Every one of the 1,601 bonding-curve accounts was present.** Zero absent, so the freeze's separate
"missing account" category is empty and nothing had to be assumed about it.

## F1 — The tradable population graduates at 1.41%

That is the number that matters, because it describes the population the project has decided to
trade. A strategy that takes every tradable launch needs a winner returning **~71×** merely to break
even, before fees, slippage, priority tips, and failed transactions.

That is not a claim that no strategy works — it is the base rate any strategy must beat, and it is
the first time this project has had one.

## F2 — Exit liquidity is nearly absent for non-graduates, and this may matter more than F1

`real_quote_reserves` is the SOL actually sitting in the curve, i.e. what an exit could draw against.
For the 1,558 non-graduates:

| | |
|---|---:|
| median | **0.0000 SOL** |
| exactly zero | 159 (**10.2%**) |
| **under 0.01 SOL** | **1,474 (94.6%)** |
| under 0.1 SOL | 1,535 (98.5%) |
| p99 / max | 0.1811 / 34.3368 SOL |

**94.6% of non-graduates never accumulated 0.01 SOL.** Entering these is not a position that loses
slowly — for most of them there is no counterparty to sell back to at any size. A backtest that
assumes exits fill would be measuring a market that does not exist.

## F3 — Mayhem graduates 4.12× more often, and this does NOT mean the exclusion was wrong

| | rate | |
|---|---:|---|
| Mayhem | 5.81% | 27 / 465 |
| non-Mayhem | 1.41% | 16 / 1,136 |
| **rate ratio** | **4.12×** | Fisher exact two-sided **p = 3.6 × 10⁻⁶** |

**It is not driven by a few actors** — the obvious confound, checked before drawing any conclusion.
The 27 Mayhem graduations come from **22 distinct `creator ∪ user` actor groups** (largest single
actor: 3, i.e. 11%), and non-Mayhem's 16 from 15 groups. Measured **per actor group** with ≥3
launches, the gap widens rather than closes: **6.83% versus 0.31%.**

**And yet the frozen exclusion stands, for a reason already in the record.** `B7A_LIFECYCLE_AND_MAYHEM.md`
F44 established that `set_mayhem_virtual_params` lets the operator **mutate a Mayhem curve's virtual
reserves outside trading**. So:

- A Mayhem curve's price math can be changed by a counterparty **between entry and exit**.
- Its "graduation" may be **administratively produced** rather than market-produced — which would
  explain this rate difference directly.

**So F3 is best read as evidence *for* the exclusion, not against it.** The higher rate is what a
mutable curve would look like, and a higher chance of completion is worthless if the operator sets
the terms of your exit. Recorded because it would be easy to read this table backwards and conclude
the project excluded its best population.

## F4 — USDC's 12.5% is not established

3 of 24, Wilson **[4.34%, 31.00%]** — an interval wide enough to contain both the SOL rate and three
times it. Two of the three could be chance. **No USDC effect may be claimed from this**, and the
B8b census already recorded that USDC share itself is not distinguishable between cohorts.

## What this does not establish

- **No return, no profit, no strategy.** Graduation only.
- **One 24-hour window, one program regime**, carrying the day-of-week and market-conditions
  confounds the B8b census already states.
- **Nothing about timing.** When a token graduated, how far it ran before dying, or whether an early
  exit was available — none of that is here. It requires trade-level reconstruction.
- **Nothing about the 34.3 SOL outlier** or the shape of the upper tail, which is where any
  positive expectancy would have to come from.

## Reproduction

```
python3 scripts/b9a_cohort_outcomes.py     # read-only, resumable, ~17 requests
```

The artifact records the cohort it measured, that cohort's freeze hash, and that the measurement is
a label rather than a feature.
