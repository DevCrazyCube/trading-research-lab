# AFTERSHOCK PAC SCALP — multi-position momentum-convexity scalper (measurement instrument)

**Status:** PREREGISTERED PAPER-SCENARIO INSTRUMENT — NOT A PROFIT CLAIM, NO WALLET, NO ORDERS.

**Preregistered UTC:** 2026-08-31. A separate ledger; inherits no PAC V1–V2.6 performance. It reuses
V2.4's already-anchored processed-inclusion executor calibration (send/sign/land path byte-unchanged;
strategy results and activation watermark are NOT inherited).

## Why this exists (and its honest status)

A deep cross-version analysis proved the PAC "shock-absorption" entry has NO directional edge (no
decision-time feature separates winners from losers; every AUC ~0.5), so more entry/threshold variants
are futile. The owner's actual goal is not an edge-hunt: grab money often, scale the book, exploit the
rugs and runners — i.e. harvest CONVEXITY, not prediction. The pooled book has a genuinely fat runner
tail (realized winners to +304%/+318%, which the old 12% trail CAPPED) and cappable losers.

An adversarial design workflow then FALSIFIED the naive convexity math: "a −8% stop → break-even" is a
LOOKAHEAD artifact (it caps each trade by its FINAL realized R; a real path-triggered stop fires blind
and also scratches proto-runners that dip first), and ~5% of trades are ATOMIC unexitable rugs (dev
drains all reserve inside the landing window — no bid, no stop escapes). Honest expected book on
current evidence is NEGATIVE (≈ −0.03 to −0.07 mean R). The result hinges on ONE parameter the existing
ledgers cannot supply — the fraction of rugs a proactive stop catches BEFORE the mint goes unexitable
(break-even needs ~70%). **This instrument is built to MEASURE that forward, honestly — not as a proven
profit engine.**

## Frozen design

- **Architecture:** a MULTI-POSITION book (up to N_MAX = 4 concurrent slots) fanning the audited
  single-position PAC honest core out over `open_positions`/`pending_orders`; the per-slot fill, resolve,
  cross-venue PumpSwap exit and ATA-rent reclaim are reused verbatim, so every fill still lands at the
  modeled target (decision + inherited processed-p90 = 3.788s) and is priced at the snapshot observed
  THEN — lookahead-free by construction.
- **Entry (observable gate, not an edge):** over a 4-second window a free slot admits a mint iff its
  curve SOL reserve is strictly rising, buy volume > sell volume, ≥3 distinct buyers arrive, and the
  reserve is ≥ 6× our notional (a live bid to fill the stop against). Deduped per mint, 90s re-entry
  cooldown. Makes no winner/loser prediction; it just puts slots on live momentum, often.
- **Convex exit (the engine):** absolute ordering HORIZON > HARD_STOP > CAPACITY > LET_RUN_TRAIL.
  A tight entry-relative HARD STOP at −6% floors every loser small and fast (turning gradual rugs into
  small capped losses); an unproven position has ONLY that stop (no winner-capping trail); once PROVEN
  (peak net ≥ +12%) a WIDE, widening peak-trail rides the fat tail (peak [12,50)%→18% trail, [50,150)%
  →25%, ≥150%→35%). Backstops: capacity, 12-minute absolute horizon, PumpSwap venue transition, honest
  unexitable full loss when no bid exists.
- **Portfolio caps:** 0.10-SOL paper clip per slot, ≤ 0.80 SOL gross deployed, one clip per mint, and a
  correlated-dump breaker (≥50% of open slots hard-stopping within 30s halts new entries 5 min).
- **Measurement instrument:** a continuous mark logger records every observed intra-trade net-exit quote
  (priceable or not) for every open slot, so the rug-catch fraction and proto-runner early-dip rate can
  be measured from forward honest data instead of assumed by lookahead.

## Gate

PAPER scenario only — read-only pricing, no wallet/signer/order path. No profit is claimed; the
scenario ledger + mark log are the only arbiters. The convexity is unproven and the honest current-
evidence expectation is negative; the instrument runs to settle it, and if the forward hinge is
unfavorable the honest conclusion is to stop, with evidence.
