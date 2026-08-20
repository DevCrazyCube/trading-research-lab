# SWEEP — intraday equity/ETF relative value & mean reversion

## Verdict: the theme is DEAD, and it dies in an unusually informative way

**98 structurally different formulas** were scored on the design window. **Zero** of them are net-positive at the headline 1.0 bp/side cost rung. The best is `D1_gap_rev_mega` at **-0.27**, against a noise bar — the 95th percentile of best-of-98 Sharpe when nothing has an edge — of **+2.01**. The winner is not near the bar; it is 2.3 Sharpe units below it.

But the interesting part is *why*, and it is not "there is no signal":

- **Before costs the signal is real, large, and it replicates out of sample.** 50 of 98 configs beat the *gross* noise bar (+1.59). The best gross design Sharpe is **+6.86** (`A2_pair_z_intraday`), and the same formula prints **+5.41** gross on the held-out window.
- **The edge is smaller than the friction by one to two orders of magnitude.** `A2_pair_z_intraday` can bear a total charge of **0.031 bp per unit of turnover** before its gross edge is exactly consumed. The headline rung charges 1.15 bp — **37× more** than the edge can pay. It is worse than that: the SEC 31 + FINRA TAF pass-through **alone** is 0.15 bp, so this formula cannot cover the regulatory fee, never mind the spread. The repo's own measured half-spread for liquid names is 1.13 bp and the tightest mega-cap ETF is ~0.2–0.5 bp; there is no venue at which this closes.
- **82 of 98** configs cannot pay even the 0.15 bp regulatory floor out of their gross edge.
- Only **3 of 98** configs are positive even at the 0.5 bp/side rung, and the best of those reaches +0.22 — still far under the noise bar.

Mean reversion between ETF siblings and across the short-horizon equity cross-section is not a mispricing that a taker can harvest. It is, to a very good approximation, the bid-ask bounce itself: the thing being measured *is* the spread, which is why the measurement is stable and the trade is impossible.

## This was predictable before any strategy was scored

`rv_census.py` measured how far each same-claim pair's log ratio travels from its own 78-bar trailing mean, on the design window, **before** any config ran. A two-leg pair trade crosses four half-spreads per round trip, so at the headline rung it must capture **4.60 bp** to break even.

| pair | sd of dislocation (bp) | p95 \|dislocation\| (bp) | p95 ÷ round-trip cost | ac(1) |
|---|---|---|---|---|
| SPY/IVV | 0.79 | 1.51 | 0.33 | +0.141 |
| SPY/VOO | 0.79 | 1.52 | 0.33 | +0.113 |
| IVV/VOO | 0.79 | 1.58 | 0.34 | +0.048 |
| GLD/IAU | 1.31 | 2.58 | 0.56 | +0.083 |
| SPY/SPLG | 1.32 | 2.61 | 0.57 | +0.055 |
| AGG/BND | 1.55 | 3.08 | 0.67 | +0.703 |
| VTI/ITOT | 1.68 | 3.23 | 0.70 | +0.234 |
| GLD/GLDM | 1.89 | 3.77 | 0.82 | +0.052 |
| … | | | | |
| XLI/VIS | 10.41 | 21.26 | 4.62 | +0.710 |
| XLV/VHT | 10.84 | 22.67 | 4.93 | +0.870 |
| XLY/VCR | 12.81 | 25.73 | 5.59 | +0.662 |
| SMH/SOXX | 17.89 | 35.56 | 7.73 | +0.962 |

The genuinely same-claim pairs — SPY/IVV/VOO, the ones where the arbitrage argument is airtight — sit at the top of that table with sub-2 bp p95 dislocations and one-bar autocorrelations near zero: the displacement does not survive a single bar, because it is non-synchronous prints rather than a dislocation. The pairs further down the table have larger, more persistent spreads precisely because they are *not* the same claim (XLK vs VGT hold different books), so there is no arbitrage force pulling them together and the 'reversion' is a bet, not a convergence.

## Method

