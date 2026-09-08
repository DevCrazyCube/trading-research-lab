# T4 — the paper forward-test bot

**This is not a validated money-maker and nothing below should be read as one.** It runs the
T13 volatility-targeting overlay forward on an Alpaca **PAPER** account and writes an
append-only log. T13's verdict on this rule was **dead on the frozen gate** (drawdown
`p = 0.233`, `DSR = 0.355`); it is run forward because 1990–2026 is burned for it, not because
it was certified. **The log is the evidence being accrued. It is not yet evidence of anything.**

The rule, the gates, the minimum sample, and the list of claims this log may never support are
frozen in `research/trading_bot/T4_FORWARD_PREREGISTRATION.md`. Read that before reading a
number out of the ledger.

---

## 1. What it does, once per session

```
during session D, between 15:50 and 15:58 ET  -- the FINAL MINUTES, not mid-session
  1. verify the frozen rule           T13_PREREGISTRATION.md hash must still match
  2. fetch SPY daily closes           strictly before session D
  3. reconcile yesterday's order      fill price vs the official close, in bp
                                      a NON-FILL drops the decision it never executed
  4. settle whatever has printed      advance three equity curves + drawdowns
  5. compute the weight               w = min(1.0, 0.10 / realised_vol_60(through close D-1))
  6. size it                          whole shares, rounded down, against paper equity
  7. place a MARKET *DAY* ORDER       dry-run: logged and not sent.  submit: owner-gated
  8. append one JSON record           research/trading_bot/T4_FORWARD_LOG.jsonl
```

Step 5's weight is established by step 7's fill, a few minutes before close(D), and earns the
**next** session's return — which is what makes the live schedule reproduce T13-L1 exactly
rather than approximately. See the pre-registration §4.

### 1a. Why it is a market DAY order and not a market-on-close — read this before the rest

The original design placed a market-on-close order (`time_in_force = "cls"`). **On the Alpaca
PAPER account that order does not execute. It expires.** This is measured, not inferred:

| | |
|---|---|
| order | `3a5487f8-b9bc-46b2-89a1-f19ba46e964c` |
| submitted | 2026-08-17T13:50:54Z — 93 SPY, BUY, `type=market`, `tif=cls` |
| at the close | 2026-08-17T20:00:56Z — `status="expired"`, `filled_qty=0`, `filled_avg_price=null` |
| position after | none. `GET /v2/positions/SPY` → 404 |

Alpaca's paper simulator does not participate in the closing auction. The bot was scheduled,
firing, authorised and correct, and **every order it will ever place would expire** — zero
sessions settle and the forward test accrues nothing, forever, silently.

The mechanism is now `type=market, time_in_force=day`, submitted inside the action window. It
fills immediately against the paper book while the market is open.

**This was an execution change and nothing else.** The target weight, the reference close, the
sizing arithmetic and the whole-share rounding were verified byte-identical across the change on
a pinned clock: `target_weight = 0.7242369236978444`, `realised_vol = 0.13807636248289454`,
93 shares BUY, reference close `2026-08-14` — before and after. Only `type` and
`time_in_force` moved (`market_on_close`/`cls` → `market`/`day`).

**Two consequences, both stated rather than absorbed.**

1. **The priced rail is no longer the executed rail.** The cost model is still M0's auction
   rail (`measured_auction_leg`, a MEASURED zero half-spread), and M0 measured the *auction*,
   which this bot no longer trades. A near-close market order crosses the spread and takes a few
   minutes of drift. The auction-rail cost is therefore a **lower bound**, and
   `cost_if_taker_rail` (2.5 bp/side) is the better model of what is actually being paid. The
   primary model is deliberately **not** switched, because that would restate an accrual
   mid-flight; the frozen protocol already decides this — **FG4** measures the realised
   shortfall and prereg §5 restates the entire accrual at the taker rail if FG4 fails. Every
   record now carries `costs.rail_note` saying exactly this.
2. **`shortfall_bp_adverse_positive` changed meaning.** It is now *near-close market fill vs the
   official closing print*, not *auction fill vs the print*. The drift is unbiased, so the
   **median** — which is what FG4's 2 bp threshold gates on — is still the right statistic and
   the gate is read unchanged; the **dispersion** will be wider than an auction fill's, and that
   is expected. Records before and after 2026-08-18 are the same field and not the same
   measurement.

### 1b. A non-fill now cancels its own decision

The expired order exposed a second, worse bug. Nothing noticed the non-fill: the decision the
order was meant to execute stayed queued in `pending_weights`, and two runs later it would have
been filed into `weight_changes` and **settled** — accruing a curve for a position the account
never held. A phantom weight is indistinguishable from a real one in the PnL.

`reconcile_fill` now resolves an outstanding order into exactly one of three states:

