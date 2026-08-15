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

Step 2's exact flag spelling is to be read from `--help` at run time, **not guessed** — the
observation-cutoff argument must be `438,854,169`, window 2's own value from the frozen B11M window,
and must not be taken from window 1's `437,211,659`.

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

## The one parameter, and where its value comes from

`observation_window_end_slot` is the only value that differs between windows. It is **not a choice**:
it is the observation cutoff derived by `B11A.derive_window` from the frozen B11M register, and for
generation 2 it is **438,854,169**. Using window 1's value would silently truncate the label window.

Recorded because it is the single place where a wrong number would produce a plausible-looking result
rather than an error.