- **Design** 2021-01-04 .. 2024-12-31 (1005 sessions). **Held out** 2025-01-02 .. 2026-08-15 (405 sessions), untouched until the shortlist was frozen.
- **Universe** 132 symbols, Alpaca SIP 5-minute bars, RTH only, `adjustment=all`. Same-claim ETF clusters, SPDR/Vanguard sector twins, style and regional ETFs, levered/inverse funds, 30+ mega-caps. Survivorship-biased (every ETF is alive today) and price levels are not point-in-time; no config filters on a level.
- **Execution** signal from closes through bar t-1, fill at bar-t VWAP, return vwap[t+1]/vwap[t]-1. Flat at every close.
- **Costs** [0.5, 1.0, 2.0, 2.5] bp/side on `|Δw|`, headline 1.0 bp, plus 0.15 bp/turnover for SEC 31 + FINRA TAF. Borrow 0.0 — zero because every config is flat at the closing bar; US borrow fees accrue overnight. A variant that held overnight would owe B22G's measured 0.33%/yr ETB median and is not what was tested here.
- **Cost provenance** ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG -- repo-measured liquid-name close half-spread is 1.13 bp (t3, 19,835 symbol-days); intraday mega-cap ETF spreads are tighter, so 1.0 bp/side is conservative. The 2.5 bp rung is retail_taker_costs()'s own default half-spread.
- **Harness self-test** (`rv_selftest.py`): recovers a planted OU dislocation at gross Sharpe +12.45, flips to -12.45 under negation, and returns -0.34 on a random-walk spread with nothing to find. All three checks pass.

## The noise bar

Best-of-98 Sharpe under H0, from a stationary block bootstrap (block = 5 days, 500 resamples) of each config's *demeaned* daily net PnL, drawing the same day indices for every config so the sweep's internal correlation survives:

| statistic | net (1.0 bp) | gross |
|---|---|---|
| mean | +1.31 | +1.17 |
| p95 | +2.01 | +1.59 |
| p99 | +2.47 | +1.83 |
| naive √(2 ln N)/√years | +1.52 | — |

## Distribution of design results (all 98 configs)

| basis | min | p10 | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|---|
| gross (0 bp) | -3.11 | -0.38 | +0.43 | +1.70 | +3.29 | +5.62 | +6.86 |
| net 0.5 bp/side | -224.31 | -158.89 | -73.31 | -15.65 | -5.16 | -1.16 | +0.22 |
| net 1.0 bp/side | -314.92 | -215.99 | -93.01 | -28.20 | -10.11 | -1.97 | -0.27 |
| net 2.0 bp/side | -406.32 | -236.32 | -124.30 | -50.74 | -19.79 | -3.09 | -0.87 |
| net 2.5 bp/side | -434.56 | -247.14 | -132.08 | -62.50 | -22.52 | -3.66 | -1.18 |

The net rows are not close calls. The median config loses ~28 Sharpe units to friction.

## Held-out (pre-registered shortlist)

Nothing cleared the p95 bar, so per §5 of the pre-registration these ran out of sample as a **documented negative control**, not as candidates. The two highest-*gross* formulas were added, labelled, to test whether the before-cost signal itself persists — it does.

| formula | design gross | HELD-OUT gross | design net 1bp | HELD-OUT net 1bp | break-even bp/turnover |
|---|---|---|---|---|---|
| `D1_gap_rev_mega` | +0.43 | +0.64 | -0.27 | +0.06 | 0.711 |
| `I5_xs_rev_mega_lb6_hold39` | +0.88 | +0.21 | -0.29 | -0.75 | 0.862 |
| `D4_first30_rev_mega` | -0.15 | -0.80 | -1.01 | -1.53 | -0.199 |
| `A2_pair_z_intraday` | +6.86 | +5.41 | -252.58 | -197.97 | 0.031 |
| `C1_xs_rev_mega_lb1` | +6.09 | +4.79 | -33.71 | -28.49 | 0.175 |

The gross column is the finding: the mean-reversion signal is stable across a four-year design window and a twenty-month held-out window. The net column is the verdict: it is unreachable.

