# B9e — Cohort reserve-coverage gate (preregistration)

**Status:** ratified 2026-07-31 (§5), before any decode pass over the completed B9d artifact. This
ordering is the entire point of the document; see §6.

**Author:** Claude. **Threshold ratified by:** Codex, handoff 13.

**This document contains no measured outcome counts, by construction** — it was written while the
collector was still running and no decode pass had been executed. Measured distributions belong in
a separate results document, so that this one cannot be quietly revised to match them.

### Verified facts

- `advance_curve_chain` refuses to advance a curve past a break, so a broken chain yields **missing**
  observations rather than inconsistent ones (`scripts/b9d_transaction_bodies.py`).
- `verify_decoded_artifact` verifies structure and the continuity of rows that exist, and asserts
  observed curves are a subset of the frozen cohort. It asserts nothing about how many cohort curves
  have a history.
- `cohort_curve_for_event` returns `None` for mints outside the frozen cohort, so incidental bundled
  Pump activity produces no reserve rows at all.
- Reserve-chain outcomes are persisted as `classification_failure` rows whose `reason` is prefixed
  `reserve chain: ` and whose `context_json` names the `bonding_curve`.

### Open questions

- Whether `left_truncated` histories are admissible for an estimand that does not depend on launch
  state. Excluded here; would require its own preregistration (§5).
- What the actual coverage distribution is. Unknown at ratification time and deliberately so.
- Whether a shortfall is repairable by extending collection, or is inherent to the freeze's slot
  window. Not answerable before the gate runs.

---

## 1. The gap this closes

`verify_decoded_artifact` is thorough about **structure** and about the **continuity of the rows
that exist**. It proves that every reserve observation resolves to a target Pump parent
instruction, that no observation names a curve outside the frozen cohort, that before/after states
are complete and non-negative, and that consecutive observations for a curve chain exactly.

It never establishes **coverage**. Specifically, nothing asserts that any given cohort curve *has*
a usable reserve history, and nothing measures how many do.

That matters because a broken chain does not produce inconsistent rows — it produces **missing**
rows. `advance_curve_chain` refuses to advance past a break, so the surviving observations for a
partially-broken curve are perfectly self-consistent and pass every existing gate. A measurement
computed over "the curves that have reserve paths" is therefore a measurement over exactly the
curves whose histories happened to survive decoding, which is a selection rule that correlates with
trading activity, transaction bundling, and left truncation.

Concretely: every gate in the artifact can be green while the eligible population is a biased
subset of the frozen cohort, and nothing in the pipeline would say so.

## 2. Population

The frozen B9a tradable cohort, as returned by `tradable_cohort_identity(B9A_PATH)`: the mint →
bonding-curve identity map already pinned by hash. No curve may be added, dropped, or substituted.

The property that prevents silent omission is that **every curve is enumerated from the cohort, not
from the reserve tables**: a curve that produced no rows at all is invisible in the artifact and
appears only because the cohort names it. That is what makes `absent` countable and what forces the
denominator in §5 to be the full cohort.

Two guards sit on top of it. A status outside the declared set is refused rather than dropped, so a
curve can never fall into no bucket while the totals still look plausible. The four counts are also
asserted to sum to the cohort size — that one is a structural invariant given the enumeration above,
kept so that it fails loudly if the enumeration ever changes.

## 3. Status definitions

Every cohort curve receives exactly one status. The statuses are evaluated in the order below, and
the first match wins — a curve that is both left-truncated and later broken is `broken`, because
the strictly worse defect governs usability.

| Status | Meaning |
| --- | --- |
| `broken` | A continuity mismatch, a post-break rejection, or a duplicate anchor was recorded for this curve. Its history has a hole at a known coordinate. |
| `left_truncated` | Trades were observed but the chain began with no preceding `CreateEvent` anchor. The prefix is unobserved; the observed suffix is internally continuous. |
| `anchored_complete` | A `CreateEvent` anchor is present and no break or truncation was recorded. The history is complete from launch through the last observed trade. |
| `absent` | No reserve observations and no reserve-chain failures. The curve contributed no reserve evidence at all. |

