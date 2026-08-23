# INVENT_0823 — INTRADAY MICROSTRUCTURE BEYOND THE AUCTION

**Date:** 2026-08-23 · research only, cached/free data, no orders, no money.
**Pre-registration:** `INVENT_0823_intramicro_PREREGISTRATION.md` (commit `01ef87c`, written and
committed before any design number existed). **Frozen shortlist:** commit `0f13929`, written
before the held-out window was read.

---

## 0. Verdict — the theme is NOISE, and it fails one gate earlier than the last one did

**28 structurally different low-turnover intraday formulas. Zero clear the noise bar. Zero clear
it on GROSS either.**

| | |
|---|---|
| formulas scored | **28** |
| bootstrap best-of-28 **net** p95 (the operative bar) | **+1.41** |
| bootstrap best-of-28 **gross** p95 | **+1.40** |
| best design **net @ 1.0 bp/side** | `E4_PDPOC_MAGNET` **+0.21** |
| best design **gross** | `F2_LD_REV` **+1.34** |
| configs beating the net bar | **0 / 28** |
| configs beating the **gross** bar | **0 / 28** |
| best design-window break-even | 1.41 bp/turnover (`E4`), vs a 1.15 bp charge |
| held-out net @1.0 bp of every shortlisted config | **negative** (−0.50, −0.57, −0.61, −2.20) |

The one config that was net-positive on design, `E4_PDPOC_MAGNET` (previous session's
volume-profile point-of-control as a magnet for the post-open price), **fails the pre-registered
one-bar-gap gate** — +0.21 with the fill at bar *s+1*, **−0.03** with the fill at bar *s+2* — and
then prints **−0.57** out of sample. It is a design-window fluke, exactly what a best-of-28
selection is supposed to produce when nothing is there.

**This is a harder negative than `SWEEP_intraday_rv`.** That sweep found a large, replicable
*gross* edge (design +6.86, held-out +5.41) that was unreachable only because of friction — 50 of
its 98 configs beat the gross bar. **Here, 0 of 28 beat the gross bar.** The difference between
the two rounds is exactly the two things this round changed: the holding period went from minutes
to hours, and the fill stopped sharing a print with the signal. When you remove those two things,
the intraday "edge" does not shrink below the spread — **it disappears before a single basis point
of cost is charged.** That is a statement about what the earlier gross number was made of.

---

## 1. What was tested, and why it is not the last sweep again

The prior intraday sweep killed the *relative-value / mean-reversion* branch: pair-z, ETF-vs-basket,
PCA residual, high-frequency cross-sectional reversal, all at 20–130 units of turnover per day with
break-evens of 0.01–0.30 bp. Its own verdict was that the signal *was* the bid-ask bounce.

So this round refused that entire branch by construction. **Every formula here trades ≤ 3 units of
turnover per day** (in practice 1.88–2.00), holds for hours rather than minutes, and is directional
in the cross-section rather than a spread convergence. At turnover 2.0/day the 1.0 bp rung charges
2.3 bp/day against a book with ~40–60 bp/day of return sd — a ~0.6–0.9 Sharpe drag, a hurdle rather
than a 37× wall. This is the only region of intraday where an answer other than "friction" was
still possible. It came back "no signal".

### The six sub-families

| family | n | idea | best design gross | best design net@1bp | best break-even |
|---|---|---|---|---|---|
| **A** opening drive | 5 | does the first 15–30 min of *intraday* tape predict the rest of the session, cross-sectionally? | +0.60 (`A5_DRIVE_EX_GAP`) | −0.18 | 0.89 bp |
| **B** order flow / trade size | 5 | close-location-value × dollar-volume; average trade size vs the name's own 20-day norm; volume front-loading; trade-count acceleration | +0.12 (`B2_OFI_MORN_FADE`) | −0.98 | 0.10 bp |
| **C** VWAP deviation | 4 | fade/follow the deviation from the running session VWAP at 10:25 and 12:00, with a later fill | +0.73 (`C1_VWAPDEV_MID_REV`) | −0.73 | 0.58 bp |
| **D** opening-range breakout | 4 | first-hour and first-30-min range, break and extension, honest slippage | +0.23 (`D2_ORB_FADE_XS`) | −1.06 | 0.21 bp |
| **E** volume-profile value area | 4 | 20-bin dollar-volume profile, 70% value area, POC magnet, previous-session POC | **+1.12** (`E4_PDPOC_MAGNET`) | **+0.21** | **1.41 bp** |
| **F/G** late-day drift | 6 | last 30–45 min, on 34 mega-caps and on the point-in-time top-500 | **+1.34** (`F2_LD_REV`) | −0.33 | 1.00 bp |

