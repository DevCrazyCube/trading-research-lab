# INVENT D0821 — Term structure of volatility as a **directional** signal for equity

**Verdict: NOISE. 0 of 43. Honest zero.**

Date 2026-08-21 · design `20110103..20191231` (2263 d, 8.98 y) · holdout `20200101..20260820`
(1667 d, 6.62 y) · all data free and cached, no network call inside the sweep.

---

## 1. The one-line result

| | |
|---|---|
| formulas tested, signs fixed a priori | **43** |
| analytic bar, `sqrt(2 ln 43)` | t = 2.74 → **Sharpe 0.92** |
| circular-shift bootstrap **E[max Sharpe]** (B=2000) | **0.95** (p95 1.23, p99 1.40) |
| **best design Sharpe** | **0.88** (`H21_A4_INVERT_HOLD`) |
| its bootstrap p-value | **0.63** |
| formulas above the bootstrap E[max] | **0** |
| formulas above bootstrap p95 | **0** |
| buy-and-hold SPY over the same window | **0.94** — *above all 43* |
| best design alpha-t against SPY | **+1.11** against a 2.74 bar |

The best formula in the theme does not beat holding the index, and does not beat a
search over shuffled returns. Nothing is promoted.

---

## 2. What was actually tested

Every formula carries one of four named mechanisms and an **a-priori sign**, and is scored
exactly as written. The search is **not** sign-agnostic: a good Sharpe on the flipped sign is
recorded as a failure. (All ten top formulas have a negative flipped sign — that is
arithmetic, not evidence.)

* **M1 panic impulse** — forced hedgers buy near-dated vol on a risk-limit trigger, flattening
  or inverting the front; that demand is non-informational and unwinds → long equity.
* **M2 calm supply** — a steep/steepening curve means the front is being sold and dealers
  accumulate long gamma, damping realised moves → long equity.
* **M3 repricing lag** — realised above implied means options are underpriced against what is
  happening; the catch-up comes with de-risking → short equity.
* **M4 convexity bid** — VVIX rich to VIX means somebody is paying up specifically for crash
  convexity → same forced-hedger logic, one derivative up.

| group | n | content |
|---|---|---|
| **A** implied curve shape/dynamics | 10 | 1d and 5d slope changes on all three measured segments; slope levels; outright front inversion, binary and depth-scaled; 9d/30d/93d butterfly curvature; slope acceleration; near-vs-far twist |
| **B** realised vs implied dynamics | 6 | rv21−VIX and rv10−VIX9D gaps and their 1d changes; PIT rolling-regression residual of the VIX move on the realised-vol move (pure implied *overshoot*); realised-vol term slope rv5/rv21; implied front curve minus realised front curve |
| **C** vol-of-vol | 4 | log(VVIX/VIX) level and 5d change; 1d VVIX shock; realised vol-of-VIX minus VVIX |
| **D** session decomposition | 3 | the flattening impulse and the inversion state held overnight-only and intraday-only |
| **E** curve-driven rotation | 4 | belly slope driving QQQ-vs-SPY and IWM-vs-SPY; VXN rich-to-VIX level and 5d change driving QQQ-vs-SPY |
| **H** holding horizon | 8 | the four most promising batch-1 signals as overlapping **5-day** and **21-day** books |
| **G** event triggers | 5 | long SPY for 5/10/21 sessions after a bottom-5% flattening, a fresh inversion, a fresh **un**-inversion, a bottom-5% belly collapse |
| **V** risk-off rotation | 3 | front slope, belly slope and VVIX/VIX driving **TLT vs SPY** |

Batch 2 (H/G/V, 16 formulas) was added *after* batch 1 was scored, on the one structural axis
batch 1 does not sweep — the **holding horizon**, since a forced-hedger unwind need not be a
one-day object. Both batches are in the reported N and in the same bootstrap null. That is the
whole point of reporting N.

---

## 3. Design table, top 8 of 43

| formula | design SR | boot p | α-t vs SPY | lag1 SR | flipped | holdout SR |
|---|---|---|---|---|---|---|
| `H21_A4_INVERT_HOLD` | +0.88 | 0.63 | +1.11 | +0.89 | −0.91 | +0.27 |
| `G3_FRESH_INVERSION_21D` | +0.83 | 0.77 | −0.78 | +0.79 | −0.86 | +0.79 |
| `A4_NEAR_INVERT_DEPTH` | +0.71 | 0.97 | +0.87 | +0.40 | −0.78 | +0.12 |
| `H5_A4_INVERT_HOLD` | +0.68 | 0.98 | +0.63 | +0.65 | −0.72 | +0.09 |
| `G5_BELLY_SHOCK_10D` | +0.68 | 0.98 | +0.34 | +0.53 | −0.72 | +0.14 |
| `A3_NEAR_INVERT_BINARY` | +0.61 | 1.00 | −0.39 | +0.51 | −0.69 | +0.24 |
| `G2_FRESH_INVERSION_5D` | +0.51 | 1.00 | −0.37 | +0.58 | −0.58 | +0.90 |
| `G4_UNINVERSION_10D` | +0.36 | 1.00 | −2.08 | +0.27 | −0.40 | **+1.42** |

