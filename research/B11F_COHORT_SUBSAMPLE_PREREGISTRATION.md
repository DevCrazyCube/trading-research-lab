# B11F — Cohort Subsample Preregistration (V1)

**Amended (handoff 239), still before any selected-set outcome exists:** (1) N set to
**5,000** with the overfitting rationale; (2) a **pilot disclosure** added — a cost
measurement preceded and informed N; (3) the redraw/resize prohibition **reworded** to
forbid resizing after the *selected set's own* outcomes are seen, not sizing from an
independent pilot (the earlier wording accidentally forbade both); (4) a **second selector
test** added, asserting the pilot artifacts are not selection inputs.

**Frozen 2026-08-08, before any outcome for this window exists.** Stage 4
(`signature_inventory`) has never run against B11a: `supervisor_state.json` shows
`stages_completed = [program_boundary, enumerate_creates, build_cohort]`, a
`Q07_stage_failed` quarantine on `signature_inventory`, and `stage_output_bytes: 0`.
No signature count, trade, graduation, price, or reserve exists for any curve here.
The rule below is written into that ignorance on purpose.

## Why

The B11a cohort is **33,866 curves** — every Pump create in a 24h window. Stage 5
fetches one `getTransaction` per signature. The pipeline was sized against the burned
B9 study's ~59 signatures/curve. A **direct measurement** (80 curves, fixed seed,
signatures at/below the cutoff) disproves that for this window:

| stat | value |
|------|-------|
| min | 1 |
| p25 | 2 |
| **median** | **31** |
| p75 | 2,178 |
| max | 11,102 |
| **mean** | **1,283** |

Mean × 33,866 ≈ **43.4M in-window signatures**. At the measured concurrent ceiling of
13.76 `getTransaction`/s that is **~36 days** for stage 5 (~86 serial). No worker count
closes it — a one-week stage needs ~72 calls/s, ~5× what the provider serves this
credential. This is a **scale** problem, not a tuning one; the earlier ~2.4-day estimate
extrapolated the burned per-curve rate onto a window ~22× more active per curve.

## The rule

Deterministic hash-threshold uniform sample. For each curve,
`key = int(sha256(SEED || mint))`; select the **N smallest keys**.

- **SEED** = `b11f-cohort-subsample-v1`
- **N** = **5000** (owner-set; the one operational knob — sets HOW MANY, never WHICH)
- Reproducible and tamper-evident: anyone recomputes the exact set from `(SEED, N)` and
  the cohort's mints. A changed SEED or N is visibly a different set.
- **Nested**: any N′ < 5,000 sample ⊂ the N=5,000 sample. Documented as a real property,
  **not used** — V1 fixes one N; any staged extension is a *separate* preregistered
  decision, because letting realised cost pick the final N once the selected set's
  outcomes are visible is a dependency on the study's own results.

### Why N = 5,000 (the overfitting rationale)

The failure that kills a strategy is not a slow start — it is **an edge fitted to noise**,
and sample size is the direct defence. This data is *hostile to small samples*: median 31,
max 11,102, so a few curves dominate any statistic and a heavy tail needs **more** sample
for the same confidence. At ~600 active curves a couple of outliers manufacture an apparent
edge; at ~1,500 that is much harder. 5,000 is also the **largest N that clears inside a
week** — ~6.4M signatures, ~5.4 days at 13.76/s — and of those, ~3,000 carry real history
and ~1,500 are genuinely active.

## The prohibition this document exists to enforce

**The selection key reads only `mint` and the frozen SEED.** It never reads a signature
count, trade, graduation, price, or reserve — those *are* the outcome, and dropping the
quiet tokens is exactly what would make collection cheap, which is exactly why it is
refused. Legitimate creation-time keys: random draw (used here), `launch_slot`,
`is_mayhem_mode`. The cohort table carries only creation-time columns and **no outcome
column**, so the rule cannot accidentally reach one. Two tests enforce this: (a) an **AST
test** that the selector's inputs are creation-time identity only; (b) a **pilot-isolation
test** that the pilot *code* contains **no selection machinery at all** — no executable
pilot module imports `hashlib` or references `sha256`, the frozen SEED, or `nsmallest`-style
hash ordering. The stronger form (absence of the machinery) survives someone later adding a
hash helper to a pilot script; "the selector doesn't import the pilot" does not. The check
is over the `.py` files (AST-parsed), not a substring grep — the README documents the
property in prose and so contains the words `sha256`/`smallest`.

