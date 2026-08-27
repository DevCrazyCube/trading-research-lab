# Sweep: futures/commodities term structure, roll, seasonality, carry-momentum
**Verdict: the theme is noise.** 49 structurally different formulas, best design Sharpe **+0.80** against a bootstrap expected-max-under-null of **+0.78**. The winner does not clear the bar it has to clear (bootstrap p = 0.308); nothing in the sweep does.
## How this was scored
- **Design window:** 20070101..20181231 (~12y). **Held out:** 20190101..20261231 (NOT evaluated by this command)
- **Formulas tested:** 49. The search is sign-agnostic (a curve signal has no sign this sweep is entitled to assume), so it is **98 effective one-sided tries**.
- **Analytic bar:** sqrt(2 ln 2N) = 3.03 in Sharpe-SE units = Sharpe **0.87**.
- **Bootstrap bar (2000 draws):** circularly shift the realised return matrix against the fixed weight matrices. This preserves each formula's turnover and cost line exactly, the return autocorrelation, the cross-asset correlation, and the correlation *between formulas* -- so the max is over 49 correlated tries, not 49 independent ones. Statistic drawn is identical to the one reported: best-of-two-signs, net of costs.
  - E[max Sharpe] = **0.78**, p95 = 1.51, p99 = 1.66
- **Costs charged** per side of turnover, in bp of notional: SPY 1, GLD/TLT 1.5, SLV/IEF/SHY/IAU 2, USO 3, UNG/DBC/PDBC 4, GSG/DBA/SVXY/VIXY 8, USL/BNO/PPLT 10, CORN/WEAT/SOYB/UGA/DJP/DBB/DBE 12, UNL/CANE/CPER 15. Provenance is ASSUMED (spread-scale for these ETFs), not measured -- so gross Sharpe and the annual cost drag are reported per formula and you can re-charge any row yourself.

## The data fact that shaped the whole design
Yahoo's `X=F` continuous series is the **front contract's price, spliced** -- each contract drifts down toward spot inside its life and the splice gaps back up at every roll, so the roll yield is silently deleted. Measured over 2007-01-03..2018-12-31: the CL=F price series fell **~25%** while USO -- an actual front-month WTI position -- fell **80.4%**. That 55pp gap *is* the contango drag. Any backtest that takes P&L from `=F` returns books it as profit.
So `=F` series are used **only as signal inputs** (they are a fine spot proxy) and every P&L leg is an ETF adjusted-close return, which is real, holdable, and roll-and-fee-inclusive.
The carry estimator is `carry_i(t) = 252 * mean_k[ logret(ETF_i) - logret(FUT_i) ]`, consumed only as a z-score against its own history or a cross-sectional rank -- both invariant to the constant per-name offset (expense ratio, collateral yield). Sanity check on the levels, which come out economically right: crude -10.1%/yr, natgas -29.1%/yr, wheat -10.7%/yr (all deep contango over the window), gold -0.4%/yr (GLD is spot-backed, so this is just its fee).

## Full design distribution (every formula, not just the winner)
| min | p25 | median | p75 | max |
|---|---|---|---|---|
| -0.69 | -0.03 | +0.14 | +0.28 | +0.80 |

Formulas above the bootstrap E[max] (+0.78): **1** of 49. Above bootstrap p95 (+1.51): **0**.

A null search over this many correlated tries is *expected* to hand back a best of about +0.78. It handed back +0.80. That is the finding.

## Every formula, by group

### A. Maturity-ladder term structure (ETF pair spreads: USL/USO, UNL/UNG, DBC/GSG, GC=F/GLD)
| formula | net SR | sign | gross SR | cost %/yr | ann ret | vol | maxDD | boot p |
|---|---|---|---|---|---|---|---|---|
| `A5_OPTROLL_STATIC` | **+0.41** | +1 | +0.41 | 0.00 | +2.0% | 4.8% | -8% | 1.000 |
| `A1_LADDER_CRUDE` | **+0.39** | +1 | +0.41 | 0.37 | +5.9% | 15.1% | -30% | 1.000 |
| `A1_LADDER_BROAD` | **+0.31** | +1 | +0.41 | 1.24 | +3.9% | 12.4% | -37% | 1.000 |
| `A1_LADDER_NATGAS` | **+0.27** | +1 | +0.29 | 0.43 | +5.6% | 20.6% | -40% | 1.000 |
| `A4_GOLD_BASIS` | **+0.26** | -1 | +0.43 | 1.44 | +2.2% | 8.4% | -27% | 1.000 |
| `A6_LADDER_SPREAD_NATGAS` | **+0.08** | +1 | +0.28 | 1.58 | +0.6% | 7.7% | -29% | 1.000 |
| `A2_LADDER_CHANGE_CRUDE` | **-0.03** | +1 | +0.00 | 1.01 | -0.9% | 33.0% | -75% | 1.000 |
| `A3_LADDER_SPREAD_CRUDE` | **-0.06** | -1 | +0.28 | 1.20 | -0.2% | 3.5% | -13% | 1.000 |

