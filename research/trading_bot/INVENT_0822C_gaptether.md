# INVENT_0822C — the PUBLISHED-GAP TETHER (exotic / left-field, 3rd rotation)

**Date:** 2026-08-22 · **Formulas pre-registered and tested: 28** · **Survivors: 0** ·
**Verdict: the theme is NOISE — and the single most valuable thing this round produced is a
data-integrity bug in a cache six other scripts read.**

Pre-registration `INVENT_0822C_gaptether_PREREGISTRATION.md`
sha256 `987b283f548c54a12bd3a3ca935d99cdc8e80863a6c1eaac0d4e39892065ca65`, written before any
design statistic. Code: `scripts/trading_bot/exo0822c_{panel,sweep,nulls,diag,matched,foreign}.py`.
Panel: `research/data/exo0822c/events.npz`.

---

## 0. THE ONE-PARAGRAPH ANSWER

I built the one anchored spread on US equities where lesson 4 is satisfied exactly: on an ex-date a
third party **publishes the expected overnight price change** (the dividend rate, the split ratio),
so `eps = ln(P_open(ex)/P_close(cum)) − ln(1 − D/P) + ln(new/old)` is a free, daily, unbiased meter
of *unexpected* overnight demand on ~9 liquid names a day. The first pass looked like the best
result of any invention round: mean hedged residual **+7.3 bp**, drop ratio 0.87 exactly as
Elton–Gruber predicts, design gross **t = 4.18** on the yield-weighted book, **0 of 400** placebo
replicates reaching it, and a held-out matched estimate that came in *stronger* at +9.4 bp
(t = 3.69). It was all wrong. One of the five pre-registered E-family controls plus a single split
on "how many dividend records does this ex-date carry" showed the entire effect living in 8 % of
events at **+62 bp**, and the cause is that
`research/data/t7_cache/corporate_actions_all.json.gz` **contains 26,038 exactly duplicated
cash-dividend records** (the same `id` twice), so summing the published rates over-states the
dividend by ~2× on those dates and manufactures a residual equal to the duplicate. After
deduplication the best of the 23 candidate formulas is design **|t| = 2.50**, which does not reach
the analytic bar (2.84) let alone the size-matched placebo p95 (**3.24**); the honest matched
estimate of the ex-day residual is **+1.6 bp design / +4.7 bp held out**, against a round-trip cost
of ~6 bp on the headline rail and ~3 bp on the measured auction rail. **Nothing is promoted.**

---

## 1. THE DATA BUG — read this even if you skip the rest

`research/data/t7_cache/corporate_actions_all.json.gz`:

| record type | rows | distinct `id` | duplicated |
|---|---:|---:|---:|
| `cash_dividends` | 385,845 | 359,807 | **26,038** |
| `forward_splits` | 980 | 943 | 37 |
| `reverse_splits` | 5,637 | 5,430 | 207 |

The duplicates are byte-identical rows carrying the **same `id`** — e.g.
`('ABEV','2016-02-01')` appears twice as `(0.023243, id 27af59a3)`. A further 609
(symbol, ex-date) groups carry the same rate under two different ids. This is an overlapping paging
window in whatever wrote the cache.

**Why it matters.** Any consumer that *sums* the rates on an ex-date doubles the dividend on ~8 % of
ex-dates; any consumer that *multiplies* split factors **squares** them. In this round that turned a
true ex-day residual of +3.5 bp into a measured +7.3 bp and produced a fully significant, fully
out-of-sample-confirmed result that does not exist:

| statistic (ordinary cash dividends) | duplicated cache | deduplicated |
|---|---:|---:|
| mean hedged ex-day residual, full sample | +7.33 bp | **+3.54 bp** |
| implied drop ratio | 0.87 | **0.92** |
| design gross t, `A2_YW` | **+4.18** | **+0.70** |
| design gross t, `A1_EQ` | +3.22 | +1.15 |
| design gross t, `A3_YHI` | +2.90 | +0.26 |
| matched event−control, design | +4.36 bp (t 3.20) | **+1.58 bp (t 1.17)** |
| matched event−control, held out | +9.39 bp (t 3.69) | **+4.71 bp (t 1.89)** |
| … restricted to **multi-record** ex-dates | **+62.4 bp (t 3.97 / 9.76)** | +8.6 bp (t 0.56) |

