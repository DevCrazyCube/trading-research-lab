# FACTORY v2 — results (real data)

Pre-registration sha256 `83d568c3b3b51692…`. Generated 2026-11-10T18:04:07.480152+00:00.

## Tier 1 — the 16 primary ensembles

Net of the base (retail-wrapper) cost unless stated; `ref` = futures-like financing; Sharpe is of excess returns.

| primary | label | FULL Sharpe | ref | stress | POST-PUB | P(SR>0) | ann. ret | max DD | basket Sharpe / DD | alpha/yr | gross | kept |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|
| P.FX.G10.TREND | **NOT A CANDIDATE** | 0.11 | 0.25 | -0.10 | -0.26 | 0.73 | 1.4% | -45.8% | -0.07 / -64.4% | 1.4% | 1.76 | 19/20 |
| P.FX.G10.CARRY | **NOT A CANDIDATE** | 0.25 | 0.48 | -0.02 | -0.13 | 0.88 | 2.8% | -56.4% | -0.08 / -61.6% | 2.8% | 2.76 | 8/8 |
| P.FX.G10.VALUE | **NOT A CANDIDATE** | -0.47 | -0.18 | -0.87 | -0.29 | 0.01 | -5.1% | -80.4% | -0.07 / -60.0% | -5.1% | 3.34 | 7/7 |
| P.FX.G10.XSMOM | **NOT A CANDIDATE** | -0.33 | -0.02 | -0.81 | -0.46 | 0.04 | -3.7% | -77.3% | -0.08 / -61.0% | -3.7% | 3.65 | 5/7 |
| P.FX.G10.ALL | **NOT A CANDIDATE** | 0.12 | 0.36 | -0.25 | -0.18 | 0.74 | 1.4% | -49.8% | -0.07 / -62.0% | 1.4% | 2.88 | 39/42 |
| P.FX.G10EM.CARRY | **NOT A CANDIDATE** | 0.17 | 0.61 | -0.28 | -0.12 | 0.78 | 1.9% | -64.1% | -0.04 / -60.3% | 2.0% | 3.07 | 8/8 |
| P.FX.G10EM.ALL | **NOT A CANDIDATE** | 0.21 | 0.61 | -0.25 | -0.22 | 0.84 | 2.4% | -52.3% | -0.04 / -60.9% | 2.5% | 2.81 | 23/42 |
| P.MACRO.TREND | **NOT A CANDIDATE** | -0.27 | 0.22 | -0.44 | -0.27 | 0.19 | -2.8% | -41.9% | 0.11 / -25.3% | -2.9% | 2.02 | 18/20 |
| P.MACRO.XSMOM | **NOT A CANDIDATE** | -0.36 | 0.40 | -0.62 | -0.36 | 0.12 | -3.4% | -39.9% | 0.11 / -23.4% | -3.4% | 2.85 | 5/7 |
| P.MACRO.ALL | **NOT A CANDIDATE** | -0.29 | 0.35 | -0.52 | -0.29 | 0.17 | -2.9% | -43.5% | 0.11 / -24.2% | -3.0% | 2.54 | 23/27 |
| P.MACRO.LO_TREND | **NOT A CANDIDATE** | 0.20 | 0.20 | 0.15 | 0.20 | 0.78 | 1.6% | -18.8% | 0.43 / -18.0% | -1.0% | 0.84 | 8/20 |
| P.CRYPTO.TREND | **PAPER-CANDIDATE** | 0.90 | 0.94 | 0.81 | 0.77 | 0.99 | 22.4% | -26.2% | 0.42 / -38.1% | 22.4% | 0.41 | 20/20 |
| P.CRYPTO.XSMOM | NOT IMPLEMENTABLE AT THIS COST | – | – | – | – | – | – | – | – | – | – | 0/7 |
| P.CRYPTO.ALL | **PAPER-CANDIDATE** | 0.90 | 0.94 | 0.81 | 0.77 | 0.99 | 22.4% | -26.2% | 0.42 / -38.1% | 22.4% | 0.41 | 20/27 |
| P.CRYPTO.LO_TREND | **NOT A CANDIDATE** | 0.35 | 0.38 | 0.27 | 0.69 | 0.80 | 9.1% | -54.2% | 0.34 / -39.9% | 2.9% | 0.35 | 13/20 |
| P.GLOBAL | **COMPOSITE (see its three books)** | 0.21 | – | – | 0.22 | 0.88 | 2.7% | -42.2% | – / – | – | – | 3/3 |

