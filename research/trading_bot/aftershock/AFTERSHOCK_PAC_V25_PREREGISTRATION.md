# AFTERSHOCK PAC V2.5 — premise-bound paid absorption

**Status:** PREREGISTERED PAPER-SCENARIO SUCCESSOR — NOT A PROFIT CLAIM, NO WALLET, NO ORDERS.

**Decision (2026-08-31):** V2.4 is retired after 10 resolved rows (mean −0.42%, median −10.51%)
with one additional open row preserved as right-censored. V2.5 starts a separate ledger and inherits
no V2.4 performance observation.

## Frozen hypothesis

Pump.fun supplies a mechanical house edge through entry/exit tolls and a highly asymmetric rug tail.
V2.5 does not claim to reverse that edge. It tests whether we can demand that later participants have
already paid enough flow to finance our exit before taking a fixed USD 10 paper probe:

1. Observe one same-mint sell withdrawing at least our exact probe `q`.
2. Require reserve recovery to `pre_shock_real_quote + q`; this paid floor must survive for the
   authenticated processed-inclusion p90, with at least three literal buyer addresses excluding the
   shock seller.
3. Require current reserve at least `max(paid_floor, 6 × max(q, shock_withdrawal))`.
4. Graduation runway: over every causal p90 window in the setup, measure the largest observed real
   token depletion `D`. The decision state must retain at least `decision_tokens_out + 2 × D` real
   token atoms (one window for entry landing, one for an emergency exit landing).
5. At most one filled entry per mint for the entire V2.5 ledger. Rejected attempts may be reconsidered;
   a filled mint never is. The hashed ledger is the restart authority.

## Frozen exit and accounting

- Full-position only; no scale-out. Existing absolute 12-minute horizon and 12% executable-quote
  trail remain.
- The combined reserve gate recorded at entry is the premise floor. If a causally refreshed live
  curve falls below it, issue `EXIT_PREMISE_BREAK` immediately, with normal calibrated landing and
  slippage accounting; do not wait for the trailing stop.
- Every unpriceable bonding-curve path, including a throttled refresh and a rejected pending curve
  exit, must first enter the bounded PumpSwap venue-transition flow. It may become a full loss only
  after the existing no-route grace/horizon outcome.
- Exact V2.4 all-cost accounting remains: fixed USD 10 point-in-time sizing, curve fees, attempts,
  slippage, and ATA rent reclaimed only after a confirmed full exit net of close gas.

## Calibration inheritance and decision gate

V2.5 changes strategy-only modules, not V2.4's send/sign/processed-land measurement path, public RPC
provider, snapshot decoder or execution kernel. It therefore inherits V2.4's anchored p90 and exact
calibration artifact by hash. This is executor calibration reuse, not result reuse; V2.5 gets a new
post-seal activation watermark and no backfill.

At 100 resolved positions: continue only if mean all-cost return is positive, capital index exceeds
100, and unexitable full-loss rate is not worse than V2.4. This never authorizes real money.
