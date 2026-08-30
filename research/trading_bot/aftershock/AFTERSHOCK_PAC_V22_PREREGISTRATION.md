# AFTERSHOCK PAC V2.2 — low-lag feed repair

**Status:** PREREGISTERED ENGINEERING SUCCESSOR — NOT SEALED, NOT CALIBRATED, NOT ACTIVE.

**Preregistered UTC:** 2026-08-30. This successor changes feed measurement and liveness only. It does
not change PAC V2.1's entry formula, USD 10 probe, processed-p90 requirement, buyer threshold, reserve
cover, slippage, execution model, exit policy, discovery gate, or paper-only boundary.

## Defect and burned boundary

The active V2.1 collector was audited after its dashboard event-dwell appeared frozen. Internal JSONL
ordering was valid, but the recorder was not realtime: it accidentally created two identical Pump log
subscriptions, performed a complete event/receipt history scan after every reconnect, and assigned
`source_received_unix_nanos` only after a queued frame reached decode. At audit time the feed process used
about 95% CPU, reconnects failed roughly every 95–115 seconds, the latest decoded event was 521 slots
behind a contemporaneous processed head, and its local source clock was 112 seconds after that slot's
reported block time. Backlogged chain activity was therefore compressed into local processing time.

All V2.1 observations and every V2.2 engineering-soak observation before a later V2.2 activation are
**BURNED FOR V2.2 PERFORMANCE**. V2.1 has zero fills and zero resolved positions; nothing is migrated.

## Frozen feed repair

1. Create exactly one Pump `logsSubscribe` at processed commitment per collector epoch.
2. Capture the raw WebSocket frame receive clock immediately after `recv()` and before JSON parsing or
   trade decoding. Multiple events in one frame are ordered by exact one-nanosecond increments only.
3. Replace full-history reconnect recovery with an O(1) tail invariant. Because one single-threaded writer
   fsyncs event then receipt before accepting another event, at most the final event can lack a receipt.
4. Poll an independent public processed `getSlot` head. A missing head, a head observation older than five
   seconds, or event lag above 32 slots degrades the collector and cannot qualify a new entry.
5. A reconnect is a new reserve-continuity epoch. The first event for each mint remains a seed only.
6. Feed health is a separately hash-bound operational artifact. It is not performance evidence.
7. Open-position and pending-exit servicing remains available during entry-feed degradation; the health
   gate applies when and only when the detector is asked to admit a new position.

The 32-slot bound is an engineering staleness refusal selected before V2.2 forward performance. It is not
an alpha threshold and may not be optimized on outcomes.

## Strategy and execution inheritance

The V2.1 single-shock rule and V2 execution/exit core remain byte-unchanged. V2.2 uses one observed sell
at least the exact USD 10 probe, full recovery and floor survival, event-time dwell at least the separately
calibrated processed p90, at least three observed buyer addresses excluding the shock seller, and current
reserve at least six times the larger of probe and shock. Execution remains decision → calibrated landing
target → first later processed account snapshot → own exact curve impact and all costs. Exit remains the
absolute 12-minute horizon, capacity loss, then 12% executable-net-quote trail, full position only.

## Activation and evaluation

No previous campaign is reusable: final feed/runner/config bytes must be sealed and committed first, then
a new campaign artifact must be committed before any memo broadcast, followed by at least 100 authentic
processed observations, every failure, independent finalized attestation, evidence commit, and set-once
activation commit. Broadcasting spends SOL and always requires explicit owner authorization.

The runner initializes at V2.2 feed EOF after activation. Promotion still requires 100 resolved, fully
costed paper positions, positive mean all-cost return, normalized capital above 100, and a full-loss rate
no worse than the immutable V1 baseline. Passing never authorizes real-money strategy orders.
