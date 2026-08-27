# INVENT_0822C — MASTER SYNTHESIS (2026-08-22, 3rd rotation)

Three genuinely different angles, **223 pre-registered formulas**, pooled correction over the total.
Themes: **CEF family deepened** (114), **portfolio-level overlays across the sized basket** (81),
**published-gap tether / corporate-action ex-day** (28).

> **HEADLINE: 3 of 3 themes are noise. ZERO survivors, zero promotions — and the round is still the
> most consequential of the three rotations today, because its real output is SUBTRACTIVE: one
> infrastructure bug that silently inflated a shared cache, and three escalations that each REMOVE or
> SHRINK something already inside BASKET1. The round found no alpha and deleted some.**

Nothing was committed. BASKET1 is untouched. No orders, no network access — every input was cached.

---

## 1. The pooled null over all 223

| Bar over N = 223 | max abs t |
|---|---|
| Analytic one-sided sqrt(2 ln N) | 3.29 |
| Analytic two-sided sqrt(2 ln 2N) | **3.49** |
| × the largest measured placebo/analytic ratio in the programme (1.14, overlapping books) | **3.98** |
| Programme-cumulative, ~1,430 distinct formulas, sqrt(2 ln 2N) | **3.99** |

No single cross-theme placebo is constructible: the three panels share no instrument, no calendar and
no statistic (theme 2's statistic is a **dSharpe between two ~0.99-correlated books**, not a raw
Sharpe). Each theme therefore measured its own size-matched placebo and the pooled bar above is
assembled. It never binds this round — **no theme's best cell reaches even its own per-theme bar**:

| Theme | N | best design stat | own analytic bar | own size-matched placebo | verdict |
|---|---|---|---|---|---|
| CEF deepened | 114 | held-out stressed alpha t **1.17** (vs incumbent L5) | 3.078 (3.295 at 2N) | 2.784 (placebo gross-t SD 0.845 — **under**-dispersed) | noise |
| Portfolio overlay | 81 | held-out dSharpe **+0.345** (a pre-declared FITTED control) | 2.965 σ | p95 +0.330 / +0.392 / **+0.574** by panel | noise |
| Published-gap tether | 28 | design gross \|t\| **2.50** | 2.582 (2.84 at 2N) | p95 **3.24**, mean-of-max 2.28 | noise |

**Third measurement of the placebo/analytic ratio, and it is now a stable finding.** 1.08× on the
disjoint auction book (0822B), ~2× on the overlapping weekly CEF pair book (0822), 1.14× on this
round's disjoint event book, and **0.845× on the CEF fund-identity permutation** — i.e. below the
analytic bar. The inflation lives in **holding overlap**, not in multiple testing as such. Keep
measuring per book; assume neither direction.

---

## 2. Survivors

**None.** No formula in any of the three themes cleared its gross bar, so no held-out promotion was
available to make. Two near-cells were carried to the holdout anyway, for the record, and both died:

* **B03_disc_grp_mad_etbboth_H1** (CEF): the incumbent discount tilt with a group-MAD
  standardisation. It answered a narrow pre-registered question — *does MAD-standardisation beat the
  raw level on the stressed held-out block?* — and the answer is **no**: design stressed 1.86 vs the
  incumbent's 1.49, held-out stressed **1.22 vs the incumbent's 2.10**, held-out stressed 2-factor
  alpha to L5 **−0.70**. Better in sample, worse out of sample. The dispersion normalisation is a
  design-window artefact. Corr 0.75 to L5, so it was never a diversification candidate.
* **D1_FWD_GAP** (gap tether): forward-split ex-date gap residual, design gross SR 0.94 / t 2.50 on
  59 active days, **below its own analytic bar (2.84) and well below its placebo p95 (3.24)** — it
  never earned the held-out look it was given. Held out it collapses to SR 0.55 (t 1.04) and the
  matched-control estimate falls from +68.8 bp (t 2.59) to +10.0 bp (t 0.45).

The clean statement for theme 1: **across all 114 formulas the single highest held-out stressed
two-factor alpha t to the incumbent L5 is 1.17**, against a size-matched alpha bar of 3.35. Unlike
DEEPMINE_CEFNAV — where peeking at the holdout would have promoted C02_cat_within at alpha t 3.77 —
peeking here would have found **nothing**. There is no winner to argue about.

---

## 3. What the round actually produced: one bug, three escalations, one ledger correction