### Why each label

- **P.FX.G10.TREND** — NOT A CANDIDATE: (a) FULL net Sharpe < 0.30; (b) stress Sharpe < 0.15; (c) bootstrap P(Sharpe>0) < 0.80; (d) POST-PUB Sharpe < 0; (e) concentration or < half of years positive
- **P.FX.G10.CARRY** — NOT A CANDIDATE: (a) FULL net Sharpe < 0.30; (b) stress Sharpe < 0.15; (d) POST-PUB Sharpe < 0
- **P.FX.G10.VALUE** — NOT A CANDIDATE: (a) FULL net Sharpe < 0.30; (b) stress Sharpe < 0.15; (c) bootstrap P(Sharpe>0) < 0.80; (d) POST-PUB Sharpe < 0; (e) concentration or < half of years positive; (g) alpha vs the lane basket < 0
- **P.FX.G10.XSMOM** — NOT A CANDIDATE: (a) FULL net Sharpe < 0.30; (b) stress Sharpe < 0.15; (c) bootstrap P(Sharpe>0) < 0.80; (d) POST-PUB Sharpe < 0; (e) concentration or < half of years positive; (g) alpha vs the lane basket < 0
- **P.FX.G10.ALL** — NOT A CANDIDATE: (a) FULL net Sharpe < 0.30; (b) stress Sharpe < 0.15; (c) bootstrap P(Sharpe>0) < 0.80; (d) POST-PUB Sharpe < 0
- **P.FX.G10EM.CARRY** — NOT A CANDIDATE: (a) FULL net Sharpe < 0.30; (b) stress Sharpe < 0.15; (c) bootstrap P(Sharpe>0) < 0.80; (d) POST-PUB Sharpe < 0
- **P.FX.G10EM.ALL** — NOT A CANDIDATE: (a) FULL net Sharpe < 0.30; (b) stress Sharpe < 0.15; (d) POST-PUB Sharpe < 0
- **P.MACRO.TREND** — NOT A CANDIDATE: (a) FULL net Sharpe < 0.30; (b) stress Sharpe < 0.15; (c) bootstrap P(Sharpe>0) < 0.80; (d) POST-PUB Sharpe < 0; (e) concentration or < half of years positive; (g) alpha vs the lane basket < 0
- **P.MACRO.XSMOM** — NOT A CANDIDATE: (a) FULL net Sharpe < 0.30; (b) stress Sharpe < 0.15; (c) bootstrap P(Sharpe>0) < 0.80; (d) POST-PUB Sharpe < 0; (e) concentration or < half of years positive; (g) alpha vs the lane basket < 0
- **P.MACRO.ALL** — NOT A CANDIDATE: (a) FULL net Sharpe < 0.30; (b) stress Sharpe < 0.15; (c) bootstrap P(Sharpe>0) < 0.80; (d) POST-PUB Sharpe < 0; (e) concentration or < half of years positive; (g) alpha vs the lane basket < 0
- **P.MACRO.LO_TREND** — NOT A CANDIDATE: (a) FULL net Sharpe < 0.30; (b) stress Sharpe < 0.15; (c) bootstrap P(Sharpe>0) < 0.80; (g) not better than the vol-matched basket
- **P.CRYPTO.TREND** — PAPER-CANDIDATE
- **P.CRYPTO.XSMOM** — NOT IMPLEMENTABLE AT THIS COST: every member exceeds the speed limit
- **P.CRYPTO.ALL** — PAPER-CANDIDATE
- **P.CRYPTO.LO_TREND** — NOT A CANDIDATE: (c) bootstrap P(Sharpe>0) < 0.80; (g) not better than the vol-matched basket
- **P.GLOBAL** — COMPOSITE (see its three books)

