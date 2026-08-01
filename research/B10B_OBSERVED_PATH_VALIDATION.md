# B10b — canonical observed-state position path evaluator, validated over 1,136 curves

Date: 2026-08-02. Author: Claude (handoff 64). Offline, read-only, no network.
Code: `scripts/b10b_position_path.py`, `scripts/b10b_path_dataset.py`.
Schema: `docs/POSITION_PATH_SCHEMA.md` v1.0.0. Tests: `tests/test_b10b_position_path.py`.

Reproduce:

```
python scripts/b10b_path_dataset.py build research/b9d_transaction_bodies.sqlite
python scripts/b10b_path_dataset.py validate research/b10b_observed_paths.sqlite --gate
```

## 1. What was built, and the claim it makes

Given a decision state at t0, an explicit order and cost policy, and a chronologically ordered
sequence of later canonical reserve observations for the same mint, the evaluator prices one
hypothetical entry with `b10a` and then marks that position to an **executable-size-constrained**
exit at every later observed state — producing gross and net exit value with every cost field, a
liquidity state and reason code per observation, a peak-to-trough drawdown on realisable net exit
value, an explicit terminal state, and caller-stated horizon/exit-rule outcomes with right-censoring.

**The claim is narrow on purpose.** The later reserve observations came from a world in which our
hypothetical trade never happened. Every record carries the label `SIMULATED_OBSERVED_PATH` —
deliberately *not* `b10a`'s `SIMULATED` — so that no reader can take it for a counterfactual replay
of a world containing our order. The record itself carries three limitation strings, verbatim, as
fields rather than as prose in a document elsewhere.

**Unmodelled, and named as such:** our entry would have removed tokens from the real reserve and
added quote lamports to it; that perturbation would persist into every later state and other
participants would have responded to it. Neither is modelled. **The sign of the resulting bias is
not stated,** because subsequent participants' orders would have executed against different reserves
and their observed sizes are not invariant to that.

## 2. Why counterfactual replay was refused, by trade variant

The directive permitted adjusting later states *only if validity could be proven by trade variant*.
It cannot be, and the reason is specific rather than cautious:

| variant | pins | what breaks under shifted reserves |
| --- | --- | --- |
| `buy_exact_sol_in`, `buy_exact_quote_in` | the quote spent | the tokens received differ from what the trader got; the slippage bound is on the token side and is not in the reserve evidence |
| `buy`, `buy_v2` | the tokens received | the quote cost differs, possibly above the `max_sol_cost` the trader signed — in which case the transaction **would have failed and the observation would not exist** |
| `sell`, `sell_v2` | the tokens sold | the proceeds differ, likewise bounded by a signed `min_sol_output` |

In every variant the order's other dimension moves, and in two of the three the trade may not have
landed at all. Beyond the arithmetic, the decision to trade is not invariant to the price. **No
reserve delta is added to any later state, no order is replayed, no small-impact assumption is made,
and no tolerance exists anywhere in the module.**

## 3. Two structural corrections this work forced

### 3.1 An exit cannot land inside somebody else's transaction

Our exit is its own transaction. A curve that receives two trades in one transaction publishes two
reserve observations, and only the last is a state a transaction of ours could ever have faced.
Marking a position to a mid-transaction state reports a price nobody could have taken.

**Measured:** 1,121 transactions in the artifact carry more than one reserve observation on the same
curve (1,033 with two, 88 with three). Of 94,389 observations, **93,180 are transaction-terminal**
and 1,209 are not. Non-terminal states are recorded with reason `exit_unreachable_intra_transaction`
and never priced — **289** of them fell inside evaluated paths.

The same rule applies to t0. The corpus runner advances t0 to the first transaction-terminal state,
which for **910 of 1,136 curves** is past the launch instruction, because the launch transaction
also carries the creator's own first buy.

### 3.2 Completion applies from its transaction, inclusive

`CompleteEvent` fires at an inner index *after* the trade that completed the curve. A trade
observation in the completing transaction therefore describes a curve already finished before
anything of ours could follow it. Comparing on the full instruction coordinate, or comparing
exclusively, would publish exactly one tradable state per completed curve that never existed for
us — **and it would sit at the top of the curve, the highest-valued state on the whole path.**

