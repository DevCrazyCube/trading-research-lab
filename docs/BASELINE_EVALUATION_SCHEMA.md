# Baseline evaluation schema — feature contract v1.0.0, metric set v1.0.0

Produced by `scripts/b11b_t0_features.py` and `scripts/b11b_baseline_metrics.py`. Read-only:
consumers must treat every record as immutable and must pin both versions.

The **frozen choices** — which features, which vetoes, which policies, which horizon is primary,
which metric is the headline — live in `research/B11B_BASELINE_EVALUATION_PREREGISTRATION.json`
(file `55263060…`, canonical `90b159fb…`), committed before this code was written. This document
describes the **record shapes and the runtime guarantees**; it does not restate the choices, and it
cannot change them.

## Status

`model_family: none`. Zero learned parameters, zero fitted thresholds. This is a baseline/pipeline
evaluation whose purpose is to establish what the machinery produces with no selection in it.

**No result on the B11a window exists or may be computed.** The unlock gate below is what stands
between this schema and a number.

## Feature record

```
feature_contract_version  "1.0.0"
model_family              "none"
coordinate                slot, transaction_index, outer_index, inner_index   (t0)
features                  17 fields, integers / booleans / null ONLY
grouping                  mint, bonding_curve, creator, create_user, t0_user
features_sha256           canonical hash of the feature block alone
```

### The rule that carries the design

**No string may appear in a feature block, ever.** Every value is an integer, a boolean, or null.

That is the structural form of "identities are for grouping, never for prediction": a mint, a
creator, a URI or a symbol cannot enter a model that only accepts numbers — and the rule is
checkable *without anyone having to notice which strings happen to be identities*. A rule requiring
vigilance is a rule that fails the week nobody is looking.

The no-string rule alone is not sufficient: a `creator_hash_bucket` integer would pass it. So
`FEATURE_FIELDS` is **pinned as an exact tuple by a test**, and adding any field at all fails.

### Runtime guarantees

| guarantee | mechanism |
| --- | --- |
| no observation after t0 | `build_t0_features` has no parameter for one, and every supplied observation's canonical key must be ≤ t0's |
| no observation from outside the launch transaction | checked per observation; t0 is provably always inside it |
| the decision state is present | an observation at exactly t0 is required |
| features reach only scalars | `b10b.assert_no_future_reachable` over the feature block |
| features and identities are disjoint | `assert_disjoint_contract`, which takes its field sets as arguments so it is reachable and testable rather than a guard nobody can make fire |

**Why the launch-transaction check is not redundant:** t0 is the first transaction-terminal state,
so it is necessarily inside the `CreateEvent`'s transaction — verified on the burned-development
corpus, **1,136 of 1,136 curves**. An observation from another transaction therefore cannot be at or
before t0 unless the corpus is malformed, and a malformed corpus is how a future state arrives
wearing a valid-looking coordinate.

**Fee rates are observed, never assumed.** A launch transaction with no trade publishes no basis
points at t0, and the four `*_bps_observed` fields are null. Substituting the regime's usual rates
would assert a fee schedule the decision instant did not state.

## Vetoes

Eight codes, `V1`–`V8`, each a point-in-time predicate with no fitted threshold. `evaluate_vetoes`
returns a sorted tuple; empty means eligible. A test cross-checks that the states triggering
`V1`/`V2`/`V3`/`V6` are exactly the states `b10a.price_entry` refuses — otherwise the veto list would
be documentation rather than the regime.

`version_supported` must be stated `True` or `False`. An unstated program-version check is refused,
because an unstated check is not a passed one.

## Policies

`decide(policy_id, features, vetoes, grouping) -> lamports | None`. Five frozen rules; no policy
consults an observation after t0, another curve, or a threshold computed from anything.

Only `P2_mint_hash_random_control` reads an identity, and it reads it as a source of **deterministic
noise** — frozen seed, fixed rate, no ability to encode history. A test asserts every other policy
is invariant to the mint across 40 different values, and that the control actually varies.

