# SWEEP v2 — cross-asset & cross-venue lead-lag, the two corners the first sweep missed

**Verdict: the theme is still noise, and this time the reason is sharper than "nothing predicts anything".** 70 more structurally different lead-lag formulas (49 intraday US cross-asset + 21 cross-venue crypto), on top of the 74 in `SWEEP_xll_leadlag.md`. Two things are now clear:

1. **Pure cross-asset transmission is dead at every frequency tested.** Every formula whose signal is one asset's past return predicting another's future return, with no term for the predicted asset's own past return — `A6_spypush_beta_xs`, `B3_sectorpush_only`, `G3_foreign_spypush`, the whole F macro family, `Z3_binanceflow_only` — sits at or below its noise bar intraday, exactly as it did daily. Adding a 5-minute clock did not wake it up.
2. **What DOES clear the bar is not a lead-lag, it is stale quotes, and it is priced out by 30-70x.** The clone/dual-listed ETF family (SPY-IVV-VOO-SPLG, QQQ-QQQM, GLDM-IAU, SMH-SOXX, GOOG-GOOGL, VGT-XLK ...) posts design gross Sharpe 5.06 against a bar of 1.06, and it HOLDS OUT (4.79). It is real. It is also completely untradeable: it breaks even at **0.028 bp per side**, against a 1 bp per-side cost on the very cheapest leg in the panel. The convergence is the slower ETF's 5-minute print catching up inside the spread. You cannot cross a 1 bp spread to collect 0.03 bp.

Nothing here should be promoted to a forward test.

## What is new versus `SWEEP_xll_leadlag.md`

The first sweep covered US equities DAILY and Binance perps at 5m, both inside a single venue. It never tested (a) intraday transmission inside the US session, or (b) one venue leading another. Both gaps are closed here:

- **Block A — intraday (5-minute) US cross-asset**, 49 formulas on 122 cached ETFs and mega-caps, 2021-01 .. 2026-08: index -> component, sector ETF -> member, ETF <-> its creation basket, clone/dual-listed pairs, leveraged-vs-base tracking, rates / credit / oil / gold / curve -> equity inside the day, and the US tape -> foreign ETFs whose home exchange is shut.
- **Block B — cross-VENUE crypto**, 21 formulas: Hyperliquid's hourly premium and funding (t25 cache, 62 coins that also trade on Binance) against the next hour's Binance USD-M return. Hyperliquid's premium change is literally "venue A's price moved away from the index"; the question is whether venue B follows.

## Method, and what makes the noise bar honest

- Every formula scored on a **design window only**. The held-out window is computed by the same code path and never used to choose anything.
- **Execution is deliberately un-idealised.** The signal is built from closes through bar `t`; the position is held over `open[t+1] -> open[t+2]`. One full bar of air between the last price the signal sees and the price it trades. This is what stops the 5-minute bid-ask bounce from masquerading as a lead-lag, which is what inflated the crypto block of the first sweep to gross Sharpe 51.
- **Sharpe is computed on the SESSION-aggregated P&L**, not on overlapping bar P&L, so a smoothed / multi-bar-hold position cannot inflate it.
- The noise bar is **empirical, not `sqrt(2 ln N)`**: each draw time-shifts the return matrix by at least one session, both signs, and re-scores EVERY formula against the same shift. That destroys the lead-lag relation while preserving turnover, autocorrelation, and — crucially — how correlated the formulas are with each other.
- **Lookahead audit, automated:** 49/49 configs CLEAN (tail past 65% reversed and rescaled; 0 reading the future)
- Costs are charged per side on realised `sum|w_t - w_{t-1}|`, per symbol, and every table also reports the **breakeven cost per side** so the reader never has to trust the cost assumption.

## Block A: `us_intraday_5m_xasset_leadlag`

- panel: `/home/anont/meme/research/data/xll2_cache/intraday5m_panel.npz`
- design: 2021-01-04 .. 2024-12-31   |   held out: 2025-01-02 .. 2026-08-14
- formulas: **49**
- execution: signal from closes through bar t; position held open[t+1]->open[t+2] (one full bar of air); Sharpe on session-aggregated P&L
- cost: per-symbol per-side tier by trailing ADV: >$2B 1.0bp, >$300M 2.0bp, >$50M 3.5bp, else 6.0bp
- cost provenance: B22B MEASURED full quoted spread p50=3bp on a mid-liquidity US band -> 1.5bp half-spread; tiers scale that by ADV and add a 5-minute impact rung (STRESS_LADDER). NOT a measurement of our own fills.
- known bias: 122-name universe is a CURRENT liquid ETF/mega-cap list (survivorship); all formulas dollar-neutral and XS-demeaned, which absorbs most of it.

