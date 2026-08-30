# AFTERSHOCK PAC V2.2 — full-run evaluation (falsification of Pump-only exit)

Date: 2026-08-30. Paper-scenario only. This is a post-hoc evaluation of the frozen V2.2
seal `9f96201967587828152dd323f10f66415142be8f3414a239f1af9eade26e85d9`. No retrospective
price repair; every number is reconstructed from the durably-appended scenario ledger
`AFTERSHOCK_PAC_V22_SCENARIO_LEDGER.jsonl`.

## Why V2.2 was stopped

The owner observed a mint that had visibly dumped on Pump.fun yet stayed `OPEN` in the
runner. Root cause (confirmed, not a dashboard lag): **V2.2 computes every exit quote from
the last-received pump.fun bonding-curve reserve state only** (`pac_v2_runner._service_position`
→ `feasibility.kernel_accounting` on `position.last_state`). When a mint **graduates**
(`complete == true`, liquidity migrates to the PumpSwap AMM), the bonding-curve account stops
updating. The runner is then blind to the real post-migration market and cannot see the dump.

Two distinct graduation failure modes, both wrong:
1. **Frozen-curve** — the bonding-curve account is still readable with stale reserves, so
   `kernel_accounting` returns a *stale positive* quote that never moves. The trail can never
   trigger; the position holds until the 12-minute horizon and would book a **fictional
   frozen price**. (This is the still-open position `FSQgP6a26KF…`.)
2. **Zeroed/refused-curve** — the account is closed/withdrawn, the quote is unavailable, and
   the policy writes the position off as `UNEXITABLE_FULL_LOSS` (−100%) even though a live
   PumpSwap market exists where the token could actually be sold. (This is `2AaMD4p6HbA…`.)

## Full run — 18 filled positions, 17 resolved, 1 stuck open

| Metric | Value |
|---|---|
| Entries filled | 18 |
| Resolved | 17 |
| Stuck OPEN (migration-frozen) | 1 (`FSQgP6a26KFEDrpsJJfSLnkWiy59ScKY2EChEGU9pump`) |
| Wins / Losses | 7 / 10 |
| Full losses (≤ −99%) | 1 (`2AaMD4p6HbA…`, EXIT_HORIZON → `EXIT_SNAPSHOT_PERMANENT_REFUSAL`) |
| Mean R (all-cost) | **−0.083** |
| Median R | −0.086 |
| Range | −1.00 … +0.33 |
| Exit paths | 15× TRAIL, 1× CAPACITY, 1× HORIZON(full-loss) |

Note on the "capital index 0.0000": a serially-compounded index collapses to zero because one
−100% appears at full position size. With the actual fixed independent ~0.098-SOL sizing the
honest aggregate is the **arithmetic mean R = −0.083 per position**, not a wipeout.

## What the data proves

- The trail itself works **on the bonding curve** (15 of 17 exits are clean TRAIL fills). The
  entry/snapshot/latency machinery is sound.
- The **only** structural hole is graduation/migration. **2 of 18 positions (~11%) were
  migration casualties, and each is catastrophic** (−100% or frozen-forever). This is exactly
  the loss-tail signature that is the honest decider for this strategy — small capped wins
  (max +0.33), rare uncapped losses — not the win rate.
- n = 17 ≪ the frozen 100-resolved decision boundary, so **no profitability verdict**. This
  run is a *falsification of the Pump-only exit design*, not a verdict on the entry edge.

## Successor requirement (V2.3)

Exits must become **venue-aware**. On `complete == true`, stop trusting the bonding curve and
quote the honest sell on the **PumpSwap AMM pool** (`pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`):
discover the pool for the mint, read the real base/quote vault reserves, price a constant-product
sell (net of lp+protocol+creator fees), and drive the same trail/capacity/horizon policy from
that quote. Bounded "pool not yet observable" → HOLD within a window; **no provable sale route
at the bound/horizon → honest `UNEXITABLE_FULL_LOSS`**. No fictional frozen-curve prices, ever.
