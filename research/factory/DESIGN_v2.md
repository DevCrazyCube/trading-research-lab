# FACTORY v2 — DESIGN CONTRACT (builders' spec; the v2 pre-registration is frozen from this)

**Author:** Claude (conductor, Fable 5.2). **Written:** 2026-11-10 ~13:45–14:10 UTC.
**Status:** DESIGN — the contract every builder codes against. `PREREGISTRATION_v2.md` (windows, costs,
decision rules, final rule counts) is frozen from this document plus the verified venue costs in
`landscape/venues.json`, BEFORE any strategy result is computed on real data.
**Supersedes:** `PREREGISTRATION_v1.md` (frozen 2026-11-10 ~13:15 UTC, sha `c30ceefe…`), which was **never
run**. v1 is kept unedited for the record; nothing in it is evidence.

## 0. Why v1 was replaced before it ran (review by the conductor)

| # | v1 defect | v2 fix |
|---|---|---|
| 1 | ETF positions were scored on TOTAL return — a long book was handed the risk-free rate for free (≈ +0.4 Sharpe at 10 % vol in 2022–26) | every lane is scored in **excess return**: the carry panel is the financing leg (`−r_f` for funded instruments, rate differential for FX, `−funding` for perps) |
| 2 | FX cost "1 bp/side" was assumed; fee tiers, per-order minimums, financing markups and "no interest below a balance threshold" were never checked | costs come from `landscape/venues.json` (sourced per venue); a **realism pass** re-simulates every adopted book at €1k / €5k / €10k with lot sizes, minimum fees and financing |
| 3 | the ETF lane was "paper-only" for an NL account (PRIIPs) | MACRO lane = US ETFs as **research proxies** for wrappers the owner can use (UCITS ETFs via an API broker, CFDs, micro futures); a long-only unlevered variant is a primary hypothesis |
| 4 | EM list contained non-deliverable currencies (KRW, BRL, INR, TWD, THB) | EM = deliverable, commonly offered pairs only |
| 5 | crypto universe ranked on full-year-2021 volume and traded from 2021-01 (look-ahead) | point-in-time universe mask (trailing 30-day volume, known at t) |
| 6 | crypto fill convention executed 25 h after the decision | `exec_prices` semantics: an execution print strictly later in clock time than the decision print, `extra_lag ≥ 0` |
| 7 | 80 single formulas vs a 3.19-SE bar and then a second gate: ≈ 12 % power for a true Sharpe-0.6 strategy | **three tiers**: few parameter-free PRIMARY ensembles (no selection, so no snooping penalty beyond a handful), a large SECONDARY screen with FDR + Romano-Wolf + PBO, and selection-based books validated by nested CV — see §1 |
| 8 | no portfolio layer, no execution design, one path only | `portfolio.py`, `realism.py`, landscape research (`landscape/*.md`), paper runner later |
| 9 | clock times logged as UTC were CET; `window()` dropped the last day | fixed in `panel.py`; all timestamps in this tree are UTC from `date -u` |

## 1. The three tiers

**Tier 1 — PRIMARY ensembles (confirmatory).** Each is ONE fully specified, parameter-free book built
from literature-standard CORE rules combined at equal risk. No selection happens, so the only multiplicity
is the count of primaries (16, §6). Evidence table per primary: FULL sample, PRE-publication,
POST-publication, LAST-5-years, plus the long-history robustness panel where one exists.
Labels (pre-declared; thresholds are frozen in the prereg):
`CONFIRMED` = post-publication HAC t ≥ 2.0 after Holm adjustment across the 16;
`ADOPT-FOR-PAPER` = full-sample net HAC t ≥ 3.0 AND post-publication net Sharpe > 0 with one-sided p < 0.20
at base cost AND net Sharpe > 0 at stress cost AND no instrument > 50 % of P&L AND audit clean;
`NOT ADOPTED` otherwise. A 0.5-Sharpe premium cannot be certified at t ≥ 3 on ten post-publication years
(the standard error alone is 0.32); demanding that is how the previous programme went 0-for-N. Tier 1
therefore asks two honest questions — does the premium exist in the long record net of our costs, and has
it NOT decayed to zero since publication — and sends positives to a forward paper book.

