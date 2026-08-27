# SWEEP — overnight-equity signals (the T3 family)

**51 structurally different overnight formulas, designed on 2016–2021, held out 2022-01-03 → 2026-08-14.**

Built from `research/data/t3_cache` only — official SIP opening/closing auction prints, the
15:29 / 15:49 / 15:59 last trades, monthly dollar-ADV and the corporate-action calendar.
No network call, no new data purchase. 1,179,206 valid symbol-nights on a point-in-time
top-500-ADV universe.

Harness: `scripts/trading_bot/t26_overnight_panel.py` (dense npz panel) +
`t26_overnight_sweep.py` (sweep / joint null / held-out) + `t26_overnight_diag.py` +
`t26_overnight_pair.py` + `t26_overnight_final.py`.

## Verdict, first

**The theme is real and it contains exactly one signal.** 27 of the 51 configs clear the
empirical joint-null bar on the design window, and 5 clear it with the *opposite* sign — this
is not a noise theme. But every one of those 27 is a restatement of the same feature: the
last-ten-minute price move reverses overnight. That feature is T3.

**No formulation beats T3 out of sample.** The one config that beat it on design with a
bootstrap CI excluding zero (`A08`, residualising the pressure on the same-session move,
ΔSharpe +0.39, CI [0.08, 0.74]) improves on T3 held out by **+0.31 bp/night, t = 0.43**.
The improvement does not replicate.

**Nothing here is promotable.** The best held-out number in the sweep is `A08` at net
+4.99 bp/night, annualised Sharpe 1.40, t 2.98 — and its deflated Sharpe at the honest
51-trial count is **0.83 under the generous deflation input and 0.0000 under López de Prado's
own**, against the repo's frozen 0.95 gate. T3 failed the same gate at 0.9379 with 8 trials.
Widening the search from 8 formulas to 51 moved the bar out of reach of everything the search
found. That is the correct outcome, not a technicality.

## The rails, and why the split matters

| rail | signal may use | entry | exit | modelled cost |
|---|---|---|---|---|
| **A** marketable | up to 15:59 | marketable order at the 15:59 last trade | next opening auction | 1.13 bp (design) / 1.43 bp (held out) half-spread + 0.50 bp auction + borrow |
| **B** MOC-legal | **≤ 15:49 only** | MOC lodged before the 15:50 cutoff, filled at the official closing print | next opening auction | 0.50 bp auction × 2 + borrow |

Rail B exists because the MOC cutoff is 15:50 and a 15:59 signal cannot reach the closing
auction. The 0.50 bp auction leg comes from `M0_AUCTION_FILLS.json` (official print vs mid:
signed mean +0.18 bp, absolute median 1.61 bp, close half-spread median 0.90 bp on rank 1–50).
T3 charged **zero** for its auction legs; this sweep does not.

**Rail B is dead across all eight configs — best net Sharpe 0.37, t 0.89.** The overnight edge
in US equities lives entirely on the rung that has to pay a spread. This reproduces T3's own
structural finding (its pre-cutoff variant was t = 1.38 held out) from a different direction
and with seven further pre-cutoff formulas.

## Noise bar — 51 formulas

Analytic: √(2 ln 51) = **2.80** Sharpe-SE units; one full config has SE(Sharpe) = √(252/1466) = 0.41,
so the expected max annualised Sharpe under the null is **1.16**.

Empirical, and this is the one to use — 400 replicates, within each trading day the overnight
returns are permuted among the valid names, **one permutation shared by all 51 configs** so the
correlation between formulas is preserved, and the max across all 51 is recorded per replicate:

| statistic | mean | p50 | p90 | p95 | p99 | max of 400 |
|---|---|---|---|---|---|---|
| max annualised Sharpe | 1.08 | 0.96 | 1.75 | 2.02 | 2.32 | 2.73 |
| max t | 1.99 | 1.97 | 2.75 | 2.95 | 3.53 | 4.08 |

The empirical bar (expected max t ≈ 2.0, p95 ≈ 2.95) sits **below** the analytic 2.80 because
the 51 formulas are heavily correlated — the effective number of independent tries is closer to
15 than to 51. Read the t column against 2.95, not the Sharpe column: several configs trade
only a subsample of nights and their Sharpe SE is up to 0.98, which is what inflates the
null's max-Sharpe p95 to 2.02.

