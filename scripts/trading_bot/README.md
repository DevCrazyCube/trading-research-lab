# T2 — the leakage-free backtest and paper-execution harness

The rig every edge candidate must pass through before anyone believes it. Built **before any
equity candidate exists**, so no part of it was shaped by a result someone wanted.

It is a skeleton, not a strategy. Nothing in it is an edge, and the only strategies shipped
with it are ones whose answer is known in advance.

```bash
python -m scripts.trading_bot selftest          # synthetic data; no network, no credentials
python -m scripts.trading_bot run --symbol SPY --start 2016-01-04 --end 2026-08-14 \
    --strategy buy_and_hold --costs retail_taker --folds 5 --trials 1
```

```python
from scripts.trading_bot import load_bars, retail_taker_costs, walk_forward_run, BuyAndHold, bars_per_year

bars, manifest = load_bars("SPY", "2016-01-04", "2026-08-14", "1Day")
report = walk_forward_run(bars, BuyAndHold, retail_taker_costs(),
                          periods_per_year=bars_per_year("1Day"), n_folds=5, trials=1)
```

---

## 1. How lookahead is prevented — three layers, and only the third is proof

**Layer 1 — the strategy is never handed the series.** `on_bar` receives a `PointInTimeView`,
a cursor over a private tuple. `view[i]` for `i > cursor` refuses; `len(view)` is `cursor + 1`;
`history(n)` refuses if `n` bars have not printed; slicing and iteration refuse outright,
because `view[a:b]` and `for bar in view` both read as "all the data" at the call site while
meaning "the data so far". `__slots__` and a name-mangled store mean there is no `__dict__`
and no attribute called `bars`.

**Layer 2 — a decision can never be filled at the price that produced it.** A signal computed
from bar *i*'s close cannot execute at bar *i*'s close: when you knew the close, it had
already printed. `execution_lag_bars` is **>= 1 and there is no flag to disable it**. Fills
happen at bar *i+lag*'s **open**, and positions are marked **open-to-open**, so the price you
transact at and the price you mark at are the same tick. The classic "fill at the open, mark
at the close" mismatch cannot occur because the engine never mixes the two.

**Layer 3 — the audit, which is the layer that actually proves it.** Layers 1 and 2 constrain
the *interface*; they cannot stop a strategy holding its own reference to the bars. So every
backtest re-runs the strategy at several probe bars `k` under two probes:

| probe | what it does | strength |
|---|---|---|
| **truncation** | bars after `k` are **deleted**; every decision in `[warmup, k]` must be bit-identical | **deterministic**. A forward-reading strategy hits the end of the data and must differ or raise. Both are caught. |
| **scramble** | bars after `k` are **regenerated** from an LCG anchored at the last honest close | catches a peek at a bar that still exists in the truncated run — e.g. a normalisation constant taken over the whole series |

`run_backtest` refuses to report if either fires. `CheatingOracle` in `strategies.py` is the
negative control, and it is caught.

> **The audit's first version was toothless and its own negative control found that out.**
> The scramble multiplied every field of a bar by one factor, which **preserves the sign of
> (close − open)** — so a strategy peeking at tomorrow's candle direction saw the same answer
> in both runs and passed. The scramble now regenerates the future instead, and the truncation
> probe was added so detection does not depend on a distortion happening to matter.

**Stated limit.** A strategy that opens its own file inside `on_bar`, or reads a module global
the harness never touches, is outside what any re-run can detect. The guarantee is: *no
decision depends on the future of the series the harness controls.* For that to hold, **a
strategy that needs the bars must take them as a constructor argument** (`build_strategy`
hands a series-taking factory the series being probed). A zero-argument lambda closing over
the real bars keeps the real future in both runs — that blind spot is asserted in the tests so
it stays documented rather than rediscovered.

---

## 2. Reuse of the frozen B22B artifact

`scripts/b22b_slippage_harness.py` is pinned at sha256 `a0f1b4c4…` by
`research/B22B_SLIPPAGE_PREREGISTRATION.json`. `frozen.py` **imports** it and verifies the
hash at import time, so an edit to the pinned harness makes the whole rig refuse to start
rather than run against a mutated definition. Nothing is copied.

