# FACTORY v2 — realism pass (PREREGISTRATION_v2 §6)

## Realism pass — 2026-11-10T17:54:41Z (real data)

Pre-registration sha256 `83d568c3b3b51692…`. Account sizes EUR 1,000, 5,000, 10,000; monthly contribution EUR 0 / 100; EUR/USD 1.1193 (ECB euro foreign exchange reference rates, value date 2026-11-09).

### How to read this

- Each account opens on the first print of the lane's FULL window, flat, with the stated cash; contributions arrive on the first print of each later calendar month. Warm-up rows are not simulated. A scheduled (long-only) book makes its opening trade at once, so until the ideal account's next scheduled rebalance the two can hold slightly different weights.
- Timing, rebalance schedule and no-trade band are the Tier-1 runner's. Returns (CAGR, vol, Sharpe, drawdown) are time-weighted from the account's per-print net, so a contribution is not a return.
- Returns and tracking error — the account's and the ideal's alike — are measured from the first print on which the account's opening trade earns (one print after the opening on the crypto lanes, two on FX and MACRO): before it the new account is flat while the ideal book is already invested. Final equity and cost totals cover the account's whole life.
- IDEAL = the same book in the Tier-1 drift-aware account: frictionless fractional venue plus the lane's base proportional cost. 'Share of ideal' = the venue account's arithmetic annual net return divided by the ideal's, defined only when the ideal's is positive (below zero: the venue account lost money where the ideal made some). Tracking error = annualised standard deviation of (venue net - ideal net) per print.
- Currency: USD, the panels' currency; EUR amounts are converted at the ECB reference rate in venues.json. The EUR/USD exposure of a EUR account is not modelled, so multiples of starting equity are what to read.
- Excess-return accounts: the carry panel charges the risk-free rate on funded positions and no venue cash interest is credited (the rates are unknown in venues.json).
- Instruments the venue does not list, or that cannot be mapped with certainty, are not held; their targets are not re-distributed. Today's listings and lot sizes are applied to the whole history.
- Orders fill in full at the print plus or minus half the spread: no market impact, no partial fills. The leverage cap is enforced when trading and only counted between trades; margin calls are not modelled. 'Max margin use' is the largest gross notional / leverage cap / equity on any print: 1.000 is the limit, and a few bp above it on an unlevered venue is the cost of the last rebalance, not borrowing.
- Costs in bp per year are bp of the account's average equity over its life.

### Instrument metadata used

- `kraken_instruments`: https://futures.kraken.com/derivatives/api/v3/instruments — fetched 2026-11-10T16:53:24Z by scripts/factory/v2_extras.py; sha256 `5cdaaad744f329f0…`; `/home/anont/meme/research/factory/landscape/evidence/venue_instruments/kraken_futures_instruments.json`
- `bitvavo_markets`: https://api.bitvavo.com/v2/markets — fetched 2026-11-10T16:53:25Z by scripts/factory/v2_extras.py; sha256 `82327c410a4c8fa7…`; `/home/anont/meme/research/factory/landscape/evidence/venue_instruments/bitvavo_markets.json`
- `kraken_tickers`: https://futures.kraken.com/derivatives/api/v3/tickers — fetched 2026-11-10T13:52:47.257Z by the landscape task (platforms_R1), NOT by v2_extras; sha256 `17d897c536ae8eac…`; `/home/anont/meme/research/factory/landscape/evidence/venue_instruments/kraken_futures_tickers.landscape_copy.json`

### P.MACRO.LO_TREND @ `trading212_invest`

40 of the book's 40 instruments are simulated (100.0% of its gross target exposure inside the window); 2477 prints, 2017-01-03 → 2026-11-09 (returns scored from 2017-01-05). Long-only, trades on the monthly schedule. Ideal reference: P.MACRO.LO_TREND.parquet column 'base' (Tier-1 drift-aware account, ideal venue, lane base cost) — CAGR 1.3%, Sharpe 0.20, max drawdown -18.8%.

- ASSUMED instrument availability: every US-listed ETF of the panel is taken to have a UCITS equivalent at Trading 212 (prereg §2: US ETFs proxy UCITS funds). The instrument list needs an API key and was not read.
- ASSUMED: EUR-denominated share classes, so the 15 bp FX fee of venues.json does not apply; a USD line would add 15 bp per side.
- Cash interest is not credited: the rate is unknown in venues.json.

Venue fields (`venues.json` = read by `VenueSpec.from_json`; VERIFIED / ASSUMED = an explicit override):

| field | value | unit | basis | instruments | source |
|---|---|---|---|---|---|
| fee_bp | 0 | bp/side | venues.json | 40 | trading212_invest.fee_bp_taker ['stocks_etfs'] number |
| min_fee | 0 | USD/order | venues.json | 40 | trading212_invest.min_fee_per_order [amount] number |
| half_spread_bp | 5 | bp/side | ASSUMED | 40 | prereg §3: MACRO long-only base cost 5 bp per side with zero commission — the exchange half-spread of UCITS ETFs is unmeasured (venues.json: null, the API has no market-data endpoint) |
| lot_step | 0 | units | ASSUMED | 40 | venues.json lot_step text: 'fractional quantities; API orders by QUANTITY only' — the per-instrument quantity precision sits behind an API key and was not read; treated as continuous |
| min_notional | 1.1193 | USD | ASSUMED | 40 | venues.json min_order_notional: null (UNKNOWN). EUR 1 is the commonly reported minimum order value for fractional orders, taken from general knowledge and NOT verified on 2026-11-10; the per-instrument minTradeQuantity of the keyed instruments endpoint was not read. Converted at EURUSD 1.1193 |
| contract_notional | 1 | x price | ASSUMED | 40 | by construction: one unit = one fund share at the panel price |
| financing_long_bp_year | 0 | bp/yr | venues.json | 40 | trading212_invest.financing_long_bp_year [markup_bp] number |
| financing_short_bp_year | unknown | bp/yr | UNKNOWN | 40 | null — not needed: the book is long-only |
| leverage_cap | 1 | x equity | venues.json | 40 | trading212_invest.leverage_caps ['invest'] number |
| cash_interest_bp_year | unknown | bp/yr | UNKNOWN | 40 | no key ('cash_interest_bp_year',) in the venue entry — not needed: no cash yield is credited (report_total=False): the venue's rate is unknown |
| cash_interest_threshold | unknown | USD | UNKNOWN | 40 | object with no usable key (pass instrument_class=...); keys: ['eur_cap', 'minimum_balance', 'note', 'rate_pct'] — not needed: no cash yield is credited (report_total=False): the venue's rate is unknown |

