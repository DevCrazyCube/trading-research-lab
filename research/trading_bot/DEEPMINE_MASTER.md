# DEEPMINE_MASTER — cross-family synthesis of the deep-mine of the productive families

**Date:** 2026-08-20
**Scope:** five parallel deep-mine sweeps inside families already believed to contain real edges
(identical-claim relative value; overnight equity). **358 formulas** tested in total.
**Sources:** `DEEPMINE_crosslist.{md,json}`, `DEEPMINE_CEFNAV.{md,json}`,
`DEEPMINE_etf_structural_rv.{md,json}`, `DEEPMINE_holdco_corpstructure.{md,json}`,
`DEEPMINE_overnight_event.{md,json}` (all under `/home/anont/meme/research/trading_bot/`).

---

## 0. Headline

**358 formulas. One survivor. Four of five sub-families are noise as tradable claims.**

The single formula that clears the pooled multiple-testing bar on the design window, holds a
positive net number out of sample under honest stress, AND is not already owned by the basket is
`Y05_muni_eq_static_H1` — a closed-end-fund discount-LEVEL decile tilt restricted to MUNI + EQUITY
funds, one-week hold. It is a **forward-test candidate with a guard, not a proven edge**, and its
margin over the second-round noise bar is 1.06x.

Everything else — cross-listing/ADR RV (30), ETF structural RV beyond same-index siblings (51),
holdco/corporate-structure RV (130), overnight-equity event anomalies (81) — is noise, or is a
restatement of a leg the basket already holds. That is 328 of 358 formulas returning nothing, in
families that were selected *because* they had already produced survivors. The deep-mine hypothesis
("dig where you already struck") is **substantially disconfirmed**: the productive families were
productive at exactly one or two points each, not across a rich neighbourhood.

---

## 1. Cross-family multiple-testing correction on the pooled 358

### 1.1 The bar

Each formula's sign was free — a negative result is traded the other way round — so the search is
two-sided and the correct count is 2N:

| quantity | value |
|---|---|
| N formulas tested (pooled) | **358** |
| one-sided expected max, `sqrt(2 ln N)` | **3.429 SE** |
| **two-sided expected max, `sqrt(2 ln 2N)`** | **3.626 SE** ← *headline pooled noise bar* |
| expected false positives at that bar over 358 tries | **0.103** |

**Use 3.626 SE.** Every number below is measured against it.

### 1.2 Translated into annualised Sharpe, per family (design spans differ)

One SE of an annualised Sharpe over a span of `y` years is `1/sqrt(y)`:

| family | design span | SE of ann. Sharpe | pooled bar in Sharpe units |
|---|---|---|---|
| Cross-listing / ADR | 6.00 y | 0.408 | **1.480** |
| Holdco / corp-structure | 6.00 y | 0.408 | **1.480** |
| Overnight-equity event | 6.00 y | 0.408 | **1.480** |
| ETF structural RV | 3.99 y | 0.501 | **1.815** |
| CEF NAV-discount (modal, 125 wk) | 2.40 y | 0.645 | **2.339** |
| CEF NAV-discount (52-wk warm-up, 73 wk) | 1.40 y | 0.844 | **3.060** |

Each family's own bar was *lower* than this (their N was smaller). Pooling raises the bar by
0.5–0.9 SE. **The pooling changes one verdict and confirms four.**

### 1.3 Is the naive `sqrt(2 ln 2N)` the right number? Both corrections were measured, not assumed

Two effects push in opposite directions and both were quantified inside the sweeps:

* **Correlation among tries pushes the true bar DOWN.** The 358 are not independent. The ETF
  family measured mean pairwise correlation 0.13 across its 51 configs (~11.6 effective independent
  bets). T26 previously found that 51 restatements of *one* feature pushed the empirical bar *below*
  the analytic one.
* **Fat tails and autocorrelation in daily/weekly P&L push it UP.** The ETF family's stationary
  block bootstrap (block=5d, 800 resamples, shared day-indices so cross-config correlation is
  preserved) put the p95 of max-Sharpe at **1.61 against a naive 1.404 — a 1.15x inflation.** The
  overnight-event family's within-day permutation null (400 replicates, one shared permutation
  across all 53 configs) put p95 at **3.27 against a naive 3.19 — 1.03x.**

