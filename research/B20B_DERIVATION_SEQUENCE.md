# B20B — the derivation sequence, fixed BEFORE window 2 exists

**Why this exists.** `B20B_DEADNESS_SCREEN_PREREGISTRATION.json` step 5 says *"run the pinned runner
ONCE against the collected window."* That is incomplete: **the runner cannot read the collection
directly.** Two derivation steps sit between them, and neither is part of b11c's ten-stage pipeline.

Discovered by checking, before the collection finished, whether the pinned runner could actually
consume window 2's output. It could not. **Finding this after a week of collection would have meant
choosing a derivation while looking at the data**, which is exactly what the frozen document exists to
prevent.

**This note does not amend the preregistration.** That document is frozen and stays frozen. This
records the operational sequence, fixed while the data is still unreadable, so that the path from raw
corpus to result is not a decision made later.

---

## What the pipeline produces, and what the runner needs

| ten-stage pipeline produces | pinned runner requires |
|---|---|
| `b11a_bodies.sqlite` ✓ | `--bodies` ✓ |
| `b11a_creates.sqlite` | |
| `b11a_cohort.sqlite` | |
| `b11a_subsample.sqlite` | |
| `b11a_signatures.sqlite` | |
| — | `--paths` **not produced** |
| — | `--identity` **not produced** |

Window 1's `b11a_paths.sqlite` and `b11a_identity.sqlite` were built days after its collection, by
separate tools.

## The sequence, fixed here

```
# 1. observed-state path corpus, derived from the bodies artifact
python scripts/b10b_path_dataset.py build \
    research/b11m_window2/b11a_bodies.sqlite \
    --out research/b11m_window2/b11a_paths.sqlite

# 2. t0 identities, derived from bodies + paths, with the window's own cutoff
python scripts/b10c_label_corpus.py build-identity \
    <bodies> <paths> --out research/b11m_window2/b11a_identity.sqlite

# 3. THE SINGLE PASS
python scripts/b20b_deadness_screen_runner.py \
    --bodies   research/b11m_window2/b11a_bodies.sqlite \
    --paths    research/b11m_window2/b11a_paths.sqlite \
    --identity research/b11m_window2/b11a_identity.sqlite \
    --out      research/B20B_WINDOW2_RESULT.json
```

Step 2 takes exactly two positionals — `artifact` (bodies) and `corpus` (paths) — plus `--out`.
**Verified against `--help`, not guessed.**

## Why this does not compromise blindness

**The derivation carries no choices.** Neither tool exposes a threshold, a cut point or a tunable
parameter — checked: zero module-level numeric constants in either, and no arguments beyond
input/output paths and progress reporting.

**Both outputs are content-hashed and record their provenance.** Window 1's metadata demonstrates the
pattern:

```
b11a_paths.sqlite     source_artifact: b11a_bodies.sqlite
                      canonical_order: slot,transaction_index,outer_index,inner_index
                      content_sha256:  5e4c139c…
b11a_identity.sqlite  source_artifact: b11a_bodies.sqlite
                      corpus_artifact: b11a_paths.sqlite
                      corpus_content_sha256: 5e4c139c…   ← chains to the paths hash
                      observation_window_end_slot: 437211659
```

So the derived corpus **chains by hash back to the collected bodies**, and any substitution or re-run
with different inputs is detectable. There is one derivation, it is deterministic, and it is written
down before the data exists.

## The parameter risk I flagged — CHECKED, and it does not exist

An earlier version of this note warned that `observation_window_end_slot` must be set to window 2's
**438,854,169** rather than window 1's **437,211,659**, and called it *"the single place where a wrong
number would produce a plausible-looking result rather than an error."*

**That risk is not real, and the check is the point of writing it down.** There is no such argument.
`b10c build-identity` takes only `artifact` and `corpus`; the window end is read from the **bodies
artifact's own recorded metadata** (`("observation_window_end_slot", cutoff[0])`), so it cannot be
passed wrongly because it cannot be passed at all.

**And there is a guard on top of that.** b10c compares the preregistration's stated window end against
the value the artifact recorded and **refuses on mismatch**:

```
if document["observation_window_end_slot"] != recorded_window_end_slot:
    ... "preregistration states observation_window_end_slot X but the artifact recorded Y"
```

So the one silent-wrong-answer path I could imagine is closed twice over: the value is derived rather
than supplied, and a disagreement between document and artifact is a refusal rather than a result.

*Recorded as a corrected warning rather than deleted, because "I flagged a risk, checked it, and it
was already handled" is worth more to a later reader than a note that never mentions it.*