### 3.1 INFRASTRUCTURE BUG (owner call — the shared cache was deliberately NOT modified)

`research/data/t7_cache/corporate_actions_all.json.gz` contains **26,038 exactly duplicated
cash-dividend records** (same `id` twice; 385,845 rows → 359,807 distinct), plus 37 duplicated
forward splits and 207 duplicated reverse splits. Summing rates **doubles the published dividend on
~8% of ex-dates and SQUARES split factors**.

On the duplicated cache this theme looked like the best result of any invention round: mean hedged
ex-day residual +7.33 bp, drop ratio 0.87 (textbook Elton–Gruber), A2_YW design gross t **+4.18**
with 0/400 placebo replicates reaching it, and a held-out matched estimate that came in *stronger*.
After dedup: A2_YW **4.18 → 0.70**, A1_EQ 3.22 → 1.15, A3_YHI 2.90 → 0.26; matched design +4.36 bp
(t 3.20) → +1.58 bp (t 1.17).

The fingerprint that caught it: splitting on *how many dividend records does this ex-date carry* put
the **entire** effect in the 8% multi-record subset at +62.4 bp — one median dividend yield, exactly
what a doubled rate manufactures.

**Six scripts read that cache**: `t7_dividend_dropoff.py`, `t11_merger_arb.py`, `t11_diagnostics.py`,
`inv3_event_calendar.py`, `newterr_xseq_panel.py`, **`basket_forward.py`**. The bug is
**one-directional (it inflates)**, so every cell that DIED on it stays dead — including T7 itself.
Only cells that **LIVED** need re-checking, and the live consumer that matters is
`basket_forward.py`, i.e. **L4 (ex-open dividend residual) inside BASKET1**. The dedupe fix with its
full explanation is in `scripts/trading_bot/exo0822c_panel.py`.

### 3.2 Three escalations against BASKET1 (all subtractive)

| # | Escalation | Evidence | Recommendation |
|---|---|---|---|
| **N1** | The **T13 SPY vol overlay already in `BASKET_FORWARD_FROZEN.json`** *costs* Sharpe on the combined market-neutral book | dSharpe held-out −0.031 / −0.215 / −0.189, full-window −0.050 / −0.313 / −0.308 across three panels. It never helps in any window on any panel. T13 was validated on a **long-SPY** book; the basket legs are dollar-neutral, so SPY vol is uninformative about them, and `wmax=1.0` makes it a one-sided drag | **Remove `vol_overlay` from the combined book** |
| **E1** | **L2 ETF-sibling RV should be DEMOTED TO UNSIZED** | All five pairs FAIL the ρ1 bounce gate (−0.503/−0.463/−0.457/−0.441/−0.491 vs −0.35). The frozen spec computes z from the 15:45 print and **fills at that same 15:45 print** (R3 shared-price failure). Move the fill to 15:50: GROSS +1.295 bp (t 17.95) → **+0.076 bp (t 1.05)** — 94% of gross edge gone in five minutes; NET +0.10 bp / SR 0.74 → **−1.12 bp / t −15.4 / SR −8.0**. Standalone net t was only +1.41 anyway | **Demote L2 to UNSIZED**; re-spec on a 15:50 fill before any resize |
| **E2** | **L3 DUALCLASS survives but at half size** | One-day-gap re-entry: 50.09 bp (t 6.54) → **23.73 bp (t 3.59)** at gap 1, 19.97 bp (t 3.07) at gap 2. Half the headline is same-close bounce. 15 of 16 pairs pass ρ1 (−0.13…−0.34); **BRK.A/BRK.B is −0.459** | **Size L3 on the gap-1 rung, not the headline; drop the BRK pair** |

E1 is the sharpest available demonstration that **the gross bar is necessary but not sufficient**: at
t 17.95 against a 2.97 bar, L2 clears any multiple-testing correction by a mile and is still entirely
fake. Note also that demoting a leg does **not** reduce `declared_trials_now` — the DSR bar stays.

### 3.3 LEDGER CORRECTION

**T7 is not ALIVE.** The rotation brief listed it so; `T7_RESULT.md` says it is **DEAD**
(label-permutation p = 0.213, DSR 0.076, all eight design configurations net-negative). T7 *is* the
ex-dividend drop-off study, so family A of this round is a **re-run of T7 on a different rail**
(MOC→MOO instead of close-to-close), not an invention, and is labelled so throughout. Combined with
E1, the standing ALIVE list should now read: **T3, dual-class RV (at gap-1 size), T12 CEF discount
(still the best edge), XS_GLSR_Z (data-dead), CRYPTO_LOWVOL (logging-only, borrow-walled)** — with
ETF-sibling RV moved to unsized pending a re-spec.

