# Split plan and model artifact schema — v1.0.0

Produced by `scripts/b14a_split_planner.py` and `scripts/b14a_model_artifact.py`.

Status: **plumbing only.** No model has been fitted, no weights exist, no window is eligible, no
metric has been computed and B11a is never touched. Every row exercised so far is synthetic.

## The three leaks the planner is built against

**1. The label window that outlives the boundary.** A training row's t0 can sit safely before a test
fold while its *outcome* is still being observed inside it — so the row is labelled by the very
period it is evaluated against. This is what a naive "sort by t0 and cut" produces every time, and
**t0 cannot see it**. The purge is computed on `label_window_end_slot`.

**2. The actor who spans the cut.** One creator with rows on both sides trains the model on their
own future. Grouping by row is not enough; grouping by creator is not enough either, because a
creator in one row can be a trader in another.

**3. The censored label read as a loss.** Recoding a right-censored outcome as zero teaches the
model that "we stopped looking" and "it went to nothing" are the same event, and the second is far
rarer.

## The rules, exactly

```
purge:    label_window_end_slot + purge_slots < first evaluation slot of the fold
embargo:  t0_slot >= previous_evaluation_last_slot + embargo_slots
```

The purge measures against the **earliest** evaluation instant. Chronology is enforced, so
validation always begins before test and a window reaching test has already reached validation; a
per-segment loop would carry a branch that could never fire.

Chronology is a single comparison chain — `train_last < validation_first <= validation_last <
test_first` — and folds must walk forward. Touching segments are refused: training ending on the
slot validation begins is not a boundary, it is an overlap.

**No defaults.** No train range, no validation range, no test range, no purge, no embargo. Each is
the caller's and must arrive with a `preregistration_reference` and a `rationale`. A split boundary
chosen after seeing which side scored better is the oldest mistake in this field, and a default
would make that choice for everybody.

## R5 — the exact-identity union graph

Rows are grouped by the **transitive closure of exact identity equality**, with creator and user
addresses **pooled into one space**:

- A—B share a creator, B—C share a user → A, B and C are one group.
- An address that creates in one row and trades in another is one address. Separate creator- and
  user-spaces would let the same person sit on both sides of a boundary under two labels.

A group may occupy **exactly one segment**. A group spanning two is **dropped whole** — splitting it
would put an actor's own future in their training set, and keeping the larger half would select on
which side happened to have more rows. `assert_split_plan` refuses any plan that ships one.

The group key is derived from the sorted membership, not from whichever root the union-find picked,
so two identical groupings cannot look different.

**Exact string equality only.** This union never consumes B13b association evidence.

## Censored labels

A row whose `label_status` is not `observed` may not carry a `label_value` — refused at the door —
and is excluded from every segment with reason `X01_label_not_observed`. `observed`,
`right_censored` and `unavailable` stay three distinguishable facts.

## Exclusion codes

| code | meaning |
| --- | --- |
| `X01_label_not_observed` | censored or unavailable; excluded, never recoded |
| `X02_purged_label_window_overlap` | the label window reaches an evaluation segment |
| `X03_embargoed_after_evaluation` | t0 falls inside the embargo after a prior evaluation |
| `X04_group_spans_segments` | an identity group would occupy two segments |
| `X05_outside_every_range` | declared for completeness of the vocabulary |

## Provenance

`row_evidence_sha256` hashes the **rows** a plan was built from, not merely their identifiers.
Without it a plan is a list of row ids and a set of ranges, and the corpus underneath could be
swapped for a different one — different t0s, different label windows, different labels — while the
plan hash stayed identical. A plan that cannot say which rows it planned is not provenance.

## The open gate

| status | attainable |
| --- | --- |
| `research_plumbing_only` | **yes** — the only one |
| `publication_grade` | no |
| `model_eligible` | no |