Results (multiples are of starting equity; returns are time-weighted):

| start EUR | +EUR/mo | final x | paid in x | CAGR | vol | Sharpe | max DD | share of ideal return | TE /yr | fees bp/yr | spread bp/yr | financing bp/yr | turnover /yr | orders | skipped: minimum / lot→0 | max margin use |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 0 | 1.133 | 1.000 | 1.3% | 7.8% | 0.20 | -18.8% | 100% | 0.02% | 0.0 | 22.4 | 0.0 | 4.5 | 3,755 | 444 / 0 | 1.006 |
| 1,000 | 100 | 13.234 | 12.800 | 1.3% | 7.8% | 0.20 | -18.8% | 100% | 0.04% | 0.0 | 23.0 | 0.0 | 4.5 | 4,083 | 130 / 0 | 1.005 |
| 5,000 | 0 | 1.133 | 1.000 | 1.3% | 7.8% | 0.20 | -18.8% | 100% | 0.00% | 0.0 | 22.5 | 0.0 | 4.5 | 4,104 | 108 / 0 | 1.005 |
| 5,000 | 100 | 3.554 | 3.360 | 1.3% | 7.8% | 0.20 | -18.8% | 100% | 0.02% | 0.0 | 22.8 | 0.0 | 4.5 | 4,148 | 69 / 0 | 1.005 |
| 10,000 | 0 | 1.134 | 1.000 | 1.3% | 7.8% | 0.20 | -18.8% | 100% | 0.00% | 0.0 | 22.5 | 0.0 | 4.5 | 4,157 | 60 / 0 | 1.005 |
| 10,000 | 100 | 2.344 | 2.180 | 1.3% | 7.8% | 0.20 | -18.8% | 100% | 0.01% | 0.0 | 22.7 | 0.0 | 4.5 | 4,176 | 42 / 0 | 1.005 |

Per-print equity (multiple of starting equity) and net return of every account, beside the ideal's: `realism_paths/P.MACRO.LO_TREND__trading212_invest.parquet`.

### P.FX.G10.ALL @ `pepperstone_eu_ctrader`

9 of the book's 9 instruments are simulated (100.0% of its gross target exposure inside the window); 6873 prints, 2000-01-03 → 2026-11-09 (returns scored from 2000-01-05). Long/short, no-trade band 10%. Ideal reference: P.FX.G10.ALL.parquet column 'base' (Tier-1 drift-aware account, ideal venue, lane base cost) — CAGR 0.8%, Sharpe 0.13, max drawdown -49.8%.

- ASSUMED instrument availability: the nine USD pairs are taken to be offered; no instrument endpoint was read.
- ASSUMED leverage class: ESMA's 30:1 'major' pairs are any two of USD, EUR, JPY, GBP, CAD, CHF (general knowledge of decision (EU) 2018/796; venues.json records the caps, not the pair list) — AUD, NZD, SEK and NOK pairs get 20:1.
- The 0.27 bp commission is venues.json's figure, derived there from USD 3 per standard lot at the EUR/USD reference price; the minimum fee is its USD 0.04 per order (rounding at 0.01 lot).

Venue fields (`venues.json` = read by `VenueSpec.from_json`; VERIFIED / ASSUMED = an explicit override):

| field | value | unit | basis | instruments | source |
|---|---|---|---|---|---|
| fee_bp | 0.27 | bp/side | venues.json | 9 | pepperstone_eu_ctrader.fee_bp_taker ['fx_cfd_razor_ctrader'] number |
| min_fee | 0.04 | USD/order | venues.json | 9 | pepperstone_eu_ctrader.min_fee_per_order [amount] number |
| half_spread_bp | 0.045 | bp/side | venues.json | 1 | pepperstone_eu_ctrader.typical_half_spread_bp ['EURUSD_razor'] number; file label: VENDOR_SCHEDULE - broker-published AVERAGE spreads for 01/08/2026-31/08/2026 (EURUSD 0.1 pip, GBPUSD 0.2, USDJPY 0.2, US500 0.4 pt, GER40 1.0 pt), converted at the reference prices; not measured |
| half_spread_bp | 0.075 | bp/side | venues.json | 1 | pepperstone_eu_ctrader.typical_half_spread_bp ['GBPUSD_razor'] number; file label: VENDOR_SCHEDULE - broker-published AVERAGE spreads for 01/08/2026-31/08/2026 (EURUSD 0.1 pip, GBPUSD 0.2, USDJPY 0.2, US500 0.4 pt, GER40 1.0 pt), converted at the reference prices; not measured |
| half_spread_bp | 0.063 | bp/side | venues.json | 1 | pepperstone_eu_ctrader.typical_half_spread_bp ['USDJPY_razor'] number; file label: VENDOR_SCHEDULE - broker-published AVERAGE spreads for 01/08/2026-31/08/2026 (EURUSD 0.1 pip, GBPUSD 0.2, USDJPY 0.2, US500 0.4 pt, GER40 1.0 pt), converted at the reference prices; not measured |
| half_spread_bp | 0.33 | bp/side | ASSUMED | 4 | prereg §3: FX-majors base 0.6 bp per side less the commission — venues.json has no published average spread for this pair |
| half_spread_bp | 2.5 | bp/side | ASSUMED | 2 | prereg §3: FX Scandinavia spreads ASSUMED, 2.5 bp per side (charged on top of the commission) |
| lot_step | 1000 | units | VERIFIED | 4 | venues.json pepperstone_eu_ctrader.lot_step, verbatim: '0.01 lot (1,000 base units) on FX' — the panel instrument is the base currency of the pair |
| lot_step | 818.726 … 157947 (5 values) | units | ASSUMED | 5 | APPROXIMATION: the pair is USD-base, so a 0.01 lot is 1,000 US dollars (venues.json lot_step); converted to units of the panel instrument at the panel's latest price and held fixed over the whole history |
| min_notional | 0 | USD | VERIFIED | 9 | venues.json min_order_notional.fx_cfd: 1000 base-currency units = one 0.01 lot = one lot step, which lot_step already enforces; there is no separate currency minimum |
| contract_notional | 1 | x price | ASSUMED | 9 | by construction: one unit = one unit of the currency at the panel's USD price |
| financing_long_bp_year | 100 | bp/yr | ASSUMED | 9 | prereg §3: swap mark-up 100 bp/yr long and short — Pepperstone's own annual equivalent is not established in venues.json (peers 58-109 bp/yr, derived) |
| financing_short_bp_year | 100 | bp/yr | ASSUMED | 9 | prereg §3: swap mark-up 100 bp/yr long and short — Pepperstone's own annual equivalent is not established in venues.json (peers 58-109 bp/yr, derived) |
| leverage_cap | 30 | x equity | venues.json | 5 | pepperstone_eu_ctrader.leverage_caps ['fx_major'] number |
| leverage_cap | 20 | x equity | venues.json | 4 | pepperstone_eu_ctrader.leverage_caps ['fx_minor_gold_major_index'] number |
| cash_interest_bp_year | unknown | bp/yr | UNKNOWN | 9 | no key ('cash_interest_bp_year',) in the venue entry — not needed: no cash yield is credited (report_total=False): the venue's rate is unknown |
| cash_interest_threshold | unknown | USD | UNKNOWN | 9 | null — not needed: no cash yield is credited (report_total=False): the venue's rate is unknown |

