# INVENT R3 — CONDITION & COMBINE the surviving edges

**Verdict in one line: CONDITIONING is noise. COMBINING works, but only the version with no
fitted parameters — and the lift it delivers is ordinary diversification arithmetic, not a
discovered edge.**

107 distinct conditioning formulas, 314 declared trials, expected-max statistic under the null
`sqrt(2 ln 314) = 3.39`. Exactly two conditioners cleared that bar on the design window. Neither
survived the held-out window. Every fitted combination rule (min-variance weights,
Sharpe-proportional weights, regime-switching weights, vol-targeting) was beaten out of sample by
flat equal-risk weights.

---

## 1. What was tested, on what

### Legs (rebuilt from cache under their FROZEN specs — no leg was re-fit)

| leg | spec | obs | source |
|---|---|---|---|
| **T3** | end-of-day pressure reversal, top-300, w=10, cut=0.10, net 1.43+0.31 bp + 30 bp borrow | 2606 nights, 2016-02-01 → 2026-08-13 | `t3_cache/panel.json.gz` |
| **T7D1** | ex-dividend cum-close → **ex-open** residual, frozen cfg, auction rail | 2320 event-days, 2016-02-02 → 2026-08-14 | `t7_cache/panel.json.gz` + `t3_cache/auctions` |
| **CEF** | T12 **S2** discount-LEVEL decile tilt, H=4 wk, net @11.53 bp | 240 weeks, 2021-08 → 2026-08 | `t12_cache` (CEFConnect, cached) |

Reconstruction was validated against the frozen results: T7D1 held-out 2022-26 reproduces
+3.35 bp/event-day at the auction rail; CEF S2/H4 reproduces +13.7 bp/wk, Sharpe 2.20.
XS_GLSR_Z was **not** included — it is already demoted to logging-only (v4 freeze) and its GLSR
inputs are not in the cached panel. ETF-sibling RV and DUALCLASS were not included: the DEEPMINE
etf-structural held-out net Sharpe is already negative, so gating it studies noise.

### Windows

* daily legs — **DESIGN 2016-02-01 … 2022-12-30** (n≈1740) / **HOLDOUT 2023-01-03 … 2026-08-14** (n≈870)
* weekly ensemble — same split on the weekly calendar (design 71 wk / holdout 188 wk, because
  the CEF leg only starts 2021-08). Re-run at splits 2023-12-29 and 2024-02-29 as a robustness check.

**The honest caveat on the holdout.** 2023–2026 was *not* previously untouched at the LEG level —
T3, T7 and T12 each reported a held-out number there. What was never fit there is a
**conditioner**. So the number this document treats as evidence is always a **difference**:
conditioned-minus-raw on the identical holdout window, where both arms see the same tape.

### Conditioners (every one strictly as-of close(t−1); every threshold fit on DESIGN only)

`VIX_LEVEL`, `VIX_TERM` (VIX/VIX3M), `VIX_9D_RATIO`, `VVIX_RATIO`, `VIX_DCHG`, `SPY_TREND200`,
`SPY_TREND20`, `SPY_MOM20`, `RV20`, `RV5_OVER_RV20`, `VRP` (VIX − 20d realised), `RANGE20`,
`VOLUME_REL`, `RATE_LEVEL`, `RATE_CHG`, `SPY_RET_PREV`; day-types `DT_MON` `DT_FRI` `DT_MIDWEEK`
`DT_TURNMONTH` `DT_OPEXWEEK`; leg-derived `OWN_MOM20` `OWN_MOM60` `OWN_VOL20` `CTRL_PREV`
`CTRL_ABS20` `LEG_ASYM20` `CROSS_MOM20`; and — genuinely new — the **CEF-universe median discount**
as a Lee-Shleifer-Thaler retail-sentiment gauge applied to the *equity* legs
(`CEF_MED_DISCOUNT`, `CEF_DISC_VS_13W`, `CEF_DISPERSION`).

All VIX/SPY/rate inputs come from the already-cached `volterm_cache/raw/*.json`. **No network call
was made by this study.**

### Formula forms (five, deliberately different)

