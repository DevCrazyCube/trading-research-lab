# INVENT_0822 — STRUCTURALLY-ANCHORED COINTEGRATED SPREADS **AT SCALE**

**Date:** 2026-08-22 · **Scope:** research only. No orders, no money, no purchases, no edit to
the frozen basket. All numbers are cached/free-data backtests and every point estimate is a
selection-inflated upper bound.

**Theme.** Structurally-anchored mean reversion is the one survivor class in this programme
(ETF-sibling L2, dual-class L3, CEF-discount L5). This sweep asks whether the class has any
members left that the basket does not already own, by casting a **much wider net than
`OU_MEAN_REVERSION` did** — pairwise objects at scale, with a real economic tether, each fitted
as an OU process and gated on `ρ1(Δs)`, Hurst and ADF before any P&L is looked at.

**54 formula cells** were run across two families (45 scored + 9 declared controls/placebos),
plus **2 300 matched-size null draws** used to *measure* the bar rather than assume it.

---

## 0. One-paragraph answer

**Nothing is promoted, and one genuinely new fact was established.**

* **Family A — pairwise CEF relative premium (same manager / same mandate / NAV-verified
  near-identical portfolios), 574 pairs.** **Dead, and instructively so.** Its design-window
  t-statistics look spectacular (up to **7.77**) — but a **measured** null built from
  *untethered* cross-category CEF pairs of the same set size scores a **median design t of
  4.96 and a maximum of 7.65**. The analytic bar `√(2 ln 2N) = 2.78` is off by a factor of two
  in this family; against the honest, measured bar **not one of the 24 scored cells is
  remarkable.** Out of sample, under the correct one-day implementation lag and the p90 CEF
  spread, the whole family sits at Sharpe ≈ 0.
* **Family B — same-issuer PREFERRED-SERIES relative value, 113 pairs across 38 issuers, a
  tether never tested in this repo.** **A real spread, and an untradable one.** The gross edge
  is large, tether-dependent, and *replicates out of sample* — design gross Sharpe **3.41
  (t 7.49)**, held-out gross **3.08** — against an untethered cross-issuer placebo of **1.02 /
  0.95** and a preferred-vs-own-common control of **0.55 / 0.14**. That monotone gradient is
  the cleanest confirmation of a tether mechanism this programme has produced. It is then
  killed twice over: (1) the **measured** preferred half-spread (median **17.5 bp**, p90
  **71.2 bp**, first-party NBBO sample) eats it — held-out net falls to **+0.93 Sharpe
  (t 1.48)** and goes **negative at 2× spread**; (2) **0 of 113 pairs have both legs
  shortable** and only 25 % have even one, so the trade cannot be put on in either direction.
* The **preferred-vs-common** tether the brief asked about is **dead as predicted a priori**:
  different seniority is not a tether, and the numbers agree (design gross Sharpe 0.55,
  held-out gross 0.14, held-out net −0.31).

---

## 1. What was tested, and why these tethers

| tether | in this sweep? | why / why not |
|---|---|---|
| CEF vs own NAV, whole universe by sub-class | **prior art** (`DEEPMINE_CEFNAV`, 66 formulas; L5 in the basket) — not re-mined | the cross-sectional level tilt is already owned; re-running it is re-deriving |
| **same-manager fund families / CEF sibling pairs** | **Family A, 24 cells** | *pairwise* relative premium is a different object from the cross-sectional tilt and admits the OU/ρ1 apparatus |
| CEF sub-classes (muni / taxable-FI / equity / hybrid) separately | **Family A, block of 4 cells** | added as a complete block so nothing inside it can be cherry-picked |
| **preferred series vs preferred series, same issuer** | **Family B, 21 cells** | *new to this repo.* Same seniority, same balance sheet — the strongest tether available on free US equity data, and it exists at scale |
| **preferred vs common, same issuer** | **Family B, 3 cells** | the brief's item; tested rather than assumed, and it is dead |
| BDC vs NAV | **not testable** | BDC NAV is quarterly; no free source is wired in this repo (`DEEPMINE_CEFNAV` §2) |
| holdco vs sum-of-parts | **already dead** | `DEEPMINE_holdco_corpstructure`, 0/130 |
| ETN vs its index; when-issued vs regular; commodity-ETF vs its own front future | **not run** | no free index-level or futures/when-issued feed in this repo; the CME-basis branch is already dead (`CME_BASIS_PROBE`, below detectability) |

---

## 2. FAMILY A — pairwise CEF relative premium

### 2.1 Construction

