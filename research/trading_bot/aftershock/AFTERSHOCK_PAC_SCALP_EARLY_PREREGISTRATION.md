# AFTERSHOCK PAC SCALP · EARLY — anti-exhaustion "buy-early-on-the-curve" entry arm

**Status:** PREREGISTERED PAPER-SCENARIO INSTRUMENT — NOT A PROFIT CLAIM, NO WALLET, NO ORDERS.

**Preregistered UTC:** 2026-08-31. A separate ledger; inherits no PAC performance. It reuses V2.4's
already-anchored processed-inclusion executor calibration (send/sign/land path byte-unchanged; strategy
results and activation watermark are NOT inherited), so latency modelling is matched against the
momentum arm and the DIP arm.

## Why this exists

The forensic on 322 real forward paper trades (2026-08-31) of the momentum arm proved the loss is an
ENTRY problem: the convex EXIT works, but the momentum gate buys EXHAUSTION (82% of fills go straight
down; median loser peaks at −494 bps, never green) because on lagged free data momentum is only visible
after the move. A telling fact from that run: the median momentum entry sat at ~20 SOL of curve reserve
— i.e. LATE, after the crowd. This arm tests the opposite entry: buy EARLY, while the reserve is still
low, before the visible spike, so there is runway left to run into the convex exit.

## Frozen design (set-once)

- **Same engine, same exit.** The audited core, multi-position book, and convex exit policy are reused
  BYTE-FOR-BYTE from the momentum arm via `pac_scalp_arm_runner`; only the entry detector differs, so
  this is a clean matched comparison.
- **Entry = early-curve accumulation (`pac_scalp_detector_early`), causal, no lookahead.** Over a 4 s
  window a free slot admits a mint iff: (1) current curve SOL reserve is inside the EARLY band
  [6× notional , 8 SOL] — high enough to fill our exit against, low enough to still be early (below the
  ~20 SOL late median); (2) net SOL inflow across the window and gross buy > gross sell (accumulation);
  (3) ≥3 distinct buyers arrive; (4) RUG-GUARD — reject if any single sell event drained > 1/4 of the
  current reserve (refuse curves already showing a whale-dump signature). Makes no winner/loser
  prediction; it buys fresh-launch accumulation before the crowd.
- **Measurement.** Per-arm hash-chained scenario ledger and continuous intra-trade mark logger, identical
  to the momentum arm.

## Honest status

Pre-committed expectation is UNCERTAIN, not positive: buying early trades exhaustion risk for higher rug
exposure, and the forensic showed curve-position alone did NOT separate winners from losers, so this can
also be EV-negative. It exists to MEASURE that forward honestly against the momentum control. Kill
criterion: one week red with no separation from the momentum arm.
