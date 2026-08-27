# SWEEP: calendar / session / structural-flow effects

Generated 2026-08-20. **52 structurally distinct formulas**, each scored on a design window only.

## Verdict: THE THEME IS NOISE

52 formulas. Expected max |z| under the rotated null is **2.454** (p95 **3.268**). The best
design result is **z = +3.39** -- a ~4% event given 52 correlated tries, i.e. precisely what
the luckiest member of a family this size looks like when nothing is there. Expressed as a
Sharpe on that formula's own window the noise bar is **0.61 expected-max / 0.81 at p95**
against a design Sharpe of **0.717**: it does not clearly beat the bar, it sits inside it.

It then **halved out of sample, 0.717 -> 0.412**, and a control below shows the *ungated*
version of the same signal earns +0.355 held out on its own, so the calendar gate is worth
roughly 0.16 Sharpe out of sample -- inside the sampling error of the window.

Nothing in this theme is promotable. Two of the six design leaders flipped sign out of
sample, one is crypto beta, and the two that held are the same trade at two windows and
are not calendar-driven.

## Windows

| dataset | design | holdout |
|---|---|---|
| etf_daily | 1993-01-29..2016-12-31 (6026 sessions) | 2017-01-01..2026-08-20 (2421 sessions) |
| stock_panel | 2016-01-04..2021-12-31 (1511 sessions) | 2022-01-01..2026-08-14 (1158 sessions) |
| crypto_perp_hourly | 2020-07-01..2023-12-31 (30696 hours) | 2024-01-01..2026-08-17 (23040 hours) |

## Costs charged (per side, on |dw|)

- etf: 1.0 bp
- stock: 2.5 bp
- perp: 5.0 bp

## The multiple-testing bar

