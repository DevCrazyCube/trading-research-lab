# INVENT 0822 — theme: CRYPTO **SPOT** with a **STRUCTURAL TETHER**

**Date:** 2026-08-22 · **Formulas tested:** 36 · **Promotions: 0** · **Verdict: no formula clears
the bar; the theme's durable output is a structural finding, not an edge.**

Harness: `scripts/trading_bot/invent0822_tether_{lib,build,sweep,events,liquidity}.py`.
Results: `INVENT_0822_crypto_tether.json` (36 formulas + noise bar + UST attribution +
episode census), `..._DIAG.json` (per-spread OU/ADF/Hurst/ρ1), `..._EVENTS.json`
(event-level power check), `..._LIQUIDITY.json` (liquidity-floor robustness).
Data: cached free panels only (`research/data/xspot_cache/`), no network, no orders, no money.

---

## 0. THE ONE-PARAGRAPH ANSWER

I built four families of crypto-spot spreads whose fair value is pinned by a **real economic
mechanism** — issuer redemption at \$1 (stablecoin vs USDT), unwrap/withdrawal (wBTC/BTC,
wBETH/ETH, BETH/ETH, BNSOL/SOL, XAUT/PAXG), same-venue no-arbitrage (triangular USDC- and
TRY-quoted cross-rates), and cross-venue arbitrage (Coinbase vs Binance on the same asset) —
and tested **36 original fade formulas** on them. **The ρ1(Δs) gate killed three of the four
families before a single P&L was computed**, and the backtests then confirmed the gate exactly:
those families post *high* gross Sharpes (up to **4.07**) and *catastrophic* nets (down to
**−61**), with break-evens of **0.1–5 bp/side against a 10 bp fee** — the classic signature of
fading bid-ask bounce. The one family that passes the gate, **stablecoin peg deviation**, is real
(half-lives 2–8 days, dislocations of ±70 to ±300 bp, ρ1 −0.07 … −0.30) but is **not a Sharpe
object at all**: it is flat most of the time and resolves in **15 independent stress episodes in
8 years**, and its payoff is **short a deep-out-of-the-money put on issuer solvency**. On the
correct unit of observation the unfiltered trade earns **−146 bp per episode, t = −0.50**, because
one episode (UST, May 2022) is **−4,159 bp**. Two variants dodge that tail *structurally*, and
both then **die on a liquidity floor**: the design-window edge lives in pairs trading
\$0.05–0.9M/day, where the 10 bp taker charge is fiction. Nothing is promoted.

---

## 1. WHY THIS IS NOT A RE-RUN

| what the ledger already killed | how this round differs |
|---|---|
| `INVENT_D0821_crypto_spot_xs` (34 formulas) families **E** (cross-quote) and **H** (cross-venue) | Those were **cross-sectional tilts**: dispersion used to predict *the coin's own return*. Every formula here is a **paired convergence trade on the spread itself** — the P&L object is Δ(spread), not the coin's return. Disjoint P&L, disjoint sign convention. |
| `INVENT_D0821` family **F1_TS_PEGDEV** | F1 was a one-name z-score tilt on the peg premium. Family A here is a 15-name **survivorship-bias-free** peg book with a **$1 redemption anchor** (not a fitted mean), band/asymmetry/seasoning/tail-stop variants, and an **event-level** power analysis. |
| Wrapped & staked tokens (wBTC, wBETH, BETH, BNSOL), gold tokens (XAUT/PAXG) | **Never touched by this programme.** First test. |
| Perp funding / `count_long_short_ratio` | Data-dead; **zero** formulas spent on it. |
| Regime conditioning / gating (0/107, round 3) | **Zero** formulas are conditioners. Every one is a primary fade. |
| Fast daily equity/crypto cross-sectional reversal | Not re-mined. |
| Already-killed tethers (crosslist 0/30, ETF-structural 0/51, holdco 0/130, GDX/GDXJ) | Different asset class entirely. |

**Signs are not fitted.** Every formula fades *toward* the structural anchor; the direction is
given by the mechanism, not by the design window. That is why the honest multiple-testing bar
below is the **one-sided** `sqrt(2 ln N)`, not the sign-agnostic `sqrt(2 ln 2N)`.
**Thresholds are not searched.** Every band is a round number (5/10/15/20/25/30/50/100/300 bp)
declared before the run.

