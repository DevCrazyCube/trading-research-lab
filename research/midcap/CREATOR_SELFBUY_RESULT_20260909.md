# Creator self-buy filter — RESULT (single holdout read)

Prereg `CREATOR_SELFBUY_PREREGISTRATION.md` sha 63fb2003..., evaluator `scripts/trading_bot/memebot/creator_selfbuy_test.py`,
data = v3 tape (8,971 launches with trades; exploration 5,382 / holdout 3,589 chronological).

## Graduation lift is real but is mostly manufactured completion
| creator self-buy (create slot+2) | n | any graduation | ORGANIC (>5 min) | INSTANT (<=10 s) |
|---|---|---|---|---|
| 0 SOL | 290 | 2.41% | 0.34% | 1.38% |
| (0, 0.2) | 3,723 | 2.69% | 0.86% | 0.75% |
| [0.2, 1) | 2,164 | 1.62% | 0.55% | 0.60% |
| [1, 5) | 2,044 | 2.01% | 1.42% | 0.05% |
| >= 5 | 750 | **18.13%** | 1.47% | **14.93%** |
The "order-of-magnitude lift" at >= 5 SOL is the creator buying the whole curve in the create slot (nothing to enter).
Organic graduation rises from 0.34% to ~1.45% (4x, from a tiny base).

## Returns: every one of 27 cells negative; placebo not beaten; holdout fails
Exploration means −17% to −39% (best: T=0.2 SOL, 2-s latency, 15-min exit: −17.8% [−22.7, −11.9]); medians −15% to −45%;
win rates 3–10%. Shuffled-size placebo at the primary cell: −27.8% vs rule −23.9% (difference inside the CI half-width).
**HOLDOUT (T=1 SOL, L=32 slots, 60 min): 1,338 signals, 1,202 enterable, mean −24.10%, median −27.90%, win 4%,
95% CI [−29.9%, −17.6%]; −19.6% at −50% dropout.** FAIL on every frozen criterion.

## Why it loses
A creator's self-buy is not commitment; it is inventory. A 5 SOL buy moves a fresh 30-SOL curve ~35%; the follower buys the
price the creator just made and the creator's exit is the follower's counterparty. Latency does not rescue it: the 2-second
cells are as negative as the 3-minute cells.

## Status
NO_TRADE. The gen-1 "one positive cell" (dev-buy share >= 20%, +4.6%, n=172) does not replicate out of sample.
