# Post-graduation LP with breadth screen — RESULT (single holdout read)

Prereg `POSTGRAD_LP_PREREGISTRATION.md` sha 5c14bad2..., evaluator `scripts/trading_bot/memebot/postgrad_lp_test.py`.
341 in-window graduates (v3 tape) joined to PumpSwap/Raydium pools and GeckoTerminal 1-min USD bars; SOL/USD 103;
position 0.5% of a ~$16.3k migration pool ($81); LP fee 0.20% of volume; IL = 2*sqrt(r)/(1+r)-1; unwind 1.14% RT on the
token half; no bars / pool gone = -100%. ORGANIC = >5 min to complete AND >= 40 distinct curve buyers (53); placebo = the
other 288 graduates.

| cell | arm | n | unresolved | mean | median | win | 95% CI |
|---|---|---|---|---|---|---|---|
| A: +10 min, hold 45 | ORGANIC | 31 | 8 | -51.9% | -54.7% | 16% | [-62.4, -42.3] |
| A: +10 min, hold 45 | placebo | 173 | 79 | -48.2% | -64.9% | 20% | [-59.1, -36.1] |
| A: +10 min, hold 90 | ORGANIC | 31 | 8 | -54.3% | -69.6% | 19% | [-69.0, -37.7] |
| B: first >=20% pullback, hold 60 | ORGANIC | 31 | 9 | -35.8% | -87.8% | 13% | [-71.1, +6.2] |
| B | placebo | 173 | 104 | -84.2% | -100.0% | 6% | [-89.3, -78.8] |
| **HOLDOUT A-90** | **ORGANIC** | **22** | **6** | **-63.3%** | **-74.8%** | **0%** | **[-75.6, -52.8]** |
| HOLDOUT A-90 | placebo | 115 | 61 | -68.2% | -100.0% | 14% | [-76.6, -59.0] |

## Verdict: FAIL, and not close. Providing liquidity to a fresh graduate is the worst position measured in this repo.
Impermanent loss on first-hour paths of -70% to -100% dwarfs fee income (1-4%/h of position). The breadth screen barely
separates ORGANIC from placebo. Half of placebo pools have no bars within 90 minutes (dead on arrival). Grok's original
"+-8% concentrated range" does not exist on PumpSwap (constant product); on a concentrated venue the same paths would
leave the range within minutes and hold 100% of the losing token.

## Status
NO_TRADE. Adds "LP on fresh memecoin pools" to the dead list with a number.