Median design Sharpe across all 43: **−0.04**.

---

## 4. The holdout is a diagnostic, and it is the classic trap

The design pass was written to disk before any holdout number was computed. The holdout table
exists to *check the conclusion*, not to find a survivor — and it shows exactly why that
discipline matters.

The **two best held-out numbers in the study are two of the weakest design results**:
`G4_UNINVERSION_10D` (design 0.36, holdout **1.42**, holdout t +3.65) and
`G2_FRESH_INVERSION_5D` (design 0.51, holdout 0.90). Both have design bootstrap p-values of
1.00, and G4 has a design alpha-t of **−2.08** against SPY. Promoting either is selecting on
the holdout. A t of +3.65 as the best of 43 draws in a window nobody used to pick it is what
the null *predicts will happen to somebody*.

Design→holdout rank correlation is +0.35 — and that is **beta, not skill**: 19 of 43 books are
long-biased, SPY returned Sharpe +0.94 in design and +0.82 in holdout, so ranking long-biased
books above short-biased ones in both windows manufactures ρ=0.35 with zero forecasting
content. Mean holdout Sharpe across all 43 is +0.06.

---

## 5. Does the effect exist at all? (mechanism-level, before any book)

Univariate OLS of **next-day SPY return** on each standardised curve variable — bp per sigma,
with t-stat. This asks whether there is an effect, independent of tradability.

| signal | design | holdout | full 16 y |
|---|---|---|---|
| 9d→30d slope | −3.46 bp, t −1.83 | −1.86, t −0.60 | −2.65, t −1.55 |
| 30d→93d slope | −3.68, t −1.95 | −4.05, t −1.30 | −3.85, t −2.25 |
| 1d front flattening | +3.73, t +1.97 | +0.96, t +0.31 | +2.55, t +1.49 |
| **log(VVIX/VIX)** | −3.81, t −2.01 | −4.89, t −1.57 | **−4.27, t −2.50** |
| rv21 − VIX | −2.25, t −1.18 | −1.49, t −0.48 | −1.78, t −1.04 |

The largest raw effect in the entire theme is `log(VVIX/VIX)` at −4.27 bp/σ, t = −2.50 over
sixteen years. Three separate things kill it:

1. **The sign is the opposite of the a-priori mechanism.** M4 says a rich convexity bid is a
   forced hedger paying up, and equity should bounce. The data says a rich convexity bid
   predicts equity *down* — continuation, not reversal. By this programme's own sign rule that
   is a failed prediction, not a finding.
2. **t = −2.50 is one of five variables looked at inside a 43-formula search.** It survives no
   correction.
3. **4 bp per sigma on a book that re-trades daily** is a gross Sharpe near 0.2 against a 1 bp
   per-side round trip. There is no executable object here even if the sign had been right.

Base rate for context: the 9d→30d front is inverted on **29.1%** of design days and 23.7% of
holdout days, so the M1 formulas are not starved of events — they are simply not predictive.

---

## 6. Why this is not a re-run of anything already dead

* **vs. `NEWTERR_volatility_etp_term_structure` (2026-08-20, 39 formulas, NOISE)** — every one
  of those traded SVXY/VIXY/VIXM/UVXY: the tradable leg *was* the vol curve and the mechanism
  was roll carry. Here the curve is only the **signal**; every tradable leg is plain equity or
  duration, and nothing in the sweep is short vol.
* **vs. VRP harvesting (dead)** — no formula sells volatility. B1/B2/B3 use the
  realised-implied gap as a *directional equity predictor*, not as a premium to collect.
* **vs. round 3's gating meta-result (0/107, gating is harmful)** — **zero formulas were spent
  on conditioners**, as instructed. Nothing here multiplies an alive basket leg by a vol-curve
  condition; all 43 are standalone books whose only input is the curve.
* **vs. the dead VIX9D/VIX3M "gamma-sign proxy"** — that used a curve sign as a dealer-gamma
  proxy for *intraday momentum*. A3/D3 are close-to-close capitulation *reversal*: opposite
  sign, opposite mechanism. And they are dead too.

---

## 7. Harness self-test (all passed before any result was read)