What transfers: integer micro-dollars with `to_micros` as the single ingest float boundary;
integer-nanosecond timestamps parsed by hand; per-day DST offsets; ATR warm-up refusal;
percentiles by integer index; the adverse-sign convention; and the fail-closed rule that
**absence is refusal, never zero**.

> **What does NOT transfer: a number.** B22B is a pinned *rule* whose collection stage is
> deliberately unimplemented. **It has never been run, and this programme has measured no
> slippage magnitude in equities.** `SlippageProvenance.MEASURED_B22B` therefore *refuses* on
> construction, so nothing can quietly claim to be a measurement that is not one.

---

## 3. The cost model

Every component carries a `SlippageProvenance` and a citation; a component with an empty
source refuses. `to_report()` prints the provenance next to every number.

**Spread and slippage are charged PER SIDE.** `split_turnover(previous, target)` decomposes every
position change into the part that *opens* exposure and the part that *closes* it (a +1 → −1
reversal is a 1.0 exit **and** a 1.0 entry), and the two legs are priced separately.

| component | charged on | default source |
|---|---|---|
| `entry_half_spread` | notional of the leg that OPENS exposure | Dyhrberg/Shkilko/Werner JFE 168 (2025), ~2.5 bp half-spread after measured price improvement |
| `entry_extra_slippage` | same leg | B22B's own measurement in `b22b_measured_costs()`; a stated lower bound (zero) in `retail_taker_costs()` |
| `exit_half_spread` | notional of the leg that CLOSES exposure | the **worse** of 2.5 bp (Dyhrberg et al.) and half of B22B's own measured quoted spread on this universe |
| `exit_extra_slippage` | same leg | **nobody has measured an exit.** `b22b_measured_costs()` charges the entry's measured magnitude again as a declared adverse proxy, never zero |
| `commission_per_share` | shares traded, both legs | broker schedule; Zarattini's $0.0035/share for the paper model |
| `borrow_annual` | short notional, per **calendar** day | GC US large-cap ~30 bp/yr — *not* hard-to-borrow, which can exceed 50%/yr |

Borrow accrues on calendar days because it accrues over weekends; a Friday→Monday short pays
three days, not one. Price improvement is **not** credited — charging the full half-spread is
the conservative side of the 6.5× cross-broker spread B22C records.

> **Why per side (T6, 2026-08-17).** There used to be one spread/slippage term, charged to
> `|target − held|`. `b22b_measured_costs()` sets its half-spread to **zero** — correctly, because
> B22B's entry measurement already contains the spread — so under the old wiring every **exit**
> (stop-loss market order, market-on-close), none of which B22B ever measured, crossed the spread
> for free. Round trip **1.63 bp**; the honest number is **5.59 bp**. `trade_cost_fraction()` now
> refuses a lumped turnover by name rather than pricing it at the cheaper side.

Round trips at the defaults: `zarattini_paper_costs()` **0 bp** (straw man), `retail_taker_costs()`
**5.0 bp**, `b22b_measured_costs()` **5.59 bp** (entry 1.55 + exit 4.05), `zero_cost_model()` 0 bp
(**diagnostic only**, the B19P frictionless bound: if a strategy loses here, no execution
improvement can rescue it). `stress_ladder()` sweeps impact — on **both** sides — so a cost number
is never reported alone.

The measured entry mean is **decontaminated** before it is charged. The preregistered trigger is
"first trade at or through the stop", and SIP odd-lot / out-of-sequence prints can trigger a
stock-day at a level nobody could trade; those land in the *favourable* tail and drag the mean
**down**. `measured_extra_slippage(atr_filter=…)` drops stock-days whose trigger print was more
than *n* ATR(14) through the stop. Default **0.1 ATR = one full R** (R is defined as 10% of
ATR(14)), which raises the charged mean from 0.813 bp to **1.545 bp**; the ladder is 1.0 ATR
0.852 (+4.8%), 0.5 ATR 1.210 (+48.8%), 0.1 ATR 1.545 (+90.0%). Percentiles are read unfiltered,
since every removed point is favourable.