Results (multiples are of starting equity; returns are time-weighted):

| start EUR | +EUR/mo | final x | paid in x | CAGR | vol | Sharpe | max DD | share of ideal return | TE /yr | fees bp/yr | spread bp/yr | financing bp/yr | turnover /yr | orders | skipped: minimum / lot→0 | max margin use |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 0 | 1.465 | 1.000 | 1.4% | 7.1% | 0.23 | -25.7% | 115% | 7.85% | 17.3 | 19.1 | 92.3 | 40.6 | 1,781 | 0 / 53,435 | 0.331 |
| 1,000 | 100 | 27.773 | 33.200 | 0.6% | 10.8% | 0.11 | -49.3% | 83% | 1.79% | 32.8 | 72.3 | 281.4 | 104.3 | 23,150 | 0 / 12,496 | 0.411 |
| 5,000 | 0 | 1.360 | 1.000 | 1.1% | 10.5% | 0.16 | -46.7% | 117% | 1.95% | 32.1 | 60.8 | 241.1 | 97.1 | 15,895 | 0 / 18,464 | 0.422 |
| 5,000 | 100 | 6.648 | 7.440 | 0.8% | 11.1% | 0.13 | -48.0% | 101% | 0.96% | 32.3 | 73.3 | 282.5 | 108.9 | 26,900 | 0 / 8,364 | 0.428 |
| 10,000 | 0 | 1.351 | 1.000 | 1.1% | 11.0% | 0.16 | -47.3% | 119% | 1.01% | 31.5 | 68.6 | 264.2 | 107.2 | 24,271 | 0 / 9,883 | 0.430 |
| 10,000 | 100 | 4.008 | 4.220 | 1.0% | 11.2% | 0.14 | -47.7% | 110% | 0.67% | 31.9 | 74.1 | 283.2 | 111.4 | 29,850 | 0 / 5,915 | 0.435 |

Per-print equity (multiple of starting equity) and net return of every account, beside the ideal's: `realism_paths/P.FX.G10.ALL__pepperstone_eu_ctrader.parquet`.

### P.CRYPTO.TREND @ `kraken_derivatives_eea`

126 of the book's 317 instruments are simulated (87.9% of its gross target exposure inside the window); 2324 prints, 2020-07-01 → 2026-11-10 (returns scored from 2020-07-02). Long/short, no-trade band 10%. Ideal reference: P.CRYPTO.TREND.parquet column 'base' (Tier-1 drift-aware account, ideal venue, lane base cost) — CAGR 21.3%, Sharpe 0.90, max drawdown -26.2%.

- Eligible = PF_ perpetual, tradeable, not suspended / expired / post-only, not a TradFi perpetual and not in a non-crypto category (stocks, commodities, FX, indices, stablecoins and gold tokens), permitted on the 'europa' platform (read as the EEA platform — an inference recorded in venues.json), not banned for NL.
- Mapping corroborated by price: Kraken markPrice from the tickers snapshot of 2026-11-10T13:52:47.257Z (the landscape task (platforms_R1), NOT by v2_extras) against the panel's last Binance print (2026-11-10 00:00:00+00:00), tolerance x2.
- Today's listing and lot sizes are applied to the whole history; Kraken's past listings are not reconstructed.
- Payload openingDate of the mapped perpetuals: 2022-03-22 … 2025-12-22. Each is simulated over the whole window all the same: before its opening date the contract did not exist at this venue.

Venue fields (`venues.json` = read by `VenueSpec.from_json`; VERIFIED / ASSUMED = an explicit override):

