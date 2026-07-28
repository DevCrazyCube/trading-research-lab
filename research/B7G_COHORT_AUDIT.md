# B7g — Audit of B7e, and the Resumption Function the Summary Table Could Not Support

Run: 2026-07-27, approximately 17:20 UTC. Author: Claude (audit of Codex's B7e).
RPC via `SOLANA_RPC_URL`; key never printed or persisted. Read-only, no signing.

## 1. Completeness claim — VERIFIED independently

| Check | Result |
|---|---|
| `getBlocks(429998000, 429999999)` run independently | **1,996 slots present** |
| Implied skips | **4** — contiguous `429998132–429998135` |
| Codex's claim (1,996 retrieved + 4 verified skips) | **MATCHES** |
| `slot_scan` rows | 2,000 (full window accounted for) |
| `create_event` rows / `decode_error` rows | 200 / **0** |
| Artifact SHA-256s (launch db, lifecycle db, analysis json) | **all match** the published values |

The discovery-path completeness claim holds for the frozen window.

## 2. F53 — The published table reports numerators without denominators

B7e's trade-silence table lists, per threshold, the gaps and tokens that **resumed**. That is the
numerator of the quantity `D_dead` actually needs. The denominator — how many silences *reached*
that threshold at all — must also include the **right-censored final silences** that reached it and
have not (yet) resumed.

Computed from the lifecycle database (20,499 interior intervals + 199 final censored silences):

| Threshold | Resumed | Censored | Reached | **P(resume ∣ reached)** |
|---:|---:|---:|---:|---:|
| 1 h | 98 | 198 | 296 | **33.1%** |
| 6 h | 55 | 198 | 253 | **21.7%** |
| 12 h | 38 | 198 | 236 | **16.1%** |
| **24 h** | 27 | 197 | 224 | **12.1%** |
| 48 h | 15 | 197 | 212 | **7.1%** |
| 72 h | 11 | 197 | 208 | **5.3%** |
| 7 d | 5 | 195 | 200 | **2.5%** |
| 14 d | 1 | 194 | 195 | **0.5%** |

**This is the number that decides `D_dead`.** Declaring a token dead at 24 hours would be wrong
about **1 time in 8**. Codex's conclusion that 24 h is contradicted is correct, and this quantifies
by how much.

## 3. F54 — There is no knee, so `D_dead` is a cost trade-off, not a natural boundary

`P(resume)` decays smoothly — 33% → 22% → 16% → 12% → 7% → 5% → 2.5% → 0.5%. No threshold
separates "alive" from "dead"; each simply buys a lower false-death rate at the cost of a longer
required observation tail (`docs/DEFINITIONS.md` C2).

This reframes the decision. The question is **not** "where is the knee?" — my B7b framing, which
was wrong twice over — but **"what false-death rate is acceptable, and what observation tail will
we pay for it?"** Indicatively: 24 h costs 12%, 7 days costs 2.5% for a 7× longer tail, 14 days
costs 0.5% for 14×.

That is a decision for the owner, not a measurement, and it should be recorded as such.

## 4. F55 — 188 of 199 tokens died essentially at launch

Median final censored silence is **1,992,826 s ≈ 23.1 days**, against an observation span of
**23.1 days**. **188 of 199 tokens (94.5%)** have a final silence covering ≥90% of the entire span.

The cohort is overwhelmingly composed of tokens that traded briefly around launch and then never
again. This is a structural fact about the population that any cohort-based design must confront:
an exhaustive launch cohort is dominated by near-immediate deaths, so per-token backfill cost is
far lower than B6J's estimate assumed — but statistical power for anything conditional on survival
is correspondingly thin.

## 5. Limitations of this audit

- **Cutoff approximation.** I used the latest observed trade timestamp as the observation cutoff,
  not the block time of cutoff slot 435,570,000. The true cutoff is later, so final silences are
  longer than measured, more of them exceed each threshold, denominators grow, and
  **`P(resume)` above is therefore an upper bound.** The direction is stated rather than assumed —
  the mistake I made in B7b.
- **Interior gaps are clustered, not independent.** Several gaps can come from one token, so these
  are naive proportions, not survival estimates with grouped uncertainty. `PLAN.md` Phase 4 already
  requires grouped uncertainty; that applies here.
- **Bonding-curve recall is still unverified** — Codex's own open question. If that path misses
  trades, absent trades manufacture artificially long gaps, inflating both resumption counts and
  censored silences. This is the single most load-bearing unverified assumption in B7e.
- Development cohort; burned. No threshold may be both chosen and evaluated on it.

## 6. Recommendation

1. `D_dead` stays unset, and the choice should be framed as an explicit false-death-rate budget
   rather than a search for structure that does not exist.
2. Verify bonding-curve recall before any threshold is chosen — a block-level cross-check over a
   small slot range, comparing `TradeEvent`s found in blocks for cohort mints against those present
   in the bonding-curve-derived history.
3. Preregister a disjoint validation window before testing any candidate, as Codex requires.
