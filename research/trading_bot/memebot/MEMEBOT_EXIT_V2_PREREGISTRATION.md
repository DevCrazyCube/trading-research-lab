# MEMEBOT_EXIT_V2 — Pump-only executable-exit fast scalp

**Instrument:** `MEMEBOT_EXIT_V2` — a new, clean, forward **PAPER** experiment. It does not append to,
rename, or reinterpret `MEMEBOT_EXIT`; that ledger remains the evidence for the earlier trial.

**Why V2 exists (verified local-ledger facts at design time).** The all-trade audit found that every
priced PASS in the first EXIT ledger was outside Pump.fun, so that trial did not answer the repository's
initial Pump bonding-curve question. It also booked an unavailable exit at the −25% stop floor and stop
crossings at the exact stop, neither of which demonstrates an executable fill. V2 corrects those three
mechanical issues. This is a new trial, not evidence of an edge.

**HARD LIMITS:** paper only; no wallet, key, signer, order, transfer, paid execution endpoint, or on-chain
write. A live-trading promotion remains prohibited by `PLAN.md` without its gates and explicit owner
authorization.

## Frozen hypothesis

Within **Pump.fun bonding-curve launches only**, require proof that other wallets have already exited,
then leave on an eight-minute horizon before that exit path dries up. The hypothesis is falsified if its
full-loss-stressed paper bankroll fails to grow or its unavailable-exit rate is not lower than comparable
Pump-only observations. Missing prices are losses for adjudication, never missing observations.

## Frozen entry scope and screen

- Venue must equal `pump-fun`. Other venues are **out of scope** and enter neither PASS nor the control.
- FDV ≥ **$7,000**.
- USD reserve ≥ **$3,000**. The former $10,000 floor selected migrated/non-Pump pools; V2 uses the
  shared Pump-compatible floor and relies on the positive seller requirement for exitability.
- Unique buyers ≥ **10**.
- Buys per buyer ≤ **4.0**.
- If buys ≥ **15**, sellers must be nonzero.
- Demonstrated sellers ≥ **3**.
- Pool age ≤ **30 minutes**.
- Missing FDV, reserve, venue, or price means no entry.

The control is a deterministic sample of **in-scope Pump.fun** coins rejected by another screen rule.
An off-venue observation is a scope exclusion, not a losing control.

## Frozen paper execution

- Initial paper bankroll: **10 SOL**, fixed notional size **2%** (= 0.2 paper SOL); no martingale.
- Maximum six open positions, four PASS and three control entries per scan.
- Long only; target **+50%**, stop trigger **−25%**, toll **1.5% per side**.
- Hard horizon: **8 minutes**. Dead exit: after five minutes, at most one recent trade and price within
  ±8% of entry.
- A stop crossed inside a completed bar fills at the **worse positive observed close** when that close is
  below the trigger. The trigger is not treated as a guaranteed fill.
- At the horizon, no positive executable price is `UNEXITABLE_TIMEOUT` at **−100%** before toll. With the
  frozen stop risk unit this is `(-1.00 - 0.03) / 0.25 = -4.12R`.
- Every entry is appended with UTC and canonical SHA-256 before its outcome.

## Frozen adjudication

Primary portfolio metric: closed-PASS paper bankroll with `UNEXITABLE_TIMEOUT` at full loss. Also report
unavailable-exit rate, mean/median/sum R, and the in-scope control. `N_min = 30` terminal PASS trades
before a verdict. Kill if, at `n >= 30`, `mean_R + 1.645*SE < 0` on this already-stressed stream.

Frozen before first V2 entry at `2026-08-27T09:55:05Z`.