| field | value | unit | basis | instruments | source |
|---|---|---|---|---|---|
| fee_bp | 5 | bp/side | venues.json | 126 | kraken_derivatives_eea.fee_bp_taker ['all_perps_and_futures'] number |
| min_fee | 0 | USD/order | ASSUMED | 126 | venues.json min_fee_per_order: null; its min_order_notional.note reads 'no minimum fee' (the schedule is proportional) |
| half_spread_bp | 2 | bp/side | ASSUMED | 123 | prereg §3: CRYPTO-PERP base 7 bp per side less the taker fee — only BTC, ETH and SOL were measured |
| half_spread_bp | 0.07 | bp/side | venues.json | 1 | kraken_derivatives_eea.typical_half_spread_bp ['PF_XBTUSD'] number; file label: MEASURED - top of book from the public tickers endpoint, 2026-11-10 13:52 UTC |
| half_spread_bp | 0.24 | bp/side | venues.json | 1 | kraken_derivatives_eea.typical_half_spread_bp ['PF_ETHUSD'] number; file label: MEASURED - top of book from the public tickers endpoint, 2026-11-10 13:52 UTC |
| half_spread_bp | 0.6 | bp/side | venues.json | 1 | kraken_derivatives_eea.typical_half_spread_bp ['PF_SOLUSD'] number; file label: MEASURED - top of book from the public tickers endpoint, 2026-11-10 13:52 UTC |
| lot_step | 0.0001 … 100 (7 values) | units | VERIFIED | 126 | Kraken instruments payload: 10^(-contractValueTradePrecision) contracts of contractSize 1 unit of base, divided by the units of base in one panel unit |
| min_notional | 0 | USD | ASSUMED | 126 | the payload documents no minimum-order field; the smallest order is one increment of contractValueTradePrecision (venues.json: 'PF_XBTUSD 0.0001 BTC'), which lot_step already enforces |
| contract_notional | 1 | x price | VERIFIED | 126 | Kraken instruments payload: contractSize = 1 (one contract = one unit of base); the panel price is per panel unit |
| financing_long_bp_year | 0 | bp/yr | ASSUMED | 126 | prereg §3: no holding cost on CRYPTO-PERP beyond the panel's funding leg — which is realised BINANCE funding, not what a Kraken account pays (prereg §2, accepted limit) |
| financing_short_bp_year | 0 | bp/yr | ASSUMED | 126 | prereg §3: no holding cost on CRYPTO-PERP beyond the panel's funding leg — which is realised BINANCE funding, not what a Kraken account pays (prereg §2, accepted limit) |
| leverage_cap | 2 | x equity | ASSUMED | 126 | prereg §3 gross cap 2x: ESMA's statement of 24 Feb 2026 puts perpetual futures under the 2:1 crypto CFD cap; Kraken's own EEA tier-I schedule is 10x [venues.json had 10] |
| cash_interest_bp_year | unknown | bp/yr | UNKNOWN | 126 | no key ('cash_interest_bp_year',) in the venue entry — not needed: no cash yield is credited (report_total=False): the venue's rate is unknown |
| cash_interest_threshold | unknown | USD | UNKNOWN | 126 | null — not needed: no cash yield is credited (report_total=False): the venue's rate is unknown |

Dropped — not held at this venue (191 instruments; each reason is in the JSON):

- not a plain live Binance symbol (earlier segment, re-used ticker, or a name that does not parse) (7): `AIAUSDTSETTLED`, `BNXUSDTSETTLED`, `ICPUSDT_SETTLED`, `LITUSDTSETTLED`, `TLMUSDTSETTLED`, `币安人生USDT`, `龙虾USDT`
- the venue lists no instrument with that base (184): `1000LUNCUSDT`, `1000RATSUSDT`, `1000SATSUSDT`, `1000XECUSDT`, `1MBABYDOGEUSDT`, `ACHUSDT`, `ACTUSDT`, `AEVOUSDT`, `AGIXUSDT`, `AGTUSDT`, `AI16ZUSDT`, `AINUSDT`, `AIOTUSDT`, `AKEUSDT`, `ALCHUSDT`, `ALLOUSDT`, `ALPACAUSDT`, `ALPHAUSDT`, `ALPINEUSDT`, `ANIMEUSDT`, `ANKRUSDT`, `API3USDT`, `APRUSDT`, `ARIAUSDT`, `ARKUSDT`, `ARPAUSDT`, `AUCTIONUSDT`, `BAKEUSDT`, `BANANAS31USDT`, `BANDUSDT`, `BANKUSDT`, `BEATUSDT`, `BELUSDT`, `BERAUSDT`, `BIGTIMEUSDT`, `BLESSUSDT`, `BLURUSDT`, `BLZUSDT`, `BNTUSDT`, `BNXUSDT`, `BRUSDT`, `BSBUSDT`, `BTRUSDT`, `BTTUSDT`, `BTWUSDT`, `BULLAUSDT`, `BUSDT`, `CELRUSDT`, `CHRUSDT`, `CKBUSDT`, `COCOSUSDT`, `COTIUSDT`, `COWUSDT`, `CYSUSDT`, `DARUSDT`, `DEGOUSDT`, `DENTUSDT`, `DUSKUSDT`, `EDENUSDT`, `ENJUSDT`, `ENSOUSDT`, `EOSUSDT`, `ESPORTSUSDT`, `EVAAUSDT`, `FHEUSDT`, `FLMUSDT`, `FOLKSUSDT`, `FRONTUSDT`, `FTMUSDT`, `FTTUSDT`, `FUNUSDT`, `GIGGLEUSDT`, `GLMUSDT`, `GMTUSDT`, `GTCUSDT`, `HEIUSDT`, `HEMIUSDT`, `HIFIUSDT`, `HIGHUSDT`, `HNTUSDT`, `HOMEUSDT`, `HUSDT`, `HYPERUSDT`, `ICXUSDT`, `IDUSDT`, `IOSTUSDT`, `IOTAUSDT`, `IOUSDT`, `IPUSDT`, `IRYSUSDT`, `JCTUSDT`, `JELLYJELLYUSDT`, `KEEPUSDT`, `KITEUSDT`, `KLAYUSDT`, `KNCUSDT`, `KSMUSDT`, `LABUSDT`, `LAYERUSDT`, `LENDUSDT`, `LEVERUSDT`, `LIGHTUSDT`, `LINAUSDT`, `LRCUSDT`, `LSKUSDT`, `LUNAUSDT`, `LYNUSDT`, `MAGICUSDT`, `MASKUSDT`, `MATICUSDT`, `MEMEUSDT`, `MERLUSDT`, `MINAUSDT`, `MKRUSDT`, `MTLUSDT`, `MUSDT`, `MYXUSDT`, `NEIROETHUSDT`, `NEOUSDT`, `NMRUSDT`, `NOMUSDT`, `OCEANUSDT`, `OGNUSDT`, `OMGUSDT`, `OMUSDT`, `ONEUSDT`, `ONGUSDT`, `ONUSDT`, `ORCAUSDT`, `PERPUSDT`, `PIEVERSEUSDT`, `PIPPINUSDT`, `PLAYUSDT`, `POLYXUSDT`, `POWERUSDT`, `POWRUSDT`, `PROMUSDT`, `QUSDT`, `RAREUSDT`, `RAVEUSDT`, `REEFUSDT`, `RENUSDT`, `RIFUSDT`, `RLCUSDT`, `RNDRUSDT`, `RVNUSDT`, `SAHARAUSDT`, `SENTUSDT`, `SFPUSDT`, `SIGNUSDT`, `SIRENUSDT`, `SKLUSDT`, `SKYAIUSDT`, `SPELLUSDT`, `SRMUSDT`, `STMXUSDT`, `STORJUSDT`, `STOUSDT`, `SUSDT`, `SXPUSDT`, `TAUSDT`, `THETAUSDT`, `TNSRUSDT`, `TOMOUSDT`, `TONUSDT`, `TRADOORUSDT`, `TUTUSDT`, `UBUSDT`, `UMAUSDT`, `UNFIUSDT`, `USELESSUSDT`, `UXLINKUSDT`, `VANRYUSDT`, `VELVETUSDT`, `VETUSDT`, `VINEUSDT`, `VOXELUSDT`, `VVVUSDT`, `WAVESUSDT`, `WCTUSDT`, `YFIIUSDT`, `ZEREBROUSDT`, `ZILUSDT`, `ZRXUSDT`