- `A5_OPTROLL_STATIC` -- static long DBC / short GSG (optimised roll minus front roll, always on)
- `A1_LADDER_CRUDE` -- -z504(252*mean63(log USL/USO)); long USO when backwardated
- `A1_LADDER_BROAD` -- -z504(252*mean63(log DBC/GSG)); long GSG when backwardated
- `A1_LADDER_NATGAS` -- -z504(252*mean63(log UNL/UNG)); long UNG when backwardated
- `A4_GOLD_BASIS` -- z504 of 63d (GC=F - GLD) drift; long GLD when gold basis rich
- `A6_LADDER_SPREAD_NATGAS` -- long UNL / short UNG when natgas contango z>0, flip when backwardated
- `A2_LADDER_CHANGE_CRUDE` -- -sign(63d change in USL/USO contango); long USO when contango is FALLING
- `A3_LADDER_SPREAD_CRUDE` -- long USL / short USO when contango z>0 (harvest the ladder), flip otherwise

### B. Cross-sectional carry over a 12-commodity panel
| formula | net SR | sign | gross SR | cost %/yr | ann ret | vol | maxDD | boot p |
|---|---|---|---|---|---|---|---|---|
| `B5_XS_CARRY_ZWEIGHT` | **+0.28** | -1 | +0.60 | 3.94 | +3.6% | 12.5% | -25% | 1.000 |
| `B2_XS_CARRY_252` | **+0.28** | -1 | +0.54 | 2.03 | +2.3% | 8.0% | -22% | 1.000 |
| `B8_BASIS_MOMENTUM_252` | **+0.28** | -1 | +0.53 | 1.99 | +2.2% | 7.9% | -22% | 1.000 |
| `B11_XS_CARRY_LIQUID_MONTHLY` | **+0.14** | +1 | +0.17 | 0.33 | +2.1% | 14.9% | -40% | 1.000 |
| `B10_XS_CARRY_MONTHLY` | **+0.10** | +1 | +0.16 | 0.43 | +0.8% | 7.8% | -21% | 1.000 |
| `B7_XS_CARRY_CHANGE` | **+0.02** | -1 | +0.73 | 5.53 | +0.2% | 7.8% | -26% | 1.000 |
| `B1_XS_CARRY_63` | **-0.11** | -1 | +0.42 | 4.29 | -0.9% | 8.1% | -38% | 1.000 |
| `B6_TS_CARRY_SIGN` | **-0.19** | +1 | +0.17 | 4.87 | -2.6% | 13.7% | -56% | 1.000 |
| `B3_XS_CARRY_21` | **-0.20** | -1 | +0.78 | 7.86 | -1.6% | 8.1% | -37% | 1.000 |
| `B9_XS_CARRY_SKIP21` | **-0.39** | -1 | +0.16 | 4.22 | -3.0% | 7.7% | -40% | 1.000 |
| `B4_XS_CARRY_VOLSCALED` | **-0.42** | -1 | +0.34 | 5.18 | -2.8% | 6.8% | -39% | 1.000 |

- `B5_XS_CARRY_ZWEIGHT` -- 63d carry, continuous cross-sectional z-score weights (no tercile cut)
- `B2_XS_CARRY_252` -- same rank but carry measured over 252d
- `B8_BASIS_MOMENTUM_252` -- rank by (12m ETF return - 12m futures price return) = cumulative realised roll
- `B11_XS_CARRY_LIQUID_MONTHLY` -- carry rank restricted to the 6 cheapest-to-trade ETFs, monthly rebalance
- `B10_XS_CARRY_MONTHLY` -- 63d carry rank, weights REBALANCED ONLY ONCE A MONTH (turnover control)
- `B7_XS_CARRY_CHANGE` -- rank by 63d CHANGE in carry (basis momentum), long rising-carry names
- `B1_XS_CARRY_63` -- rank 12 commodities by 63d realised roll yield; long top 4 / short bottom 4 ETFs
- `B6_TS_CARRY_SIGN` -- per-name TIME-SERIES: long if own carry z504>0, short if <0, equal gross
- `B3_XS_CARRY_21` -- same rank but carry measured over 21d (fast)
- `B9_XS_CARRY_SKIP21` -- carry over [t-84,t-21] only -- skips the last month to kill ETF/futures price overlap
- `B4_XS_CARRY_VOLSCALED` -- 63d carry rank, position sized 1/vol63

