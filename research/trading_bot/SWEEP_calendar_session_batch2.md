# SWEEP: calendar / session / structural-flow effects -- BATCH 2

Generated 2026-08-20. **48 new, structurally distinct formulas**, each scored on a
design window only. This batch is a *second* family on the same theme; batch 1 (52
formulas, `SWEEP_calendar_session.md`) already concluded the theme is noise. Batch 2
was run to attack the structural gaps batch 1 left open, not to re-parameterise it.

## Verdict: THE THEME IS STILL NOISE -- with one candidate that refuses to die cleanly

Across the **pooled family of 100 calendar formulas** (batch 1 + batch 2, same data,
same design windows, same rotated null applied to both in one process), the expected
max |z| under the null is **2.696** (p95 **3.527**). The best design
result anywhere in those 100 is |z| = **3.403** -- batch 1's `REBAL_UNWIND_2D` --
with a **family-wise p of 0.065**. One hundred tries, and the luckiest one is a
6.5% event. That is not an edge; that is the shape of a family this size drawing from noise.

Nothing here is promotable. The most interesting single result is `SESS_OPEXDAY_INTRADAY`
(short SPY open->close on the monthly OPEX session, +0.526 design / +0.416 holdout after
costs). It is the only formula in either batch that survives *every* post-freeze control --
placebo windows, wrong-Friday placebos, and the always-on control that killed batch 1's
leader all come out the other sign -- and it keeps its sign out of sample. But it did not
clear the pre-registered noise bar (pooled |z| 2.93 vs a pooled p95 of 3.53), its held-out
t-stat on its own window is only ~1.8, and a block decomposition run after the freeze shows
it is **intermittent and dormant**: strong 1993-2012, flat 2013-2016, strong 2017-2021,
flat again 2022-2026 (+1.5 bp per OPEX session over the last 4.5 years). I am not
promoting it and I would not spend a forward slot on it in its current form.

## What batch 2 added that batch 1 did not have

| gap in batch 1 | batch 2 coverage |
|---|---|
| overnight/intraday decomposition used in only 3 of 52 formulas | 11 `SESS_*` formulas that ask, for each calendar event, whether it lives in the open gap or inside the session |
| the only cross-section was the survivorship-biased 94-name stock panel | 6 `XE_*` formulas: calendar sorts across a 24-ETF cross-asset panel |
| all exchange holidays pooled into one mask | Thanksgiving, July 4, Christmas week, post-Labor-Day scored separately |
| expiry = the monthly OPEX date only | VIX expiry (Wed 30d before the next 3rd Friday), post-OPEX Monday, pre-OPEX drift, quad-witch sector dispersion |
| crypto flow = sessions, weekend, funding sign | CME-gap continuation, weekend-move reversion at the Asia handoff, funding conditioned on MAGNITUDE with an 8h hold, alt/major session rotation, Deribit weekly-expiry block |

## Windows (unchanged from batch 1; the split was fixed before any result was seen)

| dataset | design | holdout |
|---|---|---|
| etf_daily | 1993-01-29..2016-12-31 (6026 sessions) | 2017-01-01..2026-08-20 (2421 sessions) |
| stock_panel | 2016-01-04..2021-12-31 (1511 sessions) | 2022-01-01..2026-08-14 (1158 sessions) |
| crypto_perp_hourly | 2020-07-01..2023-12-31 (30696 hours) | 2024-01-01..2026-08-17 (23040 hours) |

Costs charged per side on |dw|: ETF **1.0 bp**, single stock **2.5 bp**, Binance USD-M
perp **5.0 bp**. Open->close and gap formulas are charged **two** crossings, since both
the open and the close are traded.

## The multiple-testing bar

- formulas in batch 2: **48**; pooled over the theme: **100**
- analytic sqrt(2 ln N): 2.783 (batch 2 alone), 3.035 (pooled) -- an upper bound, these formulas are correlated
- empirical null, batch 2 alone (800 replicates): E[max|z|] = **2.479**, p90 3.013, p95 **3.306**
- empirical null, pooled 100 (400 replicates, both families rotated together): E[max|z|] = **2.696**, p90 3.223, p95 **3.527**, p99 3.889
- **observed max |z| in batch 2: 3.263** -- below batch 2's own p95 (3.306)
- **observed max |z| pooled: 3.403**, family-wise p = **0.065**

