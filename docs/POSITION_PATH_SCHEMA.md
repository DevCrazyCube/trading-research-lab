# Observed-state position path schema — v1.0.0

Produced by `scripts/b10b_position_path.py`. Read-only: consumers must treat every record as
immutable and must pin `schema_version`.

Status: **Phase 2, second bounded slice.** The deterministic arithmetic and coverage gates below are
measured and passing over the full 1,136-curve canonical reserve corpus. The stochastic Phase 2
gate — landing, contention, failure and fill distributions against forward observations — is **not**
addressed here and is not claimed.

## What this is, and the wider reading that would be false

Given a decision state at t0, an explicit order and cost policy, and a chronologically ordered
sequence of **later canonical reserve observations for the same mint**, this module prices one
hypothetical entry and marks that position to an executable-size-constrained exit at every later
observed state.

**The later states came from a world in which our hypothetical trade never happened.** They are not
counterfactual states and this module never calls them that. Every record carries the label

```
outcome_label   "SIMULATED_OBSERVED_PATH"
```

which is deliberately **not** `b10a`'s `SIMULATED`. That label covers a round trip priced against
two states. This one additionally asserts that the later states are *observed*, and a reader who
conflated the two would be reading a counterfactual claim that is not being made.

### The three limitations that travel inside every record

They are fields, not prose in a document, because a field is cheaper to read than a document.

1. **`limitations[0]` — observed states.** Our entry's own reserve impact is priced at t0 and our
   exit's own reserve impact is priced at each observed state. The **persistence** of our entry
   impact into later states, and other participants' **response** to it, are not modelled. **The
   sign of the resulting bias is not stated**, because subsequent participants' orders would have
   executed against different reserves and their observed sizes are not invariant to that.
2. **`limitations[1]` — no counterfactual replay.** No reserve delta is added to any later state and
   no observed order is replayed against shifted reserves. See below.
3. **`limitations[2]` — no latency.** No delay between observing a state and landing a transaction
   is modelled. The t0 state is stated by the caller and entry is priced against it exactly, as in
   `b10a`.

### Why the obvious repair is refused, by trade variant

The tempting fix is to add our reserve delta to each later state, or to replay the observed orders
against shifted reserves. Neither is valid for **any** variant this venue offers:

| variant | pins | what breaks under shifted reserves |
| --- | --- | --- |
| `buy_exact_sol_in`, `buy_exact_quote_in` | the quote spent | the tokens received differ from what the trader got; their slippage bound is on the token side and is not in the reserve evidence |
| `buy`, `buy_v2` | the tokens received | the quote cost differs, possibly above the `max_sol_cost` the trader signed — in which case the real transaction would have **failed and the observation would not exist** |
| `sell`, `sell_v2` | the tokens sold | the proceeds differ, likewise bounded by a signed `min_sol_output` |

In every variant the order's other dimension moves, and in two of the three the trade may not have
landed at all. Beyond the arithmetic, the decision to trade is itself not invariant to the price. So
there is no variant for which counterfactual replay is provably valid, and none is performed. **No
small-impact assumption is made and no tolerance exists anywhere in the module.**

## Inputs

| input | contents | rule |
| --- | --- | --- |
| `t0_state` | the eight `b10a` curve-state fields **plus all four canonical coordinates** | decision-time only; any missing field is refused |
| `observations` | ordered later states, each carrying `mint`, the four coordinates, the curve state and `is_transaction_terminal` | strictly increasing, same mint, strictly after t0 |
| `order` **or** `entry_policy` | explicit size, or a callable given a frozen feature view | exactly one; stating both or neither is refused |
| `fee schedule`, `CostPolicy` | as `b10a` | all fields required; absence is refused, never defaulted |
| `exit_rules` | caller-stated rules, listed below | the evaluator proposes none and selects none |

`b10a` ordered on `slot` alone. That cannot separate two observations in the same slot, and this
module's whole subject is the order of states within a path, so the **full four-component
coordinate is required** here: `slot, transaction_index, outer_index, inner_index`.

## The leakage barrier, made structural

- **`decide_entry` has no path parameter.** There is no argument through which a later observation
  could arrive. A future author cannot pass one without changing the signature and the test that
  pins it in the same edit.