`research/data/t12_cache` (100 % cached, no network): CEFConnect weekly price / NAV / premium
for 353 funds, 249 dates, 2021-08-20 → 2026-08-07, plus Alpaca `adjustment=all` daily closes.

Pair universe: every **within-Morningstar-category** pair of funds that is quoted on ≥ 60 % of
the design grid, raw price > $5 throughout, and Alpaca `easy_to_borrow` on **both** legs →
**574 pairs**. Spread `s = premium_i − premium_j` (also tested as a log-premium spread, and as
a **price-only** log ratio with the NAV information deliberately removed). Signal: rolling
26 w / 52 w z-score of `s`, strictly past window. Book: equal-weight across active pairs,
short the rich leg / long the cheap leg.

Tether tiers (all defined from static attributes or design-window NAV-return correlation — no
P&L consulted):

| tier | definition | pairs |
|---|---|---:|
| `TA_sponsor_cat` | same sponsor **and** same Morningstar category | 46 |
| `TB_cat_nav97` | same category, design-window NAV total-return corr ≥ 0.97 | 91 |
| `TC_sponsor_nav95` | same sponsor, NAV corr ≥ 0.95 | 21 |
| `TD_cat_any` | any same-category pair (loose-tether control) | 574 |
| `TF_gated` | NAV corr ≥ 0.95 **and** ρ1(Δs) > −0.35 **and** Hurst < 0.5 **and** ADF < −2.57 | 6 |
| `TG_*` | sub-class blocks: MUNI 53 / TAXFI 50 / EQUITY 39 / HYBRID 1 | — |
| `TE_placebo_xcat` | **cross-category pairs — no tether at all** | 400 |

Costs (inherited verbatim from `DEEPMINE_CEFNAV` so the numbers are comparable to the
incumbent): measured **11.53 bp** CEF half-spread on both legs of turnover, SEC §31 0.278 bp on
sales, borrow at the realised **200 bp/yr** rate on the short leg. **Stress ladder:** the
correct **one-trading-day implementation lag** (CEFConnect publishes NAV after the close) and
the **p90 spread 27.25 bp**, applied separately and together.

Design 2021-08-20 → 2024-02-23 (125 weeks). Held out 2024-03-01 → 2026-08-07 (117 weeks).

### 2.2 The result, and the measured null that interprets it

| cell | tether | pairs | design gross Sh / t | held-out net Sh / t | **held-out STRESSED Sh / t** |
|---|---|---:|---|---|---|
| A04 | any same-category (loose) | 574 | 5.63 / **7.77** | 1.72 / 2.57 | **0.02 / 0.03** |
| **A05** | **PLACEBO cross-category** | **400** | **4.79 / 6.62** | **1.24 / 1.86** | **0.04 / 0.06** |
| A13 | sponsor+cat, z52 | 46 | 4.80 / 5.68 | 1.41 / 2.12 | 0.50 / 0.75 |
| A02 | cat, NAVcorr ≥ 0.97 | 91 | 3.70 / 5.11 | 2.65 / 3.97 | **1.11 / 1.66** |
| A15 | cat, NAVcorr ≥ 0.97, z52 | 91 | 3.47 / 4.11 | 1.90 / 2.84 | 0.95 / 1.43 |
| A01 | sponsor+cat, z26 | 46 | 3.45 / 4.76 | 1.27 / 1.90 | −0.19 / −0.28 |
| A26 | TAXFI sub-class | 50 | 4.93 / 6.80 | 1.54 / 2.30 | 0.68 / 1.01 |
| A25 | MUNI sub-class | 53 | 2.75 / 3.74 | 1.72 / 2.57 | 0.75 / 1.12 |
| A27 | EQUITY sub-class | 39 | 2.95 / 4.07 | 1.14 / 1.72 | −0.36 / −0.53 |
| A09 | sponsor+cat, fixed 4 w tranches | 46 | 3.07 / 4.24 | −0.12 / −0.19 | −1.91 / −2.86 |
| A23 | sponsor+cat, LOW band \|z\|≥1 | 46 | 3.47 / 4.79 | 0.04 / 0.05 | −1.18 / −1.77 |

**Read the placebo row first.** A book of **400 pairs with no tether whatsoever** — CEFs picked
from *different* asset classes — scores a design gross Sharpe of **4.79 at t 6.62**. Every
tethered cell in the table is at or below that. The design window simply cannot discriminate
here.

So the bar was **measured**: 300 draws of untethered cross-category pair-sets at each matched
size, identical formula, identical costs (`INVENT_0822_pairtether_A_null.json`):