**Full design gross-Sharpe distribution (every formula, nothing dropped):**

| n | min | p10 | p25 | median | p75 | p90 | max | mean | sd |
|---|---|---|---|---|---|---|---|---|---|
| 49 | -4.74 | -0.61 | 0.04 | 0.35 | 0.96 | 1.73 | 5.06 | 0.57 | 1.53 |

**Noise bar:**

- 200 null draws — time-shifted returns (>=1 session, both signs), one shared shift per draw so cross-config correlation is preserved
- SD of one formula's Sharpe under the null: **0.50**
- **expected max over these 49 formulas under the null: 1.06**   (p95: 1.49)
- naive `sqrt(2 ln N) x SD` for comparison: 1.40

| formula | design gross SR | x bar | design net SR | turnover/day | breakeven bp/side | held-out gross SR | what it is |
|---|---|---|---|---|---|---|---|
| `D1_clonegap_k1_h1` | +5.06 | +4.77 | -285.44 | 126.13 | 0.028 | +4.79 | clone/dual-listed ETF pairs (SPY-IVV-VOO-SPLG, QQQ-QQQM, GLDM-IAU, SMH-SOXX, GOOG-GOOGL, ...): long whichever leg lagged its group over the last 5 minutes |
| `D2_clonegap_k3_h3` | +4.74 | +4.47 | -202.91 | 62.47 | 0.037 | +2.81 | same clone-group convergence over 15 minutes |
| `D3_clonegap_k12_h12` | +3.91 | +3.68 | -90.99 | 17.74 | 0.082 | +1.10 | same clone-group convergence over an hour |
| `A1_spygap_k1_h1` | +3.40 | +3.20 | -45.46 | 107.41 | 0.115 | -0.45 | index-leads-component catch-up: how far SPY's beta-implied 5m move exceeded the stock's own, XS-neutral, held one bar |
| `E1_levgap_k3_h3` | +2.00 | +1.88 | -22.20 | 68.10 | 0.227 | +1.35 | leveraged ETFs (SSO/UPRO/QLD/TQQQ/TNA/TMF): long by how far the base index's L-times-implied 15m move exceeded the leveraged ETF's own |
| `B1_sectorgap_k3_h3` | +1.66 | +1.57 | -23.00 | 43.55 | 0.111 | +0.68 | each stock's 15-minute catch-up gap against its own GICS sector SPDR |
| `G1_foreign_spygap_k3` | +1.64 | +1.54 | -36.43 | 43.83 | 0.097 | +1.51 | foreign-market ETFs (EEM/EFA/EWJ/EWZ/FXI/...) whose underlying exchange is CLOSED: catch-up gap to SPY's last 15 minutes |
| `A2_spygap_k3_h3` | +1.63 | +1.54 | -19.78 | 43.04 | 0.126 | +0.60 | same catch-up gap over SPY's last 15 minutes, held 15 minutes |
| `D5_dualclass_goog_k3` | +1.55 | +1.47 | -37.27 | 34.95 | 0.038 | +2.52 | the GOOG/GOOGL dual-class pair alone: long the share class that lagged over 15 minutes |
| `I1_spygap_bigmove_only` | +1.53 | +1.44 | -1.22 | 2.11 | 0.885 | +0.04 | the hourly catch-up gap armed only when SPY's last hour exceeded 2 trailing sigma |
| `D6_vanguard_vs_spdr_k3` | +1.42 | +1.34 | -86.49 | 56.24 | 0.022 | -0.68 | Vanguard sector ETF vs its SPDR twin (VGT-XLK, VDE-XLE, ...): long whichever twin lagged over 15 minutes |
| `A4_spygap_k39_h39` | +1.34 | +1.27 | -2.07 | 3.68 | 0.628 | +0.89 | same catch-up gap over SPY's last half session, held half a session |
| `E2_levgap_k12_h12` | +0.96 | +0.90 | -8.05 | 24.55 | 0.291 | -0.21 | same leveraged-vs-base tracking gap over an hour |
| `A8_spygap_k12_rank` | +0.94 | +0.89 | -9.68 | 11.62 | 0.149 | +0.35 | cross-sectional RANK of the hourly catch-up gap instead of its size |
| `A10_spygap_k12_volscaled` | +0.80 | +0.75 | -8.01 | 11.21 | 0.154 | -0.08 | hourly catch-up gap divided by the name's trailing 5-day vol (risk-parity legs) |
| `H2_spygap_close30` | +0.72 | +0.68 | -5.23 | 2.80 | 0.192 | +0.64 | the hourly catch-up gap traded only in the last 30 minutes of the session |
| `B2_sectorgap_k12_h12` | +0.65 | +0.61 | -7.00 | 11.23 | 0.137 | +0.31 | same sector-SPDR catch-up gap over the last hour |
| `A3_spygap_k12_h12` | +0.60 | +0.56 | -6.35 | 11.21 | 0.139 | +0.46 | same catch-up gap over SPY's last hour, held an hour |
| `A9_qqqgap_k12` | +0.58 | +0.55 | -6.69 | 11.20 | 0.130 | +0.21 | hourly catch-up gap against QQQ instead of SPY |
| `I2_spygap_calm_only` | +0.49 | +0.46 | -6.49 | 11.15 | 0.114 | +0.44 | the complement: the hourly catch-up gap armed only on CALM hours |
| `C4_smh_vs_semis_k3` | +0.48 | +0.45 | -5.87 | 28.78 | 0.150 | +1.42 | trade SMH alone on the 15-minute gap between the equal-weight semis (NVDA/AMD/AVGO/INTC) and the ETF |
| `C5_semis_lead_spy_k12` | +0.42 | +0.40 | -1.44 | 7.84 | 0.224 | +0.06 | trade SPY alone on the last hour of SMH-minus-SPY (semis as the cyclical bellwether leading the tape) |
| `G2_foreign_spygap_k12` | +0.39 | +0.37 | -10.68 | 11.40 | 0.076 | +1.07 | same US-leads-foreign catch-up gap over the last hour |
| `C7_rates_lead_spy_k12` | +0.35 | +0.33 | -1.44 | 7.71 | 0.194 | +0.85 | trade SPY alone on TLT's last hour (rates transmission into the index, sign: bonds up -> equity up) |
| `H3_spygap_midday` | +0.35 | +0.33 | -6.50 | 9.76 | 0.082 | -0.23 | the hourly catch-up gap traded only between 11:00 and 15:00 ET (midday only) |
| `C3_xlk_vs_members_k3` | +0.32 | +0.30 | -8.51 | 28.91 | 0.072 | +1.66 | trade XLK alone on the 15-minute gap between its equal-weight mega-cap members and the ETF (creation-basket lead-lag) |
| `E3_invgap_k3_h3` | +0.31 | +0.30 | -27.82 | 66.52 | 0.036 | -0.39 | same construction on the INVERSE ETFs (SH/SDS/PSQ/SQQQ/TZA/TMV) |
| `B3_sectorpush_only_h12` | +0.28 | +0.26 | -5.67 | 11.06 | 0.073 | -0.01 | the sector SPDR's own last-hour return times the member's sector beta -- sector transmission with NO own-return term |
| `B4_sector_rotation_h12` | +0.27 | +0.25 | -6.53 | 11.26 | 0.061 | -0.08 | sector-minus-SPY rotation over the last hour times the member's sector loading (rotation transmission) |
| `C8_smallcap_leads_spy_k12` | +0.25 | +0.24 | -1.59 | 7.77 | 0.136 | +0.10 | trade SPY alone on the last hour of IWM-minus-SPY (small caps as the risk-appetite tell) |
| `A7_spygap_k12_beta1` | +0.21 | +0.20 | -6.34 | 11.19 | 0.053 | +0.22 | hourly catch-up gap with beta forced to 1 -- no beta estimation at all |
| `C2_breadth_leads_spy_k12` | +0.16 | +0.15 | -1.54 | 7.86 | 0.093 | -0.14 | same breadth-leads-index gap over the last hour |
| `F1_rates_push_k12` | +0.15 | +0.14 | -4.47 | 8.68 | 0.052 | -1.60 | TLT's last hour times each stock's trailing rate beta, XS-demeaned |
| `G3_foreign_spypush_k12` | +0.14 | +0.13 | -7.37 | 7.95 | 0.036 | +0.02 | PURE US-to-foreign transmission: SPY's last hour times the ETF's SPY beta, no own-return term |
| `F4_gold_push_k12` | +0.09 | +0.09 | -4.24 | 8.80 | 0.035 | +1.20 | GLDM's last hour times each stock's trailing gold beta |
| `F5_curve_push_k12` | +0.08 | +0.08 | -4.55 | 8.75 | 0.028 | -1.56 | the TLT-minus-SHY yield-curve move over the last hour times each stock's curve loading |
| `C6_credit_leads_spy_k12` | +0.04 | +0.04 | -1.80 | 8.06 | 0.022 | +0.29 | trade SPY alone on the last hour of the HYG-minus-LQD credit-spread move (credit leads equity) |
| `A6_spypush_beta_xs_h12` | -0.00 | -0.00 | -3.11 | 7.70 | -0.001 | +0.15 | PURE index transmission: SPY's last-hour return times the stock's beta, XS-demeaned, NO own-return term |
| `G4_foreign_spygap_FADE` | -0.39 | -0.37 | -9.98 | 11.40 | -0.076 | -1.07 | SIGN-FLIPPED US-leads-foreign gap |
| `F3_oil_push_k12` | -0.44 | -0.41 | -5.19 | 8.01 | -0.151 | +0.42 | USO's last hour times each stock's trailing oil beta |
| `H1_spygap_open30` | -0.47 | -0.45 | -3.84 | 3.68 | -0.225 | +0.83 | the hourly catch-up gap traded only in the first 30 minutes of the session |
| `F2_credit_push_k12` | -0.50 | -0.47 | -4.70 | 9.00 | -0.189 | -0.19 | the HYG-minus-LQD credit move over the last hour times each stock's credit loading |
| `F6_macro_composite_k12` | -0.51 | -0.48 | -6.47 | 10.72 | -0.139 | +0.64 | sum of the rates, credit, oil, gold and curve one-hour transmission signals (composite cross-asset push) |
| `A5_spygap_k12_FADE` | -0.60 | -0.56 | -7.28 | 11.21 | -0.139 | -0.46 | SIGN-FLIPPED hourly catch-up gap: names that already overshot SPY keep going |
| `C1_breadth_leads_spy_k3` | -0.67 | -0.63 | -6.74 | 28.48 | -0.109 | +1.48 | trade SPY ALONE on the 15-minute gap between the equal-weight mega-cap basket and SPY itself (components lead the index) |
| `G5_foreign_leads_spy_k12` | -0.88 | -0.83 | -2.66 | 7.55 | -0.501 | +0.62 | reverse: trade SPY alone on the last hour of the equal-weight foreign-ETF basket minus SPY |
| `F7_rates_push_k3` | -0.93 | -0.88 | -13.75 | 29.86 | -0.114 | -1.04 | the same rates transmission at a 15-minute lead window (fast channel) |
| `E4_levgap_k3_FADE` | -2.00 | -1.88 | -26.23 | 68.10 | -0.227 | -1.35 | SIGN-FLIPPED leveraged tracking gap (divergence continues) |
| `D4_clonegap_k3_FADE` | -4.74 | -4.47 | -190.54 | 62.47 | -0.037 | -2.81 | SIGN-FLIPPED clone gap: the leg that ran ahead of its clones keeps running (divergence, not convergence) |

