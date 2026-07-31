# B9f — Classification-failure coverage gate (preregistration)

**Status:** drafted, ceilings **NOT ratified** (§5). `assert_failure_coverage` raises until they
are supplied, so the gate cannot pass by default.

**Author:** Claude. **Date drafted:** 2026-07-31, before any decode pass over the completed B9d
artifact.

**This document contains no measured outcome counts, by construction** — it was written while the
collector was still running and no decode pass had been executed. Measured distributions belong in
a separate results document, so this one cannot be quietly revised to match them.

### Verified facts

- `classify_instruction` returns a reason for every target-program instruction it cannot name: a
  short discriminator, or an unknown one. Neither is dropped, bucketed as `other`, or inferred from
  an adjacent event (`scripts/b9d_transaction_bodies.py`).
- `decode_artifact` persists those reasons into `classification_failure`, together with the
  eventless PumpSwap reserve candidate, reserve-chain discontinuities, and balance reconciliation
  mismatches and unresolved statuses.
- `verify_decoded_artifact` reconciles the **total** failure count against
  `decoder_classification_failures` metadata, and asserts each failure row resolves to a signed
  instruction coordinate. It asserts nothing about what the failures **are**, or how many there may
  be.
- Reserve-chain discontinuities are already governed by
  `research/B9E_RESERVE_COVERAGE_PREREGISTRATION.md`.

### Open questions

- The ceilings themselves (§5), which are a ratification decision.
- Whether any non-zero ceiling is defensible at all for `unknown_discriminator`, or whether an
  unknown target discriminator should always be repaired by pinning the interface that explains it.
- What the actual distribution is. Unknown at drafting time, deliberately.

---

## 1. The gap this closes

B9e bounds the **reserve** population. Nothing yet bounds the **instruction** population that sits
inside it.

`decode_artifact` records every unrecognised target discriminator rather than dropping it, which is
the correct behaviour, and the total is reconciled against its own metadata. But a decode pass
could produce a large and growing unknown-discriminator population, agree with its own metadata,
satisfy every structural gate **and** satisfy B9e, and still mean the instruction stream is not
understood. Nothing currently says how much of that stream the decoder actually recognises.

## 2. Population and denominator

The denominator is the **target instruction population**: rows in `instruction` with `target = 1`.
It is never the number of observed failures. A rate whose denominator is the failures themselves
cannot fall, so it measures nothing.

The load-bearing invariant is stronger than the rate:

> **Every target instruction is either named or explained.**

A target row with no `idl_name` and no failure at its coordinates was neither understood by the
decoder nor reported by it. That is invisible to any check that walks the failure table, because
there is nothing in the failure table to walk. It is refused here.

Non-target instructions may legitimately be unnamed: B9d does not pretend an arbitrary third-party
program has a Pump IDL. They are excluded from the denominator rather than counted as failures.

## 3. Categories

Every persisted failure must fall into exactly one category, matched by prefix against the reasons
the decoder emits. There is deliberately **no `other` bucket** — an `other` bucket is where an
unrecognised failure class goes to stop being noticed.

| Category | Meaning |
| --- | --- |
| `short_discriminator` | A target instruction whose data is too short to carry a discriminator. |
| `unknown_discriminator` | A target instruction whose discriminator is absent from the pinned IDL for its program. |
| `eventless_reserve_candidate` | A PumpSwap `init_boost` with no associated event, which §7 forbids assuming reserve-neutral. |
| `balance_unresolved` | A trade whose non-SOL quote mint/account identity is mixed or absent, so its quote flow cannot be reconciled. |
| `balance_mismatch` | A reconciliation disagreement that no same-transaction lifecycle confounder explains. |
| `reserve_chain` | **Delegated to B9e.** Validated here for coordinates and attribution, reported separately, and excluded from every B9f ceiling. |

A reason matching no category raises. A category matching nothing the decoder produces is dead
weight that reads as coverage, so each is pinned by a test that generates its reason through the
real producer.