1. **GATE** — median split on DESIGN, sign chosen on DESIGN, stand down when off.
2. **TILT** — continuous size `clip(1 + s·0.5·z, 0, 2)`, renormalised to unit average design gross.
3. **INTERACT** — two-way quadrant gates; trade only the best DESIGN quadrant.
4. **SIDE** — condition the T3 **long half and short half separately** on trend/term-structure.
5. **SENTGATE / SWITCH / ENSEMBLE / VOLTARGET** — cross-leg filters, regime-switching weights,
   fixed-weight combinations, and a trailing-vol overlay.

---

## 2. CONDITIONING — the result

**Statistic.** For a gate, the honest null is not "the strategy has zero Sharpe" (the legs have
real edge, so a gated leg inherits it). It is "the conditioner is uninformative", under which the
**ON-minus-OFF mean-return difference** has mean zero. That Welch t is the reported statistic, and
its expected maximum over N independent trials is `sqrt(2 ln N)`. For tilts the equivalent
statistic is the t of the **overlay** series `(w−1)·r` — what the tilt adds on top of a flat book.

**N = 314 trials → bar = 3.391.**

Only two of 107 formulas cleared it on design:

| formula | design t | HELD-OUT t | HELD-OUT ΔSharpe vs raw leg | verdict |
|---|---|---|---|---|
| `INTERACT T3 · VIX_LEVEL × RATE_CHG` (best quadrant) | **+4.47** | −0.62 | **−0.91** | **DEAD** — sign flips |
| `GATE T3 · RATE_CHG` (median split) | **+3.58** | +0.52 | +0.11 | **DEAD** — indistinguishable from zero |

The runners-up all fail the bar and then fail again out of sample:

```
GATE  T3   SPY_MOM20        design t=+3.26  HOLD t=-0.35  dSR=-0.63
GATE  T3   CTRL_ABS20       design t=+3.12  HOLD t=+0.26  dSR=-0.37
TILT  T3   RV20             design t=+3.07  HOLD t=-1.94  dSR=-0.36
TILT  T3   VIX_TERM         design t=+3.05  HOLD t=-0.08  dSR=-0.24
GATE  T3   VIX_LEVEL        design t=+3.00  HOLD t=-0.09  dSR=-0.54
```

Read the ΔSharpe column: **gating T3 on volatility regime destroys roughly half its held-out
Sharpe** (raw 1.29 → 0.75 on a VIX gate, → 0.50 on a VIX9D gate, → 0.39 on a cross-leg momentum
gate). The conditioners are not merely uninformative; the ones the design window liked are
actively harmful out of sample, which is the signature of fitting.

Of 107 formulas, **13 are positive in both windows** — fewer than chance would give, because the
sign is fit on design and the holdout is then a coin flip. The largest of them (`GATE T3 ·
CTRL_PREV`, holdout ΔSharpe +0.49) has a **design t of only +1.70**, half the bar. It is not
selected, and it is named here only so a later reader does not "rediscover" it.

**The CEF-sentiment cross-gate (new mechanism) is dead too.** Gating T3 or T7 on the CEF universe's
median discount — the classic retail-sentiment proxy — gives design t between 0.00 and 1.93 and
held-out ΔSharpe between −0.86 and −0.09. Nothing.

**Day-types are dead.** The best is `T7D1 · DT_FRI` (design t +1.33, holdout t +1.94) — below the
bar on design, and the "calendar effects" theme is already on the dead ledger from the 380-formula
sweep. Not revived.

### 2b. The one conditioning result that looked alive, and why it is not

`SIDE_LONGONLY_HI` — run the T3 long decile alone when SPY is above its 200-day (or the VIX curve
is in contango), dollar-neutral otherwise — beat the raw leg in **both** windows: design 1.92 vs
1.74, holdout 1.81 vs 1.31. That is exactly the shape a real conditioner would have.

It is beta. An un-hedged long half held overnight in a bull tape collects the **overnight equity
risk premium**, which is on the dead ledger (overnight-harvest). Subtracting the realised net
exposure times the equal-weight universe overnight return (`control` — literally that premium):

| conditioner | design unhedged | design **hedged** | raw | holdout unhedged | holdout **hedged** | raw | beta contributed |
|---|---|---|---|---|---|---|---|
| SPY_TREND200 | 1.92 | **1.64** | 1.74 | 1.81 | **1.55** | 1.31 | +4.90 bp/night |
| VIX_TERM | 1.99 | **1.84** | 1.74 | 1.79 | **1.57** | 1.31 | +4.32 bp/night |
| SPY_MOM20 | 1.73 | **1.55** | 1.74 | 1.70 | **1.66** | 1.31 | +2.37 bp/night |
| VIX_LEVEL | 1.66 | **1.69** | 1.74 | 1.44 | **1.50** | 1.31 | +2.15 bp/night |

