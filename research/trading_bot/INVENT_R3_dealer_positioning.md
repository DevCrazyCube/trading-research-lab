# INVENT-R3 — DEALER POSITIONING / OPTIONS FLOW

**36 original formulas built (35 live, 1 degenerate), three tracks, one verdict.** Design windows tested, later windows held out and untouched until the design numbers were frozen.

## 0. The data wall, stated first

There is **no free historical option open-interest series** — Cboe's daily market-statistics archive is 403, OCC per-series is paid, Alpaca's snapshot carries no `openInterest` field at all (verified this session), and Deribit's free sample holds six snapshots. `NEWTERR_optimp` therefore declared GEX **untestable** and proxied it with curve shape.

This round found the substitute that round did not: **Alpaca serves expired OPRA option daily bars back to 2024-02-01**, per contract, with volume. That buys a real per-strike gamma map — built from *cumulative traded volume* rather than open interest — for 2.5 years. It is the first per-strike dealer-gamma construct this programme has ever been able to compute.

Cache: `research/data/gex_cache/` — one JSON per expiry, 640 expiries, ±$15 strike ladder in $1 steps, calls and puts, 12 calendar days of bars each. Rebuilt by `scripts/invent_r3_gex_fetch.py` (idempotent).

## 1. The three tracks and their honest null bars

| track | what it reads | design | holdout | design yrs | E[max Sharpe] under null |
|---|---|---|---|---|---|
| **A** | per-strike gamma from real chains | 2024-02-01 .. 2025-08-31 | 2025-09-01 .. 2026-08-14 | 1.58 | **2.12** |
| **B** | price-only dealer footprints | 2016-01-04 .. 2021-12-31 | 2022-01-03 .. 2026-08-14 | 6.00 | **1.09** |
| **C** | 0DTE era, VIX1D | 2022-05-13 .. 2024-12-31 | 2025-01-02 .. 2026-08-14 | 2.64 | **1.64** |

`sqrt(2 ln N)` with live N = 35 is **2.67** in t-stat space. Divided by `sqrt(design years)` it becomes the Sharpe a formula must CLEARLY beat before its design number means anything.

## 2. Every formula, design and holdout

Costs charged per side on |Δw| at **1.5 bp** headline (SPY intraday marketable; the measured 15:45 half-spread is 0.13 bp and regulatory pass-through 0.15 bp, so this is deliberately punitive). Rungs 0.5 / 1.0 / 1.5 / 3.0 in the JSON.

