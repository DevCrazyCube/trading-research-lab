# Simulated outcome label schema — v1.0.0

Produced by `scripts/b10c_outcome_labels.py`. Read-only: consumers must treat every row as immutable
and must pin `schema_version`.

Status: **Phase 3-compatible, built on Phase 2 evidence.** One row per **preregistered decision ×
horizon** over `b10b` observed-state path records. The plumbing, accounting, determinism and leakage
gates below are measured and passing over the full 1,136-curve corpus.

## The window is burned, and was burned before this schema existed

Every `CreateEvent` in the corpus falls inside `[433,894,233, 434,097,833]`, which `DECISIONS.md`
burned on **2026-07-28** and which **R3** forbids measuring or tuning a label on.

Consequences, enforced rather than noted:

- `window_status` is a **required** preregistration field and `burned_development` is the **only**
  accepted value. Adding another requires a `DECISIONS.md` entry naming a fresh preregistered window
  disjoint from every burned range.
- Every row carries `window_status`.
- The corpus runner **does not compute or report the distribution of returns**, and says so in its
  own report. Reporting it would be measuring a label on a burned window whether or not anybody
  called the number a finding.

## The asymmetry this schema exists to enforce

**R1:** *"fix decision instant t0 at the feature-vector timestamp; the label window is `(t0, t0+H]`,
and no feature may read an observation made after t0."*

**A label MAY read observations after t0. A feature MAY NOT.** Both halves live in one row, so the
boundary is structural in four independent ways:

| # | mechanism | what it catches |
| --- | --- | --- |
| 1 | every field is declared in exactly one of `DECISION_FIELDS` / `OUTCOME_FIELDS`, and a row whose keys are not exactly that disjoint union is refused | a field added without saying which side of t0 it comes from |
| 2 | `build_decision_facts` has no path, mark, result or horizon parameter, pinned by a signature test | a future author feeding it a post-t0 quantity |
| 3 | at the merge seam the decision block's whole reference graph is walked and refused if any mark is reachable | an object smuggled in under any name |
| 4 | the decision block is asserted **identical across every horizon of one decision** | any decision-side value computed from post-t0 information, without knowing which field caused it |

`b10b` could not run check 3 at `decide_entry`, which by construction cannot see the future. This
module holds both sides, so it can.

**What this cannot defend against, stated plainly:** these guarantee the *materializer* never moves
information across t0. A feature pipeline built later on top of these rows must still respect the
partition; the row tells it where the line is.

## Preregistration

There is **no default horizon anywhere in the module**, and a test asserts the absence. A default
horizon is a horizon chosen after seeing outcome counts, with nobody's name on it.

| field | rule |
| --- | --- |
| `preregistration_id` | non-empty; an unnamed preregistration cannot be cited, and one that cannot be cited is not one |
| `window_status` | must be `burned_development` |
| `purpose` | non-empty; on a burned window the purpose is the only thing separating a plumbing check from a finding |
| `observation_window_end_slot` | positive integer, and must equal the end the **collection recorded about itself** — the runner refuses a mismatch, because censoring against an uncollected window reports geometry that never existed |
| `horizons` | at least one; names unique |

The document's SHA-256 is stamped on every row, so a later reader can tell which document produced
which number.

### Horizon kinds

| kind | geometry |
| --- | --- |
| `slot_horizon` | the state in force at `t0.slot + slots` |
| `observation_horizon` | the `count`-th evaluable observation after t0 |
| `administrative_window_end` | the last evaluable observation; flagged `horizon_is_administrative` because its value moves with the window rather than with the market |

### Horizon kinds refused by name, with the reason attached

| refused kind | why |
| --- | --- |
| `net_value_at_or_below` | a horizon selected by realised value is a stop, and a stop chosen after the outcome is visible is a profitability class |
| `net_value_at_or_above` | likewise a target |
| `first_full_size_exit` | selecting the exit instant by an outcome property is an **oracle exit**; the label would embed a decision no strategy could have made at t0 |

## `slot_horizon` labels the state in force, not the next trade

The mark is the **last** evaluable observation at or before `t0.slot + slots`, never the first one
after it. R1 fixes the label window at `(t0, t0+H]`. Taking the first observation *after* the target
would label "the value whenever this token next traded", which moves with how quiet the token
happened to go rather than with the market.

This is a deliberate difference from `b10b`'s `slot_horizon` **exit rule**, which fires at the first
mark at or after the target. The two answer different questions: `b10b`'s rule models *when a
strategy would have exited*; this schema's horizon models *what the position was worth at H*. Both
are correct for their own question and they are not interchangeable.

