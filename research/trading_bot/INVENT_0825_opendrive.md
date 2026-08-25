# INVENT_0825 — OPEN-DRIVE / CLOSE-DRIVE INTRADAY MICROSTRUCTURE

**Date:** 2026-08-25 · research only, cached/free data, no orders, no money.
**Formulas pre-registered and scored: 26** (24 distinct books — see §1) · **Survivors: 0**
**Verdict: NOISE as a tradable claim — but for the first time in this family, not noise as a
statistic.**

Pre-registration `INVENT_0825_opendrive_PREREGISTRATION.md` (commit `1f3f6a9`, written and
committed together with the harness and its self-test, before any design number existed).
Frozen shortlist `INVENT_0825_opendrive_SHORTLIST.md` (commit `56129f7`, written before the
held-out window was read).

---

## 0. The one-paragraph answer

Three of this theme's four bullets were already dead: `INVENT_0823_intramicro` killed opening-drive
continuation, late-day "close drive" and first-hour-range breakouts across 28 formulas, and it
killed them **on gross**. So this round was pre-registered as a *disjointness sweep* — 26 formulas,
none a re-parameterisation of an 0823 config, built on three instruments 0823 never touched: the
**official opening-auction print**, first-hour **path efficiency / choppiness**, and the
**opening-print dislocation**. Twenty-five of the 26 are noise. The twenty-sixth is the one bullet
0823 had *not* tested — **fade the overnight gap, cross-sectionally, in the last half hour of the
session** — and it is the first thing this family has produced that is statistically real:
design gross **+2.36** against a best-of-26 bootstrap bar of **+1.44** (above the p99 of +1.72,
so family-wise p < 0.01), ADV-decile permutation **p = 0.0020**, an anti-artefact decomposition
that is the *mirror image* of the one that killed 0823's `G1` (**1.7%** of the gross in the first
bar after entry, versus `G1`'s 152%), and it **replicates out of sample at gross +2.09 with a
larger bp/day (+1.44 → +1.81)**. It is still not promoted, because it is inside the spread on
every rail this repo can honestly price: on the best such rail — 15:49 entry, closing-auction exit
— the held-out effect is worth **0.93 bp per unit turnover against a repo-measured 1.13 bp
half-spread.** It gets **82% of the way to its own cost** and stops. Held-out net @ 1.0 bp is
**−0.57**. Zero of the four pre-registered promotion gates' conjunction is met.

---

## 1. What was tested, and the degeneracy found in it

| family | n | new instrument | best design gross |
|---|---|---|---|
| **PA path shape** | 4 | first-hour path efficiency ER = \|r60\|/Σ\|5-min moves\|, and sign-flip choppiness | +0.43 |
| **PA range-scaled drive** | 4 | first-hour range as a *scaler* of the drive, not a breakout level | +0.30 |
| **PA opening-print dislocation** | 3 | official open ÷ VWAP(first 5-min bar) − 1 | +0.60 |
| **PA open-drive → close-drive** | 3 | 30-minute terminal hold, signal from the morning | **+2.36** |
| **PB gap vs the opening auction** | 7 | the official opening auction print, 2016–2026 point-in-time top-500 | +0.85 |
| **PB vol-scaled drive** | 5 | drive normalised by its own trailing σ (0823 only tested the raw sign) | +0.58 |

**Degeneracy, disclosed rather than buried.** Because every book is cross-sectionally demeaned
before it is normalised, subtracting the cross-sectional mean of a score is a no-op:
`PB_IDIOGAP_FADE` is numerically identical to `PB_GAPZ_FADE`, and `PB_DRIVE_EXMKT_FADE` to
`PB_DRIVEZ_FADE`. **The 26 pre-registered formulas are 24 distinct books.** The bootstrap was run
on the 26 series as pre-registered; duplicates cannot raise a maximum, so this is the conservative
choice. Reusable lesson: *in a dollar-neutral sweep, "market-adjusted X" and "X" are the same
formula, and pre-registering both inflates the apparent breadth of the search without inflating
the bar.*

## 2. The one that is real on gross: `PA_GAP_CD_FADE`

Score = −(overnight gap ÷ its own trailing-60-day σ), clipped at ±5. Universe = 34 mega-caps.
Signal is fully known at 09:30. **Entry = VWAP of bar 71 (15:35–15:40). Exit = VWAP of bar 77
(15:55–16:00), unconditional.** Turnover 1.87–2.00/day. Flat at every close, so borrow = 0 exactly.

