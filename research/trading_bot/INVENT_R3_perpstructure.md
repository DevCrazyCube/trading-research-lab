# INVENT R3 — deeper perp funding / OI / liquidation structure

**Verdict: the theme is NOISE. Zero survivors. Nothing to add to the basket.**

Round 3 tested **32 formulas** (23 pre-declared candidates + 9 decomposition formulas built to
audit the two that looked alive). Every candidate failed on one of three counts:

1. it never cleared the multiple-testing bar on the design window;
2. it cleared design and then collapsed out of sample; or
3. it cleared design *and* held out, but **decomposition proved it was 7-day cross-sectional
   momentum in a costume** — a formula already in the round-1 ledger (`XS_MOM168`).

Category 3 is the interesting one and is why this round was worth running: two of the most
mechanistically attractive constructs in the whole perp theme (a reconstructed
liquidation-heatmap cost basis, and relative open-interest rotation) both turn out to be
momentum with extra steps. That is now nailed down with residual tests rather than asserted.

---

## 1. What was tested and why it is not a re-run

Rounds 1 and 2 burned 106 formulas on this panel. Round 1 tested the **level** and the **first
difference** of funding, OI and the long/short ratios. Round 2 tested **path statistics** of
those same series (persistence, flip rate, streaks) and **conjunctions** (products) of round-1
primitives.

Round 3 deliberately targeted objects neither round could express:

| family | what is new |
|---|---|
| carry **second-order** | rolling AR(1) of the funding series (mean-reversion *speed*), rolling *beta* of own funding to market funding, the idiosyncratic residual after removing that beta, and the *slope* and *curvature* of the trailing 3/9/27-period carry curve. Two coins can have identical funding level and opposite AR(1). |
| **liquidation heatmap** | an OI-weighted average entry price (OIWAP): price accumulated weighted by *positive OI creation* with a 7d decay, split by the side of the aggressor flow that created it, and the distance from spot down to the 25x liquidation band that cost basis implies. Round 1's `XS_LIQPROX` was drawdown + realised vol; it never reconstructed a cost basis. |
| **relative leverage flow** | the coin's *share* of total universe open-interest value and its drift. Round 2 did volume share; nobody did OI share. |
| **flow quadrants** | volume split by (dOI rising/falling) x (aggressor buying/selling), separating short-covering from long-liquidation from fresh leverage. |
| **orthogonalised incumbent** | `XS_GLSR_Z` residualised cross-sectionally on OI growth — explicitly designed to be the part of the basket's existing leg that is not just a leverage-build proxy. |

**Cross-venue funding was NOT tested.** The cache is Binance USD-M only; there is no second
venue's funding in this repository. Claiming a cross-venue funding-dispersion result would
have required a new network crawl, which this round did not do. That sub-question is
**untested**, not dead.

## 2. Windows, universe, costs

Inherited unchanged from `perpmicro_sweep.py`: signal uses data through the CLOSE of bar `t`;
entry and exit at the OPEN of a bar the signal cannot see; `H` overlapping tranches; funding
accrued at the settlement bar; **5.5 bp/side** (4.5 bp published Binance taker + 1.0 bp declared
half-spread); sign oriented on the design window and **frozen** out of sample.

* **Class A** (price / flow / funding only; panel runs to 2026-08-16), top-60 by trailing 7d
  quote volume, min 20 names:
  * DESIGN `2022-11-01 -> 2024-10-01` (700 days)
  * HOLDOUT `2024-10-01 -> 2026-08-16` (684 days)
* **Class B** (needs the OI / long-short metrics feed), top-60, min 20 names:
  * DESIGN `2023-01-01 -> 2024-06-01` (517 days)
  * HOLD_B1 `2024-06-01 -> 2025-01-01` (214 days, dense cross-section)
  * HOLD_B2 `2025-01-01 -> 2026-08-16` (592 days) — **thin**: the metrics cache download is
    alphabetical and only reaches "B" after 2024-12, so this window has ~20 A–B tickers, run at
    min 8 names. Directional evidence only; never used for selection.

**Data built this round:** `research/data/perpmicro_cache/panel1h_r3meta.npz` — hourly OI,
OI value, top-trader count/position L/S, global account L/S and taker L/S vol ratio for the 123
symbols of the extended grid that have the Binance daily metrics dumps, parsed from 91,602 zips
in `research/data/orphanflush_cache/raw/metrics/`. This is what makes HOLD_B2 possible at all —
the previous `panel1h.npz` stopped at 2024-12-31.

