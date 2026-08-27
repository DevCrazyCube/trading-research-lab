# SWEEP round 2: crypto-perp microstructure (Binance USD-M)

Round 1 tested 56 formulas and is written up in `SWEEP_crypto_perp_microstructure.md`. **This is a second round of 51 structurally different formulas that appear nowhere in round 1**, run with two deliberate protocol changes.

**1. The headline universe is the top-50 by trailing-7d volume, not the top-120.** Round 1's central finding was that most of its apparent survivors (`XS_AMIHUD`, `XS_QV_Z`, `XS_NTR_Z`, `XS_ATS_Z`, `XS_LIQPROX`, `XS_CROWD_UNWIND`) were illiquidity tilts living in the thin tail of the top-120, and went negative out of sample once the universe was cut to the top-50. Round 2 designs on the top-50 from the first bar, so there is no such tail to harvest and every number below is one where a 5.5 bp/side fill is defensible.

**2. There is a genuinely VIRGIN held-out window.** Round 1 evaluated all 56 of its formulas on 2024-04 -> 2025-01, so that window is burned. Round 1 stopped there because the Binance futures-METRICS feed (open interest, long/short ratios) dies at 2024-12 in the orphanflush cache -- only ~30 symbols carry it afterwards. But the 5m KLINES run monthly to 2026-07 plus daily files for 2026-08, for 130-150 symbols, and the t23 funding cache runs to 2026-07. So a second panel was built (`perpmicro_panel2.py` -> `panel1h_ext.npz`, 439 symbols x 40536 hours, trimmed to the 150 most-traded x 33984 hours) and every formula built only from price / volume / trade count / taker-buy volume / funding (**class A**, 39 of the 51) is tested on **2025-01-01 -> 2026-08-01: 577 days no formula in this programme had ever seen**. The 12 formulas that need the metrics feed (**class B**) can only use the burned window and are marked as such.

## Protocol

| | |
|---|---|
| Design window | **2023-01-01 -> 2024-04-01** (456 days) |
| Held-out 1 (`h1`) | 2024-04-01 -> 2025-01-01 -- **BURNED**: round 1 evaluated all 56 of its formulas here |
| Held-out 2 (`h2`) | 2025-01-01 -> 2026-08-01 -- **VIRGIN**, class A only, 577 days |
| Universe | point-in-time top-50 by trailing-7d quote volume, min 25 live names |
| Entry / exit | OPEN of the bar after the signal bar; H overlapping tranches; the close that made the signal is never a fill price |
| P&L | price + funding accrual (charged at the settlement bar) - turnover x cost |
| Cost | **5.5 bp/side** (4.5 bp published Binance USD-M VIP0 taker + 1.0 bp DECLARED half-spread), and a **15 bp/side** shock reported for every held-out number. Perp slippage has still never been MEASURED by this programme, so breakeven cost is reported for every formula. |
| Sign | oriented on DESIGN gross P&L (a formula and its negation are one hypothesis, which is why the bar is two-sided); FROZEN out of sample |
| Design freeze | `*_DESIGN_FROZEN.json` written before either held-out window was touched |
| Lookahead audit | every formula re-derived with all inputs after bar 12000 (metrics, 51 formulas) / 12000 (ext, 39 formulas) destroyed: **0 + 0 = 0 violations** |

## Noise bar

- NEW formulas in round 2: **51** (39 class A + 12 class B)
- cumulative for the theme, round 1 + round 2: **107**
- analytic expected max |Sharpe| under the null, sqrt(2 ln 2N)/sqrt(T), for N=51: **2.72**; for the cumulative N=107: **2.93**
- sign-flip block bootstrap (5-day blocks, 4000 draws) of max |Sharpe| across the ACTUAL correlated round-2 set: metrics panel mean 2.09, **95th pct 2.82**; klines panel mean 2.02, **95th pct 2.76**

The bar applied below is the bootstrap 95th percentile of the max: **2.82** on the metrics panel, **2.76** on the klines panel. `<<<` marks the formulas that cleared it on design.

## Class A on the VIRGIN window -- all 39 formulas, klines+funding panel, top-50

`d` = design, `h1` = burned window, `h2` = **virgin** 2025-01 -> 2026-08. Sharpes are net of 5.5 bp/side unless the column says gross or @15bp.

