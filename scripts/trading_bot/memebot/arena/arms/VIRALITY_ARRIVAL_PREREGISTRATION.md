# ARM 1 — VIRALITY_ARRIVAL_V2_1 — Pre-Registration

**Frozen:** 2026-09-01, before any V2.1 trade resolves (supersedes the standalone virality_tracker V2;
its 4 pre-fix rows are VOID / diagnostic-only, excluded from N). Ledger:
`research/data/arena/VIRALITY_ARRIVAL_V2_1/ledger.jsonl` (hash-chained; genesis binds
`virality_arrival.py` sha + this file's sha + the spec sha; git is the real append-only anchor).

## Thesis
An off-chain attention spike reaches an exitable, past-t0 memecoin before on-chain price fully prices it
in. Entry on buyer-arrival acceleration (a rate 2nd-derivative, not price momentum), tier-1 exitability-
gated, convex exit. This is an OPTIMISTIC-BOUND cheap FILTER (snapshot fills + multiplicative two-leg
toll, no marginal-vs-executable gap modelled) — a KILL is decisive, a PASS earns only a causal V3, never
a money claim.

## Mechanism (frozen)
- Universe: DexScreener boosted Solana tokens (attention proxy, coin-mapped), identity-pinned pair.
- Entry, ALL of: pair age ≥ 60 min; m5 buys ≥ 10; m5 buys up ≥ 40% vs the prior obs on the SAME pair;
  m5 buys > m5 sells; price > prior price; tier-1 proxy gate PASS; not already open.
- Fill: `arena/fill.honest_fill_snapshot` — observed snapshot price, multiplicative two-leg toll
  (TOLL_BUY=TOLL_SELL=0.015). Explicit optimistic bound.
- Exit: `arena/exit_engine` widening trail 0.18/0.25/0.35, hard-stop −12%, 12h horizon. F1: every opened
  position resolves; a rug/unpriced coin is a total loss; stuck-open > 0 at decision invalidates the read.

## Pre-registered decision (N = 120 resolved DISTINCT mints)
Via `arena/scorer.decide` — a CLUSTER (block) bootstrap CI clustered by (mint, entry-day), NOT sd/√N.
- **PASS** (earns only a causal V3, NOT a money claim): bootstrap ci95_lo > 0 AND the F6 lagging-entry
  split (net-R vs minutes-since-first-seen) is not monotonically negative in time-since-boost.
- **KILL** (decisive): bootstrap ci95_hi < 0, OR event rate < 1 entry/week, OR the lagging-exhaustion
  signature, OR the resolved-rug tail carries the sign.
- **UNDECIDED:** CI straddles 0 → extend to N=200 once, then KILL if still straddling.

## Honest limitations (recorded up front)
- The boosted universe is PAID promotion, so attention has ALREADY arrived — the m5 acceleration likely
  LAGS the true buyer-arrival inflection (the F6 mirage). The genuine leading-arrival test needs the
  creation-anchored feed; the boosted universe cannot test the leading case. Logged, not hidden.
- The tier-1 gate is a count-based PROXY, not the validated B20B screen (whose 77.7%/69.7% are t0+60-slot
  numbers that do not transfer to this data path). Never reported as B20B.
- Snapshot fills are an optimistic bound; a PASS is necessary-but-not-sufficient.