So the empirically-calibrated pooled bar sits at roughly **3.74–4.17 SE** (3.626 × 1.03–1.15).
This matters, and the report is stated against the *conservative* end: the one survivor's design
t of **4.98 clears even 4.17**. No verdict in this document depends on the choice within that range.

### 1.4 What the pooled correction actually changed

One formula moves from "clears" to "fails" purely on the pooled correction:

> **`N07_ann_p10_fade`** (overnight-event family) — design net Sharpe 3.79, **t = 3.537**. It cleared
> its own family bar (3.27, empirical) and was the family's only *structurally new* clearer. Against
> the pooled bar of 3.626 it **fails**. It then died out of sample anyway (held-out net Sharpe
> −0.51, residual alpha over T3 t = −0.99). **The pooled correction would have rejected it
> pre-emptively, and the holdout agreed.** That is the correction earning its keep on a live case,
> not in the abstract.

### 1.5 Full pooled distribution

Because the five sweeps report on different scales (some net-Sharpe, one gross because net is
catastrophically negative), the distributions are given per family and *not* silently merged:

| family | N | design distribution | # net-positive on design | # clearing pooled bar 3.626 |
|---|---:|---|---:|---:|
| Cross-listing / ADR | 30 | **gross** Sharpe: max 0.888, then 0.698, 0.653, rest < 0.6. Net: best **−10.02** | **0 / 30** | **0** |
| CEF NAV-discount | 66 | net design t: min −1.00, p25 2.05, **med 3.10**, p75 3.88, max 7.18 | 61 / 66 | **23** |
| ETF structural RV | 51 | net Sharpe: max **−1.00**, p90 −1.61, p75 −5.71, med −13.93, p25 −27.31, min −66.27. *Gross*: max +2.93, med +0.63, 42/51 positive | **0 / 51** | **0** (net) |
| Holdco / corp-structure | 130 | design t: min −2.75, p10 −1.28, p25 −0.60, **med +0.12**, p75 +0.99, p90 +2.01, max **2.35** | 68 / 130 | **0** |
| Overnight-equity event | 81 (53 scored) | net Sharpe (tradeable dir.): min −1.55, p25 −0.47, **med +0.08**, p90 +2.20, max +4.71. Max \|t\| = 5.43 | 32 / 53 | **2** |
| **pooled** | **358** | — | — | **25** |

Read this table carefully, because it says two different things:

* **Three families are centred on zero and stop there.** Holdco (median t +0.12, max 2.35 over 130
  tries against a 3.12 own-family bar) and overnight-event (median +0.08) are textbook nulls. The
  cross-listing family is worse than a null — it is negative before a single basis point of cost.
* **Two families contain real structure that is not tradable.** ETF structural RV is **gross**-positive
  in 42 of 51 formulas with a best gross Sharpe of 2.93 against a before-cost bootstrap p95 of 1.48 —
  it genuinely beats its own bar *before frictions*, then goes 0-for-51 after them. CEF has 23 of 66
  clearing even the pooled bar when a null predicts 0.10.
* **The 25 clearers are not 25 discoveries.** 23 are one family, mutually correlated and mostly
  correlated with the incumbent leg L5 (design corr to L5 up to 0.96). The other 2 are the overnight-
  event family's `T03_p10_annnight_excl` and `T01_p10_quiet`, which correlate **+0.985 and +0.943**
  with the T3 book at beta ≈ 1.0 — they *are* L1, rediscovered. **Effective independent discoveries
  among the 25: one.**

---

## 2. The shortlist — formulas beating the pooled bar with a positive held-out net

The gauntlet, applied in order and never in reverse:

```
358 formulas tested
 └─ 25  clear the pooled design bar (t ≥ 3.626)          [null expects 0.10]
     └─ 12  also positive out of sample, net of realistic costs
         └─  1  also carries positive RESIDUAL ALPHA over what BASKET1 already owns
```

### 2.1 The one real candidate

