# INVENT 0822 — VOLATILITY family from free proxies

**Verdict: NOISE. 0 of 38. Honest zero.** The one object in the theme that was genuinely
untested — the volatility-ETP complex as a *mechanically tethered* relative-value family — is
real as a tether and empty as an edge: its entire apparent alpha lives in trading at the very
same close that printed the dislocation, and it is arithmetically equal to the bid-ask spread.

Date 2026-08-22 · design `20111004..20211231` · held-out `20220101..20260820` · all data free
and cached (`research/data/volterm_cache/raw/`, Yahoo adjusted closes), **no network call**,
numpy only. Scripts: `scripts/trading_bot/invent0822_volrv_panel.py`,
`invent0822_volrv_sweep.py`, `invent0822_volrv_stats.py`. Results:
`INVENT_0822_vol.json`, `INVENT_0822_vol_RAW.json`, `INVENT_0822_vol_STATS.json`.

---

## 0. Why this is not a re-run — the four named sub-ideas were already dead

The brief named four candidate angles. Three of them, and most of the fourth, had already been
swept to a NOISE verdict by this programme. I did not re-run them; I re-checked the ledger and
spent the whole budget on the one corner nobody had touched.

| brief's sub-idea | already tested by | N | verdict |
|---|---|---:|---|
| VIX / VIX9D / VIX3M term structure as a timing signal | `INVENT_D0821_volterm` (2026-08-21) | 43 | NOISE — all slope levels, 1d/2d/5d changes, curvature, inversion, twist, 5/21-day holds, event triggers |
| realised-vs-implied on liquid ETFs | `NEWTERR_optimp` family `ownvrp` + `reliv` (2026-08-20) | 28 of 109 | NOISE — per-asset VRP on all 15 underlyings |
| VXX / SVXY roll dynamics, the mechanical ETN roll | `NEWTERR_volatility_etp_term_structure` (2026-08-20) | 39 | NOISE — roll carry, roll-yield timing, ETP decay, long/short vol-ETP pairs as *carry* |
| cross-sectional VRP across sectors | `NEWTERR_optimp` families `crosssec` + `dispersion` | 9 of 109 | NOISE — market-neutral cross-section of implied-vs-realised, implied correlation |

**Cumulative: the volatility family has now been searched 191 ways before today, and 229 ways
including this round.** Any new formula in it faces a bar set by that whole history, not by
its own N.

### The one corner that was untested

Every prior sweep used a volatility instrument **directionally** — vol curve → equity, or vol
ETP → vol carry. Nobody had used the vol complex as a **structurally-anchored spread**, which
is the one survivor class this programme has (ETF-sibling, dual-class, CEF discount). And the
vol-ETP complex has a tether that is not an approximation but an *identity*:

> **VIXY (+1x ETF), VXX (+1x ETN), UVXY (+1.5x ETF), SVXY (−0.5x ETF)** all track the same
> published index (S&P 500 VIX Short-Term Futures TR); **VIXM (+1x ETF)** and **VXZ (+1x ETN)**
> both track the mid-term index. Each is a **daily-reset** product, so its NAV return over one
> full session equals `k × (index return) − fee/day` **exactly and path-independently.**

Therefore for any two wrappers on one index,

```
    e_t  =  r_A,t  −  k · r_B,t   ≡  a constant fee differential      (in NAV terms)
```

and every non-constant part of `e_t` is a **market-price-vs-NAV dislocation of one wrapper
against another** — an ETN creation halt, a premium/discount, a stale close. It carries no
information about volatility. **A-priori sign, fixed before any result was computed: FADE it**
— short whichever wrapper outran its own contractual multiple. This is a tighter tether than
dual-class (no voting premium to drift) and tighter than ETF-sibling (no basket difference).
`k` is read from the prospectus, never fitted, including the announced ProShares change on
**2018-02-28** (UVXY 2x→1.5x, SVXY −1x→−0.5x), whose six transition sessions are guarded out.

