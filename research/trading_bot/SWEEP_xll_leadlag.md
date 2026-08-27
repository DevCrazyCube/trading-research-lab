# SWEEP — cross-asset & cross-venue lead-lag

**Verdict: the theme is noise.** 74 structurally different lead-lag formulas were built and
scored on a design window. Every formula whose signal is a *pure* cross-asset transmission —
one asset's past return predicting another's future return, with no term for the predicted
asset's own past return — sits at or below its noise bar, in both crypto and equities. The
formulas that post spectacular design numbers all share one component, the laggard's OWN
lagged return, and that component is the 5-minute bid-ask bounce, not a lead-lag: it decays
from Sharpe 20 at 5m to 0.1 at 1h, and it loses 100-400 Sharpe points to fees.

One formula out of 74 clearly cleared its bar: `P2_ovn_gap_reversal`, design gross 2.12
against a bar of 0.84, held-out gross 1.43. The focused pass below kills it as an answer to
*this* theme and very nearly kills it outright:

- **The cross-asset term does no work.** Delete the SPY-beta neutralisation entirely and the
  held-out number goes UP (1.43 -> 1.54). P2 is a single-name overnight-gap reversal that
  happened to be wearing a lead-lag hat; it is not evidence for cross-asset transmission.
- **It breaks even at 5.6 bp per side on the held-out window.** The sweep charged 5. That is
  not a margin, it is a rounding error, and the trade is a market-on-open entry across ~2,900
  names where the auction spread is the widest of the day.
- **On names liquid enough to justify a 5 bp fill it is gone.** Top half by dollar volume:
  held-out gross 0.83, breakeven 3.0 bp. Top quintile: 0.13, breakeven 0.5 bp. The effect
  lives exactly where the cost assumption stops being defensible.

Nothing here should be promoted to a forward test.

## Method, and what makes the noise bar honest

- Every formula scored on a **design window only**. The held-out window was computed by the
  same harness but never used to choose anything; it is reported for the survivors as the
  real test, and for everything else only so the full table is visible.
- The noise bar is **empirical, not `sqrt(2 ln N)`**. Each null draw time-shifts the return
  matrix (by at least a day, both signs) and re-scores *every* formula against the shifted
  returns using the *same* shift. That destroys any lead-lag relation while preserving each
  formula's turnover and autocorrelation, and — crucially — preserving how correlated the
  formulas are with each other. Max-over-formulas of that is the expected max under the null.
  The naive `sqrt(2 ln N) x SD` is printed alongside; it assumes independent tries and is the
  wrong bar for a family this correlated.
