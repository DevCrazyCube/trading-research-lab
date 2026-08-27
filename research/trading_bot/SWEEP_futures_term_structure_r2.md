# Sweep round 2: futures/commodities term structure, roll, seasonality, carry-momentum

**Verdict: the theme is noise, confirmed a second time.** 49 structurally new formulas, best *legitimate* design Sharpe **+0.59** against a bootstrap expected-max-under-null of **+0.71**. Nothing clears the bar. Combined with round 1 (`SWEEP_futures_term_structure.md`, 49 formulas, best +0.80 vs bar +0.78), **98 formulas across two independent rounds have now failed to produce a promotable edge in this theme.**

The one formula that "beat the bar" (+4.93, bootstrap p=0.000) is a **disqualified data artifact**, and catching it is the most useful thing this round produced. See "The +4.93 that isn't" below.

## Scope: what makes this round NOT a re-tune of round 1

Round 1 covered ETF maturity ladders, cross-sectional/time-series commodity carry, basis momentum, carry x momentum, seasonality, the VIX curve, the equity-index basis, and rates-curve carry. Every formula here is in a family round 1 never touched:

| group | n | what is structurally new |
|---|---|---|
| **I** FX futures basis | 17 | a term structure that is **directly measured**, not proxied: `log(6E=F / EURUSD=X)` IS the forward premium. No ETF-fee offset, no ladder proxy. |
| **J** energy-complex spreads | 7 | Brent-WTI (BNO/USO) and the gasoline crack (UGA/USO) as real tradeable ETF pairs. |
| **K** carry-quality transforms | 7 | rank by carry *information ratio*, carry *term slope*, sector-neutralised carry, carry persistence — not carry level. |
| **L** regime overlays | 6 | four-sleeve carry composite (commodity + vol + rates + FX) with vol gates, vol targeting, dollar-trend and self-trend gates. |
| **M** roll-window timing | 5 | front-run / fade the index roll window, expiry-week positioning. |
| **N** new fixed-prior seasonals | 7 | grain harvest pressure, gold festival demand, natgas *curve* seasonality, Dec-Jan index reweight. |

## Scoring (identical machinery to round 1, so the two rounds are comparable)

- **Design window:** 20070101..20181231 (~12.0y). **Held out:** 20190101..20261231, walled off behind a separate subcommand.
- **49 formulas**, sign-agnostic (a curve signal has no sign this sweep is entitled to assume) → **98 effective one-sided tries**.
- **Analytic bar:** sqrt(2 ln 2N) = 3.03 in Sharpe-SE units = Sharpe **0.87**.
- **Bootstrap bar (2000 draws):** circularly shift the realised return matrix against the fixed weight matrices. This preserves each formula's turnover and cost line exactly, return autocorrelation, cross-asset correlation, and the correlation *between formulas* — so the max is over 49 correlated tries, not 49 independent ones. Statistic drawn is the one reported: best-of-two-signs, net of costs.
  - **E[max Sharpe] = +0.71**, p95 = +1.01, p99 = +1.16.
- **Costs** per side of turnover, in bp of notional: ETF legs inherited from round 1 (SPY 1, GLD/TLT 1.5, USO 3, UNG/DBC 4, GSG 8, USL/BNO 10, CORN/WEAT/SOYB/UGA 12, UNL/CANE/CPER 15 — ASSUMED spread-scale). New FX futures legs: 6E/6J 1.5, 6B 2.0, 6A/6C 2.5, 6S 3.0 (CME 6E ticks 0.5bp and commission is ~0.2bp of notional, so these are conservative).
- **P&L rule inherited from round 1, non-negotiable:** `X=F` continuous series are the front contract's *spliced price* — the roll yield is deleted from them — so they are **signal inputs only**. Every commodity/equity/rates P&L leg is an ETF adjusted close.

## Full design distribution (all 49, not just the winner)

| min | p25 | median | p75 | max (legit) | max (incl. artifact) |
|---|---|---|---|---|---|
| -0.73 | -0.01 | +0.07 | +0.30 | **+0.59** | +4.93 |

