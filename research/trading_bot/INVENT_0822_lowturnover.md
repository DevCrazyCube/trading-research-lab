# INVENT 0822 · THEME: LOW-TURNOVER (weekly / monthly) signals, where cost is not binding

**Date:** 2026-08-22 · **Scope:** research only, no orders, no money, cached/free data only.
**Verdict: HONEST ZERO on the alpha question — and one strongly generalisable structural finding
that is worth more than the zero.**

Artifacts
- `scripts/trading_bot/invent0822_slow_xs.py` — cross-sectional US equity, monthly/quarterly books
- `scripts/trading_bot/invent0822_slow_wide.py` — the one declared universe extension ($2M+ ADV)
- `scripts/trading_bot/invent0822_slow_sector.py` — 11-sector rotation, monthly
- `scripts/trading_bot/invent0822_slow_ts.py` — bond/equity allocation drift + duration-tethered RV
- `INVENT_0822_slowturn_FREEZE.md` — picks frozen **before** the held-out window was run
- `INVENT_0822_slowturn_{XS_DESIGN,XS_HOLDOUT,WIDE,SECTOR,TS}.json`, `data/inv0822_cache/NULL.json`

---

## 0. The one-paragraph answer

The theme's premise is **confirmed as mechanics and refuted as a source of edge.** At a 21- or
63-day hold the 5 bp half-spread really does stop mattering: measured turnover is
**0.004–0.027 of book per day**, break-even costs run **40–226 bp** against a ~5.5 bp charge, and
cost eats **6–30% of gross** instead of all of it. So slow signals do escape the execution-cost
wall — and there is nothing on the other side of it. Across **81 design cells / 48 distinct
formulas** the best *genuine* design gross t is **1.82**, against a pooled bar of **2.80**
(empirical slow-book null σ_t = 0.946 × √(2 ln 81) = 2.80; the naive √(2 ln N) is 2.96). Not one
cell clears. The single highest raw design t in the whole round, **5.12**, belongs to
`RV_SHORTGOV_SCHO_VGSH` — and it is **pure bid-ask bounce**: ρ1(Δs) = −0.428, and its net Sharpe is
**−2.86 design / −6.30 held out.** That is not a footnote; it is the round's actual result, below.

---

## 1. THE FINDING: in the tethered-RV family, gross Sharpe *is* a readout of the bounce

