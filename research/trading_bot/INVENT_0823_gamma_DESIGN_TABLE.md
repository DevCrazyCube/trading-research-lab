# INVENT-0823 GAMMA — DESIGN TABLE (FROZEN 2026-08-23, BEFORE THE HELD-OUT WINDOW WAS READ)

Design window 2024-02-01 … 2025-06-30. 24 pre-registered formulas × 2 horizons = **48 cells**.
Universe 49 liquid single names + sector/broad ETFs. Signal from option bars through the close of
day *t*; entry at the **open of t+1**; exit at the close of t+1 (`intraday`) or the open of t+2
(`day`).

## Nulls (computed on the design window, 2000 draws)

| null | value |
|---|---|
| analytic multiple-testing bar, \|t\|, 48 tests | **3.272** |
| ADV-slot signal-permutation placebo, max \|t\| over the 48-cell grid — p95 / p99 | **3.471 / 3.967** |
| same placebo, max \|Sharpe\| over all 48 cells — p95 / p99 | 4.031 / 5.043 |
| same placebo, max \|Sharpe\| restricted to **dense** cells (n ≥ 250) — p95 / p99 | **3.127 / 3.569** |

The all-cell max-\|Sharpe\| null (4.03) is inflated by the four sparse OpEx-window cells (n = 77),
whose Sharpe is far noisier at the same information content. **\|t\| is the n-adjusted statistic and
is the binding bar**; the dense-restricted Sharpe null is the like-for-like Sharpe comparison for a
dense cell. A survivor must clear the analytic bar, the permutation max-\|t\| p99, and the
dense-restricted max-\|Sharpe\| p99.

## Design result — the whole 48-cell grid, ranked by \|t\|

| cell | n | gross bp/day | SR | t | perm FWER p | gap-placebo SR | net SR @3bp |
|---|---|---|---|---|---|---|---|
| **S6_SKEW_TILT \| day** | 352 | **+9.47** | **3.83** | **4.53** | **0.0010** | **+3.25** | **+3.20** |
| S6_SKEW_TILT \| intraday | 352 | +5.31 | 2.96 | 3.49 | 0.047 | +2.25 | −0.38 |
| G4_DGEX1 \| day | 292 | +7.88 | 3.08 | 3.32 | 0.080 | **−0.23** | +1.64 |
| G5_DGEX5 \| day | 288 | +6.96 | 2.65 | 2.84 | 0.264 | +0.71 | +2.01 |
| G2_GEXZ \| intraday | 293 | +5.37 | 2.56 | 2.76 | 0.318 | +1.44 | −0.30 |
| G2_GEXZ \| day | 293 | +6.30 | 2.41 | 2.59 | 0.432 | +1.11 | +2.06 |
| G4_DGEX1 \| intraday | 292 | +4.78 | 2.39 | 2.58 | 0.447 | +0.05 | −0.61 |
| G6_GEXFRAC \| day ( = S1_CPRATIO) | 352 | +5.36 | 1.93 | 2.28 | 0.682 | +1.36 | +1.62 |
| P3_PIN_OPEXWEEK \| day | 77 | +10.28 | 3.95 | 2.18 | 0.753 | −0.10 | +2.82 |
| G5_DGEX5 \| intraday | 288 | +4.58 | 2.04 | 2.18 | 0.757 | +0.82 | −0.63 |
| S4_PUT_SURGE \| intraday | 333 | −3.45 | −1.75 | −2.01 | 0.858 | −2.03 | −4.80 |
| F1_FLIP_DIST \| day | 352 | +3.49 | 1.53 | 1.81 | 0.941 | −0.75 | +0.86 |
| … remaining 36 cells | | | all \|t\| < 1.8 | | | | |

**Exactly one cell clears every design bar: `S6_SKEW_TILT | day`.**

### Disclosure: the frozen list contains one duplicate

`S1_CPRATIO` = log(call γ-OI / put γ-OI) and `G6_GEXFRAC` = (call γ-OI − put γ-OI)/(sum) are
**monotone transforms of the same ratio**, so under rank weighting they are the identical book
(their rows above are numerically identical). The 24-formula list is therefore **23 distinct
formulas / 46 distinct cells**. The nulls were run on the full 48-cell grid, i.e. the bar is if
anything slightly *conservative*, so nothing is rescued by this. It is recorded because the
pre-registration claimed 24 distinct formulas and that claim was wrong.

