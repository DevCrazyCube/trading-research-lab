# INVENT_0822B — futures / FX MECHANICAL-ROLL & SEASONAL structure

**Date:** 2026-08-22 (2nd rotation). **Verdict: the theme is NOISE. Nothing promotable, nothing frozen.**

42 structurally new formulas, design-window → pre-registered freeze → untouched held-out.
Best design net Sharpe **+1.082** (family-wise bootstrap p = 0.001) → **held out +0.553**
(family-wise p = 0.88). The primary, mechanism-chosen pick went **+0.947 → +0.470 (t 1.30)**
and **fails the pass criteria written down before the held-out was read.**

Two things in this round are worth more than the zero:
1. a **data fact** that closes the one open door the previous futures sweep left, and
2. a **characterised object** — a real, 40-year-persistent month-end Treasury effect that is
   genuinely there and genuinely too small to clear this programme's bar.

---

## 0. Context: this theme was NOT least-worked

The brief called futures/FX roll-and-seasonal the least-worked theme. It is not.
`SWEEP_futures_term_structure.md` (49 formulas, best +0.80 vs bar +0.78) and
`SWEEP_futures_term_structure_r2.md` (49 formulas, best legitimate +0.59 vs bar +0.71) already
covered ETF maturity ladders, cross-sectional and time-series carry, basis momentum, carry×momentum,
expanding-window and fixed-prior seasonality, the VIX curve, the equity-index basis, rates-curve
carry, FX futures basis carry, energy-complex spreads, carry-quality transforms, regime overlays,
roll-window timing and seven fixed-prior seasonals. **98 formulas, two independent rounds, both noise.**

This round therefore did two things instead of a third re-tune:
- attacked the **one open door** round 2 explicitly named — *"it would need a real futures calendar
  spread rather than the ETF ladder to be worth another look, and that is not free data"*;
- opened **four mechanical-flow families the earlier rounds never touched** (P, Q, R, S below).

---

## 1. THE DATA FACT — the open door is confirmed CLOSED

Stooq is behind a JavaScript proof-of-work and returns no CSV headlessly (re-verified 2026-08-22).
Yahoo chart v8 is the entire free surface. 172 per-contract futures symbols probed, 64 served
(`research/data/inv0822b_cache/contract_probe.json`).

**Finding.** Yahoo serves per-contract history only for contracts **still listed** (plus a ragged
few months of recently-expired ones — `GCZ25`, `6EU25`, `ZCN25` linger; every expired CL and NG
contract is gone). Each *live* contract carries deep history:

| contract | first bar | bars |
|---|---|---|
| `CLZ26.NYM` | 2017-11-21 | 2,203 |
| `NGZ26.NYM` | 2013-11-27 | 3,206 |
| `GCZ26.CMX` | 2020-12-30 | 1,422 |

That looks like a per-contract curve panel and it is not one. The earliest **served** CL expiry is
**Sep-2026 — today's front**. So at any past date *t*, the shallowest maturity the free feed can
show is approximately *(today − t)* forward: on 2018-01-22 the nearest available CL contract is
**8.6 years out**. The available panel is a diagonal of ever-deferred contracts, not a curve.

**Consequence:** a historical **front-month** curve — and therefore front-to-next roll-yield timing,
calendar-spread behaviour around roll dates, and per-commodity roll-window pressure measured on real
contracts — **cannot be reconstructed from free data.** Round 2's open door is closed, not open.

The only real futures calendar spreads free data does support are pairs whose **both legs are still
listed**. All five pass the ρ1 bounce gate cleanly — this family is not bounce-contaminated — and all
five are useless for a bar-clearing test:

| spread | n | window | ρ1(Δspread) | gate |
|---|---|---|---|---|
| NG Mar-27 / Apr-27 (the "widow-maker") | 2,951 | 2014-11-25 → 2026-08-21 | −0.025 | PASS |
| NG Mar-28 / Apr-28 | 2,698 | 2015-11-25 → | −0.034 | PASS |
| NG Oct-27 / Nov-27 (injection turn) | 2,950 | 2014-11-25 → | −0.016 | PASS |
| CL Dec-27 / Dec-28 | 1,813 | 2019-06-10 → | +0.029 | PASS |
| CL Jun-27 / Dec-27 | 1,949 | 2018-11-20 → | +0.000 | PASS |

