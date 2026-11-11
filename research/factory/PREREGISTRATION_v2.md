# FACTORY v2 — PRE-REGISTRATION

**Author:** Claude (conductor, Fable 5.2). **Status:** see `PREREG_PIN_v2.json` — this text is FROZEN at the
sha256 recorded there and in `DECISIONS.md`; the pin file also carries the hashes of the data manifests, the
rule grid, the code and `venues.json` that the run must match. Supersedes `PREREGISTRATION_v1.md` (never run).
Any change after the freeze is a new document (`v3`) with its own accounting.

Companions: `DESIGN_v2.md` (module contract), `landscape/PLATFORMS.md` + `venues.json` (sourced venue costs),
`landscape/STRATEGY_CLASSES.md` (evidence map), `landscape/REPO_ASSETS.md` (prior in-repo tests),
`landscape/DATA_SOURCES.md`, `landscape/LIBRARIES.md`.

---

## 0. What was known when (read this before trusting any window)

1. The lanes, the rule families and the **16 primary ensembles** were fixed in `DESIGN_v2.md`
   (sha `0b9f21ac…`, recorded in `DECISIONS.md` on 2026-11-10 before any landscape report was read).
2. After that the conductor read five landscape reports. They contain **public market-level performance for
   2017–2026** (trend-index, equity-index and BTC returns) and **prior results from this repo** (§8). No
   formula-level statistic on any factory panel existed or was seen.
3. Changes made after reading them, each applied uniformly and none chosen on performance:
   costs and holding costs taken from `venues.json`; the SEASON family and the FLOW rule disabled (already on
   the dead ledger); two redundant rules disabled; sizing divides by eligible instruments; cross-sectional
   ranks use vol-scaled returns; ML restricted to FX-G10; CPER and gold-backed tokens dropped (data quality /
   lane definition); terminal delisting returns booked; the USD rate lagged one more business day as a
   signal input; trading cost charged on drift-aware turnover; holding costs accrued in calendar time;
   primaries scored by a drift-aware account simulator; a performance-agnostic speed limit on ensemble
   members; label thresholds (§4). **No primary was added, removed or given a different signal definition.**
4. Plain limit: the conductor is a language model whose training data runs to mid-2026 and who has now read
   2017–2026 index returns. No window here is unseen in the regime sense. What is sealed is formula-level
   performance on these panels, and the mechanical rules below are what prevent that knowledge from
   steering the result.

## 1. The questions

- **Tier 1 — 16 primary ensembles (confirmatory, no selection).** Does each fully specified book earn a
  positive excess return net of the costs of the wrapper a Dutch retail account can actually use, in the
  long record and since publication — and does it add anything over simply holding less of the passive
  basket? Labels in §4.
- **Tier 2 — the screen (exploratory).** Does any individual rule beyond the classics survive honest
  multiple-testing control on a design window and then a one-shot sealed holdout? §5.
- **Tier 3** (selection-based books) is deferred: no selection-based book is scored under v2.

A 0.5-Sharpe premium cannot reach t ≥ 3 on ten years of data (standard error ≈ 0.32), so Tier 1 does not
ask for that. It asks whether the premium is visible net of real costs, has not decayed to zero, and beats
the passive alternative on drawdown — and it sends positives to a paper book, not to money.

## 2. Data (identity pinned by manifest hashes in `PREREG_PIN_v2.json`)

All lanes are scored in **excess return**: the `carry` panel is the financing leg (FX: lagged overnight /
policy rate differential, calendar-day accrual; MACRO and CRYPTO-SPOT: minus the effective fed funds rate;
CRYPTO-PERP: minus realised Binance funding over the execution interval).

