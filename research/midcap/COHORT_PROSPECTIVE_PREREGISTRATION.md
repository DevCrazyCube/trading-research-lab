# Pre-registration: prospective board-cohort early-entry test (frozen 30/30 roster)

Frozen 2026-09-09 ~16:05 UTC by Claude, BEFORE any post-freeze event has a resolved 24 h outcome. NO_TRADE, paper only.
Roster: Codex's `fomo_private/cohort_roster_v1_20260909/roster.json` (30 board / 30 control, SHA256-sampled, freeze
2026-09-09 15:20:14.748 UTC, manifest 6f572e35...). Watcher: `scripts/trading_bot/memebot/cohort_watch.py`
(3-min polls, local receipt ns, raw tx retained, fee-payer-correct SOL delta, USDC delta, first-sight pair age/mcap/liq).

## Why prospective
Today's leaderboard replayed on its own past is roster lookahead (COHORT_EVIDENCE_AUDIT_20260909 §1). Only events whose
receipt time is AFTER the freeze count. Nothing observed before 15:20:14 UTC is ever admitted.

## Event (fixed)
A wallet BUY = raw token delta > 0 for a non-quote mint AND (usdc_delta <= -1.0 OR sol_lamports <= -1,000,000) in the same
transaction (candidate label; protocol-level authentication is a later upgrade applied identically to both arms).
Cluster event E(k,N): the k-th DISTINCT wallet of one arm buys mint m, and the mint's oldest pair was created <= N hours
before that buy's receipt time. Cells: k in {2,3}, N in {2,24}. One event per (arm, mint, k, N): the first.
Both arms are evaluated with the identical definition. Arms are equal-sized by construction.

## Entry, exit, costs (fixed; no post-hoc exits)
Paper entry at the OPEN of the first GeckoTerminal bar strictly after the event receipt time (minute bars if the pool is
< 3 days old, else hour). Size 0.05 SOL-equivalent notional (chart marks, not fills). Round-trip toll 1.14% applied once;
sensitivity 2.5%. Exits are fixed horizons only: +6 h, +24 h, +72 h (open of the first bar at/after the horizon). Dropouts
(no bar within tolerance) charged -30 / -50 / -100 %, all three reported with the resolution rate. No trailing stop, no
ladder, no discretionary exit may be added on this cohort.

## Metrics
Mint-equal mean AND median net return per cell and horizon; win rate; P(max mcap after event >= $500k) and (>= $10M);
95% CI cluster-bootstrapped by mint and by 6-hour receipt session (wider wins). Placebo = the control arm.

## Pass (all required)  — read weekly, never early
1. board 24 h and 72 h mint-equal mean net return > 0 with CI-low > 0 at 1.14% toll;
2. board mean exceeds control mean by more than the CI half-width, AND board median >= control median;
3. holds in >= 2 disjoint calendar weeks of post-freeze events;
4. at least 25 board events in the cell (otherwise the read is "insufficient", not a fail or pass).
Prediction, written first: the board arm shows more early clusters than controls (they are more active), but mean net
return after toll is not distinguishable from the control arm at 24-72 h. If instead criteria 1-4 pass, the next step is a
paper forward bot on the SAME rule for one further untouched week, then an owner decision — not live trading.

## What this cannot show
Control wallets are random active tape wallets, not activity- or funding-matched; distinct addresses may be one entity;
the leaderboard is a vendor mapping; chart marks are not fills; one roster, one season.