## Full design distribution (all 51 configs, net of costs)

| min | p10 | p25 | p50 | p75 | p90 | max | mean | sd | n>0 |
|---|---|---|---|---|---|---|---|---|---|
| -2.53 | -0.68 | -0.10 | 1.65 | 2.08 | 2.42 | 3.65 | 1.02 | 1.49 | 35/51 |

**27 configs above the null-max t p95 of 2.95; 5 below −2.95.**

| # | config | rail | formula | nights | net bp | net SR | net t | gross SR | yrs+ | ΔSR vs T3 (95% CI) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `A40_p10_tom` | A | T3 p10 traded only on turn-of-month nights (first 3 / last 1 session of a month) | 278 | +8.90 | +3.65 | +3.84 | +4.35 | 6/6 | +0.00 [0.00, 0.00] |
| 2 | `A36_p10_hivolregime` | A | T3 p10 traded only on nights in the top tercile of SPY 21d realised vol | 427 | +13.36 | +2.95 | +3.84 | +3.32 | 4/5 | +0.00 [0.00, 0.00] |
| 3 | `A38_p10_downmkt` | A | T3 p10 traded only after a down session in SPY | 657 | +7.66 | +2.78 | +4.48 | +3.39 | 5/6 | +0.00 [0.00, 0.00] |
| 4 | `A08_p10_resid_day` | A | fade the CROSS-SECTIONAL RESIDUAL of p10 on the same-session open->15:59 move | 1466 | +7.05 | +2.67 | +6.45 | +3.31 | 5/6 | +0.39 [0.08, 0.73] |
| 5 | `A09_p10_over_vol` | A | fade p10 divided by trailing 21d close-to-close vol (risk-normalised pressure) | 1466 | +4.83 | +2.63 | +6.35 | +3.56 | 5/6 | +0.35 [-0.17, 0.85] |
| 6 | `A43_p10_friday` | A | T3 p10 on Friday nights only (weekend gap) | 291 | +9.15 | +2.42 | +2.60 | +2.88 | 5/6 | +0.00 [0.00, 0.00] |
| 7 | `A19_p10_lovol` | A | fade p10 inside the bottom trailing-vol tercile only | 1466 | +3.47 | +2.35 | +5.68 | +3.50 | 5/6 | +0.07 [-0.71, 0.83] |
| 8 | `A21_p10_loadv` | A | fade p10 inside the bottom dollar-ADV tercile only | 1466 | +6.61 | +2.35 | +5.67 | +2.95 | 6/6 | +0.07 [-0.50, 0.63] |
| 9 | `A01_T3_p10_c10` | A | T3 baseline: cross-sectional decile fade of the 15:49->15:59 last-trade move (cut 10%) | 1466 | +6.61 | +2.28 | +5.51 | +2.87 | 5/6 | +0.00 [0.00, 0.00] |
| 10 | `A42_p10_no_friday` | A | T3 p10 excluding Friday nights | 1175 | +5.98 | +2.28 | +4.92 | +2.91 | 6/6 | +0.00 [0.00, 0.00] |
| 11 | `A23_p10_volneutral` | A | fade p10 ranked WITHIN vol terciles, pooled (vol-neutral book) | 1466 | +5.70 | +2.27 | +5.47 | +2.94 | 5/6 | -0.02 [-0.25, 0.23] |
| 12 | `A24_p10_advneutral` | A | fade p10 ranked WITHIN ADV terciles, pooled (liquidity-neutral book) | 1466 | +6.38 | +2.20 | +5.31 | +2.78 | 5/6 | -0.08 [-0.19, 0.02] |
| 13 | `A03_T3_p10_c20` | A | T3 p10 at a 20% cut | 1466 | +4.08 | +2.12 | +5.12 | +3.00 | 5/6 | -0.16 [-0.39, 0.06] |
| 14 | `A41_p10_nontom` | A | T3 p10 on non-turn-of-month nights | 1188 | +6.07 | +2.03 | +4.41 | +2.60 | 5/6 | +0.00 [0.00, 0.00] |
| 15 | `A15_p10_top20` | A | fade p10, fixed 20 names per side | 1466 | +9.65 | +2.03 | +4.90 | +2.39 | 5/6 | -0.25 [-0.52, 0.00] |
| 16 | `A14_p10_z_cont` | A | continuous dollar-neutral book, weight proportional to -z(p10) clipped at 3 sd | 1466 | +4.54 | +2.02 | +4.86 | +2.76 | 5/6 | -0.27 [-0.46, -0.09] |
| 17 | `A34_p10_long_leg` | A | long leg only of the p10 fade, measured against the equal-weighted cross-section | 1466 | +6.65 | +2.01 | +4.84 | +2.91 | 6/6 | -0.28 [-0.65, 0.10] |
| 18 | `A39_p10_upmkt` | A | T3 p10 traded only after an up session in SPY | 803 | +5.98 | +1.99 | +3.55 | +2.55 | 6/6 | +0.00 [0.00, 0.00] |
| 19 | `A17_p10_c30` | A | fade p10 at a 30% cut | 1466 | +2.87 | +1.96 | +4.74 | +3.12 | 5/6 | -0.32 [-0.61, -0.05] |
| 20 | `A13_p10_rank_cont` | A | continuous dollar-neutral book, weight proportional to centred cross-sectional rank of -p10 | 1466 | +2.87 | +1.93 | +4.65 | +3.06 | 5/6 | -0.36 [-0.58, -0.15] |
| 21 | `A10_p10_x_vol` | A | fade p10 multiplied by trailing vol (vol-amplified pressure) | 1466 | +5.89 | +1.84 | +4.44 | +2.37 | 5/6 | -0.44 [-0.68, -0.22] |
| 22 | `A22_p10_bigmove` | A | fade p10 inside the top |session move| tercile only | 1466 | +9.17 | +1.83 | +4.42 | +2.17 | 5/6 | -0.45 [-0.87, -0.07] |
| 23 | `A16_p10_c02` | A | fade p10 at a 2% tail cut | 1466 | +14.17 | +1.82 | +4.40 | +2.04 | 5/6 | -0.46 [-0.88, -0.06] |
| 24 | `A37_p10_lovolregime` | A | T3 p10 traded only on bottom-tercile SPY-vol nights | 654 | +3.19 | +1.82 | +2.93 | +2.78 | 5/6 | +0.00 [0.00, 0.00] |
| 25 | `A18_p10_hivol` | A | fade p10 inside the top trailing-vol tercile only | 1466 | +9.89 | +1.71 | +4.12 | +2.00 | 5/6 | -0.58 [-0.89, -0.28] |
| 26 | `A06_accel_fade` | A | fade late-session acceleration, p10 - p30/3 | 1466 | +4.50 | +1.65 | +3.99 | +2.27 | 6/6 | -0.63 [-1.19, -0.07] |
| 27 | `A20_p10_hiadv` | A | fade p10 inside the top dollar-ADV tercile only | 1466 | +6.09 | +1.65 | +3.98 | +2.11 | 5/6 | -0.63 [-1.06, -0.21] |
| 28 | `A02_T3_p30_c10` | A | T3 window 30: fade the 15:29->15:59 move | 1466 | +4.93 | +1.53 | +3.70 | +2.06 | 4/6 | -0.75 [-1.41, -0.12] |
| 29 | `A35_p10_short_leg` | A | short leg only of the p10 fade, against the cross-section | 1466 | +3.96 | +1.25 | +3.01 | +2.19 | 5/6 | -1.04 [-1.52, -0.64] |
| 30 | `A05_daycont` | A | ride the full session move overnight | 1466 | +3.65 | +1.04 | +2.51 | +1.52 | 4/6 | -1.24 [-2.49, 0.01] |
| 31 | `A12_p10_minus_gap` | A | fade z(p10)+z(last night's realised gap) | 1466 | +3.48 | +0.95 | +2.29 | +1.41 | 5/6 | -1.33 [-2.04, -0.69] |
| 32 | `A07_late_vs_early` | A | fade p10 minus the 15:29->15:49 move (last 10 vs previous 20 minutes) | 1466 | +1.54 | +0.55 | +1.32 | +1.15 | 4/6 | -1.74 [-2.60, -0.91] |
| 33 | `B01_T3pre_p20early` | B | MOC-legal: fade the 15:29->15:49 move, enter in the closing auction | 1466 | +1.19 | +0.37 | +0.89 | +0.70 | 4/6 | -1.91 [-2.94, -0.93] |
| 34 | `B05_mom5_rev` | B | MOC-legal: fade the trailing 5-day return | 1466 | +0.98 | +0.25 | +0.60 | +0.52 | 4/6 | -2.04 [-3.12, -0.90] |
| 35 | `A29_mom5_rev` | A | short-term reversal, fade the trailing 5-day close-to-close sum | 1466 | +0.42 | +0.10 | +0.25 | +0.53 | 4/6 | -2.18 [-3.31, -1.00] |
| 36 | `B07_ovn5_rev` | B | MOC-legal: fade the last 5 overnight returns | 1466 | -0.02 | -0.01 | -0.01 | +0.26 | 2/6 | -2.29 [-3.43, -1.24] |
| 37 | `A11_p10_z_plus_day_z` | A | fade z(p10)+z(day move), equal-weight composite | 1466 | -0.25 | -0.07 | -0.18 | +0.43 | 2/6 | -2.36 [-3.01, -1.76] |
| 38 | `A26_gapcont` | A | ride this morning's realised overnight gap | 1466 | -0.34 | -0.07 | -0.18 | +0.30 | 1/6 | -2.36 [-3.55, -1.15] |
| 39 | `A30_mom21_cont` | A | ride the trailing 21d-minus-5d momentum | 1466 | -0.45 | -0.12 | -0.29 | +0.32 | 2/6 | -2.40 [-3.51, -1.40] |
| 40 | `A28_aucdev_lag_cont` | A | ride yesterday's closing-auction deviation | 1466 | -0.21 | -0.16 | -0.38 | +1.11 | 3/6 | -2.44 [-3.54, -1.31] |
| 41 | `A31_ovn5_rev` | A | fade the sum of the last 5 overnight returns | 1466 | -0.66 | -0.17 | -0.40 | +0.26 | 1/6 | -2.45 [-3.57, -1.37] |
| 42 | `B08_prevday_fade` | B | MOC-legal: fade yesterday's intraday move | 1466 | -1.20 | -0.37 | -0.89 | -0.04 | 3/6 | -2.65 [-3.78, -1.51] |
| 43 | `A33_prevday_fade` | A | fade yesterday's intraday move | 1466 | -1.70 | -0.53 | -1.27 | -0.00 | 3/6 | -2.81 [-3.95, -1.71] |
| 44 | `B03_gapfade` | B | MOC-legal: fade this morning's gap | 1466 | -2.51 | -0.56 | -1.35 | -0.33 | 1/6 | -2.85 [-3.94, -1.85] |
| 45 | `A32_ovn5_cont` | A | ride the sum of the last 5 overnight returns | 1466 | -2.71 | -0.68 | -1.64 | -0.26 | 0/6 | -2.96 [-4.07, -1.92] |
| 46 | `A25_gapfade` | A | fade this morning's realised overnight gap | 1466 | -3.05 | -0.68 | -1.64 | -0.30 | 1/6 | -2.96 [-4.00, -2.01] |
| 47 | `B06_combo_pre` | B | MOC-legal: fade z(15:29->15:49) + z(open->15:49) | 1466 | -3.91 | -1.28 | -3.10 | -0.94 | 0/6 | -3.57 [-4.51, -2.63] |
| 48 | `B04_aucdev_lag_fade` | B | MOC-legal: fade yesterday's closing-auction deviation | 1466 | -2.14 | -1.61 | -3.89 | -0.81 | 1/6 | -3.90 [-4.99, -2.85] |
| 49 | `A04_dayfade` | A | fade the full session move, open auction -> 15:59 | 1466 | -7.03 | -2.00 | -4.83 | -1.52 | 0/6 | -4.29 [-5.23, -3.38] |
| 50 | `A27_aucdev_lag_fade` | A | fade yesterday's closing-auction print vs its 15:59 last trade (MOC-imbalance proxy) | 1466 | -3.17 | -2.39 | -5.76 | -1.11 | 1/6 | -4.67 [-5.74, -3.60] |
| 51 | `B02_day49_fade` | B | MOC-legal: fade the open-auction->15:49 session move | 1466 | -8.65 | -2.53 | -6.10 | -2.22 | 0/6 | -4.81 [-5.76, -3.90] |

ΔSR is a paired 2000-draw bootstrap of the Sharpe difference against `A01` on the nights both
trade; the time-series-conditioned configs (`A36`–`A43`) hold the *same book* as `A01` on a
subset of nights, so their paired difference is identically zero by construction and their row
carries no information — judge those on the conditioner table below.

## What actually beats T3 on design, and what survives contact with the held-out window

Only **one** of the 50 alternatives clears T3 with a bootstrap CI excluding zero:
`A08_p10_resid_day`, ΔSharpe **+0.39, CI [0.08, 0.74], p = 0.014** — and that is one p-value out
of 50 comparisons, so it is inside the multiplicity bar on its own terms. `A09_p10_over_vol`
(+0.35) and the neutral books `A19/A21/A23/A24` (≈ 0.0 to +0.07) are statistical ties with T3.
Everything else is worse.

### Conditioners — all noise except one, and that one dies out of sample

| conditioner | on | off | Welch t |
|---|---|---|---|
| `A36_p10_hivolregime` vs `A37_p10_lovolregime` | +13.36 bp (n=427) | +3.19 bp (n=654) | +2.79 |
| `A38_p10_downmkt` vs `A39_p10_upmkt` | +7.66 bp (n=657) | +5.98 bp (n=803) | +0.70 |
| `A40_p10_tom` vs `A41_p10_nontom` | +8.90 bp (n=278) | +6.07 bp (n=1188) | +1.05 |
| `A43_p10_friday` vs `A42_p10_no_friday` | +9.15 bp (n=291) | +5.98 bp (n=1175) | +0.85 |

Turn-of-month (t 1.05), Friday/weekend gap (t 0.85) and up-vs-down market (t 0.70) are **noise**,
despite `A40`'s eye-catching design Sharpe of 3.65 — that config trades 278 nights, where one
SE of Sharpe is 0.95. Only the SPY-realised-vol regime separates (t +2.79), and it is the
candidate that fails hardest out of sample.

## Held-out window — 2022-01-03 → 2026-08-14, 1,139 nights

Four configs were carried across, chosen on design alone: the T3 baseline as the reference, the
two that tied-or-beat it, and the one conditioner that separated.

| config | n | net bp/night | net SR | net t | SR at 2× cost | SR at zero cost | ann. return | max DD |
|---|---|---|---|---|---|---|---|---|
| `A08_p10_resid_day` | 1139 | +4.99 | +1.40 | +2.98 | +0.86 | +1.96 | +12.93% | −10.48% |
| `A09_p10_over_vol` | 1139 | +2.91 | +1.14 | +2.42 | +0.38 | +1.92 | +7.37% | −8.70% |
| `A01_T3_p10_c10` | 1139 | +4.67 | +1.12 | +2.37 | +0.66 | +1.59 | +11.88% | −14.36% |
| `A36_p10_hivolregime` | 445 | +4.84 | +0.93 | +1.23 | +0.56 | +1.31 | +11.98% | −14.30% |

Three things this table says:

1. **The signal is still there out of sample.** `A01` reproduces T3's published held-out result
   (+4.67 bp here against T3's +5.35 bp — the gap is the 0.50 bp opening-auction leg T3 charged
   at zero), which is the plumbing check for the whole harness.
2. **`A08`'s design edge over T3 does not replicate.** Paired held-out difference **+0.31 bp,
   t = 0.43** on 1,139 common nights.
3. **`A36`, the vol-regime conditioner, is design noise.** Net Sharpe 0.93, t 1.23 — the +2.79
   Welch t on design was the search finding a subsample, exactly as the multiplicity arithmetic
   predicted.

At **2× the measured half-spread** the best config falls to Sharpe 0.86 and the T3 baseline to
0.66. The edge is 5 bp against 2.5 bp of modelled friction — a 2:1 ratio, which is the same
shape that killed T3, T7 and T10.

## Deflated Sharpe at the honest trial count

| config | DSR, López de Prado input (observed trial dispersion) | DSR, sampling-noise input | passes 0.95 |
|---|---|---|---|
| `A08_p10_resid_day` | 0.0000 | 0.8297 | no |
| `A09_p10_over_vol` | 0.0000 | 0.6582 | no |
| `A01_T3_p10_c10` | 0.0000 | 0.6384 | no |
| `A36_p10_hivolregime` | 0.0006 | 0.4887 | no |

Two inputs, because the choice is load-bearing and hiding it would be dishonest. The first uses
the empirical dispersion of the 51 trial Sharpes, which is López de Prado's own recipe; it is
brutal here (bar 0.214 per observation ≈ annualised 3.4) because the sweep deliberately contains
sign-flipped pairs and whole dead families, and that dispersion is real effect heterogeneity
rather than search noise. The second uses the sampling-noise dispersion 1/n — which is exactly
the null the shuffle measures, bar 0.947 annualised. **Neither candidate passes 0.95 under
either input.** For scale: T3 scored 0.9379 at 8 declared trials with free auction legs.

## Findings that survive independent of the verdict

- **The last ten minutes reverse; the rest of the session continues.** `A04_dayfade` is
  significantly *negative* (design t −4.83, negative in 6 of 6 years) and `B02_day49_fade`
  more so (t −6.10): the open→close move keeps going overnight. The 15:49→15:59 move does the
  opposite. Two windows on the same day, opposite signs, both strong. That is why residualising
  the pressure on the session move (`A08`) is the only thing in 50 tries that improved on T3 at
  all, and why the naive composite `A11_p10_z_plus_day_z` (Sharpe −0.07) destroys the signal by
  adding the two together.
- **The closing-auction print vs the 15:59 last trade — an MOC-imbalance proxy — carries
  information, in the continuation direction, and cost eats it.** `A27_aucdev_lag_fade` is
  design t −5.76, so the live direction is *continuation*: gross Sharpe +1.11, net **−0.16**.
  A one-day-lagged auction deviation is a real predictor of the next overnight return and is
  not tradeable at 2.5 bp of friction.
- **The MOC-legal rail is dead in eight independent formulations**, best Sharpe 0.37. The free,
  spread-less rung of the market cannot reach any overnight signal in this cache.
- **Neutrality constraints are free.** Ranking within vol terciles (`A23`) or ADV terciles
  (`A24`) costs nothing versus the raw book (ΔSR −0.02 and −0.08, CIs spanning zero) — so a
  hypothetical deployment could carry those constraints without paying for them. Sector
  neutrality could not be tested: the cache has no sector map.
- **The edge is not a 2020 artefact.** T3's own p10 book is positive in 5 of 6 design years and
  in 2017/2021 more than in 2020.
- **Concentration raises the mean and not the Sharpe.** The 2 % tail cut (`A16`) earns +14.17 bp
  a night against T3's +6.61, a paired +7.56 bp at t +3.35 — and its Sharpe is *lower* (1.82 vs
  2.28) because the variance rises faster than the mean. Same for the fixed-20-name book.

## Honest caveats

- The held-out window was **already spent by T3** for its own 8 configs. `A01` is therefore a
  replication there, not a virgin test; the other 43 configs are fresh on it, and the 4 that
  crossed were chosen from design output alone.
- The joint shuffle null permutes returns among *base-valid* names. The six configs that trade
  a tercile subset (`A18`–`A22`) would strictly want a within-subset permutation; their null is
  therefore slightly mis-specified. None of them is a candidate, so nothing turns on it.
- Rolling features (`mom5`, `mom21`, `vol21`, `ovn5`) end at d−2, one day earlier than they
  need to. That is deliberate — the error direction is conservative.
- Splits are handled by NaN-ing close-to-close returns on any corporate-action date and any
  |move| > 35 %, not by an adjusted price series; the cache has raw auction prints only.
- No sector map, no daily volume, no daily high/low and no VIX in the cache (Stooq is behind a
  JS challenge). Sector-neutral, relative-volume and VIX-level conditioners could not be built;
  SPY 21-day realised volatility stands in for the vol regime.