Method: circular rotation of every return array against a FIXED calendar, inside each
instrument's live span, whole family re-scored per replicate. The statistic is
studentised per formula (`z = (S - null_mean) / null_sd`) because deterministic cost
drift survives rotation -- a formula that trades three times a day still pays three
times a day, so raw max|Sharpe| would rank the family by turnover instead of by luck.
`XT_ALT_SESSION_ROT` (design Sharpe -5.06, null mean -4.23) is the object lesson: its
raw Sharpe is the largest number in the table and means nothing at all.

Batch-2 design distribution: median |z| 0.85, p75 1.36, p90 1.93, p95 2.62, max 3.26.
Four of 48 formulas have |z| > 1.96 where 2.4 are expected by chance.

## Full design distribution -- all 48 formulas, ranked by |z|

| z | design Sharpe | null mean | p (2-sided) | dataset | formula | description |
|---:|---:|---:|---:|---|---|---|
| +3.26 | +0.682 | -0.180 | 0.0000 | daily | `XE_MONTHSTART_CONT` | first 2 sessions of the month: the same MTD sort in the CONTINUATION direction (long prior-month winners) |
| -3.11 | -0.695 | -0.042 | 0.0000 | daily | `SESS_OPEXDAY_INTRADAY` | long SPY open->close on the monthly OPEX session only (pin release inside the day) |
| +2.86 | +0.693 | -0.160 | 0.0000 | daily | `TOM_DURATION_EXT` | last 2 sessions of the month: long TLT / short IEF (bond indices extend duration at each month-end reconstitution) |
| +2.18 | +0.592 | -0.011 | 0.0250 | daily | `XE_MONTHEND_REV` | last 2 sessions of the month, across a 24-ETF panel: long the worst month-to-date third, short the best (rebalance flow into the laggards) |
| +1.94 | +0.309 | -0.103 | 0.0537 | daily | `TOM_CREDIT_FLOW` | turn-of-month: long LQD / short IEF (credit index rebalance and coupon reinvestment) |
| +1.92 | +0.591 | +0.039 | 0.0612 | daily | `TOM_EM_MINUS_DM` | turn-of-month: long EEM / short EFA |
| +1.78 | +0.536 | +0.216 | 0.0800 | daily | `VIXEXP_WEEK_SPY` | long SPY through the week of VIX monthly expiry (the Wednesday 30 days before the next third Friday) |
| +1.69 | +0.164 | -0.304 | 0.0887 | daily | `XE_OPEXWEEK_LOWVOL` | OPEX week: long the low-trailing-vol third of the ETF panel, short the high-vol third (dealer gamma suppresses movers) |
| +1.61 | +0.339 | -0.093 | 0.1000 | daily | `TOQ_SPY_MINUS_TLT_UNCOND` | quarter ends only, last 2 sessions: short SPY / long TLT UNCONDITIONALLY (no month-to-date conditioner -- the pure quarter-end rebalance direction) |
| +1.59 | +0.502 | -0.319 | 0.1212 | crypto | `XT_WEEKEND_CONT_US` | Monday 13-21 UTC: take the SAME sign as the Sat+Sun BTC move (CME reopens and the weekend move continues into US hours) |
| +1.49 | +0.411 | +0.111 | 0.1350 | daily | `SESS_TDOM1_GAP` | long SPY over the open gap into the FIRST session of each month only (new-money inflow hits the open) |
| -1.40 | -0.945 | -0.456 | 0.1737 | xs | `XS_FRIDAY_REV` | Fridays only: long the week's losers third, short the winners third (weekly reversal into the weekend) |
| +1.34 | -0.721 | -1.568 | 0.1775 | crypto | `XT_POST_US_CLOSE` | long BTC perp only in the 21-24 UTC block (after the US equity close, before Asia) |
| -1.30 | -0.436 | -0.153 | 0.2125 | daily | `TOM_SECTOR_DEFENSIVE` | turn-of-month: long XLP+XLU / short XLK+XLY (defensive vs cyclical around the flow window) |
| +1.10 | +0.137 | -0.275 | 0.3150 | crypto | `XT_ALT_WEEKEND_SPREAD` | long an ETH/SOL/BNB perp basket Fri-Sun UTC and SHORT it Mon-Thu (weekend alt bid as a self-financing spread) |
| +1.06 | +0.399 | +0.206 | 0.2800 | daily | `OPEX_PRE3_SPY` | long SPY the 3 sessions BEFORE monthly OPEX (drift into the pin) |
| +1.05 | +0.268 | +0.049 | 0.3100 | daily | `THANKSGIVING_SPY` | long SPY the session before and the session after Thanksgiving |
| +1.04 | +0.320 | +0.119 | 0.3088 | daily | `SESS_EOM_GAP` | long SPY over the open gap into the LAST session of each month only |
| +0.99 | +0.255 | -0.288 | 0.3312 | crypto | `XT_DERIBIT_EXPIRY_BLOCK` | long BTC perp in the 08-16 UTC block on Fridays (Deribit options settle 08:00 UTC Friday; gamma is released after) |
| +0.97 | -0.309 | -0.669 | 0.3212 | xs | `XS_OPEXWEEK_MOM` | OPEX week: long the 21-day winners third of the stock panel, short the losers third (pin momentum) |
| +0.92 | +0.323 | +0.128 | 0.3638 | daily | `SESS_OPEXDAY_OVERNIGHT` | long SPY over the gap INTO the OPEX session (overnight positioning ahead of expiry) |
| -0.88 | -5.063 | -4.225 | 0.4450 | crypto | `XT_ALT_SESSION_ROT` | long ETH / short BTC perp in the Asia session (00-08 UTC), reversed in the US session (13-21 UTC) |
| +0.85 | +0.064 | -0.091 | 0.4050 | daily | `SESS_TOM_INTRADAY` | long SPY open->close only on every turn-of-month session (the same window, the other half of the day) |
| +0.85 | -0.896 | -1.356 | 0.4313 | crypto | `XT_SESSION_HANDOFF_EU` | sign of the Asia-session (00-08 UTC) BTC move carried through the EU session (08-13 UTC) -- continuation, not reversal |
| +0.85 | +0.154 | -0.198 | 0.4275 | xs | `XS_TOM_LOWVOL` | turn-of-month: long the LOW-vol third of the stock panel, short the high-vol third (the opposite tilt to batch 1's XS_TOM_HIVOL) |
| -0.82 | -0.999 | -0.521 | 0.3912 | crypto | `XT_WEEKEND_REV_ASIA` | Monday 00-08 UTC: take the OPPOSITE sign of the Sat+Sun BTC move (weekend illiquidity overreaction unwinds when Asia returns) |
| +0.78 | +0.352 | +0.212 | 0.4512 | daily | `SESS_TOM_OVERNIGHT` | long SPY over the OPEN GAP only (prev close->open) on every turn-of-month session -- is the TOM effect an overnight effect? |
| +0.77 | +0.179 | +0.025 | 0.4475 | daily | `SESS_MOC_REVERSAL` | first session of the month, open->close: take the OPPOSITE sign of the last session of the prior month's open->close move (month-end MOC imbalance reversal) |
| -0.74 | +0.045 | +0.234 | 0.4525 | daily | `XE_MON_REV` | Mondays only: long Friday's worst third of the ETF panel, short Friday's best (weekend overreaction reverses) |
| -0.69 | -0.247 | -0.114 | 0.4925 | daily | `POST_LABORDAY_SHORT` | short SPY the 5 sessions after Labor Day (September re-risking weakness) |
| +0.67 | -0.386 | -0.739 | 0.4738 | crypto | `XT_FUNDING_MAG_8H` | hold -sign(last settled funding) for the WHOLE 8h block, but only when |funding| is in the top third of its trailing 90-day distribution (magnitude conditioner, low turnover) |
| -0.59 | -0.031 | +0.087 | 0.5425 | daily | `VIXEXP_DAY_SPY` | long SPY on the VIX expiry session only |
| -0.53 | -0.024 | +0.092 | 0.6188 | daily | `SESS_POSTHOL_GAP` | long SPY over the holiday gap itself (last close before the holiday -> first open after) |
| -0.49 | -0.008 | +0.085 | 0.5875 | daily | `XMAS_WEEK_SPY` | long SPY every session from Dec 24 to year end |
| -0.45 | -0.135 | -0.037 | 0.6625 | daily | `OPEX_SPY_MINUS_IWM` | long SPY / short IWM through OPEX week (index-option gamma is concentrated in large caps) |
| +0.39 | +0.377 | +0.279 | 0.6663 | daily | `TOM_GOLD_2X2` | long GLD the last 2 and first 2 sessions of each month |
| +0.37 | +0.188 | +0.108 | 0.7312 | daily | `SESS_PREHOL_OVERNIGHT` | long SPY over the gap INTO the pre-holiday session (pre-holiday drift, overnight leg) |
| -0.34 | -0.160 | -0.072 | 0.7425 | daily | `PREHOL_SMALLCAP` | long IWM / short SPY on the last session before every exchange holiday (thin-tape small-cap drift) |
| -0.31 | -0.093 | -0.021 | 0.7500 | daily | `QUADWITCH_DISPERSION` | quad-witching session only: long XLK / short XLP (index-level unwind hits high-beta sectors) |
| +0.24 | +0.039 | -0.035 | 0.7875 | daily | `XE_JAN_REV` | January only: long last calendar year's worst third of the ETF panel, short the best (January reversal at the asset-class level) |
| +0.18 | +0.094 | +0.050 | 0.8538 | daily | `TOM_USD` | long UUP over the turn-of-month window (month-end FX fixing dollar demand) |
| +0.16 | -0.013 | -0.044 | 0.8725 | daily | `SESS_PREHOL_INTRADAY` | long SPY open->close on the last session before every exchange holiday (pre-holiday drift, intraday leg) |
| +0.15 | -0.076 | -0.160 | 0.8912 | crypto | `XT_MONTHEND_DERISK` | short BTC perp on the last UTC day of the month, long on the first (the opposite convention to a turn-of-month long) |
| +0.14 | +0.196 | +0.160 | 0.9038 | daily | `XE_TOM_DISPERSION` | turn-of-month: long the high-trailing-vol third of the ETF panel, short the low-vol third (flow hits the beta names) |
| +0.14 | -0.026 | -0.051 | 0.9213 | daily | `HALF_MONTH_SPLIT` | long SPY on trading days 1-10 of the month, SHORT SPY on day 11 to month end (the half-month split as one always-on trade) |
| -0.14 | +0.025 | +0.053 | 0.9012 | daily | `JULY4_SPY` | long SPY the session before and the session after July 4 |
| -0.12 | -0.063 | -0.040 | 0.9225 | daily | `SESS_MON_GAP_VS_DAY` | long SPY over the weekend gap and SHORT SPY Monday open->close (weekend news vs Monday session, as one trade) |
| +0.12 | +0.115 | +0.090 | 0.9012 | daily | `OPEX_MON_AFTER_SPY` | long SPY only on the first Monday after monthly OPEX (dealers re-hedge into the new cycle) |

## Held-out numbers for the design leaders

Printed only after the design sweep was written to disk.

| formula | design Sharpe | HELD-OUT Sharpe | held-out ann ret | held-out vol | held-out maxDD | reading |
|---|---:|---:|---:|---:|---:|---|
| `XE_MONTHSTART_CONT` | +0.682 | **+0.412** | +0.83% | 2.01% | -5.64% | halved; the ungated control earns +0.205 held out, so the calendar gate is worth ~0.21 |
| `SESS_OPEXDAY_INTRADAY` | -0.695 | **-0.569** | -1.77% | 3.11% | -19.88% | sign held; tradable (short) side is +0.526 design / +0.416 holdout after costs |
| `TOM_DURATION_EXT` | +0.693 | **+0.051** | +0.06% | 1.16% | -3.14% | **dead out of sample**; placebo windows are non-monotone |
| `XE_MONTHEND_REV` | +0.592 | **+0.929** | +1.64% | 1.76% | -3.12% | held out better than design, but z=2.18 never cleared the bar and the window sweep shows no structure |
| `TOM_CREDIT_FLOW` | +0.309 | **-0.030** | -0.03% | 0.92% | -3.03% | **dead out of sample** |
| `TOM_EM_MINUS_DM` | +0.591 | **+0.601** | +1.67% | 2.78% | -3.40% | held, but z=1.92 is inside the noise bar and this is EM-vs-DM beta with a calendar mask |

Note on sign: `SESS_OPEXDAY_INTRADAY` is registered long and scores -0.695 design, so
the tradable side is the short. Flipping it does **not** flip the Sharpe symmetrically --
cost is negative in both directions -- so the honest tradable numbers are the ones in the
controls table below (+0.526 design / +0.416 holdout), not 0.695 / 0.569.

## Post-freeze controls

### `SESS_OPEXDAY_INTRADAY` -- short SPY open->close on the monthly OPEX session

Every placebo and the always-on control point the **other way**. This is the profile a
real structural effect is supposed to have, and it is the profile batch 1's leader failed.

| variant | design | holdout |
|---|---:|---:|
| OPEX session (the formula, short) | +0.526 | +0.416 |
| OPEX week, 1 session(s) before | +0.025 | -0.192 |
| OPEX week, 2 session(s) before | -0.172 | +0.259 |
| OPEX week, 3 session(s) before | -0.509 | -0.238 |
| OPEX week, 4 session(s) before | -0.454 | -0.466 |
| 1st Friday of the month instead of the 3rd | -0.331 | -0.494 |
| 2nd Friday of the month instead of the 3rd | -0.271 | -0.317 |
| 4th Friday of the month instead of the 3rd | +0.061 | -0.230 |
| every non-OPEX Friday | -0.227 | -0.602 |
| every session (always on, short) | -0.364 | -0.724 |

Cost sensitivity (bp per side, design / holdout): **1.0bp** +0.526 / +0.416, **2.0bp** +0.441 / +0.338, **3.0bp** +0.355 / +0.261, **5.0bp** +0.180 / +0.104.

What it would be worth if it were live: 12 trades a year, ~+1.5%/yr on 3% vol. Small and low-capacity even in the good regimes.

Why it still is not promotable:

- pooled |z| = 2.93 against a pooled expected-max of 2.696 and p95 of 3.527. In Sharpe units its observed deviation from its own null mean is 0.653 against an expected-max bar of 0.566 and a p95 bar of 0.741. It beats the *average* luckiest-of-100, not the 95th percentile of it.
- it was the 2nd-ranked formula of 48, in a theme where 100 have now been tried.
- the held-out window contains 116 OPEX sessions. At the observed effect size (~15bp per OPEX session against ~90bp daily intraday vol) that is a standalone t of ~1.8. The out-of-sample replication is encouraging, not conclusive.
- and the block decomposition below shows the held-out Sharpe is one 5-year block; the last 4.5 years are flat.


#### Stability and look-ahead audit (`SESS_OPEXDAY_INTRADAY`)

A shift probe first: replacing the OPEX-session intraday return with the neighbouring
session's return destroys the result (design +0.526 -> +0.025 at +1, -0.036 at -1;
holdout +0.416 -> -0.192 and -0.350). The formula uses only a date known months in
advance and the open and close of that one session. There is no look-ahead.

