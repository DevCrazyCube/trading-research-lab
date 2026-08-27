# INVENT_0822C — CEF structure beyond the discount level (3rd rotation, 2026-08-22)

**Status when §§1–5 were written: PRE-REGISTRATION.** No design number and no held-out number
existed. §6 onward is the result and is appended after.

---

## 1. What is already owned, and what this sweep is therefore forbidden to "discover"

Basket slot **L5 / `T12CEF`**: cross-sectional **discount-LEVEL** decile tilt over the ~353-fund
CEFConnect universe, ETB-short-screened, price > $5, dollar-neutral, 4-week hold, weekly
overlapping tranches. Held out 2024-03 → 2026-08 at ann Sharpe **2.35**, re-measured **2.73** in
`DEEPMINE_CEFNAV`.

`DEEPMINE_CEFNAV` (66 formulas, same data, same split) already tested and **closed** these
branches. None of them may be re-reported as a discovery here:

* discount **z-score / percentile / distance-from-own-mean** (52 w, 26 w, 13 w, and both
  orthogonalised to the level) — high design t, **all bid-ask bounce**, held-out stressed alpha
  −3 to −6;
* discount **change / momentum / acceleration** at 1, 4, 13, 26 w — same verdict, worse;
* **price-minus-NAV cumulative return spread** — same verdict;
* **NAV total-return momentum** (`S03`/`S04`) — negative both windows, the price does *not*
  under-react to NAV;
* **pure trailing-distribution-yield tilt** (`Y01`) — negative both windows;
* **term-fund / mandated-wind-up screen** (`X01`) — 0.02 design, 0.05 held;
* category / group / sponsor **median-demeaning** of the level, and the within-group book;
* the **low-PIT-yield half** conditioner (`Y04`) — stands alone but held-out alpha to L5 = 0.77,
  i.e. it is a subset of L5, not a new leg;
* `Y05_muni_eq_static_H1` (muni+equity-only level tilt) — the one survivor, carried as a
  **forward-test candidate with a guard**, unstable across held-out halves, 7-name short leg.

**This sweep asks a different question:** the CEF wrapper has *corporate-action and
distribution-policy* machinery that a discount level cannot see. Does any of it carry an edge
that L5 does not already own?

## 2. Two new primitives, and one new data source

### 2a. Point-in-time **dollar distribution per share** (from cached data only)

CEFConnect's price history is a **raw** close; Alpaca's bar is **distribution-adjusted**. Their
weekly return difference is the realised distribution yield
`Y[t] = (A[t+1]/A[t] − 1) − (P[t+1]/P[t] − 1)`, already built in `DEEPMINE_CEFNAV`. That sweep
used only its **trailing 52-week sum** (a yield *level*). Here it is converted to a
**dollar amount per share**, `dps[t] = Y[t] · P[t]`, and summed over 13 weeks to give a
price-independent **quarterly distribution run-rate**. Its 13-week-over-13-week change,

```
ddps[t] = dps13[t] / dps13[t−13] − 1
```

is a **point-in-time distribution CUT / RAISE detector**. Nothing in the repo has ever used it.
A CEF distribution cut is the single most-watched corporate event in this asset class and it is
observable, free, with no look-ahead, from two price series we already hold.

**Declared limits.** (i) The detector has a one-quarter lag by construction — it sees a cut
after a full quarter at the new rate, so it measures the *aftermath*, not the announcement.
(ii) Special year-end distributions inflate `dps13` and then deflate it; they are a genuine
source of false "cuts" and are **not** filtered, because any filter would need the snapshot's
distribution-type field, which is not point-in-time. (iii) Funds paying annually or
semi-annually (17 of 360) produce a meaningless `ddps`; they are dropped from every
distribution-event formula by a `DistributionFrequency ∈ {Monthly, Quarterly}` screen, which is
a static field but a structurally time-invariant one.

### 2b. Point-in-time **NAV erosion** (distribution coverage proxy)

`RV` (weekly NAV *price* return, distribution excluded) summed over 52 weeks is the fund's NAV
per share erosion. A fund that earns its distribution has erosion ≈ 0; one that funds it out of
capital grinds NAV down. Because market direction contaminates this for equity funds, it is
used **category-demeaned**. This is the standard "destructive return of capital" screen, built
PIT, and it is not in the 66.