**Tier 2 — SECONDARY screen (exploratory).** Every individual rule × lane × universe on the DESIGN
window only, all ledgered. Multiplicity control: Benjamini-Hochberg FDR q = 10 % on HAC one-sided
p-values, Romano-Wolf StepM / Hansen SPA at 5 % FWER (`arch.bootstrap`, stationary bootstrap), the
circular-shift max-stat null, and PBO (CSCV, S = 16). Survivors (StepM set ∪ BH set, minus LEAKY and
PRINT-PROXIMITY) are frozen and hashed, then read ONCE on the sealed holdout. This is the hunt for
anything beyond the classics.

**Tier 3 — selection-based books.** "Top-K by design Sharpe" style portfolios are scored only by nested
walk-forward inside design (their selection is re-done in every fold) and then once on holdout.

Sequencing rule: the Tier-2 survivor freeze is computed and hashed BEFORE any Tier-1 post-publication row
or any holdout row is displayed.

## 2. Lanes, prints, windows

| lane id | instruments | decision print | execution | sample |
|---|---|---|---|---|
| `FX` | ECB reference rates crossed to USD per 1 unit FX. G10: EUR GBP JPY CHF CAD AUD NZD SEK NOK. EM (deliverable): MXN ZAR SGD PLN HUF CZK ILS. TRY loaded but sensitivity-only | ECB 14:15 CET fix | `lag = 1` (next fix). Robustness: same-day FRED noon-NY print as `exec_prices` (H.10 subset) on the ECB∩FRED calendar | 1999-01-04 → present |
| `FX-FRED` | FRED H.10 noon rates, USD per FX: GBP JPY CHF CAD AUD NZD SEK NOK (+EUR from 1999) | noon NY | `lag = 1` | 1971 → present (robustness / pre-euro evidence) |
| `MACRO` | 41 US ETFs as proxies: SPY QQQ IWM EFA EEM VGK EWJ EWU EWG FXI INDA EWZ EWA EWC EWY EWT · XLE XLF XLK XLV XLU XLI XLP XLY XLB · SHY IEF TLT TIP LQD HYG EMB AGG · GLD SLV USO UNG DBC DBA CPER · VNQ | Alpaca SIP adjusted close | `lag = 1` (next close) | 2016-01-04 → present |
| `CRYPTO-PERP` | Binance USD-M perps, point-in-time top-30 by trailing-30-day quote volume, listed ≥ 60 days | daily 00:00 UTC close | `exec_prices` = 01:00 UTC close (`extra_lag = 0`); robustness 02:00 | 2019-09 → present |
| `CRYPTO-SPOT` | Binance spot USDT pairs, point-in-time top-20; long-only use | daily 00:00 UTC close | 01:00 UTC close | 2017-08 → present |

**Excess returns everywhere.** `carry` (per-print accrual for +1.0 exposure, calendar-day count between
prints): `FX`/`FX-FRED` `(i_fx − i_usd)·days/360` from BIS daily policy rates, lagged one business day;
`MACRO` and `CRYPTO-SPOT` `−i_usd·days/360` (financing of a funded position; effective fed funds, lagged one
day); `CRYPTO-PERP` `−Σ funding` over the interval. `tbill` = `i_usd·days/360`. A book's TOTAL return is
its excess return plus the cash yield its venue actually pays — reported separately by `realism.py`.