## 3. Noise bar

Sign-flip block bootstrap (block 5 days, 4000 draws) of the max |Sharpe| across the whole
tested set, preserving cross-formula correlation:

| set | mean | p50 | **p95** |
|---|---|---|---|
| class A design (12 formulas, 700 d) | 1.46 | 1.43 | **2.15** |
| class B design (12 incl. incumbent, 517 d) | 1.44 | 1.38 | **2.26** |

Analytic `sqrt(2 ln N)`: **2.63** at N = 32 for this round; **3.14** at N = 138 for the perp
theme cumulatively (56 round 1 + 50 round 2 + 32 round 3). The bootstrap p95 is the bar used
below because it accounts for the correlation between formulas and the finite window.

## 4. Class A results — funding term structure and second-order carry

Net Sharpe at 5.5 bp/side. Sign frozen from design.

| formula | design | holdout | verdict |
|---|---:|---:|---|
| R3A_NETCARRY_MOM | **+1.53** | **+2.85** | **momentum in disguise — see §6** |
| R3A_FLOW_VS_FUND | +1.14 | +0.69 | below bar |
| R3A_TAKER_AR1 | +0.94 | +0.10 | below bar, decays |
| R3A_FUND_AR1 | +0.90 | +1.16 | below bar |
| R3A_FUND_BETA | +0.65 | +0.49 | below bar |
| R3A_FUND_ALPHA | +0.60 | +1.13 | below bar |
| R3A_WEEKEND_CARRY | +0.51 | +0.35 | below bar |
| R3A_CARRY_IR | +0.42 | +0.68 | below bar |
| R3A_FUND_DECAY | −0.01 | −0.42 | dead |
| R3A_FUND_TERM | −1.26 | −1.01 | **dead: gross +0.43, turnover 1.55/day, breakeven 1.4 bp/side** |
| R3A_FUND_CONVEX | −1.58 | −1.68 | dead |
| R3A_FUND_LEAD_FLOW | −2.54 | −2.37 | dead |

**The funding term-structure sub-theme is emphatically dead.** `R3A_FUND_TERM` (3-period vs
21-period mean funding, scaled by 30d funding sd) and `R3A_FUND_CONVEX` (curvature) both have
gross Sharpes near zero *and* turn the book over 1.55–1.7x per day, giving breakeven costs of
**0.7–1.4 bp/side** against a 4.5 bp published taker fee. The carry curve reshapes far faster
than the price impounds it; there is no tradable slope.

The second-order carry family (AR1, beta, alpha, IR) is uniformly in the +0.4 to +1.2 band on
both windows — consistent, never significant. That is what a small, real, but sub-cost effect
looks like, and it is also what pure noise looks like at N = 12. Nothing here is promotable.

## 5. Class B results — OI, liquidation heatmap, flow quadrants

| formula | design | HOLD_B1 | HOLD_B2 (thin) | corr vs `XS_GLSR_Z` (design) | verdict |
|---|---:|---:|---:|---:|---|
| R3B_TT_CONC | **+3.79** | +0.46 | +0.67 | +0.26 | design winner, **dies OOS** |
| R3B_COVER_SHARE | **+3.53** | +2.25 | **−1.02** | −0.02 | dies on the virgin window |
| R3B_GLSR_RESID_OI | +2.64 | +0.53 | −1.30 | **+0.92** | not orthogonal, no improvement |
| R3B_NEWLONG_SHARE | +2.31 | −0.07 | +2.05 | +0.27 | inconsistent |
| R3B_OIWAP_GAP | +2.26 | +2.76 | +2.13 | +0.34 | **= 7d momentum — see §6** |
| R3B_LIQ_ASYM | +2.26 | +2.74 | +2.10 | +0.35 | same construct as above |
| R3B_OI_STICKY | +2.05 | +1.17 | +0.18 | +0.12 | below bar, decays |
| R3B_OISHARE_CHG | +1.74 | +0.92 | +1.84 | +0.41 | **mechanically contains r168 — §6** |
| R3B_LIQ_DIST_25X | +1.20 | +2.53 | +2.46 | +0.25 | = OIWAP_GAP + a low-vol tilt |
| R3B_FLUSH_ASYM | +1.07 | +0.67 | +0.78 | +0.21 | below bar |
| R3B_FUNDxOISHARE | +0.69 | +0.94 | +0.76 | +0.34 | below bar |
| *REF_XS_GLSR_Z (incumbent)* | *+3.00* | *+0.30* | ***−1.21*** | *+1.00* | *see §7* |