Results (multiples are of starting equity; returns are time-weighted):

| start EUR | +EUR/mo | final x | paid in x | CAGR | vol | Sharpe | max DD | share of ideal return | TE /yr | fees bp/yr | spread bp/yr | financing bp/yr | turnover /yr | orders | skipped: minimum / lot→0 | max margin use |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 0 | 3.128 | 1.000 | 19.6% | 21.6% | 0.94 | -26.2% | 91% | 6.03% | 130.3 | 43.8 | 0.0 | 25.7 | 28,497 | 0 / 3,099 | 0.960 |
| 1,000 | 100 | 15.136 | 8.600 | 19.4% | 21.8% | 0.92 | -26.6% | 90% | 5.92% | 137.8 | 46.6 | 0.0 | 25.9 | 30,437 | 0 / 1,573 | 0.962 |
| 5,000 | 0 | 3.085 | 1.000 | 19.4% | 21.8% | 0.92 | -26.4% | 90% | 5.85% | 131.5 | 44.2 | 0.0 | 26.0 | 31,357 | 0 / 741 | 0.963 |
| 5,000 | 100 | 5.481 | 2.520 | 19.3% | 21.8% | 0.92 | -26.5% | 89% | 5.85% | 134.5 | 45.3 | 0.0 | 26.0 | 31,408 | 0 / 593 | 0.964 |
| 10,000 | 0 | 3.072 | 1.000 | 19.3% | 21.9% | 0.92 | -26.4% | 89% | 5.83% | 131.5 | 44.2 | 0.0 | 26.0 | 31,652 | 0 / 407 | 0.964 |
| 10,000 | 100 | 4.271 | 1.760 | 19.3% | 21.9% | 0.92 | -26.5% | 89% | 5.83% | 133.3 | 44.9 | 0.0 | 26.0 | 31,662 | 0 / 365 | 0.964 |

Per-print equity (multiple of starting equity) and net return of every account, beside the ideal's: `realism_paths/P.CRYPTO.TREND__kraken_derivatives_eea.parquet`.

### P.CRYPTO.ALL @ `kraken_derivatives_eea`

126 of the book's 317 instruments are simulated (87.9% of its gross target exposure inside the window); 2324 prints, 2020-07-01 → 2026-11-10 (returns scored from 2020-07-02). Long/short, no-trade band 10%. Ideal reference: P.CRYPTO.ALL.parquet column 'base' (Tier-1 drift-aware account, ideal venue, lane base cost) — CAGR 21.3%, Sharpe 0.90, max drawdown -26.2%.

- Eligible = PF_ perpetual, tradeable, not suspended / expired / post-only, not a TradFi perpetual and not in a non-crypto category (stocks, commodities, FX, indices, stablecoins and gold tokens), permitted on the 'europa' platform (read as the EEA platform — an inference recorded in venues.json), not banned for NL.
- Mapping corroborated by price: Kraken markPrice from the tickers snapshot of 2026-11-10T13:52:47.257Z (the landscape task (platforms_R1), NOT by v2_extras) against the panel's last Binance print (2026-11-10 00:00:00+00:00), tolerance x2.
- Today's listing and lot sizes are applied to the whole history; Kraken's past listings are not reconstructed.
- Payload openingDate of the mapped perpetuals: 2022-03-22 … 2025-12-22. Each is simulated over the whole window all the same: before its opening date the contract did not exist at this venue.

Venue fields (`venues.json` = read by `VenueSpec.from_json`; VERIFIED / ASSUMED = an explicit override):

