# Solana mid-cap memecoin flow screen — PRE-REGISTRATION
Frozen 2026-09-03, BEFORE any snapshot is read. $0, paper, decision-support only.

## Origin
Owner is trading a live fomo.family terminal with ~$63 of size. Every prior kill in this repo on
post-graduation memecoins was a kill AT SIZE (capacity $153/clip in a median survivor). At $63 the
capacity objection does not bind; the toll and the loss tail still do.

## The hypothesis (from a read of HUGGY at $1M MC, +743%/1d)
A mid-cap memecoin late in its move shows THREE simultaneous tells:
 1. DECELERATION  - priceChange ladder collapsing (m5 << h1 << h6), move exhausting
 2. FLOW PARITY   - txn buy/sell counts approaching 1:1 at short horizons while price is off its high
                    (early buyers handing off one-for-one; genuine accumulation runs buy-skewed)
 3. SELL ROTATION - sells outnumbering buys at m5/h1 before they do at h6/h24
Claim: tokens scoring EARLY outperform tokens scoring LATE over the next 30m-6h, net of toll.

## Universe (fixed, no discretion)
chainId=solana; liquidity.usd >= $20,000; pairCreatedAt age >= 1h; enumerated from a FIXED query
list + token-boosts feed, deduped by pairAddress. Snapshot every 5 minutes, append-only.

## Signal (frozen definition)
  imb(w)   = (buys(w) - sells(w)) / (buys(w) + sells(w))          for w in m5,h1,h6,h24
  decel    = priceChange.m5*12 - priceChange.h1                   (per-hour accel, negative = fading)
  rotation = imb(m5) - imb(h6)                                    (negative = sells rotating in early)
  LATE score = -(decel_z) - (rotation_z) - (imb_h1_z)             higher = later in the move
Deciles by LATE score, formed on each snapshot, held to the horizon.

## Outcome
Forward log return of priceUsd at +30m, +2h, +6h from snapshot. Toll charged 3.0% round trip
(Solana memecoin measured toll). Benchmark = EQUAL-WEIGHTED MEAN of the same-snapshot universe.
NEVER the cross-sectional median (that control is not a holdable portfolio; it compounds to -100%
and cost this repo a 7pp artifact once already).

## Gates (in order, effect NOT read until gate 2 passes)
 GATE 1 coverage: >= 400 usable token-snapshots with a resolved +2h forward return.
 GATE 2 power:    MDE computed from realized residual sd, clustered by snapshot timestamp, ICC 0.3,
                  BEFORE any effect is read. Family must be adequately powered or it is not read.
 GATE 3 effect:   decile-spread (early minus late) mean, 5000-draw cluster bootstrap by snapshot.
 GATE 4 economics: spread must exceed the 3.0% round-trip toll to be tradeable at all.

## PASS condition (frozen)
Early-decile minus late-decile, market-controlled, CI-lower > 0 AND point estimate > 3.0% at the
+2h horizon. Anything less = the screen is decision-support at best, never a buy signal.

## Declared kill-risks
 1. The whole spread is toll-sized or smaller -> untradeable at any size. MOST LIKELY OUTCOME.
 2. txn COUNT imbalance is a poor proxy for VOLUME imbalance (the API gives counts only; the
    owner's terminal shows volume). A count-based null does not falsify the volume version.
 3. Survivorship: DexScreener drops dead pairs. Tokens that go unexitable may silently leave the
    panel, biasing forward returns UP. Must be measured by tracking disappearance explicitly.
 4. 5-minute snapshots of a 60-second market may be far too slow to act on.
