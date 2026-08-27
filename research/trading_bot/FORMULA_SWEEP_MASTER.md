# FORMULA SWEEP — MASTER SYNTHESIS (ROUND 2)

**367 formulas, 6 themes, one pooled multiple-testing correction.**
Written 2026-08-20 as the cross-theme judge over the six round-2 wide sweeps. Round 1's master
(380 formulas) is archived verbatim at `FORMULA_SWEEP_MASTER_R1.md` and is **not** superseded on
facts — its one promoted leg (L5 `XS_GLSR_Z`) still stands. This document judges the new search.

Per-theme reports:
`SWEEP_overnight_equity.{md,json}` · `SWEEP_intraday_rv.{md,json}` ·
`SWEEP_crypto_perp_microstructure_R2.{md,json}` · `SWEEP_xll_leadlag_v2.md` ·
`SWEEP_futures_term_structure` round 2 · `SWEEP_calendar_session_batch2.{md,json}` +
`SWEEP_calendar_session_POOLED_NULL.json`.

---

## 0. THE ONE-PARAGRAPH ANSWER

Of 367 formulas, **one** clears the pooled noise bar on design, stays net-positive on a genuinely
virgin held-out window after realistic costs, survives a cost shock, and is **not** already a
BASKET1 leg: **`X2_FLOWSTREAK`** — a cross-sectional quintile book on the fraction of the last 24
hours in which Binance USD-M taker flow was net *buying* (order-flow one-sidedness, magnitude
discarded), top-50 perps, 24h hold. Design 4.61 (pooled bar 3.08 in the same units); virgin
2025-01→2026-08 net **+2.31** at 5.5 bp/side, **+0.54** at 15 bp/side, breakeven **17.9 bp/side**,
correlation to the equal-weight perp basket −0.01. **Four of the six themes are pure noise** at the
pooled bar. The overnight-equity theme is not noise but produces nothing new — all 27 of its
bar-clearers restate the single feature that is already leg L1. Recommendation: **one new leg**,
`X2_FLOWSTREAK`, under its own pre-registration freeze, **unsized until perp taker slippage is
measured**.

---

## 1. THE POOLED NOISE BAR

### 1.1 The per-theme bars are all correct and all too low

Every theme built its own joint-null max statistic — shuffle, stationary block bootstrap, circular
rotation, sign-flip bootstrap — always re-scoring the whole family per replicate so that
within-theme correlation survives. Those bars are right *within* a theme and wrong *across* the
programme: the search that actually happened was six such searches with a winner picked by looking
at all six.

**(a) Analytic, in Sharpe-standard-error units.** N = 367 → `sqrt(2 ln 367)` = **3.437 SE**.
Four of the six themes searched sign-agnostically (a formula and its negation are one hypothesis
tested twice), so the defensible two-sided count is 2N = 734 → `sqrt(2 ln 734)` = **3.633 SE**.

**(b) Empirical, correlation-aware.** Fit a Gumbel to each theme's *reported* null-max distribution
from its (mean, p95), studentise by that theme's own single-formula null SD, Monte-Carlo the max
over the six blocks, 400k draws:

| theme | N | E[max] (SE units) | p95 (SE units) |
|---|---|---|---|
| Overnight equity (max-t, empirical shuffle) | 51 | 1.99 | 2.95 |
| Intraday RV (block bootstrap, SD 0.50) | 98 | 2.62 | 4.02 |
| Crypto perp R2 (sign-flip bootstrap, SD 0.894) | 51 | 2.57 | 3.09 |
| Lead-lag v2 block A (time-shift, SD 0.50) | 70 | 2.12 | 2.98 |
| Futures TS R2 (circular shift, SD 0.289) | 49 | 2.46 | 3.49 |
| Calendar batch 2 (studentised rotation) | 48 | 2.70 | 3.53 |
| **POOLED max over all six** | **367** | **3.21** | **4.27** (p50 3.09, p90 3.92, p99 5.11) |

The empirical pooled expected-max is **3.21 SE**; the analytic is **3.44 SE**. They bracket each
other for the usual reason — within-theme correlation deflates each block, six independent bites
at the apple inflate the pooled max. **I use the conservative 3.44 SE as the headline pooled bar**
(identical to round 1's 3.44 at N=380 — the bar is essentially flat in N over this range, which is
itself the point: doubling a search barely moves the bar, so the bar is not the reason things fail).