| field | value | unit | basis | instruments | source |
|---|---|---|---|---|---|
| fee_bp | 5 | bp/side | venues.json | 126 | kraken_derivatives_eea.fee_bp_taker ['all_perps_and_futures'] number |
| min_fee | 0 | USD/order | ASSUMED | 126 | venues.json min_fee_per_order: null; its min_order_notional.note reads 'no minimum fee' (the schedule is proportional) |
| half_spread_bp | 2 | bp/side | ASSUMED | 123 | prereg §3: CRYPTO-PERP base 7 bp per side less the taker fee — only BTC, ETH and SOL were measured |
| half_spread_bp | 0.07 | bp/side | venues.json | 1 | kraken_derivatives_eea.typical_half_spread_bp ['PF_XBTUSD'] number; file label: MEASURED - top of book from the public tickers endpoint, 2026-11-10 13:52 UTC |
| half_spread_bp | 0.24 | bp/side | venues.json | 1 | kraken_derivatives_eea.typical_half_spread_bp ['PF_ETHUSD'] number; file label: MEASURED - top of book from the public tickers endpoint, 2026-11-10 13:52 UTC |
| half_spread_bp | 0.6 | bp/side | venues.json | 1 | kraken_derivatives_eea.typical_half_spread_bp ['PF_SOLUSD'] number; file label: MEASURED - top of book from the public tickers endpoint, 2026-11-10 13:52 UTC |
| lot_step | 0.0001 … 100 (7 values) | units | VERIFIED | 126 | Kraken instruments payload: 10^(-contractValueTradePrecision) contracts of contractSize 1 unit of base, divided by the units of base in one panel unit |
| min_notional | 0 | USD | ASSUMED | 126 | the payload documents no minimum-order field; the smallest order is one increment of contractValueTradePrecision (venues.json: 'PF_XBTUSD 0.0001 BTC'), which lot_step already enforces |
| contract_notional | 1 | x price | VERIFIED | 126 | Kraken instruments payload: contractSize = 1 (one contract = one unit of base); the panel price is per panel unit |
| financing_long_bp_year | 0 | bp/yr | ASSUMED | 126 | prereg §3: no holding cost on CRYPTO-PERP beyond the panel's funding leg — which is realised BINANCE funding, not what a Kraken account pays (prereg §2, accepted limit) |
| financing_short_bp_year | 0 | bp/yr | ASSUMED | 126 | prereg §3: no holding cost on CRYPTO-PERP beyond the panel's funding leg — which is realised BINANCE funding, not what a Kraken account pays (prereg §2, accepted limit) |
| leverage_cap | 2 | x equity | ASSUMED | 126 | prereg §3 gross cap 2x: ESMA's statement of 24 Feb 2026 puts perpetual futures under the 2:1 crypto CFD cap; Kraken's own EEA tier-I schedule is 10x [venues.json had 10] |
| cash_interest_bp_year | unknown | bp/yr | UNKNOWN | 126 | no key ('cash_interest_bp_year',) in the venue entry — not needed: no cash yield is credited (report_total=False): the venue's rate is unknown |
| cash_interest_threshold | unknown | USD | UNKNOWN | 126 | null — not needed: no cash yield is credited (report_total=False): the venue's rate is unknown |

Dropped — not held at this venue (191 instruments; each reason is in the JSON):

- not a plain live Binance symbol (earlier segment, re-used ticker, or a name that does not parse) (7): `AIAUSDTSETTLED`, `BNXUSDTSETTLED`, `ICPUSDT_SETTLED`, `LITUSDTSETTLED`, `TLMUSDTSETTLED`, `币安人生USDT`, `龙虾USDT`
- the venue lists no instrument with that base (184): `1000LUNCUSDT`, `1000RATSUSDT`, `1000SATSUSDT`, `1000XECUSDT`, `1MBABYDOGEUSDT`, `ACHUSDT`, `ACTUSDT`, `AEVOUSDT`, `AGIXUSDT`, `AGTUSDT`, `AI16ZUSDT`, `AINUSDT`, `AIOTUSDT`, `AKEUSDT`, `ALCHUSDT`, `ALLOUSDT`, `ALPACAUSDT`, `ALPHAUSDT`, `ALPINEUSDT`, `ANIMEUSDT`, `ANKRUSDT`, `API3USDT`, `APRUSDT`, `ARIAUSDT`, `ARKUSDT`, `ARPAUSDT`, `AUCTIONUSDT`, `BAKEUSDT`, `BANANAS31USDT`, `BANDUSDT`, `BANKUSDT`, `BEATUSDT`, `BELUSDT`, `BERAUSDT`, `BIGTIMEUSDT`, `BLESSUSDT`, `BLURUSDT`, `BLZUSDT`, `BNTUSDT`, `BNXUSDT`, `BRUSDT`, `BSBUSDT`, `BTRUSDT`, `BTTUSDT`, `BTWUSDT`, `BULLAUSDT`, `BUSDT`, `CELRUSDT`, `CHRUSDT`, `CKBUSDT`, `COCOSUSDT`, `COTIUSDT`, `COWUSDT`, `CYSUSDT`, `DARUSDT`, `DEGOUSDT`, `DENTUSDT`, `DUSKUSDT`, `EDENUSDT`, `ENJUSDT`, `ENSOUSDT`, `EOSUSDT`, `ESPORTSUSDT`, `EVAAUSDT`, `FHEUSDT`, `FLMUSDT`, `FOLKSUSDT`, `FRONTUSDT`, `FTMUSDT`, `FTTUSDT`, `FUNUSDT`, `GIGGLEUSDT`, `GLMUSDT`, `GMTUSDT`, `GTCUSDT`, `HEIUSDT`, `HEMIUSDT`, `HIFIUSDT`, `HIGHUSDT`, `HNTUSDT`, `HOMEUSDT`, `HUSDT`, `HYPERUSDT`, `ICXUSDT`, `IDUSDT`, `IOSTUSDT`, `IOTAUSDT`, `IOUSDT`, `IPUSDT`, `IRYSUSDT`, `JCTUSDT`, `JELLYJELLYUSDT`, `KEEPUSDT`, `KITEUSDT`, `KLAYUSDT`, `KNCUSDT`, `KSMUSDT`, `LABUSDT`, `LAYERUSDT`, `LENDUSDT`, `LEVERUSDT`, `LIGHTUSDT`, `LINAUSDT`, `LRCUSDT`, `LSKUSDT`, `LUNAUSDT`, `LYNUSDT`, `MAGICUSDT`, `MASKUSDT`, `MATICUSDT`, `MEMEUSDT`, `MERLUSDT`, `MINAUSDT`, `MKRUSDT`, `MTLUSDT`, `MUSDT`, `MYXUSDT`, `NEIROETHUSDT`, `NEOUSDT`, `NMRUSDT`, `NOMUSDT`, `OCEANUSDT`, `OGNUSDT`, `OMGUSDT`, `OMUSDT`, `ONEUSDT`, `ONGUSDT`, `ONUSDT`, `ORCAUSDT`, `PERPUSDT`, `PIEVERSEUSDT`, `PIPPINUSDT`, `PLAYUSDT`, `POLYXUSDT`, `POWERUSDT`, `POWRUSDT`, `PROMUSDT`, `QUSDT`, `RAREUSDT`, `RAVEUSDT`, `REEFUSDT`, `RENUSDT`, `RIFUSDT`, `RLCUSDT`, `RNDRUSDT`, `RVNUSDT`, `SAHARAUSDT`, `SENTUSDT`, `SFPUSDT`, `SIGNUSDT`, `SIRENUSDT`, `SKLUSDT`, `SKYAIUSDT`, `SPELLUSDT`, `SRMUSDT`, `STMXUSDT`, `STORJUSDT`, `STOUSDT`, `SUSDT`, `SXPUSDT`, `TAUSDT`, `THETAUSDT`, `TNSRUSDT`, `TOMOUSDT`, `TONUSDT`, `TRADOORUSDT`, `TUTUSDT`, `UBUSDT`, `UMAUSDT`, `UNFIUSDT`, `USELESSUSDT`, `UXLINKUSDT`, `VANRYUSDT`, `VELVETUSDT`, `VETUSDT`, `VINEUSDT`, `VOXELUSDT`, `VVVUSDT`, `WAVESUSDT`, `WCTUSDT`, `YFIIUSDT`, `ZEREBROUSDT`, `ZILUSDT`, `ZRXUSDT`

