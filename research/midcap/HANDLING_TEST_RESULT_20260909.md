# Handling test — RESULT (single holdout read)

Pre-registration: `HANDLING_TEST_PREREGISTRATION.md`, sha `874314606b38aaf0d75869cf3ff454ef6e6ca5c67d609fe2cdd85912fe69ba93`, frozen before decoding finished.
Evaluator: `scripts/trading_bot/memebot/handling_test.py`. Data: v3 tape (10,122 creates, 1.16M trades, 7.3 h, 99.43% coverage).
Population 9995 mints with a successful CreateEvent; exploration 5,997 / holdout 3,998 (chronological).

## Verdict: NO handling rule makes unconditional entry profitable. Prediction confirmed.

Best exploration cell (by mean): `E1|H4|end` (trailing stop: exit at 0.6x peak once peak >= 1.5x).
- exploration: mean -29.1%, median -25.1%, win 15%   (H0 hold: mean -33.9%, median -42.9%)
- **holdout (read once): mean -30.09%, median -24.00%, win 14%, 95% CI [-34.4%, -25.7%], Bonferroni(0.05/42) CI [-37.3%, -22.7%]**
- at -50% dropout charge the holdout mean is -17.8% — still negative.

## What the 42 cells say
- Entry at create_slot+2 (E1): hold = -33.9% mean / -42.9% median. 26% of coins never trade again after entry (charged -100%).
- Entry at t0+60 s (E2): hold = -60% mean, **median -100%**: 56% of coins have no trade after the first minute. The first minute is the whole life of most launches.
- Trailing stop (H4) and trim ladders (H1/H6) lift the MEDIAN by 13-18 pp and the win rate from 8% to 15-16%, but the mean by only ~3-5 pp — inside the CI half-width, so "handling helps" is NOT established on the mean by the frozen criterion. Handling reduces catastrophe frequency; it does not create expectancy.
- Stop-loss -30% (H3) is slightly BETTER than hold here (-30.1% vs -33.9%), contradicting the written prediction. On the bonding curve decay is continuous enough for stops to fill; the "death is a jump" finding was measured on post-graduation pools with LP removal and does not transfer to the curve.
- Toll measured from the tape: 0.95% protocol + 0.30% creator per side (1.25%); a buy-then-sell round trip costs 2.48%.

## Read with the owner's real ledger
The owner's clean Solana result (13 closed positions, -23.0%) sits inside this distribution: an E1-like entry with partial trimming (H1) is -31% here. The live loss is not bad luck or bad handling; it is the population mean.

## Status
NO_TRADE. This closes the last free-data question ("does discipline fix an unconditional entry?"): no.