| | |
|---|---|
| **key** | `Y05_muni_eq_static_H1` |
| **family** | CEF NAV-discount RV |
| **design (2021-08-20 … 2024-02-23, 125 wk)** | net t **4.98**, ann Sharpe **3.213** — clears pooled 3.626 by **1.37x**, and clears the fat-tail-inflated 4.17 too |
| **held out (2024-03-01 … 2026-08-07, 114 wk)** | **+33.26 bp/wk net**, ann Sharpe 3.07, t 4.54 at the measured 11.53 bp half-spread |
| **held out, honestly stressed** | 1 trading-day implementation lag + p90 (27.25 bp) half-spread both legs + 200 bp/yr realised borrow on the ETB-screened short: **+18.58 bp/wk**, ann Sharpe **1.95**, t 2.89 |
| **decisive statistic — stressed 2-factor alpha to incumbent L5** | **t = 2.93** vs the pre-registered second-round bar of 2.751 → **1.06x** |
| **held-out beta / corr to L5** | **−0.003 / −0.10** |
| **block bootstrap (8-wk blocks, 5000 draws) on stressed alpha** | P(>0) = **0.999**, +20.2 bp/wk, 95% CI **[+7.6, +32.7]** |

### 2.2 Honest sensitivity on that 1.06x — the number this document is least comfortable with

The second-round bar of 2.751 = `sqrt(2 ln 44)` charges the **22 formulas that passed the
pre-registered design rule** and were carried into the holdout. That is defensible: the shortlist of
22 was written to disk before the holdout was read, and the four other families carried **zero**
formulas into an alpha test, so nothing else pools in at this stage.

But if you instead charge **all 66** alphas that exist in the artefact, the bar is
`sqrt(2 ln 132) = 3.125` and **Y05 fails it at 0.94x.**

Both readings are stated. The pre-registered one is the one the programme committed to in advance
and is the one used here; the conservative one is the reason `Y05` is sized as a **satellite** and
not as a full leg. Anyone reading this document as a promotion memo should read the conservative
number instead.

### 2.3 The near-misses, recorded and claimed as nothing

Each of these would be a "discovery" under a sloppier protocol. None is promoted.

| formula | why it looks good | why it is rejected |
|---|---|---|
| `T03_p10_annnight_excl`, `T01_p10_quiet` (overnight) | design t 5.43 / 4.92 — clear the pooled bar outright | corr to the T3 book **0.985 / 0.943**, beta ≈ 1.0, held-out residual alpha over T3 t = **−0.41 / +0.43**. They are **L1**. |
| `Z03_z13_H1` (CEF) | **design t 7.18, ann Sharpe 4.90** — the strongest thing in all 358 | Closing-print **bid-ask bounce**. Add a 1-day implementation lag (CEFConnect publishes NAV *after* the close) and the p90 spread and it goes to **held-out stressed t −6.58**, alpha −5.74. Same collapse for `M01` (−7.69), `M05` (−7.69), `M02` (−5.09), `S01` (−5.08), `Z05` (−3.93), `Z01` (−3.40). |
| `X02_levered_H1`, `C03_grp_demean_H1`, `Y02_level_resid_yield_H1` (CEF) | clear pooled design bar (t 5.09 / 5.06 / 3.71) **and** are held-out-positive under stress (t 2.16 / 2.37 / 2.23) | **collinear with L5**: design corr 0.92 / 0.88 / 0.77; stressed held-out alpha t **0.69 / 0.23 / 0.39**. Already owned. |
| `Y04_level_in_loyield_H4` (CEF) | the **pre-committed primary**; held-out standalone Sharpe 1.77 | held-out alpha to L5 t = **0.77** (2-factor 1.05, stressed 0.92) against a design alpha t of 2.90. A **subset** of L5 and *worse* than L5 (2.73) out of sample. Reported as a failure, not quietly swapped. |
| `C02_cat_within_H1/H4` (CEF) | best held-out alpha after Y05 (**3.87 / 2.28** stressed) | design t **2.20 / 1.98**, below every bar. Selecting them is held-out mining. Explicitly recorded as *what would have been picked if I had peeked*, and claimed as nothing. |
| `M03_spy_fomc_eve` (overnight) | held out **+18.87 bp/night, Sharpe 6.55, t 2.51**, survives 2x stress | design t **2.06**, nowhere near the bar; **placebo lags k=2 and k=5 give design Sharpes +4.57 and +4.58**, i.e. 3 of 10 arbitrary lags beat +4.5 on 48 nights; it is the published Lucca-Moench drift, not an invention; ~8 nights/yr. |
| `B15` (cross-listing) | the family's only held-out-positive formula, +9.35 bp | design was **−39 bp, t −1.17**. A coin flip that landed heads. |
| `L07_rebal_flow_fade_nextopen` (ETF) | held-out **gross** +1.63 | net −0.19 held out and −1.00 on design. Positive only at an arithmetic tick-floor fill no account can achieve. |
| `H ret/L60/K2.5` (holdco) | held-out t **3.21**, above the bar | group H produced the **worst** design t-stats in the entire sweep (−2.75, −2.24, −1.82). Selecting it is selecting on held-out data. |

