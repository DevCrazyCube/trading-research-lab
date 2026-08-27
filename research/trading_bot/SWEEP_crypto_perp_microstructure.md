# SWEEP: crypto-perp microstructure (Binance USD-M)

**Verdict: the theme is NOT noise, but most of it is.** 56 structurally different formulas were
tested on a design window; the design->held-out rank correlation is **+0.44** (Spearman, n=56),
the 15 formulas that cleared the design noise bar averaged **2.48** gross Sharpe out of sample
against **0.82** for the other 41, and the design winner repeated. But the funding-carry family
and the open-interest family are dead OOS, and most of the survivors evaporate when the universe
is cut to genuinely liquid names. What is left is one idea: **fade retail account positioning**.

## Protocol

| | |
|---|---|
| Design window | **2023-01-01 -> 2024-04-01** (456 days) |
| Held out (untouched during the sweep) | **2024-04-01 -> 2025-01-01** (275 days) |
| Panel | 265 Binance USD-M perps, 1h bars from the 5m orphanflush cache (klines + metrics) + t23 funding |
| Universe | point-in-time top-120 by trailing-7d quote volume, min 30 live names |
| Entry / exit | OPEN of the bar after the signal bar; H overlapping tranches; the close that made the signal is never a fill price |
| P&L | price + funding accrual (charged at the settlement bar) - turnover x cost |
| Cost | **5.5 bp/side** = 4.5 bp Binance USD-M VIP0 taker (published exchange schedule) + 1.0 bp DECLARED half-spread. This programme has not MEASURED perp slippage, so breakeven cost is reported for every formula. |
| Lookahead audit | all 56 formulas re-derived with every input after bar 16228 destroyed: **0 violations** |

Each formula is ORIENTED by its design gross P&L (a formula and its negation are one
hypothesis), so the bar is two-sided. Costs are sign-invariant and charged after orienting.
**Held-out signs are frozen from the design window** -- nothing is re-fit OOS.

## Noise bar

- formulas tested: **56**
- analytic expected max |Sharpe| under the null, sqrt(2 ln 2N)/sqrt(T): **2.75**
- sign-flip block bootstrap (5-day blocks, 4000 draws) of max |Sharpe| across the ACTUAL
  correlated set: mean **2.06**, median 2.02, **95th pct 2.80**

The bar used below is the bootstrap 95th percentile, **2.80**. 15 of 56 cleared it -- far more
than the ~3 the null produces, which is itself evidence the theme carries signal.

## Design vs held-out, every formula

`d` = design, `o` = held-out. `SR` is gross Sharpe (the number the bar applies to), `net` is after cost.
`be` is the breakeven cost in bp/side. `<<<` marks the 15 that cleared the design bar.

