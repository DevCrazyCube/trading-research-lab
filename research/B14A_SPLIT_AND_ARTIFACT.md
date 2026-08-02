# B14a — the split that cannot see forward, and the envelope that cannot be misused

Date: 2026-08-02. Author: Claude (handoff 92). Offline, synthetic only.
Code: `scripts/b14a_split_planner.py`, `scripts/b14a_model_artifact.py`,
`scripts/b14a_split_fixtures.py`. Schema: `docs/SPLIT_AND_ARTIFACT_SCHEMA.md`.
Tests: `tests/test_b14a_split_planner.py`, `tests/test_b14a_model_artifact.py`.

## 0. Scope, and what was not touched

Plumbing and synthetic rows only. **No model was fitted**, no weights exist, no window is eligible,
no metric was computed, no threshold was chosen, and **B11a was never accessed**. Funding-cluster
leakage remains an explicit open gate and nothing here closes it.

## 1. The leak that t0 cannot see

The obvious way to split time-series decisions is to sort by t0 and cut. It is wrong, and it is
wrong in a way that leaves no trace.

A decision at slot 1,950 sits comfortably inside a training range ending at 2,000. Its **outcome**
is observed over the following 600 slots — to 2,550 — which is inside a validation segment beginning
at 2,500. The row is therefore labelled by the period it is about to be evaluated against. Nothing
about its t0 says so, and the split looks clean.

So the purge is computed on `label_window_end_slot` and never on t0, and the fixture corpus contains
two rows with the *same* t0 and different label windows precisely so a test can show that t0 alone
cannot separate them.

The purge measures against the **earliest** evaluation instant. That is a simplification the
mutation sweep forced: chronology is already enforced, so validation always begins before test, and
a window reaching test has reached validation first. The per-segment loop had a branch that could
never fire, and it was removed rather than disclosed.

## 2. Pooling creator and user is the whole of R5

Grouping by row is not enough. Grouping by creator is not enough either, and the reason is worth
stating plainly: **an address that creates one token and trades another is one address.** If the
grouping keeps a creator-space and a user-space apart, the same person appears under two labels and
can sit on both sides of a boundary while every check passes.

So identities are pooled into one space and closed transitively. A—B through a shared creator and
B—C through a shared user put A, B and C in one group, and the fixture corpus contains exactly that
bridge — with nothing linking A to C directly — so that a non-transitive implementation fails
visibly.

A group spanning two segments is **dropped whole**. Splitting it would put an actor's own future in
their training set; keeping the larger half would select on which side happened to have more rows.

The group key is derived from the sorted membership rather than from whichever root the union-find
happened to pick, so two identical groupings cannot look different.

**Exact string equality only.** The union never consumes B13b association evidence, and a ledger
offered as a grouping — or as the artifact that would close the cluster gate — gets its own refusal
naming what it actually is.

## 3. A censored outcome is not a zero

`right_censored` and `unavailable` rows may not carry a label value at all: that is refused at the
door, so the recoding cannot happen before the planner ever sees the row. They are excluded from
every segment with a reason code, and a hand-built plan that assigns one is refused too.

The distinction matters because the two events have wildly different frequencies. Recoding "we
stopped looking" as "it went to nothing" does not add noise — it adds a systematic mass of false
negatives, concentrated exactly on the rows whose observation was cut short.

## 4. No defaults, and why the refusal says so

There is no default train range, validation range, test range, purge or embargo. Every one is the
caller's and must arrive with a preregistration reference and a rationale, and the refusal message
explains why rather than merely reporting a missing field: *a split boundary chosen after seeing
which side scored better is the oldest mistake in this field.* A module that supplied a default
would have made that choice for everybody who ever used it.

## 5. A plan must say which rows it planned

The mutation sweep found a genuine defect here, and the test that found it was checking something
apparently trivial: changing a row's t0 did not change the plan hash.

It did not, because the plan stored only row **identifiers**. The corpus underneath could have been
swapped for a different one — different t0s, different label windows, different labels — while the
plan hash stayed identical, and an artifact bound to that hash would have inherited the same
blindness. `row_evidence_sha256` now hashes the rows themselves. **A plan that cannot say which rows
it planned is not provenance.**

## 6. The envelope, and the three things it will not do

A fitted model is a claim about a specific matrix: these columns, in this order, labelled this way,
over these rows. Every one of those is invisible in the weights. A model handed a matrix whose
columns were reordered produces numbers with no error and no meaning; a model whose scaler was
fitted on validation produces numbers better than it deserves. Both are silent.

