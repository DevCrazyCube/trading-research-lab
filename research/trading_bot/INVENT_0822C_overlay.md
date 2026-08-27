# INVENT_0822C — PORTFOLIO-LEVEL OVERLAY across the sized basket legs

**81 overlays. 3 multi-leg panels. Zero survivors. The whole overlay family is noise —
and the overlay the basket is ALREADY frozen with is one of the losers.**

Date: 2026-08-22 (rotation 3). Theme: does any **zero-parameter or structurally-motivated**
overlay on the **combined** book beat plain equal-risk 1/N, without fitting weights?
Round 3 proved that *fitting* basket weights costs −0.48 Sharpe out of sample. This round asks
whether the un-fitted overlays — vol targeting, correlation timing, structural risk parity,
known-blackout switch-offs — do any better.

**Answer: no. Not one of 81.**

---

## 1. What was built

The previous ensemble work (R3) had only three legs (T3, T7D1, CEF) on a weekly calendar.
This round rebuilt a **six-leg daily panel** from the frozen specs so the overlays have a real
book to act on. Three legs were reconstructed from scratch:

| leg | source | n | mean net | standalone SR | t |
|---|---|---|---|---|---|
| T3 | cached `invent_r3/t3_daily.json` | 2606 d | +6.41 bp/night | 1.56 | 5.03 |
| T7D1 | cached `invent_r3/t7d1_daily.json` | 2320 d | +2.73 bp | 1.38 | 4.19 |
| CEF (T12 S2 H4) | cached `invent_r3/t12_all.json` | 240 wk | +13.74 bp/wk | 2.20 | 4.73 |
| **ETFRV** | **rebuilt** from `rv_cache` 5-min bars, frozen L2 spec | 927 d | +0.10 bp | 0.74 | 1.41 |
| **DUALCLASS** | **rebuilt** from `t28_dualclass_cache`, frozen L3 spec, daily MTM | 2321 d | +0.68 bp | 1.33 | 4.04 |
| **ORB** | **rebuilt** from `t17_cache` selection + 1-min paths, frozen L6 spec | 2643 d | +6.18 bp | 0.69 | 2.22 |

Builder: `/home/anont/meme/scripts/trading_bot/inv0822c_panel.py` →
`/home/anont/meme/research/data/inv0822c_cache/legs_daily.json`

### Panels

| panel | legs | calendar | n | span | design | held-out |
|---|---|---|---|---|---|---|
| `P1_LONG4` | T3, T7D1, ORB, DUALCLASS | daily | 2418 | 2016-12-29 … 2026-08-13 | → 2022-12-30 | 2023-01-03 → |
| `P2_FULL5` | + ETFRV | daily | 1349 | 2021-03-31 … 2026-08-13 | → 2024-03-29 | 2024-04-01 → |
| `P3_BASKET6W` | + CEF | weekly | 257 | 2021-08-27 … 2026-07-24 | → 2024-03-29 | 2024-04-01 → |

**BASE (the thing to beat)** = equal-risk: each leg divided by its **design-window** sd, then
1/N. Zero fitted parameters, no lookahead. Base Sharpes: design 2.59 / 3.19 / 3.07, held-out
**2.16 / 1.65 / 2.53**.

---

## 2. The bar

- **N = 81** overlay statistics (26 + 27 + 28). Analytic `sqrt(2 ln 81) = 2.965 σ`.
- The operative bar is the **size-matched placebo**, because ΔSharpe between two highly
  correlated books has no clean analytic SE. Null = **IID within-leg permutation** (2000 draws),
  which keeps each leg's marginal but destroys vol clustering, correlation timing and every
  calendar effect. Each draw rebuilds BASE *and all K overlays* and records
  `max_over_overlays ΔSharpe(held-out)`. This is size-matched by construction.
- Cross-sectional rotate-the-returns nulls were not used (broken — injects a directional leg).

| panel | K | placebo **mean** of max ΔSR | placebo **p95** of max ΔSR | **observed** max ΔSR | median overlay ΔSR |
|---|---|---|---|---|---|
| P1_LONG4 | 26 | +0.154 | **+0.330** | +0.160 | **−0.006** |
| P2_FULL5 | 27 | +0.181 | **+0.392** | +0.142 | **−0.033** |
| P3_BASKET6W | 28 | +0.268 | **+0.574** | +0.345 | **−0.018** |