Hedged, the design lift collapses to +0.10 at best and is negative for three of four conditioners.
A rule whose design window does not support it and whose entire visible gain is a market premium
already declared dead is **not a conditioner**. Killed.

### 2c. A diagnostic worth keeping (not a strategy)

Decomposing T3 against the equal-weight universe overnight return:

| | long half vs control | short half vs control |
|---|---|---|
| design 2016-2022 | +9.51 bp, **t 5.48** | +7.58 bp, **t 4.75** |
| holdout 2023-2026 | +11.28 bp, **t 3.85** | +3.87 bp, **t 1.36** |

**T3's short half has stopped working.** The long half is intact and if anything stronger; the
short half's t fell from 4.75 to 1.36. This is a structural fact about the anchor leg, it costs
nothing to monitor, and it is the *real* reason the "long-only in an uptrend" variant looked good.
It belongs in the forward log as a per-half diagnostic, **not** as a rule change — the basket
freeze forbids changing L1, and a half whose t is 1.36 is not yet evidence of death either.

---

## 3. COMBINING — the result

Every leg is scaled to unit DESIGN volatility, weekly calendar, self-financing.

| book | weights | design SR | **HELD-OUT SR** |
|---|---|---|---|
| T3 alone | — | 1.64 | 1.24 |
| T7D1 alone | — | 0.60 | 1.70 |
| CEF alone | — | 2.68 | 1.81 |
| `ENS_EQRISK_T3_T7` | ⅓·2 | 1.52 | 2.21 |
| **`ENS_EQRISK_ALL3`** | **⅓ ⅓ ⅓, un-fitted** | 2.64 | **2.93** |
| `ENS_MINVAR` (design cov) | fitted | 2.77 | 2.93 |
| `ENS_SHARPE_WEIGHTED` (design SR) | fitted | 3.03 | 2.90 |
| `ENS_BASKET_V5` (the frozen v5 budgets) | fitted | 2.77 | 2.45 |
| `ENS_CEF_HEAVY` 0.25/0.15/0.60 | — | 3.06 | 2.77 |
| `VT13_ENS_EQRISK_ALL3` (13-wk vol target) | overlay | 2.61 | 3.11 |
| `SWITCH` on VIX_LEVEL / VIX_TERM / TREND / RV20 | fitted per regime | 3.11 / 3.10 / 3.19 / 3.38 | **2.86 / 2.71 / 2.97 / 2.59** |

Three things fall out, and only the first is good news.

**(1) Combining is a real, held-out, deployable upgrade.** Equal-risk over the three legs holds out
at **2.93 vs 1.81 for the best single leg** — a lift of **+1.11 Sharpe**. It is split-insensitive:
2.97 / 2.63 / 2.79 at splits 2022-12-30 / 2023-12-29 / 2024-02-29. On the two long-history legs
alone (361 design weeks, 188 holdout weeks — a much better-powered sample than the CEF-truncated
one) T3+T7 equal-risk holds out at **2.21 vs 1.24 and 1.70** for the legs.

**(2) It is arithmetic, not discovery.** Feeding each leg's *own* held-out Sharpe and the *design*
correlation matrix into `Σwᵢ·SRᵢ / √(wᵀCw)` predicts a combined Sharpe of **2.61**. Realised: 2.93.
The **+0.32 excess** is entirely realised correlations landing more negative than design
(design corr T3/T7/CEF = +0.04 / +0.05 / +0.07; holdout = −0.10 / −0.02 / −0.10). Nothing was
discovered here that a spreadsheet could not have said in advance from the legs' own priors. That
is worth stating plainly, because a 2.93 in a report reads like a finding and it is not one.

