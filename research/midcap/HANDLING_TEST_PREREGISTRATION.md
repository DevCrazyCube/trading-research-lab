# Pre-registration: "Handling, not picking" on the survivorship-free tape

Author: Claude. Frozen 2026-09-09 UTC, BEFORE `research/midcap/tape_v3.sqlite` finished decoding
and before any per-mint outcome was inspected. Status: NO_TRADE, paper-only.

## Why this test and not another picker

Every measurement in this repository says coin *selection* on free data is impounded by
create_slot+1 (audit 2026-09-08: 36 of 82 winners complete before a bot can act; 0 buyable at
<=1.05x; every m60 bin negative on hold). The one live finding that is not a picking claim:
the owner's real fills separate winners from losers by **exit count, not size** (Solana ledger,
per-owner attribution: winners 2.50 sells/position vs losers 1.27; FOMO window: 2.89 vs 0.65).
That observation is reverse-causal as stated. This test asks the causal version:

> Holding entry fixed and unconditional, does any fixed handling rule change the
> mint-equal net return, and does any rule make it positive?

## Data

Codex's v3 capture: 10,891 CreateEvents, 9,613,996 frames, 7.3 h, coverage 99.43% (7 gaps,
150.6 s blind), raw replay EXACT. Decoded by `scripts/trading_bot/memebot/tape_decode.py`
into every TradeEvent (with on-chain `fee` and `creator_fee`) and Complete/Migrate events.
Successful transactions only. Population = every mint with a CreateEvent inside the window.
**No mint is excluded for any reason other than "no trade at or after the entry slot"; those
are reported as a count and charged as dropouts, not dropped.**

## Entry (fixed, unconditional — this is NOT a picker)

- E1: first observed trade with `slot >= create_slot + 2`; we take the post-trade reserve state
  as our fill basis (we are assumed one slot slower than the fastest bot).
- E2: first observed trade with `ts >= create_ts + 60 s`.
- Size 0.05 SOL. Fill computed exactly on the constant-product curve from the recorded
  virtual reserves, charging the recorded `fee_basis_points`/`creator_fee` of that trade,
  plus 5,000 lamports base fee and 100,000 lamports priority fee per transaction (b15c p50).

## Handling rules (fixed set, no grid search)

Applied to the observed post-entry tape; exits fill against the curve with exact impact.
- H0 hold to horizon, sell at last observed state <= horizon (baseline).
- H1 trim ladder: 33% at +50%, 33% at +150%, remainder at horizon.
- H2 forced time exit: sell all at min(horizon, entry+T) with T = 10 min.
- H3 stop-loss -30%: sell all at the first trade whose post-state price <= 0.7x entry (fills at
  THAT state, not at the level — measures jump-death honestly).
- H4 trailing stop: sell all when price <= 0.6x running peak, after peak >= 1.5x entry.
- H5 sell-into-strength: 50% at +100%, remainder at horizon.
- H6 = H1 + H2.
Horizons: 30 min, 120 min, end-of-capture. Total cells: 2 entries x 7 rules x 3 horizons = 42.

## Metrics (all mint-equal)

Net return in SOL per mint after all fees. Report **mean and median**, win rate, and
dropout-stressed means (unexitable positions at -50% and -100%). Uncertainty: 95% cluster
bootstrap (2,000 resamples) clustered by **creator** and, separately, by **30-minute
create-time session**; the wider of the two is the reported interval.

## Split and single-read holdout

Chronological by create_slot: first 60% of mints = exploration (all 42 cells reported);
last 40% = holdout, read **once**, only for the cell pre-declared as "best" on exploration
by mean net return. Hash-splits are forbidden (audit 2026-09-08 §4).

## Pass criteria (frozen)

- "Handling helps": a rule's exploration mean exceeds H0's by more than the bootstrap CI
  half-width AND its median >= H0's median.
- "A bot exists": the pre-declared cell's **holdout** mean net return has 95% CI lower bound
  > 0 after Bonferroni over 42 cells (alpha 0.05/42). Anything else is NOT a bot.
- Prediction, written before the data: no cell clears zero; H3 is worse than H0 (death is a
  jump); H1/H5 raise the median but not the mean; the toll measured from `fee` fields is
  ~0.95% protocol + ~0.30% creator per side.

## What this cannot show

It cannot show that the owner's own entries were random, that latency assumptions hold
live, or anything about coins born outside a 7.3-hour Monday-evening window. A pass here is
a reason to run a paper forward test, not to trade.