## Block B: `crypto_cross_venue_hl_binance_1h`

- panel: `/home/anont/meme/research/data/xll2_cache/xvenue_1h_panel.npz`
- design: 2023-07-18 .. 2025-06-30   |   held out: 2025-07-01 .. 2026-08-17
- formulas: **21**
- execution: signal known at the close of hour t; position held over hour t+1; Sharpe on day-aggregated P&L
- cost: **6.0 bp per side**
- cost provenance: BROKER_SCHEDULE (Binance USD-M VIP0 taker 5bp) + STRESS_LADDER (1bp slippage). NOT a measurement of our own fills.
- known bias: Hyperliquid universe is the CURRENT HL listing; 55 delisted coins are flagged in t25 and simply absent here (survivorship). Books are XS-demeaned and dollar-neutral.

**Full design gross-Sharpe distribution (every formula, nothing dropped):**

| n | min | p10 | p25 | median | p75 | p90 | max | mean | sd |
|---|---|---|---|---|---|---|---|---|---|
| 21 | -1.11 | -0.61 | -0.08 | 0.61 | 0.96 | 1.29 | 1.52 | 0.46 | 0.74 |

**Noise bar:**

- 200 null draws — time-shifted returns (>=1 day, both signs), one shared shift per draw so cross-config correlation is preserved
- SD of one formula's Sharpe under the null: **0.65**
- **expected max over these 21 formulas under the null: 1.17**   (p95: 1.74)
- naive `sqrt(2 ln N) x SD` for comparison: 1.60