| # | formula | H | d SR | d net | h1 net | **h2 SR** | **h2 net** | h2 @15bp | h2 be bp | turn/day | corr(mkt) | 2025 | 2026 | signal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `X2_FLOWSTREAK` `<<<` | 24h | 4.61 | +3.11 | -0.67 | **+3.34** | **+2.31** | +0.54 | 17.9 | 1.38 | -0.01 | +2.53 | +2.01 | fraction of the last 24 hours with net taker BUYING (one-sidedness, not magnitude) |
| 2 | `X2_WICKASYM` `<<<` | 24h | 3.69 | +2.26 | +1.59 | **+0.73** | **-0.39** | -2.33 | 3.6 | 1.48 | +0.16 | -0.03 | -1.00 | 24h mean (lower wick - upper wick)/range: which tail is being bought |
| 3 | `X2_UPWICK` `<<<` | 24h | 3.48 | +1.88 | +1.39 | **+1.14** | **-0.01** | -1.99 | 5.4 | 1.51 | +0.19 | +0.28 | -0.45 | 24h mean UPPER-wick share of the hourly range: supply hitting rallies |
| 4 | `X2_TOD_FLOW_EU` `<<<` | 24h | 3.24 | +2.18 | +1.06 | **+2.80** | **+1.85** | +0.21 | 16.2 | 0.42 | -0.06 | +1.72 | +2.06 | 24h taker imbalance held ONLY during 07-15 UTC (Europe session) |
| 5 | `X2_FLOW_VA` `<<<` | 24h | 2.94 | +1.84 | -0.02 | **+1.36** | **+0.16** | -1.91 | 6.2 | 1.28 | +0.18 | +0.43 | -0.25 | 24h taker imbalance divided by realised vol (aggression per unit of price response) |
| 6 | `X2_IDIOVOL` `<<<` | 24h | 2.77 | +2.63 | +0.07 | **+1.97** | **+1.87** | +1.70 | 109.8 | 0.25 | +0.47 | +1.78 | +2.02 | 7d residual (idiosyncratic) volatility after removing the basket |
| 7 | `X2_RESID_MOM` | 24h | 2.46 | +2.06 | +0.76 | **+3.01** | **+2.72** | +2.22 | 57.4 | 0.61 | -0.11 | +2.15 | +3.66 | beta-adjusted 7d momentum (idiosyncratic momentum) |
| 8 | `X2_KYLE` | 24h | 2.29 | +2.16 | +1.07 | **+1.02** | **+0.92** | +0.74 | 55.9 | 0.24 | +0.58 | +0.54 | +1.54 | Kyle lambda: 7d regression slope of 1h return on taker imbalance (impact per unit flow) |
| 9 | `X2_FUNDPATH_REV` | 24h | 2.20 | +1.84 | +1.32 | **+2.13** | **+1.85** | +1.36 | 41.7 | 0.55 | -0.14 | +1.53 | +2.41 | 7d realised funding paid minus 7d return: carry the price never justified |
| 10 | `X2_KYLE_RES` | 24h | 1.79 | +0.58 | -0.22 | **+2.78** | **+1.77** | +0.03 | 15.2 | 1.34 | +0.12 | +1.69 | +1.90 | 24h move in excess of what its own Kyle lambda x realised flow explains (unsponsored move) |
| 11 | `X2_VOLSHARE` | 24h | 1.70 | +1.23 | +0.70 | **+1.63** | **+1.31** | +0.76 | 28.0 | 0.54 | -0.15 | +1.73 | +0.73 | the symbol's share of total universe quote volume (attention dominance LEVEL) |
| 12 | `X2_AR1` | 24h | 1.64 | +1.08 | +0.82 | **+0.87** | **+0.45** | -0.26 | 11.6 | 0.61 | +0.10 | +0.87 | -0.24 | own 7d 1h-return autocorrelation: trending vs mean-reverting microstructure |
| 13 | `X2_BETA` | 24h | 1.64 | +1.49 | +0.11 | **-0.72** | **-0.83** | -1.00 | -38.8 | 0.27 | +0.68 | -1.12 | -0.35 | 7d beta to the equal-weight perp basket (cross-sectional bet-against-beta) |
| 14 | `X2_SKEW` | 24h | 1.59 | +1.14 | -0.97 | **+1.01** | **+0.64** | +0.01 | 15.1 | 0.54 | +0.21 | +0.85 | +0.28 | 7d skewness of hourly returns (crash-prone names) |
| 15 | `X2_CLVWAP` | 24h | 1.50 | +0.09 | -0.76 | **+2.06** | **+1.10** | -0.55 | 11.8 | 1.53 | -0.07 | +0.47 | +2.06 | close vs 24h volume-weighted average price: where the marginal buyer sits |
| 16 | `T2_MKTVOL` | 24h | 1.42 | +1.19 | +2.54 | **+0.12** | **-0.10** | -0.47 | 2.9 | 0.65 | -0.06 | +0.08 | -0.56 | TIME-SERIES: z of universe-mean realised vol (vol-regime basket timing) |
| 17 | `X2_RANGE_Z` | 24h | 1.41 | -0.59 | -2.32 | **+2.06** | **+0.75** | -1.51 | 8.7 | 1.47 | +0.10 | +0.32 | +1.55 | z of log hourly high-low range vs own 7d (range expansion, not return vol) |
| 18 | `X2_RESID_REV` | 24h | 1.35 | +0.09 | -0.01 | **+2.65** | **+1.66** | -0.05 | 14.7 | 1.50 | -0.01 | +1.09 | +2.58 | reversal of the BETA-ADJUSTED 24h return (idiosyncratic reversal) |
| 19 | `T2_BREADTH` | 24h | 1.22 | +0.71 | -0.96 | **-0.03** | **-0.42** | -1.11 | -0.5 | 1.11 | +0.21 | -0.23 | -0.91 | TIME-SERIES: z of the fraction of the universe up over 24h (breadth regime) |
| 20 | `X2_TOD_MOM_US` | 4h | 1.20 | -4.20 | -4.75 | **+1.98** | **-1.68** | -7.93 | 3.0 | 3.50 | -0.06 | -2.09 | -1.06 | 4h cross-sectional momentum held ONLY during 13-21 UTC (US session) |
| 21 | `X2_JUMPS` | 24h | 1.19 | +0.77 | +0.05 | **+1.42** | **+1.12** | +0.59 | 25.8 | 0.56 | +0.11 | +1.58 | +0.49 | fraction of the last 7d of hours that were >3-sigma jumps (jumpiness, not variance) |
| 22 | `X2_FUNDPERSIST` | 24h | 1.18 | +0.97 | +0.38 | **-0.96** | **-1.17** | -1.53 | -25.6 | 0.25 | -0.15 | -1.32 | -0.92 | fraction of the last 7d of settlements with POSITIVE funding (sign persistence, magnitude-free) |
| 23 | `T2_WEEKEND` | 24h | 1.10 | +0.90 | +0.06 | **+0.10** | **-0.06** | -0.35 | 3.3 | 0.60 | +0.54 | +0.22 | -0.78 | TIME-SERIES: long the basket on Sat/Sun, short Mon-Fri |
| 24 | `X2_FLOWACCEL` | 24h | 0.97 | -1.43 | -4.21 | **-0.01** | **-2.31** | -6.28 | -0.0 | 1.87 | +0.06 | -1.13 | -4.17 | 24h taker imbalance minus its own value 24h ago (flow acceleration) |
| 25 | `X2_FLOW_QUIET` | 24h | 0.90 | -1.07 | -0.48 | **+0.89** | **-1.19** | -4.75 | 2.4 | 1.51 | -0.21 | -1.21 | -1.15 | taker imbalance ONLY in names whose 24h move was below the cross-sec average (absorbed flow) |
| 26 | `X2_FUNDPAID168` | 24h | 0.90 | +0.68 | +2.22 | **+0.75** | **+0.60** | +0.33 | 26.5 | 0.28 | -0.10 | +1.06 | -0.26 | funding actually paid over the last 7d (slow realised carry) |
| 27 | `X2_FUNDPAID24` | 24h | 0.85 | +0.20 | +1.14 | **+0.17** | **-0.31** | -1.14 | 1.9 | 0.78 | -0.15 | -0.57 | +0.07 | funding actually PAID over the last 24h (sum over settlements, not the last rate) |
| 28 | `T2_MKTREV` | 24h | 0.74 | +0.27 | -1.16 | **-0.54** | **-0.92** | -1.56 | -8.1 | 1.05 | +0.08 | -0.67 | -1.57 | TIME-SERIES: z of universe-mean 24h return (basket momentum/reversal timing) |
| 29 | `X2_FUNDFLIP` | 24h | 0.71 | +0.44 | +1.99 | **-2.00** | **-2.27** | -2.72 | -41.8 | 0.31 | -0.09 | -3.04 | -1.11 | rate at which the funding SIGN flipped over 7d (carry-regime instability) |
| 30 | `X2_TOD_REV_ASIA` | 24h | 0.64 | -0.53 | -0.76 | **+2.27** | **+1.42** | -0.06 | 14.6 | 0.51 | -0.02 | +1.28 | +1.64 | 24h cross-sectional reversal held ONLY during 00-08 UTC (Asia session) |
| 31 | `X2_ILLIQ_TRD` | 24h | 0.63 | +0.20 | +0.80 | **+0.75** | **+0.53** | +0.15 | 18.9 | 0.45 | -0.41 | +0.31 | +0.87 | |return| per TRADE rather than per notional (impact per ticket, size-free) |
| 32 | `X2_ATS_TREND` | 24h | 0.54 | -1.24 | -1.49 | **+1.38** | **+0.04** | -2.27 | 5.7 | 1.68 | +0.03 | -0.68 | +1.20 | 24h change in mean trade size: tickets getting bigger (whales arriving) or smaller (retail) |
| 33 | `T2_DISPERSION` | 24h | 0.47 | +0.20 | +2.34 | **+0.56** | **+0.31** | -0.14 | 12.1 | 0.73 | -0.13 | +0.67 | -0.60 | TIME-SERIES: z of the cross-sectional dispersion of 24h returns |
| 34 | `X2_GAPSUM` | 24h | 0.39 | -1.30 | -2.36 | **+0.23** | **-0.89** | -2.81 | 1.1 | 1.37 | +0.13 | +0.01 | -2.40 | 24h sum of bar-to-bar gaps log(open_t)-log(close_t-1): jump flow vs continuous flow |
| 35 | `T2_MKTFLOWP` | 24h | 0.37 | -0.02 | -0.15 | **+0.65** | **+0.30** | -0.30 | 10.2 | 0.93 | +0.04 | +0.35 | +0.18 | TIME-SERIES: z of universe-mean order-flow autocorrelation (market trending-ness) |
| 36 | `X2_VOLVOL` | 24h | 0.34 | -0.07 | +0.56 | **+1.92** | **+1.65** | +1.17 | 38.6 | 0.53 | -0.08 | +3.12 | -0.49 | vol-of-vol: 7d std of the rolling 24h vol, scaled by its mean |
| 37 | `X2_DVOLSHARE` | 24h | 0.16 | -1.45 | -2.61 | **+1.55** | **+0.43** | -1.50 | 7.6 | 1.64 | -0.02 | +0.16 | +0.90 | 24h log change in volume share (attention ROTATING into the name) |
| 38 | `X2_BODY` | 24h | 0.09 | -1.85 | -1.70 | **-0.81** | **-2.12** | -4.39 | -3.4 | 1.53 | -0.13 | -2.19 | -2.04 | 24h mean body/range: how much of the hour's range the net move kept (trend efficiency) |
| 39 | `X2_FLOWPERSIST` | 24h | 0.08 | -2.12 | -3.24 | **+1.49** | **-0.12** | -2.90 | 5.1 | 1.55 | -0.02 | -1.35 | +1.83 | 24h mean sign agreement of consecutive hourly taker imbalances (order-flow autocorrelation) |