- formulas tried: **52**
- analytic sqrt(2 ln N) for N independent tries: **2.811** SE units (upper bound -- these formulas are correlated)
- empirical null: 600 replicates, circular rotation of every return array against a fixed calendar (inside each instrument's live span); the whole family re-scored per replicate; statistic studentised per formula to strip deterministic cost drift; max|z| across the family recorded
- **expected max |z| under the null: 2.454** (p90 3.028, p95 3.268)
- **observed max |z| on the design window: 3.385**

`z` is the design Sharpe minus that same formula's own rotated-null mean, over the null sd. Studentising is not cosmetic: a formula that trades three times a day pays a deterministic cost drift that survives rotation, so raw Sharpe would rank the family by turnover rather than by luck.

## Full design distribution (all formulas, ranked by |z|)

| z | design Sharpe | null mean | p (2-sided) | dataset | formula | description |
|---:|---:|---:|---:|---|---|---|
| +3.39 | +0.717 | -0.127 | 0.0017 | daily | `REBAL_UNWIND_2D` | first 2 sessions of the month: the REBAL_FLOW_2D position reversed (flow unwind) |
| -2.46 | -1.058 | -0.063 | 0.0083 | xs | `XS_DEC_TAXLOSS` | December: short the worst YTD tercile / long the best; reversed over the first 5 sessions of January |
| +2.27 | +0.550 | -0.041 | 0.0200 | daily | `REBAL_FLOW_2D` | last 2 sessions of the month: short SPY / long TLT when equities beat bonds month-to-date, reversed when they lagged (pension rebalance direction) |
| +2.06 | +1.330 | +0.490 | 0.0417 | crypto | `XT_WEEKEND_ALTS` | long an equal-weight ETH/SOL/BNB perp basket over Sat+Sun UTC |
| +1.91 | -3.990 | -5.738 | 0.0400 | crypto | `XT_FUNDING_PRE` | hour before each 8h funding settlement: long BTC perp when the PREVIOUS settled funding rate was negative, short when positive |
| -1.65 | -1.134 | -0.527 | 0.0950 | xs | `XS_MONTHEND_DRESS` | last 2 sessions of the month: long the month's winners, short the losers (window dressing) |
| -1.59 | -0.253 | +0.084 | 0.1183 | daily | `OPEX_DAY_ONLY_SPY` | long SPY only on the OPEX session itself |
| +1.50 | +0.825 | +0.131 | 0.1183 | crypto | `XT_TOM_BTC` | long BTC perp on the last UTC day of the month and the first |
| +1.30 | -4.050 | -5.310 | 0.2267 | crypto | `XT_FUNDING_POST` | hour after each 8h funding settlement: the XT_FUNDING_PRE position reversed |
| +1.14 | +0.311 | +0.103 | 0.2433 | daily | `SANTA_SPY` | long SPY the last 5 sessions of December + first 2 of January |
| -1.13 | -0.109 | +0.218 | 0.2567 | daily | `DEC_GLD` | long GLD in December (year-end metals demand) |
| -1.10 | -0.243 | +0.097 | 0.2617 | daily | `TOM_TLT` | long TLT over the turn-of-month window (bond-side flow) |
| +1.07 | +0.445 | +0.246 | 0.2683 | daily | `TOM_ARIEL_SPY` | long SPY on the last session of the month + first 3 of the next |
| +1.07 | +0.357 | +0.156 | 0.3033 | daily | `TOM_TIGHT_SPY` | long SPY only on the last session of the month and the first |
| +1.06 | -1.337 | -2.059 | 0.2950 | crypto | `XT_USOPEN_BTC` | long BTC perp only in the two hours spanning the US equity open (13-15 UTC) |
| -1.04 | -0.077 | +0.131 | 0.3033 | daily | `DOW_MON_BASKET` | long an equal-weight 9-sector-ETF basket only on Mondays |
| +1.00 | +0.331 | +0.164 | 0.3050 | daily | `OPEX_QUAD_WEEK_SPY` | long SPY in OPEX week only in quad-witching months |
| +0.99 | +0.240 | -0.018 | 0.3183 | daily | `REBAL_FLOW_QTR` | REBAL_FLOW_2D restricted to quarter ends, conditioned on quarter-to-date spread |
| -0.97 | -1.050 | -0.624 | 0.3617 | crypto | `XT_ASIA_BTC` | long BTC perp only in the Asia session (00-08 UTC) |
| -0.93 | +0.004 | +0.177 | 0.3367 | daily | `DOW_FRI_SPY` | long SPY close-to-close only on FRI (weekday effect) |
| +0.93 | -0.249 | -0.791 | 0.3567 | crypto | `XT_HANDOFF_MOM` | sign of yesterday's US-session BTC return, held through the next Asia session |
| +0.89 | -0.240 | -0.625 | 0.4017 | crypto | `XT_US_BTC` | long BTC perp only in the US session (13-21 UTC) |
| -0.87 | +0.003 | +0.168 | 0.3783 | daily | `DOW_THU_SPY` | long SPY close-to-close only on THU (weekday effect) |
| +0.87 | +0.133 | -0.108 | 0.3867 | daily | `TOM_EFA_MINUS_SPY` | long EFA / short SPY over the turn-of-month window |
| +0.87 | -0.153 | -0.441 | 0.3750 | xs | `XS_DOW_MON` | Mondays only: long the high-vol tercile, short the low-vol tercile |
| +0.85 | +0.328 | +0.174 | 0.4133 | daily | `DOW_TUE_SPY` | long SPY close-to-close only on TUE (weekday effect) |
| -0.85 | -0.427 | -0.072 | 0.4200 | xs | `XS_TOM_HIVOL` | turn-of-month: long the high-vol tercile of the stock panel, short the low-vol tercile |
| +0.82 | -0.644 | -1.114 | 0.4367 | crypto | `XT_EU_BTC` | long BTC perp only in the EU session (08-13 UTC) |
| +0.80 | +0.582 | +0.463 | 0.4300 | daily | `HALLOWEEN_SPY` | long SPY Nov-Apr, flat May-Oct ('sell in May') |
| +0.75 | +0.284 | +0.143 | 0.4450 | daily | `TOQ_ARIEL_SPY` | turn-of-month SPY window restricted to QUARTER ends only |
| +0.73 | +0.443 | +0.175 | 0.4933 | xs | `XS_TOM_LONGONLY` | long the equal-weight stock panel over the turn-of-month window |
| +0.65 | +0.392 | +0.277 | 0.5333 | daily | `OPEX_WEEK_LONG_SPY` | long SPY every session of monthly OPEX week |
| -0.63 | -0.197 | -0.055 | 0.4883 | daily | `TOM_IWM_MINUS_SPY` | long IWM / short SPY over the turn-of-month window |
| +0.62 | +0.234 | +0.052 | 0.5367 | daily | `YEAREND_TLT` | long TLT the last 3 sessions of December (index-extension buying) |
| +0.61 | +0.258 | +0.090 | 0.5533 | daily | `TOM_SPY_MINUS_TLT` | long SPY / short TLT over the turn-of-month window |
| +0.56 | +0.506 | +0.279 | 0.5767 | crypto | `XT_WEEKEND_BTC` | long BTC perp over Sat+Sun UTC, flat on weekdays |
| +0.53 | +0.089 | -0.016 | 0.6217 | daily | `JAN_IWM_MINUS_SPY` | long IWM / short SPY in January only (small-cap January effect) |
| -0.44 | -0.147 | +0.007 | 0.6183 | xs | `XS_MONTHSTART_UNWIND` | first 2 sessions of the month: the window-dressing position reversed |
| +0.42 | -0.214 | -0.292 | 0.6600 | daily | `OPEX_POST_SHORT_SPY` | short SPY the 3 sessions after monthly OPEX |
| +0.38 | +0.153 | +0.071 | 0.7267 | daily | `PREHOLIDAY_SPY` | long SPY on the last session before every exchange holiday |
| +0.35 | +0.226 | +0.062 | 0.7167 | crypto | `XT_MONDAY_BTC` | long BTC perp on UTC Mondays only |
| -0.25 | +0.127 | +0.173 | 0.8067 | daily | `DOW_MON_SPY` | long SPY close-to-close only on MON (weekday effect) |
| -0.24 | +0.158 | +0.213 | 0.8150 | daily | `DOW_MON_OVERNIGHT` | long SPY over the weekend gap only (Fri close -> Mon open) |
| -0.24 | -0.461 | -0.423 | 0.8083 | daily | `MIDMONTH_SHORT_SPY` | short SPY on trading days 8-15 of each month |
| +0.22 | -0.163 | -0.205 | 0.8450 | daily | `OPEX_WEEK_CONT` | carry the sign of OPEX-week SPY return into the following 3 sessions |
| +0.22 | +0.129 | +0.085 | 0.8350 | daily | `POSTHOLIDAY_SPY` | long SPY on the first session after every exchange holiday |
| +0.13 | +0.263 | +0.236 | 0.8933 | daily | `DOW_FRI_OVERNIGHT` | long SPY overnight into every Friday (Thu close -> Fri open) |
| +0.13 | +0.406 | +0.367 | 0.8983 | daily | `TOM_XSEC_BASKET` | long a 6-ETF cross-asset basket over the turn-of-month window |
| +0.09 | +0.008 | -0.008 | 0.9133 | daily | `OPEX_QQQ_MINUS_SPY` | long QQQ / short SPY through OPEX week (mega-cap gamma pin) |
| -0.05 | -0.089 | -0.081 | 0.9583 | daily | `DOW_MON_INTRADAY` | long SPY Monday open->close only (no weekend gap) |
| -0.04 | +0.170 | +0.177 | 0.9667 | daily | `DOW_WED_SPY` | long SPY close-to-close only on WED (weekday effect) |
| +0.03 | -1.560 | -1.578 | 0.9850 | crypto | `XT_HANDOFF_REV` | minus the sign of the Asia-session BTC return, held through the EU session |

## Held-out results for the design leaders

| formula | design Sharpe | HELD-OUT Sharpe | held-out ann ret | held-out vol | maxDD |
|---|---:|---:|---:|---:|---:|
| `REBAL_UNWIND_2D` | +0.717 | **+0.412** | +1.63% | 3.96% | -12.82% |
| `REBAL_FLOW_2D` | +0.550 | **+0.519** | +1.62% | 3.12% | -6.37% |
| `XS_DEC_TAXLOSS` | -1.058 | **+0.511** | +1.16% | 2.27% | -5.05% |
| `XT_WEEKEND_ALTS` | +1.330 | **+0.430** | +11.41% | 26.52% | -37.09% |
| `XT_TOM_BTC` | +0.825 | **-0.926** | -11.10% | 11.99% | -38.24% |
| `XS_MONTHEND_DRESS` | -1.134 | **-1.314** | -3.62% | 2.75% | -16.82% |

## Controls on the one design leader

`REBAL_UNWIND_2D` is the only formula whose design |z| (3.39) exceeds the p95 of the
family max under the null (3.27). Given 52 correlated tries that is a ~4% event -- it is
what the luckiest member of a family this size looks like when nothing is there. Two
controls, both run only after the design sweep was frozen:

**Placebo window sweep.** The same SPY/TLT cross-asset reversal signal, moved to other
two-session windows counted back from month end (design / holdout Sharpe):

| window | design | holdout |
|---|---:|---:|
| rtdom 1-2 (**the formula**) | +0.550 | +0.519 |
| rtdom 3-4 | +0.666 | +0.441 |
| rtdom 5-6 | -0.121 | +0.121 |
| rtdom 7-8 | -0.305 | +0.047 |
| rtdom 9-10 | -0.221 | -0.407 |
| rtdom 11-12 | +0.012 | -0.257 |

The decay away from the month boundary is real and is the strongest thing in this sweep.

**But the always-on control kills it.** The identical signal held EVERY session with no
calendar gate at all earns design +0.182, **holdout +0.355**. The month-end-gated version
earns holdout +0.519. The calendar gate contributes ~0.16 Sharpe out of sample, well
inside the sampling error of a 9.6-year window. The calendar is not the edge; a weak
cross-asset reversal is, and that is a different theme.

**Cost sensitivity** (bp per side; design / holdout):

| bp/side | REBAL_FLOW_2D | REBAL_UNWIND_2D |
|---|---|---|
| 1.0 | +0.550 / +0.519 | +0.717 / +0.412 |
| 2.0 | +0.487 / +0.436 | +0.668 / +0.352 |
| 3.0 | +0.425 / +0.353 | +0.619 / +0.291 |
| 5.0 | +0.300 / +0.186 | +0.521 / +0.169 |

## Held-out numbers for every design leader

Four of the six leaders flipped sign or halved out of sample:

| formula | design | holdout | reading |
|---|---:|---:|---|
| `REBAL_UNWIND_2D` | +0.717 | +0.412 | halved; not separable from the ungated control |
| `REBAL_FLOW_2D` | +0.550 | +0.519 | held, but never cleared the design noise bar (z=2.27 < 2.45) |
| `XS_DEC_TAXLOSS` | -1.058 | +0.511 | **sign flip** |
| `XT_WEEKEND_ALTS` | +1.330 | +0.430 | crypto beta, not a weekend effect |
| `XT_TOM_BTC` | +0.825 | -0.926 | **sign flip** |
| `XS_MONTHEND_DRESS` | -1.134 | -1.314 | consistently negative, but flipping the sign does not clear costs |

## Data caveats

- The 94-name single-stock panel is names that existed in 2016 **and** still have data in
  2026: survivorship-biased and small/mid-cap tilted. Every `XS_*` row is the weakest
  evidence here; none survived anyway.
- ETF bars are Yahoo adjusted closes. Total-return correct; price levels are retroactive.
  No formula filters on a price level.
- The crypto perp design window (2020-07..2023-12) holds one bull-bear cycle. Long-only
  crypto formulas mostly measure beta, which is why `XT_WEEKEND_ALTS` shows Sharpe 1.33
  raw but only z=+2.06 against its own rotated null.
- Both funding formulas lose ~4 Sharpe on deterministic cost drift alone (they trade three
  times a day at 5bp per side). Their raw Sharpes are the largest in the table and mean
  nothing; this is exactly why the family bar is built on the studentised statistic.