| formula | design gross SR | x bar | design net SR | turnover/day | breakeven bp/side | held-out gross SR | what it is |
|---|---|---|---|---|---|---|---|
| `V5_hlprem_rank` | +1.52 | +1.30 | -3.35 | 3.08 | 1.859 | +0.49 | cross-sectional RANK of the Hyperliquid premium instead of its size |
| `Z2_prem_vs_binance_flow` | +1.45 | +1.24 | -26.08 | 30.56 | 0.253 | -1.67 | Hyperliquid's dislocation MINUS Binance's taker imbalance (standardised): the two venues DISagreeing |
| `V6_hlprem_z168` | +1.29 | +1.10 | -6.91 | 6.57 | 0.936 | -2.56 | Hyperliquid premium as a z-score against its own trailing week (each coin vs its own normal basis) |
| `V3_hlprem_level_h4` | +1.22 | +1.04 | -1.03 | 3.26 | 3.246 | -0.03 | same cross-venue basis level, held 4 hours |
| `V1_hlprem_level_h1` | +1.11 | +0.95 | -4.21 | 7.32 | 1.247 | -0.43 | long the coins that trade RICHEST on Hyperliquid relative to the index, short the cheapest, on Binance (cross-venue basis catch-up), held 1h |
| `Y1_hlfunding_level` | +0.96 | +0.82 | -0.63 | 2.53 | 3.628 | +1.11 | long the coins paying the most funding on Hyperliquid (venue-A crowding as a directional tell), held 8h |
| `W5_hldislocation_1h_rank` | +0.81 | +0.69 | -31.08 | 27.82 | 0.106 | -0.59 | cross-sectional rank of the one-hour Hyperliquid dislocation |
| `V4_hlprem_level_h24` | +0.81 | +0.69 | +0.01 | 1.03 | 6.082 | +1.04 | same cross-venue basis level, held 24 hours |
| `W6_hldislocation_1h_liquid` | +0.75 | +0.64 | -11.32 | 28.58 | 0.359 | -1.57 | the one-hour Hyperliquid dislocation traded only on the coins with a deep Binance book (>$10M/h) |
| `Y3_hlfunding_change_24h` | +0.61 | +0.52 | -2.05 | 4.13 | 1.379 | +0.63 | the 24-hour CHANGE in Hyperliquid funding (venue-A positioning is shifting) |
| `W1_hldislocation_1h` | +0.61 | +0.52 | -13.80 | 29.99 | 0.241 | -1.06 | Hyperliquid's price moved away from the index over the last hour; go WITH that move on Binance (venue A leads venue B) |
| `Z3_binanceflow_only` | +0.56 | +0.47 | -30.18 | 27.76 | 0.077 | +2.26 | CONTROL: Binance's own taker imbalance alone, no cross-venue term at all |
| `W8_hldislocation_accel` | +0.52 | +0.44 | -13.52 | 29.64 | 0.210 | +0.04 | the last hour's dislocation MINUS the previous three hours' (cross-venue transmission acceleration) |
| `W7_hldislocation_bigonly` | +0.49 | +0.42 | -6.54 | 15.57 | 0.408 | -1.26 | the one-hour dislocation armed only when it exceeds 2 trailing sigma of that coin's basis (big cross-venue gaps only) |
| `W3_hldislocation_4h` | +0.20 | +0.17 | -8.59 | 11.37 | 0.134 | -1.88 | Hyperliquid's dislocation from the index over the last 4 hours, followed on Binance |
| `Z1_prem_x_binance_flow` | -0.08 | -0.07 | -13.18 | 30.23 | -0.033 | +0.91 | Hyperliquid's dislocation TIMES Binance's own taker-buy imbalance: the two venues agreeing |
| `W4_hldislocation_24h` | -0.16 | -0.13 | -1.96 | 2.46 | -0.517 | +1.06 | Hyperliquid's dislocation over the last 24 hours, followed on Binance |
| `Z4_btc_hlprem_leads_alts` | -0.35 | -0.30 | -3.60 | 9.67 | -0.645 | +0.74 | BTC's Hyperliquid premium (one venue's view of the majors) times each alt's BTC beta -- majors' cross-venue basis leading the complex |
| `W2_hldislocation_1h_FADE` | -0.61 | -0.52 | -14.89 | 29.99 | -0.241 | +1.06 | same one-hour Hyperliquid dislocation traded the other way (Binance does NOT follow, it reverts) |
| `Y2_hlfunding_FADE` | -0.96 | -0.82 | -2.54 | 2.53 | -3.628 | -1.11 | short the coins paying the most Hyperliquid funding (crowding unwinds) |
| `V2_hlprem_level_FADE` | -1.11 | -0.95 | -6.41 | 7.32 | -1.247 | +0.43 | SIGN-FLIPPED: short what is rich on Hyperliquid (the dislocation mean-reverts rather than propagates) |