Results (multiples are of starting equity; returns are time-weighted):

| start EUR | +EUR/mo | final x | paid in x | CAGR | vol | Sharpe | max DD | share of ideal return | TE /yr | fees bp/yr | spread bp/yr | financing bp/yr | turnover /yr | orders | skipped: minimum / lot→0 | max margin use |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 0 | 3.128 | 1.000 | 19.6% | 21.6% | 0.94 | -26.2% | 91% | 6.03% | 130.3 | 43.8 | 0.0 | 25.7 | 28,497 | 0 / 3,099 | 0.960 |
| 1,000 | 100 | 15.136 | 8.600 | 19.4% | 21.8% | 0.92 | -26.6% | 90% | 5.92% | 137.8 | 46.6 | 0.0 | 25.9 | 30,437 | 0 / 1,573 | 0.962 |
| 5,000 | 0 | 3.085 | 1.000 | 19.4% | 21.8% | 0.92 | -26.4% | 90% | 5.85% | 131.5 | 44.2 | 0.0 | 26.0 | 31,357 | 0 / 741 | 0.963 |
| 5,000 | 100 | 5.481 | 2.520 | 19.3% | 21.8% | 0.92 | -26.5% | 89% | 5.85% | 134.5 | 45.3 | 0.0 | 26.0 | 31,408 | 0 / 593 | 0.964 |
| 10,000 | 0 | 3.072 | 1.000 | 19.3% | 21.9% | 0.92 | -26.4% | 89% | 5.83% | 131.5 | 44.2 | 0.0 | 26.0 | 31,652 | 0 / 407 | 0.964 |
| 10,000 | 100 | 4.271 | 1.760 | 19.3% | 21.9% | 0.92 | -26.5% | 89% | 5.83% | 133.3 | 44.9 | 0.0 | 26.0 | 31,662 | 0 / 365 | 0.964 |

Per-print equity (multiple of starting equity) and net return of every account, beside the ideal's: `realism_paths/P.CRYPTO.ALL__kraken_derivatives_eea.parquet`.

### P.CRYPTO.LO_TREND @ `bitvavo`

128 of the book's 205 instruments are simulated (88.6% of its gross target exposure inside the window); 3024 prints, 2018-08-01 → 2026-11-10 (returns scored from 2018-08-02). Long-only, trades on the weekly schedule. Ideal reference: P.CRYPTO.LO_TREND.parquet column 'base' (Tier-1 drift-aware account, ideal venue, lane base cost) — CAGR 5.9%, Sharpe 0.35, max drawdown -54.1%.

- Eligible = <BASE>-EUR market in status 'trading'.
- Mapping corroborated by price: the EUR price the payload itself implies (minOrderInQuoteAsset / minOrderInBaseAsset, converted at EURUSD 1.1193) against the panel's last Binance print (2026-11-10 00:00:00+00:00), tolerance x2.
- The account trades EUR pairs; the simulation is in the panel's USD(T) prices and the EUR/USD move is not modelled.
- Today's listing and lot sizes are applied to the whole history. Cash interest is not credited (unknown).

Venue fields (`venues.json` = read by `VenueSpec.from_json`; VERIFIED / ASSUMED = an explicit override):

