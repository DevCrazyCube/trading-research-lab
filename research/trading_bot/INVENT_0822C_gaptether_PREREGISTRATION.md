# INVENT_0822C — PRE-REGISTRATION: the PUBLISHED-GAP TETHER

**Written 2026-08-22, before any design-window statistic was computed on any formula.**
Theme: EXOTIC / LEFT-FIELD — *overnight gap statistics conditioned on a structural cause where a
third party publishes the exact expected gap.*

---

## 1. The object

For a corporate action with a published rate, the mechanical overnight price change from the
**cum-day close** to the **ex-day open** is arithmetic, not an estimate:

```
g   = ln( P_open(ex) / P_close(cum) )                     actual printed gap  (RAW prices)
a   = ln( 1 - D / P_close(cum) )  -  ln( new/old )        PUBLISHED expected gap
eps = g - a                                               residual
```

`D`, and the split ratio `old:new`, are published by the issuer/transfer agent **before** the
event and are carried in the Alpaca corporate-actions feed. This is the lesson-4 condition:
the tether is a third-party claim, not a fitted statistic. `eps` is therefore a clean,
free, daily measurement of **unexpected overnight demand** on ~9 liquid names per day.

Two questions, deliberately separated:

* **Q1 (family A/D)** — is `eps` itself predictably non-zero, i.e. is the ex-day gap a trade?
  *(This is the published ex-day drop-ratio anomaly; it is a replication, not an invention,
  and is labelled as such wherever it appears.)*
