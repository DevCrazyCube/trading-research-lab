# B11b — baseline evaluation plumbing, validated without looking at anything

Date: 2026-08-02. Author: Claude (handoff 70).
Freeze: `research/B11B_BASELINE_EVALUATION_PREREGISTRATION.json`, committed **alone** in `dc96132`
before any of this code existed. Schema: `docs/BASELINE_EVALUATION_SCHEMA.md`.
Code: `scripts/b11b_t0_features.py`, `scripts/b11b_baseline_metrics.py`,
`scripts/b11b_feature_corpus.py`. Tests: `tests/test_b11b_baseline_evaluation.py`.

```
python scripts/b11b_t0_features.py --contract
python scripts/b11b_baseline_metrics.py --contract
python scripts/b11b_feature_corpus.py research/b9d_transaction_bodies.sqlite \
    research/b10b_observed_paths.sqlite --gate
```

## 0. What was not done

**No B11a composition, count, feature distribution, path result, label or return was computed.**
The window has still never been queried. **No feature distribution was inspected on any window,
including the burned one** — the materializer ran over 1,136 curves and reports only that it worked.

**No model was fitted and no threshold, rate or transform was estimated from data.** The order size
is inherited from the earlier plumbing runs, the random control's rate is a frozen fraction, and the
vetoes are point-in-time predicates from the regime.

## 1. The ordering, which is the substance

The preregistration was written and committed before the materializer existed. That matters
specifically here: had the code come first, every feature in the list would be a feature somebody
chose while able to see what it looked like. The commit history is the evidence, not a claim in a
document.

## 2. The feature contract, and the one rule that carries it

Seventeen features, all from the pinned IDL, read from the `CreateEvent` and any `TradeEvent` at or
before t0.

**No string may appear in a feature block, ever.** Every value is an integer, a boolean, or null.
That is the structural form of "identities group, never predict", and its virtue is that it is
checkable without anyone having to notice which strings happen to be identities.

It is not sufficient on its own — a `creator_hash_bucket` integer would pass it — so the field list
is **pinned as an exact tuple by a test**. Adding any field fails, whatever it is called. A mutant
that adds exactly that field is killed.

### Why the creator's launch buy is a t0 fact, proven rather than assumed

t0 is the first transaction-terminal state. The `CreateEvent`'s transaction contains at least one
observation for the curve, so the first transaction-terminal observation is necessarily inside it —
therefore everything in the launch transaction, including a buy by the creator, is at or before t0.

Checked on the burned-development corpus: **1,136 of 1,136 curves have t0 inside the launch
transaction, 0 in a later one.** The feature is "the creator bought in the launch transaction". "The
creator's first buy ever" would be a look into the future and is not offered.

The feature is an *equality test between two t0 identities*, not an identity entering the model: the
identities themselves never reach the feature block, and a stranger buying the same amount yields
`false`.

## 3. Measured: the materializer over the burned-development corpus

| quantity | value |
| --- | --- |
| curves | 1,136 |
| feature records materialized | **1,136** |
| t0 inside the launch transaction | **1,136 / 1,136** |
| partition + no-string rule holds | **1,136 / 1,136** |
| post-t0 observations supplied | **0** |
| errors | **0** |
| feature hash chain (SHA-256) | `ec64f1194b335714119582b4c6cc80f85bb9bcad1b16dbd9a0bf327e62d8e782` |
| distributions reported | **none, deliberately** |

The hash chain reproduces across runs. The corpus used is the burned B8b window: it is burned
already, so a materializer pass over it costs nothing, and no label or outcome is touched.

## 4. Vetoes, policies and metrics

**Eight vetoes**, `V1`–`V8`, cross-checked against `b10a`: the states triggering `V1`/`V2`/`V3`/`V6`
are exactly the states `price_entry` refuses. Without that cross-check the veto list would be
documentation rather than the regime. `version_supported` must be stated — an unstated check is not
a passed one.

**Five policies**, none adaptive. Only the random control reads an identity, as deterministic noise
from a frozen seed; a test asserts every other policy is invariant across 40 different mints and
that the control actually varies. Invariants enforced: `P0` empty, `P3 ⊎ P4 = P1`, `P2 ⊆ P1`.

