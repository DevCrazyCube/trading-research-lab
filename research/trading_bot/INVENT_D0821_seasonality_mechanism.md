# INVENT-D0821 — SEASONALITY WITH A STRUCTURAL MECHANISM

**41 formulas tried across six mechanical-flow calendars. One mechanism survives to a
forward log; the other five are noise, and the theme as a whole loses 91% of its design
Sharpe out of sample.** Written 2026-08-21.

Machinery: `scripts/d0821_season_lib.py`, `d0821_season_etf.py`, `d0821_season_stock.py`,
`d0821_season_fix.py`, `d0821_season_eval2.py`, `d0821_season_diag.py`, `d0821_season_diag2.py`.
Numbers: `INVENT_D0821_seasonality_mechanism.json`,
`research/data/d0821_cache/{eval2,p_diag,p_diag2}.json`.

---

## 0. THE ONE-PARAGRAPH ANSWER

The brief was to test seasonals that tie to a **mechanical flow** — money somebody is
*obliged* to move on a known date — rather than to a bare calendar position, which
round 2 already killed. Six such calendars were built: balanced-mandate month-end
rebalancing, payroll-deferral turn-of-month contribution inflow, ETF and single-name
dividend/DRIP plumbing, bond-index month-end duration extension, quarter-end window
dressing, and tax-loss harvesting with its wash-sale clock. Across 41 pre-registered
formulas the largest design statistic is |t| = 3.21 against an analytic sign-agnostic bar
of **2.97** and a correlation-aware empirical E[max |t|] of 2.07 (ETF panel) / 2.49 (stock
panel). **The 19-formula stock panel is flatly noise** — joint-null p = 0.19, and its
largest hit (a January cross-sectional effect) points the *opposite way to its own
mechanism* and dies out of sample. The 22-formula ETF panel is not: joint-null p = **0.026**,
and the whole of that comes from one family — **balanced-mandate month-end rebalancing**,
where 6 of 7 members keep their sign across a 12.6-year untouched held-out window. Its best
member has design net Sharpe **0.87** against an analytic bar of 0.909; it does **not
clearly clear**, so it is logged, not promoted. The single most useful number in this
document is the theme-wide one: mean design net Sharpe **+0.205**, mean held-out net Sharpe
**+0.018**, with 22 of 41 signs surviving — a coin flip.

---

## 1. WHAT WAS NEW HERE, AND WHAT WAS DELIBERATELY NOT REPEATED

Not re-proposed, per the dead ledger: every published equity edge, VRP, all
carry-standalone, box, Orphan Flush, Coiled, the 18 SIZE candidates, the four noise sweep
themes. **Zero formulas were spent on regime conditioners** (round 3: 0/107). The four
`C0x` books in the results table are labelled CONTROLS and are excluded from the
multiple-testing count and from every verdict; they exist only to answer "what does the
calendar window buy".

Round 1–2 tested calendar position at the index level (`XE_MONTHSTART_CONT`,
`ETF_AUCTION_CONCESSION`, `SESS_OPEXDAY_INTRADAY`) and round 3 tested month/quarter-end
**index-rebalance close distortion** in the stock cross-section. Neither is repeated. What
is new is the **asset-allocation** rebalance rather than the index-membership one: the
signal is the intra-period divergence between the equity and bond sleeves that a
fixed-weight mandate is obliged to undo, not a date and not an index membership change.

Two mechanisms in the brief could not be tested and are declared untested rather than
reported negative: **ETF creation/redemption seasonality** (no share-count feed cached) and
**index add/delete reconstitution proper** (no point-in-time membership data — the same
gap round 3 hit).

---

## 2. THE BAR

* **Analytic.** N = 41 candidate formulas. The search is sign-agnostic, so the defensible
  count is 2N = 82 → `sqrt(2 ln 82)` = **2.97**. In design-Sharpe units that is **0.909**
  on the ETF panel (10.66 design years) and **1.212** on the stock panel (6.00 design years).
* **Empirical, correlation-aware.** 20,000 replicates, sign drawn once per 21-session block
  and shared by every formula, so contemporaneous cross-formula correlation survives.
  - ETF panel (22 books): E[max |t|] **2.07**, p95 2.89, p99 3.33. Observed max **3.08**,
    joint p = **0.026**.
  - Stock panel (19 books): E[max |t|] **2.49**, p95 3.76, p99 4.14. Observed max **3.21**,
    joint p = **0.189**.
