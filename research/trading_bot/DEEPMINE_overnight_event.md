# DEEPMINE — overnight-equity EVENT anomalies

**53 structurally different event-conditioned overnight formulas (81 distinct
parameterisations across three design-window iterations), designed on 2016-01-04 → 2021-12-31,
held out on 2022-01-03 → 2026-08-14.**

Sibling sweep to T3 (pressure reversal, survived), T7 (ex-dividend open, survived) and T26
(the 51-formula *non-event* overnight sweep). Where T26 asked "what else lives in the
overnight leg", this one asks "what lives in the overnight leg **around an event**":
earnings announcements, 52-week extremes, an index-add proxy, turn-of-month and FOMC.

Harness: `scripts/trading_bot/t27_event_overnight.py` (event panel + sweep + joint null +
held-out) and `scripts/trading_bot/t27_diag.py` (distribution, mirror-direction accounting,
census, T3 correlation). Data is entirely cached — no network call, no purchase.

---

## Verdict, first

**The sub-family is noise. Nothing here is promotable, and nothing here is new.**

Three of 53 configs clear the empirical joint-null bar on the design window. Two of them
(`T01`, `T03`) correlate **+0.94 and +0.99** with the T3 book — they are T3 with a handful of
names removed, and they carry no residual alpha over T3 out of sample (t = +0.43 and −0.41).

The one structurally new formula that cleared — `N07`, T3's pressure fade run **inside
tonight's earnings-announcer set only**, design net **+37.1 bp/night, Sharpe +3.79, t +3.54** —
held out at **−8.04 bp/night, Sharpe −0.51, t −0.48**. Its residual alpha over T3 goes from
+29.8 bp (t = +2.98) on design to **−15.9 bp (t = −0.99)** held out. It does not replicate.

The largest *gross* event effect in the family is real and dies on cost: names in the 1–5
sessions after an earnings print **underperform matched peers overnight** by ~2.3 bp/night
gross (design `D13`, gross Sharpe −2.27, t −6.86), decaying monotonically to −0.90 at nights
1–10 and −0.41 at nights 11–20. Traded in the profitable direction — short the recently
reported names, long the coverage-matched cross-section — it nets **+0.63 bp/night, Sharpe
+0.62** on design and **−1.01 bp/night, Sharpe −0.83** held out. The gross edge is smaller
than the 1.63 bp it costs to harvest.

---

## The rails and the cost model (inherited verbatim, not re-derived)

| rail | signal may use | entry | exit | cost charged |
|---|---|---|---|---|
| **A** marketable | up to 15:59 | marketable order at the 15:59 last trade | next opening auction | 1.13 bp (design) / 1.43 bp (held out) half-spread + 0.50 bp auction + borrow |
| **B** MOC-legal | ≤ 15:49 only | MOC lodged before the 15:50 cutoff, filled at the official closing print | next opening auction | 0.50 bp auction × 2 + borrow |

Half-spread from T3's own SIP-quote measurement on the top-500-ADV screen; the 0.50 bp
auction leg from `M0_AUCTION_FILLS.json` (official print vs mid on rank 1–50: signed mean
+0.18 bp, absolute median 1.61 bp, close half-spread median 0.90 bp); borrow 30 bp/yr on the
short notional accrued over calendar days held (T6/T8 per-side convention). Every
market-neutral book charges **both legs' spreads plus borrow on the short**. The universe is
the point-in-time top-500 by prior-month dollar ADV with a $5 price floor and a $20 M ADV
floor — an easy-to-borrow screen by construction; the hard-to-borrow tail that killed
dual-class RV never enters.

### Mirror-direction accounting — the thing that decides most of this sweep

A config whose design result is negative is traded the other way round. The mirror pays the
same costs; it does not earn them:

    net_mirror = −gross − cost      NOT   −(gross − cost)