A mutant flipping this comparison from inclusive to exclusive survived the first mutation run. The
rule is now a named function, `is_complete_at`, with its own test.

## 4. Measured results — the full 1,136-curve corpus

### 4.1 Corpus

Derived from `research/b9d_transaction_bodies.sqlite` into
`research/b10b_observed_paths.sqlite`, 24 MB, every observation decoded from its own preserved
transaction body at the coordinates its reserve evidence names.

| quantity | value |
| --- | --- |
| curves | 1,136 |
| observations | 94,389 (1,136 `CreateEvent`, 93,253 `TradeEvent`) |
| curves in the frozen regime | 1,126 |
| curves out of regime | 10, all non-SOL quote; **zero Mayhem, zero mixed within a curve** |
| curves with a `CompleteEvent` | 16 |
| curves in strictly increasing canonical order | **1,136 / 1,136** |
| content SHA-256 | `4aca86d3756afec09d70725f76d0b51952c1008bcdb0f5730c5b787de62ce7b3` |

**Reproducibility measured, not asserted:** a full rebuild from the source artifact produced a
byte-identical content hash and identical metadata.

**Independent agreement with `b10a`.** `b10a`'s replay gate counted **743** out-of-regime *trade*
observations over the same artifact by an entirely different route. This corpus's 753 out-of-regime
observations are exactly those 743 trades plus their 10 `CreateEvent`s. The two modules agree on the
regime boundary rather than each defining its own; the equality is pinned by a test.

### 4.2 Coverage — a partition, not a set of counters

Every observation lands in exactly one bucket, and the buckets are asserted to sum:

| bucket | observations |
| --- | --- |
| on out-of-regime curves | 753 |
| on curves with no later observation | 323 |
| on curves where entry was refused | 3 |
| at or before t0 on evaluated curves | 1,711 |
| **supplied to the evaluator** | **91,599** |
| **total** | **94,389 — partition sums** |

Curve accounting: 1,126 in regime = **884 evaluated** + 241 with no later transaction-terminal
observation + 1 entry-refused. Of the 241, **159 have no trade at all** and the remaining 82 have
every trade inside their launch transaction.

The single entry refusal is `b10a`'s real-reserve size guard firing correctly: at that curve's t0 the
real token reserve held 100,000,000,000 raw units and the fixed order would have taken
243,342,228,618.

### 4.3 Evaluation

| quantity | value |
| --- | --- |
| paths evaluated | 884 |
| observations supplied | 91,599 |
| observations evaluated | 91,296 |
| recorded but not evaluated | 303 (289 intra-transaction, 14 curve complete) |
| dropped after completion | 0 |
| **arithmetic errors** | **0** |

`dropped_after_completion = 0` is itself a consistency signal: no curve published a further trade
observation after its completing transaction, which is what a closed curve should look like.

Liquidity state per evaluated mark, one fixed 0.1 SOL order applied to every curve:

| liquidity | marks |
| --- | --- |
| `L0_full_size_executable` | 86,033 |
| `L2_size_constrained` | 5,263 |
| `L3_structural_unavailable` | 14 |
| `L1m_no_executable_size` | 0 |

`L1m` did not occur because the minimum observed post-trade `real_quote` in the corpus is 1 lamport,
never 0. The state is exercised by unit fixtures instead, not left untested.

Terminal states: 870 paths right-censored by the end of the observation window (`DEFINITIONS.md`
C1), 14 ended in structural unavailability.

Exit-rule outcomes, over 884 paths. **These are diagnostics of the evaluator, not strategy results:**
one fixed order size was applied to every eligible curve without exception, and no profitability
figure is computed anywhere.

| rule | triggered | right-censored | structurally unavailable |
| --- | --- | --- | --- |
| 1,000-slot horizon | 503 | 372 | 9 |
| 10,000-slot horizon | 321 | 551 | 12 |
| 10-observation horizon | 469 | 408 | 7 |
| first full-size exit | 623 | 260 | 1 |
| terminal observation | 883 | 0 | 1 |

**Right-censored is neither success nor failure and is never counted as either.** The 10,000-slot
row is the clearest case: 551 of 884 curves simply have no observation that far out, and scoring
those as outcomes would be reporting on the observation window rather than on the market.