Nineteen structurally tethered spreads were built on 24 years of daily bond/credit ETF total
returns (2002-07-30 … 2026-08-20) and traded on a **weekly** clock — deliberately answering the
open question left by `DEEPMINE_etf_structural_rv` ("this family does not need better execution,
it needs a different business"). Each spread carries a real economic tether: same-maturity-bucket
Treasury siblings, a duration-neutral 2s10s30s butterfly, a TIPS-vs-nominal breakeven anchored by
an inflation target, two MBS funds, two muni funds, two HY funds, two EM-sovereign funds.

Across those 19 pairs, the **rank correlation between ρ1(Δs) and design GROSS Sharpe is −0.837**
(Pearson −0.76). The more a spread's daily change looks like measurement error, the *better* its
gross Sharpe looks. On **net** Sharpe the correlation collapses to −0.30, because the cost bill
tracks the same axis (ρ1 vs gross-minus-net: −0.55).

| pair | ρ1(Δs) | Hurst | ADF t | half-life | design gross SR | design **net** SR | held-out net SR |
|---|---:|---:|---:|---:|---:|---:|---:|
| `RV_SHORTGOV_SCHO_VGSH` | **−0.428** | 0.29 | −9.22 | 2.4 d | **+2.17** | **−2.86** | **−6.30** |
| `RV_TIPS_TIP_SCHP` | **−0.439** | 0.32 | −9.43 | 2.6 d | **+2.14** | −0.61 | −1.04 |
| `RV_MBS_MBB_VMBS` | **−0.444** | 0.33 | −6.19 | 6.3 d | +1.36 | +0.28 | −0.01 |
| `RV_MUNI_MUB_TFI` | **−0.362** | 0.38 | −7.99 | 6.1 d | +1.25 | +0.98 | +0.12 |
| `RV_EMSOV_EMB_PCY` | **−0.375** | 0.49 | −6.03 | 9.9 d | +0.63 | +0.55 | −0.32 |
| `RV_STRIPS_ZROZ_EDV` | **−0.391** | 0.40 | −4.46 | 13.8 d | +0.59 | +0.35 | −0.07 |
| `RV_LONGGOV_VGLT_TLT` | **−0.456** | 0.35 | −4.65 | 10.7 d | +0.53 | +0.15 | −0.45 |
| `RV_AGG_BND` | −0.334 · **pass** | 0.37 | −7.94 | 6.9 d | +0.52 | +0.12 | −0.49 |
| `RV_IGBROAD_LQD_USIG` | −0.177 · **pass** | 0.42 | −4.08 | 35.7 d | +0.49 | +0.34 | +0.12 |
| `RV_HY_HYG_JNK` | −0.187 · **pass** | 0.47 | −5.29 | 19.6 d | +0.23 | +0.15 | −0.77 |
| `RV_PREF_PFF_PGX` | −0.220 · **pass** | 0.49 | −3.22 | 71.9 d | +0.04 | −0.07 | −0.12 |
| `RV_BREAKEVEN_TIP_IEF` | +0.083 | 0.58 | −2.12 | 288 d | −0.18 | −0.32 | −0.27 |
| `RV_BFLY_2s10s30s` | −0.048 | 0.57 | −1.30 | 1044 d | −0.53 | −0.90 | −1.36 |
| `RV_BELLY_vs_SHORT` | −0.068 | 0.58 | −1.89 | 1488 d | −0.87 | −1.15 | −1.59 |

*(pass = clears all three of ρ1 > −0.35, Hurst < 0.5, ADF < −2.86. Full 19-row table in the JSON.)*

**Read the table top to bottom.** Every candidate that clears the design gross bar fails the ρ1
gate; every candidate that passes the ρ1 gate is far below the bar. There is no cell in either
corner. This is the same picture `OU_MEAN_REVERSION` found for the five equity ETF-sibling pairs
at 15:45, now reproduced independently on **19 different pairs, a different asset class, a weekly
rather than intraday clock, and a 24-year sample.** The lesson generalises, and it generalises
with a sign: **within this family, a high gross Sharpe is evidence AGAINST the spread, not for
it.** The gate should be applied *before* looking at the Sharpe, not as a tiebreak after.

The curve trades are the mirror image and just as informative. The 2s10s30s butterfly, the
belly-vs-wing spreads, and the TIPS breakeven all have ρ1(Δs) ≈ 0 — they are *not* bounce, they
are honest slow objects — and their half-lives are **288 to 1,678 days** with ADF failing to
reject a unit root. Over a 24-year sample, a spread with a 4-year half-life is a directional macro
bet wearing an RV costume. Both ends of the ρ1 axis are untradable, for opposite reasons.

---

## 2. Cross-sectional equity, monthly/quarterly: 21 formulas × 2 horizons, honest zero

Universe and engine inherited from `newterr_xseq_sweep` (US equity panel 2016-01-04 … 2026-08-14,
$20M+ ADV, px ≥ $5, ~1,735 eligible names/day, open-to-open returns, Corwin-Schultz-shaped
half-spread anchored to a 5 bp universe mean + 0.5 bp fee). Books are **overlapping**: the signal
formed at *t* enters at the next open and is held 21 or 63 days as one of h staggered sub-books,
so no rebalance-date luck is being measured. Signs are declared from the mechanism, never fitted.
**Zero regime conditioners were spent** (lesson 1, obeyed by omission).

Design window **2016-01-04 … 2021-12-31**. Best gross t = **1.69** (`COSKEW_NEG` h63). Nothing
close to the bar.

| cell | design gross SR / t | held-out gross SR / t | held-out net SR | turnover/day | break-even |
|---|---|---|---|---|---|
| `COSKEW_NEG` h63 (pick 1) | +0.69 / 1.69 | +0.31 / 0.67 | +0.25 | 0.016 | 61 bp |
| `DIV_CUT_DEPTH` h21 (pick 2) | +0.51 / 1.24 | **+0.52 / 1.10** | **+0.37** | 0.016 | 39 bp |
| `ILLIQ_UNCERT` h63 (pick 4) | +0.43 / 1.04 | +0.21 / 0.44 | +0.16 | 0.014 | 56 bp |
| `SPREAD_LEVEL` h63 (pick 3) | +0.40 / 0.98 | +0.14 / 0.29 | +0.11 | 0.007 | 116 bp |
| best held-out cell (`DOWNBETA_GAP` h21) | +0.14 / 0.35 | +0.89 / 1.91 | +0.81 | 0.026 | 120 bp |

Newey-West t (lag = h) was computed for every cell, because an h-day overlapping book has h−1 days
of built-in autocorrelation and the naive t is mechanically suspect. It changes nothing here
(`COSKEW_NEG` h63: naive 1.69 → NW 2.00; still sub-bar).

**Context worth recording:** the published slow tilts are *negative* in this window and universe.
`BETA_LOW` (BAB) design gross SR −0.53/−0.55, held out −0.36/−0.38. `IVOL_LOW` −0.22/−0.25 design,
−0.13/−0.15 held out. `DIVY_TTM` (dividend yield as the only available value proxy) −0.23/−0.25
design, −0.12/−0.14 held out. `DIVY_x_LOWVOL` ("quality income") −0.47 to −0.50 design. The engine
is not broken — it reproduces planted edges at SR 13.9 and flips their sign — the era simply did
not pay these, which is consistent with the standing "all published equity edges DEAD" ledger.

### 2b. The declared universe extension: the illiquidity premium, measured and rejected

The $20M+ ADV screen structurally excludes the population where an illiquidity premium could
exist, so one — and only one — extension was declared in advance and run on a **$2M+ ADV**
universe (6,609 columns, ~3,382 eligible names/day):

| formula | design gross SR (h21/h63) | held-out gross SR (h21/h63) |
|---|---|---|
| `ILLIQ_AMIHUD` | +0.01 / −0.08 | **−0.87 / −0.70** |
| `SPREAD_LEVEL` | +0.37 / +0.32 | −0.25 / −0.19 |
| `ILLIQ_UNCERT` | +0.26 / +0.29 | −0.51 / −0.42 |
| `ATTN_DECAY` | +0.07 / +0.10 | +0.40 / +0.33 |
| `DIV_CUT_DEPTH` | **+0.75 / +0.55** | +0.31 / +0.13 |
| `DIVY_TTM` | −0.31 / −0.25 | +0.10 / +0.08 |

The theme's headline economic claim — *"the illiquidity premium is the canonical cost-wall-escaping
signal, because it pays you to hold what is expensive to trade, so you must trade it rarely"* —
was the most attractive idea going in. It is **dead on measurement**: flat in design and clearly
negative out of sample in the wider universe, in both the Amihud and the spread-level
parameterisation. Do not re-propose it.

---

## 3. Sector rotation on a slow clock, and the rebalancing premium: both zero

**Sector rotation** (11 SPDRs, top-3 vs bottom-3, 21-day overlapping book, 2 bp/side) was declared
underpowered by construction and behaved like it: design gross t of −1.16, +0.26, −0.10, −0.18 for
sector dividend yield, low-vol, residual long-term reversal, and flow-decay. `SEC_RESID_LTREV` then
printed +1.04 held out (t 2.24) off a design of −0.04 — a coin, reported so it is on the record and
not rediscovered.

**Volatility harvesting / the rebalancing premium** (monthly-rebalanced vs drifting SPY/TLT,
inverse-vol SPY/TLT, SPY/TLT/GLD, and SPY/TLT/LQD/GLD, 2002–2026) is a real algebraic effect and an
economically honest one — it is not a forecast — but it is **far too small relative to the variance
of the difference series** to be an edge: best design Sharpe +0.43 (t 1.62), and **all four are
negative out of sample** (−0.09 to −0.30). Turnover 0.001–0.004/day, so cost is genuinely nil; the
signal simply is not there.

**Term premium** is reported only as a reference beta and it was a *loser* over this sample:
duration-matched long TLT / short SHY, design Sharpe −0.89, held out −1.21. Credit
(duration-matched HYG vs IEF) +0.26 design, +0.51 held out — a positive beta, not an alpha, and
already covered by the standing carry ledger.

---

## 4. Multiple-testing accounting

| quantity | value |
|---|---|
| distinct formulas | **48** (21 XS + 4 sector + 23 TS candidates; 2 static references excluded) |
| design cells (trials) | **81** (42 XS + 12 wide + 4 sector + 23 TS) |
| naive expected max t under null, √(2 ln 81) | **2.96** |
| **empirical** slow-book null: σ_t over 60 random 250-day-smoothed signals | **0.946** (h21 0.944, h63 0.948) |
| empirical null \|t\| p95 / max over 60 draws | 1.83 / 2.33 (h21); 1.75 / 2.62 (h63) |
| **pooled bar used** = 0.946 × 2.96 | **2.80** |
| best *genuine* design gross t observed | **1.82** (`DIV_CUT_DEPTH` h21, wide universe) = **0.65× bar** |
| best design gross t of any kind | 5.12 — `RV_SHORTGOV_SCHO_VGSH`, ρ1 = −0.428, **net −2.86** |

The empirical null σ_t of 0.946 is a useful by-product: it says the naive t is **well calibrated**
for a single slow overlapping book on this panel, so the sub-bar conclusion does not rest on a
variance assumption.

---

## 5. The one thing worth logging (not promoting): `DIV_CUT_DEPTH`

`DIV_CUT_DEPTH` = −max(0, 1 − TTM dividend ÷ prior-year TTM dividend), payers only. It is long the
non-cutters and short by the *depth* of the cut, a deliberately one-sided functional form (the
symmetric `DIV_GROWTH` sibling is much weaker: design 0.01/0.03). Mechanism: a dividend cut evicts
an income clientele that is a price-insensitive seller, and the eviction takes months.

It is **positive in 8 of 8 gross cells** — {narrow, $2M-wide} × {design, held out} × {h21, h63} —
gross Sharpe +0.13 to +0.75, and net positive in 7 of 8. Break-even 15–74 bp against a 5.5 bp
charge; cost is 24–34% of gross. **It is nevertheless not a signal.** Best t is 1.82 against a 2.80
bar, the eight cells are heavily overlapping so the 8-for-8 sign run is worth far less than 2⁻⁸,
and the held-out numbers decay in the wide universe (0.75 → 0.31 at h21). Filed as
**logging-only**, the same status as `XS_GLSR_Z`: recorded, forward-observable from a free
corporate-actions feed, promoted by nothing.

---

## 6. What this round rules out, so it is not re-mined

1. **Slow does not rescue a cross-sectional equity tilt.** The cost wall really is escapable at
   monthly horizon — measured, not assumed — and the ground behind it is empty. 42 + 12 cells,
   nothing above 0.65× the bar.
2. **The illiquidity / neglect premium is not harvestable here**, in either the $20M+ or the $2M+
   universe, in either the Amihud or the spread parameterisation. Negative out of sample.
3. **Duration-tethered RV on a weekly clock is not the "different business"** that
   `DEEPMINE_etf_structural_rv` was pointing at. 19 pairs, 24 years: gross Sharpe in this family
   is a −0.84-rank-correlated readout of bid-ask bounce.
4. **Curve-shape RV (butterfly, breakeven) is not RV at all** at these horizons — half-lives of
   288–1,678 days with ADF failing to reject. Anything traded on it is a macro direction bet.
5. **The rebalancing premium is real and too small**, and **the term premium was negative** over
   2002–2026 in duration-matched form.

**Recommended next move, and it is not another formula sweep.** Every dead end this round shares
one shape: the free data can price a *statistic* but not a *claim*. The two survivors the programme
already owns (T12 CEF discount, dual-class RV) both work because a third party publishes the
tether's true value — a NAV, a share-class ratio — and the panel here publishes nothing of the
kind. That is the same wall recorded in `free-data-convexity-wall`, reached from a new direction.
The productive question is which cheap feed publishes a *tether value* the programme does not yet
consume, not which new function of OHLCV+DIV has not been tried.
