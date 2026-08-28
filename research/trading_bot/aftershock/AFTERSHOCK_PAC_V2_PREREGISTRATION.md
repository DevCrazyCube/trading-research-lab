# AFTERSHOCK PAC V2 — causal challenger preregistration

**Status:** DESIGN-FROZEN CANDIDATE; no forward rows may be admitted until the dependency seal is
anchored, an authentic latency calibration artifact passes the frozen loader, and an activation
watermark is created afterwards.  This is a paper-scenario instrument: no wallet, signer, sender, or
real-money promotion is authorized.

## Question and lineage

PAC V1 is retained unchanged as the burned baseline.  Its post-activation book is economically
negative and is not a tuning set.  V2 tests one prospective question: does requiring the observed
second recovery to survive one measured execution-latency window, with address breadth and enough
quote-reserve capacity to withstand the largest observed setup sell, improve all-cost paper-scenario
outcomes?

The unchanged PAC core is two sequential quote-reserve withdrawals and recoveries where the second
withdrawal is no weaker, its recovery is no slower, and both pre- and recovered reserves are no lower.
Minimum withdrawal is 50,000,000 lamports and the complete setup plus dwell must fit in 180 seconds.

## Entry rule (all conditions required)

1. The original PAC core passes using only causally received PAC V2 feed events.
2. The recovered reserve never falls below recovery 2 during a dwell of at least the authentic
   nearest-rank p90 decision-to-land latency.
3. At least three distinct observed buyer addresses buy during recovery-2-plus-dwell.  This is address
   breadth only; it is not evidence of independent ownership or funding.
4. Current real quote reserve is at least six times the larger of the planned exact-quote probe and
   the largest observed quote-reserve withdrawal in the setup.
5. A fresh point-in-time SOL/USD observation sizes the probe to exactly USD 10, rounded down to
   lamports.  The probe must fit inside both demonstrated PAC withdrawals.

Decision time is the runner's internal observation time after all evidence is materialized.  Modeled
landing target is decision time plus the calibrated p90.  Entry price is the first public-RPC processed
bonding-curve account snapshot requested no earlier than that target.  The snapshot's response state,
not the signal trade's reserves, is passed through the existing exact-integer b10a kernel.  Ten-percent
output slippage is fixed.  A missing, closed, completed, wrong-owner, zero-output, below-minimum, or
otherwise unpriceable entry is not a fill.  Snapshot observation is retried for at most 30 seconds
after the modeled target; an entry then rejects, a non-horizon exit returns to observable
HOLD/redecision, and a horizon exit settles conservatively as a full loss so the book cannot wedge.

## Exit rule

One full-position exit only; no scale-out, ratchet, stop-loss optimization, or runner.  Every observable
state updates a full-position b10a exit quote.  The 12-minute horizon has absolute priority, then reserve
capacity below 6× initial quote input, then a 12% executable-net-quote trail from peak.  Any triggered
exit gets a new decision time and a separate account snapshot at decision plus calibrated p90; no later
trade is required.  At or after the horizon, an unpriceable or net-negative dust position resolves as
a full loss and releases the one-position lock.  Before the horizon, a venue-unpriceable position also
resolves as a full loss.  Unknown programming/schema errors remain visible refusals.

ATA rent is charged in the primary all-cost return and is not claimed back without a separately
observed close-account attempt and cost.  A rent-reclaimed counterfactual may be displayed separately
but cannot decide promotion.

## Clocks, feed, and restart rules

- `source_received_unix_nanos`, `materialized_unix_nanos`, and `runner_seen_unix_nanos` are distinct,
  ordered clocks and may not be relabelled.
- Feed event bytes and materialization receipts authenticate each other.  The runner consumes only
  complete new rows from durable byte offsets; truncation, orphan receipts, duplicates, and backward
  clocks refuse.
- Active-mint memory is incremental and bounded to the 180-second decision window plus open-position
  latest state.  It may not rescan the full per-mint history each cycle.
- State transitions are written atomically and ledger appends are idempotent.  A restart may skip a new
  opportunity, but may not reconstruct a historical entry.

## Calibration and activation gates

Latency has no default.  The calibration artifact requires at least 100 authentic landed samples with
decision/build/sign/send/ack/land clocks and raw-evidence hashes.  The loader pins the whole-file SHA-256,
rejects duplicates or impossible clocks, and derives exact nearest-rank p90.  Synthetic samples cannot
activate the instrument.  Creating a signing/landing recorder is a separately authorized measurement
stage; this preregistration does not authorize it.

Forward evidence begins only after: preregistration + config + code closure are sealed and git-anchored,
the exact calibration artifact is pinned, and a later set-once activation watermark is persisted.  No
pre-activation feed event, state, or result may enter the V2 ledger.

## Decision rule

Report all-cost mean/median return, win rate, full-loss rate, max drawdown, decision-to-snapshot delay,
RPC failure rate, entry rejection reasons, and time-to-resolution.  At 100 resolved discovery positions,
V2 may only replace V1 as the paper research focus if its mean all-cost return is positive, capital index
is above 100, and full-loss rate is no worse than V1's frozen comparable baseline.  Failure of any
condition is a kill.  This is not authorization for real money.