### Does the design ranking survive into a window nobody had seen?

| | value |
|---|---|
| Spearman rank corr, design gross SR -> **virgin** gross SR (n=39) | **+0.390** |
| Spearman rank corr, design gross SR -> burned h1 gross SR | +0.417 |
| mean virgin GROSS SR, the 6 that cleared the design bar | **+1.89** |
| mean virgin GROSS SR, the 33 that did not | +0.92 |
| mean virgin NET SR, cleared / not | +0.97 / +0.16 |
| fraction of all 39 with positive virgin gross SR | 82% |

The design ranking does carry information into the virgin window: +0.39 rank correlation, and the bar-clearers average roughly twice the gross Sharpe of the rest. That is the single strongest piece of evidence in this sweep. The 82% positive-gross figure is much weaker evidence than it looks -- see the correlation matrix below, these 39 formulas are about four clusters, not 39 independent draws.

## All 51 formulas on the metrics panel, top-50 (h1 only -- burned window)

| # | formula | cls | H | d SR | d net | h1 SR | h1 net | h1 @15bp | h1 be bp | turn/day | corr(mkt) | signal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `X2_RETAIL_VS_TAKER` `<<<` | B | 24h | 3.91 | +2.96 | +2.49 | +1.30 | -0.74 | 11.5 | 1.13 | -0.15 | accounts positioned long while the aggressor flow sells (positioning/flow divergence) |
| 2 | `X2_GLSR_SLOW` `<<<` | B | 24h | 3.30 | +2.80 | +1.13 | +0.59 | -0.36 | 11.4 | 0.72 | -0.08 | global L/S ratio vs its own 30d mean (SLOW crowding; round 1 used a 7d z) |
| 3 | `X2_FLOWSTREAK` `<<<` | A | 24h | 3.27 | +1.99 | +1.22 | -0.17 | -2.56 | 4.8 | 1.36 | -0.19 | fraction of the last 24 hours with net taker BUYING (one-sidedness, not magnitude) |
| 4 | `X2_OI_PER_ACCT` `<<<` | B | 24h | 2.91 | +1.42 | -0.98 | -2.54 | -5.23 | -3.4 | 1.59 | -0.02 | OI growth in excess of account-count growth (position size per account rising) |
| 5 | `X2_GLSR_ASIA` | B | 24h | 2.72 | +2.41 | +1.83 | +1.45 | +0.79 | 26.5 | 0.17 | -0.03 | retail crowding signal held ONLY 00-08 UTC (is the fade an Asia-hours effect?) |
| 6 | `X2_UPWICK` | A | 24h | 2.49 | +1.07 | +3.10 | +1.65 | -0.83 | 11.8 | 1.50 | +0.23 | 24h mean UPPER-wick share of the hourly range: supply hitting rallies |
| 7 | `X2_SMART_CONF` | B | 24h | 2.28 | +1.80 | +0.91 | +0.44 | -0.36 | 10.8 | 0.37 | -0.06 | smart-vs-crowd spread, but only in names where the spread is >1sd from its own 30d norm |
| 8 | `X2_WICKASYM` | A | 24h | 2.11 | +0.83 | +2.33 | +1.04 | -1.18 | 9.9 | 1.47 | +0.25 | 24h mean (lower wick - upper wick)/range: which tail is being bought |
| 9 | `X2_TOD_FLOW_EU` | A | 24h | 2.04 | +1.12 | +1.88 | +0.78 | -1.11 | 9.4 | 0.42 | -0.19 | 24h taker imbalance held ONLY during 07-15 UTC (Europe session) |
| 10 | `X2_AR1` | A | 24h | 1.95 | +1.42 | +0.53 | -0.02 | -0.97 | 5.3 | 0.62 | +0.02 | own 7d 1h-return autocorrelation: trending vs mean-reverting microstructure |
| 11 | `X2_CROWD_x_VOL` | B | 24h | 1.90 | +1.20 | +1.72 | +0.84 | -0.67 | 10.8 | 0.87 | -0.13 | crowded AND volatile: crowding weighted by how fragile the name is |
| 12 | `X2_FLOW_VA` | A | 24h | 1.83 | +0.87 | -0.07 | -1.15 | -3.03 | -0.3 | 1.26 | +0.11 | 24h taker imbalance divided by realised vol (aggression per unit of price response) |
| 13 | `X2_CLVWAP` | A | 24h | 1.72 | +0.37 | +0.53 | -0.85 | -3.21 | 2.1 | 1.52 | -0.15 | close vs 24h volume-weighted average price: where the marginal buyer sits |
| 14 | `T2_MKTVOL` | A | 24h | 1.42 | +1.20 | +2.61 | +2.43 | +2.12 | 80.9 | 0.63 | -0.04 | TIME-SERIES: z of universe-mean realised vol (vol-regime basket timing) |
| 15 | `X2_KYLE` | A | 24h | 1.33 | +1.19 | +0.47 | +0.33 | +0.08 | 17.9 | 0.26 | +0.58 | Kyle lambda: 7d regression slope of 1h return on taker imbalance (impact per unit flow) |
| 16 | `T2_BREADTH` | A | 24h | 1.23 | +0.73 | -0.88 | -1.22 | -1.82 | -14.5 | 1.12 | +0.35 | TIME-SERIES: z of the fraction of the universe up over 24h (breadth regime) |
| 17 | `X2_FLOWPERSIST` | A | 24h | 1.23 | -0.70 | +2.05 | +0.23 | -2.92 | 6.2 | 1.55 | -0.02 | 24h mean sign agreement of consecutive hourly taker imbalances (order-flow autocorrelation) |
| 18 | `X2_FLOWACCEL` | A | 24h | 1.15 | -1.24 | -1.15 | -3.66 | -8.00 | -2.5 | 1.87 | +0.00 | 24h taker imbalance minus its own value 24h ago (flow acceleration) |
| 19 | `X2_RESID_MOM` | A | 24h | 1.15 | +0.77 | +0.51 | +0.11 | -0.57 | 7.1 | 0.62 | -0.12 | beta-adjusted 7d momentum (idiosyncratic momentum) |
| 20 | `X2_LONGLIQ` | B | 24h | 1.11 | -0.33 | +2.97 | +1.30 | -1.59 | 9.8 | 1.40 | -0.09 | PRODUCT (conjunction) of OI destroyed AND price down: long liquidation, not voluntary exit |
| 21 | `X2_VOLVOL` | A | 24h | 0.99 | +0.58 | -0.61 | -1.06 | -1.83 | -7.5 | 0.55 | +0.34 | vol-of-vol: 7d std of the rolling 24h vol, scaled by its mean |
| 22 | `X2_FUNDPAID168` | A | 24h | 0.97 | +0.74 | +2.28 | +2.04 | +1.63 | 52.3 | 0.31 | -0.14 | funding actually paid over the last 7d (slow realised carry) |
| 23 | `X2_IDIOVOL` | A | 24h | 0.95 | +0.80 | -0.40 | -0.56 | -0.83 | -14.1 | 0.27 | +0.45 | 7d residual (idiosyncratic) volatility after removing the basket |
| 24 | `X2_RESID_REV` | A | 24h | 0.93 | -0.27 | +0.91 | -0.36 | -2.52 | 3.9 | 1.50 | -0.11 | reversal of the BETA-ADJUSTED 24h return (idiosyncratic reversal) |
| 25 | `X2_TOD_MOM_US` | A | 4h | 0.92 | -4.16 | +0.65 | -4.40 | -12.95 | 0.7 | 3.49 | +0.12 | 4h cross-sectional momentum held ONLY during 13-21 UTC (US session) |
| 26 | `X2_FUNDPERSIST` | A | 24h | 0.90 | +0.67 | +1.41 | +1.15 | +0.69 | 29.4 | 0.28 | -0.18 | fraction of the last 7d of settlements with POSITIVE funding (sign persistence, magnitude-free) |
| 27 | `X2_FUNDPATH_REV` | A | 24h | 0.88 | +0.54 | +0.38 | -0.01 | -0.68 | 5.3 | 0.56 | -0.16 | 7d realised funding paid minus 7d return: carry the price never justified |
| 28 | `T2_WEEKEND` | A | 24h | 0.88 | +0.67 | -0.04 | -0.21 | -0.50 | -1.3 | 0.62 | +0.52 | TIME-SERIES: long the basket on Sat/Sun, short Mon-Fri |
| 29 | `X2_KYLE_RES` | A | 24h | 0.86 | -0.23 | +1.10 | -0.16 | -2.34 | 4.8 | 1.31 | -0.17 | 24h move in excess of what its own Kyle lambda x realised flow explains (unsponsored move) |
| 30 | `X2_OI_VS_FLOW` | B | 24h | 0.84 | -0.90 | -0.72 | -2.33 | -5.12 | -2.4 | 1.49 | +0.01 | OI growth SIGNED by the direction of the aggressor flow that built it (new longs vs new shorts) |
| 31 | `X2_BETA` | A | 24h | 0.82 | +0.65 | +0.03 | -0.14 | -0.43 | 0.9 | 0.31 | +0.64 | 7d beta to the equal-weight perp basket (cross-sectional bet-against-beta) |
| 32 | `X2_GLSR_ACCEL` | B | 24h | 0.81 | -1.21 | -1.36 | -3.34 | -6.74 | -3.8 | 1.84 | +0.07 | second difference of the global L/S ratio (crowding acceleration) |
| 33 | `T2_MKTREV` | A | 24h | 0.80 | +0.34 | -1.02 | -1.35 | -1.91 | -17.7 | 1.06 | +0.30 | TIME-SERIES: z of universe-mean 24h return (basket momentum/reversal timing) |
| 34 | `X2_RANGE_Z` | A | 24h | 0.79 | -0.96 | +0.19 | -1.79 | -5.20 | 0.5 | 1.46 | -0.16 | z of log hourly high-low range vs own 7d (range expansion, not return vol) |
| 35 | `X2_BODY` | A | 24h | 0.78 | -0.98 | +0.76 | -0.91 | -3.78 | 2.5 | 1.54 | +0.04 | 24h mean body/range: how much of the hour's range the net move kept (trend efficiency) |
| 36 | `T2_MKTFLOWP` | A | 24h | 0.75 | +0.36 | +0.07 | -0.21 | -0.69 | 1.4 | 0.93 | +0.05 | TIME-SERIES: z of universe-mean order-flow autocorrelation (market trending-ness) |
| 37 | `X2_VOLSHARE` | A | 24h | 0.75 | +0.25 | +1.36 | +0.88 | +0.05 | 15.6 | 0.61 | -0.29 | the symbol's share of total universe quote volume (attention dominance LEVEL) |
| 38 | `X2_FUNDPAID24` | A | 24h | 0.68 | +0.02 | +1.94 | +1.25 | +0.04 | 15.3 | 0.82 | -0.13 | funding actually PAID over the last 24h (sum over settlements, not the last rate) |
| 39 | `X2_FLOW_QUIET` | A | 24h | 0.67 | -1.03 | +1.47 | -0.26 | -3.25 | 4.7 | 1.50 | -0.19 | taker imbalance ONLY in names whose 24h move was below the cross-sec average (absorbed flow) |
| 40 | `X2_CROWDCONJ` | B | 24h | 0.54 | -0.96 | -0.39 | -1.85 | -4.36 | -1.5 | 1.44 | +0.03 | PRODUCT of retail crowding and OI destruction (round 1 only tested the SUM) |
| 41 | `T2_MKT_GLSR` | B | 24h | 0.51 | +0.37 | +0.71 | +0.58 | +0.36 | 30.3 | 0.45 | -0.18 | TIME-SERIES: z of universe-mean retail long/short ratio (aggregate positioning timing) |
| 42 | `X2_ILLIQ_TRD` | A | 24h | 0.49 | +0.07 | +1.59 | +1.21 | +0.57 | 23.5 | 0.49 | -0.50 | |return| per TRADE rather than per notional (impact per ticket, size-free) |
| 43 | `X2_SKEW` | A | 24h | 0.32 | -0.14 | -1.64 | -2.14 | -3.00 | -18.1 | 0.56 | +0.19 | 7d skewness of hourly returns (crash-prone names) |
| 44 | `T2_DISPERSION` | A | 24h | 0.16 | -0.13 | +2.48 | +2.21 | +1.75 | 51.4 | 0.78 | -0.37 | TIME-SERIES: z of the cross-sectional dispersion of 24h returns |
| 45 | `X2_JUMPS` | A | 24h | 0.16 | -0.23 | +1.41 | +0.99 | +0.26 | 18.4 | 0.57 | -0.12 | fraction of the last 7d of hours that were >3-sigma jumps (jumpiness, not variance) |
| 46 | `X2_GAPSUM` | A | 24h | 0.15 | -1.40 | +0.10 | -1.50 | -4.27 | 0.4 | 1.39 | +0.09 | 24h sum of bar-to-bar gaps log(open_t)-log(close_t-1): jump flow vs continuous flow |
| 47 | `X2_TOD_REV_ASIA` | A | 24h | 0.15 | -0.99 | -0.07 | -1.18 | -3.09 | -0.3 | 0.51 | -0.16 | 24h cross-sectional reversal held ONLY during 00-08 UTC (Asia session) |
| 48 | `X2_DVOLSHARE` | A | 24h | 0.11 | -1.33 | +1.30 | -0.14 | -2.64 | 5.0 | 1.63 | +0.08 | 24h log change in volume share (attention ROTATING into the name) |
| 49 | `X2_CASCADE` | B | 24h | 0.07 | -1.08 | -0.77 | -1.92 | -3.89 | -3.7 | 1.38 | -0.07 | 24h forced-liquidation intensity: OI destroyed in hours whose range was abnormally wide |
| 50 | `X2_FUNDFLIP` | A | 24h | 0.06 | -0.22 | +1.26 | +0.92 | +0.33 | 20.2 | 0.34 | +0.14 | rate at which the funding SIGN flipped over 7d (carry-regime instability) |
| 51 | `X2_ATS_TREND` | A | 24h | 0.03 | -1.58 | -0.02 | -1.67 | -4.53 | -0.1 | 1.67 | +0.12 | 24h change in mean trade size: tickets getting bigger (whales arriving) or smaller (retail) |

