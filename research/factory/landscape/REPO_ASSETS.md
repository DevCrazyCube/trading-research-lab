# REPO_ASSETS — read-only audit of everything earlier models built in `/home/anont/meme`

**Author:** Claude (audit agent, model `claude-fable-5-2`). **Written:** 2026-11-10 ≈14:25 UTC.
**Status:** audit report for the conductor. Nothing in the repo was edited, created, deleted, moved or
restored to produce it; this file is the only write. No network call, no service start, no test suite.

**Labels used.** **[fact]** = verified in this audit by reading code/files or by a read-only command
(the command class is named in §9). **[hyp]** = working hypothesis, not verified. **[opinion]** = my
engineering judgement. **[owner]** = a decision only the owner can make.

**Verdict vocabulary.** REUSE-AS-IS · REUSE-WITH-CHANGES · REFERENCE-ONLY (read it, copy the idea, do not
import it) · RETIRE (no role in the new programme; deletion is an owner decision, never mine).

---

## 0. One-page summary

| # | Area | State today | Quality | Tests | Verdict | Entry point → what must change |
|---|---|---|---|---|---|---|
| 1a | T2 bar engine `scripts/trading_bot/engine.py` (+ `strategies.py`, `walkforward.py`, `runner.py`) | imports and runs; self-contained | high: exact `Fraction` accounting, lag ≥ 1 enforced, truncation + scramble audit | 113 in `tests/test_t2_backtest_harness.py` (not run, §9) | **REFERENCE-ONLY** for the factory (single symbol, per-bar Python loop); **REUSE-AS-IS as a differential-test oracle** | `run_backtest` `engine.py:552`, `lookahead_audit` `:448` |
| 1b | Cost provenance `costs.py` | generic models work; the two measured legs (M0 auction, T18 exit) **refuse** because their JSON was deleted | high, but equity-specific (per-share commission, micro-dollars) | 25 tests (same file) | **REUSE-WITH-CHANGES** (the pattern + the measured numbers) | `SlippageProvenance` `:106`, `CostComponent` `:230`, `split_turnover` `:259`, `stress_ladder` `:1077` |
| 1c | Alpaca loader `data.py` | code works; cache dir deleted, so every call needs the network | good guards (host allow-list, manifest, level/return caveat) | 7 | **REUSE-WITH-CHANGES** | `load_bars` `:214` → batch symbols, parquet, incremental end date |
| 1d | **Alpaca PAPER order rail** `t4_forward.py` `PaperAccount` | **functional end to end** (2 real paper POSTs, 1 reconciled fill, 2026-08-17/18); now disabled: its authorisation, frozen-rule and cost files were deleted | high; idempotent `client_order_id`, non-fill handling, owner gate | 60 in `tests/test_t4_forward.py` (not run; they load files that are now deleted) | **REUSE-WITH-CHANGES** | `PaperAccount` `:561–658`, `assert_owner_authorised` `:669`, `reconcile_fill` `:1178` → extract, make multi-symbol |
| 1e | Forward loggers: `basket_forward.py` (2,617 lines), `forward_eval.py`, `prefrv_forward.py`, `cefbot/` | all refuse (frozen specs/ledgers deleted) | careful but bespoke; one monolith per strategy | only T4 + forward_eval have pytest | `cefbot/` = **REUSE-WITH-CHANGES** (template); the rest **REFERENCE-ONLY** | `cefbot/strategy.py:64`, `bot.py:166`, `evaluate.py:51` |
| 1f | Sweep engines (`perpmicro_*`, `xll*`, `newterr_*`, `ts_sweep*`, `cal_*`, `rv_*`, ~40 files) | code intact; **every input cache deleted** | good discipline, but each theme re-implements engine + null + audit | none (in-file `selftest` only) | **REFERENCE-ONLY** | patterns listed in §1.4 |
| 1g | Loaders (Binance archive, FRED, Yahoo, Alpaca, DoltHub, Deribit, IBKR borrow) | code intact; caches gone; 31 scripts `mkdir` their cache at import | uneven; `t23_collect.py` is the best | none | **REUSE-WITH-CHANGES** (3–4 of them) | table in §1.6 |
| 1h | Statistics (DSR, permutation, bootstraps, HAC) | DSR + permutation tested; bootstraps and HAC are ad-hoc copies | DSR good; HAC = five untested `nw_t` copies | DSR/permutation only | port tests, not code | table in §1.5 |
| 1i | `predmarket/`, `newsdesk/`, `memebot*/`, `memestream/`, `sniper/`, `aftershock/`, `eventstudy/`, `postures/` | dead or refusing | varies | selftests | **RETIRE** for the factory, except `postures/c2_collect.py` (FRED FX map) | §1.7 |
| 2 | `apps/trader` (+ `trader_mc`, `trader_backups`) LLM paper trader | **stopped**; last data 2026-10-10 18:42Z; unclean stop (WAL + pid files left) | very high engineering quality, deeply memecoin-specific (4,030-line `contracts.py`) | ~1,750 backend tests reported 10-04 (not run) | **REFERENCE-ONLY** as a host for other venues; keep as-is for memecoins **[owner]** | patterns in §2.3 |
| 3 | `scripts/agent_graph` durable tick supervisor | off since 2026-10-25; 490 ticks ran | 24 KB bash harness with layered repairs; `loop.py status` **crashes** | none | **RETIRE** as scheduler; keep 3 patterns | §3 |
| 4 | `scripts/scanner`, `smartmoney`, `holdco_rv`, `t28_dualclass`, `t29_crosslist`, dashboards, `ui/`, `config/`, `docs/`, `skills/`, `tests/` | scanner state deleted; rest dormant | mixed | `tests/`: 99 files, ~4,600 test functions, almost all Pump.fun pipeline | **RETIRE / REFERENCE-ONLY**; `tests/_netguard.py` = **REUSE-AS-IS** | §4 |
| 5 | Hygiene | 15 GB repo; 2 months of work uncommitted; `.git` holds salvageable copies of deleted data that a `git gc` would probably destroy | — | — | **[owner]** decisions listed in §5.7 | §5 |
| 6 | Process (prereg/freeze, cost provenance, scramble audit, forward register) | protocols survive in git history | sound ideas, self-defeating thresholds | — | **REUSE-WITH-CHANGES** | §6 |

**Six things the conductor should know before designing further** (each is expanded below):

1. **[fact] FX, crypto trend and turn-of-month were already tested here.** The claim in
   `research/factory/README.md` and `DECISIONS.md` (2026-11-10) that forex was never tested is wrong for carry:
   `ts_sweep2.py` family I ran 17 FX-carry formulas on six CME FX futures (design 2007–2018, held out
   2019–2026): noise after a data fix. `t34_crypto_tsmom.py` ran daily TSMOM + Donchian on the top-20
   Binance perps: in-sample Sharpe 1.00, held-out 0.12. `cal_sweep.py` ran turn-of-month on SPY/TLT/IWM/EFA
   inside a 100-formula calendar family judged noise. Details and sources in §1.8.
2. **[fact] A working Alpaca PAPER order rail exists** (`t4_forward.py`), and it measured two things the
   factory needs: market-on-close orders **expire unfilled** on Alpaca paper, and one near-close market
   fill landed **5.07 bp** worse than the official close (one observation).
3. **[fact] Every data cache is gone.** `research/data/` holds only `aftershock/` and an empty
   `memebot_cache/`. All loaders must re-download. 31 old scripts create their cache directory at import
   time, which would silently recreate deleted lane directories (the open T110 owner question).
