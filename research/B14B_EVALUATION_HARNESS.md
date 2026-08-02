# B14b — the headline that flatters, and the bound that does not

Date: 2026-08-02. Author: Claude (handoff 94). Offline, synthetic only.
Code: `scripts/b14b_evaluation.py`, `scripts/b14b_evaluation_fixtures.py`.
Schema: `docs/EVALUATION_SCHEMA.md`. Tests: `tests/test_b14b_evaluation.py`.

## 0. Scope, and what was not touched

Plumbing and synthetic rows only. **No model was fitted**, no window is eligible, no real metric was
computed, no threshold was chosen, and **no B11a outcome was read** — this module opens no file and
connects to no database, and a test asserts it against the source. The funding-cluster gate remains
open and nothing here closes it.

## 1. The number that flatters, and why publishing one of them is a choice

Suppose a cohort of a hundred decisions. Sixty produce a priced outcome. Of the other forty, some
were right-censored at the horizon, some had no observed state to mark against, and some had a
structurally unavailable exit.

Report the mean over the sixty and you have a number that is arithmetically correct and materially
misleading. **The forty are not a random sample.** A position with no observed state is a position
nothing traded against; a structurally unavailable exit is one the book could not absorb. These are
the outcomes that went wrong in ways the pipeline could not price, and dropping them is exactly the
selection that makes a strategy look good on paper.

So this harness publishes every headline **twice**, side by side:

- `observed_evaluable`, the figure over what could be measured;
- `whole_cohort_worst_case`, the same figure with every unevaluable at-risk row assigned a total
  loss of its deployed capital.

Neither is *the* answer. The truth is somewhere between, and the distance between them is the most
informative number in the report — it is the size of what nobody knows. A report carrying only one
basis is refused, a headline metric present on one and absent on the other is refused, and neither
may be labelled as the other.

The two must also genuinely differ on the fixture corpus, and a test asserts that: if they ever
collapsed together, mislabelling one as the other would become invisible.

## 2. Censoring is not a zero, three times over

The recoding is refused at three separate points, because it can arrive three ways:

1. **At the door.** A side in any bucket but `marked_at_horizon` carrying a `net_pnl_lamports` is
   refused, so the recoding cannot happen before this module sees the row. It may not carry a class
   label either — an outcome nobody observed has no class.
2. **In the specification.** `recode_as_zero`, `recode_as_loss`, `impute_median`, `drop_silently`
   and `carry_forward` are refused **by name**, and an invented treatment is refused for not being
   declared.
3. **In the arithmetic.** Censored rows are absent from every observed numerator and present in
   every whole-cohort count, and the gate checks that the capital moves between the two bases by
   exactly the censored amount.

A decision the policy *declined* is a fourth thing again: it deployed nothing, so it cannot lose
anything even under the worst-case rule. `not_entered_by_policy` is deliberately not an at-risk
bucket.

## 3. Selection on evaluability

A paired comparison drops rows where either side failed to produce an outcome. That is unavoidable —
and it is also a place where the cohort can be selected on an outcome of the comparison.

So the paired cohort is **exactly** the rows where both sides produced an outcome, a caller-supplied
one is refused, and the report publishes `model_evaluable_only`, `baseline_evaluable_only` and their
difference. The fixture corpus contains one of each asymmetry, so the figure is not trivially
one-sided.

Order size, horizon and cost policy live on the **row**, never on a side. A paired comparison whose
sides could differ in them is not a paired comparison, and making that unrepresentable is stronger
than checking it afterwards — a per-side order size is an undeclared field and is refused.

## 4. Exactness where it actually matters

Every figure is an integer or a gcd-reduced rational, checked against `fractions.Fraction` as an
independent oracle. Three places where the exactness is load-bearing rather than decorative:

- **Brier** is summed as one rational over a common denominator. A Brier score assembled from
  rounded squares is a different number from the one it claims to be.
- **Concordance** counts only pairs whose *outcomes differ*. Two identical outcomes cannot rank each
  other, and counting them would let a model that separates nothing score one half by default on
  them. Score ties count as half, expressed as `(2·concordant + tied)/(2·comparable)` so no division
  is ever rounded.
