# B10c — leakage-safe simulated outcome labels, materialized over 1,136 curves

Date: 2026-08-02. Author: Claude (handoff 66). Offline, read-only, no network.
Code: `scripts/b10c_outcome_labels.py`, `scripts/b10c_label_corpus.py`.
Schema: `docs/OUTCOME_LABEL_SCHEMA.md` v1.0.0. Tests: `tests/test_b10c_outcome_labels.py`.
Preregistration: `research/B10C_PREREGISTRATION_PLUMBING.json`.

Reproduce:

```
python scripts/b10c_label_corpus.py build-identity research/b9d_transaction_bodies.sqlite \
    research/b10b_observed_paths.sqlite
python scripts/b10c_label_corpus.py materialize research/b10b_observed_paths.sqlite \
    research/b10c_t0_identity.sqlite research/B10C_PREREGISTRATION_PLUMBING.json --gate
```

## 0. The one thing to read first

**This corpus is the B8b cohort, and B8b was burned on 2026-07-28.** All 1,136 `CreateEvent`s fall
inside `[433,894,233, 434,097,833]`, and R3 states: *never measure or tune the label on B8b.*

That is not a caveat added to this work; it is a constraint that predates it. Everything below is a
**plumbing, accounting, determinism and leakage** result. **No return distribution is computed and
none is reported** — the runner refuses to produce one and says so in its own output. No horizon,
threshold or class here may be carried into any evaluation or used to place a later window.

## 1. What was built

One row per **preregistered decision × horizon** over `b10b` observed-state path records, carrying:
the t0 coordinate and reserves; the grouping identities published at or before t0; the horizon's
explicit geometry; the outcome status and its censoring reason; the exact-rational simulated return;
the exact-rational maximum drawdown to that horizon; the liquidity or unavailability state; and five
evidence hashes.

Two supporting artifacts, both reproducible and self-hashing:

| artifact | contents |
| --- | --- |
| `research/b10c_t0_identity.sqlite` | `creator`, `create_user`, `t0_user` and the t0 coordinate for all 1,136 curves; plus `observation_window_end_slot = 435,536,742`, taken from the `b9d` artifact's own `cutoff_slot` metadata rather than inferred from the maximum observed slot |
| `research/b10c_labels.sqlite` | the 4,544 label rows, columns in declared decision-then-outcome order |

## 2. The leakage boundary, made structural in four ways

R1 permits a label to read after t0 and forbids a feature from doing so. Both halves live in one
row, so the boundary cannot be a convention:

1. **A declared field partition.** Every key belongs to exactly one of `DECISION_FIELDS` (31) or
   `OUTCOME_FIELDS` (33). A row whose keys are not exactly that disjoint union is refused, so a
   field cannot be added without saying which side of t0 it comes from.
2. **A signature that cannot receive a mark.** `build_decision_facts` has no path, mark, result or
   horizon parameter, pinned by a test.
3. **A reachability check at the merge seam.** The decision block's whole reference graph is walked
   and refused if any mark object is reachable from it. `b10b` could not run this at `decide_entry`,
   which by construction cannot see the future; this module holds both sides.
4. **The decision block must not move when the horizon does.** Horizons are post-t0 geometry, so a
   single equality catches a whole class of leaks without knowing which field caused them.

Measured over the corpus: **1,136 / 1,136** decision blocks constant across horizons, **4,544 /
4,544** rows with the field partition holding and no mark reachable from the decision half.

**Stated limit:** these guarantee the materializer never moves information across t0. A feature
pipeline built later on these rows must still respect the partition — the row tells it where the
line is, it does not enforce it downstream.

## 3. Two semantic decisions worth arguing with

### 3.1 A slot horizon labels the state in force, not the next trade

The mark is the **last** evaluable observation at or before `t0.slot + H`, never the first one
after. R1 fixes the label window at `(t0, t0+H]`. Taking the first observation *after* the target
labels "the value whenever this token next traded", which moves with how quiet the token went rather
than with the market.

This deliberately differs from `b10b`'s `slot_horizon` **exit rule**, which fires at the first mark
at or after the target. The two answer different questions — *when would a strategy have exited* vs
*what was the position worth at H* — and the difference is visible in the counts: `b10b` reported
551 of 884 paths right-censored at 10,000 slots, while B10c right-censors **none** of them, because
the recorded window extends to slot 435,536,742 and every target is inside it. Neither number is
wrong; they are answers to different questions, and conflating them would have silently discarded
843 labels.

### 3.2 "Nothing traded inside the window" is not censoring

A fourth status, `no_observed_state_in_window`, is kept out of `right_censored` on purpose.
Right-censoring is a statement about window *geometry*: the horizon lies past what was recorded.
This is a different thing — the window covers the horizon and simply contains no observation inside
it. The only state available is then t0's own, and **our own hypothetical entry has already changed
it**, so pricing an exit against it would price our own impact away.

That is the one place where this project's standing "we do not model our own impact" limitation
stops being a residual and becomes the entire content of the label. It gets its own status rather
than being folded into censoring. It occurs 105 times.

## 4. Measured results

### 4.1 Rows and coverage

