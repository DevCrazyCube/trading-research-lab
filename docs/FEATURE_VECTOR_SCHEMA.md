# Prospective feature vector schema — v1.0.0

Materialized by `scripts/b13f_feature_vector.py` against the frozen
`research/B13F_FEATURE_CONTRACT_PREREGISTRATION.md`.

Status: **contract and materializer only.** No model has been fitted, no transform selected, no
window is eligible, and no corpus has been read. Every vector exercised so far is synthetic.

## Two commits, in order

The 99-field contract was committed **alone** and first; the materializer came second. A feature
list committed alongside the machinery that computes it can always be claimed to have been trimmed
until the numbers came out well, and the git ancestry is the only evidence otherwise — so a test
asserts the contract's commit is an ancestor of the module's.

## No window is eligible, and B11a never will be

`eligible_windows` is **empty**. `assert_eligible` fails closed on everything, and B11a gets its own
refusal naming why: its evaluation was frozen as a **no-model baseline over B11b's 17 declared
fields**, and its unlock evidence was written against that. A 99-field vector there would evaluate
something nobody preregistered, on a window whose maturity conditions were set for something else.

**The B11a refusal is unconditional** — it does not consult the document's `eligible_for_b11a` flag.
That flag is pinned by the hash; the code's own refusal is independent of the document and strictly
stronger, so a contract re-pinned with `eligible_for_b11a: true` and B11a in `eligible_windows`
still cannot get a vector out.

Before any window may be added, a new training/evaluation design must name a fresh window, state its
split, and **fit every transform on training folds only**. Nothing here is a fitted transform, and
that is deliberate: there is nowhere in this contract to put one.

## The 99 fields

| block | source | count | naming |
| --- | --- | --- | --- |
| A | B11b's frozen t0 contract | 17 | **unchanged** — renaming would fork a frozen contract |
| B | B13a histories over the B13e lookback | 26 | suffixed `_in_lookback` — `_observed` says what we saw, `_in_lookback` says what we looked at |
| C | B13d concentration, both denominators | 56 | rationals flattened into named integer pairs |

Nothing is recomputed. Every value is read out of an already-validated B11b, B13a or B13d record
through that module's own validator, so a change upstream fails rather than silently diverging.

### Deliberately excluded, with reasons

| excluded | why |
| --- | --- |
| `counts_are_lower_bounds` | the window must be complete or the vector is unavailable, so it is a constant — and a constant is not a feature |
| `actor_seen_in_window`, `launch_observed_in_window` | derivable under a complete window, or a fact about the collection rather than the token |
| **every absolute slot number** | a calendar index. A model given one learns "later is better", which is not a property of a token and does not survive a different window. The relative spans carry the same information without the calendar |
| the token block's launch-transaction fields | exact duplicates of Block A; two names for one fact |
| B13b association evidence | declares itself `uncalibrated_evidence_only`; admitting it turns "we do not know" into a number a model weights |
| clusters, B13c text/URLs/handles, sentiment, engagement, market-cap transforms | judgements and identities, not observations |
| ranks, quantiles, logs, normalisation, standardisation | every one is fitted on a distribution, and a distribution computed outside a training fold has already seen the evaluation data |

A feature may never inspect an outcome, a label or any path state after t0.

## Types

**Integers, booleans and `null` only.** Every share travels as **two named integer fields** — a
numerator and a denominator — never as one number: a single `share` field is what a later model
adapter float-rounds. After gcd reduction the pair no longer carries the magnitude, so `*_units` and
`*_denominator_units` travel alongside; the ratio and the scale are different facts.

## Unavailable is not zero

| code | condition |
| --- | --- |
| `V01_history_incomplete` | a contributing history is truncated or short of the lookback |
| `V02_unresolved_decode_evidence` | unresolved decode evidence at or before this subject's t0 |
| `V03_concentration_not_atomic_or_incomplete` | the enumeration is incomplete, or the snapshot is not as of this t0 |
| `V04_required_denominator_undefined` | either required denominator is zero |
| `V05_evidence_after_t0` | a contributing record is as of a coordinate after t0 |
| `V06_source_hash_drift` | a source record does not hash to what it claims |
| `V07_contract_hash_mismatch` | the frozen contract is not the one this code was written against |

An unavailable vector carries **no feature block at all** — `features` is `null`, not an empty dict,
because an empty one invites a caller to fill it in. It must state at least one declared reason.

**Why not impute.** A zero claims the thing did not happen. A median claims the subject was typical,
and is computed from a distribution fitted outside any fold. A missingness flag whose encoding was
chosen because it improved a score is the outcome leaking in through the door marked "handling
missing data".

### Genuinely optional fields

| availability flag | governs | available when |
| --- | --- | --- |
| `concentration_owner_grouping_available` | 4 owner-grouping fields × 2 denominators | every token account has exact owner evidence |
| `concentration_creator_share_available` | 3 creator-share fields × 2 denominators | the creator binding is exact **and** every owner is resolved |

When a flag is false the fields it governs are `null` — **never zero**. A creator share of zero says
the creator holds nothing; `null` says we cannot say. A model that cannot tell them apart will learn
from the difference anyway. Both directions are checked: a false flag with a value, and a true flag
with a null, are each refused.

## Order is part of the contract

`feature_order_sha256` hashes the **order**, not the set. Two vectors with the same fields in
different positions are the same set and a different matrix, and a model trained on one and scored
on the other is wrong in every row. `assert_vector` compares `list(features)` against the frozen
order, and reports separately whether the set differs or only the ordering.

## Provenance and determinism

Every vector carries `schema_version`, the contract hash, the feature-order hash, its own t0
coordinate, and the source hashes it was built from. Canonical JSON, deterministic `vector_sha256`.

The materializer only reads its inputs — a test asserts it leaves all three byte-identical.

**Feature values are order-independent; evidence hashes are not, and should not be.** Two snapshots
differing only in account order produce identical features and *different* `concentration_sha256`
values, because the evidence block records the hash of the input actually consumed. Provenance that
ignored that would be provenance of something else.

## A known constant, disclosed

`concentration_supply_residual_units` is **always 0 in any available vector**: an incomplete
enumeration makes the vector unavailable, and B13d already refuses a complete enumeration with a
non-zero residual. It is retained anyway, as a tripwire — if a future edition ever relaxes the
completeness rule, the field is already in the frozen tuple and begins carrying signal without
forking the contract. A mutation that hardcodes it to zero is therefore an **equivalent mutant**,
disclosed rather than papered over.

## Measured

```
python scripts/b13f_feature_vector.py --contract
```

See `research/B13F_FEATURE_CONTRACT_PREREGISTRATION.md` for the full ordered tuple.

## Not covered

- Any model, fit, transform, threshold or score.
- Any eligible window, including and especially B11a.
- Any real corpus, feature value or distribution — none has been computed or reported.
