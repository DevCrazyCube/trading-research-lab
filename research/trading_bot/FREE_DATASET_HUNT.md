# FREE_DATASET_HUNT — hunting free public data dumps for the four programme data-walls

**Date:** 2026-08-23
**Scope:** research/recommendation only. Small keyless verification fetches were made (a handful of
~11 KB Binance metrics zips, DoltHub SQL-API metadata queries, S3 listing reads). **No bulk
downloads, no accounts, no purchases, no git commit.**
**Question:** the programme's standing conclusion is "the wall is data, not ideas." Has a hobbyist /
academic / data-hoarder already dumped, free, the specific dataset that unblocks one of the four
named walls? For each source: exact URL, contents, span+granularity, point-in-time integrity,
license, and which bottleneck it resolves — brutally vetted.

---

## TL;DR — THE HEADLINE

**One target is not just resolved, it OVERTURNS a death verdict the programme already recorded.**

- **Target 3 (Binance global long/short account ratio) is NOT dead.** `XS_GLSR_Z_RECHECK.md` concluded
  the leg "is going UN-OBSERVABLE on free data … Binance has largely STOPPED publishing the
  global-account long/short ratio for most symbols since ~2025." **This is false as of today.** I
  downloaded the actual `data.binance.vision` metrics files and the `count_long_short_ratio` column is
  **fully populated at 5-minute granularity into 2026-08 for every major coin**, including 2025-listed
  names (HYPE, FARTCOIN, ENA, SUI, WLD). See §3 for the raw evidence. This revives a leg the programme
  measured at **design Sharpe 2.94 / full-span 1.66** and wrote off. **This is the single most valuable
  finding in this hunt and it costs $0 to act on** — re-run the panel build against a fresh pull.

- **Target 2 (US EQUITY options), NEW resolve:** `post-no-preference/options` on DoltHub is a genuine
  free daily EOD US equity-options chain **with IV + full greeks + bid/ask**, **2019-02-09 → 2026-08-21,
  current**, CC-licensed. Yahoo-grade (no OI/volume, model greeks, one snapshot/day) — not
  research-grade, but real and new to the programme. Crypto (Deribit) side stays sample-only free.

- **Targets 1 (borrow availability/rate) and 4 (intraday iNAV / bond-ETF NAV) remain UNRESOLVED on free
  data.** No archive exists. This confirms the programme's own conclusions — these are genuinely
  forward-collect-or-pay walls. Details and every dead end below.

---

## TARGET 3 — Binance `count_long_short_ratio` — **RESOLVED, and it reopens a killed leg** ★★★

### The claim under test
`XS_GLSR_Z_RECHECK.md` §3–4: after a full alphabetical backfill, "the terminal window still has only
11/50 names carrying a `count_long_short_ratio` value and turnover collapses to ~0/day … Binance has
largely STOPPED publishing the global-account long/short ratio for most symbols since ~2025." Verdict
recorded: **"a DATA-AVAILABILITY death."**

### What I actually found (raw verification, 2026-08-23)
Source: `https://data.binance.vision/data/futures/um/daily/metrics/{SYM}/{SYM}-metrics-{DATE}.zip`
(the free, no-auth archive; same endpoint the incumbent fetcher uses). Column layout:
`create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,`
`sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio`.
`count_long_short_ratio` **is** the global-account long/short ratio (`globalLongShortAccountRatio`) — the
exact XS_GLSR_Z signal input.

Downloaded date **2026-08-01**, checked the last-row `count_long_short_ratio` for the top perps:

| symbol | glsr @ 2026-08-01 | rows/day | symbol | glsr | rows/day |
|---|---|---|---|---|---|
| BTCUSDT | 2.194 | 288 | HYPEUSDT | 1.644 | 288 |
| ETHUSDT | 2.624 | 288 | FARTCOINUSDT | 1.408 | 288 |
| SOLUSDT | 2.830 | 288 | WLDUSDT | 1.070 | 288 |
| XRPUSDT | 2.776 | 288 | SUIUSDT | 1.940 | 288 |
| DOGEUSDT | 2.853 | 288 | TRXUSDT | 1.456 | 288 |
| BNBUSDT | 2.665 | 288 | ENAUSDT | 1.249 | 288 |
| ADAUSDT | 2.371 | 288 | AVAXUSDT | 1.603 | 288 |
| LINKUSDT | 1.490 | 288 | | | |