---

## 2. DATA, UNIVERSE, WINDOWS, COSTS

**Panels** (all cached, all free): Binance spot daily USDT klines (677 symbols, delisted names
included, 2017-08 → 2026-07), Binance cross-quote daily (330 `*USDC`, 366 `*TRY` + `USDTTRY`),
Coinbase Exchange daily `*-USD` (91 products).

**The stablecoin universe is chosen by an objective, listing-window-only screen** — a `*USDT`
pair whose **first 60 live days** have median price within 2% of 1.00 and daily vol < 1%. It is
decided on data that predates every depeg, so it **admits UST by construction** (UST traded at
\$1.0003 with 0.079%/day vol for its first 60 days, then went to \$0.2458). 15 names:

`BFUSD, BUSD, FDUSD, PAX, RLUSD, sUSD, TUSD, USD1, USDC, USDe, USDP, USDS, UST, U, XUSD`

**Windows.** Design **< 2023-01-01**, held out **≥ 2023-01-01** (same split as the prior crypto
round, for comparability). Instruments that do not span that boundary (the wrapped/staked family
starts 2023-04) use their **own 60/40 split**, recorded per formula in the JSON.

**Execution.** Signal from the **close of day d−1**; book entered at the **open of day d**, marked
to the **open of day d+1**; cost charged on `Σ|Δw| × legs` the day weights move. Binance is 24/7,
so open[d] ≈ close[d−1] — the entry is near-instantaneous, which is why every formula is *also*
reported under a **one-extra-day LAG1 placebo** (`lagD` column). Cross-venue formulas use
close-to-close (the free Coinbase candle has no usable open).

**Costs.** Headline **10 bp/side/leg** (Binance spot taker, base tier). Shock **20 bp**.
Sensitivity **1 bp** (Binance has run zero-fee stablecoin-pair promotions; reported, never headline).

**Self-test** (`invent0822_tether_lib` + a synthetic path): a +50 bp dislocation that decays is
captured as **+44.9 bp** with **2.0 legs** of turnover; the result is invariant to shifting the
whole path one day (no lookahead); and a **pure iid measurement-bounce series earns gross −0.21
Sharpe, net −3.67** — the harness does not manufacture profit from bounce.

---

## 3. THE ρ1(Δs) GATE DID THE WORK — BEFORE ANY BACKTEST

`ρ1(Δs) → −0.50` is the signature of a spread that is nothing but bid-ask / non-synchronous
measurement error. Gate: **ρ1 > −0.35**.

