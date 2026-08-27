# ITERATION PROTOCOL — how this programme is allowed to get better

**Written 2026-08-17 (T19), while the only running forward test had `0` settled sessions and no
result of any kind existed to be tempted by.** That timing is the point. A protocol written after
a bad month is a rationalisation; this one was written when there was nothing to rationalise.

**Scope.** Every PAPER forward test in `research/trading_bot/FORWARD_REGISTER.json`, starting with
T4. It governs what an evaluation may cause, how a new idea is stood up, and how a running
strategy is retired.

---

## 0. The one sentence

> **A running strategy's rule is immutable. Improvement is a NEW pre-registered forward test with
> its own ledger, judged only on data that printed after it was frozen. There is no third option.**

---

## 1. The failure mode this document exists to prevent

The owner asked for a *trade → evaluate → improve* loop. The loop has a well-known way of eating
itself, and it is worth naming precisely because it does not feel like cheating while you do it:

    run the bot -> look at the last few weeks -> "the 60-day lookback reacted too slowly in
    that drop" -> change it to 40 -> the curve looks better -> ship it

Every step is locally reasonable. The result is a rule fitted to the noise in a handful of
observations, carrying the *provenance of a forward test* — which is exactly what makes it
dangerous. A backtest that overfits is at least labelled a backtest. A forward test that was
edited mid-flight looks like out-of-sample evidence and is not.

**This programme has already priced that error.** `FINDINGS.md` §5: a `+0.48 %` result at 43 %
volatility carried a Deflated Sharpe of **0.176** — *below the chance ceiling* — because the search
that produced it was counted honestly. T3 died at **DSR 0.9379**, missing a threshold frozen in
advance by 0.012, and it stayed dead. The discipline is the only reason those numbers mean
anything, and it costs nothing to keep until the day it costs everything to break.

**Second failure mode, less discussed and equally fatal: the silent restart.** Deleting a ledger
after a bad stretch and "starting clean" is a selection on the outcome. `FORWARD_REGISTER.json`
keeps retired entries forever for this reason (§7).

---

## 2. What an evaluation may and may not cause

`scripts/trading_bot/forward_eval.py` reads the ledger and reports. It cannot write one —
`_refuse_if_protected()` refuses any path ending `_LOG.jsonl`, `_STATE.json`,
`_AUTHORISATION.json`, `_PREREGISTRATION.md/.json`, `_FROZEN_CONFIG.json` or
`FORWARD_REGISTER.json`. That is a guard in code, not a promise in prose.

| what the evaluation shows | permitted response |
|---|---|
| the curve is down / up over the last N days | **none.** Not a permitted input to anything. |
| the drawdown gate FG1 is not met yet | **none.** It is not readable before the §6 minimum. |
| a parameter "would obviously have been better" | **write it down as a candidate (§4). Do not touch the running rule.** |
| FG3 fidelity mismatch — a weight in force ≠ the frozen rule's weight | **STOP the bot. The window is invalidated.** Reconcile, then §7 decides whether the ledger restarts under a new pre-registration. |
| FG4 rail failure — fills drifting off the official close | **restate the whole accrual at the taker rail before FG1 is read**, per T4 prereg §5. This is a *cost-model* correction the pre-registration already authorised, not a rule change. |
| the pre-registration's sha256 no longer matches the register | **the evaluator refuses to score it.** Restore the document. Never update the hash. |
| an operational gap > 5 sessions | record the discontinuity (T4 prereg §7). The curve is continuous; the operational record is not. |
| a genuinely new idea | **§4.** A new ledger, a new freeze, a new trial count. |

**The two things that are never a permitted response, at any sample size:** editing a running
rule, and restarting a running ledger.

---

## 3. The distinction that does the work: *maintenance* vs *rule change*

The rule is the object under test. Everything else is plumbing, and plumbing may be repaired.
The test is: **would the fix change the weight the strategy targets on a day it already
traded?** If yes, it is a rule change and needs §4. If no, it is maintenance.

| maintenance — allowed, logged in `DECISIONS.md` | rule change — §4 only |
|---|---|
| fixing a crash, a retry, a timeout, a log field | `L`, `target`, `w_max` |
| a broker API migration that places the same order | the instrument, the universe |
| restating costs at the taker rail when FG4 says so (already authorised) | the execution rail or order type |
| adding a *read-only* metric to the evaluator | the cost model, other than an authorised restatement |
| correcting a data-vendor bar that the vendor itself revised | the rebalance schedule, adding a band or threshold |
| widening the evaluator's disclaimers | the benchmark or the null |

**Ambiguous cases go to the owner as a scope call with a recommendation, not to the agent's own
judgement.** Both a rule change and a "small fix" reported as maintenance carry the same
consequence if wrong: the ledger stops meaning what it claims.

---

## 4. Standing up a NEW forward test — the only permitted form of improvement