Design->h1 rank correlation on this panel: **+0.238**. The 4 that cleared the design bar average **-0.21** net Sharpe out of sample against -0.27 for the rest -- i.e. clearing the bar bought nothing on this panel. **On the top-50, round 2's open-interest and long/short-ratio transforms are noise.** `X2_RETAIL_VS_TAKER` (design 3.91, h1 net +1.30) and `X2_GLSR_SLOW` (design 3.30, h1 net +0.59) are the only two that stayed positive, both die at 15 bp/side, and both are built from the same two Binance long/short-ratio fields as round 1's single survivor `XS_SMART` -- they are not an independent finding, they are the same one.

## Is the virgin-window shortlist several findings or one bet?

Daily net P&L of the shortlist on the virgin window, correlated against each other:

| | FLOWSTREAK | TOD_FLOW_EU | IDIOVOL | FLOW_VA | UPWICK | WICKASYM | RESID_MOM | KYLE | FUNDPATH_REV | RESID_REV | KYLE_RES |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **FLOWSTREAK** | +1.00 | +0.80 | +0.29 | +0.60 | +0.19 | +0.24 | +0.43 | +0.28 | +0.41 | +0.36 | +0.40 |
| **TOD_FLOW_EU** | +0.80 | +1.00 | +0.33 | +0.73 | +0.18 | +0.24 | +0.44 | +0.29 | +0.46 | +0.37 | +0.37 |
| **IDIOVOL** | +0.29 | +0.33 | +1.00 | +0.60 | +0.40 | +0.39 | +0.32 | +0.86 | +0.37 | +0.12 | +0.33 |
| **FLOW_VA** | +0.60 | +0.73 | +0.60 | +1.00 | +0.31 | +0.36 | +0.35 | +0.56 | +0.42 | +0.22 | +0.28 |
| **UPWICK** | +0.19 | +0.18 | +0.40 | +0.31 | +1.00 | +0.85 | +0.20 | +0.38 | +0.16 | +0.18 | +0.06 |
| **WICKASYM** | +0.24 | +0.24 | +0.39 | +0.36 | +0.85 | +1.00 | +0.21 | +0.37 | +0.16 | +0.17 | +0.12 |
| **RESID_MOM** | +0.43 | +0.44 | +0.32 | +0.35 | +0.20 | +0.21 | +1.00 | +0.16 | +0.80 | +0.47 | +0.26 |
| **KYLE** | +0.28 | +0.29 | +0.86 | +0.56 | +0.38 | +0.37 | +0.16 | +1.00 | +0.21 | +0.08 | +0.23 |
| **FUNDPATH_REV** | +0.41 | +0.46 | +0.37 | +0.42 | +0.16 | +0.16 | +0.80 | +0.21 | +1.00 | +0.36 | +0.22 |
| **RESID_REV** | +0.36 | +0.37 | +0.12 | +0.22 | +0.18 | +0.17 | +0.47 | +0.08 | +0.36 | +1.00 | +0.24 |
| **KYLE_RES** | +0.40 | +0.37 | +0.33 | +0.28 | +0.06 | +0.12 | +0.26 | +0.23 | +0.22 | +0.24 | +1.00 |

