# FACTORY v2 — leverage ladder (PREREGISTRATION_v2 §6) — real data

Pre-registration sha256 `83d568c3b3b51692…`. Generated 2026-11-10T17:55:29Z. 5,000 one-year stationary-bootstrap paths per book; the same paths for every L. Ruin: a single print loses >= 100 % (1 + L*r <= 0) or wealth <= 10% of the start; absorbing.

## Read this first

- Prints are daily. A levered position is liquidated on the intraday path, not at the close, so every P(ruin) here is a LOWER BOUND — the hourly BTC table below shows how much a daily print hides.
- Each stream is the book's base-cost net return. Scaling it by L scales its trading and holding costs by L and nothing else: no extra financing spread on the borrowed notional, no liquidation fee, no funding cap.
- The streams are excess returns, so a levered row borrows at the risk-free rate with no mark-up.
- P.MACRO.LO_TREND at Trading 212 and P.CRYPTO.LO_TREND at Bitvavo are unlevered cash accounts: their rows above L = 1 are arithmetic on the stream, not an account those venues offer.
- A one-year path is a stationary-bootstrap resample of the book's own history: it can only contain days that happened.
- 'Mean log wealth, survivors' is conditional on not being ruined: with few survivors it is the luck of the survivors, not an expectation.
- The growth-optimal L and the Kelly ratio are computed on the whole sample and are IN-SAMPLE: they describe this history, not a forecast, and estimation error makes the true optimum lower.

## P.MACRO.LO_TREND (`trading212_invest`)

Base-cost net stream, 2017-01-03 → 2026-11-09: 2,477 prints, annual return 1.6%, volatility 7.8%, Sharpe 0.20, worst print -3.12%. Paths of 252 prints, mean block 28.

| L | median wealth | 5th pct | 95th pct | P(final < 0.5) | P(ruin) | of which single-print wipe-out | mean log wealth, survivors | survivors | actual history |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0.5 | 1.010 | 0.957 | 1.060 | 0.0% | 0.0% | 0.0% | 0.008 | 5,000 | survives |
| 1 | 1.018 | 0.914 | 1.122 | 0.0% | 0.0% | 0.0% | 0.014 | 5,000 | survives |
| 2 | 1.029 | 0.827 | 1.252 | 0.0% | 0.0% | 0.0% | 0.022 | 5,000 | survives |
| 3 | 1.034 | 0.744 | 1.389 | 0.1% | 0.0% | 0.0% | 0.024 | 5,000 | survives |
| 5 | 1.028 | 0.586 | 1.690 | 2.3% | 0.0% | 0.0% | 0.008 | 5,000 | survives |
| 10 | 0.905 | 0.275 | 2.520 | 21.2% | 0.6% | 0.0% | -0.129 | 4,970 | survives |
| 20 | 0.402 | 0.074 | 4.015 | 55.2% | 31.1% | 0.0% | -0.200 | 3,446 | ruined 2022-05-09 |
| 50 | 0.058 | 0.000 | 0.697 | 94.4% | 93.0% | 35.7% | 0.684 | 352 | ruined 2018-02-05 |
| 200 | 0.000 | 0.000 | 0.086 | 100.0% | 100.0% | 77.2% | – | 0 | ruined 2017-03-02 |

- L with the highest median log wealth on the ladder: **3**.
- Full-sample growth-optimal L (in-sample): **2.606**; mean log growth 2.08% a year. A single print wipes the account from L = 32.0.
- Continuous-time Kelly, mean / variance: **2.63** (in-sample).

## P.FX.G10.ALL (`pepperstone_eu_ctrader`)

Base-cost net stream, 2000-01-03 → 2026-11-09: 6,873 prints, annual return 1.4%, volatility 11.4%, Sharpe 0.12, worst print -11.43%. Paths of 252 prints, mean block 39.