| broker says | what happens |
|---|---|
| `filled_qty > 0` | the decision stands. A **partial** fill is flagged `partial_fill_warning` and left for FG3 rather than silently re-derived |
| terminal with `filled_qty == 0` (`expired`, `canceled`, `rejected`, `done_for_day`, …) | **the pending weight is dropped.** No position was established, so no weight change occurred and the previous weight stayed in force — which is what the account actually did |
| still live at the broker | order **and** decision are left outstanding and re-asked next run. Dropping either would be guessing |

### 1c. The schedule is now part of the execution price

A market DAY order fills **when it is sent**, so the firing minute *is* the execution price.
Two guards, deliberately independent:

- `ACTION_WINDOW_ET = ((15,50), (15,58))` — outside it, `--skip-outside-window` exits 0 and
  `--mode submit` refuses.
- `SUBMIT_HARD_CUTOFF_ET = (15,59)` — a separate named guard, because an order landing after
  16:00 queues to the **next open** and would establish the weight one session late at a price
  from the wrong session. A future widening of the window cannot silently defeat it.

15:50 is the lower bound specifically because the **installed** crontab is `*/10 12-23 * * 1-5`,
which fires on ten-minute marks; a 15:55–15:58 window would be tighter to the close and would
**never fire**. One attempt per day is thin, so:

> **RECOMMENDED (not applied — requires a crontab edit):**
> ```
> crontab -e
> -  */10 12-23 * * 1-5 /home/anont/meme/scripts/trading_bot/t4_entrypoint.sh
> +  50-58 12-23 * * 1-5 /home/anont/meme/scripts/trading_bot/t4_entrypoint.sh
> ```
> Nine attempts in the window instead of one; the first success wins and the rest are no-ops.
> The bot's own Eastern-time check is what actually decides, so the broad hour range is safe
> across every combination of US and EU DST.

## 2. Start

```bash
# one session, by hand, nothing leaves the process
python -m scripts.trading_bot.t4_forward session --dry-run --account-source broker

# scheduled. Safe to fire every ten minutes: it is a no-op outside the window and a no-op
# once the session is logged.
crontab -e
*/10 13-21 * * 1-5 /home/anont/meme/scripts/trading_bot/t4_entrypoint.sh
```

`13-21` UTC brackets 09:00–17:00 ET across both DST offsets; the bot does the precise Eastern
windowing itself, per day, from the frozen `et_offset_hours`.

**Modes.**

| flag | what it does | reaches the network |
|---|---|---|
| `--dry-run --account-source simulated --equity N` | computes and logs against a stated notional | market data only |
| `--dry-run --account-source broker` | sizes against the **real paper account** equity and position | market data + paper GETs |
| `--mode submit --account-source broker` | places the near-close market DAY order | + one paper POST, **owner-gated** |
| `--offline` | cache only; refuses rather than fetching | nothing |

## 3. Stop

| you want | do this |
|---|---|
| stop everything | remove the crontab line |
| stop **orders**, keep the record accruing | `rm research/trading_bot/T4_OWNER_AUTHORISATION.json` |
| same, from the scheduler side | `T4_MODE=dry-run` |
| start over with a clean ledger | delete `T4_FORWARD_LOG.jsonl` **and** `T4_FORWARD_STATE.json` together — they are one unit, and a state file without its ledger is a curve with no audit trail |

Deleting the authorisation file is the intended stop switch: the bot keeps computing, settling
and logging, and simply stops sending. That is the mode you want during any investigation,
because a bot that stops logging stops being evidence.

## 4. The owner gate, stated plainly

**Order submission — even to the paper endpoint — does not happen until the owner creates**

```
research/trading_bot/T4_OWNER_AUTHORISATION.json
{"paper_order_submission_authorised": true,
 "authorised_by": "<owner>", "authorised_utc": "<iso8601>"}
```

The file does not exist and this bot did not create it. `scripts/trading_bot/paper.py` records
the standing position that explicit owner sign-off is required before any order leaves this
process, **paper or otherwise**, and an agent's task brief is not that sign-off.

The **live** endpoint is a different matter entirely: it is unreachable from this rig by
hostname, there is no flag or file that reaches it, and `PaperBroker` refuses it at construction
time rather than at submission time. Funding a real account is out of scope for this document.

## 5. Reading the accruing track record

```bash
python -m scripts.trading_bot.t4_forward status      # rule, gate state, curves
python -m scripts.trading_bot.t4_forward report      # + weight distribution and this protocol
python -m scripts.trading_bot.forward_eval report    # the full EVALUATION -- start here
python -m scripts.trading_bot.forward_eval status-line
tail -n 1 research/trading_bot/T4_FORWARD_LOG.jsonl | python3 -m json.tool
```

> **`forward_eval` is the one to read.** `t4_forward report` is the bot describing itself;
> `forward_eval report` is a separate read-only evaluator that recomputes everything from the
> ledger, including the **vol-matched null** and the **certifiability arithmetic** (how many more
> crashes and sessions before anything is licensable). It runs daily from
> `scripts/trading_bot/t4_eval_entrypoint.sh`. It cannot write a ledger, a state file or a
> pre-registration — those paths refuse.

**In this order, and the order matters.**