### 1.2 Every theme's best, converted to pooled units

Design statistic ÷ that theme's own single-formula Sharpe SE, against the 3.44 bar:

| theme | best formula | design stat | SE of one config | **design in SE units** | vs 3.44 |
|---|---|---|---|---|---|
| Overnight equity | A08_p10_resid_day | SR 2.673 | 0.414 | **6.46** | ✅ 1.9× |
| Overnight equity | A09_p10_over_vol | SR 2.635 | 0.414 | **6.36** | ✅ |
| Overnight equity | A01_T3 (baseline) | SR 2.284 | 0.414 | **5.52** | ✅ |
| Overnight equity | A36_hivolregime | SR 2.95 | 0.752 (445 nights) | 3.92 | ✅ marginal |
| Crypto perp R2 | X2_FLOWSTREAK | SR 4.61 | 0.894 | **5.16** | ✅ 1.5× |
| Crypto perp R2 | X2_RETAIL_VS_TAKER | SR 3.91 | 0.894 | 4.37 | ✅ |
| Crypto perp R2 | X2_WICKASYM | SR 3.69 | 0.894 | 4.13 | ✅ |
| Crypto perp R2 | X2_TOD_FLOW_EU | SR 3.24 | 0.894 | 3.62 | ⚠️ clears 3.44, misses 3.63 |
| Crypto perp R2 | X2_IDIOVOL | SR 2.77 | 0.894 | 3.10 | ❌ |
| Lead-lag v2 | D1_clonegap_k1_h1 | gross 5.06 | 0.50 | **10.1** | ✅ (artefact — §4) |
| Futures TS R2 | L3_FOURSLEEVE_VOLTARGET | SR 0.59 | 0.289 | 2.04 | ❌ |
| Futures TS R2 | *I2_FX_XS_CARRY_D* | *SR 4.93* | 0.289 | *17.1* | **DISQUALIFIED — §5** |
| Calendar batch 2 | XE_MONTHSTART_CONT / best-of-100 | \|z\| 3.26 / 3.40 | (studentised) | 3.40 | ❌ |
| Intraday RV | D1_gap_rev_mega | net −0.27 | 0.50 | −0.54 | ❌ |

Three themes put **nothing at all** above the pooled bar. One puts a 10-SE monster above it that is a
quote-staleness artefact costing −274 net. One puts many above it that are all the same feature and
that feature is already in the basket. One puts a genuine candidate above it.

### 1.3 The honest cumulative trial count

367 is this round. Overnight (51) and intraday RV (98) are the *same* sweeps judged in round 1; the
other four themes are structurally new families run *on top of* round 1's crypto (56), lead-lag (74),
futures (49) and calendar (52). **Cumulative distinct formulas across both rounds: 598**
(`sqrt(2 ln 598)` = 3.58 SE, 3.77 sign-agnostic). Nothing in §3 changes at the cumulative bar —
FLOWSTREAK is 5.16 SE and A08 is 6.46 SE — but every future draw from these families inherits the
598, and the per-theme cumulative counts are what the individual reports already used
(crypto 107, lead-lag 144, futures 98, calendar 100).

---

## 2. FULL DESIGN DISTRIBUTIONS (all 367, nothing dropped)

| theme | min | p10 | p25 | median | p75 | p90 | max | # net-positive |
|---|---|---|---|---|---|---|---|---|
| Overnight equity (net SR, 51) | −2.53 | −0.68 | −0.10 | +1.65 | +2.08 | +2.42 | **+3.65** | 35 |
| Intraday RV (net SR @1 bp, 98) | −314.9 | −216.0 | −93.0 | −28.2 | −10.1 | −2.0 | **−0.27** | **0** |
| Intraday RV (gross SR, 98) | −3.11 | −0.38 | +0.43 | +1.70 | +3.29 | +5.62 | +6.86 | (gross only) |
| Lead-lag v2 block A (gross SR, 49) | −4.74 | −0.61 | +0.04 | +0.35 | +0.96 | +1.73 | **+5.06** | 0 net |
| Lead-lag v2 block B (gross SR, 21) | −1.11 | −0.61 | −0.08 | +0.61 | +0.96 | +1.29 | +1.52 | 0 above bar |
| Futures TS R2 (net SR, 49) | −0.73 | — | −0.01 | +0.07 | +0.30 | — | **+0.59** (legit) | 0 above E[max] |
| Calendar batch 2 (\|z\|, 48) | — | — | — | 0.85 | 1.36 | 1.93 | **3.26** | 4 with \|z\|>1.96 (2.4 expected) |
| Crypto perp R2 | full 51 + 39 table with design/h1/h2/net/@15bp/breakeven/turnover in `_R2.md` | | | | | | **4.61** | 6 bar-clearers |