**Windows** (dates inclusive, UTC days). Tier-2 design / sealed holdout: `FX` 2000-01-03→2016-12-30 /
2017-01-02→last; `MACRO` 2017-01-03→2021-12-31 / 2022-01-03→last; `CRYPTO-PERP` 2020-07-01→2023-12-31 /
2024-01-01→last; `CRYPTO-SPOT` 2018-08-01→2023-12-31 / 2024-01-01→last. Tier-1 evidence windows: `FX`
FULL 2000-01-03→last, PRE-PUB →2012-12-31, POST-PUB 2013-01-01→last; `MACRO` FULL = POST-PUB
2017-01-03→last; `CRYPTO-*` FULL from the design start, POST-PUB 2021-01-01→last; LAST-5 = final 5 years.
Warm-up rows before each window are passed to the rules (lookbacks) but never scored.

## 3. Module contracts (who owns what)

```
scripts/factory/
  panel.py        (conductor)  PanelBundle: prices, carry, aux{}, tbill, meta; window(), subset(), eligible(), returns()
  engine.py       (B1) backtest core
  stats.py        (B1) per-series statistics
  mtest.py        (B1) multiple testing: BH/BY/Holm, StepM, SPA, PBO, circular-shift null, bootstrap CIs
  audit.py        (B1) future-scramble audit, lag sensitivity
  portfolio.py    (B1) equal-risk combos, book vol target, buffering, long-only cap, rebalance schedules, margin check
  realism.py      (B1) small-account simulator (VenueSpec)
  xcheck.py       (B1) an INDEPENDENT naive loop engine used only to cross-check engine.py
  strategies/     (B2) common.py, rules_*.py, registry.py
  data/           (B3) loaders, build_panels.py, load_lane()
  run_*.py        (conductor) sweep / freeze / holdout / reports
  tests/          each builder owns the tests of its modules
```

### 3.1 Engine (B1)

```python
backtest(panel, w, *, lag=1, cost_bp_side, hold_cost_long_bp_year=0.0, hold_cost_short_bp_year=0.0,
         exec_prices=None, extra_lag=0, missing_return="refuse") -> BacktestResult
```
- `w`: target exposure decided at row t from rows ≤ t (signed fraction of equity), panel index/columns.
- **Without `exec_prices`:** `r_t = P_t/P_{t−1} − 1`, `held = w.shift(1 + lag)`, `lag ≥ 1` enforced
  (`lag = 0` raises `Refused`).
- **With `exec_prices` F** (aligned to the panel index; the data layer GUARANTEES and records in its
  manifest that clock(F_s) > clock(P_s) for every row): `r_t = F_t/F_{t−1} − 1`,
  `held = w.shift(1 + extra_lag)`, `extra_lag ≥ 0`; `lag` is ignored and must be left at its default. The
  engine refuses `exec_prices` unless `panel.meta["exec_prices_strictly_after_decision"] is True`.
- `net = Σ held·r + Σ held·carry − Σ|Δheld|·cost_side − Σ max(held,0)·hc_long − Σ max(−held,0)·hc_short`
  with `hc = bp_year/1e4/periods_per_year`; costs and hold costs accept a scalar, dict or per-instrument
  Series; a missing/negative/NaN cost refuses.
- `BacktestResult`: `net, gross, price_pnl, carry, cost, hold_cost, held, turnover, gross_leverage, meta`.
  **No statistics inside the engine** — `stats.summarize` is called by the runner on an explicit window.
- `missing_return`: `"refuse"` (FX, MACRO) or `"zero"` (crypto: a held instrument whose price ends is closed
  at its last price; count recorded in `meta`).
- `fast_net_returns(held, r, carry, cost_frac, hc_long, hc_short)` numpy path for the nulls, proven equal
  to `backtest` in tests.

The previous model's drafts of `engine.py`, `stats.py`, `nulls.py`, `audit.py` exist on disk: audit them
line by line, keep what is correct, change what this contract changes (notably `fill_prices` →
`exec_prices` semantics, borrow → hold costs both sides, stats decoupled, `nulls.py` → `mtest.py`).

### 3.2 Stats (B1)