| field | value | unit | basis | instruments | source |
|---|---|---|---|---|---|
| fee_bp | 25 | bp/side | venues.json | 128 | bitvavo.fee_bp_taker ['crypto_spot_eur_markets'] number |
| min_fee | 0 | USD/order | ASSUMED | 128 | venues.json min_fee_per_order: null; the published schedule is proportional and lists no per-order minimum |
| half_spread_bp | 2 | bp/side | ASSUMED | 125 | prereg §3: CRYPTO-SPOT base 27 bp per side less the taker fee — only BTC, ETH and SOL were measured |
| half_spread_bp | 0.08 | bp/side | venues.json | 1 | bitvavo.typical_half_spread_bp ['BTC-EUR'] number; file label: MEASURED - top of book from the public ticker endpoint, 2026-11-10 14:12 UTC |
| half_spread_bp | 0.03 | bp/side | venues.json | 1 | bitvavo.typical_half_spread_bp ['ETH-EUR'] number; file label: MEASURED - top of book from the public ticker endpoint, 2026-11-10 14:12 UTC |
| half_spread_bp | 0.47 | bp/side | venues.json | 1 | bitvavo.typical_half_spread_bp ['SOL-EUR'] number; file label: MEASURED - top of book from the public ticker endpoint, 2026-11-10 14:12 UTC |
| lot_step | 1e-08 … 1 (8 values) | units | VERIFIED | 128 | Bitvavo markets payload: 10^(-quantityDecimals) units of base, divided by the units of base in one panel unit |
| min_notional | 5.5965 | USD | VERIFIED | 128 | Bitvavo markets payload: minOrderInQuoteAsset (EUR), converted at the ECB reference EURUSD 1.1193 [venues.json had 5] |
| contract_notional | 1 | x price | ASSUMED | 128 | by construction: spot, one unit = one panel unit at the panel price |
| financing_long_bp_year | 0 | bp/yr | venues.json | 128 | bitvavo.financing_long_bp_year ['spot'] [markup_bp] number |
| financing_short_bp_year | unknown | bp/yr | UNKNOWN | 128 | object with no usable key (pass instrument_class=...); keys: ['margin_borrow'] — not needed: the book is long-only |
| leverage_cap | 1 | x equity | venues.json | 128 | bitvavo.leverage_caps ['spot'] number |
| cash_interest_bp_year | unknown | bp/yr | UNKNOWN | 128 | no key ('cash_interest_bp_year',) in the venue entry — not needed: no cash yield is credited (report_total=False): the venue's rate is unknown |
| cash_interest_threshold | unknown | USD | UNKNOWN | 128 | null — not needed: no cash yield is credited (report_total=False): the venue's rate is unknown |

Dropped — not held at this venue (77 instruments; each reason is in the JSON):

- not a plain live Binance symbol (earlier segment, re-used ticker, or a name that does not parse) (4): `FTTUSDT@20221116`, `LUNAUSDT@20220514`, `STRAXUSDT@20240321`, `币安人生USDT`
- the venue lists no instrument with that base (70): `1000SATSUSDT`, `BAKEUSDT`, `BANANAS31USDT`, `BANKUSDT`, `BCCUSDT`, `BCHABCUSDT`, `BCHSVUSDT`, `BLZUSDT`, `BNXUSDT`, `BONDUSDT`, `BROCCOLI714USDT`, `BURGERUSDT`, `CFXUSDT`, `COCOSUSDT`, `DARUSDT`, `DASHUSDT`, `DENTUSDT`, `DEXEUSDT`, `DOCKUSDT`, `EOSUSDT`, `ERDUSDT`, `FLMUSDT`, `FRONTUSDT`, `FTMUSDT`, `GXSUSDT`, `HIFIUSDT`, `HOOKUSDT`, `ICXUSDT`, `IDEXUSDT`, `IOTAUSDT`, `IOTXUSDT`, `KAVAUSDT`, `KLAYUSDT`, `LENDUSDT`, `LEVERUSDT`, `LINAUSDT`, `LOOMUSDT`, `LUNCUSDT`, `MATICUSDT`, `MBOXUSDT`, `NULSUSDT`, `OGUSDT`, `OMGUSDT`, `OMUSDT`, `ONEUSDT`, `ONTUSDT`, `ORDIUSDT`, `PERPUSDT`, `QTUMUSDT`, `REEFUSDT`, `RNDRUSDT`, `RVNUSDT`, `STMXUSDT`, `STORJUSDT`, `SUNUSDT`, `SXPUSDT`, `TFUELUSDT`, `THETAUSDT`, `TOMOUSDT`, `TONUSDT`, `TRUUSDT`, `TUTUSDT`, `UNFIUSDT`, `USTCUSDT`, `WAVESUSDT`, `WRXUSDT`, `XEMUSDT`, `XMRUSDT`, `YFIIUSDT`, `ZECUSDT`
- no recent Binance price (not live at the end of the panel), so the mapping cannot be corroborated (2): `BTTUSDT`, `LRCUSDT`
- the venue's price disagrees with Binance's — not the same asset or unit with certainty (1):
    - `LUNAUSDT`: price mismatch with LUNA-EUR: venue 3.89865e-05 vs Binance 0.0367 per panel unit (ratio 0.001062) — not the same asset or unit with certainty

Results (multiples are of starting equity; returns are time-weighted):

| start EUR | +EUR/mo | final x | paid in x | CAGR | vol | Sharpe | max DD | share of ideal return | TE /yr | fees bp/yr | spread bp/yr | financing bp/yr | turnover /yr | orders | skipped: minimum / lot→0 | max margin use |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 0 | 1.691 | 1.000 | 6.5% | 22.4% | 0.39 | -46.1% | 97% | 6.98% | 186.7 | 12.1 | 0.0 | 7.2 | 3,174 | 2,637 / 0 | 1.004 |
| 1,000 | 100 | 17.145 | 10.900 | 7.0% | 22.4% | 0.41 | -46.6% | 101% | 6.90% | 198.6 | 13.0 | 0.0 | 7.5 | 4,931 | 958 / 0 | 1.001 |
| 5,000 | 0 | 1.767 | 1.000 | 7.1% | 22.4% | 0.42 | -46.3% | 102% | 6.88% | 193.7 | 12.6 | 0.0 | 7.5 | 4,863 | 1,024 / 0 | 1.001 |
| 5,000 | 100 | 4.849 | 2.980 | 7.1% | 22.4% | 0.42 | -46.3% | 102% | 6.88% | 197.2 | 12.9 | 0.0 | 7.5 | 5,279 | 625 / 0 | 1.001 |
| 10,000 | 0 | 1.772 | 1.000 | 7.1% | 22.4% | 0.42 | -46.2% | 103% | 6.87% | 194.2 | 12.6 | 0.0 | 7.5 | 5,287 | 619 / 0 | 1.001 |
| 10,000 | 100 | 3.312 | 1.990 | 7.1% | 22.4% | 0.42 | -46.2% | 103% | 6.88% | 196.4 | 12.8 | 0.0 | 7.5 | 5,458 | 454 / 0 | 1.001 |

Per-print equity (multiple of starting equity) and net return of every account, beside the ideal's: `realism_paths/P.CRYPTO.LO_TREND__bitvavo.parquet`.