---

## 4. Mechanism, not just p-values

**Theme 1 — CEF.** Every formula above the bar is a re-parameterisation of the discount **LEVEL**
(group/category-MAD standardisation, level minus activists, level with both legs ETB, level split by
managed-distribution flag, level inside covered/eroding halves, level orthogonalised to erosion,
level inside the recent-cut cohort) and every one fails corr < 0.7 and/or alpha > 2. Every genuinely
**new** primitive is at \|gross t\| < 3: distribution run-rate change 1.38, distribution-stability
screen 0.47, NAV-erosion score 1.51, category-relative NAV momentum 2.47 (best new primitive, held
out −0.38 stressed), SC 13D activist cohort 0.77, SC TO tender 0.86, N-23C repurchase 0.65,
N-2/424B rights 1.42.

*The placebo earned its keep*: the **SC 13G (passive)** placebo cohort's held-out stressed alpha t is
0.89, sitting **inside** the activist cluster (0.74–1.17). A cohort someone filed a *passive* form on
is indistinguishable from one someone filed an *activist* form on. The honest reading is not that
activists don't matter in CEFs — the literature says they do — but that a **form-type flag is far too
coarse a label**: it cannot separate a campaign from a routine amendment, cannot see stake size or
demand, and the live-only CEFConnect universe deletes exactly the campaigns that ended in
liquidation.

**Theme 2 — overlay.** Four independent mechanisms, all dead for stated reasons:
1. **Correlation timing has nothing to time.** Mean off-diagonal \|ρ\| across the six legs = 0.067;
   the trailing diversification ratio has mean 0.994, sd 0.049. The quantity being steered does not
   move, and the overlay/inverse pairs are exactly antisymmetric — pure scale noise.
2. **Vol targeting: sign unstable.** OV_VT60 −0.025/−0.152/−0.043 vs its inverse −0.067/+0.070/+0.026;
   design and held-out disagree too.
3. **Risk parity is cost-blind.** OV_RP60 on P2 is **+1.557 GROSS and −0.427 NET** — a 2.0-Sharpe
   inversion, because trailing-vol RP loads onto exactly the legs (ETFRV, DUALCLASS) whose
   gross-to-net gap is largest.
4. **Calendar blackouts are sign flips.** OV_MONTHEND_OFF is +0.160/+0.142/+0.082 held out and
   −0.104/−0.080/−0.226 on design.

Two more decisive negatives worth keeping: **equal-DOLLAR is −0.968/−0.391/−1.099 held out vs
equal-RISK** (the design-vol scaling is load-bearing, keep it), and **OV_DROP_MOSTCORR120 is
−0.130/−0.308/−0.805** (never drop a leg on correlation). The observed max dSharpe is at or *below*
the null-max **mean** in two of three panels and the median overlay is negative in all three.

**Theme 3 — gap tether.** The genuinely new idea was **family C**: the published dividend turns the
ex-day gap into a free, daily, unbiased meter of unexpected demand on ~9 liquid names/day since 2016.
It carries nothing — design gross t 1.74/0.98/0.80/0.78/0.40/0.06, whole family below the placebo
*mean* of the max, five of six negative held out. The reason is arithmetic: **the residual is ~1.6 bp
against a ~200 bp daily sigma**, so even as pure order flow its predictive S/N is ~1%.

And the family-A finding is a cost wall, not a zero. A post-hoc sharpening of the pre-registered E1
control (mean of ~23.6 eligible non-event days in ±3…15 sessions) gives a matched control of
**−0.05 bp (t −0.16)** — the hedge is unbiased, so the event day is the whole effect: +1.58 bp design
(t 1.17), +4.71 bp held out (t 1.89). Round trip is 8.0 bp on the headline rail, 3.0 bp on the
measured M0 auction rail; every family-A cell breaks even between 0.2 and 2.4 bp/side, **below the
2.5 bp liquid-taker half-spread**. 22/23 candidates are design-positive and 14/23 positive in both
windows, but only 5/23 are net-positive held out at headline cost. That gap *is* the finding:
**the effect is not zero, it is smaller than the rail.** EXECUTION_COST_WALL from a fresh direction.