| L | median wealth | 5th pct | 95th pct | P(final < 0.5) | P(ruin) | of which single-print wipe-out | mean log wealth, survivors | survivors | actual history |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0.5 | 1.006 | 0.920 | 1.103 | 0.0% | 0.0% | 0.0% | 0.006 | 5,000 | survives |
| 1 | 1.009 | 0.843 | 1.212 | 0.0% | 0.0% | 0.0% | 0.009 | 5,000 | survives |
| 2 | 1.005 | 0.700 | 1.450 | 0.0% | 0.0% | 0.0% | 0.006 | 5,000 | survives |
| 3 | 0.988 | 0.573 | 1.712 | 2.0% | 0.0% | 0.0% | -0.012 | 5,000 | survives |
| 5 | 0.917 | 0.362 | 2.287 | 14.1% | 0.0% | 0.0% | -0.089 | 5,000 | ruined 2024-09-03 |
| 10 | 0.594 | 0.089 | 3.759 | 43.8% | 10.9% | 3.5% | -0.297 | 4,457 | ruined 2011-12-19 |
| 20 | 0.094 | 0.000 | 3.682 | 79.7% | 67.8% | 9.9% | -0.040 | 1,610 | ruined 2005-03-24 |
| 50 | 0.030 | 0.000 | 0.096 | 99.9% | 99.9% | 40.8% | 0.616 | 6 | ruined 2000-01-04 |
| 200 | 0.000 | 0.000 | 0.066 | 100.0% | 100.0% | 86.3% | – | 0 | ruined 2000-01-04 |

- L with the highest median log wealth on the ladder: **1**.
- Full-sample growth-optimal L (in-sample): **1.046**; mean log growth 0.72% a year. A single print wipes the account from L = 8.7.
- Continuous-time Kelly, mean / variance: **1.05** (in-sample).

## P.CRYPTO.TREND (`kraken_derivatives_eea`)

Base-cost net stream, 2020-07-01 → 2026-11-10: 2,324 prints, annual return 22.4%, volatility 24.8%, Sharpe 0.90, worst print -12.79%. Paths of 365 prints, mean block 27.

| L | median wealth | 5th pct | 95th pct | P(final < 0.5) | P(ruin) | of which single-print wipe-out | mean log wealth, survivors | survivors | actual history |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0.5 | 1.104 | 0.934 | 1.330 | 0.0% | 0.0% | 0.0% | 0.103 | 5,000 | survives |
| 1 | 1.201 | 0.859 | 1.740 | 0.0% | 0.0% | 0.0% | 0.190 | 5,000 | survives |
| 2 | 1.359 | 0.690 | 2.830 | 0.6% | 0.0% | 0.0% | 0.318 | 5,000 | survives |
| 3 | 1.441 | 0.517 | 4.287 | 4.4% | 0.0% | 0.0% | 0.382 | 5,000 | survives |
| 5 | 1.315 | 0.216 | 8.113 | 17.8% | 1.3% | 0.0% | 0.327 | 4,937 | survives |
| 10 | 0.099 | 0.000 | 13.964 | 65.9% | 54.1% | 23.4% | 0.511 | 2,297 | ruined 2021-07-22 |
| 20 | 0.008 | 0.000 | 0.099 | 98.4% | 97.8% | 49.3% | 1.062 | 109 | ruined 2020-11-07 |
| 50 | 0.000 | 0.000 | 0.094 | 100.0% | 100.0% | 59.7% | – | 0 | ruined 2020-08-03 |
| 200 | 0.000 | 0.000 | 0.053 | 100.0% | 100.0% | 90.4% | – | 0 | ruined 2020-07-07 |

- L with the highest median log wealth on the ladder: **3**.
- Full-sample growth-optimal L (in-sample): **3.453**; mean log growth 39.69% a year. A single print wipes the account from L = 7.8.
- Continuous-time Kelly, mean / variance: **3.65** (in-sample).

## P.CRYPTO.ALL (`kraken_derivatives_eea`)

Base-cost net stream, 2020-07-01 → 2026-11-10: 2,324 prints, annual return 22.4%, volatility 24.8%, Sharpe 0.90, worst print -12.79%. Paths of 365 prints, mean block 27.