| lane | instruments | decision print → execution | sample |
|---|---|---|---|
| `FX` | ECB reference rates crossed to USD per unit. G10: EUR GBP JPY CHF CAD AUD NZD SEK NOK. EM: MXN ZAR PLN HUF CZK ILS. (SGD has no rate series and is ineligible; TRY sensitivity-only.) | ECB fix (row stamped 14:15 Europe/Berlin) → next fix (`lag = 1`) | 1999-01-04 → 2026-11-09 |
| `FX-EXEC` | the 12 H.10 currencies on the ECB∩FRED calendar | ECB fix → FRED noon-NY rate the same day (`exec_prices`) | 1999-01-04 → 2026-11-06 |
| `FX-FRED` | FRED H.10 noon rates, G10 (EUR from 1999) | noon NY → next noon | 1971-01-04 → 2026-11-06 |
| `MACRO` | 40 US ETFs as research proxies (16 equity regions, 9 US sectors, 8 bonds, 6 commodities, 1 real estate; CPER dropped as illiquid) | Alpaca SIP adjusted close → next close | 2016-01-04 → 2026-11-09 |
| `CRYPTO-PERP` | Binance USD-M perps, point-in-time top 30 by trailing-30-day quote volume, ≥ 60 days listed, live at the print; TradFi perps, synthetic indices, stablecoins and gold tokens excluded; delisted names included with their terminal return | daily 00:00 UTC close → 01:00 UTC print (`exec_prices`, `extra_lag = 0`) | 2019-09-09 → 2026-11-10 |
| `CRYPTO-SPOT` | Binance spot USDT pairs, point-in-time top 20, same exclusions; long-only | same | 2017-08-18 → 2026-11-10 |

Known data limits, accepted: BIS policy rates stand in for money-market rates outside USD/EUR/GBP (JPY gaps
filled from the OECD call rate); CPI is the current vintage with a publication lag, not real-time vintages;
Alpaca closes are rounded to cents; Binance funding is not the funding a Kraken or OKX account pays; US ETFs
proxy UCITS funds and CFDs that track the same indices; all returns are in USD terms (a EUR investor's
translation is reported beside the long-only books, not scored).

**Windows** (inclusive UTC dates; warm-up rows are fed to rules but never scored).

| lane | Tier-2 design | Tier-2 sealed holdout | Tier-1 FULL | Tier-1 POST-PUB |
|---|---|---|---|---|
| `FX` | 2000-01-03 → 2016-12-30 | 2017-01-02 → last | 2000-01-03 → last | 2013-01-01 → last |
| `MACRO` | 2017-01-03 → 2021-12-31 | 2022-01-03 → last | 2017-01-03 → last | = FULL |
| `CRYPTO-PERP` | 2020-07-01 → 2023-12-31 | 2024-01-01 → last | 2020-07-01 → last | 2021-01-01 → last |
| `CRYPTO-SPOT` | 2018-08-01 → 2023-12-31 | 2024-01-01 → last | 2018-08-01 → last | 2021-01-01 → last |

Also reported, never gating: `FX-FRED` 1976-01-02 → 1998-12-31 (pre-euro record; that panel has 25 interior
missing prints, so a held position there is carried at its last price), LAST-5 (final five years), calendar
years.

## 3. Scoring conventions

**Sizing.** Rule signal `s ∈ [−1, 1]` → `w_i = s_i · (σ*/σ̂_i) / N_eligible`, σ̂ = annualised rolling-60-print
vol of excess returns floored at 25 % of its expanding median, σ* = 10 % (`FX`, `MACRO`) / 20 % (`CRYPTO-*`),
`|w_i| ≤ 1`. `CRYPTO-SPOT` books are clipped to long-only.

**Engines.** Tier 2: the weight engine `engine.backtest` with **drift-aware turnover** (the trade charged on
each print is the move from the drifted position to the new target, so daily re-sizing is not free);
`lag = 1`, or `exec_prices` with `extra_lag = 0` on crypto; `missing_return = "zero"` on crypto, `"refuse"`
on `FX` and `MACRO` (both verified to have no interior price gap). Tier 1: the drift-aware account simulator
`realism.simulate_account` on an ideal venue with the lane's proportional costs (units drift between
trades; trades only when the no-trade band or the rebalance schedule says so); the weight engine is
reported beside it as a cross-check. Holding costs accrue by calendar days.

**Costs** (per side on traded notional; holding cost per year on gross notional, calendar-day accrual).
Provenance: `landscape/venues.json`, accessed 2026-11-10; `ASSUMED` where no venue figure exists.

