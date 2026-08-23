# INVENT-0823 — SINGLE-NAME & SECTOR DEALER-GAMMA / OPTIONS-FLOW

**Date:** 2026-08-23 · research only, no orders, no money, free/cached data only.
**Pre-registration:** `INVENT_0823_gamma_PREREGISTRATION.md` (committed `a86abe1`, before any backtest number existed).
**Frozen design table:** `INVENT_0823_gamma_DESIGN_TABLE.md` (committed `e8dd7a0`, before the held-out window was read).
**Data:** `research/data/inv0823_gex/` (127 MB, regenerable) · **Code:** `scripts/invent0823_gex_{fetch,panel,eval,diag}.py`

---

## 0. THE ONE-PARAGRAPH ANSWER

**One formula out of 24 survives, and it survives everything — but it is not the dealer-gamma
formula the theme set out to find.** `S6_SKEW_TILT` (the gamma-weighted OTM call-vs-put
open-interest tilt, cross-sectionally ranked, held one session from the open of t+1 to the open of
t+2) posts design gross Sharpe 3.83 at t 4.53 with a signal-permutation family-wise p of **0.0010**,
and on the untouched held-out window it is again the **strongest of all 48 cells**: gross 7.90
bp/day, Sharpe 3.58, t 3.64, break-even 16.1 bp/side against a 3.0 bp rail, **held-out net Sharpe
+2.92**. It is not a bounce artefact (one-day-gap re-entry keeps SR +3.35), not reversal (spanning
regression alpha t +3.61 with REV1/REV5 loadings), not beta (0.036), not one name (worst
leave-one-out SR 3.09 of 3.58), and not a portfolio-construction artefact (every tail cut from 10%
to 50% is positive in both windows). **But the Black–Scholes apparatus is decoration:** a crude
call-minus-put *volume* imbalance with no greeks, no moneyness split and no gamma weighting does
*better* (held-out SR 4.32). So the honest claim is **an options order-flow imbalance predictor in
liquid single names**, not a dealer-gamma effect — and the *sector-ETF half of the theme is dead*
(held-out Sharpe 0.55). The theme is **not noise**, which makes it the first non-noise theme in six
consecutive sweeps, with the caveats in §6 attached.

---

## 1. The R3 ledger entry was too broad, and correcting it is the theme's foundation

Round 3 recorded: *"The textbook GEX sign-flip is structurally degenerate on SPY at short tenor …
gamma-weighted near-money option volume is put-dominated on 97% of days."* True for SPY. **Not true
of the single-name/sector cross-section**, which is an options fact of a completely different shape:

| pool | fraction of name-days with net dealer gamma > 0 |
|---|---|
| SPY, 0–5 DTE (round 3) | 0.03 |
| this universe, pooled | 0.783 |
| IWM / XLRE (broad + rate-sensitive ETFs) | 0.15 / 0.17 |
| XLU / XLP / XLB (defensives) | 0.46 / 0.50 / 0.52 |
| MSFT / NVDA / META / AMZN | 0.95 / 0.96 / 0.97 / 0.99 |

**32 of 49 names flip sign between 10% and 90% of the time.** Index options are the market's hedging
instrument and are structurally put-heavy; single names are the market's speculation instrument and
are structurally call-heavy; and the *degree* varies enormously by name. The cross-sectional
dispersion in dealer-gamma sign that SPY does not have **does exist here**. The R3 entry should be
narrowed to "on index options at short tenor", not "on options".

---

## 2. Method

| item | choice |
|---|---|
| Option data | Alpaca expired-OPRA **daily bars**, every monthly (3rd-Friday) expiry 2024-02 … 2026-08 |
| OI proxy | cumulative traded volume per strike over `[E−70d, E]`, through the close of day *t*, front **and** next monthly |
| Greeks | Black–Scholes at a flat per-(name, expiry, day) ATM IV solved from the nearest-to-money call and put closes |
| Universe | 34 liquid single names + 15 sector/broad ETFs, all top-decile ADV — **no illiquid tail exists in this universe by construction** |
| Windows | design 2024-02-01…2025-06-30 (352 days) / held-out 2025-07-01…2026-08-21 (260 days), untouched until the design table was committed |
| Rail | signal from the close of *t*, **entry at the open of t+1** (≥17.5 h gap, never a shared print), exit close of t+1 (`intraday`) or open of t+2 (`day`) |
| Cost | 1.0 / **3.0** / 5.5 bp per side (`EXECUTION_COST_WALL.md` §1); turnover measured, not assumed |
| Grid | 24 formulas × 2 horizons = 48 cells |

**Two data bugs were found and fixed before any result was computed**, both the same failure mode —
a strike grid whose step is not a divisor of the listed step silently drops most of the ladder. Pass
1 used $5 for every $200+ name and fetched only $5 strikes; pass 2 used $1 and fetched only the
multiples of $5 out of a $2.50 ladder. The shipped fetcher uses a **half-step fine grid over ±5%
unioned with a 5× coarse grid over ±20%**, which is a divisor of the $1, $2.50 and $5 ladders alike.

