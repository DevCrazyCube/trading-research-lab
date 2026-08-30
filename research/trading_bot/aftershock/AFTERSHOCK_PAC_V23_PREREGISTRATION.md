# AFTERSHOCK PAC V2.3 — cross-venue (PumpSwap) exit repair

**Status:** PREREGISTERED ENGINEERING SUCCESSOR — NOT SEALED, NOT CALIBRATED, NOT ACTIVE.

**Preregistered UTC:** 2026-08-30. This successor changes the EXIT observation only. It does not change
PAC V2.2's low-lag feed, PAC V2.1's entry formula, USD 10 probe, processed-p90 requirement, buyer
threshold, reserve cover, slippage, calibration machinery, discovery gate, or paper-only boundary.

## Defect and burned boundary

Frozen V2.2 (seal `9f96201967587828152dd323f10f66415142be8f3414a239f1af9eade26e85d9`) priced every exit from
the pump.fun bonding curve only. When a mint **graduates** — liquidity migrates to the PumpSwap AMM and
the bonding-curve account is zeroed/closed — the V2.2 feed goes permanently silent, the trailing-peak
exit freezes on a stale (fictional) curve price, and the position either holds to the 12-minute horizon
or is written off as an unexitable −100% even though a live, sellable PumpSwap market exists.

The V2.2 forward run (17 resolved positions, evidence `AFTERSHOCK_PAC_V22_SCENARIO_LEDGER.jsonl`, analysis
`AFTERSHOCK_PAC_V22_EVALUATION.md`) falsified the Pump-only exit: 2 of 18 filled positions were graduation
casualties — one booked a fabricated −100% full loss, one hung OPEN forever on a frozen price — each
catastrophic. All V2.2 observations are **BURNED FOR V2.3 PERFORMANCE**; nothing is migrated.

## Frozen exit repair (the only change)

1. **Active on-chain liveness probe.** An open position is re-observed on-chain on a bounded cadence
   (throttled ~2 s), independent of the feed, because the feed is not a reliable liveness signal — it goes
   silent exactly at graduation.
2. **Graduation is defined by observation, not belief.** A bonding curve that reads healthy (live,
   `complete == false`) refreshes the trail state as before. A curve that is `complete`, zeroed, closed or
   otherwise not tradeable escalates to a venue transition. The existence of a PumpSwap pool for the mint
   is the definitive graduation test.
3. **Honest cross-venue liquidation.** On graduation the position is liquidated on the PumpSwap AMM
   (`pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`) at a constant-product sell priced from the pool's REAL
   observed base/quote vault reserves and its live GlobalConfig fees (lp + protocol + creator bps), net of
   the same modeled per-transaction exit gas the entry paid. The pool, reserves and fees are read read-only
   from a public RPC; every raw exchange is durably appended before any economic interpretation. The
   modeled p90 landing latency still applies: decide now, resolve at now + p90 against a capture taken then.
4. **Bounded pool-availability window.** A freshly graduated pool that is not yet observable is a bounded
   HOLD, retried within a grace window (120 s) re-armed per graduation episode — a transient RPC failure or
   a momentary curve blip can never poison it into a premature liquidation.
5. **Honest unexitable full loss.** If no provable PumpSwap sale route exists by the grace window or the
   absolute 12-minute horizon, the position resolves as an unexitable full loss. No fabricated frozen-curve
   price is ever booked, in either direction.

The 2 s probe cadence and 120 s grace are engineering staleness/robustness bounds selected before any V2.3
forward performance. They are not alpha thresholds and may not be optimized on outcomes.

## Strategy and execution inheritance

Entry qualification, the V2.2 low-lag feed, the USD 10 probe, processed-p90 dwell, buyer breadth, reserve
cover, slippage, the 12-minute absolute horizon, the 12% trail, the 6× capacity multiple, full-position-only
sizing, the calibration/attestation machinery and the paper-only boundary are all inherited from V2.2/V2.1
unchanged. There is no wallet, signer, transaction builder or sender in the runner. The PumpSwap venue is
observed read-only for pricing; it is never traded against with real funds.

## Calibration and promotion

A fresh 100-sample processed-latency calibration campaign is required because the sealed closure changed
(the shared execution core plus the new PumpSwap module). The promotion gate is unchanged: 100 terminal
paper positions, positive mean all-cost return, capital index above 100, and it authorizes no real money.