Two rows deserve to be stared at.

**Intraday RV.** 50 of 98 beat the *gross* bar and the gross effect replicates out of sample — and
**0 of 98** are net-positive at 1 bp/side. Break-even is 1.15 bp per unit of turnover; the best
formula in 98 captures **0.863 bp**, the median captures 0.028 bp. That is a real, measured,
replicating market effect that is too small to take by 25%. It is the cleanest negative in the repo
because it fails on an arithmetic identity, not on a small Sharpe.

**Futures TS R2.** The best *legitimate* result (+0.59) came in **below** what a null search of this
size is expected to produce (+0.71). 0 of 48 clear their own within-theme E[max] once the artefact is
removed. There is no ambiguity to adjudicate.

---

## 3. THE SHORTLIST — clears the pooled bar AND is held-out net-positive

Four gates, in order, no exceptions:
**G0** mechanism not disproven · **G1** design above the pooled 3.44-SE bar ·
**G2** held-out net-positive after the theme's realistic cost model ·
**G3** survives the cost/capacity shock where the cost assumption is defensible.

| # | formula | theme | G0 | G1 design | G2 held out | G3 shock | verdict |
|---|---|---|---|---|---|---|---|
| 1 | **X2_FLOWSTREAK** | crypto perp R2 | ✅ | 5.16 SE ✅ | virgin 577d: gross +3.34, **net +2.31** @5.5 bp ✅ | **+0.54 @15 bp**, breakeven 17.9 bp ⚠️ | **PROMOTE — one new leg, unsized until slippage measured** |
| 2 | X2_TOD_FLOW_EU | crypto perp R2 | ✅ | 3.62 SE ⚠️ (clears 3.44, misses the 3.63 sign-agnostic bar) | virgin: net **+1.85** @5.5 bp ✅; burned window +1.06; **positive on all three windows** | +0.21 @15 bp, breakeven 16.2 bp ⚠️ | **LOG UNSIZED** — same hypothesis as #1 |
| 3 | A08_p10_resid_day | overnight equity | ✅ | 6.46 SE ✅ | net **+4.99 bp/night**, t +2.98, SR +1.40 ✅ | SR 0.86 at 2× half-spread ⚠️ | **ALREADY IN BASKET as L1** — no action |
| 4 | A09_p10_over_vol | overnight equity | ✅ | 6.36 SE ✅ | net +2.91 bp/night, t +2.42, SR +1.14 ✅ | weaker than #3 | same signal as L1 — **NO** |

Everything else fails a gate outright, and the failures are more informative than the survivors:

- **X2_WICKASYM** (4.13 SE, design 3.69) and **X2_UPWICK** (3.48): cleared the pooled design bar,
  **died on the virgin window** (net −0.39 and −0.01). Round 2's clearest overfits. Two formulas
  above a 367-formula pooled bar that are worth exactly zero out of sample — the bar is necessary,
  not sufficient.
- **X2_RETAIL_VS_TAKER** (4.37 SE): passes G1, and its only available held-out window is the one
  round 1 already burned (net +1.30 @5.5 bp, **−0.74 @15 bp**, breakeven 11.5 bp). The Binance
  metrics feed ends 2024-12, so a virgin test is impossible with this cache. It is also built from
  the same two L/S-ratio fields as round 1's `XS_SMART` / `XS_GLSR_Z` — i.e. it is **the already
  promoted leg L5 wearing a new name**, not an independent finding. **No new leg.**
- **X2_IDIOVOL** (3.10 SE, virgin net **+1.87**, still **+1.70 at 15 bp**, breakeven 110 bp) is the
  best-looking *held-out* number in the whole 367 and I am **not** promoting it: on a top-50 universe
  it is long-majors/short-alts, correlation **+0.47** to the equal-weight perp basket, over a window
  of rising BTC dominance. A directional regime bet in a cross-sectional costume. It also misses the
  pooled design bar. Rejecting a +1.87 net OOS Sharpe on mechanism is the whole point of G0.