* **Q2 (family B/C)** — does `eps` carry information about the **subsequent** price path, i.e.
  is the published dividend a free order-flow meter? *(This is the round's original claim.)*

All returns are **hedged**: every event return has the cross-sectional median return of the
clean liquid universe on the same clock subtracted. The books are therefore market-neutral by
construction and the hedge leg is charged.

## 2. Panel, windows, universe

* `research/data/exo0822c/events.npz`, built by `scripts/trading_bot/exo0822c_panel.py` from
  `research/data/auc0822_cache/panel.npz` (**RAW / unadjusted** prints, verified on the NVDA
  10:1 of 2024-06-10) and `research/data/t7_cache/corporate_actions_all.json.gz`.
* Universe filter, applied at the cum-day close on **raw** levels (point-in-time legal):
  in the auc0822 liquid universe, corporate-action coverage present, price > $5, ADV > $1M.
* Events: 15,959 (15,759 ordinary cash dividends, 50 special, 117 forward splits, 33 reverse
  splits) on 2,423 of 2,669 trading days.
* **Design 2016-01-04 → 2022-12-30. Held out 2023-01-03 → 2026-08-14, untouched until every
  sign in §3 is frozen to `_DESIGN.json`.**

## 3. The 28 pre-registered formulas

Sign column: `apriori` = the sign is fixed now from the mechanism/literature and may not be
re-chosen; `design` = the sign is set on the design window from the zero-cost P&L and frozen.

| # | name | book | sign |
|---|---|---|---|
| A1 | `A1_EQ` | equal weight all ordinary dividends, hold cum-close → ex-open | apriori + |
| A2 | `A2_YW` | same, weight ∝ dividend yield | apriori + |
| A3 | `A3_YHI` | same, top **expanding tercile** of yield only | apriori + |
| A4 | `A4_YLO` | same, bottom expanding tercile only | apriori + |
| A5 | `A5_YSPREAD` | within-day long top-yield / short bottom-yield half (cohort-neutral) | apriori + |
| A6 | `A6_SPECIAL` | special dividends only | apriori + |
| A7 | `A7_REG` | regular payers (prior ex-date 40–90 trading days back) | apriori + |
| A8 | `A8_IRREG` | non-regular payers | apriori + |
| A9 | `A9_ADVHI` | top-half ADV of the day's cohort | apriori + |
| A10 | `A10_ADVLO` | bottom-half ADV of the day's cohort | apriori + |
| B1 | `B1_EPS_OC` | w ∝ cohort-demeaned z(eps) → ex-day open→close | design |
| B2 | `B2_Y_OC` | w ∝ cohort-demeaned z(yield) → ex-day open→close | design |
| B3 | `B3_GRAW_OC` | w ∝ cohort-demeaned z(**raw** gap g) → ex-day open→close (no-tether control) | design |
| C1 | `C1_EPS_H1` | w ∝ cohort-demeaned z(eps), ex-open → ex+1 open | design |
| C2 | `C2_EPS_H5` | same, H = 5 | design |
| C3 | `C3_EPS_H20` | same, H = 20 | design |
| C4 | `C4_EPS_GAP5` | same signal, entry delayed one session (ex+1 open → ex+6 open) — the **one-day-gap re-entry test**, carried inside N | design |
| C5 | `C5_EPSAGG_TS` | day's cohort-mean eps as a time-series sign on the equal-weight clean universe, H = 1 | design |
| C6 | `C6_EPS_VOLADJ` | w ∝ cohort-demeaned z(eps / trailing-60d overnight vol), H = 5 | design |
| D1 | `D1_FWD_GAP` | forward splits, ex-day gap residual | apriori + |
| D2 | `D2_FWD_H20` | forward splits, ex-open → ex+20 open | design |
| D3 | `D3_REV_GAP` | reverse splits, ex-day gap residual | apriori − |
| D4 | `D4_REV_H20` | reverse splits, ex-open → ex+20 open | apriori − |
| E1 | `E1_PLACEBO_DATE` | A1 run on the same names' hedged overnight gap on a nearby **non-event** date | must be ≈ 0 |
| E2 | `E2_SHUFFLE_RATE` | A2 with the day's dividend rates permuted across the cohort before forming both `a` and `w` | must be ≈ 0 |
| E3 | `E3_NOTETHER` | A1 on the **raw** gap `g` with no published rate subtracted | expected strongly − |
| E4 | `E4_RUNUP5` | hedged close-to-close return over the 5 sessions ending at the cum close | design |
| E5 | `E5_RUNUP20` | same over 20 sessions | design |

**N = 28.** The five E cells are controls and they are counted **inside N**, not bolted on.

## 4. Execution model

* Event legs fill in the **closing auction of the cum day (MOC)** and the **opening auction of
  the ex day (MOO)** — the rail that `M0_AUCTION_FILLS` measured at ≈ 0 half-spread for liquid
  tiers. It is nevertheless charged conservatively.
  * **headline `c_e` = 3.0 bp/side** (Dyhrberg liquid-taker 2.5 + 0.5 fee)
  * **shock `c_e` = 6.0 bp/side**
  * **auction rail `c_e` = 0.5 bp/side** reported as the optimistic bound, never as headline.
* Hedge leg charged at **1.0 bp/side** (SPY-like).
* Overlapping tranches: a horizon-H book deploys 1/H of capital per day.
* Sharpe is annualised over **every trading day in the window**, including days the book is flat.
* Break-even one-way event-leg cost is reported for every cell.

## 5. Gates, fixed now

1. **Pooled gross bar first.** Analytic two-sided bar over N = 28: `sqrt(2 ln 56)` = **2.84** in
   |t| units. A cell must clear this **and** the size-matched placebo p95 on the **design**
   window before its held-out window is read.
2. **Size-matched placebo (the round's null).** Per replicate, each event's returns are replaced
   by the **same symbol's** hedged returns on a nearby **non-event** date (offset drawn from
   ±3…±15 sessions, corporate-action days excluded), and **all 28 formulas are re-scored and the
   maximum |t| taken**. 400 replicates. This preserves symbol, calendar proximity, cohort size,
   universe and cross-sectional covariance, and destroys only "is this an event". A
   rotate-the-returns null is not used (broken, per INVENT_0822B §4.2).
3. **ρ1 gate.** `eps` is an anchored-spread residual, so the bounce gate applies:
   ρ1 of the per-event residual series, and ρ1 between the ex-day gap and the ex-day session,
   are reported **before** any gross claim. Need ρ1(Δ) > −0.35. Additionally `C4_EPS_GAP5` is the
   one-day-gap re-entry test and is inside N.
4. **Held-out.** Real only if design clears both bars **and** held-out net is positive at the
   headline cost **and** the ρ1 gate passes.
5. **No regime conditioning.** No cell gates a single leg on a market/vol state. The A3/A4/A9/
   A10 subsets are structural cross-sectional size sorts, and A5 is a within-day spread.

## 6. Disclosure made before the window was split

The panel builder printed one full-sample descriptive line per event class before the design
window was isolated: ordinary dividends mean hedged `eps` **+7.33 bp** on a median yield of
46.7 bp (drop ratio ≈ 0.84), special dividends +65.9 bp, forward splits +90.9 bp, reverse splits
−136.3 bp. This is a peek and it is disclosed rather than buried. Its practical effect is
limited because the four signs it reveals are exactly the signs the published literature fixes
a priori (Elton–Gruber drop ratio < 1; split ex-date pop; reverse-split distress), which is why
those cells are pre-registered `apriori` above and cannot be re-chosen later. Every `design`-sign
cell in families B, C and E was **not** touched by that print.
