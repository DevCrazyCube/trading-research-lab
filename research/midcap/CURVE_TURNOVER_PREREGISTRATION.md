# Pre-registration: curve turnover at graduation -> post-migration return (DeepSeek round-3 Rank 2, restated)

Frozen 2026-09-09 ~20:15 UTC by Claude before any post-migration return was joined to turnover. Paper only.

## What the variable actually is
DeepSeek's "creator fee-revenue ratio" = sum(creator_fee on curve trades) / SOL raised. Creator fee is a fixed 0.30% of every
trade and every completion raises ~85 SOL, so the ratio is curve TURNOVER: total traded SOL per SOL of net inflow before
graduation. Its story (creators delaying migration) is wrong — completion is automatic at the 85th SOL — but turnover is an
unmeasured lifetime-of-curve variable: high = churned/washed, low = accumulated in few hands.

## Population, variable, split
The v3 tape's 341 in-window graduates with a PumpSwap pool and GeckoTerminal minute bars (same set as the LP test).
TURNOVER = (sum of buy SOL + sum of sell SOL on the curve) / real SOL at completion (from the last curve state's rsol, or 85 SOL).
Quartiles by TURNOVER within the exploration set; chronological split 60/40 by completion slot.

## Entry, exits, costs
Paper entry at the OPEN of the first minute bar strictly after pool creation; exits at +15 min and +60 min (next bar open);
toll 1.14% round trip; no bars = -100% (also -50%). Mint-equal mean AND median; CI by 30-min completion session.

## Cells and pass
Q1 (lowest turnover) vs Q4 (highest) at 15 and 60 min; placebo = quartiles from SHUFFLED turnover. Pre-declared primary cell:
Q1 at +60 min, single holdout read. PASS (DeepSeek's number, adopted): holdout Q1 mean >= +5% AND median >= 0% AND exceeds the
shuffled-placebo Q1 by more than the CI half-width. Prediction, written first: all quartiles deeply negative (the LP test's
hold returns were -60% at 90 min); Q4 (churned) worse than Q1, but Q1 not positive.