The last row is the fingerprint: before dedup the whole effect was concentrated in the 8 % of
events with more than one dividend record and sat at ~+62 bp — roughly one median dividend yield,
which is exactly what a doubled rate manufactures.

**Consumers of this cache that should be re-checked**, in the order they matter:
`scripts/t7_dividend_dropoff.py`, `scripts/t11_merger_arb.py`, `scripts/t11_diagnostics.py`,
`scripts/inv3_event_calendar.py`, `scripts/trading_bot/newterr_xseq_panel.py`,
`scripts/trading_bot/basket_forward.py`.

**The bug's sign is known and it is one-directional: it inflates.** So every cell that *died* on
this cache is still dead — including **T7 itself**, which is the ex-dividend drop-off study
(`T7_RESULT.md`: label-permutation p = 0.213, DSR 0.076, all eight design configurations negative).
T7's verdict stands *a fortiori*. The cells that need re-checking are any that **lived**.

The fix is three lines and is in `exo0822c_panel.py`: dedupe on `id`, then on
`(symbol, ex-date, rate)`. Distinct rates on one ex-date (regular + special) are kept and summed,
which is correct.

---

## 2. THE OBJECT, AND WHY IT WAS WORTH A ROUND

Free data prices a statistic, not a claim — except here. On an ex-date the **issuer publishes the
number** before the event:

```
g   = ln( P_open(ex) / P_close(cum) )                     printed gap, RAW prices
a   = ln( 1 − D/P_close(cum) ) − ln( new/old )            PUBLISHED expected gap
eps = g − a
```

`a` is arithmetic on a third-party claim, not a fitted hedge ratio. That makes `eps` the only
anchored residual in the US-equity book that does not need a purchased NAV, a holdings file or an
estimated beta. It is measurable on **15,966 liquid events over 2,423 of 2,669 sessions**
(15,760 ordinary dividends, 49 special, 122 forward splits, 35 reverse splits), and it is available
before the ex-day open, so it is tradeable at the **MOC→MOO auction rail** — the one rail
`M0_AUCTION_FILLS` actually measured at ≈ 0 half-spread (official print on 99.96 % of top-500
symbol-days, 99.5 % at ADV rank 501–1500).

Prices come from `auc0822_cache/panel.npz`, verified **unadjusted** on the NVDA 10:1 of 2024-06-10.
Universe: the auc0822 liquid set (≈489 names/day), corporate-action coverage present, raw price
> $5, ADV floor. Design **2016-01-04 → 2022-12-30** (1,762 sessions), held out
**2023-01-03 → 2026-08-14** (907 sessions), signs frozen to `_DESIGN.json` first.

**Honesty first: family A is not an invention.** It is the ex-dividend drop-off, i.e. `T7`, on a
different rail (close→open rather than close→close) with different weightings. `T7` is **dead**, and
my brief's "ALIVE" list was wrong about it. The genuinely new objects in this round are family B
(does the residual predict the ex-day session), family C (**is the published dividend a free
order-flow meter for the following days**), family D (split ex-dates), and the E-family controls.

---

## 3. THE ρ1 GATE — run before any gross claim, as required

| statistic | value | gate |
|---|---:|---|
| ρ(eps, ex-day open→close) | **+0.029** | pass |
| ρ(eps, ex-day open → ex+1 open) | **+0.037** | pass |
| per-symbol ρ1 of the residual series, mean | **−0.008** | pass |
| per-symbol ρ1, median | −0.021 | pass |
| share of symbols below −0.35 | **6.0 %** (349 symbols) | pass |