### 2c. **SEC EDGAR filing events** (new, free, network-fetched once into a cache)

`scripts/trading_bot/cef_edgar_fetch.py` pulls `data.sec.gov/submissions/CIK*.json` for every
ticker in the universe and keeps the filing **form type + filing date** for the corporate-action
forms. From that, three event flags, each dated by its **EDGAR filing date** (public the day it
is filed, so an event on date *d* is actionable at the next weekly grid point ≥ *d*, and the
implementation-lag stress pushes it one further session):

| flag | forms | economic claim being tested |
|---|---|---|
| `ACTIVIST` | `SC 13D`, `SC 13D/A` | an activist accumulating a CEF forces a tender / open-ending / liquidation, and the discount narrows on the expectation |
| `TENDER` | `SC TO-I`, `SC 13E`, `SC 14D` | an issuer tender at ~98 % NAV is a mechanical discount cap |
| `RIGHTS` | `N-2`, `424B` shelf take-downs | a rights offering issues shares below NAV, is dilutive, and the discount widens then reverts |

**Declared limits.** `SC 13G` (passive) is kept separately and is expected to be *inert* — it is
carried as the sweep's own internal placebo, because an activist story that also "works" on
passive 13G filings is not an activist story. Form-type-only classification means `N-2` catches
every shelf registration, not only rights offerings; that branch is therefore reported as a
**weak-label** test and will not be promoted on its own. Survivorship: EDGAR is complete for
live filers, but the universe is still CEFConnect's live-today list, so funds whose activist
campaign ended in liquidation are **absent** — this biases the activist test toward the null in
the most interesting cases, and that direction is stated, not smoothed over.

## 3. The formula catalogue (structures, not a parameter grid)

* **E — distribution policy events:** fade the distribution run-rate change (post-cut long /
  post-raise short); the same restricted to the 8-week post-detection window; the level tilt
  restricted to funds with a **stable** distribution (no ±5 % change in 26 w); the level tilt
  restricted to funds that **recently cut**; the run-rate change **orthogonalised
  cross-sectionally to the discount level**.
* **N — NAV erosion / coverage:** long low-erosion (well-covered) funds; the level tilt inside
  the well-covered half; inside the eroding half; erosion orthogonalised to the level.
* **R — risk-normalised discount:** discount divided by its own trailing 52 w NAV volatility;
  discount standardised **within category by category MAD** (not merely demeaned — this is the
  branch `C01` did not test); discount relative to leverage ratio.
* **I — idiosyncratic NAV lead-lag:** the fund's NAV total return **minus its category mean**,
  cumulated 4 w and 13 w, long. (`S03`/`S04` tested *raw* NAV momentum and it was negative; the
  category-relative version has never been run and is the version the under-reaction story
  actually predicts.)
* **A — EDGAR corporate-action events:** long the `ACTIVIST` cohort vs the rest; the level tilt
  inside the activist cohort; `TENDER` cohort long; `RIGHTS` cohort fade; and the **13G
  placebo**.
* **G — managed-distribution / structural statics:** level tilt inside `IsManagedDistribution`
  funds and inside the complement.

Every structure is run at **H = 4** and **H = 1**.

## 4. Costs, screens, windows — identical to `DEEPMINE_CEFNAV`, fixed before the run

Measured **11.53 bp** CEF half-spread on both legs of realised turnover; SEC §31 0.278 bp on
sale notional; borrow at the **realised 200 bp/yr** short rate on the short half; short leg
screened to Alpaca `easy_to_borrow`; price > $5. Design **2021-08-20 → 2024-02-23**, held out
**2024-03-01 → 2026-08-07**.

**Stress ladder, applied to every formula on both windows:** one-trading-day implementation lag
(CEFConnect publishes NAV after the close) and the **p90** half-spread 27.25 bp, because a book
that holds the extremes of a 360-fund universe does not pay the median spread. `DEEPMINE_CEFNAV`
proved this ladder is the difference between a Sharpe-5 mirage and a loss.

## 5. Bars and the decision rule — fixed now

1. **ρ1 bounce gate.** ρ1 of the weekly change in the discount is computed pooled and reported
   *before* anything else. If it is below ≈ −0.35 the whole spread family is closing-print
   bounce and no gross number in it may be believed. Reported either way.
