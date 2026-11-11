# PLATFORMS — execution venues with API trading for a Dutch retail resident

**State of 2026-11-10.** Written for the FACTORY conductor by a research analyst sub-agent (model `claude-fable-5-2`).
Companion file: `venues.json` (machine-readable specs for 12 venues). Research only: no account was opened, no
order placed, no form submitted, no login used.

> **Correction, 2026-11-10 20:35 UTC (conductor): the Kraken Futures demo is NOT available.** This file marks it
> "Yes (V)" in three places: the Kraken Derivatives row of the venue table, the row "Kraken Futures demo and public
> API" of the data table, and the "free demo APIs" remark in the crypto-perp recommendation. That tag rested on
> Kraken's developer guide `[K13]` alone; nobody had requested the host.
> - **Verified fact (own requests, 2026-11-10 20:32:43 GMT, plain GET):** `https://demo-futures.kraken.com/` and
>   `https://demo-futures.kraken.com/derivatives/api/v3/tickers` both answer HTTP 301 to
>   `https://www.kraken.com/gb/features/futures` (Kraken's ordinary futures page).
> - **Verified fact (primary source, accessed 2026-11-10):** Kraken help article
>   https://support.kraken.com/articles/360024809011-api-testing-environment-derivatives, served in Dutch, "Laatst
>   bijgewerkt: 29 oktober 2026": "Onze bestaande demo-omgeving op demo-futures.kraken.com wordt op maandag 14 juli om
>   13:00 UTC buiten gebruik gesteld." No year is given; 14 July was a Monday in 2025 and a Tuesday in 2026.
> - **Stale:** the developer guide `[K13]` still says "A fully functional demo environment is available at
>   demo-futures.kraken.com".
> - **Not verified:** whether Kraken offers a replacement test environment on request. One web-search summary said so;
>   two fetches of the article and a second search did not show it.
> - `venues.json` carries the same wrong `paper_api.available: true` for Kraken Derivatives. It is pinned by FACTORY v2
>   and FORWARD-CRYPTO v1 and is deliberately NOT edited; no code reads that field.
> - OKX demo trading is described in OKX's own documentation (accessed 2026-11-10: "Login OKX —> Trade —> Demo Trading
>   —> Personal Center —> Demo Trading API", header `x-simulated-trading: 1`). It needs an OKX login and was not probed.

**Question answered.** Where can an individual retail resident of the Netherlands (EU/EEA, ESMA retail client,
€500–€10,000) trade through an API in late 2026, and what does a small ticket really cost there?

## 0. How to read this file

**Labels** (AGENTS.md evidence discipline):

| Tag | Meaning |
|---|---|
| **V** — verified fact | Read on 2026-11-10 on the venue's own page, legal PDF or public API, or on a regulator's own page/file. |
| **M** — measured | One public order-book or funding observation taken on 2026-11-10. A point-in-time print, not a typical value. |
| **D** — derived | Arithmetic on V or M inputs; the inputs are shown. |
| **C** — claim | Third party, search-engine extract, marketing "from" figure, or a page read only through a summarising fetcher. |
| **U** — unknown | Looked for, not verified. Never filled in with a guess. |
| ⟨JS-render⟩ | Read by a sub-analyst through a headless browser on a JavaScript-only public page (see limits below). Lower grade. |

**"NL-eligible"** means: the venue's own page or a regulator's register says Dutch residents are served. It does
not mean an onboarding was completed. Every "yes" below still has to survive a real application.

**Who verified what.** I verified Kraken, Interactive Brokers, OANDA, Trading 212, Saxo, IG, Bitvavo, Deribit,
One Trading, Hyperliquid and the benchmark rates myself (sources `[K..]`, `[IB..]` etc. in §5.1). Four sub-analysts
covered the rest and recorded a verbatim quote and URL for every line; their source lists are in §5.2–§5.5 and
are cited as `[A]` prop firms + prediction markets, `[B]` secondary FX/CFD brokers, `[C]` stock brokers + DEX
perps, `[D]` other crypto exchanges. I did not re-fetch their pages.

**Limits of this pass.**

- Pages that refused automated access were recorded as unreachable, not worked around: trading212.com main site
  (HTTP 403), Bitstamp's fee page (script challenge), bybit.eu, revolut.com (403), theocc.com (403),
  cmegroup.com (timeout), Kalshi's current member agreement (429), Apex Trader Funding (403), FXCM, AvaTrade,
  FxPro (403). Interactive Brokers' knowledge base and Hyperliquid's Terms are JavaScript apps that a plain
  client cannot read.
- interactivebrokers.ie returned HTTP 403 to the summarising fetcher but answered a plain HTTP client that
  identified itself as `research-fetch/1.0` (no browser headers). All IBKR pages were read that way.
- One sub-analyst rendered 17 JavaScript-only public pages in a headless browser (honest user-agent, fresh
  profile, no login) before I stopped it. None of those pages had refused a plain client. The facts that depend
  on them are tagged ⟨JS-render⟩: tastytrade and Tradier accepting Dutch residents, Robinhood's crypto API being
  US-only, Freedom24 API details, and the GMX terms.
- Spreads marked M are single snapshots between 13:50 and 14:40 UTC on a Tuesday. They say what the book looked
  like then, not what a fill will cost on a bad day.
- Tax (Dutch box 3 and the treatment of derivatives or prop-firm "rewards") was not researched.

## Headline findings

1. **Kraken spot FX is 20 bp per side, not 1 bp.** The EUR/USD book is tight (0.18 bp wide, M) but the fee for
   fiat FX and stablecoin pairs is 0.20% maker and taker below $50k of 30-day volume (V). Only 12 fiat pairs
   exist: no NZD, SEK or NOK, and USD/JPY was 235 bp wide (M). FX pairs carry no margin, Kraken's EEA terms
   close margin to consumers, and fiat balances "will not earn interest" (V) — so no short without holding
   the other currency, and no carry.
2. **Interactive Brokers charges 0.2 bp on FX with a USD 2.00 minimum per order (V).** That is 59.6 bp per side
   on €300, 17.9 bp on €1,000, 3.6 bp on €5,000; the 0.2 bp rate is reached at USD 100,000 (D). For an EEA
   retail client leverage runs through Forex CFDs, whose financing is the pair benchmark ∓ 2.0%/yr (1% tier
   spread + 1% retail add-on, V). Cash earns 0% below €10,000 (V).
3. **A 0.3–0.6 bp per side FX cost does exist** — at CFD brokers reachable through the cTrader Open API
   (Pepperstone, IC Markets, FP Markets; broker-published average spreads, V as published) — with a 0.01-lot
   (≈ €1,000) minimum and a swap mark-up of roughly 0.6–1.1%/yr (D). CME micro FX futures at IBKR cost USD 0.40
   per contract per side (0.29 bp on M6E, V+D) with carry priced inside the future, but one contract is
   €6,200–€13,600 of notional.
4. **Position granularity, not fees, blocks the FX lane at small size.** The pre-registered sizing puts about
   €139 / €694 / €1,389 on each of nine FX legs at €1k / €5k / €10k equity (D, illustrative 8% pair
   volatility). Micro futures need roughly €45k–€90k of equity for one contract to equal one leg; 0.01-lot
   CFDs need roughly €7k–€10k before rounding error falls under ±50%.
5. **OANDA's v20 REST API is not available to EU clients** (V): "available to all divisions except OANDA
   Global Markets and OANDA TMS BROKERS S.A.", and OANDA TMS is the entity that serves the EU.
6. **US-domiciled ETFs cannot be bought (PRIIPs, V); IBKR sells CFDs on them** at USD 0.005 per share, USD 1.00
   minimum, financing benchmark ± 2.5%/yr for retail (V). **Trading 212 Invest has an official API** with
   commission-free UCITS ETFs and stocks, fractional quantities and a demo environment (V) — long-only, no
   market-data endpoint, quantity orders only.
7. **EU-regulated crypto "perps" are open to retail at up to 10×** on Kraken Derivatives (CySEC entity), OKX
   X-Perps, Coinbase's Cyprus futures entity, Backpack EU, One Trading and Bitstamp, at about 2 bp maker / 5 bp
   taker (V). ESMA said on 24 February 2026 that such products "are likely to fall within the scope of the
   existing national product intervention measures on CFDs" (V), whose crypto cap is 2:1. Treat leverage and
   availability as revocable.
8. **Funding is the real holding cost of a perp.** Measured over the last 365 days, a BTC long paid 3.7%/yr on
   Kraken and 5.8%/yr on Hyperliquid (M). Kraken's commodity, index and tokenized-stock perps had funding too
   erratic to hold (gold +17%/yr, US100 +65%/yr since listing, M).
9. **The cheapest EUR/USD-like spot route found is OKX's USDC-EUR pair**: fee group "Spot zero" (0% / 0%, V
   for the group, U for the charge on a retail account) and €5,000 crossed for 0.3–0.6 bp (M). Bitvavo's
   USDC-EUR costs 10 bp per side (V).