**No formula was scored on them.** The two NG H/J series are the same seasonal spread one year
apart and overlap in calendar time — n_independent ≈ 2 — and both are deferred contracts aging from
~12 years out toward the front, i.e. not the object anyone would trade. There is no bar two
overlapping series could clear, and pretending otherwise would be the exact mistake this programme
keeps catching.

---

## 2. THE SEARCH

- **Design** 2007-01-01..2018-12-31 (12.0y). **Held out** 2019-01-01..2026-08-21 (7.6y), walled
  behind a separate subcommand and read only after `INVENT_0822B_futroll_FREEZE.md` was written.
- **N = 42**, sign-agnostic → **84 effective one-sided tries**. Analytic bar √(2 ln 2N) = **t 2.977**.
- **Measured, size-matched null** (this is the operative bar, per INVENT_0822 lesson (a)):
  circular-shift bootstrap, 2,000 draws — shift the realised return matrix against the **fixed**
  weight matrices, so each formula's turnover and cost line, each asset's autocorrelation, the
  cross-asset correlation and the **correlation between formulas** are all preserved, and the max is
  over 42 *correlated* tries. The statistic drawn is the one reported: best-of-two-signs, net of costs.
  For a calendar formula this is precisely the right placebo — it destroys the alignment between the
  weights and the day-of-month and changes nothing else.

| window | E[max] | p95 | p99 | max of 2,000 |
|---|---|---|---|---|
| design | **+0.608** | +0.849 | +0.975 | +1.138 |
| held out | **+0.741** | +1.020 | +1.233 | +1.342 |

- **P&L rule inherited and non-negotiable:** Yahoo `X=F` continuous series are the front contract's
  *spliced* price — the roll yield is deleted from them — so they are **signal inputs only**. Every
  P&L leg here is an ETF adjusted close or an FX spot rate.
- **Costs**, bp per side of notional: CME FX 6E/6J 1.5, 6B 2.0, 6A/6C 2.5, 6S 3.0; TLT 1.5, IEF/SHY/AGG/GOVT 2.0,
  TLH 4.0; commodity ETFs inherited from round 1 (USO 3, UNG 4, GLD 1.5, SLV 2, DBC 4, UGA/CORN/WEAT/SOYB/DBE 12, CPER/CANE 15).

---

## 3. FAMILY LEDGER

| family | n | mechanism | best design | best held out | verdict |
|---|---|---|---|---|---|
| **P** FX month-end hedge rebalancing | 13 | a USD investor holding FX-hedged foreign equities must resize the hedge at month end; if the foreign market rose, hedge notional rises and the foreign currency is **sold** into the 4pm fix | **+0.136** | +0.356 | **NOISE — below E[max] by 4.5×** |
| **Q** month-end bond-index duration extension | 16 | the Bloomberg US Agg/Treasury indices rebalance on the last calendar day; new issuance enters, index duration **extends**, and index trackers must buy duration | **+1.082** (p = 0.001) | +0.810 (p = 0.31) | **real effect, sub-bar out of sample** |
| **R** commodity-index roll window × published index weight | 7 | S&P GSCI rolls business days 5-9, BCOM 6-10; mandated flow into commodity *i* ∝ its index weight, which differs sharply between the two indices | **+0.551** | +0.283 | **NOISE** |
| **S** physical / regulatory calendar seasonals | 6 | RVP gasoline spec switch, EIA storage-cycle turn dates, distillate build, grain planting/harvest window pair | **+0.563** | +1.015 (sign FLIPPED) | **NOISE** |

Median design net Sharpe across all 42 formulas: **+0.211**. Formulas above the measured design
E[max] of +0.608: **7**, all in family Q. Above design p99 (+0.975): **1**.

### 3.1 Family P — FX month-end hedge rebalancing is flat

The most-anticipated family in the round and the deadest. Thirteen formulas: cross-sectional
z-weights on −(foreign equity − US equity) month return over 6 CME currencies, held the last 1 / 3 / 5
business days; tercile cut; sign-only; per-currency time-series sign; unhedged-investor (USD-terms)
version; aggregate dollar leg; unsigned month-end dummy; quarter-end restriction; the next-month
unwind; a 5-day signal-gap mechanism control; and a mid-month window placebo.