Steps in order. **Each one must be complete before the next begins**, and steps 1–5 happen before
a single live datum is touched.

**1. Write the candidate down, with its prior.** One paragraph: the mechanism, why it should
exist, what the literature says the effect size is, and — required — *what would make it false*.
No code. `EDGE_SHORTLIST.md` is where these live.

**2. POWER GATE FIRST, and freeze it before computing it.** This is `FINDINGS.md` §5g's earned
rule and it is not optional. Declare, in a document that is then hashed:

- the benchmark effect size, sourced, and why that figure rather than a more flattering one;
- the acceptance criterion (`MDE ≤ benchmark effect`);
- the count of independent observations the instrument can actually deliver.

**T15 is the precedent that justifies the ordering: it was killed by its own power gate *before*
it was tested, and the held-out window was never burned.** The scoping arithmetic that had
promoted it was wrong by 9.8×. A power gate computed after the MDE is not a gate.

For a *drawdown-shaping* candidate the unit of observation is a **crash episode**, not a session.
T4's arithmetic — 6.00 pp mean advantage, sd 6.84, ~1 crash per 9 years ⇒ 10.2 crashes ≈ 92 years
for 80 % power — is the honest template. Most candidates die here, cheaply, which is the point.

**3. Declare the trial count honestly, and include the ones you are not running.** Every
configuration considered, plus every forward test ever stood up in the same family (the register's
`declared_trial_accounting`). DSR is computed at that number. Under-declaring trials is the
mechanism by which a chance maximum becomes a discovery.

**4. Write the pre-registration.** It must contain, at minimum:

- the rule, in closed form, with every parameter and its provenance;
- the instrument, rail, account, sizing and rebalance schedule;
- the cost model, **per side**, with each charge's provenance;
- the timing convention and the mechanism that *enforces* it (T4-L1 holds by construction because
  the data request window ends before the session; an assertion in prose is not a mechanism);
- **the null** — for anything that reshapes risk, the ex-post vol-matched constant weight, not
  buy-and-hold. T13 §5i records what happens when the easy benchmark is used instead;
- the gates, with thresholds, and the minimum sample below which **no verdict** is issued;
- kill conditions;
- an explicit list of claims the log may **never** support;
- the honest expectation, stated in years, so nobody discovers the horizon in year twelve.

**5. Freeze it.** Hash the document. Pin the runner's hash if it imports frozen arithmetic. The
runner must verify the hash at start-up and **refuse to run** if the document moved.

**6. Register it.** A new entry in `FORWARD_REGISTER.json` with `status: "RUNNING"`, a **new**
`id`, a **new** ledger path, and the pre-registration's hash. Never reuse an existing ledger, and
never point two entries at one file.

**7. Run it dry, then paper.** `selftest` → `session --dry-run` → owner authorisation → `submit`.
Order submission stays gated on `T4_OWNER_AUTHORISATION.json`; live money stays owner-gated and
this protocol does not reach it.

**8. Evaluate it read-only, on the schedule, and act on it only per §2.**

> **The bar is deliberately high and it is supposed to hurt.** If a candidate is not worth eight
> steps, it is not worth the provenance of a forward test.

### 4b. Two forward tests may run at once. Three rules govern it.

- **Separate ledgers, separate registers entries, separate state.** Never a shared file.
- **Both count as trials** for the family's DSR, forever, including after retirement.
- **A variant of a running rule is not a hedge; it is a search.** Standing up `L = 40` beside
  `L = 60` and later reporting the better one is a two-trial search reported as one test. If both
  run, both are declared, and the DSR is computed at the honest trial count. This is permitted;
  concealing it is not.

---

## 5. Cadence — who reads what, and how often

| when | what | who |
|---|---|---|
| every session, in-window | `t4_entrypoint.sh` — decide, size, place, log | cron |
| every session, 16:30 ET | `t4_eval_entrypoint.sh` — the read-only report + status line | cron |
| weekly | read `FORWARD_STATUS.txt`; open the full report only if a gate flag moved | owner |
| when FG3 or FG4 flags | act per §2 immediately | agent, then owner |
| when a crash episode completes | record it; **still no verdict below the minimum** | agent |
| when the §6 minimum is met | read the gates in the frozen order and publish the verdict, pass or dead | owner-gated |

**The expected reading on almost every day is "no change, the sample has not moved."** An
evaluator that produces an action item most days is an evaluator that is fitting noise.

---

## 6. What a "better" version of the loop looks like, concretely

Because "pre-register a new test" is abstract, here is what the *next* honest step for this
programme actually is, in priority order — and note that none of them is a tweak to T4:

1. **Let FG4 accrue.** ~300 clean on-close fills bounds the non-fill rate under 1 % by the rule of
   three. That is a year of sessions, not a career, and **four dead candidates in this programme
   rest on the auction rail being what M0 measured**. It is the highest-information-per-day thing
   the current rig produces, and it requires zero new code.