| tether spread | n | half-life | sd (bp) | p01 … p99 (bp) | Hurst | ADF t | **ρ1(Δs)** | gate |
|---|---:|---:|---:|---:|---:|---:|---:|:--|
| USDC/USDT | 2621 | 2.9 d | 25.0 | −70 … +103 | 0.449 | −12.35 | **−0.072** | **PASS** |
| TUSD/USDT | 2819 | 7.4 d | 54.0 | −136 … +247 | 0.501 | −9.21 | **−0.118** | **PASS** |
| FDUSD/USDT | 1102 | 2.5 d | 13.2 | −31 … +36 | 0.433 | −12.43 | **−0.160** | **PASS** |
| USD1/USDT | 436 | 3.1 d | 5.6 | −10 … +14 | 0.366 | −6.97 | **−0.172** | **PASS** |
| sUSD/USDT | 494 | 3.0 d | 73.5 | −81 … +234 | 0.380 | −5.74 | **−0.288** | **PASS** |
| BUSD/USDT | 1548 | 2.0 d | 8.8 | −30 … +22 | 0.477 | −8.35 | **−0.301** | **PASS** |
| PAX/USDT | 1069 | 8.4 d | 62.3 | −104 … +300 | 0.411 | −7.98 | **+0.003** | **PASS** |
| **implied USDT/USD (x-venue)** | 3271 | 2.1 d | 62.8 | −177 … +218 | 0.456 | −7.01 | **−0.313** | **PASS** |
| BNSOL/SOL | 653 | — (accrual) | 310 | +75 … +1156 | 0.433 | −1.13 | **−0.349** | PASS (marginal) |
| BETH/ETH | 223 | 11.6 d | 54.9 | −233 … +2 | 0.503 | −2.47 | **−0.321** | PASS (short) |
| XAUT/PAXG | 128 | 3.6 d | 13.3 | −46 … +9 | 0.567 | −3.46 | −0.281 | PASS (too short) |
| USDP/USDT | 1621 | 1.9 d | 8.9 | −15 … +22 | 0.449 | −10.64 | **−0.434** | **fail** |
| USDe/USDT | 326 | 3.6 d | 5.0 | −9 … +8 | 0.436 | −3.87 | **−0.363** | **fail** |
| **wBTC/BTC** | 1191 | 1.4 d | 14.1 | −36 … +33 | 0.298 | −6.10 | **−0.450** | **fail** |
| **wBETH/ETH** | 1109 | — (accrual) | 251 | +95 … +967 | 0.386 | −1.01 | **−0.489** | **fail** |
| **triangular USDC gap (agg)** | 2620 | 0.1 d | 5.5 | −15 … +18 | 0.264 | −50.81 | **−0.534** | **fail** |
| triangular USDC gap (BTC) | 2620 | 0.2 d | 3.5 | −11 … +10 | 0.265 | −26.66 | **−0.486** | **fail** |
| **triangular TRY gap (agg)** | 2411 | 0.2 d | 8.2 | −25 … +26 | 0.247 | −22.82 | **−0.481** | **fail** |
| **x-venue basis (agg, num-neutral)** | 3271 | 0.8 d | 19.0 | −34 … +94 | 0.420 | −9.78 | **−0.469** | **fail** |
| x-venue ETH / SOL / XRP | 3271/1871/1809 | 0.3–0.6 d | 4.6–18 | — | 0.35–0.39 | −13 … −40 | −0.45 … −0.48 | **fail** |

**Read the triangular and cross-venue rows carefully.** ADF t of **−50.8** and a **0.1-day**
half-life look like the most powerfully mean-reverting series in the whole programme. They are
the most *measurement-error-dominated* series in the whole programme. **ADF strength and low
Hurst are actively anti-diagnostic here; only ρ1 separates the two cases.**

---

## 4. THE 36 FORMULAS, NOTHING DROPPED

`Dgr/Dgt` design gross Sharpe / t · `Dnet/Dnt` design net · `Hgr/Hgt/Hnet/Hnt` held-out ·
`BEd` design break-even bp/side · `net20`/`net1` design net at the 20 bp shock / 1 bp floor.
Sorted by design gross Sharpe.