### Nulls (design window, 2000 draws, ADV-slot signal permutation)

Signal values are shuffled **within ADV-decile slots each day**, so the placebo book has the same
cross-sectional size, liquidity and gross-leverage profile as the real book; only the name→signal
assignment is destroyed. Rotate-the-returns is known-broken and was not used. One permutation per
(draw, day) is shared by all formulas, so the null keeps the real cross-formula correlation rather
than assuming independence.

| null statistic | mean | p95 | p99 |
|---|---|---|---|
| max \|t\| over the 48-cell grid | 2.55 | **3.471** | **3.967** |
| max \|Sharpe\| over all 48 cells | 2.65 | 4.031 | 5.043 |
| max \|Sharpe\|, dense cells only (n ≥ 250) | — | 3.127 | **3.569** |
| analytic multiple-testing bar, \|t\|, 48 tests | — | **3.272** | — |

The all-cell Sharpe null (4.03) is inflated by the four n=77 OpEx cells, whose Sharpe is far noisier
at the same information content; **\|t\| is the n-adjusted statistic and is the binding bar.**

---

## 3. Result

### Design (frozen before the held-out read) — 48 cells

One cell clears every bar. `S6_SKEW_TILT|day`: t **4.53**, permutation FWER p **0.0010**
(2 of 2000 draws), Sharpe 3.83 vs the dense max-\|Sharpe\| p99 of 3.569.
`G4_DGEX1|day` (t 3.32) is the only other cell above the analytic bar and it is **killed by the
one-day-gap placebo**, collapsing +3.08 → −0.23. Everything else has \|t\| < 2.9. Full table in
`INVENT_0823_gamma_DESIGN_TABLE.md`.

### Held-out (untouched until the design table was committed)

| cell | n | gross bp/day | SR | t | turnover | break-even | net @1 / 3 / 5.5 bp | gap placebo |
|---|---|---|---|---|---|---|---|---|
| **S6_SKEW_TILT \| day** | 260 | **+7.90** | **3.58** | **3.64** | 0.49 | **16.1 bp** | **+3.36 / +2.92 / +2.36** | **+3.35** |
| S6_SKEW_TILT \| intraday | 261 | +4.81 | 2.95 | 3.00 | 2.00 | 2.4 bp | +1.72 / −0.73 / −3.80 | +2.80 |
| S4_PUT_SURGE \| intraday | 261 | −5.91 | −3.01 | −3.06 | 2.00 | −3.0 bp | fails on cost | −2.14 |
| C2_VANNA \| day | 260 | +6.88 | 2.56 | 2.60 | 0.80 | 8.6 bp | +2.27 / +1.67 / +0.93 | **+0.35** |

**The frozen pick is again the strongest cell in the grid on a window it had never seen.** Its
intraday twin is the same signal at a horizon whose 2.0 turnover eats the whole edge — it is not an
independent confirmation and is not counted as one.

### The survivor, stated precisely

```
S6 = ( Σ_{K>S} γ_K·callOI_K  −  Σ_{K<S} γ_K·putOI_K ) / Σ_all γ_K·OI_K
```

cross-sectionally rank-normalised across the 49 names, dollar-neutral, long the top / short the
bottom, entered at the open of t+1 and exited at the open of t+2. Turnover 0.49 of gross per day.

---

## 4. Every gate it had to pass

| test | design | held-out |
|---|---|---|
| gross Sharpe / t | 3.83 / 4.53 | 3.58 / 3.64 |
| permutation FWER p | 0.0010 | — (frozen sign) |
| **one-day-gap re-entry placebo** | +3.25 | **+3.35** |
| beta to equal-weight universe | +0.146 | **+0.036** |
| beta-hedged Sharpe | 3.68 | 3.42 |
| xs rank corr with r₁ / r₅ / r₂₀ | −0.052 / −0.049 / −0.020 | −0.06 / −0.06 / −0.02 |
| residualised on r₁, r₅, r₂₀ each day | 3.78 (t 4.33) | **4.03 (t 4.10)** |
| residualised on MA20-dist and MA60-dist | 3.96 | 3.44 |
| residualised on `P1_PIN_DIST` | 4.18 | 3.76 |
| **spanning-regression alpha vs IV-book, RV-book, REV1, REV5, market** | **+7.45 bp/day, t +4.40** | **+7.84 bp/day, t +3.61** |
| orthogonal (residual) Sharpe from that regression | 3.88 | 3.65 |
| worst leave-one-name-out Sharpe (49 deletions) | — | **3.09** (full 3.58) |
| equal-weight tails 10 / 20 / 33 / 50 % | 3.40 / 3.94 / 3.36 / 2.93 | 4.79 / 2.75 / 3.16 / 2.58 |
| positive-day rate | 0.614 | 0.596 |
| worst peak-to-trough of cumulative gross P&L | 362 bp (≈30 avg days) | 606 bp (≈50 avg days) |

