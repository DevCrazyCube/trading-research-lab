# Risk decision schema — v1.0.0

Produced by `scripts/b12a_risk_governor.py`. Read-only: consumers must treat every record as
immutable and must pin `schema_version`.

Status: **offline library only.** No server, no UI, no model, no signal, no wallet, no key, no
transport, no signing, no submission, no live RPC. A test asserts the module's source contains none
of those.

## What it decides, and the one thing it must never do

Given an immutable candidate order, the exact direct-Pump state, a portfolio snapshot, a
system-health snapshot and an explicit `RiskConfig`, it answers one question: **may this exact order
be placed?**

**It never resizes.** A governor that quietly shrinks an order to fit a limit changes the thing
being evaluated — the policy proposed 0.1 SOL, the book received 0.03 SOL, and every return,
drawdown and capacity figure downstream now describes a strategy nobody wrote. So there are two
outcomes, not three: approve the exact order, or reject it with reasons. `order_was_resized` is on
every record and is always `false`, and an invariant refuses a record where it is not.

## Fail closed, in three specific senses

1. **Default is no trade.** The empty reason list is the only thing that approves. No path returns
   approved while holding a reason, and an invariant refuses such a record if one were ever built.
2. **Absence is refusal, never a permissive default.** Every config, health, portfolio and proposal
   field is required. **No financial limit defaults to zero or to infinity** — zero silently
   disables trading, infinity silently disables the limit, and both are decisions nobody made. An
   *unknown* config key is also refused: a misspelled limit is an absent limit wearing a plausible
   name.
3. **An unexpected failure raises rather than approving.** Any non-refusal exception is re-raised as
   `RiskRefused`. A bug can stop this system; it can never open it. A test injects a genuine fault
   through the real entry point, because bad input is caught by validation and exercises a different
   path.

## Required inputs

| input | fields |
| --- | --- |
| `RiskConfig` | `config_version`, `ratification`, `max_order_lamports`, `max_total_exposure_lamports`, `max_open_positions`, `max_creator_exposure_lamports`, `max_creator_positions`, `max_daily_realised_loss_lamports`, `max_portfolio_drawdown_ratio`, `max_pending_exposure_lamports`, `max_evidence_age_slots`, `max_evidence_age_seconds` |
| health | `kill_switch_engaged`, `emergency_state`, `evidence_complete`, `evidence_conflicting`, `program_version_supported`, `curve_regime_consistent`, `evidence_slot`, `current_slot`, `evidence_unix`, `current_unix`, `provenance` |
| portfolio | `open_positions`, `pending_orders`, `realised_pnl_today_lamports`, `peak_realizable_portfolio_lamports`, `current_realizable_portfolio_lamports` |
| proposal | `proposal_id`, `mint`, `bonding_curve`, `creator`, `side`, `quote_lamports` |
| curve state | the eight `b10a` state fields |

`ratification` accepts **only** `operator_unratified`. No treasury or risk authorization exists, so
no other value can be true; adding one requires a `DECISIONS.md` entry. Every record carries the
value, plus `approval_is_simulation_only` and `NO_SIGNING_OR_SUBMISSION`.

`max_portfolio_drawdown_ratio` is an exact `[numerator, denominator]` pair. A percentage in floating
point is a different number from the one it prints as.

## Limit semantics — one rule, stated once

**A limit is the largest permitted value. Strictly exceeding it rejects; equalling it is
permitted.** That rule holds for every control without exception, including the daily realised loss,
where "limit reached" colloquially suggests otherwise. Consistency beats colloquialism, and every
limit has a test at cap−1, cap and cap+1.

## Controls

| reason | control |
| --- | --- |
| `R01_EMERGENCY_STATE` | rejects everything, including proposals that were acceptable a moment earlier |
| `R02_KILL_SWITCH_ENGAGED` | global operator stop |
| `R03`–`R07` | evidence incomplete, conflicting, version-unsupported, stale in slots, stale in seconds |
| `R08`–`R14` | curve eligibility and reserve capacity, **delegated to `b11b.evaluate_vetoes`** |
| `R15`–`R19` | order size, total exposure, open positions, per-creator exposure and count |
| `R20`–`R22` | daily realised loss, portfolio drawdown, drawdown unverifiable |
| `R23`–`R24` | pending exposure, duplicate pending proposal |