- **D1_clonegap_k1_h1** (lead-lag, **10.1 SE**, the largest statistic in this round, design 5.06 →
  held out **+4.79 gross**): net **−274**. Breakeven **0.027 bp/side** against a 1.0 bp/side cost on
  the cheapest legs in existence (SPY/IVV/VOO, all >$2B/day). It is the slower wrapper's 5-minute
  print catching up *inside* the spread. A post-hoc rescue pass cut turnover from 126×/day to 5×/day
  and gross fell in almost exactly the same proportion — breakeven never leaves the 0.015–0.10 bp
  band at any hold, any subset. Flat wall.
- **A36_hivolregime** (3.92 SE, design SR 2.95 — the overnight theme's *design* winner among
  conditioners): held out **+0.93, t 1.23**. The conditioner that separated best on design failed
  hardest out of sample. Every other conditioner tested (turn-of-month t 1.05, Friday/weekend 0.85,
  up-vs-down market 0.70) was noise on design too.
- **L3_FOURSLEEVE_VOLTARGET** (futures, 2.04 SE, bootstrap p = 0.741): 74% of null searches of this
  size produce a better best. Held-out +0.24 reported as *evidence for the noise verdict*, not as a
  result it earned.
- **SESS_OPEXDAY_INTRADAY** (calendar, pooled \|z\| 2.93 vs its own 100-formula p95 of 3.53) is the
  most carefully defended near-miss in the round — every placebo comes out the other sign, the
  always-on control is −0.36/−0.72, the shift probe is clean, it kept its sign out of sample. And a
  post-freeze block decomposition shows it is **dormant**: +11.5/+15.0/+17.4/+13.2 bp per session
  1993–2012, flat +1.1 bp 2013–2016, +19.1 bp 2017–2021, flat **+1.5 bp 2022–2026**. The entire
  held-out Sharpe is one five-year block; the last 4.5 years contribute +0.86% *total*. Not promoted.
- **XE_MONTHSTART_CONT** (calendar design winner, z 3.26): the **ungated** version of the same
  cross-sectional sort earns +0.205 held out on its own. The calendar gate buys ~0.21 Sharpe, inside
  the sampling error of a 9.6-year window. It is cross-asset momentum in a calendar mask.

---

## 4. THE CANDIDATE, IN DETAIL

### X2_FLOWSTREAK — cross-sectional taker-flow one-sidedness (Binance USD-M perps)

- **Signal.** For each symbol, count how many of the last 24 hourly bars had net taker *buying*
  (`sign(2·takerBuyQuote − quoteVol)`), magnitude discarded. Cross-sectional quintile book: long the
  top 20%, short the bottom 20%. Point-in-time **top-50** perps by trailing-7d quote volume.
  24h hold in overlapping tranches; entry and exit at the **open of the bar after the signal bar**;
  P&L includes funding accrual at the settlement bar.
- **Numbers.** Design 2023-01-01→2024-04-01 (456d): gross 4.61, **net +3.11** at 5.5 bp/side
  (4.5 bp published Binance VIP0 taker + 1.0 bp declared half-spread), turnover 1.38×/day.
  Virgin holdout 2025-01-01→2026-08-01 (**577 days never touched by this programme**): gross +3.34,
  **net +2.31** @5.5 bp, **+0.54** @15 bp, breakeven **17.9 bp/side**, 2025 +2.53 / 2026 +2.01,
  correlation to the equal-weight perp basket **−0.01**.
- **Why the theme, not just the formula.** Design→virgin rank correlation **+0.39** across the 39
  klines-panel formulas; the 6 design-bar clearers average **+1.89** virgin gross versus **+0.92**
  for the other 33; the virgin window was scored on all 39 with design signs frozen to disk first, so
  that rank correlation is a statistic and not a survivor's anecdote. Lookahead audit: all 90
  formulas re-derived with every input after bar 12000 destroyed → **0 violations**.
