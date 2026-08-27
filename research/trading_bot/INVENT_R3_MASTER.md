# INVENT R3 — MASTER SYNTHESIS

**265 formulas. Six fresh-angle themes. Zero new signal survivors.**

Five of the six themes declared themselves pure noise. The sixth's signal half — 107 conditioning
formulas on the legs that are already alive — is noise too. The only deployable output of the
entire round is a **zero-parameter sizing change** (stop fitting basket weights), plus one
**escalation** (an incumbent leg is decaying out of sample) and one **diagnostic** (half of the
anchor leg has stopped working).

Date: 2026-08-21. Synthesised by the basket-owner session from six independent theme agents.

---

## 1. The pooled multiple-testing bar

| convention | N | bar (t-units) |
|---|---|---|
| **round-3 pooled, analytic** | 265 | **3.341** ← headline |
| round-3 pooled, sign-agnostic (sign fit on design ⇒ 2N) | 530 | 3.542 |
| round-3 pooled on *declared trials* (conditioning counts each gate twice) | 472 | 3.509 |
| programme-cumulative (598 prior distinct formulas + 265) | 863 | 3.677 |

`E[max |t|] ≈ sqrt(2 ln N)`. Every theme computed its own within-theme bar (2.57–3.06 analytic).
Pooling raises the bar by 9–30% depending on the theme, and it is the pooled bar that applies,
because these six searches were commissioned together and the survivors are being read together.

**Converted to Sharpe units**, the pooled 3.341 bar is `3.341 / sqrt(years)`:

| panel | span | Sharpe SE | pooled bar in Sharpe |
|---|---|---|---|
| daily equities design (6.0 y) | 2016-02 … 2022-12 | 0.408 | **1.36** |
| intraday flow panel (3.48 y) | 2021 … 2024-06 | 0.536 | **1.79** |
| perp daily (3.0 y) | 2022-01 … 2025-01 | 0.577 | **1.93** |
| weekly 3-leg ensemble design (71 wk) | 2021-08 … 2022-12 | 0.856 | **2.86** |
| weekly ensemble holdout (188 wk) | 2023-01 … 2026-08 | 0.526 | **1.76** |

---

## 2. What cleared the pooled design bar, and what happened next

Exactly **three** of 265 design statistics exceeded 3.341. All three collapsed on held-out data.
That is not a near-miss story — it is *precisely* the count a pure null predicts at N = 265, where
E[max] = 3.34.

| # | formula | theme | design | held-out | verdict |
|---|---|---|---|---|---|
| 1 | `INTERACT T3 · VIX_LEVEL × RATE_CHG` (best quadrant) | condition | **t +4.47** | t −0.62, ΔSharpe **−0.91**, sign flips | DEAD |
| 2 | `GATE T3 · RATE_CHG` (median split) | condition | **t +3.58** | t +0.52, ΔSharpe +0.11 | DEAD — indistinguishable from zero |
| 3 | `R3B_TT_CONC` (top-trader position ratio ÷ account-count ratio) | perp structure | **SR 3.79** (≈ t 4.5 naive; clears its own bootstrap p95 of 2.26 and the pooled extrapolation of 2.87) | +0.46 / +0.67 net on two virgin windows | DEAD — collapse, not decay |

Below the bar but worth naming so nobody rediscovers them: max |t| in the event-calendar theme was
**3.11 — and it was the *ungated control*** (net −0.62 at 3 bp/side, real but uneconomic); the best
event-gated formula reached only 2.44 against that theme's own 2.88 bar. The dealer-positioning
theme's largest design |t| anywhere was **2.52, and in the opposite sign to its pre-registered
mechanism**. The exotic theme's best formula (design SR 1.11) did not even reach the **mean** of
its own null-max distribution (1.27) — the cleanest negative in the round, since there was no
winner to argue about.

**Nothing is promoted. No new signal leg is proposed.**

---

## 3. Theme-by-theme