**In every panel the observed maximum sits at or below the *mean* of the null-max
distribution, and the median overlay is negative.** That is the cleanest negative shape
available: there is no winner to argue about.

**Survivors: none. 0 of 81.**

---

## 3. Ranked results (held-out ΔSharpe vs BASE)

`dHoldGrs` = the same overlay rerun on the legs' **gross** series. `afterCost` = ΔSharpe after
charging the overlay its own **rebalancing cost** (legs that unwind every session — T3, T7D1,
ORB, ETFRV — can be re-sized for free; DUALCLASS and CEF must actually trade the weight delta,
charged at their measured one-way costs).

### P1_LONG4 (base held-out 2.16, placebo p95 +0.330)

| overlay | dDesign | dHold | dFull | dHoldGrs | afterCost |
|---|---|---|---|---|---|
| OV_MONTHEND_OFF | −0.104 | +0.160 | −0.005 | — | — |
| OV_VT20 | −0.142 | +0.087 | −0.092 | +0.066 | — |
| OV_VT120 | −0.124 | +0.086 | −0.084 | +0.098 | — |
| OV_VT_EWMA20 | −0.151 | +0.079 | −0.103 | +0.088 | — |
| OV_RP_EXPAND | −0.065 | +0.021 | −0.031 | +0.041 | +0.020 |
| OV_INVCORR120 | −0.001 | +0.009 | +0.003 | +0.008 | — |
| OV_DIVSCALE120 | −0.052 | +0.003 | −0.033 | −0.003 | — |
| OV_RP60 | −0.214 | −0.021 | −0.140 | +0.098 | −0.060 |
| OV_T13_SPYVOL | +0.028 | **−0.031** | −0.050 | −0.051 | — |
| OV_DROP_MOSTCORR120 | −0.442 | −0.130 | −0.326 | −0.287 | — |
| OV_EQDOLLAR | −0.715 | **−0.968** | −0.831 | — | — |

### P2_FULL5 (base held-out 1.65, placebo p95 +0.392)

| overlay | dDesign | dHold | dFull | dHoldGrs | afterCost |
|---|---|---|---|---|---|
| OV_MONTHEND_OFF | −0.080 | +0.142 | +0.024 | — | — |
| OV_RP60_INV | +0.190 | +0.093 | +0.098 | −1.289 | +0.035 |
| OV_ETFRV_EXDIST_OFF | +0.032 | +0.075 | +0.052 | — | — |
| OV_ALWAYSFULL | −0.164 | +0.043 | −0.045 | — | — |
| OV_DIVSCALE120 | +0.008 | +0.016 | +0.004 | −0.009 | — |
| OV_VT60 | −0.111 | −0.152 | −0.095 | −0.112 | — |
| OV_SQRTVOL60 | −0.181 | −0.164 | −0.151 | +0.785 | −0.209 |
| OV_T13_SPYVOL | −0.296 | **−0.215** | −0.313 | −0.279 | — |
| OV_RP120 | −0.302 | −0.374 | −0.297 | +1.464 | −0.424 |
| OV_EQDOLLAR | −1.515 | −0.391 | −1.017 | — | — |
| OV_RP60 | −0.408 | **−0.427** | −0.377 | +1.557 | −0.526 |

### P3_BASKET6W (base held-out 2.53, placebo p95 +0.574)

