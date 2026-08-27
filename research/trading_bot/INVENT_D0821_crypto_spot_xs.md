# INVENT D0821 — theme: CRYPTO **SPOT** & cross-sectional (free Binance spot klines)

**Date:** 2026-08-21 · **Formulas tested:** 34 · **Survivors: 0** · **Verdict: the theme is noise
at spot execution cost.**

Harness: `scripts/trading_bot/xspot_sweep.py` (families A–D, F, G) +
`scripts/trading_bot/xspot_sweep2.py` (families E, H, pooled null, shared-price placebo).
Data builders: `xspot_enumerate.py`, `xspot_fetch2.py`, `xspot_panel.py`, `xspot_coinbase.py`.
Library: `xspot_lib.py`. Results: `INVENT_D0821_crypto_spot_xs.json`,
`..._pnl.npz`, `..._PLACEBO.json`.

---

## 0. THE ONE-PARAGRAPH ANSWER

I built a **survivorship-bias-free** Binance spot panel (677 USDT pairs, delisted names
included — LUNA, FTT, BCC, MATIC are all in it — 2017-08 → 2026-07) plus a cross-quote panel
(367 TRY pairs, 333 USDC pairs) and a free Coinbase daily panel (91 USD products), and tested
**34 original formulas** across the six sub-themes I was given: spot cross-sectional
momentum/reversal, spot taker-flow microstructure, BTC-dominance rotation, spot volume/vol
breakouts, cross-quote and cross-exchange dispersion, stablecoin peg/on-ramp flow, and
spot-listing dynamics. **The best design-window net Sharpe in the whole search is 1.43. The
sign-flip block-bootstrap E[max |Sharpe|] over 34 correlated formulas is 1.15, its p95 is 1.57,
and the conservative sign-agnostic analytic bar `sqrt(2 ln 68)·SE` is 1.45.** The best formula
does not clear its own theme bar, and it collapses from +1.43 design to **+0.03** held out.
Nothing is promoted; nothing goes on a shortlist.

The theme's one *durable* output is not a formula, it is a **cost wall**, and it is sharp:
crypto spot daily cross-sections *do* contain measurable structure, but **it lives almost
entirely inside the 10 bp Binance spot taker fee**. The three highest-gross-Sharpe reversal
formulas have break-evens of **1.5–3.4 bp/side**. That is the same shape as the free-data
convexity wall already in the ledger, now measured on a second asset class.

---

## 1. WHY THIS IS NOT A RE-RUN

Checked against `THOROUGH_REEXAM.md`, `FORMULA_SWEEP_MASTER.md`, `INVENT_R3_MASTER.md`,
`FINDINGS.md`, and `perpmicro_sweep2.py`'s 51 class-A names.

| what the ledger already killed | how this round differs |
|---|---|
| Round-2 (51) and round-3 perp-structure (32) formulas | **Every prior crypto formula in the programme is on USD-M PERPS.** This is the first spot panel in the repo. Different instrument, different fee, different universe (677 vs 439), and **6 extra years of history** (2017-08 vs 2022-01). |
| R3 exotic family A — new-listing **perp** dynamics | G1–G3 are **spot** listings. A spot listing is a different event: no funding, no leverage, and the cohort includes coins that never got a perp. |
| R3 exotic family F — stablecoin **supply** (DefiLlama aggregate) | F1/F2 are the **market price** of stablecoins against USDT on Binance (peg premium) and the **traded volume** of the stablecoin pairs. Adjacent mechanism, disjoint data. |
| R3 exotic family D — dispersion / avg-correlation regimes | E and H are **price dispersion of the same coin across quote currencies and across venues**, not return dispersion across coins. |
| Regime conditioning / gating (0/107 in round 3) | **Zero formulas spent on conditioners or gates.** Every formula here is a primary signal. |
| VRP, box, Orphan Flush, Coiled, the 18 SIZE candidates, published equity edges | Not touched. |

`A1_XS_REV1` (plain one-day cross-sectional reversal) is included deliberately **as a control**,
not as a discovery — it anchors what the panel's best-known effect is actually worth.

---

## 2. DATA, WINDOWS, COSTS