| # | formula | H | d SR | d net | o SR | o net | o be bp | o ann net | corr(mkt) | sign | signal |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `XS_GLSR_Z` `<<<` | 24h | 4.94 | +3.37 | +3.92 | +2.38 | 14.0 | +35% | -0.01 | -1 | global L/S ratio z vs own 7d (crowding surprise) |
| 2 | `XS_SMART_CHG` `<<<` | 24h | 4.10 | +1.48 | +0.87 | -1.74 | 1.8 | -22% | -0.04 | +1 | 24h change in the smart-vs-crowd spread |
| 3 | `XS_GLSR_CHG` `<<<` | 24h | 4.05 | +1.51 | +1.26 | -1.13 | 2.9 | -16% | -0.03 | -1 | 24h change in log global L/S ratio |
| 4 | `XS_CROWD_UNWIND` `<<<` | 24h | 3.90 | +2.65 | +2.90 | +1.63 | 12.6 | +26% | -0.06 | -1 | crowded long AND shrinking OI: the crowd is being forced out |
| 5 | `XS_ATS_Z` `<<<` | 24h | 3.64 | +1.31 | +4.11 | +1.55 | 8.8 | +17% | +0.07 | +1 | z of log average trade size (quote vol / trade count) vs 7d: whale-print detector |
| 6 | `XS_SMART` `<<<` | 24h | 3.25 | +2.74 | +1.90 | +1.42 | 22.1 | +22% | -0.04 | +1 | log(top-trader position L/S) - log(global account L/S): smart-vs-crowd divergence |
| 7 | `XS_GLSR` `<<<` | 24h | 3.23 | +2.76 | +4.32 | +3.91 | 57.5 | +72% | -0.02 | -1 | log global account long/short ratio, cross-sec rank (retail crowding level) |
| 8 | `XS_AMIHUD` `<<<` | 24h | 3.21 | +2.84 | +1.98 | +1.71 | 40.9 | +34% | +0.19 | +1 | Amihud illiquidity (|r|/quote vol), 24h mean |
| 9 | `XS_FUND_PRE` `<<<` | 2h | 3.16 | -14.85 | +0.51 | -17.78 | 0.2 | -117% | -0.05 | -1 | funding rank held ONLY in the 2h BEFORE the 00/08/16 UTC settlement (capture window) |
| 10 | `XS_TAKER24` `<<<` | 24h | 3.15 | +1.41 | +2.64 | +1.12 | 9.6 | +19% | -0.11 | +1 | 24h taker buy-sell notional imbalance |
| 11 | `XS_QV_Z` `<<<` | 24h | 3.11 | +1.32 | +3.75 | +2.03 | 12.0 | +31% | +0.01 | +1 | z of log hourly quote volume vs 7d (volume shock) |
| 12 | `XS_LIQPROX` `<<<` | 24h | 3.11 | +2.06 | +3.00 | +1.98 | 16.2 | +36% | +0.14 | +1 | liquidation proximity: far from the 7d high and high realised vol |
| 13 | `XS_TAKER_Z` `<<<` | 24h | 3.08 | +0.69 | +1.54 | -0.79 | 3.6 | -10% | -0.00 | +1 | 24h taker imbalance z-scored against its own 7d history (flow surprise) |
| 14 | `XS_SMART_x_FUND` `<<<` | 24h | 2.86 | +2.15 | +1.07 | +0.23 | 7.0 | +3% | -0.10 | +1 | top traders long where funding is cheap (informed carry positioning) |
| 15 | `XS_NTR_Z` `<<<` | 24h | 2.80 | +1.04 | +3.37 | +1.77 | 11.6 | +28% | +0.01 | +1 | z of log hourly trade count vs 7d (attention shock) |
| 16 | `XS_RANGEPOS` | 24h | 2.72 | +0.45 | +2.56 | +0.73 | 7.7 | +12% | -0.12 | -1 | position of close inside the 24h high-low range, inverted |
| 17 | `XS_TSIZE` | 24h | 2.58 | +2.09 | +1.57 | +1.12 | 19.1 | +18% | -0.03 | +1 | log(top-trader POSITION ratio) - log(top-trader ACCOUNT ratio): size concentration |
| 18 | `XS_REV_VA` | 24h | 2.57 | +0.63 | +2.88 | +1.27 | 9.9 | +25% | -0.03 | -1 | 24h reversal scaled by own realised vol |
| 19 | `XS_FUND_VA` | 8h | 2.41 | +0.04 | +0.36 | -2.45 | 0.7 | -41% | +0.41 | -1 | funding rate divided by 24h realised vol (risk-adjusted carry) |
| 20 | `XS_MOM168` | 24h | 2.37 | +1.84 | +1.73 | +1.22 | 18.8 | +28% | +0.00 | +1 | 7d cross-sectional momentum |
| 21 | `XS_FUND_Z` | 8h | 2.23 | -1.37 | -0.38 | -4.37 | -0.5 | -61% | +0.17 | -1 | funding rate z-scored vs its own 30d history |
| 22 | `XS_TLSR` | 24h | 2.19 | +1.10 | +0.82 | -0.28 | 4.1 | -5% | -0.29 | +1 | Binance taker long/short volume ratio, 24h mean, cross-sec rank |
| 23 | `XS_TTS` | 24h | 2.16 | +1.61 | +4.48 | +4.16 | 75.7 | +73% | +0.01 | -1 | log top-trader POSITION long/short ratio |
| 24 | `TS_TOD_ASIA` | 8h | 2.15 | +0.64 | +0.19 | -0.90 | 0.9 | -67% | +0.62 | -1 | TIME-SERIES: long the basket 00-08 UTC, short 08-24 UTC (time-of-day) |
| 25 | `XS_OI24` | 24h | 2.12 | -0.15 | -0.95 | -3.20 | -2.3 | -43% | +0.03 | +1 | cross-sec rank of 24h log change in open interest (contracts) |
| 26 | `XS_FUND` | 8h | 2.11 | -0.72 | -0.01 | -3.56 | -0.0 | -48% | -0.03 | -1 | cross-sec rank of last settled funding rate, 8h hold |
| 27 | `XS_REV24` | 24h | 2.09 | +0.37 | +2.64 | +1.09 | 9.4 | +21% | +0.01 | -1 | 24h cross-sectional reversal |
| 28 | `XS_FUND_MINUS_RET` | 24h | 2.06 | +0.33 | +2.30 | +0.64 | 7.6 | +11% | -0.04 | -1 | expensive funding without the price move to justify it |
| 29 | `XS_OI_PLUS_RET` | 24h | 2.01 | +0.19 | +0.85 | -0.93 | 2.6 | -16% | -0.01 | +1 | z(OI growth) + z(24h return): new money chasing (fresh-leverage momentum) |
| 30 | `XS_OI72` | 24h | 1.99 | +0.75 | +0.07 | -1.13 | 0.3 | -17% | +0.08 | +1 | 72h log change in open interest |
| 31 | `XS_OI24_RANK` | 24h | 1.97 | -0.60 | -0.85 | -3.34 | -1.9 | -35% | +0.03 | +1 | OI-24h signal, full rank-weighted book |
| 32 | `TS_MKT_OI` | 24h | 1.70 | +1.31 | +1.54 | +1.27 | 30.5 | +83% | -0.21 | -1 | TIME-SERIES: sign of universe-mean 24h OI growth (z vs 30d), whole basket |
| 33 | `XS_FUND_CHG` | 24h | 1.66 | -0.53 | -0.98 | -3.40 | -2.2 | -37% | +0.15 | -1 | 3-day change in the funding rate (funding momentum) |
| 34 | `XS_OI_ACCEL` | 24h | 1.61 | -1.51 | +0.14 | -2.86 | 0.3 | -35% | +0.02 | +1 | second difference of OI: 24h OI change minus its own value 24h ago |
| 35 | `XS_VOLEXP` | 24h | 1.60 | +0.27 | +1.32 | -0.09 | 5.2 | -1% | -0.15 | +1 | volatility expansion: 24h realised vol relative to 7d realised vol |
| 36 | `TS_TOD_SETTLE` | 1h | 1.60 | -1.74 | +0.14 | -2.67 | 0.3 | -229% | +0.67 | -1 | TIME-SERIES: long the basket only in the settlement hour, short elsewhere |
| 37 | `XS_CHURN` | 24h | 1.55 | +0.95 | +2.81 | +2.26 | 27.9 | +47% | +0.43 | +1 | 24h quote volume / open-interest notional (position churn rate) |
| 38 | `XS_LOWVOL` | 24h | 1.36 | +1.21 | +1.09 | +0.94 | 40.1 | +26% | +0.57 | -1 | inverse 7d realised vol (bet-against-beta) |
| 39 | `XS_FUND_24` | 24h | 1.27 | +0.00 | -0.02 | -1.58 | -0.1 | -19% | -0.07 | -1 | same funding rank, 24h hold |
| 40 | `XS_REV4` | 4h | 1.26 | -8.77 | +1.62 | -8.40 | 0.9 | -154% | +0.12 | -1 | 4h cross-sectional reversal |
| 41 | `XS_FUND_RANK` | 8h | 1.24 | -1.88 | -0.17 | -3.75 | -0.3 | -41% | -0.05 | -1 | funding signal, full rank-weighted book |
| 42 | `XS_TLSR_Z` | 24h | 1.23 | -6.35 | -1.68 | -9.22 | -1.2 | -39% | +0.01 | +1 | taker long/short volume ratio z-scored vs its own 7d history |
| 43 | `XS_FUND_POST` | 2h | 1.13 | -16.31 | +1.21 | -16.27 | 0.4 | -112% | -0.02 | -1 | funding rank held ONLY in the 2h AFTER settlement (post-settlement reversion) |
| 44 | `XS_OI_NORM` | 24h | 0.98 | -0.94 | +1.41 | -0.57 | 3.9 | -8% | +0.37 | -1 | OI growth in excess of what its own price volatility explains |
| 45 | `XS_OI4` | 4h | 0.96 | -10.90 | -0.83 | -13.11 | -0.4 | -184% | +0.07 | +1 | 4h log change in open interest, 4h hold |
| 46 | `XS_TAKER_DIV` | 24h | 0.90 | -1.19 | +0.74 | -1.28 | 2.0 | -18% | +0.20 | -1 | aggressive buying that did NOT move price (absorbed flow divergence) |
| 47 | `XS_FUND_x_OI` | 24h | 0.89 | -1.21 | -0.08 | -2.27 | -0.2 | -29% | +0.12 | +1 | high funding AND rising OI: leverage piling into an expensive side |
| 48 | `XS_ATS_REV` | 24h | 0.88 | -1.64 | +0.26 | -2.29 | 0.6 | -27% | +0.05 | -1 | big prints against the 24h move (whale accumulation into weakness) |
| 49 | `XS_TRAPPED` | 24h | 0.85 | -0.50 | -1.38 | -2.51 | -6.7 | -50% | +0.48 | -1 | deep below the 7d high while OI keeps growing: trapped longs |
| 50 | `XS_OI_MINUS_RET` | 24h | 0.52 | -1.69 | +2.38 | +0.38 | 6.5 | +6% | +0.01 | -1 | z(OI growth) - z(24h return): OI built while price fell (trapped/crowded shorts) |
| 51 | `XS_SQUEEZE` | 24h | 0.52 | -1.69 | +2.38 | +0.38 | 6.5 | +6% | +0.01 | +1 | OI destroyed while price rose: short-squeeze covering signature |
| 52 | `TS_MKT_TAKER` | 24h | 0.38 | +0.04 | -1.26 | -1.53 | -26.6 | -100% | -0.08 | -1 | TIME-SERIES: sign of universe-mean taker imbalance (z vs 30d), whole basket |
| 53 | `XS_OI_PER_VOL` | 24h | 0.28 | -2.44 | +3.26 | +0.81 | 7.3 | +10% | -0.06 | -1 | OI growth in excess of the volume shock that produced it |
| 54 | `XS_TTS_Z` | 24h | 0.26 | -1.62 | -1.56 | -3.22 | -5.2 | -39% | +0.07 | +1 | top-trader position ratio z vs own 7d |
| 55 | `XS_TAKER1` | 4h | 0.09 | -25.23 | +2.32 | -20.01 | 0.6 | -167% | +0.02 | +1 | 1h taker buy-sell notional imbalance, 4h hold |
| 56 | `TS_MKT_FUND` | 8h | 0.07 | -0.27 | +0.87 | +0.62 | 19.0 | +48% | +0.02 | +1 | TIME-SERIES: sign of universe-mean funding z-scored vs 30d, applied to the whole basket |

