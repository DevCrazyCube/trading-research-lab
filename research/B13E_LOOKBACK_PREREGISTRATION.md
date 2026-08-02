# B13e — preregistration: the actor/token history lookback and collection contract

Date: 2026-08-02. Author: Claude (handoff 88).
Status: **FROZEN. Committed alone, before any chain query and before any B11a actor is enumerated,
inspected or read.**

This document is the whole of the first commit. No code, no test and no orchestrator accompanies it,
because a parameter committed alongside the machinery that consumes it can always be claimed to have
been adjusted until the machinery worked.

## 0. What has not happened

At the moment this is committed:

- **B11a has not been unlocked, enumerated, queried or read.** No actor, token, creator or trader
  identity from the fresh window is known to the author.
- **No chain query of any kind has been made** for this task — no RPC, no signature scan, no token
  account enumeration.
- **No actor history has been collected, and none has been looked at.** No count, no span, no
  distribution, no coverage figure from any real actor informed a single number below.
- B11b's frozen no-model baseline evaluation is untouched and this contract does not alter it.

## 1. The lookback: 1,642,509 slots, and it was not chosen

```
LOOKBACK_SLOTS = B9D_CUTOFF_SLOT − B8B_WINDOW_START_SLOT
               = 435,536,742 − 433,894,233
               = 1,642,509
```

Both operands were frozen long before this task. This is the **same quantity** B11a already inherited
as `observation_span_slots` and used to derive the fresh observation cutoff; recomputing it here is
arithmetic anybody can redo by hand from two constants already in the repository.

**Why reuse rather than choose.** A lookback picked after seeing how far back actor histories happen
to run is a lookback picked for its results — and the only histories available to look at are the
burned ones, whose outcomes have already been measured. Reusing the geometry the project is already
committed to removes the choice entirely: there is no free parameter here to tune, and no version of
this number that could have been made larger or smaller by anything observed.

The alternative — a round number in hours or days — would be worse in two ways. It would be chosen
(why 24 hours and not 12?), and it would require a slot-to-wall-clock conversion that is itself an
estimate with error.

### 1.1 It is never translated into wall-clock time

The lookback is **defined in slots and applied in slots**. It is not converted to seconds, hours or
days for any purpose, including presentation. Slot production rate varies, so a wall-clock lookback
is a different number of slots on every day it is applied, and a lookback whose length depends on
network conditions is not a frozen parameter.

Any downstream display may say "1,642,509 slots". It may not say "roughly N hours" without stating
that the conversion is an estimate outside this contract.

## 2. The window, per decision, with exact boundary rules

For a decision at t0 with canonical coordinate `(t0_slot, t0_tx, t0_outer, t0_inner)`:

```
lookback_start_slot = max(0, t0_slot − 1,642,509)

An event E is IN the lookback window  ⟺
        lookback_start_slot ≤ E.slot                                   (lower bound: SLOT-wise)
    AND (E.slot, E.tx, E.outer, E.inner) ≤ (t0_slot, t0_tx, t0_outer, t0_inner)
                                                                 (upper bound: COORDINATE-wise)
```

**The bounds are deliberately asymmetric, and the asymmetry is the point.**

- The **upper** bound is a leakage boundary. It must be exact to the instruction, and it is
  inclusive at t0's own coordinate and exclusive one coordinate later — the identical rule B13a
  already applies and publishes on every record.
- The **lower** bound is a coverage boundary. A whole slot is its natural unit: half a slot of
  lookback is not a meaningful quantity, and a coordinate-exact lower bound would make the window's
  effective length depend on where inside a slot the decision happened to fall. Two decisions one
  instruction apart would then have measurably different histories for no reason anybody could
  defend.

So the lower bound admits **the whole of** `lookback_start_slot`, inclusive.

### 2.1 Near slot zero

`max(0, …)` clamps the start; a negative slot is never computed and never queried.

