# Evaluation report schema — v1.0.0

Produced by `scripts/b14b_evaluation.py`.

Status: **plumbing only.** No model has been fitted, no window is eligible, no real metric has been
published and no B11a outcome has been read. Every row exercised so far is synthetic.

## Every headline is published twice

**A headline computed on the rows that happened to be evaluable is survivorship, and it always
flatters.** The rows that fail to produce an outcome are not a random sample: a curve with no
observed state, a structurally unavailable exit and a right-censored horizon are exactly the
positions that went wrong in ways the pipeline could not price. Dropping them and reporting the mean
of what is left answers a question nobody asked.

So every headline figure appears on **two bases at once**, each labelled:

| basis | meaning |
| --- | --- |
| `observed_evaluable` | the figure over rows that produced an outcome |
| `whole_cohort_worst_case` | the same figure with every unevaluable at-risk row assigned the worst admissible outcome under the caller's declared rule |

A report carrying only one is refused. A headline metric present on one basis and absent from the
other is refused. Neither may be labelled as the other. **The truth about a cohort is somewhere
between them, and how far apart they are is the most informative number in the report.**

## Outcome buckets, inherited from B10c

| bucket | evaluable | at risk |
| --- | --- | --- |
| `marked_at_horizon` | **yes** | yes |
| `right_censored` | no | yes |
| `structural_exit_unavailable` | no | yes |
| `no_observed_state_in_window` | no | yes |
| `no_decision` | no | no |
| `not_entered_by_policy` | no | no |

Only `marked_at_horizon` carries a realised figure. A side in any other bucket carrying a
`net_pnl_lamports` is **refused at the door** — that is the recoding this module exists to prevent.
A side outside the at-risk buckets may not deploy capital at all: a decision the policy declined
risked nothing, so it cannot lose anything even under the worst case.

Every bucket is counted over the **whole cohort**, for both participants.

## Nothing has a default

No metric, class threshold, calibration bin edge, censoring treatment, worst-case rule or
performance cutoff. Each is the caller's and arrives in a metric spec with a preregistration
reference. Every recoding treatment anyone would reach for — `recode_as_zero`, `recode_as_loss`,
`impute_median`, `drop_silently`, `carry_forward` — is refused **by name**, and an invented one is
refused for not being declared.

**There is no performance cutoff field at all.** Nobody here has earned a "good enough" line.

## Exact arithmetic

Integers and gcd-reduced rationals; **no float anywhere**. A rate rounded once is a rate nobody can
reconcile against the counts it came from.

- **Capital-weighted return** = net P&L over deployed capital, on each basis's own denominator.
  Undefined over no capital — never zero.
- **Brier** is summed as one rational over a common denominator, not as a mean of rounded terms.
- **Concordance** counts only pairs whose **outcomes differ**: two identical outcomes cannot rank
  each other, and counting them would let a model that separates nothing score one half by default.
  Score ties count as half, expressed exactly as `(2·concordant + tied) / (2·comparable)`.
- **Maximum drawdown** is taken from the published path, not the endpoints. A position that ended
  flat after losing four fifths of its value is not the same risk as one that never moved.
- **Calibration bins** report exact observed rates and mean predicted values; an empty bin reports
  no rate rather than zero. Edges are preregistered and must name the folds they were chosen on —
  edges chosen by looking at the evaluation fold are edges fitted to the answer.

## Pairing

Order size, horizon and cost policy live on the **row**, never on a side. A paired comparison whose
two sides could differ in them is not a paired comparison, and making that unrepresentable is
stronger than checking it afterwards. A cohort mixing horizons, targets or cost policies is refused.

The paired cohort is **exactly** the rows where both sides produced an outcome, and a caller-supplied
one is refused: choosing which mismatches to keep selects the comparison cohort on an outcome of the
comparison. The report publishes `model_evaluable_only`, `baseline_evaluable_only` and their
difference, so an asymmetry is visible rather than resolved.

## Grouped uncertainty

Jackknife over the split plan's **exact-identity groups**, leaving out whole groups. Rows sharing a
creator or a trader are not independent observations: leaving one row out of a group leaves the rest
of that actor's behaviour in, and the resulting spread is far too narrow.

A group the split plan does not know is refused — grouped uncertainty over invented groups is a
spread over nothing.

**A spread, never a p-value.** Nothing here has earned a test.

## Multiplicity

The specification's `family_size` must equal the **frozen** family size (B11b's is **16**), and the
primary cell must be B11b's frozen primary. A family that shrank between preregistration and
evaluation shrinks the correction with it, which is the cheapest way to make a secondary cell look
primary. Promoting a secondary cell after the numbers are in is choosing the hypothesis to match the
result, and no correction undoes it.

## Status and provenance

`status` is `synthetic_plumbing_only` and `performance_status` is `not_evaluated`; both are locked.
`publication_grade` is refused and the refusal names the **still-open funding-cluster gate**.
Profitable, executable, validated and live are refused by name.

Every report binds: row evidence, split plan, model artifact, baseline record, feature order, label
preregistration and metric spec hashes, plus code revision and environment manifest. A figure that
cannot name the rows, the split, the model, the spec and the code that produced it is not
reproducible.

## Exception hierarchy

Refusals form a chain across modules — `EvaluationRefused` ⊂ `ArtifactRefused` ⊂ `SplitRefused` ⊂
`VectorRefused` ⊂ `ConcentrationRefused` ⊂ … ⊂ `FreezeViolation`. This module re-exports B13d's
rational validator rather than reimplementing it, so a bad probability raises **B13d's** class — an
ancestor. **A caller should catch the project base**, not the newest class, or it will miss the
validators the module inherited.

## Measured

```
python scripts/b14b_evaluation.py --contract
python scripts/b14b_evaluation_fixtures.py --gate
```

The gate publishes counts and checks and **no metric value or return distribution**, because there
is nothing to measure and a figure would be read as a result. A test scans the gate report's field
names for metric-shaped words.

## Not covered

- Any fitted model, real metric, return distribution or performance claim.
- Any eligible window, any status above `synthetic_plumbing_only`, any cluster.
- B11a outcomes. This module opens no file and connects to no database, and a test asserts it.