2. **Analytic noise bar** `sqrt(2 ln 2N)` over the N scored formulas.
3. **Size-matched placebo null.** The analytic bar understates for overlapping books. The
   placebo is a **fund-identity permutation**: the score matrix's columns are permuted by a
   random fixed permutation of the funds, held constant through time, so the signal's
   persistence, the book size, the turnover and every screen are preserved exactly and only the
   fund↔return link is destroyed. Run over a representative spread of structures; the empirical
   SD of the null t is what scales the expected maximum.
4. **Decision rule:** a formula is put forward only if — on the **design window** —
   design t > the placebo-scaled bar, **and** |corr| to L5 < 0.7, **and** two-factor
   alpha-to-L5 t > 2.0, **and** it survives the lag1+p90 stress. The held-out block then
   confirms or kills; whichever it does is what gets written down. As in `DEEPMINE_CEFNAV`, the
   held-out block is **not virgin at the family level**, so the decisive held-out statistic is
   the **stressed two-factor alpha to L5**, not the raw held-out Sharpe.

Staging: `design` writes every held-out field as the literal string `"SEALED"`; selection is
made against that file; only then is `reveal` run.

---

## 6. Two bugs found in my own harness before the reveal, and both fixed

Written before `reveal` was run. Both were found by mechanism, not by a number I disliked.

**6a. Look-ahead in the new PIT primitives.** `Y[k] = R[k] − RP[k]` is the distribution realised
over week `k → k+1` — it is **contemporaneous with the very return the book at `k` earns**.
Building a distribution run-rate or a NAV-erosion sum out of `Y[..k]` / `RV[..k]` puts a slice of
the traded return inside the signal. Measured leak, mean per-date cross-sectional correlation of
the signal at `k` with the traded return at `k`:

| primitive | un-shifted | shifted one week |
|---|---|---|
| distribution run-rate change | −0.0071 (t −1.00) | −0.0122 (t −1.84) |
| **52 w NAV erosion** | **+0.1132 (t 6.48)** | +0.0362 (t 2.03) |

The erosion leak was large. Every distribution and NAV primitive is now built from a
one-week-shifted series. The un-shifted run inflated the distribution-event book by ~1.8 of t
(`E03` went from |t| 4.70 to 2.87) and this fix was applied **before** any selection.

*Note for the record on the incumbent sweep:* `DEEPMINE_CEFNAV`'s `yld52 = _roll_sum(Y, 52)`
carries the same contemporaneous week at 1/52 weight, and it is used as a **mask** (`Y03`/`Y04`),
not a score. The effect is far smaller than the one measured here but it is not zero, and
`Y04`'s design-window alpha — which did not replicate — is the number it would have flattered.

**6b. The distribution detector was measuring ex-date timing, not distribution policy.** A
13-week *sum* of the reconstructed distribution swings ~33 % whenever a monthly payer's ex-date
crosses a window boundary. Measured median |quarter-over-quarter change| was **6.8 %**, with 55 %
of fund-weeks flagged as a ±5 % "change" — i.e. the detector was almost pure timing noise, and
the `STABLE` screen it fed was empty (formula `E04` produced no book at all). Replaced with a
**median-of-the-last-3-reconstructed-payments vs the 3 before** comparison, which is immune to
ex-date timing. Median |change| falls to **2.45 %**; ±5 % flags 29 % of fund-weeks, ±10 % flags
14 %. Both thresholds are run as separate formulas so the threshold is reported, not tuned.

**6c. A third construction fault, found the same way.** `book_from_score` screens only the
**short** leg to easy-to-borrow, so negating a score does **not** produce a mirror book, and a
sign-free formula could show |t| 4.6 in one direction and 0.4 in the other. Worse, in *net*
terms a book and its sign flip differ by **twice the friction** — so a large negative net t on a
sign-free formula is a measurement of cost, not of signal. Two fixes, both before selection:

* a `B`-family that restricts the **whole universe** to ETB on both legs, making the book fully
  executable and the sign flip an exact mirror (verified: `B04` gross t −0.91, `B05` +0.91); and
* **the pooled multiple-testing screen is applied to GROSS t**, not net t, exactly as the
  programme's standing rule says. The net and stressed numbers are then charged on top.

## 7. Design-window result, and the selection — written before the reveal