- **The four reasons I am sizing it at zero until slippage is measured.**
  1. **It failed the middle window.** +3.11 design → **−0.67** on 2024-04→2025-01 → +2.31 virgin.
     One of the three windows says no. `X2_TOD_FLOW_EU` is the only formula positive on all three,
     and it is the weaker one — which is the usual trade between the formula that wins the design
     bar and the formula that survives everything.
  2. **This is one hypothesis, not six.** FLOWSTREAK, TOD_FLOW_EU and round 1's `XS_TAKER24` are the
     same feature. Round 1's version scored design 3.15 and then **+0.32 on the top-50 h1 window and
     −1.67 at 15 bp** — the top-50 cut is exactly what killed round 1's taker-flow variant. Round 2
     designs on top-50 from bar one and gets a better answer, which is progress; it is not
     independent confirmation.
  3. **Perp slippage has still never been measured in this repo.** The 1.0 bp half-spread is
     *declared*. `orphanflush_cache/bookdepth` exists and was again not used. The edge is real at
     5.5 bp and gone before ~20 bp, and nobody here knows which side the fills land on. Breakeven is
     reported per formula precisely so this can be re-charged the day it is measured.
  4. **One virgin window, one regime**, during which funding intervals moved from 8h to 4h/1h on many
     symbols.
- **Flagged for the next round, deliberately not promoted:** `X2_RESID_MOM` (beta-adjusted 7d
  momentum) and `X2_FUNDPATH_REV` were positive on **all three** windows (+2.06/+0.76/+2.72 and
  +1.84/+1.32/+1.85 net) and survive 15 bp — but they never cleared the design bar (2.46 and 2.20 vs
  2.76), so under the pre-committed protocol they are observations, not findings. They are also 0.80
  correlated with each other.

---

## 5. THE MOST IMPORTANT RESULT IN THIS ROUND IS A METHODOLOGY TRAP

`I2_FX_XS_CARRY_D` (futures TS round 2) scored **design Sharpe +4.93** (bootstrap p = 0.000, 17.1 SE
— it would clear any pooled bar this programme could construct) and then **went up out of sample, to
+8.28** (t +3.85, 3.6% vol, −2% max DD). It would have passed G1, G2 and G3 and walked straight into
the basket.

**It is false.** Yahoo's `=X` FX spot bar stamps *earlier* than the CME futures settle, so
`log(F_t/S_t)` is not a forward premium — it is hours of futures move that spot has not printed yet,
which lands mechanically in tomorrow's spot bar. Proof: `corr(basis_t, futures_ret_t)` = +0.27..+0.38
and `corr(basis_t, spot_ret_{t+1})` = +0.28..+0.34 — the same number. Kill test: lag the signal one
extra day and net SR goes **+5.10 → −0.56 → −0.91** (2d) and stays negative to 63d; gross goes
+6.03 → +0.41. The corrected 21-day-mean version of the whole FX family collapses to −0.02 / −0.00 /
−0.01.

**The general lesson, which is worth more than any formula in this round:** a broken data feed is a
property of the *data*, not luck, so it **reproduces on every window**. Out-of-sample persistence
does not validate a signal whose mechanism is disproven. Any sweep that mixes two data sources with
different stamp times needs the extra-lag kill test as a standing gate — G0 before G1.

---

## 6. HOW MANY THEMES WERE PURE NOISE

**Four of six.**

| theme | N | verdict at the pooled bar |
|---|---|---|
| Intraday equity/ETF RV | 98 | **NOISE as a tradeable theme.** 0 of 98 net-positive at any rung. Real gross effect (best gross +6.86), 0.863 bp available per unit turnover against 1.15 bp needed. Only the maker side is untested and this data cannot backtest it. |
| Cross-asset / cross-venue lead-lag v2 | 70 | **NOISE.** Pure transmission (X's past return → Y's future return, no own-return term) fails at every frequency and in every pairing: SPY-push −0.00, sector-push +0.28, foreign +0.14, rates +0.15, credit −0.50, oil −0.44, gold +0.09, curve +0.08, composite −0.51, Binance-flow-only +0.56. The cross-venue W family tops out at +0.81 against a 1.17 bar with each sign-flip its exact mirror — the signature of zero. The one bar-clearer is a quote-staleness artefact. **With round 1 that is 144 lead-lag formulas failing the same way.** |
| Futures term structure / carry / seasonality R2 | 49 | **NOISE.** 1 of 49 above the within-theme E[max] and that one is a disproven data artefact; excluding it, **0 of 48**, with the best legitimate result *below* the null search's expected best. With round 1, **98 formulas across two independent rounds**. |
| Calendar / session / structural flow batch 2 | 48 | **NOISE.** Pooled over 100 calendar formulas, the single luckiest one is a family-wise p = 0.065 event. Median \|z\| 0.85; 4 of 48 above \|z\| 1.96 where 2.4 are expected. |
| Overnight equity, T3 family | 51 | **NOT noise — and produces nothing new.** 27 of 51 clear the within-theme joint null and 5 clear it with the opposite sign, but all 27 restate **one** feature (the last ten minutes reverse overnight) and that feature is already leg L1. No formulation beats T3 out of sample: A08's held-out improvement over the baseline is **+0.31 bp/night, t 0.43**. |
| Crypto-perp microstructure R2 | 51 | **NOT noise, and produces one candidate.** Design→virgin rank correlation +0.39, bar-clearers +1.89 virgin gross vs +0.92 for the rest. The metrics half (OI, L/S ratios, liquidation cascades) is **dead at top-50** — 4 of 51 cleared the design bar and their mean held-out net is −0.21 vs −0.27 for the rest, i.e. clearing the bar bought nothing. The candle-shape cluster died. Funding died again. What survived is taker aggressor-flow imbalance. |