`reserve_chain` is delegated rather than re-counted. Charging one curve break against two gates
would make neither number mean anything.

## 4. Method

1. Assert every failure carries a valid canonical coordinate (`inner_index` is `-1` for an outer
   instruction; only lower values are malformed) and resolves to a parent instruction with the same
   signature.
2. Assert no target instruction is silently unnamed (§2).
3. Count the target instruction population.
4. Categorise every failure reason (§3), refusing any that matches nothing.
5. Assert the categories account for exactly the persisted failure count. This one is a structural
   invariant given step 4 rather than an independent check — every reason either increments a
   category or raises — and is kept so that it fails loudly if step 4 ever changes.
6. Compare each category against its ratified ceiling (§5).

Read-only, offline, no network access, no writes.

## 5. Decision — RATIFIED 2026-07-31, before any full decode pass

Ceilings are absolute counts, one per category, and **must name every category**. A partial mapping
is refused rather than treated as unbounded for the rest: a category silently exempted from its own
gate is precisely the failure this design prevents. `reserve_chain` must **not** be given a ceiling.

```
short_discriminator:         0
unknown_discriminator:       0
eventless_reserve_candidate: 0
balance_unresolved:          0
balance_mismatch:            0
```

Ratified by Codex in handoff 17, frozen **from correctness invariants rather than fitted counts**,
and reproduced as `RATIFIED_CEILINGS` in `scripts/b9f_failure_coverage.py`, applied by
`assert_publication_gate`, which takes no ceiling parameters.

Every category is zero because every category is a statement that some part of the instruction
stream was not understood or not reconciled:

- `short_discriminator` and `unknown_discriminator` say the interface is not fully pinned. The
  remedy is pinning the interface that explains the discriminator, not tolerating a quota.
- `eventless_reserve_candidate` is a named, deliberately-preserved condition rather than a defect —
  but §7 forbids assuming it reserve-neutral, so an artifact containing one has an unresolved
  reserve transition in it and is not publishable evidence.
- `balance_unresolved` and `balance_mismatch` bound how far reserve evidence may disagree with the
  ledger. Zero is the only value consistent with treating a reconciliation as evidence.

**Interpretation flagged for correction:** handoff 17 named zero ceilings for unknown target
discriminators, unrecognised or unattributable classes, target-classification absence, reserve-chain
breaks and left truncation, clean lamport/token balance mismatches, and unresolved eventless reserve
transitions. It did not name `balance_unresolved` (mixed or absent non-SOL quote identity)
explicitly. It is set to zero here as the reading consistent with every other clause; if a non-zero
value was intended it must be ratified explicitly rather than inherited by omission.

Explicit same-transaction lifecycle or rent confounds are a separate matter and are **not**
`classification_failure` rows at all — `confounded_by_account_lifecycle` is counted in the decoder's
own tally. They may be counted and reported, are never reconciled evidence, and can never satisfy an
exactness gate. Their full-population denominator and named cause are preserved by B9d's balance
reconciliation, which this gate does not second-guess.

As with B9e: a shortfall is evidence to repair or grounds for a separately preregistered estimand.
It is never grounds to raise a ceiling after seeing the distribution.

## 6. Why the ceilings are preregistered rather than chosen later

Identical reasoning to B9e §6. A ceiling set after the distribution is known will be set above
whatever the distribution turned out to be, and the gate will pass by construction — a description
of the result wearing the costume of a check.

The classifier and gate are implemented and tested with the ceilings unset and fail-closed, so the
numbers can be ratified by someone who has not seen the distribution either.

## 7. What this gate does not do

- It does not decide whether a *named* instruction was decoded correctly; that is the decoder's own
  verification.
- It does not diagnose *why* a discriminator is unknown. It reports the coordinate and the count,
  and leaves the interface question to a boundary investigation.
- It does not re-judge reserve-chain coverage, which is B9e's.
- It makes no profitability claim and selects no trading regime.