* **Programme-cumulative.** ~634 formulas before this round plus 41 → 675 →
  `sqrt(2 ln 675)` = **3.61**. **Nothing in this round is within 0.5 SE of that.**

### 2a. A sign/cost correction that changed the answer

The first evaluation pass ranked on **net** t and produced four "hits" with large negative
net t (T01 −2.73, R01 −1.92, D04 −1.83, R03 −1.94). All four are artefacts. Reversing a
book flips the **gross** series but *not* the cost, so the best net any trader can have is
`sign·gross − cost`; a large negative net t on a weak gross series is **cost drag being
read as a reversed edge**. T01's gross t is −1.46, not −2.73; R01's is −0.47, not −1.92.
The hypothesis test is therefore run on gross and tradability on the correctly-signed net
(`d0821_season_eval2.py`). Every number in §3 onward uses that convention.

---

## 3. THE HONEST ZEROES

### 3a. Turn-of-month contribution inflow (family T, 6 formulas) — NOISE

The mechanism is real — payroll deferrals arrive on fixed dates and are invested
cap-weighted — so the falsifiable prediction is a **cap-weight tilt** in the inflow window,
not a market-direction effect. It is not there. `T01_TOM_CAPWEIGHT` (SPY vs the equal-weight
sibling RSP over sessions −2..+2) has design gross Sharpe **−0.45** — the tilt goes the
*wrong way*, equal-weight beats cap-weight in the window — and held-out gross **−0.00**.
`T02_TOM_MEGACAP` (OEF vs SPY) is −0.18/+0.10. The family max |t| is **1.66**
(`T03_TOM_SIZE`), below even E[max]. The semi-monthly sibling `T04_MIDMONTH_CAPWEIGHT`,
which the payroll story requires to fire, has design gross t = **0.01**. The 401(k)
contribution story does not leave a cross-sectional footprint anything here can see.

### 3b. Bond-index month-end duration extension (family R, 5 formulas) — NOISE

Bloomberg/ICE rulebooks extend index duration on the last business day of the month and
tracking funds must buy it. Family max |t| = **1.31** (`R05`, TLT vs SHY), median 1.13. The
refunding-month magnitude variant `R03` is **weaker** than the flat version, which is the
wrong ordering for the mechanism. Held-out is positive for R04/R05 gross and negative for
R01/R03; net of a measured 2–3.6 bp/side it is negative for four of five. Dead.

### 3c. Quarter-end window dressing (family W, 7 formulas) — NOISE

Design signs are consistent (the quarter's decile winners *under*-perform into the reporting
date, i.e. the mark-up story is backwards) but tiny: family max |t| **1.75**, and the
quarterly cluster count is 23 — the honest sample size, at which a t of 1.75 is nothing. The
sharpest mechanical test in the whole round, `W06_WD_CLOSE_TO_OPEN` (a mark-up printed in
the close must unwind in the *next opening auction*, before information can arrive), is
design gross 0.72 / held gross **−0.46** and is net-negative at 3 bp before the held-out
window is even opened. The control `C01_CTRL_MTDMOM_EVERYDAY` shows the same book held every
session is −0.13 design / +0.16 held: the window buys nothing that survives.

### 3d. Tax-loss harvesting and the wash-sale clock (family L, 9 formulas) — NOISE, and
backwards

This family owns the largest design statistic in the round, and it is a trap.
`L02_TLS_JAN_BOUNCE` has design gross |t| = **3.21** — but with a **negative** sign, meaning
the prior year's decile *losers* keep losing in January and the winners keep winning. That
is the opposite of the tax-loss mechanism the formula was written to test. The same
inversion appears in `L03_TLS_WASHSALE_31D` (|t| 2.42, wrong sign), `L04`, and `L08`. All
four are one hypothesis — *January cross-sectional momentum in 2016–2021* — tested four
ways, its honest sample size is **5 Januaries**, its year-clustered t is −1.70, and its
held-out net Sharpe is **+0.17**. The mechanism-shaped refinements all fail: scoring by
**embedded** unrealised loss instead of YTD return (`L07`) is design 0.29; the October
mutual-fund fiscal year-end (`L05`) is −0.32; the retail-heavy sub-$15 cohort (`L09`) is
0.13 on design. Joint p for the whole stock panel is 0.19. Honest zero.

