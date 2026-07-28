> # SUPERSEDED — do not cite as the B8a design
>
> **2026-07-28.** Two B8a preregistrations were frozen concurrently. The owner authorised the
> other one: `research/B8A_DISJOINT_COHORT_PREREGISTRATION.md`, freeze SHA-256
> `59da9f8d511605f1b8160233feeb14755b96472a2cd83f172b7fd71daff1d1cf` (`agent_discussion.md`
> Seq 77). **That document, not this one, governs the cohort.** This file is retained as a design
> record only, so the reasoning survives and so a reader who finds it cannot mistake it for the
> live specification.
>
> **One thing here is not superseded and must not be lost with the rest.** The observation tail
> and `D_dead` are coupled, and the authorised design fixes the tail at ~10.96 days without
> resolving `D_dead`. Verified arithmetic on that tail:
>
> | `D_dead` | usable observation after it | reachable? | false-death rate (B7g) |
> |---|---:|---|---:|
> | 24 h | 9.96 d | yes | 12.1% |
> | 72 h | 7.96 d | yes | 5.3% |
> | 7 days | 3.96 d | yes | **2.5%** |
> | 14 days | −3.04 d | **NO** | 0.5% |
>
> So the accepted tail **caps `D_dead` at about 7 days**, and 14 days is unreachable in this
> cohort at any price. Since B7g found **no knee** in the resumption curve, this is not a
> parameter waiting to be discovered — it is a false-death-rate budget, now additionally bounded
> by a tail that was accepted before this consequence was visible. **That remains an owner
> decision** and is recorded in `agent_discussion.md` Seq 82.

# B8a — Evaluation Cohort Preregistration (SUPERSEDED design record)

**Frozen (document only):** 2026-07-28
**Status:** **SELECTION RULE FROZEN. WINDOW NOT YET INSTANTIATED — blocked on an owner gate.**
**No RPC call has been made. No window has been inspected. No scanner exists.**
**Author:** Claude (ownership recorded in `agent_discussion.md` Seq 75 before this file was written)

## Purpose

This is the first step aimed at the project's actual objective — establishing whether a positive
executable edge exists — rather than at validating instruments. The instruments are now good
enough: the decode path reconciles exactly at integer precision, discovery recall is validated for
both `TradeEvent` and the graduation anchors, and a free capture path exists.

What does **not** exist is any evidence either way about an edge. This document freezes how the
evaluation cohort will be selected, **before** any window is looked at, so the selection cannot be
tuned to a result.

## Why the rule is frozen now and the window is not

The concrete slot range **cannot** be fixed yet, because its length depends on `D_dead`, which is
unset and is an owner decision (see the gate below). Rather than wait and then choose a window with
the answer in view, the **selection rule** is frozen here in full. When the gate clears, the window
is *computed* from the rule, not chosen.

This ordering is the entire point. A rule frozen before the data cannot be reverse-engineered from
it.

## Disjointness — the cohort must avoid every burned range

Four ranges are burned and permanently excluded from training, validation and test:

| Range | Origin |
|---|---|
| `[429,998,000, 430,000,000)` | B7e mature cohort |
| `[435,564,885, 435,565,324)` | B7j/B7k positive-control envelope (burned 2026-07-28) |
| `435,566,652 – 435,566,690` | B7b `D_dead` throwaway sample |
| `435,569,119 – 435,569,149` | B7c trade-only gap sample |

**Frozen rule:** the cohort launch window and its entire observation span must be **disjoint from
all four**, with no partial overlap. Disjointness is asserted programmatically before any fetch and
fails closed.

## Frozen selection rule

1. **Membership is fixed at launch.** A token enters the cohort if and only if it emits a
   `CreateEvent` inside the launch window. Nothing may enter later.
2. **Exhaustive within the window.** *Every* `CreateEvent` in the window enters. **No filtering on
   any attribute** — not creator, not name, not initial reserves, not `is_mayhem_mode`, not
   `quote_mint`. Filters are a *policy* applied later at decision time using only information
   available then; they are never a sampling step.