## What the held-out window killed

| family | design | held out | verdict |
|---|---|---|---|
| **funding carry** (`XS_FUND`, `_Z`, `_CHG`, `_24`, `_RANK`, `_VA`, `_PRE`, `_POST`, `TS_MKT_FUND`) | gross SR 1.1-3.2 | gross SR -0.4 to +1.2, **every one net-negative** | **DEAD**. Consistent with this programme's four prior carry deaths. `XS_FUND_PRE` had design gross 3.16 but breaks even at 1.0 bp/side -- it was never tradeable. |
| **open interest** (`XS_OI24`, `_72`, `_4`, `_ACCEL`, `_RANK`, `_PLUS_RET`, `_MINUS_RET`) | gross SR 0.5-2.1 | gross SR -1.0 to +0.9 | **DEAD**. Same verdict the Orphan Flush got. |
| **24h-change positioning** (`XS_SMART_CHG`, `XS_GLSR_CHG`) | gross SR **4.10 / 4.05** -- ranks 2 and 3 | gross **0.87 / 1.26**, net -1.74 / -1.13 | **DEAD**. The clearest overfit in the sweep: two of the three best design formulas collapsed. |
| **short-horizon flow** (`XS_TAKER1`, `XS_OI4`, `XS_REV4`, `TS_TOD_SETTLE`) | -- | -- | **DEAD on cost**. Breakeven 0.0-2.6 bp/side against a 4.5 bp published fee. Turnover 8-12x/day. |
| **positioning level** (`XS_GLSR`, `XS_GLSR_Z`, `XS_SMART`, `XS_TSIZE`, `XS_TTS`, `XS_CROWD_UNWIND`) | gross SR 2.2-4.9 | gross SR **1.9-4.5, all net-positive** | **SURVIVES.** |

