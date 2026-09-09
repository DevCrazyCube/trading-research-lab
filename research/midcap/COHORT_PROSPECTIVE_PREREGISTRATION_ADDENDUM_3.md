# Addendum 3 — pre-listing allocation cells (DeepSeek's "PSMAT"), frozen 2026-09-09T19:59:17Z

Applies to events with avail_ns >= the timestamp above (watcher v2 + follower-wave DBs). Nothing earlier is removed.

DeepSeek's Rank-1 mechanism is the pre-pool TRANSFER positioning already defined in Addendum 2 (a roster wallet's raw token delta
> 0 with no quote leg, on a mint with no pair yet), with one genuine addition: a 7-DAY coincidence window instead of 30/90 min.

## Cells added (per arm; identical definition for board and control)
P(K, 7d): K in {2,3} distinct roster wallets receive a transfer of the same mint (>= 0.01% of supply where supply is known,
else any nonzero amount) within 7 days, while the mint has NO tradable pair at the time of the K-th transfer. Signal time =
avail_ns of the K-th transfer. Entry = OPEN of the first 1-min bar strictly after the FIRST observed trade on any venue after
the signal (the listing), flagged PRE-POOL. Exits: +72 h and +7 d after entry. Toll by venue at entry. Dropouts -30/-50/-100.
Also reported: time from K-th transfer to listing, and the share of signals that never list within 14 days (charged as
unresolved, not dropped).

## Pass (unchanged form; Bonferroni now over 4 + 16 + 4 = 24 cells)
Board mean > 0 with CI-low > 0 (alpha 0.05/24), board 72 h median > 0, board beats control by more than the CI half-width,
>= 2 disjoint entry weeks, >= 25 board events in the cell. Prediction, written first: pre-listing transfers to the 30 board
wallets will be rare (single digits per week), so this cell will read "insufficient" on 2026-09-26 and needs a longer
accrual or a larger roster v2 (frozen later from a 30-day board, never applied backwards).

## Rejected from the same answer
DeepSeek's mechanical premise for killing curve-completion entries — a ~35% price drop at migration because "the AMM gets
only real SOL" — is wrong: pump.fun deposits the 206.9M reserved tokens (1e9 supply minus 793.1M sellable) with the ~85 SOL,
so the completion price (115 SOL / 279.9M virtual tokens) equals the pool price (85 SOL / 206.9M tokens); ratio 1.000 by
construction. Graduation timing is dead for measured reasons (see the audit), not for that one.