| formula | fam | split | Dgr | Dgt | Dnet | Dnt | Hgr | Hnet | Hnt | BEd | net20 | net1 |
|---|:--|:--|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `B1_WBTC_LIN30` | B | own | **4.07** | 5.69 | −9.02 | −12.61 | 1.25 | −11.02 | −12.59 | 2.7 | −14.64 | 2.53 |
| `B5_WBETH_TREND60` | B | own | 2.75 | 3.72 | −9.43 | −12.72 | 1.29 | −5.25 | −5.79 | 2.0 | −15.11 | 1.37 |
| `B10_GOLDTOKEN_RV` | B | own | 2.75 | 1.25 | −7.42 | −3.39 | 4.35 | −18.31 | −6.85 | 2.5 | −13.62 | 1.67 |
| **`A12_PEG_BAND20_SEASONED`** | A | cal | **2.64** | **5.66** | **+1.31** | **+2.82** | 1.17 | **+0.38** | +0.72 | **19.9** | −0.01 | 2.51 |
| `B2_WBTC_BAND30` | B | own | 2.46 | 3.43 | −1.95 | −2.73 | 0.13 | −0.22 | −0.25 | 5.1 | −3.85 | 2.00 |
| `D5_XV_USDT_IMPLIED_LIN` | D | cal | 2.28 | 4.43 | −0.15 | −0.30 | 0.19 | −0.99 | −1.83 | 9.4 | −2.42 | 2.03 |
| `C2_TRI_TRY_BAND30` | C | cal | 2.17 | 3.78 | −6.06 | −10.53 | 1.44 | −9.50 | −17.98 | 2.6 | −12.53 | 1.34 |
| `B3_WBTC_DISC_ONLY` | B | own | 2.14 | 3.00 | −1.92 | −2.68 | 0.13 | −0.22 | −0.25 | 4.4 | −3.21 | 1.68 |
| `C1_TRI_TRY_XS` | C | cal | 2.00 | 3.48 | −21.21 | −36.86 | 2.78 | −61.02 | −115.47 | 0.8 | −35.64 | −0.55 |
| `D4_XV_USDT_IMPLIED` | D | cal | 1.91 | 3.72 | **+1.20** | **+2.34** | −0.01 | −0.03 | −0.06 | 26.9 | +0.48 | 1.84 |
| `B7_WRAP_BOOK` | B | own | 1.78 | 2.48 | −1.87 | −2.61 | 1.19 | +0.54 | +0.62 | 4.7 | −4.18 | 1.41 |
| `B6_BETH_LIN30` | B | own | 1.76 | 1.06 | −0.72 | −0.43 | 3.37 | −17.20 | −8.50 | 7.0 | −3.00 | 1.51 |
| **`A6_PEG_PREM_ONLY`** | A | cal | 1.35 | 2.90 | **+0.84** | +1.79 | 1.18 | **+0.49** | +0.93 | **26.0** | +0.31 | 1.30 |
| `C1_TRI_USDC_XS` | C | cal | 1.33 | 2.59 | −19.23 | −37.40 | 1.03 | −30.64 | −56.40 | 0.6 | −33.88 | −0.84 |
| `B9_BNSOL_TREND60` | B | own | 1.19 | 1.23 | −5.08 | −5.26 | 1.71 | −9.81 | −8.30 | 1.9 | −10.29 | 0.55 |
| `C2_TRI_USDC_BAND30` | C | cal | 0.96 | 1.86 | −5.64 | −10.96 | 0.01 | −6.32 | −11.64 | 1.4 | −11.35 | 0.28 |
| `B4_WBETH_CUMMAX` | B | own | 0.89 | 1.21 | −0.70 | −0.95 | 1.29 | +0.72 | +0.80 | 5.6 | −2.00 | 0.74 |
| `B8_BNSOL_CUMMAX` | B | own | 0.68 | 0.70 | −0.53 | −0.55 | 0.91 | −0.87 | −0.74 | 5.6 | −1.60 | 0.56 |
| `A10_PEG_SQRT` | A | cal | 0.50 | 1.07 | −0.57 | −1.23 | 2.60 | −4.08 | −7.71 | 4.7 | −1.63 | 0.39 |
| `D2_XV_NUMNEUT_BAND50` | D | cal | 0.50 | 1.16 | −1.88 | −4.35 | 0.04 | −1.84 | −3.48 | 2.0 | −3.76 | 0.26 |
| `A1_PEG_LIN20` | A | cal | 0.49 | 1.06 | −0.41 | −0.88 | 2.35 | −2.79 | −5.28 | 5.5 | −1.30 | 0.40 |
| `A15_PEG_ANCHOR_FITSCALE` | A | cal | 0.42 | 0.89 | −0.62 | −1.32 | 2.53 | −5.31 | −10.05 | 4.0 | −1.64 | 0.31 |
| `A7_PEG_Z90_FITTEDMEAN` | A | cal | 0.24 | 0.52 | −0.69 | −1.49 | 2.45 | −5.01 | −9.48 | 2.6 | −1.63 | 0.15 |
| `C3_TRI_TRY_AGG` | C | cal | 0.16 | 0.28 | −0.98 | −1.70 | 0.50 | +0.45 | +0.85 | 1.4 | −2.08 | 0.05 |
| `D1_XV_NUMNEUT_LIN` | D | cal | 0.16 | 0.37 | −6.46 | −14.99 | 0.34 | −29.32 | −55.48 | 0.2 | −11.77 | −0.54 |
| `A2_PEG_BAND20` | A | cal | 0.15 | 0.33 | −0.29 | −0.62 | 1.53 | +0.36 | +0.68 | 3.5 | −0.73 | 0.11 |
| `A11_PEG_BAND20_LIQW` | A | cal | 0.08 | 0.18 | −0.44 | −0.94 | 1.92 | +0.34 | +0.64 | 1.6 | −0.96 | 0.03 |
| `D3_XV_XS` | D | cal | 0.07 | 0.17 | −13.01 | −30.17 | 0.23 | −34.70 | −65.66 | 0.1 | −18.76 | −1.56 |
| `A3_PEG_BAND50` | A | cal | 0.06 | 0.13 | −0.14 | −0.31 | 0.85 | +0.61 | +1.16 | 2.9 | −0.34 | 0.04 |
| `A13_PEG_BAND20_SOLVSTOP` | A | cal | −0.11 | −0.24 | −0.51 | −1.10 | 1.16 | −0.03 | −0.06 | −2.8 | −0.91 | −0.15 |
| `A14_PEG_HOLD10` | A | cal | −0.19 | −0.40 | −0.46 | −0.98 | 1.20 | −0.14 | −0.26 | −7.0 | −0.72 | −0.21 |
| `A8_PEG_XS_DEMEAN` | A | cal | −0.22 | −0.47 | −1.09 | −2.34 | 1.93 | −2.70 | −5.11 | −2.5 | −1.96 | −0.31 |
| `A4_PEG_BAND100` | A | cal | −0.23 | −0.49 | −0.27 | −0.59 | 0.85 | +0.74 | +1.40 | −52.9 | −0.32 | −0.23 |
| `A9_PEG_EVENT5` | A | cal | −0.27 | −0.58 | −0.45 | −0.96 | 1.16 | +0.86 | +1.62 | −15.3 | −0.62 | −0.29 |
| `C3_TRI_USDC_AGG` | C | cal | −0.38 | −0.73 | −2.99 | −5.82 | 0.60 | −0.03 | −0.05 | −1.3 | −4.90 | −0.66 |
| `A5_PEG_DISC_ONLY` | A | cal | −0.42 | −0.91 | −0.56 | −1.19 | 0.96 | +0.05 | +0.10 | −31.6 | −0.69 | −0.44 |