10. **Prediction markets are closed to a Dutch resident** (Polymarket's Terms name the Netherlands; the Dutch
    gambling regulator's order was upheld on 23 June 2026, V per `[A]`). **Prop-firm "funded" accounts are
    simulated** and carry consistency rules that punish lumpy systematic returns; the AFM has classed one
    funded-trading business as unlicensed investment services (V per `[A]`).

---

## 1. Master table

Columns: platform · assets · NL-eligible? · entity / licence · API + Python library · paper/demo API? · lowest-tier
fees incl. minimums · financing · EU-retail leverage · minimum size · bots allowed? · status.

**Status labels.** `USABLE` = NL-eligible on paper, official API, fees verified. `USABLE*` = usable with one
named open point. `NO-API` = account possible, no programmatic route (or contractually banned). `CLOSED` = not
available to Dutch retail. `UNVERIFIED` = a key fact is unknown. `AVOID` = material custody or legal problem.

### 1A. Crypto — centralised venues

| Platform | Assets | NL? | Entity / licence | API + Python lib | Paper/demo API? | Lowest-tier fees incl. minimums | Financing | EU-retail leverage | Min size | Bots? | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Kraken Pro (spot)** | Crypto spot; 12 fiat FX pairs (no NZD/SEK/NOK); stable pairs (no USDT pairs for NL); 177 xStocks (tokenized US stocks/ETFs, USD-quoted) | Yes (V): ESMA register, NL passport; API returns 1,266 of 1,431 pairs for NL | Payward Europe Solutions Ltd (Central Bank of Ireland, MiCA 25/06/2025); xStocks via Payward Europe Digital Solutions (CY) Ltd (CySEC 342/17) | REST, WebSocket, FIX; `python-kraken-sdk` 3.5.1 (community), ccxt | None found (U) | Spot 0.40% maker / 0.80% taker ($0+); 0.30/0.60 from $2.5k 30-day; 0.22/0.38 from $10k. FX and stable pairs 0.20% both sides (0.16% from $50k). xStocks 0% / 0.08%. No minimum fee (V) | None on spot; fiat "will not earn interest" (V), so no carry. Margin 0.01–0.04% to open plus the same every 4 h (V) | 1× — "Consumers are not eligible to receive Margin Extensions" (V) | EUR/USD 4 EUR; BTC 0.00006 (V) | Yes — API Trading is a product | `USABLE`, expensive. xStocks via API for EEA disputed (U). `[K1–K3, K8, K9, R4]` |
| **Kraken Derivatives (EEA)** | Crypto perps and dated futures; perps on gold, silver, WTI, Brent, gas, copper, US100, xStocks, a few equities. FX perps are not on the EEA platform (V) | Unknown by name (U): EEA retail needs full verification, a questionnaire and a tax ID; country list not published | Payward Europe Digital Solutions (CY) Ltd, CySEC 342/17 | REST v3, WebSocket, FIX; `python-kraken-sdk`; ccxt `krakenfutures` | **Yes** (V): demo-futures.kraken.com, no existing account, API keys | 0.02% maker / 0.05% taker, no minimum (V). Kraken *app* perps: 0.25% each way | Hourly funding. 365-day mean (M): BTC +3.7%/yr, ETH +3.8%, SOL +0.7% (long pays). Gold +17%, US100 +65% since listing; SPYx −25% overall, +18% last 90 d | 10× (10% initial margin, tier I) (V) | 0.0001 BTC ≈ $7 (V) | Yes | `USABLE*` — confirm NL in-account; ESMA perps statement. `[K1, K4–K7, K10, K11, K13]` |
| **Bitvavo** | Crypto spot in EUR and USDC; USDC-EUR; margin terms on the fee page | Yes (V) — Dutch entity | Bitvavo B.V., AFM MiCA 26/06/2025 | REST, WebSocket; `python-bitvavo-api` 1.4.3 (official), ccxt; 1,000 weight/min | None mentioned (U) | 0.15% / 0.25% on EUR markets; 0.05/0.05 on USDC-quoted markets; USDC-EUR 0.10/0.10; EURC-EUR 0/0.01. SEPA and iDEAL free (V) | Margin borrow 0.0023%/h ≈ 20%/yr, 2% liquidation fee (V) | Spot 1×; margin eligibility U | €5 (V) | API offered | `USABLE` for spot. `[BV1–BV4, R4]` |
| **OKX Europe** | Spot; spot margin 10× long and short; X-Perps (5-year-expiry perp-style: 167 crypto, 89 equity/ETF, gold, silver, WTI, Brent; no FX) | Yes for spot (V); X-Perps "all 30" EEA countries supported, activation may lag (V) | OKX Europe Ltd (MFSA, MiCA 27/01/2025); OKX Europe Markets Ltd (MFSA investment services) | REST and WebSocket on `eea.okx.com`; `python-okx` (official); ccxt `myokx` | **Yes** (V): demo trading with header `x-simulated-trading: 1` | Spot 0.10/0.20 (spot-only) or 0.08/0.10 (with an X-Perps account); zero-fee pairs 0/0 — USDC-EUR is in fee group "Spot zero" (V), charge on a retail account U; X-Perps 0.02/0.05 (V) | Funding every 8 h, capped ±0.375% per period (V) | 10×; negative balance protection stated; margin call at 30% (V) | 1 USDC; BTC X-Perp 0.0001 BTC per API, 0.01 per help page (conflict) | Bots marketed; terms unread | `USABLE*` — appropriateness test; confirm fee group and contract size. `[D]` |
| **Coinbase** (Advanced + EU futures) | Spot; "perpetual-style" futures (5-year expiry, hourly funding); index and commodity futures | Yes (V) — futures "in 26 European countries, including … Netherlands" | Coinbase Luxembourg S.A. (CSSF, MiCA); Coinbase Financial Services Europe Ltd (CySEC 374/19) | Advanced Trade REST and WebSocket; official Python SDK; API for the EU futures U | No — static mock sandbox (V) | Spot 0.25/0.50 under $10k, 0.20/0.40 from $10k; stable-pair schedule exists, numbers U. Futures 0.02% + $0.12 per contract per side ≈ 3.6 bp on a nano BTC contract (V+D) | Hourly funding (V) | 10× on BTC, ETH, equity indices; 4–5× others; no spot margin (V) | 1 contract: 0.01 BTC ≈ €660 | U | `USABLE*` spot; futures-by-API `UNVERIFIED`. `[D]` |
| **Bitstamp by Robinhood** | Spot incl. real EUR/USD and GBP/USD pairs; 20 perps incl. gold, oil, QQQ and an EUR/USD perp | Spot yes (V); perps for "eligible EU traders", NL not named; FX perp launch described as institutional | Bitstamp Europe S.A. (CSSF, MiCA); Bitstamp Financial Services Ltd (Slovenian ATVP, MiFID) | HTTP v2, WebSocket, FIX; ccxt; 400 req/s | Sandbox host answers; key issuance U | **U** — fee page blocks automated clients; third-party figures conflict | Funding every 8 h | 10× (5× commodities) (V) | Order value 10 USD/EUR | U | `UNVERIFIED` fees. `[D]` |
| **Bybit EU** | Spot (129 pairs); spot margin on 37 USDC pairs; no derivatives (EU API returns empty lists, V) | Yes (V) | Bybit EU GmbH (Austrian FMA, MiCA 28/05/2025) | REST v5 on `api.bybit.eu`, but docs say the EU API "only support 'Connect to Third-Party Applications' feature for API broker user" (V) | No EU testnet listed | 0.25% unified (C) | Hourly borrow rates via API | Spot margin 10× (C) | 1 EUR | Personal API keys unclear | `UNVERIFIED` — API restriction. `[D]` |
| **Backpack EU** | Perps, USDC-settled | Yes (V) — NL in its served-country list | Trek Labs Europe Ltd (CySEC 273/15); MiCA entity in Latvia | REST and WebSocket, `api.eu.backpack.exchange` | U | 0.02% / 0.05% (V) | Hourly funding | "up to 10×" | 0.00001 BTC | API keys offered | `USABLE*` — USDC only, EUR funding route U. `[D]` |
| **One Trading** | Crypto futures (5-year, funding every 4 h; 10 coins vs USD), equity-index and stock futures (ONEX100, SPCX), spot BTC/ETH-USDC, USDC-EUR | Yes (V) — Dutch entity serving "institutions and retail investors" | One Trading Exchange B.V., AFM investment firm operating an organised trading facility; MiCA 15/05/2025 | REST `api.onetrading.com/fast/v1`; no official Python SDK found | U | Screen trading 0.10/0.20 under $10k 30-day, 0.04/0.08 above. "API Trading: −0.005% / 0.015%, all volumes" — who qualifies is not stated. Liquidation 3%. Custody fee 0.17%/month of balance after 90 idle days (V) | Funding every 4 h; snapshot ≈ 3.9%/yr (M) | Up to 10× | Size 10 in quote currency | API schedule published | `USABLE*` — thin (BTC $8M/day, M); API-fee eligibility U. `[OT1–OT4]` |
| **Deribit** | Options, perps, futures; USDC perps on SPY, QQQ, gold, silver, oil, EURC | **U** — NL/EEA absent from the restricted list (edited 2026-10-06); UK retail barred | Not established for EU clients | REST, WebSocket, FIX; testnet answers | Yes — `test.deribit.com` | API fields: maker 0.015% / taker 0.035% on perps (V as API output) | Funding | Venue limit 50× on BTC | 0.0001 BTC | Yes | `UNVERIFIED` access. `[DB1, DB2]` |
| **Revolut X** | Spot only | Yes (V) | Revolut Digital Assets (Europe) Ltd (CySEC, MiCA 20/10/2025) | REST for retail accounts; ccxt `revolutx` | U | 0% / 0.09% (C) | — | 1× | 0.1 quote | Yes | `UNVERIFIED` fees; USDC/EUR book 15.6 bp wide (M). `[D]` |
| **Bitpanda (Fusion)** | Broker-style spot; long-only margin | Yes (V) | Bitpanda GmbH (Austrian FMA, MiCA) | Fusion API "to selected customers" (C) | U | 0.25% single rate (V) | Margin 0.18%/day for 60 days (V) | Up to 10×, long only | — | Limited | Low priority. `[D]` |
| **Gemini, Binance, Bitget, Bitfinex, BitMEX, MEXC** | — | **No** — Gemini closed all EEA accounts on 6 April 2026 (V); the others are absent from ESMA's MiCA register of 5 Nov 2026 (V) | — | — | — | — | — | — | — | — | `CLOSED`. `[D]` |

KuCoin EU and Gate are in the register with a Dutch passport and show spot only; not researched further `[D]`.
Crypto.com's EEA derivatives offering is unknown `[D]`.

### 1B. Crypto — on-chain perps

No venue in this table claims a MiFID II authorisation. "Open by the terms" only means the Netherlands is absent
from the venue's own exclusion list.

| Platform | Assets | NL? | Entity / licence | API + Python lib | Paper/demo API? | Lowest-tier fees incl. minimums | Financing | Leverage | Min size | Bots? | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Hyperliquid** | 235 crypto perps; builder-deployed "xyz" perps: S&P 500, Nasdaq-100, gold, silver, oil, EUR, JPY, GBP, TLT, ~100 stocks; spot | **U** — no KYC step in the docs; Terms unreadable by a plain client; US/Ontario exclusion is a C | None serving the EU | REST and WebSocket; `hyperliquid-python-sdk` 0.24.0 (official); 1,200 weight/min | Testnet — faucet needs an address that has deposited on mainnet (V) | Perps 0.015% maker / 0.045% taker (V). xyz index and FX perps in growth mode ≈ 0.003% / 0.009% (D from the docs formula). xyz:GOLD not in growth mode ≈ 0.03% / 0.09% (D) | Hourly funding with a fixed 0.01%/8 h interest leg. 365-day mean (M): BTC +5.8%/yr, ETH +6.4%, Nasdaq-100 perp +3.2%; S&P 500 perp −0.8% since March 2026; gold +8.4%; EUR +3.1% | Venue limits 40× BTC, 50× S&P 500 — far above EU retail caps | USD 10 order (C) | API-first | `UNVERIFIED` legality; cheapest index perp found (S&P 500: $403M/day, 0.27 bp wide, M). `[HL1–HL8]` |
| **dYdX v4** | 57 active perps; every FX and commodity perp is in final settlement (V) | Open by the terms (US, Canada, UK excluded) | — | Indexer REST; `dydx-v4-client` 1.1.6; testnet answers | Yes | 0.01% maker / 0.05% taker (V) | Hourly funding (inferred) | 50× BTC/ETH | 0.0001 BTC | Yes | Thin — about $33M/day in total. `[C]` |
| **GMX v2** | Crypto perps; gold, silver, oil, gas, SPY, QQQ | Open by the terms ⟨JS-render⟩ | — | TypeScript SDK; community Python SDK stale | U | 0.04–0.06% per side; 0.01–0.02% on SPY, QQQ, gold in market hours; plus borrow, funding, price impact (V) | Borrow + adaptive funding | Up to 100× | U | Yes | Secondary. `[C]` |
| **Jupiter Perps** | SOL, ETH, wBTC and a few beta markets | Open by the terms | — | Perps API "work in progress"; official CLI | U | 0.06% + price impact (V) | Hourly borrow fee on the full position | 250× | $10 collateral | CLI | Secondary. `[C]` |
| **Drift → Velocity** | Perps only since relaunch | U — Terms unreadable | — | `driftpy` predates the relaunch | U | 0.06% taker (V) | — | — | — | — | `AVOID` — $295M loss on 1 April 2026; recovery pool ≈ 1% funded (V). `[C]` |
| **Ostium** | FX, index, commodity, stock perps | **No** — Terms exclude "the European Union" (V) | — | — | — | 3–10 bp open | Rollover | 200× FX | — | — | `CLOSED`. `[C]` |
| **gTrade, Veranta (ex-Avantis), Lighter, Aster** | FX / index / commodity / crypto perps | Open by the terms; gTrade applies per-asset regional blocks, NL status U | — | Lighter `lighter-sdk` 1.1.8; Veranta SDK; others U | Lighter and gTrade testnets | gTrade FX 0.012% each way; Lighter 0% with a 300 ms taker delay; Aster 0% / 0.04% (RWA 0 / 0.0125%); Veranta "zero commission" on RWA in growth mode (V) | Varies | Up to 100×+ | U | Yes | `UNVERIFIED` — markets, collateral and minimums not read. `[C]` |

### 1C. FX and CFDs

EU retail CFD rules apply to every row (AFM decision of 18 April 2019, V `[B]`): 30:1 major FX, 20:1 other FX /
gold / major indices, 10:1 other commodities and indices (the AEX falls here), 5:1 shares, 2:1 crypto; close-out
at 50% of required margin; negative balance protection.

| Platform | Assets | NL? | Entity / licence | API + Python lib | Paper/demo API? | Lowest-tier fees incl. minimums | Financing | EU-retail leverage | Min size | Bots? | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Interactive Brokers** | Spot FX conversions; CFDs on FX (85 pairs incl. NZD, SEK, NOK, MXN, ZAR; no KRW, INR, BRL, THB, TWD), indices, shares, US ETFs, gold, silver, oil | Yes (V) — "IBIE serving all EU and EEA residents" | Interactive Brokers Ireland Ltd, Central Bank of Ireland C423427 | TWS API (open source, Python), Web API (REST + WebSocket), FIX for institutions; `ib_async` 2.1.0 | Paper account / free trial with delayed data (V); API on paper is standard but not re-read today (C) | FX spot and FX CFD 0.20 bp, **minimum USD 2.00 per order**. Index CFD 0.005% (US 500, Germany 40) or 0.010% (US Tech 100, Euro 50, Netherlands 25), minimum USD/EUR 1.00. US share and ETF CFDs USD 0.005/share, minimum USD 1.00. EU share CFDs 0.05%, minimum €3. Gold CFD 1.5 bp, minimum USD 2 (V) | FX CFD: pair benchmark ∓ 1% ∓ 1% retail = **2.0%/yr against you, long or short**. Index and share CFDs: benchmark ± 1.5% ± 1% retail = **± 2.5%** (USD long 6.38%, short receives 1.38%). Oil CFDs: none. Cash: 0% on the first €10,000 / $10,000; margin loan benchmark + 1.5% (V) | CFD caps above; leveraged *spot* FX for EEA retail U (C: only via Forex CFDs) | Index CFD 1 unit × index (US 500 ≈ $7,500; Germany 40 ≈ €26,600). FX and share-CFD minimum U; FX below USD 25,000 trades as an odd lot (C) | Yes | `USABLE` — minimum fees and financing mark-ups dominate small tickets. `[IB1–IB12, IB25, IB26]` |
| **OANDA** | CFDs, shares, ETFs | Yes | OANDA TMS Brokers S.A. (Polish KNF) (V) | **No API for EU clients** (V): v20 account "available to all divisions except OANDA Global Markets and OANDA TMS BROKERS S.A."; platforms are MT5, mobile, TradingView. `oandapyV20` 0.7.2 exists for other divisions | v20 practice host exists (`api-fxpractice.oanda.com`); whether a Dutch resident can get a practice token U | U (instrument pages render no numbers) | U | CFD caps | U | MT5 expert advisors only | `NO-API`. `[OA1–OA3]` |
| **Saxo** | FX (rolling spot, classed as CFD), CFDs, futures, options, stocks, ETFs | Yes (V) — Dutch branch | Saxo Bank A/S, Saxo Nederland branch (KvK 34357130) | OpenAPI REST + streaming; simulation `gateway.saxobank.com/sim/openapi`; live needs an application key and "required permission and testing"; 120 req/min, 1 order/s (V). `saxo-openapi` 0.6.0 is from 2019 | Simulation yes (24-hour token) | Bronze: Euronext stocks/ETFs 0.08% min €2; US 0.08% min $1; futures €3 / $3 per contract incl. micros, plus exchange fees; EUR/USD from 0.7 pip; FX conversion 0.25%; service fee 0.01%/month of portfolio, max €40, returned as trading credit (V) | FX: tom/next ± 0.65% and financing of unrealised P&L benchmark ± 2.00%. Cash 0% (Bronze). Debit ESTR + 4% (V) | CFD caps | U | Via OpenAPI after approval | `USABLE*` — live API approval for an individual U; costly at small size. `[SX1–SX5]` |
| **IG** | CFDs on FX, indices, commodities, shares, crypto | Yes (V) — AFM-registered Dutch branch | IG Europe GmbH (BaFin, Bundesbank 148759) | REST + streaming; `trading-ig` 0.0.25 (community) | **Yes** — `demo-api.ig.com` (V) | No commission on FX/index CFDs. Spread per side per IG's cost document: EUR/USD 0.41 bp, USD/JPY 0.34, Germany 40 1.93, gold 0.74, bitcoin 12.2 (D; document dated January 2024) | FX ≈ tom/next ± 0.95%/yr; indices benchmark ± 2.5% (D, same document) | CFD caps | U | API free within quotas | `USABLE*` — minimum sizes and current spreads U; history capped at 10,000 points/week. `[IG1–IG3]` |
| **Capital.com** | CFDs on FX, indices, commodities, shares, crypto; real stocks | Yes (V) — Dutch site, CySEC register | Capital Com SV Investments Ltd (CySEC 319/17) | REST + WebSocket; 10 req/s; candles with bid and ask, 1,000 per call; no Python SDK (V) | **Yes** — demo API, no expiry (V) | No commission; EUR/USD 0.6 pip in the page's example (C — not an average). **0.7% currency conversion on P&L booked in a non-account currency** (V) | FX tom/next ± 1.5%/yr; indices benchmark ± 4%/yr; unleveraged positions mostly free (V) | CFD caps | U (fractional contracts in examples) | Yes | `USABLE*` — typical spreads U. `[B]` |
| **Pepperstone EU** | CFDs on FX, indices, commodities, shares, ETFs, crypto; forward CFDs | Yes (V) — CySEC cross-border list | Pepperstone EU Ltd (CySEC 388/20) | cTrader Open API (50 req/s; app must be approved by Spotware); `ctrader-open-api` 0.9.2 — official, last released June 2024; MT4/MT5 | Yes — cTrader demo via Open API; expires after 90 idle days | Razor on cTrader: $3.00 per lot per side (0.27 bp) + 0.1 pip average on EUR/USD → **0.63 bp round trip** (D). Standard: 1.1 pip, no commission. US 500 0.4 pt, Germany 40 1.0 pt, no commission (V as published averages for August 2026) | FX: providers' tom/next plus a funding fee (annual size U). Indices: reference rate ± 2.5%. **Forward CFDs: no overnight funding** (V) | CFD caps | 0.01 lot = 1,000 base units; commission rounds up to $0.04 per 0.01 lot (V) | Yes; latency-abuse clause | `USABLE*` — best verified FX trading cost; Linux via Open API. `[B]` |
| **IC Markets EU** | CFDs | Yes (V) | IC Markets (EU) Ltd (CySEC 362/18) | cTrader Open API; MT4/MT5 | Demo; expiry U | Raw cTrader: $3 per $100k + 0.06 pip average → 0.65 bp round trip EUR/USD (D); US 500 0.36 pt; Germany 40 1.46 pt (V) | Swap points; EUR/USD mark-up ≈ 1.1%/yr (D); index swaps ≈ 5%/yr if quoted in index points (unit assumed) | CFD caps | 0.01 lot | "no restrictions on trading" | `USABLE*`. `[B]` |
| **FP Markets EU** | CFDs | Yes (V) | First Prudential Markets Ltd (CySEC 371/18) | cTrader Open API; MT4/MT5 | Demo; expiry U | Raw: $3 per lot per side + 0.16 pip → 0.68 bp round trip EUR/USD (D); US 500 0.25 pt; Germany 40 1.54 pt (V) | Swap points; EUR/USD mark-up ≈ 0.6%/yr (D) | CFD caps | 0.01 lot | EAs "Yes" | `USABLE*`. `[B]` |
| **Dukascopy Europe** | CFDs; FX | Yes via the Latvian entity (V); the Swiss bank (1:200) U | Dukascopy Europe IBS AS | JForex API (Java), FIX for professionals | 14-day demo | $35 per $1M per side under $5,000 equity (0.35 bp) + spread from 0.1 pip → ≥ 0.79 bp round trip (D) | Central-bank rates plus own carry cost, worse the more is held overnight | 1:30 | U | Yes | `USABLE*` — Java only; €50 per idle half-year. `[B]` |
| **Darwinex** | CFDs; futures and stocks through an IBKR link | Probably (V: only Spanish retail excluded) | Sapiens Markets EU SV SA (CNMV 311) | MT4/MT5, FIX 4.4 with Python modules | U | U — pricing pages render client-side | U | CFD caps | U | Yes | `UNVERIFIED`. `[B]` |
| **eToro** | Stocks, CFDs, crypto | Yes (V) | eToro (Europe) Ltd (CySEC 109/10) | **Public REST API exists** with demo and real keys; 60 GET/min, ~20 trade requests/min; candles bid or ask (V) | Yes — demo keys | CFD spreads U; $1–2 per stock order; $5 USD withdrawal | U | CFD caps | U | Yes | `UNVERIFIED` costs. `[B]` |
| **FXCM EU** | CFDs | New accounts go to AvaTrade (C — read through a summariser) | Stratos Europe Ltd (CySEC 392/20) | — | — | — | — | — | — | — | `CLOSED` to new clients. `[B]` |
| **XTB** | CFDs, stocks | Yes | XTB Ltd (CySEC 169/12) | **None** — "API access is no longer available. The service was discontinued on March 14, 2025." (V) | — | — | — | — | — | No | `NO-API`. `[B]` |
| **CMC Markets** | CFDs | U | CMC Markets Germany GmbH (BaFin 154814) | API is institutional; retail route is MT4 | — | "from" figures only | U | CFD caps | U | MT4 EAs | `NO-API` for retail. `[B]` |
| **Plus500** | CFDs | Yes | Plus500CY Ltd (CySEC 250/14) | **Prohibited** — "All Transactions must be completed manually by you." (V) | — | — | — | — | — | No | `NO-API`. `[B]` |
| **Trading 212 CFD** | CFDs | Yes | Trading 212 Markets Ltd / EU GmbH | Not covered by the public API (V) | — | — | — | — | — | — | `NO-API`. `[T1]` |

MetaTrader-only brokers (Tickmill and others): the official `MetaTrader5` Python package ships Windows wheels
only (V `[PY]`), so a Linux bot needs Wine, a Windows server or a paid bridge.

### 1D. Stocks, ETFs, options, futures

| Platform | Assets | NL? | Entity / licence | API + Python lib | Paper/demo API? | Lowest-tier fees incl. minimums | Financing | Leverage | Min size | Bots? | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Trading 212 Invest** | Stocks, UCITS ETFs, ETCs | Yes (V) | Trading 212 EU GmbH (BaFin) | **Official REST API (beta)**: account, instrument metadata, orders (market, limit, stop, stop-limit on live), positions, history. **No quotes or candles.** Quantity orders only; primary account currency only. No official Python SDK (V) | **Yes** — `demo.trading212.com/api/v0` (V) | Commission 0, custody 0; FX fee 0.15% when the instrument's currency differs (V) | None (cash account). Interest on idle cash with no minimum balance; rate U | 1× | Fractional; minimum order value U | Yes, via the API | `USABLE` — best small-ticket wrapper for long-only UCITS books. `[T1–T7]` |
| **Interactive Brokers** | EU stocks and UCITS ETFs; US options; futures incl. CME micros; crypto via zerohash europe B.V. | Yes (V) | IBIE | as in 1C | as in 1C | EU stocks/ETFs tiered 0.05%, **minimum €1.25**, maximum €29, plus third-party fees; fixed 0.05%, minimum €3. US options $0.65/contract, minimum $1. Futures: micros $0.25 + exchange $0.35 (equity) → **$0.61 per side**; micro FX $0.15 + $0.24 → **$0.40**; MGC $0.96; MCL $0.86; MBT $2.01; Micro DAX €0.38. Crypto 0.18%, minimum $1.75 (V) | Futures: none (carry in the price); overnight position fee $0.10/contract/day only when equity is near the margin requirement (V) | Futures margin, e.g. MES $2,756, M6E $544, MGC $2,714 overnight (V, 2026-11-10) | Futures 1 contract: MES ≈ €33,500; M6E €12,500; M6B ≈ €7,500; M6A ≈ €6,200; MGC ≈ €36,200; MCL ≈ €7,500; MBT ≈ €6,600 (D) | Yes | `USABLE` — contract size is the constraint. KIDs for specific US futures/options to be checked in-account (U). `[IB13–IB24]` |
| **Lynx / Mexem / CapTrader** (IBKR introducing brokers) | As IBKR | Lynx yes (V); Mexem probably; CapTrader U | Carrying broker IBIE; Mexem Ltd (CySEC 325/17) | Same TWS / Web API stack (V) | U | Lynx: EU shares 0.06%, **minimum €6**; US $0.01/share, minimum $5; micro futures $1.25; **€5/month minimum activity fee** under €100k. Mexem: 0.06%, minimum €1; FX conversion 0.05%, minimum €5 (V) | As IBKR | As IBKR | As IBKR | Yes | Lynx is dearer than IBKR direct for a small account. `[C]` |
| **DEGIRO** | Stocks, ETFs, options, futures | Yes | flatexDEGIRO Bank Dutch Branch | **Banned by contract** — "The Client is not allowed to use the services of DEGIRO for algorithmic trading." (V) | — | Core-selection ETFs €0 + €1 handling; other €2 + €1; FX 0.25% (V) | — | — | — | No | `NO-API` — manual fallback only. `[C]` |
| **Scalable Capital** | Stocks, ETFs | Yes (V) | Scalable Capital Bank GmbH (BaFin) | Official CLI and MCP server, **but every order needs a separate human confirmation** and login lapses within 7 days (V) | U | €0 for PRIME ETFs from €250, otherwise €0.99 (V) | — | — | — | Not autonomous | `NO-API` for unattended trading. `[C]` |
| **Alpaca** | US stocks, ETFs, options, crypto | **U** — no country list; "ask support" (V) | Alpaca Securities LLC (US, SIPC); Alpaca Europe is B2B | REST, WebSocket, FIX; `alpaca-py` 0.45.0 (official) | **Yes for anyone** — paper-only account with IEX data (V) | $0 commission; **1.5% conversion each way on EUR funding**, max $40 (V) | Margin and shorting need $2,000 equity | US rules | Fractional | Yes | `UNVERIFIED` live access; whether an EU resident may buy US ETFs there U. Useful as free paper + data. `[C]` |
| **tastytrade** | US stocks, ETFs, options, futures | Yes ⟨JS-render⟩ | tastytrade, Inc. (US) | Open API, sandbox `api.cert.tastyworks.com`; unofficial `tastytrade` 13.2.3 | Sandbox (V) | Options $1/contract to open; micro futures $0.75; no currency conversion service; $45 outgoing wire | 6.75% margin | US rules | — | Yes | `UNVERIFIED` — eligibility read via render; USD-only. `[C]` |
| **Tradier** | US stocks, ETFs, options | Yes ⟨JS-render⟩ | Tradier Brokerage Inc. (US) | REST + streaming; sandbox needs a live account | Sandbox | $0.35 per trade on the free plan; $50/year inactivity fee (V) | — | US rules | — | Yes | `UNVERIFIED`. `[C]` |
| **Freedom24** | Stocks, ETFs, options | Probably (CySEC passport; NL acceptance not captured) | Freedom Finance Europe Ltd (CySEC 275/15) | Tradernet REST + WebSocket; `tradernet-sdk` 2.2.0 (official); API keys for bots ⟨JS-render⟩ | U | Smart plan €2 + €0.02 per share per order; US options $0.65/contract (V) | U | U | — | Yes | `USABLE*` — €2 minimum per order. `[C]` |
| **Trade Republic, Lightyear, BUX, Robinhood EU** | Stocks, ETFs; Robinhood: stock tokens, perps | Yes (TR, Lightyear, BUX); Robinhood NL U | TR Bank GmbH NL branch; Lightyear Europe AS; BUX B.V. (AFM); Robinhood Europe UAB | None: Lightyear "We don't offer an API" (V); TR and BUX none found; Robinhood's crypto API is US-only ⟨JS-render⟩ | — | TR €1/trade (C); Lightyear ETFs free, FX 0.35% (V); BUX up to €3.99 (V) | — | — | — | No | `NO-API`. `[C]` |

**PRIIPs** (V `[C]`): a retail client may not be sold a product without a key information document, so US-domiciled
ETFs are blocked at EU brokers; DEGIRO and Lynx say so, and Lynx adds that only MiFID professional clients can
trade them. US-listed options and CME futures are sold to Dutch retail (they appear on Lynx's and DEGIRO's Dutch
price lists, V). IBKR's own KID lookup has a "Non-European ETD" category but needs a login for exchange-traded
contracts, so KID coverage of a specific contract (MES, M6E, SPY options) is U until checked in an account.

### 1E. Prediction markets

| Platform | NL? | API | Fees | Status |
|---|---|---|---|---|
| **Polymarket** | **No** — Terms name "THE NETHERLANDS"; VPN use prohibited; Dutch gambling regulator order of 20 Jan 2026 (€420,000/week, max €840,000), objection rejected 23 June 2026; the live geoblock endpoint returned `blocked: true, country: NL` (V) | CLOB API; official SDK is now `polymarket-client` | Taker fees on most categories, 2–3.5% of stake at 50¢; makers free (V) | `CLOSED`. `[A]` |
| **Kalshi** | Restricted — NL absent from the only member agreement that could be read (October 2025 copy); the Dutch regulator says bets of this kind are not permitted on the Dutch market at all, even for licence holders (V, Dutch original in `[A]`) | REST, WebSocket, FIX; demo; `kalshi-python` | Formula not read (429) | `UNVERIFIED`, legally exposed. `[A]` |
| **IBKR ForecastEx** | No for retail — "Available to MiFID professional clients only" (V) | — | $0.01 exchange fee | `CLOSED`. `[IB20]` |
| **Betfair, Limitless, others** | Betfair's API blocks Dutch IPs (V); Limitless puts the legality check on the user | — | — | `CLOSED` / `UNVERIFIED`. `[A]` |

### 1F. Prop firms (capital-scaling route)

Every firm below states that evaluation and funded accounts are simulated; the payout is a contractual reward
from the firm, not trading profit (V `[A]`). No firm publishes an audited pass rate.

| Firm | NL? | Bots / API | Cost | Rules that bite a systematic strategy | Status |
|---|---|---|---|---|---|
| **FTMO** | Yes | EAs and algos allowed on MT4, MT5, cTrader; **max 2,000 server requests/day** | 10k 2-Step €89, refunded with the first reward; 1-Step €79 not refunded | Targets 10% then 5%; 5% daily loss, 10% total; 1-Step consistency 50%, Instant 30% | Open; external Open API routing U |
| **The5ers** | Yes | Own EAs only (source code required); MT5 | 2.5k from $19 | No tick scalping, no one-sided bets | Open |
| **FundedNext** | Yes | EAs only under $50k on MT4/MT5, paid add-on; none on cTrader | 6k 2-Step $59.99 | Switching EA ↔ manual after funding banned | Open |
| **Topstep** (futures) | Yes | **REST + WebSocket API**, $29/month ($14.50 with code); bots allowed, HFT banned; **must run on a personal device — no VPS**; no API on the real-capital Live account | 50K $49/month + $149 activation | $2,000 max loss on 50K; consistency 55% (Combine), 40% (funded) | Open; only firm with a documented API |
| **Breakout** (Kraken Prop) | Yes | No bot rule, no documented API | 5k from $20 | Copied ideas banned | Open |
| **HyroTrader** (crypto) | U | Own bots via an exchange demo API key | From $9 | 40% per-day consistency, 5% per-payout cap; "no real-capital stage at any point" | `UNVERIFIED` |
| **Apex Trader Funding** | U | Reportedly bans automation (C) | U | U | `UNVERIFIED` (site returned 403) |

Regulators (V `[A]`): the AFM wrote that "Ufunded operates illegally by providing investment services" and that
1,279 Dutch investors transferred more than €20 million; an appeal was lodged on 22 June 2026. Italy's CONSOB
warned about "funded trading" in July 2024. This is a precedent for how the AFM may read the model, not a ruling
on challenge-style firms.

### 1G. Free demo APIs and what they give as a data source

| Source | Free without a funded account? | Historical data through the API | Bid/ask? |
|---|---|---|---|
| Capital.com demo API | Yes, no expiry (V `[B]`) | Candles from 1 minute to 1 week, 1,000 per call; depth U | **Bid and ask** in every candle (V) |
| IG demo API | Yes (V `[IG3]`) | 10,000 price points per week; 1 s (4 days), 1–3 min (40 days), 5 min–4 h (360 days), daily (15 years) | U |
| eToro API, demo key | Needs a verified account (V `[B]`) | Candles 1 m to 1 w, 2,000 per page, daily and weekly "up to all history" | Bid or ask, selectable (V) |
| cTrader Open API, demo | Yes with a cTrader ID and an approved app (V `[B]`) | Bars M1 to MN1; ticks; depth set by the broker (U) | Ticks: bid and ask requested separately (V) |
| Alpaca paper-only account | **Yes, "Anyone globally"** (V `[C]`) | US stocks and ETFs since 2016 from IEX; latest 15 minutes withheld; 200 calls/min | Trades and quotes, IEX only |
| OANDA v20 practice | U for a Dutch resident (`[OA2]`) | Candle endpoint exists; spec page returned 404 today | U today |
| Kraken Futures demo and public API | Yes (V `[K13]`) | Charts endpoint (depth not checked); about one year of hourly funding (M `[K6]`) | U |
| Bitstamp public API | Yes (V `[D]`) | OHLC up to 1,000 bars per call; daily EUR/USD back to 2024-02-15 | No |
| OKX public API (EEA host) | Yes (V `[D]`) | History candles for "recent years"; 1-second candles for 3 months | No |
| Hyperliquid public API | Yes (V `[HL5, HL8]`) | Hourly funding history; recent candles; older order-book snapshots on a requester-pays archive | Order-book snapshots |
| IBKR free trial | Yes (V `[IB24]`) | Delayed data, except spot FX and metals | U |
| Trading 212 demo API | Yes (V `[T1]`) | **None** | — |
| Saxo simulation | Yes (V `[SX3]`) | The environments page says simulation has no market data | — |

---

## 2. Small-account cost reality

Reference prices: EUR/USD 1.1193 (ECB reference rate of 2026-11-09), so €300 = $336, €1,000 = $1,119, €5,000 =
$5,597. Round trip = 2 × fee per side + full bid-ask spread. All figures in basis points of notional.

### 2.1 FX majors (EUR/USD)

| Venue / instrument | €300 | €1,000 | €5,000 | Basis |
|---|---|---|---|---|
| IBKR spot FX or FX CFD — commission only | 119.1 | 35.7 | 7.1 | V fee, D arithmetic. Spread not included (U; odd lots reportedly 1–2 bp outside the quote per side, C) |
| IBKR CME micro future M6E | n/a | n/a | n/a | One contract is €12,500. At one contract: 0.57 bp in fees (D) + one tick ≈ 0.9 bp (C) ≈ 1.5 bp |
| Pepperstone Razor, cTrader | n/a (min €1,000) | 0.80 | 0.63–0.80 | V published averages; D. Commission rounds up at 0.01 lot |
| IC Markets Raw / FP Markets Raw, cTrader | n/a | 0.65 / 0.68 | 0.65 / 0.68 | V published averages; D |
| Capital.com | 0.54 | 0.54 | 0.54 | C — the page's worked example; minimum size U |
| IG | 0.82 | 0.82 | 0.82 | D from a cost document dated January 2024; minimum size U |
| Saxo (Bronze) | ≥ 0.63 | ≥ 0.63 | ≥ 0.63 | V minimum spread 0.7 pip; small-ticket fee U |
| Kraken EUR/USD spot | 40.2 | 40.3 | 40.6 | V fee 20 bp per side + M spread |
| Bitvavo USDC-EUR | 21.1 | 21.1 | 21.1 | V fee 10 bp per side + M spread 1.1 bp |
| OKX USDC-EUR | 0.6 | 0.6 | 0.8 | M book; **only if** the 0% zero-fee group applies to the account (U). Worst case add 40 bp |
| Coinbase USDC-EUR | U | U | U | Stable-pair fee behind a login; spread 1.1 bp (M) |
| Hyperliquid xyz:EUR perp | 3.6 | 3.6 | 3.6 | D fee 0.9 bp per side + M spread 1.8 bp; legality U |

### 2.2 Index and commodity exposure

| Venue / instrument | €300 | €1,000 | €5,000 | Basis |
|---|---|---|---|---|
| IBKR index CFD (US 500) | n/a | n/a | n/a | Minimum one index unit ≈ €6,700; there the fee is 1.33 bp per side (D), spread U |
| IBKR CFD on a US ETF, $50 share price | 59.6 | 17.9 | 3.6 | V fee USD 1 minimum; D. Spread not included |
| IBKR CFD on SPY ($748) | n/a | 26.7 (1 share) | 3.8 (7 shares) | D; whole shares assumed (fractional CFDs U) |
| IBKR micro futures (MES, MGC) | n/a | n/a | n/a | Contracts are €33,500 and €36,200 |
| IBKR gold CFD | 119.1 | 35.7 | 7.1 | V fee USD 2 minimum; minimum size U |
| Pepperstone US 500 / Germany 40 CFD | 0.53 / 0.38 | 0.53 / 0.38 | 0.53 / 0.38 | V published averages, no commission; minimum size U |
| IG Germany 40 CFD | 3.9 | 3.9 | 3.9 | D from the dated cost document |
| Kraken SPYx tokenized ETF, taker | 16.4 | 16.4 | 16.4 | V fee 8 bp + M spread 0.4 bp. Posting passively costs 0 bp. USD-quoted: converting EUR on Kraken costs a further 20 bp each way |
| Kraken SPYx perp | 12.7 | 12.7 | 12.7 | V fee 5 bp + M spread 2.7 bp; funding erratic |
| Hyperliquid xyz:SP500 perp | 2.1 | 2.1 | 2.1 | D fee 0.9 bp + M spread 0.27 bp; legality U |
| Hyperliquid xyz:GOLD perp | 18.3 | 18.3 | 19.6 | D fee 9 bp (not in growth mode) + M spread; the ask was thin at the snapshot |
| One Trading ONEX100 future | 41.8 | 41.8 | 41.8 | V screen fee 20 bp + M spread 1.8 bp. 4.8 bp if the API schedule applies (U) |

### 2.3 UCITS ETFs (EUR-listed)

| Venue | €300 | €1,000 | €5,000 | Basis |
|---|---|---|---|---|
| Trading 212 Invest (API) | spread only | spread only | spread only | V zero commission; the exchange spread is U (no market-data endpoint) |
| IBKR tiered (API) | 83.3 | 25.0 | 10.0 | V €1.25 minimum then 0.05%; exchange fees and spread on top |
| IBKR fixed (API) | 200.0 | 60.0 | 12.0 | V €3 minimum |
| Saxo Bronze (API after approval) | 133.3 | 40.0 | 16.0 | V €2 minimum then 0.08% |
| Mexem (IBKR API) | 66.7 | 20.0 | 12.0 | V €1 minimum then 0.06% |
| Lynx (IBKR API) | 400.0 | 120.0 | 24.0 | V €6 minimum, plus €5/month activity minimum |
| DEGIRO core selection (manual) | 66.7 | 20.0 | 4.0 | V €1 handling fee |

### 2.4 Crypto perps (BTC, taker)

| Venue | €300 | €1,000 | €5,000 | Basis |
|---|---|---|---|---|
| Kraken Derivatives (EEA) | 10.1 | 10.1 | 10.1 | V 5 bp + M spread 0.14 bp. Maker: 4 bp |
| OKX X-Perps | 10.0 | 10.0 | 10.0 | V 5 bp; spread ≈ 0.01 bp (M) |
| Coinbase EU nano BTC future | n/a | 7.2 | 7.2 | V 2 bp + $0.12 per contract; one contract ≈ €660 |
| Backpack EU | 10+ | 10+ | 10+ | V 5 bp; spread U |
| One Trading BTC future | 43.4 | 43.4 | 43.4 | V screen fee + M spread 3.4 bp. 6.4 bp if the API schedule applies (U) |
| Hyperliquid | 9.1 | 9.1 | 9.1 | V 4.5 bp + M spread 0.14 bp. Maker: 3 bp |

### 2.5 Crypto spot (BTC/EUR, taker)

| Venue | €300 | €1,000 | €5,000 | Basis |
|---|---|---|---|---|
| Bitvavo | 50.2 | 50.2 | 50.2 | V 25 bp + M spread. Maker: 30 bp |
| Kraken Pro | 160.1 | 160.1 | 160.1 | V 80 bp at the entry tier; 120 bp after $2.5k of 30-day volume, 76 bp after $10k |
| Coinbase Advanced | 100.1 | 100.1 | 100.1 | V 50 bp under $10k |
| OKX Europe | 42 / 22 | 42 / 22 | 44 / 24 | V 20 bp spot-only or 10 bp with an X-Perps account; M spread 2 bp |
| IBKR via zerohash | 104.2 | 36.0 | 36.0 | V 18 bp, USD 1.75 minimum |
| Bitpanda Fusion | 50 | 50 | 50 | V 25 bp |
| Revolut X | ≈ 21 | ≈ 21 | ≈ 21 | C 9 bp taker + M spread 3 bp |

### 2.6 Annual cost of holding 1× notional

"Mark-up" is what the venue adds against you on top of the fair carry, whether long or short.

| Wrapper | Long 1× | Short 1× | Basis |
|---|---|---|---|
| IBKR FX CFD, majors | fair carry − 2.0%/yr | fair carry − 2.0%/yr | V. EUR.USD today: long pays 3.35%, short pays 0.65% (fair: long pays 1.35%, short earns 1.35%) |
| IBKR index, share and ETF CFDs | pays benchmark + 2.5% (USD 6.38%) | receives benchmark − 2.5% (USD 1.38%), less borrow on shares | V |
| IBKR futures | 0 mark-up; carry is in the price | 0 mark-up | V. Idle margin cash earns 0% below €10,000 |
| IBKR cash balances | credit 0% below €10,000 | debit benchmark + 1.5% (EUR 4.03%) | V |
| Pepperstone / Capital.com / IG index CFDs | benchmark + 2.5% / 4% / 2.5% | benchmark − the same | V / V / D |
| CFD-broker FX swaps | mark-up ≈ 0.6% (FP), 1.1% (IC), 1.5% (Capital.com), 0.95% (IG) | same | D from swap points / V formula / D |
| Pepperstone forward CFDs | 0 — carry in the forward price | 0 | V; spreads U |
| Saxo rolling FX | tom/next ± 0.65% plus benchmark ± 2% on unrealised P&L | same | V |
| Kraken spot FX, unlevered | 0, and **no carry earned** (fiat earns no interest) | not possible without holding the other currency | V |
| Kraken BTC perp | paid 3.7%/yr (365-day mean) | received 3.7%/yr | M; mean absolute rate 6.5%/yr |
| Hyperliquid BTC perp | paid 5.8%/yr | received 5.8%/yr | M; mean absolute rate 8.5%/yr |
| Hyperliquid S&P 500 / Nasdaq-100 / EUR perps | −0.8% / +3.2% / +3.1% per year | opposite | M; S&P 500 since 2026-03-18, EUR since 2025-12-23 |
| Kraken gold / US100 / SPYx perps | +17% / +65% / −25% per year | opposite | M; not holdable |
| Bitvavo / Bitpanda margin borrow | ≈ 20%/yr / ≈ 66%/yr | — | V |
| UCITS ETF at Trading 212 | fund TER only | not possible | V |

### 2.7 What this means for the three FACTORY lanes

These are arithmetic consequences of `PREREGISTRATION_v1.md` §2 sizing, `w = (σ*/σ_i)/N`, with **illustrative**
volatilities that I assumed (FX pair 8%, equity ETF 16%, bond ETF 7%, crypto 80%). They are not research results.

| Lane | Weight per leg | € per leg at €1k / €5k / €10k | Consequence |
|---|---|---|---|
| FX-D, 9 currencies | 0.139 | 139 / 694 / 1,389 | Below the €1,000 minimum of 0.01-lot CFDs until about €7k–€10k of equity; one micro future equals one leg only at about €44k (M6A) to €90k (M6E) |
| MA-ETF, 50 funds | 0.0125 (equity), 0.029 (bond) | 12–29 / 62–143 / 125–286 | A USD 1.00 or €1.25 minimum is 0.4–10% of such a ticket. Only a zero-minimum venue (Trading 212) can hold this book, and only long |
| CRYPTO-H, 40 perps | 0.006 | 6 / 31 / 62 | Fees are proportional, but €6 legs sit at or below venue minimums (≈ $7–10) |

**Financing drag** = mark-up × gross notional ÷ equity. A 9-leg FX book at these weights runs about 1.25× gross
when every leg is on (D):

| Mark-up | 0.83× gross | 1.25× gross | 2× gross | 3× gross |
|---|---|---|---|---|
| 0.6%/yr (FP Markets FX) | 0.50% | 0.75% | 1.2% | 1.8% |
| 1.0%/yr | 0.83% | 1.25% | 2.0% | 3.0% |
| 2.0%/yr (IBKR FX CFD, retail) | 1.66% | 2.5% | 4.0% | 6.0% |
| 2.5%/yr (index and ETF CFDs) | 2.07% | 3.12% | 5.0% | 7.5% |

Suggested changes to the cost model in `PREREGISTRATION_v1.md` §3 (for a v2 — v1 is frozen):

- **FX-D.** The 1.0 bp base is conservative for the trade itself at CFD brokers (0.3–0.6 bp per side on published
  averages) and about right for micro futures (≈ 0.75 bp incl. half a tick). What is missing is a holding-cost
  term: 0.6–2.0%/yr on gross notional for CFDs, zero for futures. "Kraken spot" should be dropped as the
  unlevered wrapper: 20 bp per side, six of nine currencies, no carry, no shorts.
- **MA-ETF.** The US closing-auction rail is not available to a Dutch retail account. The executable wrappers are
  IBKR CFDs on the same US ETFs (per-order minimum, ± 2.5% financing) or UCITS equivalents at Trading 212 (zero
  commission, long-only formulas only).
- **CRYPTO-H.** 7 bp base matches the verified 5 bp taker fee plus a small spread on majors (0.07–0.6 bp half-spread
  measured on BTC, ETH, SOL; alts not measured). Funding differs by venue: the Binance archive is not the funding
  a Kraken, OKX or Hyperliquid account pays.
- **All lanes.** Cost per order should be `max(rate × notional, minimum fee)`, and daily vol-target rebalancing
  needs a no-trade band, or minimum fees are paid on every small adjustment.

---

## 3. Recommended stacks

Ranked by what is verified, not by what is cheapest on paper. "Unregulated" options are listed last and only
where nothing regulated does the job.

### €1,000

| Asset class | Use | Why | Not this |
|---|---|---|---|
| UCITS ETFs and stocks, long-only | **Trading 212 Invest API** | The only verified venue where a €10–€150 ticket costs no commission; fractional; demo API to rehearse on | IBKR (€1.25 minimum = 83 bp on €300) |
| Crypto perps, long and short | **Kraken Derivatives (EEA)** first; **OKX X-Perps** second | 2 / 5 bp, no minimum fee, ≈ $7 minimum, free demo APIs, EU-licensed entities | One Trading on screen fees (43 bp); Coinbase (one contract ≈ €660) |
| Crypto spot | **Bitvavo** | Dutch entity, iDEAL, 15 / 25 bp, €5 minimum | Kraken Pro (40 / 80 bp) |
| FX | **None fits.** If EUR/USD alone is enough: OKX USDC-EUR once the zero fee is confirmed; otherwise a single 0.01-lot leg at a cTrader broker | Nine €139 legs cannot be placed anywhere with verified costs | Kraken spot FX (40 bp round trip); IBKR ($2 minimum) |
| Index, gold | Long: UCITS ETF or ETC at Trading 212. Short: a CFD at Pepperstone or Capital.com if their minimum size allows (U) | Perps on Kraken have unusable funding | IBKR index CFD (minimum ≈ €6,700) |

### €5,000

Same core, plus:

| Asset class | Use | Why |
|---|---|---|
| UCITS ETFs | Trading 212 for many small positions; **IBKR** for a few positions of €2,500 or more (5 bp, no further minimum effect) | IBKR adds real market data, short selling and one account for futures later |
| FX | **cTrader broker (Pepperstone, IC Markets or FP Markets)** with a 3–5 pair subset in 0.01-lot steps | 0.6–0.8 bp round trip; swap mark-up 0.6–1.1%/yr; €694 target legs round to €1,000 (±44%) |
| Index | Pepperstone **forward CFDs** (no overnight funding) if their spreads prove acceptable (U) | Avoids the ± 2.5%/yr CFD financing |
| Crypto | Kraken Derivatives or OKX as above | Costs do not improve with size at this level |

IBKR's FX CFDs become tolerable per trade at €5,000 tickets (3.6 bp per side) but the 2%/yr financing mark-up
does not shrink with size.

### €10,000

| Asset class | Use | Why |
|---|---|---|
| FX, 9-currency book | **cTrader broker**, 0.01-lot legs (≈ €1,389 target per leg, ±30–45% rounding) | Still the only granular wrapper. Micro FX futures at IBKR are cheap and carry-fair, but one contract is 4–9 times a leg |
| FX, single large position | **IBKR micro futures** (M6A, M6B, MCD, MJY at €6–7.5k each) | 0.3–0.6 bp fees, no financing mark-up, real exchange |
| ETFs | Trading 212 for the 50-fund long book; IBKR for concentrated positions and for CFDs on US ETFs when a short is needed (accept ± 2.5%/yr) | — |
| Index futures | Not yet: MES is €33,500, Micro DAX about €26,600 | Use ETFs or forward CFDs |
| Crypto | As above; consider maker orders (2 bp) once volume justifies the engineering | — |

Cash interest is 0% at IBKR below €10,000 and 0% at Saxo Bronze (V). Idle collateral only earns something at
Trading 212 (rate U) or inside a money-market ETF.

**Hyperliquid** would be the cheapest wrapper found for index, EUR and crypto perps in one account (0.9–4.5 bp
taker, deep S&P 500 and Nasdaq books). It is not recommended until the owner has settled §4 question 10: it is
unlicensed in the EU, its terms could not be read, leverage has no retail protection, and custody is on-chain.

**Prop firms** are not a capital-scaling route for slow systematic premia: accounts are simulated, a 10% target
with a 5% daily loss limit rewards volatility, and consistency rules cap any single day at 30–55% of profit.

---

## 4. Open questions for the owner

Eligibility and legal points that could **not** be verified from documents. Each needs an account, a support
ticket or advice.

1. **Client category.** Everything here assumes a MiFID retail client. Elective professional status needs two of
   three tests (frequency, a portfolio above €500,000, a finance job). Confirm retail is the working assumption.
2. **Interactive Brokers.**
   a. Is the "Forex-Leveraged" permission offered to a Dutch retail account, or only Forex CFDs? IBIE's own
      disclosure says it "may also offer spot trading … on a leveraged basis"; an introducing broker says EEA
      residents can only lever through Forex CFDs.
   b. Minimum order size for FX CFDs, and whether share and ETF CFDs accept fractional quantities.
   c. Does a key information document exist for MES, M6E, M6B, M6A, MGC, MCL, MBT and for options on SPY/QQQ?
      (Contract Details → PRIIPs KID in Client Portal.)
   d. Does the paper account accept API orders before the live account is funded?
   e. What does an odd-lot FX order actually fill at, relative to the IDEALPRO quote?
3. **Kraken.**
   a. Is the Netherlands on the eligible list for Kraken Derivatives? (The questionnaire appears in-account.)
   b. Can an EEA client trade xStocks on the Kraken Pro order book and through the API? An older support text
      said no; the current article and the August 2026 launch post do not repeat it.
   c. Does futures volume or assets on platform lower the 0.20% FX-pair fee in practice? (The tier table for FX
      pairs is keyed to 30-day spot crypto volume.)
4. **OKX Europe.** Is USDC-EUR really charged 0% on a retail account? Are X-Perps enabled for a Dutch account
   today? Is a BTC X-Perp contract 0.0001 or 0.01 BTC?
5. **Coinbase.** Can the EU futures be traded through the Advanced Trade API? What is the stable-pair taker fee?
6. **One Trading.** Does the "API Trading" schedule (−0.5 bp / 1.5 bp) apply to a retail account, and what does
   retail onboarding for futures require?
7. **Bybit EU.** Can a retail client create a personal API key at all?
8. **Bitstamp.** Current fee schedule; whether a retail client may trade the EUR/USD perp.
9. **Deribit.** Will it onboard a Dutch retail resident, and under which entity? The restricted list does not
   name the Netherlands, which is not the same as acceptance.
10. **Hyperliquid and other on-chain perps.** Is use by a Dutch retail resident lawful and how is it taxed? ESMA's
    February 2026 statement is addressed to firms; no AFM statement on DeFi perpetuals was found.
11. **OANDA.** Can a Dutch resident obtain a v20 *practice* token purely for historical bid/ask candles?
12. **Trading 212.** Interest rate on EUR cash, minimum order value, and whether the API terms limit order
    frequency. The main site refused automated access.
13. **Bitvavo.** Who may use margin trading, and with what leverage?
14. **Prop firms.** How does the AFM treat challenge-style firms after the Ufunded case, and how are "rewards"
    taxed?
15. **US brokers.** Does Alpaca accept Dutch residents, and does any US broker let an EU resident buy US ETFs?
    tastytrade and Tradier eligibility rests on ⟨JS-render⟩ pages — re-read by hand before relying on it.
16. **Every "Yes" in §1** rests on a document, not on a completed application.

---

## 5. Sources

Access date for every entry: **2026-11-10**. "Supports" says which statements above rest on the source.

### 5.1 Sources read directly for this file

**Kraken**
- `[K1]` https://www.kraken.com/pro/fees — spot, FX/stable, futures and xStocks fee tiers; margin opening and rollover fees; entity footer (fetched from a Dutch IP, Dutch page)
- `[K2]` https://api.kraken.com/0/public/AssetPairs (also `?country_code=NL`, `?aclass_base=tokenized_asset`) — pair list for NL, minimum order sizes, per-pair leverage, absence of USDT pairs, xStocks universe
- `[K3]` https://api.kraken.com/0/public/Depth and `/Ticker` — measured spreads and depth, 13:50–13:52 UTC
- `[K4]` https://futures.kraken.com/derivatives/api/v3/instruments — 219 instruments, platforms permitted, EEA margin schedule, FX perps not on the EEA platform
- `[K5]` https://futures.kraken.com/derivatives/api/v3/tickers — measured perp spreads, volumes
- `[K6]` https://futures.kraken.com/derivatives/api/v4/historicalfundingrates?symbol=PF_XBTUSD (and other symbols) — hourly funding history
- `[K7]` https://futures.kraken.com/derivatives/api/v3/feeschedules — futures fee schedules incl. the 0.25% consumer schedule
- `[K8]` https://www.kraken.com/legal/eea-terms — EEA Terms effective 14 October 2026: entities, Part K "Consumers are not eligible to receive Margin Extensions"
- `[K9]` https://support.kraken.com/articles/xstocks-availability — xStocks rules for EEA clients (updated 18 June 2026)
- `[K10]` https://support.kraken.com/articles/derivatives-eligibility-requirements-eea — verification, questionnaire, tax ID, entity (updated 10 December 2025)
- `[K11]` https://support.kraken.com/articles/derivatives-margin-schedule-and-maximum-leverage-eea — 10× tier I (updated 30 October 2026)
- `[K12]` https://support.kraken.com/articles/4402532394260 — spot margin availability by region (updated 11 September 2026)
- `[K13]` https://docs.kraken.com/api/docs/guides/futures-introduction — demo environment, base URLs
- `[K14]` https://blog.kraken.com/product/equities/announcing-us-listed-stock-trading-for-eea-customers — US stocks for EEA clients, 18 August 2026
- `[K15]` https://www.kraken.com/features/fee-schedule — Kraken app fees (1% instant buy; 0.25% app perps)

**Interactive Brokers (Ireland)**
- `[IB1]` https://www.interactivebrokers.eu/en/home.php — IBIE serves all EU and EEA residents
- `[IB2]` https://www.interactivebrokers.ie/en/pricing/commissions-spot-currencies.php — 0.20 bp, USD 2.00 minimum, 0.03% auto-conversion
- `[IB3]` https://www.interactivebrokers.ie/en/pricing/commissions-cfd-forex.php — FX CFD commission
- `[IB4]` https://www.interactivebrokers.ie/en/pricing/commissions-cfd-index.php — index CFD commissions, one-unit minimum
- `[IB5]` https://www.interactivebrokers.ie/en/pricing/commissions-cfd-share.php — share and US ETF CFD commissions
- `[IB6]` https://www.interactivebrokers.ie/en/pricing/commissions-cfd-metals.php — gold and silver CFD commissions
- `[IB7]` https://www.interactivebrokers.ie/en/trading/ibkr-forex-cfds.php and https://www.interactivebrokers.ie/webrest/interests/fxcfds — FX CFD financing formula, retail 1% add-on, per-pair table
- `[IB8]` https://www.interactivebrokers.ie/en/trading/ibkr-index-cfds.php — index CFD financing
- `[IB9]` https://www.interactivebrokers.ie/en/trading/ibkr-share-cfds.php — share CFD financing
- `[IB10]` https://www.interactivebrokers.ie/en/trading/products-cfds.php — CFDs on restricted US ETFs; oil CFD financing
- `[IB11]` https://www.interactivebrokers.ie/en/accounts/fees/pricing-interest-rates.php — interest paid, thresholds, benchmark-linked rates
- `[IB12]` https://www.interactivebrokers.ie/en/trading/margin-rates.php — margin loan rates
- `[IB13]` https://www.interactivebrokers.ie/en/pricing/commissions-stocks.php?region=europe — EU stock and ETF commissions
- `[IB14]` https://www.interactivebrokers.ie/en/pricing/commissions-futures.php?region=americas — futures commissions incl. micros and Eurex micros
- `[IB15]` https://www.interactivebrokers.ie/en/accounts/fees/CME.php , `/COMEX.php` , `/NYMEX.php` — exchange fees
- `[IB16]` https://www.interactivebrokers.ie/en/accounts/fees/overnight-position-fee-europe.php — overnight position fee
- `[IB17]` https://www.interactivebrokers.ie/en/trading/margin-futures-fops.php?hm=eu&ex=us&rgt=0&rsk=1&pm=0&rst=040404040404040104 — futures margins
- `[IB18]` https://www.interactivebrokers.ie/en/trading/margin-cfd.php?hm=eu&ex=eu&rgt=0&rsk=1&pm=0&rst=040404040404040104 — retail CFD margins
- `[IB19]` https://www.interactivebrokers.ie/en/pricing/commissions-options.php?region=americas — US option commissions
- `[IB20]` https://www.interactivebrokers.ie/en/pricing/commissions-events.php — forecast contracts for professional clients only
- `[IB21]` https://www.interactivebrokers.ie/en/pricing/commissions-crypto-assets.php — crypto via zerohash europe B.V.
- `[IB22]` https://www.interactivebrokers.ie/en/accounts/required-minimums.php and `/pricing/other-fees.php` — no minimum, no inactivity fee, two free withdrawals a month
- `[IB23]` https://www.interactivebrokers.ie/en/pricing/market-data-pricing.php — market data terms
- `[IB24]` https://www.interactivebrokers.ie/en/trading/ib-api.php and `/trading/free-trial.php` — APIs; free trial
- `[IB25]` https://gdcdyn.interactivebrokers.com/Universal/servlet/Registration_v2.formSampleView?formdb=4766 — IBIE retail CFD and forex risk disclosure, 9 October 2026
- `[IB26]` https://www.captrader.com/en/tradable-products/forex/ — introducing-broker statement on leveraged forex for EEA residents (C)
- `[IB27]` https://www.interactivebrokers.ie/cstoolsws/ibgroup.custops.priips/index — KID lookup (public for IBKR CFDs; login for exchange-traded contracts)
- IBKR knowledge-base nodes 1459 (odd lots) and 2993 (PRIIPs) were seen only as search extracts (C).

**OANDA, Trading 212, Saxo, IG**
- `[OA1]` https://www.oanda.com/eu-en/ — OANDA TMS Brokers S.A., platforms
- `[OA2]` https://developer.oanda.com/rest-live-v20/introduction/ — v20 API not available to OANDA TMS
- `[OA3]` https://developer.oanda.com/rest-live-v20/development-guide/ — hosts and rate limits
- `[T1]` https://docs.trading212.com/api — API scope, environments, limits
- `[T2]` https://helpcentre.trading212.com/hc/en-us/articles/14584770928157-Trading-212-API-key — order types on live
- `[T3]` https://helpcentre.trading212.com/hc/en-us/articles/11471996799517-What-are-the-fees-in-the-Invest-ISAs-and-SIPP — fees
- `[T4]` https://helpcentre.trading212.com/hc/en-us/articles/12933782261917-What-are-the-supported-countries — Netherlands → Trading 212 EU GmbH
- `[T5]` https://helpcentre.trading212.com/hc/en-us/articles/15475153380637-How-can-I-start-earning-interest-on-my-cash — interest on cash
- `[T6]` https://helpcentre.trading212.com/hc/en-us/articles/9511997937437-Can-I-trade-with-fractional-shares — fractional execution
- `[T7]` https://helpcentre.trading212.com/hc/en-us/articles/360018909758-What-is-the-FX-fee-Invest-Stocks-ISA — FX fee
- `[SX1]` https://www.home.saxo/-/media/documents/regional/nl/pricing-unified.pdf — Dutch price list of 13 July 2026
- `[SX2]` https://www.home.saxo/nl-nl/rates-and-conditions/pricing-overview — Bronze commissions
- `[SX3]` https://www.developer.saxo/openapi/learn/environments — simulation and live hosts
- `[SX4]` https://www.developer.saxo/openapi/learn/rate-limiting — limits
- `[SX5]` https://www.developer.saxo/openapi/learn — 24-hour token, application registration
- `[IG1]` https://www.ig.com/nl/kosten-en-tarieven — entity, AFM registration, loss rate
- `[IG2]` https://www.ig.com/content/dam/igcom-websites/1770999417219/nl_NL/pdf/2026/02/13/240110_StandardisedCost_OTC_NL.pdf — standardised costs per €25,000
- `[IG3]` https://labs.ig.com/faq.html — API hosts, quotas, history depth

**Bitvavo, Deribit, One Trading, Hyperliquid**
- `[BV1]` https://bitvavo.com/en/fees — fee categories, margin terms, entity
- `[BV2]` https://api.bitvavo.com/v2/markets — markets, minimums
- `[BV3]` https://api.bitvavo.com/v2/ticker/book and `/ticker/24h` — measured spreads and volumes, 14:12 UTC
- `[BV4]` https://docs.bitvavo.com/docs/rate-limits/ — rate limits
- `[DB1]` https://support.deribit.com/hc/en-us/articles/25944487427741-Restricted-Jurisdictions — restricted list, edited 2026-10-06
- `[DB2]` https://www.deribit.com/api/v2/public/get_instruments — instruments, commissions, leverage
- `[OT1]` https://www.onetrading.com/ — entity, licences, retail statement, 10×
- `[OT2]` https://www.onetrading.com/fees — fee tables, liquidation and custody fees
- `[OT3]` https://api.onetrading.com/fast/v1/instruments and `/fees` — instruments, funding period, fee tiers
- `[OT4]` https://api.onetrading.com/fast/v1/market-ticker and `/order-book/{instrument}?level=2` — measured volumes and spreads
- `[HL1]` https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees — fee tiers, HIP-3 multiplier, growth mode
- `[HL2]` https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding — funding formula, 0.5%/hour cap
- `[HL3]` https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits — limits
- `[HL4]` https://hyperliquid.gitbook.io/hyperliquid-docs/onboarding/how-to-start-trading and `/onboarding/testnet-faucet` — onboarding, testnet
- `[HL5]` https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/protocol-vaults and `/historical-data` — HLP lock-up, data archive
- `[HL6]` https://api.hyperliquid.xyz/info (`metaAndAssetCtxs`, also with `"dex":"xyz"`; `userFees`) — universe, leverage, growth mode, base fees
- `[HL7]` https://api.hyperliquid.xyz/info (`l2Book`) — measured spreads, 14:31 UTC
- `[HL8]` https://api.hyperliquid.xyz/info (`fundingHistory`) — hourly funding, last 365 days

**Rates, registers, libraries**
- `[R1]` https://fred.stlouisfed.org/graph/fredgraph.csv?id=SOFR — SOFR 3.88% (2026-11-09); `id=DFF` 3.88%
- `[R2]` https://fred.stlouisfed.org/graph/fredgraph.csv?id=ECBESTRVOLWGTTRMDMNRT — €STR 2.442% (2026-11-09); `id=ECBDFR` 2.50%
- `[R3]` https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml — reference FX rates of 2026-11-09
- `[R4]` https://www.esma.europa.eu/sites/default/files/2024-12/CASPS.csv — ESMA interim MiCA register (Kraken, Bitvavo, One Trading, zerohash rows checked)
- `[PY]` https://pypi.org/pypi/<package>/json — versions and upload dates of `ib_async`, `python-kraken-sdk`, `hyperliquid-python-sdk`, `python-bitvavo-api`, `trading-ig`, `oandapyV20`, `saxo-openapi`, `ccxt`; `MetaTrader5` ships `win_amd64` wheels only

### 5.2 Sub-analyst A — prop firms and prediction markets

Source list as recorded by the sub-analyst (`[A]` in the tables). 87 URLs.

Prop firms
- https://ftmo.com/en/faq/who-can-join-ftmo/ - FTMO CFD eligibility, restricted table, US/AU affiliates
- https://ftmo.com/en/futures/faq/who-can-join-ftmo-futures/ - FTMO Futures eligibility
- https://cdn.ftmo.com/docs/terms-and-conditions/b1d80f4da76c4bd4bcd42a5807727e34 - FTMO Challenge T&C (12 Oct 2026): entities, simulated trading, no-refund clause, USD 400,000 cap
- https://ftmo.com/en/forbidden-trading-practices/ - FTMO prohibited practices, 2,000 server requests/day
- https://ftmo.com/en/faq/which-instruments-can-i-trade-and-what-strategies-am-i-allowed-to-use/ - FTMO EA/algo permission, server limits
- https://ftmo.com/en/trading-objectives/ - FTMO targets, loss limits, consistency rules (1-Step, 2-Step, Instant)
- https://ftmo.com/en/comparison-table/ - FTMO "from" prices, refund, reward ratio, disclaimers
- https://ftmo.com/en/faq/why-is-there-a-fee/ - FTMO fee refund terms
- https://ftmo.com/en/trading-platforms/ - FTMO platforms, cTrader Automate/Open API statement, news and weekend FAQ excerpts
- https://ftmo.com/en/2-step-challenge/ - FTMO page-source price list and "average_reward" figures, free trial
- https://ftmo.com/en/reward-growth-and-scaling-plan/ - FTMO scaling plan
- https://ftmo.com/en/ and https://ftmo.com/en/how-it-works/ - FTMO Instant leverage, TradingView/OANDA, reward wording
- https://the5ers.com/faqs/who-can-join-the5ers/ - The5ers country list, simulated-environment disclaimer
- https://the5ers.com/faqs/can-i-use-an-ea-expert-advisor-can-i-set-a-stealth-mode-stop-loss/ - The5ers EA rules
- https://the5ers.com/faqs/prohibited-trading-practices/ - The5ers prohibited practices
- https://the5ers.com/high-stakes/ - The5ers High Stakes prices, targets, platform, payouts, scaling
- https://the5ers.com/terms-and-conditions/ - The5ers entities, jurisdiction, MetaQuotes US clause
- https://help.fundednext.com/en/articles/8020080-are-any-countries-restricted-on-fundednext-cfds - FundedNext restricted countries
- https://help.fundednext.com/en/articles/8020763-is-ea-allowed-in-fundednext - FundedNext EA policy
- https://help.fundednext.com/en/articles/8388896-are-there-any-restrictions-on-my-trading-strategy - FundedNext strategy rules
- https://help.fundednext.com/en/articles/17255124-stellar-2-step-challenge - FundedNext prices, targets, cycles, rules
- https://fundednext.com/terms-of-service - FundedNext entities
- https://help.topstep.com/en/articles/8284116-am-i-eligible-to-trade-with-topstep - Topstep eligibility
- https://help.topstep.com/en/articles/11187768-topstepx-api-access - Topstep API, price, personal-device rule, no API on Live
- https://help.topstep.com/en/articles/10296582-prohibited-conduct - Topstep prohibited conduct
- https://help.topstep.com/en/articles/10305426-prohibited-trading-strategies-at-topstep - Topstep prohibited strategies / SIM fills
- https://help.topstep.com/en/articles/8284099-topstep-program-overview - Topstep stages
- https://help.topstep.com/en/articles/8284197-trading-combine-parameters - Topstep Combine rules, automation FAQ
- https://help.topstep.com/en/articles/8284215-express-funded-account-parameters - Topstep XFA rules
- https://help.topstep.com/en/articles/8284233-topstep-payout-policy - Topstep payouts, caps, 63% statistic
- https://help.topstep.com/en/articles/14289835-topstep-pricing-and-payment-questions - Topstep pricing
- https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit - Topstep MLL mechanics
- https://www.topstep.com/terms-of-use/ - Topstep entities, simulated account definition
- https://www.hyrotrader.com/ - HyroTrader programmes, prices (page source), entities, disclosures
- https://www.hyrotrader.com/faq/ - HyroTrader "no real-capital stage" disclosure
- https://www.hyrotrader.com/blog/prop-firms-that-allow-bots/ - HyroTrader bot rules, 40% rule, 5% payout cap
- https://www.breakoutprop.com/ , https://www.breakoutprop.com/kraken/ , https://www.breakoutprop.com/pricing/ - Breakout rules, prices (page source), POL disclosures
- https://blog.kraken.com/news/kraken-acquires-breakout - Kraken acquisition of Breakout (4 Sept 2025)
- https://intercom.help/breakoutprop/en/articles/11644118-which-countries-are-ineligible-for-breakout-services - Breakout ineligible countries
- https://intercom.help/breakoutprop/en/articles/11644090-what-trading-practices-are-prohibited-during-the-breakout-evaluation - Breakout prohibited practices
- https://intercom.help/breakoutprop/en/articles/11644132-will-i-be-trading-in-a-live-environment - Breakout demo disclosure
- https://intercom.help/breakoutprop/en/articles/11643732-what-types-of-breakout-evaluations-can-i-purchase - Breakout variants
- https://apextraderfunding.com/help-center/getting-started/restricted-countries/ and /prohibited-activities/ - UNREACHABLE (HTTP 403)
Regulators and industry
- https://www.afm.nl/en/sector/actueel/2026/jan/pb-ufunded - AFM warning: funded trading classified as investment services
- https://www.afm.nl/~/profmedia/files/maatregelen/waarschuwing/2026/ufunded-waarschuwing-stand-van-zaken.pdf - AFM case status
- https://www.iosco.org/i-scan/?id=33616 - CONSOB alert on funded trading / prop firms (2024-07-15)
- https://www.financemagnates.com/forex/demo-account-prop-trading-platforms-do-not-need-authorisation-czech-regulator/ - CLAIM: CNB position
- https://www.financemagnates.com/forex/exclusive-czech-regulator-asserts-prop-trading-firms-may-be-subject-to-mifid - CLAIM: CNB first comment, ESMA "initial check"
- https://financemagnates.com/forex/another-regulator-warns-against-prop-firms-calls-them-trading-video-games - CLAIM: Belgian FSMA warning
- https://www.financemagnates.com/forex/my-forex-funds-parent-defeats-cftc-in-court-as-judge-imposes-sanctions/ - CLAIM: CFTC v. My Forex Funds dismissal
- https://financemagnates.com/forex/prop-trading-firms-renaissance-cutting-us-clients-integrating-new-trading-platforms - CLAIM: 2024 MetaQuotes episode
- https://www.fxstreet.com/press-releases/ftmo-building-global-trading-powerhouse-completes-acquisition-of-oanda-from-cvc-202512020741 - CLAIM: FTMO-OANDA closing
Prediction markets
- https://kansspelautoriteit.nl/sites/default/files/2026-02/2026-01-20_22310_LOD%20Adventure%20One%20SQQ%20Inc._sanctiebesluit.pdf - Ksa order against Polymarket (20 Jan 2026)
- https://kansspelautoriteit.nl/last-onder-dwangsom-voor-illegaal-kansspelaanbod-polymarket - Ksa news item (17 Feb 2026), general stance on prediction markets
- https://kansspelautoriteit.nl/adventure-one-qss-inc-polymarket - Ksa case page: forfeiture, collection, status
- https://kansspelautoriteit.nl/sites/default/files/2026-07/2026-06-23_24971_beslissing%20op%20bezwaar%20Adventure%20One%20QSS%20Inc._sanctiebesluit.pdf - Ksa objection decision (23 June 2026)
- https://polymarket.com/tos - Polymarket Terms of Use (11 Aug 2026): restricted persons incl. the Netherlands, VPN ban, Panama law, Polymarket US footer
- https://docs.polymarket.com/api-reference/geoblock.md - Polymarket API geoblock groups
- https://help.polymarket.com/en/articles/13364163-geographic-restrictions - Polymarket help-centre restricted list
- https://polymarket.com/api/geoblock - live geoblock response from a Dutch IP
- https://docs.polymarket.com/llms.txt - Polymarket docs index
- https://docs.polymarket.com/getting-started/api.md - Polymarket API surfaces and auth
- https://docs.polymarket.com/getting-started/python.md - Polymarket official Python SDK
- https://docs.polymarket.com/migrate/clob-sdk-to-unified-sdk.md - legacy SDK packages
- https://docs.polymarket.com/api-reference/rate-limits.md and /trading-rate-limits.md - Polymarket rate limits
- https://docs.polymarket.com/resources/contracts.md - Polygon mainnet chain ID
- https://docs.polymarket.com/trading/fees.md - Polymarket fee formula and rates
- https://docs.polymarket.com/programs/maker-rebates.md and /liquidity-rewards.md - Polymarket maker programmes
- https://help.polymarket.com/en/articles/13364459-holding-rewards - Polymarket holding rewards (3.25%)
- https://docs.polymarket.com/trading/place-orders.md - minimum order size field
- https://docs.polymarket.com/concepts/pusd.md , /trading/bridge/deposit.md , /trading/bridge/withdraw.md - pUSD, deposits, withdrawals
- https://gamma-api.polymarket.com/markets?closed=false&limit=1 - live sample of market parameters
- https://polymarket.us/ - Polymarket US operator statement
- https://help.kalshi.com/en/articles/14026044-can-i-trade-on-kalshi-from-outside-the-united-states - Kalshi international access and funding methods
- https://kalshi-public-docs.s3.amazonaws.com/kalshi-member-agreement.pdf - Kalshi Member Agreement copy (Last-Modified 10 Oct 2025)
- https://kalshi.com/docs/kalshi-member-agreement.pdf and https://kalshi.com/docs/kalshi-fee-schedule.pdf - UNREACHABLE (HTTP 429)
- https://help.kalshi.com/en/articles/13823805-fees - Kalshi fees overview
- https://docs.kalshi.com/llms.txt , /getting_started/api_environments.md , /demo_env.md , /api_keys.md , /rate_limits.md , /fee_rounding.md - Kalshi API
- https://www.coinperps.com/learn/kalshi-restricted-countries - CLAIM: current Kalshi restricted list
- https://cointelegraph.com/news/kalshi-hyperliquid-offer-prediction-markets-to-dutch-users-despite-polymarket-ban - CLAIM: FD investigation
- https://forecasttrader.interactivebrokers.ie - IBKR Ireland prediction-markets page: MiFID retail exclusion
- https://www.interactivebrokers.ie/en/general/about/mediaRelations/8-1-25.php - IBKR European launch release
- https://www.interactivebrokers.com/en/general/about/mediaRelations/5-7-25.php - IBKR May 2025 release (entities before Europe)
- https://support.developer.betfair.com/hc/en-us/articles/28271961503516-Which-IP-regions-are-restricted-from-accessing-the-Betfair-API - Betfair API restricted regions
- https://docs.limitless.exchange/user-guide/terms-of-service.md , /user-guide/fees.md , /llms.txt - Limitless terms, fees, SDK
- https://cointelegraph.com/news/hungary-portugal-block-polymarket-prediction-market - CLAIM: Hungary/Portugal blocks
- https://www.gamingintelligence.com/legal/232164-european-gambling-regulators-warn-of-prediction-market-risks/ - CLAIM: nine-regulator declaration

### 5.3 Sub-analyst B — secondary FX / CFD brokers, cTrader, MetaTrader, ESMA / AFM rules

Source list as recorded by the sub-analyst (`[B]` in the tables). 74 URLs.

Regulation
- https://www.esma.europa.eu/press-news/esma-news/esma-agrees-prohibit-binary-options-and-restrict-cfds-protect-retail-investors - ESMA leverage caps, 50% close-out, negative balance protection, incentives ban
- https://www.esma.europa.eu/investor-corner/product-intervention - national measures replaced ESMA's temporary ones; AFM turbo opinion mention
- https://www.afm.nl/~/profmedia/files/onderwerpen/productinterventie/besluit-productinterventie-cfd.pdf - AFM CFD decision of 18 April 2019 (margins, close-out, negative balance, incentives)
- https://www.afm.nl/en/sector/themas/over-het-toezicht-en-beleid-van-de-afm/toezicht-en-beleid/productinterventie - AFM product-intervention page (CFD decree link, binary-option ban, turbo restrictions)
- https://www.afm.nl/en/sector/actueel/2021/juni/besluit-beperkingen-turbos - turbo restrictions, in force 1 October 2021
- https://wetten.overheid.nl/jci1.3:c:BWBR0020421 - BGfo consolidated text (negative search for a CFD advertising ban)
- https://www.cysec.gov.cy/en-GB/entities/investment-firms/cypriot/ and entity pages /42294/ /101891/ /88151/ /80418/ /82198/ /88692/ /40631/ /37683/ /89835/ /37686/ /74706/ - licence numbers, approved domains, Netherlands in cross-border lists
- https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml - reference FX rates of 2026-11-09
cTrader / MetaTrader
- https://help.ctrader.com/open-api/ - access, rate limits, demo, SDK list
- https://help.ctrader.com/open-api/account-authentication/ - OAuth 2.0, token lifetimes
- https://help.ctrader.com/open-api/proxies-endpoints/ - live/demo hosts and ports
- https://help.ctrader.com/open-api/creating-new-app/ - application approval
- https://help.ctrader.com/open-api/messages/ - trend-bar and tick requests
- https://help.ctrader.com/open-api/faq/ - 429, bars need ticks
- https://help.ctrader.com/open-api/python-SDK/python-sdk-index/ - official Python SDK
- https://raw.githubusercontent.com/spotware/openapi-proto-messages/main/OpenApiMessages.proto and OpenApiModelMessages.proto - request fields, bar periods, quote types
- https://pypi.org/pypi/ctrader-open-api/json - SDK versions, yanked release, dependencies, wheel tag
- https://api.github.com/repos/spotware/OpenApiPy , https://api.github.com/repos/spotware/openapi-proto-messages - last push dates
- https://help.ctrader.com/fix/ - cTrader FIX API exists
- https://pypi.org/pypi/MetaTrader5/json - Windows-only wheels
- https://www.mql5.com/en/docs/python_metatrader5 - official Python integration docs
- https://www.metatrader5.com/en/terminal/help/start_advanced/install_linux - terminal on Linux via Wine
- https://metaapi.cloud/ - MetaApi subscription prices
Capital.com
- https://open-api.capital.com/ - API reference (limits, demo, history, key generation, notice)
- https://capital.com/en-eu/ways-to-trade/fees-and-charges/cfd-and-ko - fees, conversion 0.7%, overnight formulas, minimum deposit
- https://capital.com/en-eu/ways-to-trade/pricing - spread examples
- https://capital.com/en-eu/trading-platforms/demo-account - demo, no expiry
- https://capital.com/nl-nl - Dutch site, entities, exclusions
- https://capital.com/en-eu/ways-to-trade/fees-and-charges/stocks - real stocks available to NL residents
Pepperstone
- https://pepperstone.com/en-eu/ - entity, exclusions
- https://pepperstone.com/en-eu/ways-to-trade/pricing/ - account models, swap formulas, leverage, deposits, inactivity
- https://pepperstone.com/en-eu/ways-to-trade/trading-accounts/ - Razor/Standard, micro-lot rounding
- https://pepperstone.com/en-eu/markets/forex/pairs-and-spreads/ - FX min/avg spreads, commissions per platform
- https://pepperstone.com/en-eu/markets/index-cfds/ - index min/avg spreads
- https://pepperstone.com/en-eu/markets/cfd-forwards/ - forward CFDs without overnight funding
- https://pepperstone.com/en-eu/ways-to-trade/demo-accounts/ - demo expiry
- https://pepperstone.com/en-eu/platforms/trading-platforms/ctrader/ - cTrader API mention
- https://eu-assets.contentstack.com/v3/assets/bltaec35894448c7261/bltfaf6f57172dc686e/Pepperstone_EU_Limited_Cyprus_Terms_and_Conditions.pdf - latency-abuse clause, inactivity reservation
- https://eu-assets.contentstack.com/v3/assets/bltd74737b907a31bbb/blta2d7108dd719db16/CostsandCharges_V09.2026.pdf - swap formulas with mark-ups, no inactivity fee, withdrawal fee
IC Markets EU
- https://www.icmarkets.eu/en/ - entity, exclusions
- https://www.icmarkets.eu/en/trading-pricing/spreads-and-swaps - min/avg spreads and swap points
- https://www.icmarkets.eu/en/trading-pricing/trading-costs - commissions, swap calculation
- https://www.icmarkets.eu/en/trading-accounts/overview - account table
- https://www.icmarkets.eu/en/trading-accounts/ctrader-raw - scalping / HFT statement, server location
- https://www.icmarkets.eu/en/trading-markets/futures - futures CFDs
FP Markets EU
- https://www.fpmarkets.eu/ - entity, exclusions
- https://www.fpmarkets.eu/account-types/forex-account-types/ - account terms
- https://www.fpmarkets.eu/ctrader-fees-and-charges/ - cTrader commissions
- https://www.fpmarkets.eu/forex/spreads/ - typical spreads
- https://www.fpmarkets.eu/swap-rates/ - swap points
Dukascopy
- https://www.dukascopy.com/europe/english/home/ , /about/company/ , /forex/trading/ - entity, exclusions, leverage, minimum deposit
- https://www.dukascopy.com/europe/english/about/fee-schedule/ - commissions, maintenance fee, transfers
- https://www.dukascopy.com/europe/english/forex/api/jforex-api/ , /forex/api/fix-api/ - APIs
- https://www.dukascopy.com/europe/english/forex/demo-fx-account/ - 14-day demo, protections
- https://www.dukascopy.com/europe/english/cfd/cfd-overnight-policy/ and /forex/forex-trading-accounts/overnight/ - rollover tiers
- https://www.dukascopy.com/swiss/english/home/ - Swiss bank leverage, FINMA, solicitation notice
Darwinex
- https://www.darwinex.com/eu/ , /eu/trading/platforms , /eu/forex-cfds - entity, platforms, FIX/Python libraries, Spain restriction
- https://www.darwinexzero.com/ - Darwinex Zero price and operator
FXCM / XTB / CMC / Plus500 / eToro / Trading 212 / Tickmill
- https://www.fxcm.com/eu/ , /eu/algorithmic-trading/api-trading/ , /eu/trading-details/spread-costs/ - AvaTrade notice, APIs, FIX minimum (WebFetch)
- https://pypi.org/pypi/forexconnect/json , https://pypi.org/pypi/fxcmpy/json - FXCM Python packages
- https://www.xtb.com/en/help-center/our-platforms/does-xtb-offer-investment-automation-tools - API discontinued 14 March 2025
- https://www.cmcmarkets.com/de-de , https://www.cmcmarkets.com/en/institutional/cmc-markets-api , https://www.cmcmarkets.com/en - German entity, MT4 EAs, institutional API
- https://www.plus500.com/Docs/Plus500CY/UserAgreement.pdf - automation ban, section 15.17
- https://api-portal.etoro.com/index.md , /llms.txt , /core/getting-started/authentication.md , /core/getting-started/rate-limits.md , /core/guides/market-orders.md , /api-reference/data/get-price-candles-for-an-instrument.md - eToro public API
- https://www.etoro.com/trading/fees/ - eToro withdrawal, inactivity, conversion text
- https://docs.trading212.com/api - API limited to Invest and Stocks ISA
- https://www.tickmill.com/eu/trading/accounts-overview - Tickmill Europe accounts
Third-party (CLAIM level only)
- https://query1.finance.yahoo.com/v8/finance/chart/ - index and gold reference levels
- https://www.financemagnates.com/fintech/retail-traders-gain-quant-level-tools-as-etoro-launches-public-api-and-ai-assistant-tori/ - eToro API rollout history
- https://www.compareforexbrokers.com/reviews/fp-markets-review - FP Markets minimum deposit
- https://www.myfxbook.com/forex-brokers/dukascopy , https://www.daytrading.com/dukascopy-vs-xm - Dukascopy entity routing
- https://www.banken.nl/nieuws/20088/afm-werkt-aan-reclameverbod-op-bepaalde-financiele-producten - 2017 advertising-ban proposal
- https://axebps-redlib.hf.space/r/XTB/comments/1isak4q/xtb_killing_api - XTB user report on no replacement
- https://futures-technologies.plus500.com/api/ - Plus500 futures API (not the CFD platform)
Raw downloads kept beside this file: /tmp/claude-1000/-home-anont-meme/6080f3fd-667a-4f3a-891c-095ad42a53a6/scratchpad/landscape/raw_B/

### 5.4 Sub-analyst C — stock / ETF brokers, PRIIPs, on-chain perps

Source list as recorded by the sub-analyst (`[C]` in the tables). 70 URLs.

EU / regulator
- https://publications.europa.eu/resource/celex/32014R1286 - PRIIPs Regulation Arts. 2, 4, 5, 13
- https://publications.europa.eu/resource/celex/32017R0653 - PRIIPs Delegated Regulation, Annex II point 4 (derivatives are Category 1 PRIIPs)
- https://publications.europa.eu/resource/celex/32023R1114 - MiCA Art. 2(4) exclusion of financial instruments
- https://www.esma.europa.eu/press-news/esma-news/esma-reminds-firms-their-obligations-under-cfd-product-intervention-measures - ESMA 24/02/2026 statement on perpetuals and CFD measures
- https://www.afm.nl/~/profmedia/files/onderwerpen/productinterventie/besluit-productinterventie-cfd.pdf - AFM CFD restrictions (2:1 crypto, in force 19 April 2019)
Alpaca
- https://alpaca.markets/support/countries-alpaca-is-available - no country list, contact support
- https://alpaca.markets/learn/live-trading-account-non-us/ - non-US live accounts, 195+ countries, Portugal example, Canada excluded, PDT
- https://alpaca.markets/support/currencycloud-transfer-questions - Netherlands in local-currency regions, 1.5% fee
- https://alpaca.markets/support/how-can-an-international-user-non-us-tax-resident-fund-their-account - Rapyd, USD only
- https://alpaca.markets/support/is-there-an-account-minimum-for-live-brokerage-accounts-2 - no minimum
- https://alpaca.markets/support/commission-clearing-fees ; /regulatory-fees ; /short-selling-fees ; /fractional-shares ; /alpaca-cryptocurrency - fees, shorting, fractional, crypto
- https://files.alpaca.markets/disclosures/library/BrokFeeSched.pdf - fee schedule revised 12 Oct 2026
- https://docs.alpaca.markets/us/docs/account-plans ; /paper-trading.md ; /about-market-data-api.md ; /margin-and-short-selling.md ; /crypto-fees.md ; /crypto-trading.md ; /trading-api.md - entity, paper, data plans, margin, crypto
- https://docs.alpaca.markets/us/page/regions ; https://docs.alpaca.markets/eu/llms.txt ; https://docs.alpaca.markets/eu/docs/about-alpaca.md ; /about-broker-api.md - Alpaca Europe A.V. SLU is B2B
tastytrade
- https://tastytrade.com/learn/accounts/account-types/international-account/ - international products and account types
- https://support.tastytrade.com/support/s/solutions/articles/43000435355 - eligible/restricted countries [via headless render]
- https://support.tastytrade.com/support/s/solutions/folders/43000342967 ; /articles/43000540765 - international folder, withdrawals [via headless render]
- https://tastytrade.com/pricing/ - commissions
- https://developer.tastytrade.com/ ; /llms.txt ; /docs/sandbox.md ; /docs/guides/rate-limits-and-backoff.md - API, sandbox, limits
- https://docs.optionalpha.com/technical-documentation/platform/supported-countries - third-party country lists (CLAIM)
Tradier
- https://support.tradier.com/kb/guide/en/permitted-and-blocked-countries-CLzSa0D1rf/Steps/4997916 - permitted/blocked countries [via headless render]
- https://tradier.com/pricing - plans and fees
- https://docs.tradier.com/llms.txt ; /overview/endpoints.md ; /overview/rate-limits.md - API, sandbox, limits
DEGIRO / Lynx / Mexem / CapTrader
- https://www.degiro.ie/data/pdf/ie/Client_Agreement_Investment_Services_Terms_and_Conditions.pdf - clauses 5.5, 5.6, 7.5, definitions
- https://www.degiro.nl/data/pdf/Voorwaarden_Beleggingsdiensten.pdf - Dutch version of the same clauses
- https://www.degiro.nl/data/pdf/Tarievenoverzicht.pdf - NL fee schedule from 29-10-2026, entity/supervision
- https://www.degiro.nl/helpdesk/handelsmogelijkheden/producten-beurzen/waarom-kan-ik-niet-beleggen-amerikaanse-etfs - US ETF block
- https://www.lynx.nl/trading-software/api-oplossingen/ - TWS / Web / FIX API for Lynx clients
- https://www.lynx.nl/tarieven-kosten-beleggen/ - Lynx fees, monthly minimum activity fee
- https://www.lynx.nl/beleggingsrekening/minimumeisen/ - no minimum deposit, margin EUR 2,000 and age 21
- https://www.lynx.nl/service/wetgeving-en-producten/wetgeving/essentieel-informatiedocument/ - PRIIPs/KID, professional-only route
- https://www.lynx.nl/beurs/beurs-koersen/opties/optiehandel/opties-op-amerikaanse-indices-futures-etfs/ - alternatives to US ETFs
- https://nl.mexem.com/api ; https://nl.mexem.com/tarieven - Mexem API, fees, CySEC licence
- https://www.captrader.com/en/conditions/ - CapTrader role
Scalable / Trade Republic / Lightyear / BUX / Robinhood / Freedom24
- https://nl.scalable.capital/en/agentic-investing ; https://nl.scalable.capital/en/broker-online - MCP/CLI, fees
- https://help.scalable.capital/en/agentic-investing-aac939f8 (and articles under it) - order confirmation, access levels, cost
- https://raw.githubusercontent.com/ScalableCapital/scalable-cli/main/README.md ; /public-docs/automation.md - CLI trading flow, session limits
- https://www.financemagnates.com/fintech/scalable-capital-rolls-out-ai-agent-integration-for-portfolio-analysis-and-trading/ - context (CLAIM)
- https://traderepublic.com/en-nl - Dutch branch footer
- https://lightyear.com/en-eu/help/getting-verified/do-i-have-to-download-the-app-or-do-you-have-a-website - no API
- https://lightyear.com/en-eu/help/getting-verified/what-services-do-you-offer-and-who-is-eligible - countries, unavailable products
- https://lightyear.com/en-eu/pricing - fees, licence
- https://bux.com/nl/tarieven/ - BUX fees, AFM supervision
- https://robinhood.com/eu/en/ - stock tokens, perpetuals, licence
- https://docs.robinhood.com/crypto/trading/ - API US-only [via headless render]
- https://freedom24.com/tradernet-api - API index (plain); /faq and /errors-and-limits [via headless render]
- https://freedom24.com/download/documents/1203/Appendix_6_Fee_Schedule_19082026 - fee schedule effective 19 Aug 2026, CySEC licence
- https://freedom24.com/documents - document index (latest fee schedule link)
DEX perps
- https://indexer.dydx.trade/v4/perpetualMarkets ; /v4/height - market parameters, status, volumes
- https://dydx-rest.publicnode.com/dydxprotocol/v4/feetiers/perpetual_fee_params - on-chain fee tiers
- https://indexer.v4testnet.dydx.exchange/v4/height - testnet alive
- https://dydx.exchange/v4-terms ; https://www.dydx.xyz/legal/terms-of-use - restricted persons
- https://docs.gmx.io/llms.txt ; /docs/trading/fees.md ; /docs/trading/tradfi-markets.md ; /docs/trading/overview.md ; /docs/security.md - GMX fees, markets, chains, audits
- https://gmx.io/terms-and-conditions - GMX terms [via headless render]
- https://www.drift.trade/updates/recovery-plan-for-affected-users ; /updates/dfx-claim-and-redemptions ; /updates/drift-recovery-update-june-3-2026 - exploit, recovery, Velocity
- https://docs.velocity.exchange/protocol ; /protocol/trading/trading-fees.md - Velocity scope and fees
- https://developers.jup.ag/docs/legal/terms-of-use.md ; /docs/perps/index.md ; /docs/ai/cli.md - Jupiter prohibited localities, API status, CLI
- https://docs.jup.ag/user-docs/trade/perps/fees.md ; /faq.md - Jupiter Perps fees, minimums, leverage
- https://docs.ostium.com/legal/terms-of-use.md ; /traders/reference/fees.md ; /traders/reference/markets.md - EU restricted; fees and markets
- https://docs.gains.trade/help/eligibility-and-restricted-regions.md ; /gtrade-leveraged-trading/fees-and-spread.md - gTrade restrictions and fees
- https://www.veranta.xyz/docs/tos ; https://docs.veranta.xyz/trading/fees/fee-schedule-by-asset-class.md - Veranta terms and fees
- https://lighter.xyz/terms ; https://docs.lighter.xyz/trading/trading-fees.md ; /developers/getting-started/sdks.md - Lighter terms, fees, SDK, testnet
- https://docs.asterdex.com/resources/terms-and-conditions.md ; /trading/perpetuals/fees-and-specs/fees.md - Aster terms and fees
- https://pypi.org/pypi/<package>/json for alpaca-py, tastytrade, tradernet-sdk, dydx-v4-client, driftpy, lighter-sdk, gmx-python-sdk, ostium-python-sdk, avantis-trader-sdk, tradier-python - library existence, versions, upload dates
Unreachable to automated access (not circumvented)
- https://www.theocc.com/company-information/documents-and-archives/priips-key-information-documents (HTTP 403)
- https://www.cmegroup.com/priipskids and /market-regulation/european-regulation/priips-options-products.html (connection reset / timeout)
- https://international.schwab.com/PRIIPS-Regulation (HTTP 403); https://us.etrade.com/l/priips (connection reset)
- https://ibkb.interactivebrokers.com/node/2993 and /node/3324 (redirect to a JavaScript FAQ app)
- https://traderepublic.com/en-nl/pricing and support pages (JavaScript-only; no usable content)
- https://docs.velocity.exchange/protocol/legal-and-regulations/terms-of-use (text painted on a canvas)

### 5.5 Sub-analyst D — other centralised crypto exchanges

Source list as recorded by the sub-analyst (`[D]` in the tables). 76 URLs.

- https://www.esma.europa.eu/sites/default/files/2024-12/CASPS.csv - MiCA CASP register: entities, authorities, dates, NL passporting; absence of Binance/Bitget/Bitfinex/BitMEX/MEXC
- https://www.esma.europa.eu/press-news/esma-news/esma-reminds-firms-their-obligations-under-cfd-product-intervention-measures - ESMA 24/02/2026: perpetual futures likely within national CFD measures
- https://api.bybit.eu/v5/market/instruments-info?category=linear (also inverse, option, spot) - Bybit EU: no derivatives; 129 spot pairs; margin flags; minimums
- https://api.bybit.com/v5/market/instruments-info?category=linear - control: global Bybit lists 930 linear contracts
- https://api.bybit.eu/v5/market/tickers?category=spot&symbol=USDCEUR (EURCUSDC, BTCEUR) - Bybit EU book snapshots
- https://api.bybit.eu/v5/market/kline?category=spot&symbol=USDCEUR&interval=D&limit=1000 - Bybit EU candle depth
- https://api.bybit.eu/v5/spot-margin-trade/data - Bybit borrow-rate output (entity scope unconfirmed)
- https://api.bybit.eu/v5/announcements/index?locale=en-US&limit=100 - shows the EU host serves global announcements (caveat)
- https://bybit-exchange.github.io/docs/v5/guide - Bybit API hosts, EU API restriction quote, testnet host, official SDK list
- https://www.bybit.eu/en-EU/help-center/article/Trading-Fee-Structure - Bybit EU fee page (NOT opened; search extract only)
- https://www.okx.com/en-eu/x-perps - OKX X-Perps landing: 10x, eligibility, 2 bps / 5 bps, entity statement, collateral
- https://www.okx.com/en-eu/help/okx-x-perps-eea-what-are-expiry-perps - X-Perps definition, appropriateness test, retail/professional, "10+ markets"
- https://www.okx.com/en-eu/help/okx-x-perps-eea-regional-availability-eligibility - "all 30 are supported", rollout caveat, KYC + assessment
- https://www.okx.com/en-eu/help/x-perps-contract-specifications - contract list, "Up to 10x", contract sizes, margin call 30%, liquidation, negative balance protection, settlement
- https://www.okx.com/en-eu/help/okx-x-perps-eea-fees-overview - X-Perps maker 0.02% / taker 0.05%, funding every 8 hours, VIP 1 threshold
- https://www.okx.com/en-eu/help/what-are-the-new-trading-fees-for-eea-users - EEA spot fee tiers with and without a derivatives account
- https://www.okx.com/en-eu/help/important-notice-upcoming-spot-fee-adjustment-eea - 25 Sep 2026 spot-only schedule incl. "Stablecoins" 0.000% / 0.050%
- https://www.okx.com/en-eu/help/updates-to-eea-fee-framework - Nov 2025 EEA tiers incl. zero-fee pair column (0.000% / 0.000%)
- https://www.okx.com/en-eu/help/okx-to-support-new-unified-usd-and-eur-spot-trading-pairs-in-eea - EEA "Unified USD" and "EUR" spot pair listings
- https://www.okx.com/en-eu/help/what-costs-apply-besides-trading-fees - Convert/Buy-Sell spread max 1.00%, network fees
- https://www.okx.com/en-eu/learn/spot-margin-arrives-in-europe - OKX Europe spot margin: 10x, long and short, cross margin
- https://www.okx.com/docs-v5/en/ and https://my.okx.com/docs-v5/en/ - OKX API: EEA hosts, demo trading, rate limits, history candles, Python SDK, fee-group enumeration (11 = Spot zero, 17 = Spot stablecoin)
- https://eea.okx.com/api/v5/public/instruments?instType=SPOT|MARGIN|SWAP|FUTURES (and www.okx.com, my.okx.com) - instrument lists (global catalogue on all hosts), X-Perp instruments, minimums, `groupId` fee groups (USDC-EUR = 11), `tradeQuoteCcyList`
- https://eea.okx.com/api/v5/market/ticker?instId=USDC-EUR (and others) - OKX book snapshots
- https://eea.okx.com/api/v5/public/funding-rate?instId=BTC-USD_UM_XPERP-310404 - funding interval and caps
- https://eea.okx.com/api/v5/public/interest-rate-loan-quota - OKX public borrow rates
- https://eea.okx.com/api/v5/market/history-candles?instId=USDC-EUR&bar=1D&limit=100 - candle endpoint works on the EEA host
- https://www.coinbase.com/en-gb/blog/futures-contracts-europe - Coinbase EU futures launch: 26 countries incl. Netherlands, product types, leverage, 0.02% claim
- https://www.coinbase.com/cbfse - CBFSE entity, CySEC CIF 374/19, licensed services, document list
- https://assets.ctfassets.net/o10es7wu5gm1/3fVuEIOKaXOxfN2P31zfwM/349ad352b7f35706bdd25d07b9f0cb1d/Coinbase_Financial_Services_Europe_Ltd_Fees_and_Charges_v1.4-1__1_.pdf - CBFSE futures fees (2 bp + $0.12 per contract), hourly funding
- https://assets.ctfassets.net/o10es7wu5gm1/3TrohnTMA9RgU6RiqfFxzX/693d5934634fbd3d37eeac7f8a49f7da/CBFSE_Target_Market_Disclosure.pdf - retail in target market subject to appropriateness
- https://www.coinbase.com/advanced-vip - Coinbase Advanced tier table as served to this client (Intro 0.25% / 0.50%)
- https://www.coinbase.com/en-nl/advanced-markets - "Dated Futures are offered by CBFSE, a MiFID regulated broker."; FX stable markets listed
- https://help.coinbase.com/en/coinbase/trading-and-funding/advanced-trade/advanced-trade-fees - Advanced fee model; separate stablecoin-pair schedule exists
- https://help.coinbase.com/en/exchange/trading-and-funding/exchange-fees - Coinbase Exchange: stablepair 0.00% maker / 0.45 bps taker, SEPA fees, fx_stablecoin flag
- https://api.exchange.coinbase.com/products (and /products/{id}/ticker, /candles) - product flags, minimums, books, candle depth
- https://api.coinbase.com/api/v3/brokerage/market/products (and ?product_type=FUTURE) - Advanced public products, futures contract details
- https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/overview , /sandbox , /guides/futures , /guides/derivatives/overview - SDK, static sandbox, US-only futures API wording, INTX-to-Deribit migration
- https://api-sandbox.coinbase.com/api/v3/brokerage/accounts - sandbox answers with canned data
- https://www.coinbase.com/en-nl/blog/coinbase-unlocking-new-opportunities-in-crypto-derivatives - EURC-PERP on the international exchange (Feb 2025)
- https://www.bitstamp.net/api/v2/markets/ - Bitstamp markets incl. 20 perpetuals, EUR/USD spot and EUR/USD-PERP, minimums, max leverage
- https://www.bitstamp.net/api/v2/ticker/{eurusd,eurusd-perp,usdceur,eurcusdc,btcusd-perp,btceur}/ - Bitstamp book snapshots
- https://www.bitstamp.net/api/v2/funding_rate/eurusd-perp/ and /funding_rate_history/{eurusd-perp,btcusd-perp}/ - funding prints and 8-hour spacing
- https://www.bitstamp.net/api/v2/ohlc/eurusd/?step=86400&limit=1000 - candle depth
- https://www.bitstamp.net/api/ - Bitstamp API docs: sandbox host, request limits, OHLC steps, perps endpoints, FIX/WebSocket
- https://sandbox.bitstamp.net/api/v2/markets/ - sandbox reachable
- https://blog.bitstamp.net/post/bitstamp-by-robinhood-announces-general-launch-for-crypto-perpetual-futures-for-institutional-and-retail-investors/ - perps for retail, 10x, BFS/ATVP entity
- https://blog.bitstamp.net/post/introducing-multi-asset-perpetual-futures/ - multi-asset perps described as institutional; entity footers
- https://blog.bitstamp.net/post/lower-trading-fees-for-maker-orders-and-stablecoins/ - 2022: 80% discount on fiat/stable pairs
- https://blog.bitstamp.net/post/upcoming-changes-to-fee-schedule/ - 2019: SEPA withdrawal 3 EUR
- https://assets.bitstamp.net/msc/Bitstamp_Derivatives_Program_803fdd0871.pdf - derivatives market-maker pilot fees (not retail)
- https://bitget.eu/en-gb - parked domain (no Bitget EU platform there)
- https://www.bitget.com/support/articles/12560603848109 - Bitget France suspension notice (search extract)
- https://support.gemini.com/hc/en-us/articles/46255474469275-Gemini-closing-accounts-in-the-UK-EU-and-Australia-Everything-you-need-to-know - Gemini EEA exit
- https://support.gemini.com/hc/en-us/articles/12086543664283-What-are-the-eligibility-requirements-for-trading-perpetuals - Gemini derivatives country list
- https://api.binance.com/api/v3/ping - Binance public API reachable
- https://www.binance.com/en/square/post/658553 - Binance 2023 NL exit (search extract)
- https://eu.support.backpack.exchange/exchange/account/supported-regions-and-countries.md - Backpack EU serves EEA incl. Netherlands
- https://eu.support.backpack.exchange/legal-documentation/risk-disclosure - Trek Labs Europe Ltd, CySEC 273/15, retail protections wording, appropriateness
- https://eu.support.backpack.exchange/exchange/trading-fees.md - Backpack EU perp fees
- https://eu.support.backpack.exchange/exchange/perpetual-futures-trading-faqs - entity, 1-hour funding
- https://eu.support.backpack.exchange/exchange/deposits-and-withdrawals-1/crypto/withdrawal-fees.md - withdrawal fees
- https://eu.support.backpack.exchange/llms.txt and /exchange/api-and-developer-docs.md and /start-here/trading-with-backpack-eu.md - API pointers, generic product description
- https://learn.backpack.exchange/blog/backpack-eu-launch - Backpack EU launch: MiFID II/CySEC, 40+ pairs, up to 10x
- https://api.eu.backpack.exchange/api/v1/markets and https://api.backpack.exchange/api/v1/markets - identical market lists, funding interval, minimums
- https://help.crypto.com/en/articles/4894471-perpetual-contracts-trading-frequently-asked-questions-faqs - Crypto.com generic perps FAQ
- https://defillama.com/exchange/crypto-com-eu - Crypto.com EEA: no margin/perps, 0.25% / 0.50% (CLAIM, search extract)
- https://developer.revolut.com/docs/api/revolut-x-crypto-exchange - Revolut X REST API, auth, rate limits, endpoints
- https://revx.revolut.com/api/1.0/public/configuration/pairs and /public/tickers - Revolut X pairs, minimums, regional books, snapshots
- https://cdn.revolut.com/terms_and_conditions/pdf/crypto_exchange_trading_rules_cea4f668_1.0.1_1761855172_en.pdf - Revolut X trading rules (fee model, abuse rules)
- https://www.revolut.com/en-FR/business/revolut-x-eea/ - Revolut X EEA fees 0% / 0.09% (search extract; page blocked)
- https://support.bitpanda.com/hc/en-gb/articles/21417526386588-Margin-Trading-for-Cryptocurrencies - Bitpanda margin terms
- https://support.bitpanda.com/hc/en-gb/articles/16663481714844-Bitpanda-Fusion - Bitpanda Fusion fees, broker model, API
- https://www.kucoin.com/en-eu - KuCoin EU product footer
- https://www.gate.com/en-eu - Gate EU navigation
- https://raw.githubusercontent.com/ccxt/ccxt/master/README.md - ccxt exchange ids (bybiteu, myokx, coinbase, bitstamp, backpack, revolutx, gateeu, cryptocom, ...)
- Press / third party (CLAIM only): financemagnates.com (Bybit MiFID application), prnewswire.com (Bybit EU spot margin), coinacademy.fr, fintechfutures.com (OKX licence number), cryptoslate.com (Coinbase stable-pair fee), cointelegraph.com (Crypto.com MiFID), casptracker.eu and tangem.com (Bitget), bleap.finance and paymentexpert.com (Binance), datawallet.com (KuCoin EU), cryptoadventure.com (Bitstamp fees)

### 5.6 Where the quote-level evidence is

Each sub-analyst wrote a file with one line per fact: label, verbatim quote, URL, access date. Those four files,
my own notes and the raw page captures sit in the session scratch directory and are **not** in the repository
(this task owns only `PLATFORMS.md` and `venues.json`):

`/tmp/claude-1000/-home-anont-meme/6080f3fd-667a-4f3a-891c-095ad42a53a6/scratchpad/landscape/`
(`evidence_A_prop_prediction.md`, `evidence_B_fx_cfd.md`, `evidence_C_stocks_dex.md`, `evidence_D_crypto_cex.md`,
`notes_core.md`, `raw/`, and `tools/build_venues.py`, which generates `venues.json`).

The scratch directory is temporary. Copy it somewhere durable if the quotes are wanted later.

---

## Appendix A. What the sub-analysts could not verify

Verbatim "could not verify" lists. §4 carries the points that need the owner; these are the full detail.

### Sub-analyst A — prop firms and prediction markets

1. Apex Trader Funding: everything. Its help-centre pages and Zendesk API returned HTTP 403 to automated access; all Apex lines are search-snippet CLAIMs and third-party figures conflict (fees, consistency 30% vs 50%, split 90% vs 100%). Netherlands eligibility: UNKNOWN.
2. Kalshi's CURRENT Member Agreement and fee schedule PDFs (kalshi.com/docs/...): HTTP 429 Vercel checkpoint. The Netherlands' absence from the restricted list is verified only for the copy last modified 10 Oct 2025; for the 1 Oct 2026 version it is a CLAIM.
3. Whether any Dutch authority has acted against Kalshi, Limitless or Myriad specifically. Only the Polymarket case was found on kansspelautoriteit.nl.
4. Whether participating as a player in an unlicensed prediction market is itself sanctioned under the Dutch Wok; and whether a court appeal against the Ksa's 23 June 2026 decision exists.
5. FTMO: payout frequency, first-payout delay, payout methods, base (pre-scaling) split on the 2-Step, leverage by asset class, whether external cTrader Open API order routing is permitted on challenge/funded accounts, DXtrade availability, FTMO Futures platform/API.
6. The5ers: any platform other than "Mt5 Hedge"; API access from Linux/Python; payout methods; pass statistics. The 4% / 8% loss limits on the $50K and $100K High Stakes tabs come from page-source data and should be re-read in a browser before use.
7. FundedNext: EA add-on price; exact demo-account wording of ToS section 8; leverage; payout methods; pass statistics.
8. Topstep: profit-target table per account size (CLAIM only), payout methods and processing time, non-TopstepX platforms, pass statistics beyond the firm's "63%" marketing line.
9. HyroTrader: any country-restriction list; martingale/news/weekend rules (inside a JS help app); whether a Dutch resident can hold the Bybit or BloFin demo account its API route needs.
10. Breakout: whether bots are allowed and whether any API exists for the Breakout Terminal.
11. Bybit: whether Bybit itself runs any prop programme (none found).
12. ESMA: no public statement on prop / funded trading found. CNB (Czech) and FSMA (Belgium) positions are trade-press CLAIMs; CNMV (Spain) not found.
13. MetaQuotes 2024 episode, CFTC v. My Forex Funds outcome, FTMO-OANDA closing date, FPFX "7% get a payout" figure: trade-press / snippet CLAIMs, primary documents not read.
14. Dates and texts of French, Belgian, Polish, Italian, German, Hungarian, Portuguese, Czech actions against Polymarket, and the June 2026 nine-regulator declaration: trade-press CLAIMs. Polymarket's own Terms and docs do list those countries as restricted (verified).
15. Polymarket: whether polymarket.us accepts non-US residents; whether the legacy py-clob-client still works; KYC rules for API trading; liquidity depth (not measured).
16. Betfair: Dutch licence status and website availability; commission.
17. Myriad, Robinhood, Crypto.com: no primary source read.

### Sub-analyst B — secondary FX / CFD brokers, cTrader, MetaTrader, ESMA / AFM rules

1. Whether any of these brokers actually completes onboarding for a NL retail resident (no account was opened; regulator passport lists and site exclusions only).
2. cTrader Open API: historical depth for bars/ticks, per-request window limits, which side the bars are, approval turnaround for a new application, and whether each broker's EU entity leaves the Open API enabled. Terms of use not read.
3. AFM: numeric turbo leverage limits; existence of any separate NL advertising ban for CFDs (none found in the BGfo text).
4. Capital.com: typical/average spreads for any instrument (dynamic only), inactivity fee, minimum trade sizes, leverage text, T&C clauses on scalping/arbitrage, which of the two CySEC entities contracts with a new NL client, FX-forward conditions.
5. Pepperstone: average gold spread, forward-CFD spreads, P&L currency-conversion mark-up, index/commodity minimum sizes, whether Pepperstone GmbH (BaFin) is the entity for some NL clients.
6. IC Markets EU: minimum deposit, inactivity and funding fees, conversion fee, demo expiry, Standard-account average spreads, the unit of index swap "points" (my 5.4%/yr reading depends on it), client-agreement clauses on arbitrage.
7. FP Markets EU: minimum deposit, funding/inactivity/conversion fees, demo expiry, measurement window of the "typical" spreads, unit of index swap points, legal clauses on scalping/arbitrage. www.fpmarkets.com/eu blocked (403).
8. Dukascopy: regulator name and licence number of Dukascopy Europe from a primary page; whether Dukascopy Bank SA accepts NL retail residents and with what protections; FIX minimum deposit; average spreads; minimum trade size; size of the "own carry costs"; history depth through the JForex API; demo extension rules.
9. Darwinex: every price (spreads, commissions, swaps, minimum deposit, inactivity fee) - pages render client-side; FIX API access conditions; whether Darwinex Zero exposes anything beyond MT4/MT5.
10. FXCM EU: all figures. The site blocks curl (403); the AvaTrade statement and the FIX "€5,000" minimum come from WebFetch model extraction and should be re-read by a person. Timing of the transfer of existing accounts unknown.
11. AvaTrade and FxPro: sites blocked (403); nothing verified.
12. CMC Markets: whether CMC Markets Germany GmbH accepts NL residents; average spreads; financing formula; any retail API (none found).
13. eToro: FX and index CFD spreads, conversion-fee rates, overnight formula, minimum sizes, ToS on bots, whether the API key menu is live for every EU retail account, any official Python SDK.
14. Trading 212 CFD and XTB and Plus500: trading costs (not pursued because none can be automated).
15. Interest on uninvested cash: not verified for any broker in this slice.
16. Reference index/gold levels come from a third-party quote endpoint, used only to scale points into basis points.
Unreachable or blocked pages
- https://www.fpmarkets.com/eu/ - HTTP 403 (curl and WebFetch)
- https://www.fxcm.com/eu/ and sub-pages - HTTP 403 to curl (WebFetch succeeded); https://www.fxcm.com/eu/forex-trading/spreads/ - 404
- https://www.plus500.com/nl-nl/ , https://www.plus500.com/en-cy/tradingacademy/faq/trading , https://www.plus500.com/en-ch/tradingacademy/faq/trading - HTTP 403
- https://www.fxpro.com/trading-platforms/ctrader - HTTP 403
- https://www.avatrade.com/trading-platforms/api-trading - HTTP 403
- https://www.afm.nl/nl-nl/sector/themas/belangrijke-europese-wet--en-regelgeving/mifid-ii/productinterventie - HTTP 403 / 404 (guessed URL)
- https://pepperstone.com/nl-nl/ - 404; https://capital.com/en-eu/markets/forex/eur-usd - 404 (guessed URL)
- https://t212public-api-docs.redoc.ly/ - redirects to a login page (superseded by docs.trading212.com)
- https://www.xtb.com/en/help-center/our-platforms/do-you-offer-api - 404 (the automation-tools article was readable)
- https://www.darwinex.com/eu/ - redirect loop without a cookie jar; readable once cookies were kept
- https://www.esma.europa.eu/press-news/esma-news/esma-ceases-renewal-product-intervention-measures-relating-contracts-differences - page shell only, no article text
- https://stooq.com/q/l/ quote endpoint - not available

### Sub-analyst C — stock / ETF brokers, PRIIPs, on-chain perps

- Whether Alpaca Securities LLC accepts residents of the Netherlands today (no published list; must ask support).
- Whether Alpaca, tastytrade or Tradier let an EU-resident retail client BUY US-domiciled ETFs; none publishes a PRIIPs/KID statement I could read.
- Whether an NL retail client can open options on US-domiciled ETFs (e.g. SPY options) at any broker.
- OCC and CME KID pages (HTTP 403 / connection reset): content known only from search snippets.
- IBKR, Schwab International, E*TRADE PRIIPs pages (unreachable to automated access).
- Alpaca Trading API rate limit; Alpaca crypto eligibility for EU residents; current Alpaca day-trading rule.
- tastytrade API Terms of Service; tastytrade minimums.
- Tradier inactivity-fee waiver condition; any FX facility.
- Trade Republic: fees, API stance and ToS (site unreachable to automated access; search snippets only).
- BUX: any API statement; ABN AMRO press release not opened.
- Robinhood EU: NL availability, fees, any API for stock tokens or perpetuals.
- Freedom24: explicit NL acceptance, FX conversion fee, minimum deposit, paper account.
- Lynx: own licence, FX fee, paper account, exact differences against IBKR direct.
- CapTrader: everything except its introducing-broker role. flatex: everything.
- Velocity Terms of Use (canvas-rendered); gTrade full Terms of Service and NL regional status per asset class.
- Collateral, leverage, minimum order size and FX/index market lists for Veranta, Lighter and Aster; collateral asset for dYdX.
- ESMA statement PDF (only the news page was read); any AFM statement on DeFi perpetuals.
- Facts tagged [via headless render] rest on a method I was later told not to use; they were not re-verified by a plain client (those pages need JavaScript). Dependent conclusions: tastytrade NL eligibility, Tradier NL eligibility, Robinhood API US-only, Freedom24 API-key/bot/limit details, GMX Terms.

### Sub-analyst D — other centralised crypto exchanges

1. Bybit EU: current fee schedule, any stable-pair schedule, SEPA and withdrawal fees, spot-margin terms and whether shorts are possible, WebSocket host, rate limits, and above all whether a retail client can create a personal API key (docs say the EU API only supports the third-party-application feature). bybit.eu refused automated access.
2. OKX Europe: that an EEA retail account is really charged 0% on USDC-EUR (fee group 11 "Spot zero" is verified from the public instrument list and API docs, the account-level fee is not); whether the zero-fee and stable schedules still apply once an X-Perps account is opened; whether the public order book equals the EEA book; EEA-account borrow rates; inactivity fee; ToS clause on bots; whether X-Perps are enabled for an NL account today; MFSA register entry for OKX Europe Markets Ltd.
3. Coinbase: stable-pair taker fee on Advanced (behind log-in); SEPA/instant-buy/inactivity fees for the retail app; margin close-out and negative-balance terms for CBFSE futures; EU-specific margin rates and contract list; API access to CBFSE futures; REST rate limits; NL eligibility for the Deribit-powered international perpetuals; CySEC register entry for CIF 374/19.
4. Bitstamp: the whole current fee schedule (spot, stable/fiat pairs, perps, SEPA, crypto withdrawal); retail access to FX/commodity/ETF perps; perps eligibility by country (Netherlands not named); close-out, negative balance protection, appropriateness test; funding formula and unit; sandbox key issuance; whether an EU retail client can hold USD and trade the fiat EUR/USD pair; ATVP register entry for BFS.
5. Bitget: any official statement specific to the Netherlands; status of the FMA application.
6. Binance: its own current restricted-country list (page not readable); any 2026 MiCA authorisation under a name not containing "Binance".
7. Backpack EU: exact retail leverage and close-out rules; whether spot is live for EU clients; EUR funding route; EU-specific market list; rate limits; testnet.
8. Crypto.com: everything about the EEA exchange offering beyond the MiCA entry (fees, margin, perps, API scope).
9. Revolut X: the fee schedule from a page I could open; order-placement rate limit; sandbox; candle depth.
10. Bitpanda: Fusion API eligibility for an ordinary retail client; API rate limits from a primary page.
11. KuCoin EU / Gate EU: whether they onboard NL clients today, fees, API hosts for the EU entities, any derivatives.
12. Bitfinex / BitMEX / MEXC: their own terms on Dutch residents (only the ESMA absence is verified).
13. Regulator side: MiFID investment-firm register entries (MFSA, CySEC, ATVP) for the derivatives entities; any AFM measure or statement on perpetual-style futures sold to Dutch retail clients.
14. The client IP's geolocation (inferred as NL from Coinbase localisation only).