**When the clamp binds, the window is shorter than the lookback, and that is left truncation.** The
per-actor coverage record must set `left_truncated = true` and the counts remain lower bounds. A
clamped window that reported itself complete would claim knowledge of a period before the chain
existed.

### 2.2 A short source reports incomplete — it never shifts the start

If a provider, an index or an artifact cannot reach back to `lookback_start_slot`, the collection
reports that actor's coverage as **incomplete**, naming the earliest slot it did reach.

It does **not** move `lookback_start_slot` up to whatever the source happened to have. Shifting the
start would silently redefine the parameter per actor, so that "no prior launches in the lookback"
would mean a different lookback for each one — and the actors with the shortest available history
would get the shortest window, which is precisely backwards.

## 3. Where the lookback reaches, and the burned-data rule

The reach is fully determined by §1 and §2 and is stated here so nobody has to rediscover it:

| decision at | lookback starts at | relation to burned territory |
| --- | --- | --- |
| 435,569,150 (first fresh launch slot) | 433,926,641 | 32,408 slots **after** the B8b start; deep inside burned territory |
| 435,772,750 (last fresh launch slot) | 434,130,241 | still inside burned territory |
| 437,211,659 (observation cutoff) | **435,569,150** | **exactly one slot after the last burned slot** |

The last row is a consequence of reusing the observation span as the lookback, not a design: because
the fresh window starts one slot after the maximum burned endpoint and the lookback equals the
observation span, the burned overlap decays to **exactly zero** at the observation cutoff. Nobody
arranged that; it falls out of the arithmetic.

### 3.1 Burned events may be CONTEXT. Burned members may never be EVIDENCE.

The lookback reaches into burned ranges for most fresh decisions, and that is legitimate: those
events genuinely happened before those decisions, and a creator's prior launch is a prior launch
whichever window it fell in. Excluding them entirely would be a different error — it would report
`prior_launch_count_observed = 0` for creators who demonstrably launched, and that zero would be a
collection artefact presented as a fact about the creator.

The distinction is between two roles a burned datum can play:

| role | permitted? | why |
| --- | --- | --- |
| a **prior event** in a fresh subject's history, at a coordinate genuinely before that subject's t0 | **yes** | it is point-in-time context; the decision could have known it |
| a **subject** whose outcome is evaluated | **no** | its outcome has already been measured |
| a **label** or outcome source | **no** | R3 |
| **tuning** data — anything that selects a transform, feature, threshold or model | **no** | the answers are already known |
| **performance evidence** — any number quoted as how well something works | **no** | it would be measured on data already used |

Stated as one rule: **a burned curve may appear in a feature and may never appear in a metric.**

The check that separates them is mechanical rather than a matter of care: every evaluated subject
must come from B11a's enumeration (§4), and B11a's window is disjoint from every burned range by
construction — that disjointness is already asserted by `b11a_window_freeze.assert_disjoint`. So a
burned curve cannot become a subject without violating a check that already exists.

## 4. Cohort scope: B11a's enumeration only, after unlock

Histories are collected **only** for the actors and tokens that B11a's own enumeration produces —
its creators, its launch signers, its t0 traders and its mints.

- **No wider population.** Collecting broadly and filtering afterwards would select on whatever the
  wider population happened to contain.
- **No narrower one.** Dropping cohort members whose collection is awkward would select on
  collectability, which correlates with activity.
- **Nothing before unlock.** No query may be issued until B11a's maturity condition is satisfied and
  its **U3** unlock criterion has passed. Before that the cohort is *unknown*, and a collection run
  that ran anyway would necessarily have chosen its own population.

**No history value or count may be inspected to decide collection depth.** The depth is
`1,642,509` slots, computed from t0 alone, before any history is read. There is no adaptive
deepening, no "collect more where it looks interesting", and no early stop where it looks empty.

## 5. Collection completeness

### 5.1 Per actor, and never averaged

Coverage is published **per actor**. A cohort-level fraction, mean or median is forbidden: one
actor's complete history does not make another's complete, and an average is precisely the statistic
that hides the single actor whose history is missing.