The block decomposition is the problem:

| block | window | OPEX sessions | mean per session | Sharpe |
|---|---|---:|---:|---:|
| 1993-1997 | design | 59 | +11.5 bp | +0.709 |
| 1998-2002 | design | 60 | +15.0 bp | +0.501 |
| 2003-2007 | design | 60 | +17.4 bp | +0.903 |
| 2008-2012 | design | 60 | +13.2 bp | +0.468 |
| 2013-2016 | design | 48 | +1.1 bp | +0.070 |
| 2017-2021 | holdout | 60 | +19.1 bp | +0.694 |
| 2022-2026 | holdout | 56 | +1.5 bp | +0.066 |

Four consecutive design blocks 1993-2012 at +11 to +17 bp, then **flat** 2013-2016,
then +19.1 bp across 2017-2021, then **flat** again 2022-2026. The out-of-sample Sharpe
of +0.416 is entirely the 2017-2021 block; the most recent 4.5 years contribute +0.86%
in total. This is intermittent and currently dormant. It is compatible with a real
regime-dependent expiry effect and equally compatible with an unstable statistic, and
116 held-out observations cannot tell those apart.

### `XE_MONTHSTART_CONT` -- the batch-2 design winner

| variant | design | holdout |
|---|---:|---:|
| tdom 1-2 | +0.682 | +0.412 |
| tdom 3-4 | +0.485 | +0.193 |
| tdom 5-6 | +0.057 | +0.145 |
| tdom 7-8 | -0.009 | -0.800 |
| tdom 9-10 | -0.001 | +0.142 |
| **always on (calendar gate removed)** | +0.277 | +0.205 |

