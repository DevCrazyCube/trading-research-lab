# STRATEGY CLASSES — an evidence-graded map of what a small NL retail systematic account can run (2026)

**Author:** Claude subagent (model `claude-fable-5-2`), commissioned by the FACTORY conductor.
**Written:** 2026-11-10, 14:20 UTC (15:20 local). **Status:** research note for the v2 redesign. No code, no orders, no spend. This is the only file I own.
**Requested action:** read §0–§3, challenge §4, then decide what v2 builds. Verdicts here are recommendations, not decisions.

**Owner profile assumed:** Netherlands resident, MiFID retail (repo T105 default), €500–€10k, a laptop, no paid data, wants automation, any market, long or short.

**Evidence labels.** `ACADEMIC` peer-reviewed or working paper · `INDUSTRY` index, fund or regulator data · `PRACTITIONER` public live track record · `ANECDOTE` unverified · `REPO` measured in this repository · `COMPUTED` calculated today from a cited public series (Appendix A).
Source numbers `[n]` refer to §5; every `REPO` statement comes from the files listed under [78]. Each source is tagged **[P]** (I opened and read the page or file) or **[S]** (I saw the claim only in a search-engine summary; treat it as a working hypothesis). `‡` = recalled from training knowledge or implied by arithmetic, not sourced today. All web access was on 2026-11-10.

**Holdout-hygiene warning — read before designing v2.** This note reports public, market-level performance for 2017–2026 (index returns, ETF returns, the BTC price). Those years overlap FACTORY v1's sealed holdout windows. I computed no formula-level statistic on any factory lane. But anyone who reads this and then picks classes or formulas for v2 has seen holdout-period regime information (for example, that trend following had a good 2026 and crypto a bad one). Choosing a class because it did well in the holdout years is a selection, and v2's trial accounting should say so.

---

## 0. Bottom line