No bounce. Structurally there cannot be much: the two prints are **separate auctions ~17.5 hours
apart**, and consecutive residuals for one symbol are a quarter apart. The mirror artefact
(averaged-price momentum) does not apply — no VWAP rail is used. Tick granularity is not the story
either: the median event's price is $83.7 (one penny = 1.19 bp) and the mean residual is 4.9 ticks,
unlike the auction round's 2.0-half-tick dislocation. `C4_EPS_GAP5` carries the one-day-gap
re-entry test inside N and it is noise in both windows.

---

## 4. THE NULLS

Size-matched placebo, pre-registered: per replicate every event's returns are replaced by the
**same symbol's** hedged returns on a nearby **non-event** date (±3…15 sessions, corporate-action
days excluded), all 28 formulas re-scored, maximum |t| taken; 400 replicates. Cohort membership,
cohort size, calendar, universe, weights, turnover and cross-sectional covariance survive; only
"is this date an event" is destroyed. (A rotate-the-returns null is not used — broken, INVENT_0822B §4.2.)

| bar over N = 28 | max &#124;t&#124; |
|---|---:|
| analytic two-sided `sqrt(2 ln 56)` | 2.84 |
| placebo **mean** of the max | 2.28 |
| placebo p50 | 2.21 |
| placebo **p95** | **3.24** |
| placebo p99 | 3.60 |
| programme-cumulative `sqrt(2 ln 2N)`, N ≈ 1,430 | ≈ 3.99 |

**Best design |t| among the 23 candidate formulas: 2.50 (`D1_FWD_GAP`).** It does not reach the
analytic bar, it sits *below* the placebo p95, and it is barely above the placebo **mean** of the
max. There is no winner to argue about.

Placebo/analytic ratio here is **1.14** — a third measurement of the ratio the programme now knows
is book-shaped (1.08 on the auction book, ~2× on overlapping weekly CEF pairs, 1.14 here). Event
books with disjoint holding periods are close to the analytic bar; overlapping books are not.

---

## 5. ALL 28 FORMULAS, NOTHING DROPPED

Design gross/net at the headline cost (3.0 bp/side event legs + 1.0 bp/side hedge), then held out
with the sign frozen. `BE` = break-even one-way event-leg cost. `auct` = net Sharpe at the measured
auction rail (0.5 bp/side).