| null, size 91 | median | p90 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|
| design gross **t** | 4.96 | 6.03 | 6.56 | 7.25 | **7.65** |
| design gross Sharpe | 3.60 | 4.37 | 4.76 | 5.26 | 5.55 |
| held-out net Sharpe | 0.70 | 1.47 | 1.69 | 2.01 | 2.60 |
| **held-out stressed Sharpe** | **−0.20** | 0.44 | 0.62 | 0.94 | 1.48 |

| null, size 46 | median | p95 | max |
|---|---:|---:|---:|
| design gross t | 4.15 | 5.33 | 6.18 |
| held-out stressed Sharpe | −0.11 | 0.75 | 1.48 |

**Verdict, Family A: HONEST ZERO.** The best cell, `A02`, has a held-out stressed Sharpe of
1.11 — the ~p99 of the *untethered* null, which is exactly what one expects as the maximum of
24 scored cells. Its block bootstrap agrees it is not decisive (P(α>0) = 0.95, 95 % CI
[−0.8, +10.7] bp/wk). Two structural readings worth keeping:

1. **The 1-day implementation lag, not the spread, is what kills the family.** Decomposed on
   the held-out block, `A02` goes 2.65 → 2.04 (lag only) → 1.70 (p90 spread only) → 1.11
   (both); `A04` goes 1.72 → 0.68 → 1.02 → 0.02. The signal is substantially a *response to a
   NAV print that is not yet actionable*, i.e. the same defect `DEEPMINE_CEFNAV` §7b found in
   the cross-sectional short-horizon branch, reproduced here on a completely different object.
2. **The NAV information does almost no work.** `A18`, the same 46 pairs with the spread
   redefined as a plain price log-ratio and the NAV thrown away, held out stressed at 0.38 —
   *better* than the premium-spread version of the same pairs (`A01`, −0.19). A "tether" whose
   defining information can be deleted without loss is not operating as a tether.

---

## 3. FAMILY B — same-issuer preferred-series relative value  ⟵ **the real finding**

### 3.1 Why this tether is strong

Two preferred series of one issuer are claims of the **same seniority on the same balance
sheet**, differing only in coupon and call date. Their price ratio is pinned by the coupon
ratio plus a call-option term; there is no mechanism by which `GS.PRA` and `GS.PRC` can
diverge permanently. No FX, no time zone (unlike cross-listing), no NAV opacity (unlike
holdco), no basket difference (unlike ETF siblings). And it exists **at scale**: 361 listed
`.PRx` series, 85 issuers with ≥ 2 series, 518 raw within-issuer pairs.

### 3.2 Data — newly fetched, first-party measured

`research/data/inv0822_tether/` (Alpaca DATA endpoint only):

* daily bars 2018-01-01 → 2026-08-20, **both** `adjustment=all` (for returns) and
  `adjustment=raw` (for the level). This distinction matters: `adjustment=all` subtracts each
  series' *own* dividends, so two preferreds with different coupons acquire a deterministic
  divergence in their adjusted ratio that is a pure artefact. **Raw for the spread, adjusted
  for the P&L.**
* **half-spread measured from the historical NBBO tape** — quotes sampled in six 2-minute
  windows across six sessions (2026-03 … 2026-08), 506 symbols: **median 17.5 bp, p25 6.0,
  p75 34.3, p90 71.2**. (`quotes/latest` is 403 on these credentials; the historical tape is
  entitled. This is a first-party measurement, not an assumption — but it is a 2026 snapshot
  applied to a 2018-2026 backtest, and that is declared, not hidden.)
* Alpaca `shortable` / `easy_to_borrow` flags per series.

Screen: quoted on ≥ 70 % of the design grid, median raw price in ($5, $40) — a $25-par
preferred → **145 series, 113 within-issuer pairs across 38 issuers**. Weekly (5-session)
sampling because a preferred's daily close is a stale, bouncing print. Design 2018-01-02 →
2023-12-31 (302 weeks); held out 2024-01-03 → 2026-08-14 (131 weeks).

### 3.3 The OU / cointegration diagnostics — this family passes them properly

| statistic (113 pairs, design window) | p10 | median | p90 |
|---|---:|---:|---:|
| **ρ1(Δs)** | −0.398 | **−0.245** | −0.076 |
| Hurst | 0.456 | 0.539 | 0.654 |
| ADF t | −5.86 | **−3.35** | −1.53 |
| OU half-life (weeks) | 1.4 | **4.4** | 20.3 |
| measured half-spread (bp) | 9.4 | 22.2 | 175.3 |

