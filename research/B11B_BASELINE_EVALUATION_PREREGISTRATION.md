# B11b — baseline evaluation, frozen before any fresh label exists

Date: 2026-08-02. Author: Claude (handoff 70).
Machine-readable freeze: `research/B11B_BASELINE_EVALUATION_PREREGISTRATION.json`.

```
file      sha256 = 55263060716e99500a097f11260c047d03dbf16c4779a37b3f159d55592cb220
canonical sha256 = 90b159fb4f7492c98571429855c7939d95654c15543e891aaaee279bdf4c506d
```

Applies to the B11a window `[435,569,150 .. 435,772,750]`, observation cutoff `437,211,659`
(`b11a-fresh-cohort-2026-08-02`, file `5faabb33…`). **That window has not been queried, enumerated,
counted or inspected in any way**, and this document was committed before the feature materializer
was ever run.

## What this freezes, and why it has to be first

B11a gave the project its first clean window. A clean window buys nothing if the thing being
evaluated is chosen after the labels appear, so everything that could be chosen is chosen **now**:
the features, the vetoes, the policies, the horizons, the metrics, which single result is the
headline, what makes the evaluation valid, and what evidence must exist before any label may be
computed at all.

**There is no model.** `model_family: none`, zero learned parameters, zero fitted thresholds. This is
a baseline/pipeline evaluation: it establishes what the machinery produces with no selection in it,
so that a future model has something honest to be measured against. A future evaluation with a model
needs its own preregistration and a model artifact hash frozen before unlock.

## The t0 feature contract

Seventeen features, all from the pinned Pump IDL, read from the curve's own `CreateEvent` and from
any `TradeEvent` for the same curve at a canonical coordinate **at or before t0**.

### One rule does most of the work: no strings

**Every feature value is an integer, a boolean, or null. No string may appear in the feature block,
ever.** That is the structural form of "identities are for grouping, never for prediction": a mint,
a creator, a URI or a symbol cannot enter a model that only accepts numbers, and the rule is
checkable without anyone having to notice which strings happen to be identities.

`mint`, `bonding_curve`, `creator`, `create_user` and `t0_user` are carried in a separate grouping
block, for the R5 `creator ∪ user` split and nothing else.

### No transform was selected, because selecting one requires looking

There is no log, bucket, rank, quantile, standardisation or ratio-to-cohort in the list. Choosing any
of those means inspecting a distribution, and inspecting a distribution to choose a transform is
feature selection with the outcomes one join away. The only arithmetic present —
`tokens_left_curve_units = launch_real_token_units − t0_real_token_units` — is an accounting
identity, not a choice.

### Why the creator's initial buy is observable at t0, proven rather than assumed

t0 is the first **transaction-terminal** state (`b10b.select_t0`). The `CreateEvent`'s transaction
contains at least one observation for the curve, so the first transaction-terminal observation is
necessarily inside that same transaction. Therefore everything in the launch transaction — including
a buy by the creator — is at or before t0.

Checked against the burned-development corpus: **1,136 of 1,136 curves have t0 inside the launch
transaction; 0 in a later one.** The feature is therefore "the creator bought in the launch
transaction", which is a t0 fact. "The creator's first buy ever" would be a look into the future and
is not offered.

## Hard vetoes

Eight, all already implied by the frozen regime and named here so no policy can quietly widen it:
non-SOL quote, Mayhem, curve complete at t0, incomplete state, mixed regime within the curve, order
exceeding the real token reserve, order buying zero tokens, unsupported program version. Each is a
point-in-time predicate; none has a fitted threshold. A vetoed curve is entered by no policy **and
still produces label rows**, so the cohort denominator survives.

## Policies — five, none adaptive

| id | enters | role |
| --- | --- | --- |
| `P0_do_nothing` | never | degenerate reference; proves the accounting cannot manufacture value from an empty book |
| **`P1_all_eligible_fixed_size`** | every non-vetoed curve, 0.1 SOL | **PRIMARY** |
| `P2_mint_hash_random_control` | non-vetoed curves whose frozen mint hash falls in half | plumbing control |
| `P3_creator_initial_buy_present` | non-vetoed, creator bought at launch | categorical arm |
| `P4_creator_initial_buy_absent` | non-vetoed, creator did not | complementary arm |

No top-k, no quantile, no rank, no rate estimated from the cohort. The order size (0.1 SOL) is
inherited unchanged from the B10a/B10b/B10c runs, so no size was chosen with this window in view.

`P2`'s seed is `b11b-random-control-2026-08-02` and its rule is
`int(sha256(seed + mint), 16) % 2 == 0`. One half maximises the control's sample size while keeping
it a strict subset of `P1`; no other rate was evaluated. **Its role is artefact detection, not
performance comparison** — a random subset of `P1` has the same expected outcome as `P1`, so a
divergence beyond grouped uncertainty means the accounting is wrong, not that something was found.