| formula | mechanism (one line) | design S | design t | n | holdout S | holdout t | n |
|---|---|---|---|---|---|---|---|
| `B1_PIN_MONTHLY_1D` | dealers long gamma at the heavy $1.0 strike pin spot to it into the close mark | +1.18 | +0.60 | 65 | +1.40 | +0.63 | 52 |
| `B2_PIN_FRIDAY_1D` | dealers long gamma at the heavy $1.0 strike pin spot to it into the close mark | -0.78 | -0.82 | 279 | -0.40 | -0.38 | 233 |
| `B3_PIN_ALLDAY_1D` | dealers long gamma at the heavy $1.0 strike pin spot to it into the close mark | +0.00 | +0.01 | 1382 | -0.04 | -0.09 | 1158 |
| `B4_PIN_FRIDAY_5D` | dealers long gamma at the heavy $5.0 strike pin spot to it into the close mark | -0.80 | -0.41 | 65 | -1.67 | -1.05 | 99 |
| `B5_PIN_MONTHLY_5D` | dealers long gamma at the heavy $5.0 strike pin spot to it into the close mark | -3.29 | -1.01 | 24 | +1.57 | +0.57 | 33 |
| `B6_POSTOPEX_ROLLOFF` | monthly expiry retires the dealer long-gamma book; the clamp on downside is released the next se… | +0.58 | +0.31 | 71 | -4.17 | -1.89 | 52 |
| `B7_OPEXWEEK_REV` | peak dealer long gamma during expiry week clamps and reverses the prior session's move | +0.01 | +0.01 | 354 | -1.18 | -1.21 | 265 |
| `B8_NONOPEX_REV` | peak dealer long gamma during expiry week clamps and reverses the prior session's move | +0.26 | +0.55 | 1156 | +0.24 | +0.46 | 893 |
| `B9_GSIGN_CONTANGO_FADE` | VIX9D/VIX3M is the sign of the dealer gamma book: deep contango = long gamma = intraday moves ge… | -1.12 | -1.93 | 751 | -0.65 | -0.78 | 366 |
| `B10_GSIGN_BACKWARD_RIDE` | VIX9D/VIX3M is the sign of the dealer gamma book: deep contango = long gamma = intraday moves ge… | -1.15 | -1.29 | 317 | +0.56 | +0.62 | 302 |
| `B11_GSIGN_CONTANGO_LASTHR` | VIX9D/VIX3M is the sign of the dealer gamma book: deep contango = long gamma = intraday moves ge… | -1.40 | -2.41 | 753 | -1.98 | -2.38 | 366 |
| `B12_GSIGN_BACKWARD_LASTHR` | VIX9D/VIX3M is the sign of the dealer gamma book: deep contango = long gamma = intraday moves ge… | -1.13 | -1.27 | 318 | +0.35 | +0.39 | 303 |
| `B13_VANNA_SKEWxDVOL` | dealers short a rich put wing carry positive vanna: a vol DROP mechanically raises their delta a… | -0.49 | -1.10 | 1256 | +0.20 | +0.42 | 1157 |
| `B14_CHARM_EXPIRY_DRIFT` | charm: as monthly expiry approaches, the delta of a dealer's short OTM put decays toward zero, f… | +1.42 | +1.10 | 151 | -0.54 | -0.43 | 159 |
| `B15_CONTROL_UNCOND_FADE` | CONTROL -- unconditional intraday fade, contains no options or dealer information whatsoever | -0.49 | -1.20 | 1510 | -0.43 | -0.93 | 1158 |
| `B16_OVERNIGHT_REV_LONGGAMMA` | a long-gamma dealer book has to buy the close down / sell it up, and the flow unwinds against hi… | -0.89 | -1.54 | 756 | -0.56 | -0.67 | 365 |
| `B17_OVERNIGHT_REV_SHORTGAMMA` | a short-gamma book chases the close, so the overnight session should CONTINUE, not revert | -1.48 | -1.66 | 318 | +0.30 | +0.33 | 303 |
| `B18_OPEX_AM_SETTLE_GAP` | SPX AM-settled monthly options print off the opening auction, so the unwind of the hedge against… | +1.26 | +0.67 | 71 | -1.44 | -0.65 | 52 |
| `C1_V1D_RICH_MOMENTUM` | VIX1D rich to VIX = the day's flow is concentrated in 0DTE, where dealers are net SHORT gamma, s… | -0.75 | -0.38 | 65 | +0.74 | +0.40 | 75 |
| `C2_V1D_CHEAP_FADE` | VIX1D cheap to VIX = little 0DTE demand, dealers keep the longer-dated long-gamma book, so intra… | -2.77 | -2.52 | 209 | -1.68 | -1.44 | 186 |
| `C3_V1D_RICH_LASTHOUR` | 0DTE gamma goes hyperbolic in the final hour; a short-gamma dealer's hedge is self-reinforcing r… | -3.06 | -1.56 | 66 | +2.31 | +1.26 | 75 |
| `C4_V1DSLOPE_RICH_MOM` | VIX1D - VIX9D is the pure 0DTE kink in the term structure, cleaner than the VIX1D/VIX ratio whic… | -1.02 | -0.53 | 69 | +0.35 | +0.20 | 80 |
| `C5_V1D_VRP_SIGNFLIP` | a fat 0DTE variance premium means the vol sellers are solvent and supplying gamma (dealers long)… | -0.08 | -0.10 | 411 | +0.41 | +0.51 | 405 |
| `C6_V1D_SPIKE_CONTINUE` | a VIX1D spike is a rush into same-day protection; the dealer selling it is short gamma at the mo… | +3.27 | +1.59 | 60 | -6.62 | -3.12 | 56 |
| `A1_GEX_SIGN_AUTOCORR` | net dealer gamma built from real per-strike SPY option volume across every expiry inside 5 sessi… | -0.42 | -0.53 | 395 | +0.22 | +0.21 | 240 |
| `A1b_GEX_SIGN_LAGSAFE` | A1's mechanism, entered at the next cash open so no position is ever taken on an option bar that… | -0.56 | -0.70 | 395 | +0.68 | +0.66 | 240 |
| `A2_GAMMA_CofM_PIN` | the gamma-weighted centre of mass of the near-dated strike ladder is where a long-gamma dealer b… | +0.81 | +1.01 | 395 | -0.39 | -0.38 | 240 |
| `A3_GAMMA_CofM_INTRADAY` | as A2 but the pull is claimed to act during the cash session when the hedging actually happens, … | -0.16 | -0.20 | 395 | -1.52 | -1.49 | 240 |
| `A4_GAMMA_FLIP_LEVEL` | the strike at which the running net gamma profile crosses zero: above it dealers are long gamma … | +0.95 | +0.33 | 30 | -0.84 | -0.45 | 70 |
| `A4b_GAMMA_FLIP_LAGSAFE` | A4's mechanism entered at the next cash open | -3.89 | -1.34 | 30 | -1.57 | -0.83 | 70 |
| `A5_PUTGAMMA_SURGE` | a day-on-day collapse in the call/put gamma balance is a hedging rush: the dealer taking the oth… | +0.91 | +0.70 | 148 | -0.31 | -0.30 | 240 |
| `A9_RELGAMMA_AUTOCORR` | the call/put gamma balance relative to its own expanding history: an unusually call-heavy book i… | +1.85 | +1.42 | 149 | -0.69 | -0.68 | 240 |
| `A9b_RELGAMMA_LAGSAFE` | the call/put gamma balance relative to its own expanding history: an unusually call-heavy book i… | +1.31 | +1.01 | 149 | -0.46 | -0.44 | 240 |
| `A6_CALL_WALL_RESIST` | the strike carrying the most call gamma above spot is where dealer supply is thickest; spot stal… | +0.00 | +0.00 | 0 | +0.00 | +0.00 | 1 |
| `A7_PUT_WALL_SUPPORT` | the strike carrying the most put gamma below spot is where dealer demand is thickest; spot bounc… | +0.09 | +0.10 | 366 | +0.19 | +0.18 | 237 |
| `A8_BIG_GAMMA_CLAMP` | when the absolute size of the near-dated gamma book is large, hedging volume dominates the tape … | -0.82 | -0.55 | 112 | -0.85 | -0.76 | 199 |