The window decay is monotone and real, but the always-on control tells the same story
batch 1 told: the ungated cross-sectional ETF momentum sort earns +0.205 held out on its
own, the gated version +0.412. The calendar gate contributes ~0.21 Sharpe out of sample,
inside the sampling error of a 9.6-year window. The calendar is a tilt on an asset-momentum
trade, not an effect of its own -- and asset momentum is a different theme.

### `TOM_DURATION_EXT` -- killed by its own placebo sweep

| variant | design | holdout |
|---|---:|---:|
| rtdom 1-2 | +0.693 | +0.051 |
| rtdom 3-4 | -0.269 | -0.092 |
| rtdom 5-6 | +0.313 | +0.025 |
| rtdom 7-8 | -0.010 | +0.142 |
| rtdom 9-10 | +0.506 | -0.488 |
| every session (always on) | +0.263 | -0.132 |

`rtdom 9-10` scores +0.506 on design -- mid-month, where no index-extension story exists.
There is no decay away from the month boundary, and the holdout is +0.051. Noise.

## Data caveats

- `VXX` is in the cache but starts 2018-01, entirely inside the holdout window, so no
  volatility-ETP formula could be designed at all. Any VXX calendar result would have
  been fitted on the holdout; none was run.
- The 24-ETF `XE_*` panel is anchored on GLD's 2004-11 inception, so those formulas see
  a 12.1-year design window rather than the full 23.9. The controls apply the same
  truncation -- without it the always-on control silently scores years in which half the
  panel did not exist, and the comparison is meaningless.