| check | result |
|---|---|
| overnight × intraday reconstructs close-to-close | max abs err **2.2e-16** |
| an oracle on tomorrow's sign is visible to the harness | Sharpe **+14.81** |
| the same oracle delayed one day collapses (no leakage) | Sharpe **−0.05** |
| cost is positive and scales with turnover | buy-hold 0.001%/yr → daily-flip **5.19%/yr** |
| gross exposure bounded | max **1.00** |
| no formula live before its inputs exist | first-live date logged per formula |
| index staleness (days repeating the prior print) | VIX 0.5%, VIX9D 1.0%, VIX3M 1.5%, VVIX 0.7% |

**Lag semantics.** Headline is lag0: the CBOE indices publish continuously 09:30–16:15 ET, so a
15:55 read is a real input to a 16:00 MOC fill. lag1 and lag2 (one and two extra full days) are
reported for every formula as a decay test. **Costs**: 1.0 bp per side SPY/QQQ, 1.5 IWM, 2.0
TLT, +0.5 on any MOO fill, charged on entry *and* exit; the session legs round-trip every day
and are charged on |W| daily rather than |ΔW|; borrow accrues on every negative weight. Every
holdout row also carries a 2× cost column — it changes no verdict, because nothing survived at 1×.

---

## 8. What would change the answer

1. **The real VX futures settlement curve.** Everything here rests on the CBOE *constant-maturity
   indices*, which are synthetic interpolations that smooth away precisely the roll-date and
   expiry-cycle structure a genuine curve signal would trade. VX settlements are on no free
   keyless endpoint reachable from this host. This is the same wall the 2026-08-20 ETP sweep
   hit, and it is a **data** wall, not a mechanism wall.
2. **Intraday term structure.** The curve is sampled once a day at the close. The forced-hedger
   impulse M1 describes is an intraday object that may be over before the close prints. Free
   data gives no intraday VIX9D.
3. **Nothing else.** Adding more daily formulas to this theme only raises the bar.

---

## 9. Dead-ledger additions

Feed to the next round. All tested on a frozen design window with a reserved holdout, all dead:

**Vol term structure as an equity direction signal.** Front/belly/back slope levels and their
1d, 2d (acceleration) and 5d changes; outright front inversion, binary and depth-scaled;
9d/30d/93d butterfly curvature; near-vs-far twist; all of the above re-expressed as 5-day and
21-day overlapping books; event triggers on bottom-5% flattening, fresh inversion, fresh
un-inversion and bottom-5% belly collapse at 5/10/21-session horizons.

**Realised-vs-implied as a direction signal (not as a premium).** rv21−VIX, rv10−VIX9D, their
1d changes, the PIT rolling-regression residual of the VIX move on the realised-vol move
(implied overshoot), realised-vol term slope rv5/rv21, implied front curve minus realised front
curve.

**Vol-of-vol as a direction signal.** log(VVIX/VIX) level and 5d change, 1d VVIX shock,
realised vol-of-VIX minus VVIX. *(Note the one honest whiff in the theme: log(VVIX/VIX) has a
full-sample t of −2.50 — with the sign inverted against its mechanism and an effect size of
4 bp/σ that no daily-turnover book can pay for. It is logged so it is not rediscovered as a
near-miss.)*

**Curve-driven rotation.** Belly slope → QQQ-vs-SPY and IWM-vs-SPY; VXN rich-to-VIX level and
5d change → QQQ-vs-SPY (the worst result in the study, holdout Sharpe −1.20, alpha-t −3.39);
front slope, belly slope and VVIX/VIX → TLT-vs-SPY.

**Session placement of the curve signal.** The flattening impulse and the inversion state held
overnight-only and intraday-only. Both are gross-marginal and net-negative: the session legs
must pay a full round trip every day.

---

## 10. Files

| | |
|---|---|
| sweep | `scripts/trading_bot/invent_d0821_volterm_dir.py` |
| extra-symbol fetcher | `scripts/trading_bot/volts_fetch.py` |
| design | `research/trading_bot/INVENT_D0821_volterm_dir_DESIGN.json` |
| holdout | `research/trading_bot/INVENT_D0821_volterm_dir_HOLDOUT.json` |
| self-test | `research/trading_bot/INVENT_D0821_volterm_dir_SELFTEST.json` |
| mechanism diagnostic | `research/trading_bot/INVENT_D0821_volterm_dir_DIAG.json` |
| master | `research/trading_bot/INVENT_D0821_volterm.{md,json}` |

Data: `research/data/volterm_cache/raw` (^VIX ^VIX9D ^VIX3M ^VIX6M ^VVIX SPY TLT) and
`research/data/volts_cache/raw` (QQQ IWM ^VXN ^VXD ^SKEW). Yahoo chart API v8, keyless, free.
`^RVX` returns 404 on that surface and is not used.