Family key — **A** stablecoin peg vs USDT, fair \$1, 15 names, 1 leg (12 formulas: linear /
20-50-100 bp bands / discount-only / premium-only / fitted-90d-mean contrast / XS-demeaned /
event-hold / sqrt sizing / liquidity-weighted / seasoned-issuer / 300 bp solvency stop / fixed
10-day clock / anchored-mean-fitted-scale). **B** wrapped & staked, 2 legs (10 formulas: wBTC/BTC
linear-band-discount, wBETH/ETH cummax-accrual and trend, BNSOL/SOL cummax and trend, BETH/ETH
parity, XAUT-vs-PAXG gold parity, joint wrapped book). **C** triangular no-arb, 2 legs
(6 formulas: per-coin USDC and TRY gaps, XS-demeaned and banded, plus the basket-implied stable
price traded against the quoted pair). **D** cross-venue Coinbase-vs-Binance, 2 legs (5 formulas:
BTC-numeraire-neutral linear and banded, XS-demeaned, and the cross-venue-implied USDT/USD peg
executed on the USDCUSDT pair, banded and linear).

---

## 5. THE NOISE BAR

Sign-flip block bootstrap (10-day blocks, 2,000 replicates) of the **max |Sharpe| over all 36
formulas jointly**, one global sign vector per replicate (so cross-formula correlation survives)
with each formula scored on **its own** design window.