Formulas above the bootstrap E[max] (+0.71): **1** of 49 — and it is the disqualified artifact. Excluding it: **0 of 48**. Above p95 (+1.01): same single artifact.

A null search over this many correlated tries is *expected* to hand back a best of about +0.71. Excluding the artifact it handed back +0.59 — **below** what pure noise would have produced. That is the finding.

---

## The +4.93 that isn't: a stale-quote artifact, caught by mechanism test

`I2_FX_XS_CARRY_D` — rank the 6 currencies by same-day basis carry `log(F/S)/T_IMM`, rebalance daily — scored **design Sharpe +4.93, bootstrap p = 0.000**, on 5.7% vol with a -14% drawdown. It is not a signal.

**The mechanism.** Yahoo's `=X` FX spot bar stamps *earlier* than the CME futures settle. So `log(F_t/S_t)` is not a forward premium — it is a few hours of futures move that the spot series has not printed yet, and which mechanically appears in *tomorrow's* spot bar. The two correlations are the same number:

| currency | corr(basis_t, **futures** ret_t) | corr(basis_t, **spot** ret_t+1) |
|---|---|---|
| EUR | +0.380 | +0.343 |
| JPY | +0.350 | +0.331 |
| GBP | +0.331 | +0.341 |
| AUD | +0.269 | +0.275 |
| CAD | +0.305 | +0.286 |
| CHF | +0.368 | +0.337 |

**The kill test.** Lag the signal by one extra day. A carry signal barely moves (rate differentials are persistent for months); a stale quote dies instantly:

| extra lag | 0d | 1d | 2d | 3d | 5d | 10d | 21d | 63d |
|---|---|---|---|---|---|---|---|---|
| design net SR | **+5.10** | -0.56 | -0.91 | -0.83 | -0.42 | -0.34 | -0.47 | -0.35 |
| design gross SR | **+6.03** | +0.41 | +0.06 | +0.13 | +0.50 | +0.61 | +0.43 | +0.59 |

`I2X_FX_XS_CARRY_D_LAG1` is carried in the sweep as the standing counter-evidence: design **-0.73**, held out **-1.51**.

**The trap worth writing down: it PERSISTS out of sample.** `I2` goes design +4.93 → **held-out +8.28** (t=+3.85, 3.6% vol, -2% max drawdown). A broken data feed is a property of the data, not luck, so it reproduces on every window you test. **Out-of-sample persistence does not validate a signal whose mechanism has been disproven.** Had this round only run design→holdout without the lag test, it would have "found" a Sharpe-8 strategy that is unfillable — the trade is to buy a currency at a price that no longer exists.

**The correction, and what survives it.** The stale gap is zero-mean and unwinds in a day, while the rate differential is persistent — so a 21-day mean of the basis keeps the carry and averages the artifact away. Group `I11..I17` re-runs the whole FX family on the stale-corrected estimator (and the modelled carry accrual uses it too). Result: the entire family collapses to nothing.

| formula | raw-basis version | stale-corrected version |
|---|---|---|
| XS carry, daily | I2 **+4.93** | I11 **-0.02** |
| XS carry, monthly | I1 +0.14 | I12 -0.00 |
| XS carry, z-weights | I3 +0.13 | I13 +0.10 |
| TS carry sign | I4 +0.36 | I14 +0.32 |
| carry / vol63 | I5 +0.14 | I15 -0.01 |
| carry, VIX risk gate | I9 -0.04 | I16 +0.07 |
| carry x momentum | I6 +0.07 | I17 +0.04 |

The measured FX basis is economically *correct* — JPY 2007 +4.35%/yr, AUD 2007 -1.47%, CHF 2024 +3.70%, exactly the right signs and sizes for those rate differentials. It simply has no forecasting power for spot over this window, which includes the 2008 carry crash.

### A second honesty flag on the FX sleeve

