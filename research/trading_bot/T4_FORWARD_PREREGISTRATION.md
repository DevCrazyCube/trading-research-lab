# T4 — pre-registration of the PROSPECTIVE test of the T13 volatility-targeting overlay

**Status:** frozen before any evidence accrued. Written 2026-08-17, the same day the ledger was
opened and while it contained **one run record and zero settled sessions**.

**Instrument of record:** `research/trading_bot/T4_FORWARD_LOG.jsonl` (append-only) plus
`T4_FORWARD_STATE.json` (the running curves).
**Implementation:** `scripts/trading_bot/t4_forward.py`. **Operator manual:**
`scripts/trading_bot/T4_FORWARD.md`.

---

## 0. The one-paragraph honest summary

T13 froze a volatility-targeting overlay on 1929–1989 and tested it on 1990–2026. **It is dead
on the frozen gate.** Its `+7.25 pp` drawdown advantage over the ex-post vol-matched
buy-and-hold null carries **p = 0.233** and **DSR = 0.355**, and the headline is essentially
2008 alone. What survived is *behaviour*: the sign is positive in all four decades and all
eight declared configurations, the rule is cheap, and volatility clustering is the most robust
regularity in the field. What killed it is *power*: a drawdown claim gets one observation per
crash. **1990–2026 is now burned for this rule**, so it cannot be re-run backward. This
document freezes what running it *forward* is allowed to conclude, before the first session
settles — and §6 states plainly that on the observed effect size **this test will almost
certainly never certify anything**, so that nobody discovers that in year twelve.

---

## 1. The rule under test — inherited, not chosen here

    w_t = min(w_max, target / realised_vol_L)

| parameter | value | where it comes from |
|---|---|---|
| `L` | 60 daily returns | `T13_FROZEN_CONFIG.json` → `frozen_vol` |
| `target` | 0.10 annualised | ditto |
| `w_max` | 1.0 (no leverage) | ditto |
| realised vol | annualised stdev (population, ÷L) of the last `L` daily simple returns | `t13_risk_shaping.vol_exposure` |
| remainder | cash, at the 3-month T-bill rate (FRED DTB3) | T13 §3 |

**No parameter is selected in T4.** The grid was declared and searched in T13, the freeze
happened before its held-out window, and this document inherits the winner unchanged.
**Declared trials for T4 = 1.** Any future change to `L`, `target`, `w_max`, the instrument,
the execution rail, or the cost model **starts a new ledger under a new pre-registration**; the
existing ledger is never extended across a rule change. `load_state` refuses to open a ledger
whose `rule_id` no longer matches.

**Integrity.** `t4_forward.frozen_rule()` verifies the SHA-256 of `T13_PREREGISTRATION.md`
against the hash recorded in `T13_FROZEN_CONFIG.json` on every run
(`0eda5f7aa65b91cc5532b5ba734d5168746a9fb5b65548a3457b2b7e407745da`) and refuses if the
document has moved. The arithmetic is **imported** from `scripts/t13_risk_shaping.py`, not
copied, and cross-checked against an independent recomputation in `t4_forward.py`; a
disagreement of more than `1e-12` refuses rather than sizes a position.

## 2. Instrument, rail, and account

| | |
|---|---|
| instrument | **SPY** — T13's confirmatory instrument; `^SP500TR` is not tradeable |
| price series | Alpaca SIP daily bars, `adjustment=all` (total return) |
| execution | **market-on-close both sides** (Alpaca `type=market, time_in_force=cls`) |
| account | **Alpaca PAPER only.** The live endpoint is unreachable by hostname, not by policy |
| sizing | whole shares, rounded **down** in absolute value |
| rebalance | every session, to the exact frozen weight — **no band, no threshold**. Whole-share rounding supplies the only deadband, and it is reported (`projected_weight_after_rounding`) rather than treated as part of the rule |

## 3. Cost model — frozen here, before any accrual

Per side, as T6 requires. There is no side-agnostic number.

