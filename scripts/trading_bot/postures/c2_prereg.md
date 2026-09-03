# POSTURE C2 — PRE-REGISTRATION (written before any effect was computed)

Date: 2026-09-03. Seed: 20260903. Paper-only, free data only.

## Question
Which cross-sections OUTSIDE equities and crypto are NOT tail-dominated, i.e. the
cross-sectional MEDIAN member tracks the EQUAL-WEIGHTED MEAN basket?

## Primary statistic (identical for every cross-section)
For each date t with m_t live members:
  ew_t     = mean_i r_{i,t}        (holdable, daily-rebalanced EW basket)
  med_t    = median_i r_{i,t}      (NOT holdable — control-rule note below)
  g_t      = ew_t - med_t          (the per-day gap, in pp/day)
Delta = mean_t g_t.
Compounding: EW basket = prod_t (1 + ew_t) - 1 ; "median name" = prod_t (1 + med_t) - 1.
Horizons: non-overlapping windows of 1 / 21 / 252 trading days; gap reported per-day (/h).
Concentration: share of summed member-window return taken by the top 1% and top 5% of
member-window observations.

## CONTROL RULE (from the C1 finding, applied here)
The benchmark is ALWAYS the EW-mean of the investable universe. The cross-sectional
median is reported only as the diagnostic being tested, never as a benchmark.

## GATE 1 — COVERAGE (minimums declared BEFORE counting)
A cross-section is admissible only if ALL hold:
  M1  >= 8 members
  M2  >= 1000 dates on which >= 8 members are simultaneously live
  M3  every retained member has >= 60% non-missing observations inside the common window
  M4  source is free and keyless, and its survivorship property is stated explicitly
Failing M1 or M2 -> reported as INSUFFICIENT, excluded from the ranking (not "no effect").

## GATE 2 — POWER (formula fixed BEFORE any effect is read)
Cluster unit = DATE. T = number of admissible dates.
  MDE = (z_0.95 + z_0.80) * sd(g_t) / sqrt(T) = 2.48557 * sd(g_t)/sqrt(T)   [pp/day]
Also reported, per the ICC convention: with member-day observations N and mean members
per date mbar, DEFF = 1 + (mbar - 1) * 0.30 and N_eff = N / DEFF.

### KILL LINE (declared now, before any effect)
Materiality threshold theta = 5.0 bp/day = 0.050 pp/day.
(Justification: a daily-rebalanced RV book turning over ~1 round trip every ~2 days at a
2-4 bp equity/ETF round trip costs on the order of 1-2 bp/day; 5 bp/day is a deliberately
generous ceiling. Crypto perps measured 57.07 bp/day, i.e. 11.4x this line.)
  - Delta CI-low > theta                    -> TAIL-DOMINATED
  - Delta CI covers 0 AND MDE <= theta      -> NOT TAIL-DOMINATED  (the prize; informative null)
  - MDE > theta                             -> UNDERPOWERED, no verdict
  - Delta CI-high < -theta                  -> INVERSE-SKEWED (median beats basket)

## GATE 3 — EFFECT
Cluster bootstrap by DATE, 5000 draws, seed 20260903, two-sided 95% percentile CI on Delta
(one-sided p also reported against the kill line).

## ECONOMICS
Round trips sourced, not assumed. Edge/cost ratio stated explicitly for the winner.

## Refusal is a valid outcome
If free data cannot populate a cross-section to Gate-1 minimums, the verdict for that
cross-section is INSUFFICIENT and it is named as such.
