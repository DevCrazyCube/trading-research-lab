# B14c — preregistration: candidate model families and the selection protocol

Date: 2026-08-02. Author: Claude (handoff 104).
Status: **FROZEN. Committed alone, before any implementation, before any window is eligible, and
before any fresh outcome exists.**

The machine-readable freeze is `research/B14C_MODEL_PREREGISTRATION.json`. This document is the
argument for it. Neither commit carries code, a fit, a metric or a number computed from data.

## 0. The tension in the assignment, stated rather than papered over

The brief asks for a design that binds to the **frozen 99-field feature contract** *and* says how the
model **compares against the frozen B11b no-model policies**. Those two things cannot both happen on
B11a, and it is worth being exact about why before anything is built on the assumption that they can.

- B13f §0 makes the 99-field contract **permanently ineligible for B11a**. B11a's maturity
  conditions and unlock evidence were written for a *no-model* baseline over a 17-field t0 contract.
  A 99-field vector there evaluates something nobody preregistered, on a window whose stopping rule
  was set for something else.
- B11b's *figures* are figures **about B11a**.

So the comparison cannot be "model on a future window versus B11b's published numbers". That
subtraction measures the difference between two windows and attributes it to the model.

The resolution this document freezes is a distinction between two different things inside B11b:

| portable | not portable |
| --- | --- |
| the **policy definitions** P0–P4, the four B10c horizons, the order size, the metric definitions, the multiplicity family size, the state-in-force label semantics | **every figure B11b computes on B11a** |

The policies are *rules*. They carry no fitted parameter and import nothing from the window they
were first written for, so re-instantiating them on the eligible window — same rows, same split
plan, same horizons as the model — is legitimate and is what "compares against the frozen B11b
no-model policies" has to mean. `cross_window_comparison` is refused **by name** in the frozen
block, because it is the reading a later reader will reach for by default.

`eligible_windows` is **empty**, and B11a can never enter it. Nothing may be fitted until a
superseding preregistration names a fresh window disjoint from every burned range and from B11a.

## 1. Why these four families and no others

Every candidate must be **exactly representable in integers and rationals**. This is not a style
preference inherited from elsewhere in the project; it is the condition under which a model artifact
can be hashed at all. A float coefficient serialised on two machines can differ in its last bits, so
two identical models hash differently — and worse, two different models can hash the same. The
whole B14a envelope, and every `I01`–`I12` compatibility refusal built on it, rests on the artifact
hash meaning something.

| family | what it is | why it is here |
| --- | --- | --- |
| **F1** `constant_prior` | the training-fold base rate | the degenerate reference. A family that cannot beat it learned nothing, and publishing it makes that visible instead of arguable. |
| **F2** `single_threshold_stump` | one feature, one threshold | the simplest model that can use a feature at all: the honest floor for "the vector carries signal". |
| **F3** `depth_limited_cart` | depth ≤ 3, exact rational Gini | bounded interaction structure, still fully auditable — you can read the whole model. |
| **F4** `rational_gradient_boosted_stumps` | additive stumps over rational residuals | the one family with capacity beyond a shallow tree, bounded hard so its capacity is *declared* rather than discovered. |

Boosting stays exact by **quantising to a fixed denominator of 10¹²** after every round, rounding
half to even. Without that, exact rational residuals compound and denominators grow without bound;
with it, the arithmetic is integer, deterministic, and identical on every machine.

Notable exclusions and their reasons are in the frozen block. Two are worth repeating here:

- **Logistic regression, neural networks, SVMs** — excluded on the float objection above, not on
  any judgement about their merit.
- **Monotone-constrained variants** — *deferred, not refused*. A monotone direction per feature is a
  directional hypothesis, and we have no basis for one that was not obtained by looking at outcomes.
  A superseding preregistration stating each direction and its prior justification may admit them.

## 2. Preprocessing: the parts that are usually where the leak lives

Nothing is scaled, standardised, normalised, log-transformed, ranked, quantised into buckets or
target-encoded. Trees do not need any of it, and every one of those is a transform fitted on a
distribution — which, computed outside a training fold, has already seen the evaluation data.

There is **no feature selection step**. All 99 fields are offered to every family. A family that
ignores a field does so by fitting; it does not get to have a selection step that looked at the data
first and then claim the fit was honest.

Two rules do real work:

**Rational pairs are one feature, not two.** Twelve of the 99 fields are numerator/denominator pairs
(§`preprocessing.rational_pair_handling`). A split on a numerator alone is refused, because a
numerator without its denominator is not a quantity — `top_1_units = 5` means nothing until you know
whether the denominator is 10 or 10⁹. Splits compare the exact rational by integer cross-
multiplication, so no division and no float ever occurs.

**Threshold candidates come from training folds only.** This is the quietest leak available in tree
fitting: CART's candidate cut points are derived from the observed values, and if they are derived
from all rows then the evaluation fold has chosen where the model is allowed to cut. Candidates are
midpoints between consecutive distinct *training-fold* values, expressed exactly as rationals, and
the candidate set is declared to the artifact as a fitted transform naming its folds — so B14a `I10`
refuses it if it ever names a non-training fold.