Mean absolute off-diagonal correlation **0.35**. Four clusters are visible and they are what the 39 formulas actually are:

| cluster | members | internal corr | virgin verdict |
|---|---|---|---|
| **taker-flow imbalance** | `X2_FLOWSTREAK`, `X2_TOD_FLOW_EU`, `X2_FLOW_VA` | 0.60-0.80 | **the only market-neutral one that works** (corr to basket -0.01 / -0.06) |
| **liquidity / low-vol tilt** | `X2_IDIOVOL`, `X2_KYLE` | 0.86 | works, but corr to the equal-weight basket +0.47 / +0.58 -- this is a long-majors/short-alts directional bet |
| **candle shape** | `X2_UPWICK`, `X2_WICKASYM` | 0.85 | cleared the design bar, **died on the virgin window** (net -0.01 / -0.39) |
| **residual momentum / carry-vs-return** | `X2_RESID_MOM`, `X2_FUNDPATH_REV` | 0.80 | positive on all three windows but **never cleared the design bar** (2.46 / 2.20 vs 2.76) |

An equal-weight composite of the three bar-clearers that stayed positive at 15 bp (FLOWSTREAK, TOD_FLOW_EU, IDIOVOL) nets Sharpe **2.54** (+55%/yr) on the virgin window at 5.5 bp/side, with correlation +0.30 to the equal-weight perp basket. That correlation is entirely `IDIOVOL`'s.