| leg | half-spread | extra slippage | provenance |
|---|---|---|---|
| entry (MOC) | **0 bp** | 0.0019 bp | `MEASURED_M0_AUCTION_PRINT`, ADV tier `A_rank_1_50` |
| exit (MOC) | **0 bp** | 0.0019 bp | same |
| sell side only | **SEC 31: 0.278 bp** + FINRA TAF $0.000166/share | — | statutory schedule |
| commission | 0 | — | Alpaca schedule |

**Why the zeros are measurements and not omissions.** M0 measured that an official closing
print exists on **99.89 %** of tier-A symbol-days and clears a median **$104.7 M**, so a
retail-sized on-close order is not the auction and has no bid-ask to cross. The residual
`auction_non_fill_provision` is charged. **Tier assignment:** SPY's dollar volume exceeds every
tier-A constituent's, so tier A is the least favourable measured tier that can apply to it —
this is not an extrapolation down the liquidity ladder, which `measured_auction_leg` refuses
outright.

**Why SEC 31 and TAF are charged separately.** `retail_taker_costs()` describes them as folded
into a 2.5 bp half-spread's round-up. This model's half-spread is a measured **zero**, so there
is nothing to fold them into and they must be named. The $8.30 TAF per-order cap is deliberately
**not** applied: leaving it off is the adverse side.

**A stress rail is logged beside every accrual.** `cost_if_taker_rail` prices the identical
turnover at `retail_taker_costs()` (2.5 bp per side). The auction rail is the one assumption
this accrual leans on, and §5's FG4 is the gate that decides whether it survives contact.

## 4. Timing — T13-L1, enforced by the schedule rather than asserted

T13-L1: the exposure applied to session *t*'s close-to-close return uses closes through *t−2*.

    run during session D, inside 09:45–15:45 ET
      newest printed close is close(D−1)
      w  <- min(1.0, 0.10 / realised_vol_60(returns ending at close(D−1)))
      place MOC  -> weight established at close(D)
      weight earns close(D) -> close(D+1), i.e. session D+1
      (D+1) − 2 = D−1.   The convention holds by construction.

Three mechanisms keep it honest, and each can refuse:

1. the market-data request window **ends the calendar day before the session**, so a
   later close is not merely unused — it is not fetched;
2. a bar dated on or after the session refuses outright;
3. the weight for each settled session is recomputed from the frozen `vol_exposure` in the
   verification harness and must match bar for bar. **Measured 2026-08-17: 58 replayed
   sessions, 58 weights checked, 0 mismatches.**

**A weight persists until something moves it.** If the bot does not run on a session, no order
is placed and the previous weight really did stay in force; settlement carries it forward
rather than inventing a change. A gap of **more than five consecutive sessions** is a recorded
discontinuity (§7).

## 5. The gates — declared now, evaluated only when §6's minimum is met

Let `F` be the forward-accrued overlay curve (`model_withcash`) and let `N1` be the **ex-post
volatility-matched constant-weight buy-and-hold** over the *same forward window*: a constant
`w*` in SPY plus T-bills whose realised annualised volatility equals `F`'s, solved by bisection.
`N1` is fitted with hindsight `F` never gets. That is deliberate, and it is the gate that killed
both T13 families.

| gate | test | threshold |
|---|---|---|
| **FG1 (primary)** | ΔmaxDD of `F` against `N1` | ≥ **3 pp** better **and** p < 0.05 by paired block bootstrap (block = 21 sessions, 10,000 draws) |
| **FG2** | ΔCAGR of `F` against `N1` | ≥ **−0.5 %/yr** |
| **FG3** | fidelity | every settled weight equals `vol_exposure` on the same closes; **one mismatch invalidates the window** |
| **FG4** | the rail assumption | median adverse `shortfall_bp` of on-close fills ≤ **2 bp** and the fill rate ≥ 99 %. If it fails, the entire accrual is **restated at the taker rail** before FG1 is read — not after |
| **FG5** | DSR | ≥ 0.95 at **1** declared trial |

**The un-overlaid buy-and-hold benchmark logged beside the curves is a diagnostic, not a gate.**
Beating 100 % exposure is the easy comparison and T13 §5i records exactly this error about G3.
`delta_maxdd_vs_benchmark_pp` may never be reported without `N1`.