| lane / group | wrapper the owner can use | base | stress | reference |
|---|---|---|---|---|
| FX majors (EUR GBP JPY CHF CAD AUD NZD) | cTrader CFD broker (Pepperstone Razor: 0.27 bp commission + ≈ 0.05–0.08 bp half-spread, broker-published averages; swap mark-up derived 58–109 bp/yr at peers) | 0.6 bp + 100 bp/yr long and short | 1.5 bp + 200 bp/yr (IBKR FX CFD) | futures-like: 0.75 bp, no mark-up (needs ≈ €50k+) |
| FX Scandinavia (SEK NOK) | same; spreads `ASSUMED` | 2.5 bp + 100 bp/yr | 5 bp + 200 bp/yr | 2.5 bp |
| FX EM (MXN ZAR PLN HUF CZK ILS) | same; spreads and swaps `ASSUMED` (IBKR MXN/ZAR mark-up 250 bp) | 6 bp + 250 bp/yr | 15 bp + 400 bp/yr | 6 bp |
| MACRO long/short books | index/ETF CFDs: benchmark ± 2.5 %/yr financing (IBKR, Pepperstone) | 1.0 bp + 250 bp/yr long and short | 2.5 bp + 300 bp/yr | futures-like: 1.0 bp, no mark-up (needs ≈ $100k) |
| MACRO long-only book | UCITS ETFs at Trading 212 Invest: zero commission; exchange spread unmeasured (`ASSUMED`) | 5 bp, no holding cost | 15 bp | — |
| CRYPTO-PERP | Kraken Derivatives EEA / OKX X-Perps: 5 bp taker; half-spread 0.07–0.6 bp measured on majors, alts `ASSUMED` | 7 bp | 15 bp | maker 4 bp |
| CRYPTO-SPOT long-only | Bitvavo: 25 bp taker, half-spread < 0.5 bp on majors | 27 bp | 50 bp | maker 17 bp |

**Tier-2 screen costs.** `FX` and `MACRO` formulas are screened at the reference (futures-like) cost with a
trading-cost stress (FX 1.5 / 5 / 15 bp; MACRO 2.5 bp) so that a wrapper's financing cannot hide a signal;
each formula is also scored at the retail-wrapper cost and tagged. Crypto lanes are screened at their
retail base and stress costs, which are the only costs there are.

**Gross caps** in book vol targeting: FX 10×; MACRO long/short 4×; CRYPTO-PERP 2× (ESMA's February 2026
statement puts perps under the 2:1 crypto CFD cap); long-only books 1×.