## 3. Verdict — the theme is NOISE. Zero survivors.

- **Largest design |t| of all 35: `C2_V1D_CHEAP_FADE` at -2.52** — *below* the max-of-35 null bar of 2.67, and **in the opposite sign to its own stated mechanism**. Nothing in this theme reached the bar even before the holdout was opened.
- **Largest design Sharpe: `C6_V1D_SPIKE_CONTINUE` at +3.27** (n = 60, t = +1.59). Its holdout is **-6.62**. This is what a Sharpe-ranked miner would have shipped, and it is the single worst number in the table.
- **Only 3 of 35 live formulas are positive in BOTH windows** (`B1_PIN_MONTHLY_1D`, `B8_NONOPEX_REV`, `A7_PUT_WALL_SUPPORT`), and the best of them carries design t = +0.60. That is indistinguishable from three coins landing heads twice.
- **No formula beat the no-information control.** `B15_CONTROL_UNCOND_FADE` contains no options data at all and posts −0.49 / −0.43. Every dealer-conditioned intraday fade lands in the same place, which means the conditioning does nothing.

### 3a. The one pattern that survives both windows is not a dealer effect

`B11_GSIGN_CONTANGO_LASTHR` is the only formula with the same large sign in both windows (design t -2.41, holdout t -2.38). It fades the day's move in the last half hour, so a consistent negative means the last half hour **continues** the day. Two reasons that is not a finding:

1. It is the wrong sign for its mechanism, and the sign was fixed in advance.
2. **Gross, it is only -0.21 / -0.87.** The whole apparent magnitude is the 1.5 bp × 2 legs a day of turnover cost. Flip the sign and the gross edge is ≈ +0.2 Sharpe — under the null bar, and negative net of the same costs.

3. Late-day intraday momentum is already on the dead ledger — B22D/B22E tested Gao-et-al intraday momentum and killed it out of sample. This is a rediscovery of a corpse.

## 4. What this round DID establish (both are new facts, not edges)

**(a) The per-strike dealer-gamma map is computable on free data after all.** `NEWTERR_optimp` recorded GEX as untestable. It is testable from 2024-02-01 forward, at 0–5 DTE, on a ±$15 near-money ladder, from Alpaca's expired option daily bars. The cache is built, idempotent and gitignorable. Any future dealer-positioning claim now has a real instrument instead of a curve-shape proxy. It just does not predict SPY.

**(b) The textbook GEX sign-flip is structurally degenerate on SPY at short tenor.** Gamma-weighted near-money option volume is **put-dominated on 97 % of days** (net-normalised balance negative on 358 of 369 sampled days; deciles run −0.67 to −0.11). Under the standard convention — dealers long the calls, short the puts — SPY 0–5DTE dealers are *always* net short gamma near the money. There is no zero crossing to trade, which is why `A4_GAMMA_FLIP_LEVEL` collapsed to n = 30 and `A6_CALL_WALL_RESIST` to n = 0 (degenerate, excluded from the live count). The regime split has to be made against the measure's own history (`A9`/`A9b`) to exist at all — and then it is noise.

## 5. Honesty ledger

- Formulas built: 36. **One (`A6_CALL_WALL_RESIST`) is degenerate — n = 0 in design — and is reported, not silently dropped.** Live N = 35.
- Signs were fixed from the mechanism before any backtest ran. No sign was flipped after seeing a result; §3a explains what would have happened if one had been.
- Holdout windows were not read until the design column was written to JSON.
- Every Track A close-to-close formula has a lag-safe twin (`A1b`, `A4b`, `A9b`) entered at the next cash open, because the option daily bar for day *t* completes at the 16:15 options close, *after* the 16:00 cash close. The twins are no better.
- Costs are punitive on purpose (1.5 bp/side vs a measured 0.13 bp SPY half-spread). Gross columns are in the JSON: **the gross numbers fail too**, so this is not a friction story.

## 6. What was NOT testable, declared

| wanted | blocked by |
|---|---|
| true open interest (rather than cumulative volume) | no free historical OI anywhere; Alpaca's option snapshot has no `openInterest` field — verified live |
| OI/volume validation against a same-day real-OI chain | Yahoo's option endpoint returned 401 then 429 this session; the check is deferred, not done |
| intraday 0DTE flow footprint (per-minute gamma) | needs option minute bars for ~60 contracts × 640 days; buildable from the same endpoint, not built here |
| pre-2024-02 per-strike gamma | Alpaca's OPRA archive starts there; 2022–23 0DTE boom is invisible to any free per-strike source |
| single-name GEX (NVDA/TSLA/AAPL) | same endpoint, same 2024-02 floor; not run because SPY — the deepest and most dealer-hedged chain in the world — already showed nothing |

