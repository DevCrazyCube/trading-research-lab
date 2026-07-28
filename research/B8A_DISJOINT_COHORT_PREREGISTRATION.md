# B8a — Disjoint evaluation cohort (preregistration)

**Frozen (document only):** 2026-07-28
**Status:** FROZEN, **not authorised to execute.** No enumeration has been run, no scanner exists,
no RPC call has been made under this design.
**Owner:** Claude (Seq 75)

This is the first cohort in this project intended for **model research** rather than instrument
validation. Everything in the B7 series was built to test the measuring apparatus. That work is
sufficient (see "What the instruments now support"), and continuing it has diminishing returns
against the actual objective.

## What this document decides, and what it deliberately does not

**Decides:** the slot window, the program regime, membership, the attributes recorded at launch,
the point-in-time and leakage rules, the observation cutoff and censoring rules, and the
completeness criteria.

**Does not decide, and must not be read as deciding:**

- **`D_dead`.** Still unset, deliberately. `DECISIONS.md` keeps it unset and requires any candidate
  to be derived on one burned sample and validated on a *disjoint untouched* window. This cohort is
  that disjoint window's sibling, not its derivation set.
- **Any label.** Executable return, drawdown, dump hazard, graduation and liquidity labels are a
  **separate freeze** that must be written before this cohort's outcomes are inspected.
- **Any feature.** Same reason.
- **Any model, baseline, or threshold.**

**The ordering is the point.** Freezing the window before the labels means the labels cannot be
chosen to suit a window, and freezing both before enumeration means the window cannot be reselected
after seeing outcomes. B7j's envelope was selected outcome-positive and is permanently burned as a
result; this design exists so that does not happen again.

**`docs/DEFINITIONS.md` is version 0.2 and remains an unratified proposal.** This preregistration
does not ratify it and does not depend on any contested definition in it. It uses only the
lifecycle **anchors** that exist on-chain in the pinned IDL — `CreateEvent`, `CompleteEvent`,
`CompletePumpAmmMigrationEvent`, `TradeEvent` — which are facts about the program, not definitions
under negotiation.

## Program regime — and why the existing cohort is in the wrong one

| Boundary | Slot | Date |
|---|---|---|
| Previous regime start | 422,112,651 | — |
| **Current regime start** | **433,095,571** | 2026-07-15 16:11:40 UTC |

**The B7e cohort's frozen regime is "after 422,112,651 and before 433,095,571" — the superseded
one.** Any lifecycle rate, silence distribution, or graduation frequency inherited from B7e
describes a regime the project has already left. B7e remains valid for what it was for
(methodology development, and it is burned anyway), but it is not a basis for current-regime
modelling.

This cohort is therefore frozen **entirely inside the current regime**. If a further program
upgrade lands at a slot below this cohort's observation cutoff, the cohort spans a boundary and
**must be reported as regime-split rather than silently pooled** — the run fails visibly and the
split is recorded.

## Burned-range register

The window must not intersect any of these. All are on the record in `DECISIONS.md`.

| Range | Origin | Status |
|---|---|---|
| `[429,998,000, 430,000,000)` | B7e mature cohort | burned |
| `[430,000,000, 430,000,500)` | B7d engineering pilot | burned |
| `[435,564,885, 435,565,324)` | B7j / B7k envelope | burned |
| `435,566,652 – 435,566,690` | B7b dead-threshold sample | burned |

## Window selection rule — mechanical, derived, not searched

The rule is stated so the window is fully determined by numbers already recorded elsewhere. **No
candidate window was inspected and rejected.**

1. **Anchor** = the current regime start, `433,095,571`. A recorded measurement, not chosen here.
2. **Settling margin** = one day of slots, to avoid the regime-transition transient at the
   boundary. B0f observed the first local `collect_creator_fee_v2` in the post-upgrade window, so
   the transition is known to carry atypical traffic. One day = **206,793 slots**, from a slot rate
   of **2.3934 slots/s measured on 438 consecutive B7j blocks over 183 s** — an existing artifact,
   not an assumption.
3. **Launch window** = the **2,000 slots** beginning at anchor + margin. The length 2,000 is
   inherited verbatim from B7e so it cannot be tuned here.
4. **Observation cutoff** = **435,570,000**, reused verbatim from B7e's frozen cutoff. Reusing an
   already-frozen number is the least gameable available choice, and the cutoff is known-good:
   B7b observed to 435,566,690 and B7j to 435,565,323.

**Resulting frozen window:**

| Quantity | Value |
|---|---|
| Launch window | **`[433,302,364, 433,304,364)`** — half-open, 2,000 slots |
| Observation cutoff | **435,570,000** |
| Observation tail | 2,265,636 slots ≈ **10.96 days** |
| Regime | current; entirely after 433,095,571 |

Disjointness is checked against every entry in the burned register above: the nearest burned range
begins at 435,564,885, which is 2,260,521 slots after this window ends.

**Honest limitation of the tail.** ~11 days is materially shorter than B7e's ~26 days. It is the
price of staying inside the current regime, which began only ~12 days before the cutoff. Any
question needing a longer horizon than 11 days **cannot** be answered by this cohort and must not
be attempted on it. This is a real constraint on what labels the later freeze may define.

