# FACTORY v2 — post-hoc diagnostics (NOT pre-registered; read as warnings, not as results)

Written 2026-11-10 after the frozen run, by the conductor. Nothing here changes a pre-registered label. These
checks were run because the descriptive holdout table disagreed with the headline book, and they are recorded so
nobody mistakes the headline number for a measured edge.

## 1. The crypto trend book (`P.CRYPTO.TREND`, label PAPER-CANDIDATE) is fragile

**Its members did not hold up after 2023.** The 20 CORE trend rules, each as its own book, net of 7 bp with daily
re-sizing: mean Sharpe **+0.48** on the design window (2020-07 → 2023-12) and **+0.05** on 2024-01 → 2026-11.
Thirteen of 24 trend formulas (CORE + EXPLORATORY) are positive on the later window; the slow ones (126–320
prints) are all negative there.

**Where the book's Sharpe comes from** (weight engine, drift-aware turnover, 7 bp; same instruments):

| construction | design | 2024 → 2026-11 | full | vol | gross |
|---|---:|---:|---:|---:|---:|
| A — static mean of the 20 member books, no scaling | +0.68 | **+0.13** | +0.45 | 5.0 % | 0.07 |
| A at zero cost | +0.75 | +0.20 | +0.52 | 5.0 % | 0.07 |
| B — equal-risk combo of members (each scaled by its own trailing vol) | +1.02 | +0.53 | +0.81 | 17.3 % | 0.29 |
| C — static mean + book vol target 20 % (cap 2×) | +0.91 | +0.46 | +0.71 | 23.7 % | 0.37 |
| D — the primary (ensemble + vol target, 60-print windows) | +1.02 | **+0.75** | +0.90 | 24.9 % | 0.41 |

The risk-scaling layers multiply the static book's exposure by a factor whose median is 4.2 and whose 10th–90th
percentile range is 1.4–12.2. The later-window result is produced by that time-varying leverage, not by the
trend signal itself.

**One smoothing parameter moves the later-window Sharpe from −0.04 to +1.27.** Same book, only the vol-scaling
window changed (60 is the pre-registered value):

| window (prints) | 20 | 30 | 45 | **60** | 75 | 90 | 120 | 180 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| design Sharpe | +1.15 | +0.94 | +1.17 | +1.02 | +1.12 | +1.13 | +0.85 | +0.72 |
| 2024 → 2026-11 Sharpe | +0.67 | +0.05 | +0.60 | **+0.75** | +1.05 | +1.27 | −0.04 | +0.27 |

Mean of the eight later-window values 0.58, median 0.64; two of eight are zero. The design window is stable
across windows; the later window is not.

**Eight days are the whole later-window result.** With the 60-print window, total log return over 2024-01 →
2026-11 is 0.441; the eight best days sum to 0.464 (105 %). On 2024-10-15 (+7.75 %) and 2024-06-05 (+5.56 %) the
book sat at 1.98× and 1.87× gross — next to its 2× cap; with a 120-print window the same days made +0.50 % and
+0.92 % at 0.21× and 0.29×.

**Reading.** The pre-registered book passed its pre-declared label rule and that label stands. But its 0.90
full-sample / 0.75 recent Sharpe should be read as "between 0 and 1": the underlying crypto trend premium was
strong in 2020–21 and roughly flat since 2022 (static book by year: +3.3 %, +6.8 %, +1.6 %, +0.7 %, −0.5 %,
+0.2 %, +1.7 % at 5 % vol), which agrees with this repo's August result (single-lookback TSMOM: in-sample 1.00,
held-out 0.12). The leverage-ladder and realism tables are computed on the primary's stream and inherit this
optimism.

## 2. The Tier-2 survivor is steadier on the same kind of check

`CRYPTO-PERP|ALL|XSMOM.HIGH_PROXIMITY` (long the perps nearest their N-print high, short the furthest; no
vol-scaling layer; 6.7 sides of turnover a year). Only the lookback changed (252 is the registered value):

| lookback (prints) | 126 | 189 | **252** | 378 |
|---|---:|---:|---:|---:|
| design Sharpe | +1.76 | +2.06 | +1.77 | +1.01 |
| 2024 → 2026-11 Sharpe | +0.57 | +1.01 | **+0.99** | +1.11 |

Positive at every lookback on the sealed window. Its registered verdict is still ALIVE-UNPROVEN (holdout t 1.52
< 2), Kraken lists roughly 40 % of the names it would trade, and its shorts carry squeeze risk.

## 3. The descriptive holdout across all 255 formulas (not evidence)

| block | n | corr(design t, holdout t) | median design t | median holdout t | share positive on holdout |
|---|---:|---:|---:|---:|---:|
| CRYPTO-PERP | 46 | +0.80 | +0.96 | +0.05 | 52 % |
| CRYPTO-SPOT (long-only) | 33 | +0.61 | +1.54 | +0.04 | 52 % |
| FX G10 | 67 | −0.04 | +0.71 | −0.32 | 42 % |
| FX G10+EM | 64 | +0.66 | +0.62 | −0.84 | 25 % |
| MACRO | 45 | −0.21 | +0.87 | −0.53 | 29 % |

Mean Sharpe by family, design → holdout: FX trend +0.34 → −0.27; FX carry +0.27 → +0.25; FX value −0.10 → +0.10;
FX cross-sectional momentum −0.03 → −0.36; MACRO trend +0.44 → −0.30; MACRO momentum +0.41 → −0.07; crypto-perp
trend +0.48 → +0.04; crypto-perp cross-sectional momentum +0.82 → +0.44; crypto-perp reversal −1.15 → −0.84.
Across the whole screen 38 % of formulas are positive on their holdout and the median holdout t is −0.33.