**80 % of pairs pass the ρ1(Δs) > −0.35 gate and 67 % reject a unit root at 5 %** (median ADF
−3.35). Compare the ETF-sibling family, where `ρ1(Δs) ≈ −0.50` on all five pairs and ADF failed
on four of five. This is not bid-ask bounce dressed as convergence; it is genuine cointegration
with a ~4-week clock. (Hurst is the odd one out at median 0.539 — the R/S estimator is biased
upward on ~300 points, which is why the joint gate is so restrictive.)

### 3.4 The tether gradient — the cleanest mechanism confirmation in the programme

Identical formula (log raw price ratio, 52 w z, enter |z| ≥ 2, exit |z| ≤ 0.5, 26 w cap),
identical costs, three populations:

| population | pairs | design gross Sh / t | **held-out GROSS Sh** | held-out net Sh / t | held-out net @2× spread |
|---|---:|---|---|---|---|
| **same issuer, same seniority** (B01) | 113 | **3.41 / 7.49** | **3.08** | +0.93 / 1.48 | −0.98 |
| cross-issuer PLACEBO (B05) | 500 | 1.02 / 2.23 | 0.95 | −0.35 / −0.56 | −1.26 |
| preferred vs its **own common** (B23) | 111 | 0.55 / 1.21 | 0.14 | −0.31 / −0.49 | −0.56 |

The ordering is monotone in tether strength, it is large (3.4 vs 1.0 vs 0.55 on gross), and it
**replicates out of sample** (3.08 vs 0.95 vs 0.14). Same asset class, same cost model, same
formula, same window — the only thing that changes is whether the two legs are claims on the
same balance sheet at the same seniority. **The tether is doing the work, and it is
measurable.** Note also that this is the pattern the brief demanded and Family A failed to
show.

### 3.5 …and it is dead anyway, for two independent reasons

**(a) The execution-cost wall — but this time the gross signal cleared the bar first.**
`EXECUTION_COST_WALL`'s rule is that a signal must clear multiple testing on GROSS before any
cost-fix is worth discussing. This one does: design gross t **7.49** against an analytic bar of
`√(2 ln 42) = 2.73` and against a *measured* untethered placebo of **2.23**. It is therefore a
legitimate cost-wall casualty rather than a sub-bar mirage. But the wall is total: at the
measured median 17.5 bp half-spread the held-out net is **+0.93 Sharpe (t 1.48, +9.6 bp/wk,
block-bootstrap P(>0) = 0.92)** — positive, not significant — and at 2× spread it is **−0.98**.
Restricting to the liquid half (half-spread ≤ 30 bp, 71 pairs) gives held-out net 0.96 (t 1.53)
and survives 2× at only 0.44. There is no version of this that is a business.

**(b) It cannot be shorted. At all.** Of the 113 within-issuer pairs, **0 have both legs
shortable** and **28 (25 %) have even one leg shortable**. A relative-value trade needs to short
whichever leg is rich, which is either leg depending on the sign of `z`. The one-leg-shortable
subset (B26, 28 pairs) is the most one could actually attempt: held-out net **1.21 (t 1.92)**,
2× spread 0.69 — and it is a half-signal book by construction.

### 3.6 The two cells that survived cost — and the matched-size null that kills them

`B04` (OU-gated **and** liquid, 6 pairs) held out at net Sharpe **1.86 (t 2.69)**, and still
1.47 at 2× spread; `B16` (same 6 pairs, wide |z| ≥ 3 → 1.0 band) at **2.76 (t 1.99)**, 2.36 at
2×. Both look promotable. They are not:

* The 6 pairs are **GS.PRA/GS.PRC, GS.PRA/GS.PRD, PSA.PRF/PSA.PRG, PSA.PRQ/PSA.PRR,
  TRTN.PRA/TRTN.PRB, TWO.PRA/TWO.PRC** — **four distinct issuers**, two of them contributing
  overlapping pairs, and **1.3 concurrent positions** on the held-out block. Ten of the twelve
  legs are not shortable.
* Matched-size null, 400 draws of size-6 pair-sets, identical spec and costs
  (`INVENT_0822_pairtether_B_null.json`):

| null (size 6, held-out **net** Sharpe) | median | p90 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|
| N1 — untethered, gated + liquid, `B04` spec | 0.31 | 0.94 | 1.09 | 1.37 | 1.68 |
| **N2 — tethered, ungated, `B04` spec** | **0.46** | **1.34** | **1.47** | **1.79** | **2.39** |
| N1 — untethered, `B16` wide-band spec | 0.28 | 2.04 | 3.05 | 5.12 | 6.98 |
| **N2 — tethered, ungated, `B16` spec** | **1.42** | **3.54** | **4.36** | **7.10** | **8.26** |