**Nine ways to have found a fake edge in these 358 formulas, all declined.**

---

## 3. Diversification assessment vs BASKET1

Current BASKET1 (`BASKET_FORWARD_FROZEN.json`, frozen 2026-08-20T16:20Z, prereg sha256
`2e72ac08…`): **L1 T3** overnight cross-sectional pressure reversal · **L2 ETFRV** intraday
same-index ETF sibling RV · **L3 DUALCLASS** multi-day dual-class voting-premium z-fade ·
**L4 T7** ex-dividend ex-open residual · **L5 T12CEF** CEF discount-LEVEL tilt, H=4 ·
**L6 ORB** intraday opening-range breakout.

### 3.1 `Y05_muni_eq_static_H1` — **NEW DIVERSIFIER (in return space), with a stated structural caveat**

| vs leg | overlap | verdict |
|---|---|---|
| L1 T3 | different instrument (CEF vs common), different horizon (1 wk vs overnight), different rail | orthogonal |
| L2 ETFRV | different instrument, intraday vs weekly | orthogonal |
| L3 DUALCLASS | different instrument | orthogonal |
| L4 T7 | CEFs distribute 7–8%/yr, but this is a decile-tilt book on distribution-adjusted returns, not an ex-date event trade | negligible overlap |
| **L5 T12CEF** | **same asset class, same NAV feed, same broker rail** — but **held-out corr −0.10, beta −0.003**; different universe (MUNI+EQUITY only, taxable-credit excluded), different horizon (H=1 weekly vs H=4 overlapping tranches) | **statistically diversifying, structurally adjacent** |
| L6 ORB | different instrument, intraday directional | orthogonal |

**The honest tension.** The return series is genuinely uncorrelated with L5 out of sample
(−0.10) — that is measured, not assumed, and it is why the leg is worth standing up. But
diversification in return space is not diversification in *failure* space. L5 and Y05 share the
CEFConnect NAV pipeline, the CEF closing-auction liquidity regime, the same ~360-fund live-only
universe, and the same broker's easy-to-borrow list. A CEF-wide discount-regime shift, a NAV-feed
outage, or a borrow-availability change hits both. Note also that the design-window correlation was
**0.585**, not −0.10 — the orthogonality claim rests entirely on the held-out window and could
revert.

**Consequence for sizing:** treat L5 + L7 as **one class with a combined cap**, not as two
independent legs (§4.5).

### 3.2 Everything else — no new legs

* **Cross-listing / ADR (30):** nothing survived. Contributes a **boundary condition** instead, and
  it is a sharp one: L3 DUALCLASS works because both closes come off **one tape at one instant**.
  The moment a second venue, a second currency or a second timestamp enters the spread, measurement
  error swamps the effect on free daily data. Measured: lag-1 autocorrelation of the daily spread
  *change* is −0.44 to −0.52 in every bloc (theory says −0.50 for pure iid measurement error). Canada
  — TSX/NYSE, same minute, fully fungible — still shows 49 bp/day of "premium" motion at ρ₁ −0.49.
  **No liquidity screen rescues it. Do not retry this family on daily closes.**
* **ETF structural RV (51):** no leg. The gross signal is real (best gross Sharpe 2.93 vs a
  before-cost p95 of 1.48) and dies entirely on frictions: a unit-gross book here has 1.2–2.0%
  annualised vol, so gross edge of 1–5 bp/day meets a 3–137 bp/day friction bill. **45 of 51 lose at
  a literally zero spread** — at 10–22 book rewrites a session, SEC §31 + FINRA TAF alone exceed the
  entire gross edge. And the four best-by-net are the four with the *lowest* turnover and *weakest*
  gross signal: slowing down keeps the cost and discards the edge.
* **Holdco / corp-structure (130):** no leg, and the binding constraint is **data, not parameters** —
  point-in-time holdco constituent ratios do not exist free, which downgrades "holdco vs
  sum-of-listed-parts" from an identical-claim trade to an ordinary statistical pair, the exact thing
  already killed eight times. Two independent screens kill the apparent survivors: **shortability**
  (BIP, IEP, LTRPA, UN, AMTD not shortable — removing them takes group H from t 1.43 to t 0.50) and
  **borrow at the measured HTB 10.28%/yr** (three of four groups negative in both windows).