**Primary construction** (members = enabled CORE rules of the named families on the named universe):
each member book sized as above → **speed limit**: a member is dropped from the ensemble when its trading-cost
drag at the primary's base cost exceeds 0.13 Sharpe units, i.e. `(turnover per year × cost per side) / annual
vol > 0.13`, measured on the lane's Tier-2 design window from positions and returns only (a member with no
activity in that window is dropped too) → equal-risk within
family → equal-risk across families → book vol target σ* with the gross cap → no-trade band 10 % (long-only
books instead: negatives clipped to zero, vol target with gross ≤ 1, trade only on the first print of each
month for `MACRO`, of each ISO week for `CRYPTO-SPOT`). The dropped-member list is written before any
performance figure is displayed. If every member of a primary is dropped, its label is
`NOT IMPLEMENTABLE AT THIS COST`.

**The 16 primaries.** `P.FX.G10.{TREND, CARRY, VALUE, XSMOM, ALL}`; `P.FX.G10EM.{CARRY, ALL}`;
`P.MACRO.{TREND, XSMOM, ALL}`; `P.MACRO.LO_TREND`; `P.CRYPTO.{TREND, XSMOM, ALL}` (on `CRYPTO-PERP`);
`P.CRYPTO.LO_TREND` (on `CRYPTO-SPOT`); `P.GLOBAL` = equal-risk mix of the base-cost net return streams of
`P.FX.G10.ALL`, `P.MACRO.ALL`, `P.CRYPTO.ALL` on the dates each exists, re-targeted to 10 % vol (causal). `P.GLOBAL` is a
composite: it gets the evidence rows and the `CONFIRMED` test but no candidate label of its own (its three
books carry theirs), and the cost of re-scaling between books is not charged.

**Leakage controls.** Every rule: future-scramble audit (three probe rows in the screen, one for ML; each
kept member is re-probed once on the full panel at Tier 1); lag-sensitivity run
(`lag = 2`, or the 02:00 UTC print on crypto) — PRINT-PROXIMITY when Sharpe(base timing) > 2 × Sharpe(later
timing) > 0. `FX-EXEC` re-scores `P.FX.G10.ALL` with same-day NY-noon execution; a Sharpe gap above 0.2
against the `lag = 1` result is reported as a timing-artifact warning (this repo once carried a +4.93-Sharpe
FX-carry artifact from stale stamps that only an extra day of lag exposed).

## 4. Tier-1 labels (pre-declared thresholds; base cost unless stated)

`PAPER-CANDIDATE` iff ALL of:
(a) FULL-window net Sharpe ≥ 0.30;
(b) FULL-window net Sharpe at stress cost ≥ 0.15;
(c) stationary-bootstrap probability that the FULL-window Sharpe exceeds 0 is ≥ 0.80;
(d) POST-PUB net Sharpe ≥ 0;
(e) no single instrument's share of absolute P&L (`|pnl_i| / Σ|pnl_j|`) exceeds 50 %, and at least half of
    the calendar years are positive;
(f) every member rule is audit-clean and the book is not PRINT-PROXIMITY;
(g) **value-add over holding less:** for long/short books, the annualised alpha against the lane's
    equal-weight long basket (scaled to the book's own volatility, same wrapper costs) is ≥ 0; for long-only
    books, net Sharpe ≥ (Sharpe of the vol-matched constant-exposure basket −
    0.10) AND max drawdown ≤ 0.80 × that basket's. A long-only book that fails (g) while passing (a)–(f) is
    labelled `NO VALUE-ADD OVER HOLDING` and the recommendation is the passive basket.

`CONFIRMED` (reported beside the label, expected to be rare): the POST-PUB one-sided p-value (Newey–West, 21
lags) is ≤ 0.05 after Holm adjustment across the primaries — for the best of 16 that is t ≈ 2.7. Tier-1
statistics use 21 HAC lags and a 2,000-replication stationary bootstrap.

`NOT A CANDIDATE` otherwise. Every label is shown with the reference-cost row, so a book that fails only
because of retail financing is visibly "works with futures-like financing, not at this account size".

## 5. Tier 2 — the screen

**Formulas** = every enabled rule on every Tier-2 lane and universe it applies to (`FX` on G10 and G10EM;
`MACRO`; `CRYPTO-PERP`; `CRYPTO-SPOT` with TREND and XSMOM only; ML on FX-G10 only): **255 formulas** —
FX-G10 67, FX-G10EM 64, MACRO 45, CRYPTO-PERP 46, CRYPTO-SPOT 33 — from 67 enabled rules (42 CORE, 25
EXPLORATORY); 11 rules are disabled and never run (SEASON ×5 and FLOW: dead ledger; LINREG ×3 and one
reversal: redundant by construction; one value rule: unassessable). The grid hash is in the pin file. Scored on the **design window only**; every formula is ledgered.

**Per formula:** net Sharpe and HAC(5) t at the screen cost, one-sided p-value, stress-cost Sharpe,
retail-wrapper Sharpe, later-timing Sharpe, turnover, breakeven cost, alpha-t against the lane basket, audit
verdict.

**Multiplicity:** (i) Benjamini–Hochberg at q = 10 % over ALL formulas pooled; (ii) Romano–Wolf StepM
(studentised, stationary bootstrap, 2,000 replications) within each of the five lane-universe blocks at
α = 1 % (5 % Bonferroni-split across blocks); (iii) reported, not gating: Hansen SPA p-values, the
circular-shift max-t null, PBO (CSCV, S = 16; noisy by nature).

**Survivors** = (BH set ∪ StepM sets) with stress-cost net Sharpe > 0, audit clean, not PRINT-PROXIMITY. The
list is frozen and hashed (`runs/v2/SURVIVORS_FROZEN.json`, recorded in `DECISIONS.md`) **before any Tier-1
post-publication figure or any holdout row is displayed.**

**Holdout (one shot):** `PASS` = holdout HAC t ≥ 2.0 one-sided at the screen cost AND stress net > 0 (each
result also shows the retail-wrapper Sharpe);
`ALIVE-UNPROVEN` = 1.0 ≤ t < 2.0; `DEAD` otherwise. Holdout rows of non-survivors are descriptive only.

## 6. Realism and the leverage ladder (run for the executable books whatever their label)

Books: `P.MACRO.LO_TREND` @ `trading212_invest`; `P.CRYPTO.TREND` and `P.CRYPTO.ALL` @
`kraken_derivatives_eea` (instruments restricted to those Kraken lists, with its lot precision and minimum
order); `P.CRYPTO.LO_TREND` @ `bitvavo`; `P.FX.G10.ALL` @ `pepperstone_eu_ctrader` (0.01-lot steps).
Account sizes €1,000 / €5,000 / €10,000, with and without a €100 monthly contribution. Output: equity path,
cost breakdown, tracking error and the share of the ideal net return that survives. Venue fields that
`venues.json` lacks (lot steps, minimum orders) are read from the venues' public instrument endpoints at run
time and recorded with their URL; a field that is still unknown makes that simulation refuse rather than
default, and an explicit `ASSUMED` override is labelled as such in the output.

**Leverage ladder** (owner request, 2026-11-10: "leverage ×200"): each executable book's base-cost daily
net returns scaled by L ∈ {0.5, 1, 2, 3, 5, 10, 20, 50, 200}, costs scaling with L; 5,000 stationary-bootstrap
one-year paths per L; reported: median and 5th/95th percentile terminal wealth, probability of losing more
than half, probability of ruin (wealth ≤ 10 % of start or a single-print loss ≥ 100 %), and the L that
maximises median log wealth. Daily data understate intraday liquidation, so the ruin figures are lower
bounds. A separate table uses Binance hourly BTC candles: how often a 200× position is liquidated within
1, 4 and 24 hours of entry, and what its fees cost.

## 7. Sequence, and what a result triggers

Freeze → Tier-2 design sweep → survivor freeze → Tier-1 evidence tables and Tier-2 holdout → realism and
ladder → reports (`reports/v2/`). `PAPER-CANDIDATE` books and holdout `PASS` formulas go to a forward paper
logger (a scheduled Python job with an append-only ledger and venue-realistic fills; demo/paper APIs where
the owner has opened one). Eight weeks of paper is an operational-parity check, not a proof. Money, accounts
and leverage are the owner's decisions. The factory never places an order.

## 8. Prior evidence and expectations, written before the run

**This repo (REPO_ASSETS §1.8):** FX carry on six CME futures 2007–2026 — stale-corrected Sharpe 0.00 to 0.32,
judged noise, plus the +4.93 stale-stamp artifact; crypto TSMOM — in-sample 1.00 (2023-01 → 2025-02),
held-out 0.12 over 535 days; cross-sectional long/short account ratio — about breakeven on 2025-01 → 2026-08;
turn-of-month and calendar effects — 100 formulas, noise; ETF commodity/rates carry — 98 formulas, noise.
The old forward basket (read from an unreachable git blob): +1.3 % vs +0.3 % cash over six weeks to
2026-10-02, not informative.

**Public record (STRATEGY_CLASSES):** diversified trend following is the one active class with a century of
academic evidence and a live after-fee record (SG Trend 5.75 %/yr 2000 → Sep 2026, ≈ 0.2–0.4 Sharpe); FX
carry, momentum and value have decayed since publication (0–0.3 after retail financing).

**Expectations:** FX primaries 0.0–0.4 Sharpe before financing and at or below zero after a 100 bp/yr
mark-up at 2–3× gross; MACRO long/short negative at CFD financing and 0.2–0.5 at futures-like financing;
the long-only ETF trend book close to its vol-matched basket in Sharpe with a smaller drawdown; crypto trend
0.4–0.9 over the full window and weak in 2025–26; Tier 2: zero to three survivors, at most one holdout
`PASS`. Most likely outcome: one to three `PAPER-CANDIDATE` books — the long-only ETF trend book and the
crypto trend books — with expected excess returns of a few percent a year at the owner's account size.