| quantity | value |
| --- | --- |
| curves | 1,136 (884 with a priced decision, 252 without) |
| horizons | 4 |
| rows | **4,544 — exactly curves × horizons** |
| distinct decisions | 1,136 |
| arithmetic errors | **0 over 4,544 rows checked** |
| marks cross-checked against the corpus | **2,994 / 2,994 found, 0 missing** |
| slot-horizon rows citing a state at or before their own target | **1,642 / 1,642** |

`no_decision` rows, one per horizon per curve, preserve the whole cohort as the denominator:

| reason | rows | curves |
| --- | --- | --- |
| `no_later_observation` | 964 | 241 |
| `out_of_regime_non_sol_quote` | 40 | 10 |
| `entry_refused` | 4 | 1 |
| **total** | **1,008** | **252** |

### 4.2 Outcome status by horizon

**These are burned-window plumbing counts. They are not findings and may not be cited as any.**

| horizon | marked | right-censored | structurally unavailable | no observed state | no decision |
| --- | --- | --- | --- | --- | --- |
| `h_1000_slots` | 799 | 0 | 9 | 76 | 252 |
| `h_10000_slots` | 843 | 0 | 12 | 29 | 252 |
| `h_10_observations` | 469 | 408 | 7 | 0 | 252 |
| `administrative_window_end` | 883 | 0 | 1 | 0 | 252 |

Every row sums to 1,136.

Two independent cross-checks against `b10b`, which implements its rule engine separately:

- `h_10_observations` gives 469 / 408 / 7, matching `b10b`'s `h_10_observations` exit rule exactly
  (469 triggered / 408 right-censored / 7 structurally unavailable).
- `administrative_window_end` gives 883 marked and 1 unavailable, matching `b10b`'s
  `terminal_observation` rule exactly.

So the two modules agree wherever they are asking the same question, and differ only where §3.1 says
they should.

### 4.3 Determinism

Two consecutive runs produced byte-identical reports. 4,544 rows serialised canonically — sorted
keys, no insignificant whitespace, **no float in any row**, verified by walking the parsed row — and
chained:

```
row_hash_chain_sha256      = 36400580db9e8173a19570ab019c98f4066ab22bdd32d995d0d6380c14298d30
preregistration_sha256     = cbbf99df2a649b86d4c41fa3ead2d3f33f6e9568d0921a109104d6226222b4c2
dataset_content_sha256     = 4aca86d3756afec09d70725f76d0b51952c1008bcdb0f5730c5b787de62ce7b3
observation_window_end_slot= 435536742   (b9d metadata `cutoff_slot`, not an inference)
```

## 5. Verification — 28 mutants, 4 survived first

63 tests in this module's suite; **922 passing repository-wide**, 12 skipped. Every mutant is a real
textual edit to the shipped source, applied, the suite run, then reverted; each anchor must match
exactly once so a mutation that failed to apply is reported as a miss rather than counted as a kill.

The first 20 mutants — accepting an out-of-sample window status, defaulting a horizon, admitting a
value-selected horizon, scoring a censored row as a total loss, taking the first state *after* a
slot horizon, valuing a completed curve, folding an empty window into censoring, running the
drawdown past the horizon, leaving the rational unreduced, dropping exit costs from the denominator,
conditioning the corpus on evaluability, reporting returns from the burned window, and eleven
others — were all killed on the first run.

That was suspicious rather than reassuring, so a second, harder set targeted the seams no test
walked directly. **Four of eight survived, and all four changed the code, not only the tests:**

| survivor | what it revealed | fix |
| --- | --- | --- |
| the reachability check at the merge seam is removed | the suite proved `assert_no_future_reachable` worked, never that `materialize_row` calls it | a test that leaks a mark through the real entry point |
| the field partition is not checked when a row is built | same shape: the checker was tested, the call site was not | a test that passes an undeclared field through `materialize_row` |
| the create identity is no longer proven to precede t0 | the ordering proof sat beside the row construction as a droppable line | merged into `identity_row`: **dropping the check means dropping the row** |
| the preregistration may censor against an uncollected window | the check lived in `main`, which no test exercises | moved into `materialize` as a **required** parameter, so the work cannot happen without it |

After the fixes: **28 of 28 killed.**

## 6. What is not claimed

- **No return distribution, expectancy, win rate, profitability class or success label** is computed
  anywhere. The runner reports `returns: NOT COMPUTED` and states why.
- **No entry is selected and no strategy is scored.** One fixed 0.1 SOL order is applied to every
  eligible curve, unchanged from the `b10b` run, so nothing here is a fit.
- **No horizon in the shipped preregistration was chosen after seeing a label distribution** — all
  four are carried over unchanged from the `b10b` plumbing run of the same day.
- **No split, model, baseline or feature vector exists.** R5's grouping keys are emitted; the
  grouping is Phase 3. Funding-cluster leakage remains an unmeasured superset and an open gate.
- **Rug, dump, graduation and liquidity-failure labels remain unconstructed**, and each needs its
  own preregistration on a fresh window disjoint from every burned range.
- **The economic L1 threshold** of `EXECUTABLE_RETURN.md` §3 remains unfrozen.
- **The stochastic half of the `PLAN.md` Phase 2 gate is untouched.** Landing, contention, failure
  and fill distributions are uncalibrated, so every value here is **simulated, not executable**.