**1. Start with the denominator, not the equity.** `years_elapsed` is the only field that moves
this from behaviour to evidence. The pre-registration's minimum is **three completed crash
episodes**, and crashes arrive about one per nine years. Under a decade, `equity` is a
description of the weather.

**2. The comparison that matters is not the one in `equity`.** Beating buy-and-hold is not the
question. The question is whether the overlay beats **a constant weight vol-matched to it** —
"you could have just held less" — and that null is what killed both T13 families and killed
funding carry before them. **`forward_eval` computes it** (`drawdown.vs_vol_matched_null_N1`)
as soon as there is a forward sample with a realised volatility worth matching, and it refuses
to print `delta_maxdd_vs_benchmark_pp` without labelling it `DIAGNOSTIC_ONLY`.

**3. A good stretch without a crash is not information about crashes.** The whole claim is about
the left tail. Calm-market underperformance is the **known** price of a mean exposure near 0.74
and is not a surprise; calm-market outperformance is noise on the question being asked.

**4. Check the rail before you check the PnL.** On every settled session compare
`cost.total_bp` against `cost_if_taker_rail.total_bp`, and on every reconciled fill read
`fill_reconciliation.shortfall_bp_adverse_positive` and `position_established`. Positive
shortfall means the fill was **worse** than the official close. This is the one assumption the
whole accrual leans on, and since 2026-08-18 it is **known** to be violated in kind if not yet
in magnitude: the priced rail is M0's auction and the executed rail is a near-close market
order (see §1a). It is also the one thing here that accrues fast enough to be answered. A
persistent positive drift means the accrual must be restated at the taker rail **before** any
other gate is read.

**5. Check that the weight moved when volatility did.** `decision.realised_vol_annual` up must
mean `decision.target_weight` down. If it does not, the implementation is broken and the PnL is
irrelevant regardless of its sign.

**6. Three curves, and they answer different questions.**

| curve | what it is | compare it to |
|---|---|---|
| `model_withcash` | the T13 rule with its cash leg at the T-bill rate | T13's backtest, and eventually the vol-matched null |
| `model_excash` | the same fills with idle cash earning nothing | the paper account, which pays no interest |
| `benchmark` | un-overlaid buy-and-hold, one entry charged | a diagnostic only — see point 2 |

**7. Nothing here is a reason to fund a live account.** Live execution is owner-gated and this
log cannot promote itself.

## 6. Files

| path | what |
|---|---|
| `scripts/trading_bot/t4_forward.py` | the bot |
| `scripts/trading_bot/t4_entrypoint.sh` | scheduler entrypoint |
| `research/trading_bot/T4_FORWARD_PREREGISTRATION.md` | the frozen protocol — rule, gates, minimum sample, prohibited claims |
| `research/trading_bot/T4_FORWARD_LOG.jsonl` | append-only, one record per run |
| `research/trading_bot/T4_FORWARD_STATE.json` | running curves, peaks, drawdowns, queued decisions |
| `research/trading_bot/T4_CASH_RATE.csv` | the bot's own FRED DTB3 series; the T13 artifact is never mutated |
| `research/trading_bot/logs/t4_forward.*.log` | scheduler stdout/stderr |
| `tests/test_t4_forward.py` | 52 hermetic tests |
| `scripts/trading_bot/forward_eval.py` | **the read-only evaluator** — PnL, exposure, both nulls, certifiability |
| `scripts/trading_bot/t4_eval_entrypoint.sh` | daily evaluate step + the cron line |
| `research/trading_bot/ITERATION_PROTOCOL.md` | **how a new idea is stood up, and how a running one is retired** |
| `research/trading_bot/FORWARD_REGISTER.json` | the register of forward tests; hashes enforced |
| `research/trading_bot/FORWARD_EVAL.json` | the latest evaluation, rewritten daily |
| `research/trading_bot/FORWARD_STATUS.txt` | the one-line status the dashboard surfaces |
| `tests/test_forward_eval.py` | 46 hermetic tests for the evaluator |

## 7. Things it deliberately will not do

- **Backfill.** A bar dated at or after the session refuses. A forward test that can be
  backfilled is a backtest with a different filename.
- **Accrue a weight it did not fill.** A terminal non-fill drops its own decision (§1b). The
  ledger may under-report what the strategy wanted; it may never over-report what the account
  held.
- **Send an order that fills in the wrong session.** Past 15:59 ET it refuses rather than let a
  market DAY order queue to the next open.
- **Recompute history.** Curves advance one session at a time and are never rebuilt, because
  `adjustment=all` retroactively revises past closes at each dividend and a forward test whose
  past silently moves is not one.
- **Add a rebalance band.** The frozen rule has none. Whole-share rounding is the only deadband
  and it is reported rather than absorbed into the rule.
- **Short, or lever.** `w_max = 1.0`. The cost model carries a borrow term anyway, so a future
  variant that shorts cannot inherit a silent zero.
- **Guess a cost.** Absence refuses. An unmeasured leg is charged an adverse proxy and labelled
  as one.
- **Grant itself an authorisation.**
