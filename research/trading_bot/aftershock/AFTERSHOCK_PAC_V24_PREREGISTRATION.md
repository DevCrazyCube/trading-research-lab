# AFTERSHOCK PAC V2.4 — honest toll (reclaimed ATA rent)

**Status:** PREREGISTERED ENGINEERING SUCCESSOR — NOT SEALED, NOT CALIBRATED, NOT ACTIVE.

**Preregistered UTC:** 2026-08-31. This successor changes the RESOLVE ACCOUNTING only. It does not
change PAC V2.3's cross-venue exit, PAC V2.2's low-lag feed, PAC V2.1's entry formula, the USD 10
probe, the processed-p90 requirement, the trail/horizon/capacity policy, or the paper-only boundary.

## Motivation

A deep cross-version loss analysis (V1 n=525, V2.2 n=17, V2.3 n=24) established, with adversarial
verification, that: (a) the exit rework is real but at its ceiling — mean R improved monotonically
(V1 −0.126 → V2.2 −0.083 → V2.3 −0.06→−0.03 as it grew) and the catastrophic full-loss tail went
28 → 1 → 0; (b) the dominant loss mode is a modest adverse price FADE (5–25% drift, ~87% of losers)
that no entry filter, scale-out, or exit refinement can remove — entry features do not separate
winners from losers (every candidate AUC within 0.14 of 0.5), and a scale-out is mathematically
impossible to fire on losers under the 12% trail; (c) the single honest, non-lookahead, non-overfit
improvement is TOLL REDUCTION, specifically reclaiming the ATA rent, which is ~45% of the round-trip
toll and the largest reducible cost.

## Frozen change (the only change)

Opening a pump.fun position creates an associated token account (ATA) with a **refundable**
rent-exemption deposit of 2,039,280 lamports (~2.1% of a ~0.098-SOL entry). V2.1–V2.3 charged this
deposit as a permanent sunk cost (`CHARGED_NOT_RECLAIMED_WITHOUT_OBSERVED_CLOSE`), which understates
every trade — a real bot closes the emptied token account after a full exit and recovers the deposit.

V2.4 reclaims it, and only where it is provably realizable:
1. On a **confirmed full-position exit** (bonding-curve `SCENARIO_ACCOUNT_SNAPSHOT_FILLED` or PumpSwap
   `PUMPSWAP_POOL_SNAPSHOT_FILLED` — both an `EXACT_TOKEN_SELL` of the entire position with net > 0),
   the token balance is exactly zero, so SPL-Token `CloseAccount` is a deterministic, always-available
   action that refunds the exact rent. `net_return_num` adds back `ata_rent − ATA_CLOSE_GAS_LAMPORTS`
   (5,000 lamports, one conservative closeAccount signature fee; bundling into the sell would make it
   zero marginal), labelled `RECLAIMED_ON_CONFIRMED_FULL_EXIT_NET_CLOSE_GAS`.
2. On an **unexitable full loss** the ATA still holds unsold tokens, so `CloseAccount` is invalid; the
   rent stays **charged** (unchanged). This asymmetry is deliberate and conservative — it never makes
   the worst-case/unexitable outcomes (the metric that matters) rosier than reality.

There is no lookahead: the refund is a fixed constant known at entry, realized by a deterministic
protocol action, not an observed price. Entry accounting is unchanged; the denominator still includes
the rent. Verified honest by a 3-lens adversarial audit (realizability / lookahead-timing /
consistency-scope, all CLEAN).

## Honest expected effect and the standing verdict

Reclaiming the rent lifts mean R by ~+0.02 uniformly (V2.3's live sample moves from ≈ −0.033 toward
≈ −0.013). **The strategy remains net-negative** on the honest sample; this is a measurement-realism
correction, not an edge. The analysis is decisive that the FADE loss is structural and unbeatable on
free data. A fresh 100-sample latency calibration is required because the sealed closure changed. The
promotion gate is unchanged (100 terminal positions, positive mean all-cost return, capital index
above 100, authorizes no real money) — and on the evidence to date it is not met.