### Calendar years (base cost, net)

- **P.FX.G10.TREND**: 2000 +11.4%, 2001 -0.7%, 2002 +20.7%, 2003 +23.7%, 2004 -9.2%, 2005 -7.4%, 2006 -5.7%, 2007 +18.8%, 2008 +13.6%, 2009 +1.9%, 2010 +11.2%, 2011 -4.2%, 2012 +8.3%, 2013 -8.9%, 2014 +10.5%, 2015 -9.3%, 2016 -13.1%, 2017 -18.7%, 2018 +7.4%, 2019 -7.9%, 2020 +27.0%, 2021 -9.5%, 2022 +16.6%, 2023 -11.2%, 2024 -9.7%, 2025 -14.5%, 2026 -2.1%
- **P.FX.G10.CARRY**: 2000 +4.4%, 2001 +9.2%, 2002 +48.3%, 2003 +30.1%, 2004 +12.2%, 2005 +21.4%, 2006 -5.2%, 2007 -9.8%, 2008 -18.1%, 2009 +10.2%, 2010 +0.5%, 2011 -7.3%, 2012 +11.6%, 2013 -1.1%, 2014 -3.5%, 2015 -22.3%, 2016 +8.4%, 2017 -14.6%, 2018 +1.0%, 2019 -0.4%, 2020 -13.3%, 2021 +13.1%, 2022 +5.2%, 2023 -2.0%, 2024 +14.3%, 2025 -6.9%, 2026 +1.0%
- **P.FX.G10.VALUE**: 2000 +0.0%, 2001 -2.7%, 2002 -24.8%, 2003 -8.7%, 2004 -4.4%, 2005 -15.5%, 2006 +2.3%, 2007 -6.8%, 2008 +1.5%, 2009 +5.0%, 2010 -20.0%, 2011 -16.4%, 2012 +1.4%, 2013 -12.0%, 2014 -10.1%, 2015 -9.3%, 2016 +0.5%, 2017 +24.6%, 2018 +6.8%, 2019 -7.0%, 2020 -11.5%, 2021 +3.9%, 2022 -6.0%, 2023 -13.1%, 2024 -5.3%, 2025 -13.3%, 2026 +4.4%
- **P.FX.G10.XSMOM**: 2000 +2.3%, 2001 -0.8%, 2002 +22.8%, 2003 -1.5%, 2004 -16.3%, 2005 +10.0%, 2006 +0.3%, 2007 -7.4%, 2008 -11.0%, 2009 -14.4%, 2010 +7.7%, 2011 -15.1%, 2012 -4.7%, 2013 +4.3%, 2014 -4.6%, 2015 -3.2%, 2016 +3.2%, 2017 -14.8%, 2018 -29.4%, 2019 -4.3%, 2020 +6.7%, 2021 -6.8%, 2022 -1.9%, 2023 -7.7%, 2024 -12.3%, 2025 +7.9%, 2026 -9.4%
- **P.FX.G10.ALL**: 2000 +10.2%, 2001 +1.6%, 2002 +34.0%, 2003 +24.5%, 2004 -7.5%, 2005 +7.7%, 2006 +5.3%, 2007 +1.4%, 2008 -5.3%, 2009 +3.6%, 2010 +3.3%, 2011 -21.7%, 2012 +13.8%, 2013 -6.8%, 2014 +4.0%, 2015 -22.5%, 2016 +5.3%, 2017 -4.4%, 2018 -4.5%, 2019 -5.3%, 2020 +5.4%, 2021 +5.2%, 2022 +11.8%, 2023 -13.4%, 2024 -1.5%, 2025 -7.6%, 2026 +1.4%
- **P.FX.G10EM.CARRY**: 2000 +2.8%, 2001 +11.4%, 2002 +36.4%, 2003 +21.7%, 2004 +15.5%, 2005 +20.3%, 2006 -14.3%, 2007 -16.3%, 2008 -5.9%, 2009 +0.5%, 2010 +2.1%, 2011 -7.8%, 2012 +12.8%, 2013 +2.9%, 2014 -11.1%, 2015 -25.9%, 2016 -0.8%, 2017 -5.4%, 2018 +5.0%, 2019 -2.0%, 2020 -14.5%, 2021 -0.3%, 2022 +2.7%, 2023 +3.7%, 2024 +14.7%, 2025 +4.0%, 2026 +5.1%
- **P.FX.G10EM.ALL**: 2000 +4.8%, 2001 +16.9%, 2002 +48.7%, 2003 +8.2%, 2004 +4.5%, 2005 +26.0%, 2006 -7.5%, 2007 -17.9%, 2008 -0.7%, 2009 +6.4%, 2010 +2.1%, 2011 -3.4%, 2012 +22.2%, 2013 -7.4%, 2014 -7.1%, 2015 -28.3%, 2016 -12.4%, 2017 +4.6%, 2018 +13.2%, 2019 -3.1%, 2020 -10.3%, 2021 +0.8%, 2022 +4.0%, 2023 -0.2%, 2024 -3.1%, 2025 +7.0%, 2026 +6.7%
- **P.MACRO.TREND**: 2017 +8.1%, 2018 -5.8%, 2019 -0.6%, 2020 +10.0%, 2021 -5.1%, 2022 +11.5%, 2023 -20.0%, 2024 -11.0%, 2025 -13.0%, 2026 -1.1%
- **P.MACRO.XSMOM**: 2017 +2.0%, 2018 -5.9%, 2019 -0.7%, 2020 +7.3%, 2021 -4.4%, 2022 +7.3%, 2023 -11.1%, 2024 -11.7%, 2025 -13.7%, 2026 -3.5%
- **P.MACRO.ALL**: 2017 +3.8%, 2018 -5.7%, 2019 +0.4%, 2020 +12.9%, 2021 -4.6%, 2022 +11.2%, 2023 -17.2%, 2024 -12.8%, 2025 -14.2%, 2026 -2.0%
- **P.MACRO.LO_TREND**: 2017 +12.3%, 2018 -6.1%, 2019 +6.3%, 2020 -0.5%, 2021 +6.4%, 2022 -10.4%, 2023 +2.5%, 2024 +0.3%, 2025 +7.4%, 2026 -3.3%
- **P.CRYPTO.TREND**: 2020 +33.2%, 2021 +32.3%, 2022 +1.8%, 2023 +23.5%, 2024 +17.2%, 2025 +3.6%, 2026 +27.2%
- **P.CRYPTO.ALL**: 2020 +33.2%, 2021 +32.3%, 2022 +1.8%, 2023 +23.5%, 2024 +17.2%, 2025 +3.6%, 2026 +27.2%
- **P.CRYPTO.LO_TREND**: 2018 -36.2%, 2019 -27.7%, 2020 +46.5%, 2021 +125.4%, 2022 -20.1%, 2023 +19.5%, 2024 +12.8%, 2025 +10.3%, 2026 -11.7%
- **P.GLOBAL**: 1999 -11.3%, 2000 +8.6%, 2001 -0.2%, 2002 +31.1%, 2003 +21.0%, 2004 -11.0%, 2005 +16.5%, 2006 -0.7%, 2007 +8.7%, 2008 -3.1%, 2009 +0.0%, 2010 -3.7%, 2011 -30.1%, 2012 +13.9%, 2013 +10.7%, 2014 +1.8%, 2015 -13.5%, 2016 +0.6%, 2017 -4.3%, 2018 -5.1%, 2019 +5.1%, 2020 +26.3%, 2021 +15.1%, 2022 +23.5%, 2023 -8.0%, 2024 -4.0%, 2025 -13.2%, 2026 +2.5%