### C. Momentum and carry x momentum combinations
| formula | net SR | sign | gross SR | cost %/yr | ann ret | vol | maxDD | boot p |
|---|---|---|---|---|---|---|---|---|
| `C6_TS_MOM` | **+0.20** | +1 | +0.27 | 0.97 | +3.3% | 16.0% | -41% | 1.000 |
| `C1_XS_MOM_12_1` | **-0.08** | +1 | +0.09 | 1.51 | -0.7% | 8.7% | -19% | 1.000 |
| `C2_XS_REVERSAL_1M` | **-0.25** | +1 | +0.25 | 4.45 | -2.2% | 9.0% | -31% | 1.000 |
| `C3_CARRY_PLUS_MOM` | **-0.34** | -1 | +0.14 | 3.69 | -2.6% | 7.8% | -37% | 1.000 |
| `C5_MOM_SIGNED_BY_CARRY` | **-0.41** | -1 | +0.47 | 5.66 | -2.6% | 6.4% | -39% | 1.000 |
| `C4_CARRY_MOM_AGREE` | **-0.69** | +1 | +0.06 | 5.54 | -5.1% | 7.3% | -49% | 1.000 |

- `C6_TS_MOM` -- per-name time-series 12-1 momentum sign (trend following, no cross-section)
- `C1_XS_MOM_12_1` -- classic cross-sectional 12-1 momentum on the commodity ETFs
- `C2_XS_REVERSAL_1M` -- short past-1m winners / long past-1m losers
- `C3_CARRY_PLUS_MOM` -- rank by z(carry63)+z(mom12-1), long top 4 / short bottom 4
- `C5_MOM_SIGNED_BY_CARRY` -- score = sign(carry) * |mom12-1| (carry picks the side, momentum the size)
- `C4_CARRY_MOM_AGREE` -- trade only names where carry and momentum AGREE in sign

### D. Seasonality (expanding-window and fixed-prior)
| formula | net SR | sign | gross SR | cost %/yr | ann ret | vol | maxDD | boot p |
|---|---|---|---|---|---|---|---|---|
| `D8_CRUDE_DRIVING_SEASON` | **+0.80** | +1 | +0.80 | 0.12 | +27.4% | 34.3% | -66% | 0.308 |
| `D6_TURN_OF_MONTH_EQ` | **+0.16** | +1 | +0.18 | 0.24 | +1.4% | 8.7% | -29% | 1.000 |
| `D3_TS_SEASONALITY` | **+0.09** | +1 | +0.12 | 0.42 | +1.0% | 11.3% | -34% | 1.000 |
| `D2_XS_SEASONALITY_T` | **+0.06** | -1 | +0.14 | 0.27 | +0.2% | 3.8% | -8% | 1.000 |
| `D1_XS_SEASONALITY_MEAN` | **+0.05** | -1 | +0.11 | 0.25 | +0.2% | 3.9% | -9% | 1.000 |
| `D7_TS_SEASONALITY_DBC` | **+0.03** | -1 | +0.05 | 0.25 | +0.3% | 12.5% | -46% | 1.000 |
| `D4_NG_INVENTORY_CYCLE` | **+0.01** | +1 | +0.01 | 0.16 | +0.2% | 41.7% | -79% | 1.000 |
| `D5_GOLDMAN_ROLL_WINDOW` | **-0.32** | +1 | +0.33 | 1.44 | -0.7% | 2.2% | -14% | 1.000 |

- `D8_CRUDE_DRIVING_SEASON` -- long USO Feb-Jun (refinery/driving build), short Jul-Jan; fixed prior
- `D6_TURN_OF_MONTH_EQ` -- long SPY on the last trading day + first 3 of each month, flat otherwise
- `D3_TS_SEASONALITY` -- per-name: long if prior-years mean for this month > 0, else short
- `D2_XS_SEASONALITY_T` -- same but ranked by the prior-years t-statistic, not the mean
- `D1_XS_SEASONALITY_MEAN` -- rank by expanding prior-years mean return in the CURRENT calendar month
- `D7_TS_SEASONALITY_DBC` -- long/short the broad basket DBC by its own expanding month-of-year mean
- `D4_NG_INVENTORY_CYCLE` -- long UNG Feb-Aug (injection season), short Sep-Jan; fixed prior, nothing fitted
- `D5_GOLDMAN_ROLL_WINDOW` -- long DBC / short GSG only on business days 5-9 (the index roll window), flat else