`summarize(net, *, periods_per_year, window=None, gross=None, turnover=None, gross_leverage=None,
benchmark=None, hac_lags=5) -> dict` with keys: `n_obs, start, end, ann_return` (arithmetic mean × ppy),
`cagr, ann_vol, sharpe, hac_t, p_one_sided, sortino, max_drawdown, calmar, skew, excess_kurt, hit_rate,
worst_print, worst_21, avg_gross_leverage, turnover_sides_per_year, breakeven_cost_bp_side, beta,
alpha_ann, alpha_t, psr0`. Also `evidence_table(net, windows, ppy)`, `expected_max_sharpe`, `psr`,
`deflated_sharpe`, `min_track_record_length`, `sharpe_ci_bootstrap` (stationary bootstrap),
`contribution_by_instrument(result)`.

### 3.3 Multiple testing (B1, `mtest.py`)

`bh_fdr(p, q)`, `by_fdr(p, q)`, `holm(p, alpha)`; `stepm(returns: DataFrame[T×K], benchmark=None, alpha,
block, reps, seed)` and `spa(...)` wrapping `arch.bootstrap` (document the loss/return sign convention and
test it on a planted-winner toy); `pbo_cscv(returns, S=16)` (Bailey-Borwein-López de Prado-Zhu) returning
PBO, the logit distribution and the IS→OOS degradation slope; `circular_shift_null(...)` (existing draft,
windowed scoring); `white_reality_check` if cheap.

### 3.4 Audit (B1)

`future_scramble_audit(fn, panel, params, probe_rows, rng) -> AuditResult(.passed, .detail)`;
`lag_sensitivity(net_a, net_b, ppy) -> {flag, sharpe_a, sharpe_b}` (PRINT-PROXIMITY when
Sharpe_a > 2·Sharpe_b and Sharpe_a > 0).

### 3.5 Portfolio (B1) — all functions strictly causal

`book_returns(w, panel)`; `equal_risk_combo(books, panel, vol_window=60, target=0.10)`;
`ensemble(rule_books: dict[id→w], family_of: dict[id→str], panel)` = equal-risk within family, then equal-risk
across families; `vol_target(w, panel, target, vol_window=60, max_gross)`; `apply_buffer(w, band=0.10)`
(no-trade band; trade to the nearest band edge); `long_only_cap(w, max_gross=1.0)`;
`rebalance_on(w, "monthly"|"weekly")` (hold between first prints of the period);
`margin_utilisation(w, margin_rate_by_class, asset_class_of)`.

### 3.6 Realism (B1)

`VenueSpec` (per instrument class): `fee_bp, min_fee, half_spread_bp, lot_step, min_notional,
contract_notional, financing_long_bp_year, financing_short_bp_year, leverage_cap, cash_interest_bp_year,
cash_interest_threshold`. `simulate_account(panel, w, *, equity0, venue, monthly_contribution=0.0, ...)`
loops over prints: targets → units with lot rounding and minimum notional, per-order fee
`max(min_fee, fee_bp·notional)` + half-spread, financing on notional, carry/funding, margin check, equity
path. Returns the equity curve, a cost breakdown and the tracking error against the ideal backtest.
`VenueSpec.from_json(landscape/venues.json, venue_id)`.

### 3.7 Strategy library (B2)