| | design 2021–2024 | **held out 2025–2026** |
|---|---|---|
| gross Sharpe | **+2.36** | **+2.09** |
| gross bp/day | +1.44 | **+1.81** |
| break-even (bp / unit turnover) | 0.77 | 0.90 |
| net @ 0.5 bp/side | +0.37 | **+0.59** |
| **net @ 1.0 bp/side (headline)** | −1.16 | **−0.57** |
| net @ 2.0 / 2.5 bp/side | −3.60 / −4.83 | −2.87 / −4.03 |
| one-bar-gap fill, gross | +2.46 | +1.25 |

### It passes every anti-artefact test that killed the previous round

1. **Hold decomposition.** 0823's `G1_LD500_CONT` had **152%** of its gross in the ten minutes
   immediately after the signal print, then lost into the close at Sharpe −2.27 — the ρ1 object seen
   from the other side. Here: bar 71→72 carries **+0.02 of +1.44 bp/day = 1.7%**; bars 72→77 carry
   **98.3%**. The gap fill scores *higher* than the primary fill on design (+2.46 vs +2.36).
2. **Entry-slot profile — positive at all ten slots tested.** Gross bp/day falls monotonically as
   the hold shortens and gross Sharpe rises as late-day noise falls, which is what a smooth
   all-session drift looks like and is not what a single-slot fluke looks like:

| entry bar | 6 | 12 | 24 | 36 | 48 | 60 | 66 | **71** | 74 | 76 |
|---|---|---|---|---|---|---|---|---|---|---|
| gross Sharpe | +1.47 | +1.10 | +0.33 | +1.28 | +1.64 | +2.01 | +2.23 | **+2.36** | +2.05 | +0.76 |
| gross bp/day | 3.69 | 2.38 | 0.61 | 1.96 | 2.03 | 2.00 | 1.78 | **1.44** | 0.96 | 0.20 |

3. **Monotone dose–response in the signal magnitude.** Split by |gap z|: small tercile
   **−0.37 bp/day**, mid **+0.34**, large **+1.54**.
4. **Both nulls.** Best-of-26 block bootstrap (block = 5 sessions, 2000 resamples, same day indices
   for every config): gross mean +0.93, **p95 +1.44**, p99 +1.72; net p95 +1.41; analytic
   √(2 ln 26)/√years = +1.28, understating the bootstrap by 12% as the standing note predicts.
   **+2.36 is above the p99, so the family-wise p is < 0.01.** ADV-decile signal permutation on
   **gross** (500 draws, permuted *within* within-day ADV deciles, never rotate-the-returns):
   observed +2.36 vs null mean +0.89 / p95 +1.49, **p = 0.0020**.

## 3. Why it is not promoted anyway — three independent kills

### 3.1 It is inside the spread on the pre-registered rail

Break-even 0.77 bp (design) / 0.90 bp (held out) per unit turnover, against the repo-measured
liquid-name half-spread of **1.13 bp** (T3, 19,835 symbol-days) and Dyhrberg et al.'s 2.5 bp liquid
retail taker. Held-out net @ 1.0 bp = **−0.57**. Gate 4 of the pre-registration fails outright.

### 3.2 The rail that could have rescued it can only be priced where the signal is absent

The pre-registered exit is a bar-77 VWAP, which pays a full spread. The obvious improvement is to
exit in the **closing auction** — 0 bp of spread, because M0 *measured* the official print on 99.96%
of top-500 symbol-days. The 5-minute cube has no official close, so this was run post-hoc on
Panel B restricted to **the same 34 mega-cap names**, holding the universe fixed and changing only
the rail (`INVENT_0825_opendrive_AUCTIONRAIL.json`): entry at the 15:49 print, exit in the auction.

| window | gross Sharpe | bp/day | break-even (bp/turnover) | net @ 0.5 | net @ 1.0 |
|---|---|---|---|---|---|
| pre-sample 2016–2020 (1259 d) | +2.60 | 1.28 | **1.35** | +1.06 | **+0.10** |
| design 2021–2024 (1005 d) | +1.23 | 0.57 | 0.57 | −0.49 | −1.57 |
| **held out 2025–2026 (405 d)** | **+1.45** | 0.92 | **0.93** | +0.20 | **−0.58** |