A long FX-futures total return is `spot_return + carry/252`, and the carry term is **modelled** from the same basis the signal reads — so a long-high-carry book books that carry by construction. That is genuinely how forwards work (basis at t-1 sets carry earned t→t+1, no lookahead), but it means any FX result here would be the *known* FX carry premium being re-measured, not an edge discovered. Every FX and composite formula is therefore also scored **spot-only**, with the carry leg deleted. The two agree throughout (L3 +0.59 vs +0.53, L1 +0.57 vs +0.54, L4 +0.53 vs +0.52), so the composites are not living on the modelled leg.

---

## Every formula, by group

### I. FX futures basis carry — measured `log(F/S)/T_IMM`
| formula | net SR | sign | gross SR | cost %/yr | vol | maxDD | boot p |
|---|---|---|---|---|---|---|---|
| `I2_FX_XS_CARRY_D` | ~~+4.93~~ | -1 | +5.86 | 5.40 | 5.7% | -14% | **DISQUALIFIED** |
| `I4_FX_TS_CARRY` | +0.36 | -1 | +0.39 | 0.22 | 7.0% | -15% | 1.000 |
| `I7_FX_CARRY_CHANGE` | +0.25 | -1 | +0.31 | 0.36 | 5.7% | -19% | 1.000 |
| `I1_FX_XS_CARRY_M` | +0.14 | -1 | +0.19 | 0.30 | 5.8% | -13% | 1.000 |
| `I5_FX_CARRY_VOLSCALED` | +0.14 | -1 | +0.20 | 0.32 | 5.4% | -11% | 1.000 |
| `I3_FX_XS_CARRY_Z` | +0.13 | -1 | +0.19 | 0.32 | 6.2% | -16% | 1.000 |
| `I6_FX_CARRY_X_MOM` | +0.07 | +1 | +0.10 | 0.17 | 6.2% | -15% | 1.000 |
| `I8_FX_DOLLAR_CARRY` | +0.02 | -1 | +0.05 | 0.20 | 7.4% | -31% | 1.000 |
| `I9_FX_CARRY_RISKGATE` | -0.04 | -1 | +0.09 | 0.53 | 4.0% | -16% | 1.000 |
| `I10_FX_CARRY_SLOPE_GATE` | -0.10 | -1 | +0.23 | 0.54 | 1.6% | -5% | 1.000 |
| `I2X_FX_XS_CARRY_D_LAG1` | -0.73 | -1 | +0.24 | 5.40 | 5.6% | -49% | 1.000 |

- `I1/I2` — rank 6 CME FX futures by basis carry, long top2 / short bottom2, monthly / daily rebalance
- `I3` — continuous cross-sectional z-weights instead of a tercile cut
- `I4` — per-currency time-series: long if own carry z252 > 0
- `I5` — carry rank sized 1/vol63 (risk-parity carry)
- `I6` — z(carry) + z(12-1 spot momentum) ranked jointly
- `I7` — rank by the 63d *change* in basis carry (FX basis momentum)
- `I8` — dollar factor: hold the 6-currency basket by its *average* carry z504
- `I9` — carry flat whenever log(VIX) z252 > +1 (the carry-crash conditioner)
- `I10` — carry sized by cross-sectional carry dispersion z504
- `I2X` — the mechanism test on I2 (signal lagged one extra day)

### I(clean). Stale-corrected FX basis carry — 21d-mean basis, lagged 1d
| formula | net SR | sign | gross SR | cost %/yr | vol | maxDD | boot p |
|---|---|---|---|---|---|---|---|
| `I14_FXCLEAN_TS_CARRY` | +0.32 | +1 | +0.35 | 0.24 | 6.9% | -16% | 1.000 |
| `I13_FXCLEAN_XS_CARRY_Z` | +0.10 | +1 | +0.14 | 0.19 | 5.6% | -14% | 1.000 |
| `I16_FXCLEAN_CARRY_RISKGATE` | +0.07 | +1 | +0.17 | 0.45 | 4.3% | -16% | 1.000 |
| `I17_FXCLEAN_CARRY_X_MOM` | +0.04 | +1 | +0.08 | 0.20 | 5.6% | -21% | 1.000 |
| `I12_FXCLEAN_XS_CARRY_M` | -0.00 | +1 | +0.03 | 0.18 | 5.8% | -16% | 1.000 |
| `I15_FXCLEAN_CARRY_VOLSCALED` | -0.01 | -1 | +0.03 | 0.20 | 5.7% | -16% | 1.000 |
| `I11_FXCLEAN_XS_CARRY_D` | -0.02 | -1 | +0.12 | 0.81 | 5.8% | -17% | 1.000 |