- ETF bars are Yahoo adjusted closes (total-return correct, price levels retroactive).
  No formula filters on a price level. The intraday/overnight split uses raw open and
  close, so a dividend ex-date leaks into the overnight leg; at ETF dividend sizes this
  is a few bp a quarter and does not move any conclusion.
- The single-stock panel is survivorship-biased; all three `XS_*` formulas here are the
  weakest evidence in the table and none survived anyway.
- Binance perp design window (2020-07..2023-12) is one bull-bear cycle. Long-only crypto
  formulas measure beta, which is why the studentised statistic and not raw Sharpe governs.

## Files

- `scripts/trading_bot/cal_sweep2.py` -- batch-2 family + rotated null
- `scripts/trading_bot/cal_pooled_null.py` -- the 100-formula pooled theme bar
- `scripts/trading_bot/cal_holdout2.py` -- held-out scoring, run after the freeze
- `scripts/trading_bot/cal_control2.py` -- placebo / always-on / cost controls
- `research/trading_bot/SWEEP_calendar_session_batch2.json`
- `research/trading_bot/SWEEP_calendar_session_batch2_holdout.json`
- `research/trading_bot/SWEEP_calendar_session_batch2_CONTROLS.json`
- `research/trading_bot/SWEEP_calendar_session_batch2_STABILITY.json`
- `research/trading_bot/SWEEP_calendar_session_POOLED_NULL.json`