Sub-family **B** is the genuinely new instrument here: it uses the 5-minute bars' **trade count**
and **high/low**, fields the earlier panel did not carry, to build order-flow and participation
proxies rather than another price-reversion. It is the *deadest* family of the six — best gross
+0.12, best break-even 0.10 bp. Institutional-participation proxies built from free bar data carry
no cross-sectional information about the rest of the session.

---

## 2. The anti-bounce design, and the fact that it fired

ρ1(Δspread) is what killed auction-imbalance and manufactured the ETFRV leg. On a 5-minute cube the
equivalent discipline is a fill that never shares a print with the signal, plus a **one-bar-gap
re-entry test**, both frozen in §3 of the pre-registration:

- signal observes bars `0..s`; **primary fill = VWAP of bar `s+1`**; **gap fill = VWAP of bar `s+2`**;
- unconditional exit at the VWAP of bar 77, so the exit carries no signal;
- Panel B: signal from open→15:29, primary fill at the 15:49 print, gap fill at 15:59, exit in the
  closing auction (charged 0 bp of spread — M0 *measured* the official print on 99.96% of top-500
  symbol-days — but still charged the 0.15 bp regulatory fee);
- **gate:** gap net Sharpe must be ≥ 0.5 × primary net Sharpe *and* positive, or the config is a
  bounce artefact and is disqualified however large its primary number.

**The harness self-test proves the gate can actually see a bounce** (`_selftest.json`): a planted
signal is recovered at gross +31.85 and mirrors to −32.49 under negation; a random score returns
−0.22; and a deliberately planted **one-bar artefact** (a score that is literally the next bar's
return) scores **+7.84 primary and collapses to +1.53 under the gap fill**. All four checks pass.

### The gate fired on the broad late-day family, and named the mechanism

`G1_LD500_CONT` — buy the day's cross-sectional winners at 15:49, exit in the closing auction, over
the point-in-time top-500 — looks like a modest positive on design (gross +0.55). Decomposing the
hold (`_DIAG.json`) shows where that lives:

| leg | design gross bp/day | design Sharpe |
|---|---|---|
| **full hold, 15:49 → close** | +0.399 | +0.55 |
| 15:49 → 15:59 (the ten minutes the gap test removes) | **+0.605** | +0.83 |
| 15:59 → close | **−0.207** | **−2.27** |

**152% of the gross sits in the ten minutes immediately after the signal, and the position then
*loses* into the closing auction at Sharpe −2.27.** That is not late-day drift; that is a
short-lived continuation of the signal print which then reverses into the close — the same object
that died on ρ1 in the auction-imbalance round, seen from the other side. Its gap-filled net Sharpe
is −16.4 on design, −19.1 held out, −22.0 on the 2016–2020 pre-sample. Both signs of it lose:
`G2_LD500_REV` is −2.33 design, and the pre-sample flips the raw sign of `G1` outright (gross
−0.27 over 2016–2020 vs +0.55 over 2021–2024).

For the mega-cap late-day reversal `F2_LD_REV`, the first-bar contribution flips sign between the
two windows — **−0.10 bp/day (−10% of gross) on design, +1.03 bp/day (+62% of gross) held out** —
which is itself the tell: a component that changes sign across windows is noise, not mechanism.

---

## 3. Both nulls

**Null 1 — size-matched placebo / best-of-N.** Stationary block bootstrap (block = 5 sessions,
2000 resamples) of each config's demeaned daily PnL, drawing the **same day indices for every
config** so the sweep's internal correlation survives.

| statistic | net @1.0 bp | gross |
|---|---|---|
| mean best-of-28 | +0.94 | +0.94 |
| **p95 (the bar)** | **+1.41** | **+1.40** |
| p99 | +1.68 | +1.63 |
| naive √(2 ln 28)/√years | +1.29 | — |

The analytic number understates the bootstrap bar by ~9% here, consistent with the standing note
that it understates on overlapping books.

**Null 2 — ADV-slot signal permutation.** Symbols are bucketed into ADV deciles *within each day*
and the score vector is permuted **within** buckets, destroying the symbol↔score mapping while
preserving the day, the liquidity profile and the score distribution. 500 permutations.
Rotate-the-returns is not used.

**A methodological correction, disclosed rather than buried.** The null stage first ran this
permutation on the **net** series, which is mis-specified: a permuted book still pays full cost, so
the null distribution sits far below zero and *any* config with a non-negative gross "beats" it —
`E4` scored p = 0.004 against a null p95 of **−0.33**, which is meaningless. The permutation was
re-run on **gross**, which is the question the permutation actually answers
(`_permgross.json`, `im0823_permgross.py`):