- **Maximum drawdown** is taken from the published path. The fixture holds an equity path that fell
  to −700,000 and recovered to +10,000: endpoint arithmetic reports no drawdown at all, and the path
  reports 1,200,000.

## 5. Grouped uncertainty, and what it is not

The jackknife leaves out **whole identity groups** from the split plan, not rows. Rows sharing a
creator or a trader are not independent observations, and leaving one row out of a group leaves the
rest of that actor's behaviour in — the resulting spread is far too narrow, in the flattering
direction.

A group the split plan does not know is refused: grouped uncertainty over invented groups is a
spread over nothing.

It is a **spread and never a p-value**, and a test greps the output for `p_value`, `significan` and
`confidence_interval` to keep it that way. Nothing here has earned a test.

## 6. Multiplicity binds the frozen family, not the computed one

B11b froze a family of **16** cells with `P1_all_eligible_fixed_size × h_1000_slots` as primary. The
specification must declare both, and both are checked against the frozen constants.

A family that shrank between preregistration and evaluation shrinks the correction with it, which is
the cheapest available way to make a secondary cell look primary. Promoting a secondary cell after
the numbers are in is choosing the hypothesis to match the result, and no correction undoes that.

## 7. Measured — the synthetic fixture corpus

```
python scripts/b14b_evaluation_fixtures.py --gate
```

| quantity | value |
| --- | --- |
| synthetic rows | 11 |
| identity groups | 11 |
| paired rows | 7 |
| model evaluable only / baseline evaluable only | 1 / 1 |
| neither evaluable | 2 |
| bases published | **2 / 2** |
| headline metrics on both bases | **3 / 3** |
| worst case never better than observed | **yes** |
| censored capital moves between bases exactly | **yes** |
| declined rows risk nothing | **yes** |
| drawdown uses the path, not the endpoints | **yes** |
| result independent of row order | **yes** |
| refusals verified to fire | **7 / 7** |
| errors | **0** |

**No metric value and no return distribution appear in that report**, and a test scans its field
names for metric-shaped words. It scans names rather than raw JSON because the report carries hex
digests, and a substring search over those matches metric words by coincidence — a check that fires
on a hash is a check nobody keeps.

## 8. Verification — 65 mutants, 65 killed, none disclosed

84 tests, 108 subtests; **1,985 passing repository-wide**.

Covering every failure mode the directive named: censored-as-loss (8), denominator filtering (3),
unpaired cohorts (4), horizon/order mismatch (2), model score float (3), validation-fitted bin edge
(4), group split (4), P&L sign (1), exact ratio boundary (2), primary promotion (1), family-size
drift (3), worst-case labelled as headline (6), row hash drift (2) and B11a outcome access (1) —
plus the specification, status, determinism and record-shape gates.

**Five survived the first run.** One was dead code, **removed rather than disclosed**: a branch
returning zero for non-at-risk sides, which `assert_side` already guarantees deploy nothing, so the
general rule produced the same answer. Two were fixture weaknesses — the two sides deployed the same
capital, so a return divided by the wrong side's denominator was the same number, and no
specification test drove an *undeclared* censoring treatment as opposed to a refused-by-name one.
Two were properties the report happens not to expose (canonical row ordering, and the fixtures using
one module graph) and are now driven directly, on the same reasoning as B13d's tiebreak: a property
nothing can observe today is one that silently stops holding tomorrow.

## 9. A note on the exception chain

This module re-exports B13d's rational validator rather than reimplementing it, so a float
probability raises **B13d's** class — which is an *ancestor* of this module's, not a descendant. A
caller catching only `EvaluationRefused` would miss it.

That is a real property of a project whose modules build on each other, and it is now written down
and tested rather than discovered: **catch the project base**, not the newest class. The test asserts
both the inheritance chain and the one direction that does *not* hold.

## 10. Not claimed

No model, no fit, no real metric, no return, no threshold, no cluster, no eligible window, no
performance figure. No operational readiness. The counts in this document are counts of synthetic
rows, checks and refusals.
