# DATA_SOURCES — verified map of market-data sources for the factory

**Author:** Claude research sub-agent (model `claude-fable-5-2`), for the factory conductor.
**Access date of every item:** 2026-11-10. Probes and page reads ran 13:49–14:32 UTC from the NL laptop (the host the factory runs on).
**Status:** landscape reference. It is NOT a preregistration and changes nothing in `PREREGISTRATION_v1.md`.
**Scope:** data usable for systematic research AND for live signal generation, per asset class and
frequency — free first, then cheap paid — with access method, depth, granularity, point-in-time
quality, automated-use terms, limits and account/key needs.

## How to read this file

**Evidence labels (every row carries one).**

| label | meaning |
|---|---|
| **V-P** | VERIFIED by probe: the endpoint answered a scripted request from this host today and the response was inspected. |
| **V-D** | VERIFIED on the provider's own page today; I read the raw page text. |
| **V-D†** | Read on the provider's own page today **through the fetch tool's summariser**. Numbers are the provider's, but a small model transcribed them — re-read the page before paying money on the strength of one. |
| **CLAIM** | third-party page, search-result snippet, or analyst recall. Not checked against a primary source today. |
| **UNKNOWN** | could not be determined today. |
| **GIVEN** | verified from this host earlier today by the conductor (listed in the task brief); not re-verified here. |

**Constraints honoured.** No account was created, no login, no form submitted, no captcha or bot check
bypassed, no browser impersonation (default `curl` user agent; a generic client name without contact
details for Wikimedia and SEC; page reads marked † went through the fetch tool's own agent). At most a few requests per endpoint, with two declared exceptions:
20 small S3 bucket listings to map the Binance archive, and 8 short FRED CSV pulls (one per series).
Eight read-only GETs used the repo's existing Alpaca key (the key was never printed). Hyperliquid's
API is POST-only and was therefore read from its docs, not probed.

**Not retried (bot checks or refusals to a plain scripted GET).** By instruction: Dukascopy datafeed
HTTP, Stooq, Yahoo. Found today: `api.nasdaq.com` (HTTP/2 stream reset), the OECD API explainer page
(Cloudflare challenge), FMP docs (403), IBKR Campus docs (403), Birdeye pricing (403), Reddit help
centre (403), Deutsche Börse's public Xetra S3 bucket (`AccessDenied`).

Source keys in square brackets (`[F3]`, `[C12]`, …) resolve in the source list at the end.

---

## 0. Ten findings that change decisions

1. **OANDA's EU entity does not offer the v20 API (V-D).** OANDA's own developer page says a v20 account "is
   available to all divisions except OANDA Global Markets and OANDA TMS BROKERS S.A." The EU site
   (`oanda.com/eu-en`) is operated by OANDA TMS Brokers S.A. (Warsaw, MetaTrader 5). The planned FX
   bid/ask route is therefore probably unavailable to a Dutch owner. Replacements, all owner actions:
   IG demo API, cTrader Open API demo, Dukascopy JForex demo, Saxo SIM. [F5–F7, F12–F15]
2. **The ECB reference rate is a same-day print, but late (V-P + V-D).** Struck at the ~14:10 CET
   concertation, "usually updated at around 16:00 CET". The 2026-11-09 file carries
   `Last-Modified: 14:56:21 GMT` = 15:56 CET (today's file had not yet appeared at 15:32 CET, as
   expected). The ECB publishes it "for information purposes only"; transaction use is "strongly
   discouraged". FRED H.10 is released weekly with a lag (GIVEN), so a **live** FX-D signal cannot use
   the print the backtest uses; ECB (EUR crosses) is the nearest same-day official print. [F1, F2]
3. **Every central-bank daily FX feed tried answers a plain GET with no key (V-P):** ECB, Bank of
   Canada, Bank of England, SNB, RBA, Norges Bank, Riksbank, Bank of Japan, plus the ECB-mirror
   Frankfurter API. Their fixing times differ (see §3.1) — never mix them as if synchronous. [F2, F16–F23]
4. **No free roll-adjusted continuous futures source was verified.** Cheapest real routes (the $125,
   $99 and $270 figures are V-D): Databento's
   **$125 signup credit** (CME from 2010-06-06; continuous symbols are deliberately **not**
   back-adjusted; ICE from 2018-12-23 and Eurex from 2025-03-10 are separate, shorter datasets — dates
   CLAIM), Pinnacle CLC **$99 one-time** (98 markets, earliest 1969, back/ratio-adjusted, includes
   Bund/DAX/softs but not Brent), Norgate **$270/yr** (needs Windows). [U1–U8]
5. **Tiingo's free account is the single highest-value owner action (V-D†).** "30+ years" of
   split+dividend-adjusted US EOD on the $0 plan (500 symbols/month, 50 requests/hour, 1,000/day). It
   would extend the MA-ETF lane back before Alpaca's 2016 start. Alpha Vantage's free tier cannot do
   this: full-history output and the adjusted series are premium (V-D). [E2, E3]
6. **FRED is thinner than assumed for index history (V-P).** `SP500` returns only the last 10 years
   (first row 2016-11-07); the ICE BofA total-return indices return only the last 3 years (first row
   2023-11-10); the LBMA gold series ID returns 404. `NASDAQCOM` (1971-02-05→), `VIXCLS` (1990→) and
   `DGS10` (1962→) are intact. Ken French's daily US market return (1926-07-01→2026-09-30 in today's
   file) downloads with no key. [E14, E15]
7. **UCITS ETFs: one free no-account route, two years deep (V-P).** Euronext's CSV endpoint returned
   IWDA Amsterdam OHLC + volume + VWAP, but only 2024-11-11→ even when asked for 2009→. EODHD at
   €19.99/month is the cheapest verified route to 30+ years incl. LSE and XETRA (V-D), and its pricing
   page offers students 50% off for 12 months "for educational purposes". Trading 212's API has
   no price endpoint at all (V-D†); justETF's terms forbid "programs to carry out automated price
   inquiries" (V-D). [E7–E12]
8. **Options: the repo's free sources are healthier than the paid market suggests (V-P; prices V-D†).** DoltHub
   `post-no-preference/options` holds data through 2026-11-09. Deribit serves historical option
   trades (tested back to 2017-01) with no key. Alpaca option bars exist from 2024-01-18. Binance's option end-of-hour
   summary archive stopped on 2023-10-23. Tardis starts at $700/month. [O1–O9]
9. **Point-in-time macro is free without a key (V-P; release timing V-D).** `alfredgraph.csv?id=…&vintage_date=…` returned
   the 2020-01-30 vintage of real GDP. CFTC COT answers by Socrata API back to 1986-01-15 (TFF from
   2006-06-13), released Fridays 15:30 ET for Tuesday positions. FINRA daily short volume, SEC, BLS,
   Treasury, NY Fed, Eurostat, Wikimedia and GDELT all answered. [M1–M20]
10. **QuantConnect cannot be a data source for this repo (V-D).** Its terms now contain a "No Data
    Export" section: platform data "may be used only inside the Site's hosted environment", export
    "by any means, in any amount" is prohibited, explicitly including via AI agents, logs, charts or
    the API. It is usable only as an independent cloud cross-check. [F24–F26]

Corrections to the brief are collected in §5.

---

## 1. Master tables

Columns: **access** = exact method · **depth / grain** · **quality** = point-in-time, timestamp and
adjustment notes · **terms** = licence / automated use · **limits** · **key?** = account or API key
(account creation is an OWNER action) · **cost** · **ev** = evidence label and source key.

### 1.1 FX