- **An entry policy receives a `MappingProxyType` of scalars only**, copied out of t0. Its whole
  reference graph is walked at runtime and every reachable object must be a mapping or a scalar;
  any other container is a route out of the decision instant and is refused.
- **A stronger identity check is available** (`assert_no_future_reachable(view, observations)`) for
  a caller that holds a path — the test suite does, and asserts no observation is reachable, buried
  at any depth.
- **What this cannot defend against, stated plainly:** a caller whose policy *closes over* the
  future has leaked it themselves. The guarantee is that the engine never supplies it.

## Result record

```
schema_version   "1.0.0"
outcome_label    "SIMULATED_OBSERVED_PATH"   — always
calibration      "uncalibrated"              — always
limitations      the three above, verbatim
mint             the one mint this path is for
t0               canonical coordinate of the decision state
entry            b10a entry record: tokens_out, curve_fees, execution_costs,
                 lamports_out_of_wallet
marks[]          index, coordinate, evaluable, liquidity, reason, mark,
                 realizable_net_lamports, net_versus_entry_lamports,
                 running_peak_lamports, drawdown_lamports
drawdown         series, evaluable_points, peak/trough, max_drawdown_lamports,
                 max_drawdown_peak_lamports, ratio numerator/denominator
terminal_state   structural_unavailability | path_exhausted_right_censored
exit_rules[]     name, kind, detail, outcome, at, realizable_net_lamports, censoring
observations_*   supplied / evaluated / recorded_not_evaluated / dropped_after_completion
```

Each `marks[].mark` carries `tokens_held`, `tokens_executable`, `tokens_unrealizable`,
`gross_exit_lamports`, `realizable_net_lamports`, the full `curve_fees` breakdown and the full
`execution_costs` breakdown, plus the underlying `b10a` exit record.

## Executable-size-constrained exit

`quote_out_for_tokens_in` is non-decreasing in size, so the executable sizes form a prefix and a
binary search finds its end. **Maximality is then proven on the result, not trusted:** one more
token must overdraw the real quote reserve, or the module raises. No tolerance, no epsilon, no
sampling.

The bound is against the **real** quote reserve. A virtual-reserve bound would never bind — the
sell formula approaches the virtual quote reserve asymptotically and can never exceed it, however
large the size.

| liquidity | condition | value reported |
| --- | --- | --- |
| `L0_full_size_executable` | the whole position can be sold against the real reserve | net of the full size |
| `L2_size_constrained` | only a strictly smaller size is executable | net of the executable part; **the remainder is reported as tokens and never valued** |
| `L1m_no_executable_size` | the largest executable size pays **zero** lamports gross | `0`, and **no cost is charged** — no transaction would be submitted, and an invented cost is the same error as an invented proceed |
| `L3_structural_unavailable` | the curve is `complete` | nothing; the path terminates |

**`L1m` is not the `L1` of `docs/EXECUTABLE_RETURN.md` §3.** That L1 is an *economic* condition
whose threshold §3 deliberately leaves unfrozen, because choosing one after seeing the outcome
distribution is exactly the selection the preregistration apparatus exists to prevent. `L1m` is the
strictly *mechanical* floor underneath it: it chooses no threshold and reports where the integer
arithmetic runs out. **The economic L1 threshold remains open.**

The unrealisable remainder is never valued. Pricing it at the marginal rate would report proceeds
the reserve cannot pay; pricing it at zero would assert a loss the evidence does not show.

## An exit cannot land inside somebody else's transaction

Our exit is its own transaction. A curve that receives two trades in one transaction publishes two
reserve observations, and only the last is a state a transaction of ours could have faced. Every
observation carries `is_transaction_terminal`, and a non-terminal state is **recorded with reason
`exit_unreachable_intra_transaction` and not evaluated**. 1,121 transactions in this artifact carry
more than one observation on the same curve, so this is measured, not hypothetical.

The same rule applies to t0: the corpus runner advances t0 to the first transaction-terminal state,
which for **910 of 1,136 curves** is past the launch instruction, because the launch transaction
also carries the creator's own first buy.

