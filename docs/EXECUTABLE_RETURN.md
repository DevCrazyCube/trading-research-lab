# Executable Return, Drawdown, and Liquidity Failure

Version 0.1 — 2026-07-30. Author: Claude (`agent_discussion.md` Seq 222).
Status: **UNRATIFIED PROPOSAL.** `DECISIONS.md` remains authoritative. Nothing here is frozen, and
no parameter below may be treated as adopted because this document exists.

## Why this document exists

`PLAN.md` Phase 0 requires frozen definitions for *"rug, dump, graduation, executable return,
drawdown, and liquidity failure"*, and its gate reads *"labels, exclusions, and evaluation protocol
are documented before model research."* `docs/DEFINITIONS.md` (RATIFIED, v0.3) closes **graduation**
— T1/T1a/T1b — plus the terminal states and censoring rules C1–C5.

**Executable return, drawdown, and liquidity failure are defined in no document in this repository.**
They are the objective every promotion gate is stated against, so leaving them undefined means the
project's success criterion is currently unspecified. This proposal fills that, and only that.

### A conflict between two project documents, stated rather than resolved

`PLAN.md` line 31 places **rug** and **dump** in Phase 0. `DEFINITIONS.md` §2 deliberately defers
them to Phase 3:

> There is deliberately **no "rugged" terminal state.** Rug is an *outcome label* about price and
> extractable value, not a lifecycle state … "rugged" is usually recognised from post-collapse
> behaviour.

Both cannot be satisfied at once, and AGENTS.md forbids silently selecting the more convenient
claim. **This document does not define rug or dump.** `DEFINITIONS.md`'s reasoning is sound — a label
recognised from post-collapse behaviour is a leakage vector — but it is not this author's call to
retire a `PLAN.md` gate item. **Owner decision required:** either amend `PLAN.md` line 31 to move
rug/dump to Phase 3, or state that Phase 0 needs a leakage-safe rug definition and that Phase 0
cannot close without it.

## 1. Executable return

**Definition.** For one round trip in one token, executable return is

```
R = (Q_out - Q_in - C) / (Q_in + C)
```

where every term is an **exact integer lamport quantity** actually realised on chain:

| term | meaning |
|---|---|
| `Q_in` | quote lamports debited to acquire the position, from the entry transaction's own balance evidence |
| `Q_out` | quote lamports credited on exit, at the reserves in force **at exit time** |
| `C` | every cost enumerated below, including the cost of transactions that failed |

**Three properties are definitional, not implementation details.**

**1a. Integer-exact, never floating point.** The curve arithmetic is reproducible exactly:
`B2A_CURVE_CHAIN_CHECK.md` and `B2B_OFFICIAL_BUY_FORMULA.md` reproduced **11/11** sampled
exact-input buys, **9/9** legacy exact-token buys and **49/49** sells at integer precision, and
`B0E_TRADEEVENT_DECODE.md` verified the fee invariant

```
fee == ceil(quote_amount * fee_basis_points / 10_000)
```

with ceiling rounding, zero mismatches, at the observed 95/30 bps (0.95% protocol + 0.30% creator,
the documented 1.25%). A return computed in floats is a different number from the one the chain
produced, and `PLAN.md`'s Phase 2 gate already demands integer reproduction.

**1b. `C` includes failed transactions.** `PLAN.md` line 11 enumerates protocol fees, creator/LP
fees, base fees, priority fees, Jito tips, slippage, failed transactions, and unavailable exits.
Failures are not a rounding detail here: B9c measured that of **1,287,248** distinct in-window
signatures on the tradable population, only **94,985 (7.38%)** succeeded and **1,192,263** failed.
Whatever fraction of those a strategy would itself have submitted, a cost model that prices only
successful transactions is pricing a market that does not exist. Failed transactions commit no state
change — that is why B9d excludes them from *reserve* reconstruction — but they still cost fees.

**1c. `Q_out` is drawn against reserves at exit time, and may not exist.** See §3.

**What executable return is not.** Not chart return, not mark-to-last-trade, not the curve's
quoted price. `AGENTS.md`: *"Report executable returns after all costs; chart returns are not
trading returns."*

