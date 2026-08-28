# AFTERSHOCK PAC V2 — causal challenger preregistration

**Status:** DESIGN-FROZEN CANDIDATE, revised before any V2 row after hostile handoff-439 review. No
forward row may be admitted until the repaired dependency seal is anchored, a pre-anchored campaign
produces an independently attested latency bundle, and a later activation is separately anchored.
This is a paper-scenario instrument: no wallet, signer, sender, or real-money promotion is authorized.

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
landing target is decision time plus the calibrated p90. Entry price is the first public-RPC processed
bonding-curve account snapshot requested no earlier than that target and received no more than 30
seconds after it. Its RPC request carries minContextSlot equal to the newest decision-evidence slot
(or the newest position-state slot for an exit), and the returned context must meet that floor. A later
or pre-evidence snapshot cannot become the modeled fill. The snapshot's response state,
not the signal trade's reserves, is passed through the existing exact-integer b10a kernel.  Ten-percent
output slippage is fixed.  A missing, closed, completed, wrong-owner, zero-output, below-minimum, or
otherwise unpriceable entry is not a fill.  Snapshot observation is retried for at most 30 seconds
after the modeled target; an entry then rejects, a non-horizon transport timeout returns to observable
HOLD/redecision, and a horizon timeout settles conservatively as a full loss so the book cannot wedge.
A permanent schema/owner/regime/decode refusal rejects an entry and settles an open exit as a full loss;
it may never crash-loop the single-position lock.

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
  complete new rows from durable byte offsets. Both halves are fsynced; a crash after the event append
  is recovered as a later, visibly marked materialization rather than backdated or silently censored.
  An orphan/duplicate receipt is recorded and advanced once while its coincident batch is ineligible;
  truncation, malformed bytes and backward clocks still refuse.
- The first event for a mint in every collector/reconnect epoch is a continuity seed only. It has no
  pre-state and can never become detector evidence. Only a later event chained to that seed is eligible.
- Active-mint memory is incremental and bounded to the 180-second decision window plus open-position
  latest state.  It may not rescan the full per-mint history each cycle.
- State transitions are written atomically and ledger appends are idempotent.  A restart may skip a new
  opportunity, but may not reconstruct a historical entry.
- Production decision/horizon clocks are engine-owned. An entry fill is durably committed before any
  exit-policy service, and the fill is never serviced during the older clock sample that requested it.

## Calibration and activation gates

Latency has no default. Authority is a three-artifact bundle:

1. A campaign manifest is git-anchored before sampling and binds the repaired seal, one exact
   calibration fee payer, a submit RPC origin, a distinct verification RPC origin, campaign start,
   and the legacy single-signer memo-only transaction profile.
2. At least 100 hash-chained samples bind ordered wall and monotonic decision/build/sign/send/ack/land
   clocks to the exact signed wire transaction, acknowledged signature, slot, and campaign fee payer.
   Every transaction must contain exactly one no-account SPL Memo instruction whose challenge is
   deterministically bound to the campaign id, sample index, and previous sample id. Existing or
   unrelated transactions from the same fee payer therefore cannot satisfy the campaign.
3. A read-only attester queries every signature from the independently pinned verification origin at
   finalized commitment, preserves the raw response, and requires the returned on-chain wire bytes,
   signature, fee payer, successful meta and slot to equal the local sample. The on-chain block time
   must be within 120 seconds of the locally observed land clock.

Campaign, sample, and attestation file hashes are committed before activation and pinned out-of-band by
the later activation record. The campaign commit must be a strict ancestor of both evidence commits.
Both evidence commits must in turn be strict ancestors of the activation commit; runtime rechecks this
ancestry and git cleanliness rather than trusting the activation writer.
Activation must follow the last land and last attestation and occur within six hours of the last land.
The loader derives p90 from monotonic decision-to-land time only. A self-hashed or caller-pinned file,
copied public transaction, wrong fee payer, non-finalized response, or same-origin verification refuses.
Synthetic selftest bundles cannot activate the instrument. Creating/funding a calibration payer and
sending transactions remains a separately authorized measurement stage; this preregistration does not
authorize it.

Protocol fields were checked on 2026-08-28 against Solana's current official RPC documentation:
`getAccountInfo` exposes `minContextSlot` and a returned context slot, while `getTransaction` exposes
finalized commitment, base64 transaction bytes, slot, block time, and transaction metadata. Sources:
https://solana.com/docs/rpc/http/getaccountinfo and
https://solana.com/docs/rpc/http/gettransaction. The campaign memo profile uses the official SPL Memo
v3 program id/version published at https://github.com/solana-program/memo/blob/main/idl.json (accessed
2026-08-28; no historical slot range claimed).

Forward evidence begins only after: preregistration + config + code closure are sealed and git-anchored,
the exact calibration artifact is pinned, and a later set-once activation watermark is persisted.  No
pre-activation feed event, state, or result may enter the V2 ledger.

## Decision rule

Report all-cost mean/median return, win rate, full-loss rate, max drawdown, decision-to-snapshot delay,
RPC failure rate, entry rejection reasons, and time-to-resolution.  At 100 resolved discovery positions,
V2 may only replace V1 as the paper research focus if its mean all-cost return is positive, capital index
is above 100, and full-loss rate is no worse than V1's frozen comparable baseline.  Failure of any
condition is a kill.  This is not authorization for real money.