For the same reason, **completion applies from its transaction, inclusive.** `CompleteEvent` fires
at an inner index after the trade that completed the curve, so a trade observation in the completing
transaction describes a curve already finished before anything of ours could follow. An exclusive
comparison would publish one tradable state per completed curve that never existed for us — and it
would sit at the top of the curve, the highest-valued state on the whole path.

## Drawdown

Series: **realisable net exit value**, `V(t)`, per `docs/EXECUTABLE_RETURN.md` §2 — not price, not
mark-to-last-trade, and only over evaluable marks.

- `max_drawdown_lamports = max_t (running_peak(t) - V(t))`, in exact integer lamports.
- `peak_lamports` is the **global** maximum; `max_drawdown_peak_lamports` is the peak the deepest
  fall actually started from. A later, higher peak followed by a shallow fall leaves the deepest
  drop behind an earlier one, so the two are reported separately rather than inferred.
- The **ratio is an exact numerator/denominator pair, never a float**, and is withheld entirely
  unless the relevant peak is strictly positive. A ratio against a peak of zero or less is not a
  small number, it is an undefined one, and reporting `0.0` or infinity would invent a drawdown
  figure for a position that never had value to lose. `V(t)` is routinely negative here, because
  costs exceed proceeds on a small position.

`V(t)` is size-dependent, so every drawdown figure is reported alongside the order that produced it.

## Exit rules and censoring

The evaluator proposes no rule and selects none. Every rule is caller-stated:

| kind | fires at |
| --- | --- |
| `slot_horizon` | first evaluable mark at or after `t0.slot + slots` |
| `observation_horizon` | the `count`-th evaluable mark |
| `first_full_size_exit` | first mark at `L0_full_size_executable` |
| `terminal_observation` | the last evaluable mark |
| `net_value_at_or_below` / `net_value_at_or_above` | first mark crossing a caller-stated lamport threshold |

Three outcomes, and the third is the point:

- `triggered` — with the mark, its liquidity state and its net value.
- `structurally_unavailable` — the curve completed before the rule could fire. Curve trading has
  ended and this regime has no exit venue after it.
- `right_censored` — the rule did not fire within the observation window. **Not a loss, not a win,
  and not a zero.** This is `docs/DEFINITIONS.md` C1 administrative censoring applied to a rule
  instead of to a token.

## Fail-closed conditions

| condition | outcome |
| --- | --- |
| observations not strictly increasing in canonical order | refused — a sequence is never sorted on the way in |
| a repeated canonical coordinate | refused; a duplicate would double-count a state |
| an observation at or before t0 | refused as leakage |
| any coordinate component missing | refused |
| any observation for another mint, or a t0 for another mint | refused |
| non-SOL quote, Mayhem mode, missing state field | refused (`b10a` eligibility) |
| curve already complete at t0 | entry refused |
| order exceeds the real token reserve at t0 | refused |
| cost-policy or fee-schedule field missing | refused, never defaulted |
| both `order` and `entry_policy`, or neither | refused |
| an unknown exit-rule kind, or a rule missing its parameter | refused, never ignored |
| a container reachable from the entry feature view | refused |
| the reachability walk exceeding its bound | refused, never truncated |

## Measured validation — the full 1,136-curve corpus

```
python scripts/b10b_path_dataset.py build research/b9d_transaction_bodies.sqlite
python scripts/b10b_path_dataset.py validate research/b10b_observed_paths.sqlite --gate
```

See `research/B10B_OBSERVED_PATH_VALIDATION.md` for the measured figures, the exact coverage
partition, the independent cross-check against `b10a`'s regime boundary, and the mutation results.

## Not covered

- **Landing, contention, tips, latency, slippage.** Unmeasured; require forward observation. Any
  value computed here is **simulated, not executable**.
- **The persistence of our own entry impact, and market response to it.** Named above; not modelled,
  and the direction of the bias is not claimed.
- **PumpSwap, migration, and any post-graduation exit.** A completed curve is structural
  unavailability, full stop.
- **Partial, scaled or multi-leg exits.** Each mark is an independent "what if the whole position
  were exited here"; taking one changes nothing about the others.
- **Strategy profitability and entry selection.** Not computed. The corpus run applies one fixed
  order to every eligible curve without exception, so it exercises the evaluator rather than
  searching it for a profitable rule.

No profitability claim is made and nothing here is a trading recommendation.