The gross is positive in all three windows across **eleven years**, which is the strongest
persistence anything in this family has shown. It is still not enough: net @ 1.0 bp is negative in
two of three, and the only positive one is the *oldest* window, when spreads were wider — the wrong
direction for an execution story. **And that table is an upper bound, not a fair estimate:** the
10-minutes-later control shows **75% (design) and 87% (held out) of the return arriving in the ten
minutes right after the 15:49 entry**, and a single print is exactly the bounce-prone object that
a 5-minute VWAP fill damps. The clean-fill Panel-A number (§2) is the honest one, and it is the
smaller one.

### 3.3 The breadth version is zero, and the mechanism claim does not hold out

- **Point-in-time top-500, no survivorship bias** (`PB_GAPZ_FADE`, auction exit):
  pre-sample **+0.28**, design **+0.85**, held out **−0.02**. The survivorship-free breadth version
  of the trade drifts to zero, and the design window is its outlier. Break-evens 0.15 / 0.35 /
  −0.01 bp. Dead.
- **The all-day hold inverts.** The entry-slot profile in §2 was the strongest argument that this is
  a mechanism rather than a slot. It was tested. `PA_GAP_FADE_ALLDAY` (identical score, entry bar 6
  = 10:00 instead of bar 71 — **post-hoc, labelled as such in the frozen shortlist, and never
  promotable**) scores design gross +1.47 and **held-out gross −0.47**. A **sign flip across
  windows**, which by the standing rule from 0823 §2 is noise, not mechanism. The late-day slot
  replicated; the all-day drift that was supposed to explain it did not.

## 4. The other 25 — distribution, design window

| rung | min | median | max | # positive |
|---|---|---|---|---|
| gross (0 bp) | −0.98 | +0.24 | **+2.36** | 17 of 26 |
| net 0.5 bp/side | −2.99 | −1.05 | +0.37 | 2 |
| **net 1.0 bp/side (headline)** | −4.55 | −1.98 | **−0.26** | **0** |
| net 2.0 bp/side | −7.65 | −4.43 | −1.02 | 0 |
| net 2.5 bp/side | −9.19 | −5.78 | −1.40 | 0 |

**Zero of 26 are net-positive at the headline rung on design** — the best of all 26 at 1.0 bp/side
is −0.26, and `PA_GAP_CD_FADE` itself is −1.16 there because it is the highest-turnover book in the
sweep. Seventeen of 26 have positive gross, which
is roughly what a sweep containing five explicit sign-flipped pairs produces whatever happens; the
count is not the informative number, the size of the largest is, and only one of them is above the
+1.44 bar.

The three genuinely new instruments were all empty:

- **Path efficiency / choppiness** (best +0.43, perm p = 0.26 for the family's best cousin). The
  shape of the first hour carries no cross-sectional information about the rest of the session,
  which extends 0823's finding that bar-level order-flow proxies are empty from *magnitude* proxies
  to *shape* proxies.
- **Opening-print dislocation** open ÷ VWAP(bar 0) − 1 (best +0.60, perm p = 0.2595). The opening
  auction does not misprice against the first five minutes in a way that is recoverable
  cross-sectionally.
- **Vol-scaled drive on the point-in-time panel** (best +0.58). Normalising 0823's raw-sign drive by
  its own σ does not resurrect it. And its Panel-B decomposition names the reason the raw version
  ever looked alive: **209% of `PB_DRIVEZ_FADE`'s hold sits in the last ten minutes**, i.e. in the
  15:59-print-to-auction leg — the same close-auction bounce that killed auction-imbalance on ρ1.

## 5. Method

- **Design** 2021-01-04 → 2024-12-31 (1005 sessions, both panels, so one pooled best-of-N bar is
  valid). **Held out** 2025-01-02 → 2026-08-14 (405 sessions), untouched until commit `56129f7`.
  **Pre-sample** (Panel B only, declared in the pre-registration, can only kill) 2016-01-04 →
  2020-12-31 (1259 sessions).
- **Panel A** — the existing `im0823_cache/cube.npz` 5-minute cube (1410 × 78 × 132), Alpaca SIP,
  `adjustment=all`, RTH. Survivorship-biased; no config filters on a price level. Entry = VWAP of
  bar s+1, exit = VWAP of bar 77, so signal and fill never share a print.
- **Panel B** — the existing `auc0822_cache/panel.npz` point-in-time top-500 auction rail
  (2669 × 1611): official open, official close, 15:29/15:49/15:59 prints, corporate-action flag,
  point-in-time membership, trailing ADV. Prices are RAW, so the **only** cross-session quantity
  computed is the overnight gap, and it is NaN whenever the corporate-action flag is set (plus a
  |gap| > 50% guard).
- **Costs** 0.5 / 1.0 / 2.0 / 2.5 bp per side on |Δw|, headline 1.0, plus 0.15 bp/turnover for
  SEC 31 + FINRA TAF. Panel B's auction exit pays fee only.
- **Harness self-test** (`_selftest.json`): planted edge +41.01, mirrors to −41.01 under negation;
  random score +0.58; a deliberately planted one-bar artefact scores +0.75 primary and **collapses
  to −0.98** under the gap fill, so the gate can see the object it is there to catch; Panel B
  planted edge +27.58.
- **Disclosed contamination:** 0823 read the 2025–2026 window for four named configs
  (`E4_PDPOC_MAGNET`, `A5_DRIVE_EX_GAP`, `F2_LD_REV`, `G3_LD500_CONT_TOP150`). None of the 26 here
  is one of them or a monotone re-parameterisation of one. The window is not virgin for the
  *theme*, and that is stated rather than hidden.
- **Truncation disclosed:** the permutation stage ran on the top 8 by design gross, not all 26. The
  remaining 18 have design gross ≤ +0.58 against a +1.44 bar, so no per-config p-value could change
  a verdict.

## 6. What this closes, and the one thing it opens

1. **The last untested cell of the intraday-equity theme is now tested.** 0823 killed opening drive,
   close drive and opening range on gross; this round killed path shape, opening-print dislocation
   and vol-scaled drive on gross, and found the one remaining cell — the overnight gap conditioned
   on the opening auction — to be **statistically real and economically unreachable**. The theme is
   closed. Nothing further should be spent on free-bar intraday equity microstructure.
2. **This is a materially different negative from 0823's, and the difference is worth logging.**
   0823 died *before* a single basis point of cost was charged — 0 of 28 beat the gross bar. This
   round produced a gross effect that clears a family-wise p < 0.01 bar, survives a permutation at
   p = 0.002, decomposes cleanly away from the entry print, and **replicates out of sample at
   +2.09 with a bigger bp/day than it had on design** — and then dies at 0.90 bp against a 1.13 bp
   spread. That is `EXECUTION_COST_WALL` in its purest observed form and the sharpest single
   confirmation of the standing lesson that **free data prices a statistic, not a claim.**
3. **The margin is 18%, and that is the thing to write down.** The held-out effect is 0.93 bp per
   unit turnover on the best honestly-priceable rail; the cost is 1.13 bp. This is the closest any
   invented equity formula in this repo has come to its own execution floor without clearing it.
   It does not change today's answer — **nothing is promoted, and per the standing instruction the
   basket forward clock is LOCKED, so this is not added to the frozen basket** — but it is the
   correct object to re-test first if the execution assumption ever changes (measured price
   improvement on mega-cap marketable orders, a mid-point rail, or paid data). It is logged as a
   **gross-real / net-dead** observation, not as a candidate leg.

**Nothing from this theme goes near the basket.**

---

## Artifacts

| what | path |
|---|---|
| pre-registration (committed first) | `research/trading_bot/INVENT_0825_opendrive_PREREGISTRATION.md` |
| harness self-test | `research/trading_bot/INVENT_0825_opendrive_selftest.json` |
| design, 26 configs, both fills, 4 rungs | `research/trading_bot/INVENT_0825_opendrive_design.json` |
| nulls (bootstrap best-of-26 + ADV permutation on gross) | `research/trading_bot/INVENT_0825_opendrive_null.json` |
| decomposition / entry-slot / tercile diagnostics | `research/trading_bot/INVENT_0825_opendrive_DIAG.json` |
| frozen shortlist (committed before held-out) | `research/trading_bot/INVENT_0825_opendrive_SHORTLIST.md` |
| held out | `research/trading_bot/INVENT_0825_opendrive_heldout.json` |
| Panel-B pre-sample 2016–2020 | `research/trading_bot/INVENT_0825_opendrive_presample.json` |
| post-hoc closing-auction rail test | `research/trading_bot/INVENT_0825_opendrive_AUCTIONRAIL.json` |
| code | `scripts/trading_bot/od0825_{sweep,diag,auction_rail}.py` |
| panels (both pre-existing, nothing re-downloaded) | `research/data/im0823_cache/cube.npz`, `research/data/auc0822_cache/panel.npz` |