---

## 7. DIVERSIFICATION VS BASKET1

BASKET1 (frozen 2026-08-20, `BASKET_FORWARD_PREREGISTRATION.md`, sha-verified by the runner):
**L1** T3 end-of-day cross-sectional pressure reversal (US equity, overnight, close→next open),
**L2** ETF-sibling identical-claim RV (US equity intraday, 15:45→close), **L5** `XS_GLSR_Z`
(Binance perp cross-sectional positioning fade, promoted by round 1), plus a T13 vol-targeting sleeve.

| candidate | relation to BASKET1 | add? |
|---|---|---|
| **X2_FLOWSTREAK** | **NEW vs L1/L2** — different asset class, venue, data source, holding calendar, 24h horizon, corr −0.01 to perp beta. **PARTIALLY CORRELATED vs L5**: same venue, same universe (top-50 perps), same 24h cross-sectional quintile construction, same rebalance clock. Different *field* (taker aggressor volume vs account long/short ratio) but the two books will trade overlapping names in overlapping directions. Their realised correlation has **not** been measured and must be, before either is sized. | **YES — new leg L6, own freeze, size 0 until (a) perp taker slippage is measured from `bookdepth` and (b) corr(L5, L6) is measured** |
| X2_TOD_FLOW_EU | Same hypothesis as L6 (both taker-flow), further restricted to 07–15 UTC. Diversifying vs L1/L2, redundant vs L6. The only formula positive on all three windows. | **LOG UNSIZED** under the same freeze, as the pre-declared robustness sibling — exactly the L5/`XS_SMART` arrangement round 1 used |
| X2_RETAIL_VS_TAKER | **This is L5's family.** Same two Binance L/S-ratio fields. No virgin window exists for it (metrics feed ends 2024-12). | **NO** |
| X2_IDIOVOL | Not microstructure — corr +0.47 to the perp basket. It would add crypto *beta*, which is the one thing a market-neutral basket must not import. | **NO** |
| A08 / A09 / A01 (overnight family) | **CORRELATED — this IS L1.** A08's held-out edge over the frozen L1 spec is +0.31 bp/night, t 0.43. Re-specifying L1 would break the freeze to buy a statistically absent gain. | **NO — do not touch L1's spec** |
| D1_clonegap (lead-lag) | Overlaps L2's instrument set (same-claim ETF wrappers) and is the same economics at a shorter horizon; net −274. | **NO** |
| SESS_OPEXDAY_INTRADAY | Directional SPY, 12 trades/yr, dormant since 2022. | **NO** |

**One new leg.** It slots as **L6** and raises `declared_trials_now` on the combined basket gate.
Killed and retired legs keep counting forever, and so do these 367 formulas — plus round 1's 380,
minus the 149 counted twice: **598 declared trials** for anything drawn from this programme.

---

## 8. FINDINGS THAT SURVIVE EVEN THOUGH THE FORMULAS DIDN'T

1. **G0 before G1: the extra-lag kill test is now mandatory.** Any signal built from two data sources
   with different stamp times must be re-scored with one extra day of lag. A stale-price artefact
   survives every out-of-sample window ever constructed (§5).
2. **The last ten minutes reverse; the rest of the session continues.** Fading the open→close move
   overnight is significantly *negative* (t −4.83, 6 of 6 years) while fading the 15:49→15:59 move is
   positive. That asymmetry is why residualising on the session move (A08) was the only improvement
   in 50 tries, and why the naive `z(p10)+z(day)` composite destroys the signal (SR −0.07).