4. **[fact] `.git` contains unreferenced copies of some deleted data**, including the first 16 daily T31
   Deribit snapshots, 15 raw T30 borrow files, the T4 and BASKET1 ledgers through 2026-10-02 and seven
   US-equity panel caches. The incident note calls T30/T31 "unrecoverable" and BASKET1/T4 "5 weeks
   behind"; both are too pessimistic for the period up to early September / early October.
   **[hyp]** a `git gc` would delete them (they are older than git's default 2-week prune window). §5.3.
5. **[fact] The only tested, shared statistics are DSR, a timing-permutation test and paired excess.** HAC
   exists as five untested copy-pasted `nw_t` functions; every bootstrap/null lives inside one sweep script.
6. **[opinion] The old gates could not pass a real but modest edge.** A true Sharpe-1.0 strategy had about
   a 26 % chance of clearing the old bar on a 4.6-year holdout; the forward tests were specified to need
   decades. Numbers in §6.3.

---

## 1. `scripts/trading_bot/` (253 top-level `.py`, 10 sub-packages, 481 MB of which ≈390 MB is runtime logs)

### 1.1 The T2 harness: `engine.py`, `costs.py`, `frozen.py`, `data.py`, `paper.py`, `stats.py`, `walkforward.py`, `runner.py`, `strategies.py`

**[fact] State.** `import scripts.trading_bot` succeeds (checked with `python3 -B`, no bytecode written).
`frozen.py:48–72` loads `scripts/b22b_slippage_harness.py` at import and refuses unless its sha256 equals
the value in `research/B22B_SLIPPAGE_PREREGISTRATION.json`; both files exist and the hash matches
(`a0f1b4c4…`). Consequence: editing or deleting either file makes the **whole package** fail at import.

**[fact] `engine.py`.** One symbol per run. A strategy is a class with `on_bar(view, state)` returning a
target exposure (`:263`). Three protections: a clamped `PointInTimeView` (`:171`), `execution_lag_bars ≥ 1`
with no override (`:89`, `:570`), and `lookahead_audit` (`:448`), which re-runs the strategy with the future
**deleted** (truncation probe, deterministic) and with the future **regenerated** (`_scramble`, `:411`).
Fills at the next bar's open, marks open-to-open, per-bar returns are exact `Fraction`s, turnover is split
into entry and exit legs (`costs.split_turnover`, `costs.py:259`). The docstring records two earlier bugs
the negative control caught (a scramble that preserved candle direction; a factory that kept the real
series).

**[opinion] Verdict: REFERENCE-ONLY as the factory engine, REUSE-AS-IS as an oracle.** It cannot run a
50-instrument book or an 80-rule sweep (pure-Python loop over `Fraction`s, one symbol). The new
`scripts/factory/audit.py` draft already carries both probes. The best use of the old engine is a
differential test: feed the factory engine a one-instrument panel of **opens** at lag 1 and require the
same net returns as `run_backtest` on the same bars (two independent implementations, one exact).

**[fact] `costs.py` (1,125 lines).** Every `CostComponent` needs a non-empty `source` string and a
`SlippageProvenance` (`:106`); `assert_available()` (`:149`) refuses a "measured" label unless the result
file exists **and** covers the sample it claims. Checked today:

| constructor | result |
|---|---|
| `retail_taker_costs()` `:540`, `zarattini_paper_costs()` `:485`, `zero_cost_model()` `:1109` | OK |
| `b22b_measured_costs()` `:1007`, `measured_extra_slippage()` `:618`, `measured_borrow_annual()` `:755` | OK (`research/B22B_SLIPPAGE_RESULT.json`, `research/B22G_BORROW_COST.json` still exist) |
| `measured_auction_leg()` `:852` | **Refused**: `research/trading_bot/M0_AUCTION_FILLS.json` absent |
| `measured_exit_leg_t18()` `:916` | **Refused**: `research/trading_bot/T18_EXIT_MEASUREMENT.json` absent |

Both missing files are in git `HEAD` (`git show HEAD:research/trading_bot/M0_AUCTION_FILLS.json`).
The factory README's ETF cost line cites `M0_AUCTION_FILLS.md` as provenance; that document is also only in
git history now.

**[opinion] Verdict: REUSE-WITH-CHANGES.** Keep the four ideas (source string mandatory; measured label
gated on an artifact; per-side charging; a stress ladder next to every number). Do not import the class:
it prices per-share commission in integer micro-dollars and has no notion of FX pips, funding or
financing. Carry over the **measured numbers** with their provenance instead (§7, item 5).

**[fact] `data.py`.** Alpaca market-data host only, by parsed hostname (`:60–119`); fully paged; one
JSON cache file per `(symbol, timeframe, start, end, feed, adjustment)` (`:231`); manifest records
adjustment mode and a survivorship warning. Limits: one symbol per request; the cache key includes the
end date, so extending a window by a day refetches everything; `DEFAULT_CACHE_DIR`
`research/data/trading_bot_cache` (`:54`) no longer exists.

**[fact] `paper.py`.** `Order` schema with whole shares only (`:50`), `orders_for_target` rounds the share
count down (`:77`), `PaperBroker` accepts only `paper-api.alpaca.markets` and refuses the live host at
construction (`:110`). `submit()` **refuses by design** (`:129`); the real submission lives in
`t4_forward.py`.

### 1.2 The T4 path — is the paper order rail functional?

**[fact] Yes.** `t4_forward.py` (1,571 lines) is a one-rule forward bot (SPY volatility targeting, rule
frozen in `T13_FROZEN_CONFIG.json`). The reusable part is small:

| piece | location | what it does |
|---|---|---|
| `PaperAccount` | `t4_forward.py:561–658` | `clock()`, `account()`, `position(symbol)`, `order(id)`, `place_near_close_market(order, client_order_id)` → `POST /v2/orders`, `type=market`, `time_in_force=day` |
| owner gate | `assert_owner_authorised()` `:669`; path `AUTHORISATION_PATH` `:162` | refuses unless `research/trading_bot/T4_OWNER_AUTHORISATION.json` says `paper_order_submission_authorised: true` |
| time guards | `ACTION_WINDOW_ET` `:201` (15:50–15:58 ET), `SUBMIT_HARD_CUTOFF_ET` `:208` | a DAY market order sent after the bell would fill next morning |
| idempotency | `client_order_id = f"t4-{rule_id}-{session_date}"` `:1059` | Alpaca rejects a duplicate id, so a retry cannot double a position |
| fill reconciliation | `reconcile_fill()` `:1178` | filled → keep; terminal with zero fill → drop the pending weight; still live → ask again next run |
| secret scrubbing | `_scrub()` `:661`, `_assert_clean()` `:1316` | credentials never reach a log or ledger row |
| cron wrapper | `t4_entrypoint.sh` | `--skip-outside-window --skip-if-logged`; default mode dry-run |

**[fact] Evidence it worked** (ledger in git `HEAD`, 19 rows, 2026-08-17 → 09-09):

- 2026-08-17: `tif=cls` (market-on-close) order `3a5487f8…` accepted, then **expired unfilled** at the
  close. Alpaca's paper simulator does not run the closing auction (`T4_FORWARD.md` §1a).
- 2026-08-18 15:50:01 ET: market DAY order for 94 SPY, filled at 767.838724; official close 767.45;
  recorded shortfall **+5.065 bp** (adverse). One observation, not a distribution.
- Rows are `mode=submit` through 2026-08-25 and `mode=dry-run` from 2026-08-26. **[hyp]** Cause: in the
  current crontab the line `T4_MODE=submit` sits **below** the t4 job line, and cron applies environment
  lines only to entries after them (the crontab's own T78/T79 comments record that `CRON_TZ` is
  positional). I found no decision entry explaining the switch.

**[fact] Why it is disabled today.** The directory `research/trading_bot/` was deleted on 2026-10-15 and
now contains only `logs/`. Missing: the authorisation file, `T13_PREREGISTRATION.md`,
`T13_FROZEN_CONFIG.json`, `T4_FORWARD_PREREGISTRATION.md`, the ledger and state, `M0_AUCTION_FILLS.json`.
All are in git `HEAD` as of 2026-09-10; a later ledger (36 rows, last session 2026-10-02) survives only as
an unreferenced git object (§5.3). The cron lines are commented out.

**[fact] What is owner-gated.** Paper submission needs the authorisation file (owner-created). Live
trading is unreachable by hostname, not by policy.

**[opinion] Verdict: REUSE-WITH-CHANGES.** Extract `PaperAccount`, the gate and the reconciliation state
machine (≈250 lines) into a factory paper runner; do not reuse the T13-specific session logic. Three
things must change for a multi-asset book:

1. Positions and orders per symbol (`GET /v2/positions`, one `client_order_id` per strategy-date-symbol).
2. **Share rounding.** `orders_for_target` floors to whole shares. The T4 test sized against ≈$100k paper
   equity (94 SPY ≈ 72 % weight). At €5k and 2 % per name, any ETF above $100 gets zero shares. The runner
   needs notional (fractional) orders for longs or a universe filter by price; shorts cannot be fractional.
3. The authorisation path must not live under `research/trading_bot/` (deleted tree, T110).

### 1.3 Forward loggers and the register

| asset | what it is | state | verdict |
|---|---|---|---|
| `basket_forward.py` (2,617 lines) | BASKET1: 14 frozen legs logged as hypothetical P&L, **no orders**; spec hash-checked at load | refuses: `BASKET_FORWARD_FROZEN.json` deleted (in `HEAD` as of 09-10, 13 ledger rows) | **REFERENCE-ONLY**: every leg is hard-coded in one file |
| `forward_eval.py` (1,357 lines) | read-only evaluator; `_refuse_if_protected()` `:157` refuses to write any ledger/state/prereg path | T4/T13-specific; inputs deleted | **REFERENCE-ONLY** (keep the write-guard idea) |
| `FORWARD_REGISTER.json` (git `HEAD` only) | one entry per forward test: rule, prereg sha256, ledger path, declared trials, minimum before a verdict; retired entries are kept forever | deleted on disk | **REUSE-WITH-CHANGES** (the schema) |
| `cefbot/` (775 lines: `strategy.py`, `bot.py`, `evaluate.py`, `__main__.py`) | weekly paper bot for the CEF discount tilt | refuses (prereg deleted) | **REUSE-WITH-CHANGES**: cleanest template (frozen constants + `assert_frozen()` `strategy.py:64`; one idempotent cycle `bot.py:166`; kill rule + score `evaluate.py:51,70`) |
| `prefrv_forward.py` (1,084 lines) | preferred-share RV runner built blind, hash-pinned | data lane deleted | **REFERENCE-ONLY** |
| `t30_borrow_collect.py` | daily IBKR `usa.txt` snapshot (fee rate, availability per symbol) | code fine; ledger deleted | **REUSE-WITH-CHANGES** (§7 item 6) |
| `t31_deribit_collect.py`, `t33_us_options_collect.py`, `t45_etf_liquidation_collect.py` | forward option-chain and event collectors | code fine; ledgers deleted (T31's first 16 days survive in `.git`, §5.3) | **REFERENCE-ONLY** unless an options lane reopens |
| `input_recency_alarm.py` (401 lines) | reads the **age of the newest input row** of each live instrument against its cadence (`evaluate` `:210`) | works; reports all 13 old instruments missing | **REUSE-WITH-CHANGES** (point it at factory ledgers) |
| `t48_datapath_audit.py` | per-collector input-surface checks (recency, duplicate-day detection) | inputs deleted | **REFERENCE-ONLY** |

### 1.4 Sweep engines and panels

**[fact]** About 40 files, 300–1,100 lines each, one per theme. Each contains its own vectorised scorer, its
own multiple-testing null, a design/holdout wall and usually a selftest. None has pytest coverage. All read
caches under `research/data/*_cache` that no longer exist.

**[opinion] Verdict: REFERENCE-ONLY.** The factory has one shared engine, which is the right structure.
Ideas worth copying, with where to read them:

| idea | where |
|---|---|
| Null that keeps cross-formula correlation: one shared time shift per draw, max over the family | `xll_sweep_crypto.py:221` (`null_sharpes`), `ts_sweep.py:708` (`null_max`) |
| Pooled bar across two batches of the same theme | `cal_pooled_null.py` |
| Prefix-identical look-ahead audit for a vectorised weight matrix | `xll_audit_equity.py`, `xll2_audit_intraday.py` |
| Planted-edge / no-edge harness selftest | `rv_selftest.py`; `newterr_xseq_sweep.py selftest` |
| Post-freeze controls: placebo window and "always-on" (gate removed) | `cal_control2.py` |
| Extra-lag kill test for stale prints | `ts_sweep2.py` (the FX artifact, §1.8) |
| Point-in-time universe by trailing volume | `perpmicro_sweep.py` header |

### 1.5 Statistical utilities that already exist

| utility | location | tested? |
|---|---|---|
| Deflated Sharpe, expected max Sharpe, cross-trial variance | `stats.py:235`, `:203`, `:228` | **yes**: `tests/test_t2_backtest_harness.py:683–790`, incl. an independent Bailey–López de Prado formula check (`:739`) |
| Timing permutation test (add-one corrected) | `stats.py:295` | **yes** (`:766–784`) |
| Paired excess vs benchmark, and refusal without a benchmark | `stats.py:374`, `evaluate` `:410` | **yes** (`:799–827`) |
| Walk-forward folds with purge + embargo, independent leakage check | `walkforward.py`; also `scripts/b14a_split_planner.py` | **yes** (`:840–896`; `tests/test_b14a_split_planner.py`) |
| Second DSR implementation | `scripts/t13_risk_shaping.py:373` | no pytest |
| Circular-shift null | `scripts/t13_risk_shaping.py:273` | no pytest |
| Paired block bootstrap of drawdown difference | `scripts/t13_risk_shaping.py:322` | no pytest |
| Block bootstrap of a family max | `rv_sweep.py:985`, `deepmine_etfstruct.py:850`, `scripts/d0821_season_lib.py:212` | no |
| Bootstrap max-t | `newterr_ratescredit.py:718` | no |
| Sign-flip joint null (one sign per trading day) | `scripts/inv3_null.py` | no |
| Cluster bootstrap by date/event | `t45_etf_liquidation_collect.py:393`, `t45_tierb_reader.py:99`, `memebot/arena/scorer.py:17` | no |
| HAC / Newey-West t | five separate `nw_t`: `scripts/inv3_run.py:138`, `invent0822_slow_ts.py:92`, `invent0822_slow_xs.py:182`, `prefrv_forward.py:211`, `inv0830_spotpremium.py:34` | **none** |

**[opinion]** Port the DSR and permutation **tests** (not the stdlib-only code) to `scripts/factory/stats.py`
as cross-checks, and validate the factory's `newey_west_t` against `statsmodels` (installed in
`research/factory/.venv`). Nothing else here is library-grade.

### 1.6 Loaders: what can feed the factory

**[fact]** All cache directories named below were under `research/data/` and are gone. **[fact] Hazard:**
31 scripts run `CACHE.mkdir(parents=True, exist_ok=True)` (or equivalent) at module level, e.g.
`newterr_ratescredit_fetch.py:27`, `t17_collect.py:49`, `t34_crypto_tsmom.py:39`, `scripts/m0_auction_fills.py:64`.
Importing one to reuse a function recreates a deleted directory. Copy the function instead.

| factory need | existing code | notes | verdict |
|---|---|---|---|
| **FX spot, FRED H.10** | `postures/c2_collect.py`: `fred()` `:28`, `fred_series()` `:48`, series maps `G10` `:151`, `EM` `:157` | Has the quote-direction flag per series (`DEXUSEU` is USD per EUR; `DEXJPUS` is JPY per USD and must be inverted). Shells out to `curl`; no manifest; EM map includes pegged/undeliverable currencies and VEF | **REUSE-WITH-CHANGES**: lift the map and the parser |
| FX spot, Yahoo `=X` | `ts_fetch.py:42`; `scripts/t29_crosslist/xl_universe.py:20–34` | **Do not use as a signal input**: the bar stamps earlier than CME settle; produced a Sharpe +4.93 artifact that persisted out of sample (§1.8) | hazard |
| ECB reference rates | no code | A 14.4 MB ECB `EXR` CSV exists only as an unreferenced git blob (§5.3) | build new |
| T-bill / policy rates (FRED) | `scripts/t13_data.py:115` (`_fred`), `:204` (`read_cash_daily`, DTB3/TB3MS); `t4_forward.py:449` (`refresh_cash_rates`); `newterr_ratescredit_fetch.py:86` | raw CSV kept, sha256 manifest in `t13_data.py` | **REUSE-WITH-CHANGES** |
| US ETF daily bars (Alpaca SIP, `adjustment=all`) | `data.py:214` | see §1.1 limits | **REUSE-WITH-CHANGES** |
| ETF/index daily (Yahoo `adjclose`) | `ts_fetch.py`, `cal_fetch.py`, `volterm_fetch.py`, `newterr_ratescredit_fetch.py:63` | keyless; raw JSON preserved. `X=F` continuous futures are a spliced front contract: the roll yield is deleted (documented in `SWEEP_futures_term_structure.md`) | REFERENCE-ONLY |
| **Binance USD-M funding + 1d klines + premium index, incl. delisted names** | `t23_collect.py`: `cmd_enumerate` `:112` (universe from the S3 bucket listing, so LUNA/FTT/SRM are present), `KINDS` `:168`, `cmd_download` `:198` (raw zips + sha256 manifest), `cmd_panel` `:258` | Best loader in the repo. Matches the survivorship rule in the factory design | **REUSE-WITH-CHANGES**: add a `klines/1h` kind and the daily `metrics` kind; parametrise `CACHE` (`:62`) |
| Binance 5m klines + daily metrics (open interest, long/short ratios) | `orphanflush_fetch.py` (`cmd_universe` `:241`, `cmd_download` `:355`), `glsr_metrics_backfill.py`, `perpmicro_r3_metapanel.py` (column map in its docstring) | Windows hard-wired (`:63–64`). The metrics crawl once stopped alphabetically at `BNXUSDT`, which made a 2025–26 cross-section an A–B subset and produced a false "edge died" reading (`XS_GLSR_Z_RECHECK.md`, git `HEAD`) | **REUSE-WITH-CHANGES**; add a per-symbol coverage assertion |
| Binance spot klines incl. delisted | `xspot_fetch2.py`, `xspot_enumerate.py` | | REFERENCE-ONLY |
| Hyperliquid hourly funding | `t25_collect.py` | | REFERENCE-ONLY |
| Quoted half-spread from Alpaca SIP quotes | `scripts/t3_pressure_reversal.py:617` (`measure_half_spread`) | median `(ask−bid)/(2·mid)` in the last second before the close, sampled days | **REUSE-WITH-CHANGES** (turns an ASSUMED ETF spread into a MEASURED one) |
| Short borrow fee per symbol | `t30_borrow_collect.py:74` (IBKR public `usa.txt`: `FEERATE`, `AVAILABLE`) | | **REUSE-WITH-CHANGES** |
| US options EOD chains (DoltHub SQL API) | `dolt_options_fetch.py` | API limits documented in the docstring (only `date=` equality is fast; 1,000-row cap) | REFERENCE-ONLY |
| Deribit / US option forward snapshots | `t31_deribit_collect.py`, `t33_us_options_collect.py`, `deribit_free_snapshot.py` | | REFERENCE-ONLY |
| RegSHO short volume, FINRA short interest | `t16_free_panels.py` (1,182 lines) | | REFERENCE-ONLY |
| CEF discounts (CEFConnect) | `cefbot/bot.py:33` | | keep with cefbot |

### 1.7 Sub-packages (classification only)

| package | what it is | verdict |
|---|---|---|
| `predmarket/` (10 files) | agent-vs-crowd calibration tracker on Kalshi/Polymarket; frozen spec deleted | RETIRE (REFERENCE if prediction markets return) |
| `newsdesk/` (12 files) | LLM reads news feeds, logs hypothetical setups; 2 of 30 resolved, no verdict | RETIRE |
| `cefbot/` | see §1.3 | REUSE-WITH-CHANGES (template) |
| `eventstudy/` (6 studies) | crypto event studies (funding extremes, listings, liquidation cascades) | REFERENCE-ONLY |
| `postures/` (27 files) | 2026-09-03 "posture" diagnostics; contains the FRED FX collector | REFERENCE-ONLY except `c2_collect.py` |
| `memebot/` (87 py), `memebot_evo/`, `memestream/` (includes its own `.venv`), `sniper/`, `aftershock/` (146 py) | Solana memecoin paper bots, tapes, evolution loop, latency calibration | RETIRE for the factory. ≈400 MB here is logs (`memestream/bitquery_ingest.log` 202 MB, `aftershock/solusd_recorder.log` 140 MB, `aftershock/pac_runner.log` 40 MB) |

**[fact] Two execution-capable pieces live in these packages.** `sniper/live_execution.py` builds a
PumpPortal `trade-local` request but is gated on `ALLOW_REAL_ORDERS` (hard-coded `False`) and has stub
sign/broadcast functions. `aftershock/pac_v2_send.py` and `pac_v21_send.py` can sign and broadcast
**memo-only** mainnet transactions when run with `--broadcast` and a keypair (latency calibration; they
cannot trade). Neither is wired to any scheduler.

### 1.8 Prior tests that overlap the factory's planned grid

**[fact]** Sources are git `HEAD` reports under `research/trading_bot/` plus the scripts.

| factory family | prior test | result |
|---|---|---|
| FX carry (cross-sectional, time-series) | `ts_sweep2.py` family I (`:306` onward), 17 formulas on 6 CME FX futures vs Yahoo spot, design 2007-01→2018-12, held out 2019→2026; report `SWEEP_futures_term_structure_r2.md` | Raw daily XS carry scored design Sharpe **+4.93**, held-out **+8.28**: an artifact (Yahoo `=X` spot stamps earlier than the futures settle). One extra day of lag gives −0.56. Stale-corrected family: XS monthly ≈ 0.00, XS z-weights +0.10, TS sign +0.32. Whole theme judged noise (best legitimate +0.59 vs bootstrap E[max] +0.71) |
| FX month-end flow | `inv0822b_sweep.py` family P (hedge-rebalancing flow) | part of `INVENT_0822B_MASTER.md` (not re-read here) |
| FX cross-section, FRED H.10 G10 + EM | `postures/c2_collect.py` + `c2_analyze.py` | a tail-dominance diagnostic (mean vs median member), **not** a strategy test |
| Crypto TSMOM, Donchian | `t34_crypto_tsmom.py`; `T34_CRYPTO_TSMOM.json` | top-20 perps, daily, 3.5 bp/side. Lookback 60 picked in-sample (Sharpe 1.00, 2023-01→2025-02); **held-out 0.12** (535 days), below the random-timing null's p95 (0.55). Donchian 55/20: held-out mean R −0.009 |
| Crypto positioning (long/short account ratio) | `perpmicro_sweep.py` `XS_GLSR_Z`; `XS_GLSR_Z_RECHECK.md` | design strong, 2024-06→2025-01 +0.44, 2025-01→2026-08 about breakeven after the data-hole fix; kept "logging only" |
| Turn-of-month (equities, bonds) | `cal_sweep.py:361–379` (SPY, TLT, SPY−TLT, IWM−SPY, EFA−SPY, quarter-end) | inside 52 + 48 calendar formulas, both batches judged noise (`SWEEP_calendar_session*.md`, pooled null in `cal_pooled_null.py`) |
| Commodity/rates carry, carry × momentum, seasonality via ETFs | `ts_sweep.py`, `ts_sweep2.py` (98 formulas) | noise twice (best +0.80 vs E[max] +0.78; +0.59 vs +0.71) |

**[opinion]** These are different universes and windows from the factory's, so they are priors, not
verdicts. They should be listed in the factory's dead ledger with their numbers, and the trial accounting
should say whether they count. The FX artifact is the important one: it survived a design→holdout split
and was caught only by adding a day of lag. The factory's lag-2 flag covers this; the two-print FX
placebo should be kept for the same reason.

---

## 2. `apps/trader`, `apps/trader_mc`, `apps/trader_backups` (3.0 GB, entirely untracked by git)

### 2.1 What it is

**[fact]** A local program (`trader serve`, dashboard on `127.0.0.1:8795`) that reads Solana mainnet
read-only, turns events into checked facts, and asks Claude (through the local `claude` CLI with tools
disabled) what to do with a virtual $100. Three books on the same coin stream: CASH (never trades),
BASELINE (the owner's coded rule R1) and JUDGMENT (Claude decides; no coded stops). Sources:
`README.md` §1–§6, `SPEC.md` (508 KB), `docs/STATUS.md`.

- Backend: 16 packages under `backend/trader/` (`exec` 9.4k lines, `feeds`, `evidence`, `agents`, `api`,
  `model`, `experiment`, `supervisor`, `store`, `governor`, `security`, `learning`, `engineer`, `chains`,
  `core`, `config`), `contracts.py` 4,030 lines, `ports.py` 597 lines of `Protocol` interfaces. About 107k
  lines of Python including tests.
- Web: React 18 + TypeScript + Vite + Tailwind + `lightweight-charts` (`web/package.json`).
- `apps/trader` is the running instance; `apps/trader_mc` is the build/test copy (10 `.py` files differ);
  `apps/trader_backups/20261005T020600Z` is a pre-swap backup (355 MB, no secrets directory inside).

### 2.2 Governor, risk caps, paper execution

**[fact]**
- Governor = a pure function `evaluate(inp) -> verdict` (`backend/trader/governor/rules.py:171`): approves
  the exact proposal or rejects it with every failing check recorded; never resizes, never invents an
  order; sells are never blocked by caps or halts.
- Caps in `config/experiment.toml`: per-position 20 % of a ≤ $100 book scaling to 5 % at ≥ $10k
  (`:182–185`), `max_open_positions = 5` (`:187`), aggregate cap 80 % of a ≤ $100 book scaling to 20 % at
  ≥ $10k (`:189`), `drawdown_halt_bps = 5000` (`:192`; halts new exposure only; the value is 50 % while
  its inline comment still says 20 %), conviction bands, an exit-impact guard.
- Halts and kill: `supervisor/halts.py`, `runstate.py`, `killwatch.py` (a `run/KILL` file is polled every
  250 ms and works when the main loop is stuck); pause vs kill semantics in `README.md` §5.
- Paper landing model: an approved order fills only after the model call finished plus a declared delay,
  at a later real pool state, with both sides' fees, own price impact, failed transactions and rent
  (`exec/fill_engine.py`, `exec/service.py`).
- Journal: hash-chained SQLite journal with content-addressed blobs and a `trader verify` command
  (`store/journal.py`, `store/verify.py`).
- Modes: `paper` or `devnet` only; the config rejects anything else and the egress layer refuses
  `sendTransaction` on mainnet (`README.md` §3–§4).

### 2.3 What is generic, what is memecoin-specific

**[fact]** Every candidate-generic module imports `contracts.py` (`store/journal.py:33`,
`supervisor/halts.py:36`, `governor/haltcodes.py:31`, `model/budget.py:27`, …), and `contracts.py` is
written in mints, pools, lamports, slots and reserve snapshots.

**[opinion] Verdict: REFERENCE-ONLY as a host for other strategies or venues.** Extracting the generic
parts means splitting a 4,030-line contract file; that costs more than writing a small runner. Port the
designs, not the code:

| pattern | read it in | use in the factory |
|---|---|---|
| Pure approve-exactly-or-reject governor with every check recorded | `governor/rules.py:1–95` (docstring), `:171` | pre-trade check for the paper runner |
| Halts that block new exposure only; KILL file watchdog | `supervisor/halts.py`, `killwatch.py` | stop switch for any scheduled runner |
| Hash-chained append-only journal + verify command | `store/journal.py`, `store/verify.py` | forward ledgers (cheap tamper evidence) |
| Benchmark books run on the same stream (CASH, coded BASELINE) | `README.md` §6 | every forward test logs its benchmark beside it |
| Sandboxed `claude` CLI runner with per-hour/day budgets | `model/runner.py`, `budget.py`, `sandbox.py` | only if an LLM-judgment lane is ever wanted |

The web dashboard is likewise built around coins and candles; it is not a generic strategy dashboard.

### 2.4 Start/stop, cost, state on disk

**[fact] Start/stop.** `apps/trader/scripts/run.sh` (background, waits for `/api/health`, pid in
`data/trader.serve.pid`) and `scripts/stop.sh` (SIGTERM, 90 s grace, then kill). It starts with the stub
decider unless `config/trader.toml` says `decider = "claude-cli"` (it currently does, `:12`).

**[fact] State.** No trader process is running (the only local listeners, ports 8796 and 8765, belong to
another project). `data/trader.serve.pid` and `run/trader.pid` are stale. Four SQLite databases have
un-checkpointed WAL files last written 2026-10-10 18:42Z (unclean stop). I read `trader.sqlite` with
`immutable=1` (no lock, no WAL replay, so the last ≈4 MB of writes are not in these numbers):

| item | value |
|---|---|
| Book epochs | 9; epoch 9 started 2026-10-07 20:46Z; books in micro-USD, $100 each |
| Epoch 9 at the last snapshot (10-10 18:30Z) | CASH $100.00; BASELINE $61.46 conservative / $76.98 marked (15 fills, drawdown 38.5 %); JUDGMENT $100.00 (**0 fills**) |
| Earlier epochs | BASELINE: epoch 6 $53.15 (drawdown-halted), epoch 7 $91.42, epoch 8 $59.54 (drawdown-halted). JUDGMENT: 2 fills in epoch 6 (−0.3 %), none in 7–9 |
| Model jobs kept in the table | 14,346 from 2026-10-07 17:43Z to 10-10 18:30Z; 14,121 are `scout` calls |
| Failures | 9,326 (65 %): 9,312 `cli_pin`, continuous from 2026-10-08 15:25Z until the end |
| Cost reported by the CLI | $161.39 for the 5,020 successful calls (10-07: $55; 10-08: $106), ≈ $0.03 per call, model `claude-opus-5-5` |

**[fact] Cost to run.** `config/experiment.toml` allows `calls_per_hour = 100000` and
`calls_per_day = 36000` (`:94–95`), plus 720 scout calls per hour (`:369`). Observed: 14,346 jobs in three
days (5,097 on 10-08). The `$` figure is what the CLI reported; what the owner actually pays depends on
their plan, which I did not check.

**[opinion]** If the owner restarts it: the `cli_pin` failure should halt and stop spawning (it spawned
9,312 failing jobs over two days), and the budgets should be finite. As evidence about strategy, the
record says the coded baseline lost in every epoch and the judgment book mostly declined to trade.

**[fact] Tests.** 110 test files, ~1,390 test functions under `backend/tests/`; `docs/STATUS.md:85` reports
1,750 passed on 2026-10-04. Not run here. `STATUS.md:270` says to run one full suite at a time with
≥ 3 GB free memory. Test litter: `.pytest_tmp` (115 MB) and `.spec_check` (20 MB).

---

## 3. `scripts/agent_graph` — the durable tick supervisor

### 3.1 What it automated

**[fact]** `durable_tick.sh` (24 KB) was run by cron every 3 hours. One tick: take an `flock`; run three
no-LLM engines (`basket_forward session`, `newsdesk resolve`, `predmarket resolve`, `:238–257`); run the
input-recency alarm and a missed-tick reconciler; then start **one headless Claude**
(`claude -p … --permission-mode bypassPermissions`, 1-hour timeout, `:358–359`) whose prompt
(`supervisor_prompt.txt`) rotates by hour: strategist, invention round, newsdesk, prediction markets.
`.env` is sourced only inside each engine's subshell so the model never inherits credentials (`run_py`, `:238`).
`loop.py` + `agenda.json` (109 tasks, 922 KB) are the task list; `server.py` is a stdlib dashboard on
`127.0.0.1:8787` (read-only Alpaca paper GETs; POST endpoints edit `agenda.json`, `:417`, no auth beyond
loopback).

### 3.2 Why it was turned off

**[fact]** `logs/durable_heartbeat.log` has 490 ticks from 2026-08-23 to 2026-10-25 12:01 local time (461
`claude=ok`, 28 `claude=exit-1`). After the 2026-10-15 deletion every instrument it supervised was missing,
and it kept running: `research/FINDINGS.md` records the 79th tick since the incident on 10-25, still
holding for an owner answer (T110). Each was a full headless Claude session. All project cron lines were
commented `[off 2026-10-25]`.

### 3.3 Known hazards — confirmed

| hazard | evidence |
|---|---|
| Never rewrite `durable_tick.sh` in place | **[fact]** the file itself documents three incidents (bash reads a script incrementally; an in-place edit moved bytes under a running tick) and now copies itself to a temp file and `exec`s the copy (`:21–44`). Two `.bak-*` copies sit beside it |
| `loop.py status` crashes on a string result | **[fact] confirmed.** `loop.py:192` calls `t["result"].get("headline")` and `:193` calls `.get` on `verdict`. In `agenda.json` 44 tasks have a string `result` and 11 a string `verdict`. Replaying `cmd_status`'s logic on the file raises `AttributeError: 'str' object has no attribute 'get'`. `cmd_merge` ends by calling `cmd_status` (`:180`), so a merge also ends in a traceback after saving |
| `loop.py` writes the agenda non-atomically | **[fact]** `save()` `:69–71` uses `write_text` directly (the control file uses temp + rename, `:58–62`) |
| `status.sh` reports the supervisor as ON | **[fact]** `status.sh:25` tests `crontab -l | grep -q durable_tick`, which also matches the commented-out line |
| "exit 0" is not "did work" | **[fact]** the harness added a nonce canary after five ticks whose shell could not execute anything still logged `claude=ok` (`:60–110`) |

### 3.4 Is a plain scheduled Python job a better fit for deterministic daily strategy jobs?

**[opinion] Yes.** The three deterministic engines never needed the model, and the supervisor's
complexity (self-copy guard, canaries, attendance reconciler) exists to make an LLM session safe to run
unattended. For daily strategy jobs I would use:

- one Python entrypoint per job, idempotent per `(strategy, session date)`, exiting 0 as a no-op when the
  row exists (the `t4_entrypoint.sh` flags `--skip-if-logged --skip-outside-window` already do this);
- a scheduler that catches up after power-off: the host is switched off about once a day (agenda task
  T81), and cron silently skips missed slots. A systemd user timer with `Persistent=true`, or a runner
  that loops over every missing session date, removes the dependence on being awake at a given minute.
  This is valid for a **logger** (hypothetical fills at official prints). A runner that sends paper
  orders must still be awake in its window and must refuse otherwise;
- `flock`, a heartbeat line, and the input-recency alarm pointed at the new ledgers;
- no model in the path; a model reads the reports on request.

Worth keeping from this directory: the per-engine `.env` scoping, the recency alarm, the idea that
liveness is the age of the newest **input row** rather than process uptime.

---

## 4. Other directories

| path | what it is | state | verdict |
|---|---|---|---|
| `scripts/scanner/` (29 files, untracked) | memecoin launch screen → Telegram alert cards; marks collector; vamp (copycat) gate; systemd units | its state directory `research/scanner/` (alerts, queue, `COORD.md`) was deleted; 8 `memebot-*.service` user units exist, all disabled | RETIRE for the factory; owner tool **[owner]** |
| `scripts/smartmoney/` (3 files) | copy-trading study on Bitquery data | concluded negative | RETIRE |
| `scripts/holdco_rv/`, `scripts/t28_dualclass/`, `scripts/t29_crosslist/` | equity relative-value sweeps (holding companies, dual-class shares, ADRs vs home listings) | caches deleted | REFERENCE-ONLY (dual-class and ETF-sibling RV were the "alive, structural" legs) |
| `scripts/interactive_dashboard.py` (1,427 lines), `scripts/autonomy_loop.py`, `AUTONOMY.md`, `DASHBOARD_CHEATSHEET.md`, `config/autonomy_result.schema.json`, `.autonomy/` | tmux loop that alternated Codex and Claude CLIs | retired 2026-08-16 in favour of `agent_graph` | RETIRE. **[fact] Conflict:** `AGENTS.md` still mandates this handoff command for every release |
| `scripts/b*.py` and `b*.sh` (135 files), `docs/` (19 schema documents), `ui/operator_console.html`, `skills/pumpfun-research/` | the July–August Pump.fun pipeline (decoder, simulator, labels, splits, governor) and its console | dormant; reads the big SQLite files in §5.4 | RETIRE for the factory. Must stay: `scripts/b22b_slippage_harness.py` (pinned import of `trading_bot`). Worth reading: `b14a_split_planner.py` (purge on the label window, not on t0), `b12a_risk_governor.py`, `b19_preregistration_register.py` (hash pins in code), `mutation_sweep.py` |
| `scripts/t3…t15*.py`, `m0_auction_fills.py`, `inv3_*`, `d0821_*`, `auc0822_*` | the first US-equity tests and measurements | caches deleted | REFERENCE-ONLY |
| `tests/` (99 files, 53k lines, ≈4,630 test functions) | 90 % Pump.fun pipeline; `test_t2_backtest_harness.py`, `test_t4_forward.py`, `test_forward_eval.py` cover `trading_bot` | not run. At least six files reference deleted `research/` sub-directories. No recorded suite duration found in the logs | keep with their code. **`tests/_netguard.py` + `conftest.py` = REUSE-AS-IS**: blocks every non-loopback socket for the whole pytest session |

**[fact] Test hazards.** `tests/test_t2_backtest_harness.py` writes and removes fixture files inside
`tests/` (`:98`, `:1010`) instead of a temp directory, which is why I did not run it. `scripts/factory/tests/`
is empty. No flakiness note found in `DECISIONS.md`.

---

## 5. Repository hygiene

### 5.1 Size and git state

**[fact]** 15 GB working tree: `research/` 7.2 GB (6.25 GB is top-level SQLite, 0.68 GB the factory venv),
`apps/` 3.0 GB, `.git` 2.8 GB, `scripts/` 0.5 GB, root scratch ≈0.5 GB. Disk: 109 GB free. Branch
`freeze/honest-overhaul-2026-08-27`, in sync with its GitHub remote. **Last commit 2026-09-10.** Everything
since then (`apps/`, `scripts/scanner/`, `scripts/factory/`, `research/factory/`, all October documents)
exists on this one disk only.

### 5.2 Tracked-deleted, untracked, modified

| class | count | where |
|---|---|---|
| tracked but deleted | 2,072 | all under `research/<subdir>/`: `trading_bot` 898, `postures` 637, `midcap` 247, `mutation` 48, `real_economy` 45, `launchpads` 34, `h69` 29, `data` 27, `b11m_window2` 26, `scratch_combo2` 23, `b11a` 18, `b11f` 11, others ≤ 6 |
| untracked | 1,536 entries = 3,360 files | `scripts/agent_graph` 1,520 (logs), `apps/trader_mc` 635, `apps/trader` 633, `apps/trader_backups` 518, `scripts/scanner` 29, `scripts/factory` 10, `research/` 11, `scripts/trading_bot` 4 |
| modified | 15 | `DECISIONS.md`, `agent_discussion.md`, `research/FINDINGS.md`, 3 agent_graph files, `scripts/operator_notify.py`, 8 files under `scripts/trading_bot/` (two of them are tracked `.log` files) |

### 5.3 `.git` holds copies of deleted data — and would probably lose them on the next `gc`

**[fact]** 10,549 git objects (9.57 GB uncompressed; 10,522 of them file contents) are not reachable from
any branch. Most sit in a cruft pack written 2026-09-08 22:37 local time (`pack-d6abafba….pack`, 2.11 GB,
with a `.mtimes` file); the rest are among the 2,315 loose objects. **[hyp]** They are files that were
hashed into the object store (staged) at some point and never committed. Identified by reading the first
bytes of each (no file was extracted):

| content | detail |
|---|---|
| T31 Deribit forward snapshots | 16 daily `csv.gz` snapshots, 2026-08-24 → 09-08, plus two versions of a `ledger.json` whose day range (08-24 → 09-08, 16 days) matches T31 |
| T30 IBKR borrow raw files | 15 daily `usa.txt.gz`, 2026-08-23 → 09-07 |
| T4 forward ledger | blob `a69113b602`: 36 rows, 2026-08-17 → 10-02 (7 submit, 29 dry-run). Git `HEAD` has 19 rows to 09-09 |
| BASKET1 forward ledger | blob `8f4851183a`: 31 rows, 2026-08-21 → 10-02. Git `HEAD` has 13 rows |
| T45 state | one 398-byte state file, last date 2026-09-07 |
| US-equity panel caches (`.npz`) | 5-minute RTH panel 1,410 days × 78 bars × 132 symbols (261 MB); daily OHLC 3,521 symbols × 2,669 sessions (two variants, 96 and 167 MB); close + dollar volume 15,940 symbols × 2,020 days with an ETF flag (105 MB); three event/overnight panels |
| Raw tapes | SOL-USD Coinbase trades (nine snapshots of ≈353 MB), a 3.24 GB event ledger, memecoin snapshot files |
| Documents | several hundred Markdown/JSON/CSV files, including strategist and invention notes dated after 2026-09-10 |
| Other | an ECB `EXR` exchange-rate CSV (14.4 MB); Alpaca daily-bar JSON chunks from 2016 |

**[fact]** 967 of the loose objects were written in seven seconds at 2026-10-15 13:00:31–38Z, 78 minutes
before the deletion; 1,109 were written today at 14:07:57–14:10:02Z. I do not know what wrote them
(blobs only, no trees or commits). **[hyp]** A tool hashing untracked, non-ignored files through a
temporary index. Not found by my signatures: any T33 snapshot, or any T30/T31/T33/T45 data after
2026-09-08 (those directories were git-ignored from that date). Blobs carry no file names, so anything
salvaged has to be named from its content.

**[hyp] Hazard.** Git's default `gc.pruneExpire` is two weeks and this repo does not override it, so a
manual `git gc` or `git prune` would delete everything above except today's objects. Auto-gc starts when
loose objects exceed 6,700; a commit of the ≈3,400 untracked files could reach that. Not tested.

**[owner]** Decide whether any of this is wanted (it bears directly on T110, "is there a backup?") before
anyone commits a large change or runs `git gc`. Extraction is `git cat-file blob <sha> > file`; I did not
do it.

### 5.4 Big SQLite files under `research/` and what reads them

| file | size | readers |
|---|---|---|
| `b9d_transaction_bodies.sqlite` | 4.52 GB | `scripts/b11e_pipeline_dryrun.py`, `b13b_association_corpus.py`, `b16a_operator_archetypes.py`, `b19e_evaluation_window.py`; 4 test files |
| `b9c_signature_inventory.sqlite` | 840 MB | `b9c_…py`, `b9d_…py`, `b11e_…py`; 1 test file |
| `b7j_positive_control_435564885_435565324.sqlite` | 769 MB | `b7k_decoder_common_mode.py`, `b7l_field_identity.py`; 1 test file |
| `b7e_lifecycle_429998000_430000000.sqlite` | 194 MB | `b7f_enrich_analyze.py`; 1 test file |
| `b10b_observed_paths.sqlite` | 24 MB | six `b1x` scripts; 3 test files |
| `b6g_processed_raw_2026-07-27.bin` 17 MB, `b7h_recall_….sqlite` 11 MB | | no reader found |
| `b10c_labels.sqlite`, `b8b_cohort_….sqlite`, `b10c_t0_identity.sqlite` | ≤ 6 MB | `b10c_label_corpus.py`, `b8b_*`, `b9a_*`, `b16a`, `b19e` |

All are July–August Pump.fun evidence, git-ignored (`*.sqlite`). Nothing in `scripts/trading_bot`,
`scripts/factory` or `apps/` reads them. **[owner]** 6.25 GB to keep or archive.
`apps/trader/data/market.sqlite` (1.8 GB) is the trader's own market cache.

### 5.5 Root scratch directories

**[fact]** Eighteen directories created in one night (2026-09-04 03:00–06:00 local time), 0.5 GB, and
**tracked by git** (swept into the 09-08/09-10 snapshot commits and pushed):

`.scratch_fc` 101 MB · `_c3` 85 MB · `.ff3` 60 MB · `.scratch_feat_flow2` 48 MB · `.scratch_att2` 47 MB ·
`.scr2` 29 MB · `.scr` 28 MB · `.tmp_combo3` 19 MB · `_fv0` 18 MB · `.fc3` 15 MB · `.combo2way` 13 MB ·
`.scr_fc3` 11 MB · `.combo2way_scratch` 10 MB · `.fm3work` 7 MB · `_r0` 4 MB · `.regime1` 0.7 MB ·
`.c2w`, `.scratch_hv` < 0.1 MB.

No script, document or decision entry references any of them by path (searched `scripts/`, the root
documents, `FINDINGS.md`, `DECISIONS.md`). Also at the root: `.h30_*`, `.holdout_rule1*`, `.chk_out.txt`,
`.ls.txt`, `.ping_test.txt`, `.zz_test`, `p6_xyz.txt`, `scan_*.txt`, `form.idx` (2.1 MB). `.autonomy/`
(12 MB) is ignored. **[owner]** Candidates for `git rm`; they contain pickles and intermediate tables from
memecoin feature work.

### 5.6 `.gitignore`, secrets, crontab

**[fact] `.gitignore`** covers `.env*`, `*.sqlite*`, `*.bak*`, `.autonomy/`, `__pycache__/`, `*.log`,
`.venv/`, `research/data/`, `*.npz`, `*.npy` and many per-lane runtime files. Not covered: the root scratch
directories and stray dot-files, `.pytest_cache/`, `*.pkl`, `*.parquet`, `node_modules/` at repo level.
`apps/trader` and `apps/trader_mc` carry their own `.gitignore` (secrets, data, run, venv, node_modules);
`apps/trader_backups` has none (it contains no secrets directory, but 355 MB of copies).

**[fact] Secrets.** Root `.env` is mode 0600, ignored, never committed. It defines 27 names:
`CHAINSTACK_API_URL` (empty), `SOLANA_RPC_URL`, `SOLANA_WS_URL`, `ALPACA_API_KEY_ID`,
`ALPACA_API_SECRET_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `BITQUERY_API`, `LIGHTNING_API`, nine
`PAC_*_RPC_URL`, `HELIUS_RPC_URL`, `HELIUS_API_KEY`, two `PAC_SCALP_LL_INTERVENTION_*_RPC_URL`,
`EXITGUARD_BOT_TOKEN`, `EXITGUARD_REF_TEMPLATE`, `EXITGUARD_REF_CODE`, `PUMPPORTAL_DATA_API_KEY`,
`FOMO_API_KEY`. `apps/trader/secrets/` holds five 0600 files (`api_token`, `session_key`, `bootstrap_url`,
`rpc_fallback.json`, `devnet-keypair.json`).

I searched for the **values** (never printed) of every `.env` entry ≥ 20 characters and of the trader
tokens in:

| searched | result |
|---|---|
| every git object, all history, reachable or not (19,012 objects, 11.4 GB) | **no match** |
| 8,269 working-tree files (1.5 GB): `scripts/`, `research/`, logs, `.autonomy/`, root files, memory notes | **one match**: the key inside `PAC_SCALP_LL_INTERVENTION_SUBMIT_RPC_URL` appears in `.autonomy/interactive/codex-sqlite/state_5.sqlite-wal` (a Codex CLI state file; local, git-ignored) |
| `apps/` code, data, run logs, backups, test temp directories (4,699 files) | **no match** |
| not searched | three SQLite files > 600 MB under `research/`, and `apps/trader/data/market.sqlite` |

**[opinion]** Two things to weigh: `LIGHTNING_API` is described in the memory notes as a funded
trading-capable key, and it sits in the same `.env` every research script can read; and the RPC key above
was written into a tool's state file. Rotating both is cheap. **[owner]**

**[fact] Crontab.** 24 lines carry `# [off 2026-10-25]`: the durable tick (every 3 h); the T4 paper bot
(every 10 min on US weekdays) and its evaluator (22:35); T31 Deribit collector (02:15, 02:45); T30 borrow
collector (16:30, 17:00, 20:30); T33 US-options collector (two lines); T45 ETF-liquidation collector
(23:15); PREFRV weekly (Sat 10:10); ten watchdogs (every 2–3 min: memebot, memebot_evo, memestream ×2,
sniper, aftershock ×3, memebot dashboard, window-2 decode); `books_snapshot` (12:40); scanner `marks.py`
(every 10 min). Still active: three non-project lines (`/tmp/updates-check`,
`/tmp/posture-check`, `/tmp/battery-check`), the environment line `T4_MODE=submit`, and two `CRON_TZ`
lines. Several off lines redirect into directories that no longer exist.

### 5.7 Decisions for the owner

1. Salvage or discard the unreferenced git objects (§5.3), before any large commit or `git gc`.
2. Commit or otherwise back up the two months of untracked work (`apps/`, `scripts/scanner/`,
   `scripts/factory/`, `research/factory/`), or accept single-disk risk.
3. The 2,072 tracked-deleted files: record the deletion in git (`git rm`) or restore selected ones. The
   three that unblock reuse are `research/trading_bot/M0_AUCTION_FILLS.json`, `T18_EXIT_MEASUREMENT.json`
   and `ITERATION_PROTOCOL.md` (copying them into `research/factory/` avoids touching the deleted tree).
4. Root scratch directories and the 6.25 GB of Pump.fun SQLite: keep, archive or remove.
5. Refresh `AGENTS.md`/`PLAN.md`: they describe a Pump.fun project, require reading `DECISIONS.md`
   (440 KB) at the start of every task, and mandate a retired handoff tool.
6. Rotate the two credentials named in §5.6; remove the stray `T4_MODE=submit` crontab line if the T4 bot
   is not coming back.

---

## 6. Process assets, and a candid opinion

### 6.1 Worth keeping

| asset | where | why |
|---|---|---|
| Freeze-then-test with a hash checked **by the runner** | `cefbot/strategy.py:64`; `t4_forward.py:229`; `basket_forward.py` `frozen_spec`; `scripts/b19_preregistration_register.py` | a rule that can be edited after results is not a test; refusing at start-up is cheap |
| Evaluators written and pinned before data exists | `t30_borrow_evaluate.py`, `convexity_evaluate.py` (developed on synthetic panels only) | removes threshold-picking after the fact |
| Cost provenance | `costs.py:106–207` | a number without a source is an assumption; a "measured" label needs a file |
| Truncation + regeneration audit with a negative control | `engine.py:448`, `strategies.py` `CheatingOracle` | found two real bugs in its own first version |
| Lag kill-test for print asynchrony | `ts_sweep2.py`, report §"kill test" | the only thing that caught a result that passed its holdout |
| Forward register that never deletes retired entries | `FORWARD_REGISTER.json` (git `HEAD`) | a silent restart is selection on the outcome |
| Maintenance vs rule-change test | `ITERATION_PROTOCOL.md` §3 (git `HEAD`): "would the fix change the weight on a day already traded?" | a usable line between repair and tuning |
| Input-recency liveness | `input_recency_alarm.py` | process uptime and a green dashboard both stayed true through a 56-hour dead feed |
| Declared trial counts and a pooled bar across themes | `FORMULA_SWEEP_MASTER.md`, `FORMULA_SWEEP_MASTER_R1.md` (git `HEAD`) | 380 + 367 formulas judged against one pooled bar; one leg promoted per round (`XS_GLSR_Z`, later about breakeven; `X2_FLOWSTREAK`, later parked) |
| `DECISIONS.md` convention | `## date — title`, then decision / why / evidence | good per entry; see §6.2 on volume |

### 6.2 What was self-defeating — [opinion], with the facts it rests on

1. **Binary gates on continuous evidence.** T3 (overnight reversal) held out at +5.35 bp/night, t = 2.73,
   Sharpe 1.29 over 1,139 nights, permutation p = 0.0001, and was declared dead because DSR was 0.9379
   against 0.95 (`FINDINGS.md` §5e). The follow-up showed a real execution problem (the auction rail needs
   information from before 15:50), which is a better reason. A threshold missed by 0.012 should lower a
   size or extend a test, not end a line of work.
2. **Several gates in conjunction.** Typical rule: net mean > 0 **and** permutation p < 0.05 **and**
   DSR ≥ 0.95 **and** positive at stress cost. Each is reasonable; together the pass probability for a
   real but modest edge is small (§6.3).
3. **Forward tests that cannot finish.** T4's minimum before any verdict was three completed ≥ 20 % crash
   episodes; the protocol itself computes ≈92 years for 80 % power (`ITERATION_PROTOCOL.md` §4, step 2). CEFBOT
   needed 123 weekly observations before "survives" was even readable (`cefbot/strategy.py:54`). A
   two-month programme cannot learn anything from instruments like these.
4. **The verdict of each gate was recorded; the evidence was not pooled.** Many results were "positive,
   not significant" (T13 "positive-signed in every decade", DSR 0.355). Nothing combined such legs into
   one book and asked whether the **portfolio** was distinguishable from zero, which is the question a
   small account actually has.
5. **Process cost.** `research/FINDINGS.md` is 8,213 lines, `agent_discussion.md` 22,525 lines,
   `DECISIONS.md` 4,464 lines. 68 tick entries were added to `FINDINGS.md` between 10-16 and 10-25, after
   every supervised instrument had been deleted. The context-recovery rule in `AGENTS.md` can no longer be
   followed literally.
6. **Fail-closed on one disk.** The discipline protected ledgers from edits and did nothing about loss:
   every forward ledger lived in a git-ignored directory with no second copy, and one file-manager action
   ended four forward tests.
7. **A prose dead ledger.** The new pre-registration missed three earlier tests (§1.8) because prior
   results are scattered across reports. A machine-readable ledger (family, universe, window, cost,
   result, artifact path) would let a new grid be checked against it automatically.

What I would **not** relax: the lag ≥ 1 rule, the look-ahead audit, costs with provenance and a stress
case, declaring the trial count, and freezing before the holdout. None of those caused the 0-for-N record;
the thresholds and sample sizes did.

### 6.3 Power of the gates — my calculation, normal approximation

A strategy with true annual Sharpe `S` tested on `T` years has t ≈ N(S·√T, 1). Probability of clearing
the bar:

| gate | S = 0.5 | S = 0.7 | S = 1.0 | S = 1.5 |
|---|---|---|---|---|
| old programme, t ≥ 2.8 on a 4.6-year holdout (≈ DSR ≥ 0.95 at ~8 trials) | 4 % | 10 % | 26 % | 66 % |
| factory v1 design bar 3.19 SE, FX 18 years | 14 % | 41 % | 85 % | 100 % |
| factory v1 design bar, ETF 6 years | 3 % | 7 % | 23 % | 69 % |
| factory v1 design bar, crypto 3 years | 1 % | 2 % | 7 % | 28 % |
| factory v1 design **and** holdout (t ≥ 2), crypto | 0.1 % | 0.5 % | 3 % | 20 % |

Years needed for 80 % power: at a bar of 2.0, 8 years for S = 1.0 and 32 years for S = 0.5; at 3.19, 16 and
65 years. `DESIGN_v2.md` §0 item 7 already reaches the same conclusion and moves to a few parameter-free
primary ensembles; this table is the quantitative reason, and it says the crypto lane cannot confirm
anything short of a very large effect on three years of data.

---

## 7. Highest-value reuse opportunities

Ordered by value to the new programme. Line counts are my estimates.

| # | opportunity | entry point | what must change |
|---|---|---|---|
| 1 | **Alpaca paper rail for an ETF book** | `scripts/trading_bot/t4_forward.py:561–710`, `:1178–1281`; guard in `paper.py:110` | Copy ≈250 lines into a factory runner; loop over symbols; one `client_order_id` per strategy-date-symbol; notional orders for longs; new authorisation path. ≈200–300 lines of glue. Needs the owner's authorisation file before any paper order. Remember: no closing-auction fills on paper |
| 2 | **Survivorship-complete Binance archive loader** | `scripts/trading_bot/t23_collect.py:112`, `:168`, `:198` | Add `klines/1h` and daily `metrics` to `KINDS`; point `CACHE` at `research/factory/data/`; add a per-symbol coverage check (the `BNXUSDT` incident). ≈60 lines |
| 3 | **FRED H.10 FX map with quote directions** | `scripts/trading_bot/postures/c2_collect.py:28–66`, `:149–164` | Lift the dictionary and parser; replace `curl` with a fetch that writes raw CSV + sha256 manifest; drop pegged and undeliverable currencies. ≈80 lines |
| 4 | **Forward-logger template** | `scripts/trading_bot/cefbot/` (775 lines) + the `FORWARD_REGISTER.json` schema (git `HEAD`) | Generalise to "spec JSON + hash → one idempotent `run --date` → append-only ledger → evaluator". Derive state from the ledger instead of a separate state file. Replace fixed minimum-sample gates with a running estimate and a pre-declared kill rule (BASKET1's is a good shape: drop a leg when the one-sided 95 % bound is below zero after n ≥ 40) |
| 5 | **Measured costs instead of assumed ones** | spread: `scripts/t3_pressure_reversal.py:617`; borrow: `scripts/trading_bot/t30_borrow_collect.py:74` and `research/B22G_BORROW_COST.json`; existing measurements: SPY half-spread 0.116 bp, CEF median 11.53 bp (`cefbot/strategy.py:43–44`), near-close market fill +5.07 bp vs close (T4, n = 1), M0 auction-print study (git `HEAD`) | Run the spread sampler on the ETF universe (50 symbols × ~40 sampled days of one-second quote windows); take borrow fees from one day of IBKR `usa.txt`. Tags the ETF lane's two ASSUMED numbers as MEASURED |
| 6 | **Differential test of the factory engine** | `scripts/trading_bot/engine.py:552` with `retail_taker_costs()`-style simple costs | One-instrument open-price panel, lag 1: factory net returns must equal `run_backtest`'s within float tolerance. ≈60 lines of test |
| 7 | **Network guard for tests** | `tests/_netguard.py`, `tests/conftest.py` | Copy both into `scripts/factory/tests/`. No change |
| 8 | **DSR and permutation tests as cross-checks** | `tests/test_t2_backtest_harness.py:683–790` | Re-point at `scripts/factory/stats.py`; add a `statsmodels` HAC comparison |
| 9 | **Input-recency alarm** | `scripts/trading_bot/input_recency_alarm.py:210` | Replace the instrument table with the factory's ledgers and data manifests |
| 10 | **Pure governor + KILL file** (design only) | `apps/trader/backend/trader/governor/rules.py:171`, `supervisor/killwatch.py` | Re-implement in ≈150 lines for the paper runner: approve exactly or reject with reasons; caps on gross, per-name weight, daily turnover; a kill file checked before every order |
| 11 | **Dead-ledger seeds** | git `HEAD`: `research/trading_bot/FORMULA_SWEEP_MASTER.md`, `FORMULA_SWEEP_MASTER_R1.md`, `SWEEP_*.md`, `T34_CRYPTO_TSMOM.json`, `XS_GLSR_Z_RECHECK.md` | Transcribe into a structured ledger file the sweep runner can check a grid against |
| 12 | **Equity panels in `.git`** (only if the owner salvages them) | blobs `b752cabdcb` (daily OHLCV, 3,521 × 2,669), `ece3284bb6` (close + dollar volume, 15,940 × 2,020, ETF flag), `8dddbc542a` (5-minute, 132 symbols) | Provenance is unverified (adjustment mode unknown): use as a cross-check on fresh downloads, not as a source |

---

## 8. Open questions

1. **[owner]** T110 is still unanswered (was the 2026-10-15 deletion intended; is there a backup). §5.3
   adds a partial answer to the second half.
2. **[owner]** May paper orders be sent again, and under which authorisation file?
3. **[open]** What wrote the loose git objects on 2026-10-15 13:00Z and today 14:08Z? If a tool stages
   files as a side effect, it also explains how large data files reached the object store.
4. **[open]** Why did T4 switch from submit to dry-run on 2026-08-26?
5. **[open]** Do the earlier FX-carry, crypto-trend and calendar tests count toward the factory's trial
   accounting, and are they listed in its dead ledger?

---

## 9. Method and limits

- **Read with:** `cat`/`sed`/`grep`, `git show HEAD:<path>`, `git ls-files`, `git cat-file`, `git rev-list`,
  `git status`, `crontab -l`, `ps`, `ss`, `systemctl --user list-unit-files`, and Python run with `-B`.
  `git status` may take git's optional index lock; the index file was not rewritten.
- **SQLite:** `apps/trader/data/trader.sqlite` opened with `mode=ro&immutable=1`. Counts exclude whatever
  is still in the WAL.
- **Not run:** any pytest file (the relevant ones write fixtures into the repo), any service, any network
  call, any script with an import-time `mkdir`.
- **Not read in full:** `agent_discussion.md`, `DECISIONS.md`, `FINDINGS.md`, `SPEC.md` (searched with
  `grep`); the `memebot*`, `aftershock`, `memestream`, `sniper` packages and the `b*` pipeline (classified
  from docstrings and file lists); `apps/trader` beyond README, STATUS, config, governor, ports and the
  import graph.
- **Not verified:** that the Alpaca keys still work (the 2026-11-10 `DECISIONS.md` entry says they do);
  test-suite durations; the prune behaviour in §5.3.
- **Concurrent edits:** other agents were writing in `scripts/factory/` and `research/factory/` during
  this audit (`run_sweep.py` disappeared between two listings), so the factory drafts are described only
  where needed.
- **Outside the repo:** one scratch listing was written to the session's temp directory early on; nothing
  else was created anywhere.