| L | median wealth | 5th pct | 95th pct | P(final < 0.5) | P(ruin) | of which single-print wipe-out | mean log wealth, survivors | survivors | actual history |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0.5 | 1.103 | 0.933 | 1.331 | 0.0% | 0.0% | 0.0% | 0.102 | 5,000 | survives |
| 1 | 1.200 | 0.856 | 1.741 | 0.0% | 0.0% | 0.0% | 0.189 | 5,000 | survives |
| 2 | 1.354 | 0.691 | 2.833 | 0.4% | 0.0% | 0.0% | 0.316 | 5,000 | survives |
| 3 | 1.434 | 0.518 | 4.317 | 4.5% | 0.0% | 0.0% | 0.377 | 5,000 | survives |
| 5 | 1.302 | 0.221 | 8.359 | 18.9% | 1.6% | 0.0% | 0.320 | 4,922 | survives |
| 10 | 0.098 | 0.000 | 12.918 | 66.2% | 55.1% | 23.4% | 0.495 | 2,244 | ruined 2021-07-22 |
| 20 | 0.010 | 0.000 | 0.099 | 98.5% | 98.1% | 49.3% | 1.511 | 96 | ruined 2020-11-07 |
| 50 | 0.000 | 0.000 | 0.094 | 100.0% | 100.0% | 59.4% | – | 0 | ruined 2020-08-03 |
| 200 | 0.000 | 0.000 | 0.053 | 100.0% | 100.0% | 90.2% | – | 0 | ruined 2020-07-07 |

- L with the highest median log wealth on the ladder: **3**.
- Full-sample growth-optimal L (in-sample): **3.453**; mean log growth 39.69% a year. A single print wipes the account from L = 7.8.
- Continuous-time Kelly, mean / variance: **3.65** (in-sample).

## P.CRYPTO.LO_TREND (`bitvavo`)

Base-cost net stream, 2018-08-01 → 2026-11-10: 3,024 prints, annual return 9.1%, volatility 26.3%, Sharpe 0.35, worst print -14.09%. Paths of 365 prints, mean block 29.

| L | median wealth | 5th pct | 95th pct | P(final < 0.5) | P(ruin) | of which single-print wipe-out | mean log wealth, survivors | survivors | actual history |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0.5 | 1.031 | 0.809 | 1.347 | 0.0% | 0.0% | 0.0% | 0.035 | 5,000 | survives |
| 1 | 1.045 | 0.643 | 1.776 | 0.6% | 0.0% | 0.0% | 0.054 | 5,000 | survives |
| 2 | 1.027 | 0.386 | 2.891 | 11.1% | 0.0% | 0.0% | 0.040 | 5,000 | survives |
| 3 | 0.944 | 0.211 | 4.364 | 24.0% | 1.0% | 0.0% | -0.020 | 4,952 | ruined 2019-11-22 |
| 5 | 0.636 | 0.089 | 8.053 | 43.6% | 16.7% | 0.0% | 0.018 | 4,165 | ruined 2018-11-23 |
| 10 | 0.094 | 0.000 | 9.891 | 76.9% | 68.8% | 7.7% | 0.625 | 1,560 | ruined 2018-10-10 |
| 20 | 0.043 | 0.000 | 0.098 | 99.1% | 98.9% | 41.8% | 1.861 | 55 | ruined 2018-08-09 |
| 50 | 0.000 | 0.000 | 0.091 | 100.0% | 100.0% | 73.6% | – | 0 | ruined 2018-08-05 |
| 200 | 0.000 | 0.000 | 0.061 | 100.0% | 100.0% | 89.4% | – | 0 | ruined 2018-08-03 |

- L with the highest median log wealth on the ladder: **1**.
- Full-sample growth-optimal L (in-sample): **1.327**; mean log growth 6.03% a year. A single print wipes the account from L = 7.1.
- Continuous-time Kelly, mean / variance: **1.32** (in-sample).

## A 200× BTC position on hourly candles

Binance USD-M BTCUSDT 1 h candles on disk (research/factory/data/raw/binance/futures_um/{archive_klines_1h,rest_klines_1h}/BTCUSDT), every hourly open from 2020-01-01: 60,133 candles, 2020-01-01T00:00 → 2026-11-10T13:00 UTC, 1 hourly candles missing, 1 zero-trade candles dropped.

A long entered at an hourly open is liquidated when a candle's low is ≤ entry × (1 − d); a short when a high is ≥ entry × (1 + d). The entry candle counts. At 200x the whole margin is a 0.5 % adverse move; 0.25 % stands for a typical maintenance level — the exact liquidation distance is venue-specific (maintenance margin, fees, mark versus last price). Entries without 24 h of data after them are left out.