| theme | N | own bar | verdict | best design | best held-out |
|---|---|---|---|---|---|
| **Condition & combine** the alive legs | 107 | 3.39 (314 declared) | conditioning **NOISE**; combining works but discovers nothing | t +4.47 | −0.91 ΔSR |
| **Event / catalyst calendar** (8-K metadata, FOMC, OPEX, recon, blackout) | 36 | 2.88 | **NOISE** | t 2.44 gated | net SR 0.08 → negative at 6 bp |
| **Dealer positioning / options flow** (first real GEX build) | 35 | 2.67 | **NOISE** | t 2.52 (wrong sign) | −6.62 SR on the design maximum |
| **Perp funding / OI / liquidation structure** | 32 | 2.63 (bootstrap p95 2.26) | **NOISE** | SR 3.79 | +0.46 |
| **Mechanical flow / structure** (levered-ETF, stale-NAV, auction print) | 28 | 1.38 SR (intraday) | **NOISE** | SR 1.67 | +0.96 but unexecutable artefact |
| **Exotic / left-field** (new listings, weekend, VOV, dispersion, stablecoin) | 27 | 1.58 SR | **NOISE** | SR 1.11 | −0.58 |

**Themes that are pure noise: 5 of 6** by the agents' own declarations. The sixth is noise on the
half that searched for signal (107 conditioning formulas → 0 survivors); its non-noise output is a
weighting rule with no fitted parameters, which is not a formula discovery and is treated as such
below.

### Three failure modes worth carrying into round 4

1. **Gating destroys value, repeatedly and independently.** Theme 1: gating T3 on VIX takes holdout
   Sharpe 1.29 → 0.75; on VIX9D/VIX → 0.50; on cross-leg trailing P&L → 0.39. Theme 6: all four
   regime-gates underperformed the raw book they gated, 4 for 4. Theme 5: every month/quarter-end
   flow gate (F1/F2/F3) was worse than the ungated formula. Theme 2: no calendar gate reached
   |t| = 2, and gates sharing a mechanism disagreed by 12.5 bp. **Future rounds should not spend
   formulas on conditioners.** This is now the most heavily replicated negative in the programme.
