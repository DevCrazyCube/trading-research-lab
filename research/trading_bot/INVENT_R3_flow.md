# INVENT R3 — MECHANICAL FLOW / STRUCTURE

**28 original formulas. Verdict: the theme is noise. Nothing is promotable.**

Written 2026-08-21. Round-3 invention pass on predictable non-discretionary flow, restricted to
free data. Scripts: `scripts/invr3_flow_data.py` (collection), `scripts/invr3_flow_eval.py`
(the 25 pre-registered formulas, design then holdout), `scripts/invr3_flow_diag.py`
(the survivor's post-mortem). Results: `INVENT_R3_flow_{design,holdout}.json`,
`INVENT_R3_flow_diagnostics.json`, `INVENT_R3_flow.json`.

---

## 0. The one-paragraph answer

Six mechanically distinct flow families were built and scored — levered-ETF close rebalancing,
non-CEF stale-NAV premium/discount, closing-auction print dislocation, distribution-reinvestment
timing, creation/redemption pressure, and month/quarter-end. **One** formula cleared the family's
own analytic noise bar on the design window: `C2_AUCT_RESID_ON`, a cross-sectional fade of the
closing-auction print's dislocation from the 15:55 price, residualised on the last-30-minute move
so the claim is incremental to leg L1. Design net Sharpe **1.667**, held-out net **+0.960**, gross
Sharpe 4.26 / 2.78, and — importantly — **genuinely orthogonal to T3** (corr +0.19 design,
−0.07 holdout; orthogonalised Sharpe unchanged at 1.77 / 0.99). It is nevertheless **not an edge**.
It is a shared-price measurement-error artefact, and a placebo isolates that exactly: keep the same
book and the same overnight window but mark the entry at the 15:55 price instead of at the closing
auction print the signal is measured from, and gross Sharpe goes from **+4.26 to −6.16**. The
signal is also not executable in the first place — you cannot observe an auction's clearing price
and then trade in that auction. Both strictly-executable re-timings die: entry at the next opening
print gives gross −1.80 (design) / −1.05 (holdout) into the next close, and +0.57 / +0.10
open-to-open. The only formula that is net-positive in both windows without touching a shared price
is `A6_LETF_ASYM_XS` at **0.79 design / +0.35 holdout** — a quarter of the noise bar.

---

## 1. What was searched, and why it is new

Excluded up front from the dead ledger: ORB-with-stop, PEAD, ex-div close-to-close, spin-off,
overnight harvest, merger arb, CEF reversion, VRP put-write, crypto carry, box spread, Orphan
Flush, Coiled Leverage, all 18 SIZE candidates, and the four round-2 sweep themes that were pure
noise. The generic calendar family (`SWEEP_calendar_session` batches 1–2, 100 formulas, verdict
noise) already killed index-level month-end direction bets — `REBAL_FLOW_2D`, `TOM_DURATION_EXT`,
`XE_MONTHEND_REV`, `TOM_CREDIT_FLOW`, `TOQ_*`. Nothing here re-proposes those: every month/quarter-end
formula in this pass is **cross-sectional and flow-identified** (the calendar picks the day someone
is forced to trade, a second flow variable picks which names), and appears only as a *gate* on a
mechanism that is also tested ungated.

| family | mechanism | new? |
|---|---|---|
| **A** levered-ETF rebalance (8) | an L× ETF must trade `L(L−1)·AUM·r` into the close, and inverse products push the *same* way (`L(L−1) > 0` for L = −1,−2,−3), so family flow is always same-signed as the day's move; intensity proxied by `Σ\|L(L−1)\|·LETF $vol / underlying $vol` | yes — Coiled Leverage was the *volatility-drag RV* between wrappers, not the rebalance flow or the retail-positioning asymmetry |
| **B** non-CEF premium/discount (6) | bond and international ETF NAV is stale (dealer marks, closed home markets); the price/NAV gap is a liquidity premium that reverts. NAV is not free, so the premium is proxied by a causal rolling-OLS residual against a duration+credit or beta+FX hedge | yes — the dead CEF work (T12/DEEPMINE_CEFNAV) is a different universe with a different, non-arbitraged mechanism |
| **C** closing-auction dislocation (4 + 3 diagnostics) | the auction clearing price differs from the last continuous price by the imbalance; imbalance pressure should revert. Imbalance feeds are paid, so the *realised* dislocation `auction print / 15:55 price − 1` is the free proxy | yes, and explicitly residualised on T3's own last-30-min feature so the claim is incremental to leg L1 |
| **D** distribution reinvestment (2) | monthly-paying bond ETFs nearly all go ex on the first business day and pay about a week later; the reinvestment bid is concentrated and dated | yes — this is a *cross-sectional yield sort inside a dated window*, not the dead ex-div close-to-close trade |
| **E** creation/redemption pressure (2) | anomalous own-volume in one wrapper relative to its same-exposure siblings is a primary-market flow proxy; primary flow pushes a wrapper off group fair value | builds on live leg L2 (ETF-sibling RV) by *gating* it on a flow variable rather than re-deriving it |
| **F** month/quarter-end (3) | A5 / B1 / B6 restricted to the windows where the forced flow is largest | gates only |

Data, all free: Alpaca SIP daily bars **raw and split/dividend adjusted** for 185 ETFs plus the
official opening/closing auction prints, 2016-01-04 … 2026-08-14 (485,341 bar rows, 479,927 auction
rows, zero thin symbols); the existing `rv_cache` 5-minute panel (137 names, 2021-01-04 …
2026-08-14); the existing `t3_cache` auction pool (1,648 symbols).

**Windows, fixed before any result was seen.** Daily panel: design ≤ 2021-12-31 (1,511 sessions,
6.00 y), holdout ≥ 2022-01-03 (1,158 sessions, 4.60 y). Intraday panel: design ≤ 2024-06-28 (877
sessions, 3.48 y), holdout ≥ 2024-07-01 (533 sessions, 2.11 y). The holdout was scored once, after
the design file was written.

---

## 2. Two harness bugs found and fixed before any number was read

Both would have manufactured a promotable-looking result, and both are worth carrying forward.

**(a) Turnover was undercharged on every round-trip book.** An overnight book (enter at the closing
auction, exit at the next opening auction) and an intraday book (15:30 → close) are *fully
liquidated every single day*. Charging `|w_t − w_{t−1}|` prices them as if the position persisted.
The first run showed `A1_LETF_PUSH_TS` at net Sharpe +0.54 and `B4_INTL_PREM_ON` at −3.52; with
turnover correctly at 2× gross per day those become **−0.96** and **−5.56**. Fixed by an explicit
`roundtrip=True` mode in `book_pnl`.

**(b) The raw auction feed was being divided by a back-adjusted price cache.** `rv_cache` is
split- and dividend-back-adjusted (TQQQ opens the panel at \$21.93 in Jan 2021, against a traded
price near \$100); the auction feed is raw prints. `auction / intraday_close` therefore exploded on
every split. On the daily panel the fix is exact — both raw and adjusted bars were pulled, so
`f = adj_close / raw_close` puts every raw print into adjusted units and every auction-to-auction
return is a genuine total return across splits and ex-dates. On the intraday panel the fix is a
trailing 21-day median of the ratio, with all returns winsorised.

The first, buggy run reported a best design Sharpe of +0.54 and two large negatives that looked like
sign-flip discoveries. Both "discoveries" were pure cost: for `E1`, gross was **+0.04 bp/day**
against a **2.84 bp/day** cost, so flipping the sign gives `−gross − 2·cost`, which is worse, not
better. Every table below reports gross Sharpe, gross bp, cost bp and break-even half-spread side by
side so a cost artefact cannot be mistaken for a signal again.

---

## 3. The noise bar

`N` = 28 (25 pre-registered + `C5`, `C6`, `C7` diagnostics; controls and the two re-scored buggy
runs are not counted, and no formula was silently dropped).

* **Analytic.** `sqrt(2 ln 28)` = **2.582 SE**. Sign-agnostic (`2N` = 56) = **2.837 SE**.
  Single-formula Sharpe SE is ≈ `sqrt(1/years)`: **0.408** on the 6.00 y daily panel, **0.536** on the
  3.48 y intraday panel. So the analytic expected-max in Sharpe units is **1.05 (daily) / 1.38
  (intraday)**.
* **Empirical, correlation-aware.** Stationary block sign-flip (block 21 sessions, 2,000 replicates)
  applied identically to all 28 PnL columns, so cross-formula correlation survives; record
  `max |Sharpe|` per replicate. Design window: **mean 1.180, p50 1.116, p95 1.811, p99 2.199.**
  (Holdout window, for reference only: mean 1.691, p95 3.210 — wider because it is shorter.)
* **Programme-cumulative.** 598 distinct formulas across rounds 1–2 plus these 28 = **626**;
  `sqrt(2 ln 626)` = **3.589 SE** → **1.47 (daily) / 1.93 (intraday)** in Sharpe units. This is the
  bar that actually applies, because the winner here was picked by looking at every theme.

**Headline bar: 1.93 on the intraday panel, 1.47 on the daily panel.** The best formula in this
pass reaches **1.667** on the intraday panel — below the cumulative bar and below its own family's
empirical p95 of 1.811.

---

## 4. Full design distribution — all 25, nothing dropped

Costs: half-spread tiered on median dollar volume (≥\$500 M → 1.0 bp/side, \$100–500 M → 1.5,
\$20–100 M → 3.0, \$5–20 M → 6.0, < \$5 M → 15.0), charged on realised turnover, plus 50 bp/yr borrow
on short notional. `be` is the break-even half-spread in bp per side.

| net SR | gross SR | formula | hold | turn/day | gross bp | cost bp | be bp |
|---:|---:|---|---|---:|---:|---:|---:|
| **+1.667** | +4.26 | `C2_AUCT_RESID_ON` | overnight | 1.94 | +4.395 | 2.677 | 2.27 |
| +1.467 | +2.71 | `C3_AUCT_RESID_MEND` | overnight | 0.46 | +1.335 | 0.637 | 2.90 |
| +0.941 | +3.58 | `C1_AUCT_DISLOC_ON` | overnight | 1.94 | +3.635 | 2.681 | 1.87 |
| +0.793 | +1.16 | `A6_LETF_ASYM_XS` | 1d | 0.84 | +3.615 | 1.137 | 4.32 |
| +0.495 | +1.12 | `C4_AUCT_RESID_D1` | 1d | 0.70 | +1.866 | 1.039 | 2.69 |
| +0.269 | +0.79 | `D2_HIYIELD_EXWEEK` | 3d | 0.08 | +0.391 | 0.258 | 4.92 |
| +0.239 | +0.44 | `A8_LETF_TURN_XS` | 5d | 0.26 | +0.818 | 0.375 | 3.13 |
| +0.064 | +0.92 | `F3_QEND_BOND_PREM` | 3d | 0.04 | +0.134 | 0.124 | 3.22 |
| +0.039 | +0.84 | `A2_LETF_PUSH_BIG` | 1530→close | 0.95 | +0.997 | 0.951 | 1.05 |
| +0.016 | +0.70 | `D1_BONDETF_EXWEEK` | 3d | 0.08 | +0.236 | 0.231 | 2.98 |
| −0.200 | +0.41 | `B5_PREM_EXTREME_2D` | 2d | 0.32 | +0.718 | 1.065 | 2.23 |
| −0.352 | +0.53 | `B2_BOND_PREM_STRESS` | 3d | 0.15 | +0.282 | 0.469 | 1.84 |
| −0.432 | +0.44 | `B3_INTL_PREM_FADE` | 3d | 0.31 | +0.613 | 1.219 | 1.96 |
| −0.864 | −0.29 | `F1_MEND_LETF_ON` | overnight | 0.46 | −0.303 | 0.600 | — |
| −0.961 | +0.63 | `A1_LETF_PUSH_TS` | 1530→close | 2.00 | +0.794 | 2.000 | 0.40 |
| −1.063 | +0.49 | `B1_BOND_PREM_FADE` | 3d | 0.33 | +0.326 | 1.028 | 1.00 |
| −1.184 | −0.20 | `A3_LETF_PUSH_HIINT` | 1530→close | 1.32 | −0.265 | 1.323 | — |
| −1.219 | −0.54 | `A4_LETF_ON_GIVEBACK` | overnight | 2.00 | −1.990 | 2.463 | — |
| −1.497 | −0.23 | `A7_LETF_ASYM_ON` | overnight | 1.98 | −0.463 | 2.535 | — |
| −1.662 | +0.82 | `E2_CR_GATED_RV` | 3d | 0.45 | +0.300 | 0.911 | 0.67 |
| −1.764 | −0.52 | `A5_LETF_ON_XS` | overnight | 1.92 | −1.051 | 2.536 | — |
| −2.143 | +1.82 | `B6_SIB_PREM_FADE` | 3d | 0.37 | +0.491 | 1.073 | 1.33 |
| −2.149 | +0.77 | `F2_MEND_SIB_RV` | 3d | 0.06 | +0.045 | 0.176 | 0.73 |
| −5.556 | +0.31 | `B4_INTL_PREM_ON` | overnight | 1.88 | +0.373 | 6.992 | 0.20 |
| −6.284 | +0.09 | `E1_CR_VOLZ_XS` | 1d | 1.01 | +0.038 | 2.839 | 0.04 |

Median design net Sharpe **−0.43**; 10 of 25 net-positive; 1 of 25 above the analytic family bar.

Two rows are worth staring at, for the same reason the intraday-RV sweep was:

**The whole levered-ETF rebalance thesis is gross-flat.** `A1`'s prediction — the family's forced
close-of-day trade is same-signed as the day's move, so the last 30 minutes should push — earns
**+0.79 bp/day gross** against a **2.00 bp/day** cost floor, a break-even of 0.40 bp/side on a
universe whose own charged half-spread is 1.00. Gating on move size (`A2`) or on rebalance intensity
(`A3`) does not rescue it; `A3` turns the gross *negative*. The overnight give-back (`A4`, `A5`) is
gross-negative in design too. The mechanism is real and the arithmetic is public, which is exactly
why the flow is pre-positioned rather than harvestable.

**The premium/discount family never had the gross to pay for itself.** `B1`/`B3` earn +0.33 and
+0.61 bp/day gross against 1.03 and 1.22 bp/day of cost; break-even is 1.00 and 1.96 bp/side against
charged half-spreads that are already conservative for these wrappers. `B4` — the one timing that
should work, holding only across the window in which the closed home market reprices — is the worst
cost/gross ratio in the family at 0.20 bp break-even against 7.0 bp/day of round-trip cost.

---

## 5. Holdout — scored once, after the design file was frozen

| formula | design net | **holdout net** | holdout gross | holdout be bp |
|---|---:|---:|---:|---:|
| `C2_AUCT_RESID_ON` | +1.667 | **+0.960** | +2.78 | 2.11 |
| `C3_AUCT_RESID_MEND` | +1.467 | **+0.925** | +1.60 | 3.23 |
| `C4_AUCT_RESID_D1` | +0.495 | **+0.743** | +1.20 | 3.86 |
| `C1_AUCT_DISLOC_ON` | +0.941 | **+0.649** | +3.00 | 1.76 |
| `A6_LETF_ASYM_XS` | +0.793 | **+0.347** | +0.61 | 3.06 |
| everything else (20 of 25) | — | **negative** | — | — |

Five of 25 survive in sign. Four of the five are one mechanism. `C2`'s holdout t-statistic is
**1.40** (0.960 × √2.11) — positive, and not significant on its own.

---

## 6. Post-mortem on the only survivor: `C2` is an artefact, and it is unexecutable anyway

### 6a. It is genuinely not T3 — that part checks out

Scored on the identical panel, window and cost model, the T3-style control (cross-sectional fade of
the z-scored last-30-minute return, held over the same overnight auction gap) gives net −0.35
design / +0.43 holdout. Correlation of daily PnL with `C2`: **+0.188 design, −0.072 holdout**.
`C2` orthogonalised day-by-day to the control: **1.765 design / 0.994 holdout**, i.e. slightly
*higher* than raw. Whatever `C2` is, it is not leg L1 in disguise. This is the one honest positive
in the whole pass.

### 6b. You cannot trade at the price you are conditioning on

`C2` measures the dislocation *of the closing auction print* and then enters *at that print*. An
auction's clearing price is not observable until the auction clears. The only real entry is the
post-close session. Break-even is **2.27 bp/side (design), 2.11 (holdout)**; the cost ladder:

| half-spread charged | design net SR | holdout net SR |
|---|---:|---:|
| 0 bp | +4.17 | +2.72 |
| 1 bp | +2.29 | +1.40 |
| 1.38 bp (as charged) | +1.57 | +0.90 |
| 2 bp | +0.41 | +0.08 |
| 3 bp | −1.48 | −1.25 |
| 5 bp | −5.24 | −3.89 |
| 8 bp | −10.82 | −7.86 |

Post-close NBBO half-spreads on even top-ADV names run several times 2 bp. Re-timed to something
strictly executable, it dies outright: entering at the **next opening print** gives gross Sharpe
**−1.80 design / −1.05 holdout** into that day's close, and **+0.57 / +0.10** open-to-open, both net
negative. Using *yesterday's* dislocation so a real MOC order can be placed before 15:50 (`C7`)
gives net **+0.78 design / −0.35 holdout**.

### 6c. And the gross number itself is a shared-price artefact

Two independent tells.

**The dislocation is 84% autocorrelated at lag 1** (ρ = 0.838, n = 167,097). A genuine
auction-pricing error is close to serially independent. 0.84 says `auction print / 15:55 price` is
mostly a slow-moving per-symbol level that the trailing-median normaliser does not fully remove —
so the "fade" is a slow reversion book on a measurement offset.

**The placebo is decisive.** Keep the same book, the same signal and the same overnight window, and
change one thing: mark the entry at the 15:55 price instead of at the closing auction print the
signal is measured from.

| overnight return measured as | design gross SR | holdout gross SR |
|---|---:|---:|
| `AUO[t+1] / AUC[t] − 1` — shares the print with the signal | **+4.26** (+4.40 bp) | **+2.78** (+4.21 bp) |
| `AUO[t+1] / C1555[t] − 1` — same window, unshared entry mark | **−6.16** (−7.23 bp) | **−5.08** (−8.20 bp) |

The book is short exactly the names whose closing print landed high relative to 15:55, and the
return is then computed *from that same high print*. Any noise in the print enters the signal with
one sign and the return with the other. That is the textbook microstructure-reversal trap, and it
accounts for **all** of the gross Sharpe — the same failure mode as the lead-lag sweep's
`D1_clonegap` 10-SE quote-staleness monster.

`C2`, `C1`, `C3`, `C4` are dead. Add them to the ledger.

---

## 7. Verdict and ledger additions

**The theme is noise.** No formula clears the programme-cumulative bar of 1.93 (intraday) / 1.47
(daily); the single formula that clears the *analytic family* bar is a shared-price artefact and is
unexecutable besides. **No new leg. No pre-registration. Nothing to size.**

New entries for the dead ledger, all with a measured reason rather than a p-value:

1. **Levered-ETF close rebalancing** — flow is real and its size is public arithmetic; captured
   gross is +0.79 bp/day against a 2.00 bp/day round-trip floor (break-even 0.40× the universe's own
   half-spread). Intensity and move-size gates make it worse, not better.
2. **Levered-ETF retail-positioning asymmetry** (`A6`) — the *only* formula in the pass that is
   net-positive in both windows with no shared-price contamination and a comfortable cost margin
   (break-even 4.32 / 3.06 bp against ~1.36 charged), and it is **0.79 / +0.35** — roughly a quarter
   of the noise bar. Not a candidate; recorded because it is the honest ceiling of the theme.
3. **Non-CEF stale-NAV premium/discount** (bond and international wrappers, 6 formulas) — gross
   never exceeds 0.62 bp/day against ≥1.0 bp/day of cost. The best-motivated timing (`B4`, the
   overnight home-market reprice) has the worst ratio in the set.
4. **Closing-auction print dislocation** (4 + 3) — artefact, above.
5. **Distribution-reinvestment timing** (bond-ETF ex-week yield sort) — gross +0.24 bp/day design,
   +0.03 holdout. Nothing there.
6. **Creation/redemption volume-anomaly proxy** — gross +0.04 bp/day design against 2.84 bp/day of
   cost. Own-volume anomaly relative to same-exposure siblings carries no next-day information; it
   is also a bad *gate* on live leg L2 (`E2`, `F2` both worse than ungated `B6`).
7. **Month/quarter-end as a gate** — `F1`/`F2`/`F3` are each worse than the ungated formula they
   gate. Consistent with the round-1/2 calendar verdict, now also in the cross-sectional
   flow-identified form the calendar sweeps never tried.

Two methodological notes worth keeping regardless of the verdict: round-trip books must be charged
2× gross turnover per day, and a raw auction feed must never be divided by a back-adjusted bar
cache. Both bugs were live in this harness and both produced promotable-looking numbers.