| overlay | dDesign | dHold | dFull | dHoldGrs | afterCost |
|---|---|---|---|---|---|
| OV_FIT_SHARPEWEIGHT_EXPAND *(declared fitted control)* | −0.123 | +0.345 | +0.091 | +2.010 | — |
| OV_ETFRV_EXDIST_OFF | +0.061 | +0.180 | +0.116 | — | — |
| OV_CEF_MONTHEND_OFF | +0.017 | +0.101 | +0.056 | — | — |
| OV_MONTHEND_OFF | −0.226 | +0.082 | −0.084 | — | — |
| OV_RP60 | −0.106 | +0.026 | −0.045 | +1.042 | **−0.004** |
| OV_VT60 | +0.004 | −0.043 | −0.025 | −0.063 | — |
| OV_T13_SPYVOL | −0.397 | **−0.189** | −0.308 | −0.244 | — |
| OV_TRIPLEWITCH_OFF | −0.076 | −0.292 | −0.178 | — | — |
| OV_DROP_MOSTCORR120 | −0.060 | −0.805 | −0.431 | −1.070 | — |
| OV_EQDOLLAR | −1.195 | −1.099 | −1.181 | — | — |

Full 81-row table: `research/trading_bot/INVENT_0822C_overlay.json`.

---

## 4. Why each overlay family fails — mechanism, not just a p-value

### 4a. Correlation timing has nothing to time

Weekly cross-leg correlation matrix over the six legs (2021-08 … 2026-07):

|  | T3 | T7D1 | ORB | DUALCLASS | ETFRV | CEF |
|---|---|---|---|---|---|---|
| **T3** | 1.00 | −0.04 | −0.05 | +0.06 | 0.00 | 0.00 |
| **T7D1** | | 1.00 | +0.06 | −0.13 | −0.13 | −0.06 |
| **ORB** | | | 1.00 | +0.14 | +0.07 | −0.04 |
| **DUALCLASS** | | | | 1.00 | +0.07 | +0.08 |
| **ETFRV** | | | | | 1.00 | +0.05 |
| **CEF** | | | | | | 1.00 |

Mean off-diagonal |ρ| = **0.067**. The book's trailing diversification ratio
(`sqrt(Σwᵢ²σᵢ² / wᵀCw)`; 1.0 = fully uncorrelated) has **mean 0.994, sd 0.049**, p5–p95 of
0.92–1.07 in every panel. The quantity a correlation overlay steers on **does not move**.
`OV_DIVSCALE120 = +0.003 / +0.016 / −0.025` and its inverse `= −0.006 / −0.019 / +0.022` —
**exactly antisymmetric**, i.e. pure scale noise carrying zero information. Same for the
drawdown pair (`OV_DD_DELEVER` −0.006/−0.013/−0.009 vs `OV_DD_LEVERUP` +0.006/+0.012/+0.009).

This is a structural statement about a market-neutral multi-leg book, not a failed search: an
already-uncorrelated book has no correlation to time.

### 4b. Vol targeting: the sign is not stable

The book's trailing-60 vol *does* vary (p95/p5 = 4.22× on P1). Vol targeting still fails,
and the sign flips across panels: `OV_VT60 = −0.025 / −0.152 / −0.043`, `OV_VT60_INV =
−0.067 / +0.070 / +0.026`. Whichever direction you pick, another panel disagrees. Design and
held-out disagree too (VT20 on P1: design −0.142, held-out +0.087).

### 4c. Risk parity overweights exactly the legs with the worst gross-to-net gap

The `dHoldGrs` column is the tell. On P2, `OV_RP60` is **+1.557 gross** and **−0.427 net** —
a 2.0-Sharpe inversion. Trailing-vol risk parity loads onto ETFRV and DUALCLASS because their
*gross* series are the lowest-vol; those are precisely the legs whose costs eat the most
(ETFRV pays ~1.0 bp against a ~1.2 bp gross edge). **A risk-parity overlay run on gross
returns is a cost-blind overlay.** Anyone reading only the gross number would size this the
wrong way round by two full Sharpe points.

Charging the overlay its own rebalancing cost then removes what little is left: the only
overlay positive on P3 after cost accounting is `OV_RP60` at **−0.004** — i.e. zero.

### 4d. Structural blackouts are calendar noise

`OV_MONTHEND_OFF` is the best zero-parameter overlay on two of three panels
(+0.160 / +0.142 / +0.082 held-out) — and it is **negative on design in all three**
(−0.104 / −0.080 / −0.226) and ≈0 or negative on the full window. It is a sign flip between
windows, which is what a null looks like. `OV_TRIPLEWITCH_OFF` and `OV_YEAREND_OFF` are
negative nearly everywhere.