### J. Energy-complex spreads (real ETF legs)
| formula | net SR | sign | gross SR | cost %/yr | vol | maxDD | boot p |
|---|---|---|---|---|---|---|---|
| `J3_BRENT_WTI_CURVE` | +0.19 | +1 | +0.36 | 2.28 | 13.8% | -36% | 1.000 |
| `J6_NG_CRUDE_RATIO` | +0.14 | +1 | +0.17 | 0.93 | 34.0% | -88% | 1.000 |
| `J4_CRACK_REV` | +0.02 | -1 | +0.16 | 2.55 | 17.7% | -40% | 1.000 |
| `J5_CRACK_SEASONAL` | -0.03 | +1 | +0.00 | 0.28 | 8.5% | -35% | 1.000 |
| `J2_BRENT_WTI_MOM` | -0.01 | +1 | +0.23 | 1.27 | 5.4% | -18% | 1.000 |
| `J1_BRENT_WTI_REV` | -0.13 | +1 | +0.06 | 1.81 | 9.5% | -35% | 1.000 |
| `J7_CRACK_X_CURVE` | -0.18 | -1 | +0.04 | 1.91 | 8.9% | -36% | 1.000 |

- `J1/J2` — BNO/USO pair: fade (-z252) vs trend (63d change) the cumulative Brent-WTI spread
- `J3` — BNO/USO signed by which *curve* is more backwardated (63d BZ=F minus CL=F drift, z504)
- `J4` — UGA/USO gasoline crack proxy, -z252 mean reversion
- `J5` — long UGA/short USO Feb-May (refinery turnaround into driving season), flip Sep-Dec
- `J6` — fuel substitution: -z504 of the cumulative log UNG/USO ratio
- `J7` — the crack pair traded only when the WTI curve is backwardated

### K. Carry-quality transforms on the 12-commodity panel
| formula | net SR | sign | gross SR | cost %/yr | vol | maxDD | boot p |
|---|---|---|---|---|---|---|---|
| `K1_CARRY_INFO_RATIO` | +0.21 | -1 | +0.46 | 1.91 | 7.5% | -29% | 1.000 |
| `K3_CARRY_SECTOR_NEUTRAL` | +0.15 | -1 | +0.44 | 1.93 | 6.8% | -18% | 1.000 |
| `K7_CARRY_PERSISTENCE` | +0.05 | -1 | +0.18 | 0.49 | 3.7% | -15% | 1.000 |
| `K2_CARRY_TERM_SLOPE` | -0.00 | -1 | +0.63 | 4.90 | 7.7% | -32% | 1.000 |
| `K6_CARRY_DISPERSION_SIZED` | -0.07 | -1 | +0.11 | 0.59 | 3.3% | -13% | 1.000 |
| `K5_CARRY_LOWVOL_TILT` | -0.31 | +1 | -0.00 | 3.75 | 12.0% | -47% | 1.000 |
| `K4_CARRY_MINUS_MOM` | -0.42 | -1 | +0.05 | 3.12 | 6.7% | -45% | 1.000 |

- `K1` — rank by carry / std(carry): the information ratio of the roll yield, not its level
- `K2` — rank by (63d carry - 252d carry): whether a name's roll yield is improving vs its own year
- `K3` — carry rank demeaned within energy/metals/ags (strips the sector bet)
- `K4` — contrarian: z(carry252) - z(mom 12-1); buy high carry that has not already run
- `K5` — carry rank restricted to the 6 lowest-realised-vol commodities
- `K6` — carry sized by cross-sectional carry dispersion z504
- `K7` — trade only names whose carry sign has been stable all year

`K2_CARRY_TERM_SLOPE` is the round-1 turnover trap firing again in a new costume: gross +0.63, cost 4.90%/yr, net 0.00.