Two design winners cleared the 2.26 bar: `R3B_TT_CONC` (3.79) and `R3B_COVER_SHARE` (3.53).
Both then failed. `TT_CONC` fell to +0.46 / +0.67; `COVER_SHARE` held on HOLD_B1 (+2.25) and
then went **negative** (−1.02) on the virgin 2025–2026 window. Neither is promotable.

## 6. The decomposition that kills the two survivors

This is the part of round 3 that produced actual knowledge.

### 6a. `R3A_NETCARRY_MOM` is `XS_MOM168`

The formula is 7d return minus 7d funding paid — "the total return a levered long really
earned". Funding is O(10 bp/week); a 7d crypto return is O(1000 bp/week. Decomposition on the
same panel and windows (`INVENT_R3_perpstructure_ATTRIB.json`):

| | design | holdout |
|---|---:|---:|
| M_ONLY (`r168`, = round-1 `XS_MOM168`) | +1.55 | +2.94 |
| NETCARRY (round-3 formula) | +1.53 | +2.85 |
| NETCARRY with the funding term **tripled** | +1.54 | +2.71 |
| F_ONLY (realised carry alone) | +0.73 | +0.92 |
| **NC_RESID_M** (XS residual of NETCARRY on `r168`) | **+0.07** | **+0.81** |
| corr(NETCARRY, M_ONLY) daily P&L | **0.998** | **0.987** |

Correlation 0.998. Tripling the funding weight barely moves it. The residual is +0.07 on design.
This is round 1's formula with rounding error, and round 3 claims nothing for it.

### 6b. The whole liquidation-heatmap family is a vol-scaled moving-average crossover

`R3B_OIWAP_GAP` / `R3B_LIQ_ASYM` / `R3B_LIQ_DIST_25X` were the only class-B signals positive in
design *and* both holdouts, and they share one construct: a 7d-decay average price weighted by
positive OI creation, compared to spot, divided by daily vol. Replace the OI weights with
nothing and with volume (`INVENT_R3_perpstructure_ATTRIB_OIWAP.json`):

| | design | HOLD_B1 | HOLD_B2 (thin) |
|---|---:|---:|---:|
| GAP_EQ (equal-weight 7d EWMA, **no OI at all**) | +2.34 | +2.32 | +2.50 |
| GAP_QV (volume-weighted, **no OI at all**) | +1.19 | +2.22 | +2.51 |
| GAP_OI (= `R3B_OIWAP_GAP`) | +2.26 | +2.76 | +2.13 |
| MOM_VOL (`r168` / daily vol) | +2.09 | +1.62 | +2.45 |
| **OI_RESID** (XS residual of GAP_OI on GAP_EQ) | **+0.08** | **−2.29** | **−0.85** |
| corr(GAP_OI, GAP_EQ) | 0.934 | 0.957 | — |
| corr(GAP_OI, MOM_VOL) | 0.842 | 0.861 | — |

**The open-interest weighting contributes nothing and is negative out of sample.** Strip it and
you get an equal-weight 7d EWMA price gap, which is 0.89-correlated with plain vol-scaled 7d
momentum. The "reconstructed cost basis / distance to the 25x liquidation cluster" story is a
story; the P&L is 7d cross-sectional momentum, already in the ledger. `R3B_LIQ_DIST_25X` is
additionally just `OIWAP_GAP` plus `+0.0408 / daily_vol`, i.e. the same gap with a low-vol tilt
bolted on (hence its −0.30 market correlation) — and round 1 already had `XS_LOWVOL`.

### 6c. `R3B_OISHARE_CHG` and `R3B_FUNDxOISHARE` are contaminated by construction

Both use OI **value** (`sum_open_interest_value` = OI units x price). Therefore
`dlog(oi_value, 168h) = dlog(oi_units, 168h) + r168`, and the OI-share signal mechanically
embeds the 7d price return. The right version uses OI in contract units — which is round 1's
`XS_OI72`, already tested. Design error on my part, caught in review, reported rather than
buried.