## Capacity / cost robustness on the shortlist

The headline universe is top-120 by volume, whose tail is thin. Re-running the shortlist on the
**top-50** (where a 5.5 bp/side assumption is actually defensible) and at a **15 bp/side** cost shock:

| formula | d net @120 | o net @120 | o net @120, 15bp | d net @**50** | o net @**50** | o net @50, 15bp | survives liquidity cut? |
|---|---|---|---|---|---|---|---|
| `XS_SMART` | +2.74 | +1.42 | +0.61 | +3.29 | +1.53 | +0.80 | **yes** |
| `XS_GLSR` | +2.76 | +3.91 | +3.19 | +2.84 | +1.34 | +0.65 | **yes** |
| `XS_GLSR_Z` | +3.37 | +2.38 | -0.28 | +2.58 | +0.73 | -1.19 | **yes** |
| `XS_CROWD_UNWIND` | +2.65 | +1.63 | -0.54 | +2.20 | -0.64 | -2.35 | no |
| `XS_TAKER24` | +1.41 | +1.12 | -1.50 | +1.03 | +0.32 | -1.67 | no |
| `XS_AMIHUD` | +2.84 | +1.71 | +1.25 | -0.36 | -2.73 | -3.31 | no |
| `XS_LIQPROX` | +2.06 | +1.98 | +0.22 | +0.41 | +0.23 | -0.96 | no |
| `XS_QV_Z` | +1.32 | +2.03 | -0.94 | -0.33 | -0.59 | -2.77 | no |
| `XS_NTR_Z` | +1.04 | +1.77 | -1.00 | -0.38 | -0.70 | -2.73 | no |
| `XS_ATS_Z` | +1.31 | +1.55 | -2.86 | -0.40 | -1.71 | -4.78 | no |
| `XS_SMART_CHG` | +1.48 | -1.74 | -6.23 | +1.59 | -1.34 | -4.43 | no |
| `XS_FUND` | -0.72 | -3.56 | -9.68 | -0.32 | -3.59 | -7.87 | no |