Ranking on `net` alone would have promoted several event books that are only "significant"
because they pay 1.63 bp/night against a 0.5 bp gross edge. Every table below ranks on the
**tradeable** number: the better of the as-specified net and the mirror net. `t` is the Sharpe
expressed in its own standard-error units, so `t` — not Sharpe — is what goes against the
noise bar; the raw max-Sharpe null is inflated by the configs that trade only 37–300 nights.

---

## Noise bar — and why it is higher here than in T26

**Analytic.** 53 configs in the final table; 81 distinct evaluated parameterisations across
the three design-window iterations (see *Iteration ledger*). Both directions are tradeable, so
the search is two-sided: √(2 ln(2·81)) = **3.19** Sharpe-SE units. On the 53-config table
alone, √(2 ln 106) = 3.05.

**Empirical, and this is the bar used.** 400 replicates; within each trading day the overnight
returns are permuted among the valid names; **one permutation shared by all 53 configs** so
their correlation is preserved; max |t| and max |Sharpe| across all 53 recorded per replicate.

| statistic | mean | p50 | p90 | **p95** | p99 | max of 400 |
|---|---|---|---|---|---|---|
| max abs t | 2.49 | 2.44 | 3.03 | **3.27** | 3.76 | 4.08 |
| max abs annualised Sharpe | 2.48 | 2.41 | 3.30 | 3.56 | 4.05 | 4.97 |

The empirical max-|t| p95 of **3.27** and the analytic 3.19 agree closely — unlike T26, where
51 highly correlated restatements of one feature pushed the empirical bar *below* the analytic
one. Here the formulas are genuinely different from each other, so correlation buys almost
nothing back. The max-|Sharpe| row is 3.56 and should **not** be used: `M03` trades 48 nights,
`M04` 48, `D01` 148, so their Sharpe standard errors run to 2.3–2.6 and they dominate the
max-Sharpe null without carrying any evidence.

**Everything is judged against |t| ≥ 3.27.**

---

## Full design distribution (53 configs, tradeable direction, net of costs)

| | min | p10 | p25 | p50 | p75 | p90 | max | mean | sd | n > 0 |
|---|---|---|---|---|---|---|---|---|---|---|
| net Sharpe (as specified) | −4.98 | −2.66 | −1.78 | −0.65 | +0.40 | +2.17 | +4.71 | −0.55 | 1.84 | 18/53 |
| net Sharpe (tradeable dir.) | −1.55 | −0.94 | −0.47 | +0.08 | +0.68 | +2.20 | +4.71 | +0.39 | 1.28 | 32/53 |
| net t (tradeable dir.) | −3.15 | | | +0.09 | | +2.17 | +5.43 | | | |

**3 of 53 clear |t| ≥ 3.27; 0 clear it in the opposite direction.** The median tradeable
Sharpe is +0.08 — an event book that pays a full half-spread plus two auction legs every
single night, for nothing.