3. **No left-truncation.** A token may never be added because it later became interesting. This is
   the single most important anti-leakage rule.
4. **Window placement is deterministic, not chosen.** Once `D_dead` is ratified, the launch window
   is the **most recent** contiguous `W_launch` slots satisfying: disjoint from all burned ranges;
   ending at least `W_obs` before the current tip so every member has a full observation span; and
   lying entirely within one program regime (no loader `Upgrade` slot inside launch window or
   observation span — B0 established a ~13-day upgrade cadence, so this must be checked, not
   assumed).
5. **Regime recorded, not filtered.** Mayhem status and `quote_mint` are recorded as covariates for
   every member. Mayhem members are **excluded from the tradable population** at decision time —
   a policy, applied after selection — because B2a/B7a established Mayhem curves are mutated
   outside trading by `set_mayhem_virtual_params` and are therefore not reconstructible from the
   trade stream. They remain in the cohort for regime accounting.

## Frozen leakage rules (inherited from `docs/DEFINITIONS.md` §3)

- **C1** administrative right-censoring: members still active at observation end are censored, not
  dropped and not relabelled. Dropping is survivorship bias; relabelling is fabrication.
- **C2** launch window ends at least `D_dead` before the observation window ends.
- **C3** no left-truncation.
- **C4** exhaustive within window.
- **C5** any recorder `gap` overlapping a member's lifetime marks that member **incomplete**, and
  incomplete members are reported, never silently analysed.

## Frozen feature and label scope

**Features may use only information observable strictly before the decision timestamp.** The
decision point for each member is its `CreateEvent` slot plus a fixed offset frozen with `W_launch`.

**Known trap, frozen as a rule:** `sol_amount` **must not** be read without branching on
`quote_mint`. B7k found a USDC-quoted graduation in the B7j window whose `sol_amount` differed by
~4 orders of magnitude from the SOL-quoted case, consistent with denomination in the quote mint
rather than lamports. That inference rests on two observations and is **not** established — which
is exactly why the rule is defensive: any feature or label reading `sol_amount` must branch on
`quote_mint` or fail closed.

**Labels** are executable-return based, computed after costs, per `DECISIONS.md`. No chart return,
no unrealised peak.

## Frozen baselines — run before any model

Per `PLAN.md` Phase 4, and in this order:

1. **Do-nothing.** The hardest to beat after costs, and free to implement.
2. **Random entry** at matched frequency.
3. **Fixed-filter** — the public-bot archetype from `research/MEMECOIN_BOT_REPOSITORY_REVIEW.md`.

A model is only interesting if it beats these on **executable** return. If do-nothing wins, that is
the finding, and it must be reported as such rather than iterated away.

## OWNER GATE — instantiation is blocked

Three parameters remain unset, and two of them are the owner's to decide, not an agent's:

| Parameter | Status |
|---|---|
| `D_dead` | **UNSET — owner gate.** The 24-hour proposal was **withdrawn** (`DECISIONS.md`), so nothing is adopted. |
| `W_launch` | derived once `D_dead` is set |
| `W_obs` | `≥ W_launch + D_dead`; derived once `D_dead` is set |

**`D_dead` is a false-death-rate budget, not a research question.** The measurement is already done
(`research/B7G_COHORT_AUDIT.md`): P(a silence of length *t* ever ends) is **12.1% at 24 h**, 5.3% at
72 h, **2.5% at 7 days**, 0.5% at 14 days, and the curve has **no knee** — so there is no natural
boundary to discover. Choosing it is picking an acceptable false-death rate against the observation
tail it costs. That is an owner decision.

`docs/DEFINITIONS.md` also remains **unratified**, and this preregistration inherits its rules.

**Nothing may be instantiated, fetched, or scanned until both clear.**

## Gates

Read-only when it eventually runs. No signing, no spending, no deployment, no live or devnet
transactions. Credentials sourced silently and never printed or persisted.