## 7. Non-formula finding worth escalating: the incumbent `XS_GLSR_Z` is negative on 2025–2026

`REF_XS_GLSR_Z` was re-run in this round only as a correlation benchmark, but the metrics panel
built here extends past 2024-12 for the first time, so it produced the **first out-of-sample
read on the basket's perp leg beyond the round-1 window**:

* design 2023-01 → 2024-06: **+3.00** net
* HOLD_B1 2024-06 → 2025-01: **+0.30** net
* HOLD_B2 2025-01 → 2026-08: **−1.21** net (gross −0.60, breakeven −5.4 bp/side)

**Caveats that matter:** HOLD_B2 is the thin ~20-name A–B-ticker cross-section, run at min 8
names, so the universe is both small and alphabetically biased, and this is one window. It is
not proof the leg is broken. But the sequence +3.00 → +0.30 → −1.21 is a monotone decay, and the
gross number is already negative in the last window, so the decay is not a cost artefact.
`R3B_GLSR_RESID_OI` (the orthogonalised version, corr 0.92 with the incumbent) decays the same
way, which rules out "the leverage-build contamination broke it".

**Recommendation to the basket owner: complete the metrics backfill past "B" and re-run
`XS_GLSR_Z` on a full 2025–2026 cross-section before sizing that leg again.** That is a cheap
data job (the same downloader, continued past `BNXUSDT`) and it is now the highest-value
follow-up in this theme.

## 8. Files

* `scripts/trading_bot/perpmicro_r3_metapanel.py` — builds `panel1h_r3meta.npz` (hourly OI /
  L-S metrics on the 2022-10 → 2026-08 grid) from the Binance daily metrics dumps.
* `scripts/trading_bot/perpmicro_r3.py` — the 23 round-3 candidate formulas, both classes.
* `scripts/trading_bot/perpmicro_r3_attrib.py` — the `NETCARRY` / momentum decomposition.
* `scripts/trading_bot/perpmicro_r3_attrib_oiwap.py` — the OIWAP / equal-weight / momentum
  decomposition.
* `research/trading_bot/INVENT_R3_perpstructure_{A,B}.json` — full per-window result records.
* `research/trading_bot/INVENT_R3_perpstructure_{A,B}_pnl.npz` — daily net P&L per formula per
  window, for the correlation work.
* `research/trading_bot/INVENT_R3_perpstructure_ATTRIB{,_OIWAP}.json` — decomposition records.
* `research/trading_bot/INVENT_R3_perpstructure.json` — this summary, machine-readable.

## 9. Dead ledger additions

Add to `FORMULA_SWEEP_MASTER.md` / `FINDINGS.md`:

* **Funding term structure (front-vs-deferred slope, curvature) — DEAD.** Gross Sharpe ~0.2–0.4,
  turnover 1.5–1.7x/day, breakeven 0.7–1.4 bp/side vs a 4.5 bp fee. Not marginal; not close.
* **Funding second-order statistics (AR1 / half-life, funding beta, idiosyncratic funding,
  carry information ratio) — DEAD.** All in the +0.4 to +1.2 band on both windows, none clears
  the 2.15 bootstrap bar.
* **Funding-vs-flow lead/lag — DEAD.** `R3A_FUND_LEAD_FLOW` is −2.5 net on both windows.
* **Liquidation-heatmap proximity via a reconstructed OI-weighted cost basis — DEAD as an
  independent mechanism.** The OI weighting adds nothing (residual +0.08 design, −2.29 / −0.85
  OOS); what survives is 7d vol-scaled cross-sectional momentum, already known.
* **OI share / leverage rotation — DEAD as specified**, and any future version must use OI in
  contract units, not OI value, or it silently re-imports the price return.
* **Flow-quadrant decomposition (short-covering vs long-liquidation share) — DEAD.** Best design
  Sharpe of the round (3.53) and negative on the virgin window.
* **Top-trader position-vs-account-count concentration — DEAD.** 3.79 design, 0.46 / 0.67 OOS.
* **`XS_GLSR_Z` residualised on OI growth — DEAD.** 0.92-correlated with the incumbent, no
  improvement in any window.
* **Cross-venue funding dispersion — UNTESTED** (single-venue cache only), not dead.