* **Overnight-equity event (81):** no leg. **Recommend closing the overnight-equity family.** Three
  independent wide sweeps — T3's original 8, T26's 51, this 81 — now agree that **T3 is the only
  thing in the US overnight leg**, and T3 itself failed the repo's deflated-Sharpe gate at 0.9379.

---

## 4. Frozen-spec essentials — proposed **L7 `CEFMUNIEQ`**

Everything needed to wire this as a new pre-registered leg. Nothing here may be re-tuned; any change
is a new trial and re-arms the whole multiple-testing count.

### 4.1 Universe

* Source: **CEFConnect** live snapshot, ~360 closed-end funds (`DailyPricing` + weekly NAV).
* **Restriction (this is the signal-defining choice, not a filter):** Morningstar category in
  **MUNI or EQUITY** only. **Taxable-credit CEFs are excluded.** Economic claim: in credit CEFs the
  discount is a *yield-spread instrument*, not a *NAV-convergence instrument*, so the tilt does not
  belong there.
* Price > **$5.00**, both legs.
* Short leg further restricted to the broker's **`easy_to_borrow` = true** list (186 of 360 names at
  screen time). Hard-to-borrow is what took dual-class RV to −45 bp; it is a **hard exclusion, never
  a price**.
* Typical book: **18 long / 7 short** (medians).

### 4.2 Signal

* `Discount = (Price − NAV) / NAV`, from the point-in-time weekly NAV.
* Score = **`−Discount`** — the **raw cross-sectional LEVEL**, deliberately *not* a z-score, *not* a
  change, *not* an acceleration. (Every z / change / acceleration branch of this family was tested and
  is closing-print bid-ask bounce; see §2.3.)
* Long the **widest-discount decile**, short the **narrowest/premium decile**, of the restricted
  universe.
* **Dollar-neutral, equal-weight** within each side.
* Hold **1 week**; rebalance weekly. Realised turnover **0.333 of book per week**.

### 4.3 Execution rail

* **Mandatory 1 trading-day implementation lag.** CEFConnect publishes NAV *after* the close
  (`NAVPublished` trails `LastUpdated` by a session), so a discount observed at grid date *k* is
  actionable **no earlier than the next session's close**. This is not conservatism — without it the
  book is trading a price it could not have seen, and it is the single correction that turns this
  family's headline Sharpe-5 formulas negative.
* Entry and exit at the **closing print**, weekly.
* Returns must be **distribution-adjusted** (Alpaca `adjustment=all`). CEFs pay 7–8%/yr; a raw-price
  series misstates the long leg badly.

### 4.4 Cost + borrow guard (T6/T8/M0 conventions, both legs charged)

| component | charge |
|---|---|
| half-spread | **p90 = 27.25 bp**, *not* the 11.53 bp median — the book deliberately holds the **extremes** of a universe whose spread distribution is 11.5 / 18.4 / 27.2 at median / p75 / p90 |
| applied to | every unit of realised turnover, **both sides** |
| regulatory | SEC §31 at **0.278 bp** of sale notional |
| borrow | **200 bp/yr realised short rate** (not the 33 bp ETB floor), accrued daily on short notional |
| screen | short leg `easy_to_borrow` only; price > $5 both legs |

**Live sizing must use the p90 spread.** If the leg is only profitable at the median spread, it is
not profitable.

### 4.5 Sizing

* **Status: SATELLITE. Forward-test candidate, not a proven edge.**
* **Risk budget: half a standard leg** — 8% of BASKET1 risk (a full equal leg in a 7-leg basket is
  ~14.3%). Justification: stressed alpha clears its bar by only 1.06x and fails the conservative
  66-alpha bar (§2.2); it was a **secondary** pick whose pre-committed primary failed, which is
  exactly the move the programme should distrust.
* **Combined CEF cap: L5 + L7 ≤ 25% of basket risk.** They are uncorrelated in returns and adjacent
  in structure; do not let the class become a quarter-plus of the book on the strength of a −0.10
  held-out correlation.
* **Hard notional cap.** Capacity is trivial — the short leg is **7 names** and CEF closing auctions
  clear **$0.0–0.3M**. Low single-digit $M at the very best. Size to the auction, not to the Sharpe.
* Vol overlay: inherit the basket's `T13-VOL-L60-T0.1-WMAX1.0` convention.