| formula | fam | sgn | D gross SR | **D gross t** | D net SR | D BE bp | H gross SR | **H gross t** | H net SR | H auct SR | placebo p |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| E3_NOTETHER | E | + | −13.11 | −34.66 | −14.72 | −22.13 | −10.24 | −19.43 | −11.80 | −10.83 | 0.000 |
| E2_SHUFFLE_RATE | E | + | 3.72 | 9.83 | 2.60 | 9.93 | 3.74 | 7.09 | 2.80 | 3.38 | 0.000 |
| D1_FWD_GAP | D | + | 0.94 | **2.50** | 0.84 | 25.8 | 0.55 | 1.04 | 0.36 | 0.48 | 0.010 |
| A10_ADVLO | A | + | 0.81 | 2.15 | −0.70 | 1.61 | −0.09 | −0.17 | −1.41 | −0.58 | 0.038 |
| B2_Y_OC | B | − | 0.77 | 2.05 | −0.21 | 2.37 | 0.12 | 0.23 | −0.79 | −0.03 | 0.053 |
| E4_RUNUP5 | E | + | 0.72 | 1.89 | 0.15 | 3.78 | −0.59 | −1.12 | −1.07 | −0.77 | 0.048 |
| A6_SPECIAL | A | + | 0.66 | 1.75 | 0.59 | 22.5 | 0.57 | 1.08 | 0.48 | 0.53 | 0.108 |
| C4_EPS_GAP5 | C | − | 0.66 | 1.74 | 0.35 | 6.34 | −0.38 | −0.72 | −0.68 | −0.43 | 0.213 |
| A7_REG | A | + | 0.65 | 1.73 | −1.51 | 0.91 | 1.01 | 1.91 | −0.58 | 0.41 | 0.073 |
| A4_YLO | A | + | 0.57 | 1.50 | −0.99 | 1.09 | 0.16 | 0.30 | −0.92 | −0.25 | 0.140 |
| E1_PLACEBO_DATE | E | + | 0.55 | 1.47 | −1.58 | 0.78 | 0.49 | 0.93 | −1.13 | −0.12 | 0.108 |
| A8_IRREG | A | + | 0.49 | 1.29 | −0.43 | 1.59 | 0.92 | 1.74 | −0.02 | 0.57 | 0.195 |
| D2_FWD_H20 | D | − | 0.48 | 1.26 | 0.45 | 47.1 | 0.18 | 0.34 | 0.15 | 0.17 | 0.208 |
| D3_REV_GAP | D | − | 0.44 | 1.16 | 0.39 | 23.9 | 0.76 | 1.43 | 0.74 | 0.75 | 0.285 |
| A1_EQ | A | + | 0.44 | 1.15 | −1.85 | 0.57 | **1.19** | **2.26** | −0.58 | 0.53 | 0.265 |
| B1_EPS_OC | B | − | 0.39 | 1.04 | −0.47 | 1.37 | 0.17 | 0.32 | −0.64 | 0.03 | 0.373 |
| C5_EPSAGG_TS | C | + | 0.37 | 0.98 | 0.23 | 7.80 | −0.58 | −1.10 | −0.78 | −0.78 | 0.353 |
| E5_RUNUP20 | E | + | 0.33 | 0.88 | 0.09 | 4.12 | −0.68 | −1.30 | −0.90 | −0.77 | 0.528 |
| C2_EPS_H5 | C | − | 0.30 | 0.80 | −0.00 | 2.97 | −0.28 | −0.52 | −0.56 | −0.32 | 0.500 |
| C6_EPS_VOLADJ | C | − | 0.30 | 0.78 | −0.05 | 2.60 | −0.48 | −0.90 | −0.81 | −0.53 | 0.498 |
| A2_YW | A | + | 0.26 | 0.70 | −1.88 | 0.37 | 1.06 | 2.02 | −0.57 | 0.45 | 0.480 |
| D4_REV_H20 | D | − | 0.26 | 0.68 | 0.25 | 98.1 | −0.85 | −1.60 | −0.85 | −0.85 | 0.373 |
| A9_ADVHI | A | + | 0.20 | 0.54 | −1.58 | 0.34 | 0.85 | 1.61 | −0.34 | 0.40 | 0.625 |
| A5_YSPREAD | A | + | −0.16 | −0.42 | −2.04 | −0.25 | −0.34 | −0.64 | −1.57 | −0.54 | 0.703 |
| C3_EPS_H20 | C | + | 0.15 | 0.40 | 0.01 | 3.18 | 0.32 | 0.61 | 0.19 | 0.30 | 0.805 |
| B3_GRAW_OC | B | − | 0.12 | 0.33 | −0.73 | 0.44 | −0.10 | −0.19 | −0.93 | −0.24 | 0.768 |
| A3_YHI | A | + | 0.10 | 0.26 | −1.35 | 0.21 | 0.54 | 1.03 | −0.54 | 0.14 | 0.778 |
| C1_EPS_H1 | C | + | 0.02 | 0.06 | −0.63 | 0.11 | −0.48 | −0.90 | −1.12 | −0.58 | 0.975 |

**Family roll-up.**

| family | n | best design t | best held-out t | held-out net-positive at headline |
|---|---:|---:|---:|---:|
| A · ex-day gap capture | 10 | 2.15 | 2.26 | 1 / 10 |
| B · residual → ex-day session | 3 | 2.05 | 0.32 | 0 / 3 |
| C · residual as a demand meter | 6 | 1.74 | 0.61 | 1 / 6 |
| D · split ex-dates | 4 | 2.50 | 1.43 | 3 / 4 (n = 3–52 days) |
| E · controls, inside N | 5 | (34.7, arithmetic) | — | — |