### 4.4 The 16 completions, all accounted for

14 were reached inside an evaluated path. The other two are explained rather than left as a gap:

- one curve **completed inside its own launch transaction** — its only transaction-terminal state is
  already complete, so no open state ever existed for us to enter at;
- one is the single entry refusal above — its t0 sat near the top of the curve with 100 raw tokens
  of real reserve remaining.

Correspondingly, `terminal_observation` triggered on 883 of 884 paths: 13 of the 14 completed curves
still had priced marks before completion, and only one had none at all.

### 4.5 Determinism

Two consecutive validation runs produced byte-identical reports. 884 path records were serialised
canonically (sorted keys, no insignificant whitespace, **no float anywhere in any record** — a test
walks the parsed record and fails on any float) and chained:

```
path_record_hash_chain_sha256 = b15f81f4f0c3fe73ea38158b78de2219143ac177e620e1f54bd5c8ca348ca434
```

## 5. Verification — 15 mutants, 3 survived first

Tests: 72 in this module's suite, 859 passing across the whole repository.

Every mutant is a real textual edit to the shipped source — applied, the suite run, then reverted —
not a hypothetical. Each anchor is asserted to match exactly once, so a mutation that silently
failed to apply is reported as a miss rather than counted as a kill.

| # | mutation | result |
| --- | --- | --- |
| 1 | size bound uses the virtual reserve instead of the real one | killed |
| 2 | executable size off by one, maximality proof removed | killed |
| 3 | duplicate coordinates accepted | killed |
| 4 | the path is sorted on the way in instead of being checked | killed |
| 5 | foreign mints accepted into the path | killed |
| 6 | negative realisable value clamped to zero | killed |
| 7 | a completed curve is marked instead of declared unavailable | killed |
| 8 | an unfired rule falls back to the last mark instead of censoring | killed |
| 9 | the running peak is allowed to fall | killed |
| 10 | a mid-transaction state is priced as if we could have traded against it | killed |
| 11 | the entry feature view is replaced by the raw t0 mapping | **survived first** |
| 12 | an undefined drawdown ratio is reported as zero over zero | killed |
| 13 | completion keyed exclusively, exposing the completing transaction's state | **survived first** |
| 14 | t0 taken from the first row rather than the first tradable state | killed |
| 15 | the coverage partition check never reports a mismatch | **survived first** |

**All three survivors were real gaps, and each changed the code, not only the tests.**

- **11.** The suite proved a safe feature view *could* be built but never that `decide_entry`
  actually hands it over. Handing the policy the raw t0 mapping gives it a mutable object carrying
  every field the caller attached — here `mint` and the terminality flag — and nothing noticed. A
  test now asserts the policy receives a `MappingProxyType` whose keys are exactly the declared
  decision-time set, and that mutating it raises.
- **13.** The completion comparison was inline and untested at that granularity. It is now
  `is_complete_at`, with a test pinning that the completing transaction's own state is already
  unreachable for us.
- **15.** A gate reporting on its own completeness is worth exactly as much as a test that can make
  it say no, and the inline comparison could not be made to. It is now `coverage_partition_error`, a
  pure function the tests hand a deliberately unbalanced count.

After the fixes: **15 of 15 killed.**

## 6. What is not claimed

- **The stochastic half of the `PLAN.md` Phase 2 gate is untouched.** No landing, contention,
  failure or fill distribution is calibrated. Every value here is **simulated, not executable**.
- **No profitability figure, expectancy, win rate or strategy result is computed**, and no entry is
  selected. The corpus run applies one fixed order to every eligible curve so that it exercises the
  evaluator rather than searching it for a rule.
- **The economic L1 threshold of `docs/EXECUTABLE_RETURN.md` §3 remains unfrozen.** `L1m` is the
  mechanical arithmetic floor underneath it and chooses no threshold.
- **The persistence of our own entry impact, and market response to it, are not modelled**, and the
  direction of that bias is not claimed.
- **A caller whose entry policy closes over the future has leaked it themselves.** The guarantee is
  that the engine never supplies it; that is enforceable and is enforced.
- **PumpSwap, migration and post-graduation exits.** A completed curve is structural unavailability,
  full stop.