**The boundary between legitimate sizing and forbidden resizing.** SEED and N are frozen.
*Forbidden:* redrawing, reseeding, or resizing once the **selected set's own outcomes** are
observed — after stage 4+ produces any signature count, trade, graduation, price or reserve
for a hash-selected curve. Choosing N from the study's own results is selecting on the
dependent variable. *Legitimate, and what was done:* choosing N from an **independent cost
pilot** that measured aggregates on separate random draws and never derived the hash order.
An earlier draft said "may not be resized after any cost or outcome is observed", which read
literally forbids the legitimate sizing too — corrected here deliberately, because a clause
forbidding something already done is one somebody quietly reinterprets later.

## Pilot disclosure — a cost measurement preceded and informed N

N=5,000 was chosen using a cost observation made **before** this document was finalised.
That is legitimate sizing, but only if disclosed and checkable.

- **What it was:** two cost-measurement draws unrelated to the hash rule — seed 11 / 40
  curves, seed 23 / 80 curves.
- **What it measured:** *aggregates only* — quartiles, mean, SD, projected total. These fed
  the cost model (median 31, mean 1,283, ~6.4M for N=5,000, ~5.4 days) and the choice of N.
- **What it did NOT do:** never computed `sha256(SEED‖mint)` for any curve, never derived
  the hash order, never looked at *which* curves the rule selects, never compared activity
  against selection status.
- **Why the distinction is the whole ballgame:** knowing *both* activity *and* the hash
  order would let someone tune N to include/exclude specific high-activity curves — N would
  become a **selection** knob, not a size knob. That channel is closed because the two inputs
  were never brought together, and test (b) makes it checkable in code.
- **Where:** versioned at `research/b11f/pilot/` (committed `58ef4c9`), with a README that
  records these are a **cost model, not a finding** (±29% at 95% — the 80-curve pilot's own
  error, not the draw) and keeps the corrected first-probe mistake on the record (a serial
  probe reporting 40 calls/s while measuring *itself* — flat 171ms, `1/0.171 = 5.85` being
  the plateau it mistook for the endpoint's). Fixed-seed, no credential, imports via
  `__file__` so they rerun from the versioned home.

## Cost is a draw, not a promise

At mean 1,283 sig/curve, N=5,000 projects ~6.4M signatures, **~5.4 days** at 13.76/s —
a *median-of-draws expectation*, not a guarantee, and the largest N that clears inside a
week. The draw is uniform, so it can pull several 11,102-signature tokens; stage-5 runtime
is a random variable whose upper tail the rule does **not** cap (capping would select
against high-activity curves — the forbidden dependency by the back door). Rule of thumb:
**~26h of stage-5 per 1,000 curves** at the mean rate, with tail risk above.

## Representativeness & the frozen studies

A uniform draw preserves the population's signature distribution in expectation, heavy
tail included; generalisation carries sampling error ~1/√N. B19b/c/d run unchanged on this
subsample with power reduced ∝ N/33,866 and wider CIs each must report. A preregistered
random subsample of a preregistered cohort, frozen before any outcome, is still
preregistration.

## What remains to build (after this doc is committed alone)

1. `scripts/b11f_cohort_subsample.py` — pure `selected(cohort_mints, seed, n)` + a CLI
   stage writing the subsampled cohort artifact stage 4 reads. Committed **after** this
   document so history proves the doc precedes the code.
2. Pipeline wiring so stage 4's `--source` points at the subsample (edits b11c + manifest;
   owner-authorized, reviewed both directions, as the cutoff fix was).
3. Tests + mutation sweep: (a) AST leakage test, (b) pilot-isolation test, (c) nested
   property.

This document **selects no curve**. It fixes the rule; realising the selection is a
separate, owner-gated step.
