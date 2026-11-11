# LIBRARIES — verified, hands-on map of open-source tooling for the factory

**Author:** Claude research sub-agent (model `claude-fable-5-2`), for the factory conductor.
**Access date of every item:** 2026-11-10. Metadata reads and tests ran 13:46–15:07 UTC (`date -u` / file
mtimes in UTC) on the NL laptop the factory runs on: Linux 6.18 LTS, glibc 2.43, 15 GB RAM, `uv 0.11.23`,
uv-managed CPython 3.12.12.
**Status:** landscape reference. It is NOT a preregistration and changes nothing in `DESIGN_v2.md` or the
prereg. Only this file was written inside the repo; the repo venv `research/factory/.venv` was never touched.
**Scope:** maintained status, Python 3.12 support, licence, real strengths and weaknesses of backtest
engines, overfitting statistics, broker/exchange SDKs, feature/ML libraries, ops tooling and LLM-agent
trading frameworks — plus a recommended stack and a concrete plan to cross-check `scripts/factory/engine.py`
against independent implementations.

## How to read this file

| label | meaning |
|---|---|
| **V-T** | VERIFIED by test: installed into a scratch venv on this host today and exercised; the result is in §4. |
| **V-M** | VERIFIED metadata: read by script today from the PyPI JSON API (`pypi.org/pypi/<name>/json`) or the GitHub REST API (`repos/<owner>/<repo>`, `/releases`, raw README / pyproject). Raw JSON was kept in the scratch dir (session-only). |
| **V-D†** | Read today on the project's own page **through the fetch tool's summariser** (a small model transcribed it). Re-read the page before paying money on the strength of one number. |
| **CLAIM** | third-party page, search-result snippet, or analyst recall; not checked against a primary source today. |
| **UNKNOWN** | could not be determined today. |

"py3.12" column: **T** = tested on CPython 3.12.12 with the repo's own numeric stack (numpy 2.5.4, pandas
3.1.1, scipy 1.18.1, statsmodels 0.15.0); **T(pd2)** = tested on 3.12.12 but the package forces
pandas < 3 (cannot share the repo venv); **T(own)** = tested in its own venv because it conflicts with or
downgrades something else; **C** = claimed by package metadata only (not installed); **✗** = does not
install / import.

**Constraints honoured.** No account created, no login, no API key used, no order sent, no secret read.
Network: PyPI JSON API; GitHub REST API through the host's existing `gh` login (public repository
metadata only); keyless public market-data calls to Kraken Futures (2 GETs + ccxt) and Hyperliquid's
`/info` endpoint (via ccxt and the official SDK); page reads through the fetch tool. Installs were
sequential, one package at a time, with `UV_LINK_MODE=symlink` so that the scratch venvs (on tmpfs = RAM)
hold only symlinks into `~/.cache/uv` on disk.

---

## 0. Bottom line

1. **Keep the custom core; do not adopt a framework for research.** On identical inputs the engine agrees
   with three independent libraries — `bt`, `vectorbt`, `cvxportfolio` — to **≤ 1.3e-15 per print** on the
   price leg and the carry leg under timing convention A (`lag`), and with bt and vectorbt under
   convention B (`exec_prices` / `extra_lag`) (V-T, §3). It is 40× to 1,500× faster than they are (3 ms per 600×6 run vs 121 ms / 750 ms / 4.7 s), and
   none of them has the things that make the factory honest: `lag = 0` refusal, the future-scramble audit,
   the circular-shift null, cost provenance.
2. **Cross-check with `cvxportfolio` first.** It is the only library found that replays **all four legs**
   (price, linear cost, hold cost on shorts/longs, per-print carry) for fixed target weights. `bt` is
   second (levers natively, different code lineage), `vectorbt` third (fast after a 49 s JIT warm-up, but
   the open-source edition cannot lever and fails silently). The in-repo `xcheck.py` is a same-author
   reading of the same contract; the external check tests the contract itself.
3. **The external check surfaced four convention gaps between the engine and a real rebalancer** — none is
   an arithmetic bug, all are now measured (toy panel, §3.4): (i) the engine charges `|Δ target|`, a real
   book trades `target − drifted position`: turnover understated by 0.7 % when targets are re-sized
   daily, **6 % with weekly and 17 % with monthly decisions** (1.5 / 5.4 / 6.2 bp/yr at 5 bp/side); (ii)
   hold costs accrue per print (÷ 252) while cvxportfolio — and real borrow — accrue on calendar time:
   a 5.7 % difference on the toy's holiday-free calendar (about 1.5 % would remain on a true 252-print
   year — computed, not measured) and a different split across weekends; (iii) a target held constant between weekly decisions is, in the
   engine, a book rebalanced back to target every print for free: Sharpe 0.416 (engine) vs 0.444 (traded
   only on change) on the toy; (iv) the engine books a trade's cost one row after the fill and never
   books the trade due on the last print. `engine.py` v2 already states (i), (ii) and (iv) in its
   docstring; this file puts numbers on them.
4. **Multiple testing: `arch` 8.0.0 is the only maintained Python source of SPA / StepM / MCS I found**,
   and it is already in the repo venv. API and behaviour verified on planted-winner toys (V-T). Three
   traps: it takes **losses** (feeding returns silently inverts the test), `SPA.better_models()` returns
   **positions** not labels (while `StepM.superior_models` returns labels), and the default block length
   is `sqrt(T)` (67 at T = 4500), not a data-driven choice.
5. **`stats.py` (v2, sha `90879ccc…`) agrees with independent implementations**: Sharpe / max drawdown /
   CAGR ≤ 2e-15 vs `empyrical-reloaded` and `quantstats`; PSR 2.6e-9 vs `quantstats`; deflated Sharpe
   8.9e-16 vs `vectorbt` (whose `var_sharpe` is in **annualised** units — multiply the repo's per-print V
   by 252); hand-coded Newey-West t ≤ 4.4e-15 vs `statsmodels` 0.15.0 HAC at lags 0/5/10; bootstrap Sharpe
   CI [0.847, 2.061] vs `arch` [0.844, 2.059] (V-T).
6. **The repo's numeric stack is ahead of much of the ecosystem.** With numpy 2.5.4 / pandas 3.1.1 these
   install and run: vectorbt, bt, cvxportfolio, skfolio, riskfolio-lib, NautilusTrader 1.231, freqtrade,
   backtesting.py, backtrader, PyBroker, quantstats, empyrical/pyfolio-reloaded, ccxt, TA-Lib,
   pandas-ta-classic, LightGBM, XGBoost, CatBoost, Optuna, polars, duckdb, tsfresh, tsfel. These **force a
   downgrade or a separate venv**: zipline-reloaded, statsforecast, pysystemtrade (pandas < 3), jesse
   (pandas ~= 2.2.3), pandas-ta (numba == 0.61.2 → numpy 2.2.6), hummingbot (numpy 2.2.6), mlfinpy
   (numpy < 1.27), RiskLabAI (statsmodels < 0.15). `PyPortfolioOpt.HRPOpt` is **broken** on scipy 1.18.1
   (V-T / dry-run resolver output, §4).
7. **NautilusTrader is the framework to remember, not to adopt now.** 1.231.0 installs on 3.12 (189 MB
   wheel, 583 MB unpacked) and ran a 750-bar backtest in 0.33 s (V-T). But 2.0.0rc7 "removes support for
   Python 3.12" (V-M), the API is mid-migration (Cython removed), and an event-driven engine is not
   look-ahead-proof by default: with daily BID + ASK bars the shipped `EMACross` example got **0 fills
   with no error** on one-sided bars, and then filled market orders either at the **signal bar's own
   close** or at the **previous bar's close**, depending only on which bar stream had been added first
   (V-T, §4 T12c) — never at the next bar. It earns its cost only if order-book / latency realism becomes
   the binding question.