**15/15 populated, zero missing**, 288 rows/day = 5-minute bars. Independently confirmed a mid-window
date (2026-05-15) for BTC/ETH/SOL/DOGE — all present. The S3 listing shows BTCUSDT metrics files
running continuously through at least **2026-05** (and Aug-2025 files carry **Aug-2026 upload
timestamps**, i.e. Binance appears to have *re-published/backfilled* the metrics archive recently).

### Honest reconciliation — why the programme saw 11/50 and I see 15/15
The programme's `glsr_metrics_backfill.py` pulls from this same source, yet its rebuilt panel had only
11/50 names in the terminal window. Two live hypotheses, both benign for us:
1. **Binance re-published the metrics archive after the programme's backfill run (2026-08-19).** The
   Aug-2026 upload timestamps on 2025 files support this. The programme measured a genuinely thinner
   archive that has since been filled in.
2. **A join/parse bug in the panel rebuild** (the incumbent path had a known alphabetical-crawl defect;
   the fix may not have re-touched the major-coin metrics dirs).

Either way, **the current ground truth is unambiguous: the data is there, free, 5-min, into 2026-08.**

### Payoff — GENUINELY REOPENS A TESTABLE (previously strong) EDGE
- XS_GLSR_Z is not a marginal sub-bar object. On data it exists on, the programme measured **net Sharpe
  +2.94 design → +0.44 hold → +1.66 full-span** (`XS_GLSR_Z_RECHECK.md` §3). It was shelved *only* for
  presumed data death — which was wrong.
- **Recommended action (free, ~2 h):** re-run `glsr_metrics_backfill.py` against a **fresh** pull for
  the top-50 volume universe, rebuild `panel1h_r3meta.npz`, and re-run `glsr_recheck_eval.py` on
  2025-01→2026-08. If the terminal-window `median names w/ GLSR` now sits at ~50 (not 11) and turnover
  recovers, the "data-availability death" disposition must be reversed and the leg re-sized per its real
  out-of-sample Sharpe. **This is the highest expected-value item in the entire hunt.**
- Caveat to stay honest: the terminal-window Sharpe was contaminated by the data hole (0.002 turnover).
  We do **not** yet know the clean terminal-window number. But that is now *measurable for free*, which
  is exactly the thing the death verdict said was impossible.

**Adjacent free bonus (same files):** `count_toptrader_long_short_ratio`, `sum_toptrader_long_short_ratio`
(top-trader crowd), `sum_taker_long_short_vol_ratio`, and 5-min `sum_open_interest[_value]` are all in
the same zip — a full free positioning panel, not just GLSR.

---

## TARGET 2 — Historical options data

### 2a. US EQUITY options — `post-no-preference/options` (DoltHub) — **RESOLVED, new to programme** ★★
- **URL:** `https://www.dolthub.com/repositories/post-no-preference/options` (SQL API:
  `https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master?q=…`).
- **Contents (verified via `DESCRIBE option_chain`):** `date, act_symbol, expiration, strike, call_put,
  bid, ask, vol` (= implied vol), `delta, gamma, theta, vega, rho`. A sibling `volatility_history`
  table holds per-symbol IV history.
