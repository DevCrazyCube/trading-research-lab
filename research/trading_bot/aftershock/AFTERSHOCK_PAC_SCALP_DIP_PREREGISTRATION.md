# AFTERSHOCK PAC SCALP · DIP — anti-exhaustion "buy-the-reclaim" entry arm

**Status:** PREREGISTERED PAPER-SCENARIO INSTRUMENT — NOT A PROFIT CLAIM, NO WALLET, NO ORDERS.

**Preregistered UTC:** 2026-08-31. A separate ledger; inherits no PAC performance. It reuses V2.4's
already-anchored processed-inclusion executor calibration (send/sign/land path byte-unchanged; strategy
results and activation watermark are NOT inherited), so latency modelling is matched against the
momentum arm and the EARLY arm.

## Why this exists

The forensic on 322 real forward paper trades (2026-08-31) of the momentum arm proved the loss is an
ENTRY problem, not an exit problem: the convex EXIT works (EXIT_TRAIL n=27, +19.85% avg, 0 unexitable),
but the momentum gate systematically buys EXHAUSTION — 82% of fills went straight down and the median
LOSER's peak intra-trade gain was −494 bps (never green). On lagged free data the momentum signal only
becomes visible after the vertical move, so we enter as exit liquidity. No decision-time feature
separated winners from losers (buyer_breadth weak, curve-position null; the one positive filter cell was
19-trade swept-optimum overfit noise). This arm tests the one untested, principled lever: change the
ENTRY so it does not buy the spike.

## Frozen design (set-once)

- **Same engine, same exit.** The audited single-position fill/resolve/PumpSwap-exit/ATA-reclaim core
  and the multi-position book (N_MAX=4, 0.80 SOL gross cap, 90 s re-entry cooldown, correlated-dump
  breaker) and the convex exit policy (HORIZON > HARD_STOP −6% > CAPACITY > LET_RUN trail) are reused
  BYTE-FOR-BYTE from the momentum arm via `pac_scalp_arm_runner` rebinding only the entry detector, so
  this is a clean matched comparison — only the entry differs.
- **Entry = dip-reclaim (`pac_scalp_detector_dip`), causal, no lookahead.** Over a 12 s window a free
  slot admits a mint iff: (1) a local PEAK in curve SOL reserve forms earlier in the window; (2) a
  PULLBACK ≥ 800 bps drains the reserve off that peak (weak hands flushed); (3) a RECLAIM — the current
  reserve has recovered ≥ 30% of the peak→trough range on RENEWED buying (buy>sell + ≥3 distinct buyers
  strictly AFTER the trough) while STILL BELOW the peak (buying the reclaim, never a fresh high — a new
  high would be momentum/exhaustion again); (4) live-bid floor: reserve ≥ 6× our notional. Makes no
  winner/loser prediction; it just refuses the vertical spike and buys the shakeout-reclaim instead.
- **Measurement.** Per-arm hash-chained scenario ledger and continuous intra-trade mark logger, identical
  to the momentum arm, so the three arms are compared on identical honest accounting.

## Honest status

Pre-committed expectation is UNCERTAIN, not positive: the forensic showed the available free features do
not separate winners from losers, so an anti-exhaustion entry has a real chance of also being EV-negative.
This instrument exists to MEASURE that forward honestly against the momentum control — not as a proven
profit engine. Kill criterion: one week red with no separation from the momentum arm.
