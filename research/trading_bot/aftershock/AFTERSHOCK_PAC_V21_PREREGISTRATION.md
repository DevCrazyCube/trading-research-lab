# AFTERSHOCK PAC V2.1 — single-shock payable absorption

**Status:** PREREGISTERED DESIGN ONLY — NOT SEALED, NOT CALIBRATED, NOT ACTIVE.

**Preregistered UTC:** 2026-08-29T18:08:09Z. This file must be committed alone before any PAC V2.1
forward observation is inspected. It authorizes no transaction, wallet, order, paper fill, or performance
claim.

## Evidence boundary and lineage

PAC V1 is a falsified burned baseline. PAC V2 remains an untouched frozen control. PAC V2.1 is a new
candidate, not a post-hoc reinterpretation of either book.

The V2 feed interval from activation `1788018302155084220` through this preregistration is **BURNED FOR
V2.1 DESIGN**. It motivated the mechanism and may never become V2.1 forward evidence. The read-only
census at design time contained 819 usable events across 169 mints: 22 mints exhibited at least one
withdrawal/recovery cycle, one reached the complete two-cycle PAC core, and none reached V2's finalized-
latency dwell. These are design diagnostics, not performance results, and cannot tune the frozen rule
after this commit.

## Question

After one observed sell at least as large as our planned exact-quote probe, does full reserve recovery by
multiple observed buyer addresses, followed by survival for one authentic **processed-inclusion** latency
window and six-times exit capacity, identify a payable continuation more often than V2's two-cycle core
without increasing all-cost full-loss risk?

This mechanism is named **single-shock payable absorption**. It makes no claim that observed addresses are
independent people, owners, or funding clusters.

## Frozen entry rule

All conditions are required, using only causally received, same-mint, same-collector-epoch events in exact
receive order:

1. Size a planned exact-quote probe to exactly USD 10 from a fresh point-in-time SOL/USD observation,
   rounded down to lamports. No stale or missing quote may default.
2. Observe one sell whose reduction in real quote reserve is at least the planned probe. This is the
   payable-shock condition: the market has observed a withdrawal no smaller than our intended input.
3. After that sell, observe the first event whose post-event real quote reserve is at least the shock's
   pre-event real quote reserve. This is exact full recovery; partial recovery does not pass.
4. From that first full recovery through the decision event, real quote reserve never falls below the
   shock's pre-event reserve. Small fluctuations above that economic floor are allowed; a post-recovery
   all-time-high ratchet is not required.
5. The decision event is at least one separately calibrated nearest-rank p90 **decision-to-processed-
   inclusion** latency after full recovery. The complete shock-through-decision span is at most 180
   seconds. Latency has no default and finalized time may not be relabelled as processed time.
6. At least three distinct observed buyer addresses bought after the shock and at or before the decision.
   The shock seller address is excluded from this count. This is address breadth only.
7. At the decision event, real quote reserve is at least six times the larger of the planned probe and
   the observed shock withdrawal.

The newest qualifying shock is selected. Evidence binds the shock, first full recovery, and every later
event through the decision. A later event may create a new decision prefix; no historical prefix may be
backfilled after activation.

Formula, evaluated component-wise with exact integers:

`W >= Q  ·  R_recovery >= R_pre  ·  min(R_after_recovery) >= R_pre  ·  dwell >= p90_processed`

`buyers_ex_seller >= 3  ·  R_decision >= 6 * max(Q, W)  ·  span <= 180s`

## Execution and exit policy

If later activated, entry execution must use the causal V2 execution boundary: decision first, then a
separate modeled landing target, then the first processed account snapshot requested no earlier than that
target, with own exact-integer curve impact, all costs, and ten-percent output slippage. A missing or
unpriceable entry is no fill.

Exit policy is inherited unchanged from PAC V2: one full-position exit; absolute 12-minute horizon first,
then reserve capacity below six times initial quote input, then a 12% executable-net-quote trail. There is
no scale-out, fixed take-profit, ratchet, or threshold sweep.

## Processed-inclusion calibration contract

PAC V2's 12.164662268-second artifact measured decision through a `getTransaction(finalized)` observation.
It remains valid evidence of finalization, but is not a processed-inclusion clock and may not authorize
V2.1.

V2.1 requires a new pre-anchored, default-off, memo-only campaign with at least 100 unique transactions.
Each sample must preserve decision/build/sign/send/ack clocks, then record the first successful public-RPC
observation whose confirmation status is at least `processed`, and finally preserve independent finalized
attestation of the identical signature and wire bytes. The nearest-rank p90 is derived only from monotonic
decision-to-first-processed-observation intervals. Finalized attestation proves reality; it does not replace
the earlier processed clock. Failed, timed-out, or ambiguous observations remain failures and cannot be
dropped. No existing V2 sample may be reused because it did not record the first processed observation.

Building and testing this tooling is authorized by the research task. Broadcasting a campaign spends SOL
and remains a separate owner-authorized step.

## Forward evaluation and kill rule

Forward V2.1 evidence starts only after the final code/config/dependency seal, pre-sampling campaign commit,
new processed-inclusion calibration and independent attestation commits, and a later activation commit.
All earlier observations are excluded by an activation watermark.

Report the complete entry funnel, signal rate, decision-to-snapshot delay, RPC/failure outcomes, all-cost
mean and median return, win rate, full-loss rate, and maximum drawdown. At 100 terminal positions, V2.1 is
killed unless mean all-cost return is positive, normalized capital index exceeds 100, and full-loss rate is
no worse than V1's immutable comparable baseline. No interim result may change this rule or any entry/exit
threshold. Passing is a paper-research result, not authorization for live money.