| config | observed gross | perm null mean | perm null p95 | one-sided p |
|---|---|---|---|---|
| `F2_LD_REV` | +1.34 | +0.51 | +1.00 | 0.008 |
| `E4_PDPOC_MAGNET` | +1.12 | +0.31 | +0.84 | 0.008 |
| `F3_LD_VWAPDEV_REV` | +1.10 | +0.29 | +0.83 | 0.010 |
| `C1_VWAPDEV_MID_REV` | +0.73 | −0.07 | +0.36 | 0.002 |
| `A5_DRIVE_EX_GAP` | +0.60 | +0.21 | +0.68 | 0.092 |
| `G3_LD500_CONT_TOP150` | +1.11 | +0.55 | +1.31 | 0.130 |
| `G1_LD500_CONT` | +0.55 | +0.38 | +1.19 | 0.345 |

Four configs carry a *per-config* p < 0.01. **This does not make them real, and saying so is the
whole point of running the first null too.** The permutation p-value is uncorrected for the 28
draws that produced the ranking; the family-wise bar for that is the best-of-28 bootstrap, and the
largest gross in the sweep (+1.34) sits **below** it (+1.40). A p-value computed on the winner of a
28-way search is not evidence, and every one of these configs then fails on cost and out of sample
anyway. Note also that the permutation null's *mean* is positive (+0.21 to +0.55): the score
*magnitude* profile alone, with the symbol mapping destroyed, already earns something, so the
observed numbers are less anomalous than they look against zero.

---

## 4. Held-out — the documented negative control

Nothing cleared, so per §7 the top 3 by design net Sharpe ran out of sample **as a negative
control, not as candidates**, plus one explicitly labelled addition (`F2_LD_REV`, the highest
design gross) to test whether the *before-cost* signal persists.

| config | design gross | HELD-OUT gross | design net@1bp | **HELD-OUT net@1bp** | held-out net@0.5bp | held-out gap net@1bp | held-out break-even |
|---|---|---|---|---|---|---|---|
| `E4_PDPOC_MAGNET` | +1.12 | +0.23 | **+0.21** | **−0.57** | −0.22 | −0.67 | 0.33 bp |
| `A5_DRIVE_EX_GAP` | +0.60 | +0.17 | −0.18 | **−0.50** | −0.21 | −0.33 | 0.29 bp |
| `F2_LD_REV` *(added, highest gross)* | +1.34 | +1.56 | −1.54 | **−0.61** | +0.33 | −1.73 | 0.83 bp |
| `G3_LD500_CONT_TOP150` | +1.11 | −1.20 | −0.33 | **−2.20** | −1.81 | −19.14 | −1.58 bp |

Every held-out net Sharpe is negative at the headline rung. `E4`'s design edge does not merely
shrink — its break-even falls from 1.41 bp to 0.33 bp, i.e. **77% of the thing that made it
net-positive is gone.** `G3` inverts outright.

`F2_LD_REV` is the only config whose *gross* both persists (+1.34 → +1.56) and clears 0.5 bp/side
net (+0.33 held out). It is still not a signal: it is below the noise bar on design gross, its
break-even of 0.83 bp is under the 1.13 bp measured liquid-name half-spread, its gap-filled net is
−1.73, and its gross decomposition changes sign between windows. It is reported because it is the
strongest thing in the sweep and the strongest thing in the sweep is not enough.

### Panel-B pre-sample (declared in advance, cannot promote anything)

Over 2016-01-04 → 2020-12-31 (1259 sessions, point-in-time top-500):
`G1_LD500_CONT` gross **−0.27** / net −2.28, `G2_LD500_REV` gross +0.27 / net −1.73,
`G3_LD500_CONT_TOP150` gross **−0.53** / net −2.12. The raw sign of the broad late-day drift is not
stable across the 2016–2020 and 2021–2024 halves. Five extra years of a broader, genuinely
point-in-time universe say the same thing the design window said, more loudly.

---

## 5. Distribution of all 28, design window

| rung | min | p10 | p25 | median | p75 | p90 | max | # net-positive |
|---|---|---|---|---|---|---|---|---|
| gross (0 bp) | −1.34 | — | — | — | — | — | **+1.34** | 14 of 28 |
| net 0.5 bp/side | — | — | — | −0.69 | — | — | +0.61 | **3** |
| **net 1.0 bp/side** | −4.23 | −2.10 | −1.55 | **−1.23** | −0.92 | −0.47 | **+0.21** | **1** |
| net 2.0 bp/side | — | — | — | −2.28 | — | — | −0.59 | **0** |
| net 2.5 bp/side | — | — | — | −2.73 | — | — | −0.98 | **0** |

The median config loses ~1.2 Sharpe to friction, not ~28 as in the RV sweep — the low-turnover
design did exactly what it was meant to do to the cost side. It just found nothing to spend the
budget on. Fourteen of 28 have positive gross, which is what you expect from 28 draws of noise
under seven sign-flipped pairs: **the sign-pairs are constructed so that the count is ~14 whatever
happens, and the informative number is the size of the largest, +1.34 against a +1.40 bar.**