**Funding-cluster leakage remains open.** Two actors can be one person without sharing an address,
and this planner groups by exact identity only — so a split it calls clean may still put one
operator on both sides. Closing the gate needs a cluster artifact that is calibrated, preregistered,
complete and point-in-time, and provenanced. `ACCEPTED_CLUSTER_ARTIFACT_TYPES` is **empty**.

A B13b association ledger offered to close the gate gets its own refusal naming what it is: it
declares itself `uncalibrated_evidence_only` and its links explicitly do not assert common control,
so using it here would launder "we do not know" into a grouping that decides which rows may see each
other.

---

# The model artifact envelope

**Not a model.** No algorithm, no weights, no training loop, no metric. The envelope's job is to
make an incompatible artifact impossible to use by accident.

A fitted model is a claim about a specific matrix — these columns, in this order, labelled this way,
over these rows — and every one of those is invisible in the weights.

## What it binds

Feature contract hash and **feature order hash**, label preregistration hash, split plan hash and
status, target and horizon, algorithm **identifier**, declared hyperparameter names and their
values, random seed, transforms with the folds they were fitted on, calibration, training row and
evidence hashes, training fold ids, code revision and environment manifest.

## Three refusals

**No default anything.** No algorithm, hyperparameter, transform, metric or threshold. Every
hyperparameter must be **declared by name before it may carry a value**, so a parameter that appears
later is an undeclared one rather than a new default — and a declared name with no value is a
default hiding in the algorithm.

**No transform fitted outside training.** Every transform names its folds; any that is not a
training fold of the bound plan is refused. A scaler fitted on validation produces numbers better
than the model deserves, and nothing downstream can tell. Calibration is restricted the same way: a
probability calibrated on the evaluation fold is calibrated against the answer.

**No performance claim.** `performance_status` is locked to `not_evaluated`, `seal_artifact` takes
no argument for it, and `evaluated`, `executable`, `profitable`, `production_ready`, `validated` and
`live` are each refused **by name** — a status nobody listed is a status somebody invents. Likewise
`eligible_for_b11a` is always false and cannot be passed in.

## No floats, anywhere

A float hyperparameter is the quietest reproducibility failure available: the same value serialised
on two machines can differ in its last bits, so two artifacts that are the same model hash
differently — or worse, two different models hash the same. Rationals travel as named integer pairs
(the fixture expresses a shrinkage of 1/10 as `shrinkage_numerator: 1`, `shrinkage_denominator: 10`).
The type scan walks the whole envelope, including values nested inside a hyperparameter mapping.

## Inference compatibility

`I01`–`I12`. A request missing any declared field is **refused rather than passed**: a compatibility
check that skips a field is a check that passes for the wrong reason.

| code | fails on |
| --- | --- |
| `I01` | feature contract hash, or artifact hash drift after sealing |
| `I02` | **feature order** — the same columns in different positions is a different matrix |
| `I03` | contract version |
| `I04` | target or horizon |
| `I05` | split plan |
| `I06` | an undeclared hyperparameter |
| `I07` | a changed hyperparameter value |
| `I08` | seed drift — a run that cannot reproduce the weights has not checked them |
| `I09` | a differing transform set or differing fitted parameters |
| `I10` | a transform fitted outside training |
| `I11` | a performance claim |
| `I12` | a B11a eligibility claim, on the artifact or in the request's window |

## Measured

```
python scripts/b14a_split_planner.py --contract
python scripts/b14a_model_artifact.py --contract
python scripts/b14a_split_fixtures.py --gate
```

The fixture report publishes **fold counts, exclusion counts and hashes only** — no metric, no
score, no performance figure, because there is nothing to measure and a number would be read as one.
A test scans the report's field names (not its raw JSON, which carries hex digests) for
metric-shaped names.

## Not covered

- Any fitted model, weights, algorithm implementation, metric or threshold.
- Any eligible window, any status above `research_plumbing_only`, any cluster.
- B11a, which is never accessed and never eligible.