**Best design +0.136** against an E[max] of +0.608. The *unsigned* month-end dummy (+0.022) and the
*mid-month placebo* (+0.158) score as well as the signed mechanism formula (+0.136) — i.e. the sign
carries nothing. Held out, **nine of thirteen are negative** and the best is +0.356, half the held-out E[max] of +0.741. **The month-end FX rebalancing flow is real
in the plumbing literature and has no daily-close forecasting content over 2007-2026.**

One structural note, recorded so it is not re-proposed: the rebalancing flow executes at the **WMR
4pm London fix**, and a daily close-to-close series cannot see an intraday fix print. Reviving this
family requires intraday FX quotes around 16:00 London, not another formula.

### 3.2 Family R — the commodity-index roll window is flat, and its placebo is as strong

R traded the GSCI roll window (business days 5-9) cross-sectionally by **published index weight**,
which the previous rounds never did — they traded the window only in aggregate (DBC/GSG, USL/USO).

| formula | design | held out |
|---|---|---|
| `R05_JANREWEIGHT` (Jan roll window only) | +0.551 | +0.283 |
| `R04_ROLL_WDIFF` (GSCI weight − BCOM weight) | +0.370 | +0.097 |
| `R06_ROLL_LIQUID` | +0.331 | +0.086 |
| **`R07_ROLL_PLACEBO`** (**bd 16-20, no index roll**) | **+0.299** | +0.033 |
| `R01_GSCIROLL_WZ` (the a-priori window) | +0.243 | +0.052 |
| `R02_GSCIROLL_PRE` (bd 1-4, front-run) | +0.218 | +0.155 |
| `R03_GSCIROLL_POST` (bd 10-14, fade) | +0.130 | +0.013 |

**The window placebo out-scores the a-priori roll window in the design window** (+0.299 vs +0.243).
The cost line is also fatal on its own terms: 1.04–1.45%/yr of cost on a 7% vol book, i.e. the
roll-window cross-section spends more than a third of its gross on the ten-legged commodity ETF
basket it needs. Family R is dead on both counts.

### 3.3 Family S — seasonals: the held-out winner is a sign flip

`S06_TURNOFYEAR_COMMOD` (long DBC 15-Dec..15-Jan) is the **top held-out formula in the entire round
at +1.015** — and its design score is **+0.207 with the opposite sign**. A formula that needs sign
−1 in design and +1 out of sample is a coin. `S03_DISTILLATE_BUILD` runs the same way (+0.563 design
at sign −1 → −0.012 held out). `S01_RVP_SPEC` (+0.479 held out) is +0.05 *negative* in design.
Nothing here is a signal; recorded so the held-out numbers are never quoted as evidence.

---

## 4. THE ONE REAL OBJECT: month-end Treasury index extension

This is the part worth keeping. It is **real, it replicates on 64 years of data the search never
touched, and it does not clear the bar.**

### 4.1 What it is

The Bloomberg US Aggregate / Treasury indices rebalance on the last calendar day of the month: newly
auctioned issues enter and index duration **extends**, so every index tracker must buy duration on
that day. Prediction: intermediate and long Treasury **yields fall** into month-end, in proportion to
duration, with **no effect at the bill**, which has no meaningful extension.

### 4.2 Confirmation on an instrument outside the search

Raw CBOE constant-maturity yield indices — no ETF, no fee, no dividend adjustment, no cost model.
Month-end (last 2 business days) fall in yield vs the rest of the month:

(cells are the month-end mean fall in yield, and the t of month-end vs rest-of-month)

| series | duration | **pre-sample 1962-2006** | design 2007-2018 | held out 2019-2026 |
|---|---|---|---|---|
| `^IRX` 13-week bill | ~0.25 | +0.27 bp, **t +1.04** | +0.23 bp, t +0.51 | +0.52 bp, t +2.96 |
| `^FVX` 5-year | ~4.5 | +0.60 bp, t +2.99 | +0.89 bp, t +2.67 | +0.88 bp, t +2.61 |
| `^TNX` 10-year | ~8 | +0.55 bp, **t +2.98** | +1.03 bp, t +3.32 | +0.76 bp, t +2.49 |
| `^TYX` 30-year | ~16 | +0.74 bp, t +2.87 (from 1977) | +1.00 bp, t +3.30 | +0.58 bp, t +2.19 |