```python
@dataclass(frozen=True)
class Rule:
    id: str            # "TREND.EWMAC.16_64"
    family: str        # TREND | CARRY | VALUE | XSMOM | REVERSAL | VOL | SEASON | SKEW | XASSET | FLOW | ML
    kind: str          # "TS" | "XS"
    tier: str          # "CORE" | "EXPLORATORY"
    fn: Callable       # fn(panel, **params) -> DataFrame signal in [-1, 1], NaN = no view; rows ≤ t only
    params: dict
    lanes: tuple       # lane ids where it applies
    requires: tuple    # e.g. ("carry",), ("aux:cpi",), ("aux:glsr",)
    description: str
```
`common.size_positions(signal, panel, sigma_target)`: `w_i = s_i·(σ*/σ̂_i)/N_active`; σ̂ = annualised
rolling-60-print std of excess returns (min 40 prints), floored at 25 % of its own expanding median;
`N_active` = eligible instruments with a non-zero, non-NaN signal; ineligible (`panel.eligible()`) → 0;
`|w_i| ≤ 1`; σ* = 10 % (`FX`, `MACRO`), 20 % (`CRYPTO-*`). XS rules rank among eligible instruments only.
`registry.rules(lane, panel=None)`, `registry.primaries()`, `registry.declared_counts()`.
Every rule passes a truncation no-lookahead test on synthetic panels in B2's own suite.

### 3.8 Data (B3)

`load_lane(lane_id) -> PanelBundle` from parquet, no network. `meta` must carry: `periods_per_year`,
`print_convention`, `universe_groups` (e.g. `{"G10": [...], "EM": [...]}` / asset classes),
`asset_class_of` (MACRO), `exec_prices_strictly_after_decision` where an exec series is supplied,
`source_manifest`. Aux names used by rules: `rates`, `cpi`, `exec_prices`, `exec_prices_alt`,
`universe_mask`, `volume_quote`, `glsr`, `oil` (FX lane: WTI spot, lagged one day).

## 4. Rule grid (B2 implements exactly this; counts are re-stated in the prereg)

`z_L(x)` = trailing-L z-score clipped ±2 then /2. "tercile" = top/bottom third of eligible instruments.
EWMAC forecast scalars (Carver): 2/8 10.6, 4/16 7.5, 8/32 5.3, 16/64 3.75, 32/128 2.65, 64/256 1.87; cap 20.