**Sign-stability census over the 23 candidates.** 22 of 23 have a positive design gross t once the
sign is frozen; **14 of 23 are positive in both windows** (a coin gives 11.5) and 14 of 23 are
positive out of sample — i.e. the *direction* is mildly consistent, which is what you expect when a
small real effect (+1.6 → +4.7 bp) sits far below the noise. **Only 5 of 23 are net-positive out of
sample at the headline cost, and 12 of 23 at the measured auction rail.** That gap *is* the finding
for family A: the effect is not zero, it is smaller than the rail.

---

## 6. THE HONEST ESTIMATOR, AND THE COST WALL

`E1_PLACEBO_DATE` compares each event to **one** nearby non-event date, which is a noisy control. The
post-hoc sharpening (`exo0822c_matched.py`, labelled post-hoc, a-priori sign) uses the **mean of
every eligible non-event date in ±3…15 sessions** — 23.6 control days per event on average — which
cuts the control's variance contribution by an order of magnitude without changing the estimand.

| ordinary cash dividends | design | held out |
|---|---:|---:|
| n events / days | 10,228 / 1,588 | 5,516 / 830 |
| mean hedged ex-day residual | +1.53 bp (t 1.16) | +5.38 bp (t 2.25) |
| **matched control** (same names, non-event dates) | **−0.05 bp (t −0.16)** | +0.67 bp (t 1.14) |
| **event − control** | **+1.58 bp (t 1.17)** | **+4.71 bp (t 1.89)** |
| yield-weighted event − control | −1.66 bp (t −0.57) | +7.57 bp (t 2.02) |
| domestic issues only | +4.81→ see §1 | +5.07 bp (t 2.02) |
| foreign / ADR issues (tether mis-stated by withholding) | n 279 | n 344, t 0.96 |

The control coming in at **−0.05 bp** is the single cleanest number in the round: the hedge is
unbiased, so the event-day figure is the whole effect, and the whole effect is **1.6 bp**.

**The cost arithmetic that ends it.** The trade is one round trip per event: buy in the cum-day
closing cross, sell in the ex-day opening cross, plus a hedge leg.

| rail | event leg | hedge leg | round-trip | design residual | held-out residual |
|---|---:|---:|---:|---:|---:|
| headline (Dyhrberg liquid taker 2.5 + 0.5 fee) | 6.0 bp | 2.0 bp | **8.0 bp** | +1.6 bp ✗ | +4.7 bp ✗ |
| shock | 12.0 bp | 2.0 bp | 14.0 bp | ✗ | ✗ |
| **measured auction rail** (M0, ≈0 spread) | 1.0 bp | 2.0 bp | **3.0 bp** | ✗ | +1.7 bp, t ≈ 0.7 |

Even on the rail the programme has actually *measured at zero*, the held-out edge nets ~1.7 bp/event
with a t under 1, and the design window nets negative. Break-evens in §5 confirm it from the other
side: every family-A cell breaks even between **0.2 and 2.4 bp/side**, i.e. below the 2.5 bp liquid
taker half-spread the repo charges. This is `EXECUTION_COST_WALL`'s conclusion arriving from a fresh
direction: *the signal is not cost-killed, it is too small to certify, and the cost is the
messenger.*

Two further gradients, both post-hoc and both recorded so they are not re-discovered: the residual
is larger in **low-ADV** names (design +7.7 bp t 3.8 pre-dedup, and the low-ADV cell `A10_ADVLO` is
the one that flips hardest out of sample, −0.17), and it is larger where a **tick is a larger
fraction of price** — the classic shape of a limits-to-arbitrage effect that also cannot be traded.

---

## 7. THE E-FAMILY CONTROLS EARNED THEIR PLACE IN N