- **Lookahead audit, automated.** Every context is rebuilt with everything past 65% of the
  sample replaced by reversed, rescaled prices; a formula whose weights on the surviving
  prefix change at all is reading the future. This caught a real bug (`N1_liqtier_lead` was
  using the leader basket's *same-day* return and scored 2.83; corrected it scores 0.43).
  Final state: 31/31 equity formulas and 32/32 crypto formulas at two frequencies, CLEAN.
- Costs are charged per side on `sum|w_t - w_{t-1}|`, and the provenance of each number is
  stated rather than assumed.

## Block: `crypto_perp_5m_leadlag`

- panel: `/home/anont/meme/research/data/xll_cache/perp5m_panel.npz`
- design: 2023-01-01 .. 2025-06-30   |   held out: 2025-07-01 .. 2026-08-17
- formulas: **32**
- cost: **6.0 bp per side** — BROKER_SCHEDULE (Binance USD-M VIP0 taker 5bp) + STRESS_LADDER (1bp slippage). NOT a measurement of our own fills.

**Full design gross-Sharpe distribution (every formula, nothing dropped):**

| n | min | p10 | p25 | median | p75 | p90 | max | mean | sd |
|---|---|---|---|---|---|---|---|---|---|
| 32 | -20.25 | -1.87 | -0.67 | 1.36 | 12.24 | 20.24 | 51.35 | 7.17 | 13.00 |

**Noise bar:**

- 96 null draws — time-shifted returns (>=1 day, both signs), same shift for every config so cross-config correlation is preserved
- SD of one formula's Sharpe under the null: **1.12**
- **expected max over these 32 formulas under the null: 1.27**   (p95: 1.86)
- naive `sqrt(2 ln N) x SD` for comparison: 2.96

| formula | design gross SR | x bar | design net SR | turnover/bar | held-out gross SR | held-out net SR | what it is |
|---|---|---|---|---|---|---|---|
| `C1_betagap_rank_5m` | +51.35 | +40.30 | -398.53 | 1.35 | +32.95 | -225.87 | cross-sectional RANK of the 1-bar catch-up gap instead of its raw size |
| `I1_liqtier_lead_k1_5m` | +30.94 | +24.29 | -230.52 | 1.44 | +39.13 | -182.50 | the top-liquidity-quintile alt basket leads; trade only the bottom-half-liquidity names on their catch-up gap |
| `C3_gap_volscaled_5m` | +30.56 | +23.99 | -237.23 | 1.47 | +32.42 | -201.60 | catch-up gap divided by the alt's trailing 1d return volatility (risk-parity legs) |
| `B1_betagap_k1_5m` | +20.25 | +15.90 | -146.27 | 1.46 | +22.56 | -109.37 | alt is long by how far its beta-implied move from BTC's last bar exceeds its own realised move (XS-neutral) |
| `C2_gap_beta1_5m` | +20.11 | +15.78 | -144.88 | 1.46 | +21.98 | -105.91 | catch-up gap assuming beta==1 for every alt (no beta estimation at all) |
| `G3_gap_calm_only_5m` | +18.22 | +14.30 | -141.62 | 1.21 | +21.86 | -109.53 | catch-up gap armed only on CALM bars (BTC move under 1 trailing sigma) -- the complement of G2 |
| `I2_liqtier_lead_k6_5m` | +13.55 | +10.64 | -96.20 | 0.63 | +19.91 | -72.78 | same tier lead-lag with a 30m leader lookback, 5m rebalance |
| `B2_betagap_k3_5m` | +13.06 | +10.25 | -81.22 | 0.87 | +14.53 | -58.22 | same catch-up gap measured over BTC's last 3 bars (15m) at 5m rebalancing |
| `K1_gap_multilag_5m` | +11.97 | +9.40 | -64.54 | 0.74 | +15.14 | -46.63 | catch-up gap summed over BTC lookbacks 1, 3 and 12 bars (distributed-lag transmission) |
| `H1_gap_asia_hours_5m` | +11.78 | +9.24 | -88.91 | 0.49 | +13.06 | -64.45 | catch-up gap traded only during 00:00-08:00 UTC (Asia session) |
| `K2_gap_accel_5m` | +10.25 | +8.05 | -147.84 | 1.27 | +9.99 | -108.04 | gap over BTC's last bar MINUS the gap over the previous 3 bars (transmission acceleration) |
| `H2_gap_us_hours_5m` | +9.44 | +7.41 | -74.02 | 0.49 | +13.61 | -68.26 | catch-up gap traded only during 13:00-21:00 UTC (US session) |
| `D2_btcpush_illiq_5m` | +7.54 | +5.92 | -261.49 | 1.03 | +4.77 | -212.40 | BTC's last-bar return weighted by INVERSE liquidity rank -- the thin-book alts are the ones that lag |
| `B3_betagap_k12_5m` | +5.50 | +4.32 | -41.76 | 0.45 | +8.21 | -29.67 | catch-up gap over the last 1h of BTC vs alt, 5m rebalancing |
| `G2_gap_after_bigbtc_5m` | +4.87 | +3.82 | -36.66 | 0.10 | +2.63 | -18.40 | catch-up gap, but only armed on bars where BTC's last move exceeded 2 trailing sigma |
| `B4_betagap_k1_30m` | +2.33 | +1.83 | -23.40 | 1.44 | +3.55 | -18.39 | catch-up gap at 30m bars, one-bar lookback |
| `B7_betagap_k1_1d` | +0.40 | +0.31 | -0.45 | 1.44 | -2.77 | -3.40 | catch-up gap at daily bars |
| `B5_betagap_k1_1h` | +0.10 | +0.07 | -14.45 | 1.44 | +0.64 | -10.80 | catch-up gap at 1h bars |
| `J1_alts_lead_btc_k1_5m` | +0.00 | +0.00 | +0.00 | 0.00 | +0.00 | +0.00 | trade BTC ALONE on the gap between the equal-weight alt complex and BTC over the last 5m (reverse lead-lag) |
| `J2_alts_lead_btc_k6_30m` | +0.00 | +0.00 | +0.00 | 0.00 | +0.00 | +0.00 | trade BTC alone on the alt-complex-minus-BTC gap over the last 3h, 30m rebalance |
| `F2_ethbtc_rot_4h` | -0.00 | -0.00 | -6.38 | 0.97 | -0.00 | -6.30 | same ETH-minus-BTC rotation signal at 4h |
| `A1_btc_push_dir_5m` | -0.13 | -0.10 | -79.29 | 1.03 | +3.26 | -68.97 | long every liquid alt when BTC's last 5m return is up, short when down (equal weight, directional) |
| `E2_btc_takerimb_beta_xs_5m` | -0.23 | -0.18 | -181.21 | 0.94 | -0.06 | -182.65 | BTC aggressor imbalance times alt beta, cross-sectionally demeaned |
| `B6_betagap_k1_4h` | -0.58 | -0.46 | -4.25 | 1.44 | +0.33 | -2.47 | catch-up gap at 4h bars |
| `F1_ethbtc_rot_30m` | -0.92 | -0.72 | -46.54 | 0.95 | -1.40 | -47.09 | when ETH outperformed BTC over the last 30m, go long the alt complex and short nothing else (XS-demeaned by beta) |
| `E3_btc_takerimb_1h` | -1.02 | -0.80 | -8.12 | 1.05 | -0.30 | -7.94 | BTC aggressor imbalance at 1h aggregation, directional across alts |
| `D1_btcpush_beta_xs_5m` | -1.16 | -0.91 | -216.98 | 0.96 | +0.11 | -204.76 | BTC's last-bar return times the alt's beta, cross-sectionally demeaned -- high-beta alts get the push, no own-return term |
| `E1_btc_takerimb_dir_5m` | -1.22 | -0.96 | -73.44 | 0.94 | +2.54 | -61.87 | BTC aggressor imbalance (taker-buy share minus half) last bar, directional across all alts |
| `A3_btc_push_dir_4h` | -1.94 | -1.52 | -3.84 | 1.10 | +0.93 | -1.19 | BTC's last 4h return sign drives a 4h-held equal-weight alt book |
| `D3_majors_push_xs_30m` | -2.31 | -1.82 | -41.70 | 1.05 | -0.74 | -45.95 | equal-weight BTC/ETH/BNB/SOL/XRP basket return over the last 30m times beta, XS-demeaned |
| `A2_btc_push_dir_30m` | -2.99 | -2.34 | -17.26 | 1.06 | +0.22 | -13.67 | same, BTC's last 30m return sign drives a 30m-held equal-weight alt book |
| `G1_betagap_FADE_5m` | -20.25 | -15.90 | -186.46 | 1.46 | -22.56 | -154.37 | the SIGN-FLIPPED catch-up gap: alts that already ran past their beta-implied move keep running |

## Block: `crypto_perp_leadlag_ADDENDUM_slow_horizons`

- panel: `(shared with the parent crypto block)`
- design: 2023-01-01 .. 2025-06-30   |   held out: 2025-07-01 .. 2026-08-17
- formulas: **11**
- cost: **6.0 bp per side** — BROKER_SCHEDULE (Binance USD-M VIP0 taker 5bp) + STRESS_LADDER (1bp slippage). NOT a measurement of our own fills.

**Full design gross-Sharpe distribution (every formula, nothing dropped):**

| n | min | p10 | p25 | median | p75 | p90 | max | mean | sd |
|---|---|---|---|---|---|---|---|---|---|
| 11 | -0.59 | -0.46 | 0.60 | 0.81 | 0.99 | 1.13 | 3.04 | 0.80 | 0.90 |

**Noise bar:**

- 96 null draws — time-shifted returns (>=1 day, both signs), shared shift per draw
- SD of one formula's Sharpe under the null: **0.65**
- **expected max over these 11 formulas under the null: 0.90**   (p95: 1.46)
- naive `sqrt(2 ln N) x SD` for comparison: 1.43

| formula | design gross SR | x bar | design net SR | turnover/bar | held-out gross SR | held-out net SR | what it is |
|---|---|---|---|---|---|---|---|
| `J1b_alts_lead_btc_k1_5m` | +3.04 | +3.38 | -115.57 | 1.00 | +3.59 | -130.14 | trade BTC ALONE on the gap between the equal-weight alt complex and BTC over the last 5m (reverse lead-lag) |
| `J2b_alts_lead_btc_k6_30m` | +1.13 | +1.26 | -7.28 | 0.39 | +0.01 | -9.45 | trade BTC alone on the alt-complex-minus-BTC gap over the last 3h, 30m rebalance |
| `Z1_illiq_lag_btc_sign_30m` | +1.04 | +1.16 | -65.89 | 1.07 | +0.02 | -50.94 | long thin-book alts / short liquid alts on the SIGN of BTC's last 30m move, held 30m (no own-return term) |
| `Z1_illiq_lag_btc_sign_1h` | +0.93 | +1.04 | -34.60 | 1.08 | -1.33 | -33.47 | long thin-book alts / short liquid alts on the SIGN of BTC's last 1h move, held 1h (no own-return term) |
| `Z2_illiq_lag_btc_mag_1h` | +0.93 | +1.04 | -34.60 | 1.08 | -1.33 | -33.47 | same illiquidity-tier transmission but scaled by the SIZE of BTC's last 1h move, held 1h |
| `Z3_illiq_lag_btc_2bar_4h` | +0.81 | +0.91 | -5.66 | 0.77 | -0.15 | -6.53 | illiquidity-tier transmission on BTC's last TWO 4h bars (slower lead window) |
| `Z2_illiq_lag_btc_mag_4h` | +0.77 | +0.86 | -8.69 | 1.13 | -0.51 | -9.55 | same illiquidity-tier transmission but scaled by the SIZE of BTC's last 4h move, held 4h |
| `Z1_illiq_lag_btc_sign_4h` | +0.77 | +0.86 | -8.69 | 1.13 | -0.51 | -9.55 | long thin-book alts / short liquid alts on the SIGN of BTC's last 4h move, held 4h (no own-return term) |
| `J3b_alts_lead_btc_k1_4h` | +0.43 | +0.48 | -2.39 | 1.02 | +1.69 | -1.62 | trade BTC alone on the alt-complex-minus-BTC gap over the last 4h |
| `Z3_illiq_lag_btc_2bar_1d` | -0.46 | -0.52 | -1.65 | 0.86 | -0.34 | -1.38 | illiquidity-tier transmission on BTC's last TWO 1d bars (slower lead window) |
| `Z1_illiq_lag_btc_sign_1d` | -0.59 | -0.66 | -2.21 | 1.17 | -1.43 | -2.89 | long thin-book alts / short liquid alts on the SIGN of BTC's last 1d move, held 1d (no own-return term) |

## Block: `us_equity_daily_leadlag`

- panel: `/home/anont/meme/research/data/xll_cache/eq_daily_panel.npz`
- design: 2016-01-05 .. 2021-12-31   |   held out: 2022-01-03 .. 2026-08-14
- formulas: **31**
- cost: **5.0 bp per side** — B22B MEASURED full quoted spread p50=3bp on this liquidity band -> 1.5bp half-spread, plus a 3.5bp impact rung (STRESS_LADDER).
- known bias: t17 universe comes from a CURRENT broker asset list: delisted names absent (survivorship). All formulas are dollar-neutral and XS-demeaned, which absorbs most of it.

**Full design gross-Sharpe distribution (every formula, nothing dropped):**

| n | min | p10 | p25 | median | p75 | p90 | max | mean | sd |
|---|---|---|---|---|---|---|---|---|---|
| 31 | -2.12 | -0.61 | -0.32 | -0.05 | 0.43 | 0.61 | 2.12 | 0.01 | 0.69 |

**Noise bar:**

- 240 null draws — time-shifted returns (>=5 days, both signs), one shared shift per draw so cross-config correlation is preserved
- SD of one formula's Sharpe under the null: **0.53**
- **expected max over these 31 formulas under the null: 0.84**   (p95: 1.25)
- naive `sqrt(2 ln N) x SD` for comparison: 1.39

| formula | design gross SR | x bar | design net SR | turnover/bar | held-out gross SR | held-out net SR | what it is |
|---|---|---|---|---|---|---|---|
| `P2_ovn_gap_reversal` | +2.12 | +2.52 | +0.65 | 1.48 | +1.43 | +0.15 | the stock's own overnight gap minus its beta-implied share of SPY's gap, faded from open to close (idiosyncratic overnight overreaction) |
| `L4_spy_gap_k20` | +0.77 | +0.91 | +0.45 | 0.30 | +1.06 | +0.71 | same catch-up gap over SPY's last 20 days (slow transmission) |
| `M2_sector_gap_k5` | +0.72 | +0.86 | +0.06 | 0.63 | +1.48 | +0.75 | same sector-ETF catch-up gap over the last 5 days |
| `L3_spy_gap_k5` | +0.61 | +0.72 | -0.02 | 0.63 | +1.49 | +0.78 | same catch-up gap measured over SPY's last 5 days |
| `M3_sector_push_only` | +0.51 | +0.60 | -1.32 | 1.28 | -0.05 | -2.32 | the most-loaded sector SPDR's own return yesterday, XS-demeaned -- sector transmission without the own-return term |
| `M1_sector_gap_k1` | +0.47 | +0.56 | -1.12 | 1.45 | +1.12 | -0.53 | each stock's catch-up gap against the sector SPDR it loads most on (1-day lead) |
| `Q1_breadth_leads_spy` | +0.43 | +0.52 | -0.26 | 0.97 | +0.26 | -0.45 | trade SPY ALONE on yesterday's gap between the equal-weight liquid universe and SPY itself (components lead the index) |
| `P5_btcovn_leads_oc` | +0.43 | +0.51 | -0.80 | 0.87 | -0.12 | -0.91 | Bitcoin's most recent completed UTC-day move (crypto trades while the US is shut) times BTC beta, held US open-to-close |
| `N1_liqtier_lead` | +0.43 | +0.51 | -1.13 | 1.44 | +1.00 | -0.63 | the top-liquidity-quintile basket's move yesterday leads the bottom-half-liquidity names' catch-up gap |
| `L2_spy_gap_k2` | +0.38 | +0.45 | -0.64 | 1.01 | +1.13 | +0.00 | same catch-up gap measured over SPY's last 2 days |
| `O7_btc_lead_equity` | +0.33 | +0.40 | -0.55 | 0.87 | +0.35 | -0.32 | yesterday's Bitcoin (Bitstamp spot) return times each stock's trailing BTC beta -- crypto-to-equity transmission |
| `N2_size_rotation` | +0.22 | +0.27 | -0.58 | 0.84 | +0.00 | -0.79 | yesterday's IWM-minus-SPY small-vs-large rotation times each name's loading on that spread |
| `L1_spy_gap_k1` | +0.19 | +0.22 | -1.28 | 1.45 | +0.97 | -0.66 | each stock is long by how far SPY's beta-implied move yesterday exceeded the stock's own move (index-leads-component catch-up, XS-neutral) |
| `L5_spy_gap_rank` | +0.15 | +0.18 | -2.14 | 1.28 | +0.08 | -2.40 | cross-sectional RANK of the 1-day SPY catch-up gap |
| `L8_qqq_gap_k1` | +0.11 | +0.13 | -1.31 | 1.45 | +1.10 | -0.60 | same 1-day catch-up gap but with QQQ as the leading index instead of SPY |
| `O5_vol_lead_VIXY` | -0.05 | -0.06 | -0.62 | 0.80 | -0.34 | -0.97 | yesterday's VIXY return times each stock's trailing vol beta |
| `O9_rates_lead_5d` | -0.09 | -0.11 | -0.45 | 0.37 | +0.46 | -0.12 | TLT's last 5 days times the stock's rate beta (slower rates transmission) |
| `O3_oil_lead_USO` | -0.11 | -0.13 | -0.72 | 0.83 | -0.30 | -1.33 | yesterday's USO (crude) return times each stock's trailing oil beta |
| `Q2_smh_leads_spy` | -0.18 | -0.21 | -0.92 | 1.05 | -0.01 | -0.76 | trade SPY alone on yesterday's SMH-minus-SPY gap (semis as the cyclical bellwether leading the tape) |
| `L6_spy_gap_FADE` | -0.19 | -0.22 | -1.66 | 1.45 | -0.97 | -2.61 | SIGN-FLIPPED SPY catch-up gap: names that already overshot SPY keep going |
| `Q3_credit_leads_spy` | -0.22 | -0.26 | -0.96 | 1.05 | +0.36 | -0.36 | trade SPY alone on yesterday's HYG-minus-LQD credit-spread move (credit leads equity) |
| `P1_spyovn_leads_oc` | -0.25 | -0.30 | -1.23 | 0.86 | -0.61 | -1.38 | SPY's OVERNIGHT gap times each stock's overnight beta, held from today's open to today's close |
| `O4_credit_lead_HYGLQD` | -0.27 | -0.32 | -1.05 | 0.89 | +0.28 | -0.61 | yesterday's HYG-minus-LQD credit-spread return times each stock's loading on it |
| `O2_usd_lead_UUP` | -0.37 | -0.45 | -1.55 | 0.87 | -0.35 | -1.21 | yesterday's UUP (dollar index) return times each stock's trailing dollar beta |
| `P4_overseas_leads_oc` | -0.54 | -0.64 | -1.54 | 0.89 | +0.06 | -0.72 | the overseas basket's close-to-close move yesterday, times EFA beta, traded US open-to-close today |
| `L7_spy_push_beta_xs` | -0.56 | -0.67 | -1.19 | 0.86 | -0.89 | -1.50 | SPY's return yesterday times the stock's beta, XS-demeaned -- pure index transmission with NO own-return term |
| `O6_gold_lead_GLD` | -0.60 | -0.71 | -1.59 | 0.87 | -0.32 | -1.23 | yesterday's GLD return times each stock's trailing gold beta |
| `O8_overseas_lead` | -0.61 | -0.72 | -1.27 | 0.89 | -0.10 | -0.74 | yesterday's EFA+EWJ+FXI overseas-session basket return times each stock's EFA beta -- the foreign close leads the US open |
| `O1_rates_lead_TLT` | -0.70 | -0.83 | -1.56 | 0.89 | +0.13 | -1.27 | yesterday's TLT (long-bond) return times each stock's trailing rate beta, XS-demeaned |
| `O10_xasset_composite` | -0.71 | -0.85 | -1.66 | 1.09 | -0.16 | -1.34 | sum of the TLT, UUP, USO, credit and VIXY one-day transmission signals (composite cross-asset push) |
| `P3_ovn_gap_momentum` | -2.12 | -2.52 | -3.58 | 1.48 | -1.43 | -2.71 | the SAME idiosyncratic overnight gap traded with the opposite sign (continuation instead of reversal) |

## Focused pass on the one survivor (`P2_ovn_gap_reversal`)

P2 was the only formula in 74 to clearly clear its bar (design gross 2.12 against a bar of
0.84). It is a stock's own overnight gap, minus its beta-implied share of SPY's overnight
gap, faded from today's open to today's close. Three questions the sweep table cannot
answer: does the cross-asset term do anything, what cost turns it off, and does it survive
on names where a 5bp fill is defensible.

| variant | design gross SR | held-out gross SR | turnover/day | breakeven cost/side (design) | breakeven (held-out) | net@5bp d/h | net@10bp d/h |
|---|---|---|---|---|---|---|---|
| P2 as swept: SPY-beta-neutralised overnight gap, faded open->close | +2.12 | +1.43 | 1.48 | 7.2 bp | 5.6 bp | +0.65 / +0.15 | -0.82 / -1.13 |
| NO cross-asset term at all: fade the raw overnight gap, XS-demeaned | +1.92 | +1.54 | 1.48 | 6.7 bp | 6.4 bp | +0.49 / +0.33 | -0.93 / -0.87 |
| beta forced to 1 instead of estimated | +1.92 | +1.54 | 1.48 | 6.7 bp | 6.4 bp | +0.49 / +0.33 | -0.93 / -0.87 |
| rank of the residual gap instead of its size | +2.67 | +1.52 | 1.26 | 4.0 bp | 2.3 bp | -0.71 / -1.73 | -4.09 / -4.99 |
| P2 restricted to the top HALF by dollar volume | +1.02 | +0.83 | 1.48 | 3.5 bp | 3.0 bp | -0.43 / -0.57 | -1.88 / -1.97 |
| P2 restricted to the top QUINTILE by dollar volume | +0.46 | +0.13 | 1.48 | 1.8 bp | 0.5 bp | -0.85 / -1.12 | -2.17 / -2.38 |