This is the most important table in the sweep. `XS_AMIHUD` (design net 2.84, OOS net 1.71) goes to
**-2.73 OOS** on the top-50: it was an illiquidity tilt inside the tail of the universe, not an edge.
`XS_QV_Z`, `XS_NTR_Z`, `XS_ATS_Z`, `XS_LIQPROX` and `XS_CROWD_UNWIND` do the same thing. Only the
**account-positioning level** signals hold up where the fills are real.

## The one thing that survived everything

**`XS_SMART`** -- long names where the top-trader POSITION long/short ratio is high relative to the
global RETAIL account long/short ratio, short the reverse. `signal = log(sum_toptrader_long_short_ratio)
- log(count_long_short_ratio)`, cross-sectional quintile book, 24h hold, both fields straight off
Binance's 5m futures-metrics feed.

| | design | held out |
|---|---|---|
| gross Sharpe, top-120 | 3.25 | 1.90 |
| net Sharpe @5.5 bp, top-120 | +2.74 | +1.42 |
| net Sharpe @5.5 bp, **top-50** | +3.29 | +1.53 |
| net Sharpe @15 bp, **top-50** | +2.64 | +0.80 |
| ann. net return, top-120 | +50.4% | +22.1% |
| breakeven cost, top-120 held out | | 22.1 bp/side |
| turnover | 0.47 x/day | |
| corr to equal-weight basket | -0.04 | |

It was 6th on design, not 1st -- the design winner `XS_GLSR_Z` (design gross 4.94 / net 3.37;
held out gross 3.92 / net 2.38, +34.5%/yr, breakeven 14.0 bp/side) also repeated, but loses half its
held-out Sharpe on the top-50 cut (net +0.73) where `XS_SMART` keeps +1.53.

## Honest caveats

1. **One held-out regime.** Apr-Dec 2024, 275 days. It is one draw, not a walk-forward.
2. **The cost is declared, not measured.** 4.5 bp is a published fee; the 1.0 bp half-spread is an
   assumption. Breakeven and a 15 bp shock are reported so the reader can move it. `XS_SMART` on the
   top-50 still nets +0.80 OOS at 15 bp/side; nothing else in the sweep does.
3. **No book-depth impact model.** `orphanflush_cache/bookdepth` has +-1%..+-5% notional for 264
   symbols and was NOT used here. Sizing this to real capital needs it.
4. **The metrics cache forces the window.** Binance futures-metrics coverage in the cache is dense
   only 2023-01 -> 2024-12; 2022 is nearly empty and 2025+ is thin (~30 symbols). That is why the
   design and held-out windows are what they are, and why there is no 2025-26 confirmation.
5. **Two survivors are one hypothesis.** `XS_SMART`, `XS_GLSR`, `XS_GLSR_Z`, `XS_TTS` and `XS_TSIZE`
   are all built from the same two Binance long/short-ratio fields. Count them as ONE idea that
   passed, not five.
6. **15 of 56 cleared the design bar**, which means the bar was doing its job as a filter but the
   theme is heterogeneous: a real sub-family plus a lot of illiquidity-tilt artifacts.

## Files

- `scripts/trading_bot/perpmicro_panel.py` -- builds `research/data/perpmicro_cache/panel1h.npz` (265 x 27048)
- `scripts/trading_bot/perpmicro_sweep.py` -- the sweep harness (formula catalogue in `catalogue()`)
- `research/trading_bot/SWEEP_crypto_perp_microstructure_DESIGN_FROZEN.json` -- design results, frozen before the holdout ran
- `research/trading_bot/SWEEP_crypto_perp_microstructure.json` -- design + held out
- `research/trading_bot/SWEEP_crypto_perp_microstructure_ROBUSTNESS.json` -- top-50 / cost-shock grid