## Verdict

**The metrics half of the theme is noise; the taker-flow half is not, but it is too thin to trade at an honest cost.**

What survived everything -- design bar, a window nothing had seen, and a 15 bp/side cost shock:

| | `X2_FLOWSTREAK` | `X2_TOD_FLOW_EU` |
|---|---|---|
| signal | fraction of the last 24 hours with net taker BUYING (one-sidedness, magnitude discarded) | 24h taker buy-sell notional imbalance, held ONLY 07-15 UTC |
| design gross / net | 4.61 / +3.11 | 3.24 / +2.18 |
| burned h1 net | **-0.67** | +1.06 |
| **virgin h2** gross / net | **+3.34 / +2.31** | **+2.80 / +1.85** |
| virgin net @ 15 bp/side | **+0.54** | **+0.21** |
| virgin breakeven cost | 17.9 bp/side | 16.2 bp/side |
| virgin 2025 / 2026 net | +2.5 / +2.0 | +1.7 / +2.1 |
| corr to equal-weight basket | -0.01 | -0.06 |
| turnover | 1.38 x/day | 0.42 x/day |

### Honest caveats

1. **These two are ONE hypothesis, and round 1 already had it.** Both are the cross-sectional taker aggressor-flow imbalance; round 1's `XS_TAKER24` is the same feature (design gross 3.15, h1 net +1.12 on the top-120 but only +0.32 on the top-50 and -1.67 at 15 bp). Counting round 1 and round 2 together this family has been tested six ways across three windows and is positive in most of them, negative in some. It is not six confirmations.
2. **`X2_FLOWSTREAK` failed the middle window.** Design +3.11, h1 **-0.67**, h2 +2.31. A formula that is strong, then negative, then strong is not a stable edge; it is a formula with a wide sampling distribution. `X2_TOD_FLOW_EU` is the only one positive in all three (+2.18 / +1.06 / +1.85) and it is the weaker of the two.
3. **At a realistic cost this is not tradeable.** Breakeven is 16-18 bp/side against a 4.5 bp published taker fee, which sounds like room -- but the surviving net Sharpe at 15 bp/side is +0.54 and +0.21. This programme has still never MEASURED perp slippage. `orphanflush_cache/bookdepth` holds +-1%..+-5% notional for 264 symbols and was again not used. Until that measurement exists, the honest statement is: the edge is real at 5.5 bp and gone somewhere before 20 bp, and nobody here knows which side of that line the fills land on.
4. **`X2_IDIOVOL` should not be counted as a microstructure finding.** It is long low idiosyncratic-vol perps / short high -- on a top-50 universe that is long majors, short alts. Its virgin Sharpe (+1.87 net, +1.70 at 15 bp) coincides with a period of rising BTC dominance, and its correlation to the equal-weight basket is +0.47. It is a directional regime bet wearing a cross-sectional costume.
5. **The 82%-positive statistic is not 39 confirmations.** Mean absolute pairwise correlation of the shortlist is 0.35 and the set collapses to about four clusters, so the effective number of independent draws is closer to 4-8 than to 39. The +0.39 design->virgin rank correlation should be read with that effective n, at which it is suggestive, not significant.
6. **Two formulas were initially untestable and were fixed, not dropped.** `X2_FUNDPERSIST` and `X2_FUNDFLIP` returned NaN on the first pass because funding settles 3x/day and the shared rolling-window helper requires 60% of the hours in a window to be observed. They were re-derived with a settlement-count gate and both then failed on their own merits (design 1.18 / 0.71, virgin net -1.17 / -2.27).
7. **The virgin window is one draw of one regime**, 2025-01 to 2026-08. It is not a walk-forward, and 2025-26 perp market structure (funding intervals moved from 8h to 4h and 1h on many symbols during it) is not the 2023 market the formulas were designed on.

## Files

- `scripts/trading_bot/perpmicro_panel2.py` -- builds the extended klines+funding panel (439 symbols x 40536 hours, 2022-01 -> 2026-08)
- `scripts/trading_bot/perpmicro_trim_ext.py` -- trims it to 150 symbols x 33984 hours
- `scripts/trading_bot/perpmicro_sweep2.py` -- the round-2 harness; formula catalogue in `catalogue2()`
- `scripts/trading_bot/perpmicro_r2_shortlist.py` -- shortlist correlation / independence check
- `research/trading_bot/SWEEP_crypto_perp_microstructure_R2_{metrics,ext}_top50_DESIGN_FROZEN.json` -- design results, written before any held-out window was touched
- `research/trading_bot/SWEEP_crypto_perp_microstructure_R2_{metrics,ext}_top50_holdout.json`
- `research/trading_bot/SWEEP_crypto_perp_microstructure_R2_SHORTLIST.json`