---

## 5. Method results worth more than the formulas

1. **VERIFY THE PUBLICATION — a corollary to lesson 4.** `E2_SHUFFLE_RATE`, which replaces the
   published tether with a *wrong* published rate, manufactures gross SR **+3.72 (t 9.83) on design
   and +3.74 (t 7.09) held out out of pure arithmetic**, while `E3_NOTETHER` shows the term the tether
   cancels is ~15× the alpha (gross SR −13.1). The residual inherits the feed's errors magnified by
   drop/alpha — which is precisely what the duplicated cache did to family A. *Free data prices a
   statistic not a claim* now needs: **and when the tether is published, verify the publication.**
2. **THREE HARNESS BUGS FOUND BY MECHANISM, BEFORE THE REVEAL** (theme 1), all of which generalise:
   * **Look-ahead.** `Y[k] = R[k] − RP[k]` is the distribution realised over the traded week, so any
     run-rate or NAV-erosion sum built from `Y[..k]` contains a slice of the traded return. Measured:
     NAV erosion xs corr +0.1132 (t 6.48) unshifted vs +0.0362 shifted — ~1.8 of t, pure inflation.
     **Escalation to the incumbent sweep:** DEEPMINE_CEFNAV's `yld52 = _roll_sum(Y,52)` carries the
     same contemporaneous week at 1/52 weight and is used as the Y03/Y04 mask. Much smaller, not zero,
     and it is the number Y04's non-replicating design alpha would have flattered.
   * **A 13-week-sum "distribution policy" detector was measuring EX-DATE TIMING**, not policy
     (median \|QoQ change\| 6.8%, 55% of fund-weeks flagged at ±5%, and the STABLE screen it fed was
     empty). Replaced with median-of-last-3-reconstructed-payments vs the 3 before → 2.45%.
   * **SIGN-FLIP IS NOT A MIRROR.** `book_from_score` ETB-screens only the SHORT leg, so negating a
     score gives a different, possibly non-executable book (one structure showed \|t\| 4.6 one way and
     0.4 the other). Worse, in NET terms a book and its sign flip differ by **twice the friction**, so
     a large negative net t on a sign-free formula measures cost, not signal. **Recommend a
     both-legs-ETB control in every future cross-sectional sweep in this repo** (verified exact
     mirror: B04 gross t −0.91 / B05 +0.91).
3. **A matched multi-control-day estimator has ~10× the power of a single-control-day placebo at no
   cost in bias.** Make it the standard E-family control.
4. **The dSharpe statistic needs its own null.** Comparing two ~0.99-correlated books, the analytic
   sqrt(2 ln N) in σ units is not directly usable; theme 2's 2,000-draw within-leg permutation
   rebuilding BASE *and* all K overlays per draw is the pattern to reuse.

---

## 6. Discipline record and disclosed imperfections

* Pre-registration for theme 3: `INVENT_0822C_gaptether_PREREGISTRATION.md`, sha256
  `987b283f548c54a12bd3a3ca935d99cdc8e80863a6c1eaac0d4e39892065ca65`, written before any design
  statistic; signs frozen to `_DESIGN.json` before the held-out window was read.
* Theme 1's `_DESIGN.json` carries the literal string `SEALED` in every held-out field, verified.
* **ρ1 gates run BEFORE any gross claim.** Theme 1: pooled ρ1(weekly discount change) median −0.199,
  p10 −0.319 → **passes**. Theme 3: ρ(ε, ex-day session) +0.029, ρ(ε, next open-to-open) +0.037,
  per-symbol ρ1 mean −0.008 / median −0.021, 6.0% of 349 symbols below −0.35 → **passes, and is
  structurally bounce-immune** (two separate auctions ~17.5 h apart, consecutive residuals a quarter
  apart). This is the programme's first anchored spread where bounce is absent **by construction**.
  Median event price $83.7 (1 tick = 1.19 bp), mean residual 4.9 ticks — not a tick artefact.
* No regime conditioning anywhere. Theme 3's subsets are structural cross-sectional size sorts;
  theme 2's overlays are zero-parameter or pre-declared fitted **controls carried inside N**.
* Placebos are signal/label-destroying by construction (fund-identity permutation preserving
  persistence and every screen; each event's returns replaced by the *same* symbol's hedged returns
  on a nearby non-event date). Never rotate-the-returns.