## What S6_SKEW_TILT is

`S6 = (Σ_{K>S} γ_K · callOI_K − Σ_{K<S} γ_K · putOI_K) / Σ_all γ_K · OI_K`

— the **gamma-weighted out-of-the-money call/put open-interest tilt**, cross-sectionally
rank-normalised, long the top of the cross-section, short the bottom, dollar-neutral, held one
session from the open of t+1 to the open of t+2. Turnover 0.52 of gross/day; **break-even one-way
cost 18.2 bp**, six times the 3.0 bp liquid-taker rail.

## The four gates it had to pass, and its numbers

1. **Structural non-degeneracy — PASSED, and this is the theme's central positive finding.**
   Round 3 killed SPY gamma because near-money net gamma is one-signed on 97% of days. On this
   universe net gamma is positive on 78.3% of name-days pooled, but **32 of 49 names have a
   sign-flip frequency between 10% and 90%** — broad/index ETFs are put-dominated (IWM 0.15,
   XLRE 0.17) and mega-cap single names are call-dominated (AMZN 0.99, META 0.97, NVDA 0.96). The
   cross-sectional dispersion in dealer-gamma sign that SPY does not have **does exist** in the
   single-name/sector cross-section. The R3 ledger entry generalised an index fact to all options
   and was too broad.
2. **Gross bar — PASSED.** t = 4.53 vs analytic 3.272, permutation max-\|t\| p99 3.967
   (family-wise permutation p = **0.0010**, 2 of 2000 draws); Sharpe 3.83 vs the dense-restricted
   max-\|Sharpe\| p99 of 3.569.
3. **Fill realism — PASSED.** The one-day-gap re-entry placebo (skip a whole session, then trade
   identically) keeps SR **+3.25**. It is not a bounce artefact. By contrast `G4_DGEX1|day`, the
   next-strongest cell, collapses from +3.08 to **−0.23** under the same placebo and is killed by it.
4. **Not short-term reversal in a gamma costume — PASSED.** Cross-sectional rank correlation of S6
   with the underlying's past return is −0.052 (1d), −0.049 (5d), −0.020 (20d). Residualising S6 on
   r₁, r₅ **and** r₂₀ each day leaves t = 4.33 / SR 3.78 (from 4.53 / 3.83). A plain reversal book
   on this same universe and window is worth almost nothing: REV1 SR 0.86 (t 1.01), REV5 0.42,
   REV20 0.43. Daily P&L correlation of the S6 book with REV5 is +0.27.

## Design-window robustness (all computed before the held-out window was read)

| cut | n | gross bp | SR | t | net SR @3bp |
|---|---|---|---|---|---|
| all 49 names | 352 | +9.47 | 3.83 | 4.53 | +3.20 |
| **single names only (34)** | 352 | +12.20 | 3.87 | 4.57 | +3.25 |
| **sector / broad ETFs only (15)** | 351 | +2.40 | 1.48 | 1.74 | +0.51 |
| beta-hedged to the equal-weight universe | 352 | +7.82 | 3.68 | 4.35 | +2.95 |

Realised beta to the equal-weight universe is **+0.146** — small, and hedging it costs 0.15 of
Sharpe, so this is not beta wearing a costume. Sub-period Sharpe inside design: **2.86 / 5.31 /
4.22** across 2024-02…09, 2024-10…2025-02, 2025-03…06. Positive-day rate 0.619.

**The edge lives in the single names, not in the sector ETFs** — which is the opposite of an
illiquid-name artefact story (the 34 single names are all top-decile ADV; the weak pool is the
*more* liquid one). It also means the "sector" half of the theme is, on this evidence, dead.

## Frozen prediction for the held-out window (not yet read at the time of writing)

* Cell: **`S6_SKEW_TILT`, horizon `day`** (enter open t+1, exit open t+2).
* Sign: **long high S6, short low S6** (positive, as fitted in design).
* Universe: all 49; the single-name sub-book is also recorded.
* Rail: 3.0 bp/side primary; 1.0 and 5.5 bp also reported.
* Bar to be called real: **held-out net Sharpe at 3.0 bp/side must be positive**, with the gap
  placebo not collapsing.
* Everything else in the 48-cell grid is declared **noise** as of this document, including
  `G4_DGEX1|day` (killed by the gap placebo) and all four pin, all four flip, all four charm/vanna
  and all four surge cells.
