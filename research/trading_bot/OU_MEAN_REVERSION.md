# OU (Ornstein-Uhlenbeck) MEAN-REVERSION AUDIT of the live RV legs — and a hunt for new tethers

**Date:** 2026-08-21 · **Scope:** research only, no orders, no money, no git commit, cached/free
data only, **the frozen basket is NOT edited** — every parameter change below is a *recommendation*
carrying its out-of-sample number, for the owner to accept into a new freeze or decline.

**The honest lesson this respects (stated up front).** Mean reversion is tradable only when the
mean is **structurally anchored** — a real economic tether pins a spread of *identical* cash-flow
claims — and it is a mirage as a fitted statistic on a raw price series. This audit adds a sharper
edge to that lesson: **a low Hurst exponent and an ADF rejection are necessary but NOT sufficient.**
A spread that is nothing but *bid-ask / non-synchronous measurement error* also has Hurst well below
0.5 and reverts fast — and it is completely untradable, because the "reversion" is the half-spread
you just paid, bouncing. The discriminator that separates a real tether from measurement noise is
the **lag-1 autocorrelation of the spread's daily CHANGE, `ρ1(Δs)`**: a pure measurement-error
spread has `ρ1(Δs) → −0.50` (DEEPMINE_crosslist's finding); a genuine slow convergence sits well
above that. This single number reorganises the whole picture below.

Tools (pure numpy — no scipy/statsmodels/pandas in this env): OU fit by exact AR(1)/MLE
(`θ = −ln φ / Δt`, `μ`, `σ`, `σ_eq = σ/√(2θ)`, `half-life = ln2/θ`); ADF with a constant (MacKinnon
CVs −3.43/−2.86/−2.57); rescaled-range Hurst; Bertram (2010) optimal band by **numerical**
maximisation of expected net return per unit time, using the OU mean-first-passage time from the
scale/speed densities (verified to scale as `1/θ` and to obey the drift). Library + per-leg drivers
+ JSON results in `research/trading_bot/ou_mean_reversion/` (`oulib.py`, `A_l2.py`, `A_l3.py`,
`A_l5.py`, `B_screen.py`, and the matching `*.json`).

---

# PART A — SHARPENING THE EXISTING RV LEGS

## A0. One-paragraph answer

- **L5 (CEF discount)** is the real thing: median discount **half-life 6.75 weeks (~47 d)**, 76% of
  360 CEFs Hurst < 0.5, a genuine slow convergence. Its 4-week hold is well-matched to the clock. It
  uses a decile tilt, not a z-band, so there is no band to optimise — nothing to change.
- **L3 (dual-class)** is real but slow: median ETB half-life **45 d**, 9/11 pairs Hurst < 0.5, ADF
  rejects for 7/11. The crude `|z|≥2.0 / exit 0.5` band is **not badly wrong**, but a **wider exit
  band (≈1.0)** travels better out of sample (held-out book Sharpe 0.50 → **0.66**) and the
  Bertram-optimal band prefers a *higher* entry and *higher* exit. **Recommendation: widen L3's exit
  to `|z|≈1.0`.** No band clears a real significance bar OOS — the leg stays a weak-but-real positive.
- **L2 (ETF-sibling)** is the cautionary one. Its raw 15:45 log-spread is **measurement-error
  dominated** — `ρ1(Δs) = −0.47 … −0.53` on all five pairs, and ADF *fails* to reject a unit root on
  four of five. The crude **`|z|≥1.5` band is net-NEGATIVE out of sample (−0.13 bp/session, t −1.78,
  Sharpe −1.62)** — it fades bounce and pays the spread. Only a **materially higher band (`|z|≥2.0`,
  better `2.5`)** is net-positive OOS. **Recommendation: raise L2's entry band from 1.5 to ≥2.0.**

## A1. Per-leg OU parameters and half-lives

### L2 — ETF-sibling RV · daily 15:45 log-spread · design 2021-01-04 … 2024-12-31

| pair | half-life | θ (/day) | σ_eq (bp) | φ (AR1) | Hurst | ADF t | **ρ1(Δs)** |
|---|---:|---:|---:|---:|---:|---:|---:|
| IVV/SPY | **85.2 d** | 0.008 | 7.5 | 0.992 | 0.312 | +0.03 · FAIL | **−0.472** |
| VOO/SPY | **73.1 d** | 0.009 | 7.5 | 0.991 | 0.343 | −0.38 · FAIL | **−0.482** |
| QQQM/QQQ | 3.69 d | 0.188 | 5.9 | 0.829 | 0.294 | −2.59 · reject@10% | **−0.528** |
| VTWO/IWM | 51.6 d | 0.013 | 18.4 | 0.987 | 0.295 | −0.40 · FAIL | **−0.506** |
| IJH/MDY | **150.8 d** | 0.005 | 27.4 | 0.995 | 0.315 | +0.01 · FAIL | **−0.485** |

**Read this carefully — it is the most important table in Part A.** The daily-sampled 15:45 spread
has half-lives of *weeks to months* and ADF cannot reject a unit root for four of the five pairs, yet
Hurst is 0.29–0.34 (strongly anti-persistent) and `ρ1(Δs) ≈ −0.5` for every pair. That combination is
the exact signature of `spread = (slow, near-unit-root true premium) + (iid measurement error)`. The
low Hurst is the *measurement error* bouncing, **not** a fast economic convergence. **The daily OU
half-life is therefore the WRONG CLOCK for L2**: the leg does not hold for 73 days, it holds 15
minutes (15:45 → 16:00 close), so it is harvesting a *within-session* dislocation, and the daily-OU
reversion it would capture over 15 min is `1 − e^{−θ·(15min)} ≈ 0` — negligible. L2's edge, where it
exists, is the intraday reversion of a transient 15:45 print dislocation back to the close; the daily
z-score only *standardises* the dislocation, and standardising a bounce-dominated series is exactly
what lets a too-low band trade noise (see A2).

### L3 — dual-class voting-premium RV · daily raw log-spread · design 2016-01-04 … 2021-12-31

ETB-guarded frozen pairs (structural-break transitions removed before the AR1 fit):

| pair | half-life | θ (/day) | σ_eq | Hurst | ADF t |
|---|---:|---:|---:|---:|---:|
| Z/ZG | 15.4 d | 0.045 | 1.79% | 0.436 | −5.06 · reject@1% |
| LILA/LILAK | 7.8 d | 0.089 | 1.26% | 0.367 | −4.71 · reject@1% |
| LBRDA/LBRDK | 23.3 d | 0.030 | 1.06% | 0.451 | −4.01 · reject@1% |
| CENTA/CENT | 29.3 d | 0.024 | 2.73% | 0.414 | −3.72 · reject@1% |
| NWSA/NWS | 38.3 d | 0.018 | 2.60% | 0.422 | −3.01 · reject@5% |
| FWONA/FWONK | 55.2 d | 0.013 | 3.37% | 0.473 | −3.18 · reject@5% |
| HEI/HEI.A | 51.7 d | 0.013 | 5.30% | 0.538 | −2.70 · reject@10% |
| PBR/PBR.A | 65.0 d | 0.011 | 7.03% | 0.466 | −2.72 · reject@10% |
| GOOGL/GOOG | 62.8 d | 0.011 | 1.35% | 0.433 | −2.51 · FAIL |
| FOXA/FOX | 66.7 d | 0.010 | 2.41% | 0.470 | −1.79 · FAIL |
| UAA/UA | 2540 d | ~0 | 31.4% | 0.455 | −2.58 · reject@10% |

**Median ETB half-life ≈ 45 d.** 9 of 11 pairs Hurst < 0.5, ADF rejects for 7 of 11 (four at 1%).
This is a genuinely mean-reverting family — the identical cash-flow claim of two share classes is a
real tether. The weak ones (FOXA/FOX; UAA/UA, whose 2540-day half-life and 31% spread sd say it
barely reverts) are the ones to size down. `ρ1(Δs)` is **not** near −0.5 here — the reversion is slow
and real, not bounce.

### L5 — CEF discount convergence · weekly discount level · design < 2024-03-01 (331 CEFs)

| quantity | value |
|---|---|
| discount half-life (weeks) | **median 6.75** (p25 4.0, p75 11.0, mean 8.7) |
| discount half-life (days) | ≈ 47 d |
| Hurst | median 0.441, **76.4% of CEFs < 0.5** |
| ADF | median t −2.44, **31% reject at 5%** |

The discount level mean-reverts (Hurst) with a ~7-week clock, and the frozen leg holds 4 weeks
(overlapping tranches) — it captures roughly half the reversion, a sensible design. ADF is *weaker*
(only a third reject a unit root): CEF discounts are **persistent** — a wide discount can stay wide
for months — which is exactly why the leg is a slow cross-sectional decile tilt on the *level*, not a
fast z-fade, and why its hold is a month. Half-life and Hurst confirm the tether; ADF's weakness is a
property of the instrument, not a defect of the leg.

## A2. OU-optimal entry/exit bands vs the crude fixed band — OUT OF SAMPLE

### L2 — the crude `|z|≥1.5` band loses money out of sample

L2 is a **fixed-horizon fade** (enter 15:45, exit 16:00 no matter what), so Bertram's
hold-until-reversion band does not strictly apply; the OU-relevant question is the **entry
threshold** that best trades off per-fire edge against how often it fires. Realised same-session fade
P&L (`sign(−z)·[(Pc_A/P45_A−1) − (Pc_B/P45_B−1)] − cost`, frozen per-symbol 15:45 half-spreads + SEC),
portfolio = mean over fired pairs, one session = one observation:

| entry `|z|≥K` | DESIGN n / mean bp / t / Sharpe | HELD-OUT n / mean bp / t / **Sharpe** |
|---:|---|---|
| 1.0 | 871 / −0.12 / −1.96 / −1.05 | 388 / −0.43 / −8.21 / −6.61 |
| **1.5 (frozen)** | 675 / +0.16 / +1.91 / +1.17 | 303 / −0.13 / −1.78 / **−1.62** |
| 2.0 | 392 / +0.67 / +4.85 / +3.89 | 164 / +0.09 / +0.74 / **+0.92** |
| 2.5 | 176 / +1.33 / +4.96 / +5.93 | 64 / +0.51 / +2.05 / **+4.06** |
| 3.0 (design-optimal) | 75 / +2.10 / +3.57 / +6.55 | 27 / +0.82 / +1.69 / +5.16 |

**The frozen `|z|≥1.5` band is net-NEGATIVE out of sample (−0.13 bp/session, t −1.78, Sharpe
−1.62).** The reason is A1's `ρ1(Δs) ≈ −0.5`: at a low band you are standardising and fading
*measurement-error bounce*, and the half-spread eats you. Only once the band is high enough that the
dislocation exceeds the bounce (`|z| ≥ 2.0`, cleanly `≥ 2.5`) does the fade become net-positive OOS.
The pattern is monotone and consistent design→held-out, which is what makes it trustworthy rather
than a fit. **Recommendation (not a freeze edit): raise L2's entry band from 1.5 to ≥ 2.0, target
≈ 2.5.** OOS lift at `|z|≥2.5`: Sharpe **−1.62 → +4.06**, mean **−0.13 → +0.51 bp**, t **−1.78 →
+2.05**. Caveat: the higher band fires far less (64 vs 303 held-out sessions) — the leg is even more
capacity-tiny than the freeze assumed — and this P&L uses a faithful-but-simplified 5-min fill (slot
75→77) rather than the exact 15:45-continuous→16:00-auction rail; the *sign and direction* of the
finding are robust, the third decimal is not.

### L3 — Bertram-optimal band and the (entry, exit) grid, out of sample

L3 **is** a hold-until-reversion trade, so Bertram (2010) applies. From the median ETB OU fit
(θ = 0.0158/day, half-life 44 d, σ_eq = 2.51%) and a representative round-trip cost of 16.9 bp
(measured NBBO half-spreads + SEC + borrow), the numerical Bertram optimum that maximises expected
net return per unit time is **enter at `|z| ≈ 3.5`, exit at `|z| ≈ 1.5`** — i.e. a *higher* entry and
a *much higher* exit than the frozen `|z|≥2.0 / exit 0.5` (the objective surface is flat-topped, so
read this as "higher on both", not the exact 3.5/1.5). Held-out reproduction of the frozen dual-class
rule on the ETB-guarded frozen pairs, sweeping the band:

| cell (entry K / exit) | DESIGN n / net bp / t / SR | HELD-OUT n / net bp / t / **book SR** |
|---|---|---|
| **K2.0 / X0.5 (frozen)** | 176 / 77.7 / 4.96 / 2.02 | 150 / 11.5 / 1.08 / **0.50** |
| K1.5 / X1.0 (design-optimal by SR) | 424 / 57.5 / 8.07 / 3.29 | 315 / 8.2 / 1.42 / **0.66** |
| K2.0 / X1.0 | 190 / 74.5 / 5.67 / 2.32 | 159 / 10.8 / 1.13 / 0.53 |
| K3.0 / X0.0 (Bertram-flavoured high entry) | 43 / 145.6 / 3.93 / 1.60 | 33 / 34.8 / 1.62 / **0.76** |
| K3.0 / X1.0 | 45 / 160.6 / 4.31 / 1.76 | 33 / 27.6 / 1.39 / 0.65 |

**Yes, an OU-informed band beats the crude one out of sample — modestly.** Widening the **exit** from
0.5 to 1.0 (the design-Sharpe-optimal `K1.5/X1.0`) lifts held-out book Sharpe **0.50 → 0.66** and t
**1.08 → 1.42**, on *more* trades (315 vs 150) — the cleanest, most capacity-friendly improvement,
and it agrees with Bertram's "exit before full reversion when cost is small relative to σ_eq". The
Bertram high-entry band (`K3.0`) lifts held-out Sharpe to 0.76 and per-trade net to 34.8 bp but on
only 33 trades — better *per trade*, too thin to certify. **Recommendation (not a freeze edit): widen
L3's exit band toward `|z|≈1.0`; entry `|z|` of 1.5–2.0 is fine.** Brutal-honesty rider: **no band
clears a real significance bar out of sample** (best t 1.62 at n 33; design→held-out net shrinks
~7×). This is consistent with the leg's own frozen prior (design t 2.13 → ETB held-out t 1.31) — L3
is a weak-but-real positive, and the band choice moves it inside the noise, it does not rescue it.

### L5 — no band to optimise

L5 is a widest/narrowest-**decile** tilt on the discount *level*, not a `|z|≥K` entry, so the
Bertram optimal-threshold comparison does not map onto it. The A1 half-life (6.75 wk) already says
the 4-week hold is well-chosen; there is no crude band here to sharpen.

## A3. Hurst + ADF confirmation (are we trusting genuine reverters?)

- **L5:** ✅ mean-reverting — 76% Hurst < 0.5, median half-life 6.75 wk. ADF weak (31% reject) because
  discounts are legitimately persistent; the leg is designed around that (slow tilt, monthly hold).
- **L3:** ✅ mostly — 9/11 Hurst < 0.5, ADF rejects 7/11 (4 at 1%). Weakest links **FOXA/FOX** (ADF
  fails, t −1.79) and **UAA/UA** (half-life 2540 d, σ_eq 31% — barely reverts); both should carry
  less weight than the strong revert-ers (Z/ZG, LILA/LILAK, LBRDA, CENTA).
- **L2:** ⚠️ **the confirmation FAILS on the axis that matters.** Hurst < 0.5 for all five, which
  *looks* like confirmation — but ADF cannot reject a unit root on 4/5 and `ρ1(Δs) ≈ −0.5` on all 5.
  The daily 15:45 spread is a slow-drifting true level plus a large measurement-error bounce; the low
  Hurst is the bounce, not a tradable daily convergence. L2 is only viable as a *high-band, 15-minute*
  fade of transient intraday dislocations, never as a daily-spread OU trade — and the crude 1.5 band
  is *inside the bounce*, which is precisely why it dies OOS (A2).

---

# PART B — HUNT FOR NEW STRUCTURALLY-ANCHORED MEAN-REVERTING SPREADS

## B0. The search space is already heavily canvassed — and mostly dead

Every structural tether the brief lists as a candidate has **already been generated, frozen, and
tested** by this programme, and each is dead. Reported here through the OU/measurement-error lens
rather than re-run:

| tether (requested) | prior test | verdict |
|---|---|---|
| **ADR vs home-listing** | `DEEPMINE_crosslist` — 30 pre-registered formulas | **DEAD: 0/30 net-positive design.** Mechanism: `ρ1(Δs) = −0.42 … −0.52` across every country bloc — *the spread is its own measurement error*. The real signals sit inside the shuffled-name placebo band. This is the finding that named the discriminator used throughout this document. |
| **Commodity/crypto ETF vs front future** | `CME_BASIS_PROBE` (BTC/ETH CME basis) | **DEAD: below detectability.** +2.08 pp/yr vs an MDE(80%) of 4.45 pp; certifying it needs 29.7 y of an 8.7-y-old product. A carry/convergence trade, worse than perp funding carry. |
| **Sector-basket vs sector-ETF; ETF vs its components; country-ETF vs stale NAV; overlapping-holdings** | `DEEPMINE_etf_structural_rv` — 51 formulas | **DEAD: 0/51 net-positive.** The signal is *real* (42/51 positive gross, best +2.93 vs a 1.48 bar) and **entirely inside the half-spread**; 45/51 lose at *literally zero* spread on SEC/TAF alone. |
| **Holdco / corporate-structure (known-ratio claims)** | `DEEPMINE_holdco_corpstructure` — 130 formulas | **DEAD: 0/130 clear the bar** (best design t 2.35 vs √(2 ln 130)=3.12). |

So the free-data-tradable structurally-tethered reverters that exist are, essentially, **already the
three legs in the basket** (L2 same-index siblings, L3 dual-class, L5 CEF). That is itself the honest
top-line answer to Part B.

## B1. A fresh freeze-then-test: DAILY-hold OU z-fade on cached ETF-sibling tethers

To add a genuinely new datum rather than only cite prior work, I ran a **different-horizon** object
the sweeps had not: a **daily (multi-day-hold) OU z-fade** on the tightest cached sibling tethers —
L3's machinery applied to liquid ETFs, which the intraday `rv_sweep` never tested at a daily hold.
Design 2021-01-04…2023-12-31, held-out 2024-01-02…2026-08-15; enter `|z|≥2`, exit `|z|≤0.5` or 20 d;
realistic per-symbol ETF half-spreads + SEC + borrow; multiple-testing bar `√(2 ln 9) = 2.10` SE.
Each candidate is stamped with `ρ1(Δs)`, the measurement-error flag.

| pair | tether | half-life | Hurst | ADF t | **ρ1(Δs)** | flag | DESIGN net/t | HELD-OUT net/t |
|---|---|---:|---:|---:|---:|:--:|---|---|
| GLD/IAU | identical (physical gold) | 23 d | 0.309 | −0.71 | **−0.502** | ⚠ meas-err | −0.4 / −0.86 | −1.5 / −1.75 |
| SLV/SIVR | identical (physical silver) | 10 d | 0.281 | −1.55 | **−0.520** | ⚠ meas-err | +0.2 / +0.21 | +0.3 / +0.25 |
| HYG/JNK | broad USD high-yield credit | 125 d | 0.519 | −1.19 | −0.254 | — | −8.4 / −2.32 | −5.6 / −2.06 |
| LQD/VCIT | USD investment-grade credit | 108 d | 0.550 | −1.68 | −0.076 | — | −4.6 / −0.25 | +17.6 / +1.91 |
| TLT/VGLT | long US Treasuries | 207 d | 0.517 | −0.80 | −0.187 | — | −5.7 / −0.84 | +3.4 / +0.71 |
| AGG/BND | total US bond market | 8 d | 0.456 | −4.19 | −0.326 | — | −0.3 / −0.26 | +0.0 / +0.05 |
| EEM/VWO | emerging-market equity | 187 d | 0.476 | −1.97 | −0.091 | — | −8.6 / −0.72 | −73.2 / −1.40 |
| **GDX/GDXJ** | **miners senior vs junior (LOOSE)** | 76 d | 0.523 | −2.61 | −0.061 | — | +85.6 / +1.84 | **+109.8 / +2.50** |
| **GLD/GDX** | **metal vs miners (LOOSE)** | 57 d | 0.546 | −2.22 | −0.028 | — | +151.7 / +1.47 | +196.4 / +1.47 |

**Nothing clears the bar with BOTH a tether AND an OOS-positive number, and the table is a clean
demonstration of why:**

1. **The identical-claim metal siblings (GLD/IAU, SLV/SIVR)** have the prettiest OU stats in the
   table — Hurst 0.28–0.31, half-lives 10–23 d — and are **worthless**: `ρ1(Δs) = −0.50/−0.52` fires
   the measurement-error flag, and their net edge is ≈ 0 (±1.5 bp, |t|<1.8). The low Hurst is bounce.
   This is the discriminator catching a corpse the naïve stats would have promoted — and it is the
   same signature as the live L2 leg's 15:45 spread (A1), confirming the mechanism on independent data.
2. **The credit/duration/EM siblings** are not bounce (`ρ1(Δs)` ≈ −0.1 to −0.3) but they **do not
   cointegrate tightly**: ADF mostly fails, the spreads drift (the ETFs hold *similar*, not
   *identical*, baskets), and net P&L is negative-to-noise. LQD/VCIT's held-out +17.6 bp (t 1.91) is
   *below* the 2.10 bar and was **negative in design** — a coin flip. EEM/VWO's −73 bp held-out shows
   how a "sibling" with a real basket difference blows out.
3. **The only OOS-significant cells are the two LOOSE-tether controls** — GDX/GDXJ (held-out t **2.50**,
   above the bar) and GLD/GDX (+196 bp). **These are exactly the trap the brief warns about and I am
   REJECTING them.** Gold miners are not a claim on gold; there is no mechanism forcing GDX and GDXJ
   (or GLD and GDX) to converge — miners can de-rate versus the metal for years. The huge per-trade
   net (86–196 bp) on ~17 trades with a large σ_eq is a **directional beta bet on the mining
   complex** that a z-fade happened to catch in a trending window, dressed as relative value. Promoting
   it would be the precise error the programme's whole history warns against: a data-mined
   "cointegration" with an OOS number and **no tether**. Verdict: **REJECT.**

## B2. Part B verdict

**No new basket-leg candidate is promoted.** The structurally-anchored reverters that survive free
data and realistic costs are already the three RV legs in the basket; every additional tether tested
— by prior agents (cross-listing, ETF-vs-futures basis, ETF-vs-components, overlapping-holdings,
holdco) and freshly here (metal/credit/duration/EM siblings at a daily hold) — either is
measurement-error bounce (`ρ1(Δs)≈−0.5`), fails to cointegrate (ADF, drift), or is a directional
artifact with no real tether. The one honest *addition* is the **`ρ1(Δs)` measurement-error
discriminator**: it should gate any future RV candidate before its OU half-life or Hurst is even
looked at — and, applied backward, it is the cleanest single explanation for why the live L2 leg's
crude band fails out of sample.

---

# RECOMMENDATIONS (numbers attached; owner decides; frozen basket untouched)

1. **L2 — raise the entry band from `|z|≥1.5` to `|z|≥2.0` (target ≈ 2.5).** The frozen 1.5 is
   net-NEGATIVE out of sample (−0.13 bp/session, t −1.78, Sharpe −1.62); `|z|≥2.5` is +0.51 bp,
   t +2.05, Sharpe +4.06 OOS. Rationale: the raw 15:45 spread is measurement-error dominated
   (`ρ1(Δs)≈−0.5`), so a low band fades bounce and pays the spread. Rider: the higher band is
   capacity-tinier still, and this uses a simplified 5-min fill.
2. **L3 — widen the exit band from `|z|≤0.5` toward `|z|≤1.0`.** Held-out book Sharpe 0.50 → 0.66 on
   more trades (315 vs 150), agreeing with the Bertram optimum (higher exit). Entry `|z|` of 1.5–2.0
   is fine. Rider: no band clears a real significance bar OOS — this sharpens a weak-but-real leg, it
   does not rescue it; size FOXA/FOX and UAA/UA (weak reverters) down.
3. **L5 — leave as is.** OU confirms the tether and the 4-week hold; no band to optimise.
4. **Adopt `ρ1(Δs)` as a pre-registration gate** for any future RV leg: if the spread's daily change
   has `ρ1 < ≈ −0.35`, the "mean reversion" is measurement error and the leg is dead on arrival,
   whatever its Hurst or ADF says.
5. **Do not open a new RV tether on free data.** Part B is exhausted: the tradable structurally-
   anchored reverters are already in the basket; everything else is bounce, non-cointegration, or a
   tether-less directional artifact.

*Research only. No orders, no money, no purchases, no git commit, no edit to the frozen basket. All
numbers are cached-data backtests and every point estimate is a selection-inflated upper bound; the
forward log remains the only arbiter.*