| source | access | depth / grain | quality notes | terms | limits | key? | cost | ev |
|---|---|---|---|---|---|---|---|---|
| FRED H.10 | `fred.stlouisfed.org/graph/fredgraph.csv?id=DEX…` | daily, 1971/1999→ | noon-NY buying rate, one print, no bid/ask; **released weekly with a lag** | FRED terms; attribution | none hit | no | $0 | GIVEN |
| ECB euro reference rates | `ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml`, `…-hist.zip` (CSV), `…-hist-90d.xml`; SDMX `data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A` | daily, 1999→, ~30 currencies vs EUR | one print from the ~14:10 CET concertation; published ~16:00 CET same day (observed 15:56 CET); none on TARGET closing days; no bid/ask | "for information purposes only"; transaction use "strongly discouraged" | none hit | no | $0 | V-P, V-D [F1,F2] |
| Frankfurter (ECB mirror) | `api.frankfurter.dev/v1/latest?base=EUR&symbols=USD,JPY` | as ECB | third-party re-serve of the ECB file; adds nothing but JSON | open-source project; terms not read | UNKNOWN | no | $0 | V-P [F3] |
| Bank of Canada Valet | `bankofcanada.ca/valet/observations/FXUSDCAD/json?recent=3` (also `/csv?start_date=…`) | daily, **2017-01-03→** | "Daily **average** exchange rate" — not a tradeable print | BoC terms URL in payload | none hit | no | $0 | V-P [F16] |
| Bank of England IADB | `bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=…&Dateto=now&SeriesCodes=XUDLUSS&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N` | daily spot; start date not checked | fixing time not read today (CLAIM: ~16:00 London mid) | not read | none hit | no | $0 | V-P [F17] |
| SNB data portal | `data.snb.ch/api/cube/devkum/data/csv/en` | **monthly** averages verified; daily cube UNKNOWN | CHF per 1 or 100 units | not read | none hit | no | $0 | V-P [F18] |
| RBA F11.1 | `rba.gov.au/statistics/tables/csv/f11.1-data.csv` | daily; current file **2023-01-03→** (older years are separate files) | A$1 = X; fixing time not read (CLAIM: 16:00 Sydney) | not read | none hit | no | $0 | V-P [F19] |
| Norges Bank | `data.norges-bank.no/api/data/EXR/B.USD.NOK.SP?format=csv&lastNObservations=3` | daily | metadata label: "ECB concertation time 14:15 CET" | not read | none hit | no | $0 | V-P [F20] |
| Riksbank SWEA | `api.riksbank.se/swea/v1/Observations/Latest/SEKUSDPMI` | daily | mid fix | not read | UNKNOWN | no | $0 | V-P [F21] |
| Bank of Japan API | `stat-search.boj.or.jp/api/v1/getDataCode?format=json&lang=en&db=FM08&code=FXERD01&startDate=YYYYMM&endDate=YYYYMM` | daily | "US.Dollar/Yen Spot Rate at 9:00 in JST, Tokyo Market" | not read | none hit | no | $0 | V-P [F22] |
| Kraken spot fiat pairs | public REST `OHLC` (last 720 bars), `Trades` pagination | 14 fiat FX pairs, tick→ | real trades 24/7, thin; exchange price, not interbank | Kraken API terms | public limits | no | $0 | GIVEN |
| Binance spot `EURUSDT` etc. | `api.binance.com/api/v3/klines?symbol=EURUSDT&interval=1d` + archive | 1m→ | USDT-quoted proxy (stablecoin basis); 24/7 | Binance terms | public limits | no | $0 | V-P [C2] |
| FXCM candle **sample** | `candledata.fxcorporate.com/{m1,H1,D1}/{PAIR}/{year}[/{week}].csv.gz` | **2017–2020 only**; 21 pairs; m1/H1/D1 | **bid and ask OHLC**; UTC; D1 bars stamped 22:00 UTC; "indicative … lowest spreads … Active Trader" | "for personal use and abides by our EULA" | none hit | no | $0 | V-P, V-D [F8,F9] |
| OANDA v20 practice | `api-fxpractice.oanda.com/v3/accounts/{id}/instruments/{inst}/candles?price=BA&granularity=…` | "back to 2005"; S5…M (21 granularities) | bid/ask/mid candles; candle time = bar start; daily alignment 17:00 America/New_York by default; count max 5,000 | account terms | 120 req/s per IP; 20 streams | **yes — and not offered by the EU entity** | $0 | V-D [F5,F6,F7] |
| Dukascopy JForex (demo) | JForex platform Historical Data Manager, or JForex API `IHistory.getBars/getTicks` (`OfferSide.BID/ASK`) | tick→monthly; depth not stated on the pages read | bid and ask; demo history "must be equal to LIVE" | website terms: "non-commercial use"; no "scraper/robot/bot"; "may not be used to construct a database". **No clause found that grants or forbids bulk export through JForex → UNKNOWN; ask support in writing** | UNKNOWN | yes (demo; 14 days = CLAIM) | $0 | V-D, V-D† [F10,F11] |
| TrueFX | historical downloads page | tick, top-of-book, ms; pairs/years not visible without login | Integral OCX liquidity | terms page not located | UNKNOWN | yes ("log in or register for free access") | $0 | V-D† [F27] |
| HistData.com | web pages, one file per pair-month; or SFTP | M1 (all formats) + tick (ASCII, NinjaTrader); 66 pairs; start year not read | **EST without DST**; bars are **bid**; ask only in ASCII tick; "no warranty" | no automation or redistribution clause found | SFTP: 1 IP, 3 sessions | web: no; SFTP: PayPal | web $0; **SFTP $27 for 15 days**; updates $7/mo | V-D (SFTP price and term), V-D† (rest) [F28,F29] |
| IG REST API (demo) | REST price-history endpoints with a demo API key | "up to 20 years" | bid/ask candles (CLAIM) | free "as long as you are using the default API quotas" | **10,000 historical points/week**; 30–60 non-trading req/min | yes (demo) | $0 | V-D [F12] |
| cTrader Open API (demo) | Open API through a cTrader broker's demo account (transport not read) | trendbars and ticks (CLAIM) | broker-specific quotes | not read | 50 req/s; **5 historical req/s** per connection | yes (cTrader ID + broker demo) | $0 | V-D† [F13] |
| Saxo OpenAPI (SIM) | REST, 24-hour token | UNKNOWN | UNKNOWN | not read | 120 req/min per session per service group | yes (developer SIM = CLAIM) | $0 | V-D† [F14] |
| IBKR TWS API | `reqHistoricalData` with `MIDPOINT`/`BID`/`ASK`/`BID_ASK` | bars ≤30 s only 6 months back; longer bars deeper | bar time zone = TWS login zone; daily bar dated on the close day | account agreement | 60 requests/10 min; `BID_ASK` counts double; identical request within 15 s is a violation | yes (account; FX data free of subscription = CLAIM) | $0 data | V-D (pacing), V-D† (bar conventions) [F30,F31] |
| QuantConnect FX | cloud only | 72 pairs, Jan 2007→ (varies), tick→daily; free tier = minute/hour/daily | QuoteBars built from OANDA ticks; UTC; no sizes | **no export, by any means** | free: 1 backtest node | yes | $0 cloud | V-D† [F24–F26] |
| Tiingo FX | `api.tiingo.com/tiingo/fx/<pair>/prices?resampleFreq=5min`; `/top` | 140+ pairs; depth not stated | history is OHLC **without** bid/ask; `/top` has bid/ask; "beta" | "Internal Use Only" | free: 50 req/h, 1,000/day | yes (token) | $0 / $30 | V-D† [E2,F32] |
| Twelve Data | REST | UNKNOWN | — | "internal non-display" | Basic: 8 credits/min, 800/day | yes | $0; paid prices on the page are internally inconsistent | V-D† [F33] |
| Alpha Vantage FX | `function=FX_DAILY`; `FX_INTRADAY` is premium | daily; compact = 100 points | OHLC, no bid/ask | personal use; commercial via sales | **25 requests/day** | yes | $0 / $49.99+ | V-D [E3,E4] |
| Massive (ex-Polygon) Currencies | REST + flat files | Basic: 2 years; Starter: 10+ years | Starter adds **quotes (BBO)**, second bars, flat files | individual plans | Basic 5 calls/min; Starter unlimited | yes | $0 / **$49/mo** | V-D, V-P [F34,F35] |
| FirstRate Data FX bundle | one-time purchase, file download | 74 pairs, 1-min→1-day, Jan 2009/2010→ | bid/ask not stated | not read | — | purchase | price not in page; updates $59.95/mo | V-D [F36] |
| Alpaca FX | `data.alpaca.markets/v1beta1/forex/latest/rates` | — | — | — | — | repo key lacks the grant: 403 "insufficient grants" | — | V-P [O3] |
| Finnhub | REST | UNKNOWN | — | — | 60 calls/min (CLAIM); candles reported premium (CLAIM) | yes | UNKNOWN | CLAIM |
| EODHD FX | REST | UNKNOWN for FX | — | "Personal use" plans | free 20 calls/day | yes | €19.99+ | V-D† [E5] |

### 1.2 Futures (continuous, roll-adjusted)