* **Disclosed imperfections.** (a) Theme 3's panel builder printed a full-sample per-event-class mean
  before the split — disclosed in prereg §6; it revealed only four class signs, all pre-registered
  `apriori` and unchangeable. (b) After the signs were frozen but **before** the duplication was
  found, the held-out matched estimator was read on the buggy panel (+9.39 bp, t 3.69); no sign or
  rule changed as a result, but 2023-01…2026-08 has now been read twice by this round and was already
  the programme's third pass over that calendar. (c) Alpaca survivorship biases family A toward
  surviving payers (so a null is the conservative read); `ca_covered` is 76% of panel symbols;
  `advusd` is a rank not a dollar figure so no capacity is quoted; foreign/ADR issues carry a
  mis-stated tether (gross vs withheld), 3–6% of events, reported separately, t<1 both windows;
  opening-cross non-fill risk is unmodelled and the opening cross is ~8× smaller than the closing
  cross, so the auction-rail row is an **upper bound**; tax makes it worse than T7 §6 already
  computed. (d) Theme 2's CEF distribution blackout used a month-end-week proxy because no cached
  feed carries CEF ex-distribution dates; a mid-month variant was not run — but every calendar
  blackout landed inside the null, so this is unlikely to change the verdict.

---

## 7. Standing leads (recorded as leads, not plans)

1. **13D/13E filing TEXT.** EDGAR full-text search is free, and the distinction that matters — a
   campaign demanding a tender or open-ending vs a routine amendment — is **in the document, not the
   form type**. This is a data-acquisition project (text pipeline), not another formula, and should
   not be attempted until someone commits to building it.
2. **Re-check every LIVE cell that consumed `t7_cache/corporate_actions_all.json.gz`** — dead cells
   stay dead (the bug only inflates); L4 inside BASKET1 is the one that matters.

---

## 8. Cumulative position

180 formulas across the CEF family (114 here + DEEPMINE_CEFNAV's 66) have now yielded exactly one leg
(**L5**) plus one guarded forward candidate (Y05_muni_eq_static_H1). This round added neither. L5 was
re-confirmed on the untouched window: **net 2.73 (t 4.10, +16.22 bp/wk)**, 2.10 under lag1 + p90
spread. It remains the only thing in that family worth owning.

Programme total after this round: **~1,430 distinct formulas**, bar sqrt(2 ln 2N) ≈ **3.99**.

---

## 9. Artifacts

**Reports**
`research/trading_bot/INVENT_0822C_cefdeep.md` / `.json` / `_DESIGN.json`
`research/trading_bot/INVENT_0822C_overlay.md` / `.json`
`research/trading_bot/INVENT_0822C_gaptether.md` / `.json` / `_PREREGISTRATION.md` / `_DESIGN.json` /
`_HOLDOUT.json` / `_NULLS.json` / `_MATCHED.json` / `_FOREIGN.json` / `_DIAG_design.json`

**Code**
`scripts/trading_bot/invent_0822c_cef.py`, `cef_edgar_fetch.py`
`scripts/trading_bot/inv0822c_panel.py`, `inv0822c_overlay.py`, `inv0822c_finalize.py`, `inv0822c_legdiag.py`
`scripts/trading_bot/exo0822c_{panel,sweep,nulls,diag,matched,foreign}.py`

**Data (new, cached, free)**
`research/data/cef0822c_cache/edgar_submissions.json.gz` — 360/360 tickers, 0 missing; 641 SC 13D,
1695 SC 13G, 374 SC TO, 355 N-23C, 540 N-2/424B in-window
`research/data/exo0822c/events.npz` — 15,966 events over 2,669 sessions

---

## 10. What the parent has to decide

Zero survivors means there is nothing to queue as a leg. The three items below are **spec changes to
an existing basket**, not additions, and all three shrink risk:

* **N1** — remove `vol_overlay` (T13-VOL-L60-T0.1-WMAX1.0) from the combined book.
* **E1** — demote **L2 ETF-sibling RV** to UNSIZED; it is a shared-price artefact at the 15:45 rail.
* **E2** — resize **L3 DUALCLASS** on the gap-1 rung (~23.7 bp, not 50.1 bp); drop BRK.A/BRK.B.

Plus one owner call outside the basket: **dedupe (or leave and patch at read time)
`research/data/t7_cache/corporate_actions_all.json.gz`**. The shared cache was deliberately not
modified by this round.