`B04`'s 1.86 sits at ≈ p99 of the "pick six tethered pairs at random" null — precisely the
maximum one expects from 21 scored cells. `B16`'s 2.76 is **below the p90 (3.54)** of the same
null: a six-pair wide-band book has enormous dispersion and 2.76 is an unremarkable draw. **The
OU gate adds nothing beyond the tether; the apparent survival is small-n dispersion.**

---

## 4. Scoreboard and the honest bar

| | Family A | Family B |
|---|---|---|
| scored formula cells | 24 | 21 |
| declared controls / placebos | 3 | 6 |
| pairs in the widest tether | 574 | 113 (38 issuers) |
| analytic bar `√(2 ln 2N)` | 2.78 | 2.73 |
| **measured null, design gross t** | **median 4.96, max 7.65** (size 91) | placebo 2.23 (500 pairs) |
| best design gross Sharpe / t | 5.63 / 7.77 (`A04`, untethered-equivalent) | **3.41 / 7.49** (`B01`) |
| best held-out **gross** | — | **3.08** (`B01`) |
| best held-out net after honest stress | 1.11 (`A02`, ≈ p99 of null) | 1.86 (`B04`, ≈ p99 of null, 4 issuers, unshortable) |
| **verdict** | **noise** | **real spread, untradable** |

45 scored cells → analytic `√(2 ln 45) = 2.76` as the nominal Sharpe/t bar. Family A's measured
null says that number is **wrong by 2×** for overlapping pair books on weekly CEF data; Family
B's placebo says it is roughly right there. *Measure the null; do not assume it.*

## 5. Diversification against the existing legs

Moot — nothing clears. For the record, had Family B been tradable it would have been
**structurally orthogonal** to the basket: its instruments (issuer-level preferred stock) share
no security, no issuer and no asset class with L2 (index ETFs), L3 (dual-class common) or L5
(closed-end funds), and its driver is issuer-level preferred-curve dislocation rather than a
fund discount. Family A is *not* diversifying by construction — it trades the same 353 CEFs as
L5.

---

## 6. What to carry forward

1. **`ρ1(Δs) > −0.35` is necessary, not sufficient — and now there is a positive control.**
   Same-issuer preferred pairs pass it comfortably (median −0.245, 80 % of pairs) *and* reject
   a unit root (67 %) *and* still produce nothing tradable. The gate correctly separates
   bounce from convergence; it does not separate convergence from unprofitability.
2. **Measure the null with a size-matched, tether-free placebo before reading any design-window
   t.** In the pairwise-CEF family the untethered median design t is **4.96**; anyone applying
   `√(2 ln 2N) = 2.78` to that family will "discover" twenty edges that are not there. This is
   the single most transferable output of this sweep and it costs one extra script.
3. **A tether gradient is the right acceptance test for the survivor class.** Family B's
   3.41 → 1.02 → 0.55 ordering (same-issuer / cross-issuer / pref-vs-common) is what a real
   tether looks like; Family A's flat placebo is what a fake one looks like. Demand the
   gradient before the Sharpe.
4. **Preferred-vs-common is dead** — different seniority is not a tether. Do not re-propose.
5. **Same-issuer preferred RV is now a known, characterised, *shelved* object**, not an open
   question: real gross Sharpe ≈ 3 that replicates OOS, killed by a measured 17.5 bp median
   half-spread and a hard borrow wall (0/113 pairs both-shortable). The only thing that could
   revive it is a venue with materially better preferred borrow and sub-10 bp execution —
   which is a *data/broker* question, not a research question, and it belongs with the
   free-data-convexity-wall finding rather than in another formula sweep.

---

### Files

* `scripts/trading_bot/invent0822_pairtether.py` — Family A engine (cached t12 data only)
* `scripts/trading_bot/invent0822_null_A.py` — Family A measured null
* `scripts/trading_bot/invent0822_pref_fetch.py`, `..._pref_fetch2.py` — Family B data pull
  (Alpaca DATA endpoint only; raw + adjusted bars, NBBO half-spread sample, borrow flags)
* `scripts/trading_bot/invent0822_preftether.py` — Family B engine
* `scripts/trading_bot/invent0822_null_B.py` — Family B matched-size nulls
* `research/trading_bot/INVENT_0822_pairtether_{A,B}.json`,
  `INVENT_0822_pairtether_{A,B}_null.json`, `INVENT_0822_tether_scale.json`
* `research/data/inv0822_tether/` — newly cached preferred universe

*Research only. No orders, no money, no purchases, no edit to the frozen basket. The forward
log remains the only arbiter.*