| statistic | value |
|---|---|
| **design t-bar, one-sided `sqrt(2 ln 36)`** (signs are structural, not fitted) | **2.68** |
| design t-bar, sign-agnostic `sqrt(2 ln 72)` | 2.92 |
| **programme-cumulative `sqrt(2 ln 959)`** | **3.70** |
| 1 SE of one family-A design Sharpe (4.0 y) | 0.467 |
| analytic bar in Sharpe units, family-A window | **1.25** |
| bootstrap E[max &#124;Sharpe&#124;] on **gross** | 1.75 (p95 3.28) |
| bootstrap E[max &#124;Sharpe&#124;] on net | 2.92 (p95 5.61) |

The bootstrap numbers are inflated by the short-window family-B formulas (77–450 design days),
which is why the **per-formula t against 2.68** is the comparison that actually means something.

**Nine formulas clear the gross t-bar of 2.68 — and that is the round's sharpest methodological
result, not a discovery.** `B1_WBTC_LIN30` posts design gross **t = 5.69** and dies at
**−9.02 net**, on a break-even of **2.7 bp/side against a 10 bp fee**. `C1_TRI_TRY_XS` posts gross
t 3.48 and net **−21.21**, break-even 0.8 bp. `D3_XV_XS` break-even **0.1 bp**. Their gross P&L
**is** the half-spread they would have paid, measured. Hence:

> **Refinement to the round-2 lesson.** *"Clear the multiple-testing bar on GROSS Sharpe first"*
> is necessary but **not sufficient for an RV/tether spread**: a bounce-dominated spread
> manufactures gross significance. **The ρ1(Δs) gate must be applied BEFORE the gross bar, not
> after it.** Every one of the nine gross-bar-clearing formulas that sits on a ρ1-failing spread
> has a break-even under 5.1 bp/side.

---

## 6. THE PEG TRADE IS NOT A SHARPE OBJECT — IT IS A SHORT CREDIT PUT

Family A is flat most days and resolves in a handful of stress episodes. Counting **any name more
than 100 bp off peg, merged across names, episodes separated by ≥30 quiet days**, the whole 8-year
sample contains **15 independent episodes** (10 design, 5 held out):

`2018-06 TUSD` · `2018-09→2019-02 PAX,TUSD,USDC,USDS` · `2019-04→05 (same four)` · `2019-06 (same
four)` · `2020-02→05 USDS` · `2020-12→2021-05 sUSD` · `2021-06 sUSD` · `2021-09 sUSD` ·
`2021-12 sUSD` · **`2022-05 UST`** · `2023-03 USDC,USDP (SVB)` · `2024-01→03 TUSD` ·
`2024-12 TUSD` · `2025-04 FDUSD` · `2025-06 TUSD`

**n = 15 is the real sample size, not 1,478 days.** Re-scored per episode (net, 10 bp):

| formula | bp/episode | **t across 15 episodes** | % episodes + | worst episode | design / held-out mean |
|---|---:|---:|---:|---:|---|
| `A2_PEG_BAND20` (the natural form) | **−146** | **−0.50** | 80% | **−4,159 bp** | −254 / +70 |
| `A5_PEG_DISC_ONLY` (buy the discount) | **−614** | **−0.91** | 60% | **−10,082 bp** | −936 / +30 |
| `A3_PEG_BAND50` | −110 | −0.30 | 93% | −5,148 bp | −221 / +113 |
| `A12_PEG_BAND20_SEASONED` | +144 | +2.28 | 73% | −157 bp | +170 / +92 |
| `A6_PEG_PREM_ONLY` (sell the premium) | +107 | **+2.74** | 80% | **0 bp** | +138 / +45 |

**The natural formula loses.** 80% of episodes are winners and the mean is −146 bp, because one
episode is −4,159 bp. Fading a stablecoin discount is **selling a deep-OTM put on the issuer**,
and free daily price data cannot price the default probability. UST's leg P&L alone:
**−4,088 bp** in `A2` (67 days positioned), **−10,044 bp** in `A5` (9 days). Design-window skew
for `A2` is **−23.4**, worst day −2,774 bp, max drawdown −4,234 bp; the held-out window's skew is
**+3.6** with a worst day of −161 bp — **the two windows differ mainly in whether an issuer failed
in them**, which is why every wide-band peg formula reads "design ≈ 0, held-out positive."

Two variants avoid the tail by construction rather than by luck, and both must be reported with
their caveat:

- **`A12_PEG_BAND20_SEASONED`** (trade only issuers with ≥250 days of quoted history) is the
  search maximum: design net **+1.31 (t 2.82)**, gross **2.64 (t 5.66)**, break-even **19.9 bp/side
  ≈ 2× the fee**, held-out net **+0.38**. But the attribution is unambiguous: **it never traded
  UST at all** (0 days), because UST was ~140 days old when it collapsed. `A2` *without* UST is
  design net **+0.72**; `A2` *with* UST is **−0.29**. The filter has **exactly one binding
  instance** in the design window, and out of sample it **lowers** gross Sharpe (1.53 → 1.17).
  Its event-level t of **2.28 is below the 36-formula bar of 2.68**, and far below 3.70.
- **`A6_PEG_PREM_ONLY`** (only ever *sell* a stablecoin trading rich to USDT, never buy a
  discount) is the structurally tail-safe leg: it **cannot be hit by an issuer failure** — it was
  **+54 bp on UST** — worst episode **0 bp**, positive in both windows on gross (1.35 / 1.18), net
  (+0.84 / +0.49) and per episode (+138 / +45 bp). Its event-level t is **2.74**, at the
  36-formula bar, below the programme bar. Its own tail is a **USDT** failure, which has never
  occurred in sample and is therefore unmeasured, not absent.

---

## 7. THE LIQUIDITY FLOOR KILLS BOTH

A 10 bp taker charge is only credible where there is a book. Median \$volume/day:
BUSD 338M, FDUSD 302M, USDC 202M, UST 92M, USD1 56M, RLUSD 19M, U 15M, XUSD 7.0M, TUSD 6.0M,
PAX 5.9M, BFUSD 5.5M, USDe 4.8M, **USDP 0.84M**, **sUSD 0.17M**, **USDS 0.05M**.

Re-run under a trailing-30-day median-\$volume floor applied at the signal date:

| floor | `A2_PEG_BAND20` D-net | `A12_SEASONED` D-net | `A6_PREM_ONLY` D-net |
|---|---:|---:|---:|
| none | −0.29 | **+1.31** (t 2.82) | **+0.84** (t 1.79) |
| ≥ \$5M/day | −0.53 | +0.69 (t 1.49) | +0.19 (t 0.41) |
| ≥ \$25M/day | −0.62 | **−0.03** (t −0.07) | **+0.08** (t 0.18) |

**The design-window edge lives entirely in pairs trading \$0.05–0.9M/day** — sUSD alone
contributes +2,894 bp of `A2`'s gross, USDS +246 bp, USDP +279 bp — where a 10 bp taker fee is
fiction and the real half-spread is unmeasurable on daily klines. On liquid names only, both
candidates are flat in design. *(The liquid-only **held-out** numbers are better — `A6` reads
Sharpe +1.27, t 2.40 at the \$25M floor — but that restriction was chosen **after** seeing the
design result, so it is held-out mining and is recorded here as a forward-log observation, not
as evidence.)*

---

## 8. VERDICT AND WHAT SURVIVES AS A FACT

**0 promotions. 0 shortlist entries.** Nothing here goes near the frozen basket.

The theme is not "noise" in the ordinary sense — three of its four sub-families were killed by a
**deterministic structural test**, and the fourth has a real, mechanism-explained convergence.
It fails for two reasons that are worth more than a formula:

1. **`ρ1(Δs)` is the master gate for tether RV, and it must run first.** wBTC/BTC (−0.450),
   wBETH/ETH (−0.489), triangular no-arb gaps (−0.48 … −0.55) and per-name cross-venue basis
   (−0.45 … −0.48) are **measurement bounce with an economic story attached**. Their ADF t-stats
   (down to −50.8) and Hurst exponents (0.25) are the *best* in the programme and are
   anti-diagnostic. Nine of them clear the gross t-bar; all nine break even under 5.1 bp/side.
2. **A structurally-anchored spread can still be untradable because of its payoff SHAPE.** The
   stablecoin peg is the one genuine crypto-spot tether on free data — and fading it is short a
   credit put resolving 15 times in 8 years. Daily-Sharpe arithmetic reports t = 2.82 for a book
   whose event-level t is 2.28 and whose unfiltered form is **−146 bp/episode**.

**Recorded as Pile-B "positive-but-unproven", not promoted:** `A6_PEG_PREM_ONLY` — premium-side
only, tail-safe against issuer failure, positive gross/net/per-episode in both windows
(+0.84 / +0.49 net Sharpe, +2.74 event t), break-even 26 bp/side ≈ 2.6× the headline fee. It is
sub-bar, it is capacity-tiny (838 positioned days in 8 years across 15 names), it is flat once a
\$25M liquidity floor is applied to the design window, and its own tail — a USDT failure — is
unmeasured. It earns a forward log line, nothing more.

**Do not re-propose:** triangular / cross-quote no-arb gaps, per-name cross-exchange spot basis,
wBTC-vs-BTC, wBETH/BETH/BNSOL-vs-underlying, XAUT-vs-PAXG, index-token-vs-basket on free daily
data (same construction), and the discount side of the stablecoin peg.
