# Pre-registration: Mayhem residual burn as a supply-shock event (DeepSeek round-2 Rank 1)

Frozen 2026-09-09 ~20:00 UTC by Claude, before any 24 h mark of the tape's mayhem graduates has been read. Paper only.

## Mechanics (stated first, because it decides the prediction)
The agent (`BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s`, 199,353 zero-fee trades on the tape) holds an extra 1e9 tokens,
trades randomly for 24 h, then burns its residual. On a constant-product pool price = reserveSOL / reserveTok; the agent's
tokens are outside both reserves, so the burn changes supply accounting (FDV, "mcap") and NOT the pool price. Any move is
narrative ("50% of supply burned") or a change in the agent's own random flow stopping.

## Population and arms
97 mayhem graduates on the v3 tape (24 h marks 2026-09-09 19:04 -> 2026-09-10 02:07 UTC); agent residual at end of curve
phase = 1e9 + net curve buys - sells (median 55% of the 2e9 supply). PLACEBO = the 244 non-mayhem graduates on the same tape
at the same ages. Executability screen: liquidity >= $5k at the 23 h mark (reported, not used to drop).

## Measurement (fixed)
DexScreener price/liquidity/mcap recorded at each coin's +23 h, +24 h, +25 h, +26 h marks (first observation at or after the
mark). Paper entry at the +23 h observation, exit at +25 h (DeepSeek's spec) and +26 h; toll 1.14% RT; no bars = -100%
(also -50%). Mint-equal mean AND median per arm; CI by 30-min birth session. Secondary: split mayhem by residual share
>= 50% vs < 50%.

## Pass
Mayhem arm mean > 0 with CI-low > 0, median > 0, and exceeds the placebo arm by more than the CI half-width.
Prediction, written first: no difference between arms; both negative or flat; liquidity at 23 h below $5k for most.
