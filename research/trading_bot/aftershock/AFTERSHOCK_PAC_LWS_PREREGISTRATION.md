# AFTERSHOCK PAC LWS — Launch-Window Sentinel Scalper (veto arm)

**Status:** PREREGISTERED PAPER-SCENARIO INSTRUMENT — NOT A PROFIT CLAIM, NO WALLET, NO ORDERS, NO SIGNER.

**Preregistered UTC:** 2026-09-01. A separate ledger; inherits no PAC performance. Reuses V2.4's
already-anchored processed-inclusion executor calibration (send/sign/land path byte-unchanged;
strategy results and activation watermark are NOT inherited), so latency modelling is matched against
the NULL control arm.

## Why this exists — a measurement instrument, not a money-maker

An exhaustive research programme established: the momentum scalp loses because it buys mid-life
EXHAUSTION (82% of fills go straight down), and its feed observes tokens mid-life — for ~96% of mints
the first captured trade is already ~0.88× fresh reserves, so the first-60-slot buyer set that the ONE
leakage-audited finding (B20B) needs was MISSED (B20B saved only +0.22 SOL live for that reason). This
instrument opens the launch window: a creation-anchored feed captures each mint from its CREATE event
at t0, restoring the [t0, t0+60] window (measured coverage 68.6% vs ~4% mid-life), making B20B
OPERATIONAL live for the first time.

**Honest scope.** B20B is loss-AVOIDANCE, not an edge — its own text: "screening out dead tokens does
not make the surviving ones profitable." The book is expected to remain materially negative; the
headline question this rig answers is the POPULATION one: does the fresh-mint (t0+60) population trade
better (fatter trail tail, smaller hard-stop bleed, fewer atomic unexitable rugs) than the mid-life
exhaustion population — measured by this arm minus the matched NULL arm.

## Frozen design (set-once)

- **Creation-anchored feed** (`pac_lws_feed`): one processed `logsSubscribe` on the pump program,
  dual create+trade decode, seeded from the CreateEvent `real_token` so the first trade reconciles to
  t0; fail-closed on unreconciled/unanchored mints; the feed thread never awaits an RPC.
- **Deadness veto** (`pac_lws_screen`, veto_enabled=TRUE): the validated B20B rule — at t0+60 slots, if
  the single largest buyer holds ≥ 0.95 of all tokens bought so far → refuse entry. Byte-identical to
  the leakage-audited `b20b.score` (60/95/2 asserted at import). Footprint filters (dev-share,
  same-slot bundle) are computed SHADOW-only, never gating. No lookahead: the feature reads only
  [t0, t0+60]; the entry is strictly after the window closes.
- **Admission = coverage clause-4 only:** `real_quote ≥ 6 × notional` (a live-bid exit-impact floor).
  NOT the momentum clauses (net inflow / buy>sell / ≥3 buyers = the exhaustion top). Enter the
  surviving fresh-mint population, not a momentum signal. Full `ReserveState` is reconstructed from the
  feed's `real_token` via the pinned bonding-curve constants (exact at t0 by construction).
- **Convex exit + audited core reused byte-identically** (`pac_scalp_policy.decide` +
  `pac_v2_runner` fill/resolve/PumpSwap-exit/ATA-reclaim): fill at decision + inherited processed-p90,
  priced at the snapshot observed THEN — lookahead-free. Multi-position book N_MAX=4, gross cap
  0.80 SOL, per-mint re-entry cooldown, correlated-dump breaker.
- **Measurement:** hash-chained scenario ledger + continuous mark logger, matched to the NULL arm.

## Honest status

Pre-committed expectation: the book stays materially negative; the veto avoids a class of guaranteed
losses (the atomic unexitable / high-concentration rugs) but rescues no trade and creates no edge. The
number worth waiting for is the NULL-arm fresh-population book and the LWS−NULL veto margin. The B20B
window-2 one-shot OOS read is the stronger confirm and is read alongside, not ahead of, this forward
paper run. Kill criterion: one week with no separation from the NULL control.
