# MEMEBOT_EVO — Pre-registration (frozen BEFORE running the search)

This document freezes the **selection rule, the multiple-testing noise bar, the reality gate, and the
kill rule** for the evolutionary variant engine, *before* any forward result is read. A genetic search
that is allowed to move its own success bar after seeing the numbers proves nothing. These rules do not
move; an improvement is a new pre-registration, never an edit to a running one.

> **PAPER ONLY.** No real orders, no wallet, no SOL, no on-chain writes. Every position is a hypothetical
> mark-to-market, frozen (sha256 + UTC) before its outcome. **CPU-only** — no GPU, no neural nets, no
> training, no external ML dependencies. Reuses the memebot's free/keyless feed and deterministic screen
> **read-only**. Real trading is a separate, owner-gated wallet decision, not reachable from here.

## 0. The honest prior
The programme has already shown memecoin trading is **negative-sum by construction**: the ~3% round-trip
venue toll is the house edge, the best gross edge measured anywhere was 0.86%, and the exit-rule family
lost −18.94%/trade even at zero cost. **Evolution cannot create an edge that is not there.** The expected
outcome of this search is that the population converges to ~flat/negative — and *that is the honest
answer*, not a failure of the engine. This engine is built to make a false "we evolved an edge" claim
*hard to make by accident*, not to manufacture a winner.

## 1. The genome (unit of selection)
A genome is a dict of rule parameters with fixed bounds (see `genome.py::GENE_BOUNDS`):
screen thresholds (`min_fdv_usd`, `min_reserve_usd`, `min_unique_buyers`, `max_buys_per_buyer`,
`honeypot_min_buys`, `max_pool_age_minutes`); exit rule (`horizon_minutes`, `stop_frac`, `target_frac`);
a dead-coin early exit (`dead_*`, switch `use_dead_exit`); and a flow-following early exit
(`flow_*`, switch `use_flow_exit` — exit when sells/buys pressure reverses past a ratio).

**Fixed, NOT evolved:** `bankroll_sol = 10`, `position_fraction = 0.02`, and the round-trip
`toll_per_side = 0.015`. The toll is the measured house edge; a search allowed to lower it would
"discover" a fantasy. It is pinned.

## 2. Population & forward accumulation
- **Population size:** 24 (seeded from the 3 named seeds — `BASE_180m`, `FAST_25m_dead`, `FLOW_follow` —
  plus fresh-random diversity).
- Each genome paper-trades **forward** on the **same** live/cached coin stream (one shared GeckoTerminal
  `new_pools` pull + PumpPortal buffer per scan; one refresh per unique open pool per track), each writing
  its **own** append-only sub-ledger `ledgers/{genome_id}.jsonl`. Each entry is frozen (sha256 + UTC)
  before its outcome. A per-genome **control null** (same sizing/stop/target/exit on screen-REJECT coins)
  is tracked alongside, as a secondary benchmark.

## 3. Selection rule (forward-only — NEVER re-scored on the same trades)
- A genome is **mature** once it has **`N_min_eval = 20` resolved PASS trades**.
- A **generation** (kill + breed) runs only when **≥ `MIN_MATURE_FOR_SELECTION = 4`** genomes are mature.
  Below that the loop only **accumulates** — there is **NO VERDICT** and no selection.
- In a generation, mature genomes are ranked by **forward mean R** (net of toll). The **top
  `SURVIVE_FRAC = 50%`** survive; the rest are killed. Killed slots are refilled by breeding from the
  survivors — **crossover** (uniform) then **mutation** (`rate = 0.30`, gaussian step `scale = 0.20`×range,
  clipped to bounds) — plus **`FRESH_FRAC = 20%`** fresh-random genomes for diversity. New genomes always
  start with an empty ledger and are selected only on trades they were **not** bred on. Immature genomes
  are never killed for lack of data; they keep accumulating.

## 4. Multiple-testing discipline — the anti-overfitting core (NON-NEGOTIABLE)
- **K** = the cumulative count of **distinct genomes ever evaluated** (only ever grows).
- The **K-corrected noise bar** = **√(2 ln K)** in per-trade standard-error units — the expected maximum
  t-statistic of the luckiest of K pure-noise strategies (the same analytic bar the equity programme uses,
  `FORMULA_SWEEP_MASTER`).
- A mature genome's forward **t = mean_R / SE**. It is only a **candidate** if **t > √(2 ln K)**.
- **Reality gate (confirmation):** a candidate is called **REAL** only if, on a **FRESH out-of-sample
  forward slice** of ≥ `N_min_eval` trades accrued *after* it was declared a candidate, it **again**
  clears the (current K) bar. A candidate that fails the fresh slice is recorded as **falsified**. This is
  the anti-overfitting confirmation the whole design rests on: beat the K-bar once *and* repeat it on data
  the genome was not selected on.
- Every generation report prints: the population, the current best genome + its forward expectancy, the
  K-corrected bar, and whether **anything** clears it — honestly.

## 5. Kill rule (HALT)
If, after **`M_GENERATIONS_KILL = 8`** real generations, **no** genome has been **confirmed REAL** *and*
the best mature genome's one-sided upper-95% bound on mean R is **< 0** (or no genome ever matured), the
search **HALTS** and reports **"no evolvable edge found"**. This is the expected, honest terminal state if
memecoin trading is negative-sum.

## 6. Framing clause (must accompany every output)
> NO VERDICT below the minimum. Population expectancy is **behaviour, not evidence**. Honest prior ~0 or
> negative. A survivor is REAL only if it beats the K-corrected bar **and** holds on a fresh out-of-sample
> slice. Evolution cannot manufacture an edge that is not in the data.
