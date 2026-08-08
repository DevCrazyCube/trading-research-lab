# B11F — Cohort Subsample Preregistration (V1)

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
- **N** = **2000** (recommended; the one operational knob)
- Reproducible and tamper-evident: anyone recomputes the exact set from `(SEED, N)` and
  the cohort's mints. A changed SEED or N is visibly a different set.
- **Nested**: the N=1,000 sample ⊂ the N=2,000 sample. Documented as a real property,
  **not used** — V1 fixes one N; any staged extension is a *separate* preregistered
  decision, because letting realised cost pick the final N is a dependency on the
  aggregate outcome.

## The prohibition this document exists to enforce

**The selection key reads only `mint` and the frozen SEED.** It never reads a signature
count, trade, graduation, price, or reserve — those *are* the outcome, and dropping the
quiet tokens is exactly what would make collection cheap, which is exactly why it is
refused. Legitimate creation-time keys: random draw (used here), `launch_slot`,
`is_mayhem_mode`. The cohort table carries only creation-time columns and **no outcome
column**, so the rule cannot accidentally reach one. A test will assert the selector's
inputs are creation-time identity, read from the AST. SEED and N may not be redrawn after
any cost or outcome is seen.

## Cost is a draw, not a promise

At mean 1,283 sig/curve, N=2,000 projects ~2.57M signatures, **~2.2 days** at 13.76/s —
a *median-of-draws expectation*, not a guarantee. The draw is uniform, so it can pull
several 11,102-signature tokens; stage-5 runtime is a random variable whose upper tail
the rule does **not** cap (capping would select against high-activity curves — the
forbidden dependency by the back door). Rule of thumb: **~26h of stage-5 per 1,000
curves** at the mean rate — ~1,000 ≈ a day, ~2,800 ≈ three days, each with tail risk above.

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
3. Tests + mutation sweep for the leakage prohibition and the nested property.

This document **selects no curve**. It fixes the rule; realising the selection is a
separate, owner-gated step.