**Primary panel** — `research/data/xspot_cache/spot_daily.npz`, 21 MB.
Binance spot monthly 1d klines from `data.binance.vision` for **every USDT pair the archive has
ever hosted** (723 enumerated, 677 with ≥30 bars), 2017-08-01 → 2026-07-31 (3,307 days).
Fields per name/day: open, high, low, close, base volume, quote volume, **trade count**, **taker-buy
quote volume**. The archive contains delisted symbols, so the panel is **survivorship-bias-free** —
verified directly (BCCUSDT, FTTUSDT, LUNAUSDT, SRMUSDT, MATICUSDT all present).

**Cross-quote panel** — `spotxq_daily.npz`: 367 `*TRY` and 333 `*USDC` pairs plus `USDTTRY`,
same grid. **Cross-venue panel** — `coinbase_daily.npz`: 91 Coinbase Exchange `*-USD` products,
free public `/products/{id}/candles`, UTC daily, same grid.

**Universe.** Top-50 each day by trailing 30-day mean quote volume, among names with an open
price today *and* tomorrow, excluding every stablecoin/fiat base. Mean realised size 41.6.

**Windows.** Design **2019-01-01 → 2023-01-01** (1,461 days, 4.00 y). Held out
**2023-01-01 → 2026-08-01** (1,308 days, 3.58 y), untouched until every sign was frozen.
Pre-2019 is excluded because Binance had fewer than 25 live USDT pairs and a cross-section is
not defined. *Honest disclosure:* the design window 2019–2022 is **virgin calendar time for the
programme** (no prior crypto work reaches before 2022-01); the held-out window overlaps
calendar time that round-2/round-3 used **on perps**, which is a third pass over that calendar
even though it is a first pass over this data and these features.

**Execution.** Signal formed from data through the close of day *d−1*; book entered at the
**open of day d** and marked to the **open of day d+1**; cost `fee × Σ|Δw|` charged the day the
weights move. Sign oriented on the **design window using zero-cost P&L** and then frozen — and,
because cost is sign-invariant, **subtracted after the flip** (an earlier version of the harness
subtracted it before, which made shocked cost *improve* net Sharpe; the bug and its fix are in
`xspot_sweep.py::run`). Sharpe is annualised over **every** day in the window, flat days included.

**Costs.** Headline **10 bp/side** — Binance spot taker is 0.1% at the base tier, and a book
this size is at the base tier. Shock **20 bp/side**. This is materially heavier than the 5.5 bp
the perp rounds charged, and it is the correct charge: these formulas trade *spot*, where there
is no maker rebate to lean on and the short leg needs margin or a perp overlay anyway.

---

## 3. THE NOISE BAR

Sign-flip block bootstrap (10-day blocks, 2,000 replicates), re-scoring **the maximum over all
34 formulas in every replicate**, so the correlation between formulas survives into the null.