8. **Execution: `ccxt` 4.5.92 as the single crypto client, `ib_async` 2.1.0 for IBKR.** Native exchange
   SDKs cannot share one venv (V-T: hyperliquid-python-sdk needs eth-account < 0.14 while web3 8 installs
   0.14; coinbase-advanced-py pins websockets < 14 and breaks web3 / python-kraken-sdk / solana;
   ctrader-open-api downgrades requests below ibind's floor).
9. **Dead or gone:** backtrader (last release 2023-04), blankly (2023-07), fastquant (2023-01), ib_insync
   (archived), mlfinlab (not on PyPI, last push 2023-10), `timeseriescv` (2018), py-clob-client (repo
   archived; superseded by `py-clob-client-v2`), and **pandas-ta upstream** (GitHub repo returns 404,
   `www.pandas-ta.dev` has no DNS record, only two 2025 beta releases left on PyPI) (V-M / V-T).
10. **Venue facts that fell out of the library work:** `MetaTrader5` has Windows wheels only (install
    fails on this host, V-T); the Trading 212 API is beta and covers Invest / Stocks ISA only (V-D†);
    QuantConnect's free plan excludes the LEAN CLI, paper and live trading, and "Researcher" is $84/month
    (V-D†); Polymarket is under a Dutch regulator order of 2026-01-20 (decision PDF reachable, NOS
    2026-02-17) so its SDK is moot for an NL resident; OANDA's v20 API excludes "OANDA TMS BROKERS S.A.",
    its EU entity (V-D† + CLAIM); BitMEX is absent from ccxt 4.5.92 (V-T).
11. **LLM-agent trading frameworks: the evidence is negative.** The most-starred repos disclaim real
    trading; the one live public experiment with money ended with 4 of 6 models losing (−$16.8k on $60k,
    my sum of the reported figures) and a later roundup reports 6 profitable results out of 32; the
    long-horizon academic re-tests find the reported backtest advantages do not survive (§1F).

---

## 1. Master table

Verdict codes: **USE** (in the stack now) · **XCHECK** (use only to cross-check our own code) ·
**OPTIONAL** (fine, not needed yet) · **LATER** (revisit when a named condition holds) · **SKIP** (wrong
tool for this factory) · **AVOID** (dead, broken or unavailable).

### 1A. Backtesting / research engines and portfolio optimisers

| library | purpose | latest version (date) | py3.12 | licence | verdict |
|---|---|---|---|---|---|
| **vectorbt** (open source) | numba-vectorised backtests; `Portfolio.from_orders/from_signals`; returns accessor with a deflated Sharpe ratio | 1.2.0 (2026-10-19); 8 releases in 365 d; repo pushed 2026-11-08, 9.8k stars (V-M) | **T** — needs numpy ≥ 2.4.6, pandas ≥ 3.0.3, numba ≥ 0.66; py ≥ 3.11, < 3.15 | Apache-2.0 **with Commons Clause** (read from the wheel's `LICENSE.md`, V-T) | **XCHECK**. Good: fast after JIT (121 ms / run), target-percent orders with cash sharing, optional Rust engine since 1.0.0 (V-M). Bad: first call 49 s JIT; open-source edition **cannot lever** — at gross 2.6× it filled what cash allowed with no exception (per-print error 3e-2, V-T); no carry / funding / borrow; NaN target = "no order", not "flat"; pulls 60 further packages (plotly, ipywidgets, numba / llvmlite, …). |
| vectorbt PRO | closed successor ("VectorBT is the open-source community edition of VectorBT PRO") | not on PyPI (404, V-M); private GitHub repo | not testable | proprietary membership; "starts at" $25/month, $240/12 months, $500 lifetime; "personal, non-commercial use only" (V-D†) | **SKIP**. README lists what it adds: "parallelization, additional data integrations, portfolio optimization, pattern recognition, event projections, limit orders, leverage, and over 100 other features" (V-D†). Nothing the weight-based contract needs. |
| **NautilusTrader** | event-driven backtest + live engine (Rust core), venue adapters | 1.231.0 (2026-08-02); 2.0.0rc8 (2026-10-29, pre-release); 31k stars (V-M) | **T** (1.231.0). 2.0.0rc7+: "removes support for Python 3.12 and supports Python 3.13 and 3.14" (V-M) | LGPL-3.0-or-later | **LATER**. Adapters shipped in the 1.231.0 wheel (V-T): architect_ax, betfair, binance, bitmex, bybit, databento, deribit, dydx, hyperliquid, interactive_brokers, kraken, okx, polymarket, sandbox, tardis. Docs for the development line add Coinbase, Derive, Lighter, Kalshi (beta), CoinAPI (beta), FinFeed (beta) (V-D†); 2.0.0rc6 "Removed the BitMEX adapter … following the exchange closure on 23 September 2026" (V-M for the release note; the closure is its statement). Has a `FundingRateUpdate` data type (V-T). **Bar-fill behaviour observed (V-T):** a market order sent from `on_bar` is filled at that bar's timestamp at the close of the same bar, or at the stale close of the previous bar when the strategy listens to the bar stream that is processed first — a next-bar fill has to be coded by hand. Same strategy code in backtest and live is the project's design claim (CLAIM — only the backtest path was run here). Cost: steep learning curve (instruments, precisions, venue/account config, bar-vs-quote execution rules), 583 MB, API in flux until 2.0. |
| QuantConnect **LEAN** + `lean` CLI | C# engine with Python API; cloud platform; local runs in Docker | `lean` 1.0.233 (2026-10-27); engine repo pushed 2026-11-10, 22k stars (V-M) | **T** (CLI `--help` only; engine image not pulled) | Apache-2.0 | **SKIP**. Pricing (V-D†, `quantconnect.com/pricing.md`): Free = 1 backtest node, minute/hour/daily data in the cloud, **no** LEAN-CLI, **no** paper or live trading, no API access, 25 backtest downloads; Researcher $84/month ($888/year) adds CLI, paper trading, 2 live nodes; Team $168. Local data downloads are tied to paid credits ("QCC"). C#/Docker stack, recurring fee, and nothing the custom core lacks. |
| **backtesting.py** | single-instrument signal backtests with plots and a grid optimiser | 0.6.6 (2026-07-22); 1 release in 365 d (V-M) | **T** | AGPL-3.0 | **SKIP**. One instrument per `Backtest` (`MultiBacktest` runs one strategy over several datasets, not a portfolio); no target-weight API. Fine for a quick single-pair sanity plot. |
| **bt** (+ `ffn`) | tree-of-algos, weight-based portfolio backtester | 1.4.1 (2026-10-10); 10 releases in 365 d; repo pushed 2026-11-08 (V-M) | **T** | MIT | **XCHECK**. Good: `WeighTarget` + `Rebalance` is exactly our contract; negative weights and leverage work natively; has `Margin`, `TargetVol`, `WeighERC`, `LimitDeltas` algos. Bad: 0.75 s per 600×6 run (250× the engine); `integer_positions=True` by default; `initial_capital=1e9` with fractional positions raises "Potentially infinite loop detected" (float tolerance 1e-16 in `allocate()`, V-T) — use 1e6. |
| **cvxportfolio** | multi-period convex portfolio optimisation + market simulator with cost models | 1.5.1 (2025-07-06); 0 releases in 365 d; repo pushed 2026-04-27 (V-M) | **T** | GPL-3.0 | **XCHECK (primary)**. `MarketSimulator` + `FixedWeights` + `TransactionCost(a=)` + `HoldingCost(short_fees=, long_fees=, dividends=)` replays every engine leg. Slow (4.7 s per run) and quiet upstream — pin the version. |
| zipline-reloaded | Quantopian's engine, kept alive; US-equity bundles, Pipeline API | 3.2.1 (2026-10-25) (V-M) | **T(pd2)** — pandas < 3 → 2.3.3; import only (needs an ingested bundle) | Apache-2.0 | **SKIP**. Bundle/calendar machinery built for US single stocks. |
| backtrader | classic event-driven engine | 1.9.78.123 (2023-04-19, 1,300 d ago); repo last pushed 2024-08-19 (V-M) | **T** — runs, but emits `SyntaxWarning: invalid escape sequence` on import (a future `SyntaxError`); `cerebro.plot()` blocks on a GUI window | GPL-3.0 | **AVOID** for new work (unmaintained). |
| **freqtrade** | complete crypto bot: backtest, hyperopt, dry-run, live, Telegram, web UI | 2026.10 (2026-10-30); monthly releases; 56.7k stars (V-M) | **T(own)** — needs py ≥ 3.12; resolves with numpy 2.5.4 / pandas 3.1.1 | GPL-3.0 | **OPTIONAL** (crypto dry-run runner only). `list-exchanges` (V-T): officially supported = Binance, Bitget, BingX, Bybit, Bybit EU (spot), Gate, Gate EU, HTX, **Hyperliquid** (spot, isolated + cross futures), **Kraken** (spot), **Kraken Futures** (isolated futures), **OKX**, **MyOKX (EEA)** (spot); Bitvavo, Coinbase Advanced, Deribit listed as unsupported-but-available. Base install has **no FreqAI and no hyperopt** (`No module named 'datasieve'` / `'optuna'`, V-T) — they are extras. Strategy model = per-pair entry/exit signals on an OHLCV frame, not cross-sectional target weights. Docs (V-D†): Kraken spot API serves only 720 candles; Hyperliquid 5,000 candles, market orders emulated by limit at ≤ 5 % slippage; Bybit gives no funding history; Binance blocks server IPs in "Canada, Malaysia, the Netherlands, and the United States". |
| jesse | crypto backtest/live framework with its own UI | 3.6.1 (2026-11-10); 64 releases in 365 d (V-M) | **C** (≥ 3.10). Dry-run resolver: 65 packages; requires `pandas~=2.2.3`, `statsmodels~=0.14.4`, ray, psycopg2-binary (V-M) | MIT (core) | **SKIP**. "Live and paper trading functionality is supported … via an official plugin"; "access is limited to those with an active license" (V-D†). |
| hummingbot | market-making / arbitrage bot, 50+ connectors | PyPI 20260922 (2026-10-07); GitHub v2.17.0 (2026-09-22) (V-M) | **C** (cp312 wheel). Dry-run: 112 packages, downgrades numpy → 2.2.6 | Apache-2.0 | **SKIP**. Built for quoting, not for daily weight books. Connector list (V-D†) names Binance, Bybit, OKX, Kraken, Coinbase, Hyperliquid, dYdX; not Bitvavo or Deribit. |
| **pysystemtrade** | Rob Carver's futures trend/carry system: backtest + production for IBKR | 1.8.3 (2026-09-30), GitHub only — "isn't hosted on pypi.org"; moved to `pst-group/pysystemtrade` in 2026-01; maintainer Andy Geach since 2024 (V-M / V-D†) | **C** — `requires-python >= 3.11`, **pandas ≥ 2.3, < 3**, statsmodels 0.15, `ib_async ≥ 2` (pyproject, V-M) | GPL-3.0 | **SKIP as code, USE as a design reference.** Production assumes "a linux box" + MongoDB (+ Parquet) + cron (V-M, `docs/production.md` headings). Reusable ideas, not modules (recalled from Carver's published design — CLAIM, not re-read today): forecast scaling and capping, forecast-diversification and instrument-diversification multipliers, vol-targeted position sizing, buffering (no-trade bands), costs measured in Sharpe units with a turnover "speed limit", separation of *optimal* vs *held* positions with reconciliation reports. |
| qlib | Microsoft's ML platform for cross-sectional equity alpha | PyPI `pyqlib` 0.9.7 (2025-08-15) lags GitHub v0.9.8 (2026-10-08); 50k stars (V-M) | **C** (cp312 wheel). Dry-run: 110 packages incl. mlflow, jupyter, gym | MIT | **SKIP**. Built for thousands of stocks; our lanes have 9–41 instruments. |
| FinRL | deep-RL trading examples | PyPI 0.3.7 (2024-04-12); GitHub v0.3.8 (2026-03-20) (V-M) | not tested (torch + stable-baselines stack, heavy) | MIT | **SKIP**. |
| lumibot | broker-connected strategy framework, now "AI trading agents" | 4.6.48 (2026-11-07); 191 releases in 365 d (V-M) | **C** (≥ 3.10). Dry-run: **189 packages** incl. anthropic, google-genai, boto3, databento, ccxt pinned 4.5.64 | GPL-3.0 | **SKIP**. Brokers (V-D†): Alpaca, IBKR, Tradier, Schwab, Tradovate, ccxt exchanges, Kalshi, Polymarket. |
| blankly | exchange-agnostic bot framework | 1.18.25b0 (2023-07-23); repo last pushed 2024-12-30 (V-M) | not tested (classifiers stop at 3.10) | LGPL-3.0 | **AVOID** (dead). |
| PyBroker (`lib-pybroker`) | ML-oriented strategy backtester with walk-forward and bootstrap metrics | 2.0.2 (2026-10-20); sdist only (V-M) | **T** — 20 s for a 600-bar, 2-symbol run incl. bootstrap | Apache-2.0 **with Commons Clause** | **SKIP**. Per-symbol rule callbacks, share-based orders; pins `optuna < 5`. Its built-in bootstrap confidence intervals for Sharpe / profit factor ran (V-T); we already cover that with `arch`. |
| fastquant | backtrader wrapper | 0.1.8.1 (2023-01-04); repo last pushed 2023-09-15 (V-M) | not tested | PyPI says GPLv3, GitHub says MIT | **AVOID** (dead). |
| **skfolio** | scikit-learn-style portfolio optimisation and model selection | 1.12.8 (2026-11-08); 90 releases in 365 d (V-M) | **T** — only 7 runtime dependencies | BSD-3-Clause | **USE** (when a book needs estimation). `MeanRisk`, `HierarchicalRiskParity`, `RiskBudgeting`, `InverseVolatility`; `CombinatorialPurgedCV`, `WalkForward`, `MultipleRandomizedCV`, `optimal_folds_number` all ran (V-T). |
| riskfolio-lib | portfolio optimisation with many risk measures | 7.4.1 (2026-11-04) (V-M) | **T** — but 80 packages: depends on **vectorbt**, arch, astropy, cvxpy | BSD-3-Clause | **OPTIONAL** (alternative to skfolio). Min-variance weights agree with skfolio to 1.5e-4 (V-T). |
| PyPortfolioOpt | classic mean-variance / HRP / Black-Litterman | 1.6.0 (2026-02-26); 1 release in 365 d; moved to `PyPortfolio/PyPortfolioOpt` (V-M) | **T, partly broken** — `EfficientFrontier.min_volatility()` works; `HRPOpt.optimize()` raises `AttributeError: module 'scipy.cluster.hierarchy' has no attribute '_LINKAGE_METHODS'` on scipy 1.18.1 | MIT | **AVOID** on this stack. |

### 1B. Statistics for backtest overfitting and multiple testing

| library | purpose | latest version (date) | py3.12 | licence | verdict |
|---|---|---|---|---|---|
| **arch** | `arch.bootstrap`: `StationaryBootstrap`, `CircularBlockBootstrap`, `optimal_block_length`, `SPA` (Hansen; `upper` p-value = White's reality check), `StepM` (Romano-Wolf), `MCS` | 8.0.0 (2025-10-21); repo pushed 2026-11-09 (V-M) | **T** (already in the repo venv) | NCSA | **USE**. Toy: 50 formulas, T = 1,500, two planted winners → SPA p = 0.000, StepM keeps the Sharpe-2.4 one and rejects the Sharpe-1.2 one; pure-noise sweep → SPA p = 0.24 / 0.35 / 0.35, StepM empty (V-T). K = 160, T = 4,500, 1,000 reps: 13 s each. |
| **statsmodels** | `multipletests` (Bonferroni, Holm, BH, BY); HAC covariance | 0.15.0 (2026-08-27) (V-M) | **T** | BSD-3-Clause | **USE / XCHECK**. `multipletests` ran on 160 p-values with 3 planted; `scipy.stats.false_discovery_control` returns identical BH and BY adjusted p-values (V-T). HAC t-stat matches `stats.newey_west_t` to ≤ 4.4e-15. |
| scipy | `stats.false_discovery_control`, `stats.bootstrap` (iid only) | 1.18.1 (2026-08-21) (V-M) | **T** | BSD-3-Clause | **USE**. |
| **RiskLabAI** | López de Prado toolbox: PBO (CSCV), PSR, expected-max-Sharpe, purged K-fold, combinatorial purged CV, `lplz_sharpe_inference` (a Sharpe test on a Newey-West long-run variance; origin not checked) | 3.2.0 (2026-10-02); 14 releases in 365 d. GitHub repo `RiskLabAI/RiskLabAI.py` was created 2026-06-28 and has **9 stars** (V-M) | **T(own)** — pins `statsmodels < 0.15` (would downgrade the repo's 0.15.0); ran with numpy 2.5.4 / pandas 3.1.1 | BSD-3-Clause | **XCHECK**. PSR equals `stats.psr` exactly; `expected_max_sharpe_ratio` equals `stats.expected_max_sharpe` to 1e-14; PBO = 0.000 with one real formula in 80, and on pure noise averages 0.46 with **s.d. 0.18** over 24 seeds (so a single PBO number is a noisy statistic). Little public scrutiny — do not make it a dependency. |
| pypbo | PBO, PSR, MinTRL, MinBTL, DSR | GitHub only (`esvhd/pypbo`, pushed 2026-07-06, 145 stars); not on PyPI (V-M) | not tested; README lists "statsmodels 0.8.0" | AGPL-3.0 | **OPTIONAL** (read as a reference). |
| mlfinlab | Hudson & Thames toolbox | not on PyPI (404); public repo last pushed 2023-10-02, licence `NOASSERTION` (V-M) | — | proprietary | **AVOID** (unavailable). |
| mlfinpy | community re-implementation of *Advances in Financial ML* | 0.1.2 (2024-10-09); 2 releases ever (V-M) | **✗ / T(own)** — forces numpy 1.26.4, pandas 2.3.3, numba 0.60; `import mlfinpy` fails with `No module named 'sklearn'` (undeclared dependency) | MIT | **AVOID**. Has `PurgedKFold` and `CombinatorialPurgedKFold`; **no** PBO or deflated Sharpe. |
| timeseriescv | purged / combinatorial CV | 0.2 (2018-09-07) (V-M) | not tested | MIT | **AVOID** (dead). |
| skfolio `model_selection` | `CombinatorialPurgedCV(n_folds, n_test_folds, purged_size, embargo_size)`, `WalkForward` | see 1A | **T** | BSD-3-Clause | **USE** for Tier-3 nested validation. `split()` yields `(train, [test_fold, …])` — a list of test folds, so it is not a drop-in for `sklearn.cross_val_score`; use skfolio's `cross_val_predict` or loop. |
| vectorbt returns accessor | `deflated_sharpe_ratio(nb_trials=, var_sharpe=)` | see 1A (the DSR formula was corrected in v1.1.1, 2026-09-26, V-M) | **T** | — | **XCHECK** for `stats.deflated_sharpe`. |
| **quantstats** | tear sheets and metrics, incl. `probabilistic_sharpe_ratio` | 0.0.86 (2026-09-27) (V-M) | **T** (pulls yfinance, seaborn) | Apache-2.0 | **OPTIONAL** (reports) / **XCHECK**. |
| **empyrical-reloaded** | plain performance metrics | 0.7.2 (2026-11-02) (V-M) | **T** | Apache-2.0 | **XCHECK** (adds only bottleneck, peewee, pytz). |
| pyfolio-reloaded | notebook tear sheets | 0.10.2 (2026-11-02) (V-M) | **T** (import) | Apache-2.0 | **OPTIONAL**. |
| alphalens-reloaded | factor IC / quantile analysis | 0.5.1 (2026-10-26) (V-M) | **C** | Apache-2.0 | **OPTIONAL**. |
| tsbootstrap | time-series bootstrap collection | 0.7.3 (2026-09-29) (V-M) | **C** | MIT | not needed — `arch` covers it. |

### 1C. Execution / broker / exchange SDKs (NL retail)

| library | purpose | latest version (date) | py3.12 | licence | verdict |
|---|---|---|---|---|---|
| **ccxt** | unified REST + WebSocket client | 4.5.92 (2026-11-04); 72 releases in 365 d; 104 REST / 76 WebSocket exchange classes (V-T) | **T** | MIT | **USE**. Capability matrix and live keyless calls in §4 (T14). |
| hyperliquid-python-sdk | official Hyperliquid SDK (signing, agent wallets) | 0.24.0 (2026-06-04) (V-M) | **T** — `Info.meta()` returned 235 perps, `funding_history("BTC")` worked. Requires eth-account < 0.14, eth-utils < 6 | MIT | **OPTIONAL** (fallback to ccxt; keep in its own venv). |
| pybit | official Bybit SDK | 5.17.2 (2026-11-10) (V-M) | **T** (`HTTP(testnet=True)` → `api-testnet.bybit.com`) | MIT | **OPTIONAL**. |
| python-okx | official OKX SDK | 0.4.4 (2026-09-07) (V-M) | **T** (`flag` live / demo switch present) | MIT on PyPI; no licence file detected on GitHub | **OPTIONAL**. |
| python-kraken-sdk | community Kraken spot + futures SDK | 3.5.1 (2026-09-28) (V-M) | **T** | Apache-2.0 | **OPTIONAL** (alternative to ccxt for Kraken). |
| **ib_async** | asyncio client for the IBKR TWS API (successor of ib_insync) | 2.1.0 (2025-12-08); repo pushed 2026-11-04 (V-M) | **T** (import; needs a running IB Gateway / TWS — not started here) | BSD-2-Clause | **USE** for IBKR. README (V-D†): "The ibapi package from IB is not needed"; needs API port enabled; Gateway heap ≥ 4096 MB advised for bulk data. |
| **ibind** (+ ibeam) | client for the IBKR Client Portal Web API (REST + WebSocket) | ibind 0.2.3 (2026-11-08); ibeam 0.6.0 (2026-11-08) (V-M) | **T** (import) | Apache-2.0 | **OPTIONAL** (main alternative to ib_async). "IBind supports fully headless authentication using OAuth 1.0a"; prerequisite "An IBKR 'Pro' account", self-service key setup, activation may wait for the weekend server restart (V-M, repo docs). No Java process on the laptop. |
| ib_insync | predecessor | 0.9.86 (2023-07-02); repo **archived** (V-M) | — | BSD | **AVOID**. |
| oandapyV20 | OANDA v20 REST wrapper | 0.7.2 (2021-08-27) (V-M) | **T** (import) | MIT | **AVOID** for this owner: OANDA says the v20 account "is available to all divisions except OANDA Global Markets and OANDA TMS BROKERS S.A." (V-D†) and the TMS entity is the one named across OANDA's EU pages (CLAIM). |
| v20 (official) | OANDA's own bindings | 3.0.25.0 (2018-09-28) (V-M) | **✗ → T** — import fails with `No module named 'yaml'` until PyYAML is added | MIT | **AVOID** (stale). |
| **alpaca-py** | Alpaca trading + data | 0.45.0 (2026-11-05) (V-M) | **T** (`TradingClient(paper=True)`) | Apache-2.0 | **USE** for US-ETF paper (already the repo's data rail). |
| Trading 212 Public API | REST v0, "currently in **beta**"; "enabled and usable only for **Invest and Stocks ISA**"; demo + live hosts; HTTP Basic key:secret; per-account rate limits (V-D†) | no official SDK. Community: `pyt212` 0.1.0 (2026-03-05), `trading212py` 0.1.3 (2026-04-06, py ≥ 3.13), `python-trading212` 2.0.4 (2024-12-04) (V-M) | not tested | MIT (community) | **OPTIONAL**: write a thin `requests` client; none of the wrappers has a track record. No CFD accounts → no shorts, no leverage. |
| saxo_openapi | Saxo OpenAPI wrapper | 0.6.0 (2019-09-16); repo pushed 2026-02-03 (V-M) | **T** (import) | MIT | **SKIP the wrapper** (7 years stale); the API offers a demo environment, a 24-hour token and a live application key (V-D†). |
| trading-ig | IG REST + streaming wrapper | 0.0.25 (2026-08-25) (V-M) | **T** (import) | BSD-3-Clause | **OPTIONAL** (if IG is the CFD venue). |
| ctrader-open-api (`OpenApiPy`) | cTrader Open API (Protobuf / JSON) | 0.9.2 (2024-06-26); repo last pushed 2024-08-07 (V-M) | **T** (import; Twisted-based; downgrades `requests`) | MIT | **OPTIONAL**. API: demo and live accounts, 50 req/s (5 req/s historical) (V-D†). |
| MetaTrader5 | MT5 terminal bridge | 5.0.6231 (2026-09-27) (V-M) | **✗** — "Wheels are available … on the following platform: `win_amd64`" | MIT (package) | **AVOID** on Linux. Workaround `mt5linux` 1.1.1 (2026-08-04) imports (V-T) but needs Wine or Docker plus a Windows `mt5server.exe` (V-M) — a second OS inside a 15 GB laptop. |
| py-clob-client → **py-clob-client-v2** | Polymarket CLOB | 0.34.6 (2026-02-19, repo **archived**) → v2 1.2.1 (2026-10-15) (V-M) | **T** (both import) | MIT | **AVOID** for an NL resident: Kansspelautoriteit order against Adventure One QSS Inc. dated 2026-01-20 (decision PDF returns HTTP 200; its file name spells the company "SQQ"); NOS 2026-02-17 "Polymarket moet weg uit Nederland"; later fines / court case are CLAIM (search snippets). |
| solders / solana | Solana primitives and RPC client | solders 0.29.0 (2026-08-13); solana 0.41.0 (2026-10-03) (V-M) | **T** (import) | Apache-2.0 / MIT | out of factory scope (memecoins are not a lane). |
| Jupiter API | Solana swap / price / perps REST | "A single key from the Developer Platform unlocks every Jupiter API"; "Start free" (V-D†). Base URLs and limits: UNKNOWN (not on the page read) | not tested | — | out of scope. |
| web3.py | EVM client | 8.0.0 (2026-08-31); repo moved to `ApeWorX/web3.py` (V-M) | **T** (import); conflicts with hyperliquid-python-sdk's eth-account pin | MIT | out of scope. |
| python-bitvavo-api | official Bitvavo client | 1.4.3 (2025-05-14) (V-M) | **T** (import) | ISC | **OPTIONAL** — ccxt `bitvavo` covers it. |
| coinbase-advanced-py | official Coinbase Advanced SDK | 1.8.4 (2026-06-19); 2.0.0rc1 (2026-09-30) (V-M) | **T** (import); pins websockets < 14 | Apache-2.0 | **OPTIONAL** — ccxt `coinbase` covers it. |

### 1D. Indicators, features, ML, data

| library | purpose | latest version (date) | py3.12 | licence | verdict |
|---|---|---|---|---|---|
| **TA-Lib** | C indicator library, Python wrapper | 0.8.3 (2026-10-28) (V-M) | **T** — binary manylinux wheel, **no compiler or system library needed**; 237 functions | BSD-2-Clause (repo) | **OPTIONAL**. The old install pain is gone. |
| pandas-ta | indicator library | 0.4.71b0 (2025-09-14); only 2 releases left on PyPI; **GitHub repo 404, `www.pandas-ta.dev` no DNS** (V-M / V-T) | **T(pd2)** — pins numba == 0.61.2 → numpy 2.2.6 | none declared | **AVOID**. |
| **pandas-ta-classic** | community fork of the old pandas-ta | 0.9.0 (2026-10-28); 10 releases in 365 d (V-M) | **T** — no extra dependencies | MIT | **OPTIONAL**. RSI(14) identical to TA-Lib and `ta` (34.908). |
| ta | small pure-pandas indicator set | 0.11.0 (2023-11-02); repo pushed 2026-03-18 (V-M) | **T** | MIT | **OPTIONAL** (stale but trivial). |
| tsfresh / tsfel | automatic time-series features | tsfresh 0.21.2 (2026-05-31); tsfel 0.2.0 (2025-08-20) (V-M) | **T** / **T** | MIT / BSD-3 | **SKIP** for now: hundreds of generated features × a multiple-testing account is the wrong direction for 9–41 instruments. |
| **LightGBM** | gradient boosting | 4.7.0 (2026-07-18) (V-M) | **T** | MIT (PyPI field empty; not re-read today) | **USE** for the declared ML rules (lightest of the three). |
| XGBoost | gradient boosting | 3.4.1 (2026-08-15) (V-M) | **T** as `xgboost-cpu`; the default `xgboost` wheel also pulls `nvidia-nccl-cu13` | Apache-2.0 | **OPTIONAL** — install `xgboost-cpu` on this laptop. |
| CatBoost | gradient boosting | 1.2.10 (2026-02-18) (V-M) | **T** (97 MB wheel) | Apache-2.0 | **OPTIONAL**. |
| scikit-learn | `HistGradientBoosting*`, CV utilities | 1.9.1 (2026-09-10) (V-M) | **T** (in the repo venv) | BSD-3-Clause | **USE** (zero new dependencies). |
| **Optuna** | hyper-parameter search | 5.0.0 (2026-09-07) (V-M) | **T** | MIT | **OPTIONAL** — every trial is a trial in the multiplicity account; prefer declared grids. |
| darts | forecasting models, unified API | 0.48.1 (2026-10-16) (V-M) | **T(pd2)** — ran on pandas 2.3.3; the resolver also accepts pandas 3.1.1 (untested); core install has **no torch**; downgrades python-dateutil | Apache-2.0 | **SKIP**. |
| statsforecast | fast ARIMA / ETS | 2.1.1 (2026-07-16) (V-M) | **T(pd2)** — pandas < 3 | Apache-2.0 | **SKIP**. |
| **polars** / **duckdb** / pyarrow | columnar data, SQL over parquet | polars 2.1.0 (2026-10-25); duckdb 2.0.0 (2026-10-21); pyarrow 26.0.1 (2026-11-03) (V-M) | **T** / **T** / in repo venv | MIT / MIT / Apache-2.0 | **USE** (polars and pyarrow are already in the repo venv; duckdb for ad-hoc SQL over the parquet panels). |
| numba | JIT | 0.68.1 (2026-10-27); llvmlite 0.50.0 is a 60 MB wheel (V-M) | **T** | BSD | **OPTIONAL** — only if profiling shows a loop that numpy cannot express (`realism.simulate_account`). |
| bottleneck | fast rolling / nan-aware reductions | 1.6.0 (2025-09-08) (V-M) | **T** — `move_std` equals pandas rolling std | Simplified BSD | **OPTIONAL** (pandas uses it automatically when present). |

### 1E. Ops (brief — versions V-M, recommendations are judgement, not tests)

| need | pick | why | alternative |
|---|---|---|---|
| scheduling | **systemd user timers** (`OnCalendar=… UTC`, `Persistent=true`, `loginctl enable-linger`) | catch-up after sleep or crash, journald logs, `MemoryMax=` / `CPUQuota=` per unit — matters on a laptop that has frozen on memory pressure; the repo has run its watchers as systemd user units before (not re-checked today) | cron (no catch-up, silent env differences); APScheduler 3.11.3 (2026-06-28) — in-process, dies with its process, fine only inside a long-running runner |
| state / ledger | **sqlite (WAL) for orders, fills, positions; append-only JSONL + sha256 for decisions** | one file, transactional, zero services; matches the repo's ledger discipline; duckdb reads both for analysis | Postgres / MongoDB (what jesse and pysystemtrade need) — more RAM, more ops |
| secrets | keys in a file outside the repo with mode 600, or `systemd-creds` / `LoadCredentialEncrypted=`; API keys **trade-only, no withdrawal, IP-allowlisted**; signing kept outside research services (AGENTS.md) | the repo's `.env` exists and must never be committed | `keyring` 25.7.0 (Secret Service; needs a desktop session) ; `python-dotenv` 1.2.4 for local dev |
| logging / alerting | stdlib `logging` or `structlog` 26.1.0 → journald; one Telegram message per fill / halt / daily digest via plain HTTPS `sendMessage` (the repo already holds a bot token in `.env` — an option, not a decision) | no extra daemon | `apprise` 2.2.0 (multi-channel), `python-telegram-bot` 22.8 (if two-way commands are wanted) |
| dashboard | **static HTML report regenerated by a timer** first | zero resident memory | `streamlit` 1.67.0 (quick, but another always-on Python process), Grafana (+ a datasource; heaviest) |

### 1F. LLM-agent trading frameworks

| project | what it is | status (V-M) | what its own page says | evidence of live performance |
|---|---|---|---|---|
| TradingAgents (`TauricResearch`) | multi-agent LLM "trading firm" (analysts, debate, trader, risk) | v0.7.1 (2026-10-27), 121.8k stars, Apache-2.0 | "designed for research purposes … not intended as financial, investment …" (README). Project page table (V-D†): AAPL cumulative return 26.62 %, Sharpe **8.21** vs buy-and-hold −5.23 %, three tickers, a few months of 2024, transaction costs not mentioned. Release notes of 2026-09 add "point-in-time integrity across every dated path" and "backtests that see only data published by each analysis date" (README news, V-M) — my reading: earlier backtests did not guarantee it | **none**. A Sharpe of 8 over a few months on three stocks is not evidence; third-party re-computation disputing the baseline is CLAIM. |
| ai-hedge-fund (`virattt`) | persona agents + backtester + paper mode | v2.7.2 (2026-11-09), 64.6k stars, MIT | "for **educational** purposes only and is not intended for real trading or investment" (README) | none claimed. |
| FinRobot / FinGPT (`AI4Finance`) | agent platform / financial LLM fine-tunes | FinRobot 8.4k stars; FinGPT v1.0.0 (2026-04-08), 21.5k stars | "should not be construed as financial advice or recommendations for live trading" (FinRobot README) | none. |
| AI-Trader (`HKUDS`), nofx (`NoFxAiOS`) | agent-vs-agent arenas / agentic trading OS | AI-Trader 23.2k stars, no licence, last push 2026-06-11; nofx 13.3k stars, AGPL-3.0 | paper-trading arenas | no audited results found (UNKNOWN). |
| **Alpha Arena** (Nof1) — an experiment, not a library | six LLMs, $10,000 real money each, crypto perps, about two weeks ending 2025-11-03 | — | organiser quoted: "PnL … was dominated by trading costs in early runs"; LLMs "don't really handle numerical time series data very well" (as quoted by Protos, 2025-11-04 — a news outlet read through the fetch tool; Nof1's own write-up was not reachable, so CLAIM) | Season 1 P&L: Qwen3 Max +$2,232, DeepSeek +$489, Claude Sonnet −$3,081, Grok −$4,531, Gemini −$5,671, ChatGPT −$6,267 (CLAIM — Protos; the matching percentages +22.32 %, +4.89 %, −62.66 % appear in other outlets' search snippets) → **−$16,829 on $60,000 = −28 %** (my arithmetic); win rates 25–30 %. Season 1.5 (US stocks): one "mystery model" won with ≈ +10–12 % (CLAIM). 2026-05 roundup: "6 of 32" results profitable, aggregate about −⅓, organiser: "It's not yet feasible to directly hand over money to an LLM and let it trade on its own" (CLAIM — KuCoin news flash citing CoinDesk). |

Academic re-tests (abstracts read through the fetch tool, V-D†): **FINSABER** (arXiv 2505.07078, v6
2026-06-26) — over two decades and 100+ symbols the previously reported LLM advantages shrink
considerably; LLM strategies are too conservative in bull markets and too aggressive in bear markets.
**StockBench** (arXiv 2510.02209, v2 2026-03-02) — most LLM agents fail to beat buy-and-hold on a
contamination-free multi-month test. **The Alpha Illusion** (arXiv 2605.16895, 2026-05-16) — position
paper: reported alpha "should not be treated as deployment evidence"; it cannot be separated from temporal
contamination, unmodelled frictions, short-window Sharpe uncertainty, narrative fitting and parametric
priors. **LiveTradeBench** (arXiv 2511.03628) — 21 LLMs, 50 live days, general benchmark scores
uncorrelated with trading results, transaction costs omitted (CLAIM — search snippet only).

**Verdict.** No LLM in the decision seat. If an LLM-derived signal is ever wanted, it enters as one more
rule: point-in-time inputs logged, declared in the grid, counted in the multiplicity account, scored by
the same engine, forward-papered.

---

## 2. Recommended stack

**Custom core or framework? Keep the custom core.** Reasons, each backed by something measured today:

- *Fit.* The research contract is "target weights × returns". That is ~100 lines of numpy. Every
  framework's weight is in order simulation the daily/hourly weight contract does not use.
- *Correctness is demonstrable.* ≤ 1.3e-15 against three independent code bases on the price and carry
  legs; costs and hold costs reconcile to 1.4e-7 and 4e-16 once the documented conventions are applied.
- *Speed.* `backtest`: 3.0 ms (600×6), 8.6 ms (4,500×9), 32 ms (4,500×41); `fast_net_returns`: 160
  formulas × 4,500 × 9 in 0.81 s. bt 750 ms, cvxportfolio 4.7 s, vectorbt 121 ms after a 49 s first call.
- *Honesty features are ours alone.* `lag = 0` and un-flagged `exec_prices` are refused (re-verified, §4
  T21); scramble audit; circular-shift null; cost provenance. A framework would have to be wrapped in all
  of them and brings silent defaults of its own (vectorbt's un-levered partial fills, bt's integer
  positions, Nautilus' zero fills on one-sided FX bars and its same-bar or previous-bar fills).
- *Dependency exposure.* Eight of the surveyed packages cannot share the repo's venv today (§0 item 6). A numpy core cannot be stranded that way.
- *Licences.* vectorbt and PyBroker carry the Commons Clause, backtesting.py is AGPL, bt MIT,
  cvxportfolio / freqtrade / pysystemtrade GPL-3. All are fine for private research; none should become
  a runtime dependency of something the owner might one day offer to others.

| role | pick | why | main alternative |
|---|---|---|---|
| **research core** | `scripts/factory` engine on numpy + pandas; pyarrow / polars for panels; duckdb for ad-hoc SQL | above | vectorbt 1.2.0 if a framework were forced (fast grids; but no leverage, no carry, Commons Clause) |
| **multiple-testing statistics** | `arch` 8.0.0 for SPA / StepM / MCS / stationary bootstrap; own BH / BY / Holm / PBO / DSR in `mtest.py` and `stats.py` | `arch` is maintained, numerically sane on toys, already installed; our own small functions are each pinned to an independent implementation (§3.7) | no second maintained Python implementation of SPA + StepM was found (`model-confidence-set` 0.1.3, last release 2024-10, by its name covers MCS only — not inspected) — the alternative is R |
| **portfolio construction** | own causal equal-risk / inverse-vol / buffer functions (`portfolio.py`) for parameter-free books; **skfolio 1.12.8** when something is estimated (HRP, risk budgeting, shrinkage) | parameter-free books need no optimiser; skfolio is light (7 dependencies), BSD, sklearn-native and ships purged CV | riskfolio-lib 7.4.1 (more risk measures, 80 dependencies incl. vectorbt) |
| **cross-validation of the engine** | **cvxportfolio 1.5.1** (all four legs) + **bt 1.4.1** (leverage, different lineage) + **vectorbt 1.2.0** (third opinion) in a separate venv; `xcheck.py` stays as the in-repo loop twin | §3 | NautilusTrader for an execution-realistic replay — a different question (fills, not arithmetic) |
| **time-series CV for ML rules / Tier 3** | skfolio `WalkForward`, `CombinatorialPurgedCV` | tested; purge and embargo are explicit integers | RiskLabAI `PurgedKFold` (label-end-time based) in its own venv |
| **crypto execution** | **ccxt 4.5.92**: `krakenfutures` (sandbox = `demo-futures.kraken.com`), `kraken`, `hyperliquid` (testnet), `myokx` (host `eea.okx.com`), `bitvavo`, `coinbase` | one client, one venv, unified `fetch_funding_rate(_history)`, `fetch_positions`, `set_leverage`; funding units verified against Kraken's own endpoint (§4 T14) | native SDKs per venue (hyperliquid-python-sdk, python-kraken-sdk) each in its own venv; freqtrade dry-run as a packaged bot |
| **FX / CFD execution** | **IBKR through ib_async 2.1.0** (IB Gateway; README: default ports 7497 TWS / 4001 Gateway) | maintained client, real spot FX rather than CFDs, a paper account; pysystemtrade runs production on it | ibind 0.2.3 on the IBKR Web API (OAuth 1.0a, no local Java); for CFD brokers: trading-ig 0.0.25, cTrader Open API (`ctrader-open-api` 0.9.2 or raw JSON/WebSocket), Capital.com REST (only tiny community clients: `capitalcom` 1.0.4, `python-capital` 0.2.2 — write a thin one). Not OANDA v20 (EU entity excluded), not MetaTrader5 on Linux. |
| **ETF execution** | **IBKR through ib_async** (UCITS ETFs) | same connection as FX, one reconciliation path | Trading 212 Invest API (beta; long-only, unlevered; thin own REST client); Alpaca for **paper** US-ETF replication only |
| **paper trading** | the factory's own forward paper logger first (design rule); then venue demos in this order: IBKR paper account (ib_async), Kraken Futures demo (ccxt sandbox), Hyperliquid testnet, Trading 212 demo host, Alpaca paper | a venue demo tests plumbing (auth, symbols, lot sizes, rejects); it does not test edge | freqtrade dry-run (crypto), Nautilus `sandbox` adapter |

Venue eligibility and costs are `venues.json`'s job, not this file's: what a venue offers an NL retail
account (IBKR paper account, spot FX, UCITS ETFs, demo hosts) was **not** verified here beyond the SDK
facts in §1C. Library-relevant flags only:
Kraken's EEA derivatives launch is documented by press coverage of May 2025 (CLAIM; NL eligibility
UNKNOWN here); OKX's EEA "X-Perps" and Bybit EU's missing derivatives licence are CLAIM (affiliate
sites); Hyperliquid's own restricted list was not read (UNKNOWN).

---

## 3. Cross-checking the custom engine against independent libraries

### 3.1 What exists and what this adds

`scripts/factory/xcheck.py` is a naive loop engine "written from the contract's text" and, per its
docstring, pinned to `engine.py` at 1e-10 (its tests were not run by me). That proves the vectorised
code implements the contract. It cannot show that the
**contract** matches what an account experiences, because both files share one author's reading. Three
outside libraries with their own accounting (cash ledger, share quantities, fees paid from cash) can.

`engine.py` changed twice under this work; every version was tested: the v1 draft (sha256 `d0708ceb…`,
mtime 13:33 UTC), v2 (sha256 `58262e07…`, mtime 14:07 UTC; runs at 14:39 and 14:50 UTC) and the file as
it stood at 15:04 UTC (sha256 `25b9f3f9…`). Same numbers each time.

### 3.2 Mapping (verified)

| engine concept | bt 1.4.1 | vectorbt 1.2.0 | cvxportfolio 1.5.1 |
|---|---|---|---|
| timing (A): `held = w.shift(1 + lag)` | `WeighTarget(w.shift(lag).fillna(0))`, `Rebalance()` on `panel.prices` | `from_orders(close=prices, size=w.shift(lag), size_type="targetpercent", cash_sharing=True, group_by=True, call_seq="auto", direction="both")` | `FixedWeights(w.shift(lag) + cash column)`; `returns = prices.pct_change().shift(-1)` (start-of-period indexing) |
| timing (B): `exec_prices=F`, `held = w.shift(1 + extra_lag)` | same, on **F**, target `w.shift(extra_lag)` | same, `close=F`, `size=w.shift(extra_lag)` | not run (same mapping on F) |
| per-print net return | `res.prices[name].pct_change()` | `pf.returns()` | `result.v.pct_change()` |
| `cost_bp_side` | `commissions=lambda q, p: abs(q) * p * c` | `fees=c` | `TransactionCost(a=c, b=None)` |
| `hold_cost_short_bp_year` / `…long…` | none (a `Margin` algo exists for levered longs; not used) | none | `HoldingCost(short_fees=pct, long_fees=pct)` — annual **percent**, accrued on calendar time |
| `carry` panel | fold into a total-return price `P'_t = P'_{t−1}(1 + r_t + carry_t)` | same trick | `HoldingCost(dividends=carry.shift(-1))` — exact |
| leverage > 1 | native (cash goes negative) | **not possible**; scale: `L × run(w / L)` | native (cash weight goes negative) |
| fractional units | `integer_positions=False` | default | `round_trades=False` |
| index | tz-naive was passed | tz-aware UTC accepted | tz-naive was passed; needs `cash_key`, `min_history=pd.Timedelta("0d")` |

### 3.3 Reference implementation

The script below is the whole plan. It was extracted verbatim from this file and run read-only against the
live repo at 15:04:25 UTC (engine sha256 `25b9f3f9…`): 14 checks OK, exit code 0 (§4, T24). Suggested home: `scripts/factory/tests/test_xcheck_external.py`, skipped
unless bt / vectorbt / cvxportfolio import; run it in a **separate** venv (87 packages:
`uv pip install numpy==2.5.4 pandas==3.1.1 bt==1.4.1 vectorbt==1.2.0 cvxportfolio==1.5.1`) whenever
`engine.py`'s sha changes, and record the sha and the three versions next to the result.

```python
"""xcheck_external.py - cross-check scripts/factory/engine.py against three INDEPENDENT libraries.
    MPLBACKEND=Agg PYTHONDONTWRITEBYTECODE=1 python xcheck_external.py [/path/to/repo]
Exit code 0 = every assertion held. The script only READS the repo."""
import hashlib, pathlib, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

REPO = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/home/anont/meme")
sys.path.insert(0, str(REPO))
from scripts.factory.engine import backtest          # noqa: E402
from scripts.factory.panel import PanelBundle        # noqa: E402
import bt, cvxportfolio as cvx, vectorbt as vbt      # noqa: E402

LAG, PPY, CASH, BP = 1, 252, "USDOLLAR", 5.0
print("engine.py sha256", hashlib.sha256((REPO / "scripts/factory/engine.py").read_bytes()).hexdigest())
print("bt", bt.__version__, "vectorbt", vbt.__version__, "cvxportfolio", cvx.__version__, "pandas", pd.__version__)

# ---- identical inputs: 600 business days x 6 instruments, long/short vol-targeted 20-print momentum
rng = np.random.default_rng(7)
T, N = 600, 6
idx = pd.date_range("2020-01-01", periods=T, freq="B", tz="UTC")
vols = np.array([0.08, 0.10, 0.15, 0.20, 0.40, 0.60]) / np.sqrt(PPY)
P = pd.DataFrame(100 * np.cumprod(1 + rng.standard_normal((T, N)) * vols + 0.0002, axis=0), index=idx, columns=list("ABCDEF"))
CARRY = pd.DataFrame(rng.normal(0.0, 0.0001, (T, N)) + 0.00005, index=idx, columns=P.columns)
R = P.pct_change()
W = (np.sign(P.pct_change(20)) * (0.10 / (R.rolling(20).std() * np.sqrt(PPY))) / N).clip(-1, 1)   # NaN in warm-up
TW = W.shift(LAG)                       # timing map (A): w_s is traded at print s + lag, at that print's price


def eng(w, cost_bp=0.0, short_bp=0.0, carry=None):
    panel = PanelBundle(lane="XCHECK", prices=P, carry=carry, meta={"periods_per_year": PPY})
    return backtest(panel, w, lag=LAG, cost_bp_side=cost_bp, hold_cost_short_bp_year=short_bp)


def lib_bt(target, cost_bp=0.0, px=P):                  # rows of `target` = prints on which bt trades
    px, tw, c = px.tz_localize(None), target.tz_localize(None), cost_bp / 1e4
    strat = bt.Strategy("x", [bt.algos.WeighTarget(tw), bt.algos.Rebalance()])
    res = bt.run(bt.Backtest(strat, px, initial_capital=1e6, integer_positions=False,   # 1e9 trips bt's allocate() loop
                             commissions=lambda q, p: abs(q) * p * c))
    out = res.prices["x"].pct_change().reindex(px.index).fillna(0.0)
    out.index = idx
    return out


def lib_vbt(target, cost_bp=0.0):                       # NaN row = no order
    return vbt.Portfolio.from_orders(close=P, size=target, size_type="targetpercent", direction="both",
                                     fees=cost_bp / 1e4, init_cash=1e6, cash_sharing=True, group_by=True,
                                     call_seq="auto", freq="1D").returns()


def lib_cvx(w, cost_bp=0.0, short_bp=0.0, carry=None):
    px = P.tz_localize(None)
    rr = px.pct_change().shift(-1).iloc[:-1]            # cvxportfolio indexes a return at the START of its period
    rr[CASH] = 0.0
    tw = w.shift(LAG).fillna(0.0).tz_localize(None)
    tw[CASH] = 1.0 - tw.sum(axis=1)
    costs, hold = [], {}
    if cost_bp:
        costs.append(cvx.TransactionCost(a=cost_bp / 1e4, b=None))      # linear cost only, no impact term
    if short_bp:
        hold["short_fees"] = short_bp / 100.0                           # ANNUAL PERCENT, accrued on calendar time
    if carry is not None:
        hold["dividends"] = carry.tz_localize(None).shift(-1).iloc[:-1]  # per-period rate paid to the holder
    if hold:
        costs.append(cvx.HoldingCost(**hold))
    sim = cvx.MarketSimulator(returns=rr, costs=costs, round_trades=False, cash_key=CASH, min_history=pd.Timedelta("0d"))
    v = sim.backtest(cvx.FixedWeights(tw), start_time=px.index[0], end_time=px.index[-2], initial_value=1e6).v
    out = v.pct_change().fillna(0.0)
    out.index = out.index.tz_localize("UTC")
    return out.reindex(idx).fillna(0.0)


def gap(a, b):
    """max |per-print difference|, last print excluded (the engine never books the trade due on it)."""
    return float((a.iloc[:-1] - b.iloc[:-1]).abs().max())


def check(label, a, b, tol):
    g = gap(a, b)
    print(f"{'OK  ' if g <= tol else 'FAIL'} {label:62s} max|d| = {g:.2e}  (tol {tol:.0e})")
    assert g <= tol, label


def drift_turnover(held):
    """What a real rebalancer trades at print t-1 (booked in row t): target minus the DRIFTED old position."""
    port = (held * R.fillna(0.0)).sum(axis=1)
    drifted = held.shift(1).fillna(0.0).mul(1 + R.shift(1).fillna(0.0)).div(1 + port.shift(1).fillna(0.0), axis=0)
    return (held - drifted).abs().sum(axis=1)


# 1. price leg -- must be float-exact in all three libraries
e = eng(W)
check("price leg: engine vs bt", e.net, lib_bt(TW.fillna(0.0)), 1e-12)
check("price leg: engine vs vectorbt", e.net, lib_vbt(TW), 1e-12)
check("price leg: engine vs cvxportfolio", e.net, lib_cvx(W), 1e-12)

# 2. carry leg -- float-exact (cvxportfolio dividends; bt on a synthetic total-return price)
e = eng(W, carry=CARRY)
check("carry leg: engine vs cvxportfolio HoldingCost(dividends)", e.net, lib_cvx(W, carry=CARRY), 1e-12)
tr = (1 + R.fillna(0.0) + CARRY.where(R.notna(), 0.0)).cumprod() * P.iloc[0]
check("carry leg: engine vs bt on total-return prices", e.net, lib_bt(TW.fillna(0.0), px=tr), 1e-12)

# 3. linear cost -- equal once the engine's turnover is made drift-aware; the raw gap IS the convention
e = eng(W, BP)
dt = drift_turnover(e.held)
lib = lib_cvx(W, BP)
check("cost: engine.net as booked vs cvxportfolio (raw gap)", e.net, lib, 2e-5)
check("cost: engine + drift-aware turnover vs cvxportfolio", e.gross - dt * BP / 1e4, lib, 1e-6)
check("cost: engine re-booked to the fill print vs bt", e.gross - e.cost.shift(-1).fillna(0.0), lib_bt(TW.fillna(0.0), BP), 2e-5)
check("cost: engine re-booked to the fill print vs vectorbt", e.gross - e.cost.shift(-1).fillna(0.0), lib_vbt(TW, BP), 2e-5)
print(f"     turnover sides/yr: engine {e.turnover.mean() * PPY:.3f}, drift-aware {dt.mean() * PPY:.3f} "
      f"-> {(dt.mean() - e.turnover.mean()) * PPY * BP:.2f} bp/yr not charged at {BP:g} bp/side")

# 4. hold cost on shorts -- equal once re-accrued on calendar time with annual compounding
e = eng(W, short_bp=300.0)
days = pd.Series(idx, index=idx).diff().dt.total_seconds() / 86400.0
act = (-e.held).clip(lower=0.0).sum(axis=1) * (1.03 ** (days / 365.24) - 1).fillna(0.0)
check("hold cost: engine re-accrued ACT/365.24 vs cvxportfolio", e.gross - act, lib_cvx(W, short_bp=300.0), 1e-12)
print(f"     hold-cost total: engine (per print / {PPY}) {e.hold_cost.sum():.5f} vs calendar time {act.sum():.5f}")

# 5. leverage -- bt levers natively; open-source vectorbt cannot (it fills what cash allows, silently)
e = eng(W * 4.0)
check("gross 2.6x: engine vs bt", e.net, lib_bt((W * 4.0).shift(LAG).fillna(0.0)), 1e-12)
check("gross 2.6x: engine vs 4 x vectorbt(w / 4)", e.net, 4.0 * lib_vbt(TW), 1e-12)
print("all external cross-checks passed")
```

After the synthetic panel passes, repeat steps 1–3 once per lane on the **real** panel with one real rule
(the library only needs `prices`, `carry`, `w`), 2–3 years is enough: it catches index, calendar and NaN
surprises the synthetic panel cannot have. The libraries need a complete panel (no NaN prices inside the
tested window).

### 3.4 Tolerances measured (toy panel: 600 prints × 6 instruments, gross 0.64, 40.7 sides/year)

| comparison | max abs diff per print | mean diff per print | Δ Sharpe | reading |
|---|---|---|---|---|
| price leg, 0 bp — engine vs bt / vectorbt / cvxportfolio | 8.0e-16 / 3.2e-16 / 3.1e-16 | ~1e-18 | ≤ 4e-14 | identical; assert 1e-12 |
| carry leg — engine vs cvxportfolio dividends / bt on TR price | 3.9e-16 / 6.5e-16 | ~1e-18 | ≤ 6e-14 | identical; assert 1e-12 |
| timing (B) `exec_prices`, `extra_lag` 0 and 1 — engine vs bt / vectorbt | ≤ 8.6e-16 | ~1e-18 | — | identical |
| gross 2.6×, 0 bp — engine vs bt; vs 4 × vectorbt(w/4) | 1.1e-15; 1.3e-15 | ~1e-17 | ≤ 4e-14 | identical |
| gross 2.6×, 0 bp — engine vs vectorbt **unscaled** | **3.0e-2** | −9.0e-5 | −0.13 | vectorbt cannot lever; no exception raised |
| 5 bp/side — engine as booked vs bt (cost one row earlier in bt) | 4.0e-4 | +6.4e-7 | +4.1e-3 | row convention, same total |
| 5 bp/side — engine re-booked to the fill print vs bt / vectorbt | 7.7e-6 / 6.2e-6 | +6.0e-7 | +3.5e-3 | residual = drift turnover + fees paid from cash; engine slightly optimistic |
| 5 bp/side — engine as booked vs cvxportfolio (same row convention) | 5.4e-6 | +5.8e-7 | +3.4e-3 | same residual |
| 5 bp/side — engine with **drift-aware turnover** vs cvxportfolio | 1.4e-7 | +5.2e-9 | +3.0e-5 | reconciled; assert 1e-6 |
| short hold cost 300 bp/yr — engine vs cvxportfolio | 9.7e-5 | −1.8e-6 | −1.1e-2 | day-count convention (engine charges 5.7 % more on this calendar) |
| same, engine re-accrued `(1+b)^(days/365.24) − 1` | 3.6e-16 | ~1e-18 | 3e-14 | reconciled exactly |
| all legs (5 bp + carry + 300 bp/yr), after both reconciliations | 1.4e-7 | +6.5e-9 | +3.7e-5 | reconciled |
| weekly decisions, 0 bp — engine vs library re-issuing the target **every print** | 6.2e-16 | ~1e-17 | −4e-14 | the engine IS "rebalance to target every print" |
| weekly decisions, 0 bp — engine vs library trading **only on a change** | 6.0e-4 | −4.8e-6 | −2.8e-2 (0.416 vs 0.444) | positions drift between decisions; bt and vectorbt agree with each other to 8 digits |

How much turnover the "rebalanced to target every print" reading hides, same panel, 5 bp/side (V-T, T25):

| decision frequency | engine turnover (sides/yr) | every-print rebalancer (sides/yr) | understated by | uncharged cost |
|---|---|---|---|---|
| target re-sized every print | 40.66 | 40.96 | 0.7 % | 1.47 bp/yr |
| weekly decisions, held constant | 17.95 | 19.02 | 6.0 % | 5.37 bp/yr |
| monthly decisions, held constant | 7.20 | 8.44 | 17.3 % | 6.23 bp/yr |

The hidden drift turnover is bounded by about `Σ|w_i| × mean|r_i − R_portfolio|` per print; it adds in
full on prints where the target did not move and roughly in quadrature where it did. The slower the book
and the more volatile the lane (crypto), the larger its share — measure it with `drift_turnover()`
rather than assume it away. In absolute terms it is a few bp a year here (gross 0.64, vols 8–60 %).

Rule for a real lane: price and carry legs must match to 1e-12; the cost leg must match once the engine's
turnover is replaced by the drift-aware one; the hold-cost leg must match once re-accrued on calendar
time. Anything else is a bug in one of the two.

### 3.5 Known convention mismatches (check these before blaming either side)

1. **Fill timing.** Libraries trade at the row's own price. Give them `w.shift(lag)` (A) or
   `w.shift(extra_lag)` on `F` (B). They verify arithmetic only: that `F` is strictly later than the
   decision print remains a data-layer assertion.
2. **Cost row.** The engine books the cost of the trade made at print `t−1` in row `t`; bt and vectorbt
   book it on the fill row; cvxportfolio's `v.pct_change()` lands it in the same row as the engine.
3. **Last print.** A library executes and charges the trade due on the final print; the engine cannot.
   Drop the last row from every comparison.
4. **Drift turnover.** The engine charges `|held_t − held_{t−1}|` on targets; an account trades the
   difference to its *drifted* position. `engine.py` says so; `realism.simulate_account` is where it is
   charged.
5. **Constant target ≠ untouched position.** In the engine a constant `w` means "rebalanced to target
   every print at zero cost". A venue order flow that trades only on changes holds drifted weights. For
   slow rules decide which one the paper book will do and score that.
6. **Fees from cash.** Libraries pay fees out of cash, so the position after a trade is slightly below
   target: an `O(cost × turnover × |r|)` effect, ~1e-6 to 1e-5 per print at 5 bp.
7. **Day count.** The engine spreads an annual hold cost evenly over prints (`÷ periods_per_year`);
   cvxportfolio accrues `(1 + fee)^(Δt / 365.24 d) − 1` on real elapsed time ("We use the real time
   length of the trading period", `costs.py`); brokers accrue per calendar day. Three-day weekends cost
   three days there, one print here. Of the toy's 5.7 % gap, about 3.6 % is its holiday-free calendar
   (≈ 261 prints a year scored with `periods_per_year = 252`) and 1.5 % is annual compounding
   (`ln(1.03) / 0.03`).
8. **Leverage and cash.** Open-source vectorbt never borrows; check `gross_leverage.max() ≤ 1` before
   using it, or scale. bt and cvxportfolio let cash go negative at zero interest.
9. **NaN targets.** Engine: NaN = flat. vectorbt: NaN = no order (keep the position). bt: fill with 0.
   Identical only when NaNs sit in the warm-up.
10. **Missing prices.** The engine's `refuse` / `zero` policies have no library equivalent; cross-check
    on complete panels only.
11. **Library traps.** bt: `integer_positions=True` default; `initial_capital=1e9` raises a spurious
    infinite-loop error. vectorbt: first call compiles for ~49 s. cvxportfolio: needs a cash column,
    start-of-period returns, `min_history=0d`; `HoldingCost(periods_per_year=…)` is ignored in simulation.
12. **Compounding.** All three report returns on current equity, which is what the engine's per-print
    fractions are; no adjustment needed.

### 3.6 What the external check does not cover

Lot sizes, minimum fees, margin calls, funding timestamps, partial fills, spread vs mid — that is
`realism.py` and, later, a venue demo account. NautilusTrader is the library for an event-level replay if
that is ever wanted — with its own traps: in the smoke test (daily FX bars, shipped `EMACross`) it needed
BID and ASK bars to fill at all, and it filled orders sent from `on_bar` at the signal bar's own close
or, when the strategy listened to the bar stream processed first, at the **previous** bar's close (T12c).
To reproduce the factory's "decide at print s, fill at print s+1" the strategy itself must hold the order
for one bar. Expect per-trade differences of a bar's move, not 1e-12.

### 3.7 Independent checks of the statistics (all V-T, §4 T23, T07, T01b, T27)

| our function (`stats.py` sha `90879ccc…`) | independent implementation | agreement |
|---|---|---|
| `sharpe_ratio`, `max_drawdown`, `cagr` | `empyrical.sharpe_ratio / max_drawdown / annual_return`, `quantstats.stats.sharpe / max_drawdown / cagr` | ≤ 2e-15 |
| `psr` | `quantstats.stats.probabilistic_sharpe_ratio(annualize=False)`; RiskLabAI `probabilistic_sharpe_ratio` | 2.6e-9; exact |
| `expected_max_sharpe` | RiskLabAI `expected_max_sharpe_ratio(n, 0, sqrt(V))` | 1e-14 |
| `deflated_sharpe` | `series.vbt.returns(freq="1D", year_freq="252D").deflated_sharpe_ratio(nb_trials=N, var_sharpe=V*252)` | 8.9e-16 — only with **V × 252** |
| `newey_west_t` (hand-coded) | `statsmodels` `OLS(x, 1).fit(cov_type="HAC", cov_kwds={"maxlags": L})` | ≤ 4.4e-15 at L = 0, 5, 10 |
| `sharpe_ci_bootstrap(block=10)` | `arch.bootstrap.StationaryBootstrap(10, x).conf_int(method="percentile")` | [0.847, 2.061] vs [0.844, 2.059] (Monte-Carlo error) |
| BH / BY / Holm in `mtest.py` | `statsmodels.stats.multitest.multipletests`, `scipy.stats.false_discovery_control` | the two references are identical to each other; `mtest.py` itself was not run here |
| `pbo_cscv` in `mtest.py` | RiskLabAI `probability_of_backtest_overfitting(perf, n_partitions=S)` | not run against `mtest.py` (not my module); reference behaves: 0.000 with a planted winner, 0.46 ± 0.18 on noise |
| `stepm` / `spa` wrappers in `mtest.py` | `arch` directly, fed `-returns` | wrapper not run here; test it with the sign trap: feeding `+returns` gave p = 0.08–0.11 and no winner on a sweep whose planted winner has p = 0.000 |

---

## 4. Smoke-test log

**Environment.** Scratch root
`/tmp/claude-1000/-home-anont-meme/6080f3fd-667a-4f3a-891c-095ad42a53a6/scratchpad/r3/` (session
tmpfs — it will not outlive the session; everything needed to reproduce is in this file). Venvs created
with `uv venv --python 3.12` (CPython 3.12.12); every install was
`UV_LINK_MODE=symlink uv pip install --python <venv>/bin/python "<pkg>==<ver>"`, one at a time. Runs used
`MPLBACKEND=Agg PYTHONDONTWRITEBYTECODE=1` and a `timeout`.

| venv | packages | role | size on disk (symlinks resolved) |
|---|---|---|---|
| `venv` | 161 | repo stack (numpy 2.5.4, pandas 3.1.1, scipy 1.18.1, statsmodels 0.15.0, arch 8.0.0) + bt 1.4.1, ffn 1.4.1, vectorbt 1.2.0 (numba 0.68.1, llvmlite 0.50.0), skfolio 1.12.8, riskfolio-lib 7.4.1, pyportfolioopt 1.6.0, cvxportfolio 1.5.1 (cvxpy 1.9.3), empyrical-reloaded 0.7.2, quantstats 0.0.86, pyfolio-reloaded 0.10.2, backtesting 0.6.6, backtrader 1.9.78.123, lib-pybroker 2.0.2, nautilus-trader 1.231.0, ccxt 4.5.92 | 2.0 GB |
| `venv_legacy` | 15 | RiskLabAI 3.2.0 with statsmodels 0.14.6 | 296 MB |
| `venv_mlfinpy` | 24 | mlfinpy 0.1.2 with numpy 1.26.4, pandas 2.3.3, numba 0.60.0 | 534 MB |
| `venv_bots` | 82 | freqtrade 2026.10 (ccxt 4.5.92, TA-Lib 0.8.3, numpy 2.5.4, pandas 3.1.1) | 641 MB |
| `venv_sdk` | 123 | all broker / exchange SDKs of §1C | 258 MB |
| `venv_ml` | 73 | TA-Lib, pandas-ta-classic, ta, lightgbm, xgboost-cpu, catboost, optuna, polars, duckdb, bottleneck, numba, tsfresh, tsfel | 1.3 GB |
| `venv_pd2` | 93 | pandas 2.3.3 world: zipline-reloaded 3.2.1, statsforecast 2.1.1, pandas-ta 0.4.71b0 (numpy → 2.2.6), darts 0.48.1 | 907 MB |
| `venv_lean` | 42 | lean 1.0.233 | 254 MB |

| id | what ran | result |
|---|---|---|
| T01 | `arch` 8.0.0: `StationaryBootstrap.conf_int`, `optimal_block_length`, `SPA`, `StepM`, `MCS` on 50 formulas × 1,500 prints, two planted winners (true Sharpe 2.0 and 1.5; realised 2.39 and 1.22) | SPA p (lower / consistent / upper) = 0.000 / 0.000 / 0.000; StepM superior = `['f00']`; null sweep (winners removed) SPA p = 0.237 / 0.346 / 0.350, StepM `[]`; MCS(12 models, size 0.10) keeps `['f00']`; Sharpe 95 % CI of f00 [1.61, 3.20]; 2 s per test at 2,000 reps |
| T01b | `arch` details at sweep scale: K = 160, T = 4,500, 1,000 reps, block 20 | 13.0 s (SPA), 13.3 s (StepM); `SPA.better_models(0.05)` → `[np.int64(7)]` (a position), `StepM.superior_models` → `['f007']`; default `block_size` attribute = 67 = sqrt(T); SPA fed returns instead of losses → p = 0.084 / 0.112 / 0.112, winner missed |
| T02 | engine v1 vs **bt** 1.4.1 | 0 bp: max abs diff 7.5e-16; carry via TR price 8.3e-16; gross 2.6× 9.3e-16; 5 bp: see §3.4; first attempt with `initial_capital=1e9` → `RuntimeError: Potentially infinite loop detected` |
| T03 | engine v1 vs **vectorbt** 1.2.0 | 0 bp: 3.0e-16; first call 48.7 s, second 121 ms, 3,474 orders; unscaled leverage 3.0e-2; scaled 1.2e-15 |
| T04 | **skfolio** 1.12.8 | CPCV(10 folds, 2 test, purge 10, embargo 5) on 1,500 obs → 45 splits, 9 test paths; `cross_val_predict(MeanRisk)` → `Population` of 9 paths in 1.8 s; `optimal_folds_number(1500, 100 paths, 3 y train)` = (10, 5); `WalkForward(252, 63)` → `MultiPeriodPortfolio` of 19; EqualWeighted / InverseVolatility / HRP / RiskBudgeting fit and predict |
| T05 | **riskfolio-lib** 7.4.1, **PyPortfolioOpt** 1.6.0 vs skfolio (min-variance, 8 assets) | max weight difference 1.5e-4 (riskfolio) and 1.2e-3 (pypfopt); riskfolio HRP and risk parity ran; `pypfopt.HRPOpt.optimize()` → `AttributeError` on scipy 1.18.1 |
| T06 | stats v1 vs empyrical-reloaded 0.7.2 / quantstats 0.0.86; `multipletests` on 160 p-values | Sharpe, MDD, CAGR, vol ≤ 1.3e-15; PSR 4.7e-9; Bonferroni / Holm / BH reject 3, BY rejects 2; scipy BH and BY identical to statsmodels |
| T07 | **RiskLabAI** 3.2.0 | PBO(80 noise) = 0.702 on one seed; PBO(79 noise + 1 real) = 0.000; 24 seeds of pure noise (T = 800, K = 40, S = 8): mean 0.464, s.d. 0.178, range 0.16–0.79; PSR and E[max SR] equal ours; `PurgedKFold(5)` train sizes 215 / 193 / 193 / 193 / 218 with 30-day labels; `CombinatorialPurged(6, 2)` → 15 splits |
| T08 | **backtesting.py** 0.6.6 | SMA(10/30) on 1,000 synthetic bars: 35 trades, Sharpe 0.53, `optimize` over a 6-point grid ran |
| T09 | **backtrader** 1.9.78.123 | `order_target_percent` strategy ran (final value 1,214,511, Sharpe 0.835, max DD 11.4 %); `python -W error -c "import backtrader"` → `SyntaxError: invalid escape sequence '\*'` |
| T10 | engine v1 vs **cvxportfolio** 1.5.1, all legs | price 3.3e-16; carry 4.0e-16; cost raw 5.4e-6, drift-aware 1.4e-7; hold cost raw 9.7e-5, re-accrued 4.6e-16; all legs reconciled 1.4e-7; 4.7 s per run |
| T11 | **PyBroker** 2.0.2 | 2 symbols × 600 bars, 66 trades, bootstrap CIs computed; 19.6 s |
| T12 | **NautilusTrader** 1.231.0 | import 4 s; `BacktestEngine` + `EMACross` on 750 daily EUR/USD bars: BID bars only → **0 fills, no error**; BID + ASK bars → 38 fills, 19 positions, 0.33 s |
| T12c | NautilusTrader fill price of a market order sent from `on_bar` (bars with an overnight gap so open ≠ previous close; first possible signal = 30th bar, 2021-02-11; first fill stamped 2021-02-11 in all four runs) | strategy on BID bars, BID stream added first → 37 of 38 fills at the **previous** bar's close; strategy on BID bars, ASK stream added first → 38 of 38 at the **signal bar's own close**; strategy on ASK bars, BID first → 38 of 38 same-bar close; strategy on ASK bars, ASK first → 37 of 38 previous close. No variant filled at the next bar |
| T13 | **freqtrade** 2026.10 | `freqtrade --version` (ccxt 4.5.92); `list-exchanges` → 81 exchanges (the supported subset is quoted in §1A); `list-freqaimodels` → `ModuleNotFoundError: No module named 'datasieve'`; hyperopt losses → `No module named 'optuna'` |
| T14 | **ccxt** 4.5.92 | 104 REST / 76 WS classes; no `bitmex`. `has` matrix: `krakenfutures` (swap, funding rate/history, positions, setLeverage, sandbox, ws); `kraken` (spot only, no sandbox); `hyperliquid` (spot + swap, funding, leverage + margin mode, testnet, ws); `okx` / `myokx` (`eea.okx.com`; swap, funding, sandbox); `bybit` (all; testnet) / `bybiteu` (spot; testnet); `bitvavo` (spot only, no sandbox); `deribit` (swap, future, option, funding history, `test.deribit.com`); `coinbase` (spot + swap + future flags, no funding methods, no sandbox); `onetrading`. Live keyless: `krakenfutures` 219 markets (209 swaps), `fetch_funding_rate("BTC/USD:USD")` = 5.084e-07 per 1 h; `hyperliquid` 868 markets (561 swaps), funding 1.25e-05 per 1 h. Kraken's own `historical-funding-rates` endpoint at 14:00Z: `relativeFundingRate` 5.0898e-07 = ccxt's history value (its `fundingRate` field, 0.0375, is the absolute one) |
| T15 | SDK imports in one venv | OK: hyperliquid-python-sdk 0.24.0, pybit 5.17.2, python-okx 0.4.4, python-kraken-sdk 3.5.1, ib_async 2.1.0, ibind 0.2.3, oandapyV20 0.7.2, alpaca-py 0.45.0, saxo_openapi 0.6.0, trading-ig 0.0.25, ctrader-open-api 0.9.2, mt5linux 1.1.1, py-clob-client 0.34.6, py-clob-client-v2 1.2.1, solders 0.29.0, solana 0.41.0, web3 8.0.0, python-bitvavo-api 1.4.3, coinbase-advanced-py 1.8.4. Failed: `MetaTrader5` (no Linux wheel); `v20` until PyYAML was added. `uv pip check` afterwards: 6 incompatibilities (websockets 13.1 vs web3 ≥ 14 / python-kraken-sdk ≥ 14.1 / solana ≥ 16; eth-account 0.14.0 and eth-utils 6.0.0 vs hyperliquid-python-sdk; requests 2.32.3 vs ibind ≥ 2.33) |
| T16 | indicator / ML stack on the repo's numpy / pandas | all 13 OK: TA-Lib 0.8.3, pandas-ta-classic 0.9.0, ta 0.11.0 (RSI 34.908 in all three), lightgbm 4.7.0, xgboost-cpu 3.4.1, catboost 1.2.10, optuna 5.0.0, polars 2.1.0, duckdb 2.0.0, bottleneck 1.6.0, numba 0.68.1, tsfresh 0.21.2, tsfel 0.2.0 |
| T17 | pandas-2 world | zipline-reloaded 3.2.1 imports (bundles csvdir, quandl); statsforecast 2.1.1 AutoARIMA forecast; pandas-ta 0.4.71b0 RSI; darts 0.48.1 ExponentialSmoothing, torch not installed |
| T18 | **lean** 1.0.233 | `lean --version`, `lean --help` (backtest / optimize / research / live "using Docker"); no LEAN image on the host; nothing pulled |
| T19 | vectorbt DSR vs stats v1 | equal to 10 digits with `var_sharpe × 252`; off (0.9999 vs 0.8843) with per-print V |
| T20 | engine **v2** (sha `58262e07…`) vs bt + vectorbt + cvxportfolio, 7 blocks | the §3.4 table |
| T21 | engine v2 timing (B) vs bt + vectorbt; guard rails | `extra_lag` 0 and 1: ≤ 8.6e-16; `exec_prices` without the data-layer flag → `Refused`; `exec_prices` identical to `prices` → `Refused`; `lag = 0` → `Refused` |
| T22 | speed | `backtest` 2.98 ms (600×6), 8.64 ms (4,500×9), 32.05 ms (4,500×41); `fast_net_returns` 160 formulas × 4,500 × 9: 813 ms |
| T23 | stats **v2** (sha `90879ccc…`) vs empyrical, quantstats, vectorbt, statsmodels HAC, arch bootstrap | the §3.7 table |
| T24 | `xcheck_external.py` (§3.3) against `/home/anont/meme/scripts/factory/engine.py`, read-only: at 14:50:51 UTC (sha `58262e07…`) and again at 15:04:25 UTC with the code block extracted from this file (sha `25b9f3f9…`) | 14 checks OK, exit 0, identical numbers both times |
| T25 | drift turnover hidden by constant targets (engine v2, toy panel, 5 bp/side) | the second table of §3.4 |
| T27 | RiskLabAI 3.2.0 vs stats **v2** | PSR at SR0 = 0 and 0.02: difference 0.0; E[max SR] (N = 160): 1.3e-14 |

**Not installed, by design** (resolver dry-run only): jesse 3.6.1 (65 packages, pandas 2.2.3, ray),
lumibot 4.6.48 (189 packages), hummingbot 20260922 (112 packages, numpy 2.2.6), pyqlib 0.9.7 (110
packages), FinRL, blankly, fastquant, pysystemtrade (git only), the full `xgboost` wheel
(`nvidia-nccl-cu13`), the LEAN Docker image.

**Incidents and residue.**
- `backtrader`'s `cerebro.plot()` opened a blocking Tk window on the desktop twice (once until the 120 s
  tool timeout, once for 20 s) before `MPLBACKEND=Agg` was set for every run. Nothing else was affected.
- `~/.cache/uv` grew from 15 GB to 18 GB (wheels unpacked on disk; `/home` had 111 GB free). The scratch
  venvs are symlinks into it; they die with the session. Reclaiming the 3 GB is the owner's call — the
  cache is shared with other projects and was not cleaned.
- Memory: `free` showed 6.6–8.2 GiB available at every check; no per-process RSS was measured.
- My first comparison of costs was wrong by a whole trade on one row until the last-print rule (§3.5
  item 3) was understood; the log keeps the corrected runs only.

**Not verified, stated plainly.** No live or paper order was sent through any SDK; ib_async / ibind were
import-tested only (no Gateway, no account); `mtest.py`, `portfolio.py`, `realism.py`, `xcheck.py` were
not executed by me; the engine's `missing_return="zero"` path and per-instrument cost vectors were not
cross-checked externally; convention (B) was not run through cvxportfolio; GitHub star counts and "last
pushed" dates are single reads of today.

---

## 5. Sources (all accessed 2026-11-10)

**Primary, machine-read (V-M).**
- PyPI JSON API `https://pypi.org/pypi/<name>/json` for: vectorbt, nautilus_trader, lean, backtesting, bt,
  ffn, zipline-reloaded, backtrader, freqtrade, jesse, hummingbot, pyqlib, finrl, lumibot, blankly,
  lib-pybroker, fastquant, skfolio, riskfolio-lib, pyportfolioopt, cvxportfolio, arch, statsmodels, scipy,
  quantstats, pyfolio-reloaded, empyrical-reloaded, alphalens-reloaded, mlfinpy, RiskLabAI, timeseriescv,
  tsbootstrap, recombinator, model-confidence-set, scikit-learn, ccxt, hyperliquid-python-sdk, pybit,
  python-okx, python-kraken-sdk, ib_async, ib_insync, ibapi, ibind, ibeam, oandapyV20, v20, alpaca-py,
  saxo_openapi, trading-ig, ctrader-open-api, MetaTrader5, mt5linux, py-clob-client, py-clob-client-v2,
  solders, solana, web3, python-bitvavo-api, coinbase-advanced-py, TA-Lib, pandas-ta, pandas-ta-classic,
  ta, tsfresh, tsfel, lightgbm, xgboost, xgboost-cpu, catboost, optuna, darts, statsforecast, polars,
  duckdb, numba, llvmlite, bottleneck, numpy, pandas, pyarrow, APScheduler, streamlit,
  python-telegram-bot, apprise, keyring, python-dotenv, structlog, cvxpy, capitalcom, python-capital,
  pyt212, python-trading212, trading212py. HTTP 404 (not on PyPI): pysystemtrade, vectorbtpro, pypbo,
  mlfinlab.
- GitHub REST API `https://api.github.com/repos/<owner>/<repo>` (+ `/releases/latest`, `/releases`, raw
  files) for: polakowo/vectorbt, nautechsystems/nautilus_trader, QuantConnect/Lean, QuantConnect/lean-cli,
  kernc/backtesting.py, pmorissette/bt, stefan-jansen/zipline-reloaded, mementum/backtrader,
  freqtrade/freqtrade, jesse-ai/jesse, hummingbot/hummingbot, pst-group/pysystemtrade (README,
  `pyproject.toml`, `docs/production.md`), microsoft/qlib, AI4Finance-Foundation/FinRL, Lumiwealth/lumibot,
  blankly-finance/blankly, edtechre/pybroker, enzoampil/fastquant, skfolio/skfolio, dcajasn/Riskfolio-Lib,
  PyPortfolio/PyPortfolioOpt, cvxgrp/cvxportfolio, bashtage/arch, esvhd/pypbo (README),
  hudson-and-thames/mlfinlab, RiskLabAI/RiskLabAI.py, baobach/mlfinpy, ranaroussi/quantstats,
  stefan-jansen/pyfolio-reloaded, stefan-jansen/empyrical-reloaded, ccxt/ccxt,
  hyperliquid-dex/hyperliquid-python-sdk, bybit-exchange/pybit, okxapi/python-okx,
  btschwertfeger/python-kraken-sdk, ib-api-reloaded/ib_async, erdewit/ib_insync, Voyz/ibind
  (`docs/oauth/oauth_1a.md`), Voyz/ibeam, hootnot/oanda-api-v20, oanda/v20-python, alpacahq/alpaca-py,
  hootnot/saxo_openapi, ig-python/trading-ig, spotware/OpenApiPy, Polymarket/py-clob-client,
  Polymarket/py-clob-client-v2, kevinheavey/solders, michaelhly/solana-py, ApeWorX/web3.py,
  bitvavo/python-bitvavo-api, coinbase/coinbase-advanced-py, TA-Lib/ta-lib-python,
  xgboosted/pandas-ta-classic, bukosabino/ta, lucas-campagna/mt5linux (README),
  TauricResearch/TradingAgents, virattt/ai-hedge-fund, AI4Finance-Foundation/FinRobot,
  AI4Finance-Foundation/FinGPT, HKUDS/AI-Trader, NoFxAiOS/nofx. `twopirllc/pandas-ta` → not found
  (`https://github.com/twopirllc/pandas-ta` HTTP 404; `www.pandas-ta.dev` no DNS record).
- Installed distributions: vectorbt 1.2.0 `dist-info/licenses/LICENSE.md` and `METADATA`;
  cvxportfolio 1.5.1 `costs.py`; bt 1.4.1 `core.py`.
- Public market data: `https://futures.kraken.com/derivatives/api/v3/historical-funding-rates?symbol=PF_XBTUSD`,
  `https://futures.kraken.com/derivatives/api/v3/tickers/PF_XBTUSD`; Hyperliquid `/info` via ccxt and the SDK.
- Kansspelautoriteit decision PDF (HTTP 200, 330 kB, not read in full):
  `https://kansspelautoriteit.nl/sites/default/files/2026-02/2026-01-20_22310_LOD%20Adventure%20One%20SQQ%20Inc._sanctiebesluit.pdf`;
  NOS `https://nos.nl/l/2602855` (published 2026-02-17).

**Project pages read through the fetch tool (V-D†).**
- vectorbt README `https://raw.githubusercontent.com/polakowo/vectorbt/master/README.md`; vectorbt PRO
  membership `https://vectorbt.pro/become-a-member/`.
- NautilusTrader integrations `https://nautilustrader.io/docs/latest/integrations/`.
- QuantConnect pricing `https://www.quantconnect.com/pricing/` and `https://www.quantconnect.com/pricing.md`.
- freqtrade `https://www.freqtrade.io/en/stable/` and `https://www.freqtrade.io/en/stable/exchanges/`.
- pysystemtrade README `https://raw.githubusercontent.com/pst-group/pysystemtrade/develop/README.md`.
- Jesse `https://docs.jesse.trade/docs/supported-exchanges.html`, `https://docs.jesse.trade/docs/livetrade.html`.
- Hummingbot `https://hummingbot.org/exchanges/`; Lumibot `https://lumibot.lumiwealth.com/brokers.all.html`.
- Trading 212 `https://docs.trading212.com/api`.
- ibind README `https://raw.githubusercontent.com/Voyz/ibind/master/README.md`; ib_async README
  `https://raw.githubusercontent.com/ib-api-reloaded/ib_async/main/README.md`.
- OANDA `https://developer.oanda.com/rest-live-v20/introduction/`.
- Saxo `https://www.developer.saxo/openapi/learn`; cTrader `https://help.ctrader.com/open-api/`.
- Jupiter `https://developers.jup.ag/docs/`.
- arXiv abstracts: `https://arxiv.org/abs/2505.07078` (FINSABER), `https://arxiv.org/abs/2510.02209`
  (StockBench), `https://arxiv.org/abs/2605.16895` (The Alpha Illusion), `https://arxiv.org/abs/2412.20138`
  (TradingAgents); TradingAgents project page `https://tradingagents-ai.github.io`.

**Third-party / search snippets (CLAIM).**
- Protos, 2025-11-04, `https://protos.com/llm-crypto-trading-contest-finds-llms-cant-trade-crypto` (read in
  full through the fetch tool; Alpha Arena Season 1 figures).
- KuCoin news flash 2026-05-06 citing CoinDesk:
  `https://www.kucoin.com/news/flash/ai-trading-models-struggle-in-live-market-tests-majority-of-systems-report-losses`.
- LiveTradeBench `https://arxiv.org/abs/2511.03628` (seen through search results only).
- Alpha Arena Season 1.5 coverage (forklog, aigazine; figures disagree: +10.1 % vs +12.1 %).
- Kraken EEA derivatives: Business Wire 2025-05-20 "Kraken Launches Europe's Largest Regulated Futures
  Offering" (title seen in search results).
- OANDA EU entity: OANDA regional pages and financefeeds coverage (titles seen in search results).
- OKX "X-Perps" and Bybit EU licence status: affiliate / review sites.
- Hyperliquid restricted jurisdictions: third-party summaries of its Terms of Use.

**Blocked.** IBKR Campus API pages (`interactivebrokers.com/campus/…`) returned HTTP 403 to the fetch
tool; `thinkadvisor.com` 403; `nof1.ai` blog URL 404; `www.pandas-ta.dev` unresolvable.
