# FACTORY v1 — PRE-REGISTRATION (frozen before any data was loaded into the harness)

**Author:** Claude (conductor). **Written:** 2026-11-10 13:30–14:10 UTC. **Status:** FROZEN at the sha256
recorded in `DECISIONS.md`. Any change = a new document (`PREREGISTRATION_v2.md`) with its own trial
count; this one is never edited.

**Owner mandate (2026-11-10):** test many algorithms across memecoins / forex / long-short anything,
automate the decisions, grow the portfolio. **Scope of v1:** the three venues the previous programme never
tested as risk-premia books — **forex (daily, G10 vs USD)**, **multi-asset ETFs (daily)**, **crypto perps
(daily-rebalanced from hourly data)** — with ONE harness and ONE pooled multiple-testing account.
Memecoins are explicitly OUT of v1: ~600 hypotheses died there 2026-08/10 on three structural facts
(death is a −90 % jump, momentum entry is negative alpha vs random, session noise 4 pp > every edge); the
only honest memecoin instrument that exists is the judgment paper trader `apps/trader`, an owner-usage
decision, not a factory lane.

---

## 0. The one-paragraph claim under test

> A diversified, vol-targeted book of classic and invented systematic rules on low-friction instruments
> (FX majors, liquid ETFs, large crypto perps) earns a net Sharpe that clears a pooled multiple-testing
> bar on an 18/6/3-year design window AND confirms (t ≥ 2) on a never-touched 10/5/3-year holdout.

If true for even one frozen formula, that formula is a real, executable, scalable (not get-rich) portfolio
engine and goes to a forward paper logger. If false everywhere, the honest answer to "grow the portfolio
with a bot" on free data is **no**, and the report says so.

---

## 1. Lanes, data, windows

| lane | instruments | print (fill price) | design window | holdout window (SEALED) |
|---|---|---|---|---|
| **FX-D** | 9 G10 currencies vs USD: EUR GBP JPY CHF CAD AUD NZD SEK NOK (long = long the foreign currency, USD funding). Secondary EM sub-universe: MXN KRW SGD BRL INR ZAR THB TWD (CNY/HKD excluded: managed/pegged) | FRED H.10 noon-NY buying rate (`DEX*`), converted to USD per 1 unit FX. Placebo second print: ECB 14:15 CET reference rate, crossed to USD | 1999-01-04 → 2016-12-30 (18.0 y) | 2017-01-03 → 2026-11-06 (9.85 y) |
| **MA-ETF** | 50 US-listed ETFs: SPY QQQ IWM EFA EEM VGK EWJ EWZ EWA EWC EWG EWU EWY EWT INDA FXI KWEB · XLE XLF XLK XLV XLU XLI XLP XLY XLB · TLT IEF SHY LQD HYG TIP BND AGG EMB PFF · GLD SLV USO UNG DBC DBA · VNQ · FXE FXY FXB FXA FXC FXF UUP | Alpaca SIP daily close, `adjustment=all` (total return). Levels are never filtered. | 2016-01-04 → 2021-12-31 (6.0 y) | 2022-01-03 → 2026-11-06 (4.85 y) |
| **CRYPTO-H** | Top-40 Binance USD-M perps by 2021 dollar volume, INCLUDING later-delisted names (LUNA, FTT, …) to avoid survivorship; point-in-time membership not re-ranked (fixed list, declared in the data manifest before the sweep) | Binance archive 1h kline close; positions rebalanced once per day at the 00:00 UTC print | 2021-01-01 → 2023-12-31 (3.0 y) | 2024-01-01 → 2026-11-07 (2.85 y) |

**Carry panels.** FX: `(i_fx − i_usd)/360` per day from FRED daily policy/overnight rates where daily exists
(SOFR/DFF, ECBDFR, SONIA) else OECD monthly immediate rates (`IRSTCI01*`), each lagged so the value used
on day *t* was publicly known before *t* (daily series lag 1 day; monthly series: month *m* uses month
*m−1*). Crypto: realised 8-hourly funding from the archive, charged/credited to the position held at the
funding timestamp. ETF: none (dividends are in the adjusted price); short ETF positions pay borrow (§3).

**Pre-design robustness panel (read freely, it is before every design window):** FX 8 currencies
(no EUR) 1976-01 → 1998-12. Used only to report whether a design-window result also held there; never
to select.

**Missing data rule:** forward-fill ≤ 3 consecutive prints (holidays); an instrument with > 5 % missing
prints in a window is dropped from that window and the drop is logged.

## 2. Engine conventions (identical for every lane and formula)

- `r_t = P_t/P_{t−1} − 1`; target `w_s` (fraction of equity, signed) decided at print `s` using rows
  `≤ s` only; filled at print `s+lag`; `lag = 1` everywhere in v1 (FX: next noon; ETF: next close;
  crypto: the next hourly close after the 00:00 UTC decision). `lag = 0` is refused by the engine.