| statistic | value |
|---|---|
| E[max &#124;Sharpe&#124;] over the 34 | **1.148** |
| p95 of max &#124;Sharpe&#124; | **1.574** |
| p99 | 1.796 |
| SD of one formula's design Sharpe (1 SE, 4.00 y) | 0.500 |
| analytic `sqrt(2 ln 34)` = 2.657 SE | 1.328 |
| analytic sign-agnostic `sqrt(2 ln 68)` = 2.905 SE | **1.452** ← headline |
| programme-cumulative `sqrt(2 ln 897)` = 3.678 SE | 1.838 |

**Best design net Sharpe in the search: 1.43.** It sits below the analytic sign-agnostic bar
(1.452), below the bootstrap p95 (1.574), and far below the programme-cumulative bar (1.838).
It clears only E[max] — i.e. it is the winner a 34-formula search of pure noise is *expected*
to produce.

---

## 4. ALL 34 FORMULAS, NOTHING DROPPED

`Dgr/Dnet` design gross/net Sharpe, `Hgr/Hnet` held-out, `Ht` held-out t, `BEd/BEh` break-even
bp/side per window, `turn` mean daily Σ|Δw|, `LAG1` the shared-price placebo (§5).

| formula | fam | Dgr | Dnet | Hgr | Hnet | Ht | BEd | BEh | turn | LAG1 D | LAG1 H |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `D5_XS_CLOSELOC` | D | +2.08 | **+1.43** | +1.08 | +0.03 | +0.07 | +32.2 | +10.3 | 0.56 | +1.64 | −0.12 |
| `G2_NL_AGE_TILT` | G | +1.18 | **+1.12** | +0.62 | +0.56 | +1.06 | +194.9 | +101.8 | 0.06 | +1.46 | +0.53 |
| `A6_XS_REV5` | A | +1.62 | **+1.06** | +0.31 | −0.60 | −1.13 | +29.1 | +3.4 | 0.59 | +1.02 | −0.32 |
| `G3_NL_VOLDECAY` | G | +1.14 | **+1.03** | +0.00 | −0.12 | −0.22 | +102.5 | +0.4 | 0.11 | +0.87 | −0.03 |
| `A7_XS_NEAR90HIGH` | A | +1.25 | **+0.99** | +1.37 | +1.06 | +2.00 | +48.2 | +43.5 | 0.22 | +1.46 | +1.12 |
| `F2_TS_STABVOL` | F | +1.16 | **+0.94** | +0.79 | +0.43 | +0.81 | +53.4 | +21.9 | 0.41 | +0.31 | +0.58 |
| `G1_NL_D1_FADE` | G | +0.98 | **+0.92** | −0.66 | −0.73 | −1.38 | +167.0 | −96.9 | 0.11 | +1.22 | −0.59 |
| `C3_TS_BTC_ALT_MR` | C | +0.99 | **+0.65** | −0.15 | −0.65 | −1.23 | +28.7 | −3.0 | 0.21 | +0.78 | −0.96 |
| `D6_XS_ATTN_TREND` | D | +0.79 | **+0.62** | +1.26 | +1.03 | +1.95 | +45.4 | +55.4 | 0.13 | +0.61 | +0.99 |
| `A5_XS_ACCEL` | A | +1.07 | **+0.59** | +0.04 | −0.72 | −1.36 | +22.1 | +0.5 | 0.49 | +0.29 | −0.71 |
| `B7_XS_TAKER_TREND` | B | +0.84 | **+0.57** | +0.52 | +0.09 | +0.17 | +31.2 | +12.1 | 0.16 | +0.63 | +0.12 |
| `A4_XS_IDIOMOM28` | A | +0.72 | **+0.44** | +0.72 | +0.35 | +0.66 | +25.3 | +19.4 | 0.26 | +0.74 | +0.23 |
| `B6_XS_NETTAKER_$` | B | +1.03 | **+0.43** | +0.68 | −0.22 | −0.42 | +17.2 | +7.5 | 0.39 | +0.45 | +0.21 |
| `D3_XS_UPVOL_ASYM` | D | +0.80 | **+0.37** | +0.41 | −0.18 | −0.34 | +18.5 | +7.0 | 0.35 | +0.32 | −0.37 |
| `D4_XS_AMIHUD` | D | +0.27 | **+0.15** | +1.55 | +1.39 | +2.64 | +22.0 | +96.3 | 0.08 | +0.17 | +1.42 |
| `E2_TS_TRYPREM_AGG` | E | +1.15 | **+0.03** | −0.44 | −2.02 | −3.83 | +10.3 | −2.8 | 0.52 | −0.63 | −1.14 |
| `D2_XS_RANGECOMP` | D | +0.28 | **−0.03** | +0.51 | +0.11 | +0.21 | +9.1 | +12.7 | 0.24 | +0.21 | +0.33 |
| `C4_XS_BAB` | C | +0.04 | **−0.09** | +0.96 | +0.79 | +1.49 | +2.9 | +56.4 | 0.12 | +0.13 | −1.01 |
| `F1_TS_PEGDEV` | F | +0.06 | **−0.09** | +1.12 | +1.00 | +1.90 | +3.9 | +96.7 | 0.25 | −0.09 | +0.81 |
| `C1_TS_VOLDOM` | C | +0.90 | **−0.09** | +0.50 | −0.83 | −1.58 | +9.1 | +3.8 | 0.55 | −0.24 | −1.74 |
| `D1_XS_VOLSURGE` | D | +0.30 | **−0.10** | +0.16 | −0.36 | −0.69 | +7.5 | +3.0 | 0.32 | −0.28 | −0.73 |
| `B1_XS_TBQ_IMB` | B | +0.76 | **−0.13** | +0.87 | −0.46 | −0.87 | +8.5 | +6.5 | 0.55 | +0.20 | −0.46 |
| `B3_XS_TICKET_Z` | B | +0.72 | **−0.19** | −0.69 | −2.06 | −3.89 | +7.9 | −5.0 | 0.64 | −0.20 | −1.81 |
| `B2_XS_TBQ_CHG` | B | +0.53 | **−0.28** | +0.17 | −1.00 | −1.88 | +6.5 | +1.5 | 0.53 | −0.71 | −0.74 |
| `B4_XS_TRADECT_SURGE` | B | +0.03 | **−0.34** | +1.27 | +0.72 | +1.36 | +0.9 | +23.1 | 0.27 | −0.14 | +0.66 |
| `A2_XS_REV_VOLADJ` | A | +1.22 | **−0.41** | +0.36 | −2.00 | −3.80 | +7.5 | +1.5 | 1.34 | −1.43 | −1.99 |
| `B5_XS_ABSORB` | B | +0.59 | **−0.52** | +0.11 | −1.40 | −2.65 | +5.3 | +0.7 | 0.70 | +0.37 | −1.36 |
| `C2_TS_ALTBREADTH` | C | +0.01 | **−0.59** | +0.53 | −0.23 | −0.43 | +0.2 | +7.0 | 0.33 | −0.59 | −0.43 |
| `H2_XS_CBVOLSHARE` | H | +0.27 | **−0.91** | −0.20 | −2.64 | −4.99 | +2.3 | −0.8 | 0.69 | −0.48 | −3.07 |
| `E1_XS_TRYPREM` | E | +0.19 | **−1.09** | −1.35 | −4.39 | −8.31 | +1.5 | −4.5 | 0.62 | −0.75 | −3.51 |
| `A3_XS_REV_UNSUP` | A | +0.33 | **−1.11** | −0.46 | −2.51 | −4.74 | +2.3 | −2.2 | 1.32 | −1.21 | −2.20 |
| `A1_XS_REV1` (control) | A | +0.31 | **−1.11** | −0.33 | −2.36 | −4.47 | +2.2 | −1.6 | 1.32 | −1.30 | −2.15 |
| `E3_XS_USDCGAP` | E | +0.39 | **−1.29** | +0.21 | −2.13 | −4.04 | +2.3 | +0.9 | 1.07 | −1.59 | −2.79 |
| `H1_XS_CBPREM` | H | +0.14 | **−1.44** | +0.71 | −1.96 | −3.70 | +0.9 | +2.7 | 0.91 | −1.50 | −2.79 |

Family key — **A** price structure (7): 1d/5d reversal, vol-normalised reversal, volume-unsupported
reversal, BTC-beta-residual 28d momentum, 7d-vs-28d acceleration, closeness to the 90d high.
**B** spot taker-flow (7): 3d/5d-vs-20d/20d taker-buy imbalance, log-ticket-size z, trade-count
surge net of dollar-volume surge, flow-minus-return absorption, 5d net taker dollars over ADV.
**C** dominance rotation (4): BTC share of universe dollar volume, alt breadth, 10d BTC-minus-alt
spread, bet-against-BTC-beta. **D** volume/vol (6): 3d-vs-60d volume surge, 10d-vs-60d range
compression, up-minus-down-day volume, Amihud illiquidity, close location in range, 10d-vs-90d
attention trend. **E** cross-quote (3): lira premium XS and aggregate, USDC-minus-USDT gap.
**F** stablecoin (2): peg premium z, stablecoin-pair volume surge. **G** spot listing (3): day-1
fade over days 2–7, age<60d tilt, post-listing volume decay. **H** cross-venue (2): Coinbase/Binance
price z, Coinbase volume-share change.

---

## 5. THE SHARED-PRICE PLACEBO (round-3 failure mode 3)

Because entry is the open of day *d* and the last signal input is the close of day *d−1* — one
second apart on a 24/7 venue — every book was re-run with the signal lagged **one extra day**.
The two columns are in the table. Read them this way:

* The **reversal family collapses further**, not less, under the placebo (`A1` −1.11 → −1.30
  design). That is the honest reading: the reversal effect is not a bid-ask-bounce artefact —
  it is simply *too small to pay 10 bp*, in both windows.
* `D5_XS_CLOSELOC`, the search maximum, **survives the placebo on design** (+1.43 → +1.64) and
  still dies out of sample (+0.03 → −0.12). It is not measurement error; it is overfit.
* `F2_TS_STABVOL` drops +0.94 → +0.31 under the placebo, i.e. most of its design number *was*
  next-day immediacy. Another reason it is not a candidate.

---

## 6. THE ONE THING WORTH RECORDING: A COST WALL, NOT AN EDGE

Break-even cost, in bp/side, for the whole search, by family, in **both** windows:

| formula group | typical turnover | BE design | BE held-out | verdict |
|---|---|---|---|---|
| 1-day reversal family (`A1`,`A2`,`A3`) | 1.32–1.34 | +2.2 … +7.5 | −2.2 … +1.5 | real gross effect, **1–3 bp wide**, uneconomic |
| cross-quote / cross-venue dispersion (`E1`,`E3`,`H1`,`H2`) | 0.62–1.07 | +0.9 … +2.3 | −4.5 … +2.7 | arbitrage already taken; residual is inside the fee |
| taker-flow (`B1`–`B6`) | 0.27–0.70 | +0.9 … +17.2 | +0.7 … +23.1 | no consistent sign |
| slow / low-turnover (`G2`,`D4`,`D6`,`A7`,`A4`,`B7`) | 0.06–0.26 | +22 … +195 | +12 … +102 | cost is *not* the binding constraint — the **signal** is absent |

**26 of the 34 formulas keep the same gross sign across both windows.** That is not a survivor
list — with design-fitted signs and correlated formulas it is barely distinguishable from
chance — but it is the reason the cost story, not a signal story, is the honest headline: the
panel has faint persistent structure and the fee eats all of it in the fast half, while the slow
half has break-evens of 20–200 bp and simply no Sharpe.

### 6.1 The zero-parameter low-turnover composite — examined and NOT promoted

One object deserves to be named so nobody rediscovers it and gets excited. Take the
**design-only** rule "every formula whose design turnover is ≤ 0.30/day", scale each to unit
design vol, equal-weight, signs already frozen. Thirteen formulas, mean pairwise correlation
0.077, **zero fitted parameters**:

| threshold | N | design SR | held-out SR | held-out t | LAG1 design | LAG1 held-out |
|---|---|---|---|---|---|---|
| turn ≤ 0.15 | 6 | +1.20 | +1.22 | +2.30 | +1.70 | +0.64 |
| turn ≤ 0.20 | 7 | +1.19 | +1.16 | +2.19 | +1.64 | +0.63 |
| turn ≤ 0.25 | 10 | +1.43 | +1.08 | +2.05 | +1.98 | +0.60 |
| **turn ≤ 0.30** | **13** | **+1.19** | **+1.37** | **+2.60** | +1.76 | +0.85 |
| turn ≤ 0.35 | 15 | +1.00 | +1.30 | +2.45 | +1.57 | +0.64 |
| turn ≤ 0.40 | 17 | +1.09 | +1.09 | +2.07 | +1.55 | +0.56 |
| turn ≤ 0.50 | 19 | +1.32 | +1.00 | +1.89 | +1.57 | +0.53 |
| turn ≤ 0.70 | 28 | +0.96 | **−1.44** | −2.73 | +1.06 | −1.30 |
| all 34 | 34 | +0.17 | **−2.59** | −4.89 | +0.18 | −2.47 |

It is stable across thresholds up to 0.50, and leave-one-out held-out Sharpe ranges +1.08 to
+1.63, so no single member carries it. **It is still not promotable, for four reasons:**

1. **Its design number is exactly the null.** Signs were fitted on design, so a pure-noise
   formula has E[design SR] = `E|N(0, 0.500)|` = 0.399. Thirteen such formulas at ρ = 0.077
   compose to **E[design SR] = 1.04** under a *pure* null. Observed: 1.19. There is nothing
   there to explain.
2. **The shared-price placebo takes 40% of it**: held-out +1.37 → +0.85 with one extra day of
   delay, and +0.5–0.65 at every other threshold. A slow, low-turnover book should be almost
   indifferent to a one-day delay. This one is not.
3. **Its market exposure is unstable**: beta to the equal-weight top-50 crypto basket is
   **+0.89 in design and −1.73 held out** (corr +0.11 → −0.26). Whatever it is, it is not a
   stable dollar-neutral alpha.
4. **The tail is not controlled**: worst design day is **−15.1 σ** (a single illiquid-pair gap),
   maximum drawdown 2.03 annual-vol-units in design. The owner's standing requirement is high
   reliability with a controlled tail; this fails it before the statistics are even argued.

Recommendation: **not even a forward-log leg.** Recorded here so it is a dead-ledger entry, not
a rediscovery.

---

## 7. DIVERSIFICATION VS THE ALIVE BASKET

Moot — nothing survived. For the record, had anything survived it would have diversified
structurally rather than statistically: the alive legs (T3 overnight reversal, ETF-sibling RV,
dual-class RV, T7 ex-open, T12 CEF discount) are all US-equity, all on a NYSE session calendar;
these books are 24/7 UTC crypto spot, dollar-neutral, with zero instrument overlap. The only
shared risk factor would be a global risk-on/off shock, and §6.1 shows the crypto side does not
even hold a stable sign against its own market. `XS_GLSR_Z` (perp funding, decaying,
logging-only) is the only crypto incumbent and it trades **perps on positioning data** — no
overlap with any spot price/flow/listing feature here.

---

## 8. WHAT THIS BUYS THE PROGRAMME

1. **A reusable, survivorship-bias-free spot asset.** 677 USDT pairs × 3,307 days with trade
   counts and taker-buy volume, plus 700 cross-quote pairs and 91 Coinbase products, all free,
   all cached (`research/data/xspot_cache/`, 21 MB + 13 MB + 0.8 MB). Nine years of crypto history
   — six of them calendar-virgin for this programme. Any future crypto question can be asked
   against it in seconds.
2. **The cost wall replicated on a second asset class.** The free-data convexity wall was
   established on equities and perps. Crypto spot now says the same thing with a sharper number:
   the fastest, strongest-gross effects break even at **1–3 bp/side** against a **10 bp** fee.
   Buying data will not fix this one — the effect is *measured*, it is just smaller than the fee.
3. **Two families closed for good.** Cross-quote (lira premium, USDC-vs-USDT gap) and cross-venue
   (Coinbase-vs-Binance) dispersion are **arbitraged flat at daily resolution**: break-evens of
   0.9–2.7 bp, and the held-out numbers are the most strongly *negative* in the search
   (`E1` t = −8.31, `H2` t = −4.99). Whatever is left of these dislocations lives inside the day
   and inside the fee. Do not spend another round on them without paid tick data.
4. **A harness bug worth remembering.** Freezing a sign on design and charging cost *before* the
   flip makes a shocked cost assumption *raise* net Sharpe. It produced a fake "design 2.86 /
   held-out 2.72, t = 5.16" winner for about ten minutes. Cost is sign-invariant; subtract it
   after the flip. Any future sweep that reuses this pattern should assert
   `net_shock ≤ net ≤ gross` as a self-test.

---

## 9. HONEST DISCLOSURES

* **N = 34.** Every formula built is in §4; none was dropped, silently retried, or re-parameterised
  after seeing a number. The only additions made after the first design-window run were four
  formulas (`A6`, `A7`, `B7`, `D6`) and the two families whose data was still downloading (`E`, `H`);
  all six were specified before any of them was scored, and all 34 are pooled into one null.
* **The composite threshold sweep in §6.1 is nine more looks at the held-out window.** It is
  reported in full and it is the reason §6.1 ends in a rejection rather than a proposal.
* **Held-out calendar reuse.** 2023-01 → 2026-08 has been used by round-2 and round-3 on perps.
  This is a first pass over spot data and these features, but a third pass over that calendar.
* **The panel's early years are thin.** 2019 has ~25–40 live USDT pairs; the top-50 universe
  averages 41.6 names over the design window. Cross-sectional statistics from 2019–2020 are
  noisier than the day count suggests.
* **Short leg.** Spot books are quoted as if the short leg were free. On Binance that requires
  margin borrow or a perp overlay for the alt legs. This makes every net number in §4
  **optimistic**, which only strengthens the negative verdict.