### E. Volatility term structure (VIX curve)
| formula | net SR | sign | gross SR | cost %/yr | ann ret | vol | maxDD | boot p |
|---|---|---|---|---|---|---|---|---|
| `E2_VIX_CONTANGO_SHORTVOL` | **+0.56** | +1 | +0.59 | 1.33 | +26.7% | 47.7% | -53% | 0.838 |
| `E6_VIX_CURVE_SUM` | **+0.55** | +1 | +0.57 | 0.94 | +26.1% | 47.8% | -67% | 0.868 |
| `E7_VIX_CONTANGO_MONTHLY` | **+0.46** | +1 | +0.46 | 0.14 | +22.0% | 47.8% | -81% | 1.000 |
| `E5_VIX_FAR_SLOPE` | **+0.44** | +1 | +0.45 | 0.14 | +8.4% | 19.2% | -27% | 1.000 |
| `E1_VIX_CONTANGO_SPY` | **+0.23** | +1 | +0.24 | 0.36 | +4.5% | 19.7% | -48% | 1.000 |
| `E3_VIX_CONTANGO_Z` | **+0.17** | -1 | +0.21 | 0.41 | +2.2% | 12.8% | -34% | 1.000 |
| `E4_VIX9D_SLOPE` | **+0.03** | -1 | +0.07 | 0.53 | +0.3% | 11.8% | -35% | 1.000 |

- `E2_VIX_CONTANGO_SHORTVOL` -- same vol-curve sign but expressed in SVXY (harvest the vol roll directly)
- `E6_VIX_CURVE_SUM` -- whole-curve slope (1M/3M + 3M/6M) into SVXY
- `E7_VIX_CONTANGO_MONTHLY` -- vol-curve sign into SVXY but only re-read once a month
- `E5_VIX_FAR_SLOPE` -- far end only: -sign(log VIX3M/VIX6M) into SPY
- `E1_VIX_CONTANGO_SPY` -- long SPY when log(VIX/VIX3M)<0 (vol curve in contango), short when >0
- `E3_VIX_CONTANGO_Z` -- continuous: -z252(log VIX/VIX3M) sized into SPY
- `E4_VIX9D_SLOPE` -- front of the vol curve: -sign(log VIX9D/VIX) into SPY

### F. Equity-index futures basis
| formula | net SR | sign | gross SR | cost %/yr | ann ret | vol | maxDD | boot p |
|---|---|---|---|---|---|---|---|---|
| `F2_ES_BASIS_CHANGE` | **+0.12** | -1 | +0.18 | 1.25 | +2.3% | 19.8% | -74% | 1.000 |
| `F1_ES_BASIS_Z` | **-0.02** | -1 | +0.05 | 0.76 | -0.2% | 11.9% | -60% | 1.000 |

- `F2_ES_BASIS_CHANGE` -- sign of the 21d change in the ES basis (carry momentum) into SPY
- `F1_ES_BASIS_Z` -- z252 of the ES=F / S&P cash basis; long SPY when the basis is rich

### G. Rates curve carry / rolldown
| formula | net SR | sign | gross SR | cost %/yr | ann ret | vol | maxDD | boot p |
|---|---|---|---|---|---|---|---|---|
| `G3_CURVE_SIGN_TLT` | **+0.48** | +1 | +0.48 | 0.00 | +7.0% | 14.4% | -27% | 1.000 |
| `G4_RATES_CARRY_X_MOM` | **+0.32** | +1 | +0.34 | 0.20 | +3.1% | 9.9% | -16% | 1.000 |
| `G1_CURVE_CARRY_TLT` | **+0.26** | +1 | +0.29 | 0.23 | +2.5% | 9.7% | -26% | 1.000 |
| `G2_ROLLDOWN_IEF` | **+0.23** | +1 | +0.30 | 0.31 | +1.0% | 4.3% | -14% | 1.000 |
| `G5_STEEPENER_SPREAD` | **+0.17** | -1 | +0.22 | 0.26 | +0.8% | 4.6% | -14% | 1.000 |