## FX robustness

- **P.FX.G10.TREND** on FRED noon rates — pre-euro 1976–1998: Sharpe 1.64 at futures-like cost, 1.46 at retail cost; since 1999: 0.23 / 0.09
- **P.FX.G10.CARRY** on FRED noon rates — pre-euro 1976–1998: Sharpe 0.78 at futures-like cost, 0.52 at retail cost; since 1999: 0.54 / 0.29
- **P.FX.G10.VALUE** on FRED noon rates — pre-euro 1976–1998: Sharpe -0.35 at futures-like cost, -0.60 at retail cost; since 1999: -0.10 / -0.40
- **P.FX.G10.XSMOM** on FRED noon rates — pre-euro 1976–1998: Sharpe 1.23 at futures-like cost, 0.93 at retail cost; since 1999: -0.04 / -0.35
- **P.FX.G10.ALL** on FRED noon rates — pre-euro 1976–1998: Sharpe 1.58 at futures-like cost, 1.29 at retail cost; since 1999: 0.38 / 0.14
- Timing check on `P.FX.G10.ALL`: same-day NY-noon execution Sharpe 0.41 vs next-fix 0.38 (gap 0.03).

## Tier 2 — the design-window screen

255 formulas ledgered (0 errors). Benjamini–Hochberg (q = 10 %) rejects 1; StepM superior 0.

