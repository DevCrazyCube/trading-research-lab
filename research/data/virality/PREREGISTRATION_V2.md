# Gate-B Virality Forward Paper-Decider — Pre-Registration V2

**Frozen:** 2026-09-01 (before any V2 trade resolves). Supersedes V1 (`PREREGISTRATION.md`,
retired `RETIREMENT_20260901.json`). Ledger: `paper_trades_v2.jsonl` (hash-chained; git is the real anchor).

## Why V2 (what V1 got wrong)
An adversarial audit found two real **signal** bugs in V1, so its ledger was invalid (and its N=1 result
meaningless). V2 fixes exactly those two and nothing about the result:
1. **Rolling-window breadth.** V1 read the h1 cumulative trade count as "buyer breadth" — a count that can
   *fall* as the window ages. V2 uses the **m5 (5-min) buy rate** and requires acceleration confirmed by
   two independent conditions (below), so a windowing wobble cannot trigger an entry.
2. **Pair-identity drift.** V1 re-picked the "deepest pair" each cycle, comparing counts/prices across
   different pools. V2 **pins the pair address** at first sight and re-fetches that exact pair every cycle.

## Thesis under test (unchanged)
An off-chain attention spike reaches a canonical, exitable, past-t0 memecoin *before* on-chain price fully
prices it in. Entry on **buyer-arrival acceleration** (a rate 2nd-derivative, not price momentum), gated by
an exitability screen (the B20B "did anyone actually get out" logic).

## Mechanism (locked)
- **Universe:** DexScreener boosted Solana tokens (attention proxy, coin-mapped, no name-matching).
- **Pair:** pinned at first sight (deepest), re-fetched by address thereafter.
- **Entry, ALL of:** m5 buys ≥ 10 (noise floor); m5 buys up ≥ **40%** vs the prior observation on the SAME
  pair; m5 buys > m5 sells (net demand); price up vs prior obs (confirmation); pair age ≥ 60 min; exitability
  screen PASS (`virality_probe.SPEC`); not already open.
- **Exit (convex):** −12% hard stop; else a widening trailing stop once ≥ +12% (18/25/35% give-back as the
  peak clears +0/+50/+150%); else a 12h horizon. Realized return charged a flat **3% round-trip toll**.
- **No wallet, no orders, no spend.**

## Pre-registered decision (N = 120 resolved trades)
R = net (post-toll) return per trade; mean_R with a 95% CI (mean ± 1.96·SE).
- **PASS** (worth building the causal-fill V3 — NOT a money claim): `ci95_lo > 0` at N=120.
- **KILL** (thesis dead as a cheap screen): `ci95_hi < 0` at N=120, **or** event rate < 1 entry/week.
- **UNDECIDED:** CI straddles 0 → extend to N=200 once, then KILL if still straddling.

## What this is and is NOT (the honest scope — the crux of the V1/V2 disagreement)
V2 is an **optimistic-bound cheap FILTER**, not an executable strategy. Fills use the observed pair price +
a flat toll, with **no causal decision-to-landing path and no exact costs** (real execution is strictly
worse). Therefore:
- A **KILL is decisive** — if even the optimistic bound is not +EV, real money certainly is not.
- A **PASS is necessary-but-not-sufficient** — it only earns the right to build V3 with source-receipt
  clocks, causal fills, and exact all-cost accounting. It is never, by itself, evidence to trade real money.
- The hash-chain is tamper-**evidence**, not a security boundary; a single-operator local log can always be
  re-hashed after an edit. The real append-only anchor is committing this ledger to git.