**On reversal.** A plain reversal book on this same universe and window is worth almost nothing:
REV1 SR 0.86, REV5 0.42, REV20 0.43 in design; the S6 book's P&L correlation with REV5 is +0.27,
and the spanning regression prices that loading out and still leaves 96% of the raw Sharpe.

**One genuine wrinkle, stated in full.** *Cross-sectionally* orthogonalising the S6 **signal** on
implied vol and 20-day realised vol cuts the held-out Sharpe 3.58 → 0.95. That is a different
operation from hedging the vol **books**, and it is the wrong question: S6 is legitimately correlated
with vol (+0.25 to +0.29) because high-vol names genuinely carry more OTM call OI, so stripping the
vol ordering out of the signal throws away most of its variance rather than isolating an exposure.
The exposure question is answered by the spanning regression above — the IV-book and RV-book
loadings are **statistically zero in the held-out window** (t +1.08 and −1.39) and the alpha is
+7.84 bp/day at t +3.61. Both numbers are reported because a reader who ran only the first one would
reach the opposite conclusion.

---

## 5. The mechanism is NOT dealer gamma, and that matters

| variant | design SR / net@3 | held-out SR / net@3 |
|---|---|---|
| `S6` as specified (γ-weighted, OTM-split, /gross) | 3.83 / 3.20 | 3.58 / 2.92 |
| same without the `/gross` normaliser | 2.35 / 1.95 | 2.23 / 1.85 |
| **crude (callVol − putVol)/(callVol + putVol) — no greeks, no moneyness split, no gamma at all** | **3.68 / 3.55** | **4.32 / 4.15** |

The entire Black–Scholes apparatus — the IV solve, the gamma weighting, the OTM/ITM split — **adds
nothing**. A raw put/call volume imbalance does as well in design and better out of sample. Two
consequences:

1. **What is real is an options order-flow imbalance predictor, not a dealer-gamma effect.** Do not
   describe this as a GEX strategy. The gamma machinery survives only as the route by which the
   signal was found.
2. **The crude variant is post-hoc and has no clean held-out window** — it was constructed after
   both windows had been read. Its numbers are reported as a *mechanism diagnostic*, not as a
   second survivor. Round 4 should pre-register it and test it forward.

Two supporting mechanism facts, both **against** the textbook story:

* \|net gamma\| vs the **next** session's realised range: rank correlation **+0.094** (design) /
  **+0.035** (held-out) — weakly *positive*. Long dealer gamma does not dampen next-day range here.
  The pinning premise is not supported.
* All four pin cells, all four flip cells, all four charm/vanna cells and `C3_OPEX_ROLLOFF` are
  noise. The gamma-flip level as support/resistance (`F1`, `F2`, `F4`) is dead: best design t 1.81,
  and `F1|day` has a **negative** gap placebo.

---

## 6. What is dead, and the caveats on what is not

**Dead, do not re-test:** gamma-flip level as support/resistance (F1–F4); max-gamma-strike pinning
in all four forms including the OpEx-week and expiry-session windows (P1–P4); charm drift, vanna,
post-OpEx gamma roll-off and pre-OpEx front-month gamma (C1–C4); GEX level, z-score, 1- and 5-day
change and the gamma×reversal interaction (G1–G6, with `G4_DGEX1|day` specifically killed by the gap
placebo after clearing the analytic bar — a clean demonstration that the placebo earns its place);
OTM call-volume surge (S5). **The sector/broad-ETF half of the theme is dead**: the survivor's
sector-only book is Sharpe 0.55 held-out (net −0.01), against 3.61 for single names only.

**Caveats on the survivor, all load-bearing:**

1. **Two and a half years of data, total.** Free expired OPRA begins 2024-02-01. The held-out window
   is 260 sessions. No amount of care makes this a long track record, and a signal this strong on
   this little history deserves the corresponding discount.
2. **Monthly expiries only.** Weeklies and 0DTE — now the majority of single-name option volume —
   are entirely absent from the OI proxy. What the signal measures is the monthly-expiry flow.
3. **Volume is not open interest.** There is no free OI history; cumulative volume over 70 days
   counts closing trades as opening and misses older accumulation.
4. **The named mechanism is wrong** (§5). The formula works; the story attached to it does not.
5. `S1_CPRATIO` and `G6_GEXFRAC` in the frozen list are monotone transforms of one ratio and are the
   identical book under rank weighting — the pre-registration's claim of 24 distinct formulas was
   wrong; there are 23. The nulls were run on all 48 cells, so the bar is if anything conservative.

**Recommendation to the basket owner:** this is a *candidate for forward paper logging*, not a
sized leg. It is the first non-noise theme result in six sweeps, its held-out net Sharpe is +2.92 at
a 6× break-even margin over the real rail, and it is structurally uncorrelated with all four sized
legs (T3 overnight reversal, DUALCLASS, T12 CEF discount, ORB) — none of which reads an option
feed. Against that: 260 held-out sessions, a mechanism that turned out to be mis-named, and the
programme's own prior that selection-inflated estimates are upper bounds. The correct next step is a
pre-registered forward log plus a clean out-of-sample test of the crude volume-imbalance variant,
not capital.