## Membership

Every exactly decoded `CreateEvent` in the launch window is a member. **There is no filter on:**

- later activity, history size, or whether the token ever traded again;
- graduation, completion, or migration;
- Mayhem or cashback status;
- quote mint;
- creator, user, name, symbol, metadata, or reserves.

Filtering on any of these would condition membership on outcome or on attributes whose selection
effects are unmeasured. Exclusions belong in a later, separately frozen policy — applied to a
recorded cohort, never to its construction.

Ledger-skipped slots are permitted only where absence is independently verified through
`getBlocks`. Any unexplained slot, create/event mismatch, unknown schema, or decode failure makes
enumeration **incomplete** and blocks every downstream conclusion. Fail visibly, never silently.

## Attributes recorded at launch

Recorded verbatim from the decoded `CreateEvent`, at launch time only:

`mint`, `bonding_curve`, `creator`, `user`, `timestamp`, slot and canonical chain coordinates,
initial virtual and real reserves, `token_total_supply`, `is_mayhem_mode`, `is_cashback_enabled`,
and **`quote_mint`**.

**`quote_mint` is mandatory and load-bearing, on B7k evidence.** B7k found the B7j window contained
a USDC-quoted graduation that went unnoticed through B7j's design, freeze, execution and audit, and
found that the field named `sol_amount` differs by roughly four orders of magnitude between quote
regimes — consistent with being denominated in the quote mint rather than in lamports, though that
reading is **not** established. Consequences, binding on this cohort:

- Every member carries its `quote_mint`, and the cohort must be reported **split by quote regime**,
  never pooled into a single rate.
- **No quote-denominated amount may be compared, summed, or averaged across quote regimes**, and
  none may be interpreted as lamports without branching on `quote_mint`.
- Mayhem members are recorded but flagged; they remain **excluded from any economic claim** until
  their non-trade mutations are captured, per the standing project exclusion.

## Point-in-time and leakage rules

1. **No future information may enter a launch-time record.** Every attribute above is present in
   the `CreateEvent` itself.
2. **Ordering is canonical** — slot, transaction index, outer instruction index, inner instruction
   index. Never database insertion order.
3. **Creator, funder and wallet histories, if used later, must be reconstructed as of the launch
   slot**, not as of enumeration time.
4. **Right-censoring is preserved.** A member's final silence at the cutoff is censored, never
   converted into an interior gap or into a terminal state.
5. **Completion and migration remain separate anchors.** Whether an interval can exist between them
   is an open question in `docs/DEFINITIONS.md` and must be measured, not assumed.
6. **The cohort is enumerated in canonical launch order**, not in order of activity, size, or
   affordability, so processing order cannot correlate with outcome.

## Completeness criteria

The cohort is usable only if **all** hold:

- every slot in `[433,302,364, 433,304,364)` is accounted for as retrieved or independently verified
  as skipped;
- zero decode errors and zero unknown event schemas within scope;
- every member's history is either complete to the cutoff or explicitly marked `incomplete` with
  its cap and failure reason — **never dropped, never replaced**;
- pagination and fetch caps appear in the output rather than as silent ceilings, the defect that
  invalidated the first `D_dead` estimate;
- the regime-split check passes, or the split is reported.

Partial results may report pipeline progress only. **No rate, distribution, or lifecycle statistic
may be published from an incomplete cohort.**

## What the instruments now support, and what they do not

**Support:** exact integer decode of quotes, fees and reserves; discovery recall validated on
`TradeEvent` (B7h) and on graduation anchors (B7j); decoder field assignment validated against
independent validator evidence (B7k); a free capture path.

**Do not support, and must not be assumed:** `D_dead` or any deadness threshold; label validity;
cross-regime transfer of any B7e statistic; **pubkey field identity** — B7k's C1 is a membership
test, so two transposed pubkey fields would still pass and this is undetected; any field with no
independent witness, including `sol_amount`, `mint_amount`, `pool_migration_fee` and the
`TradeEvent` reserve fields.

## Prohibited inferences, binding in every outcome branch

1. No performance, edge, or profitability claim. This cohort is a **substrate**, not a result.
2. No cross-regime generalisation to the pre-`433,095,571` regime or to any future one.
3. No `D_dead` adoption, and no reuse of this cohort to validate a threshold derived from it.
4. No pooling across quote regimes.
5. No claim requiring a horizon longer than the ~11-day observation tail.

## Execution authorisation

**This freeze does not authorise enumeration.** Executing it requires review of this document at
the hash recorded in `agent_discussion.md`, and explicit authorisation, recorded in the log **at
the moment it is given** — the B7j transcription gap is the reason that last clause is written in.

Estimated cost at execution: enumeration of 2,000 slots by full block decode, comparable to B7h's
2,000-slot scan, on the free public endpoint. Member history reconstruction is a **separate,
larger** cost and is **not** authorised by this freeze either; it needs its own scoped estimate
once member count is known.