---

## 4. Walk-forward

`walk_forward_folds` produces sequential, non-overlapping test folds, each strictly after its
own train window, with a **purge** (drops train bars whose label horizon reaches into test)
and an **embargo** (drops the first test bars, guarding serial correlation across the seam).
Both must be stated explicitly; `None` is not zero. `assert_no_leakage` re-checks the
invariants using code that does not share the construction logic — FINDINGS §8: *"verify the
diagnostic, not just the system,"* because twice in this programme the checking tool was the
thing that was wrong.

`Fold.test_slice` prepends the strategy's warm-up bars to the test range, so no fold begins
with a statistic computed from a truncated window; the engine then suppresses decisions over
exactly those bars. The benchmark is forced onto the **strategy's** warm-up so both legs cover
identical bars — otherwise the pairing compares two different date ranges and cancels nothing.

Pooled out-of-sample statistics are computed on the **concatenated** test folds. Averaging
per-fold Sharpes would weight a 40-bar fold like a 400-bar one.

---

## 5. Significance — FINDINGS §5c enforced in code

> DSR for anything with a return series that came out of a sweep. Permutation for classifiers.
> Paired differences whenever a common market move would otherwise dominate.

Both of that rule's failure modes are guarded here rather than left to memory:

- **False PASS (wrong benchmark).** `evaluate()` requires a benchmark and reports the DSR of
  the **paired excess** as `decision_instrument`. The strategy's own-return DSR is reported
  under the key `raw_dsr_DO_NOT_DECIDE_ON_THIS`, with the warning attached.
- **False FAIL (wrong object).** `deflated_sharpe` **refuses** a zero-variance series instead
  of returning a number — which is exactly what a self-differenced series or a classifier is.

`trials` is required everywhere, and `trials > 1` without a cross-trial Sharpe variance
**refuses**: defaulting it to zero would hand back an undeflated number under a deflated name.
Permutation shuffles the exposure path against fixed market returns, so every permutation
holds the same positions for the same number of bars and only the timing changes; p-values are
add-one corrected. A constant exposure permutes to itself and correctly gives p = 1.0.

---

## 6. Point-in-time discipline in the data, including where it is imperfect