3. **The MOC-legal rail is dead in all eight formulations** (best net SR 0.37, t 0.89). The free,
   spread-less rung cannot reach any overnight signal in this cache.
4. **bp captured per unit of turnover is the number that decides an RV theme**, and it can be
   computed before scoring a single strategy. Best of 98 = 0.863 bp against 1.15 bp needed; median
   0.028. Same-claim ETF pairs (SPY/IVV/VOO) have p95 displacement ~1.5 bp against a 4.6 bp round
   trip with ac(1) 0.05–0.14 — non-synchronous printing, not a dislocation. The pairs with wide
   persistent spreads and ac(1) 0.96 are the ones that are *not* the same claim, which is why the
   autocorrelation buys nothing. **Run the census first; it predicts the sweep's verdict in an hour.**
5. **Clearing a design bar carries almost no information about held-out rank in a correlated family.**
   Crypto R2 metrics half: bar-clearers averaged −0.21 held-out net vs −0.27 for the rest.
   Overnight: the best conditioner on design (A36) is the worst out of sample.
   Design→holdout rank correlation was +0.24 (metrics) and +0.39 (klines).
6. **Effective N is much smaller than N.** The overnight theme's empirical bar (1.08) sits *below*
   its analytic bar (1.16) because its 51 formulas have effective N ≈ 15. The crypto shortlist's mean
   absolute pairwise correlation is 0.35 and collapses to ~4 clusters. "82% of formulas positive on
   the virgin window" is 4–8 confirmations, not 39.
7. **Judge on t, not Sharpe, whenever configs trade different subsamples.** Configs trading a tercile
   of nights have SE up to 0.98 — they inflate the null's max-Sharpe p95 and produce eye-catching
   design numbers (A40's 3.65 on 278 nights; XT_ALT_SESSION_ROT's raw −5.06 whose null mean is
   −4.23). Studentise, or the family gets ranked by subsample size and turnover.
8. **Conditioners and regime gates fit noise.** Every gate tested this round *destroyed* the sleeve
   it gated (futures dollar-trend −0.14, self-trend −0.17) or added less than sampling error
   (calendar month-start gate +0.21, inside a 9.6y error bar). The one gate that separated on design
   (SPY vol regime) is the one that failed hardest out of sample.
9. **Carry is now dead six independent ways** — crypto funding (twice), futures term structure, ETF
   maturity ladder, VIX curve, rates curve, FX basis. Stop testing carry.
10. **Automated lookahead audits keep earning their cost**, and so does disclosing bugs rather than
    quietly fixing them: this round surfaced a mid-run panel rebuild by a peer agent (fixed by
    pinning a frozen panel snapshot and re-running design against it), a `np.bincount`-over-global-day-indices
    turnover understatement of 3.5×, and an always-on control silently scoring years before half the
    panel existed. All three are in the artifacts.

---

## 9. WHAT I AM NOT CLAIMING

- The overnight held-out window was already spent by T3 for its own 8 configs, so `A01` is a
  replication there, not a virgin test. The other 43 configs are fresh on it.
- `X2_FLOWSTREAK`'s virgin window is genuinely virgin and is also **one window, one regime**. There
  is no walk-forward anywhere in this round.
- The crypto cost model contains a **declared, never-measured** 1.0 bp half-spread; the ETF/commodity
  cost ladder in the futures theme is **assumed spread-scale, not measured**. Both report per-formula
  breakeven cost so every row can be re-charged.
- Every equity universe here comes from a current listing — **survivorship-biased by construction**.
  Dollar-neutral cross-sectional demeaning absorbs most of it, not all.
- Deflated Sharpe at honest trial counts kills the overnight family outright (0.83 generous input /
  0.0000 López de Prado input at 51 trials, against the repo's frozen 0.95 gate — and 51 is now the
  wrong number; 598 is). I am not appealing that verdict; I am reporting that the widening priced in
  the searching, which is what it is for.
- 367 is what was *scored this round*. 598 is the programme's distinct total. It only goes up.

**Bottom line: 367 formulas in, one leg out — a crypto-perp taker-flow fade with a virgin +2.31 net
Sharpe, a 17.9 bp breakeven, one failed intermediate window, and an unmeasured spread underneath it.
Four of six themes were noise, one restated a leg we already own, and the single largest statistic in
the round (10.1 SE) was a stale quote. That is the honest yield.**