### 4.6 Pre-committed forward gates

* `N_min` = **40 settled weekly observations** before any verdict (≈ 9 months).
* **Kill switch** (basket convention): drop the leg when, after n ≥ 40, `mean_net + 1.645·se < 0`.
  A killed leg's budget is **not** reallocated — that would be a search on a forward outcome.
* **Additional gate specific to this leg — the half-sample re-check.** The stressed held-out edge is
  entirely in one half: **first 57 weeks Sharpe 0.54 (+5.19 bp/wk), second 57 weeks Sharpe 3.53
  (+31.96 bp/wk)**. That is an edge that *arrived*, not a stable one. Additionally **37% of the
  stressed held-out mean comes from the 5 best of 114 weeks**. Re-check the split after **26 weeks**
  of forward log; **no budget increase** before that re-check, under any forward result.
* Declared trials for the DSR gate: this leg's family count is **66** (the CEF sweep), and the
  basket's `declared_trials_now` rises from 6 to **7**.

---

## 5. Corrections to the record

Two things the programme believed going in are wrong and are corrected here.

1. **"T12 CEF discount tilt at Sharpe 2.35" is not the formula that was pre-registered.** The
   pre-registered T12 **primary** (trial 4: a 52-week z-score of the discount, H=4) is **DEAD** — it
   failed three of four kill gates. What survived and sits in slot L5 is trial 5/6, the **raw
   discount LEVEL**, promoted out of `T12_DIAGNOSTICS.json`. So the z-score branch of this family had
   already been tested and lost *before* this sweep started. The sweep was correct to treat both the
   level and the z as unavailable ground.
2. **The deep-mine premise is largely disconfirmed.** "Dig where you already struck" returned
   1 candidate from 358 tries across five neighbourhoods of two proven families. The productive
   families are productive at a *point*, not over a region.

---

## 6. Reusable structural findings (the real output of 328 dead formulas)

1. **One tape, one instant, or nothing.** Identical-claim RV survives only when both legs print on
   the same tape at the same moment (L3 DUALCLASS, L2 ETFRV). Add a second venue, currency, or
   timestamp and free daily closes measure their own error: spread-change ρ₁ = −0.44…−0.52 across
   every ADR bloc, exactly the −0.50 that pure iid measurement noise predicts.
2. **The same-bar-fill artefact, quantified.** `B9` is identical to `B1` except it enters at the
   **same close that generated the signal**. That one change moves design gross Sharpe from −0.37 to
   **+2.34 (t = 5.6)** on a series that is otherwise nothing. This is what an unguarded RV backtest
   reports as a discovery.
3. **Publication lag is a lookahead.** CEFConnect NAV lands after the close. A 1-trading-day lag
   turns the CEF family's best formulas (design t 5–7) into held-out alphas of **−3 to −7.7**.
4. **Charge the p90 spread when the book holds the extremes.** A cross-sectional decile book
   deliberately selects the widest-spread names; the median spread is the wrong statistic by
   construction.
5. **Mirror accounting.** A config whose design result is negative and is therefore traded the other
   way round still **pays** the costs: `net_mirror = −gross − cost`, never `−(gross − cost)`.
   Ranking on net without this promotes books that are "significant" only because they pay 1.63 bp
   against a 0.5 bp gross edge.
6. **Shortability is a constraint, not a price.** Repeatedly decisive: 5 unshortable names carry 68%
   of holdco group H's P&L; SDS/SH/SQQQ/TMV/TNA/TZA/USO/VIS are not shortable at all, killing the
   levered-decay formulas on product restriction alone.
7. **Turnover-cost floor.** At 10–22 book rewrites a session, regulatory fees alone (SEC §31 + FINRA
   TAF, ~0.15 bp/turnover) exceed a 1–5 bp/day gross edge. 45 of 51 ETF formulas lose at a **zero**
   spread.
8. **Ticker series are silently stitched.** Alpaca serves by ticker and carries prior occupants
   forward: `BBT` is Beacon Financial not BB&T; `STI` is Solidion not SunTrust; `DOW` carries Dow
   Chemical's last close **flat** from 2017-08 to 2019-04; `UN` becomes a leveraged UNH ETF. Three
   guards now live in `hc_sweep.series()` and are reusable by any delisted-universe work.