Invariants, asserted rather than hoped: `entries(P0) == 0`, `entries(P3) + entries(P4) ==
entries(P1)`, `entries(P2) ⊆ entries(P1)`, and no policy reads any observation after t0 or any other
curve.

## Horizons, and a distinction that must not be lost

The four B10c horizons, **unchanged**. Nothing added, removed or reparameterised.

**The evaluation uses B10c state-in-force semantics exclusively.** A slot horizon is valued at the
*last* evaluable observation at or before `t0+H`. That is **not** B10b's `slot_horizon` exit rule,
which fires at the *first* reachable exit at or after `t0+H`. The two answer different questions —
what was the position worth at H, versus when would a strategy have exited — and on the burned
corpus they differ enormously (B10b right-censored 551 of 884 at 10,000 slots; B10c censors none). A
number computed under one and reported under the other would be a different quantity wearing the
same name.

## The primary result, chosen on meaning rather than on returns

**`P1_all_eligible_fixed_size` × `h_1000_slots` × `capital_weighted_net_return`.**

- **Policy:** `P1` is the only member of the set that answers "what does this pipeline produce".
  `P0` is degenerate, `P2` is a control, and `P3`/`P4` are arms whose union *is* `P1`.
- **Horizon:** 1,000 slots is about 7 minutes at the measured 2.3934 slots/s, which brackets the
  ~4.4-minute median time to graduation reported in the 2026 study already cited in
  `DOCUMENTATION.md`. A launch-entry decision resolves inside that span or not at all. The number is
  inherited unchanged — only the *designation* as primary is new, and it rests on operational
  meaning and a prior document, never on a burned return.
- **Metric:** what an operator on a book of fixed-size positions actually experiences; exact integer
  arithmetic; denominator is deployed capital rather than a count, so one large position cannot hide
  behind many small ones.

**It may never be quoted alone.** It is computed over marked rows only, so without the disposition
census it is a number conditioned on markedness — and markedness correlates with the outcomes it
describes. It ships with the census, the worst-case lower bound, and the grouped jackknife range.

**Multiplicity:** the family is 4 non-degenerate policies × 4 horizons = **16**. Secondary cells are
reported in a table and **may not be promoted to primary afterwards**. Any future inferential claim
over this family uses Bonferroni α = 0.05/16 = 0.003125. No test is computed in this pass.

## Metrics keep the whole cohort as the denominator

A vetoed curve, a no-decision curve and a censored horizon are all counted in the cohort census and
contribute zero deployed capital. **Filtering the cohort down to the rows that happen to carry a
value is the commonest way a backtest flatters itself, and it is forbidden.**

**No censored-as-loss shortcut.** A censored, structurally-unavailable or no-observed-state row has a
NULL value and is never quietly counted as a loss, a zero or a −1. What *is* offered is an explicit,
labelled **worst-case lower bound**: assign every entered-but-unmarked position a total loss. That is
a bound, not an estimate, and it is named as one. There is no matching upper bound — an unobserved
value is bounded below by zero and not above.

**Grouped uncertainty is a jackknife, not a distributional assumption.** Recompute the primary metric
with each `creator ∪ user` group removed in turn and report the range, alongside the group count and
the largest group's share. That is exactly the `PLAN.md` promotion criterion that results must not be
dominated by one creator or wallet cluster, made computable.

**No float anywhere**, including intermediate ordering: rationals are compared by cross-multiplied
integers.

## Pass/fail — whether the evaluation is *valid*, not whether it is *good*

E1 rows = curves × horizons exactly · E2 zero arithmetic errors under independent recomputation ·
E3 byte-identical rerun · E4 zero leakage violations · E5 coverage partition sums · E6 the b9e/b9f/
b10a gates pass on the fresh corpus · E7 every policy invariant holds · E8 grouped jackknife reported.

On failure: report it and compute no headline number. A valid-looking metric from an invalid pipeline
is worse than no metric.

## Unlock evidence B11a must require

| id | requirement |
| --- | --- |
| U1 | this preregistration committed and both hashes recorded in `DECISIONS.md` |
| U2 | `model_family: none`, or a model artifact hash frozen before unlock |
| U3 | B11a collection complete and the E6 gates passed |
| U4 | a `DECISIONS.md` entry naming both the B11a and B11b hashes and declaring the unlock |
| U5 | nothing in this contract changed since U1 — the hashes prove it |

**B11a is evaluation data and may never tune a policy.** Once labels are revealed, no feature, veto,
policy, horizon, metric or primary designation may change in response. A change after reveal requires
a new preregistration **and a new window**; B11a would then be burned and join the register.

**B10c's `window_status` enum stays locked.** This document does not authorise extending it; that is
its own decision, gated on U1–U5.

## Status

A freeze, not a result. It contains no measurement of the B11a window, and by construction cannot:
nothing in that window has been queried.