**Unmeasured components, named so they cannot be quietly assumed:** landing probability, contention,
priority-fee and tip levels required to land, and realised slippage under competition. `PLAN.md`
Phase 2's gate holds these to "separately documented statistical tolerances" against forward
observations. Until then, any `R` computed here is **simulated, not executable**, and must be
labelled so.

## 2. Drawdown

**Definition.** Drawdown is measured on the **executable exit value** path, not on price:

```
V(t) = quote lamports realisable by exiting the entire position at t, net of C
DD(t) = (max_{s<=t} V(s) - V(t)) / max_{s<=t} V(s)
```

**Why this is not a stylistic choice.** Marking a position at the curve's quoted price assumes a
counterparty at that price for the full size. B9a measured the opposite for most of this population:
for the 1,558 non-graduates, median terminal `real_quote_reserves` was **0.0000 SOL**, **94.6%** held
under 0.01 SOL, and **10.2%** were exactly zero. A price-marked drawdown series on those tokens
would report orderly decline where the truth is that nothing could be sold.

**`V(t)` is size-dependent** — exiting 100% and 10% of a position draw against the same reserves at
different marginal prices — so a drawdown figure without a stated position size is meaningless. The
denominator is the running maximum of executable value, not of notional.

**Explicitly unmeasured:** the reserve *path* between entry and exit. B9a's F2 was corrected
precisely because a terminal snapshot cannot report on the path — a curve that ran to 30 SOL and
fully round-tripped returns to its launch state, indistinguishable from one nobody ever bought.
**B9d exists to measure that path**, and until it publishes, no drawdown series on this cohort is
computable. Only the **159** curves at exactly zero with token reserves still at launch are provably
never traded.

## 3. Liquidity failure

Three distinct conditions, deliberately separated because they have different causes and different
consequences for a strategy. Reporting them as one number was the mistake F2 made.

- **L1 — No counterparty at any size.** `real_quote_reserves` is below the minimum economically
  meaningful exit at the evaluation instant. A position in L1 cannot be closed at all; it is not
  losing slowly.
- **L2 — Constrained exit.** A counterparty exists but cannot absorb the position at the quoted
  price. The realisable `Q_out` for the full size is materially below size × quoted price. This is
  the normal case and is what `PLAN.md` Phase 2 means by "constrained exits".
- **L3 — Structural unavailability.** Exit is impossible for a mechanical reason rather than a
  reserve level: the curve is `complete` so curve trading has ended, the token sits in **T1b**
  (completed, not yet migrated — duration unmeasured, `DEFINITIONS.md` §6.1), or the transaction
  cannot land.

**A threshold for L1 is deliberately not proposed here.** "Minimum economically meaningful exit"
depends on position size and on the cost floor of a landed transaction, and choosing a number now —
with B9a's outcome distribution already published and in view — would be selecting a definition
after seeing outcomes. That is the move the entire preregistration apparatus exists to prevent, and
Seq 178 already recorded one covariate contaminated exactly this way. **The threshold must be frozen
against a cost floor and a position size, before it is measured on any cohort, and it must not be
measured on B8b.**

## 4. What this document does not settle

- **Rug and dump** — the `PLAN.md`/`DEFINITIONS.md` conflict above. Owner decision.
- **The L1 threshold** — must be frozen a priori, per §3.
- **The subsampling rule** for a 24-hour launch window — still open per `DEFINITIONS.md`, must group
  by `creator ∪ user`.
- **Funding-cluster leakage** — unmeasured, and a superset of the actor-grouping problem.
- **Landing, contention, tip and slippage distributions** — Phase 2, against forward observations.
- **Any threshold on `R` or `DD`** that would constitute a promotion criterion. `PLAN.md`: numeric
  thresholds remain research hypotheses and must not be optimised repeatedly on the final test set.

## 5. Why this ordering matters

`PLAN.md`'s Phase 2 gate demands that reserve, quote, fee, rent, tip and cost calculations reproduce
observations exactly at integer precision. That gate cannot be evaluated while the quantity being
reproduced is undefined — the same structural problem `DEFINITIONS.md` §5 identified for "lifetime
transaction count", which was undefined until a terminal state was frozen.

The honest order is: **define the objective → measure the reserve path (B9d) → build the simulator
against a constrained-exit model → only then compute any return.** Claude 1 reached the same
conclusion at Seq 180 from the other direction: the next honest step after B9a was Phase 2 with a
constrained-exit model, not a model that assumes fills.