- **No default anything.** Hyperparameters must be declared by name before they may carry a value,
  so a parameter appearing later is *undeclared* rather than a new default — and a declared name
  with no value is a default hiding in the algorithm.
- **No transform fitted outside training**, calibration included. A probability calibrated on the
  evaluation fold is calibrated against the answer.
- **No performance claim.** `performance_status` is locked, `seal_artifact` takes no argument for
  it, and every claim status is refused by name — a status nobody listed is a status somebody
  invents. `eligible_for_b11a` is likewise always false and cannot be passed in.

**No floats anywhere**, hyperparameters included. A float is the quietest reproducibility failure
available: the same value serialised on two machines can differ in its last bits, so two artifacts
that are the same model hash differently — or two different models hash the same. The fixture
expresses a shrinkage of 1/10 as two integers for exactly that reason.

## 7. A bug in the fixtures that the tests found

The fixtures module originally loaded the planner and the artifact envelope as **two separate module
graphs**. Each then had its own `SplitRefused`, so the gate's `except SPLIT.SplitRefused` around an
artifact call would not have caught anything the artifact raised — the report would have come back
clean while silently missing every artifact refusal.

This is the same module-identity trap that has now appeared in four modules of this project, and it
is caught here only because a test asserted on the exception class. The fixtures now take the
planner *from* the artifact module, so there is one graph.

## 8. Measured — the synthetic fixture corpus

```
python scripts/b14a_split_fixtures.py --gate
```

| quantity | value |
| --- | --- |
| synthetic rows | 22 |
| identity groups | 19 |
| largest group (the A—B—C bridge) | 3 |
| folds planned | 1 |
| rows assigned — train / validation / test | 9 / 4 / 4 |
| rows excluded | 5 |
| — censored or unavailable | 2 |
| — purged for label-window overlap | 1 |
| — dropped for spanning segments (the role swap) | 2 |
| result independent of row order | **yes** |
| groups never span segments | **yes** |
| purge holds for every training row | **yes** |
| artifact sealed and compatible with its own request | **yes** |
| `publication_grade` / `model_eligible` refused | **yes / yes** |
| association ledger refused as a cluster artifact, by name | **yes** |
| errors | **0** |

**No metric appears in that report and none may**, and a test scans the report's *field names* for
metric-shaped words. It scans names rather than raw JSON because the report carries hex digests, and
a substring search over those matches `f1` and `auc` by coincidence — a check that fires on a hash
is a check nobody will keep.

## 9. Verification — 96 mutants, 96 killed, none disclosed

129 tests, 152 subtests; **1,901 passing repository-wide**.

Covering every failure mode the directive named: one-slot label overlap (4), purge boundary
off-by-one (7), actor bridge split across folds (3), creator/user role swap (4), B13b ledger used as
a group (5), censored-as-loss (4), mixed horizon (2), train/test reversal (5), transform fit on
validation (4), feature order set-equal but reordered (2), artifact hash drift (3), undeclared
parameter (6), seed drift (2), and a model artifact claiming B11a eligibility (4) — plus the status
gate, no-defaults, determinism and envelope shape.

**Nine survived the first run.** Two were unfireable code, **removed rather than disclosed**: the
per-segment purge loop's test branch, and a duplicate-assignment check that sat behind a range check
that always fired first — the duplicate check now runs before it, where it can fire and where its
message is the more useful one. Six were genuine gaps in the tests. One was an inert mutant that was
rewritten to be observable.

No equivalent mutants remain to disclose.

## 10. The open gate, stated concretely

Only `research_plumbing_only` is attainable. Before `publication_grade` or `model_eligible` may be
reached, a cluster artifact must exist that is calibrated against a set it will not be used on,
preregistered before the cohort was enumerated, complete and point-in-time at each row's own t0, and
provenanced. `ACCEPTED_CLUSTER_ARTIFACT_TYPES` is empty — not "none supplied" but "no type is
acceptable yet".

The honest statement of what this planner cannot do: **two actors can be one person without sharing
an address.** A split it calls clean may still put one operator on both sides, and exact-identity
grouping cannot see that. The gate is where that admission lives.

## 11. Not claimed

No model, no weights, no algorithm, no metric, no threshold, no cluster, no eligible window, no
performance figure of any kind. No operational readiness. The counts in this document are counts of
synthetic rows, folds, exclusions and checks.