---

## 6. Method

- **Design** 2021-01-04 → 2024-12-31 (1005 sessions). **Held out** 2025-01-02 → 2026-08-14 (405
  sessions), untouched until commit `0f13929`. **Pre-sample** (Panel B only, declared in advance)
  2016-01-04 → 2020-12-31 (1259 sessions).
- **Panel A** — Alpaca SIP 5-minute bars, `adjustment=all`, RTH, rebuilt into a
  (1410 days × 78 slots × 132 symbols) cube carrying open/high/low/close/VWAP/dollar-volume/
  **trade-count**. Universes: `MEGA` (34 single names), `LIQETF` (49 unlevered, non-same-claim
  ETFs — levered/inverse funds and same-claim siblings are excluded so no config can rediscover the
  ETFRV artefact).
- **Panel B** — the point-in-time top-500-ADV minute panel (1611 symbols ever, median 497/day,
  2016–2026) with 15:29 / 15:49 / 15:59 prices plus the official open and close. All Panel-B
  returns are strictly within one session, so its raw unadjusted prices are safe; **no overnight
  return is ever computed on Panel B.**
- **Weights** cross-sectionally demeaned (dollar-neutral) and L1-normalised to gross 1.0; turnover
  1.88–2.00/day.
- **Costs** 0.5 / 1.0 / 2.0 / 2.5 bp per side on |Δw|, headline 1.0 bp, plus 0.15 bp/turnover for
  SEC 31 + FINRA TAF. Provenance `ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG`; repo-measured liquid-name
  close half-spread is 1.13 bp (T3, 19,835 symbol-days), Dyhrberg et al. (JFE 168, 2025) put the
  liquid retail taker at 2.5 bp before price improvement. Borrow = 0, and that is exact: every
  config is flat at every close.
- **Survivorship** Panel A is survivorship-biased (Alpaca serves today's symbols) and its prices
  are retroactively adjusted; no config filters on a price level. Panel B *is* point-in-time in
  membership and is the honest breadth check on Panel A's survivor set — and it agrees.

---

## 7. What this closes

1. **Continuous intraday is not "different" from the auction in the way the theme hoped.** The
   auction family died on ρ1; the continuous late-day family here dies on the same object, detected
   by the gap test instead of by ρ1: 152% of `G1`'s gross is a ten-minute continuation of the signal
   print that then reverses into the close.
2. **Low turnover removes the friction excuse and reveals there was no gross edge.** The RV sweep's
   +6.86 gross was a minutes-long, same-print artefact. Hold for hours and fill on later prints and
   the largest gross in 28 tries is +1.34 against a +1.40 noise bar.
3. **Bar-level order-flow proxies are empty.** Close-location-value × volume, average trade size
   versus the name's own norm, volume front-loading and trade-count acceleration are the deadest of
   the six families (best gross +0.12, best break-even 0.10 bp). Free 5-minute bars do not carry
   recoverable order-flow information about the rest of the session.
4. **A permutation null on a net series is mis-specified.** Recorded here as a reusable finding: it
   prices "beats a random book that pays the same cost", which any non-negative-gross config does.
   Run the cross-sectional permutation on **gross**, and correct it for the search that produced
   the ranking — or it will hand you p = 0.004 for a config that is about to print −0.57 out of
   sample.

**Nothing from this theme goes near the basket.** The sized basket remains the four legs from the
2026-08-23 v9 scrub — T3, DUALCLASS, T12 CEF discount, ORB(daily) — unchanged by this round.

---

## Artifacts

| what | path |
|---|---|
| pre-registration (committed first) | `research/trading_bot/INVENT_0823_intramicro_PREREGISTRATION.md` |
| frozen shortlist (committed before held-out) | `research/trading_bot/INVENT_0823_intramicro_SHORTLIST.md` |
| harness self-test | `research/trading_bot/INVENT_0823_intramicro_selftest.json` |
| design results (28 configs, both fills, 4 rungs) | `research/trading_bot/INVENT_0823_intramicro_design.json` |
| nulls (bootstrap + net permutation) | `research/trading_bot/INVENT_0823_intramicro_null.json` |
| permutation on gross (the corrected one) | `research/trading_bot/INVENT_0823_intramicro_permgross.json` |
| held-out | `research/trading_bot/INVENT_0823_intramicro_heldout.json` |
| Panel-B pre-sample | `research/trading_bot/INVENT_0823_intramicro_presample.json` |
| gross decomposition diagnostic | `research/trading_bot/INVENT_0823_intramicro_DIAG.json` |
| code | `scripts/trading_bot/im0823_{panel,sweep,selftest,diag,permgross}.py` |
| 5-min cube | `research/data/im0823_cache/cube.npz` |