| family | rules | tier | lanes |
|---|---|---|---|
| TREND | EWMAC (2,8)(4,16)(8,32)(16,64)(32,128)(64,256): `clip(scalar·(EWMA_f − EWMA_s)/σ_price, ±20)/20`, σ_price = EWMA(36) std of price changes — 6 | CORE | all |
| TREND | TSMOM sign, L ∈ {21,63,126,252} — 4; TSMOM z: `clip(ret_L/(σ_daily·√L), ±2)/2`, same L — 4 | CORE | all |
| TREND | continuous breakout, L ∈ {20,40,80,160,320}: `2·(P − mid_L)/(max_L − min_L)` smoothed EWMA(L/4) — 5 | CORE | all |
| TREND | `sign(P − SMA_200)` — 1 | CORE | all |
| TREND | Donchian state machine L ∈ {20,55,100} — 3; linear-regression slope t-stat `clip(t/3, ±1)`, L ∈ {63,126,252} — 3; `sign(SMA_50 − SMA_200)` — 1 | EXPLORATORY | all |
| CARRY | TS: `clip(carry_ann/σ_ann, ±1)` smoothed EWMA span ∈ {1,20,60,120} — 4 | CORE | FX, FX-FRED |
| CARRY | XS tercile by annualised carry, smoothing ∈ {1,20} — 2; XS linear-rank weights, smoothing ∈ {1,20} — 2 | CORE | FX, FX-FRED |
| CARRY | XS on the change of carry over L ∈ {63,126} — 2 | EXPLORATORY | FX |
| VALUE | XS tercile on `−(ln P − mean_L ln P)`, L ∈ {756,1260} — 2; same on the CPI-deflated rate — 2; TS `−z_L(ln P)`, L ∈ {756,1260} — 2; XS on the negative 5-year real return — 1 | CORE | FX (nominal ones also FX-FRED) |
| VALUE | XS on the negative 5-year return — 1 | EXPLORATORY | MACRO |
| XSMOM | XS tercile, L ∈ {21,63,126,252} — 4; 252 skipping the last 21 — 1; linear-rank weights L ∈ {126,252} — 2 | CORE | all |
| XSMOM | residual momentum (beta-adjusted to the lane's equal-weight basket), L = 252 — 1; proximity to the 252-print high — 1 | EXPLORATORY | all |
| REVERSAL | XS tercile on the L-print return, L ∈ {1,5,10} — 3; TS `−z` of the L-print return, L ∈ {5,10,20} — 3; RSI(2) 10/90 and RSI(14) 30/70 contrarian — 2; Bollinger(20, 2σ) reversion — 1 | EXPLORATORY | all |
| VOL | long-only basket scaled by σ_252/σ_21 — 1; XS low-vol tercile — 1; vol breakout (σ_5/σ_60 > 1.5 → sign of the 5-print return) — 1 | EXPLORATORY | all |
| SEASON | turn-of-month (last 3 + first 2 prints): MACRO long equities; CRYPTO long; FX long USD and its negation (2) — by lane; "sell in May" long Nov–Apr on equities — 1 | EXPLORATORY | by lane |
| SKEW | XS low-minus-high 126-print skewness — 1; XS short the highest 21-print max return — 1 | EXPLORATORY | all |
| XASSET | oil currencies (CAD NOK MXN): sign of the trailing 63-print WTI return — 1 | EXPLORATORY | FX |
| FLOW | XS `−z` of the global long/short account ratio — 1 (reference; an already-alive leg) | EXPLORATORY | CRYPTO-PERP |
| ML | gradient-boosting classifier depth {2,4} and ridge regression on {returns at 5,21,63,126,252; carry; value z; vol}, expanding fit with a 21-print purge, refit yearly, XS tercile — 3 | EXPLORATORY | all |

Funding carry in every form is on the dead ledger and is NOT re-run on `CRYPTO-PERP`.

## 5. FX universes

`G10` (9) and `G10EM` (16 = G10 + MXN ZAR SGD PLN HUF CZK ILS). Every FX rule runs on both.

## 6. Primary ensembles (16)

CORE members only, equal-risk within family, families equal-risk, book-level vol target 10 % (`FX`, `MACRO`)
/ 20 % (`CRYPTO-*`), buffer 10 %.

| id | members |
|---|---|
| `P.FX.G10.TREND` / `.CARRY` / `.VALUE` / `.XSMOM` / `.ALL` | the CORE rules of that family on G10; ALL = the four families |
| `P.FX.G10EM.CARRY`, `P.FX.G10EM.ALL` | same on G10EM |
| `P.MACRO.TREND`, `P.MACRO.XSMOM`, `P.MACRO.ALL` | CORE trend / xsmom / both on the 41 ETFs |
| `P.MACRO.LO_TREND` | CORE trend, long-only (negative targets → 0), gross ≤ 1.0, monthly rebalance — the unlevered UCITS-ETF product |
| `P.CRYPTO.TREND`, `P.CRYPTO.XSMOM`, `P.CRYPTO.ALL` | on `CRYPTO-PERP` |
| `P.CRYPTO.LO_TREND` | CORE trend on `CRYPTO-SPOT`, long-only, gross ≤ 1.0, weekly rebalance — the unlevered spot product |
| `P.GLOBAL` | equal-risk of `P.FX.G10.ALL`, `P.MACRO.ALL`, `P.CRYPTO.ALL` on the dates each exists |

Benchmarks reported beside every book: cash (0 excess), the lane's equal-weight long basket, 60/40
(SPY/AGG), BTC buy-and-hold, and the vol-matched "just hold less" version of each.

## 7. Tests every builder ships

Known-answer tests with hand-computed numbers; property tests on random panels; the truncation /
future-scramble test for every rule; `engine.py` equal to `xcheck.py` (independent loop engine) to 1e-10
on ≥ 100 random panels including carry, hold costs and exec prices; a planted-winner / pure-noise pair for
every multiple-testing routine; lot-rounding and minimum-fee known answers for `realism.py`. One pytest
process at a time (15 GB laptop). No network in tests.