**(3) Every fitted combination rule lost to flat weights out of sample.** Min-variance ties
(2.93). Sharpe-proportional loses (2.90). The frozen v5 risk budgets lose badly (2.45). All four
regime-switching weightings win on design (3.10–3.38 vs 2.70) and **lose or tie out of sample**
(2.59–2.97 vs 2.93) — a textbook overfit signature: the more the weights are allowed to learn, the
worse they travel. The vol-target overlay is the one near-miss (3.11 vs 2.93) but the gain is
inside the noise and the overlay is already the T13 sleeve's job.

**Recommendation to the basket: do not fit weights.** The v5 fitted risk budgets (T3 0.268 / T7
0.075 / CEF 0.17 + the unsized legs) held out at 2.45 against 2.93 for flat equal-risk over the
same three legs. That is a **−0.48 Sharpe cost paid for fitting**.

---

## 4. Under a real cost rung

The headline numbers above use each leg's own frozen cost model, and T7's is the **auction rail**
(zero entry/exit half-spread, M0 unperformed). That is optimistic. The stressed rung charges T7 a
real 1.13 bp half-spread per leg (the rung that takes its standalone Sharpe to ~0.2), charges T3
2× entry half-spread **plus** a real exit spread instead of a free opening cross, and charges CEF
another half of its measured 11.53 bp on turnover:

| | design SR | **HELD-OUT SR** | worst holdout third |
|---|---|---|---|
| T3 | 1.00 | 0.61 | — |
| T7D1 | −0.46 | 0.79 | — |
| CEF | 2.49 | 1.58 | — |
| **equal-risk all 3** | 1.67 | **1.75** | **1.21** |
| T3+T7 equal-risk, full history | 0.51 | 1.05 | — |

The combination still holds out positive under stress, and its worst four-month third is +1.21 —
but the lift over simply holding the CEF leg alone shrinks to **+0.17**, and the two-leg
equity-only book falls to 1.05. **Under realistic costs the basket is mostly the CEF leg plus a
diversification kicker**, and the CEF leg's own priors carry the caveats already in the v4/v5
freeze (edge concentrated in one half-sample, 37% of the stressed mean in 5 of 114 weeks,
capacity capped at low single-digit $M by CEF auction volume).

---

## 5. What this round adds to the dead ledger

**DEAD — do not re-propose without a genuinely new mechanism:**

* regime-gating any alive leg on **VIX level, VIX term structure, VIX9D/VIX, VVIX/VIX, ΔVIX**
* regime-gating on **realised vol (20d, 5d/20d), SPY range, SPY volume**
* regime-gating on **trend (200d, 20d, 20d momentum)** — including the long-only-in-uptrend
  variant, which is overnight-harvest beta in disguise
* regime-gating on **VRP, rate level, rate change** (the two design-bar clears both die OOS)
* **continuous tilts** of the same conditioners (10 per leg, all dead)
* **two-way regime interactions** (6 pairs × 2 legs, all dead)
* **day-type gates** on T3/T7 (Mon/Fri/midweek/turn-of-month/opex week)
* **cross-leg momentum gating** (use one leg's trailing P&L to size another) — the worst of all,
  holdout ΔSharpe −0.90 on T3
* **CEF-discount retail-sentiment gating of equity legs** (new mechanism, tested, dead)
* **fitted ensemble weights** of any kind: min-variance, Sharpe-proportional, regime-switching

**ALIVE (added to the basket's evidence, not a new leg):**

* **flat equal-risk combination** of T3 + T7D1 + CEF, no fitted weights — held out 2.93 headline /
  1.75 stressed, split-insensitive, beats every fitted weighting. This is a **sizing-rule** finding,
  not a signal finding.

**MONITOR:** T3's short half (t 4.75 → 1.36 design → holdout).

---

## 6. Files

* `scripts/invent_r3_conditioning.py` — legs, conditioners, gate tests, ensembles (phase 1)
* `scripts/invent_r3_phase2.py` — tilts, interactions, side-conditioning, sentiment gate, switching
* `scripts/invent_r3_phase3.py` — beta control on the SIDE result, diversification-only null
* `scripts/invent_r3_phase4.py` — stressed cost rung, holdout subperiods
* `research/trading_bot/INVENT_R3_condition_combine.json` — phase 1 results
* `research/trading_bot/INVENT_R3_condition_combine_phase2.json` / `_phase3.json` / `_phase4.json`
* `research/data/invent_r3/` — reconstructed leg series and the cached conditioner panel

No network call was made. No leg spec was altered. No frozen file was touched.