### L. Regime overlays on a four-sleeve carry composite
| formula | net SR | sign | gross SR | cost %/yr | vol | maxDD | spot-only SR | boot p |
|---|---|---|---|---|---|---|---|---|
| `L3_FOURSLEEVE_VOLTARGET` | **+0.59** | +1 | +0.66 | 0.81 | 11.2% | -16% | +0.53 | 0.741 |
| `L1_FOURSLEEVE_CARRY` | **+0.57** | +1 | +0.64 | 0.89 | 12.1% | -18% | +0.54 | 0.811 |
| `L4_SLEEVE_CARRY_WEIGHTED` | +0.53 | +1 | +0.66 | 2.58 | 20.4% | -39% | +0.52 | 0.900 |
| `L2_FOURSLEEVE_VOLGATE` | +0.44 | +1 | +0.54 | 0.96 | 9.8% | -17% | +0.42 | 0.983 |
| `L5_COMMOD_CARRY_DOLLAR_GATE` | -0.14 | -1 | +0.12 | 1.19 | 4.6% | -13% | — | 1.000 |
| `L6_COMMOD_CARRY_TREND_GATE` | -0.17 | -1 | +0.14 | 1.36 | 4.4% | -18% | — | 1.000 |

- `L1` — equal-risk composite of four carry sleeves: commodity curve + vol curve + rates curve + FX basis
- `L2` — L1, flat whenever log(VIX) z252 > +1
- `L3` — L1 scaled to a 10% trailing-realised-vol target (causal, capped 4x)
- `L4` — allocate *across* the four sleeves in proportion to each sleeve's own carry z504
- `L5` — commodity carry on only when the trade-weighted dollar's 126d trend is down
- `L6` — commodity carry on only when the sleeve's own 126d equity-curve trend is positive

Both gates (`L5`, `L6`) *destroy* the sleeve they gate — the conditioner is fitting noise, not regime.

### M. Roll-window / calendar timing
| formula | net SR | sign | gross SR | cost %/yr | vol | maxDD | boot p |
|---|---|---|---|---|---|---|---|
| `M1_PRE_ROLL_LADDER` | +0.50 | +1 | +0.94 | 1.47 | 3.3% | -7% | 0.949 |
| `M4_ROLL_WINDOW_CONDITIONED` | +0.40 | +1 | +0.45 | 0.66 | 12.8% | -25% | 0.995 |
| `M5_MONTHEND_COMMOD` | +0.20 | -1 | +0.30 | 0.96 | 9.6% | -29% | 1.000 |
| `M3_EXPIRY_WEEK_CRUDE` | +0.01 | +1 | +0.06 | 0.72 | 16.6% | -52% | 1.000 |
| `M2_POST_ROLL_FADE` | -0.09 | -1 | +0.26 | 1.47 | 4.1% | -18% | 1.000 |

- `M1/M2` — long USL / short USO on business days 3-7 (front-run the roll) vs 10-14 (after it clears)
- `M3` — hold USO only across the WTI expiry window (bdays 13-17)
- `M4` — trade bdays 5-9 in the direction of the prevailing curve (long USO in backwardation)
- `M5` — turn-of-month in DBC (last 1 + first 3 trading days)

`M1` is the most interesting near-miss in the round: gross +0.94 on 3.3% vol, but 1.47%/yr of cost on USL/USO (10bp and 3bp per side) eats half of it, and +0.50 net is well under the +0.71 bar. It would need a real futures calendar spread rather than the ETF ladder to be worth another look, and that is not free data.

### N. New fixed-prior seasonals
| formula | net SR | sign | gross SR | cost %/yr | vol | maxDD | boot p |
|---|---|---|---|---|---|---|---|
| `N2_GOLD_SEASONAL` | +0.55 | +1 | +0.56 | 0.06 | 18.4% | -28% | 0.859 |
| `N3_NG_CURVE_SEASONAL` | +0.48 | +1 | +0.50 | 0.30 | 24.2% | -49% | 0.964 |
| `N6_JAN_REBALANCE_COMMOD` | +0.47 | +1 | +0.53 | 0.12 | 2.1% | -3% | 0.969 |
| `N5_METALS_SEASONAL_PAIR` | +0.30 | -1 | +0.31 | 0.07 | 7.7% | -23% | 1.000 |
| `N1_GRAIN_HARVEST` | +0.22 | +1 | +0.25 | 0.32 | 12.5% | -21% | 1.000 |
| `N4_XS_CARRY_SEASONAL` | +0.05 | -1 | +0.08 | 0.13 | 4.2% | -15% | 1.000 |

