# Pre-registration: replicate the persistent late-entry winners' rule (v3 tape)

Frozen 2026-09-09 by Claude before any rule-based return was computed. NO_TRADE, paper only.

## Origin (measured, not hypothesised)
Per-wallet REALIZED P&L on the v3 tape (1.16M trades, 62,789 wallets): the top decile by first-half profit made
+1,600 SOL in half 1 and +1,494 SOL in half 2 (151/194 still profitable). 108 of those 194 enter >50 slots after
creation ("LATE"); +777 / +438 SOL, 79/108 profitable in half 2. Bot-farm check: median Jaccard of traded mints 0.015.
Their 4,676 buys (top 40) sit in this box (q25-q75): age 43-538 s, curve progress 12-41%, distinct buyers last 60 s
15-95, SOL bought last 10 s 0.95-9.6, price vs 60 s ago 0.96-1.24, size 0.01-1 SOL. Their 3,337 sells: hold 8-200 s
(median 37), exit at 0.67-0.95 of peak-since-entry (median 0.86), 50% into buy-flow.

## Rule (fixed; parameters are the winners' q25/median, no search)
ENTRY trigger, evaluated at every trade of an in-window mint (one open position per mint, max 3 entries per mint):
  age 40-600 s AND progress 12-45% of 85 SOL AND distinct buyers last 60 s >= 15 AND SOL bought last 10 s >= 1.0
  AND price/price_60s_ago >= 0.95.
Fill: first trade whose receipt time >= trigger + L seconds (L = latency), on that trade's post-state; size 0.2 SOL;
exact constant-product fill; fees = recorded bps (1.25%/side); +105,000 lamports per transaction.
EXIT trigger (whichever first, checked at every trade after fill): (a) elapsed >= 37 s AND SOL sold last 10 s >
SOL bought last 10 s; (b) price <= 0.85 x peak since fill; (c) elapsed >= 200 s; (d) curve complete.
Sell at first trade >= trigger + L, exact fill. Unexitable (no trade after exit trigger) charged -100% (also -50%).

## Cells
Primary (pre-declared, single holdout read): L = 2 s. Sensitivity (exploration only): L = 0, 5, 13 s.
Placebo: identical exit rule; entry at random trades matched on the same age and progress bins WITHOUT the flow
conditions (buyers/SOL-in/price) — isolates whether flow carries the edge.

## Split, metrics, pass
Chronological by create slot, 60% exploration / 40% holdout. Mint-equal mean AND median net return per position,
win rate, positions, total SOL P&L of the bot over the window at 0.2 SOL; 95% CI cluster-bootstrapped by creator
and by 30-min session (wider wins). PASS = holdout mint-equal mean > 0 with CI-low > 0 at L = 2 s AND placebo
mean < rule mean by more than the CI half-width. Prediction, written first: the rule is positive at L = 0-2 s and
decays toward zero or negative by L = 13 s; the placebo is negative.