- `CRYPTO-PERP__ALL`: 46 formulas × 1279 prints; StepM []; SPA p (consistent) 0.013; PBO 0.27
- `CRYPTO-SPOT__ALL`: 33 formulas × 1979 prints; StepM []; SPA p (consistent) 0.044; PBO 0.41
- `FX__G10`: 67 formulas × 4351 prints; StepM []; SPA p (consistent) 0.224; PBO 0.66
- `FX__G10EM`: 64 formulas × 4351 prints; StepM []; SPA p (consistent) 0.208; PBO 0.67
- `MACRO__ALL`: 45 formulas × 1259 prints; StepM []; SPA p (consistent) 0.163; PBO 0.48

Top 25 by design HAC t (screen cost):

| formula | Sharpe | HAC t | stress | retail | later timing | turnover/yr | audit | flags |
|---|---:|---:|---:|---:|---:|---:|---|---|
| CRYPTO-PERP|ALL|XSMOM.HIGH_PROXIMITY.L252 | 1.77 | 3.38 | 1.53 | 1.77 | 1.64 | 6.7 | ok |  |
| CRYPTO-SPOT|ALL|TREND.BREAKOUT.L40 | 1.11 | 2.72 | 1.02 | 1.11 | 1.10 | 2.2 | ok |  |
| CRYPTO-SPOT|ALL|TREND.EWMAC.8_32 | 1.01 | 2.54 | 0.92 | 1.01 | 1.01 | 2.1 | ok |  |
| CRYPTO-SPOT|ALL|TREND.BREAKOUT.L20 | 1.08 | 2.54 | 0.94 | 1.08 | 1.06 | 3.8 | ok |  |
| CRYPTO-SPOT|ALL|TREND.EWMAC.4_16 | 1.03 | 2.48 | 0.88 | 1.03 | 1.01 | 3.4 | ok |  |
| FX|G10EM|TREND.DONCHIAN.L100 | 0.58 | 2.46 | 0.54 | 0.31 | 0.58 | 6.5 | ok |  |
| FX|G10|TREND.TSMOM_SIGN.L126 | 0.59 | 2.45 | 0.55 | 0.43 | 0.52 | 23.4 | ok |  |
| FX|G10|TREND.DONCHIAN.L100 | 0.56 | 2.37 | 0.55 | 0.40 | 0.55 | 6.6 | ok |  |
| FX|G10EM|TREND.TSMOM_SIGN.L126 | 0.54 | 2.26 | 0.37 | 0.27 | 0.46 | 23.7 | ok |  |
| CRYPTO-PERP|ALL|XSMOM.TERCILE.L21 | 1.16 | 2.24 | 0.78 | 1.16 | 1.28 | 15.4 | ok |  |
| CRYPTO-SPOT|ALL|TREND.EWMAC.16_64 | 0.83 | 2.14 | 0.76 | 0.83 | 0.84 | 1.4 | ok |  |
| CRYPTO-PERP|ALL|TREND.TSMOM_Z.L126 | 0.98 | 2.10 | 0.92 | 0.98 | 0.99 | 4.4 | ok |  |
| CRYPTO-SPOT|ALL|TREND.BREAKOUT.L80 | 0.82 | 2.08 | 0.76 | 0.82 | 0.83 | 1.3 | ok |  |
| CRYPTO-SPOT|ALL|XSMOM.HIGH_PROXIMITY.L252 | 0.86 | 2.07 | 0.66 | 0.86 | 0.83 | 4.0 | ok |  |
| CRYPTO-SPOT|ALL|TREND.DONCHIAN.L20 | 0.86 | 2.07 | 0.76 | 0.86 | 0.85 | 4.5 | ok |  |
| CRYPTO-SPOT|ALL|TREND.EWMAC.2_8 | 0.86 | 2.06 | 0.58 | 0.86 | 0.85 | 6.1 | ok |  |
| FX|G10EM|TREND.BREAKOUT.L160 | 0.49 | 2.05 | 0.44 | 0.27 | 0.49 | 4.0 | ok |  |
| MACRO|ALL|VOL.MANAGED_BASKET.252_21 | 0.93 | 2.05 | 0.90 | 0.40 | 0.89 | 8.2 | ok |  |
| CRYPTO-PERP|ALL|XSMOM.LINEAR.L126 | 1.11 | 2.04 | 0.88 | 1.11 | 1.04 | 6.2 | ok |  |
| FX|G10EM|TREND.DONCHIAN.L55 | 0.49 | 2.03 | 0.42 | 0.21 | 0.53 | 9.0 | ok |  |
| FX|G10EM|TREND.SMA_CROSS.50_200 | 0.47 | 2.00 | 0.43 | 0.21 | 0.47 | 6.6 | ok |  |
| FX|G10|TREND.TSMOM_Z.L126 | 0.47 | 1.97 | 0.43 | 0.36 | 0.46 | 14.0 | ok |  |
| FX|G10|TREND.BREAKOUT.L80 | 0.46 | 1.96 | 0.44 | 0.34 | 0.47 | 7.2 | ok |  |
| FX|G10EM|TREND.EWMAC.32_128 | 0.47 | 1.95 | 0.40 | 0.28 | 0.46 | 5.5 | ok |  |
| FX|G10EM|XASSET.OIL_FX.L63 | 0.46 | 1.95 | 0.27 | 0.25 | 0.40 | 7.3 | ok |  |

Distribution of design HAC t over 255 formulas: min -12.09, p25 -0.31, median 0.99, p75 1.59, max 3.38; share positive 72%.

## Frozen survivors and the holdout

Frozen 2026-11-10T17:35:52.134236+00:00: 1 survivors of 255 formulas (candidates before exclusions: 1).

- CRYPTO-PERP|ALL|XSMOM.HIGH_PROXIMITY.L252: design Sharpe 1.77, t 3.38, stress 1.53, retail 1.77 — SURVIVES

| survivor | design t | holdout Sharpe | holdout t | stress | retail | verdict |
|---|---:|---:|---:|---:|---:|---|
| CRYPTO-PERP|ALL|XSMOM.HIGH_PROXIMITY.L252 | 3.38 | 0.99 | 1.52 | 0.74 | 0.99 | **ALIVE-UNPROVEN** |

Descriptive only (all 255 formulas): correlation of design t with holdout t = 0.50; holdout t > 0 for 38%; median holdout t -0.33; of the design top decile, 50% are positive on holdout.