The tether is **measured, not assumed**: R² of `k·r_B` explaining `r_A` is **0.992** (UVXY/VIXY),
**0.965** (VXX/VIXY), **0.958** (UVXY/VXX) over the full sample. The identity is real.

---

## 1. The one-line result

| | |
|---|---|
| formulas tested, signs fixed a priori | **38** |
| declared **unevaluable**, excluded from N | 4 (`SVIX`/`UVIX` pairs — both list 2022-03-30, entirely inside the held-out window; no design window exists) |
| analytic bar `√(2 ln 38)` | **t = 2.70** |
| circular-shift bootstrap **E[max Sharpe]** (B=3000) | **1.08** (p95 1.58, p99 1.80) |
| **best design gross Sharpe at the honest lag** | **+0.54** (`X_DISAGREE_RANK`) |
| **its t** | **+1.07** against a 2.70 bar — **0.40× the bar** |
| best design **net** Sharpe | **+0.17** (1 of 38 positive) |
| held-out net Sharpe > 0 | **0 of 38** |
| mean design gross Sharpe, lag0 → lag1 → lag2 | **+1.40 → −0.06 → −0.31** |

Nothing is promoted. Nothing goes to a held-out decision, because the design pass never
produced a candidate.

---

## 2. The lag structure IS the finding

Both prints are 16:00 closes, so computing `e_t` from close *t* and filling *at* close *t* is a
zero-slack lookahead. Convention, matching `NEWTERR_optimp` and the ETP sweep:

* **lag0** — signal from close *t*, MOC fill at that same close. **Reference only.**
* **lag1** — fill MOC at close *t+1*, earns *t+1 → t+2*. **THE HEADLINE.**
* **lag2** — one further day. The kill test.

| | lag0 | **lag1** | lag2 |
|---|---:|---:|---:|
| mean design gross Sharpe over 38 formulas | **+1.40** | **−0.06** | −0.31 |
| median design gross Sharpe | +0.89 | −0.06 | — |
| best single formula | +5.96 | +0.54 | +0.33 |

**100% of the theme's apparent alpha is destroyed by one day of slack.** The residual's
autocorrelation function says why: on the design window `ρ1(e)` runs −0.07 … −0.55, and
**`ρ2` … `ρ5` are all within ±0.09 of zero for every pair.** There is no memory past one day.

### The bounce arithmetic — the decisive number

If the lag0 "profit" is the half-spread bouncing, then *gross profit per unit of turnover
should equal the round-trip half-spread*. It does:

| pair | lag0 gross **bp per unit turnover** | modelled round-trip cost (bp) | ratio |
|---|---:|---:|---:|
| VXX / VIXY | 7.66 | 9.0 | 0.85 |
| VXZ / VIXM | 8.33 | 46.0 | 0.18 |
| UVXY / VIXY | 3.60 | 9.4 | 0.38 |
| SVXY / VIXY | 6.92 | 12.3 | 0.56 |
| UVXY / VXX | 7.41 | 7.0 | 1.06 |
| SVXY / VXX | 5.78 | 11.0 | 0.53 |

The lag0 edge is the *same order as, and in five of six cases below*, the spread it would have
to pay. **You are "earning" the spread you must hand over.** That is the definition of
bid-ask/measurement bounce, and it is untradable by construction.

---

## 3. The ρ1(Δs) gate called this correctly — and then failed as an ex-ante screen

Applying the programme's gate (`ρ1(Δs) > ~−0.35` required, in addition to Hurst<0.5 and ADF),
where `Δs ≡ e_t`:

**Design window `20111004..20211231`:**