`INVENT_0822C_cefdeep_DESIGN.json`, every held-out field the literal string `"SEALED"`.
**N = 114 scored formulas** (the two-sided runs of the sign-free families count individually;
4 of the 114 are exact duplicates arising from a mirror of an already-mirrored structure, so 110
are distinct). Design window 2021-08-20 → 2024-02-23.

### 7a. Gates and bars

* **ρ1 bounce gate: PASSED.** ρ1 of the weekly change in the discount, pooled over 337 funds:
  median **−0.199**, mean −0.194, p10 −0.319, p90 −0.071. All above the −0.35 kill line, so
  closing-print bounce is **not** manufacturing gross significance in the discount itself.
  (`DEEPMINE_CEFNAV`'s short-horizon carnage was the *NAV-publication lag* plus the p90 spread,
  not ρ1 — the gate and the lag are different failures and this sweep separates them.)
* **Analytic bar** `sqrt(2 ln 2N)` = **3.295**.
* **Size-matched placebo**, 600 fund-identity permutations across 6 representative structures:
  SD of the null **gross** t = **0.845**, SD of the null net t = 1.084, SD of the null
  alpha t = 0.85. The null gross t is *under*-dispersed relative to N(0,1), so the placebo bar
  (2.784) is **lower** than the analytic one; the **larger** of the two, **3.295**, is used.
  The placebo's null *mean* net t is −1.25 to −2.79 depending on structure — that is the
  friction drag, and it is the reason a net-t ranking is not a significance ranking.

### 7b. The result: **NO formula survives the pre-registered design rule. Zero.**

Every formula with |gross t| above the bar, and why each dies:

| formula | gross t | corr L5 | α t | stressed Sh | stressed α t | verdict |
|---|---|---|---|---|---|---|
| `B03_disc_grp_mad_etbboth_H1` | 7.48 | **0.75** | 3.23 | 1.86 | 0.83 | corr ≥ 0.70 — L5 in a hat |
| `R03_disc_grp_mad_H1` | 7.25 | **0.75** | 2.79 | 1.84 | 0.54 | corr ≥ 0.70 |
| `A03_level_ex_activist_H1` | 6.63 | **0.92** | 1.74 | 2.13 | 0.98 | corr ≥ 0.70, α ≤ 2 |
| `B00_L5_level_etbboth_H1` | 5.92 | **0.89** | 1.85 | 2.03 | 1.10 | corr ≥ 0.70, α ≤ 2 |
| `R02_disc_cat_mad_H1` | 5.06 | 0.64 | **0.33** | 0.39 | **−1.94** | α ≤ 2, stressed α < 0 |
| `G02_level_in_nonmdp_H1` | 4.96 | 0.83 | 0.01 | 1.33 | −0.91 | all three |
| `G01_level_in_mdp_H1` | 4.39 | 0.55 | **0.59** | 1.66 | 0.86 | α ≤ 2 |
| `N04_level_resid_erosion_H1` | 3.97 | 0.81 | 0.34 | 1.17 | −0.03 | all three |
| `E05_level_in_cut_H1` | 3.75 | 0.46 | −0.24 | **−0.20** | −2.03 | α ≤ 2, dies under stress |
| `N03_level_in_eroding_H1` | 3.42 | 0.78 | 0.31 | 0.51 | −0.68 | all three |
| `N02_level_in_covered_H1` | 3.01 | 0.54 | 0.09 | 0.11 | −0.99 | α ≤ 2, stressed α < 0 |

**Every single one of them is a re-parameterisation of the discount level.** Not one is a new
primitive. The list is: the level standardised by group/category dispersion, the level with the
activist names removed, the level with both legs ETB, the level split by managed-distribution
flag, the level inside the eroding/covered halves, the level orthogonalised to erosion, the
level inside the recent-cut cohort. The incumbent already owns all of it.

### 7c. Every genuinely new primitive is at |gross t| < 3 — most are under 1.5