### 3e. Dividend / DRIP plumbing (families D and X, 10 formulas) — NOISE, after a bug

`D02_ETF_EXDIST_PRERUN` (capture demand into an ETF's known ex-distribution date) is the
family's best at design gross Sharpe 0.86, t = 2.80 — below the 2.97 bar and below the ETF
p95 of 2.89. Its held-out is +0.16 net and **−0.07 at 2× cost**. `D01` (post-ex DRIP
recovery) is +0.22 design / **−0.61** held. The bond-ETF coupon-DRIP window `D04` is
−0.23/−0.58.

**The bug worth recording.** The single-name X family first reported
`X01_EXDIV_CAPTURE_PRERUN` at design t = **−13.97**, Sharpe −5.70. It was entirely a data
artefact, from two compounding errors: (i) the `inv3` stock panel carries **raw,
dividend-unadjusted** prices, so the close-to-close return realised *on* an ex-date contains
a mechanical drop of the dividend, and any book sorted on something correlated with yield
harvests a spurious spread; (ii) a position decided at the close of *t* earns the *t→t+1*
return, so "1 session before the ex-date" was in fact **holding across the drop**. Fixing
both — replacing the ex-date return with that session's cross-sectional median eligible
return, and moving the nearest offset from 1 to 2 — moved the design t from **−13.97 to
−0.19**. Hedging against *other dividend payers* rather than the whole universe (`X01b`)
removes the residual value/low-beta style tilt. Nothing survives: X-family max |t| = 2.20,
held-out net negative for five of six. This is the fifth time in this programme a
spectacular number turned out to be an unmeasured mechanical artefact, and it is the reason
the raw-price correction is now inside `d0821_season_stock.load()` rather than in a comment.

---

## 4. THE ONE THING THAT IS NOT NOISE — AND WHY IT IS STILL NOT PROMOTED

**Family P: balanced-mandate month-end rebalancing.** A plan document that says 60/40
*obliges* the manager to sell whatever outperformed inside the period, in the last sessions
of it. The signal is therefore not a date: it is **minus the month-to-date divergence
between the equity and bond sleeves**, held only in the rebalance window.

| formula | design gross Sh | design gross t | design net Sh | held gross Sh | held net Sh | held net @2× cost |
|---|---|---|---|---|---|---|
| `P02_PENSION_MEQ_MAG` (sized by divergence) | **0.94** | **3.08** | 0.87 | 0.46 | **0.37** | 0.29 |
| `P05_PENSION_LASTDAY` (final session only) | 0.66 | 2.16 | 0.50 | 0.34 | 0.14 | −0.06 |
| `P01_PENSION_MEQ_SIGN` (sign only) | 0.65 | 2.12 | 0.55 | 0.69 | **0.57** | 0.45 |
| `P07_PENSION_CREDIT` (HYG vs IEF) | 0.61 | 1.98 | 0.52 | 0.34 | 0.15 | −0.04 |
| `P06_PENSION_GLOBAL` (SPY vs EFA) | 0.39 | 1.28 | 0.23 | 0.21 | 0.06 | −0.09 |
| `P03_PENSION_QTR` (quarter ends only) | 0.33 | 1.07 | 0.28 | 0.04 | −0.03 | −0.09 |
| `P04_PENSION_UNWIND` (give-back, first 3 sessions) | 0.24 | 0.79 | 0.12 | −0.37 | −0.50 | −0.63 |
| **equal-risk composite of the 5 month-end members** | 0.89 | 2.92 | 0.75 | **0.63** | 0.42 | 0.21 |

Design = 2003-05→2013-12 (RSP-bounded panel), held-out = 2014-01→2026-08, **12.6 untouched
years**. Six of seven members keep their sign into held-out gross. The composite is +0.63
held-out gross, +0.42 net, +0.21 at 2× the measured cost.

### 4a. The four questions that usually kill a survivor here

1. **Is it one crisis?** No. Excluding 2008–09 the design Sharpe is 0.80 (t = 2.34), and
   the book is net-positive in 9 of 11 design years and 26 of 34 calendar years on the
   long SPY history.
2. **Is it the deadline, or the signal?** This is the test that mattered, and the first
   version of it was **unfair**: a month-to-date signal read on session 3 contains 3 days
   and on session 20 contains 20, so "month-end works, mid-month does not" could be pure
   lookback length. Re-run with a **fixed 15-session** trailing signal held in five
   different month positions, the answer holds:

   | window (identical fixed-15 signal) | design net Sh | held net Sh |
   |---|---|---|
   | **last 4 sessions of month** | **0.75** | **0.49** |
   | sessions 1–4 | −0.31 | 0.49 |
   | sessions 5–8 | −0.03 | −0.20 |
   | sessions 9–12 | 0.16 | 0.08 |
   | sessions 13–16 | 0.09 | −0.12 |
   | every session (base rate) | 0.23 | 0.23 |

   The rebalance window carries about **3× the base rate of the same signal**. That is the
   deadline, not the lookback.
3. **Is it a bare calendar effect?** No. The *unconditional* month-end position — long SPY
   over the last 4 sessions regardless of the divergence — is design 0.26 / held 0.26, and
   the short is −0.33/−0.34. The conditioning on the flow is doing the work, which is the
   distinction this whole round was built to make.
4. **Which leg carries it?** Almost all of it is the **equity leg**: SPY-only is design
   1.11 / held 0.69, the IEF leg alone is 0.34 / −0.16. That is a refinement rather than a
   refutation — dollar for dollar the impact of a rebalance lands in the shallower market —
   but it means the honest expression of the mechanism is a **single-leg SPY timing book**,
   and that variant was found by **attribution, after the design numbers were fixed**. On
   the long SPY history it is design 1993–2013 net Sharpe 0.60 (t 2.74) / held 2014–2026
   **0.69 (t 2.46)**, and it is stable to a 1- and 2-session signal lag (0.61, 0.64 held) and
   to 3× cost (0.62 held) because it trades twice a month at 0.46× notional.

### 4b. Why it is still not promoted

* Design gross Sharpe 0.94 vs an analytic bar of **0.909** and an ETF-panel joint-null p95
  of 0.885. It clears by a hair, on the panel where the search was smallest.
* Design t 3.08 vs the **programme-cumulative bar of 3.61**. It does not clear that at all.
* Held-out is positive and cost-robust but never individually significant (best t = 2.46,
  and that is the post-hoc single-leg variant).
* The theme-wide carryover is a coin flip: **22 of 41** formulas keep a positive net sign
  out of sample, median held-out net Sharpe **+0.064**, mean **+0.018** against a mean
  design net Sharpe of +0.205 — **91% shrinkage**. A single family beating that pattern is
  what a family-shaped null also produces sometimes.

**Disposition: forward-log only, `P02_PENSION_MEQ_MAG` and the SPY-only refinement, at zero
size.** It is diversifying — every alive basket leg (T3 overnight reversal, ETF-sibling RV,
dual-class RV, T7 ex-open, T12 CEF discount, XS_GLSR_Z) is cross-sectional or relative
value, and this is an index-level directional-timing book active 19% of sessions, so it
cannot be a re-expression of any of them.

---

## 5. WHAT WOULD SETTLE IT

The mechanism predicts things this data cannot see. All three would be decisive, and none
needs a price feed:

1. **Rebalance flow should scale with the size of the drift, and with the AUM that is
   obliged to undo it.** A target-date-fund AUM series (ICI monthly, free) turns the flat
   `-z(divergence)` into a dollar-flow estimate. If the effect does not scale with it, the
   story is wrong even though the trade works.
2. **The impact should print in the closing auction of the last session**, not spread over
   the day. The `t3_cache` minute bars and `auctions.json.gz` opening/closing prints can
   answer that directly; §4a-4 says the effect concentrates in the equity leg, and this
   would say *where in the session*.
3. **A pre-committed forward window.** Design and held-out are both now spent. The only
   uncontaminated evidence left is forward: log it daily against the existing
   `BASKET_FORWARD_LOG` machinery and revisit at 60 rebalance events.