`assert_policy_invariants` enforces: `P0` empty, `P3 ⊎ P4 = P1`, `P2 ⊆ P1`.

## Metric record

```
metric_set_version   "1.0.0"
label_semantics      "b10c_state_in_force_at_or_before_horizon"   — refused if anything else
policy_id, horizon_name, is_primary
cohort_curves        the WHOLE cohort
disposition_census   marked / right_censored / structural_exit_unavailable /
                     no_observed_state_in_window / no_decision / not_entered_by_policy
entered_positions, deployed_capital_lamports, total_net_lamports
capital_weighted_net_return          exact reduced [numerator, denominator]
worst_case_lower_bound_return        exact reduced pair, labelled a BOUND
median_position_return, median_position_max_drawdown, worst_position_max_drawdown
capacity_positions_fully_executable, capacity_positions_size_constrained
grouped_uncertainty  group_count, largest_group_position_share,
                     leave_one_group_out_min_return, leave_one_group_out_max_return
metrics_sha256
```

### Two properties, enforced

**The denominator is always the whole cohort.** `assert_denominator_preserved` refuses a census that
does not sum to `cohort_curves`. `not_entered_by_policy` is kept separate from the pipeline's own
`no_decision`: a policy declining an eligible curve and the pipeline declining a curve are different
facts, and merging them would hide which one a result depends on.

**Absence is never quietly a loss.** Censored, structurally-unavailable and no-observed-state rows
carry NULL and never enter the headline. What is offered instead is an explicitly named
`worst_case_lower_bound_return` in which every entered-but-unmarked position is a total loss — a
bound, not an estimate. **There is no matching upper bound**: an unobserved value is bounded below by
zero and not above. `assert_no_censored_as_loss` refuses a record whose headline has silently become
the bound.

### No float, anywhere

Every ratio is an exact reduced integer pair; every comparison is a cross-multiplication; the median
of an even set is `(ad + cb) / (2bd)`. A test walks the serialized record and fails on any float, and
another checks that `1/1 < (10⁴⁰+1)/10⁴⁰` — which a float comparison would call equal.

### Horizon semantics are named in every record

`b10c_state_in_force_at_or_before_horizon`, never `b10b_first_reachable_exit_at_or_after_horizon`.
The two answer different questions and differ enormously in practice. `evaluate` refuses any other
value, so a record that does not name its semantics cannot exist.

## Multiplicity

`family_table` declares the family size (**16**: four non-degenerate policies × four horizons),
marks the single primary, and refuses a table in which more than one cell claims to be primary.
Secondary cells may not be promoted afterwards. No significance test is computed; grouped
uncertainty is an assumption-free jackknife instead.

## The unlock gate

`evaluate_unlock_evidence(evidence)` reports which of `U1`–`U5` hold and why each failure fails —
a report rather than a boolean, because "results are locked" is a claim someone will eventually want
to argue with, and an unexplained `False` is not arguable. `assert_unlock_evidence` raises naming the
unmet ids.

| id | requirement |
| --- | --- |
| U1 | this preregistration committed, both hashes recorded in `DECISIONS.md` |
| U2 | `model_family: none`, or a model artifact hash frozen before unlock |
| U3 | B11a collection complete and the gates passed |
| U4 | a `DECISIONS.md` entry naming both window and evaluation hashes, declaring the unlock |
| U5 | the on-disk contract still hashes to what was frozen |

**Today `U3` fails**: nothing has been collected. Results are locked.

Every report carries the evaluation-only rule: once labels are revealed, no feature, veto, policy,
horizon, metric or primary designation may change in response. That requires a new preregistration
**and a new window**, and B11a would then be burned.

## Not covered

- Any B11a composition, count, feature distribution, path result, label or return.
- Any model, threshold, rate or transform fitted to data.
- Any split implementation beyond emitting the `creator ∪ user` key; funding-cluster leakage remains
  an unmeasured superset and an open gate.
- Landing, contention, tips, latency and slippage. Every value the pipeline produces remains
  **simulated, not executable**.

No profitability claim is made and nothing here is a trading recommendation.
