# T14 — data purchase scope: what to buy, what is already free, and what to buy nothing for

**Recommendation in one line: buy nothing today.** Two of the five data-blocked candidates are
**fully unlocked by free sources that were probed live for this document**, one is unlocked but
already dead on economics, and two are not worth the spend at any price. The single best first
action is a **$0 wire of two SEC panels plus one daily cron**, and it should be preceded by an
hour-long power census, not by a purchase.

**Status.** Scoping only. Nothing was purchased, no account was created, no payment detail entered
(guardrail 1). Every "verified" row below is a live probe run on 2026-08-17 from this repository;
every price is a published list price found by search and **not** verified by transacting.

---

## 0. The two numbers that should decide the spend before any provider is discussed

**(a) The base rate. Seven candidates have been through the full frozen bar and none survived** —
T3, T7, T9, T10, T11, T12, T13 (`FINDINGS.md` §5d). A Laplace estimate of the next candidate's
pass probability is `(0+1)/(7+2) ≈ 0.11`. Any purchase argument has to survive being multiplied
by ~0.1.

**(b) The power wall, which is the one thing money can actually move — and it does not move it
far enough.** `FINDINGS.md` §5h fixed the arithmetic: certifying a true annualised Sharpe `S` at
80 % power needs **`(2.80/S)²` years of held-out data**.

| held-out window | source of that window | minimum certifiable annualised Sharpe |
|---|---|---|
| **4.6 yr** | what we hold today (2022-01 → 2026-08) | **1.30** |
| **8.6 yr** | FINRA short interest, free, 2017-12-29 → today, if the whole panel is held out | 0.955 |
| **16.6 yr** | Ortex's deepest backtest history (from 2010-01-04), if *all* of it were held out | **0.687** |

**Every remaining shortlist candidate is priced below annualised Sharpe 0.5** (`FINDINGS.md` §5h),
which needs **31.4 years** held out. **The deepest borrow-fee history that money can buy does not
reach the power this programme needs.** That is arithmetic, not a preference, and it is the single
strongest argument against any purchase on this list.

The exception is the **event-study** family, where n counts events rather than years — which is why
§5 below (PEAD) is the only candidate that survives a power census, and why its data is free.

---

## 1. What was probed, first-party, for this document

Every endpoint below was called live. Failures are recorded as failures.