## 3. Missingness: unavailable is not zero

Row-level unavailability (B13f `V01`–`V07`) produces no training row and no prediction. Field-level
nulls — the optional fields governed by `concentration_owner_grouping_available` and
`concentration_creator_share_available` — go down a **dedicated third branch** at each node, whose
direction is fitted on training folds only.

Both availability flags are themselves features (fields 70 and 93 of the frozen contract), so the
model can see "we cannot say" *as itself* rather than inferring it from a substituted number.

Twelve imputation strategies are refused **by name**. The reasoning is B13f's, unchanged: a zero
claims the thing did not happen; a median claims this subject was typical and is fitted on a
distribution; and a missingness encoding chosen because it improved a score is the outcome entering
through the door marked "handling missing data".

## 4. Selection

Fit on training folds. Select on validation folds. **The test fold is scored exactly once, with
exactly one configuration, after the selected configuration's artifact hash is recorded.** Walk-
forward only — no k-fold shuffling, no repeated CV, no re-use of any evaluation row.

**The selection metric is the exact rational Brier score, lower is better.** Three reasons, and each
one rules out an alternative:

1. It is a **proper** scoring rule, so it cannot be improved by miscalibration.
2. It is **threshold-free**, so no decision threshold gets chosen during selection. A metric needing
   a threshold makes the threshold a second, unpriced selection.
3. It is **exactly computable** as one rational over a common denominator — never a mean of rounded
   terms.

Selecting on **realised capital-weighted return is refused**: over a validation fold it picks the
configuration that happened to catch that fold's few largest winners.

**Tie-breaks are a total, deterministic order**: lower Brier → fewer fitted parameters → lower family
index → lower grid index. Nothing is ever resolved at random, and nothing is resolved by whichever
configuration happened to be enumerated first.

**Multiplicity is counted and published, not absorbed.** 15 configurations × 4 horizons = **60**.
The primary horizon alone carries 15. B11b's baseline family of 16 is counted **separately** and
neither family absorbs the other — merging them would shrink the correction, which is the cheapest
way to make a selected cell look primary. No test is computed here; grouped uncertainty is an
assumption-free jackknife spread over the split plan's exact-identity groups.

## 5. Calibration

`isotonic_pava_exact_rational`, always applied, fitted on a **dedicated calibration sub-fold** that
is chronologically last within the training segment and disjoint from the fitting sub-folds.

Calibration is deliberately **not selectable**. Making it an option doubles the family and invites
choosing it because it scored better. PAVA is exact over rationals and monotone; Platt and
temperature scaling are excluded on the float objection; chosen-edge histogram binning is excluded
because the edges are themselves a fitted choice.

## 6. Abstention and out-of-distribution behaviour

An abstention is a **declared non-decision**: counted in the census, deploying no capital, mapped to
B14b's `no_decision` bucket, which is not at-risk. It is never a prediction of the negative class —
that recoding is exactly what B14b exists to prevent.

`A01` unavailable vector · `A02` required denominator zero · `A03` inference-incompatible ·
`A04` feature outside its training-fold range · `A05` a null at a node whose training folds had no
nulls, so no direction was ever fitted · `A06` window not eligible (currently: every window).

`A04` is the OOD rule and deserves its reason. A tree predicts an out-of-range value from a leaf
whose support never contained anything like it — that is an extrapolation the fit never saw.
Recording it as an abstention keeps it in the census instead of dressing it as a prediction.

**The abstention rate is not a knob.** No threshold governs it and it may not be adjusted after any
result is seen. It is reported per code.

## 7. What the comparison must publish

Against P1 (primary), with P0 and P2 as accounting controls, on the same window, rows and split
plan, paired per B14b — exactly the rows where both sides produce an outcome, never a caller-supplied
cohort.

Mandatory: every headline on **both** bases; `model_evaluable_only`, `baseline_evaluable_only` and
their difference; **both entry counts**; abstention counts per code; the grouped jackknife spread.

The entry counts matter more than they look. **A model that abstains heavily can post a better
per-position figure while deploying almost nothing.** Publishing both entry counts alongside both
bases makes that visible rather than arguable.

**What would count as evidence:** the selected configuration beats P1 on the primary metric on the
test fold, on *both* bases, by more than the grouped jackknife spread.

**That is not a pass/fail gate**, and none is preregistered. Nobody here has earned a good-enough
line, and the **funding-cluster leakage gate remains open regardless of any figure** — two actors
can be one person without sharing an address, so a split this design calls clean may still put one
operator on both sides.

## 8. What this document does not do

No fit, on any real data. No B11a composition inspected, no outcome queried, no threshold taken from
a burned outcome distribution. U4 and U5 untouched. Nothing signed, submitted or traded. The live
watcher unaltered. No dependency added.

`performance_status` is `not_evaluated`, `publication_grade` is false, `model_eligible` is false and
`eligible_for_b11a` is false — all locked.
