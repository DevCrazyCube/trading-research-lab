# AFTERSHOCK execution-measurement chain

**Status:** implemented as paper-only measurement infrastructure on 2026-08-28 (handoff 424).
No AFTERSHOCK strategy is integrated with it, no strategy is promoted, and no live/devnet transaction
path is present. V1–V5 outcomes remain burned/plumbing evidence.

## Evidence boundary

Every produced attempt is labelled `SIMULATED_OBSERVED_PATH` and
`CALIBRATION_UNCALIBRATED`. A PumpPortal stream additionally carries
`PUMPPORTAL_RECEIVE_TIME_SCENARIO`. The engine does not emit an “executable” label.

`observation_unix_nanos` is a local receive clock. Provider event time is not accepted as a substitute.
Canonical identity, when available, is the separate tuple
`(slot, transaction_index, outer_index, inner_index)`. A partially canonicalized, mixed-source,
cross-mint, backward, duplicate, non-reconciling, or non-monotonic stream refuses.

The observed reserve path came from a world without our hypothetical order. The integer B10a kernel
prices our immediate impact against one observed boundary state, but the engine does not persist that
impact into later observations or replay other participants counterfactually. The sign of this limitation
is not assumed.

## Causal admission chain

An order attempt is reachable only through all of these records:

1. A frozen preregistration and canonical frozen JSON declare the complete dependency list, future
   experiment modules, and a post-activation warm-up policy.
2. `manifest.write_seal` hashes the preregistration bytes, canonical JSON, execution modules, actual
   B10a/B10b/B9i/B9d dependency chain, pinned IDLs, and every declared experiment module.
3. The seal file must be tracked and byte-clean against `HEAD`. An uncommitted seal cannot activate.
4. `append_activation` records an internally-clocked, set-once first activation or a monotonic restart
   coordinate. A caller cannot provide its time.
5. `append_warmup_complete` accepts only a complete, strictly post-activation stream satisfying the
   sealed event-count and receive-time-span policy. After restart, every warm-up coordinate must be
   strictly beyond the persisted resume coordinate.
6. `write_activation_anchor` pins the session event, warm-up root, and complete activation-chain prefix.
   That activation-root file must also be tracked and byte-clean against `HEAD`.
7. `load_session_proof` derives an immutable `SessionProof` from those files. It verifies every known
   historical activation anchor, so deleting or fully rehashing a previously anchored session refuses.
8. Every decision and attempt re-loads and compares the latest proof. A restart immediately invalidates
   the old proof until a new post-restart warm-up and activation-root anchor exist.

There are no caller-set `verified` or `warmup_complete` fields. Until the owner-gated commits exist,
the public positive path remains closed by design.

## Decision evidence

`build_decision_record` records its decision time internally. It derives the complete event prefix whose
receive clocks are at or before that time; a later event cannot enter the decision.

The detector is named by repository-relative module path and callable name. Its exact file hash must match
the corresponding path in the session seal. The engine loads that function itself and gives it the complete
available causal prefix. The returned evidence indices must be exact, unique, increasing, post-warm-up,
and no later than the evaluated prefix. `signal_index` is always their maximum.

`DecisionRecord` binds:

- seal, session, and activation-root hashes;
- frozen-spec hash and detector path/hash/callable;
- the full evaluated-prefix root and last evaluated index;
- all detector evidence commitments and their maximum receive/canonical coordinate;
- the internally observed decision clock.

Every attempt recomputes the record hash, the available-prefix maximum, and the evidence commitments,
then reruns the sealed detector. A publicly rehashed record that omits detector evidence therefore refuses.

## Attempt and clock semantics

Latency is a required positive integer parameter with no default. It remains an uncalibrated scenario
input. The engine calculates:

```text
modeled_land_target = recorded_decision_time + caller_latency
scenario_boundary = first later observation at/after modeled_land_target
```