| new primitive | best |gross t| across its variants | reading |
|---|---|---|---|
| PIT distribution run-rate change (`E01`,`E03`,`E08`,`B04`/`B05`) | **1.38** | no distribution-cut/raise effect at all |
| distribution-stability screen (`E04`) | 0.47 | nothing |
| PIT NAV erosion as a *score* (`N01`,`B06`/`B07`) | 1.51 | coverage does not price |
| category-relative NAV momentum (`I01`,`B01`/`B02`) | **2.47** | best of the new primitives, still sub-bar |
| SC 13D activist cohort (`A01`,`B08`) | 0.08 | nothing |
| SC TO issuer-tender cohort (`A05`) | 0.86 | nothing |
| N-23C repurchase-notice cohort (`A08`) | 0.65 | nothing |
| N-2 / 424B rights-offering cohort (`A06`, weak label) | 1.42 | nothing |
| **SC 13G placebo cohort (`B09`)** | **0.72** | correctly inert — the placebo behaves |

### 7d. The one thing worth carrying to the holdout, named in advance, and what it is not

`B03_disc_grp_mad_etbboth_H1` / `R03_disc_grp_mad_H1` — **the discount standardised within its
broad group by the group's cross-sectional MAD**, rather than merely demeaned by the group
median. Gross t 7.48, net design Sharpe 3.94, **stressed 1.86 against the incumbent's own
stressed 1.49** on the identical ladder, turnover 0.41/wk.

It **fails the pre-registered rule** on corr = 0.75 and it is *not* put forward as a new leg.
It is put forward as an **incumbent-improvement candidate**: same economic claim as L5, better
normalisation. The claim to be tested out of sample is narrow and stated now: *does the
MAD-standardised level beat the raw level on the stressed held-out block?* — not *is it a new
edge*, which the corr and the stressed α t of 0.83 already answer with no.

**No formula is promoted, no rule is relaxed.** The reveal below is confirmation, not selection.

---

## 8. The reveal — the design verdict is confirmed, and the confirmation is unusually clean

`INVENT_0822C_cefdeep.json`, held out 2024-03-01 → 2026-08-07 (114 weeks).

### 8a. The incumbent, re-measured, is fine

| | design | held out |
|---|---|---|
| L5 net Sharpe | 2.16 (t 3.35) | **2.73** (t 4.10, +16.22 bp/wk) |
| L5 under lag1 + p90 | 1.49 | **2.10** |

### 8b. The single decisive number

**Across all 114 formulas, the highest held-out stressed two-factor alpha t to L5 is 1.17.**
The size-matched alpha bar is 3.35; even a naive bar of 2.0 is not reached by anything. There is
no candidate here, and — unlike `DEEPMINE_CEFNAV`, where peeking at the holdout would have
promoted `C02_cat_within` at α t 3.77 — **peeking would have found nothing either.** The eight
best held-out stressed alphas in the whole sweep:

| formula | design gross t | corr L5 | **held stressed α t** | held stressed Sh |
|---|---|---|---|---|
| `A01_activist_long_H4` | 0.77 | 0.20 | 1.17 | 0.05 |
| `N04_level_resid_erosion_H4` | 2.25 | 0.88 | 0.98 | 2.18 |
| `B08_activist_long_etbboth_H4` | −0.08 | 0.04 | 0.94 | 0.49 |
| **`B09_placebo13g_etbboth_H4` (the placebo)** | 0.72 | 0.08 | **0.89** | 0.13 |
| `B08_activist_long_etbboth_H1` | −0.01 | 0.08 | 0.86 | 0.17 |
| `A02_level_in_activist_H4` | 0.47 | −0.01 | 0.74 | 0.33 |
| `R03_disc_grp_mad_H4` | 4.46 | 0.82 | 0.64 | 1.65 |

The **passive-13G placebo (0.89) sits inside the activist cluster (0.74–1.17)**. That is the
cleanest possible statement that the SC 13D activist signal is not a signal: a cohort of funds
someone filed a *passive* ownership form on performs indistinguishably from a cohort someone
filed an *activist* form on. Both are ≈ 0.

### 8c. The named pre-reveal candidate failed the narrow question it was given

`B03/R03` — the discount **standardised by the group MAD** rather than demeaned by the group
median. The question fixed before the reveal was *"does it beat the raw level on the stressed
held-out block?"*

| | design stressed | **held-out stressed** | held stressed α t |
|---|---|---|---|
| `B03_disc_grp_mad_etbboth_H1` | 1.86 | **1.22** | −0.70 |
| `R03_disc_grp_mad_H1` | 1.84 | **1.17** | −0.10 |
| `B03_disc_grp_mad_etbboth_H4` | 1.50 | 1.79 | 0.44 |
| `R03_disc_grp_mad_H4` | 1.55 | 1.65 | 0.64 |
| **incumbent L5, raw level** | **1.49** | **2.10** | — |