9. **Unexpected free-data upside, worth reusing:** Alpaca's SIP free tier **does** serve daily bars
   for delisted tickers back to 2016 (DVMT, VMW, XLNX, BBL, RDS.A/B, UN, BAMR, CXO, RTN, UTX, CELG,
   ETFC, MXIM, PXD, HES, PACW, CIT, UMPQ all resolve).
10. **A genuinely new point-in-time primitive.** CEFConnect's price history is a **raw** close while
    the broker's bar is distribution-adjusted; the weekly difference of the two return series **is**
    the realised distribution. Its trailing 52-week sum is a true point-in-time distribution yield,
    unlike the snapshot's look-ahead `DistributionRatePrice` — and it makes a NAV **total** return
    constructible.

---

## 7. What is not testable on free data (stated, not substituted)

Named so they can go to `DATA_PURCHASE_SCOPE.md` rather than being quietly proxied:

* Intraday quotes on **both** legs of a cross-listed pair during the overlapping session (TSX/NYSE
  09:30–16:00 ET; B3 second). The ADR effect is real and single-digit bp and lives **inside** the
  session — precisely the resolution free daily data lacks.
* Real **iNAV/IIV** for ETFs (broker returns zero bars for `SPY.IV`, `QQQ.IV`, `EWJ.IV`, …) and index
  constituent weights.
* **Point-in-time holdco constituent ratios** (LBRDA's CHTR-per-share, LSXMA's SIRI-per-share, L's
  CNA stake, IEP's CVI stake — all drift with buybacks).
* A **survivorship-free announced-deal universe** with exchange ratios; the recalled 34-deal list is
  overwhelmingly of deals that *closed*, so its design number is an upper bound with the loss tail
  structurally absent.
* **Historical borrow rates** — only a same-day snapshot exists (B22G), applied as a constant across
  ten years.
* **Point-in-time index membership** (S&P/Russell adds/deletes with effective dates).
* **BDC discounts** — CEFConnect carries zero BDCs, BDC NAV is quarterly, no free source wired.

---

## 8. Recommendations

1. **Wire `Y05_muni_eq_static_H1` as L7 `CEFMUNIEQ`** on the §4 frozen spec, at **satellite budget
   (8%)**, under a **combined L5+L7 cap of 25%**, with the **26-week half-sample re-check** as a hard
   pre-condition on any budget increase. It is a forward-test candidate; the forward log is the test.
2. **Close the overnight-equity family.** Three independent sweeps (8 + 51 + 81) agree T3 is the only
   thing there.
3. **Retire cross-listing/ADR RV on daily data permanently.** The verdict rests on a measurement-noise
   statistic every bloc shares, not on a cost judgement or a parameter choice.
4. **Add nothing from ETF structural RV.** One hypothesis deserves a *separate, fresh* pre-registration:
   `L07` restated as a once-a-session rule in the L2 mould (measure at the close, trade the open, one
   round trip) with execution **measured** rather than proxied. It **must not** be scored on this
   design window again.
5. **Stop sweeping holdco RV on free data.** All three blockers are paid-data asks, not tuning problems.
6. **Raise the standing multiple-testing count.** The programme has now spent 358 formulas in this
   round alone. Every future family's bar should be set against the *cumulative* count, not a fresh one.

---

## 9. Process attestation

* Every sub-family held out a later window and read it **once**, after the design-stage selection was
  written to disk and (in three of five) committed to git.
* The CEF sweep's design artefact writes every held-out field as the literal string `"SEALED"` until
  selection is recorded; the ETF sweep hashed its pre-registration (`sha256 1a141a67…`) and its
  shortlist script **refuses to run against any other hash**; the overnight sweep committed its pick
  list at `5b4dce5` before any held-out number existed.
* The cross-listing sweep **voided its own first design pass** as evidence (an FX-timestamp error) and
  kept it as `DESIGN_v1_voided.json` rather than deleting it.
* Two stresses in the CEF sweep (implementation lag, p90 spread) were added **after** the design
  ranking was seen but **before** any selection, motivated by mechanism rather than by a number, and
  are declared as post-freeze in the write-up.
* The pre-committed CEF **primary failed** and is reported as a failure rather than swapped.
* The formula that would have been picked by peeking (`C02_cat_within`) is named and claimed as nothing.

**Commits:** `1aaacf2c` (cross-listing), `20fdda6` (ETF structural), `5b4dce5` + `3ec6f88` (overnight
event). CEF and holdco artefacts as listed in §0.