| source | result | notes |
|---|---|---|
| **FINRA Consolidated Short Interest API** | ✅ **works, no key, no account** | `POST https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest`. **207 settlement dates, 2017-12-29 → 2026-07-31**, 24/yr, **median 19,527 records/date** ⇒ **≈ 4.0 M symbol-date rows**. 5,000 rows/request, `record-total` response header for pagination. Zero errors across a 207-date enumeration. |
| — its coverage | ✅ exchange-listed **and** ETFs | Verified present on the 2024-06-14 settlement date: `AAPL TSLA GME SPY TQQQ SOXL MMM ROKU VXX`. Market classes on 2024-06-14: OTC 2,232 / NYSE 839 / NNM 822 / SC 469 / ARCA 405 / BZX 136 / AMEX 97. |
| — its fields | short position (current **and** previous cycle), **average daily volume**, **days to cover**, split flag, settlement date | Everything needed for SI level, SI change, and days-to-cover. |
| **SEC EDGAR submissions API** (`data.sec.gov/submissions/CIK*.json`) | ✅ carries **8-K item codes and acceptance timestamps** | AAPL: `('8-K','2.02,9.01','2026-07-30')` with `acceptanceDateTime = 2026-07-30T20:30:28Z` = **16:30 ET, after the close**. Earnings announcement dates **and** their pre/post-session placement, universe-wide, free. |
| **SEC bulk submissions** | ✅ 1.56 GB, one download | `Archives/edgar/daily-index/bulkdata/submissions.zip`. The whole 8-K item index in one file. |
| **SEC XBRL frames API** | ✅ **4,994 entities** with `EarningsPerShareDiluted` in CY2023Q1 | `EntityCommonStockSharesOutstanding`: **4,743 entities** per quarter. Free. |
| **SEC XBRL companyconcept** | ✅ **338 EPS observations** for AAPL back to 2006, each with a `filed` date | Point-in-time-safe: the `filed` date is what a live strategy would have had. |
| **EDGAR full-text search** | ✅ works (GET, not POST), **2001 → present** | ~3,800–4,240 8-K hits/yr for `"Agreement and Plan of Merger"`. Delisted targets **are** findable: Seagen's announcement 8-K returns at `2023-03-13`. |
| — but SEC drops tickers for delisted filers | ⚠️ | `Seagen` and `Tabula Rasa HealthCare` both return `tickers: []`. **This is exactly T11's join problem, unchanged.** |
| **SEC N-PORT** (ETF net assets) | ✅ but coarse | Direxion Shares ETF Trust: `netAssets` per series per month-end, `reportDate` ∈ {01-31, 04-30, 07-31, 10-31}, filed **exactly 60 days later** (50/50 sampled filings). History from **2019-09-27**. One verified value: Daily Utilities Bull 3X, 2026-04-30, **$43,481,489.64**. |
| **iborrowdesk.com** (free public mirror of IBKR's securities-lending file) | ✅ works, **1 rolling year only** | Daily **borrow fee** + shares available, `2025-08-18 → 2026-08-14`, **259 daily points**, current to T-1, no key. **Rate-limited hard** — returns HTTP 444 after a few hundred requests; treat as a polite daily cron, not a bulk source. |
| **IBKR's own `ftp.interactivebrokers.com/usa.txt`** | ❌ unreachable from here | FTP blocked; the HTML page (`gdcdyn…index.php?f=4587`) loads but exposes no data URL. |
| **iShares holdings CSV** | ❌ **bot-block page again** (2.2 MB of HTML) | Confirms `EDGE_SHORTLIST.md` §2b. Not a transient failure. |
| **ProShares / Direxion fund data** | ❌ | ProShares CMS JSON contains no AUM or shares-outstanding field; Direxion returns 403/404 on every product path tried. |
| **Alpaca asset object** | ❌ no fee, no history | `/v2/assets/AAPL` exposes `shortable`, `easy_to_borrow`, `borrow_status` — **a live snapshot with no borrow rate and no history**, as §2b already said. |
| **Alpaca `/v1/locates/quotes`** (its own HTB rate endpoint) | ❌ **403 for this key** | Probed by the peer seat (`research/B22G_BORROW_COST.json`): the endpoint exists on the live host but returns 403 without a live/HTB entitlement, and 404 on paper. **Our own broker's borrow rates are not obtainable by us**, which is why a third-party feed is in scope at all. |

### 1a. Re-probes later the same day, while standing up the T16 collection

Two of the rows above changed within hours, so they are corrected here rather than silently left
to read as current. See `T16_FREE_PANELS.md` §4.

| source | revised result | notes |
|---|---|---|
| **iborrowdesk.com** | ❌ **now returns nothing at all from this address** | `/api/ticker/<SYM>`, `/api/home_stats`, `/api/most_expensive` and `/api/v2/coverage` all close the connection without a response (nginx **444**). The site's HTML and JS bundle still serve normally, and the API routes were re-confirmed against that bundle — so this is the rate-limit of §1 having tripped, not a moved endpoint. **The n = 65 cross-section of §2b cannot currently be grown, and the caveat in §9 about re-running it politely over several days now has no host to run against.** |
| **IBKR `ftp3.interactivebrokers.com/usa.txt`** | ❌ re-probed, still unreachable | Times out. `ViewShortableStocks.php` renders 169 kB of markup containing **no data URL**. |
| **FINRA Reg SHO daily short-sale volume** | ✅ **works, no key, no account — and it is new to this document** | `GET https://cdn.finra.org/equity/regsho/daily/CNMSshvol<YYYYMMDD>.txt`. Pipe-delimited, **~12.2k symbol rows per session**, `Date\|Symbol\|ShortVolume\|ShortExemptVolume\|TotalVolume\|Market`, with a record-count footer. **252 observations a year**, against the short-interest panel's 24. |
| — but its history is **not** durable | ⚠️ **rolling CDN retention** | Probed: `2018-07-02` → 403, `2018-08-01` → 200. Unlike the short-interest API, **a session that ages out cannot be refetched**, which makes §8a's "start now" argument literally rather than rhetorically true for this one panel. |

**What this does and does not change.** It does not revive #9: daily short *volume* is neither short
*interest* nor a borrow *fee*, and §2b's finding that the free fee proxy is anti-correlated
(ρ = −0.40) with the mechanism's variable is untouched. What it changes is §8a's *content* — the
free forward panel that was worth starting today now has a **daily** leg as well as a bi-monthly
one, and the leg it was supposed to have (borrow fee) has no reachable free source at all.

---

## 2. Candidate #9 — short-borrow-fee / hard-to-borrow signal

### 2a. The candidate is two different variables and the shortlist scored them as one

`EDGE_SHORTLIST.md` §9 scores this `D=1`. That is **half wrong**:

- **Short interest — FREE, COMPLETE, 8.6 YEARS, ALREADY BACKTESTABLE.** The FINRA panel above is
  not a proxy for anything; it is the bi-monthly consolidated short-interest file itself, with ADV
  and days-to-cover attached, covering exchange-listed names and ETFs. Combined with SEC
  `EntityCommonStockSharesOutstanding` (free, 4,743 entities/quarter) it also yields **short
  interest as a share of shares outstanding**, the standard normalisation. Design 2018–2021
  (96 settlement dates) / held out 2022–2026 (110 dates) is available today at **$0**.
- **Borrow fee — NOT free with history.** One rolling year (iborrowdesk, verified above). Nothing
  we can reach gives a backtestable fee panel without paying.

> ### ⚠️ FREE-SOURCE FLAG (the largest in this document)
> **The short-interest half of #9 needs no spend at all.** 4.0 M symbol-date rows, 207 settlement
> dates, no key, no account, verified end-to-end today.

### 2b. Two first-party measurements that correct the shortlist's own reasoning — in both directions

**(i) The shortlist's `A=2` justification is wrong for short interest.** §9 says *"the names where
it is largest are the ones Alpaca will not lend"*. Joining the 2026-07-31 FINRA file to Alpaca's
live asset flags (12,307 exchange-listed names matched):

| universe | pool shortable | **top-decile days-to-cover shortable** | bottom-decile shortable |
|---|---|---|---|
| all matched (n=12,307) | 40.9 % | **54.6 %** | 8.2 % |
| ADV ≥ 200k shares (n=4,824) | 74.7 % | **83.6 %** | 22.8 % |
| **ADV ≥ 1M shares (n=2,432)** | 80.6 % | **89.7 %** | 16.9 % |

In a liquid universe, **90 % of the most-shorted decile is shortable at our broker.** The
executability objection does not apply to the short-interest form of the candidate.

**(ii) And it is right for the borrow fee — which is a reason not to buy the fee.** On a random
liquid cross-section joined to the free IBKR mirror (**n = 65 only** — the site rate-limited us to
HTTP 444 before the sample could be grown; treat this as *indicative*, not as a measurement to
bank):

| | |
|---|---|
| Spearman ρ (days-to-cover, borrow fee) | **−0.40** |
| median fee, top-decile days-to-cover | 0.36 %/yr |
| median fee, **bottom**-decile days-to-cover | **55.5 %/yr** |
| names with fee ≥ 1 %/yr | 16 (24.6 %), **25 % shortable at Alpaca** |
| names with fee ≥ 5 %/yr | 6, **0 shortable at Alpaca** |

**Independently corroborated by the peer seat, on a different universe and a different data route.**
`research/B22G_BORROW_COST.json` (2026-08-16, the 100-name ORB most-actives pool, IBKR rates via a
different republisher) measures the same split from the other side: **median indicative borrow fee
0.33 %/yr on Alpaca-ETB names against 10.28 %/yr on Alpaca-HTB names** (p90 123.23 %, max
259.96 %), and **every hard-to-borrow name in that pool is also `shortable=False` at Alpaca**. Two
seats, two universes, two republishers, one conclusion: **the fee and the broker's willingness to
lend are the same variable, and the free short-interest panel is not it.**

**One correction the peer seat makes, and it cuts the other way — record it before drawing the
conclusion.** `shortable=False` at Alpaca means *this broker will not locate it for this account*.
It does **not** mean the borrow is impossible: of B22G's 11 HTB names with an obtainable IBKR rate,
**7 had shares available to borrow at 2.32 %–259.96 %/yr**. They are expensive, not unborrowable.
So the executability objection below is a **broker constraint, not a market fact**, and it is
removable — by changing broker, which is an owner call and not a data purchase.

Two consequences, and they point the same way:

1. **The free panel is not a cheap substitute for the paid one.** Short interest and borrow fee are
   *anti*-correlated in this sample. Days-to-cover is high where borrowing is easy and volume is
   large; the fee is high where float is tiny and borrow is scarce. **Buying Ortex would not confirm
   a free result — it would test a different hypothesis.** That is an argument for honesty in the
   pre-registration, not for the purchase.
2. **The fee signal is unexecutable at *this* broker.** Zero of the six names with a fee ≥ 5 %/yr
   were shortable; B22G's 100-name pool says the same. D'Avolio's effect lives precisely in that
   tail. **We would be buying a signal on names our broker will not lend, and the fee itself is the
   price of the edge — you pay it.** Per the correction above, a broker change would convert the
   constraint into a cost of 2 %–260 %/yr; whether that is worth doing is an owner call that should
   be settled *before*, not after, a data purchase predicated on it.

### 2c. Providers and cost tiers (published prices, not verified by transacting)

| provider | what it gives | history | approx. cost | verdict |
|---|---|---|---|---|
| **FINRA Consolidated Short Interest API** | short interest, ADV, days-to-cover, bi-monthly | **2017-12-29 →** | **$0** | ✅ **wire this** |
| **iborrowdesk (IBKR mirror)** | daily borrow fee + availability | **1 rolling year** | **$0** | ✅ wire as a *forward* cron |
| **IBKR securities-lending API** | fee rate + shortable shares, live | **none** (snapshot) | $0 with a funded IBKR account; market-data fees may apply | ⚠️ no history ⇒ no backtest |
| **Ortex** Basic | delayed short interest | platform | **$49/mo, $39/mo annual (~$468/yr)** | ✗ delayed SI is what FINRA already gives free |
| **Ortex** Advanced | real-time SI, **cost-to-borrow**, utilisation, backtester **from 2010-01-04** | **16.6 yr** | **$149/mo, $99/mo annual (~$948/yr)** | ⚠️ the only defensible line item on this whole list — and it still fails §0(b) |
| **Ortex API** | programmatic CTB/SI history | 16.6 yr | **from $499/mo (~$5,988/yr)** | ✗ |
| **S3 Partners BLACK App** | real-time SI, financing rates, 65,000+ securities | deep | **no public price**; institutional, distributed via Bloomberg/LSEG/Eze | ✗ ask-for-quote is itself a signal about the tier |
| FIS Astec / S&P Global (ex-IHS Markit) Securities Finance | the institutional lending tape | deep | five figures/yr, enterprise contracts | ✗ |

> **A purchase risk to settle BEFORE any spend, and one this document could not settle without
> transacting:** Ortex's public pricing page lists the two tiers and their prices but **does not
> state which tier permits historical export**. The backtester is described as a platform feature.
> If the $948/yr tier is in-platform only and programmatic history requires the **$5,988/yr** API
> tier, the cost of this candidate is **6.3× the headline**. Ask Ortex directly before buying.

### 2d. Verdict on #9

**Do not buy.** Wire the free short-interest panel and start a free daily borrow-fee cron. The
paid fee panel buys (i) a signal that is anti-correlated with the free one, (ii) on names our
broker will not lend — a constraint that a **broker decision**, not a data purchase, would have to
lift first, and (iii) whose deepest available history still cannot certify the Sharpe we would
expect. Three independent reasons, any one of them sufficient.

**And there is a sequencing point hidden in (ii) that matters more than the price.** If the owner
wants this candidate alive, the first fork is *"do we move the short leg to a broker that will
lend these names?"* — because buying a 16.6-year fee panel to trade names Alpaca refuses is paying
for a signal we cannot act on. **Settle the broker question first; the data question is downstream
of it.**

---

## 3. Candidate #7 — merger-arb announcement dates

### 3a. EDGAR is a genuine free unlock, and it fixes both of T11's data defects

`T11_RESULT.md` §6 measured Benzinga headline recall at **17.5 % (strict) / 52.5 % (loose, with a
~1-in-3 false-positive rate)**. EDGAR does far better in principle:

- The **target itself** files the announcement 8-K (item 1.01 *Entry into a Material Definitive
  Agreement*, usually with 8.01), and then SC 14D9 / DEFM14A. Verified: Seagen's 8-K on
  **2023-03-13** is the announcement date; Horizon Therapeutics, Activision Blizzard and Tabula Rasa
  all return their own filings by company name.
- EDGAR full-text search runs **2001 → present** with ~4,000 8-K merger-agreement hits/yr.
- **Crucially, EDGAR also contains the deals that BROKE.** `T11_RESULT.md` §6 records that
  `/v1/corporate-actions` *"contains only deals that COMPLETED… the left tail is not rare in this
  dataset, it is structurally absent."* An 8-K announcing a merger agreement exists whether or not
  the deal ever closed. **EDGAR is the only free source that can measure T11's break rate
  first-party**, and T11 §9 explicitly flags that the 5–10 % band it used was *"a declared
  sensitivity, not a measurement."*

### 3b. The work it still costs, stated honestly

The join key is the **target's CIK**, and the corporate-actions feed gives a **ticker**. SEC drops
tickers for delisted filers (verified: Seagen `tickers: []`). So a ticker→CIK bridge for delisted
names must be built — from cover-page inline-XBRL `dei:TradingSymbol` in each target's last 10-Q
(mandatory for all filers from mid-2021, large accelerated from mid-2019), or from archived
snapshots of `company_tickers.json`. Deterministic and free, but it is **days of work, not hours**,
and it is the same join T11 already broke on.

### 3c. Verdict on #7

**Do not buy, and do not do the free work either — with one narrow exception.**

`T11_RESULT.md` is unambiguous: the candidate **loses at zero transaction cost** (−0.776 %/event),
across a friction ladder spanning 20 bp on an 83 bp loss, and the cleanest 317-deal subset earns
**+6.66 %/yr over T-bills against a break-even break rate of 6.68 %** — inside the 5–10 % band it
must survive. **Better announcement dates do not rescue a candidate that dies on economics.** Recall
was never the binding constraint.

*The narrow exception:* if the owner wants the break-rate band replaced by a first-party
measurement — the one number T11 declared as an assumption — EDGAR is the free way to get it, and it
would settle the candidate permanently rather than provisionally. That is a **worth-knowing**
question, not a **worth-trading** one, and it should be scoped as such. Commercial M&A feeds
(Refinitiv/LSEG Deals, Bloomberg MA, Dealogic) are five-figures-a-year enterprise products and are
categorically out of scope for a $100k account.

---

## 4. Candidate #10 — LETF AUM / flows

**Exact data required:** daily assets under management (or shares outstanding × NAV) per leveraged
ETF, to size the mandated end-of-day imbalance `(L² − L) × AUM × r`.

**Free source, and why it is not enough.** SEC **N-PORT** gives `netAssets` per ETF series, verified
on a Direxion filing. But it is **month-end values at a quarterly filing cadence with an exactly
60-day publication lag**, back to 2019-09-27. A leveraged sector ETF's AUM can double inside 60
days; a 60-day-stale quarterly snapshot is a poor scaling factor and interpolating forward would
inject lookahead. Issuer routes are closed: **iShares returns a bot-block page (re-confirmed
today)**, ProShares' CMS JSON carries no AUM field, Direxion returns 403/404.

**Paid alternatives:** ETF-analytics vendors (ETFGlobal, FactSet/ETF.com data, Nasdaq Data Link ETF
products) — mid-four to five figures a year for institutional feeds; no retail tier was found that
provides *historical daily* shares outstanding across the LETF complex.

**Verdict: do not buy.** Beyond cost, the candidate is **partially pre-refuted by our own prior
work** — B22E's largest-|r1| tercile, i.e. the days when index-level rebalance flow is largest, was
the *worst* performer (−3.77 %/yr, t −1.04) — and Ivanov & Lenkey (2014) find secondary-market flows
substantially offset the mechanical imbalance. It scores 10/20 on the shortlist. **Paying four
figures to test a candidate our own data already leans against, at the wrong data frequency, is the
worst line item on this list.**

---

## 5. Candidate #12 — PEAD

> ### ⚠️ FREE-SOURCE FLAG — and the shortlist's `D=2` for this candidate is simply wrong
> **PEAD needs no analyst estimates and therefore needs no purchase at all.**

### 5a. Both missing pieces are free, and both were verified today

1. **Announcement dates, to the minute.** 8-K **item 2.02** (*Results of Operations and Financial
   Condition*) is the earnings release, and `data.sec.gov/submissions/` carries the item code
   **and** `acceptanceDateTime`. AAPL's four most recent are stamped `20:30 UTC` = **16:30 ET** —
   after the close. That is enough to classify every announcement as pre-open, intraday or
   post-close **without a single timing assumption**, which is precisely the discipline T3 and T10
   both failed at first pass (`FINDINGS.md` §5e, §5h). The whole index is one 1.56 GB download.
2. **The surprise, without I/B/E/S.** The **original** PEAD definition (Foster, Olsen & Shevlin
   1984) computes SUE from a **seasonal random walk on reported earnings** — actual EPS this
   quarter minus actual EPS four quarters ago, scaled by the standard deviation of that series.
   **No analyst estimate is involved.** SEC XBRL supplies exactly this: 4,994 entities per quarter
   in the `EarningsPerShareDiluted` frame, and per-company series back to 2006 **each tagged with
   its `filed` date**, so the panel is point-in-time by construction.

Analyst-consensus SUE is the *modern* variant, not the canonical one. If it is ever wanted, the
cheap tier is Financial Modeling Prep (published range ~$29–$99/mo depending on tier, with an
earnings-surprise endpoint) — but it should be a **second** trial declared in advance, not a
prerequisite, and buying it before the free version has been tested inverts the ordering.

### 5b. Power — and PEAD is the only data-blocked candidate that survives a census

The shortlist's own `E=2` deserves re-examination against our **measured** friction, per its §3
rubric:

- A top-500-ADV universe generates **≈ 2,000 earnings events/yr** ⇒ **≈ 9,200 held-out events**
  over 2022-01 → 2026-08.
- At a per-event 60-day dispersion of 10–18 % (T9 measured **15.5 %** for a far noisier
  instrument), the event-level MDE at 80 % power is **0.29 %–0.53 %** — *below* the decayed
  large-cap PEAD effect the literature reports. **Contrast T9, whose MDE was 5.51 % against a
  2.40 % literature effect and which therefore died before it was tested.**
- Friction is not the binding constraint here either: our measured top-500 half-spread is
  **1.13–1.43 bp** (`FINDINGS.md` §5e), and a 60-day-hold decile book turns roughly 4× a year, so
  charged friction is on the order of **11 bp/yr** against a decile spread plausibly in the
  hundreds of bp.

> **The honest qualifier, and it is why the first action is a census and not a harness.** The
> event-level MDE treats 9,200 events as independent. **They are not** — they cluster into four
> earnings seasons a year, so the effective number of independent blocks is far smaller, and the
> portfolio-Sharpe framing of §0(b) would give a much harsher answer. The two framings disagree,
> the truth is between them, and **resolving that is an hour of arithmetic with a block bootstrap,
> not a backtest.** `FINDINGS.md` §5g's earned rule applies verbatim: *count the events before
> building the harness.*

### 5c. What holds it down, stated without decoration

`U=1`. It is the most-studied anomaly in the literature, Chordia, Goyal & Sadka document its decay
in liquid names, and the shortlist ranks it **12th of 13**. A free test of a famous decayed anomaly
is most likely an eighth honest negative. **The case for it is not that it will work — it is that
it is the only remaining candidate that clears a power census, and it costs nothing.**

**Rescored on the shortlist's own rubric:** `U=1, E=3 (was 2 — friction is 36× smaller than the
literature effect on our measured spreads), A=4, D=5 (was 2 — the data is free and complete)`
⇒ **13, up from 9**. That moves it above #7, #8, #9, #10, #11 and #13 and below the four already
dead. **The re-score is a correction of a data-availability error, not a promise.**

---

## 6. Candidate #13 — index reconstitution membership history

**Exact data required:** point-in-time index membership with announcement and effective dates.

**Free route:** reconstructible from N-PORT holdings of IVV/VOO — but at the same **quarterly,
60-day-lagged** cadence as §4, which is useless for an event study keyed to an effective date.
Direct scrapes remain closed: iShares bot-blocked (re-confirmed), SSGA 301, Wikipedia's changes
table absent from the static HTML.

**Paid:** S&P Dow Jones Indices membership history and the equivalent CRSP/Compustat index
constituent files are academic/institutional licences, four to five figures a year.

**Verdict: do not buy, and do not do the free work.** Greenwood & Sammon (*The Disappearing Index
Effect*) document the S&P addition premium falling from ~7 % in the 1990s to approximately **zero**.
**The null is already close to accepted in the literature.** It scores 7/20 — last — and it should
stay there. This is the clearest "no" on the list.

---

## 7. The ranking, by expected value per dollar

`P(pass)` starts from the base rate of §0(a) (≈0.11) and is adjusted for what we now know. These
are **priors, not statistics** — the same disclaimer `EDGE_SHORTLIST.md` §7 attaches to its own U
and E scores.

| rank | candidate | data verdict | annual cost | P(pass) | EV per dollar |
|---|---|---|---|---|---|
| **1** | **#12 PEAD** | **FULLY UNLOCKED, FREE** — 8-K item 2.02 + XBRL SUE, both verified | **$0** | ~0.08 (famous, decayed — but the only one that clears a power census) | **undefined / infinite — the denominator is zero** |
| **2** | **#9 short *interest*** (the free half) | **FULLY UNLOCKED, FREE** — 207 dates, 4.0 M rows, verified | **$0** | ~0.05 (the mechanism's variable is the *fee*, and ρ(SI, fee) ≈ −0.40) | **undefined / infinite** |
| **3** | **borrow-fee *forward* panel** | free daily cron, builds a proprietary panel from today | **$0** | n/a — it is an option, not a test | **high; it is the only way to own history that does not exist yet** |
| 4 | #7 **break-rate census** via EDGAR | free, but days of ticker→CIK work | $0 + engineering | n/a — settles a dead candidate, does not revive it | low |
| 5 | #9 borrow **fee**, Ortex Advanced | 16.6 yr, but §0(b) says 16.6 yr certifies only Sharpe 0.687 | **~$948/yr** (⚠️ possibly ~$5,988/yr if export needs the API tier) | ~0.05, and **0 of 6 high-fee names are shortable at our broker** | ≈ 5 × 10⁻⁵ /$ |
| 6 | #10 LETF AUM | free source is 60-day-lagged quarterly; issuer routes bot-blocked | four figures/yr | ~0.03 — **partially pre-refuted by our own B22E** | ≈ 2 × 10⁻⁵ /$ |
| 7 | #13 index membership | free route too coarse; paid route institutional | four–five figures/yr | **~0.01 — the literature has already accepted the null** | ≈ 1 × 10⁻⁶ /$ |

**Read the table's top three rows as the finding.** The two candidates whose data is free are the
two whose data-availability score in `EDGE_SHORTLIST.md` was wrong. **The wallet was opened for a
problem that, for the two best-scoring blocked candidates, does not exist.**

---

## 8. Recommendation

### 8a. The single best first action — and it is free

> **Wire the two SEC panels and start the borrow-fee cron. Then run a one-hour power census on
> PEAD before writing a line of harness.**
>
> 1. `submissions.zip` (1.56 GB, one download) → every **8-K item 2.02** with its
>    `acceptanceDateTime` ⇒ a universe-wide earnings-announcement calendar with pre/post-session
>    placement, no timing assumption.
> 2. XBRL `EarningsPerShareDiluted` per CIK, keyed on `filed` ⇒ a **point-in-time** seasonal-
>    random-walk SUE panel. **No analyst estimates, no purchase.**
> 3. A daily cron on the free IBKR borrow-fee mirror (politely — it rate-limits to HTTP 444) and on
>    the FINRA short-interest API. **History that does not exist can only be created by starting
>    now**; in twelve months this is a panel nobody sells at a retail price.
> 4. **The census first, the harness second.** Count the events, block-bootstrap the earnings-season
>    clustering of §5b, and compare the MDE to the literature's own effect size. If the MDE exceeds
>    it, PEAD is dead before it is tested and we have spent an hour — which is exactly the T9 lesson
>    (`FINDINGS.md` §5g) applied *before* the mistake instead of after.

Properties that make this the right first move, mirroring the M0 argument in `EDGE_SHORTLIST.md`
§6: it is bounded, it costs nothing, it is a **measurement rather than a search** so it carries no
multiple-testing exposure, and **either outcome is worth having** — a failed census kills the
last free candidate for an hour's work, and a passed census hands us the only powered test left.

### 8b. If the owner wants to spend anyway

**One line item, and it is not recommended:** **Ortex Advanced, annual, ≈ $948/yr.** Before paying,
confirm in writing that this tier exports cost-to-borrow history programmatically — if that needs
the API tier, the true cost is **≈ $5,988/yr**. And go in knowing the three measured objections of
§2: the fee is anti-correlated with the free short-interest variable, **0 of 6 names with a fee
≥ 5 %/yr were shortable at our broker**, and 16.6 years of history certifies only annualised Sharpe
**0.687** against candidates priced below **0.5**.

**And do not buy it before the broker fork of §2d is settled** — a fee panel bought to trade names
this broker refuses to lend is money spent on an unactable signal.

**Spend nothing on #10 or #13 at any price.**

### 8c. And the honest competing claim on the same budget

**This purchase is not the highest-value open item, and the highest-value one is also free.**
`FINDINGS.md` §10 ranks **M0's C4** — whether an MOC/MOO order actually fills at the official
closing print — first, unperformed, "the cheapest measurement in the programme", and now
**load-bearing for five dead candidates**, worth **1,414 bp/yr** to T10 alone. It costs a fortnight
of paper orders and zero dollars. **If a single slice is available, C4 has a better claim on it
than anything in this document.**

---

## 9. What this document does not claim

- **No candidate was tested here, and none should be read as revived.** T11 is dead on economics at
  zero cost; nothing about announcement dates changes that.
- **Every price is a published list price found by search.** None was verified by transacting, none
  should be, and the Ortex export-tier ambiguity of §2c is a real unresolved cost risk.
- **The borrow-fee cross-section is n = 65 and is labelled indicative throughout.** The free mirror
  rate-limited this session to HTTP 444 before the sample could be grown. It is suggestive of a
  negative correlation and of the shortability problem; it is **not** a measurement to bank, and it
  should be re-run politely over several days before it carries weight in any decision.
- **The shortability join is a single-date snapshot** (2026-07-31 short interest against live
  Alpaca flags). `easy_to_borrow` has **no history** (§2b), so this cannot be made point-in-time and
  a backtest of #9 would have to assume today's shortability applied in the past — a real,
  unfixable weakness of the free route that must be declared in any pre-registration.
- **The `P(pass)` column of §7 is a prior, not a statistic**, and the EV-per-dollar ordering inherits
  that.
- **The peer seat's `research/B22G_BORROW_COST.json` is cited, not re-derived**, and its own
  coverage caveat travels with it: it obtained an IBKR rate for **25 of 100** names before its
  republisher bot-blocked the host, and it labels the uncovered symbols *unknown, not zero*. The
  agreement between its numbers and §2b's is agreement between two partial samples, which is worth
  more than either alone and less than a census.
- **Nothing here authorises a purchase, a subscription, or real-money execution.** Both remain
  owner-gated.

---

*All endpoint probes in §1 were run on 2026-08-17 from this repository. No paid account was created,
no subscription entered, and no payment detail supplied. The Alpaca calls were read-only queries
against `/v2/assets`; no order was placed.*

**2026-08-27 addendum — free options-implied borrow is NOT a substitute.** Put-call-parity implied dividend-plus-borrow on the
free DoltHub EOD chains (51 mega-caps, 2020–26) has a cross-sectional IQR of ~2.1 %/yr against a quote-noise floor of ~1.5 %/yr
(ratio 1.4; measurability bar 2). The panel also has no chains for the preferred series where borrow decides the RV. The
borrow-availability feed remains a paid ask. `research/trading_bot/INVENT_2026-08-27_parity.md` §3.