- `N1` — long CORN/WEAT/SOYB Feb-Jun, short Aug-Nov (northern-hemisphere harvest pressure)
- `N2` — long GLD Aug-Feb (festival/Q4 demand), short Mar-Jul
- `N3` — trade UNG by the seasonal sign of the *curve*, not of price: long when UNL/UNG is backwardated during the Nov-Mar draw season
- `N4` — rank commodities by expanding prior-years mean *carry* in the current calendar month (seasonality of the curve, not of the return)
- `N5` — long GLD / short SLV Nov-Feb, flip May-Aug
- `N6` — long DBC / short GSG across the Dec-Jan index reweight window

## Held-out numbers

**No formula earned a held-out look** — none cleared the noise bar on design. The top 3 are shown anyway as further evidence for the noise verdict; nothing was selected on these.

| formula | design SR | HELD-OUT SR | held-out t | ret | vol | maxDD |
|---|---|---|---|---|---|---|
| `L3_FOURSLEEVE_VOLTARGET` | +0.59 | **+0.24** | +0.66 | +2.7% | 11.1% | -22% |
| `L1_FOURSLEEVE_CARRY` | +0.57 | **+0.39** | +1.04 | +4.1% | 10.4% | -15% |
| `N2_GOLD_SEASONAL` | +0.55 | **+0.37** | +0.98 | +6.5% | 17.7% | -43% |
| `I12_FXCLEAN_XS_CARRY_M` (control) | -0.00 | +0.26 | +0.70 | +0.9% | 3.4% | -7% |
| `I2_FX_XS_CARRY_D` (artifact) | +4.93 | +8.28 | +3.85 | +30.2% | 3.6% | -2% |
| `I2X_FX_XS_CARRY_D_LAG1` (its kill test) | -0.73 | **-1.51** | -2.85 | -5.0% | 3.3% | -32% |

All three legitimate candidates decayed toward zero out of sample, with held-out t-stats of 0.7-1.0. The artifact went *up*, for the reason given above.

## Conclusion

Across the FX futures basis (measured, not proxied), energy-complex spreads, carry-quality transforms, four-sleeve carry composites with vol/dollar/trend regime overlays, roll-window timing, and six new fixed-prior seasonals — on free daily data, charged realistic spreads — the best of 49 formulas reached Sharpe **+0.59** against an expected-max-under-null of **+0.71**. The best formula in the round scored *below* what a null search of this size and shape is expected to produce.

**No formula in this theme is promotable.** Round 1 reached the same verdict from 49 different formulas. This is consistent with the standing project finding (`free-data-convexity-wall`): a sizeable, survivable edge is not findable in this theme on free daily data. The remaining unexplored surface — real per-contract calendar spreads rather than ETF ladder proxies, which is what `M1_PRE_ROLL_LADDER` would need to be evaluated properly — requires paid data.

**The transferable methodology result** is the stale-quote artifact: a Sharpe-4.9 design result that *strengthened* to Sharpe-8.3 out of sample and was still false. Design→holdout alone would have promoted it. It was caught only by a mechanism test (lag the signal one day; a real carry signal is indifferent, a stale quote dies). Any future sweep that mixes two data sources with different stamp times needs that test as standard.

Artifacts: `research/trading_bot/SWEEP_futures_term_structure_r2.json` (design + holdout + disqualification, combined), `..._r2_DESIGN.json`, `..._r2_HOLDOUT.json`. Harness: `scripts/trading_bot/ts_sweep2.py` (extends `ts_sweep.py`), data cache: `research/data/ts_cache/` (no re-fetch; round-1 cache reused unchanged).