The gate follows from that rather than being chosen: **any** cohort actor whose coverage does not
reach `lookback_start_slot` makes the collection incomplete. There is no percentage to pick, because
picking one would require averaging.

An incomplete collection is **reported and stopped** (§7). Building a history over a short window is
legitimate; using one as though its counts were totals is not, and `require_complete_history` already
fails closed for exactly that.

### 5.2 Pagination must be exhausted, and exhaustion must be proved

Every paginated source records: the method, the page size, the number of pages, the final cursor,
and the **termination condition actually observed** (an empty page or an explicit end-of-stream —
never "we had enough").

A run that stops at a page cap has **not** exhausted the source. It must record the cap it hit, mark
that actor incomplete, and never present the truncated result as a full history. A silent cap is the
failure mode that produces a confidently wrong zero.

### 5.3 Source population and canonical ordering

Every collection names its `source_population` and the source hashes it was built from. Events are
ordered canonically by `(slot, transaction_index, outer_index, inner_index)` and **never** by
database insertion order or provider response order, which record when a collector wrote a row and
say nothing about when the chain produced it.

### 5.4 Decode accounting travels with every history

B13a's `decode_accounting` is required on every coverage record: the three partitions must sum, and
every piece of lost evidence must be listed with a coordinate and a reason code. **Decode loss is
not completeness loss's poor relation** — an instruction that would not decode produces no edge, and
no edge is indistinguishable from no funding.

Unresolved evidence at or before an actor's own t0 makes that actor's history incomplete
(`C04`), per subject and never per window.

### 5.5 Token-account snapshots must be atomic at one slot

Any holder snapshot feeding B13d must be captured at a **single pinned slot**, recorded as the
snapshot's `as_of` coordinate. Balances read across a range of slots are not a snapshot of anything:
a transfer between two reads can appear twice or vanish, and neither shows up as an error.

The declared supply must come from the mint account **at that same slot**, or the residual measures
a disagreement between two sources rather than the units nobody enumerated.

### 5.6 Raw preservation and provenance

