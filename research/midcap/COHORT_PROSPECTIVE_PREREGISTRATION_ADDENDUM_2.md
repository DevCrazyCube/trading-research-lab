# Addendum 2 — coincidence cells (from Grok's refinement of item 12), frozen 2026-09-09T16:38:32Z

Applies to events with avail_ns >= the timestamp above (watcher v2 DB). Nothing is removed from the original rule or Addendum 1.

## Positioning event (extends "buy")
A roster wallet is POSITIONED in mint m when its raw token delta > 0 in a transaction, whether paid (USDC <= -1.0 or SOL <= -0.001)
or an inbound TRANSFER with no quote leg (the STONK allocation pattern). Buy-only and position (buy+transfer) are separate cells.

## Coincidence cluster
C(K, W, N): K distinct roster wallets of one arm are positioned in m, the K-th within W minutes of the first, and m's oldest pair
is <= N hours old at the K-th event (no pair yet = "pre-pool", age 0, flagged). Cells: K in {2,3} x W in {30,90} min x N in {2,6} h
x {buy-only, position} = 16 cells per arm. Signal time = avail_ns of the K-th event.

## Entry, exits, toll
Paper entry at the OPEN of the first bar strictly after the signal time (1-min bars if pool < 3 d old, else hourly; pre-pool signals
enter at the first bar of the first pool that appears, flagged). Exits: fixed +6 h, +24 h, +72 h, +7 d. Toll: 2.48% round trip
if the mint has no AMM pool at entry (curve), else 1.14% (sensitivity 2.5%). Dropouts -30/-50/-100% with resolution rate.

## Pass (unchanged + Bonferroni over 4 original + 16 coincidence = 20 cells)
Board mean > 0 with CI-low > 0 (Bonferroni 0.05/20), board median at 72 h > 0, board beats control by more than the CI half-width,
>= 2 disjoint entry weeks, >= 25 board events in the cell. Sensitivity (not pass/fail): controls re-weighted to match the board
arm's trade-count distribution during the epoch.

## Explicitly NOT adopted
Any use of the 14-day pre-freeze history of the current leaderboard as validation (roster lookahead). Roster refinement by
"prior cluster appearances" is deferred to a roster v2 frozen from a LATER 30-day leaderboard, never applied retroactively.