- Position sizing is FIXED across families so the grid stays small: per instrument
  `w_i = s_i · (σ* / σ̂_i) / N_active`, where `s_i ∈ [−1, 1]` is the family's signal, `σ̂_i` is the
  trailing 60-print realised vol (annualised), `σ* = 10 %` (FX, ETF) / `20 %` (crypto), and `|w_i| ≤ 1`.
  Combos sum member books at equal risk (each member scaled to 10 % trailing vol) then divided by the
  number of members.
- Net P&L per print: `Σ held·r + Σ held·carry − Σ |Δheld|·cost_side − borrow` (README has the exact
  shift). Costs per side on the fill print.
- **Future-scramble audit** is run for every (formula, lane) on three probe rows; any divergence = LEAKY,
  excluded, reported.
- **Lag-sensitivity report:** every formula is also run at `lag = 2`. If Sharpe(lag 1) > 2 × Sharpe(lag 2)
  the formula is flagged PRINT-PROXIMITY and cannot be promoted (the programme's rule: an edge that is not
  executable off its own print was never tradable).

## 3. Cost model — every number carries a provenance tag; an unsourced number refuses

| lane | base per side | stress per side | borrow on shorts | provenance to be filed in `data/costs/COSTS.json` by the data loader (URL + access date), else the tag is `ASSUMED` and the report says so |
|---|---|---|---|---|
| FX-D G10 | 1.0 bp | 3.0 bp | none (FX carry already in the carry panel) | IBKR IDEALPRO commission schedule + typical EUR/USD quoted spread; Kraken fiat-pair fee schedule + the live spread measured 2026-11-10 (EUR/USD 1 pip ≈ 0.9 bp) |
| FX-D EM | 5.0 bp | 15 bp | none | IBKR IDEALPRO EM spreads (to source) |
| MA-ETF | 0.5 bp | 3.0 bp | 1 %/yr `ASSUMED`, stress 3 %/yr | closing-auction rail: spread MEASURED ≈ 0 (git `research/trading_bot/M0_AUCTION_FILLS.md`); SEC §31 + FINRA TAF on sells (`VENDOR_SCHEDULE`) |
| CRYPTO-H | 7.0 bp | 15 bp | none (perp) | Kraken Futures taker fee (`VENDOR_SCHEDULE`, to source) + 2 bp half-spread `ASSUMED` |

Everything is reported at base AND stress. Promotion requires net > 0 at stress.

## 4. Declared formula grid (the trial count — nothing outside this list is run in v1)

Signals `s_i` are mechanism-signed in advance; where the sign is genuinely free it is counted as two trials.
`z(x)` = trailing 252-print z-score clipped to ±2 and divided by 2.

**FX-D (G10 universe) — 31 formulas**

| family | formulas | count |
|---|---|---|
| F1 TSMOM | `s = sign(P_t/P_{t−L} − 1)` and `s = z(P_t/P_{t−L} − 1)`, L ∈ {21, 63, 126, 252} | 8 |
| F2 XSMOM | rank by L-print return, long top-3 / short bottom-3, L ∈ {21, 63, 126, 252} | 4 |
| F3 CARRY | XS: long top-3 / short bottom-3 by rate differential, rebalanced {daily, monthly}; TS: `s = sign(i_fx − i_usd)` | 3 |
| F4 VALUE | XS: long bottom-3 / short top-3 by `ln P_t − mean(ln P, L)`, L ∈ {3 y, 5 y}; REAL: same on the CPI-deflated rate (FRED CPI, lagged 2 months), L ∈ {3 y, 5 y} | 4 |
| F5 BREAKOUT | Donchian: `s = +1` on a new L-print high, `−1` on a new low, else hold, L ∈ {20, 55, 100} | 3 |
| F6 ST-REVERSAL | XS: long bottom-3 / short top-3 by L-print return, L ∈ {5, 10} | 2 |
| F7 TURN-OF-MONTH | last 3 + first 2 prints of each month: long USD vs all FX; the opposite sign (free sign = 2 trials) | 2 |
| F8 COMBO | equal-risk {TSMOM-252-sign, XSMOM-252, CARRY-XS-monthly, VALUE-5y}; {XSMOM-252, CARRY-XS-monthly, VALUE-5y}; all of F1–F5 equal-risk | 3 |
| F9 ML | gradient-boosting classifier, target = sign of the next 21-print return, features = returns at the 5 lookbacks + carry + value-z + vol; trained on an expanding window inside the design window only, 21-print purge, refit yearly; XS top-3/bottom-3 on predicted probability; `max_depth ∈ {2, 4}` | 2 |

**FX-D (G10 + EM universe, 17 currencies) — 12 formulas:** F2 (4), F3 XS-daily/monthly (2), F4 (4), F8
first two combos (2).

**MA-ETF — 20 formulas:** F1 TSMOM sign/z, L ∈ {63, 126, 252} (6); F2 XSMOM long top-10/short bottom-10,
L ∈ {126, 252} and long-only top-10 (4); F3 vol-managed equal-weight long-only (1); F4 dual momentum
(long top-10 by 252 return if that return beats T-bills, else cash) (1); F5 Donchian long/flat, L ∈ {55, 100}
(2); F6 weekly XS reversal top-10/bottom-10 (1); F7 turn-of-month long equities, last 3 + first 2 prints (1);
F8 inverse-vol risk parity long-only, monthly (1, benchmark-like); F9 combo TSMOM-252 + XSMOM-252 (1);
F10 ML as FX, top-10/bottom-10, depth {2, 4} (2).