| pair | n | sd(e) bp | **ρ1(e)** | Hurst | ADF t | verdict | its lag0 SR |
|---|---:|---:|---:|---:|---:|---|---:|
| VXX / VIXY | 985 | 69.6 | **−0.553** | 0.372 | −4.85 reject@1% | **FAIL — bounce** | +2.91 |
| UVXY / VXX | 985 | 147.7 | **−0.450** | 0.481 | −0.72 FAIL | **FAIL — bounce** | +3.21 |
| UVXY / VIXY | 2572 | 72.4 | **−0.343** | 0.525 | −1.80 FAIL | borderline | +1.11 |
| VXZ / VIXM | 985 | 141.8 | −0.100 | 0.412 | −8.12 reject@1% | pass | +3.29 |
| SVXY / VIXY | 2572 | 172.7 | −0.081 | 0.563 | −0.98 FAIL | pass | +0.50 |
| SVXY / VXX | 985 | 273.4 | −0.073 | 0.543 | −0.26 FAIL | pass | +3.74 |

**The gate is confirmed as a diagnostic.** The two pairs it flags as bounce (`VXX/VIXY`,
`UVXY/VXX`) are exactly the two with the largest lag0 Sharpes and a complete lag1 collapse
(+2.91→+0.21, +3.21→+0.21). The gate would have saved this entire sweep.

**But there is no middle.** The pairs that *pass* the gate pass it by having `ρ1 ≈ −0.08` — i.e.
almost no reversion at all to harvest. 8% of a 173 bp dislocation is 14 bp of expected reversal
against a 12 bp round trip, *and only if you could trade at the same close*. The complex
offers bounce or nothing; it never offers slow convergence.

### And the gate is regime-unstable here — a caveat to hand back

| pair | ρ1 design | ρ1 held-out | verdict flips? |
|---|---:|---:|---|
| VXX / VIXY | −0.553 FAIL | **−0.044** PASS | yes |
| VXZ / VIXM | −0.100 PASS | **−0.525** FAIL | yes |
| SVXY / VIXY | −0.081 PASS | **−0.491** FAIL | yes |
| UVXY / VIXY | −0.343 | −0.412 | no (both bad) |
| UVXY / VXX | −0.450 FAIL | −0.031 PASS | yes |
| SVXY / VXX | −0.073 PASS | −0.032 PASS | no |

**Four of six pairs flip the gate's verdict between windows.** In L2/L3 the gate reads a stable
structural property; in this complex it does not, because the residual's own scale swings an
order of magnitude by year (see §4). **Recommendation to the programme: keep the ρ1 gate as a
kill test, but do not treat a single-window ρ1 as an ex-ante certificate — measure it in both
windows and require both.**

---

## 4. The tether got tighter — the dislocation is decaying out of existence

Residual standard deviation by year, `sd(e)` in bp/day:

| pair | 2011-17 | **2018** | 2019 | 2020 | 2021 | **2022** | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| VXX / VIXY | — | 126 | 18 | 48 | 43 | **202** | 27 | 41 | 39 | 31 |
| UVXY / VIXY | 24–83 | 196 | 25 | 51 | 47 | 33 | 39 | 56 | 45 | 42 |
| SVXY / VIXY | 17–71 | **545** | 17 | 25 | 29 | 14 | 13 | 15 | 15 | 20 |
| VXZ / VIXM | — | 287 | 31 | 38 | 47 | 46 | 32 | **100** | 32 | 32 |

Two things read off this table:

1. **The whole family's variance is two named events.** Feb 2018 (the SVXY NAV collapse and the
   leverage change) and Mar–Aug 2022. Outside them the wrappers track each other to 15–50 bp
   a day. `SVXY/VIXY` now tracks to **15 bp/day** — below a single round trip. There is no
   dislocation left to fade even before significance is considered.
2. **The 2022 spike is a real, identifiable mechanism** — Barclays suspended VXX issuance on
   2022-03-14, so creations could not arbitrage the premium and VXX detached from VIXY. This is
   the single most economically legitimate object in the whole theme.

### And that one legitimate object loses money

`VXX/VIXY` residual fade over the issuance-halt window `20220314..20221031` (n=161):

| lag | gross SR | net SR |
|---:|---:|---:|
| 0 | **−0.62** | −1.11 |
| **1** | **−0.18** | −0.72 |
| 2 | −0.17 | −0.76 |