* **`E3_NOTETHER`** — the same gap with **no** published rate subtracted: design gross SR **−13.1**,
  −53 bp/day, held out −10.2. That is the mechanical dividend drop, and it is the size of the term
  the published tether removes. **The tether is not creating signal; it is cancelling a term ~15×
  larger than the signal.** Any error in it therefore shows up magnified.
* **`E2_SHUFFLE_RATE`** — the tether replaced by a **wrong** published rate (rates permuted within
  the day, applied to both the residual and the weights): design gross SR **+3.72 (t 9.83)**, held
  out **+3.74 (t 7.09)**. This is a pure arithmetic artefact — weighting by the wrong rate correlates
  with the error the wrong rate injects — and it is the most useful cell in the round, because it
  quantifies lesson 4's failure mode: **a mis-specified published tether manufactures a Sharpe near
  4 in both windows out of nothing at all.** That is exactly what the duplicated cache did, in
  miniature, to family A. Note also that this control *scores*, so it must never be read as evidence;
  it is filed as a diagnostic of arithmetic.
* **`E1_PLACEBO_DATE`** — design gross t +1.47, held out +0.93, and its multi-day sharpening returns
  −0.05 bp. The hedge is clean.
* **`E4/E5_RUNUP`** — the dividend run-up: design +1.89 / +0.88, held out **−1.12 / −1.30**. Dead.

---

## 8. WHAT DIED THAT WAS ACTUALLY NEW

* **The residual as a free order-flow meter (family C, 6 formulas).** This was the round's original
  claim: because the mechanical drop is published, the ex-day gap is a clean measurement of
  unexpected demand on ~9 names a day, at no cost, since 2016. It carries **nothing**. Design gross
  t: 1.74, 0.98, 0.80, 0.78, 0.40, 0.06 — the whole family under the placebo *mean*. Held out, five
  of six are negative. Horizons 1/5/20 days, vol-normalised, aggregated to a time-series market
  signal, and with a one-day entry delay — all noise. The interpretation I believe: the ex-day
  residual is 1.6 bp against a daily σ of ~200 bp, so even if it *were* pure order flow its
  signal-to-noise as a predictor is ~1 %.
* **The ex-day session (family B, 3 formulas).** Best design t 2.05, best held-out t 0.32.
* **Split ex-dates (family D, 4 formulas).** `D1_FWD_GAP` is the round's best design cell
  (t 2.50, matched +68.8 bp t 2.59) and it collapses to held-out t 1.04 / matched +10.0 bp
  (t 0.45) on 52 events. The reverse-split cohort keeps its a-priori negative sign in both windows
  (matched −61 bp design, −225 bp held out) but on **35 events total** it has no power and cannot
  be certified; recorded, not claimed. Special dividends likewise: +44 bp design, +38 bp held out,
  t 1.42 / 0.85 on 49 events.

---

## 9. HONEST LIMITATIONS

1. **Family A is a re-run of T7** on a different rail. Not an invention. My brief listed T7 as
   ALIVE; `T7_RESULT.md` and `EDGE_SHORTLIST.md` both say it is dead. The ledger should be corrected.
2. **A held-out read happened on the buggy panel.** After the design signs were frozen (legitimate)
   but before the duplication was found, I read the held-out matched estimator and saw +9.39 bp
   (t 3.69). No sign or rule was changed as a result — the matched estimator's sign is a-priori —
   but the 2023-01 … 2026-08 calendar has now been read twice by this round, and it was already the
   programme's third pass over that window.
3. **The full-sample descriptive line was printed before the split** (disclosed in the
   pre-registration §6): it revealed the four event-class signs, all of which were pre-registered
   `apriori` from the literature and could not be re-chosen.
4. **`advusd` in the auc0822 panel is not a per-day dollar figure** (median $6.2 B across a ~489-name
   universe), so it is a *rank* here and no capacity number is quoted in dollars. The ADV floor was
   therefore non-binding; the universe filter that actually bites is `in_uni`.
5. **Survivorship.** Alpaca serves symbols that exist today; the auc0822 universe inherits that. It
   biases family A *toward* the surviving dividend payers, so the honest reading of a null result is
   conservative.