The boundary must be strictly after every detector-evidence coordinate. Its `pre_state` is passed to the
integer quote kernel. This is a scenario boundary, not proof that a transaction was sent or landed.

Only observation and decision clocks are measured. `build_unix_nanos`, `send_unix_nanos`, and
`land_unix_nanos` remain null. `modeled_land_target_unix_nanos` and
`scenario_boundary_observation_unix_nanos` have separate names. If no future observation brackets the
target, the result is `RIGHT_CENSORED_NO_BOUNDARY`; send, land, and cost remain unknown. It is not labelled
“never sent.”

Outcomes are explicitly scenario outcomes:

- `SCENARIO_FILLED`
- `SCENARIO_FAILED_SLIPPAGE`
- `SCENARIO_UNAVAILABLE`
- `RIGHT_CENSORED_NO_BOUNDARY`

### Persistent PAC orchestration boundary

`RIGHT_CENSORED_NO_BOUNDARY` closes one attempt; it is not permission for a saved historical decision
to remain fillable forever. PAC schema-3 therefore clears a censored entry as a no-trade diagnostic. A
censored trail/capacity sell can be requested again only through a fresh exit DecisionRecord. If the
12-minute hard-horizon sell is still censored, the portfolio stress outcome is exact full loss and the
single-position lock is released. Likewise, a triggered priceable exit with non-positive all-cost wallet
proceeds settles as exact full loss rather than crashing on a negative value or inventing a successful
sell. These are runner portfolio semantics; they do not relabel the engine AttemptRecord.

If a feed observation materialises between candidate snapshot and internal decision clock, the saved
prefix is incomplete. PAC invalidates that decision as a no-cost/no-fill diagnostic and releases it.
The raw observation remains preserved; it is never deleted to make the decision validate.

## Orders, costs, and retries

Only typed intents exist:

- exact-quote buy → token atoms out with positive `min_tokens_out`;
- exact-token sell → lamports out with positive `min_quote_out`.

Wrong output units, negative costs, negative/float reserves, invalid enums, and zero slippage bounds refuse.
A zero quote output is unavailable, never filled. Only B10a's named `SimulationRefused` is translated to
`PriceUnavailable`; an unknown exception propagates visibly.

The B10a adapter fixes `failed_attempts=0`. One `AttemptRecord` can therefore contain only the current
attempt's gas. Each retry has a new content-derived id and must reference the immediately preceding id;
negative, skipped, or mismatched retry metadata refuses.

ATA rent is accounted separately from attempt gas. The typed lifecycle distinguishes `NOT_CREATED`,
`PREEXISTING`, `LOCKED`, `STRANDED_AT_HORIZON`, `CLOSE_FAILED`, and
`RECLAIMED_FULL_SELL_CLOSE`. Reclaim requires a proven zero token balance, a successful close, and its
actual non-negative close-transaction cost. Contradictory lifecycle flags refuse.

## Point-in-time sizing

USD sizing uses decimal strings and a typed SOL/USD observation carrying receive time, source, and evidence
hash. Future, stale, non-finite, non-positive, float-bound, or sub-lamport results refuse. The result is an
integer lamport amount. SOL P&L and USD-equity remain separate numeraires; neither is silently substituted
for the other.

## Verification and remaining gates

`python -m scripts.trading_bot.aftershock.execution_selftest` exercises the public path under synthetic
git-anchor fixtures and adversarial negative controls. `python -m scripts.trading_bot.aftershock selftest`
adds all legacy AFTERSHOCK regression suites.

The following remain deliberately undone:

- no secondary-sell detector, thresholds, sizing policy, or outcome book;
- no real seal or activation-root artifact for such an experiment;
- no measured sign/send/land clocks or calibrated latency/failure distribution;
- no shadow/live integration and no live trading authorization.

Therefore this chain is stronger research plumbing, not evidence of an edge and not authorization to
preregister or trade a strategy.