Negative at every lag. The reason is the CEF lesson restated: **a premium that is wide can go
wider for months.** Fading a *widening* structural premium loses on the way out and only pays
at the collapse, which is one observation. A named, real, mechanically-caused dislocation is
still not a tradable signal.

---

## 5. What was actually tested (the 38)

| group | n | content |
|---|---:|---|
| `P_pairfade` | 12 | one-day replication-residual fade on all 6 evaluable pairs × {linear z-tilt (60d causal z, ±3σ clip), |z|≥2.0 threshold} |
| `L_premlevel` | 10 | the **cumulative** wrapper premium `M_t = Σe`, detrended by its own trailing 20d/60d mean, z-scored over 120d, faded at |z|≥2 with a 5-day hold — on the 5 liquid pairs. This is the ETN-premium object, and it is a *level*, so §2's one-day-bounce argument does not apply to it |
| `X_crosswrap` | 6 | **the original construction**: convert all four SPVXSTR wrappers to their *implied index return* `î = r/k`; the four must agree on one number; fade whichever disagreed. Linear, |z|≥2 threshold, cross-sectional rank, plus accumulated-premium levels at 20/60/120d. Index-neutral by construction (weights sum to zero in implied-index space) |
| `H_horizon` | 6 | the three most liquid pairs' one-day fade held 3 and 5 days — the structural axis that separates a slow premium from a bounce |
| `S_spec` | 4 | **specification controls, counted in N.** `S_BETA`: a 120d fitted regression multiple instead of the contractual `k` (a-priori: the contract is the truth, the fit should not beat it). `S_LOG`: a log-return tether, deliberately the wrong algebra for a daily-reset product — if it scores like the right one, the "tether" is not doing the work |

Not counted in N: static long each B-leg (design Sharpes −0.79, −0.79, −0.21 — the theme is not
a disguised long-vol beta, and could not be, being spread-neutral); and the leakage oracle.

`S_LOG` scores design lag1 gross **−0.35 / −0.51**, worse than every corresponding correct-algebra
formula. `S_BETA` scores **+0.30 / +0.16** vs the contractual **+0.30 / +0.15** — statistically
identical. Read together: the contractual tether is not being out-performed by a fitted one
(good), but neither specification produces an edge, so the exercise is moot.

### Top 8 of 38, design window, all at the headline lag1

| formula | yrs | gross lag0 | **gross lag1** | **t** | net lag1 | held-out gross | held-out net |
|---|---:|---:|---:|---:|---:|---:|---:|
| `X_DISAGREE_RANK` | 3.9 | +2.11 | **+0.54** | **+1.07** | −2.27 | +0.70 | −3.67 |
| `X_DISAGREE_LIN` | 3.9 | +5.96 | +0.40 | +0.80 | −7.56 | +0.68 | −2.98 |
| `H3_UVXY_VIXY` | 10.2 | +0.71 | +0.33 | +1.07 | −1.39 | +0.36 | −4.54 |
| `P_SVXY_VIXY_LIN` | 10.2 | +0.50 | +0.30 | +0.97 | −0.14 | +0.26 | −9.84 |
| `S_BETA_SVXY_VIXY` | 10.2 | +0.49 | +0.30 | +0.96 | −0.11 | +0.29 | −9.68 |
| `P_SVXY_VIXY_TH2` | 10.2 | +0.37 | +0.29 | +0.91 | **+0.17** | +0.65 | −3.51 |
| `H3_SVXY_VIXY` | 10.2 | +0.42 | +0.26 | +0.84 | −0.45 | +0.06 | −7.97 |
| `P_UVXY_VXX_LIN` | 3.9 | +3.21 | +0.21 | +0.42 | −2.35 | +0.12 | −0.97 |

Best t in the theme is **1.07**. The bar is **2.70**. Best Sharpe **0.54** against a bootstrap
E[max] of **1.08** — the best formula does not reach the *average* best-of-38 a search over
shifted signals produces. The single formula with a positive design net (`P_SVXY_VIXY_TH2`,
+0.17) has a held-out net of **−3.51**.