Converting the yield excess to a return with each tenor's duration gives **+0.07 / +3.43 / +5.94 /
+13.42 bp per month-end day** across bill / 5y / 10y / 30y over the full 1962-2026 sample: a clean
**duration gradient with a flat floor at the bill**, which is what the mechanism predicts and what a
generic "turn-of-month risk premium" would not.

**Size-matched calendar placebo on untouched data.** Over the 45-year pre-sample, score all 18
candidate two-business-day windows in the month. The a-priori window (last two days) ranks **1 of 18**
(+0.55 bp, t +2.82); the runners-up are bd_end 11-12 (+0.46) and 12-13 (+0.45). A 1-in-18 a-priori hit.

**Decade profile, and why it is a mechanism and not a constant:**

| | 1960s | 1970s | 1980s | 1990s | 2000s | 2010s | 2020s |
|---|---|---|---|---|---|---|---|
| ^TNX month-end, t | **−0.81** | **−0.18** | +1.65 | +1.96 | +3.01 | +3.41 | +1.96 |

The effect is **absent before the 1980s** — i.e. absent before bond indexing existed at scale
(Lehman Govt/Corp 1973, the Aggregate 1986). That is mechanism-confirming, and it also means the
honest sample is ~40 years, not 64. Year by year, 45 of 65 years (69%) are positive. Month by month
it is **not** concentrated in the quarterly-refunding months — October (+1.80 bp) and January
(+1.10 bp) are strongest while November (−0.12) and April (−0.72) are negative — which kills the
narrower "refunding supply" version of the story but not the general one.

### 4.3 Every gate this passed on the design window

| gate | result |
|---|---|
| gross-first (lesson 2) | `Q01` gross +1.032 → net +0.947. Cost is **8% of gross**; break-even **≈17 bp/side** against a ~1 bp TLT half-spread. **The execution-cost wall does not bind at all** — rare in this programme. |
| ρ1(Δ) bounce gate (lesson 3) | TLT −0.041, IEF −0.043, AGG −0.112, SHY −0.106, TLT/SHY spread −0.037. All far above −0.35; the gross is not manufactured by bounce. |
| bond beta / drift | unconditional TLT drift explains **13%** of the month-end day return (all-day mean +2.35 bp vs month-end +17.95 bp). A fully drift-neutral version — long month-end, short a matched notional spread across every other day — scores **+0.936**, unchanged. Not a bond bull market in disguise. |
| instant-vs-interval (lesson 5) | an **interval**: bd_end 1-2 +0.947, bd_end 1 alone +0.747, delayed to bd_start 2-3 of the next month +0.644. It survives a session of delay, so it is not an announcement timestamp. |
| measured size-matched null (lesson 4) | design family-wise bootstrap **p = 0.001** (`Q12_AGG`), **p = 0.019** (`Q01_TLT`). |
| free-feed durability (lesson 6) | TLT / IEF / AGG / `^TNX` / ZN futures. Nothing discontinuable. |
| no conditioning (lesson 1) | the two calendar-month conditioners **hurt**: `Q05_REFUND` +0.478 and `Q06_QTR` +0.389 against the unconditioned +0.947. Lesson 1 held again. |
| diversifying vs BASKET1 | fully — no shared security, issuer or asset class with T3, ETF-sibling RV, dual-class RV, T7, T12 CEF or XS_GLSR_Z. |

### 4.4 And how it fails

Pass criteria were written into `INVENT_0822B_futroll_FREEZE.md` before the held-out was read:
*(1) held-out net Sharpe > 0 with t > 1.5; (2) the mid-month placebo and the SPY control do not
out-score it; (3) the ^TNX held-out yield sign holds.*