2. **A candidate whose unit of observation is not a crash.** T4's horizon is ~92 years because a
   left-tail claim gets one observation per crash. A candidate measured per *session* or per
   *event* can be certified inside a career. The power gate (§4 step 2) is where that is decided,
   before anything is built.
3. **A classifier rather than a return series.** `FINDINGS.md` §5c: both survivors of this whole
   programme are distribution-shape claims — a drawdown reduction and a screen — and neither
   needed a certifiable Sharpe. That is not a coincidence; it is the resolution arithmetic.

---

## 7. Retiring a running strategy

A strategy is retired when **any one** of these is true. All are declared here in advance, so a
retirement is a rule being applied rather than a judgement being made:

| condition | verdict recorded |
|---|---|
| a frozen gate fails once the minimum sample is met | **DEAD** — on the gate, named |
| a kill condition in its own pre-registration fires | **DEAD** — on that condition |
| FG3 fidelity mismatch that cannot be reconciled | **INVALIDATED** — not dead, *unmeasurable*; the distinction matters |
| the rail assumption fails and the restated accrual then fails a gate | **DEAD at the taker rail** |
| the instrument, venue or data source stops existing | **DISCONTINUED** — no verdict; say so |
| superseded by a new test the owner prefers to fund | **RETIRED — SUPERSEDED**, explicitly not a verdict on the rule |
| the owner stops it | **RETIRED — OWNER CALL** |

**Retirement mechanics, and none of them is optional:**

1. Set `status` to the verdict above in `FORWARD_REGISTER.json`; fill `retired_utc` and
   `retirement_reason`.
2. **The ledger is closed, never deleted, never edited, never appended to again.** It stays in
   `research/trading_bot/` forever.
3. Write a short `Tn_FORWARD_RESULT.md` stating the verdict, the gate that decided it, the sample
   at the point of retirement, and — if it died — that it died. `FINDINGS.md` gets one row.
4. The entry keeps counting toward the family's declared trial number **permanently**.
5. Delete the cron line and, for a paper-trading strategy, remove the authorisation file.

> **A retired loser is evidence and is kept.** A programme that quietly deletes its failures has a
> 100 % hit rate and no information. Every negative in `FINDINGS.md` was worth more than the
> positives it displaced.

---

## 8. Forbidden moves — the explicit list

Written out because "don't overfit" is too abstract to catch anyone in the act.

1. Changing `L`, `target`, `w_max`, the instrument, the rail or the cost model of a **running**
   test, for any reason, including "it obviously should have been X".
2. Restarting, truncating, re-basing or "cleaning" a ledger. Ever.
3. Reading a gate before its declared minimum sample and describing the reading as promising.
4. Reporting `delta_maxdd_vs_benchmark_pp` without the vol-matched null beside it.
5. Annualising, or computing a CAGR, Sharpe or p-value from a short forward sample and quoting it
   outside the `inputs_that_are_not_results` block.
6. Standing up a variant and later reporting only the better of the two.
7. Updating a pre-registration's recorded hash to match a document that moved.
8. Extending, relaxing or reinterpreting a minimum sample **after** seeing the data.
9. Adding an instrument or a symbol to a running ledger.
10. Treating a calm stretch as evidence about the left tail — in either direction.
11. Promoting anything to live money on the strength of a paper log. **Live execution is
    owner-gated and this protocol does not reach it.**

---

## 9. Register of forward tests

Canonical machine-readable copy: `research/trading_bot/FORWARD_REGISTER.json`.

| id | rule | status | inception | minimum before verdict | declared trials |
|---|---|---|---|---|---|
| **T4** | `w = min(1.0, 0.10 / realised_vol_60)` on SPY, MOC both sides, Alpaca paper | **RUNNING** | 2026-08-17 | 3 completed ≥20 % crash episodes | 1 |

**T4's prior verdict, restated so no reader mistakes "running" for "working":** it is **DEAD on
T13's frozen held-out gate** (drawdown p = 0.233, DSR = 0.355). It runs forward because 1990–2026
is burned for this rule and a prospective test is the only honest instrument left — **not** because
it was certified, and **not** because anyone expects it to be.

---

## 10. Reproduction

```bash
python -m scripts.trading_bot.forward_eval selftest          # hermetic; no network, no ledger
python -m scripts.trading_bot.forward_eval report            # the full page
python -m scripts.trading_bot.forward_eval report --json --write
python -m scripts.trading_bot.forward_eval status-line       # the dashboard line
python -m scripts.trading_bot.forward_eval list              # the register
python -m pytest tests/test_forward_eval.py -q
```

Daily cron (`scripts/trading_bot/t4_eval_entrypoint.sh` documents both zone variants):

```cron
30 22 * * 1-5 /home/anont/meme/scripts/trading_bot/t4_eval_entrypoint.sh
```