### Costs, and why they are not the story

Half-spreads are anchored to measured median daily $ volume 2024-26 (VXX $218M, UVXY $268M,
SVXY $73M, VIXY $64M, VIXM $2.0M, **VXZ $0.5M**) with the Dyhrberg liquid-taker 2.5 bp as the
floor: VXX/UVXY 3.0, VIXY 5.0, SVXY 6.0, VIXM 15.0, VXZ 30.0 bp per side, +0.5 bp fee, plus
5%/yr borrow on short long-vol legs (2%/yr on SVXY). But per the EXECUTION-COST WALL lesson,
**cost is not what killed this** — the *gross* lag1 numbers are already at zero. Charging zero
basis points changes no verdict. (Separately: `VXZ` at $0.5M/day and `VIXM` at $2.0M/day are
not tradable in any size regardless.)

---

## 6. Harness self-test — all passed before any result was read

| check | result |
|---|---|
| tether identity is real (R² of `k·r_B` on `r_A`) | UVXY/VIXY **0.992**, VXX/VIXY 0.965, UVXY/VXX 0.958 |
| an oracle on tomorrow's residual is visible to the harness | Sharpe **+6.68** |
| the same oracle delayed two days collapses (no leakage) | Sharpe **−0.08** |
| cost is positive and scales with turnover | **+2.20 bp/day** on the 0.42 turnover book |
| gross exposure bounded | max **1.00** |
| ProShares leverage change handled from the prospectus, not fitted | `k` switches 2018-02-28; 6 transition sessions guarded |
| Feb-2018 tail kept, not winsorised | SVXY −86% residual on 2018-02-06 retained |
| no formula live before its inputs exist | VXX/VXZ pairs start 2018-01-26; SVIX/UVIX pairs declared unevaluable |

---

## 7. Dead-ledger additions — do not re-propose

**The volatility-ETP complex as a mechanically-tethered RV family.** The daily-replication
residual `r_A − k·r_B` for VXX/VIXY, VXZ/VIXM, UVXY/VIXY, SVXY/VIXY, UVXY/VXX, SVXY/VXX, faded
as a 60d causal z-score (linear and |z|≥2), held 1/3/5 days; the cumulative wrapper premium
`Σe` detrended at 20d/60d and faded at |z|≥2; the four-wrapper implied-index-return
disagreement cross-section (linear, threshold, rank) and its accumulated-premium levels at
20/60/120d; the fitted-beta and log-return tether specifications. **All dead at the honest lag.**

**Specifically dead as an idea, not just as a number:** *"the ETN creation halt is a free,
mechanical, structurally-anchored dislocation."* It is all three of those things, it is clearly
visible in the data (VXX/VIXY residual sd 202 bp in 2022 vs 18–48 bp in every other year), and
**fading it lost money at every lag over the halt window.** Structural legitimacy is not
sufficient; the premium must also *converge on a clock you can hold through.*

---

## 8. What would change the answer

1. **Intraday quotes for the vol ETPs.** Every number here is close-to-close, and the whole
   theme's alpha sits at lag0 — i.e. inside the last minutes of the session. If the dislocation
   is real intraday and decays before the close, a 15:45→16:00 rail (this programme's L2 shape)
   is the only place it could live. Free data gives no intraday history for VXX/VIXY/UVXY/SVXY.
   Note this would be a *rescue attempt on a signal whose gross alpha is already at zero at the
   only lag we can measure honestly* — the EXECUTION-COST WALL lesson says the prior on that is
   poor.
2. **Real VX futures settlements.** Still the standing data wall from both prior vol sweeps
   (2026-08-20 and 08-21). Not on any free keyless endpoint from this host. It would not help
   *this* family, whose tether never needed the curve.
3. **Nothing else.** Adding formulas to the volatility family only raises a bar that 229
   formulas have already failed.