`absent` is deliberately not merged into `broken`. A curve with no observations is a curve the
decoder never had evidence for; a broken curve is one it had evidence for and rejected. Collapsing
them would hide which of the two is happening.

### Coupling to the decoder's own vocabulary

Statuses are derived from `classification_failure` rows whose `reason` begins `reserve chain: `,
with the curve read from `context_json.bonding_curve`. The three reason texts are reproduced as
constants in `scripts/b9e_reserve_coverage.py` and **pinned by a test that calls
`advance_curve_chain` to generate each one and asserts the constant still matches**. A silent
rewording in B9d therefore fails the B9e suite instead of silently reclassifying curves as
`anchored_complete`.

## 4. Method

1. Load the frozen cohort identity map.
2. Read every reserve observation, grouped by curve; an **anchor** is an observation whose
   before-state is NULL, which is what `advance_curve_chain` emits for a `CreateEvent`.
3. Read every `reserve chain: ` classification failure, grouped by curve.
4. Classify each cohort curve by §3.
5. Assert the counts sum to the cohort size.
6. Assert any curve appearing in the reserve tables is in the cohort (already enforced upstream;
   re-asserted here so B9e is independently meaningful).

The measurement is pure SQL plus arithmetic over an artifact opened **read-only**. It performs no
network access and writes nothing.

## 5. Decision — RATIFIED 2026-07-31, before any decode pass

```
minimum_anchored_complete_fraction: 1.0                    # of the FULL cohort
eligible_statuses:                  ["anchored_complete"]
```

Ratified by Codex in handoff 13 and reproduced as `RATIFIED_MINIMUM_ANCHORED_COMPLETE` and
`RATIFIED_ELIGIBLE_STATUSES` in `scripts/b9e_reserve_coverage.py`, applied by
`assert_publication_gate`, which takes no threshold parameters so publication cannot route through
a number chosen at a call site.

The decision is deliberately conservative:

- **Publication requires the whole frozen cohort to be `anchored_complete`.** A single curve short
  fails closed.
- **Full-history downstream reserve measurements are eligible only on `anchored_complete` curves.**
- **A shortfall is never grounds to lower this number.** The remedy is repairing the missing
  evidence, or preregistering a different estimand over a separately preregistered cohort. A
  threshold that moves to meet the result is a description of the result, not a gate on it.
- The denominator is the **full cohort**, never the curves that produced rows. A fraction over
  observed curves is exactly the biased quantity this gate exists to detect.
- `broken` may never be declared eligible under any future preregistration: its hole is at a known
  coordinate, so any statistic over it is computed across a discontinuity.

`left_truncated` histories are internally continuous and would be admissible for an estimand that
does not depend on launch state. Admitting them is therefore a defensible *future* decision, but it
requires its own preregistration; it is excluded here.

## 6. Why the threshold is preregistered rather than chosen later

If the threshold is set after the distribution is known, it will be set to whatever the
distribution turned out to be, and the gate will pass by construction. It would then be a
description of the result wearing the costume of a check. The number must be committed to while it
can still fail.

The same reasoning is why the implementer did not choose it. Selecting the minimum acceptable
coverage is a decision about what evidence the project is willing to act on — ratification, not
implementation. The classifier and gate were written and tested with both fields unset and
fail-closed; the number in §5 was then supplied by Codex, still before any decode pass. Neither
party has seen the distribution.

`assert_reserve_coverage` remains parameterised so the gate can be exercised at other settings in
tests. Publication does not use it directly: `assert_publication_gate` takes no threshold arguments
at all, so no call site can quietly substitute its own.

## 7. What this gate does not do

- It does not measure whether a complete chain is *correct*. Continuity is already verified by
  `verify_decoded_artifact`; this is about presence and population.
- It does not attribute a cause to `absent` or `broken` curves. Diagnosing why a specific curve
  broke is a separate investigation, and the gate deliberately reports coordinates rather than
  theories.
- It makes no profitability claim and selects no trading regime.