## Four ways there is no label, deliberately not merged

| `outcome_status` | meaning |
| --- | --- |
| `marked_at_horizon` | a state in force was found; value fields populated |
| `right_censored` | the horizon lies beyond the recorded observation window, or the path holds fewer observations than the horizon requires. `DEFINITIONS.md` C1. **Never scored.** |
| `structural_exit_unavailable` | the curve completed at or before the horizon. Curve trading has ended and this regime has no exit venue after it — **never valued through PumpSwap.** |
| `no_observed_state_in_window` | the window covers the horizon and simply contains no observation inside it. The only state available is t0's own, which our entry has already changed, so pricing an exit against it would price our own impact away. |
| `no_decision` | no position existed to label |

**R4, enforced:** every non-`marked` row carries `NULL` for every value field — never zero, never
minus one — and must state a reason. `assert_row_arithmetic` refuses a zero slipped into one, and
refuses an absence with no reason, because an unexplained absence is indistinguishable from a lost
row.

`no_observed_state_in_window` is kept out of `right_censored` on purpose. Censoring is a statement
about window geometry; this is a statement about our own unmodelled impact, and folding them
together would hide the second behind the first.

## Every curve produces rows, including the ones we would not have traded

`no_decision` reasons — each a property of t0 or of the corpus, never of an outcome:
`out_of_regime_non_sol_quote`, `out_of_regime_mayhem`, `out_of_regime_mixed_within_curve`,
`no_transaction_terminal_state`, `no_later_observation`, `entry_refused`.

Conditioning the table on evaluability would select on tradability, and tradability is correlated
with exactly the outcomes a later model would be asked to predict.

## Return and drawdown, exact

Return is `docs/EXECUTABLE_RETURN.md` §1 exactly:

```
R = (Q_out - Q_in - C) / (Q_in + C)      C = entry curve fees + entry execution
                                             + exit curve fees + exit execution
```

reported as `net_return_numerator` / `net_return_denominator`, an **exact integer pair in lowest
terms**. No float appears in any row and a test walks the parsed row to prove it.
`assert_row_arithmetic` re-derives the numerator by a second route — realisable net minus entry
outlay — so a cost counted twice or not at all is caught rather than propagated.

Drawdown is recomputed **to the horizon**, not taken from the path record. The path record's
drawdown runs to the end of the observation window; a label at H must not see past H. That is R1
applied inside a derived statistic. Ratio is again an exact integer pair, withheld entirely unless
the relevant peak is strictly positive.

## Grouping keys, without the grouping

R5 requires splitting by at least `creator ∪ user`. The rows carry the raw keys that split will
need — `creator`, `create_user`, `t0_user`, `split_key_creator`,
`split_key_creator_union_t0_user` — all published at or before t0, with the create-precedes-t0
ordering **proved per row** rather than assumed.

**The split itself, and any model or baseline, is Phase 3/4 and is not implemented.** Emitting a key
is not performing a split. Funding-cluster leakage remains an unmeasured superset and an open gate.

## No verdicts

The row carries a *value*. It does not carry a *verdict*. There is no success field, no
profitability class, no rug or dump label, and a test asserts that no field name contains one.
Rug/dump construction remains Phase 3 and requires a fresh preregistered window (R2, R3).

## Measured validation

```
python scripts/b10c_label_corpus.py build-identity research/b9d_transaction_bodies.sqlite \
    research/b10b_observed_paths.sqlite
python scripts/b10c_label_corpus.py materialize research/b10b_observed_paths.sqlite \
    research/b10c_t0_identity.sqlite research/B10C_PREREGISTRATION_PLUMBING.json --gate
```

See `research/B10C_LABEL_MATERIALIZATION.md` for the measured counts, the coverage accounting, the
cross-checks against `b10b`, and the mutation results.

## Not covered

- **Returns.** Not computed on this window, by design.
- **Splits, models, baselines, feature vectors.** Phase 3/4.
- **Rug, dump, graduation or liquidity-failure labels.** Phase 3, and each needs its own
  preregistration on a fresh window.
- **The economic L1 threshold** of `docs/EXECUTABLE_RETURN.md` §3. Still unfrozen; the rows carry
  `b10b`'s mechanical liquidity states only.
- **Landing, contention, tips, latency, slippage.** Unmeasured. Every value here remains
  **simulated, not executable**.

No profitability claim is made and nothing here is a trading recommendation.
