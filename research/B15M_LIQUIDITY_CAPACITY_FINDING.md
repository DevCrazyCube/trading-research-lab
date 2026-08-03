# B15m — the external book, measured

Computed 2026-08-03 under `research/B15M_LIQUIDITY_CAPACITY_PREREGISTRATION.json`, committed alone
before any capacity existed. Offline and read-only; no network call of any kind.

**Nothing below is a return, and nothing below is a recommended size.** Every group carries
`LIQUIDITY_CAPACITY_DIAGNOSTIC`, `executable=false`, `landing_probability=unmeasured`,
`competitor_response=unmeasured`. A capacity is what the observed book could have absorbed.

## The estimand

For each cell — a (launch, entry delay, exit horizon) with both account reads — the greatest quote
input in [0, 100,000,000] lamports whose acquired tokens could be sold in full against the exit
checkpoint **exactly as observed**. Our own buy adds nothing to the reserves it would later be paid
out of. That self-contribution is what B15L measured and what this removes.

Population: 4,896 admissible cells of 18,846 exit checkpoints; 13,950 refused as outside B15L's
universe, chiefly for mayhem mode or a missing entry checkpoint or fee schedule.

*Conditioned on cells where BOTH an entry and an exit account checkpoint exist; B15f schedules from
B15a, which B15k measured holding 29% of the launches B15i observes, so this population is censored
by the recorders and not by the market.*

## The distribution is bimodal, not thin

| horizon, delay | cells | min | p25 | **median** | p75 | p90 | max | at ceiling |
|---|---|---|---|---|---|---|---|---|
| h_1000, 1 | 746 | 3 | 4 | **23** | 49,134,150 | 100,000,000 | 100,000,000 | 165 (22%) |
| h_1000, 2 | 748 | 3 | 4 | **23** | 49,347,954 | 100,000,000 | 100,000,000 | 166 (22%) |
| h_1000, 4 | 745 | 3 | 4 | **23** | 49,134,150 | 100,000,000 | 100,000,000 | 165 (22%) |
| h_10000, 1 | 886 | 3 | 4 | **16** | 1,710,775 | 100,000,000 | 100,000,000 | 141 (15%) |
| h_10000, 2 | 887 | 3 | 4 | **16** | 1,975,569 | 100,000,000 | 100,000,000 | 141 (15%) |
| h_10000, 4 | 884 | 3 | 4 | **16** | 1,975,569 | 100,000,000 | 100,000,000 | 138 (15%) |

All figures in lamports. A capacity at the ceiling means at least 0.1 SOL and was not measured
further; it is never reported as equal to the ceiling.

**The median cell's external book could support a buy of sixteen to twenty-three lamports.** The
quartile below it sits at four. Meanwhile 15–22% of cells could absorb the whole frozen position or
more. This is not a shallow book on average — it is a population of books that are either
essentially absent or deep, with very little in between, and a median is nearly the least
informative thing one could say about it.

## The same answer from an independent direction

B15L found the observed book could pay for the exit on 19% of cells. Here, **77% to 84%** of cells
have an external capacity below the frozen position while B15L could still price them — the same
finding reached by measuring the book instead of the round trip. The median shortfall is
**99,999,991 of 100,000,000 lamports**: where the position needed a hundred million, the external
book supported about nine.

The frozen `circular_liquidity_dependence` condition — external capacity of exactly zero — **fired
on no cell in any group**, because every book supported at least three lamports once the
worth-something bound was applied. It is published at zero, and the shortfall count above was
defined *after* seeing that, which is stated here rather than buried.

## The fixed grid, base scenario, h_1000_slots, delay 1

Reported in full, including the sizes that fail. Nothing here ranks or recommends a size.

| size (lamports) | liquidity-executable | net after costs non-negative | median net |
|---|---|---|---|
| 1,000,000 | 254 / 746 | 5 | −2,335,669 |
| 2,500,000 | 238 / 746 | 10 | −2,466,474 |
| 5,000,000 | 232 / 746 | 17 | −2,682,810 |
| 10,000,000 | 223 / 746 | 20 | −3,119,276 |
| 25,000,000 | 207 / 746 | 25 | −4,461,558 |
| 50,000,000 | 184 / 746 | 28 | −7,285,121 |
| 100,000,000 | 165 / 746 | 30 | −12,518,390 |

Two things move in opposite directions. Executability falls as size rises, which is the book
binding. Non-negativity rises as size rises, which is the 2,039,280-lamport ATA rent: it is charged
once regardless of size, so a small position cannot cover it however the curve moves. Even at the
smallest grid size only a third of cells could execute at all, and five had a non-negative net.

## Two discoveries about the arithmetic, both forced by the monotonicity requirement

The freeze said bisection may be used **only** if monotonicity is verified. It was not, twice, and
both failures were informative rather than inconvenient.

1. **A one-lamport buy acquires zero tokens at any reserves.** The pinned exact-input formula carries
   `(q - 1)` in its numerator. So the admissible set is `{0}` together with a run starting at a
   floor — measured at 2 lamports on every cell — and is not a prefix of `[0, ceiling]`. The search
   domain was corrected to start at that floor and the floor is published. The estimand's value is
   unchanged, because the maximum of a set is the top of its run either way.
2. **A small enough sale draws zero lamports, which an empty book can trivially pay.** Without a
   lower bound an empty reserve reported a capacity of two lamports. B10b already rules on exactly
   this — a zero gross is `L1M_NO_EXECUTABLE_SIZE`, "nothing can be sold for even one lamport" — so
   that rule was adopted rather than invented, and payability was split from admissibility because
   only the former is a down-set and only a down-set can be bisected.

Maximality is proven on every cell, not sampled: the returned input satisfies both constraints and
the next integer violates one, unless the answer is the ceiling. The guard is a named function with
its own tests, because a guard reachable only through a correct search is a guard nobody can
provoke.

## Differential agreement

The capacity was computed twice by different routes and they agree on every cell: bisecting over the
quote input, and bisecting over tokens via B10b's `max_executable_tokens`. That is a theorem rather
than a coincidence — since `quote_out_for_tokens_in` is non-decreasing, "the exit is payable" and
"the tokens do not exceed B10b's maximum" are the same condition — and there is a test asserting the
equivalence directly at the boundary.

## What this does not establish

No return, no profitability, no expected value. No landing probability. No competitor response. No
recommended size, and no position limit anywhere in this project is changed or should be read as
changed by it. Capacity is what the observed reserves could have paid, and the reserves were
recorded by our own instruments on a population they censor.