**Metrics** keep the whole cohort as the denominator, with `not_entered_by_policy` kept separate from
the pipeline's own `no_decision` so a result cannot hide which of the two it depends on. Censored,
structurally-unavailable and no-observed-state rows carry NULL and never enter the headline; the
explicitly named `worst_case_lower_bound_return` assigns them a total loss as a **bound**, and there
is no matching upper bound because an unobserved value is bounded below by zero and not above.

Grouped uncertainty is a **leave-one-group-out jackknife over `creator ∪ user`** — assumption-free,
no interval claimed — which makes the `PLAN.md` promotion criterion that results must not be
dominated by one creator or wallet cluster into something computable.

No float appears anywhere: ratios are exact reduced integer pairs and comparisons are
cross-multiplications. A test checks that `1/1 < (10⁴⁰+1)/10⁴⁰`, which a float comparison would call
equal.

## 5. The primary result, designated before it exists

`P1_all_eligible_fixed_size` × `h_1000_slots` × `capital_weighted_net_return`, chosen on operational
meaning and a prior document: 1,000 slots is about 7 minutes, bracketing the ~4.4-minute median
graduation time already cited in `DOCUMENTATION.md`, and `P1` is the only policy in the set that
answers "what does this pipeline produce". The horizon number itself is inherited unchanged; only the
*designation* is new.

Family size **16** is declared now. Secondary cells may not be promoted afterwards, and
`family_table` refuses a table in which more than one cell claims to be primary.

## 6. Verification — 31 mutants, all killed after one design fix

69 tests in this suite; **1,036 passing repository-wide**, 12 skipped. Every mutant is a real textual
edit to the shipped source, applied, the suite run, then reverted, with each anchor required to match
exactly once.

Grouped by the failure classes the directive named:

- **Feature leakage (5):** an observation after t0 accepted; one from another transaction accepted;
  the decision state not required; the creator-buy sum widened to every trader; missing fee rates
  filled in with the regime's usual ones.
- **Identity leakage (4):** a string allowed into the feature block; a `creator_hash_bucket` feature
  added; the feature/identity disjointness dropped; a non-control policy consulting the mint.
- **Seed drift (2):** the control's seed and its rate.
- **Adaptive thresholds (5):** the order size tuned; a veto dropped; an unstated version check
  treated as passed; the policy partition invariant dropped; do-nothing allowed to enter.
- **Horizon conflation (2):** b10b exit-rule semantics accepted; rows from another horizon pooled.
- **Denominator filtering (3):** declined curves dropped; no-decision curves dropped; the census sum
  no longer required.
- **Censored-as-loss (2):** censored positions folded into the headline; the bound silently becoming
  the headline.
- **Exact arithmetic (4):** float comparison; unreduced rationals; a position dropped from the
  jackknife for want of a split key; two cells both primary.
- **Prereg hash drift (4):** the file hash unpinned; the unlock gate no longer checking the on-disk
  contract; a model unlocking without an artifact hash; the collection requirement dropped.

**One survivor on the first run, fixed by changing the code:** deleting the feature/identity
disjointness check changed nothing observable, because it read the module constants — which are
disjoint — so it could never fire. Rather than delete it (the B11a precedent) or contrive a test
around it, it became `assert_disjoint_contract(feature_fields, grouping_fields)`, taking its inputs
as arguments so a test can hand it overlapping sets. A guard nobody can make fire is a guard nobody
can show works. **31 of 31 killed** after.

## 7. The unlock gate, and where it stands today

`U1` this preregistration committed with both hashes recorded · `U2` no model, or a model artifact
hash frozen first · `U3` B11a collection complete and gates passed · `U4` a `DECISIONS.md` unlock
entry naming both window and evaluation hashes · `U5` the on-disk contract still hashing to what was
frozen.

**`U3` fails today — nothing has been collected. Results are locked**, and `b10c`'s `window_status`
enum stays locked with them.

Every unlock report carries the evaluation-only rule: once labels are revealed, no feature, veto,
policy, horizon, metric or primary designation may change in response. That requires a new
preregistration **and a new window**, and B11a would then be burned.

## 8. What is still not claimed

No profitability figure, expectancy, win rate, success label or model. No split implementation
beyond emitting the `creator ∪ user` key. Funding-cluster leakage remains an unmeasured superset and
an open gate. The stochastic half of the `PLAN.md` Phase 2 gate is untouched, so every value the
pipeline produces remains **simulated, not executable**.