Bars are fetched with `adjustment=all`, which is correct for **total return** and retroactive
for **price levels**: the adjusted price of a 2019 bar depends on splits and dividends that had
not happened in 2019. So any universe filter on a level — Zarattini's `open > $5`, `ATR >
$0.50` — must refetch with `adjustment='raw'`, and `assert_levels_are_point_in_time()` refuses
on an adjusted series to make that impossible to forget.

Every dataset manifest also records that Alpaca serves symbols existing **today**, so a
universe built from today's listings is survivorship-biased and this loader cannot fix it.
Responses are fully paged: a truncated response is a wrong answer, not a small one.

---

## 7. Execution, and the gate in front of it

`paper.py` defines the order schema and the endpoint guard. Backtest and live share one
`Strategy.on_bar`, so the tested code is the running code.

**`PaperBroker.submit()` refuses**, mirroring B22B's deliberately-absent collection stage. Two
independent gates stand in front of it: the endpoint (only `paper-api.alpaca.markets` is
constructible; hosts are matched on the **parsed hostname**, never a substring — `api.alpaca.
markets` is a substring of `paper-api.alpaca.markets` and a substring test is wrong in both
directions), and owner authorisation per PLAN.md's promotion gates. **Do not implement
`submit()` in place. Propose it as a diff.**

Credentials are read from the environment or `.env` with quotes stripped, and an empty result
refuses rather than producing a 401 that looks like missing data.

---

## 8. Arithmetic

Prices, fills, costs, turnover and **per-bar returns are exact** (integer micro-dollars and
`Fraction`). The rig declares exactly **two** float boundaries: `to_micros` at ingest (B22B's),
and the statistics layer. `BacktestResult.equity_curve_exact()` recomputes the curve in exact
rationals; a test pins the float path against it.

---

## 9. Files

| file | what |
|---|---|
| `frozen.py` | hash-verified bridge to the pinned B22B harness |
| `engine.py` | `Bar`, `PointInTimeView`, `Strategy`, `lookahead_audit`, `run_backtest` |
| `costs.py` | provenance-carrying cost model, stress ladder, frictionless diagnostic |
| `stats.py` | CAGR, Sharpe, maxDD, DSR, permutation, paired excess |
| `walkforward.py` | purged/embargoed folds and the independent leakage re-check |
| `data.py` | Alpaca loader, cache + manifest, point-in-time and endpoint guards |
| `strategies.py` | wiring smoke tests and the leaky negative control |
| `runner.py` | `walk_forward_run`, `single_run` |
| `paper.py` | order schema, paper-only broker, owner gate |
| `__main__.py` | CLI |
| `t4_forward.py` | **T4** — the paper forward test of the T13 vol-targeting overlay (see below) |
| `t4_entrypoint.sh` | T4 scheduler entrypoint; start/stop |
| `T4_FORWARD.md` | T4 operator manual and the protocol for reading its accruing log |
| `t16_free_panels.py` | **T16** — append-only collector for the free forward-data panels (FINRA short interest, FINRA Reg SHO daily short volume, Alpaca borrow flags, iborrowdesk borrow fee — the last of which is dead at the source). Collection only: no signal, no order, no purchase |
| `t16_entrypoint.sh` | T16 cron entrypoint; the crontab line is printed for the OWNER to install and is never installed by the bot |

Tests: `tests/test_t2_backtest_harness.py` (94 tests). Every guard is exercised on the
**failing** side, because FINDINGS §8 records that a layered guard hides its inner branches and
"no test reaches this branch" is never evidence the branch is dead.

---

## 10. What this rig does NOT do

It does not fit anything, rank anything, or contain an edge candidate. No number produced by
the shipped strategies is a finding: `TrailingSmaCross` is plumbing, and FINDINGS §5b already
killed that family's return claim (DSR 0.224–0.341, nine of ten lengths lose to buy-and-hold).
It does not model partial fills, queue position, market impact as a function of size, or
hard-to-borrow inventory. It does not correct survivorship.

`paper.py`'s `submit()` still refuses, and that has not changed. The one thing in this
directory that *can* construct an order lives in `t4_forward.py` — see §11.

---

## 11. T4 — the one thing here that runs forward

`t4_forward.py` is the paper forward test of the T13 volatility-targeting overlay. It is the
only module in this directory with a live schedule, and it is **not** an edge: T13 froze the
rule on 1929–1989 and it is **dead on the held-out gate** (drawdown `p = 0.233`, `DSR = 0.355`).
It runs forward because 1990–2026 is burned for it, so no backward test of it can be honest
again. **Its log is evidence being accrued, not evidence.**

```bash
python -m scripts.trading_bot.t4_forward selftest
python -m scripts.trading_bot.t4_forward session --dry-run --account-source broker
python -m scripts.trading_bot.t4_forward report
```

It reuses this rig rather than duplicating it: `frozen.py`'s pin, `costs.py`'s per-side T6
model with M0's measured auction rail, `data.py`'s loader and endpoint guard, `paper.py`'s
hostname guard and `orders_for_target`. The T13 weight arithmetic is imported from
`scripts/t13_risk_shaping.py` and cross-checked against an independent recomputation; a
disagreement refuses.

**Submission is gated on a file only the owner creates**
(`research/trading_bot/T4_OWNER_AUTHORISATION.json`), which does not exist. Dry-run computes,
sizes, prices and logs the identical order and sends nothing. The live endpoint remains
unreachable by hostname.

Read `T4_FORWARD.md` for start/stop and the reading protocol, and
`research/trading_bot/T4_FORWARD_PREREGISTRATION.md` for the frozen gates, the minimum sample,
and the list of claims the log may never support.