### 4e. The fitted controls behave exactly as R3 predicted

`OV_FIT_SHARPEWEIGHT_EXPAND` posts the single largest held-out number in the round (+0.345 on
P3) while being **negative on design** (−0.123) and ≈0 on the other two panels
(−0.013, +0.013). Its gross reading is +2.010/+3.096 — the same cost-blind inversion as 4c.
It was pre-declared as a control and is not promoted.

---

## 5. What this round DID produce: four decisive negatives and two leg escalations

### N1 — the SPY vol overlay currently in the freeze COSTS Sharpe. **ESCALATE.**

`BASKET_FORWARD_FROZEN.json` carries `vol_overlay: T13-VOL-L60-T0.1-WMAX1.0` on SPY, applied
to the whole book. Applied to the combined **market-neutral** book it is negative essentially
everywhere:

| panel | ΔSharpe design | ΔSharpe held-out | ΔSharpe full |
|---|---|---|---|
| P1_LONG4 | +0.028 | **−0.031** | **−0.050** |
| P2_FULL5 | −0.296 | **−0.215** | **−0.313** |
| P3_BASKET6W | −0.397 | **−0.189** | **−0.308** |

Mechanism: T13 was validated as a risk-shaper for a **long SPY** book. The basket's legs are
market-neutral, so their vol is not driven by SPY vol; the overlay de-levers the book on
exactly the days SPY is volatile, which is uninformative about a dollar-neutral RV book, and
it only ever cuts (wmax = 1.0), so it is a one-sided drag. **Recommendation to the basket
owner: remove `vol_overlay` from the combined book, or keep it only on any directional leg.**
This is not a search result — it is a negative on an already-deployed rule, the same class of
finding as R3's P1.

### N2 — equal-RISK is load-bearing; equal-DOLLAR is a disaster

`OV_EQDOLLAR` (plain 1/N on raw leg returns, no vol scaling) is −0.968 / −0.391 / −1.099
held-out and −0.715 / −1.515 / −1.195 on design. The base's design-vol scaling is doing real
work and must stay.

### N3 — trailing-vol risk parity loses on a fresh panel and a fresh leg set

`OV_RP60 / OV_RP120 / OV_RP60_CAP40` = −0.43 / −0.37 / −0.43 held-out on P2. R3's
"the more the weights are allowed to learn, the worse they travel" now replicates on two extra
legs and a different window. **Fixed design-vol equal-risk remains the answer.**

### N4 — do not drop legs on correlation

`OV_DROP_MOSTCORR120` = −0.130 / −0.308 / −0.805 held-out. Dropping the currently
most-correlated leg is harmful in all three panels.

### E1 — L2 ETFRV: fails the ρ1 bounce gate AND the shared-price placebo. **DEMOTE.**

ρ1(Δs) of the daily 15:45 log-spread, against the −0.35 gate:

| pair | IVV/SPY | VOO/SPY | QQQM/QQQ | VTWO/IWM | IJH/MDY |
|---|---|---|---|---|---|
| ρ1(Δs) | **−0.503** | **−0.463** | **−0.457** | **−0.441** | **−0.491** |

All five fail. The frozen L2 spec computes z from the **15:45 print and fills at the same
15:45 print** — R3 failure mode 3 (shared-price measurement error), the `C2_AUCT_RESID_ON`
shape. The placebo: keep the 15:45 signal, move the fill 5 minutes later.

| variant | n | mean net | t | SR |
|---|---|---|---|---|
| fill 15:45 (**frozen**) | 927 | +0.10 bp | +1.41 | **+0.74** |
| fill 15:50 (placebo) | 929 | −1.12 bp | **−15.37** | **−8.01** |
| fill 15:55 (placebo) | 927 | −1.15 bp | −21.15 | −11.03 |

On **gross**: fill 15:45 = **+1.295 bp, t +17.95**; fill 15:50 = **+0.076 bp, t +1.05**.
**94% of the gross edge evaporates in five minutes**, which is the bid-ask bounce in the
signal print, not 15-minute convergence.