| # | config | rail | traded direction | nights | net bp/night | net SR | net t | gross SR (as-specified) | formula |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `M03_spy_fomc_eve` | A | as-specified | 48 | +13.28 | +4.71 | +2.06 | +5.29 | long SPY overnight into an FOMC decision day (the pre-FOMC announcement drift, overnight leg) |
| 2 | `N07_ann_p10_fade` | A | as-specified | 220 | +37.13 | +3.79 | +3.54 | +3.96 | among tonight's announcers ONLY, fade the 15:49->15:59 move (T3 inside the event set) |
| 3 | `T03_p10_annnight_excl` | A | as-specified | 1236 | +7.51 | +2.45 | +5.43 | +3.00 | T3 pressure fade with tonight's announcers REMOVED from the book |
| 4 | `R02_rankpromote_p10` | A | as-specified | 297 | +7.37 | +2.33 | +2.53 | +2.86 | T3 pressure fade restricted to newly promoted names |
| 5 | `M02_spy_tom_last` | A | as-specified | 144 | +9.28 | +2.30 | +1.74 | +2.71 | long SPY overnight on the last 2 sessions of a month |
| 6 | `T01_p10_quiet` | A | as-specified | 1236 | +8.27 | +2.22 | +4.92 | +2.68 | T3 pressure fade restricted to names with NO announcement within +-10 sessions |
| 7 | `N04_ann_long_lovol` | A | mirror | 275 | +10.59 | +2.11 | +2.20 | -2.44 | N01 inside the bottom trailing-vol tercile only |
| 8 | `T02_p10_post15` | A | as-specified | 425 | +4.13 | +1.97 | +2.56 | +2.78 | T3 pressure fade restricted to the 5 sessions after a print |
| 9 | `M04_spy_fomc_night` | A | mirror | 48 | +8.00 | +1.96 | +0.85 | -2.36 | long SPY overnight AFTER an FOMC decision |
| 10 | `N10_ann_hl_fade` | A | mirror | 220 | +17.67 | +1.71 | +1.60 | -1.87 | among tonight's announcers ONLY, long the ones nearest their 52w LOW, short nearest the 52w HIGH |
| 11 | `P04_pre_p10_fade` | A | as-specified | 264 | +1.99 | +1.46 | +1.49 | +2.69 | T3 pressure fade restricted to the 5 sessions before a predicted announcement |
| 12 | `N08_ann_day_fade` | A | as-specified | 220 | +10.38 | +1.07 | +1.00 | +1.24 | among tonight's announcers ONLY, fade the full open->15:59 session move |
| 13 | `H02_newlo_cont` | A | as-specified | 530 | +2.65 | +0.82 | +1.19 | +1.34 | short names printing a new 252-day closing low today, long the cross-section |
| 14 | `M01_spy_tom_first` | A | as-specified | 216 | +2.69 | +0.68 | +0.63 | +1.10 | long SPY overnight on the first 3 sessions of a month (turn-of-month), one half-spread in, auction out |
| 15 | `D13_post15_long_vs_xs` | A | mirror | 773 | +0.63 | +0.62 | +1.08 | -2.27 | CONTROL: long EVERY name 1-5 nights after a print, irrespective of the surprise sign, short the cross-section |
| 16 | `M06_spy_tom_moclegal` | B | as-specified | 216 | +2.19 | +0.54 | +0.50 | +0.78 | M01 executed with an MOC order instead of a marketable 15:59 buy |
| 17 | `M05_spy_alln` | A | as-specified | 1499 | +2.42 | +0.50 | +1.21 | +0.83 | unconditional long SPY overnight -- the benchmark every calendar cut has to beat |
| 18 | `N06_ann_long_loadv` | A | mirror | 283 | +4.02 | +0.48 | +0.51 | -0.68 | N01 inside the bottom dollar-ADV tercile only |
| 19 | `D06_pead15_c10` | A | mirror | 319 | +0.98 | +0.41 | +0.46 | -1.12 | D04 at a 10 % tail cut instead of 30 % |
| 20 | `H05_newhi_p10_fade` | A | as-specified | 924 | +0.68 | +0.40 | +0.77 | +1.39 | T3 pressure fade restricted to names at a new 52-week high |
| 21 | `H04_hl_pos_cont` | A | as-specified | 1236 | +0.91 | +0.32 | +0.71 | +0.91 | the continuation sign of H03 |
| 22 | `H03_hl_pos_fade` | A | mirror | 1236 | +0.91 | +0.32 | +0.71 | -0.91 | continuous 52-week range position: long the bottom decile, short the top decile, overnight |
| 23 | `N02_ann_long_advneutral` | A | mirror | 637 | +2.41 | +0.27 | +0.43 | -0.46 | N01 built inside each dollar-ADV tercile and pooled (liquidity-neutral) |
| 24 | `N09_ann_runup_fade` | A | mirror | 220 | +2.38 | +0.23 | +0.21 | -0.39 | among tonight's announcers ONLY, fade the 5-day run-up into the print |
| 25 | `G01_gapfade_postann` | A | as-specified | 148 | +0.43 | +0.12 | +0.09 | +0.60 | fade this morning's realised close-to-open gap, restricted to names that announced LAST night |
| 26 | `N05_ann_long_hiadv` | A | mirror | 270 | +0.70 | +0.10 | +0.11 | -0.35 | N01 inside the top dollar-ADV tercile only |
| 27 | `N03_ann_long_hivol` | A | as-specified | 272 | +0.88 | +0.08 | +0.09 | +0.25 | N01 inside the top trailing-vol tercile only |
| 28 | `D11_pead13_moclegal` | B | mirror | 294 | +0.14 | +0.08 | +0.09 | -0.70 | D03 executed MOC-legal (closing auction in, opening auction out) |
| 29 | `D02_pead1_rev` | A | as-specified | 148 | +0.17 | +0.05 | +0.04 | +0.55 | night 1 after the print: the reversal sign of D01 |
| 30 | `D01_pead1_cont` | A | mirror | 148 | +0.17 | +0.05 | +0.04 | -0.55 | night 1 after the print: LONG the biggest positive announcement jump, short the biggest negative (PEAD in the overnight leg) |
| 31 | `N11_ann_long_moclegal` | B | mirror | 597 | +0.17 | +0.02 | +0.03 | -0.16 | N01 executed MOC-legal: closing auction in, opening auction out |
| 32 | `G02_gapfade_quiet` | A | mirror | 1236 | +0.03 | +0.01 | +0.01 | -0.33 | the same gap fade on names with NO announcement within +-10 sessions |
| 33 | `G03_gapfade_all` | A | mirror | 1236 | -0.07 | -0.02 | -0.03 | -0.34 | the unconditional gap fade (T26's A25, repeated here as the reference) |
| 34 | `D09_pead_long_vs_xs` | A | mirror | 398 | -0.03 | -0.04 | -0.05 | -2.47 | long ONLY the positive-surprise names in nights 1-5, short the cross-section |
| 35 | `N01_ann_long_vs_xs` | A | mirror | 597 | -0.35 | -0.05 | -0.07 | -0.17 | long every name whose 8-K 2.02 lands in tonight's overnight window, short the equal-weighted rest |
| 36 | `D04_pead15_cont` | A | mirror | 424 | -0.07 | -0.05 | -0.06 | -1.07 | nights 1-5 after the print, continuation of the announcement jump |
| 37 | `D12_pead15_advneutral` | A | mirror | 288 | -0.18 | -0.15 | -0.16 | -1.22 | D04 ranked within dollar-ADV terciles and pooled |
| 38 | `D03_pead13_cont` | A | mirror | 294 | -0.35 | -0.21 | -0.22 | -0.79 | nights 1-3 after the print, continuation of the announcement jump |
| 39 | `H06_newhi_moclegal` | B | as-specified | 1140 | -0.71 | -0.27 | -0.57 | +0.13 | H01 executed MOC-legal |
| 40 | `D05_pead610_cont` | A | mirror | 420 | -0.69 | -0.47 | -0.61 | -0.69 | nights 6-10 after the print, continuation (does the drift survive the first week?) |
| 41 | `H01_newhi_cont` | A | as-specified | 1140 | -1.33 | -0.50 | -1.07 | +0.13 | long names printing a new 252-day closing high today, short the cross-section, overnight |
| 42 | `D08_pead15_z_over_vol` | A | mirror | 424 | -0.70 | -0.51 | -0.66 | -0.72 | D04 with the jump risk-normalised by 21d realised vol |
| 43 | `D17_absjump_fade` | A | as-specified | 570 | -0.99 | -0.51 | -0.76 | +0.36 | among post-print names, long the SMALLEST absolute surprise, short the largest (an attention, not a direction, sort) |
| 44 | `P01_pre15_long` | A | as-specified | 479 | -0.69 | -0.74 | -1.02 | +1.06 | long names 1-5 sessions BEFORE a realised announcement (realised date, pre-announcement drift) |
| 45 | `D10_pead_short_vs_xs` | A | as-specified | 385 | -0.68 | -0.78 | -0.96 | +1.16 | SHORT ONLY the negative-surprise names in nights 1-5, long the cross-section |
| 46 | `D07_pead15_resid_day` | A | mirror | 424 | -1.24 | -0.81 | -1.05 | -0.29 | D04 on the cross-sectional residual of the jump on the same-session move |
| 47 | `D14_pead_neg_long_vs_xs` | A | mirror | 480 | -0.83 | -0.88 | -1.21 | -0.90 | long ONLY the negative-surprise names in nights 1-5, short the cross-section |
| 48 | `D15_post110_long_vs_xs` | A | mirror | 1108 | -0.87 | -0.96 | -2.00 | -0.90 | CONTROL: D13 over nights 1-10 instead of 1-5 |
| 49 | `P03_pre110pred_long` | A | as-specified | 584 | -0.78 | -0.96 | -1.47 | +1.12 | long names 1-10 sessions before the PREDICTED announcement |
| 50 | `R01_rankpromote` | A | mirror | 293 | -1.43 | -1.23 | -1.33 | -0.22 | PROXY for an index add: names newly entering the point-in-time top-500-ADV screen, first 5 sessions of the month, long vs the cross-section |
| 51 | `X01_covered_vs_uncovered` | A | as-specified | 1229 | -1.10 | -1.43 | -3.15 | +0.77 | CONFOUND PROBE, not a strategy: long domestic 8-K filers with no print in 20 sessions, short the ETF/ADR remainder of the top-500-ADV screen |
| 52 | `D16_post1120_long_vs_xs` | A | mirror | 1115 | -1.32 | -1.46 | -3.07 | -0.41 | PLACEBO: long names 11-20 nights after a print -- the attention window should be over |
| 53 | `P02_pre15pred_long` | A | as-specified | 333 | -1.01 | -1.55 | -1.78 | +1.03 | P01 with the STRICTLY point-in-time predicted date (last filing + 91 calendar days) |

---

## Held out — 2022-01-03 → 2026-08-14, never read until the pick list was frozen and committed

Pick list frozen in `DEEPMINE_overnight_event_HOLDOUT_PICKS.md`, committed at `5b4dce5`
together with the design results, **before** `heldout` had ever been run. Group A = the three
configs that cleared the bar. Group B = five design-stage failures held out anyway so their
numbers are disclosed rather than buried; none of them may be promoted on a held-out number.

| config | traded direction | design SR | design t | held-out nights | held-out bp/night | held-out SR | held-out t | held-out zero-cost SR |
|---|---|---|---|---|---|---|---|---|
| `M03_spy_fomc_eve` | as-specified | +4.71 | +2.06 | 37 | +18.87 | +6.55 | +2.51 | +7.22 |
| `T01_p10_quiet` | as-specified | +2.22 | +4.92 | 1139 | +6.05 | +1.17 | +2.49 | +1.56 |
| `T03_p10_annnight_excl` | as-specified | +2.45 | +5.43 | 1139 | +4.67 | +1.12 | +2.38 | +1.60 |
| `T02_p10_post15` | as-specified | +1.97 | +2.56 | 413 | +0.99 | +0.34 | +0.43 | +1.01 |
| `R02_rankpromote_p10` | as-specified | +2.33 | +2.53 | 278 | -0.22 | -0.04 | -0.05 | +0.37 |
| `N07_ann_p10_fade` | as-specified | +3.79 | +3.54 | 219 | -8.04 | -0.51 | -0.48 | -0.39 |
| `M02_spy_tom_last` | as-specified | +2.30 | +1.74 | 112 | -2.41 | -0.71 | -0.47 | -0.14 |
| `D13_post15_long_vs_xs` | mirror | +0.62 | +1.08 | 695 | -1.01 | -0.83 | -1.38 | -0.80 |

### What each one says

- **`N07_ann_p10_fade` — the only new formula that cleared the design bar — is dead.**
  Design +37.1 bp/night at Sharpe +3.79 (t +3.54, just over the 3.27 bar), held out
  −8.04 bp/night at Sharpe −0.51. Hit rate falls from 61.8 % to 50.7 %; the held-out mean is
  dragged negative by a handful of nights (the single worst night is −37 % of the total). The
  design number was a 220-night sample of a book whose nightly standard deviation is 155 bp.
  Its correlation with T3 is only +0.30/+0.28, so it *was* the diversifying candidate — and it
  is the one that failed.
- **`T01` / `T03` are T3.** ρ = +0.94 / +0.99 with the T3 book in both windows, β ≈ 1.0.
  Held-out residual alpha over T3: +0.38 bp (t +0.43) and −0.15 bp (t −0.41). Removing the
  announcers from T3's book neither helps nor hurts. They survive out of sample at Sharpe
  ≈ +1.15 because **T3 survives**, which is the T26 result restated, not a new one.
- **`R02_rankpromote_p10` (T3 inside the index-add proxy)**: ρ = +0.62/+0.77 with T3, held out
  −0.04 Sharpe. A T3 subsample, and a worse one.
- **`D13` (post-print overnight underperformance)**: the mirror nets −1.01 bp/night held out.
  The gross effect halves out of sample (−2.27 → −0.80 Sharpe) and never covered its costs
  even at its design-window strength.
- **`M02_spy_tom_last` (turn-of-month, last two sessions)**: +2.30 Sharpe design, −0.71 held
  out. Dead.
- **`M03_spy_fomc_eve` is the only residue, and it is not promotable.** See below.

---

## The one residue: pre-FOMC overnight, and why it still fails

Long SPY from the 15:59 print on the session before an FOMC decision to the next opening
auction. Single instrument, no short leg, no borrow, ~8 nights a year.

| window | nights | net bp/night | net Sharpe | net t | hit rate | median night |
|---|---|---|---|---|---|---|
| design 2016–2021 | 48 | +13.28 | +4.71 | +2.06 | 68.8 % | +6.71 bp |
| held out 2022–2026 | 37 | +18.87 | +6.55 | +2.51 | 62.2 % | +9.40 bp |

Both windows positive, both medians positive, hit rate above 60 % in both, and it survives
2× spread + 2× auction (held-out Sharpe +5.88). It is also essentially uncorrelated with T3
(ρ = −0.11 design) and cannot collide with T7, which trades ex-dividend single names at the
open. On the face of it, this is the most diversifying thing in the sweep.

**It still fails, for four independent reasons.**

1. **It never cleared its own design bar.** Design t = +2.06 against 3.27. Under the
   pre-registered rule it was disclosed, not promoted.
2. **The placebo lags fire just as hard on design.** Running the identical book at *k*
   sessions before the decision instead of one:

   | k sessions before FOMC | design Sharpe | design t | held-out Sharpe | held-out t |
   |---|---|---|---|---|
   | 1 (the config) | +4.71 | +2.06 | +6.55 | +2.51 |
   | 2 | +4.57 | +2.00 | +1.77 | +0.68 |
   | 3 | −2.60 | −1.14 | −0.62 | −0.24 |
   | 4 | +0.49 | +0.21 | −1.47 | −0.56 |
   | 5 | +4.58 | +2.00 | +0.67 | +0.26 |
   | 10 | −0.47 | −0.21 | +0.08 | +0.03 |
   | 1 session *after* | −2.73 | −1.19 | −2.25 | −0.86 |

   Three of ten arbitrary lags produce a design Sharpe above +4.5 on 48 observations. A
   design Sharpe of 4.7 is simply what a 48-night sample of SPY overnight returns does. Only
   lag 1 replicates, which is one hit out of ten.
3. **It is not an invention.** This is the Lucca–Moench pre-FOMC announcement drift, published
   in 2015, on the overnight rather than the 24-hour clock. The standing instruction is
   self-invented strategies; replicating a published anomaly on 85 total observations is the
   opposite.
4. **It is not sizeable.** ~8 nights a year at ~15 bp of SPY notional is ~1.2 % a year on
   100 % gross, before any slippage beyond the modelled half-spread, and with a P&L in which
   the best three nights are 55–68 % of the total.

Recorded as an observation, not an edge. If it is ever revisited it needs a genuinely
forward-collected sample, not another cut of these 85 nights.

---

## The gross finding worth keeping: post-print overnight underperformance decays in event time

Against a **coverage-matched** control (see the confound section), long the names 1–*k*
sessions after an 8-K Item 2.02, short the rest of the covered cross-section, design window:

| window | design gross Sharpe | held-out gross Sharpe |
|---|---|---|
| the announcement night itself (`N01`) | −0.17 | — |
| nights 1–5 (`D13`) | **−2.27** | −0.80 |
| nights 1–10 (`D15`) | −0.90 | — |
| nights 11–20 (`D16`, placebo) | −0.41 | — |

A clean monotone decay in event time — the shape of a real effect, not a level shift, and the
sign is the *opposite* of the attention story (Berkman–Koch–Tuttle–Zhang would predict
recently reported names earn **more** overnight, not less). The sign does not depend on the
surprise: long the positive surprises (`D09`, gross −2.47) and long the negative surprises
(`D14`, gross −0.90) are both negative, so this is an "attention decay" effect, not PEAD.

It is untradeable on this rail. Gross ≈ 2.3 bp/night against 1.63 bp of cost on design, and
the gross halves out of sample. It is recorded because it is the only mechanism in the family
that produced a coherent event-time profile.

---

## Two confounds found and fixed inside the design window

**1. The control leg was one-third ETFs and ADRs.** An 8-K Item 2.02 exists only for domestic
filers. On a typical day **147 of the 500** point-in-time top-ADV names can never be an event
name: SPY, QQQ, IWM, IVV, VOO, DIA, TQQQ, LQD, HYG, AGG, IEF, the sector XLs, KRE, XOP, EWZ,
IEMG, VEA — plus foreign issuers that file 6-K, not 8-K (BABA, TSM). "Long the event names,
short the rest of the cross-section" was therefore a permanent long-single-stock /
short-ETF-and-ADR factor bet. Every event-vs-cross-section book was rebuilt inside the
**coverage-matched** universe (names that have already filed at least one 8-K 2.02 by that
date — point in time). The probe left in the table, `X01_covered_vs_uncovered`, measures what
was being smuggled in: gross Sharpe +0.77, net −1.43, t −3.15.

**2. The placebo fired before the fix.** Pre-fix, "long names 11–20 nights after a print"
(`D16`) came in at t = −4.50 — i.e. the supposed post-earnings window effect extended a month
out, which is what a level shift looks like. Post-fix its *gross* Sharpe is −0.41 against
−2.27 at nights 1–5, and the profile is monotone. This is exactly why the placebo was in the
table.

---

## Look-ahead: what is assumed, and the strict test that was run anyway

The 8-K acceptance timestamp is only observable after the filing. Two of the six groups need
to know at 15:59 whether a print is coming, and issuers do pre-announce their earnings date
weeks ahead — but "they pre-announced" is an assumption, not a measurement, so the strict
version was run as well:

- `P02_pre15pred_long` / `P03_pre110pred_long` use a **strictly point-in-time predicted date**
  (last observed filing + 91 calendar days, snapped to the next session), which uses only
  filings already public. Both are negative on design (−1.55 and −0.96 tradeable Sharpe).
- `P01_pre15_long` uses the realised date and is also negative (−0.74). The realised-date
  version is not better than the predicted-date version, so the pre-announcement groups carry
  no hidden look-ahead advantage — they are simply empty.
- The post-announcement groups (`D*`) and the announcement-night groups (`N*`, which need only
  the date, not the content) carry **no** look-ahead: `LAST_JUMP` at row *i* is the most recent
  finite announcement return at rows ≤ *i*, and an announcement night's overnight return is
  realised at the following open — before the 15:59 entry of the next night.

---

## Data census

| | |
|---|---|
| panel | 2,648 sessions × 1,648 symbols, 2016-01-04 → 2026-08-14 |
| valid symbol-nights | 1,076,483 |
| 8-K Item 2.02 filings mapped to panel columns | 40,832 |
| … landing inside an overnight window | 38,421 |
| … landing intraday | 2,409 |
| announcement symbol-nights inside the top-500 screen | 12,733 (6,520 design / 6,213 held out) |
| median announcers per night in the screen | 2 (p90 = 13) |
| design nights with ≥ 5 announcers | 394 of 1,499 |
| symbols with 8-K coverage | 1,080 of 1,648 |

Announcement timing is recovered from the EDGAR acceptance timestamp converted to Eastern:
the distribution is cleanly bimodal at 06:00–08:00 (before the open) and 16:00–17:00 (after
the close), which is the sanity check that the timestamps are genuine UTC and the session
mapping is right.

---

## What could NOT be tested on free/cached data — stated, not fudged

- **Index add / delete.** There is no point-in-time S&P 500 / S&P 400 / Russell membership
  list anywhere in the caches (`t13_cache/sp500tr.csv` is an index *level* series, not
  constituents), and the free vendors do not publish historical membership with effective
  dates. The proxy actually run — `R01` / `R02`, names newly entering the point-in-time
  top-500 dollar-ADV screen — is a liquidity-rank promotion, **not** an index add: it has no
  forced index-fund demand behind it, and it should not be read as evidence about index
  events either way. A real index-add test needs a purchased membership history.
- **Secondary / follow-on offerings.** Would need SEC 424B filings by symbol and pricing date.
  Not in any cache, and building it means a rate-limited EDGAR full-index crawl — a detached
  background job, not something to do inside this sweep.
- **Overnight news volume / retail attention conditioners.** No daily share-volume series
  exists for this universe in cache (`t3_cache` carries monthly dollar-ADV only;
  `t11_cache/daily_bars` has OHLCV but overlaps this universe on 56 symbols). Volume-based
  gap conditioning was replaced by same-session move magnitude and trailing realised vol,
  which are weaker proxies.

---

## Iteration ledger — the honest trial count

The design window was iterated three times; the held-out window was read once, after the
pick list was committed.

| pass | configs run | what changed | why |
|---|---|---|---|
| v1 | 43 evaluated | first table | — |
| v2 | 52 | 8 new configs (`D13`–`D17`, `G01`–`G03`), 12 re-parameterised (event-count thresholds, decile cuts, the 30-night floor that let the FOMC configs be evaluated at all) | the D-group placebo was missing and several event books were rejecting most nights |
| v3 | 53 | 16 event-vs-cross-section books rebuilt on the coverage-matched universe, `X01` probe added | the ETF/ADR confound |

**81 distinct formula/parameterisations were evaluated in total.** The 53-config empirical
null is the bar actually used; the analytic two-sided bar at the full 81 is 3.19, which is
below the empirical 3.27, so the empirical bar is the conservative one either way. Nothing
promotable was found at either level.

---

## Files

- `scripts/trading_bot/t27_event_overnight.py` — event panel, sweep, joint null, held out
- `scripts/trading_bot/t27_diag.py` — distribution, mirror accounting, census, T3 correlation
- `research/data/t27_cache/events.npz` — announcement-night / event-time panel
- `research/data/t27_cache/design_results.json`, `design_results_tradeable.json`,
  `null_results.json`, `heldout_results.json`, `corr.json`, `census.json`, `dist.json`
- `research/trading_bot/DEEPMINE_overnight_event_HOLDOUT_PICKS.md` — the frozen pick list
- `research/trading_bot/DEEPMINE_overnight_event.json` — machine-readable summary
