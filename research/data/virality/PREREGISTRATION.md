# Gate-B Virality Forward Paper-Decider — Pre-Registration

**Frozen:** 2026-09-01 (before any resolved trade). This file fixes the decision rule up front so the
verdict cannot be reverse-engineered from the data. Ledger: `paper_trades.jsonl` (hash-chained).

## Thesis under test
An off-chain attention/virality spike reaches a **canonical, exitable, past-t0** memecoin *before* the
on-chain price fully prices it in. Entry fires on **buyer-breadth inflection** (the crowd arriving, a
2nd-derivative signal — NOT price momentum, which we already falsified), while an exitability screen
(the B20B "did anyone actually get out" logic) keeps us off unexitable rugs.

## Mechanism (locked)
- **Universe (attention proxy, $0):** DexScreener boosted Solana tokens (coin-mapped, no name-matching).
- **Entry, all of:** unique-buyer count up ≥ **15%** vs the prior observation; pair age ≥ **60 min**
  (past the t0 dev/sniper casino); exitability screen **PASS** (`virality_probe.SPEC`); not already open.
- **Exit (convex):** −12% hard stop; else a widening trailing stop once ≥ +12% (18% / 25% / 35% give-back
  as the peak clears +0/+50/+150%); else a 12h horizon. Realized return is charged a **3% round-trip toll**.
- **No wallet, no orders, no spend.** Pure forward measurement.

## Pre-registered decision (N = 120 resolved paper trades)
Let R = net (post-toll) return per trade; mean_R with a 95% CI (mean ± 1.96·SE).
- **PASS** (thesis is +EV, worth real consideration): `ci95_lo > 0` at N=120.
- **KILL** (thesis is dead): `ci95_hi < 0` at N=120, **or** the event rate is < 1 qualifying entry/week
  averaged over the collection window (too rare to matter even if positive).
- **UNDECIDED:** CI straddles 0 at N=120 → extend to N=200 once, then decide by the same rule; if still
  straddling, KILL (an edge too small to separate from 0 at N=200 is too small to trade).

## Honest limitations (recorded up front, not excuses later)
1. **Boosts are paid promotions**, a noisy proxy for organic virality — this measures "does entering
   exitable coins that are getting pushed, on breadth inflection, pay?" not the pure organic-social
   variant. A PASS motivates building the organic detector; a KILL likely kills that too.
2. **DexScreener 1h buy/sell counts are trade counts, not unique wallets** — breadth is proxied by trade
   count. Directionally the crowd-arrival signal, but coarser than true unique-buyer breadth.
3. **Paper fills at the observed price**, no adverse-selection/latency penalty beyond the flat toll — so
   this is an *optimistic* bound. A KILL here is decisive; a marginal PASS is not yet real money.