2. **Beta wearing a costume.** `SIDE_LONGONLY_HI` (run T3's long decile alone in an uptrend) beat
   the raw leg in *both* windows — the exact shape a real conditioner has. Subtracting realised net
   exposure × the equal-weight universe overnight return collapsed the lift to +0.10 at best and
   negative for 3 of 4 conditioners; beta contributed +4.90 bp/night. Killed.
3. **Shared-price measurement error.** `C2_AUCT_RESID_ON` posted +0.96 held-out net. Its signal *is*
   the closing-auction clearing price and its entry is that same print; a placebo marking entry at
   15:55 instead flips gross Sharpe +2.78 → −5.08, and the dislocation is 84% autocorrelated at lag
   1. Same failure mode as the lead-lag sweep's `D1_clonegap`. Any formula whose signal and fill
   share a price needs this placebo before it is believed.

---

## 4. Proposals to the basket owner

### P1 — `ENS_EQRISK_ALL3`: replace the fitted v5 risk budgets with flat equal-risk. **RECOMMEND.**

Not a new leg and not a signal. It is the a-priori default weighting (⅓/⅓/⅓ over T3, T7D1, T12-CEF,
each scaled to unit design vol on a weekly calendar) with **zero fitted parameters**.

| book | design SR | held-out SR (188 wk) |
|---|---|---|
| T3 / T7D1 / CEF alone | 1.64 / 0.60 / 2.68 | 1.24 / 1.70 / **1.81** |
| **`ENS_EQRISK_ALL3`** (un-fitted) | 2.70 | **2.93** |
| `ENS_MINVAR` (fitted) | 2.77 | 2.93 (tie) |
| `ENS_SHARPE_WEIGHTED` (fitted) | 3.03 | 2.90 |
| **`ENS_BASKET_V5`** (the currently frozen budgets) | 2.77 | **2.45** |
| 4 × regime-switching weights (fitted) | 3.10–3.38 | 2.59–2.97 |

The textbook overfit signature: **the more the weights are allowed to learn, the worse they
travel.** The frozen v5 budgets cost **−0.48 Sharpe** versus doing nothing.

**On the pooled bar, stated plainly.** Design 2.70 on 71 weeks is t = 3.16 — it does **NOT** clear
the pooled 3.341 bar (which is 2.86 in Sharpe units on that thin window). It does not clear its own
theme's 314-trial bar either. **I am not promoting it as a discovery**, and it must not be sized as
though a 2.93 had been found. The case for it is entirely different in kind: there is nothing to
select between — it is the default, it has no parameters, and the evidence is a *negative* result
about the fitted alternative. Choosing the simpler of two already-deployed weightings is not a
multiple-testing event.

**Guard / sizing caveat (mandatory).** Size on the **stressed** rung, not the headline. Charging
T7 a real 1.13 bp half-spread per leg, T3 2× entry half-spread plus a real exit spread instead of a
free opening cross, and CEF an extra half of its measured 11.53 bp: legs go T3 **0.61** / T7D1
**0.79** / CEF **1.58**, ensemble **1.75**, worst holdout third **1.21**. That is a lift of only
**+0.17 over holding the CEF leg alone** — and the CEF leg carries its own v4/v5 caveats (edge
concentrated in one half-sample, 37% of the stressed mean in 5 of 114 weeks, capacity capped in the
low single-digit $M by CEF auction volume). Under realistic costs **this basket is mostly the CEF
leg plus a diversification kicker.** Size it that way.

Also on the record: the +1.11 headline lift is **arithmetic, not discovery.** Feeding each leg's own
held-out Sharpe and the *design* correlation matrix into `Σwᵢ·SRᵢ / √(wᵀCw)` predicts 2.61; realised
2.93; the +0.32 excess is realised correlations landing more negative than design (+0.04/+0.05/+0.07
→ −0.10/−0.02/−0.10) and is not significant.

### P2 — `ENS_EQRISK_T3_T7`: the long-history twin. **Do not freeze separately — it is subsumed.**

Same rule on the two legs that have 361 design / 188 holdout weeks (no CEF truncation), so it is the
better-powered read on whether the rule travels: design t 4.82, holdout **+2.21** vs legs 1.24 and
1.70, **+1.05 stressed**. Design corr −0.06, holdout corr −0.10. Keep it as the **fallback book if
CEF capacity binds** (a live risk at low single-digit $M), not as an additional leg.

### P3 — `DIAG_T3_SHORT_HALF_DECAY`: add a per-half diagnostic to the forward log. **Not a rule change.**

Decomposed against the equal-weight universe overnight return: T3's **long** half +9.51 bp t 5.48
(design) → +11.28 bp t 3.85 (holdout); **short** half +7.58 bp t 4.75 → **+3.87 bp t 1.36**. The
short half has stopped working and the long half is intact — and this is the real reason the
"long-only in an uptrend" variant looked good. **Do not change the frozen L1 rule**: t = 1.36 is not
yet evidence of death, and a long-tilted version harvests overnight equity beta, which is on the
dead ledger. Monitor only. It costs nothing.

### P4 — `XS_GLSR_Z`: **DEMOTION ESCALATION. Do not re-size this leg.**

The perp-structure agent built a new Binance metrics panel (`perpmicro_cache/panel1h_r3meta.npz`,
123 symbols, 2022-10 … 2026-08, parsed from 91,602 daily metrics zips) that extended the previous
panel past its 2024-12-31 wall. That gave the incumbent leg its **first out-of-sample read past
2024-12**:

`+3.00 net` (design 2023-01…2024-06) → **`+0.30`** (2024-06…2025-01) → **`−1.21`** (2025-01…2026-08)

Gross on the last window is already −0.60, so this is not a cost artefact, and the OI-orthogonalised
version decays identically, ruling out leverage-build contamination. **Caveat that keeps this an
escalation and not a kill:** the last window is a thin ~20-name alphabetically-biased A–B-ticker
cross-section at min 8 names. One window, small universe.

**Action:** the leg is already logging-only under the v4 freeze — keep it there. Continue the Binance
metrics backfill past `BNXUSDT` (same downloader, alphabetical continuation) and re-run on a full
2025–2026 cross-section **before** the leg is ever sized again. Cheap data job, highest-value
follow-up in the round.

### P5 — Everything else: **REJECT.**

Named explicitly so they are not rediscovered as "near-misses":

* `C6_V1D_SPIKE_CONTINUE` — highest design Sharpe of its theme (3.27) and the worst holdout in the
  study (−6.62). The 3.27 is an artefact of trading 60 days out of 2.64 years; its design **t** was
  only +1.59 against a 2.67 bar. It never cleared anything.
* `C2_AUCT_RESID_ON` / `F01_REBAL_CLV_FADE_POOLED` / `A6_LETF_ASYM_XS` / `D1_DISP_TS` /
  `B3_WKND_FUND_CARRY` — each below its own theme's bar before pooling.
* `E04_EARN_GAP_OC_CONT` — rejected on **mechanism**: it is intraday momentum, killed by B22D/B22E.
  Ditto `B11_GSIGN_CONTANGO_LASTHR`, which is late-day intraday momentum with the sign flipped and
  is gross-negative anyway.
* `A05_ITEM_701_REGFD_5`, `A13_AMC_VS_BMO_5` — promoting either would be selecting on the holdout.
* `GATE T3 · CTRL_PREV` (holdout ΔSharpe +0.49, design t only +1.70 — half the bar).
* `R3A_NETCARRY_MOM` — 0.998 correlated with plain `r168` P&L; it *is* round 1's `XS_MOM168`.
* `R3B_OIWAP_GAP` / `R3B_LIQ_ASYM` / `R3B_LIQ_DIST_25X` — the only class-B set positive in design and
  both holdouts, and **better with the OI weights removed** (equal weights: 2.34/2.32/2.50). The
  reconstructed liquidation cost basis is a story; the P&L is 7-day vol-scaled cross-sectional
  momentum, already in the ledger.

---

## 5. Dead-ledger additions from round 3

Every entry below was tested this round with a frozen design window and a held-out window, and is
dead. Feed this to round 4.

**Conditioners / gates (all forms, on all alive legs).** VIX level, VIX term structure, VIX9D,
VVIX, dVIX; realised vol 20d and 5d/20d; SPY range and volume; trend 200d/20d and 20d momentum,
including long-only-in-uptrend (beta); VRP; rate level and rate change; continuous TILT versions of
all of the above; two-way regime interactions (6 pairs × 2 legs); day-types (Mon/Fri/midweek/
turn-of-month/OPEX week); cross-leg trailing-P&L gating (worst of all, −0.90); and a genuinely new
mechanism, **CEF-universe median-discount retail sentiment (Lee-Shleifer-Thaler) gating the equity
legs** — design t 0.00 to 1.93, holdout ΔSharpe −0.86 to −0.09.

**Event / catalyst calendar.** 8-K item-code composition; release-time migration vs own trailing
4-quarter median hour; reporting-lag delta; buyback blackout windows from point-in-time predicted
dates (`B03_BUYBACK_WINDOW`, the most mechanically appealing idea in the theme, is the most
decisively dead: net t −8.2); peer-sympathy fade; attention-crowding gates; quarter/month-end
index-rebalance close distortion; Russell recon approximation.

**Dealer positioning.** GEX sign, gamma centre-of-mass pin, gamma flip level, put-gamma surge,
call/put walls, big-gamma clamp, relative-gamma regime; whole-dollar and $5 strike pinning;
post-OpEx gamma roll-off; OpEx-week reversal; the VIX9D/VIX3M gamma-sign proxy intraday and
overnight; vanna (skew × vol change); charm drift into monthly expiry; AM-settlement gap; VIX1D
level, change and cheapness.

**Perp structure beyond XS_GLSR_Z.** Funding term structure (breakeven 0.7–1.4 bp/side against a
4.5 bp fee — emphatically dead, not marginal); funding second-order stats (rolling AR1, mean-reversion
speed, beta-to-market-funding, idiosyncratic funding, carry information ratio); funding/flow lead-lag
(−2.5 both windows); flow-quadrant decomposition (`R3B_COVER_SHARE`: design 3.53 → −1.02 virgin);
OI-orthogonalised GLSR (0.92–0.96 correlated with the incumbent — the "orthogonal part of the
existing leg" does not exist); top-trader conviction concentration.

**Mechanical flow.** Levered-ETF close rebalancing (flow is real and its size is public arithmetic;
captured gross +0.79 bp/day against a 2.00 bp/day round-trip floor — breakeven 0.40× the universe's
own half-spread); levered-ETF overnight give-back; non-CEF stale-NAV premium/discount on bond and
international wrappers (best-motivated timing has the worst ratio in the pass); closing-auction print
dislocation (artefact + unexecutable); distribution-reinvestment timing; creation/redemption
own-volume anomaly; month/quarter-end as a cross-sectional flow gate.

**Exotic.** New-listing / listing-age effects (first week, first month, day-1 fade, birth funding,
attention decay, age tilt) — *with the honest caveat that the listing cohort is selection-biased and
the bias favours "long new listings", so the negative is the conservative reading*; weekend structure
(cross-sectional weekend-return fade, weekend taker-flow fade, weekend-only funding carry, weekend
vol-ratio regime, weekend dispersion); vol-of-vol beyond a plain rank; cross-crypto dispersion and
average-correlation regimes; positioning-crowding aggregates as primary signals; stablecoin
mint/burn impulse to basket, to BTC, and to alts-vs-BTC.

### Two ledger *corrections* (previous entries were wrong)

1. **"GEX: no free historical dealer-gamma series exists at all"** (from NEWTERR_optimp) is **false
   and should be amended.** Alpaca serves expired OPRA option daily bars back to 2024-02-01; a
   ±$15 near-money ladder in $1 steps, calls and puts, across all 640 SPY expiries was built
   (`research/data/gex_cache/`, 17 MB, regenerable in ~25 min). It is computable. It just does not
   predict SPY.
2. **The textbook GEX sign-flip is structurally degenerate on SPY at short tenor.** Gamma-weighted
   near-money option volume is put-dominated on **97% of days** (358 of 369 sampled). Under the
   standard convention, SPY 0–5DTE dealers are **always** net short gamma near the money — there is
   no zero crossing to trade. `A4_GAMMA_FLIP_LEVEL` collapsed to n=30 and `A6_CALL_WALL_RESIST` to
   n=0. Anyone proposing a "gamma flip" strategy on SPY should read this first.

---

## 6. Method and honesty notes

* **Windows.** Every theme froze a design window, fit all signs and thresholds there, and left a
  later window untouched until the design table was written. Splits: equities 2016-02…2022-12 /
  2023-01…2026-08 (conditioning), 2016-01…2021-12 / 2022-01…2026-08 (event calendar), perps
  2022-11…2024-10 / 2024-10…2026-08 (class A) and 2023-01…2024-06 / 2024-06…2025-01 / 2025-01…2026-08
  (class B), exotic 2022-01…2025-01 / 2025-01…2026-07.
* **The holdout is not virgin at the LEG level.** 2023–2026 carried previously reported held-out
  numbers for T3, T7 and T12. What was never fit there is a *conditioner*, so every conditioning
  number in theme 1 is a **difference** — conditioned minus raw on the identical window, both arms
  seeing the same tape. Stated so nobody reads a ΔSharpe as a fresh Sharpe.
* **Holdout reuse budget.** The perp/crypto window 2025-01…2026-08 has now been used **three** times
  (perpmicro_sweep2's 51 class-A formulas, perp-structure R3, exotic R3). It should not be spent on
  crypto again without a genuinely new data axis.
* **Power, so the negatives are scoped.** The event-calendar theme's minimum detectable true
  annualised Sharpe at its bar is 1.19–1.32 for *every* formula regardless of event frequency
  (median 1.30), because with a ~5 y design window the floor is `bar / sqrt(years)`. Pooling four
  quarter-end events a year into a sixteen-a-year calendar buys nothing in detectability. The honest
  finding is "**no event window here carries a true Sharpe ≥ ~1.3**" — a true Sharpe-0.6
  rebalance edge is not excluded and cannot be by any five-year panel.
* **Three harness bugs were found and fixed before results were read**, all worth carrying forward:
  (a) round-trip books charged as persistent books (fully-liquidated overnight/intraday books need
  2× gross turnover per day — the fix moved `A1_LETF_PUSH_TS` from +0.54 to −0.96); (b) raw auction
  prints divided by split/dividend **back-adjusted** bars (TQQQ at $21.93 against a ~$100 traded
  price); (c) the design sign applied to **net** P&L, which flips the direction of the cost term and
  made shock-cost Sharpes come out *higher* than headline-cost Sharpes — correct construction is to
  orient on zero-cost P&L then re-run with sign-multiplied weights. Two exotic formulas looked like
  survivors under the broken version. **Corollary trap:** a large negative net Sharpe is not a
  sign-flip discovery — flipping a book gives `−gross − 2·cost`, not `+|net|`. Every row in the
  theme reports now carries gross Sharpe, gross bp, cost bp and break-even half-spread side by side.
* **Controls everywhere.** `B15_CONTROL_UNCOND_FADE` (no options information at all) posts
  −0.49/−0.43, exactly where every dealer-conditioned intraday fade lands — the cleanest statement
  of that theme's verdict. `CTRL_XS_FUND` posts +1.02 design / +0.60 holdout, consistent with the
  standing "carry is real but not fundable standalone", which validates the crypto harness rather
  than the formulas. Every gated event book has a twin with the gate removed, so the question was
  always "what does the event add", never "does the signal exist".
* **No network crawls ran inside an agent.** All VIX/SPY/rate inputs came from cached
  `volterm_cache`; one free DefiLlama GET for aggregate stablecoin supply (restated, not
  point-in-time — family F has the weakest provenance in the round and its result is a rounding
  artefact, not a hint). No frozen leg spec was altered; no frozen file was touched.

### Declared untested (not reported as negatives)

Crypto token-unlock cliffs (no vesting feed cached); index add/delete reconstitution proper (no
point-in-time membership); CPI release dates (no BLS schedule cached — the "second Wednesday" proxy
is too crude to count as a known schedule); true option open interest (Alpaca's snapshot has no
`openInterest` field, verified live; Cboe daily stats 403; OCC per-series paid); the OI-vs-volume
proxy validation (Yahoo option endpoint 401 then 429); pre-2024-02 per-strike gamma; single-name
GEX; **cross-venue funding dispersion and cross-venue term structure** (the cache is Binance USD-M
only — this sub-question is genuinely open); real levered-ETF shares-outstanding / AUM rather than
the dollar-volume proxy.

---

## 7. Cheap, high-value follow-ups (in priority order)

1. **Backfill the Binance metrics panel past `BNXUSDT`** and re-run `XS_GLSR_Z` on a full 2025–2026
   cross-section. This decides whether a basket leg is dead. Same downloader, alphabetical
   continuation, no new code.
2. **One Yahoo OI-vs-volume correlation check** when the rate limit clears. It either validates or
   retires the entire 17 MB `gex_cache` as an instrument, for the cost of one request.
3. **Extend the close-location study back to the 1990s** on the t3 monthly/auction caches and re-run
   on an MOC-legal rail (~0.5 bp/side). The five-year panel cannot exclude a true Sharpe-0.6
   rebalance edge; a thirty-year one can.
4. **Do not** spend another slice on dealer positioning from free data, on conditioners of any kind,
   or on the crypto 2025–2026 holdout.

---

## 8. Files

**This synthesis:** `research/trading_bot/INVENT_R3_MASTER.md`, `.json`

**Theme reports:** `INVENT_R3_condition_combine.{md,json,_phase2.json,_phase3.json,_phase4.json}` ·
`INVENT_R3_event_calendar.{md,json}` · `INVENT_R3_dealer_positioning.{md,json}` ·
`INVENT_R3_perpstructure.{md,json,_A.json,_B.json,_ATTRIB.json,_ATTRIB_OIWAP.json,_{A,B}_pnl.npz}` ·
`INVENT_R3_flow.{md,json,_design.json,_holdout.json,_diagnostics.json,_*_pnl.npy}` ·
`INVENT_R3_exotic.{md,json}`

**Harnesses:** `scripts/invent_r3_conditioning.py`, `invent_r3_phase{2,3,4}.py` ·
`scripts/inv3_build_panel.py`, `inv3_event_calendar.py`, `inv3_run{,2,3}.py`, `inv3_null.py` ·
`scripts/invent_r3_dealer.py`, `invent_r3_gex_fetch.py`, `invent_r3_report.py` ·
`scripts/trading_bot/perpmicro_r3_metapanel.py`, `perpmicro_r3.py`, `perpmicro_r3_attrib{,_oiwap}.py` ·
`scripts/invr3_flow_{data,eval,diag}.py` ·
`scripts/trading_bot/invent_r3_{exotic,panel}.py`

**Caches:** `research/data/invent_r3/` · `research/data/inv3_cache/` · `research/data/gex_cache/`
(17 MB, gitignored, regenerable) · `research/data/perpmicro_cache/panel1h_r3meta.npz` ·
`research/data/invr3flow_cache/` · `research/data/invr3_cache/`

*Note: two agents nearly collided on `research/data/invr3_cache/`; the flow agent moved to
`invr3flow_cache/`. Worth a naming convention next round.*