The best formula in block B is `V5_hlprem_rank` at +1.52 against a bar of 1.17 — a factor of 1.30, and below the p95 of the null max (1.74). That is not a finding, that is the bar. Note also what the top of that table is made of: `V1/V3/V4/V5/V6/Y1` are all the same thing — the LEVEL of the Hyperliquid basis, i.e. carry, which this repo has already killed four separate ways. The formulas that are genuinely cross-venue *lead-lag* (the `W` family: venue A's price dislocates, does venue B follow?) top out at +0.81 against a 1.17 bar, and the sign-flip of each is its exact mirror image, which is what a zero looks like.

## Focused pass on the one family that clears the bar (clone / dual-listed pairs)

*POST-HOC: these 8 configs were chosen after seeing the 49-formula parent block. Their own noise bar is reported; they must not be counted as independent discoveries.* Its own bar: expected max 0.65 over 8 configs (p95 1.15).

The parent block already answers "is it real" (yes: design 5.06, held out 4.79) and "is it tradeable" (no: breakeven 0.028 bp). This pass asks the only question that could rescue it — does the gross survive when turnover is cut hard, and does it survive on the one clone group where a 1 bp fill is defensible (SPY/IVV/VOO/SPLG, every leg over $2B a day)?

| variant | design gross SR | held-out gross SR | turnover/day | breakeven bp/side (design) | breakeven (held-out) | net@1bp d/h |
|---|---|---|---|---|---|---|
| ONLY the SPY/IVV/VOO/SPLG group, half-session gap | +4.00 | +0.72 | 10.37 | 0.036 | 0.022 | -41.7 / -19.5 |
| ONLY the SPY/IVV/VOO/SPLG group, 15-minute gap | +3.91 | +1.22 | 67.15 | 0.022 | 0.010 | -139.9 / -45.9 |
| ONLY the SPY/IVV/VOO/SPLG group, hourly gap | +3.86 | +1.13 | 29.42 | 0.030 | 0.018 | -76.0 / -25.7 |
| ONLY the SPY/IVV/VOO/SPLG group (every leg >$2B/day, a 1bp fill is defensible), 5-minute gap | +2.94 | +2.73 | 121.71 | 0.015 | 0.014 | -176.7 / -88.3 |
| all clone groups but only legs above $300M/day (drops SPLG/QQQM/VTWO/SOXX-tier staleness) | +2.58 | +1.30 | 61.10 | 0.033 | 0.014 | -76.1 / -92.1 |
| all clone groups, hourly gap, held 39 bars (half a session) | +2.45 | +0.59 | 6.43 | 0.101 | 0.028 | -22.8 / -21.8 |
| all clone groups, half-session gap, held half a session | +1.90 | +1.07 | 5.19 | 0.096 | 0.061 | -18.2 / -17.0 |
| all clone groups, half-session gap, held a full session | +0.00 | +0.00 | 0.00 | 0.000 | 0.000 | +nan / +nan |

The answer is a flat wall. Cutting turnover from 126x/day to 5x/day cuts the gross in almost exactly the same proportion: the breakeven never leaves the 0.015-0.10 bp band at any hold, on any subset, liquid or not. `F3` reports zeros because a full-session hold leaves at most one armed bar per day once the averaging window is required to sit inside the session — it is a degenerate config, not a result.

## What this leaves

144 lead-lag formulas across the two sweeps, three frequencies (5m, 1h, 1d), two asset classes and two venues. The pure-transmission hypothesis — asset X's past move predicts asset Y's future move — has now been tested wide enough that its repeated failure is itself the finding: on free/cached data, at the frequencies a retail account can act on, cross-asset lead-lag in liquid instruments is arbitraged away below the spread. The only surviving structure is quote staleness between wrappers on the same basket, and it lives strictly inside the bid-ask spread that would be paid to harvest it.
