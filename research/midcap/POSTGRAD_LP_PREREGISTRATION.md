# Pre-registration: post-graduation liquidity provision with a breadth screen (Grok round-3 #1 and #4)

Frozen 2026-09-09 by Claude before any LP return was computed. Paper only, NO_TRADE.

## Population
In-window graduates of the v3 tape (CompleteEvent, 369), joined to their PumpSwap pool via DexScreener and to GeckoTerminal
1-minute USD bars from pool creation. Venue reality: pump.fun migrates to PumpSwap, a constant-product AMM — there is NO
concentrated range; Grok's "+-8% range" is replaced by a plain CP LP share.

## Screen (from the curve phase, i.e. before the pool exists; no creator/leaderboard data)
ORGANIC = time-to-complete > 5 min AND >= 40 distinct curve buyers. PLACEBO arm = graduates failing the screen.

## LP simulation (fixed)
Enter at the OPEN of the first bar >= pool creation + 10 min (cell A) or at the first bar after a >= 20% drop from the
post-migration high inside the first 60 min (cell B, "pullback"). Position = 0.5% of the initial pool (approx 2 x 79 SOL at
migration); hold 45 or 90 min (A) / 60 min (B). Fee income = 0.20% of bar volume x share (LP fee assumption; protocol and
creator fees excluded). Impermanent loss = 2*sqrt(r)/(1+r) - 1 on the entry->exit price ratio. Exit costs = 1.14% round trip
on the token half + 2 x 105,000 lamports. No bars / pool gone = -100%. Also reported: -50% dropout.

## Metrics / pass
Mint-equal mean AND median net return on the LP position, win rate, fee and IL components, resolution rate; 95% CI by
30-min migration session. Chronological 60/40 split; single holdout read of cell A-90. PASS = holdout mean > 0 with CI-low > 0,
median > 0, beats the placebo arm by more than the CI half-width. Prediction, written first: fee income 1-4% per hour of
position; IL on first-hour paths of -50..-80% or +100..+400% dominates; both arms negative; ORGANIC less negative.