- `G3_CURVE_SIGN_TLT` -- raw sign of (30y - 5y) slope into TLT (level, not z-score)
- `G4_RATES_CARRY_X_MOM` -- TLT only when curve carry and 12-1 price momentum agree, else flat
- `G1_CURVE_CARRY_TLT` -- long TLT when (10y - 3m) z252 is high (positive carry+rolldown), short when inverted
- `G2_ROLLDOWN_IEF` -- long IEF on (10y - 5y) rolldown slope z252
- `G5_STEEPENER_SPREAD` -- SHY vs TLT duration spread scaled by the 10y-3m slope z-score

### H. Multi-asset carry composites
| formula | net SR | sign | gross SR | cost %/yr | ann ret | vol | maxDD | boot p |
|---|---|---|---|---|---|---|---|---|
| `H1_MULTI_ASSET_CARRY` | **+0.62** | +1 | +0.67 | 1.33 | +17.9% | 28.8% | -40% | 0.690 |
| `H2_XSCARRY_PLUS_VOLCARRY` | **+0.39** | +1 | +0.51 | 2.81 | +9.5% | 24.2% | -42% | 1.000 |

- `H1_MULTI_ASSET_CARRY` -- one gross-1 book: commodity ladder carry + vol-curve carry + rates curve carry
- `H2_XSCARRY_PLUS_VOLCARRY` -- half commodity cross-sectional carry, half vol-curve carry

## What the sweep caught in itself
Two methodology traps fired during this run and both would have manufactured an 'edge'.

**1. Ranking a sign-agnostic search by |t| of the net series promotes turnover, not signal.** The first cut crowned `B3_XS_CARRY_21` at t = -3.80. Its *gross* Sharpe was only -0.78; the rest was a 7.9%/yr cost line on an 8.1%-vol book. Costs do not flip when the signal does, so -W does not earn +1.74 -- it earns +0.78 gross minus the same 7.9%/yr, i.e. nothing. Scoring now takes `max(SR_net(+W), SR_net(-W))` and the null draws the identical statistic.

**2. A short-window ETF-minus-futures 'carry' is mostly stale-price reversion.** The ETF and its futures print at different times and the ETF carries a mean-reverting premium/discount, so a 21-day carry estimate is partly a recent *price* move. The tell was that the family got monotonically stronger as the estimation window got *shorter* (21d > 63d > 252d) -- the opposite of what a real roll-yield signal does. `B9_XS_CARRY_SKIP21` measures carry over [t-84, t-21] instead, skipping the last month: gross Sharpe collapses from +0.78 to +0.16. It was price overlap wearing a carry costume.

## Held-out numbers
No formula earned a held-out look -- none cleared the noise bar on design. The top 3 are shown anyway as further evidence for the noise verdict; nothing was selected on these.

| formula | design SR | HELD-OUT SR | held-out ret | held-out vol | maxDD | yrs |
|---|---|---|---|---|---|---|
| `E2_VIX_CONTANGO_SHORTVOL` | +0.56 | **+0.58** | +21.5% | 37.1% | -44% | 7.62 |
| `H1_MULTI_ASSET_CARRY` | +0.62 | **+0.60** | +14.4% | 24.1% | -33% | 7.62 |
| `D8_CRUDE_DRIVING_SEASON` | +0.80 | **+0.13** | +5.6% | 42.1% | -87% | 7.62 |

The design winner behaved exactly as a noise winner behaves: `D8_CRUDE_DRIVING_SEASON` went **+0.80 -> +0.13** with an -87% held-out drawdown.

Two composites (`H1_MULTI_ASSET_CARRY`, `E2_VIX_CONTANGO_SHORTVOL`) held their level across both windows (~+0.6 on each). That is worth writing down, but it is **not** an edge claim: +0.6 sits below the +0.78 bar this search has to clear, their held-out t-stats are ~1.5, and both run 24-37% vol with 33-44% drawdowns. They are consistent with a real but small risk premium (short vol, term-structure carry) that this sweep has no power to separate from luck -- and that a levered book would not survive.

## Conclusion
Across maturity-ladder term structure, cross-sectional and time-series carry, basis momentum, carry x momentum, expanding-window and fixed-prior seasonality, the VIX curve, the equity-index futures basis, and rates curve carry -- on free daily data, charged realistic ETF spreads -- the best of 49 formulas reached Sharpe +0.80 against an expected-max-under-null of +0.78.

**No formula in this theme is promotable.** The design winner is indistinguishable from the best draw of a null search of the same size and shape.

Artifacts: `research/trading_bot/SWEEP_futures_term_structure.json` (design + holdout, combined), `..._DESIGN.json`, `..._HOLDOUT.json`. Harness: `scripts/trading_bot/ts_sweep.py`, data cache: `scripts/trading_bot/ts_fetch.py` -> `research/data/ts_cache/`.