| | design | held out |
|---|---|---|
| `Q01_BONDME_TLT_2D` (primary, mechanism-chosen) | +0.947, p 0.019 | **+0.470, t 1.30, p 0.97** |
| `Q12_BONDME_AGG` (design maximum) | +1.082, p 0.001 | +0.553, p 0.88 |
| `Q03_BONDME_TLT_3D` | +0.971, p 0.011 | +0.591, p 0.81 |
| `Q08_BONDME_IEF` | +0.913, p 0.029 | +0.707, p 0.54 |
| `Q13_BONDME_GOVT` (best held-out Q) | — | +0.810, p 0.31 |
| `Q10_BONDME_PLACEBO` (mid-month, bd 12-13) | +0.350 | **+0.385** |
| `Q15_BONDME_SPY_CTRL` (SPY — no bond-index mechanism) | — | **+0.443** |

**Criterion 1 fails outright** (t 1.30 < 1.5). **Criterion 2 passes only on paper**: the SPY control,
which has no month-end index-extension mechanism at all, earns **94% of the primary pick's held-out
Sharpe**, and the mid-month placebo earns 82% of it. Held out, the a-priori window ranks **5 of 18**
for TLT and **6 of 18** for SPY. Nothing in family Q clears the held-out E[max] of +0.741 with any
margin; the best is p = 0.31.

**Why the tradable Sharpe halved while the yield effect did not die.** The effect shrank *and* the
denominator grew:

| | month-end TLT return | TLT daily vol | per-day Sharpe |
|---|---|---|---|
| design | +17.95 bp | 90.6 bp | +0.198 |
| held out | +9.43 bp | 100.9 bp | +0.094 |

In standardised yield terms, `^TNX` goes +0.082 (pre-sample) → +0.182 (design) → +0.130 (held out):
the design window is the *strongest* of the three, so the search selected a window in which a real
but modest effect happened to be near its historical maximum. That is the ordinary way a real,
sub-bar effect produces an over-strong design number — and it is exactly why the held-out gate exists.

**Filed as a characterised object, not an open question.** It joins `B01_same_issuer_preferred_RV`
in the same drawer for the opposite reason: B01's gross cleared the bar and execution took it;
this one's execution cost is negligible (break-even 17 bp against a 1 bp spread) and **the signal is
simply too small — roughly a 0.4-0.5 Sharpe sleeve, which is under the bar and under any leverage
that would matter.** Guard, if it were ever revived: it needs the month-end effect back above
**+15 bp per month-end day on TLT** in a forward window, not another formula.

**Standing honesty flag: this is a PUBLISHED phenomenon** (Ogden 1987 turn-of-month; the
Lehman/Bloomberg index month-end extension literature). This round did not discover it — it
re-derived it from the mechanism and put it through the bar. It must never be reported as an invention.

---

## 5. DISCIPLINE AUDIT

- **Zero formulas spent on regime conditioning or gating.** The only conditioners used are *calendar*
  restrictions (quarter-end, refunding months, January), and they were all **worse** than the
  unconditioned formula, in both windows. Lesson 1 held for the third round running.
- **Gross-first ordering honoured.** No cost-fix was attempted on any sub-bar-gross signal. Where the
  survivor was found, cost was verified not to bind (8% of gross, 17 bp break-even) *before* any
  rescue was considered — and no rescue was needed or attempted, because the failure was significance.
- **ρ1(Δ) bounce gate run before the gross bar** on every spread object in the round, including the
  five real futures calendar spreads. All passed; none was used to manufacture significance.
- **The null was measured, not assumed.** The analytic bar (t 2.977 → Sharpe 0.86) would have passed
  `Q01`, `Q03`, `Q08`, `Q12` on design. The measured circular-shift null moved the operative bar to
  E[max] +0.608 / p99 +0.975 and gave family-wise p-values; the held-out null moved it to +0.741,
  which is what actually kills the family. The analytic bar was the wrong instrument in both windows.
- **Explicit placebos carried inside N, not bolted on afterwards:** `P13` (mid-month FX window),
  `Q10` (mid-month bond window), `Q15` (SPY asset control), `Q14` (SHY duration floor),
  `R07` (bd 16-20 non-roll window), `P12` (5-day signal-gap mechanism control). Three of the six
  scored at or above their own family's a-priori formula, which is how the P and R families died.