**CRYPTO-H — 17 formulas:** F1 TSMOM sign/z, L ∈ {7 d, 30 d, 90 d} (6); F2 XSMOM top-8/bottom-8,
L ∈ {7 d, 30 d, 90 d} (3); F3 Donchian long/flat, L ∈ {20 d, 55 d} (2); F4 positioning: XS z of the global
long/short *account* ratio from the archive metrics, long low-ratio / short high-ratio (1, a known alive
leg kept as reference); F5 vol-managed long-only BTC+ETH (1, benchmark-like); F6 combo TSMOM-30 +
XSMOM-30 + F4 (1); F7 24 h XS reversal (1, expected dead, kept for honesty); F8 ML depth {2, 4} (2).

**Declared trial count: 31 + 12 + 20 + 17 = 80 formulas.** Two-sided account (a wrong-signed formula
would have been read the other way): **N = 160**. Analytic expected-max bar `sqrt(2 ln 160) = 3.19 SE`.
Carried-over dead ledger (not re-run): funding carry in all forms, cross-venue funding, OI-destruction and
coil events, taker-flow streaks (parked), sub-daily crypto cross-sections, single-stock reversal/overnight
sweeps, every memecoin rule.

## 5. Statistics and the promotion rule (design window)

For every formula × lane × cost scenario the ledger records: annualised net Sharpe, HAC(Newey-West, 5 lags)
t-stat of the daily net return, annualised return and vol, max drawdown, average gross leverage, turnover
(sides/yr), breakeven cost per side, beta and alpha-t against the lane benchmark (FX: equal-weight long-FX
basket; ETF: 60/40 SPY/AGG and equal-weight-50; crypto: equal-weight long basket), the deflated Sharpe
ratio at N = 160 (reported, not gating), the lag-2 Sharpe, and the scramble-audit verdict.

**Empirical null per lane:** 500 replicates; in each, every formula's position matrix is circularly shifted
by the SAME random offset `u ∈ [252, T−252]` prints (preserving cross-formula correlation and the
autocorrelation of both positions and returns), all formulas are re-scored at base cost, and the lane's
max net Sharpe t is recorded. The lane bar is `max(3.19, empirical p95)`.

**A formula SURVIVES design if ALL hold:** (a) HAC t ≥ lane bar at base cost; (b) net Sharpe > 0 at stress
cost; (c) alpha-t vs the lane benchmark ≥ 2.0; (d) not LEAKY, not PRINT-PROXIMITY.
Survivors are listed in `runs/v1/SURVIVORS_FROZEN.json`, hashed, recorded in `DECISIONS.md`, and ONLY THEN
is any holdout row touched.

## 6. Holdout read (one shot)

For each survivor, on its sealed holdout window at base cost: **PASS** if HAC t ≥ 2.0 (one-sided, same sign)
AND net > 0 at stress; **ALIVE-UNPROVEN** if 1.0 ≤ t < 2.0 with the same sign; **DEAD** otherwise. For FX
survivors the ECB-print placebo (fill at the 14:15 CET rate instead of the noon rate) is also reported; a
survivor whose holdout Sharpe halves under the placebo is downgraded one step. Holdout rows for
non-survivors are reported afterwards as descriptive only and are not evidence.

## 7. What follows a PASS (pre-declared so success cannot be improvised)

A PASS goes to a forward paper **LOGGER** (append-only ledger, hypothetical fills at the real prints and
the base cost, no orders), for ≥ 60 sessions, under `ITERATION_PROTOCOL.md`'s immutability rule. The owner
then decides, with these facts in front of them: the executable wrapper (FX: Kraken spot fiat pairs
unlevered / IBKR IDEALPRO levered; crypto: Kraken Futures or spot; US ETFs: paper-only for an NL retail
account because of PRIIPs — UCITS equivalents would need their own mapping), the realistic return at the
chosen vol target, the drawdown, and the capital. **The factory never trades.**

## 8. Honest priors, written before the run

- FX risk premia (carry, momentum, value) have published gross Sharpes of ~0.3–0.6 each and ~0.7–0.9
  combined over 1980–2015, decaying after 2010. On 18 design years the SE of a Sharpe is 0.24, so a
  combined book at 0.8 would reach t ≈ 3.4 — right at the bar. Single signals will not clear it. The
  realistic PASS, if any, is a COMBO.
- MA-ETF's 6-year design window has SE 0.41: a formula needs Sharpe ≥ 1.3 to clear. Almost nothing honest
  does. That lane mostly supplies base rates and an executable-rail cross-check.
- CRYPTO-H's 3-year design has SE 0.58: bar Sharpe ≈ 1.85. Trend in crypto 2021–2023 was strong, so a
  TSMOM pass is possible and would still need the 2024–2026 holdout.
- Expected outcome: 0–2 survivors, most likely an FX combo; 50/50 that it confirms on holdout.