6. **`ca_covered` is 76 % of the panel's symbols.** The universe is restricted to covered names for
   exactly this reason, which costs sample but avoids unflagged drops polluting the benchmark.
7. **Foreign / ADR issues carry a mis-stated tether** (published gross rate vs. a withheld receipt).
   They are 3–6 % of events, are reported separately, and carry a t under 1 in both windows.
8. **Non-fill risk on the ex-day opening cross is not modelled.** M0 measured print *availability*
   (99.96 % top-500) but never measured whether our order joins the cross; the opening cross is also
   ~8× smaller than the closing cross ($4.8 M vs $37 M median). The auction-rail row of §6 is
   therefore an upper bound on a thing that is already too small.
9. **Tax.** T7 §6 already did this arithmetic and it is worse here: the trade is *long* across the
   ex-date, so it books non-qualified dividend income against short-term capital losses.

---

## 10. WHAT THIS ADDS TO THE LEDGER

**Dead, searched, on US equities 2016–2026, on properly deduplicated published rates:**

1. Ex-day gap capture at the MOC→MOO auction rail (equal, yield-weighted, yield-tercile,
   yield-spread, special-only, regular/irregular payer, ADV-split) — 10 formulas. Sub-bar on design,
   below the rail out of sample. Adds a second rail to T7's verdict.
2. The published-gap residual as a predictor of the ex-day session — 3 formulas.
3. **The published-gap residual as a free order-flow meter** at 1/5/20 days, vol-normalised,
   aggregated, and delayed one session — 6 formulas. This was the new idea and it is noise.
4. Forward- and reverse-split ex-date gap and 20-day drift — 4 formulas. Right signs, no power
   (35–122 events); do not re-propose without an unbiased split calendar.
5. The dividend run-up at 5 and 20 sessions — 2 formulas.

**Method / infrastructure findings worth more than the formulas:**

6. **`corporate_actions_all.json.gz` carries 26,038 duplicated cash-dividend records, 37 duplicated
   forward splits and 207 duplicated reverse splits.** Dedupe on `id` then on
   `(symbol, ex-date, rate)`. Six scripts read it. The bug inflates, so dead cells stay dead and
   live cells need re-checking.
7. **A mis-specified published tether manufactures a Sharpe near 4 in both windows** (`E2`), and the
   term the tether cancels is ~15× the signal (`E3`). Lesson 4 needs a corollary: *when the tether
   is published, verify the publication before trusting the residual* — the residual inherits the
   feed's errors magnified by the ratio of drop to alpha.
8. **A matched multi-control-day estimator is worth ~10× the power of a single-control-day placebo**
   on event studies, at no cost in bias. Use it as the standard E-family control from now on.
9. Placebo/analytic ratio on a disjoint-holding **event book: 1.14** (third measurement; 1.08 on the
   auction book, ~2× on overlapping weekly pair books). The inflation lives in overlap.
10. The ρ1 gate passes cleanly on a two-auction, quarter-spaced residual (+0.03, −0.008 per-symbol);
    this is the first anchored spread in the programme where bounce is structurally absent.

Cumulative distinct formulas after this round: **≈ 1,430** (`sqrt(2 ln 2N)` ≈ 3.99).

---

## 11. ARTIFACTS

`research/trading_bot/INVENT_0822C_gaptether.{md,json}`,
`_PREREGISTRATION.md` (sha256 `987b283f…`), `_DESIGN.json`, `_HOLDOUT.json`, `_NULLS.json`,
`_MATCHED.json`, `_FOREIGN.json`, `_DIAG_design.json`.
Code `scripts/trading_bot/exo0822c_{panel,sweep,nulls,diag,matched,foreign}.py`.
Panel `research/data/exo0822c/events.npz` (15,966 events, 2,669 sessions).
No git commits, no orders, BASKET1 untouched, no network access used — every input was already cached.