| side | adverse move d | entries | liquidated within 1 h | liquidated within 4 h | liquidated within 24 h | median hours to liquidation | never in the data |
|---|---:|---:|---:|---:|---:|---:|---:|
| long | 0.25% | 60,110 | 51.9% | 73.7% | 90.0% | 1 | 1.07% |
| short | 0.25% | 60,110 | 51.9% | 74.1% | 91.1% | 1 | 0.27% |
| long | 0.50% | 60,110 | 26.8% | 52.9% | 80.2% | 4 | 2.15% |
| short | 0.50% | 60,110 | 26.4% | 52.9% | 81.7% | 4 | 0.58% |

Fees at 200× (notional = 200 × margin):

| fee per side | round trip, % of margin | price move needed to break even |
|---:|---:|---:|
| 5 bp | 20% | 0.10% |
| 2 bp | 8% | 0.04% |

## What leverage a Dutch retail account can actually get (venues.json)

- EU retail CFD caps (VERIFIED, https://www.afm.nl/~/profmedia/files/onderwerpen/productinterventie/besluit-productinterventie-cfd.pdf): fx_major 30:1, fx_non_major_gold_major_index 20:1, other_commodity_non_major_index 10:1, single_equity_other 5:1, crypto 2:1; margin close-out at 50% of required initial margin, per account.
- Kraken Derivatives EEA: 10× — margin schedule 'europa' retail: initial margin 10%, maintenance 5% at tier I for BTC, ETH, SOL, DOGE, XAU, US100, SPYx, WTI; Kraken article: Tier I 10x, II 5x, III 3.33x, IV 2x.
- ESMA statement of 24 Feb 2026 (ESMA35-243228190-8024): perpetual futures 'are likely to fall within the scope of the existing national product intervention measures on CFDs' - the 10x perp-style products below sit in tension with the 2:1 crypto cap; treat leverage and availability as revocable
- Highest cap of any venue in the file: 50× (`hyperliquid`); highest at a venue with an EU-authorised entity: 30× (`ibkr_ie`).
- **200× is not available at any venue in venues.json.** The 200× rows above are arithmetic, not an account the owner can open at an EU-regulated venue.

| venue | highest numeric cap | EU entity claimed | legal entity (venues.json) |
|---|---:|---|---|
| `ibkr_ie` | 30× | yes | Interactive Brokers Ireland Limited, regulated by the Central Bank of Ireland (C423427), member of the Irish I |
| `kraken_pro_spot` | 10× | yes | Payward Europe Solutions Limited (Central Bank of Ireland, MiCA CASP authorised 25/06/2025, NL in passport lis |
| `kraken_derivatives_eea` | 10× | yes | Payward Europe Digital Solutions (CY) Limited (formerly I.F. Greenfields Wealth Ltd), CySEC licence 342/17 (Mi |
| `trading212_invest` | 1× | yes | Trading 212 EU GmbH (BaFin, German Securities Trading Act) for residents of NL, DE, AT, LU, DK, NO, FI, PT, FR |
| `bitvavo` | 1× | yes | Bitvavo B.V. (Amsterdam), MiCA CASP authorised by the AFM on 26/06/2025 |
| `pepperstone_eu_ctrader` | 30× | yes | Pepperstone EU Limited, Cyprus, CySEC licence 388/20 |
| `capital_com` | 30× | yes | Capital Com SV Investments Limited, Cyprus, CySEC licence 319/17 (a second group entity, Capital Com Group Ltd |
| `ig_europe` | 30× | yes | IG Europe GmbH, authorised by BaFin and Deutsche Bundesbank (registration 148759); Dutch branch registered wit |
| `okx_europe` | 10× | yes | OKX Europe Limited (MFSA Malta, MiCA CASP authorised 27/01/2025, NL in passport list) for spot; OKX Europe Mar |
| `coinbase_eu` | 10× | yes | Coinbase Luxembourg S.A. (CSSF, MiCA CASP authorised 20/06/2025, NL in passport list) for spot; Coinbase Finan |
| `one_trading` | 10× | yes | One Trading Exchange B.V. (Amsterdam, KvK 88528766), regulated by the AFM as an investment firm operating an o |
| `hyperliquid` | 50× | no | none serving the EU: no MiFID or MiCA authorisation is claimed |