**Verdict logic.** All of FG1–FG5 pass → the overlay is certified *for drawdown shaping only*,
and still licenses no return claim. Any gate fails → **DEAD**, recorded as such. §6's minimum
not met → **NO VERDICT**, which is neither a pass nor a "promising".

## 6. The minimum sample, and the honest expectation

**Crash episode (frozen definition).** A peak-to-trough decline of ≥ **20 %** in the un-overlaid
benchmark curve, measured from its running peak. The episode runs peak → trough.

**FG-minimum: no verdict is issued below 3 completed crash episodes.** That is the number the
T13 held-out window had, and it failed at that number.

**And here is the part that must not be discovered later.** T13 measured the per-crash advantage
at **6.00 pp with sd 6.84 across n = 3**. At that effect size and dispersion, a two-sided test at
α = 0.05 needs

| power | crashes required | years at ~1 per 9 |
|---|---|---|
| 50 % | 5.0 | ~45 |
| 80 % | 10.2 | ~92 |
| 90 % | 13.7 | ~123 |

**So this forward test is not expected to certify the overlay. It is expected to accrue an
honest record that a certification would need and that no shorter instrument can produce.**
Three things do accrue on a useful timescale and are the practical reasons to run it:

1. **an execution measurement** — every fill is one observation of whether the broker's
   on-close order joins the cross M0 measured, which is the live half M0 explicitly did not
   claim, and it accrues **daily**;
2. **a behavioural check** — that exposure really falls into rising realised volatility outside
   the window the behaviour was observed in;
3. **a working, verifiable bot** on the safe side of the owner gate.

Stating this now is the point of a pre-registration. **A decade-scale commitment is an owner
scope call, not a technical one** (T13 §9).

## 7. Kill, restart, and discontinuity conditions

| condition | consequence |
|---|---|
| `T13_PREREGISTRATION.md` hash moves | the bot refuses to start. Restore the document; do not update the hash |
| the two weight implementations disagree | refuses to size. The window is invalidated until reconciled |
| any change to rule / instrument / rail / cost model | **new ledger, new pre-registration.** The old one is closed, not extended |
| > 5 consecutive sessions missing | recorded as a discontinuity in the result document; the curve is continuous but the *operational* record is not |
| FG4 fails | the accrual is restated at the taker rail before any other gate is read |
| the account is funded with real money | **out of scope and owner-gated.** This document covers a paper account only |

## 8. What this log may never be used to claim

- that the overlay makes money;
- that it beats buy-and-hold;
- that it reduces the drawdown an owner will live through;
- any CAGR, Sharpe, information ratio, or p-value computed before §6's minimum is met;
- that a calm stretch without a crash is evidence about crashes. **The claim under test is
  entirely about the left tail.** Calm-market underperformance is the *known* price of a mean
  exposure near 0.74 and is not a surprise; calm-market outperformance is noise on the question.

`track_record()` ships `certifiable: false`, an empty `claims_licensed`, and an explicit
`claims_explicitly_not_licensed` on every record, so a number lifted out of this ledger carries
its own restrictions with it.

## 9. Reproduction

```bash
python -m scripts.trading_bot.t4_forward selftest      # synthetic wiring check, no network
python -m scripts.trading_bot.t4_forward session --dry-run --account-source broker
python -m scripts.trading_bot.t4_forward report
python -m pytest tests/test_t4_forward.py -q           # 52 tests, hermetic
```

| artifact | what |
|---|---|
| `scripts/trading_bot/t4_forward.py` | the bot |
| `scripts/trading_bot/t4_entrypoint.sh` | scheduler entrypoint; start/stop |
| `scripts/trading_bot/T4_FORWARD.md` | operator manual and the reading protocol |
| `research/trading_bot/T4_FORWARD_LOG.jsonl` | the append-only evidence |
| `research/trading_bot/T4_FORWARD_STATE.json` | the running curves |
| `research/trading_bot/T4_OWNER_AUTHORISATION.json` | **absent by design.** The owner creates it to permit paper order submission; deleting it is the stop switch |