This is the single most instructive number in the round: the leg clears any gross
multiple-testing bar you care to name (t = 17.95 against a 2.97 σ bar) **and is still
entirely fake**. The gross bar is necessary, not sufficient — the shared-price placebo is
what decides it.

Worse, the cost model charges a half-spread — but if the 15:45 print you signalled on is *at*
the bid and you are buying, you pay the full spread, so the frozen net number is optimistic on
top of being an artefact. The leg is not tradable as frozen. **Recommend L2 →
ACTIVE_UNSIZED (logging only) pending a quote-midpoint rebuild.** Its standalone net t was
only +1.41 to begin with.

### E2 — L3 DUALCLASS: survives a one-day gap, at half size. Drop BRK.A/BRK.B.

| variant | n round-trips | mean net | t |
|---|---|---|---|
| fill at the signal close (**frozen**) | 512 | +50.09 bp | **+6.54** |
| one-day-gap re-entry | 503 | +23.73 bp | **+3.59** |
| two-day-gap re-entry | 490 | +19.97 bp | +3.07 |

Roughly **half** the headline is same-close bounce, but a real residual survives two days of
gap at t > 3. ρ1(Δs) passes the −0.35 gate for 15 of 16 pairs (−0.13 … −0.34); **BRK.A/BRK.B
is −0.459 and should be dropped** (a $700k share price makes the tick bounce dominate).
**Recommend: size L3 on the gap-1 rung (~24 bp, not 50 bp) and remove BRK.A/BRK.B.**

---

## 6. Honest statement of the theme result

**PORTFOLIO-LEVEL OVERLAY IS NOISE.** 81 overlays, 3 panels, 2000-draw size-matched placebo
per panel. Zero survivors; observed max ≤ null-max mean in 2 of 3 panels; median overlay
negative in all 3. The best zero-parameter candidate that is positive on design, held-out and
full window in both panels where it exists (`OV_ETFRV_EXDIST_OFF`, +0.075 / +0.180 held-out)
is **not a discovery** — it is simply the ±1-session ex-distribution exclusion that the frozen
L2 spec already contains and that I deliberately omitted when rebuilding the leg. It is 3×
below its placebo bar in any case.

**Nothing is promoted. The base stays exactly as it is: equal-risk 1/N on design-vol-scaled
legs, no overlay.** The deployable output of this round is entirely negative — remove the SPY
vol overlay from the combined book, keep equal-risk, demote ETFRV, and halve DUALCLASS.

### Dead-ledger additions (do not rediscover)

Book-level vol targeting (trailing 20/60/120/EWMA, expanding-median target) · EWMA vol
targeting · the T13 SPY-vol overlay on a market-neutral book · drawdown de-lever and
lever-up · trailing-vol risk parity (60/120/expanding/capped/sqrt-shrunk) · inverse risk
parity · diversification-ratio scaling (60/120) and its inverse · inverse-mean-correlation leg
weights · drop-the-most-correlated-leg · always-full renormalisation over live legs ·
equal-dollar weighting · month-end / quarter-edge / triple-witching / year-edge book blackouts
· CEF month-end blackout · ETFRV quarter-edge blackout · expanding-window Sharpe weighting ·
expanding-window Kelly scaling.

---

## 7. Artefacts

| what | path |
|---|---|
| leg panel builder | `/home/anont/meme/scripts/trading_bot/inv0822c_panel.py` |
| overlay sweep + placebo null | `/home/anont/meme/scripts/trading_bot/inv0822c_overlay.py` |
| gross / rebalance-cost / verdict layer | `/home/anont/meme/scripts/trading_bot/inv0822c_finalize.py` |
| ρ1 + shared-price / gap-re-entry diagnostics | `/home/anont/meme/scripts/trading_bot/inv0822c_legdiag.py` |
| six-leg daily panel | `/home/anont/meme/research/data/inv0822c_cache/legs_daily.json` |
| raw sweep + 2000-draw null | `/home/anont/meme/research/data/inv0822c_cache/overlay_raw.json` |
| leg diagnostics | `/home/anont/meme/research/data/inv0822c_cache/legdiag.json` |
| **full result** | `/home/anont/meme/research/trading_bot/INVENT_0822C_overlay.json` |