**Both clocks are checked.** Slots stop advancing during an outage while the wall clock keeps
running, and a stalled provider can replay an old slot under a fresh timestamp — checking one is
checking neither. Evidence dated *after* the current instant is `R04_EVIDENCE_CONFLICTING`: a broken
clock or a mislabelled snapshot, and either way freshness cannot be evaluated.

**An unverifiable drawdown rejects.** A peak of zero is not evidence of no decline, and a limit that
cannot be checked has not been passed.

**What that means at genesis, stated because it is the case most likely to be got wrong.** The
drawdown control reads **treasury net asset value**, not the sum of open positions. A system starting
with an empty book has an empty `open_positions` list and a perfectly well-defined NAV — the capital
available to trade. **The caller must supply a positive `peak_realizable_portfolio_lamports` and
`current_realizable_portfolio_lamports` reflecting that treasury**, and must not infer zero from
having no positions.

Passing zero because the book is empty is not a conservative default; it is a category error that
makes the governor reject every first trade with `R22_PORTFOLIO_DRAWDOWN_UNVERIFIABLE` and look
broken. The behaviour is correct — a zero NAV genuinely cannot be checked for drawdown — so the fix
belongs in what the caller supplies, not in this module.

**Eligibility is delegated, not reimplemented.** `b11b.evaluate_vetoes` is called and its `V`-codes
are mapped to `R`-codes. A governor that admitted a different set of curves than the evaluation
contract would make every evaluated result unachievable in practice; a test asserts the mapping is
total and that no curve formula appears in this module.

## Precedence and all-reasons

**Every applicable reason is reported**, ordered by a frozen `REASON_PRECEDENCE` tuple, with
`primary_reason` the most severe. Controls are **evaluated grouped by concern and reported ordered
by severity**, and those two orders differ on purpose — so that emitting reasons in computation
order produces visibly wrong output rather than accidentally-correct output.

`order_reasons(codes, precedence=...)` takes the precedence as a parameter so a test can hand it a
permuted tuple and prove the sort follows *that*, rather than insertion order or alphabetical
coincidence. A sort nobody can distinguish from an accident is not a specified sort. An undeclared
reason code is refused, never appended.

## Decision record

```
schema_version, decision ("approved" | "rejected")
approval_is_simulation_only, NO_SIGNING_OR_SUBMISSION
proposal                  echoed as a deep copy, never the caller's object
grouping                  mint, bonding_curve, creator  — identities, kept out of the numbers
reasons                   ordered; primary_reason
order_was_resized         always false; resizing_is_not_available explains why
evidence                  evidence/current slot and unix, age_slots, age_seconds, the two maxima,
                          provenance, kill_switch_engaged, emergency_state
exposure_before           integer lamports and counts only
exposure_after            the book this order would create — ONLY on approval
portfolio_risk            realised PnL today, its limit, peak/current realizable,
                          current_drawdown_ratio as an exact pair, its limit
config_version, config_ratification, config_sha256
decision_sha256
```

**A rejection publishes no projected book.** It would put a number on an operator's screen that
describes a state which will never exist.

**`portfolio_risk` exists because the loss and drawdown controls read figures that appear nowhere
in the exposure block.** Without it an operator can see *that* those controls passed but not against
what — and the decision hash would be blind to a change in either, so two different books could
produce a byte-identical record. That gap was found by a hash-stability test, not by inspection.

**Identities never enter the numbers.** The exposure block is asserted to hold integers only, and
`grouping` carries the identities — the same separation `b11b` enforces on features, for the same
reason.

## Determinism

Canonical JSON with sorted keys, exact integers and exact rational pairs. **No float anywhere**, and
a test walks the serialized record to prove it. Identical inputs produce a byte-identical record and
hash; a one-lamport change in the proposal, the book, the clock or any limit moves it. `config_hash`
is stable across key order so two configs compare by one string.

## No shared state

The governor holds no module-level book, cache or counter. `apply_approved(portfolio, record)`
returns a **new** snapshot with the order added to pending and never mutates its input. Threading
the snapshot through the caller is what makes two concurrent proposals accountable: the second call
sees the first as pending, or the caller has a bug that this design makes visible instead of
absorbing. Pending orders count toward every exposure limit, because they will become positions —
and a re-submitted `proposal_id` is rejected as a duplicate rather than double-counted.

## Not covered

- Whether the order is a good idea. No model, no signal, no view.
- Choosing its own limits. Every cap is caller-supplied and unratified.
- Execution, routing, submission, retry, cancellation or settlement.
- Exit-side risk. This governs entry proposals only.

No profitability claim is made and nothing here is a trading recommendation.