1. **Nothing on this map turns €1k–€10k into an income.** The best-evidenced strategies pay a Sharpe ratio of 0.2–0.5 over cash. A net Sharpe of 0.5 at 10 % volatility is cash + 5 % a year: **€74 / €372 / €744** on €1k / €5k / €10k (cash alone pays €24 / €122 / €244 at today's 2.44 % €STR [74]). A net Sharpe of 1.0, which no retail evidence base shows being sustained, is €124 / €622 / €1,244. Saving €100 a month adds €1,200.
2. **The best-evidenced "automated way to grow a portfolio" needs no bot:** a monthly savings plan into a global-equity UCITS ETF. MSCI World in EUR returned 6.68 %/yr from end-2000 to 30 Oct 2026 with a −53.6 % worst drawdown [24].
3. **The one active class with a century of academic evidence, a live net-of-fee industry record through 2026, a mechanism that does not depend on speed, and a convex payoff is diversified trend following.** It is modest: the SG Trend Index made 5.75 %/yr from 2000 to Sep 2026 with a 20.6 % maximum drawdown [2]. Since March 2025 it can be bought as a UCITS ETF [13]. The do-it-yourself futures version needs about $100k [16].
4. **Every high-win-rate item on the list is paid for by a tail:** short volatility, grids, martingale DCA, funding carry, vault yield, merger arbitrage. Where this repo measured the tail, the tail killed the trade (T11 merger arb, funding carry, the memecoin scalps).
5. **Most published anomalies an individual could trade have decayed to about zero in liquid names** (PEAD, index additions, the pre-FOMC drift, pairs trading), and this repo's ~1,500 formulas agree with the literature.
6. **Access for an NL retail client in November 2026 is narrow.** US ETFs are blocked by PRIIPs, so UCITS only. ESMA said on 24 Feb 2026 that crypto perpetuals fall under the CFD rules [64]. The Dutch gambling regulator ordered Polymarket out on 20 Jan 2026 [53]. Running a vault or copy-trading service for others is licensed portfolio management [63].
7. **The statistics do not allow proof at these Sharpe ratios.** A Sharpe-0.5 strategy needs about 16 years of its own returns to reach t ≈ 2; a Sharpe-0.3 strategy needs 44. FACTORY v1's holdout gate (t ≥ 2) needs a Sharpe of at least 0.64 (FX, 9.85 y), 0.91 (ETF, 4.85 y) or 1.18 (crypto, 2.85 y). Realistic premia will fail that gate whether or not they exist. v2 should test **implementation** (true small-account costs, the legal wrapper, tracking of a known premium), not try to re-discover significance.

**Expected euros per year (expected, not likely; ± is one standard deviation of a single year).**

| What | Assumption | €1k | €5k | €10k |
|---|---|---|---|---|
| Cash (€STR ETF) | 2.44 % [74] | 24 | 122 | 244 |
| Global 60/40 | ≈5.5 %, vol 8 % | 55 ± 80 | 275 ± 400 | 550 ± 800 |
| Global equity | ≈7 % (cash + 4.5 % premium), vol 14 % | 70 ± 140 | 350 ± 700 | 700 ± 1,400 |
| A net Sharpe-0.5 system at 10 % vol | cash + 5 % | 74 ± 100 | 372 ± 500 | 744 ± 1,000 |
| A net Sharpe-1.0 system at 10 % vol | cash + 10 % | 124 ± 100 | 622 ± 500 | 1,244 ± 1,000 |
| Saving €100 a month | — | 1,200 | 1,200 | 1,200 |

The 7 % equity figure is my assumption. The 12.7 %/yr MSCI World made over the last ten years [24] is not a forecast.

---

## 1. Ranked table

**Evidence grade.** A = multi-decade academic evidence **and** a live, investable, after-cost track record that includes the years since 2015. B = academic evidence with material post-publication decay, or no clean live retail record. C = short or industry-only evidence, tail poorly measured. D = anecdote or marketing. F = the evidence is negative.
**Time to proof** = years of the strategy's own forward returns needed for t ≈ 2 at the realistic Sharpe, (2 / Sharpe)². It is not the time to build.

| # | Class | Grade | Realistic net Sharpe over cash | Capital floor | NL retail access | Time to proof | Verdict |
|---|---|---|---|---|---|---|---|
| 0 | Buy-and-hold global equity UCITS + cash buffer (§2.11) | A | 0.3–0.45 | €50 | Full | Not needed: it is the prior | **BUILD NOW** (default and yardstick) |
| 1 | Trend following, bought: managed-futures UCITS ETF (§2.1) | A− | 0.2–0.4 | €100 | Yes (Xetra, Paris, LSE) | Not needed | **BUILD NOW** as an optional 10–20 % sleeve |
| 2 | Trend following, DIY in small-size instruments: crypto majors long/flat, UCITS long/flat (§2.1, §2.6a) | B | 0.3–0.6 (one instrument: ≈0.2) | €2–5k | Yes | 8–44 y | **TEST CHEAPLY** |
| 3 | Trend following, DIY diversified futures (§2.1) | A | 0.4–0.8 | ≈$100k | Yes (IBKR micro futures) | 4–16 y | **NOT FOR THIS OWNER** (capital) |
| 4 | Tactical allocation and long-only factor tilts in UCITS (§2.3) | B | GTAA 0.5–0.7 at 7 % vol; tilts ±2 %/yr vs index | €5–10k | Yes | Decades | **TEST CHEAPLY** (paper) |
| 5 | Prop-firm challenge as a leverage wrapper (§2.10) | C | Wrapper, not an edge | €89–540 fee | Yes, unregulated | Conditional on an edge | **TEST CHEAPLY** on a free trial, only after #2 |
| 6 | Perp-DEX backstop vault such as HLP (§2.6e) | C | ≈10–15 %/yr, lumpy, short-gamma tail | €100 | On-chain, legally grey | n/a | **NEEDS DATA OR ACCOUNT** (a wallet is an owner gate) |
| 7 | FX carry, momentum, value (§2.2) | B, decayed | 0–0.3 after retail financing | €10k (CFD) to €25k+ | Yes | 44 y+ | **TEST CHEAPLY** on paper; not live below €25k |
| 8 | Index volatility premium: put-writing, credit spreads (§2.4) | A to 2015, B since | 0.3–0.5 with negative skew | ≈$70k per cash-secured contract | Yes (IBKR) | 16–44 y | **NOT FOR THIS OWNER** |
| 9 | Crypto options volatility premium on Deribit (§2.4) | C | Unknown net | €5–10k | Open question | 2–4 y | **NEEDS DATA OR ACCOUNT** |
| 10 | Crypto funding and basis carry, stablecoin lending (§2.2, §2.6d) | B | ≈ T-bill ± 2 % before the tail | €1k | Partly (Ethena left the EU) | — | **DEAD HERE** |
| 11 | Cross-sectional crypto factors, long-short alts (§2.6b) | C | ≤ 0.3 after funding | €5k | Perps = CFDs | — | **DEAD HERE** (parked) |
| 12 | Equity and ETF stat-arb, pairs, reversal, overnight (§2.5) | B, decayed | ≤ 0 for retail | $25k+ ‡ and borrow | Partly | — | **DEAD HERE** |
| 13 | Event-driven: PEAD, index adds, merger arb, pre-FOMC, calendar (§2.7) | B, decayed | ≈ 0 | — | Partly | — | **DEAD HERE** |
| 14 | Intraday momentum and opening-range systems (§2.13) | C | REPO residual 0.49, t 1.06 | $25k ‡ | Partly | — | **DEAD HERE** |
| 15 | Prediction markets (§2.8) | B | n/a | — | Blocked by the Ksa | — | **DEAD HERE** |
| 16 | LLM or agent discretionary trading (§2.9) | D | Negative so far | — | — | — | **DEAD HERE** as an edge; fine as tooling |
| 17 | Incentive farming, rewards market making, copy trading, grid and DCA bots, CEX–DEX arbitrage, MEV, listings, liquidations, memecoins (§2.6) | D–F | Negative | — | Mixed | — | **DEAD HERE** / **NOT FOR THIS OWNER** |
| 18 | Short-vol lookalikes: FX grid or martingale, 0DTE, naked strangles, turbo and CFD day trading (§2.4, §2.5, §2.12) | F | Negative, with a wipe-out tail | — | Yes | — | **NOT FOR THIS OWNER** |
| 19 | Leveraged beta: 2× index products, margin (§2.14) | A as a risk premium | Same Sharpe as the index, double the drawdown | €100 | Yes | n/a | **NOT FOR THIS OWNER** as a build; it is a risk choice |

---

## 2. The classes

### 2.1 Diversified time-series trend following (CTA style)

- **Mechanism, and who is on the other side.** Slow diffusion of macro information, hedging pressure, and flows that are not price-sensitive (central banks, rebalancers). The other side is hedgers, mean-reversion traders and volatility sellers. The payoff looks like a long straddle on multi-month moves: many small losses, a few large gains. It does not depend on speed or private data.
- **Best evidence.**
  - ACADEMIC/INDUSTRY: Hurst, Ooi and Pedersen test 67 markets from 1880 to 2016 and report a positive return in every decade and a Sharpe of 0.76–0.77 after simulated costs and 2-and-20 fees [11]. It is a backtest written by a manager that sells the strategy.
  - INDUSTRY, live and net of fees: SG Trend Index CAGR 5.75 % from Jan 2000 to Sep 2026, maximum drawdown 20.6 %; BTOP50 4.51 % and 15.9 % [2]. Meketa gives 4.9 %/yr at 13.4 % volatility for Jan 2000–May 2025, against 4.0 % for US bonds and 6.2 % for MSCI ACWI [9]. That is a Sharpe of about 0.37 before subtracting cash and roughly 0.2–0.25 after (my arithmetic, assuming cash averaged about 1.9 % over the period).
  - PRACTITIONER: Rob Carver's live futures account made +23.7 % in the tax year to 5 Apr 2026. Over about 12 years he reports mean 13.8 %, standard deviation 17.3 %, Sharpe 0.80 with a zero risk-free rate, against 0.54 for the SG CTA Index and 0.52 for AHL. His costs were 0.88 % a year (0.33 % commissions, 0.55 % slippage) [14]. His single-instrument "starter system" backtests at Sharpe 0.24, or 0.16 after his cost allowance: an expected 3.9 % a year at a 12 % risk target [15]. He puts the minimum for the diversified futures system at $100k [16].
  - The live record is half the backtest. That gap (0.77 versus 0.2–0.4) is the honest size of decay plus fees.
- **By year (%).**

| Year | SG Trend | SG CTA | BTOP50 | DBMF (US ETF) | KMLM (US ETF) |
|---|---|---|---|---|---|
| 2010 | ≈ +13 ‡ | ≈ +9 ‡ | | | |
| 2011 | ≈ −8 ‡ | ≈ −4.5 ‡ | | | |
| 2012 | ≈ −3.5 ‡ | ≈ −3 ‡ | | | |
| 2013 | ≈ +2.7 ‡ | ≈ +0.7 ‡ | | | |
| 2014 | ≈ +19.7 ‡ | +15.66 [7] ‡ | +12.31 [S] | | |
| 2015 | ≈ 0 ‡ | "flat" [S] | | | |
| 2016 | ≈ −6 ‡ | ≈ −3 ‡ | | | |
| 2017 | ≈ +2 ‡ | ≈ +2.5 ‡ | | | |
| 2018 | ≈ −8 ‡ | ≈ −6 ‡ | | | |
| 2019 | +9.23 [5] | +6.26 [5] | | +1.70 (from May) | |
| 2020 | ≈ +6.3 ‡ | ≈ +3.2 ‡ | | +1.81 | |
| 2021 | +9.25 [6] | +6.27 [6] | | +11.49 | +7.04 |
| 2022 | +27.35 [7] | +20.13 [7] | | +21.61 | +24.24 |
| 2023 | −4.16 [4] | ≈ −3.5 ‡ | −1.70 [4] | −8.94 | −5.66 |
| 2024 | ≈ +2.7 ‡ | ≈ +2.4 ‡ | | +7.24 | −1.70 |
| 2025 | +2.39 [3] | −0.2 [8] | +2.81 [3] | +13.85 | −2.98 |
| 2026 to date | +9.24 (6 Nov) [1] | +9.53 (6 Nov) [1] | +14.81 (30 Sep) [2] | +12.77 (9 Nov) | +11.06 (9 Nov) |

  ETF columns are from [12]. ‡ values are recalled, not sourced today; do not cite them. Cross-check: [8] gives cumulative Jan 2020–Dec 2025 returns of +49.0 % (SG Trend), +29.8 % (SG CTA) and +41.2 % (BTOP50). The four sourced SG Trend years 2021, 2022, 2023 and 2025 compound to +36.5 %, which leaves +9.1 % for 2020 and 2024 together, consistent with the ‡ values. Hedgeweek called 2018 "the most difficult year on record" for both SG indices, without a figure [6]. The source for 2014's +15.66 % names only "the Index"; I assign it to SG CTA from recall. The SG Trend Index was +15.80 % at end-September 2026 [2] and +9.24 % on 6 Nov, after −4.51 % in the first week of November [1].
- **Since 2015 and since 2020.** 2015–2018 was poor (‡: roughly −3 % a year compounded for SG Trend), then +9.2 % in 2019. 2020–2025 was +49 % cumulative, most of it in 2022 [8]. April 2025 shows the weak spot: the index was −9.3 % for the year after a −4.9 % month, while short-term CTAs were −0.9 % [10].
- **Realistic retail result.** Bought as a fund: Sharpe 0.2–0.4 over cash, volatility 10–13 %, drawdown −20 % for the index, −31 % for a single replicator (KMLM, Oct 2022 → Jun 2025) and −20 % for DBMF [12]. DBMF's CAGR since Dec 2020 is 9.9 % against 5.8 % for KMLM [12]: replicator choice matters as much as the premium.
- **Capital, data, infrastructure.**
  - Bought: one ETF share. iMGP DBi Managed Futures Fund R USD UCITS ETF (LU2951555585), TER 0.75 %, launched 7 Mar 2025, about €173m, +28.4 % since inception, −5.3 % over the last month, 1-year volatility 13.9 % [13]. It is USD-denominated and not currency-hedged in this share class.
  - DIY futures: about $100k [16]. Micro contracts are still too large for €10k: one Micro E-mini S&P is 5 × 7,354 ≈ $37k of exposure (S&P 500 close of 5 Nov 2026 [74]), while a ten-instrument, 10 %-vol book on €10k wants roughly €1–2k per instrument.
  - DIY via CFDs: financing is charged on notional at a benchmark plus a markup (IBKR forex CFDs from 1.0 % [17]; one retail broker's all-in S&P long rate was 7.4 % in May 2026 [18]). At 1.5–2.5× gross exposure that is a 2–6 %/yr drag, the same size as the expected premium (3–5 %/yr at 10 % vol and Sharpe 0.3–0.5).
  - Data: free daily prices are enough. Infrastructure: a daily cron job.
- **NL access.** UCITS ETF: yes. Micro futures at IBKR: tradable by an EEA retail client only where a KID exists [17]; that CME publishes them is my recollection ‡. US-listed DBMF and KMLM: blocked (PRIIPs, REPO T105).
- **Killers.** Multi-year flat stretches (2011–2013, 2015–2018, KMLM 2022–2025), sharp V-shaped reversals (April 2025, the first week of November 2026), financing and fees, and the investor abandoning it after two or three losing years.
- **Time to proof.** 8–44 years of own data. So do not test for significance. Test tracking: the correlation of a DIY book's monthly returns with SG Trend or DBMF, and its cost drag.
- **Verdict.** Bought as a sleeve: **BUILD NOW** (optional). DIY in small-size instruments: **TEST CHEAPLY**. DIY diversified futures: **NOT FOR THIS OWNER**.
- **REPO.** Never tested before FACTORY v1: `research/FINDINGS.md` has zero hits for trend following or time-series momentum.

### 2.2 Carry: FX, rates, commodities, crypto funding and basis

- **Mechanism.** You are paid to hold the higher-yielding asset and you lose when funding liquidity dries up. It is short crash risk. The other side is hedgers and investors who pay for safety.
- **Best evidence.**
  - ACADEMIC: carry predicts returns in every major asset class and does badly in global recessions (Koijen et al., JFE 2018) [20]. G10 FX carry made 5.3 %/yr at 8.5 % volatility in 1999–2013, a Sharpe of 0.6, and lost more than 20 % around Lehman [19]. Over 1900–2012 the Sharpe is 0.2–0.4 [19].
  - Recent years: strong in 2023 (one global basket +17 % by mid-year; an EM index +6.6 %, its best year since 2017), a loss in the summer-2024 yen unwind, strong again for EM in 2025, mostly from the interest income [23]. I found no clean G10 carry index series for 2010–2025 (§4).
  - Crypto: the futures–spot carry averaged above 10 %/yr and reached about 60 %; it is driven by leveraged trend-chasers and scarce arbitrage capital, and a high carry predicts crashes (BIS WP 1087) [21].
  - Now: Ethena's sUSDe paid 4.74 % over the 30 days to 14 Oct 2026, against a since-inception average of 10.34 % [22]. The US 3-month T-bill yields 4.19 % [74]. The premium for holding exchange, funding and peg risk is about half a percent. USDe fell to $0.97 during the October 2025 crash, and Ethena has left the EU after a BaFin order [22].
  - REPO: funding carry is dead four ways. It earned 0.46 points less than T-bills where it needed +1.47 points for the venue tail; the cross-sectional and cross-venue versions died on power (FINDINGS §5d, lines 150, 161, 163).
- **What a retail account actually earns.** The carry differential minus the broker's markup on both legs. At IBKR the forex-CFD financing spread starts at 1.0 % [17]. With a G10 policy-rate differential of 1–4 % (USD 3.88 %, EUR 2.50 % today [74]), the markup takes half or more.
- **Realistic retail result.** G10 FX carry: Sharpe 0–0.3, volatility 8–10 %, drawdown −20 to −30 %. Crypto basis on own account: about the T-bill rate, with a venue-failure tail.
- **Capital.** FX through CFDs: €10k. IBKR's interbank FX venue has a $25,000 minimum order size and a $2 minimum commission [17]; on a €700 position that $2 is about 26 bp a side. Rates and commodity carry need futures, so the §2.1 floor applies.
- **Data and NL access.** Free daily policy rates and FX fixes (FRED, ECB) are enough. FX is open to NL retail through IBKR or a CFD broker under the ESMA leverage caps (30:1 on major pairs) [65].
- **Killers.** Carry crashes (2008, August 2024), financing markups, exchange failure, negative funding.
- **Time to proof.** 44 years or more at Sharpe 0.3.
- **Verdict.** FX: **TEST CHEAPLY** on paper (already declared in FACTORY v1); expect about zero after retail financing. Crypto funding and basis: **DEAD HERE**. Rates and commodities: **NOT FOR THIS OWNER**.

### 2.3 Cross-sectional momentum, value, low-vol, quality; tactical allocation (Faber, Antonacci, Keller)

- **Mechanism.** Under-reaction and herding (momentum), compensation for distress or sentiment (value), leverage constraints (low-vol). The other side is benchmark-constrained and performance-chasing money.
- **Best evidence.**
  - ACADEMIC: across 97 published predictors, returns are 26 % lower out of sample and 58 % lower after publication (McLean and Pontiff, JF 2016) [25] ‡.
  - INDUSTRY, live long-only indices to 30 Oct 2026, ten-year annualised [24]: MSCI World Momentum 14.88 % against 12.95 % for MSCI World (USD net); Quality 15.26 % against 13.50 % (USD gross); Value 11.23 % against 13.50 %; Small Cap 10.62 % against 13.50 %; Minimum Volatility 8.16 % against 12.74 % (EUR net). Over five years Momentum is behind (9.87 % against 10.49 %). In October 2026 alone it lost 8.33 % against 0.77 % for the index. The drawdowns match the market's (−55.8 % against −57.8 %).
  - Faber's GTAA, published 2007: in-sample 1972–2005 CAGR 11.7 %, Sharpe 0.81; out-of-sample Jan 2006–Mar 2025 CAGR 6.05 %, Sharpe 0.68, maximum drawdown 11.7 % on monthly data [26]. It survived as a drawdown reducer, not as a return enhancer.
  - Antonacci's dual momentum (2014) and Keller's faster variants: I found no sourced out-of-sample table (§4). The independent replication I found dates from 2019 [27].
  - REPO: T13 — a moving-average crash filter was 9.65 points *worse* on drawdown than de-risked buy-and-hold at matched volatility (p 0.527); a volatility-targeting overlay added 0.66 %/yr (p 0.233) (FINDINGS line 165).
- **Realistic retail result.** A long-only factor ETF is the index plus or minus about 2 % a year, with a t-statistic near 1 over ten years and the same crashes. GTAA-style allocation: Sharpe 0.5–0.7 at 7–8 % volatility, 5–6 % a year, drawdown −12 to −15 %.
- **Capital and data.** Rotation costs set the floor. Five ETFs rebalanced monthly at €1 a trade costs €12–60 a year: 1–6 % of a €1k account, 0.1–0.6 % of €10k. Free daily ETF prices are enough.
- **NL access.** UCITS factor and asset-class ETFs: yes. The 50 US ETFs in FACTORY v1's MA-ETF lane: paper only.
- **Killers.** Momentum crashes, decade-long value droughts, whipsaw, tracking-error regret.
- **Time to proof.** Decades. A 2 %/yr tilt with 6 % tracking error is an information ratio of 0.33: 36 years.
- **Verdict.** **TEST CHEAPLY** on paper. Expect a risk-shaper, not alpha.

### 2.4 Volatility: selling it, managing with it, buying it

- **Mechanism.** Option buyers overpay for insurance, so the seller earns a premium for carrying crash risk. The other side is hedgers and lottery buyers.
- **Best evidence.**
  - INDUSTRY: the Cboe PutWrite index made 9.40 %/yr against 9.91 % for the S&P 500 from July 1986 to August 2023, with volatility 10.3 % against 15.4 % and a maximum drawdown of −32.7 % against −51.0 % [28]. Gross Sharpe 0.67 against 0.47 for 1986–2015 (Bondarenko) [28].
  - Since 2020 the premium looks like 0.6 of the equity market and little else: 2020 +2.1 % against +18.4 %; 2021 +21.8 % against +28.7 %; 2022 −7.7 % against −18.1 %; 2023 +14.3 % against +26.3 %; 2024 +17.8 % against +25.0 % [28]. One tracker shows 6.9 %/yr against 10.9 %/yr over ten years [28].
  - ACADEMIC: retail traders lost about $358,000 a day on zero-day S&P options after daily expiries began in 2022 [29]. US retail option traders lost $1.14bn plus $4.13bn of trading costs between Nov 2019 and Jun 2021 [32].
  - Volatility-managed portfolios (Moreira and Muir, 2017): the in-sample alphas replicate, but real-time versions have a lower Sharpe for 72 of 103 strategies (Cederburg et al., JFE 2020) [30]. REPO T13 agrees.
  - Buying protection: holding short-dated S&P puts continuously cost about 7.4 % a year; trend following was the cheaper hedge (AQR) [31]. REPO: on the free DoltHub panel a bought 15-delta strangle lost 32 % of its premium per two weeks (t −19), and the half-spread was about 9 % of premium.
  - Crypto: Bitcoin's variance risk premium is positive and larger than the S&P's [33]. I found no peer-reviewed after-cost harvest. REPO: the Deribit quote collection (T31) was deleted on 2026-10-15.
- **Realistic retail result.** Put-writing: Sharpe 0.3–0.5, negative skew, drawdown −30 % or worse. Naked strangles and 0DTE selling: unbounded.
- **Capital and data.** One cash-secured SPY or XSP put is about $70k of exposure. Defined-risk spreads fit a €2–5k account but put a large share of it at risk per position. Historical option quotes are not free beyond the DoltHub end-of-day panel (REPO), so an honest cost test needs paid data or forward collection.
- **NL access.** Listed options at IBKR: yes, where a KID exists [17]. Deribit for an NL retail client: open (REPO T105; [77]).
- **Killers.** February 2018, March 2020, August 2024, April 2025; wing spreads; margin expansion in the crash.
- **Time to proof.** 16–44 years.
- **Verdict.** Index premium: **NOT FOR THIS OWNER**. It also fails the owner's own guardrail, recorded in repo memory, against high-win-rate strategies whose rare loss wipes the account. Crypto options premium: **NEEDS DATA OR ACCOUNT**. Volatility targeting: **DEAD HERE**. Long volatility: insurance, not a return source.

### 2.5 Mean reversion, statistical arbitrage, pairs, short-term reversal, overnight versus intraday

- **Mechanism.** You are paid for supplying liquidity to impatient traders. The other side is forced sellers and buyers; the competition is market makers with lower costs than yours.
- **Best evidence.**
  - ACADEMIC: pairs trading has declined steadily, pays mainly in crises, and the naive version no longer works [34]. Short-term reversal is the return to liquidity provision and clusters in high-volatility periods; it survived costs only in the largest stocks with careful execution [36].
  - INDUSTRY: the two "night effect" ETFs closed in July 2023 with $3.7m and $1.4m in assets; their own sponsor called capturing the effect by trading "prohibitively expensive" [35].
  - REPO: the 5-day factor-neutral reversal persisted out of sample gross (Sharpe 0.86, t 1.85) and was −0.29 net at a 5 bp half-spread. The overnight premium (T10) died twice. The ETF-sibling spread was a bid-ask bounce artefact. The best structural leg, the closed-end-fund discount tilt, is US-listed and so blocked for an NL retail client.
  - FX grid and martingale bots (AUDNZD, EURCHF): I found no academic evidence of an edge. Mechanically they are short volatility with unbounded inventory. On 15 January 2015 the Swiss franc moved about 20–30 % in minutes ‡. EU negative-balance protection [65] now caps the loss at the whole account.
- **Realistic retail result.** At or below zero after costs.
- **Capital, data, access.** Equity stat-arb needs margin, borrow and many names: $25k or more. An honest cost test needs intraday quotes. US single stocks are open to NL retail at IBKR; US funds are not.
- **Killers.** The half-spread, borrow fees and availability, and crowding. With a net Sharpe at or below zero there is nothing to prove.
- **Verdict.** **DEAD HERE.** FX grids: **NOT FOR THIS OWNER.**

### 2.6 Crypto-specific

**(a) Trend and momentum in majors — TEST CHEAPLY.**
- ACADEMIC: an ensemble of Donchian-channel trend models on the 20 most liquid coins, survivorship-free since 2015, has a Sharpe above 1.5 and 10.8 %/yr alpha to Bitcoin net of fees (Zarattini, Pagani, Barbon, 2025) [37]. It is a backtest dominated by the 2017 and 2020–21 bull markets. Crypto momentum crashes are severe [38].
- COMPUTED base rate it must beat: see §2.11. Bitcoin buy-and-hold has a Sharpe of about 0.6 since 2018 with a −81 % drawdown.
- Realistic: Sharpe 0.3–0.7 for a long/flat book, with wide uncertainty. Most of it is Bitcoin beta with a crash filter, and REPO T13 says a crash filter must be compared with *vol-matched* buy-and-hold before it is believed.
- Costs decide it. Bitvavo spot is 0.15 % maker / 0.25 % taker. Kraken Pro spot rose to 0.40 % / 0.80 % at the entry tier on 9 July 2026; Kraken futures are 0.02 % / 0.05 % [67]. Eight round trips a year cost about 4 % at Bitvavo taker rates and about 13 % at Kraken's spot taker rate. A long perpetual also pays funding.
- Data and infrastructure: free exchange archives and public APIs; a daily job. Live trading needs API keys, which are an owner gate.
- Access: spot at Bitvavo (AFM-authorised). Perpetuals for EU retail: Kraken through its Cyprus MiFID firm since May 2025, One Trading, OKX "X-Perps" since April 2026 [66]. ESMA's February 2026 statement brings them under the CFD measures, whose 2018 leverage cap for crypto is 2:1 [64][65].

**(b) Cross-sectional factors (size, momentum, reversal, on-chain value) — DEAD HERE (parked).**
- The size effect disappeared out of sample; momentum lives in large caps and crashes [38].
- REPO: of 598 formulas one survived (X2_FLOWSTREAK) and its frozen sizing rule is unreachable at the bare taker fee. The crowd-fade leg lost its data. The low-volatility factor needs a short leg that cannot be borrowed.

**(c) Funding carry and delta-neutral basis — DEAD HERE.** See §2.2.

**(d) Stablecoin lending and fixed yield — DEAD HERE as growth.**
- Aave v3 USDC on Ethereum averaged 3.54 % over the last year and 4.11 % over the last 30 days [40]. The US 3-month T-bill pays 4.19 % and €STR 2.44 % [74]. A euro investor takes dollar risk and contract risk for less than the Treasury yield.
- Morpho and Pendle rates: not verified (§4).

**(e) Perp-DEX backstop vault (Hyperliquid HLP) — NEEDS DATA OR ACCOUNT (owner gate).**
- INDUSTRY [39]: cumulative profit $136.9m since May 2023, never negative, on $150–600m of deposits. Deposits fell from $604m (Sep 2025) to $269m (Jun 2026). Two events are about 41 % of all profit. No performance fee.
- Tail events: JELLY, 26 Mar 2025, an unrealised loss of $12–13.5m, closed at +$0.7m only because validators overrode the oracle price. POPCAT, 12 Nov 2025, a $4.9m loss. 10 Oct 2025, about +$41.5m (roughly +10 %) on a $19bn liquidation day. 31 Jan 2026, +$15m.
- My rough average: about $137m over 3.1 years on perhaps $300m of average deposits is of the order of 10–15 % a year. The average deposit level is my guess (§4).
- It is the fee for being the liquidation backstop of a leveraged venue whose last line of defence was a discretionary validator vote.
- Access: on-chain, no licensed EU entity, legally grey [66]. A wallet is an owner gate under AGENTS.md.

**(f) Market making for incentives — DEAD HERE.** REPO measured the Polymarket reward pool at about $2,655 a day in total, with a ceiling of low thousands of euros a year. Polymarket is now closed to NL users (§2.8).

**(g) Airdrop and points farming — NOT FOR THIS OWNER.** The one study that estimates hunters' expected profits (Hop, LayerZero) did not give me numbers [41]. Sybil filters penalise multi-wallet farming. Capital is locked for months for a lottery ticket.

**(h) Liquidation and cascade plays — DEAD HERE.** REPO: Orphan Flush fell from +41.9 bp to −11.0 bp a cluster once the real depth estimator was used; Hyperliquid liquidation fills average $173.

**(i) Listing and delisting effects — DEAD HERE.** More than 80 % of six months of new Binance listings were below their listing price; median returns for 2024–mid-2025 listings were −5 % to −19 % [43]. The gain is in the announcement, which retail does not get. REPO: the token-unlock universe is too small to test.

**(j) CEX–DEX and triangular arbitrage — NOT FOR THIS OWNER.** REPO: the latency test was lost, and the atomic arbitrage on fresh pools is zero by construction.

**(k) MEV and sniping — DEAD HERE, and outside AGENTS.md.** ESMA's draft MiCA market-abuse standards name MEV extraction such as sandwiching as possible market abuse [76]. REPO: the sniper lost at t ≈ −16.

**(l) Copy trading and leaderboards — DEAD HERE.** Copy-trading platforms push followers into excessive risk (Management Science 2020) [42]. An industry study found fewer than 7 % of 292,000 wallets on the Fomo app profitable over three months [42]. REPO: copying insiders is a lagging trap, and 294 top Fomo wallets realised −$3.16m in a week with 22 % positive.

**(m) Grid and DCA bots — DEAD HERE.** Without a view on trend, a grid has zero expectation before fees [44]. A DCA bot that averages down is a martingale.

**(n) Memecoins — the repo verdict stands.** Three structural kills: death is a −90 % jump that no stop can exit, momentum entry is worse than a random entry, and session noise exceeds every measured edge. Untested angles that remain, all forward-only with tiny samples: the frozen 30/30 cohort watch, the follower-wave watcher, the Robinhood sniper-roster one-shot read (the owner's), the Pons-completed scanner arm (5 of 7 hit 2× on a peak-after-alert read, which is not an exit), the window-2 deadness-screen read locked behind U4, and the LLM judgment paper trader. None is a class with a positive prior.

### 2.7 Event-driven

- **Earnings drift (PEAD).** Gone in large stocks since 2006 and in microcaps since about 2016 (Martineau, 2022); two 2025 papers dispute this, and the dispute turns on microcaps [45]. REPO T15: dead on power, the detectable effect was 4.9 times too large.
- **Index rebalancing.** The S&P 500 addition effect fell from about 7.4 % in the 1990s to under 1 % in 2010–2020 (Greenwood and Sammon, JF 2025) [46]. REPO: reconstitution flow is noise.
- **Merger arbitrage.** The deal spread fell by more than 400 bp after 2002; the HFRI index made 7.8 %/yr from 1990 to mid-2016 but 2.5 %/yr over the last five of those years [47]. REPO T11: −0.83 % per event; the break-even deal-failure rate of 6.7 % sits inside the observed 5–10 % band.
- **Pre-FOMC drift.** 49 bp in the 24 hours before scheduled announcements, 1994–2011 (Lucca and Moench, JF 2015); it vanished after 2015 (Kurov et al., 2021) [48].
- **Seasonality.** The evidence on the turn-of-the-month effect after publication is split [49]. REPO: the calendar theme was noise in the 380-formula sweep. Sell-in-May, and crypto weekend or hour effects: no sourced after-cost evidence (§4).
- **Capital, data, proof.** These need US single stocks, shorting and an event feed. The surviving effects are smaller than any window the repo has can detect (T9 and T15 both died on power).
- **Verdict.** **DEAD HERE.** The two turn-of-month formulas declared in FACTORY v1 are a fair, cheap last check.

### 2.8 Prediction markets

- **Mechanism.** Recreational takers overpay for longshots; makers and arbitrage bots collect.
- **Best evidence.** On Kalshi both makers and takers show a favourite–longshot pattern and takers lose far more; one summary puts average losses at about 32 % for takers and 10 % for makers [50]. About $40m of arbitrage profit was extracted on Polymarket between April 2024 and April 2025 [51], by fast bots. About 84 % of 2.5m Polymarket wallets lost money and 2 % made more than $1,000 [54].
- **LLM forecasting.** On ForecastBench superforecasters score a Brier of 0.086 against 0.103 for the best LLM; parity is projected for late 2026 to 2027 [52]. An LLM that is still behind the best humans has no demonstrated edge over a liquid market price. REPO: the prediction-market forecasting log reached 0 of 50 resolved estimates before its data was deleted.
- **NL access.** The Ksa ordered Polymarket's operator to stop offering in the Netherlands on 20 Jan 2026 (€420,000 a week, capped at €840,000). Dutch users were cut off in February and the objection was rejected in June [53]. The reasoning (an unlicensed game of chance) applies to any such venue. Kalshi and IBKR forecast contracts for NL clients: not verified (§4).
- **Verdict.** **DEAD HERE** on access. Paper research only.

### 2.9 LLM and AI-agent trading

- **Live experiments.** Alpha Arena season 1 gave six models $10,000 each on Hyperliquid perpetuals from 18 Oct to 3 Nov 2025. Two finished up (Qwen 3 Max about +22 %, DeepSeek about +5 %) and four down; press figures for the worst, GPT-5, range from −62 % to −72 %. The organiser itself listed the flaws: 17 days, small samples, prompt bias. In season 1.5 (US stocks, 19 Nov–3 Dec 2025) a "mystery model" won with about +12 % and most models lost [55]. Two weeks of leveraged trading has no statistical content either way.
- **Academic.** Over two decades and more than 100 symbols the reported LLM advantages disappear, and most agents trail buy-and-hold (FINSABER) [56]. Backtests on dates inside a model's training data are contaminated: one test attributes about 37 % of the LLM effect to look-ahead, and a decoding fix cuts in-sample returns by up to 67 % on memorised dates [57].
- **REPO.** The LLM judgment paper trader lost 14 % in its first epoch (the rule-based baseline lost 33 %). Coins it bought were −16 % an hour later against −9.5 % for coins it skipped. The news-desk slots mostly abstained.
- **Verdict.** An LLM is useful for research, code and monitoring. As a source of return it is **DEAD HERE** until a multi-month forward record exists. Any backtest of it on pre-cutoff dates is invalid.

### 2.10 Capital-scaling routes

- **What a prop challenge is.** FTMO's two-step rules: +10 %, then +5 %, a 5 % maximum daily loss, a static 10 % maximum loss, four minimum trading days. FTMO states that all accounts are demo accounts with fictitious funds [58]. The fee is about €89–99 for $10k, €540 for $100k and €1,080 for $200k, refunded with the first payout; the trader keeps 80–90 % [60].
- **INDUSTRY base rate.** Across firms about 14 % of challengers pass, 7 % ever receive a payout, and the average payout is 4 % of the account (FPFX, reported for 2024). FTMO's 2023 revenue was $203.9m [59]. At those averages a $100k attempt is worth about 0.07 × ($4,000 + the €540 refund) − €540 ≈ **−€220**.
- **COMPUTED: the challenge under idealised conditions** (Appendix A; no costs, end-of-day checks only, no rule breaches, payouts always honoured — all optimistic).

| Net Sharpe | Vol | Pass both phases | Median trading days to pass | Trader's expected payout over 2 y per funded account, % of account | Funded accounts alive after 2 y | EV per $100k attempt (fee €540) | EV per $10k attempt (fee €89) |
|---|---|---|---|---|---|---|---|
| 0.0 | 15 % | 33 % | 130 | 8.2 % | 5 % | ≈ +2,300 | ≈ +200 |
| 0.5 | 10 % | 58 % | 257 | 11.2 % | 41 % | ≈ +6,300 | ≈ +610 |
| 0.5 | 15 % | 52 % | 127 | 13.1 % | 12 % | ≈ +6,500 | ≈ +630 |
| 0.5 | 20 % | 47 % | 76 | 13.2 % | 3 % | ≈ +5,800 | ≈ +560 |
| 1.0 | 10 % | 81 % | 219 | 17.2 % | 61 % | ≈ +13,700 | ≈ +1,360 |
| 1.0 | 15 % | 68 % | 116 | 20.3 % | 25 % | ≈ +13,600 | ≈ +1,350 |

  With fat-tailed daily returns (Student-t, 4 degrees of freedom) the EVs are about 3–23 % lower. Accounts are in dollars and fees in euros, so read the EV columns as approximate.
- **How to read it.**
  1. The frictionless model gives even a zero-skill trader a positive expected value, because the firm absorbs losses beyond the fee. The real product therefore depends on costs, intraday equity-based limits, prohibited-practice clauses and payout discretion to take that value back. The industry numbers say they take back more than all of it.
  2. With a real net Sharpe of 0.5 the wrapper is worth thousands of euros per attempt. But "real, net of CFD spreads and overnight financing, and compliant with an intraday 5 % rule" is exactly what cannot be established quickly (16 years of data at Sharpe 0.5).
  3. Slow strategies pay financing on notional in a CFD account (§2.1). And the funded account rarely lasts: at a Sharpe of 0.5, between 59 % and 97 % of funded accounts are closed within two years.
- **Other routes.** Trading competitions are rank-order tournaments that reward maximum variance; I have no data on their expected value (§4). Running a Hyperliquid vault pays the leader 10 % of profits [62], but managing third-party money by automatic execution is MiFID portfolio management and needs an AFM licence [63].
- **NL constraints.** Prop firms are unregulated here. Firms have stopped paying (The Funded Trader), and Belgian, Italian and Spanish regulators have issued warnings [61]. How payouts are taxed, and whether they count as income for toeslagen, is not verified (§4).
- **Verdict.** A wrapper, not an edge. **TEST CHEAPLY** on a free trial or on paper, and only after a strategy exists whose net Sharpe under CFD costs is documented. Pay no fee before that.

### 2.11 The boring base rates

| Asset | Figures | Source |
|---|---|---|
| MSCI World, EUR, net | 2022 −12.78 %, 2023 +19.60 %, 2024 +26.60 %, 2025 +6.77 %, 2026 to 30 Oct +16.67 %. Ten years: 12.74 %/yr, vol 13.4 %, Sharpe 0.90. Since end-2000: 6.68 %/yr, Sharpe 0.43. Worst drawdown −53.6 % (2001–2009). | [24] |
| FTSE All-World UCITS ETF (VWCE), TER 0.14 % | 2022 −13.01 %, 2023 +17.78 %, 2024 +24.65 %, 2025 +8.36 %, 2026 to date +15.93 %. Five years +63.8 %. Drawdown since 2019 −33.5 %. | [75] |
| Global 60/40 (Vanguard LifeStrategy 60 UCITS) | 2022 −13.86 %, 2023 +12.46 %, 2024 +14.71 %, 2025 +6.38 %, 2026 to date +8.82 %. Five years +29.5 %, vol 8.2 %, drawdown −15.4 %. | [75] |
| Euro cash (XEON, tracks €STR + 8.5 bp, TER 0.10 %) | 2023 +3.27 %, 2024 +3.79 %, 2025 +2.22 %, last year +2.10 %. €STR 2.442 % on 9 Nov; ECB deposit rate 2.50 %. | [75][74] |
| Bitcoin in USD, COMPUTED | 2018 −73 %, 2019 +94 %, 2020 +306 %, 2021 +59 %, 2022 −64 %, 2023 +156 %, 2024 +123 %, 2025 −7 %, 2026 to 9 Nov −14 %. Since 2018: 21.4 %/yr, vol 64 %, Sharpe 0.63, drawdown −81 %. Since 2021: 17.4 %/yr, vol 57 %, Sharpe 0.57, drawdown −77 %. Now $75,091: −40 % from the 5 Oct 2025 closing high of $124,720, after a −53 % low on 30 Jun 2026. | [74], App. A |

- **Bitcoin DCA, COMPUTED.** Equal monthly buys since Nov 2024 (25 buys) are −11.5 % on the money put in. Since Nov 2023: +5.9 %. Since Nov 2022: +56.8 %. Over 2014–2026, 12-month plans ended negative 23 % of the time (worst −55 %), 24-month plans 18 % (worst −49 %), 36-month plans 4 %, 48-month plans never. The sample contains a 200-fold rise; it is not a forecast.
- **Caveat.** The factsheet figures are as of 30 Oct. The S&P 500 fell 4.4 % on 5 Nov 2026, its largest one-day drop of the year, and stood 5.9 % below its 6 Oct high [74].
- **NL tax.** In 2026 box 3 exempts the first €59,357 per person; above that a deemed 6.00 % return on investments is taxed at 36 % [73]. At €1k–€10k the tax is zero. Ordinary investing and even day trading normally fall in box 3 [73].
- **Verdict.** **BUILD NOW**: it is the default, and it is the bar every candidate must clear after costs.

### 2.12 The cost of being wrong

| Population | Result | Source |
|---|---|---|
| EU retail CFD accounts | 74–89 % lose; average loss €1,600–€29,000 per client | ESMA 2018 [65] |
| Dutch turbo investors, Jun 2017–Jun 2018 | 68 % lost, on average €2,680; 88 % of those with more than 500 trades lost; −2.9 % per trade | AFM [68] |
| Brazilian day traders who persisted over 300 days, 2013–2015 | 97 % lost; 1.1 % earned more than the minimum wage | Chague et al. [69] |
| Taiwanese day traders, 1992–2006 | Fewer than 1 % predictably profitable after fees; over 80 % lose in a typical half-year | Barber et al. [70] |
| Indian individual derivatives traders | 93 % lost over FY22–FY24, about ₹2 lakh each; 91 % lost in FY25 | SEBI [71] |
| Retail bitcoin buyers via apps, 2015–2022 | An estimated 73–81 % lost on their initial investment | BIS WP 1049 [72] |
| Polymarket wallets | About 84 % lost; 2 % made over $1,000 | [54] |
| Prop-firm challengers | 7 % ever paid | [59] |
| This repo | ~1,500 formulas, no validated net-profitable bot; the owner's clean Solana ledger is −23.0 % on 13 closed positions | REPO |

The common factor in these studies is leverage plus frequent trading. Only the Barber and Chague studies test for persistent skill, and they put it at about 1 % of traders.

### 2.13 Added class: intraday momentum and opening-range day-trading systems

- REPO: the whole opening-range loss came from the stop leg. The no-stop residual was +4.8 bp a day, Sharpe 0.49, t 1.06, and stayed logging-only. The published papers' omitted stop-fill slippage was the open question the repo set out to measure.
- Day-trader base rates: §2.12.
- **Verdict.** **DEAD HERE.**

### 2.14 Added class: leveraged beta

- A 2× index product or margin on an index fund raises the expected return and the drawdown together. It is a way to take more of a premium that exists, not an edge.
- The Dutch turbo data in §2.12 show how leverage is used in practice.
- **Verdict.** **NOT FOR THIS OWNER** as something to build. It is a risk choice.

---

## 3. What I would build first for this owner

**Pick 1 — the base portfolio and the yardstick (BUILD NOW).**
- What: an automatic monthly purchase of one global-equity UCITS accumulating ETF, a cash buffer in a €STR ETF or a savings account, and optionally 10–20 % in the managed-futures UCITS ETF. Brokers already automate this.
- What the factory builds: a base-rate logger that records, monthly and in euros at the owner's real account size, the return of that portfolio, of 60/40, of cash, of the trend ETF and of Bitcoin.
- Why first: it has the strongest evidence on the map, a positive expected return without any edge, zero research risk, and it is legally clean. It is also the bar: a candidate that cannot beat it after costs is not worth running.
- Expected: about €70 / €350 / €700 a year on €1k / €5k / €10k, with a −20 % to −50 % drawdown at some point.

**Pick 2 — small-account trend following, with true costs (TEST CHEAPLY).**
- What: finish FACTORY v1's trend lanes, but only in instruments this account can hold in sensible size. That means crypto majors long/flat on spot, and a UCITS multi-asset long/flat sleeve. For the multi-asset part, the question is whether a DIY book beats simply buying the trend ETF after its 0.75 % fee. At €10k it probably does not.
- Why: trend is the only active class with grade-A evidence, a live record through 2026, a mechanism that needs no speed, and a payoff that fits the owner's rule against wipe-out tails. Crypto is the one market where position sizes scale down to €100.
- How to judge it, given that t ≥ 2 is unreachable: estimate, do not test. Pre-declare economic thresholds, for example a net Sharpe point estimate of at least 0.3 in both windows, a drawdown no worse than half of buy-and-hold's, costs under a third of the gross return, and a win against vol-matched buy-and-hold.
- Expected if it works: €50–€60 a year per €1,000 at 10 % volatility, with multi-year flat stretches.

**Pick 3 — a paper prop-challenge harness (TEST CHEAPLY, conditional on pick 2).**
- What: replay whatever pick 2 freezes under the FTMO two-step rules with CFD spreads and overnight financing, on a free trial account, for at least 60 sessions. Feed the measured net Sharpe and its confidence interval into the Appendix A simulation.
- Why: with €10k of own capital even a real Sharpe of 0.5 pays about €500 a year. Rented notional is the only route on this map that changes the size of the number without more capital, and it costs nothing to simulate.
- The gate: if the lower bound of the net Sharpe is at or below zero, pay no fee. A fee, a tax opinion and the firm's counterparty risk are owner decisions.

**The one thing that would most change the picture: capital.**
- At about €100k the diversified micro-futures trend system becomes feasible at roughly 1 % a year in costs, which is where the best practitioner record sits. At €10k no data purchase and no account unlocks anything comparable.
- Capital comes from income and saving. The owner's data-science skill, sold part-time, would add more euros a year than any strategy here is expected to earn on €10k. That is the honest answer to "more capital, or a skill".
- Second, and free: an IBKR account (UCITS, KID-covered micro futures and listed options) and the owner's answers to the open access questions (MiFID category, Deribit).

**Notes for the v2 redesign.**
1. **Power.** With the t ≥ 2 holdout gate, the required Sharpe is 0.64 / 0.91 / 1.18. The classes with real evidence have 0.2–0.5. A v1 result of "no survivors" would say nothing about them.
2. **Costs must be true at this account size.** v1 charges FX 1 bp a side (3 bp stressed). IBKR's $2 minimum commission is about 26 bp on a €700 position [17], and Kraken's fiat and stablecoin pairs reportedly cost 0.20 % a side [67]. Kraken spot is 0.40 % / 0.80 % since July 2026. CFD financing and perpetual funding are charged on notional.
3. **Wrappers.** The MA-ETF lane uses 50 US ETFs that the owner cannot buy; a pass there needs a UCITS mapping before it means anything. Crypto perpetuals are CFDs for an EU retail client.
4. **Benchmarks.** Add "buy the trend UCITS ETF" and "vol-matched buy-and-hold" to every report. A DIY formula that passes a t-test and loses to the ETF is not a result.
5. **Selection.** See the holdout warning at the top.

---

## 4. Claims I could not verify

1. **SG Trend and SG CTA annual returns for 2010–2018, 2020 and 2024, and SG CTA 2023.** The ‡ values are recalled. One recalled value I could check was wrong: I remembered SG Trend 2021 as about +6 %, and the source says +9.25 %. The sourced figures and the 2020–2025 cumulative constrain 2020 and 2024 only as a pair. The official SG download URLs returned 404.
2. **BTOP50 by year.** Only 2014, 2023, 2025 and 2026 to date were found.
3. **McLean and Pontiff's 26 % and 58 %.** Recalled; the publisher page returned 403.
4. **Hurst–Ooi–Pedersen's net Sharpe.** Seen only in secondary summaries.
5. **A G10 FX carry index series for 2010–2025.** Not found. "Decayed after 2008" rests on the long-sample papers and scattered press.
6. **IBKR interest and financing markups at today's rates.** The 1.0 % forex-CFD figure is from an IBKR page whose example is dated 2016.
7. **Out-of-sample results for Antonacci's GEM and Keller's strategies.** No sourced table.
8. **The Kalshi loss figures (32 % takers, 10 % makers).** From a secondary summary of the VoxEU column.
9. **HLP's annual return and maximum drawdown.** The source gives cumulative profit and events. My 10–15 % a year assumes an average deposit base of about $300m.
10. **Morpho and Pendle yields in November 2026; Hyperliquid's current terms for EU users.** Secondary sources only, and they conflict.
11. **Kraken's fee schedule after 9 July 2026, and whether Kraken derivatives are offered to Dutch residents.** Search summaries only.
12. **Deribit access for an NL retail client.** Still the repo's open T105 question.
13. **Kalshi and IBKR forecast contracts for NL clients.** Not checked.
14. **FTMO's current prices.** Third-party pages disagree on the small tiers (€89 or €99 for $10k; €155 or €270 for $25k).
15. **Regulatory items reported for 2026** (an ESMA statement on challenge fees in September, SEC actions against prop firms): single-source.
16. **Dutch tax treatment of prop-firm payouts, their effect on toeslagen, and the reported plan to cut the box-3 exemption in 2027.** Needs a tax adviser or the Belastingdienst.
17. **Alpha Arena's exact figures.** Press reports differ by snapshot date; the official results page was not read.
18. **The Fomo-app study's method** (fewer than 7 % of wallets profitable).
19. **Expected value of trading competitions; after-cost evidence for sell-in-May and crypto calendar effects; the average value of airdrops per wallet.** No usable source found.
20. **The 15 January 2015 franc move and the retail-broker failures that followed.** Recalled.
21. **Whether Dutch brokers list the DBMF UCITS line, and whether a euro-hedged share class is available to retail.** Check at the broker.
22. **That CME publishes PRIIPs KIDs for its micro futures, so that an EEA retail client can trade them at IBKR.** Recalled; IBKR's page says only that a KID is required.
23. **The 7 % expected return on global equity and the 1.9 % average cash rate for 2000–2025.** My assumptions, not sourced.
24. **The $25k floor for US intraday and stat-arb accounts** (the US pattern-day-trader rule as applied to an NL client in 2026). Recalled.

---

## 5. Sources (all accessed 2026-11-10)

**Trend following**
1. [P] Société Générale Prime Services Indices, page and daily XML feeds `CTA.xml`, `CTAT.xml` (SG Trend Index), `STTI.xml` — https://wholesale.banking.societegenerale.com/en/prime-services-indices/ and https://wholesale.banking.societegenerale.com/fileadmin/indices_feeds/CTAT.xml
2. [P] Top Traders Unplugged, Trend Following Performance Report, September 2026 — https://www.toptradersunplugged.com/trend-following-performance-report-september-2026/
3. [P] Top Traders Unplugged, report for December 2025 — https://www.toptradersunplugged.com/?p=20381
4. [P] Top Traders Unplugged, report for December 2023 — https://www.toptradersunplugged.com/?p=14211
5. [P] Hedgeweek, 23 Jan 2020 — https://www.hedgeweek.com/trend-followers-maintain-momentum-with-early-year-gains/
6. [P] Hedgeweek, 7 Jan 2022 — https://hedgeweek.com/december-gains-complete-best-year-ctas-2014 ; Hedgeweek on 2018 — https://www.hedgeweek.com/ctas-see-out-challenging-2018-improvement-performance-2/
7. [S] The Full FX, 2022 year-end and "Trend Followers Eye Record Year" — https://thefullfx.com/year-end-drop-fails-to-dampen-stellar-2022-for-trend-followers/ ; https://thefullfx.com/?p=3251
8. [P] Aussie Turtles, "Battle of the Trend Following Indexes: December 2025" — https://www.aussieturtles.com/battle-of-the-trend-following-indexes-december-2025/
9. [P] Meketa, "Trend Following Strategies", December 2025 — https://meketa.com/wp-content/uploads/2025/12/MEKETA_Trend-Following.pdf
10. [P] SG Prime Services, "CTA Industry Update — Keeping Up With The Trend-Followers", May 2025 — https://content.sgmarkets.com/CTA_UPDATE_KEEPING_UP_WITH_THE_TRENDFOLLOWERS_2025
11. [S] Hurst, Ooi, Pedersen, "A Century of Evidence on Trend-Following Investing" — https://www.TrendFollowing.com/whitepaper/Century_Evidence_Trend_Following.pdf ; summary https://alphaarchitect.com/trend-following-is-everywhere/
12. [P] Total Real Returns, KMLM, DBMF, SPY, data to 2026-11-09 — https://totalrealreturns.com/n/KMLM,DBMF,SPY
13. [P] justETF, iMGP DBi Managed Futures Fund R USD UCITS ETF — https://www.justetf.com/en/etf-profile.html?isin=LU2951555585 ; [S] Xetra listing — https://etfexpress.com/2026/02/03/imgp-dbi-now-available-on-deutsche-borse-xetra/
14. [P] R. Carver, "Annual performance update — year 12", 15 Apr 2026 — https://qoppac.blogspot.com/2026/04/annual-performance-update-year-12.html
15. [P] The 7 Circles, "Leveraged Trading 3 — The Starter System" — https://the7circles.uk/?p=27861
16. [S] Carver's $100k minimum — https://harriman.house/?p=1768634 ; https://algoadvantage.substack.com/p/033-rob-carver-the-comprehensive
17. [S] Interactive Brokers: spot-currency commissions — https://www.interactivebrokers.ie/en/pricing/commissions-spot-currencies.php ; micro futures — https://www.interactivebrokers.com/en/trading/micro-futures-comparison.php ; PRIIPs — https://ibkb.interactivebrokers.com/node/2993 ; forex CFDs — https://ibkb.interactivebrokers.com/de/node/3030
18. [S] BrokerChooser, CFD financing rates (Spreadex table, May 2026) — https://brokerchooser.com/zh/broker-reviews/spreadex-review/cfd-financing-rate

**Carry**
19. [S] NBIM Discussion Note, "The currency carry trade", 2014 — https://www.nbim.no/globalassets/documents/dicussion-paper/2014/discussionnote_currency-carry-trade.pdf ; Doskov and Swinkels via Quantpedia — https://vvv.quantpedia.com/?p=571
20. [S] Koijen, Moskowitz, Pedersen, Vrugt, "Carry", JFE 127 (2018) — https://econpapers.repec.org/RePEc:eee:jfinec:v:127:y:2018:i:2:p:197-225
21. [P] BIS Working Paper 1087, "Crypto carry" — https://www.bis.org/publ/work1087.htm
22. [P] Stablecoin Insider, "Ethena USDe Q1 2026 report" — https://stablecoininsider.org/ethena-usde-q1-2026-report/
23. [S] Recent FX carry — https://macrohive.com/bilals-macroscope/bilals-macroscope-forget-equities-fx-carry-is-king-of-2023-but-not-for-long ; https://www.banque-france.fr/en/publications-and-statistics/publications/carry-trades-and-volatility-risk ; https://www.zawya.com/en/insights/carry-on-trading-rate-based-g10-currency-bets-make-a-comeback-340078 ; https://m.uk.investing.com/news/economy/analysislucrative-foreign-exchange-trade-sustained-by-low-volatility-3403389

**Factors and allocation**
24. [P] MSCI factsheets dated 30 Oct 2026: World (EUR, net) — https://www.msci.com/documents/10199/890dd84d-3750-4656-87f2-1229ed5a5d6e ; World Minimum Volatility (EUR) — https://www.msci.com/documents/10199/5eb43764-87ee-4d1a-ac07-6d7d7db8a4ec ; Momentum — https://www.msci.com/resources/factsheets/index_fact_sheet/msci-world-momentum-index-usd-net.pdf ; Quality — https://www.msci.com/resources/factsheets/index_fact_sheet/msci-world-quality-index.pdf ; Value — https://www.msci.com/resources/factsheets/index_fact_sheet/msci-world-value-index.pdf ; Small Cap — https://www.msci.com/resources/factsheets/index_fact_sheet/msci-world-small-cap-index.pdf
25. [‡] McLean and Pontiff, "Does Academic Research Destroy Stock Return Predictability?", JF 2016 — https://doi.org/10.1111/jofi.12365
26. [S] Concretum Group, "Global Tactical Asset Allocation" — https://concretumgroup.com/global-tactical-asset-allocation/
27. [S] Advisor Perspectives, "Global Equity Momentum: A Craftsman's Perspective", 2019 — https://www.advisorperspectives.com/articles/2019/05/06/global-equity-momentum-a-craftsmans-perspective

**Volatility**
28. [S] Cboe PutWrite: https://www.cboe.com/insights/posts/generating-income-and-managing-risk-cash-secured-put-writing-in-a-low-equity-return-environment ; factsheet https://cdn.cboe.com/resources/indices/factsheet/CboeGlobalIndices_PUT-Index.pdf ; Bondarenko via CXO Advisory https://www.cxoadvisory.com/equity-options/performance-of-cboe-putwrite-indexes ; ten-year comparison https://portfolioslab.com/symbol/%5EPUT
29. [S] Beckmeyer, Branger, Gayda (SSRN 4404704) via Bloomberg — https://www.bnnbloomberg.ca/day-traders-lose-358-000-per-day-gambling-on-zero-day-options-1.1910634
30. [S] Cederburg, O'Doherty, Wang, Yan, JFE 138 (2020) — https://econpapers.repec.org/RePEc:eee:jfinec:v:138:y:2020:i:1:p:95-117
31. [S] AQR, "Tail Risk Hedging: Contrasting Put and Trend Strategies" — https://www.aqr.com/Insights/Research/White-Papers/Tail-Risk-Hedging-Contrasting-Put-and-Trend-Strategies ; the −7.4 % figure via https://www.wealthmanagement.com/equities/hedging-tail-risks-tortoise-versus-hare
32. [S] Bryzgalova, Pavlova, Sikorskaya, CEPR DP 17688 — https://ideas.repec.org/p/cpr/ceprdp/17688.html
33. [S] Alexander and Imeraj, "The Bitcoin VIX and its variance risk premium" — https://sro.sussex.ac.uk/id/eprint/91094/ ; "Risk Premia in the Bitcoin Market" — https://arxiv.org/html/2410.15195v2

**Mean reversion**
34. [S] Do and Faff, FAJ 2010 — https://rpc.cfainstitute.org/research/financial-analysts-journal/2010/does-simple-pairs-trading-still-work ; https://arxiv.org/pdf/2010.01157
35. [S] NightShares closures — https://www.etf.com/sections/news/2-nightshares-etfs-close-after-struggling-gain-traction
36. [S] de Groot, Huij, Zhou, JBF 2012 — https://econpapers.repec.org/RePEc:eee:jbfina:v:36:y:2012:i:2:p:371-382 ; https://quantpedia.com/strategies/short-term-reversal-in-stocks

**Crypto**
37. [P] Zarattini, Pagani, Barbon, "Catching Crypto Trends", abstract — https://abarbon.com/papers/catching-crypto-trends
38. [S] Crypto momentum crashes and factors — https://link.springer.com/article/10.1007/s11408-025-00474-9 ; https://econpapers.repec.org/RePEc:taf:quantf:v:23:y:2023:i:12:p:1853-1869
39. [P] CoinGecko Research, "Hyperliquid HLP vault analysis", 2 Jul 2026 — https://www.coingecko.com/learn/hyperliquid-hlp-vault-analysis ; [S] https://thedefiant.io/news/defi/large-popcat-trades-result-in-usd5-million-loss-for-hyperliquid-vault
40. [S] Aavescan, Ethereum v3 USDC — https://aavescan.com/ethereum-v3/usdc
41. [P] abstract only: https://arxiv.org/abs/2503.14316 ; [S] https://arxiv.org/abs/2312.02752
42. [S] Apesteguia, Oechssler, Weidenholzer, "Copy Trading", Management Science 2020 — https://econpapers.repec.org/RePEc:inm:ormnsc:v:66:y:12:i:2020:p:5608-5622 ; Fomo study — https://yellow.com/news/fomo-copy-trading-94-percent-wallet-losses
43. [S] Listings — https://forklog.com/en/study-reveals-binance-token-listings-as-investor-traps/ ; https://rockawayx.com/insights/bullish-or-bearish-what-really-happens-when-tokens-list-on-a-cex
44. [S] Grid trading — https://arxiv.org/pdf/2506.11921

**Event-driven**
45. [S] Martineau, "Rest in Peace Post-Earnings Announcement Drift" — https://cfr.ivo-welch.info/published/papers/martineau2021rest.pdf ; https://anderson-review.ucla.edu/is-post-earnings-announcement-drift-a-thing-again/
46. [S] Greenwood and Sammon, "The Disappearing Index Effect" — https://www.nber.org/system/files/working_papers/w30748/w30748.pdf
47. [S] Merger arbitrage — https://informahealthcare.com/doi/abs/10.2469/faj.v66.n2.3 ; https://www.fa-mag.com/news/hedge-funds-are-placing-their-bets-on-the-mating-dance-28577.html
48. [S] Lucca and Moench — https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr512.pdf ; Kurov, Wolfe, Gilbert — https://www.skidmore.edu/economics/documents/KurovWolfeGilbert-TheDisappearingPre-FOMC-Announce-Drift-200914.pdf
49. [S] Turn of the month — https://www.atlantafed.org/research/publications/wp/2000/11.aspx ; https://quantpedia.com/strategies/turn-of-the-month-in-equity-indexes

**Prediction markets and LLMs**
50. [S] Bürgi, Deng, Whelan — https://cepr.org/voxeu/columns/economics-kalshi-prediction-market ; https://www.ifo.de/DocDL/cesifo1_wp12122.pdf
51. [S] Saguillo et al. — https://arxiv.org/abs/2508.03474
52. [S] Forecasting Research Institute — https://forecastingresearch.substack.com/p/llms-are-closing-the-gap-on-human
53. [S] Ksa decision of 20 Jan 2026 — https://kansspelautoriteit.nl/sites/default/files/2026-02/2026-01-20_22310_LOD%20Adventure%20One%20SQQ%20Inc._sanctiebesluit.pdf ; https://nos.nl/l/2602855 ; https://sigma.world/news/netherlands-dismisses-polymarket-appeal/
54. [S] Polymarket trader outcomes — https://www.digitaltoday.co.kr/en/view/49006/polymarket-traders-84-percent-lose-money-in-prediction-market ; https://beincrypto.com/polymarket-retail-traders-losses-galaxy-study/
55. [S] Alpha Arena — https://www.mexc.com/news/153114 ; https://stocktwits.com/news-articles/markets/equity/alibabas-qwen3-max-tops-crypto-trading-challenge-against-five-ai-models-including-gpt5-musks-grok/cL28d9pR3CN ; https://forklog.com/en/news/ai-model-grok-4-2-triumphs-in-trading-tournament
56. [S] FINSABER — https://arxiv.org/html/2505.07078v3
57. [S] Look-ahead bias — https://arxiv.org/html/2512.23847v1 ; https://arxiv.org/abs/2605.24564

**Capital scaling**
58. [P] FTMO trading objectives — https://ftmo.com/en/trading-objectives/ ; home page — https://ftmo.com/en/
59. [P] TradeInformer, "What FTMO tells us about prop firm finances" — https://www.tradeinformer.com/prop-weekly/what-ftmo-tells-us-about-prop-firm-finances
60. [S] FTMO prices — https://proptradingvibes.com/blog/ftmo-account-sizes-pricing ; https://www.jptradingcapital.com/blog/en/ftmo-pricing
61. [S] Prop-firm failures and warnings — https://fxnewsgroup.com/forex-news/retail-forex/prop-firm-the-funded-trader-halts-operations/ ; https://www.kenmoredesign.com/2026/01/06/global-regulatory-risks-for-prop-firms/
62. [S] Hyperliquid, "For vault leaders" — https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/for-vault-leaders
63. [S] ESMA Supervisory Briefing on copy trading, March 2023 — https://www.esma.europa.eu/sites/default/files/2023-03/ESMA35-42-1428_Supervisory_Briefing_on_Copy_Trading.pdf ; AFM sector letter — https://www.afm.nl/~/profmedia/files/doelgroepen/beleggingsondernemingen/2021/sectorbriefreikwijdteindividueelvermogensbeheerdocx.pdf

**Access, fees, regulation, tax**
64. [P] Finance Magnates, 24 Feb 2026 — https://www.financemagnates.com/forex/regulation/esma-tells-firms-perpetual-futures-fall-under-eu-cfd-rules
65. [S] ESMA, 27 Mar 2018, CFD and binary-option measures — https://www.esma.europa.eu/node/84933
66. [S] EU perpetual venues — https://www.businesswire.com/news/home/20250520169459/en/Kraken-Launches-Europes-Largest-Regulated-Futures-Offering-Strengthening-Market-Leading-Position-in-the-Region ; https://www.thetradenews.com/?p=100067 ; https://blockeden.xyz/blog/2026/04/17/okx-x-perps-europe-mifid-5-year-expiry-perpetual-futures/ ; https://fintelegram.com/perps-at-the-eu-perimeter-when-permissionless-meets-mifid-ii/
67. [S] Fees — https://support.kraken.com/sv-se/articles/cross-platform-fee-tier-changes ; https://support.kraken.com/articles/360048917612 ; https://www.datawallet.com/crypto/kraken-fees-explained ; https://bitvavo.com/en/fees
68. [S] AFM turbos — https://www.afm.nl/~/profmedia/files/onderwerpen/turbo/afm-turbos-factsheet-ned.pdf ; https://structuredretailproducts.com/news/75869/afm-68-of-retail-investors-lose-money-when-trading-turbos
69. [S] Chague, De-Losso, Giovannetti, "Day Trading for a Living?" — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101
70. [S] Barber, Lee, Liu, Odean — https://econpapers.repec.org/RePEc:eee:finmar:v:18:y:2014:i:c:p:1-24 ; https://faculty.haas.berkeley.edu/odean/papers/day%20traders/Day%20Trading%20Skill%20110523.pdf
71. [S] SEBI — https://business-standard.com/markets/news/over-93-retail-traders-lost-money-in-f-o-in-three-years-says-sebi-124092300853_1.html ; https://moneylife.in/article/91-percentage-of-retail-traders-lost-money-in-derivatives-losses-in-fo-surged-41-percentage-to-rs105-lakh-crore-in-fy25-sebi-study/77613.html
72. [S] BIS Working Paper 1049 — https://www.bis.org/publ/work1049.htm
73. [S] Box 3 in 2026 — https://www.sra.nl/nieuws/000000/2026/01/box-3-percentages-vrijstellingen-en-bedragen-2026 ; day-trading taxation — https://www.sra.nl/nieuws/004501/2025/05/het-belasten-van-inkomsten-uit-daytrading
74. [P] FRED CSV downloads `ECBDFR`, `ECBESTRVOLWGTTRMDMNRT`, `DFF`, `DGS3MO`, `CBBTCUSD`, `SP500`, `DEXUSEU` — https://fred.stlouisfed.org/graph/fredgraph.csv?id=CBBTCUSD (replace the id)
75. [P] justETF: Vanguard LifeStrategy 60 — https://www.justetf.com/en/etf-profile.html?isin=IE00BMVB5P51 ; Vanguard FTSE All-World — https://www.justetf.com/en/etf-profile.html?isin=IE00BK5BQT80 ; Xtrackers EUR Overnight Rate Swap — https://www.justetf.com/en/etf-profile.html?isin=LU0290358497
76. [S] MEV and MiCA — https://thedefiant.io/news/regulation/eu-threatens-to-regulate-mev-as-market-abuse
77. [S] Deribit availability — https://www.datawallet.com/crypto/deribit-restricted-countries

**Repository**
78. REPO: `research/FINDINGS.md` §5d (lines 146–165: carry, T3, T7, T9, T10, T11, T13, T15, T23, T25); memory notes `free-data-convexity-wall`, `structural-not-predictive`, `winning-bot-conclusion-and-x2-pivot`, `memecoin-structural-kills`, `first-original-survivors`, `owner-goal-make-money-not-edge`, `pivot-money-ideas-2026-08-31`, `access-audit-t105-2026-09-30`, `owner-wants-solana-trading-harness`, `solana-clean-ledger`, `fomopulse-third-party-read`; `research/factory/PREREGISTRATION_v1.md`.

---

## Appendix A — how the COMPUTED numbers were made

**Bitcoin base rates (§2.11).** FRED series `CBBTCUSD` (Coinbase daily close, 2014-12-01 to 2026-11-09, 4,327 observations). CAGR is from first to last close. Volatility and Sharpe use daily simple returns annualised with 365 days and a zero risk-free rate. Drawdown is peak to trough on closes. DCA buys one unit of currency at the first available close of each month and is valued at the last close; rolling windows use the same rule.

**Sharpe needed to pass a t ≥ 2 gate (§0).** Standard error of an annualised Sharpe ≈ 1/√years, so the required Sharpe is 2/√years: 0.64 for 9.85 years, 0.91 for 4.85, 1.18 for 2.85.

**Prop-challenge simulation (§2.10).** 40,000 paths per cell, seed 20261110, NumPy. Daily returns are independent with mean Sharpe × vol / 252 and standard deviation vol / √252, added to a balance measured as a fraction of initial capital.

```python
def phase(n, target, mu_d, sd_d, tdf, max_days):          # one challenge phase, capped at 3 years
    bal = np.zeros(n); alive = np.ones(n, bool); passed = np.zeros(n, bool); days = np.zeros(n, int)
    for d in range(max_days):
        idx = np.flatnonzero(alive)
        if idx.size == 0: break
        r = draw(idx.size, mu_d, sd_d, tdf)               # normal, or Student-t(4) scaled to unit variance
        b = bal[idx] + r
        fail = (r <= -0.05) | (b <= -0.10)                # 5 % daily loss, static 10 % maximum loss
        ok = (~fail) & (b >= target)                      # +10 % in phase 1, +5 % in phase 2
        bal[idx] = b; days[idx] += 1
        passed[idx[ok]] = True; alive[idx[fail | ok]] = False
    return passed, days

def funded(n, mu_d, sd_d, tdf, horizon=504, split=0.80, every=21):
    bal = np.zeros(n); alive = np.ones(n, bool); paid = np.zeros(n); got = np.zeros(n, bool)
    for d in range(1, horizon + 1):
        idx = np.flatnonzero(alive)
        if idx.size == 0: break
        r = draw(idx.size, mu_d, sd_d, tdf)
        b = bal[idx] + r
        fail = (r <= -0.05) | (b <= -0.10)
        bal[idx] = b; alive[idx[fail]] = False
        if d % every == 0:                                # monthly payout of 80 % of profit, balance resets
            j = np.flatnonzero(alive & (bal > 0))
            paid[j] += split * bal[j]; got[j] = True; bal[j] = 0.0
    return paid, got, alive

# EV per attempt = P(pass both) × (mean payout × account + P(any payout) × fee) − fee
```

Everything the simulation leaves out works against the trader: spreads and overnight financing, intraday breaches of the daily limit, consistency and prohibited-practice rules, payout refusals, and the firm failing.