**No.** The MAD standardisation beat the raw level on the design window (1.86 vs 1.49) and
**lost to it out of sample** (1.22 vs 2.10) at every horizon. The dispersion normalisation is a
design-window artefact. The incumbent's plain, unstandardised discount level stays as it is.

### 8d. Every new primitive, out of sample

| primitive | best design gross t | held-out net Sh | held-out stressed Sh | verdict |
|---|---|---|---|---|
| distribution CUT / RAISE run-rate change | 1.38 | −0.65 … −1.66 | −1.20 … −2.30 | **dead** |
| distribution-stability screen | 0.47 | 1.56 | 1.07 | dead (α t 0.56, it is L5) |
| NAV-erosion / distribution-coverage score | 1.51 | 0.28 | 0.02 | **dead** |
| category-relative NAV momentum | 2.47 | 0.42 | −0.38 | **dead** |
| SC 13D activist cohort | 0.77 | 0.65 | 0.49 | **dead**, and inseparable from the 13G placebo |
| SC TO issuer-tender cohort | 0.86 | 0.10 | −0.06 | **dead** |
| N-23C repurchase-notice cohort | 0.65 | −0.48 | −0.59 | **dead** |
| N-2 / 424B rights-offering cohort (weak label) | 1.42 | 0.50 | −0.18 | **dead** |
| SC 13G placebo | 0.72 | 0.31 | 0.13 | correctly inert |

### 8e. Verdict

**The theme is noise. Zero survivors, zero diversifiers, and nothing that a peek would have
rescued.** Specifically:

1. **The CEF corporate-action layer does not price on free EDGAR form-type data.** Activist
   13Ds, issuer tenders, repurchase notices and rights offerings are all ≈ 0 both windows, and
   the activist cohort is statistically indistinguishable from the passive-13G placebo. The
   honest reading is not "activists don't matter in CEFs" — the published literature says they
   do — but that **a form-type flag is far too coarse a label**: it cannot separate a campaign
   from a routine amendment, it cannot see the stake size or the demand, and the live-only
   universe deletes exactly the campaigns that ended in liquidation. Fixing that needs the
   filing *text*, not the filing *type*.
2. **The distribution cut/raise channel is not reachable from reconstructed distributions.**
   Even after replacing the timing-noise-dominated window sum with a per-payment median, the
   detector's median |change| is 2.45 % against a real distribution-change rate an order of
   magnitude rarer. The signal-to-label ratio is too low, the detection lags the announcement by
   three payments, and the result is a flat zero in both windows and both signs.
3. **Distribution coverage / NAV erosion does not price** as a score, and as a conditioner it
   just re-cuts L5.
4. **Category-relative NAV momentum is the best of the new primitives and is still sub-bar**
   (design gross t 2.47 vs a 3.295 bar) and negative out of sample. `S03`/`S04`'s verdict —
   the price does not under-react to NAV — survives being made idiosyncratic.
5. **Everything that looked significant is the incumbent re-parameterised**, and the best of
   those re-parameterisations lost to the plain incumbent out of sample.
6. **L5 is re-confirmed** at held-out 2.73 net / 2.10 stressed, and it remains the only thing
   in this family worth owning.

### 8f. What this closes, and the one door it leaves open

Closed on free data: CEF distribution-policy events, NAV-erosion coverage, EDGAR form-type
corporate actions, dispersion-normalised discounts, category-relative NAV lead-lag, and the
managed-distribution / leverage / activist structural splits. Together with `DEEPMINE_CEFNAV`'s
66, **180 formulas across the CEF family have now produced exactly one leg (L5) plus one
guarded forward candidate (`Y05`)**, and this round produced neither.

The one door that is genuinely open rather than merely untried: **the 13D/13E filing TEXT**.
EDGAR full-text search is free, and the distinction that matters — a campaign demanding a tender
or open-ending, versus a routine amendment — is in the document, not the form type. That is a
different data-acquisition problem, not another formula, and it should not be attempted until
someone is willing to build the text pipeline. It is recorded here as a lead, not a plan.