Raw responses are preserved (or hashed where a licence forbids retention, per B13c's rules), with
the query specification pinned by hash. A parse can then be told from a refetch, and a reparse can
be redone without going back to the network.

## 6. Access rules

### 6.1 Method allowlist

Only these read-only methods may be called:

```
getSlot, getBlock, getBlockTime, getSignaturesForAddress, getTransaction,
getAccountInfo, getMultipleAccounts, getProgramAccounts,
getTokenAccountsByOwner, getTokenAccountBalance, getTokenSupply, getTokenLargestAccounts
```

Everything else is refused. Explicitly and permanently forbidden: `sendTransaction`,
`simulateTransaction`, `signTransaction`, `requestAirdrop`, and any method that submits, signs or
mutates. An allowlist rather than a denylist, because the next client version will add a method
nobody thought to forbid.

### 6.2 Credentials

Credentials are **environment-only and never persisted** — not in a record, not in a query spec, not
in a log, not in a report. The endpoint identity is stored as a hash. A query specification is
stored as a hash precisely so that one containing a key cannot sit in the clear.

Any record that would carry a credential-shaped string is refused rather than redacted, because a
redaction that fails silently looks exactly like one that worked.

## 7. Abort conditions

Each of these stops the collection and is reported. None of them is a warning.

| code | condition |
| --- | --- |
| `AB01_b11a_not_unlocked` | B11a maturity or U3 not satisfied at query time |
| `AB02_cohort_not_from_b11a` | a subject not produced by B11a's enumeration |
| `AB03_pagination_not_exhausted` | a page cap hit, or a cursor left unconsumed |
| `AB04_actor_coverage_short` | any actor's coverage does not reach `lookback_start_slot` |
| `AB05_decode_loss_at_or_before_t0` | unresolved evidence poisoning a subject |
| `AB06_snapshot_not_atomic` | holder balances spanning more than one slot |
| `AB07_source_hash_drift` | a source hash not matching what was recorded |
| `AB08_method_not_allowlisted` | a call outside §6.1 |
| `AB09_raw_not_preserved` | a response neither retained nor hashed |
| `AB10_lookback_formula_mismatch` | a computed endpoint differing from §2 by even one slot |
| `AB11_preregistration_hash_mismatch` | this document's frozen parameters not matching |

## 8. What this contract does not authorise

- **No cluster, no component, no merge, no probability.** B13b's ledger remains uncalibrated
  evidence and B13d's cluster adjustment remains structurally unavailable.
- **No threshold, veto, score, label or model.** This is a collection contract. Nothing here decides
  anything.
- **No change to B11b.** Its no-model baseline evaluation is frozen and this document does not touch
  it.
- **No collection.** This commit authorises a future run; it performs none.

## 9. Frozen parameters

The block below is the machine-checkable form of §1–§7. A validator committed later must hash it and
refuse to run against anything else.

```json
{
  "preregistration_id": "B13E_LOOKBACK_V1",
  "lookback_slots": 1642509,
  "lookback_derivation": "B9D_CUTOFF_SLOT - B8B_WINDOW_START_SLOT",
  "lookback_operands": {"b9d_cutoff_slot": 435536742, "b8b_window_start_slot": 433894233},
  "lookback_units": "slots",
  "wall_clock_translation_permitted": false,
  "lower_bound_granularity": "slot",
  "lower_bound_inclusive": true,
  "upper_bound_granularity": "coordinate",
  "upper_bound_inclusive": true,
  "minimum_slot": 0,
  "clamp_sets_left_truncated": true,
  "short_source_shifts_start": false,
  "cohort_source": "b11a_enumeration_only",
  "collection_before_unlock_permitted": false,
  "required_unlock_criterion": "U3",
  "coverage_granularity": "per_actor",
  "coverage_averaging_permitted": false,
  "pagination_must_be_exhausted": true,
  "page_cap_marks_incomplete": true,
  "canonical_ordering": ["slot", "transaction_index", "outer_index", "inner_index"],
  "decode_accounting_required": true,
  "snapshot_must_be_atomic_at_one_slot": true,
  "raw_preservation_required": true,
  "credentials_persisted": false,
  "burned_events_permitted_as_context": true,
  "burned_members_permitted_as_examples": false,
  "burned_members_permitted_as_labels": false,
  "burned_members_permitted_as_tuning_data": false,
  "burned_members_permitted_as_performance_evidence": false,
  "adaptive_depth_permitted": false,
  "clusters_permitted": false,
  "probabilities_permitted": false,
  "thresholds_chosen": [],
  "alters_b11b_baseline": false,
  "method_allowlist": [
    "getSlot", "getBlock", "getBlockTime", "getSignaturesForAddress", "getTransaction",
    "getAccountInfo", "getMultipleAccounts", "getProgramAccounts",
    "getTokenAccountsByOwner", "getTokenAccountBalance", "getTokenSupply",
    "getTokenLargestAccounts"
  ],
  "abort_codes": [
    "AB01_b11a_not_unlocked", "AB02_cohort_not_from_b11a", "AB03_pagination_not_exhausted",
    "AB04_actor_coverage_short", "AB05_decode_loss_at_or_before_t0", "AB06_snapshot_not_atomic",
    "AB07_source_hash_drift", "AB08_method_not_allowlisted", "AB09_raw_not_preserved",
    "AB10_lookback_formula_mismatch", "AB11_preregistration_hash_mismatch"
  ]
}
```

## 10. Attestation

Everything above was written from two frozen constants and the rules already committed in B13a–B13d.
**No actor identity, history, count, coverage figure or outcome was consulted, and none was
available to consult.** The one number in this document that could have been a free parameter — the
lookback — is a difference of two slots frozen in earlier phases, and there is no reading of the
evidence that could have moved it.