- **Held-out integrity:** picks, pass criteria and controls frozen in writing in
  `INVENT_0822B_futroll_FREEZE.md` before `inv0822b_sweep.py holdout` was ever run. The primary pick
  was chosen on **mechanism** (last two business days), not on the design maximum (`Q12_AGG` scored
  higher and is carried as secondary). No held-out restriction was chosen after seeing a result.
- **One degeneracy caught and fixed before scoring:** `P06_FXME_ABS_EQ` (foreign equity return alone)
  is **arithmetically identical** to `P01` under cross-sectional z-scoring, because subtracting a
  common US term does not change a z-score. It was replaced by a genuinely non-cross-sectional
  time-series version and the degeneracy is recorded in the code, rather than being reported as two
  independent tries.
- **No git commits, no orders, no money moved. BASKET1 frozen and untouched.**

---

## 6. DEAD LEDGER — additions (do not re-propose on free data)

- **Per-contract futures curve reconstruction from free feeds** — §1. Stooq is gone; Yahoo serves
  live contracts only, so the historical near curve does not exist. Front-to-next roll timing,
  calendar-spread behaviour around roll dates, and per-commodity roll pressure on real contracts all
  require a paid settlement history (or forward collection starting now).
- **FX month-end hedge-rebalancing flow on daily closes** — the flow prints at the WMR 4pm London fix;
  a close-to-close series cannot see it. Reviving needs intraday FX quotes around 16:00 London.
- **Commodity-index roll window traded cross-sectionally by published index weight** (GSCI bd 5-9,
  BCOM bd 6-10, GSCI−BCOM weight difference, January reweight). Its own non-roll-window placebo
  out-scores it, and it spends a third of gross on the ETF basket.
- **RVP gasoline spec transition; EIA storage-cycle turn dates; distillate build; grain
  planting/harvest window pair; the 15-Dec..15-Jan commodity-index turn-of-year.** All sign-flip
  between windows.
- **Month-end Treasury index-extension as a tradable sleeve** — characterised in §4, sub-bar out of
  sample. The *phenomenon* is real and is worth remembering; the *sleeve* is not.

## 7. WHAT WOULD ACTUALLY CHANGE THIS THEME

Not another formula. Three rounds and 140 formulas have now failed here. The binding constraints are
both **data**, and both are cheap to state:

1. **A per-contract futures settlement history** (any paid vendor, or forward collection from today's
   live-contract snapshots, which the probe shows would accumulate a genuine front curve at ~1 new
   maturity per month). This is the only thing that makes "mechanical roll" a testable object at all.
2. **Intraday quotes at the two fixes the mechanical flows actually print at** — WMR 16:00 London for
   the FX rebalance, and the month-end bond-index close. Every mechanical flow in this theme executes
   at a fix, and a daily close is the wrong clock for all of them. This is the same conclusion the
   forced-flow family reached from equities (`F12`/`F15`/`F27` needed intraday announcement stamps),
   reached here from a second, independent direction.

---

## 8. ARTIFACTS

| what | path |
|---|---|
| this report | `research/trading_bot/INVENT_0822B_futroll.md` |
| all 42 formulas, both windows, bootstrap p-values, day-of-month profiles, data fact | `research/trading_bot/INVENT_0822B_futroll.json` |
| pre-held-out freeze + pass criteria | `research/trading_bot/INVENT_0822B_futroll_FREEZE.md` |
| design / held-out raw | `INVENT_0822B_futroll_DESIGN.json`, `INVENT_0822B_futroll_HOLDOUT.json` |
| null distributions and window placebos | `INVENT_0822B_futroll_NULLS_DESIGN.json`, `INVENT_0822B_futroll_NULLP.json` |
| per-contract probe (172 symbols) | `research/data/inv0822b_cache/contract_probe.json` |
| engines | `scripts/trading_bot/inv0822b_{lib,sweep,nulls,fetch,contract_probe}.py` |
| new data cache | `research/data/inv0822b_cache/` (local-currency equity indices, bond ETFs, FX) |

## 9. RECOMMENDATION

**Freeze nothing. Promote nothing. BASKET1 unchanged.** Close the futures/FX roll-and-seasonal theme
on free data — 140 formulas across three rounds, one real phenomenon, zero tradable edges. The next
move in this theme is a data acquisition (§7), not a fourth sweep.