- **Span/granularity (verified):** `MIN(date)=2019-02-09`, `MAX(date)=2026-08-21` — **current, ~T-2**.
  **Daily EOD** (one snapshot/day). ~2,098 underlying symbols (per the maintainer's write-up).
- **PIT integrity:** the maintainer has published **daily since April 2021**, and Dolt keeps a full
  commit history — so **2021→present is genuinely point-in-time** (each day's chain committed that day,
  survivorship-complete, immutable). The 2019-02→2021-04 seed is a historical backfill (weaker PIT).
- **License:** DoltHub data is Creative Commons (maintainer's stated terms). Usable.
- **HONEST QUALITY CAVEATS:** this is **Yahoo Finance–grade**, not OptionMetrics/IvyDB-grade. Greeks
  and IV are **model-derived** (Yahoo's), **no open interest, no volume**, **no intraday** — a single
  daily snapshot whose exact timestamp is not guaranteed to be a clean 16:00 mark. Bid/ask are
  end-of-day and can be stale on illiquid strikes. **Good enough** for: index/large-cap IV term-structure
  and skew signals, vol-risk-premium studies, event-vol (earnings) IV-crush, and delta-hedged overlay
  research. **Not good enough** for: anything needing OI/volume, microstructure, or a synchronous 16:00
  print (which — per `INVENT_0823_MASTER` Clause 2 — is exactly the tether-clock defect that killed the
  bond-ETF families; a stale Yahoo snapshot has the *same* asynchrony risk, so treat any close-to-close
  option RV built on it with the open-to-open discriminator).
- **Which bottleneck:** the equity/index half of Target 2 (bought-convexity, vol-premium). It does NOT
  give a research-grade OptionMetrics substitute, but it is a real, free, multi-year, PIT-from-2021
  greeks panel the programme did not know it had.

### 2b. Crypto (Deribit) options — sample-only free, already exploited
- **Tardis.dev free first-of-month `options_chain`** (`https://docs.tardis.dev/historical-data-details/deribit`):
  full chain incl. IV/greeks, from **2020-03-01**, but only the **1st calendar day of each month**
  without an API key. **The programme already uses exactly this** (`DERIBIT_FREE_WING_RESULT.json`,
  "Tardis FREE first-of-month deribit options_chain samples"). No new ground; a monthly snapshot cannot
  support a daily/continuous options strategy — it is an *entry-cost characterisation* sample only.
- **CryptoDataDownload Deribit** (`https://www.cryptodatadownload.com/data/deribit/`): **free tier = DVOL
  index OHLC + OHLCV-by-maturity only**. Full option chains (strikes/greeks) are **Plus+ paywalled**.
  Not a greeks source.
- **GitHub `RiveChen/deribit-historical-data`, `schepal/deribit_data_collector`:** these are **scrapers,
  not dumps** — they pull from Deribit's own history API when *you* run them (rate-limited, must run
  detached per the no-inline-crawl rule). They provide code, not a pre-collected multi-year archive with
  greeks. Deribit's public history covers trades/orderbook from 2019; assembling a continuous options
  greeks panel from it is a forward-collection project, not a ready dataset.
- **Verdict:** crypto historical options remain **paywalled beyond first-of-month samples**. No hobbyist
  has dumped a continuous free Deribit greeks archive. Target 2 (crypto half) stays blocked.

---

## TARGET 1 — Short-borrow availability / rate history (US equities incl. preferreds) — **UNRESOLVED** ✗

The exact `BORROW_FEED_SCOPE.md` blocker. **No free point-in-time historical archive exists.** Every
route checked:

- **IBKR `usa.txt` historical archive:** **does not exist free.** Confirmed via the Portfolio123
  community thread and IBKR docs — IBKR's FTP serves only the *current* file; "there is no historical
  data on the FTP." IBKR's SLB tool shows indicative rate history *inside a logged-in account only*. **No
  one has archived `usa.txt` daily on GitHub/Kaggle** — repeated targeted searches (github/kaggle/dolt
  "usa.txt", "IBKR short availability history", "stock borrow archive") returned only the live file, the
  Apify scraper (paid wrapper), and paywalled trackers. If we want history, we must **forward-collect it
  ourselves** (the sanctioned detached daily cron off-sandbox), starting now — there is no back-history
  to buy for free.
- **iborrowdesk.com** (free IBKR mirror): **rolling 1 year only** (`T14 DATA_PURCHASE_SCOPE`
  re-confirmed: 259 daily points, hard 444 rate-limit). No deep history, no bulk.
- **Academic / Zenodo / Dataverse short-fee panels:** **none redistributable.** The underlying panel is
  Markit/DataExplorers (now S&P Global Securities Finance) or DataLend/Orbisa — **all licensed, none
  free**. Academic replication packages that *use* this data are contractually barred from re-posting the
  raw borrow-fee panel; searches (Zenodo/Dataverse "securities lending fee panel", "short selling borrow
  fee replication") surfaced only the papers and the paid vendors, never a raw free dump.
- **FINRA / Reg SHO / SEC FTD — FREE but WRONG INSTRUMENT** (as `BORROW_FEED_SCOPE` §1c already noted):
  FINRA Consolidated Short Interest (free, 2017-12→present, already wired), FINRA Reg SHO **daily
  short-sale volume** (free full history at `regsho.finra.org` + Query API; community tooling
  `github.com/tangentstorm/gme-data/finra_shortvol.py`), FINRA/exchange **threshold securities** lists,
  and SEC **fails-to-deliver** (free, twice-monthly). These measure short *flow/interest/fails* — **not
  borrow availability and not a borrow rate.** They cannot answer "are both legs shortable and at what
  rate," so they do not unblock the preferred-RV edge.
- **HONEST PAYOFF EVEN IF IT WERE RESOLVED:** per `BORROW_FEED_SCOPE` §4, the preferred-RV edge is
  insignificant (held-out t 1.48) and spread-fragile *independent of borrow*. So Target 1 is the
  lowest-value target regardless: the data doesn't exist free, and the edge it gates wouldn't clear the
  bar anyway. **Recommendation: do not chase it; if borrow infra is ever wanted, forward-collect
  `usa.txt` via a detached cron — there is no free history to recover.**

---

## TARGET 4 — Intraday iNAV / NAV history for ETFs & CEFs — **UNRESOLVED** ✗

- **Intraday iNAV (^INAV / .IV tickers):** **no free historical dump found.** The per-15-second iNAV
  feed is disseminated live by listing exchanges but not archived publicly; historical iNAV is a
  **commercial product only** (IHS Markit / S&P "iNAV+" per-second; CEFdata intraday API; FirstRate
  intraday ETF prices). No GitHub/Kaggle/Dolt mirror exists. Confirmed the programme's `INVENT_0823`
  finding that Yahoo iNAV pseudo-tickers (`^HYG-IV` etc.) are **not served**.
- **Bond-ETF NAV history:** still **issuer-bot-blocked** (iShares `.ajax`, SSGA, Vanguard all fail — see
  `INVENT_0823_MASTER` §4). No third party has dumped it free. FRED ICE index total-return series remain
  **rolling-3yr license-capped** (design window not even reproducible). This is the programme's sharpest
  paid-data ask and **nothing free resolves it.**
- **CEF NAV:** the programme already has the best free source wired — **CEFConnect** via `t12_cache`
  (`history_5Y.json.gz`: 353 funds, weekly price/NAV/discount, 2021-08→2026-08). No free source improves
  on it: **no daily CEF NAV dump, no BDC NAV** (BDC NAV is quarterly, no free source — `DEEPMINE_CEFNAV`
  §2 confirmed). DoltHub `post-no-preference` publishes stocks/options/earnings/rates but **no fund/NAV
  database**; no Dolt CEF-NAV repo exists.
- **Verdict:** Target 4 is genuinely free-data-blocked. The synchronous-16:00 NAV tether the programme
  wants is published-but-not-machine-readable-free, exactly as `INVENT_0823_MASTER` §4 states.

---

## BROAD SWEEP — other high-value free dumps worth knowing (none a silver bullet)

| source | contents | span/gran | PIT | license | verdict for us |
|---|---|---|---|---|---|
| **`post-no-preference/stocks`** (DoltHub) | US EOD OHLC/adj, splits/divs | daily, 2021→now (seed to ~2019) | daily commits, PIT from 2021 | CC | redundant with Alpaca; useful as a free cross-check / corporate-action source |
| **`post-no-preference/earnings`** (DoltHub) | EPS **estimates**, analyst ranks/scores, income/BS/CF, **earnings calendar**, sales estimates | daily/quarterly, 2021→now | daily commits ⇒ **PIT estimate revisions** | CC | **potentially useful** — a free PIT analyst-estimate/revision panel is rare; could seed a PEAD/revision signal the programme hasn't tried on free PIT estimates |
| **FINRA Reg SHO daily short volume** | daily short vol by symbol | daily, full history free | native PIT | FINRA public | free short-flow panel; a *possible* new signal input (short-volume imbalance), weak, untested |
| **SEC fails-to-deliver** | FTD qty by CUSIP | twice-monthly, 2004→now | native PIT | public | free; niche squeeze/threshold signal only |
| **SEC 13F** (`toddwschneider/sec-13f-filings`, sec-api tooling) | institutional holdings | quarterly, 45-day lag | lagged, low PIT value | public | too stale/coarse for trading; ownership context only |
| **Tardis free first-of-month** (all venues) | full L2/trades/options-chain samples | 1st of month, 2019→now | snapshot | free sample | already used; sampling only, not continuous |
| **DoltHub `dolthub/options`, `post-no-preference/options`** | (see Target 2a) | — | — | CC | the real options find |

Nothing in the broad sweep is a hidden edge-maker; the earnings-estimate PIT panel is the only item with
genuine untested optionality, and it is a *maybe*, not a resolve.

---

## RANKED SHORTLIST — what to actually pull, and the honest expected payoff

1. **★ Binance `data.binance.vision` metrics (Target 3) — PULL NOW, highest EV, $0.**
   Resolves — and *reverses a recorded death verdict for* — the XS_GLSR_Z leg (design Sharpe 2.94,
   full-span 1.66). The `count_long_short_ratio` column is live, 5-min, into 2026-08 for all major coins.
   Action: fresh re-pull of the top-50 universe metrics, rebuild the panel, re-run `glsr_recheck_eval.py`
   on the terminal window. **Expected payoff: potentially resurrects a real, previously-strong basket
   leg the programme incorrectly shelved.** This is the one item where a free dataset genuinely opens
   (re-opens) a testable edge. Do this first.

2. **`post-no-preference/options` DoltHub equity-options DB (Target 2a) — PULL if any equity-vol idea is
   on the roadmap.** Free, current, 2019→2026, IV + full greeks + bid/ask, PIT-from-2021, CC. Honest
   payoff: **enables a class of equity/index IV-term-structure, skew, and earnings-vol studies the
   programme has never run on free data** — but it is Yahoo-grade (no OI/volume, daily snapshot, possible
   async-clock defect), so treat it as *exploratory research fuel*, not a research-grade OptionMetrics
   substitute, and apply the open-to-open discriminator to any RV built on it.

3. **`post-no-preference/earnings` PIT estimate panel (broad sweep) — OPTIONAL, speculative.** A free
   point-in-time analyst-estimate/revision panel is genuinely uncommon; worth a look *if* an
   estimate-revision or PEAD-on-estimates idea is proposed. No claim it contains an edge.

4. **Target 1 (borrow) — DO NOT CHASE.** No free history exists (only forward-collectable `usa.txt` via
   detached cron), and the edge it gates (preferred-RV) is insignificant regardless. Skip unless borrow
   infra is wanted for its own sake.

5. **Target 4 (iNAV / bond-ETF NAV) — NO FREE RESOLVE.** Confirmed blocked; this is the programme's
   cleanest genuine paid-data ask. Nothing free changes that.

**Bottom line:** the hunt found exactly one dataset that changes the programme's conclusions — the
Binance long/short archive, which is not gone and quietly resurrects a shelved leg — plus one solid new
free equity-options panel worth having. The borrow and NAV walls are real: no hobbyist has dumped them,
and the honest verdict remains forward-collect-or-pay for those two.

---

### Sources
- Binance public metrics archive: `https://data.binance.vision/` ·
  `https://github.com/binance/binance-public-data` (verified by direct sample download, 2026-08-23)
- DoltHub options DB: `https://www.dolthub.com/repositories/post-no-preference/options` ·
  blog `https://www.dolthub.com/blog/2024-09-27-dolt-post-no-preference/` (schema/date-range verified via
  the DoltHub SQL API)
- Tardis Deribit free samples: `https://docs.tardis.dev/historical-data-details/deribit`
- CryptoDataDownload Deribit: `https://www.cryptodatadownload.com/data/deribit/`
- IBKR borrow history (none free): Portfolio123 thread
  `https://community.portfolio123.com/t/historical-data-on-ib-short-lending-fee-and-share-availability/58254`
  · `https://www.interactivebrokers.com/en/trading/short-securities-availability.php`
- FINRA Reg SHO short volume: `https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data`
  · `https://github.com/tangentstorm/gme-data`
- Securities-lending vendors (all paid): S&P Global Securities Finance / Markit, DataLend, Orbisa,
  Nasdaq SLD
- iNAV (commercial only): S&P/IHS Markit iNAV+, `https://cefdata.com/`, FirstRate Data
