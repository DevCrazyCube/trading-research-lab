# Pump sniper V3 — clean executable-return forward cohort

Frozen before the first V3 paper entry at `2026-08-27T10:21:23Z`.

## Status and purpose

V3 is **PAPER ONLY**: no wallet, signer, key, order, transfer, or on-chain write. Legacy ledgers remain
unchanged. V2 remains an engineering shakeout: its append-only events exposed that ordinary websocket
reconnects rebuilt the in-memory book and therefore created many `INVALID_RESTART_GAP` outcomes during
deployment. Those outcomes are retained and stressed; they are not copied into V3.

V3 asks one forward question: does Pump.fun surge-following have positive executable expectancy after
all pinned costs and missing-exit penalties, when ordinary stream reconnects preserve the paper book?
No result from legacy or V2 is a V3 observation.

## Frozen scope and entry

- Pump.fun bonding-curve venue only (`Pumpfun`, normalized to `pumpfun`). Missing/other venue: no trade.
- Same real-time trade stream and frozen surge detectors:
  - `v3_core_bal`: BALANCED surge entry + `convex_core` exits.
  - `v3_core_confirm`: five-second follow-through entry + the same `convex_core` exits.
  - `v3_core_ratchet`: BALANCED entry + `convex_ratchet` breakeven ratchet.
- Three arms are parallel experiments, not positions to sum into one portfolio.
- Initial paper equity **$1,000 per arm**; base order **2% of current equity**; inverse-surge-vol scale
  bounded to 0.5×–1.5×; minimum $2; maximum 25 positions and 50% gross exposure.
- A loss changes current paper equity and therefore all later sizes. Equity is restored from the
  append-only terminal stress ledger after a true process restart.

## Frozen exits and execution

- No capped profit target. Wide 35% peak give-back, five consecutive seconds below 45% buy volume after
  20 seconds, −60% catastrophe trigger, 30-minute hard horizon. Ratchet arm additionally protects
  breakeven after a +30% peak.
- A completed bar through a trigger uses the worse observed positive close, not a guaranteed trigger fill.
- A silent token at the horizon has no executable quote and receives zero recovery for adjudication.
- Per-side toll: Pump.fun **125 bps** as already pinned by this repository. Paper slippage is the worse of
  a 25 bp floor and `130*sqrt(order USD / one-second USD flow)` bp, capped at 5,000 bp.
- Fixed priority-fee estimate: **0.00025 SOL per side at $150/SOL**. It is charged in net R.

## Frozen evidence lifecycle

- Entry event is fsync-appended immediately with full signal, intent, fill, strategy config, equity,
  executor assumptions, canonical freeze payload, config hash, experiment hash, and UTC.
- Normal provider reconnect preserves in-memory positions, peak and flow streak; it does **not** create a
  restart outcome.
- A true OS-process restart cannot reconstruct the path since the last event. Every unresolved entry is
  terminal `INVALID_RESTART_GAP`, valued at −100% plus frozen toll/tips, and restored equity includes it.
- A stale horizon mark is non-executable and receives the same full-loss stress bound.
- No row is deleted, rewritten, or moved. Duplicate terminal records and hash failures are hard errors.

## Frozen adjudication

Primary result per arm: full-loss-stress paper equity and mean R over every terminal entry. Also report
priced mean R, median, sum, restart invalidations, stale marks, and commitment failures. Fewer than
**100 terminal entries per arm** is behavior only. At/after 100, an arm is eligible for further review
only if stress mean R > 0, stress equity > $1,000, no commitment failures, and no unresolved accounting
gap. This paper gate does not authorize live trading; `PLAN.md` promotion gates and explicit owner
authorization still apply.