## Every formula, ranked by net design Sharpe at 1.0 bp/side

| # | formula | kind | turn/day | break-even bp/turnover | gross | net 0.5bp | net 1bp | net 2bp | net 2.5bp | HELD-OUT net 1bp |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `D1_gap_rev_mega` | gap_reversal | 2.0 | 0.711 | +0.43 | +0.04 | -0.27 | -0.87 | -1.18 | +0.06 |
| 2 | `D3_gap_resid_rev_mega` | gap_resid_reversal | 2.0 | 0.711 | +0.43 | +0.04 | -0.27 | -0.87 | -1.18 | +0.06 |
| 3 | `I5_xs_rev_mega_lb6_hold39` | xs_reversal | 3.5 | 0.862 | +0.88 | +0.22 | -0.29 | -1.32 | -1.83 | -0.75 |
| 4 | `D4_first30_rev_mega` | first30_reversal | 2.0 | -0.199 | -0.15 | -0.63 | -1.01 | -1.76 | -2.13 | -1.53 |
| 5 | `D2_gap_cont_mega` | gap_continuation | 2.0 | -0.711 | -0.43 | -0.83 | -1.13 | -1.74 | -2.04 | — |
| 6 | `I4_xs_rev_etf_lb6_hold39` | xs_reversal | 3.5 | 0.390 | +0.61 | -0.40 | -1.18 | -2.74 | -3.52 | — |
| 7 | `D2_gap_cont_etf` | gap_continuation | 2.0 | 0.191 | +0.24 | -0.58 | -1.22 | -2.49 | -3.13 | — |
| 8 | `D1b_gap_rev_etf_hold78` | gap_reversal | 2.1 | -0.579 | -0.47 | -0.99 | -1.39 | -2.20 | -2.60 | — |
| 9 | `D1_gap_rev_etf` | gap_reversal | 2.0 | -0.191 | -0.24 | -1.07 | -1.70 | -2.98 | -3.61 | — |
| 10 | `D3_gap_resid_rev_etf` | gap_resid_reversal | 2.0 | -0.191 | -0.24 | -1.07 | -1.70 | -2.98 | -3.61 | — |
| 11 | `D4_first30_rev_etf` | first30_reversal | 2.1 | -0.793 | -0.85 | -1.54 | -2.08 | -3.15 | -3.68 | — |
| 12 | `I6_vwap_rev_etf_hold13` | vwap_reversion | 6.3 | 0.182 | +0.47 | -1.19 | -2.48 | -5.10 | -6.42 | — |
| 13 | `I5_xs_rev_mega_lb6_hold13` | xs_reversal | 9.1 | 0.110 | +0.29 | -1.41 | -2.73 | -5.38 | -6.71 | — |
| 14 | `I3_etfbasket_band_w390_e2_x0.5` | etf_basket_band | 3.6 | 0.122 | +0.43 | -1.85 | -3.61 | -7.11 | -8.84 | — |
| 15 | `I4_xs_rev_etf_lb6_hold13` | xs_reversal | 9.1 | 0.101 | +0.37 | -2.02 | -3.88 | -7.62 | -9.50 | — |
| 16 | `C6_xs_rev_etf_lb6_open` | xs_reversal | 2.0 | -0.063 | -0.22 | -2.50 | -4.25 | -7.75 | -9.49 | — |
| 17 | `I8_resid_rev_etf_lb12_hold13` | resid_reversal | 7.7 | 0.223 | +1.05 | -1.97 | -4.33 | -9.13 | -11.56 | — |
| 18 | `D4b_first30_rev_etf_close` | first30_reversal | 2.0 | 0.036 | +0.16 | -2.68 | -4.86 | -9.22 | -11.40 | — |
| 19 | `F1_triplet_resid_w390` | triplet_resid | 5.0 | -0.090 | -0.36 | -2.95 | -4.89 | -8.24 | -9.54 | — |
| 20 | `G1_vwap_rev_mega` | vwap_reversion | 23.2 | 0.275 | +1.80 | -2.35 | -5.67 | -12.64 | -16.30 | — |
| 21 | `I5_xs_rev_mega_lb6_hold6` | xs_reversal | 18.1 | 0.097 | +0.55 | -3.16 | -6.03 | -11.85 | -14.79 | — |
| 22 | `I4_xs_rev_etf_lb6_hold6` | xs_reversal | 18.1 | 0.079 | +0.66 | -4.72 | -8.92 | -17.51 | -21.90 | — |
| 23 | `B4_spy_vs_sectors_w390` | spy_vs_sector_composite | 5.3 | -0.091 | -0.70 | -5.76 | -9.55 | -13.93 | -14.71 | — |
| 24 | `F1_triplet_resid_w78` | triplet_resid | 10.4 | -0.024 | -0.20 | -5.74 | -9.77 | -15.77 | -17.66 | — |
| 25 | `G1_vwap_rev_sector` | vwap_reversion | 24.0 | 0.172 | +1.80 | -4.69 | -10.11 | -22.14 | -28.78 | — |
| 26 | `G1b_vwap_rev_etf_after10` | vwap_reversion | 19.1 | 0.104 | +1.02 | -5.10 | -10.13 | -21.07 | -26.96 | — |
| 27 | `G1_vwap_rev_etf` | vwap_reversion | 24.1 | 0.131 | +1.34 | -5.11 | -10.40 | -21.82 | -27.98 | — |
| 28 | `C7_xs_rev_etf_lb6_close` | xs_reversal | 4.5 | -0.071 | -0.61 | -6.20 | -10.62 | -19.72 | -24.38 | — |
| 29 | `C1_xs_rev_mega_lb12` | xs_reversal | 31.6 | 0.147 | +1.60 | -5.31 | -10.80 | -22.25 | -28.20 | — |
| 30 | `C2_resid_rev_mega_lb12` | resid_reversal | 29.5 | 0.154 | +1.87 | -5.89 | -12.05 | -24.83 | -31.41 | — |
| 31 | `B1_etf_vs_basket_w390` | etf_vs_basket | 8.8 | 0.054 | +0.69 | -7.37 | -13.95 | -27.11 | -33.17 | — |
| 32 | `C1_xs_rev_mega_lb6` | xs_reversal | 45.6 | 0.169 | +2.55 | -7.07 | -14.71 | -30.59 | -38.83 | — |
| 33 | `C1_xs_rev_mega_lb3` | xs_reversal | 64.2 | 0.251 | +4.73 | -7.35 | -16.87 | -36.51 | -46.61 | — |
| 34 | `F2b_pca_resid_lb12` | pca_resid | 34.9 | 0.088 | +1.44 | -8.89 | -17.34 | -35.37 | -44.82 | — |
| 35 | `C9b_xs_rev_mega_lb6_rank` | xs_reversal | 42.6 | 0.155 | +2.79 | -8.70 | -17.89 | -37.15 | -47.20 | — |
| 36 | `C1_xs_rev_etf_lb12` | xs_reversal | 31.8 | 0.085 | +1.49 | -9.51 | -18.45 | -37.52 | -47.60 | — |
| 37 | `C3b_xs_rev_mega_lb6_vol` | xs_reversal | 45.7 | 0.156 | +2.98 | -9.14 | -18.82 | -39.02 | -49.47 | — |
| 38 | `B4_spy_vs_sectors_w78` | spy_vs_sector_composite | 10.0 | 0.002 | +0.04 | -10.02 | -18.87 | -26.74 | -26.92 | — |
| 39 | `C2_resid_rev_etf_lb12` | resid_reversal | 29.9 | 0.118 | +2.18 | -9.49 | -18.95 | -38.93 | -49.29 | — |
| 40 | `I2_levered_band_w390_e2_x0.5` | levered_resid_band | 12.9 | -0.070 | -1.13 | -16.41 | -19.01 | -20.02 | -20.14 | — |
| 41 | `C1_xs_rev_sector_lb12` | xs_reversal | 31.9 | 0.083 | +1.51 | -9.86 | -19.19 | -39.23 | -49.82 | — |
| 42 | `C8_xs_rev_etf_lb6_mid` | xs_reversal | 23.2 | 0.104 | +1.93 | -9.72 | -19.24 | -39.74 | -50.71 | — |
| 43 | `C2_resid_rev_mega_lb3` | resid_reversal | 62.1 | 0.209 | +4.50 | -9.27 | -20.09 | -42.05 | -53.08 | — |
| 44 | `C4_xs_rev_etf_lb6_hivol` | xs_reversal | 55.7 | 0.019 | +0.40 | -14.27 | -23.58 | -35.83 | -39.54 | — |
| 45 | `F2_pca_resid_lb6` | pca_resid | 47.4 | 0.033 | +0.74 | -13.28 | -24.71 | -48.88 | -61.37 | — |
| 46 | `C1_xs_rev_etf_lb6` | xs_reversal | 45.9 | 0.062 | +1.41 | -13.09 | -24.89 | -50.17 | -63.62 | — |
| 47 | `C1_xs_rev_sector_lb6` | xs_reversal | 45.7 | 0.027 | +0.61 | -13.84 | -25.72 | -51.31 | -64.90 | — |
| 48 | `C2c_resid_rev_sector_lb6` | resid_reversal | 43.6 | 0.037 | +0.87 | -14.05 | -26.33 | -52.43 | -65.91 | — |
| 49 | `A7_levered_resid_w390` | levered_resid | 32.4 | -0.006 | -0.15 | -25.86 | -26.90 | -27.08 | -27.07 | — |
| 50 | `C1_xs_rev_sector_lb3` | xs_reversal | 64.0 | 0.083 | +2.31 | -15.26 | -29.50 | -59.75 | -75.61 | — |
| 51 | `C9_xs_rev_etf_lb6_rank` | xs_reversal | 42.3 | 0.039 | +1.06 | -15.85 | -29.76 | -59.88 | -76.01 | — |
| 52 | `C1_xs_rev_etf_lb3` | xs_reversal | 64.5 | 0.113 | +3.34 | -15.44 | -30.51 | -62.22 | -78.81 | — |
| 53 | `C3_xs_rev_etf_lb6_vol` | xs_reversal | 46.0 | 0.051 | +1.45 | -16.44 | -31.07 | -62.28 | -78.59 | — |
| 54 | `C2_resid_rev_etf_lb3` | resid_reversal | 62.6 | 0.107 | +3.38 | -16.77 | -32.80 | -65.38 | -81.49 | — |
| 55 | `B1_etf_vs_basket_w78` | etf_vs_basket | 18.5 | 0.078 | +2.47 | -16.11 | -33.32 | -69.43 | -83.71 | — |
| 56 | `C1_xs_rev_mega_lb1` | xs_reversal | 109.2 | 0.175 | +6.09 | -16.21 | -33.71 | -69.53 | -87.81 | -28.49 |
| 57 | `H3b_spy_leads_sectors_beta_rev` | spy_leads_sectors | 78.5 | 0.065 | +2.07 | -18.99 | -34.61 | -61.24 | -71.61 | — |
| 58 | `H3_spy_leads_sectors_beta` | spy_leads_sectors | 78.5 | -0.070 | -2.07 | -22.15 | -35.96 | -58.11 | -66.55 | — |
| 59 | `I1_pair_band_w390_e2.5_x1.0` | pair_z_band | 23.1 | 0.045 | +1.47 | -28.26 | -36.55 | -41.01 | -41.69 | — |
| 60 | `C5_xs_rev_etf_lb6_lovol` | xs_reversal | 65.8 | 0.041 | +1.37 | -20.53 | -36.70 | -65.19 | -77.00 | — |
| 61 | `I2b_levered_band_w78_e2_x0.5` | levered_resid_band | 36.2 | 0.013 | +0.48 | -36.11 | -42.41 | -44.73 | -44.97 | — |
| 62 | `I7_pair_z_w390_hold13` | pair_z | 6.6 | 0.048 | +2.04 | -26.08 | -46.93 | -80.32 | -92.01 | — |
| 63 | `B1_etf_vs_basket_w39` | etf_vs_basket | 26.8 | 0.067 | +3.07 | -23.69 | -48.63 | -101.38 | -122.27 | — |
| 64 | `I1_pair_band_w390_e2.0_x0.5` | pair_z_band | 21.2 | 0.047 | +2.14 | -39.24 | -51.55 | -57.81 | -58.65 | — |
| 65 | `C1_xs_rev_sector_lb1` | xs_reversal | 107.7 | 0.031 | +1.53 | -30.46 | -55.90 | -107.64 | -133.21 | — |
| 66 | `C1_xs_rev_etf_lb1` | xs_reversal | 109.2 | 0.062 | +3.34 | -31.12 | -58.37 | -114.31 | -142.76 | — |
| 67 | `I1_pair_band_w78_e2.5_x1.0` | pair_z_band | 32.7 | 0.042 | +2.34 | -46.68 | -62.26 | -70.15 | -71.15 | — |
| 68 | `A7_levered_resid_w78` | levered_resid | 73.1 | 0.048 | +2.88 | -63.87 | -68.58 | -69.39 | -69.33 | — |
| 69 | `I1_pair_band_w390_e1.5_x0.25` | pair_z_band | 20.1 | 0.038 | +2.46 | -51.92 | -73.20 | -87.16 | -89.44 | — |
| 70 | `I1_pair_band_w78_e2.0_x0.5` | pair_z_band | 30.0 | 0.041 | +2.83 | -60.52 | -77.95 | -84.38 | -84.79 | — |
| 71 | `A6_pair_beta_resid_w390` | pair_beta_resid | 30.6 | 0.048 | +3.36 | -71.06 | -79.24 | -81.74 | -81.95 | — |
| 72 | `B3_etf_leads_basket_l3` | etf_leads_basket | 63.2 | -0.022 | -1.53 | -47.86 | -79.80 | -129.15 | -146.79 | — |
| 73 | `B2_basket_leads_etf_l3` | basket_leads_etf | 63.1 | 0.033 | +2.48 | -46.02 | -82.84 | -145.95 | -170.07 | — |
| 74 | `A4_pair_open_anchor` | pair_open_anchor | 39.5 | 0.026 | +2.25 | -74.06 | -96.40 | -105.78 | -106.60 | — |
| 75 | `I1_pair_band_w78_e1.5_x0.25` | pair_z_band | 26.9 | 0.037 | +3.63 | -79.55 | -110.93 | -126.98 | -128.69 | — |
| 76 | `E1_leadlag_l6` | leadlag | 45.1 | 0.035 | +3.47 | -84.60 | -112.27 | -130.99 | -134.62 | — |
| 77 | `H1b_pair_z_hlgate_w390_hl60` | pair_z_hlgate | 53.1 | 0.047 | +4.68 | -101.04 | -113.64 | -117.92 | -118.36 | — |
| 78 | `A1c_pair_z_w78_thr2` | pair_z | 88.5 | 0.033 | +3.47 | -91.16 | -118.45 | -132.73 | -134.78 | — |
| 79 | `A1_pair_z_w234` | pair_z | 50.9 | 0.048 | +5.30 | -112.41 | -124.45 | -126.43 | -126.21 | — |
| 80 | `A6_pair_beta_resid_w78` | pair_beta_resid | 48.8 | 0.046 | +5.61 | -122.30 | -138.72 | -143.00 | -143.15 | — |
| 81 | `A5_pair_ewma_z_hl78` | pair_ewma_z | 58.6 | 0.045 | +5.50 | -124.03 | -138.83 | -142.02 | -141.97 | — |
| 82 | `B2_basket_leads_etf_l1` | basket_leads_etf | 105.5 | 0.033 | +4.23 | -82.11 | -142.30 | -230.05 | -258.29 | — |
| 83 | `B3_etf_leads_basket_l1` | etf_leads_basket | 106.1 | -0.022 | -2.71 | -89.12 | -143.94 | -215.56 | -236.89 | — |
| 84 | `A1b_pair_z_w78_thr1` | pair_z | 79.5 | 0.041 | +6.03 | -146.73 | -167.79 | -172.09 | -171.89 | — |
| 85 | `E1_leadlag_l2` | leadlag | 75.2 | 0.020 | +3.14 | -122.50 | -178.53 | -226.96 | -237.55 | — |
| 86 | `A1_pair_z_w78` | pair_z | 63.7 | 0.038 | +6.25 | -158.53 | -184.87 | -191.42 | -191.45 | — |
| 87 | `H1_pair_z_hlgate_w78_hl30` | pair_z_hlgate | 66.5 | 0.035 | +6.16 | -163.94 | -198.58 | -212.22 | -213.67 | — |
| 88 | `E1_leadlag_l1` | leadlag | 104.7 | 0.017 | +3.11 | -146.79 | -213.69 | -271.31 | -283.85 | — |
| 89 | `A5_pair_ewma_z_hl20` | pair_ewma_z | 75.1 | 0.034 | +6.57 | -182.33 | -221.35 | -234.43 | -235.29 | — |
| 90 | `A2b_pair_z_intraday_thr1` | pair_z_intraday | 91.1 | 0.032 | +6.34 | -180.37 | -223.74 | -240.74 | -242.36 | — |
| 91 | `E2_leadlag_l1_rev` | leadlag | 104.7 | -0.016 | -3.11 | -158.60 | -229.10 | -285.99 | -297.12 | — |
| 92 | `A1_pair_z_w39` | pair_z | 74.4 | 0.031 | +6.48 | -190.01 | -239.17 | -258.29 | -259.94 | — |
| 93 | `A3_pair_bar_reversal_l6` | pair_bar_reversal | 92.9 | 0.016 | +3.48 | -159.56 | -240.41 | -306.70 | -319.08 | — |
| 94 | `H2_pair_z_riskparity_w78` | pair_z_riskparity | 80.3 | 0.028 | +6.13 | -199.08 | -249.06 | -275.64 | -279.88 | — |
| 95 | `A2_pair_z_intraday` | pair_z_intraday | 73.3 | 0.031 | +6.86 | -202.18 | -252.58 | -272.50 | -274.36 | -197.97 |
| 96 | `A3_pair_bar_reversal_l2` | pair_bar_reversal | 105.5 | 0.012 | +2.87 | -174.02 | -279.95 | -399.93 | -430.40 | — |
| 97 | `A3_pair_bar_reversal_l1` | pair_bar_reversal | 129.4 | 0.010 | +2.45 | -187.90 | -293.42 | -406.32 | -434.56 | — |
| 98 | `A1_pair_z_w12` | pair_z | 90.1 | 0.020 | +5.65 | -224.31 | -314.92 | -373.84 | -383.25 | — |

## Known redundancy, disclosed

`D1_gap_rev_mega` and `D3_gap_resid_rev_mega` return identical numbers: subtracting the cross-sectional mean gap before a dollar-neutralising demean is a no-op. That is one formula counted twice, so the effective N is 97, not 98. It moves the noise bar by less than 0.01 and is recorded rather than quietly deduplicated.

## Artifacts

| what | path |
|---|---|
| pre-registration | `research/trading_bot/SWEEP_intraday_rv_PREREGISTRATION.md` |
| design results | `research/trading_bot/SWEEP_intraday_rv_design.json` |
| held-out results | `research/trading_bot/SWEEP_intraday_rv_heldout.json` |
| feasibility census | `research/trading_bot/SWEEP_intraday_rv_census.json` |
| harness self-test | `research/trading_bot/SWEEP_intraday_rv_selftest.json` |
| combined | `research/trading_bot/SWEEP_intraday_rv.json` |
| fetch / panel / sweep code | `scripts/trading_bot/rv_*.py` |
| 5-min bar cache | `research/data/rv_cache/ (132 .npz + panel_rv.npz)` |