| source | access | depth / grain | quality notes | terms | limits | key? | cost | ev |
|---|---|---|---|---|---|---|---|---|
| Databento `GLBX.MDP3` (CME, CBOT, NYMEX, COMEX) | Python/HTTP API, batch download | **2010-06-06→**; OHLCV-1s/1m/1h/1d, trades, MBP, MBO, definitions, statistics | continuous symbols `ROOT.{c,n,v}.RANK` (calendar / open-interest / volume roll); "We don't create a synthetic time series by back-adjusting" → **you back-adjust**; parent `ES.FUT` returns every outright **and spread** | "Historical data: No license required"; live needs a plan | billed per byte of uncompressed binary | yes | **$125 credit** (expires 6 months after signup, one per team); then pay-as-you-go; Standard $199/mo for live | V-D, V-D† [U1–U5] |
| Databento ICE / Eurex / CFE | same API; `IFEU.IMPACT`, `IFUS.IMPACT`, `IFLL.IMPACT`, `NDEX.IMPACT`, `XEUR.EOBI`, `XCBF.PITCH` | ICE Futures Europe and ICE Europe Financials: 2018-12-23→; Eurex: **2025-03-10→** (both CLAIM — search snippets of Databento's own launch posts; confirm with `metadata.get_dataset_range`) | **cannot give 15 years of ICE or Eurex history** | as above | as above | yes | as above | V-D† (existence), CLAIM (dates) [U8] |
| Pinnacle Data CLC | one-time purchase, files + DataMaker software | 98 markets; earliest 1969 (grains); day and 24h sessions. **Listed:** Euro Bund (1989), Bobl, Schatz, DAX (1997), Euro Stoxx 50 (2002), FTSE 100, CAC 40, Nikkei, Hang Seng, 10-yr T-notes, Eurodollars, crude oil (1984), natural gas, gold, copper, sugar, coffee, cocoa, cotton, currencies. **Not listed:** Brent, Gasoil, VIX | "Reverse (back) adjusted, non-adjusted, and ratio adjusted"; O/H/L/settle, OI, volume | not read | — | purchase | **$99.00**; updates $20/mo (3-month minimum) or $18/mo (1-year) | V-D (prices), V-D† (market list) [U6] |
| Norgate Data futures | Norgate Data Updater + Python package | ~100 markets, 11 exchange groups, "to around 1980" | spot-month continuous, unadjusted and back-adjusted (arithmetic); close = official settlement | subscription licence; processing on a second machine allowed for personal use | — | subscription | **$148.50 / 6 months, $270 / 12 months** | V-D [U7] |
| ↳ platform | — | — | NDU is a Windows application (.NET Framework 4.8; the FAQ's example is "a Windows VM running on an Apple Mac") → **not native on this Linux host** | — | — | — | — | V-D [U7] |
| FirstRate Data "Futures – Most Active" | one-time purchase, file download | 130 futures, Jan 2007→Nov 2026, 1-min/5-min/30-min/1-hour/1-day | continuous in three forms (unadjusted, absolute-adjusted, ratio-adjusted) **and** individual contracts | not read | — | purchase | bundle price not in the static page (UNKNOWN); "Updates are $59.95 per month" after the first month | V-D [U9] |
| CSI (Unfair Advantage) | proprietary software | "most world markets back to the first day of trading" | back-adjustment features not shown on the page read | not read | — | subscription | UA "starting at $25/mo"; data price depends on history | V-D† [U11] |
| Barchart | site downloads / OnDemand API | Premier: daily to 1980, intraday ~10 years (CLAIM) | — | — | free members 1 download/day and 2 years (CLAIM); Premier 250 or 1,000/day (sources conflict) | yes | UNKNOWN | CLAIM [U12] |
| Nasdaq Data Link | REST | free sets are central-bank/government data incl. CFTC COT; `WIKI` prices stale since 2018; `CHRIS` continuous futures status UNKNOWN | — | — | — | yes | — | CLAIM [U13] |
| QuantConnect US Futures (AlgoSeek) | cloud only | May 2009→; 157 contracts; CME, CBOT, NYMEX, COMEX, CFE, ICE (only Sugar) | continuous via `DataNormalizationMode` (e.g. `BACKWARDS_RATIO`) and `DataMappingMode` | **no export** | free tier: 1 node, minute+ | yes | $0 cloud | V-D† [U10,F24] |
| IBKR TWS API | `reqHistoricalData` | expired futures only **two years** past expiry; expired options/FOPs never | fine for live, useless for a 15-year backtest | account | pacing as in §1.1 | account + "Level 1 streaming real time data" for the instrument | subscription (e.g. US Securities Snapshot and Futures Value Bundle USD 10.00/mo, waived at USD 30 commissions) | V-D [F30,F31,E20] |
| CME DataMine | self-service portal | EOD back to 1982-01-01 (CLAIM) | exchange-grade | exchange licence | — | yes | priced per data type and duration; no public per-year price found | CLAIM [U14] |
| Yahoo `=F` | unofficial endpoints only | front-month series, **not roll-adjusted** (CLAIM) | roll rule undocumented; gaps on roll days (CLAIM) | plain GET returns 429 from this host (GIVEN) | — | — | — | off-limits |
| FRED / EIA spot commodities | `fredgraph.csv?id=DCOILWTICO` | daily spot | **spot prices are not investable returns** (no roll yield, no financing); FRED copy lags: on 2026-11-10 the last row was 2026-11-03 | FRED terms | — | FRED no; EIA API yes (`API_KEY_MISSING` without one) | $0 | V-P [E14,M23] |
| ETF proxies via Alpaca | Alpaca bars (`GLD SLV USO UNG DBC DBA TLT …`) | 2016-01→ | investable, total-return adjusted; embeds fund roll policy and fees | Alpaca terms | 200 calls/min | repo key | $0 | GIVEN |
| Crypto-venue TradFi perps | `fapi.binance.com/fapi/v1/klines?symbol=XAUUSDT` | first candle **2025-12-11** | 24/7 perp with funding; short history | Binance terms | public limits | no | $0 | V-P [C2] |

### 1.3 US / EU equities and ETFs (daily, incl. UCITS)

| source | access | depth / grain | quality notes | terms | limits | key? | cost | ev |
|---|---|---|---|---|---|---|---|---|
| Alpaca (SIP) | `data.alpaca.markets/v2/stocks/bars`, `adjustment=all`; corporate actions `/v1/corporate-actions` | 2016-01→; minute and daily | adjusted for splits and dividends on request; **daily bar timestamp = midnight ET of the session (04:00Z in summer, 05:00Z in winter)**, i.e. a date label, not the close time; free plan cannot query the latest 15 minutes | docs carry no redistribution clause in the page read | 200 calls/min (Basic); 10,000/min at $99/mo | repo key | $0 | GIVEN, V-P, V-D† [E1,O3] |
| Tiingo EOD | `api.tiingo.com/tiingo/daily/<ticker>/prices?startDate=…` | "30+ Years"; US equities, ETFs, mutual funds | raw + `adjClose/adjOpen/…`, `divCash`, `splitFactor`; "CRSP standard … both split and dividend adjustments"; EOD at 5:30 PM ET, corrections until 8 PM | "Internal Use Only" | free: **500 symbols/month, 50 req/hour, 1,000/day, 1 GB/month** | yes (token) | $0; Power $30/mo; commercial $50/mo | V-D† [E2,E6] |
| Alpha Vantage | `function=TIME_SERIES_DAILY` | 25+ years, "global equity" (LSE `.LON` sample shown) | free = raw OHLCV, **latest 100 points only**: "The "full" outputsize is available to premium keys"; `TIME_SERIES_DAILY_ADJUSTED` is premium; has a listing/delisting utility | personal; commercial via sales | **25 requests/day** | yes | $0; $49.99/mo (75 req/min) | V-D [E3,E4] |
| EODHD | REST `eod/{SYMBOL}.{EXCHANGE}` | 30+ years; "150,000+ tickers"; LSE and XETRA codes confirmed, Euronext Amsterdam code not confirmed today; intraday US 1-min from 2004 | OHLC raw; `adjusted_close` = "Closing price adjusted for both splits and dividends"; `delisted=1` lists dead tickers; each exchange updated "2-3 hours after the market closes"; samples: BP.LSE from 1988-07-01, SAP.XETRA from 1994-09-13 | "Personal use" plans | free: **20 calls/day, 1 year**; paid 100,000/day | yes | **€19.99/mo** EOD All-World; €29.99 with intraday; "Students get a 50% discount for 12 months on all subscriptions for educational purposes" | V-D, V-D† [E5,E9,E22] |
| Massive (ex-Polygon) Stocks | REST + flat files | Basic 2 years; Starter 5; Developer 10; Advanced 20+ | US only | individual, non-pro | Basic 5 calls/min | yes | $0 / $29 / $79 / $199 | V-D† [E13] |
| Marketstack | REST | free 1 year; Basic 10 years; Professional 15+ | EOD | free = non-commercial | free **100 requests/month** | yes | $0 / $9.99 / $49.99 | V-D† [E16] |
| Twelve Data | REST | UNKNOWN | global EOD only on paid tiers (Grow) | — | 8 credits/min, 800/day | yes | $0 / $79 (see caveat §1.1) | V-D† [F33] |
| FMP | REST | UNKNOWN | — | — | UNKNOWN | yes | UNKNOWN (page refused the fetch) | UNKNOWN |
| **Euronext Live CSV** | `live.euronext.com/en/ajax/AwlHistoricalPrice/getFullDownloadAjax/{ISIN}-{MIC}?format=csv&decimal_separator=.&date_form=d/m/Y&adjusted=Y&startdate=…&enddate=…` | **last ~2 years only** (asked 2009→, got 2024-11-11→, 509 rows) | Open, High, Low, Last, Close, shares, trades, turnover, VWAP; IWDA `IE00B4L5Y983-XAMS` tested | terms page not located; `robots.txt` has no rule against `/en/ajax/` for generic agents | UNKNOWN — keep it to a daily pull | no | $0 | V-P [E7,E8] |
| Nasdaq.com | `api.nasdaq.com/api/quote/…/historical` | — | — | — | plain GET → HTTP/2 stream reset | — | — | V-P (refused) [E17] |
| Deutsche Börse public Xetra dataset | S3 `deutsche-boerse-xetra-pds` | — | — | — | `AccessDenied` | — | — | V-P (closed) [E18] |
| LSE | — | no free scripted history found | — | — | — | — | — | UNKNOWN |
| iShares product pages | `…ajax?fileType=csv` | — | returned an HTML page, not CSV, to a plain GET | — | — | — | — | V-P (no clean route) [E19] |
| justETF | website | — | — | user must refrain from "using programs to carry out automated price inquiries" | — | — | — | V-D [E11] |
| extraETF | website | — | — | terms not read | — | — | — | UNKNOWN |
| Trading 212 Public API | `live.trading212.com/api/v0`, `demo.trading212.com/api/v0` | **no price history, quotes or candles** — only account, positions, orders, instrument metadata, history of own orders/dividends/transactions | beta; Invest and Stocks ISA only | API terms PDF not read | e.g. instruments 1 req/50 s | yes | $0 | V-D† [E10] |
| IBKR | TWS API | deep daily; `TRADES` split-adjusted only, `ADJUSTED_LAST` split+dividend | **drops "securities which are no longer trading" → survivorship bias**; needs Level 1 subscription per exchange | account | pacing | account + subscriptions | page lists 15-minute delayed data for Euronext, Xetra and LSE; per-exchange subscription prices not in the static page | V-D†, V-D [F30,F31,E20] |
| Google Sheets `GOOGLEFINANCE` | manual, in a sheet | daily/weekly OHLCV | "may be delayed up to 20 minutes" | "Historical data cannot be downloaded or accessed via the Sheets API or Apps Script"; "not for trading purposes" | — | Google account | $0 | V-D† [E12] |
| Ken French Data Library | `mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip` | US market excess return + RF (and SMB, HML), daily, **1926-07-01→2026-09-30** in today's file ("created by using the 202609 CRSP database") | total-return research series, not an instrument; **published about a month or more in arrears** | academic use; terms not read | — | no | $0 | V-P [E15] |
| FRED index series | `fredgraph.csv?id=…` | `NASDAQCOM` 1971-02-05→; `VIXCLS` 1990-01-02→; `DGS10` 1962-01-02→; **`SP500` last 10 years only; ICE BofA TR indices last 3 years only** | price indices exclude dividends | third-party series: "your own personal use" unless the owner permits | none hit | no | $0 | V-P [E14,M3] |
| Stooq / Yahoo | — | — | — | bot checks (GIVEN) | — | — | — | off-limits |

### 1.4 Options

| source | access | depth / grain | quality notes | terms | limits | key? | cost | ev |
|---|---|---|---|---|---|---|---|---|
| DoltHub `post-no-preference/options` | `dolt clone`, or SQL over `dolthub.com/api/v1alpha1/post-no-preference/options/master?q=…` | latest `option_chain.date` = **2026-11-09**; start date not re-checked (heavy queries time out at 40 s — use the local clone) | EOD chains, bid/ask, IV and greeks as published by the maintainer; single unaudited maintainer | licence not read today | API is slow for scans | no | $0 | V-P [O1] |
| Alpaca options | `/v1beta1/options/bars`, `/snapshots/{underlying}?feed=indicative` | docs: "since February 2024"; a daily bar dated 2024-01-18 was returned | free = **indicative** feed ("not actual OPRA quotes", trades delayed 15 min); OPRA only for subscribers | Alpaca terms | 200 calls/min | repo key | $0; OPRA at $99/mo | V-P, V-D [O2,O3] |
| ThetaData | vendor API (access mechanics not read) | Free: **EOD, from 2023-06-01**, 1-day delay; Value 1-min from 2020-01-01; Standard tick from 2016-01-01; Pro tick from 2012-06-01 | "every OPRA NBBO quote" on Standard and Pro | not read | free 20–30 req/min (page contradicts itself) | yes | **$0 / $40 / $80 / $160 per month** | V-D ($40, $80), V-D† (rest) [O7] |
| Massive (ex-Polygon) Options | REST + flat files | Basic 2 years EOD; Starter 2; Developer 4; Advanced 5+ | greeks/IV/OI from Starter; quotes only on Advanced | "Non-pros only" | Basic 5 calls/min | yes | $0 / $29 / $79 / $199 | V-D† [O8] |
| Cboe DataShop Option EOD Summary | web shop | January 2012→ | NBBO snapshots at 15:45 ET and close, OHLC, volume, VWAP, OI; optional IV + greeks | exchange licence | — | yes | priced in cart (not shown) | V-D† [O9] |
| Deribit | `www.deribit.com/api/v2/public/…`; history host `history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time` | **option trades from 2017-01** returned (with `iv`, `index_price`) | trade prints, not quotes; expired instruments reachable on the history host; ms UTC | public API terms | public limits | no | $0 | V-P (history), GIVEN (live) [O4] |
| Tardis.dev | HTTP API, CSV datasets | Deribit, OKX, Binance, Bybit options chains, tick level | "Historical CSV datasets for the first day of each month are available to download without a Data API key" | — | — | no for monthly samples; else key | Solo **$700/mo** (Options or Perpetuals plan), $1,200 all exchanges; Academic $350–650; minimum order $300 | V-D, V-D† [O6] |
| Alpha Vantage `HISTORICAL_OPTIONS` | REST | 2008-01-01→ | chain per day | premium function | 75+ req/min | yes | $49.99/mo+ | V-D [E3,E4] |
| Binance option archive | `data.binance.vision/data/option/daily/` | `EOHSummary` BTCUSDT 2023-05-18→**2023-10-23 (stopped)**; `BVOLIndex` 2023-06-20→2026-11-09 | — | — | — | no | $0 | V-P [C1] |
| Databento `OPRA.PILLAR` | API | UNKNOWN start | docs example unit prices: `ohlcv-1d` $600/GB, `trades` $280/GB, `cbbo-1m` $2/GB | no licence for historical | per byte | yes | credit, then usage | V-D [O11] |
| OptionMetrics IvyDB | WRDS / institutional | January 1996→ | the academic standard | institutional licence | — | university account | no individual price published | CLAIM [O10] |

### 1.5 Crypto

| source | access | depth / grain | quality notes | terms | limits | key? | cost | ev |
|---|---|---|---|---|---|---|---|---|
| Binance public archive | `data.binance.vision/data/{spot,futures/um,futures/cm,option}/{daily,monthly}/…` (S3 listing `s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=…`) | see coverage map below | "new daily data becoming available the next day and new monthly data at the first monday of the month"; **spot timestamps are in microseconds from 2025-01-01** | Binance terms | none hit | no | $0 | V-P, V-D [C1,C3] |
| Binance REST | `api.binance.com/api/v3/klines`, `fapi.binance.com/fapi/v1/klines`, `…/futures/data/openInterestHist` | USD-M BTCUSDT: a candle for **2019-09-08** is returned (open 10000, the listing print) | open-time stamped | Binance terms | weight limits | no | $0 | V-P [C2] |
| Bybit | `public.bybit.com/{trading,spot,premium_index,spot_index,kline_for_metatrader4}/`; REST `api.bybit.com/v5/market/{kline,funding/history}` | `trading/BTCUSDT/` tick files from **2020-03-25** | daily `csv.gz` trade ticks | Bybit terms | — | no | $0 | V-P [C4] |
| OKX | REST `okx.com/api/v5/market/history-candles`; CDN `static.okx.com/cdn/okex/traderecords/trades/daily/YYYYMMDD/{inst}-trades-YYYY-MM-DD.zip` | swap daily candles back to at least 2019-12-30; daily trade zips | — | OKX terms | REST limits | no | $0 | V-P [C5] |
| Kraken spot | REST (GIVEN) + **OHLCVT archive** on `assets.kraken.com` | full archive "from the first trade on Kraken through 30 June 2026" in five ~2 GB parts; quarterly increments to 2026Q3; 1/5/15/(30)/60/240/720/1440-minute | **"empty intervals are not filled"** — no trade, no row; login not mentioned | Kraken terms | — | no | $0 | V-D† [C6] |
| Kraken Futures | `futures.kraken.com/api/charts/v1/trade/PF_XBTUSD/1d?from=&to=`; `…/derivatives/api/v4/historicalfundingrates?symbol=PF_XBTUSD` | `PF_XBTUSD` candles from 2022-03-23; **funding endpoint returned only 2025-10-30→ (9,021 hourly rows, ~376 days)** | hourly funding | Kraken terms | — | no | $0 | V-P [C7] |
| Coinbase Exchange | `api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400&start=&end=` | BTC-USD rows for 2015-07-20 returned (true start not probed) | **column order is `[time, low, high, open, close, volume]`** | Coinbase terms | 300 candles/request (CLAIM) | no | $0 | V-P [C8] |
| Bitstamp / Bitfinex | `bitstamp.net/api/v2/ohlc/btcusd/?step=&limit=&start=`; `api-pub.bitfinex.com/v2/candles/trade:1D:tBTCUSD/hist` | Bitstamp BTC/USD 2012-01-01 returned; Bitfinex 2013-03-31→ | longest clean BTC/USD histories | exchange terms | — | no | $0 | V-P [C9] |
| Hyperliquid | POST `api.hyperliquid.xyz/info` (`candleSnapshot`, funding history); S3 `hyperliquid-archive`, `hl-mainnet-node-data` | API: "Only the most recent 5000 candles are available"; time-range calls return 500 elements per page | S3: L2 snapshots + asset contexts "approximately once a month", "no guarantee of timely updates and data may be missing"; "No other historical data sets are provided via S3 (e.g. candles or spot asset data)" | — | — | API no; S3 needs an AWS account — "the requester of the data must pay for transfer costs" | API $0; S3 = transfer fees | V-D [C10] |
| ↳ third-party mirrors | Tardis lists Hyperliquid in its Perpetuals plan | — | free mirrors: none verified | — | — | — | $700/mo | V-D† [O6]; mirrors UNKNOWN |
| dYdX v4 indexer | `indexer.dydx.trade/v4/candles/perpetualMarkets/BTC-USD?resolution=1DAY`, `/v4/historicalFunding/BTC-USD` | history depth not probed | hourly funding; candles carry starting OI and orderbook mid | — | — | no | $0 | V-P [C11] |
| Alpaca crypto | `data.alpaca.markets/v1beta3/crypto/us/bars` | BTC/USD from **2021-01-01** | works without authentication | Alpaca terms | — | no | $0 | V-P [O3] |
| DefiLlama | `api.llama.fi`, `stablecoins.llama.fi`, `yields.llama.fi`, `coins.llama.fi` | stablecoin supply 2017-11→; pool yield history 2022-05→ (one pool tested) | free: chains/TVL, stablecoins, per-pool yield charts, fees, DEX overview, **open-interest** overview. **Paid (HTTP 402): derivatives-volume overview, perps funding yields** | terms not read | none hit | no | $0; paid tier price not read | V-P [C12] |
| CoinGecko | `api.coingecko.com/api/v3/…` | Demo: 1 year; Analyst: daily from 2013, hourly from 2018 | keyless calls work but share an IP-based limit | Demo: "Attribution required" | Demo 10k calls/month, 100/min | keyless or demo key | $0 / $35 / $129 | V-P, V-D† [C13] |
| GeckoTerminal | `api.geckoterminal.com/api/v2/networks/{net}/pools/{pool}/ohlcv/day` | pool OHLCV: 6 months on Demo/Basic, "from 2021" on Analyst+ | DEX pools | CoinGecko terms | UNKNOWN | no | $0 | V-P, V-D† [C20,C13] |
| DexScreener | `api.dexscreener.com/latest/dex/search?q=…` | snapshot only — no historical OHLCV endpoint documented | — | terms not read | 60 req/min on profile/boost endpoints; pair/search limit not captured | no | $0 | V-P, V-D† [C19] |
| CoinMarketCap | REST | Basic: daily quotes 1 year; Startup: all time (2010→) | — | — | Basic 15,000 credits/month, 50 req/min | yes | $0 / $29 / $79 | V-D† [C14] |
| CoinDesk Data (ex-CryptoCompare) | `min-api.cryptocompare.com` | — | — | — | **401 "API key required"** without a key | yes | pricing page unreadable today | V-P [C24] |
| CryptoDataDownload | CSV downloads | daily/hourly/minute OHLCV, many exchanges | re-hosted exchange data | **CC BY-NC-SA 4.0** | — | "some granularities may require a free account" | $0; Plus+ $39/mo | V-D† [C16] |
| CoinGlass | REST | 1-day interval all-time on every plan | aggregated OI, funding, liquidations | Hobbyist and Startup = personal | Hobbyist 30 req/min | yes | **$29 / $79 / $299 / $699**; no free API tier listed | V-D† [C15] |
| Velo | REST, CSV rows | monthly billing = 3 months of history; yearly = full | futures/options/spot | not read | not read | yes | **$199/mo** | V-D† [C17] |
| Laevitas | — | — | — | — | — | — | — | UNKNOWN |
| Tardis.dev | see §1.4 | tick-level, 50+ venues | best-in-class reconstruction | — | — | key | $700+/mo | V-D† [O6] |
| CoinAPI | REST, WebSocket | — | — | — | Startup 1,000 REST credits/day | yes | $25 free credits; $79 / $249 / $599 | V-D† [C23] |
| Kaiko / Amberdata | enterprise | — | — | — | — | contract | quote-based; no public price found | CLAIM [C26] |
| The Graph | subgraph queries | — | — | — | 100,000 free queries/month, then $2 per 100,000 | yes | $0+ | V-D† [C18] |
| Dune | SQL + API | — | — | — | plan numbers not readable today | yes | UNKNOWN | UNKNOWN |
| Flipside | — | Studio, dashboards, API and SDK "sunset … July 1, 2025"; only Snowflake shares remain | — | — | — | — | — | CLAIM [C25] |
| Birdeye | REST | — | — | — | pricing page refused the fetch | yes | UNKNOWN | UNKNOWN |
| Helius | RPC + enhanced APIs | archival on every plan | repo has a key; quota exhausted before | — | Free 1M credits/month, 10 RPS | repo key | $0 / $49 / $499 / $999 | V-D† [C21] |
| Bitquery | GraphQL | **historical data is an add-on "from $70/mo per chain"** | repo has a key | Personal = personal use | trial 1,000 points; Personal 100k points, 30 req/min | repo key | $29 / $69 / $199 (annual billing) | V-D† [C22] |

**Binance archive coverage map (V-P, S3 listings today).**

| path | earliest file found | latest checked | note |
|---|---|---|---|
| `spot/{daily,monthly}/{klines,trades,aggTrades}` | BTCUSDT 1d: **2017-08** | — | microsecond timestamps from 2025-01-01 |
| `futures/um/monthly/klines` | BTCUSDT 1d: **2020-01** | — | the archive starts later than the REST API (2019-09-08) |
| `futures/um/monthly/fundingRate` | BTCUSDT: 2020-01 | — | monthly folder only |
| `futures/um/daily/metrics` | BTCUSDT: **2020-09-01** | 2026-11-09 | OI and long/short ratios; daily folder only |
| `futures/um/daily/bookDepth` | BTCUSDT: **2023-01-01** | — | daily folder only |
| `futures/um/…/{aggTrades,trades,bookTicker,indexPriceKlines,markPriceKlines,premiumIndexKlines}` | present | — | start dates not probed |
| `futures/cm/monthly/klines` | BTCUSD_PERP 1d: 2020-08 | — | COIN-M also has `liquidationSnapshot` |
| `option/daily/EOHSummary` | BTCUSDT: 2023-05-18 | **2023-10-23 (ends)** | dead series |
| `option/daily/BVOLIndex` | BTCBVOLUSDT: 2023-06-20 | 2026-11-09 | implied-vol index |

### 1.6 Macro, positioning, text and alternative data

| source | access | depth / grain | quality notes | terms | limits | key? | cost | ev |
|---|---|---|---|---|---|---|---|---|
| FRED graph CSV | `fredgraph.csv?id=<ID>` | per series | **latest revised values, not point-in-time** | FRED terms | none hit | no | $0 | GIVEN |
| **ALFRED vintage CSV** | `alfred.stlouisfed.org/graph/alfredgraph.csv?id=GDPC1&vintage_date=2020-01-30&cosd=…&coed=…` | per-series vintage history | returns the series **as it stood on the vintage date** (column `GDPC1_20200130`) → point-in-time macro | FRED terms | none hit | **no** | $0 | V-P [M1] |
| FRED / ALFRED API | `api.stlouisfed.org/fred/series/observations` with `realtime_start/end`, `vintage_dates`, `output_type` 1–4 (4 = "Initial Release Only"), up to 100,000 rows | all vintages in one call | the scalable PIT route; also release dates | key must be used; attribution line; third-party series "personal use" unless cleared | bandwidth "at the Bank's discretion" | **yes (free key)** — without it: 400 | $0 | V-P, V-D† [M2,M3] |
| ECB data API, BIS | SDMX REST | — | — | — | — | no | $0 | GIVEN |
| OECD SDMX | `sdmx.oecd.org/public/rest/data/…` | — | host reachable; my test key returned `NoRecordsFound`; limits page blocked by a bot check | not read | UNKNOWN | no | $0 | UNKNOWN [M13] |
| Eurostat | `ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/<dataset>?format=JSON&…` | per dataset | latest values only | not read | none hit | no | $0 | V-P [M11] |
| BLS public API v1 | `api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0` | recent years per call | latest values; CPI Oct 2026 returned | not read | v1 limits not read | no | $0 | V-P [M8] |
| US Treasury par yield curve | `home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv` | daily, one year per call | through 2026-11-09 on 2026-11-10; slow (20 s) | public domain (CLAIM) | — | no | $0 | V-P [M9] |
| NY Fed reference rates | `markets.newyorkfed.org/api/rates/secured/sofr/last/2.json` | daily | SOFR with percentiles and volume | not read | — | no | $0 | V-P [M10] |
| World Bank | `api.worldbank.org/v2/country/NL/indicator/…?format=json` | annual | — | — | — | no | $0 | V-P [M12] |
| EIA | `api.eia.gov/v2/…` | — | — | — | — | **yes (free key)**: `API_KEY_MISSING` | $0 | V-P [M23] |
| CFTC Commitments of Traders | Socrata `publicreporting.cftc.gov/resource/6dca-aqww.json` (legacy futures-only), `gpe5-46if.json` (TFF futures-only), SoQL `$select/$order/$limit` | legacy **1986-01-15→**; TFF **2006-06-13→**; latest report date 2026-11-03 | weekly; positions as of **Tuesday**, "released every Friday at 3:30 p.m. Eastern time" → use from the following session only | US government data | Socrata anonymous throttling | no | $0 | V-P, V-D [M4,M5] |
| FINRA daily short-sale volume | `cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt` | daily; depth not probed | off-exchange short **volume**, not short interest; file for 2026-11-09 present next day | not read | — | no | $0 | V-P [M6] |
| SEC EDGAR | `data.sec.gov/submissions/CIK##########.json`, XBRL `companyfacts`, `frames`; nightly `companyfacts.zip`, `submissions.zip` | full filing history | filing timestamps are true publication times → naturally point-in-time; "processing delay of less than a second" (submissions) | "do not require any authentication or API keys"; "current maximum access rate is 10 requests per second"; "Please declare your user agent in request headers" (sample format: company name + contact e-mail) — a generic UA without contact details worked today, but is not what the SEC asks for | fair-access | no (owner should supply a contact UA) | $0 | V-P, V-D† [M7] |
| Alpaca News (Benzinga) | `data.alpaca.markets/v1beta1/news` | items from **2015-01-01** returned; latest 2026-11-10 13:59Z | `created_at` vs `updated_at` — use `created_at`; symbol-tagged | Alpaca terms | 200 calls/min | repo key | $0 | V-P [O3] |
| Official RSS | `federalreserve.gov/feeds/press_all.xml`; `ecb.europa.eu/rss/press.html` | recent items only | item `pubDate` = publication time; no history — must be logged forward | not read | poll politely | no | $0 | V-P [M24] |
| GDELT DOC 2.0 | `api.gdeltproject.org/api/v2/doc/doc?query=…&mode=timelinevol&format=json&timespan=…` | 15-minute resolution over short spans | news-volume intensity; slow (17 s) | not read | UNKNOWN | no | $0 | V-P [M15] |
| Wikipedia pageviews | `wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/<Article>/daily/<start>/<end>` | **2015-07-01→**, daily | `agent=user` filters bots | needs a descriptive User-Agent | not read | no | $0 | V-P [M14] |
| Google Trends | official API is an application-only alpha (announced 2025-07-24) | — | values are relative and re-scaled per request | scraping route: `pytrends` repo is **archived** (last push 2024-08-10) | — | alpha approval | — | V-P (repo), CLAIM (alpha) [M18] |
| Economic calendars | ForexFactory export `nfs.faireconomy.media/ff_calendar_thisweek.json`; Myfxbook RSS `myfxbook.com/rss/forex-economic-calendar-events` | **current week only** (FF) | FF fields: title, country, date, impact, forecast, previous — **no actual**; times carry an ET offset | terms not read | FF: UNKNOWN (poll rarely) | no | $0 | V-P [M16] |
| ↳ Trading Economics | `api.tradingeconomics.com/calendar?c=guest:guest` | — | — | — | **410: "the guest account has been discontinued"** | paid | UNKNOWN | V-P [M17] |
| ↳ official release dates | FRED API `fred/releases/dates` | US releases | authoritative schedule | — | — | FRED key | $0 | CLAIM (endpoint not probed) |
| X API | `docs.x.com` | — | — | "pay-per-usage pricing with no subscriptions" | cap 3 million post reads per billing cycle (cap from fetch†) | yes | **$0.005 per post read** | V-D [M19] |
| Reddit Data API | OAuth | — | — | free tier non-commercial, 100 queries/min with OAuth (CLAIM); commercial terms negotiated (CLAIM) | — | yes | UNKNOWN | CLAIM [M20] |
| Polymarket | Gamma `gamma-api.polymarket.com/markets`; CLOB `clob.polymarket.com/prices-history?market=<token>&interval=max&fidelity=1440`; Data API **v2** `data-api.polymarket.com/v2/trades` | full price history per token | `{t,p}` series; trades carry wallet, size, price; **Data API v1 is retired (410)** | not read | IP-based: Gamma `/markets` 300 req/10 s; CLOB `/prices-history` 1,000 req/10 s; Data v2 `/trades` 300 req/10 s | no | $0 | V-P, V-D† [M21] |
| Kalshi | `api.elections.kalshi.com/trade-api/v2/{markets,markets/trades,series/{ticker}}` | — | public reads worked unauthenticated | not read | Basic tier ≈ 20 reads/s (200 tokens/s, 10 per request) | no for reads | $0 | V-P, V-D† [M22] |
| AQR data library | `aqr.com/Insights/Datasets/…` | monthly factor and asset-class return series (CLAIM for content) | research returns, not instruments; page reachable | AQR terms not read | — | no | $0 | V-P (page) [E21] |

---

## 2. Per-class routes: best free no-account, best free-with-account, best cheap paid

### 2.1 FX

| need | best FREE, no account | best FREE with account (owner action) | best CHEAP paid |
|---|---|---|---|
| daily history, one print | FRED H.10 (USD pairs, 1971/1999→) and ECB (EUR crosses, 1999→) | — | — |
| **live** daily print | ECB file at ~16:00 CET (EUR crosses only); Kraken fiat pairs / Binance `EURUSDT` for a 24/7 print | IG demo API or cTrader demo for broker bid/ask at any chosen instant | Massive Currencies Starter $49/mo (real-time BBO) |
| intraday history | Kraken trades (14 fiat pairs, thin); FXCM sample 2017–2020 (m1, bid+ask, 21 pairs) | Dukascopy JForex demo (tick, bid+ask); TrueFX (tick, registration); Tiingo (OHLC, no bid/ask) | **HistData SFTP $27 one-time** (M1 + tick, 66 pairs); Massive Starter $49/mo (10+ years with quotes) |
| bid/ask to source the cost model | **FXCM sample** — the only free, scriptable, no-account bid+ask series found; enough to *measure* G10 spreads for 2017–2020 | IG demo (10,000 points/week), cTrader demo | Massive Starter |

**What matters.** (a) The backtest print (H.10 noon New York) and any live print are different
instants; a live FX-D logger must record its own print and the gap to H.10 must be measured, not
assumed (the prereg's lag-sensitivity rule already bites here). (b) ECB publishes ~1 h 45 min after the
fix, so an ECB-print signal is executable only at a later, different price. (c) OANDA's EU entity does
not offer v20; do not plan around it until the owner has tried and reported.

### 2.2 Futures

| need | best FREE, no account | best FREE with account | best CHEAP paid |
|---|---|---|---|
| CME daily/hourly, 2010→ | none | **Databento $125 credit** | Databento pay-as-you-go |
| long history (1970s–2010), Eurex and ICE US softs | none | none | **Pinnacle CLC $99 one-time** (no Brent or Gasoil); Norgate $270/yr (Windows); FirstRate (1-min from 2007; price unknown) |
| live | none official | IBKR (needs subscriptions) | Databento Standard $199/mo |
| asset-class proxy | Alpaca ETFs (2016→); FRED spot (not investable) | Tiingo ETFs (pre-2016) | — |

**Databento cost for "daily OHLCV, ~50 contracts, 15 years" — an estimate, not a quote.**
Verified inputs: billing is "per byte consumed … uncompressed size in binary encoding" [U2]; the
GLBX per-schema unit price is not public (it needs a key: `metadata.list_unit_prices`,
`metadata.get_cost`); the docs' *OPRA* example shows `ohlcv-1d` at $600/GB and `ohlcv-1m` at $280/GB
[U5]. Assumptions (CLAIM): 56 bytes per OHLCV record; a GLBX unit price of the same order.

| request | records | size | at $600/GB |
|---|---|---|---|
| A. front + next continuous (`ROOT.c.0`, `ROOT.c.1`), 50 roots, daily, ~3,780 sessions | 378,000 | 0.021 GB | **≈ $13** |
| B. every outright **and spread** via parent symbols (`ROOT.FUT`), 40–100 instruments per root-day | 7.6–18.9 M | 0.42–1.06 GB | ≈ $250–640 |
| C. as A but hourly (~23 h/day) | 8.7 M | 0.49 GB | ≈ $290 |

So request A fits the credit several times over, B and C do not. Ask for explicit or continuous
symbols, never parents, and run `get_cost` first (whether that call is itself free is not stated in the
docs — UNKNOWN). `c.0` and `c.1` on the same day give the roll gap needed to build a back-adjusted
series. **ICE and Eurex cannot be had for 15 years here** — their datasets are younger.

### 2.3 Equities and ETFs

| need | best FREE, no account | best FREE with account | best CHEAP paid |
|---|---|---|---|
| US ETFs/stocks 2016→ | Alpaca (repo key) | — | — |
| **US ETFs/stocks before 2016, adjusted** | Ken French daily market return 1926→ (a series, not instruments); FRED `NASDAQCOM` 1971→ (price only) | **Tiingo free** (30+ years; 500 symbols/month, 50 req/hour) | Tiingo Power $30/mo; Massive Advanced $199/mo (20+ years) |
| UCITS ETFs (IWDA, CSPX, VWCE, EIMI, AGGH, IGLN/SGLN, XEON) | **Euronext CSV, ~2 years**, Euronext-listed lines only | EODHD free (1 year, 20 calls/day); Alpha Vantage (latest 100 bars per call, 25 calls/day, `.LON`) | **EODHD €19.99 for one month** → pull 30+ years once; Marketstack Basic $9.99 (10 years) |
| live EOD | Alpaca; Euronext CSV after the close | Tiingo (5:30 PM ET) | — |

**Adjusted total-return series — who gives one.** Alpaca `adjustment=all` (GIVEN); Tiingo `adj*`
fields, "both split and dividend adjustments" (V-D†); Alpha Vantage only on the premium adjusted
endpoint (V-D); IBKR `ADJUSTED_LAST` (V-D†); EODHD `adjusted_close`, splits and dividends (V-D†);
Euronext `adjusted=Y` —
meaning not documented (UNKNOWN). **Accumulating UCITS share classes (IWDA, CSPX, VWCE, EIMI, SGLN,
XEON) distribute nothing, so their raw close is already the total-return series**; only distributing
lines need dividend adjustment (CLAIM from product structure — check each ISIN's distribution policy).

### 2.4 Options

| need | best FREE, no account | best FREE with account | best CHEAP paid |
|---|---|---|---|
| US equity/ETF chains EOD | **DoltHub** (current to 2026-11-09) | ThetaData Free (EOD from 2023-06-01) | ThetaData Value $40/mo (1-min, 2020→); Standard $80/mo (tick NBBO, 2016→) |
| US live | Alpaca indicative feed (repo key) | — | Alpaca OPRA $99/mo; ThetaData |
| crypto options | **Deribit** live + historical trades (tested back to 2017-01) | — | Tardis $700/mo (order books, chains) |
| free tick samples | Tardis first day of each month, no key | — | — |

### 2.5 Crypto

| need | best FREE, no account | with account | cheap paid |
|---|---|---|---|
| CEX klines, trades, funding, OI/long-short | **Binance archive + REST**; Bybit archive; OKX REST/CDN | — | — |
| long BTC/USD history | Bitstamp (2012→), Bitfinex (2013→), Kraken OHLCVT archive | — | — |
| perp DEX | dYdX indexer; DefiLlama open-interest and fees | Hyperliquid S3 (AWS account, requester pays) | Tardis; Velo $199/mo |
| cross-venue aggregates | DefiLlama; CoinGecko keyless | CoinGecko Demo, CoinMarketCap Basic (1 year each) | CoinGlass $29/mo; CoinGecko Analyst $129/mo |
| on-chain / DEX | GeckoTerminal, DexScreener (snapshots) | Helius free (1M credits), The Graph (100k queries) | Bitquery history add-on from $70/mo per chain |

### 2.6 Macro and alternative data

| need | best FREE, no account | with account | paid |
|---|---|---|---|
| point-in-time macro | **ALFRED vintage CSV** | FRED API key (all vintages per call, release dates) | — |
| positioning | CFTC COT (Socrata), FINRA short volume | — | — |
| event schedule | ForexFactory weekly JSON; Myfxbook RSS | FRED release dates | Trading Economics (guest key discontinued) |
| text / attention | Wikipedia pageviews, GDELT, Alpaca News (repo key), SEC EDGAR | — | X API $0.005 per post |
| prediction markets | Polymarket (Gamma, CLOB, Data v2), Kalshi | — | — |

---

## 3. Cross-cutting pitfalls

### 3.1 The daily FX "prints" are different instants

| series | instant | ev |
|---|---|---|
| FRED H.10 `DEX*` | noon New York buying rate | GIVEN |
| ECB reference rate | ~14:10 CET concertation; file ~16:00 CET | V-D, V-P |
| Norges Bank | labelled "ECB concertation time 14:15 CET" (the ECB page itself says 14:10) | V-P |
| Bank of Japan `FXERD01` | 9:00 JST, Tokyo | V-P |
| Bank of Canada `FXUSDCAD` | a **daily average**, no instant | V-P |
| Bank of England, RBA, Riksbank | fixing time not read today | UNKNOWN |
| OANDA daily candle | 17:00 America/New_York alignment by default | V-D |
| FXCM D1 sample | bar stamped 22:00 UTC (= 17:00 New York in winter) | V-P |
| HistData | "Eastern Standard Time … WITHOUT Day Light Savings adjustments" | V-D† |
| Kraken, Binance | 00:00 UTC bars, 24/7 | GIVEN, V-P |

A cross-sectional signal built from prints struck hours apart contains a fake lead-lag. Use one source
per panel, and treat the ECB print as the placebo the prereg already declares.

### 3.2 Timestamp conventions (bar open vs close)

- **Alpaca** daily bars: `t` = midnight Eastern of the session (04:00Z summer, 05:00Z winter) — a date
  label. The close it contains happens ~16 hours later (V-P).
- **Binance** klines: first column is open time; spot files switch to **microseconds on 2025-01-01**
  (V-D). A loader that assumes milliseconds silently mis-dates 2025+ by a factor of 1,000.
- **OANDA** candle `time` = start of the candle (V-D). **FXCM** D1 = bar start at 22:00 UTC (V-P).
- **Coinbase** candles: `[time, low, high, open, close, volume]`, bucket start (V-P).
- **Kraken OHLCVT**: intervals without trades have no row (V-D†) — reindex before computing returns.
- **IBKR**: bar time zone = the zone chosen at TWS login; a daily bar is dated on the day it closes (V-D†).
- **FRED/ALFRED**: `observation_date` is the *period* (2019-10-01 = Q4 2019), never the publication
  date. Only the vintage date tells you when a number was knowable (V-P).
- **CFTC**: `report_date` is the Tuesday; the public learns it on Friday 15:30 ET (V-D).

### 3.3 Survivorship

- IBKR does not serve "securities which are no longer trading" (V-D) → unusable for stock universes.
- Tiingo's metadata endpoint "reflects assets currently covered" (V-D†); delisted coverage UNKNOWN.
- EODHD exposes delisted tickers through `delisted=1` (V-D†); Alpha Vantage has a listing/delisting
  utility (V-D).
- Binance's archive keeps delisted symbols: `LUNAUSDT` USD-M 1h monthly files run 2021-01→2022-05
  (17 files, V-P). **But `FTTUSDT` USD-M files start 2022-04** (and run to 2026-10), so FTT cannot enter
  a universe ranked on 2021 volume — the prereg names FTT as an example; the loader must build the
  list from the files that exist, symbol by symbol (V-P).
- An ETF lane built from today's ticker list is a survivor list by construction. That applies to the
  prereg's fixed 50-ETF list (design note for the conductor, not a change to the prereg).

### 3.4 Publication lags that matter for live signals

To re-observe the ECB publication instant on any TARGET day:
`curl -sI https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml | grep -i last-modified`
(before ~16:00 CET it still shows the previous business day).

| data | available | ev |
|---|---|---|
| ECB reference rates | ~16:00 CET same day (15:56 CET observed for 2026-11-09) | V-P |
| FRED H.10 | released weekly with a lag (per the brief) | GIVEN |
| FRED copy of EIA spot oil | ~1 week (last row 2026-11-03 on 2026-11-10) | V-P |
| Tiingo EOD | 5:30 PM ET, corrections to 8 PM | V-D† |
| Alpaca free plan | everything except the latest 15 minutes | V-D† |
| Binance archive | daily files next day; monthly files first Monday | V-D |
| DoltHub options | prior session present by 14:10 UTC next day | V-P |
| FINRA short volume | prior session present next day | V-P |
| CFTC COT | Friday 15:30 ET for Tuesday | V-D |
| Kraken OHLCVT archive | quarterly | V-D† |
| Hyperliquid S3 | "approximately once a month", may be missing | V-D |
| Ken French library | a month or more (file through 2026-09-30 on 2026-11-10) | V-P |

### 3.5 Licences that bite

- **QuantConnect:** no export of any data, by any means, including by an AI agent (V-D).
- **Dukascopy website:** non-commercial use; no robots; "may not be used to construct a database" (V-D†).
- **justETF:** no automated price inquiries (V-D).
- **Tiingo:** "Internal Use Only" on $0 and $30 plans (V-D†) — fine for own research, not for publishing data.
- **FXCM sample, CryptoDataDownload (CC BY-NC-SA):** personal / non-commercial (V-D, V-D†).
- **ECB reference rates:** information only; transaction use discouraged (V-D).
- **FRED:** third-party copyrighted series are for "your own personal use" unless the owner agrees (V-D†).
- **GOOGLEFINANCE:** no programmatic access to history (V-D†).

---

## 4. Owner actions that unlock data, ranked by value / cost

Account creation, logins and payments are the owner's. Nothing below was done.

| # | action | cost | time | what it unlocks | why it matters here |
|---|---|---|---|---|---|
| 1 | **Tiingo free account → API token** | $0 | 5 min | 30+ years of adjusted US EOD, 500 symbols/month (limits are V-D† — the pricing page is script-rendered; re-read them at signup) | extends the MA-ETF lane before 2016 (inception years from recall, CLAIM: SPY 1993, EFA 2001, TLT 2002, GLD 2004); 50 tickers = 50 requests = one hour's free quota |
| 2 | **FRED API key** | $0 | 2 min | all ALFRED vintages per call, "Initial Release Only" output, release dates | point-in-time macro features and a free US release calendar; the no-key vintage CSV already works for one-offs |
| 3 | **Databento signup** | $0 ($125 credit, 6 months) | 10 min; card requirement UNKNOWN | CME futures OHLCV 2010-06→ with continuous symbols | opens a real futures lane for ≈ $13 of credit **if** the CME unit price is of the order of the docs' OPRA example (§2.2 request A); run `get_cost` first |
| 4 | **One FX demo with an API** — IG demo first, cTrader demo second, Dukascopy JForex demo third | $0 | 15–30 min each | broker bid/ask at a chosen instant; history (IG: 10,000 points/week) | replaces the OANDA route (not offered by its EU entity); gives the live FX-D logger a real executable print and a measured spread |
| 5 | Ask Dukascopy support, in writing, whether exporting history through JForex for personal research is permitted | $0 | one e-mail | the deepest free tick source, if allowed | the terms read today neither grant nor forbid it |
| 6 | SEC EDGAR contact User-Agent (owner decides which e-mail) | $0 | 1 min | policy-compliant EDGAR pulls | filings are a naturally point-in-time event source |
| 7 | EIA API key | $0 | 2 min | petroleum and gas spot, inventories | event data; FRED's copy lags a week |
| 8 | **Pinnacle CLC** | $99 once | — | 98 back-adjusted continuous futures, earliest 1969 | the cheapest way to a 30–50-year managed-futures test incl. Eurex and non-US index markets; Brent, Gasoil and VIX are not in the list |
| 9 | **EODHD, one month** | €19.99 (half for students, "for educational purposes") | — | 30+ years EOD for LSE / XETRA and more, 100,000 calls/day | pull the UCITS universe once, then cancel; "Personal use" plan |
| 10 | **HistData SFTP** | $27 once (15 days) | — | M1 + tick for 66 pairs in bulk | intraday FX research without scraping; EST-no-DST and bid-only bars must be handled |
| 11 | Massive Currencies Starter | $49/mo | — | 10+ years FX with BBO quotes, flat files, real time | the cheap paid route to FX bid/ask history at scale |
| 12 | ThetaData Value | $40/mo | — | options 1-minute from 2020, real time | only if an options lane is reopened |
| 13 | CoinGlass Hobbyist | $29/mo | — | cross-exchange OI, funding, liquidations | only if Binance-only positioning proves too narrow |
| 14 | IBKR account | $0 to open; data subscriptions extra | days | FX bid/ask history, live quotes, the eventual execution venue | needed anyway before any FX paper-to-live step; not needed for research |
| — | **Do not buy:** Norgate (Windows-only tool on a Linux host), Tardis ($700/mo), Velo ($199/mo), Bitquery history add-on, any QuantConnect tier *as a data source* | | | | |

---

## 5. Corrections to the brief (things that turned out different)

1. **Binance USD-M archive starts 2020-01, not 2019-09.** Monthly kline and funding files for BTCUSDT
   begin 2020-01; only the REST API returns candles from 2019-09-08. `metrics` begins 2020-09-01,
   `bookDepth` 2023-01-01. The CRYPTO-H design window (2021-01→) is unaffected. (V-P)
2. **ECB concertation is "around 14:10 CET"** on the ECB page, not 14:15 (Norges Bank's metadata still
   says 14:15). Publication ~16:00 CET is confirmed. When the concertation moved from 14:15 to 14:10
   was not found (UNKNOWN) — older history may have been struck at 14:15. (V-D, V-P)
3. **OANDA v20 excludes the EU entity.** (V-D)
4. **Bank of Canada `FXUSDCAD` is a daily average from 2017-01-03** — not a print, not long. (V-P)
5. **FRED `SP500` is a rolling 10-year window; ICE BofA total-return indices a rolling 3-year window;
   the LBMA gold series ID is gone (404).** (V-P)
6. **Kraken Futures' funding-history endpoint keeps about one year.** (V-P)
7. **Binance option `EOHSummary` ended 2023-10-23.** (V-P)
8. **Alpaca:** option bars exist from at least 2024-01-18; crypto bars start 2021-01-01 and need no
   key; FX is not granted to the repo key (403); news goes back to 2015-01-01. (V-P)
9. **Polymarket Data API v1 is retired (410); v2 works.** (V-P)
10. **CryptoCompare's `min-api` now requires a key.** (V-P)
11. **DefiLlama charges for the derivatives-volume overview and perps funding (402);** open interest,
    fees, stablecoins and yields charts are free. (V-P)
12. **Trading Economics' guest key is discontinued; `pytrends` is archived; Flipside's free tools are
    gone; Deutsche Börse's public Xetra bucket is closed; polygon.io redirects to massive.com.** (V-P / CLAIM for Flipside)
13. **Euronext's free history is two years, not full history.** (V-P)
14. **Trading 212's API has no price data of any kind.** (V-D†)
15. **`FTTUSDT` USD-M archive files start 2022-04**, so FTT cannot be in a universe ranked on 2021
    volume (the prereg cites FTT as an example of a delisted name). `LUNAUSDT` is there, 2021-01→2022-05. (V-P)
16. **Ken French's daily file runs a month or more behind** (through 2026-09-30 on 2026-11-10). (V-P)

---

## 6. Not verified today — do not rely on these without a check

- OANDA: whether a Dutch resident can open a v20 practice account at a non-EU division.
- Dukascopy: demo duration (14 days is a CLAIM; the demo page read today states no duration), history depth, which entity serves a Dutch applicant, and permission for bulk export via JForex.
- TrueFX: pairs, years and terms (login wall; terms page not located).
- Databento: GLBX per-schema unit prices; ICE and Eurex start dates (CLAIM-grade today); whether signup needs a card.
- FirstRate Data: bundle prices. Barchart, Nasdaq Data Link, CME DataMine, CSI data prices.
- Pinnacle CLC: file format, delivery, licence terms, and how current the history is.
- EODHD: Euronext Amsterdam coverage and code; Twelve Data, FMP, Finnhub, Dune,
  Birdeye, CoinDesk Data, Laevitas, Kaiko, Amberdata: plan details.
- Saxo: SIM account availability and chart-history limits. cTrader: historical tick/bar depth.
- IBKR: per-exchange subscription prices for Euronext / Xetra / LSE; whether FX history needs none.
- Bank of England, RBA, Riksbank fixing times; SNB daily series; OECD API limits and terms.
- Reddit API terms and status; Google Trends alpha access; Polymarket/Kalshi public data dumps.
- Hyperliquid: free third-party mirrors (none found); the API itself (POST-only, not probed).
- Binance archive: start dates of every symbol in the prereg's top-40 list (only BTCUSDT, LUNAUSDT, FTTUSDT were listed today).
- Terms of use for automated access at Euronext Live, FINRA CDN, GDELT, ForexFactory export, DefiLlama.
- Stooq's bulk daily databases (a manual browser download behind a captcha) may hold long daily
  history for futures continuations, FX and LSE/Xetra lines — CLAIM from recall, off-limits to probe,
  terms not read; owner-manual only if at all.
- Everything marked V-D†: the provider's page was read through a summariser.

---

## 7. Source list (all accessed 2026-11-10)

Method codes: **probe** = scripted GET from this host, response inspected · **raw** = page fetched and
its text read directly · **fetch†** = page read through the fetch tool's summariser · **search** =
search-result snippets only (CLAIM grade).

### FX

| key | URL | method | used for |
|---|---|---|---|
| F1 | https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html | raw (and fetch†) | 16:00 CET update, 14:10 CET concertation, "information purposes only", file list |
| F2 | https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml | probe (GET 13:49 UTC; HEAD 13:49, 14:12 and 14:32 UTC) | content dated 2026-11-09; `Last-Modified: Mon, 09 Nov 2026 14:56:21 GMT` |
| F3 | https://api.frankfurter.dev/v1/latest?base=EUR&symbols=USD,JPY | probe | ECB mirror answers without a key |
| F4 | https://github.com/neurallayer/oanda-v20-java (README, via search) | search | anecdote that OANDA dropped API support in Europe (CLAIM, not used as evidence) |
| F5 | https://developer.oanda.com/rest-live-v20/introduction/ | raw | division exclusion sentence; "dating back to 2005" |
| F6 | https://developer.oanda.com/rest-live-v20/development-guide/ · https://developer.oanda.com/rest-live-v20/pricing-ep/ · https://developer.oanda.com/rest-live-v20/instrument-df/ | raw | URLs, 120 req/s, 20 streams, candle parameters, granularities (`/instrument-ep/` returned 404) |
| F7 | https://www.oanda.com/eu-en/ | raw | EU site operated by OANDA TMS Brokers S.A., MetaTrader 5 |
| F8 | https://raw.githubusercontent.com/fxcm/MarketData/master/README.md (repo pushed 2026-10-29) | raw | sample scope 2017–2020, 21 pairs, UTC, personal use / EULA |
| F9 | https://candledata.fxcorporate.com/D1/EURUSD/2020.csv.gz | probe | bid+ask OHLC columns, 22:00 UTC stamps, 312 rows |
| F10 | https://wiki.dukascopy.com/en/development/strategy-api/historical-data/history-bars/ (raw) · …/overview-historical-data/ (fetch†) | raw, fetch† | `IHistory`, `OfferSide.BID/ASK`, demo history equals live |
| F11 | https://www.dukascopy.com/swiss/english/legal-pages/terms-of-use/ · https://www.dukascopy.com/swiss/english/marketwatch/historical/ | fetch† | non-commercial use, no robots, no database construction; export tool description |
| F12 | https://labs.ig.com/faq.html | raw (and fetch†) | free at default quotas; 10,000 historical points/week; rate limits |
| F13 | https://help.ctrader.com/open-api/ | fetch† | demo support; 50 and 5 requests/s |
| F14 | https://www.developer.saxo/openapi/learn/rate-limiting | fetch† | 120 requests/min per session per service group |
| F15 | https://www.dukascopy.com/swiss/english/forex/demo_fx_account/ | fetch† + search | platforms offered on demo (JForex, MT4, MT5); the page states no duration — "14 days" comes from search snippets (CLAIM) |
| F16 | https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?recent=3 · …/csv?start_date=2016-01-01&end_date=2017-01-10 | probe | daily average; first row 2017-01-03 |
| F17 | https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Oct/2026&Dateto=now&SeriesCodes=XUDLUSS&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N | probe | CSV to 09 Nov 2026 |
| F18 | https://data.snb.ch/api/cube/devkum/data/csv/en?fromDate=2026-10&toDate=2026-11 | probe | monthly cube |
| F19 | https://www.rba.gov.au/statistics/tables/csv/f11.1-data.csv | probe | daily; file starts 03-Jan-2023 |
| F20 | https://data.norges-bank.no/api/data/EXR/B.USD.NOK.SP?format=csv&lastNObservations=3 | probe | "ECB concertation time 14:15 CET" label |
| F21 | https://api.riksbank.se/swea/v1/Observations/Latest/SEKUSDPMI | probe | latest observation |
| F22 | https://www.stat-search.boj.or.jp/api/v1/getDataCode?format=json&lang=en&db=FM08&code=FXERD01&startDate=202610&endDate=202611 | probe | USD/JPY 9:00 JST series |
| F23 | https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?lastNObservations=1&format=csvdata | probe | SDMX route returns the same 2026-11-09 value |
| F24 | https://www.quantconnect.com/terms | raw (and fetch†) | "Data stays on QuantConnect"; §2.6 No Data Export |
| F25 | https://www.quantconnect.com/pricing · https://www.quantconnect.com/docs/v2/cloud-platform/datasets/licensing | fetch† | free-tier nodes and resolutions; cloud vs download licence |
| F26 | https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/forex-data | fetch† | 72 pairs, January 2007→, OANDA-sourced |
| F27 | https://www.truefx.com/truefx-historical-downloads/ | fetch† | registration wall; tick, top-of-book |
| F28 | https://www.histdata.com/f-a-q/ · https://www.histdata.com/download-free-forex-data/ | fetch† | EST without DST; bid bars; formats |
| F29 | https://www.histdata.com/download-by-ftp/ | raw (and fetch†) | $27, 15 days, 66 pairs, PayPal |
| F30 | https://interactivebrokers.github.io/tws-api/historical_limitations.html (legacy docs, marked deprecated) | raw (and fetch†) | pacing rules; unavailable data |
| F31 | https://interactivebrokers.github.io/tws-api/historical_data.html (raw) · …/historical_bars.html (fetch†) | raw, fetch† | Level 1 requirement; `TRADES` vs `ADJUSTED_LAST`; bar time zone |
| F32 | https://www.tiingo.com/documentation/forex | fetch† | endpoints, 140+ pairs, beta |
| F33 | https://twelvedata.com/pricing | fetch† | Basic 8 credits/min, 800/day (paid prices inconsistent on the page) |
| F34 | https://massive.com/currencies | raw (and fetch†) | Basic $0 / Starter $49 |
| F35 | https://polygon.io/ | probe (HEAD) | 301 → https://massive.com/ |
| F36 | https://firstratedata.com/b/20/fx-majors | raw | 74 tickers, Jan 2009→, updates $59.95/mo |

### Futures

| key | URL | method | used for |
|---|---|---|---|
| U1 | https://databento.com/pricing | fetch† | $125 credit; plans; history by tier |
| U2 | https://databento.com/docs/faqs/usage-pricing-and-data-credits | raw | "$125 in free credits … expire after 6 months"; billed per byte uncompressed |
| U3 | https://databento.com/catalog/cme/GLBX.MDP3 | fetch† | available from 2010-06-06; schemas; no licence for historical |
| U4 | https://databento.com/docs/standards-and-conventions/symbology | raw (and fetch†) | continuous and parent symbology; no back-adjustment |
| U5 | https://databento.com/docs/api-reference-historical/metadata/metadata-list-unit-prices (raw) · …/metadata-get-cost (fetch†) | raw, fetch† | OPRA example unit prices; `get_cost` example |
| U6 | https://pinnacledata2.com/clc.html | raw + fetch† | 98 markets, $99, update prices, adjustment methods, market list |
| U7 | https://norgatedata.com/futurespackage.php (raw) · https://norgatedata.com/faq.php (raw) · https://norgatedata.com/system-requirements.php (fetch†) | raw, fetch† | prices, coverage; Windows VM example; .NET Framework 4.8 |
| U8 | https://databento.com/docs/venues-and-datasets (fetch†) · https://databento.com/blog/ice-futures-market-data · https://databento.com/blog/introducing-ice-europe-financials · https://databento.com/blog/eurex-now-available (all three via search snippets) | fetch†, search | dataset codes; ICE start 2018-12-23 and Eurex start 2025-03-10 (CLAIM) |
| U9 | https://firstratedata.com/b/29/futures-most-active | raw | 130 futures, Jan 2007→, adjustment types, update fee |
| U10 | https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/algoseek/us-futures | fetch† | May 2009→, 157 contracts, exchanges |
| U11 | https://www.csidata.com/ | fetch† | product description, UA from $25/mo |
| U12 | https://www.barchart.com/ (pages via search) | search | download limits (CLAIM) |
| U13 | https://docs.data.nasdaq.com/docs/data-organization (via search) | search | free vs premium sets (CLAIM) |
| U14 | https://www.cmegroup.com/market-data/datamine-historical-data.html (via search; direct fetch timed out) | search | EOD to 1982; pricing by request (CLAIM) |

### Equities and ETFs

| key | URL | method | used for |
|---|---|---|---|
| E1 | https://docs.alpaca.markets/docs/about-market-data-api | fetch† | Basic vs Algo Trader Plus; 200 calls/min; latest-15-minutes rule |
| E2 | https://www.tiingo.com/about/pricing | fetch† | free-tier limits; "30+ Years"; licence |
| E3 | https://www.alphavantage.co/documentation/ | raw | compact vs full; premium endpoints; `.LON`; options since 2008 |
| E4 | https://www.alphavantage.co/premium/ | fetch† | 25 requests/day; $49.99–$249.99 |
| E5 | https://eodhd.com/pricing | raw (and fetch†) | free 20 calls/day; €19.99 All-World; student discount (1-year free-tier history from fetch† only) |
| E6 | https://www.tiingo.com/documentation/end-of-day | fetch† | adjusted fields; CRSP standard; 5:30 PM ET |
| E7 | https://live.euronext.com/en/ajax/AwlHistoricalPrice/getFullDownloadAjax/IE00B4L5Y983-XAMS?format=csv&decimal_separator=.&date_form=d/m/Y&op=&adjusted=Y&base100=&startdate=…&enddate=… | probe (2 GETs) | CSV fields; 2-year depth |
| E8 | https://live.euronext.com/robots.txt | probe | no rule against `/en/ajax/` for generic agents |
| E9 | https://eodhd.com/financial-apis/list-supported-exchanges | fetch† | LSE, XETRA codes; `delisted=1` |
| E10 | https://docs.trading212.com/api | fetch† | endpoint list (no prices); rate limits; beta |
| E11 | https://www.justetf.com/documents/justETF_general_terms_and_conditions.pdf | raw (pdftotext) | clause 3.1, automated price inquiries |
| E12 | https://support.google.com/docs/answer/3093281 | fetch† | GOOGLEFINANCE restrictions |
| E13 | https://massive.com/stocks | fetch† | plan ladder |
| E14 | https://fred.stlouisfed.org/graph/fredgraph.csv?id={NASDAQCOM, SP500, BAMLCC0A0CMTRIV, BAMLHYH0A0HYM2TRIV, GOLDAMGBD228NLBM, VIXCLS, DGS10, DCOILWTICO} | probe (8 GETs) | series start dates; rolling windows; 404; one-week lag on oil |
| E15 | https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip | probe | downloads without a key (178 KB); rows 19260701→20260930 |
| E16 | https://marketstack.com/pricing | fetch† | plan ladder |
| E17 | https://api.nasdaq.com/api/quote/SPY/historical?assetclass=etf&… | probe | HTTP/2 stream reset → not retried |
| E18 | https://deutsche-boerse-xetra-pds.s3.eu-central-1.amazonaws.com/?list-type=2&max-keys=3 | probe | `AccessDenied` |
| E19 | https://www.ishares.com/uk/individual/en/products/251882/…/1506575576011.ajax?fileType=csv&fileName=IWDA_fund&dataType=fund | probe | HTML returned, not CSV |
| E20 | https://www.interactivebrokers.com/en/pricing/market-data-pricing.php | raw | bundle USD 10.00 with USD 30 waiver; 15-minute delayed European exchanges |
| E21 | https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Factors-Monthly | probe | page reachable (content not read) |
| E22 | https://eodhd.com/financial-apis/api-for-historical-data-and-volumes | fetch† | raw OHLC, `adjusted_close` definition, ticker format, update timing, sample start dates |

### Options

| key | URL | method | used for |
|---|---|---|---|
| O1 | https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master?q=SELECT date FROM option_chain ORDER BY date DESC LIMIT 1 | probe | latest date 2026-11-09 (two heavier queries timed out at 40 s) |
| O2 | https://docs.alpaca.markets/docs/historical-option-data | raw (and fetch†) | "since February 2024"; indicative vs OPRA |
| O3 | https://data.alpaca.markets — `/v1beta1/news` (2), `/v1beta1/options/bars`, `/v1beta1/options/snapshots/SPY?feed=indicative`, `/v1/corporate-actions`, `/v1beta1/forex/latest/rates`, `/v2/stocks/SPY/bars` (2); `/v1beta3/crypto/us/bars` without auth | probe (9 GETs, 8 with the repo key) | news from 2015-01-01; option bar 2024-01-18; crypto from 2021-01-01; FX 403; daily-bar timestamps |
| O4 | https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time?currency=BTC&kind=option&start_timestamp=1483228800000&end_timestamp=1485907200000&count=2&sorting=asc | probe | 2017 option trades with IV |
| O5 | https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/option/daily/… | probe | `EOHSummary` ends 2023-10-23; `BVOLIndex` current |
| O6 | https://tardis.dev/ (fetch†) · https://docs.tardis.dev/llms-full.txt (raw) | fetch†, raw | prices; "first day of each month … without a Data API key" |
| O7 | https://www.thetadata.net/pricing (raw + fetch†) · https://thetadata.net/docs/Articles/Getting-Started/Subscriptions.html (fetch†) | raw, fetch† | $40/$80/$160; tier start dates; free tier |
| O8 | https://massive.com/options | fetch† | plan ladder |
| O9 | https://datashop.cboe.com/option-eod-summary | fetch† | contents; January 2012→ |
| O10 | https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/optionmetrics (and university library pages, via search) | search | institutional access; 1996→ (CLAIM) |
| O11 | https://databento.com/docs/api-reference-historical/metadata/metadata-list-unit-prices | raw | OPRA example unit prices |

### Crypto

| key | URL | method | used for |
|---|---|---|---|
| C1 | https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/… | probe (20 listings) | folder map; earliest/latest files; LUNAUSDT and FTTUSDT folders |
| C2 | https://api.binance.com/api/v3/klines?symbol=EURUSDT… · https://fapi.binance.com/fapi/v1/klines?symbol={BTCUSDT,XAUUSDT}… · https://fapi.binance.com/futures/data/openInterestHist | probe | REST reachable; first USD-M candle 2019-09-08; XAUUSDT from 2025-12-11 |
| C3 | https://raw.githubusercontent.com/binance/binance-public-data/master/README.md | raw | next-day daily files; microseconds from 2025-01-01 |
| C4 | https://public.bybit.com/ · https://public.bybit.com/trading/BTCUSDT/ · https://api.bybit.com/v5/market/kline · …/funding/history | probe | folders; first file 2020-03-25; REST reachable |
| C5 | https://www.okx.com/api/v5/market/history-candles?instId=BTC-USDT-SWAP&bar=1D… · https://static.okx.com/cdn/okex/traderecords/trades/daily/20240102/BTC-USDT-trades-2024-01-02.zip | probe | REST and CDN reachable |
| C6 | https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data | fetch† (page served in Dutch) | archive scope, quarterly updates, empty intervals |
| C7 | https://futures.kraken.com/api/charts/v1/trade/PF_XBTUSD/1d?from=…&to=… · https://futures.kraken.com/derivatives/api/v4/historicalfundingrates?symbol=PF_XBTUSD | probe | candles from 2022-03-23; funding 2025-10-30→ only |
| C8 | https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400&start=…&end=… | probe | 2015-07-20 rows; column order |
| C9 | https://www.bitstamp.net/api/v2/ohlc/btcusd/?step=86400&limit=2&start=1325376000 · https://api-pub.bitfinex.com/v2/candles/trade:1D:tBTCUSD/hist?limit=2&sort=1 | probe | 2012 and 2013 starts |
| C10 | https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint · https://hyperliquid.gitbook.io/hyperliquid-docs/historical-data | raw (and fetch†) | 5,000-candle cap; S3 buckets; requester pays |
| C11 | https://indexer.dydx.trade/v4/candles/perpetualMarkets/BTC-USD?resolution=1DAY&limit=2 · …/v4/historicalFunding/BTC-USD?limit=2 | probe | public indexer |
| C12 | https://api.llama.fi/v2/chains · https://stablecoins.llama.fi/stablecoincharts/all?stablecoin=1 · https://yields.llama.fi/chart/{pool} · https://api.llama.fi/summary/fees/hyperliquid · https://api.llama.fi/overview/open-interest · https://api.llama.fi/summary/open-interest/hyperliquid · https://api.llama.fi/overview/dexs · https://coins.llama.fi/chart/coingecko:bitcoin · **402:** https://api.llama.fi/overview/derivatives , https://yields.llama.fi/perps | probe | free vs paid endpoints |
| C13 | https://www.coingecko.com/en/api/pricing · https://docs.coingecko.com/docs/common-errors-rate-limit (fetch†) · https://api.coingecko.com/api/v3/ping , …/coins/bitcoin/market_chart (probe) | fetch†, probe | plan ladder; keyless access works |
| C14 | https://coinmarketcap.com/api/pricing/ | fetch† | plan ladder |
| C15 | https://www.coinglass.com/pricing | fetch† | $29–$699; no free tier |
| C16 | https://www.cryptodatadownload.com/data/ | fetch† | CC BY-NC-SA 4.0; Plus+ $39 |
| C17 | https://docs.velo.xyz/api | fetch† | $199/mo; history by billing period |
| C18 | https://thegraph.com/studio-pricing/ | fetch† | 100,000 free queries; $2 per 100,000 |
| C19 | https://docs.dexscreener.com/api/reference (fetch†) · https://api.dexscreener.com/latest/dex/search?q=SOL%20USDC (probe) | fetch†, probe | rate limits; endpoint reachable |
| C20 | https://api.geckoterminal.com/api/v2/networks/solana/pools/58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2/ohlcv/day?limit=2 | probe | pool OHLCV without a key |
| C21 | https://www.helius.dev/pricing | fetch† | plan ladder |
| C22 | https://bitquery.io/pricing | fetch† | plan ladder; history add-on |
| C23 | https://www.coinapi.io/products/market-data-api/pricing | fetch† | $25 credits; tiers |
| C24 | https://min-api.cryptocompare.com/data/v2/histoday?fsym=BTC&tsym=USD&limit=2 | probe | 401 "API key required" |
| C25 | https://docs.flipsidecrypto.xyz/support/product-special-releases/2025/2025-06-20-or-deprecating-studio-dashboards-api-sdk (via search) | search | sunset 2025-07-01 (CLAIM) |
| C26 | https://www.kaiko.com/about-kaiko/pricing-and-contracts · https://amberdata.io/pricing (via search) | search | quote-based (CLAIM) |

### Macro, positioning, text, alternative

| key | URL | method | used for |
|---|---|---|---|
| M1 | https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=GDPC1&vintage_date=2020-01-30&cosd=2019-01-01&coed=2019-12-31 | probe | vintage column `GDPC1_20200130`, no key |
| M2 | https://fred.stlouisfed.org/docs/api/fred/series_observations.html (fetch†) · https://api.stlouisfed.org/fred/series/observations?series_id=GDPC1&file_type=json&limit=1 (probe → 400 without key) | fetch†, probe | vintage parameters; key requirement |
| M3 | https://fred.stlouisfed.org/docs/api/terms_of_use.html | fetch† | attribution line; third-party series; discretionary limits |
| M4 | https://publicreporting.cftc.gov/resource/6dca-aqww.json · https://publicreporting.cftc.gov/resource/gpe5-46if.json (SoQL `$limit`, `$order`, `$select`) | probe (3 GETs) | earliest and latest report dates |
| M5 | https://www.cftc.gov/MarketReports/CommitmentsofTraders/AbouttheCOTReports/index.htm | raw (and fetch†) | Friday 3:30 p.m. Eastern; history back to 1986 / 1995 / 2006 |
| M6 | https://cdn.finra.org/equity/regsho/daily/CNMSshvol20261109.txt | probe | fields; next-day presence |
| M7 | https://data.sec.gov/submissions/CIK0000320193.json (probe, generic UA) · https://www.sec.gov/search-filings/edgar-application-programming-interfaces · https://www.sec.gov/about/webmaster-frequently-asked-questions (fetch†) | probe, fetch† | no key; latency; bulk zips; 10 requests/s; declare a user agent |
| M8 | https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0 | probe | no key |
| M9 | https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv | probe | curve to 11/09/2026 |
| M10 | https://markets.newyorkfed.org/api/rates/secured/sofr/last/2.json | probe | SOFR |
| M11 | https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr?format=JSON&geo=NL&coicop=CP00&lastTimePeriod=2 | probe | JSON-stat |
| M12 | https://api.worldbank.org/v2/country/NL/indicator/NY.GDP.MKTP.CD?format=json&mrv=1 | probe | reachable |
| M13 | https://sdmx.oecd.org/public/rest/data/… (probe → 404 `NoRecordsFound` on my key) · https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html (bot check, not retried) | probe | host reachable only |
| M14 | https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Bitcoin/daily/20150701/20150703 | probe (generic UA) | data from 2015-07-01 |
| M15 | https://api.gdeltproject.org/api/v2/doc/doc?query=bitcoin&mode=timelinevol&format=json&timespan=2d | probe | 15-minute timeline |
| M16 | https://nfs.faireconomy.media/ff_calendar_thisweek.json · https://www.myfxbook.com/rss/forex-economic-calendar-events | probe | calendar fields |
| M17 | https://api.tradingeconomics.com/calendar?c=guest:guest&f=json | probe | 410, guest discontinued |
| M18 | https://api.github.com/repos/GeneralMills/pytrends (probe: `archived: true`, pushed 2024-08-10) · https://developers.google.com/search/blog/2025/07/trends-api (via search) | probe, search | library dead; official alpha (CLAIM) |
| M19 | https://docs.x.com/x-api/getting-started/pricing | raw (and fetch†) | $0.005 per post read; 3 million cap |
| M20 | third-party pages on Reddit API terms (via search; Reddit help centre returned 403) | search | CLAIM only |
| M21 | https://gamma-api.polymarket.com/markets?limit=1… · https://clob.polymarket.com/prices-history?market=<token>&interval=max&fidelity=1440 · https://data-api.polymarket.com/trades (410) · https://data-api.polymarket.com/v2/trades?limit=1 (probe) · https://docs.polymarket.com/quickstart/introduction/rate-limits (fetch†) | probe, fetch† | public endpoints; v1 retired; rate limits |
| M22 | https://api.elections.kalshi.com/trade-api/v2/markets?limit=1&status=open · …/markets/trades?limit=1 · …/series/KXFED (probe) · https://docs.kalshi.com/getting_started/rate_limits (fetch†) | probe, fetch† | public reads; token budgets |
| M23 | https://api.eia.gov/v2/petroleum/pri/spt/data/?frequency=daily&data[0]=value&length=1 | probe | 403 `API_KEY_MISSING` |
| M24 | https://www.federalreserve.gov/feeds/press_all.xml · https://www.ecb.europa.eu/rss/press.html | probe | both feeds answer (ECB item dated 10 Nov 2026 15:00 +0100) |

**Raw probe outputs** for this run are in the session scratchpad
`/tmp/claude-1000/-home-anont-meme/6080f3fd-667a-4f3a-891c-095ad42a53a6/scratchpad/r2/raw/` (volatile
— `/tmp`; they are not part of the repo and will not survive a reboot). Re-run the URLs above to reproduce.
